"""钉钉机器人真实渠道（5b.4）。

设计：
- 走钉钉自定义机器人 webhook（POST JSON）；
- 支持「加签」模式：``secret`` 非空时，URL 自动追加 ``timestamp`` + ``sign``；
- 缺 webhook / 占位 → **降级 Mock** + 警告；
- 网络错 / 非 2xx → 降级 Mock（不抛 ``NotifierError``，业务可安心调用）。
"""

from __future__ import annotations

import logging
from typing import Any

from services.notification_channels.base_channel import (
    BaseChannel,
    HTTPError,
    compute_dingtalk_sign,
    http_post_json,
    is_placeholder,
    register_channel,
)

logger = logging.getLogger(__name__)


@register_channel
class DingTalkRealChannel(BaseChannel):
    """钉钉真实发送渠道。"""

    name = "dingtalk_real"

    def __init__(
        self,
        *,
        webhook: str | None = None,
        secret: str | None = None,
        timeout: float = 5.0,
        force_mock: bool = False,
    ) -> None:
        self._webhook = webhook
        self._secret = secret
        self._timeout = timeout
        self.force_mock = force_mock

    @property
    def is_configured(self) -> bool:
        """是否具备真实发送凭据。"""
        return self._has_credentials()

    def _has_credentials(self) -> bool:
        if self.force_mock:
            return False
        if is_placeholder(self._webhook) or not self._webhook:
            return False
        return True

    def _build_url(self) -> str:
        """根据 secret 决定是否追加 timestamp+sign。"""
        url = self._webhook or ""
        if not self._secret or is_placeholder(self._secret):
            return url
        qs = compute_dingtalk_sign(self._secret)
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}{qs}"

    async def send(
        self,
        *,
        tenant_id: str,
        title: str,
        body: str,
        severity: str = "info",
        **meta: Any,
    ) -> str:
        # ---- Mock 降级 ----
        if not self._has_credentials():
            self._log_mock(
                f"dingtalk_real → tenant={tenant_id} title={title} severity={severity}"
            )
            return self._mock_message_id("dingtalk-real")

        url = self._build_url()
        payload: dict[str, Any] = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"**[{severity.upper()}] {title}**\n\n{body}",
            },
            "at": {"isAtAll": bool(meta.get("at_all", False))},
        }

        try:
            status, text = http_post_json(url, payload, timeout=self._timeout)
            if 200 <= status < 300:
                logger.info(
                    "dingtalk_real 发送成功: tenant=%s status=%s body=%s",
                    tenant_id, status, text[:80],
                )
                return f"dingtalk-real-{status}"
            logger.warning(
                "dingtalk_real 非 2xx: tenant=%s status=%s body=%s → 降级 Mock",
                tenant_id, status, text[:80],
            )
        except HTTPError as e:
            logger.warning("dingtalk_real 网络失败: %s → 降级 Mock", e)

        return self._mock_message_id("dingtalk-real")
