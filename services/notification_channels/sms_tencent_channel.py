"""腾讯云短信（SMS）真实渠道（5b.4）。

设计：
- 走腾讯云短信服务 v3 API（``sms.tencentcloudapi.com``）；
- 自行计算 ``Authorization``（TC3-HMAC-SHA256 签名算法）：
  参数排序 + canonical request + HMAC-SHA256；
  （不依赖 ``tencentcloud-sdk-python``，沙箱无该包也能跑）
- 缺 secret_id / secret_key / app_id / sign_name / template_id / phone
  → **降级 Mock** + 警告；
- 网络错 / 非 2xx / 业务 ``Error`` 非空 → 降级 Mock（不抛 ``NotifierError``）。

参考：
- https://cloud.tencent.com/document/api/382/55981
- https://cloud.tencent.com/document/api/213/30654（签名算法）
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from services.notification_channels.base_channel import (
    BaseChannel,
    HTTPError,
    http_post_json,
    http_post_raw_json,
    is_placeholder,
    register_channel,
)

logger = logging.getLogger(__name__)

# 腾讯云 SMS 公共参数
_TENCENT_SMS_HOST = "sms.tencentcloudapi.com"
_TENCENT_SMS_ENDPOINT = f"https://{_TENCENT_SMS_HOST}"
_TENCENT_SMS_ACTION = "SendSms"
_TENCENT_SMS_VERSION = "2021-01-11"
_DEFAULT_REGION = "ap-guangzhou"
_DEFAULT_SERVICE = "sms"


def _sha256_hex(data: bytes | str) -> str:
    """SHA256 哈希，返回小写 hex。"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    """HMAC-SHA256，返回 bytes（用于签名链派生）。"""
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _sign_tencent_v3(
    secret_id: str,
    secret_key: str,
    *,
    service: str,
    host: str,
    action: str,
    payload: str,
    timestamp: int | None = None,
    region: str = "",
) -> str:
    """腾讯云 v3 TC3-HMAC-SHA256 签名。

    参考：https://cloud.tencent.com/document/api/213/30654

    步骤：
    1. 拼接 CanonicalRequest；
    2. 拼接 StringToSign；
    3. 派生 Signature = HMAC_SHA256(derived_key, StringToSign)；
    4. 组装 Authorization 头。

    Args:
        payload: 请求 body 的 JSON 字符串（必须与实际发送的 bytes 一致）。
        timestamp: UTC 秒；None 则取当前时间。
        region: 可选，腾讯云 region（ap-guangzhou 等），影响 CredentialScope 不影响签名算法。
    """
    if timestamp is None:
        timestamp = int(time.time())

    # ---- 1. CanonicalRequest ----
    # 腾讯云 v3 规范：content-type / host / x-tc-action 必须按字典序排列
    canonical_headers = (
        f"content-type:application/json; charset=utf-8\n"
        f"host:{host}\n"
        f"x-tc-action:{action.lower()}\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    hashed_payload = _sha256_hex(payload)
    canonical_request = (
        f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{hashed_payload}"
    )

    # ---- 2. StringToSign ----
    # CredentialScope 中的 date 必须用 UTC 时间（YYYY-MM-DD，带连字符）
    date_str = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
    credential_scope = f"{date_str}/{service}/tc3_request"
    string_to_sign = (
        f"TC3-HMAC-SHA256\n"
        f"{timestamp}\n"
        f"{credential_scope}\n"
        f"{_sha256_hex(canonical_request)}"
    )

    # ---- 3. Signature（派生 key 链）----
    secret_date = _hmac_sha256(("TC3" + secret_key).encode("utf-8"), date_str)
    secret_service = _hmac_sha256(secret_date, service)
    secret_signing = _hmac_sha256(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    # ---- 4. Authorization ----
    authorization = (
        f"TC3-HMAC-SHA256 "
        f"Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )
    return authorization


@register_channel
class SmsTencentChannel(BaseChannel):
    """腾讯云短信真实发送渠道。"""

    name = "sms_tencent"

    def __init__(
        self,
        *,
        secret_id: str | None = None,
        secret_key: str | None = None,
        app_id: str | None = None,
        sign_name: str | None = None,
        template_id: str | None = None,
        phone: str | None = None,
        region: str = _DEFAULT_REGION,
        endpoint: str = _TENCENT_SMS_ENDPOINT,
        timeout: float = 5.0,
        force_mock: bool = False,
    ) -> None:
        self._secret_id = secret_id
        self._secret_key = secret_key
        self._app_id = app_id
        self._sign_name = sign_name
        self._template_id = template_id
        self._phone = phone
        self._region = region
        self._endpoint = endpoint
        self._timeout = timeout
        self.force_mock = force_mock

    def _has_credentials(self) -> bool:
        if self.force_mock:
            return False
        # 6 个核心凭据任一缺失 / 占位 → 降级
        for v in (
            self._secret_id,
            self._secret_key,
            self._app_id,
            self._sign_name,
            self._template_id,
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
        # phone 允许 meta 覆盖；腾讯云要求 +8613800138000 格式
        phone = str(meta.get("phone") or self._phone or "")
        # template_params：腾讯云模板按顺序传参（数组）
        # 首版默认把 title / body 作为前两个占位参数
        template_param_set = meta.get("template_param_set")
        if template_param_set is None:
            template_param_set = [title or "", body or ""] if title or body else [body or ""]
        if not isinstance(template_param_set, (list, tuple)):
            template_param_set = [str(template_param_set)]
        template_param_set = [str(p) for p in template_param_set]

        # ---- Mock 降级 ----
        if not self._has_credentials() or is_placeholder(phone) or not phone:
            self._log_mock(
                f"sms_tencent → tenant={tenant_id} phone={phone} title={title}"
            )
            return self._mock_message_id("sms-tencent")

        # ---- 构造请求 body ----
        # 腾讯云短信 v3 要求 phone 形如 "+8613800138000"，无 + 前缀则补 +86
        if not phone.startswith("+"):
            phone = f"+86{phone}"

        payload_dict: dict[str, Any] = {
            "PhoneNumberSet": [phone],
            "SmsSdkAppId": self._app_id,
            "SignName": self._sign_name,
            "TemplateId": self._template_id,
            "TemplateParamSet": template_param_set,
        }
        payload_str = json.dumps(payload_dict, ensure_ascii=False, separators=(",", ":"))

        # ---- 签名 ----
        timestamp = int(time.time())
        try:
            authorization = _sign_tencent_v3(
                self._secret_id or "",
                self._secret_key or "",
                service=_DEFAULT_SERVICE,
                host=_TENCENT_SMS_HOST,
                action=_TENCENT_SMS_ACTION,
                payload=payload_str,
                timestamp=timestamp,
                region=self._region,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "sms_tencent 签名失败: %s → 降级 Mock",
                e,
            )
            return self._mock_message_id("sms-tencent")

        # ---- 发送 ----
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": _TENCENT_SMS_HOST,
            "X-TC-Action": _TENCENT_SMS_ACTION,
            "X-TC-Version": _TENCENT_SMS_VERSION,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Region": self._region,
        }

        try:
            # P0-6 修补：用 http_post_raw_json 保证签名计算的字节流
            # 与实际请求体完全一致（旧版用 http_post_json 会重新
            # json.dumps 生成带空格的 JSON，签名与请求体字节序列不一致
            # → 腾讯云 v3 验签必失败）
            status, text = http_post_raw_json(
                self._endpoint,
                payload_str.encode("utf-8"),  # 与签名计算同源
                timeout=self._timeout,
                headers=headers,
            )
        except (HTTPError, OSError) as e:
            logger.warning("sms_tencent 网络失败: %s → 降级 Mock", e)
            return self._mock_message_id("sms-tencent")
        except Exception as e:  # noqa: BLE001
            logger.warning("sms_tencent 请求异常: %s → 降级 Mock", e)
            return self._mock_message_id("sms-tencent")

        if not (200 <= status < 300):
            logger.warning(
                "sms_tencent 非 2xx: tenant=%s status=%s body=%s → 降级 Mock",
                tenant_id, status, text[:120],
            )
            return self._mock_message_id("sms-tencent")

        # ---- 解析腾讯云响应 ----
        # 响应形如 {"Response":{"SendStatusSet":[{"Code":"Ok","Message":"send success","SerialNo":"xxx"}],"RequestId":"..."}}
        try:
            resp = json.loads(text)
        except Exception:  # noqa: BLE001
            resp = {}
        response = resp.get("Response", resp) if isinstance(resp, dict) else {}
        request_id = response.get("RequestId", "") if isinstance(response, dict) else ""

        send_status_set = response.get("SendStatusSet", []) if isinstance(response, dict) else []
        if not send_status_set:
            logger.warning(
                "sms_tencent 响应无 SendStatusSet: tenant=%s req=%s → 降级 Mock",
                tenant_id, request_id,
            )
            return self._mock_message_id("sms-tencent")

        first = send_status_set[0] if isinstance(send_status_set[0], dict) else {}
        code = first.get("Code", "")
        if code == "Ok":
            serial_no = first.get("SerialNo", "")
            logger.info(
                "sms_tencent 发送成功: tenant=%s phone=%s req=%s serial=%s",
                tenant_id, phone, request_id, serial_no,
            )
            return f"sms-tencent-{serial_no or request_id or status}"
        logger.warning(
            "sms_tencent 业务失败: tenant=%s phone=%s code=%s message=%s → 降级 Mock",
            tenant_id, phone, code, first.get("Message", ""),
        )
        return self._mock_message_id("sms-tencent")
