"""报告电子签章（首版：HMAC-SHA256 + 租户密钥 + 内容指纹）。

设计：
- 签名内容 = SHA-256(content) + tenant_id + signed_at；
- 用 HMAC-SHA256(secret, ...) 计算签名指纹（hex 编码）；
- 阶段四接真实 CA / 国密 SM2。

使用：
    signer = ReportSigner(secret="your-tenant-key")
    info = signer.sign(content="<markdown>", tenant_id="tnt_x")
    assert verify_signature(content, tenant_id, signed_at, signature, secret)
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from common.timeutils import to_iso, utc_now


@dataclass(frozen=True)
class SignInfo:
    """签章结果。"""

    sha256: str
    signature: str
    signed_at: str
    signer: str
    algorithm: str = "HMAC-SHA256"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "signature": self.signature,
            "signed_at": self.signed_at,
            "signer": self.signer,
            "algorithm": self.algorithm,
        }


class ReportSigner:
    """报告签章器（HMAC-SHA256）。"""

    def __init__(self, secret: str, *, signer: str = "safety_audit_agent") -> None:
        if not secret:
            raise ValueError("ReportSigner.secret 不能为空")
        self.secret = secret.encode("utf-8")
        self.signer = signer

    def sign(self, content: str, tenant_id: str) -> SignInfo:
        """对报告内容签章。"""
        if not content:
            raise ValueError("签章内容不能为空")
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        signed_at = to_iso(utc_now())
        msg = f"{sha}|{tenant_id}|{signed_at}".encode("utf-8")
        sig = hmac.new(self.secret, msg, hashlib.sha256).hexdigest()
        return SignInfo(
            sha256=sha, signature=sig, signed_at=signed_at, signer=self.signer
        )

    def verify(
        self,
        content: str,
        tenant_id: str,
        signed_at: str,
        signature: str,
    ) -> bool:
        """验证签章是否一致。"""
        if not content or not signature:
            return False
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        msg = f"{sha}|{tenant_id}|{signed_at}".encode("utf-8")
        expected = hmac.new(self.secret, msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


# =====================================================
# 默认签章器（从 settings 读取 api_jwt_secret 作为共享密钥；测试可注入）
# 按 secret 缓存：不同 secret 得到不同实例，避免新密钥失效。
# =====================================================
_default_cache: dict[str, ReportSigner] = {}


def default_signer(secret: str | None = None) -> ReportSigner:
    if secret is None:
        try:
            from config import get_settings
            s = get_settings()
            secret = s.api_jwt_secret.get_secret_value()
        except Exception:
            secret = "dev-placeholder-secret"
    cached = _default_cache.get(secret)
    if cached is not None:
        return cached
    signer = ReportSigner(secret)
    _default_cache[secret] = signer
    return signer


def reset_default_signer() -> None:
    _default_cache.clear()


# =====================================================
# 模块级便捷函数
# =====================================================
def sign_report_content(content: str, tenant_id: str, secret: str | None = None) -> SignInfo:
    """便捷：对内容签章（使用默认签章器）。"""
    return default_signer(secret).sign(content, tenant_id)


def verify_signature(
    content: str,
    tenant_id: str,
    signed_at: str,
    signature: str,
    secret: str | None = None,
) -> bool:
    """便捷：验证签章。"""
    return default_signer(secret).verify(content, tenant_id, signed_at, signature)
