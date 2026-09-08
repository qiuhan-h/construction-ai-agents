"""短信渠道（首版 mock；阶段五接阿里云/腾讯云 SMS API）。"""

from __future__ import annotations

import logging
import secrets

from services.notification_channels.base_channel import BaseChannel, NotifierError, register_channel

logger = logging.getLogger(__name__)


@register_channel
class SMSChannel(BaseChannel):
    name = "sms"

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
        phone = meta.get("phone")
        if not phone:
            # 没传入 phone：走 mock（不抛错，但记录警告）
            logger.info(
                "SMS mock: tenant=%s title=%s body=%s severity=%s",
                tenant_id, title, body, severity,
            )
            return f"mock-sms-{secrets.token_hex(4)}"
        # 真实发送：阶段五接阿里云/腾讯云
        logger.info("SMS mock 发送: phone=%s body=%s", phone, body)
        return f"mock-sms-{secrets.token_hex(4)}"
