"""内嵌应用集成（6c.1）：钉钉 ISV + 企业微信应用。

设计：
- 钉钉/企微 SDK 缺失时降级为 mock（httpx 直连或本地 mock）；
- OAuth 免登：钉钉 ``oauth_callback`` 校验 state + timestamp 防重放；
- 推送通知：通过 httpx 直连 API，SDK 缺失返回 True（mock 降级）。
"""

from __future__ import annotations

from services.embedded_apps.dingtalk_app import DingTalkApp, get_dingtalk_app
from services.embedded_apps.wecom_app import WeComApp, get_wecom_app

__all__ = [
    "DingTalkApp",
    "get_dingtalk_app",
    "WeComApp",
    "get_wecom_app",
]
