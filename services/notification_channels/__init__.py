"""notification_channels 包级 re-export。"""

# 触发 @register_channel 装饰器执行
from services.notification_channels import (
    base_channel,
    dingtalk_channel,
    dingtalk_real_channel,  # 5b.4
    sms_aliyun_channel,  # 5b.4
    sms_tencent_channel,  # 5b.4
    wecom_channel,
    wecom_real_channel,  # 5b.4
)
from services.notification_channels.base_channel import (
    BaseChannel,
    HTTPError,
    NotifierError,
    compute_dingtalk_sign,
    get_channel,
    http_post_form,
    http_post_json,
    is_placeholder,
    list_channels,
    register_channel,
    reset_channel_registry,
)
from services.notification_channels.dingtalk_channel import DingTalkChannel  # noqa: F401
from services.notification_channels.dingtalk_real_channel import DingTalkRealChannel  # noqa: F401
from services.notification_channels.sms_aliyun_channel import SmsAliyunChannel  # noqa: F401
from services.notification_channels.sms_channel import SMSChannel  # noqa: F401
from services.notification_channels.sms_tencent_channel import SmsTencentChannel  # noqa: F401
from services.notification_channels.wecom_channel import WeComChannel  # noqa: F401
from services.notification_channels.wecom_real_channel import WeComRealChannel  # noqa: F401

__all__ = [
    "BaseChannel",
    "DingTalkChannel",
    "DingTalkRealChannel",  # 5b.4
    "HTTPError",
    "NotifierError",
    "SMSChannel",
    "SmsAliyunChannel",  # 5b.4
    "SmsTencentChannel",  # 5b.4
    "WeComChannel",
    "WeComRealChannel",  # 5b.4
    "compute_dingtalk_sign",
    "get_channel",
    "http_post_form",
    "http_post_json",
    "is_placeholder",
    "list_channels",
    "register_channel",
    "reset_channel_registry",
]
