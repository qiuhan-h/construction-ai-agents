"""通知聚合：按 tenant_id + 严重度路由渠道。

设计原则（O4, O5）：
- 渠道可插拔（@register_channel 装饰器注册）；
- 严重度 → 渠道映射可被 severity_map 覆盖；
- 多租户：所有调用带 tenant_id，仅作标识用，租户隔离由渠道层实施。
"""

from __future__ import annotations

import logging
from typing import Any

from services.notification_channels.base_channel import BaseChannel, get_channel

logger = logging.getLogger(__name__)


class NotificationService:
    """通知聚合服务。"""

    DEFAULT_SEVERITY_CHANNELS: dict[str, list[str]] = {
        "critical": ["dingtalk", "sms", "wecom"],
        "high":     ["dingtalk", "wecom"],
        "warning":  ["dingtalk"],
        "info":     ["wecom"],
    }

    def __init__(
        self,
        channels: list[BaseChannel] | None = None,
        severity_map: dict[str, list[str]] | None = None,
    ) -> None:
        self._channels = channels if channels is not None else self._default_channels()
        self._severity_map = severity_map or self.DEFAULT_SEVERITY_CHANNELS

    @property
    def channels(self) -> list[BaseChannel]:
        return list(self._channels)

    @property
    def severity_map(self) -> dict[str, list[str]]:
        return dict(self._severity_map)

    def _default_channels(self) -> list[BaseChannel]:
        """按 .env / Settings 自动选择真实通道；凭据缺失降级 mock。

        真实通道实例化后覆盖 ``name`` 为路由名（dingtalk / wecom / sms），
        与 ``DEFAULT_SEVERITY_CHANNELS`` 的路由键保持一致。
        """
        from services.notification_channels.base_channel import is_placeholder

        try:
            from config import get_settings

            s = get_settings()
        except Exception as e:  # noqa: BLE001
            logger.info("Settings 不可用，通知渠道全部走 mock: %s", e)
            s = None

        def _configured(v: str) -> bool:
            return bool(v) and not is_placeholder(v)

        out: list[BaseChannel] = []

        # ---- 钉钉：webhook 已配置 → 真实通道，否则 mock ----
        try:
            webhook = (getattr(s, "dingtalk_webhook", "") or "") if s else ""
            if _configured(webhook):
                from services.notification_channels.dingtalk_real_channel import (
                    DingTalkRealChannel,
                )

                secret = ""
                if s is not None and s.dingtalk_secret:
                    secret = s.dingtalk_secret.get_secret_value()
                ch = DingTalkRealChannel(webhook=webhook, secret=secret or None)
                ch.name = "dingtalk"
                logger.info("通知渠道：钉钉真实通道（webhook 已配置）")
            else:
                ch = get_channel("dingtalk")
            out.append(ch)
        except Exception as e:  # noqa: BLE001
            logger.info("钉钉通道加载失败: %s", e)

        # ---- 企微：webhook 已配置 → 真实通道，否则 mock ----
        try:
            webhook = (getattr(s, "wecom_webhook", "") or "") if s else ""
            if _configured(webhook):
                from services.notification_channels.wecom_real_channel import (
                    WeComRealChannel,
                )

                ch = WeComRealChannel(webhook=webhook)
                ch.name = "wecom"
                logger.info("通知渠道：企微真实通道（webhook 已配置）")
            else:
                ch = get_channel("wecom")
            out.append(ch)
        except Exception as e:  # noqa: BLE001
            logger.info("企微通道加载失败: %s", e)

        # ---- 短信：阿里云（5 项）→ 腾讯云（6 项）→ mock ----
        try:
            out.append(self._build_sms_channel(s, _configured))
        except Exception as e:  # noqa: BLE001
            logger.info("短信通道加载失败: %s", e)
            try:
                out.append(get_channel("sms"))
            except Exception as e2:  # noqa: BLE001
                logger.info("短信 mock 通道加载失败: %s", e2)

        return out

    @staticmethod
    def _build_sms_channel(s: Any, _configured) -> BaseChannel:
        """凭据齐全返回真实短信通道（路由名 sms），否则返回 mock SMSChannel。"""
        if s is not None:
            # 阿里云短信：access_key_id / secret / sign / template / phone 五项齐全
            ak = s.aliyun_sms_access_key_id or ""
            sk = s.aliyun_sms_access_key_secret.get_secret_value() if s.aliyun_sms_access_key_secret else ""
            sign = s.aliyun_sms_sign_name or ""
            tpl = s.aliyun_sms_template_code or ""
            phone = s.aliyun_sms_phone or ""
            if all(_configured(v) for v in (ak, sk, sign, tpl, phone)):
                from services.notification_channels.sms_aliyun_channel import (
                    SmsAliyunChannel,
                )

                ch = SmsAliyunChannel(
                    access_key_id=ak,
                    access_key_secret=sk,
                    sign_name=sign,
                    template_code=tpl,
                    phone=phone,
                )
                ch.name = "sms"
                logger.info("通知渠道：阿里云短信真实通道")
                return ch

            # 腾讯云短信：secret_id / secret_key / app_id / sign / template / phone 六项齐全
            sid = s.tencent_sms_secret_id or ""
            skey = s.tencent_sms_secret_key.get_secret_value() if s.tencent_sms_secret_key else ""
            appid = s.tencent_sms_app_id or ""
            tsign = s.tencent_sms_sign_name or ""
            ttpl = s.tencent_sms_template_id or ""
            tphone = s.tencent_sms_phone or ""
            if all(_configured(v) for v in (sid, skey, appid, tsign, ttpl, tphone)):
                from services.notification_channels.sms_tencent_channel import (
                    SmsTencentChannel,
                )

                ch = SmsTencentChannel(
                    secret_id=sid,
                    secret_key=skey,
                    app_id=appid,
                    sign_name=tsign,
                    template_id=ttpl,
                    phone=tphone,
                )
                ch.name = "sms"
                logger.info("通知渠道：腾讯云短信真实通道")
                return ch

        return get_channel("sms")

    async def send(
        self,
        *,
        tenant_id: str,
        event_type: str,
        severity: str,
        title: str,
        body: str,
        channels: list[str] | None = None,
        **meta: Any,
    ) -> list[str]:
        """按 severity 路由；返回已发送的 message_id 列表。"""
        wanted = channels or self._severity_map.get(severity, ["dingtalk"])
        sent: list[str] = []
        for ch in self._channels:
            if ch.name not in wanted:
                continue
            if not ch.supports(severity=severity, event_type=event_type):
                continue
            try:
                mid = await ch.send(
                    tenant_id=tenant_id,
                    title=title,
                    body=body,
                    severity=severity,
                    **meta,
                )
                sent.append(mid)
            except Exception as e:  # noqa: BLE001
                logger.warning("通知发送失败 channel=%s: %s", ch.name, e)
        return sent


# 单例
_default_service: NotificationService | None = None


def get_notification_service() -> NotificationService:
    global _default_service
    if _default_service is None:
        _default_service = NotificationService()
    return _default_service


def reset_notification_service() -> None:
    global _default_service
    _default_service = None
