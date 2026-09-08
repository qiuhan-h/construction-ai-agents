"""通知渠道抽象基类 + 注册表（5b.4 升级）。

设计：
- ``BaseChannel.send`` 仍是抽象方法，真实 / Mock 实现各自提供；
- 通用 ``_http_post_json`` / ``_http_post_form`` 工具：标准库 ``urllib``，
  沙箱无需 httpx；
- 缺凭据 / 缺依赖 / 网络失败 → 一律 **降级到 Mock** + 警告日志；
  保证 ``send`` 永不抛 ``NotifierError``（业务方可安心异步调用）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


# =====================================================
# 公共 HTTP 工具（标准库实现，沙箱无需 httpx）
# =====================================================
class HTTPError(Exception):
    """HTTP 工具内部错误（与 NotifierError 区分）。"""


def http_post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: float = 5.0,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    """POST JSON。返回 (status_code, body_text)。

    - 超时 / 网络错 → 抛 ``HTTPError``，由调用方决定降级或上抛；
    - 仅做 2xx 状态识别，不解析业务响应（业务层自行 JSON.loads）。
    """
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "caai-notifier/1.0",
            **(headers or {}),
        },
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        raise HTTPError(f"POST {url} 失败: {e}") from e


def http_post_form(
    url: str,
    form: dict[str, str],
    *,
    timeout: float = 5.0,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    """POST application/x-www-form-urlencoded（阿里云 SMS 用）。"""
    data = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "User-Agent": "caai-notifier/1.0",
            **(headers or {}),
        },
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        raise HTTPError(f"POST {url} 失败: {e}") from e


def http_post_raw_json(
    url: str,
    raw_body: bytes,
    *,
    timeout: float = 5.0,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    """POST 原始 JSON 字节流（P0-6 修补：腾讯云 SMS 签名同源用）。

    与 ``http_post_json`` 区别：直接接收已序列化的字节流，不在内部重新
    ``json.dumps``，保证签名计算的 ``hashed_payload`` 与实际请求体
    字节序列完全一致。否则腾讯云 v3 验签必失败。
    """
    req = urllib.request.Request(
        url,
        data=raw_body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "caai-notifier/1.0",
            **(headers or {}),
        },
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        raise HTTPError(f"POST {url} 失败: {e}") from e


# =====================================================
# 钉钉 / 企微加签工具
# =====================================================
def compute_dingtalk_sign(secret: str, timestamp_ms: int | None = None) -> str:
    """钉钉机器人加签：HMAC-SHA256(timestamp + "\\n" + secret, secret) → base64。"""
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)
    secret_enc = secret.encode("utf-8")
    string_to_sign = f"{timestamp_ms}\n{secret}".encode("utf-8")
    hmac_code = hmac.new(secret_enc, string_to_sign, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return f"timestamp={timestamp_ms}&sign={sign}"


# =====================================================
# 占位检测
# =====================================================
_PLACEHOLDER = "需要补充实际链接"


def is_placeholder(value: Any) -> bool:
    """判断是否占位（None / 空 / 平台标准占位串）。"""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v:
        return True
    return v == _PLACEHOLDER


# =====================================================
# 抽象基类
# =====================================================
class BaseChannel(ABC):
    """通知渠道抽象基类。"""

    name: str = "base"
    # 真实模式默认开启；子类构造时可强制 mock
    force_mock: bool = False

    @abstractmethod
    async def send(
        self,
        *,
        tenant_id: str,
        title: str,
        body: str,
        severity: str = "info",
        **meta: Any,
    ) -> str:
        """返回 message_id；缺凭据 / 网络错 → 降级 Mock + 警告。"""

    def supports(self, *, severity: str, event_type: str) -> bool:
        if severity in ("critical", "high", "warning"):
            return True
        if severity == "info":
            return event_type.startswith("compliance.") or event_type.startswith(
                "inspection."
            )
        return False

    # ---- Mock 工具 ----
    def _mock_message_id(self, prefix: str) -> str:
        """生成 mock 消息 ID。"""
        import secrets

        return f"mock-{prefix}-{secrets.token_hex(4)}"

    def _log_mock(self, message: str) -> None:
        logger.info("[MOCK] %s", message)


class NotifierError(Exception):
    """通知渠道失败（业务层可捕获；Mock 模式不会抛）。"""


# =====================================================
# 注册表
# =====================================================
_REGISTRY: dict[str, type[BaseChannel]] = {}


def register_channel(cls: type[BaseChannel]) -> type[BaseChannel]:
    """装饰器：注册通知渠道。"""
    _REGISTRY[cls.name] = cls
    return cls


def get_channel(name: str) -> BaseChannel:
    if name not in _REGISTRY:
        raise KeyError(f"通知渠道未注册: {name}；已注册: {list(_REGISTRY.keys())}")
    return _REGISTRY[name]()


def list_channels() -> list[str]:
    return sorted(_REGISTRY.keys())


def reset_channel_registry() -> None:
    """测试用：清空注册表。"""
    _REGISTRY.clear()
