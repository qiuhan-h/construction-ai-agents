"""钉钉机器人 webhook 渠道（首版 mock）。"""

from __future__ import annotations

import logging
import secrets

from services.notification_channels.base_channel import BaseChannel, register_channel

logger = logging.getLogger(__name__)


@register_channel
class DingTalkChannel(BaseChannel):
    name = "dingtalk"

    def __init__(self, settings: object | None = None) -> None:
        self._settings = settings

    async def send(
        self,
        *,
        tenant_id: str,
        title: str,
        body: str,
        severity: str = "info",
        **meta,
    ) -> str:
        webhook = meta.get("webhook")
        if not webhook and self._settings is not None:
            webhook = getattr(self._settings, "dingtalk_webhook", None)
        if not webhook:
            logger.info(
                "DingTalk mock: tenant=%s title=%s severity=%s",
                tenant_id, title, severity,
            )
            return f"mock-dingtalk-{secrets.token_hex(4)}"
        # 真实发送：阶段五实现 POST 到 webhook
        logger.info("DingTalk webhook 发送: %s", webhook[:30] + "...")
        return f"mock-dingtalk-{secrets.token_hex(4)}"
