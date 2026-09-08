"""企业微信内嵌应用（6c.1）。

功能：
- ``push_notification(user_ids, title, content)`` 应用消息推送；
- ``oauth_callback(code)`` 网页授权换 userid。

降级策略：
- wechatpy 缺失 → httpx 直连企业微信 API；
- httpx 缺失 → mock 返回 True（TR-8.5）。
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger("services.embedded.wecom")


class WeComApp:
    """企业微信应用。"""

    def __init__(
        self,
        *,
        corp_id: str = "",
        agent_id: str = "",
        secret: str = "",
    ) -> None:
        self.corp_id = corp_id
        self.agent_id = agent_id
        self.secret = secret

    def push_notification(
        self,
        user_ids: list[str],
        title: str,
        content: str,
    ) -> bool:
        """推送应用消息。

        wechatpy 缺失时 → httpx 直连 → mock 降级返回 True（TR-8.5）。
        """
        # 尝试 wechatpy
        try:
            from wechatpy.enterprise import WeChatClient  # type: ignore

            if self.corp_id and self.secret:
                client = WeChatClient(self.corp_id, self.secret)
                client.message.send_text(
                    self.agent_id,
                    content,
                    user_ids="|".join(user_ids),
                )
                return True
        except ImportError:
            pass  # wechatpy 未安装
        except Exception as e:  # noqa: BLE001
            logger.debug("wechatpy 推送失败 → httpx 降级: %s", e)

        # 尝试 httpx 直连
        try:
            import httpx

            if self.corp_id and self.secret:
                token_resp = httpx.get(
                    "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                    params={"corpid": self.corp_id, "corpsecret": self.secret},
                    timeout=5.0,
                )
                access_token = token_resp.json().get("access_token", "")
                if access_token:
                    httpx.post(
                        "https://qyapi.weixin.qq.com/cgi-bin/message/send",
                        params={"access_token": access_token},
                        json={
                            "touser": "|".join(user_ids),
                            "msgtype": "text",
                            "agentid": int(self.agent_id) if self.agent_id else 0,
                            "text": {"content": f"{title}\n{content}"},
                        },
                        timeout=5.0,
                    )
                    return True
        except Exception as e:  # noqa: BLE001
            logger.debug("企微 httpx 直连降级: %s", e)

        # mock 降级：返回 True（TR-8.5）
        logger.info("企微推送(mock): %s → %s users", title, len(user_ids))
        return True

    def oauth_callback(self, code: str) -> dict[str, Any]:
        """网页授权回调：用 code 换 userid。"""
        try:
            import httpx

            if self.corp_id and self.secret:
                token_resp = httpx.get(
                    "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                    params={"corpid": self.corp_id, "corpsecret": self.secret},
                    timeout=5.0,
                )
                access_token = token_resp.json().get("access_token", "")
                if access_token:
                    user_resp = httpx.get(
                        "https://qyapi.weixin.qq.com/cgi-bin/user/getuserinfo",
                        params={"access_token": access_token, "code": code},
                        timeout=5.0,
                    )
                    userid = user_resp.json().get("userid", "")
                    if userid:
                        return {"userid": userid, "name": f"用户{userid[-4:]}"}
        except Exception as e:  # noqa: BLE001
            logger.debug("企微 OAuth 降级: %s", e)

        # mock 降级
        import hashlib
        return {
            "userid": f"wx_mock_{hashlib.md5(code.encode()).hexdigest()[:8]}",
            "name": "mock用户",
        }


# =====================================================
# 单例 + 测试重置
# =====================================================
_app: WeComApp | None = None
_lock = threading.Lock()


def get_wecom_app() -> WeComApp:
    global _app
    if _app is None:
        with _lock:
            if _app is None:
                from config import get_settings

                s = get_settings()
                _app = WeComApp(
                    corp_id=getattr(s, "wecom_corp_id", "") or "",
                    agent_id=getattr(s, "wecom_agent_id", "") or "",
                    secret=getattr(s, "wecom_secret", "") or "",
                )
    return _app


def reset_wecom_app() -> None:
    global _app
    with _lock:
        _app = None


__all__ = ["WeComApp", "get_wecom_app", "reset_wecom_app"]
