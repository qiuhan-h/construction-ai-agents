"""企业微信真实渠道（5b.4）。

设计：
- 走企业微信群机器人 webhook（POST JSON）；
- 支持「文本」「Markdown」两种消息类型（默认 Markdown）；
- 缺 webhook / 占位 → **降级 Mock** + 警告；
- 网络错 / 非 2xx → 降级 Mock（不抛 ``NotifierError``）。
"""

from __future__ import annotations

import logging
from typing import Any

from services.notification_channels.base_channel import (
    BaseChannel,
    HTTPError,
    http_post_json,
    is_placeholder,
    register_channel,
)

logger = logging.getLogger(__name__)


@register_channel
class WeComRealChannel(BaseChannel):
    """企业微信真实发送渠道。"""

    name = "wecom_real"

    def __init__(
        self,
        *,
        webhook: str | None = None,
        timeout: float = 5.0,
        force_mock: bool = False,
    ) -> None:
        self._webhook = webhook
        self._timeout = timeout
        self.force_mock = force_mock

    def _has_credentials(self) -> bool:
        if self.force_mock:
            return False
        if is_placeholder(self._webhook) or not self._webhook:
            return False
        return True

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
                f"wecom_real → tenant={tenant_id} title={title} severity={severity}"
            )
            return self._mock_message_id("wecom-real")

        # _has_credentials() 为真时 webhook 必然非空（mypy 无法识别该自定义守卫）
        assert self._webhook is not None

        use_markdown = bool(meta.get("markdown", True))
        if use_markdown:
            payload: dict[str, Any] = {
                "msgtype": "markdown",
                "markdown": {
                    "content": f"## [{severity.upper()}] {title}\n\n{body}",
                },
            }
        else:
            payload = {
                "msgtype": "text",
                "text": {
                    "content": f"[{severity.upper()}] {title}\n{body}",
                    "mentioned_list": list(meta.get("mentioned_list") or []),
                },
            }

        try:
            status, text = http_post_json(
                self._webhook, payload, timeout=self._timeout
            )
            if 200 <= status < 300:
                logger.info(
                    "wecom_real 发送成功: tenant=%s status=%s body=%s",
                    tenant_id, status, text[:80],
                )
                return f"wecom-real-{status}"
            logger.warning(
                "wecom_real 非 2xx: tenant=%s status=%s body=%s → 降级 Mock",
                tenant_id, status, text[:80],
            )
        except HTTPError as e:
            logger.warning("wecom_real 网络失败: %s → 降级 Mock", e)

        return self._mock_message_id("wecom-real")
