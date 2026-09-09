"""阿里云短信（SMS）真实渠道（5b.4）。

设计：
- 走阿里云短信服务 v1.0 RPC API（``dysmsapi.aliyuncs.com``）；
- 自行计算 ``Signature``：参数排序 + URL 编码 + HMAC-SHA1 + base64；
  （不依赖 ``aliyun-python-sdk-core``，沙箱无该包也能跑）
- 缺 access_key_id / access_key_secret / phone / sign_name / template_code
  → **降级 Mock** + 警告；
- 网络错 / 非 2xx → 降级 Mock（不抛 ``NotifierError``）。

参考：
- https://help.aliyun.com/zh/sms/developer-reference/api-dysmsapi
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Any
from urllib.parse import quote

from services.notification_channels.base_channel import (
    BaseChannel,
    HTTPError,
    http_post_form,
    is_placeholder,
    register_channel,
)

logger = logging.getLogger(__name__)

# 阿里云 SMS 公共参数
_ALIYUN_SMS_ENDPOINT = "https://dysmsapi.aliyuncs.com/"
_DEFAULT_REGION = "cn-hangzhou"
_SMS_VERSION = "2017-05-25"
_SMS_ACTION = "SendSms"


def _percent_encode(s: str) -> str:
    """阿里云签名算法的特殊 URL 编码（保留 ``*`` ``-`` ``.`` ``_``，其他字符 %XX）。

    普通 ``urllib.parse.quote`` 会把 ``~`` 编码为 ``%7E``，不符合阿里云规范。
    """
    if s is None:
        return ""
    # 阿里云规范：字母 / 数字 / - _ . ~ 不编码，其他 %XX
    # 同时把 + 替换为 %20
    encoded = quote(s, safe="-._~")
    return encoded.replace("+", "%20")


def _sign_aliyun_sms(
    params: dict[str, str],
    access_key_secret: str,
) -> str:
    """按阿里云 v1 RPC API 签名算法计算 Signature（P0-6 修补）。

    阿里云 ``SendSms``（dysmsapi.aliyuncs.com，Version=2017-05-25）规定
    ``Signature = base64(HMAC-SHA1(key, StringToSign))``，再 percent-encode
    后作为参数发送。旧实做返回 ``h.digest().hex()`` 是错的——hex 会让
    阿里云服务端验签必然失败（``SignatureDoesNotMatch``）。

    步骤：
    1. 按 key 升序排序（排除 Signature 自身）；
    2. 拼成 ``k1=v1&k2=v2`` 形式，``=`` 与 ``&`` 同样做 percent-encode；
    3. 首尾加 ``POST&`` + percent_encode("/") + ``&`` + percent_encode(canonicalized)；
    4. HMAC-SHA1（key = ``{access_key_secret}&``）→ **base64**（不是 hex）。
    """
    import base64
    sorted_items = sorted(
        (k, _percent_encode(str(v))) for k, v in params.items()
    )
    canonicalized = "&".join(f"{k}={v}" for k, v in sorted_items)
    string_to_sign = f"POST&{_percent_encode('/')}&{_percent_encode(canonicalized)}"
    h = hmac.new(
        f"{access_key_secret}&".encode(),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    )
    # P0-6 修补：返回 base64（阿里云 v1 RPC 规定），不是 hex
    return base64.b64encode(h.digest()).decode("ascii")


@register_channel
class SmsAliyunChannel(BaseChannel):
    """阿里云短信真实发送渠道。"""

    name = "sms_aliyun"

    def __init__(
        self,
        *,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        sign_name: str | None = None,
        template_code: str | None = None,
        phone: str | None = None,
        region: str = _DEFAULT_REGION,
        endpoint: str = _ALIYUN_SMS_ENDPOINT,
        timeout: float = 5.0,
        force_mock: bool = False,
    ) -> None:
        self._access_key_id = access_key_id
        self._access_key_secret = access_key_secret
        self._sign_name = sign_name
        self._template_code = template_code
        self._phone = phone
        self._region = region
        self._endpoint = endpoint
        self._timeout = timeout
        self.force_mock = force_mock

    def _has_credentials(self) -> bool:
        if self.force_mock:
            return False
        # 5 个核心凭据任一缺失 / 占位 → 降级
        for v in (
            self._access_key_id,
            self._access_key_secret,
            self._sign_name,
            self._template_code,
            self._phone,
        ):
            if is_placeholder(v) or not v:
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
        # phone 允许 meta 覆盖
        phone = str(meta.get("phone") or self._phone or "")
        template_params_str = str(
            meta.get("template_params") or json.dumps(
                {"title": title, "body": body}, ensure_ascii=False
            )
        )

        # ---- Mock 降级 ----
        if not self._has_credentials() or is_placeholder(phone) or not phone:
            self._log_mock(
                f"sms_aliyun → tenant={tenant_id} phone={phone} title={title}"
            )
            return self._mock_message_id("sms-aliyun")

        # ---- 公共参数 ----
        params: dict[str, str] = {
            "AccessKeyId": self._access_key_id or "",
            "Action": _SMS_ACTION,
            "Format": "JSON",
            "PhoneNumbers": phone,
            "RegionId": self._region,
            "SignName": self._sign_name or "",
            "SignatureMethod": "HMAC-SHA1",
            "SignatureNonce": uuid.uuid4().hex,
            "SignatureVersion": "1.0",
            "TemplateCode": self._template_code or "",
            "TemplateParam": template_params_str,
            "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "Version": _SMS_VERSION,
        }
        # 计算签名
        params["Signature"] = _sign_aliyun_sms(params, self._access_key_secret or "")

        try:
            status, text = http_post_form(
                self._endpoint, params, timeout=self._timeout
            )
            if 200 <= status < 300:
                # 阿里云响应体形如 {"Code":"OK","Message":"OK","RequestId":"..."}
                try:
                    resp = json.loads(text)
                    code = resp.get("Code", "")
                except Exception:  # noqa: BLE001
                    code = ""
                if code == "OK":
                    logger.info(
                        "sms_aliyun 发送成功: tenant=%s phone=%s req=%s",
                        tenant_id, phone, resp.get("RequestId") if isinstance(resp, dict) else "",
                    )
                    return f"sms-aliyun-{resp.get('RequestId', status)}" if isinstance(resp, dict) else f"sms-aliyun-{status}"
                logger.warning(
                    "sms_aliyun 业务失败: tenant=%s phone=%s code=%s → 降级 Mock",
                    tenant_id, phone, code,
                )
            else:
                logger.warning(
                    "sms_aliyun 非 2xx: tenant=%s status=%s body=%s → 降级 Mock",
                    tenant_id, status, text[:120],
                )
        except HTTPError as e:
            logger.warning("sms_aliyun 网络失败: %s → 降级 Mock", e)

        return self._mock_message_id("sms-aliyun")
