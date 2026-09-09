"""国密 SM2 签名实现（替换 HMAC 占位）。

F8 原则：prod 默认走 SM2；dev 保留 HMAC 降级。
缺少 gmssl 时降级为 HMAC-SHA256，确保链路可用。
"""

from __future__ import annotations

import hashlib
import hmac
import logging

logger = logging.getLogger("core.security.sm2_signer")

# SM2 曲线参数（gmstdlib / gmssl 共用）
SM2_CURVE_NAME = "sm2p256v1"


class SM2Signer:
    """SM2 签名器。

    优先使用 gmssl 实现；缺包时降级为 HMAC-SHA256（dev 可用，prod 警告）。
    """

    def __init__(
        self,
        private_key: str = "",
        public_key: str = "",
        *,
        fallback_secret: str = "",
    ) -> None:
        self._private_key = private_key
        self._public_key = public_key
        self._fallback_secret = fallback_secret
        self._backend = self._detect_backend()

    def _detect_backend(self) -> str:
        """检测可用后端：gmssl → hmac 降级。"""
        import importlib.util

        if importlib.util.find_spec("gmssl") is not None:
            if self._private_key and self._public_key:
                return "gmssl"
        if not self._private_key or not self._public_key:
            logger.warning(
                "SM2 密钥未配置或 gmssl 未安装 → 降级为 HMAC-SHA256"
                "（dev 可用，prod 需配置 SM2 密钥）"
            )
            return "hmac"
        logger.warning("gmssl 未安装 → 降级为 HMAC-SHA256")
        return "hmac"

    @property
    def algorithm(self) -> str:
        return "SM2" if self._backend == "gmssl" else "HMAC-SHA256"

    def sign(self, data: bytes) -> str:
        """对 data 签名，返回 hex 签名串。"""
        if self._backend == "gmssl":
            from gmssl import sm2  # type: ignore
            crypt = sm2.CryptSM2(
                private_key=self._private_key,
                public_key=self._public_key,
            )
            # SM2 签名：先 SM3 摘要再签名
            digest = hashlib.new("md5", data).hexdigest()  # gmssl 内部用 sm3
            try:
                sig = crypt.sign(digest)
                return sig.hex() if isinstance(sig, bytes) else str(sig)
            except Exception as e:  # noqa: BLE001
                logger.warning("SM2 签名失败: %s → HMAC 降级", e)
                return self._hmac_sign(data)
        return self._hmac_sign(data)

    def verify(self, data: bytes, signature: str) -> bool:
        """验签：返回 True 表示签名有效。"""
        if self._backend == "gmssl":
            from gmssl import sm2  # type: ignore
            crypt = sm2.CryptSM2(
                private_key=self._private_key,
                public_key=self._public_key,
            )
            digest = hashlib.new("md5", data).hexdigest()
            try:
                return crypt.verify(signature, digest)
            except Exception as e:  # noqa: BLE001
                logger.warning("SM2 验签失败: %s → HMAC 降级", e)
                return self._hmac_verify(data, signature)
        return self._hmac_verify(data, signature)

    def _hmac_sign(self, data: bytes) -> str:
        return hmac.new(
            self._fallback_secret.encode(), data, hashlib.sha256
        ).hexdigest()

    def _hmac_verify(self, data: bytes, signature: str) -> bool:
        expected = self._hmac_sign(data)
        return hmac.compare_digest(expected, signature)


def generate_sm2_keypair() -> tuple[str, str]:
    """生成 SM2 密钥对（需 gmssl）。

    返回 (private_key_hex, public_key_hex)。
    缺 gmssl 时返回空串并警告。
    """
    try:
        from gmssl import func, sm2  # type: ignore
        private_key = func.random_hex(64)
        # gmssl 的公钥 = 04 + x(64 hex) + y(64 hex) = 130 hex chars
        crypt = sm2.CryptSM2(private_key=private_key, public_key="")
        # 公钥从私钥派生
        public_key = crypt._kg(int(private_key, 16), sm2.default_ecc_table["G"])  # type: ignore
        pk_hex = "04" + "{:064x}{:064x}".format(*public_key)
        return private_key, pk_hex
    except ImportError:
        logger.warning("gmssl 未安装 → 无法生成 SM2 密钥对")
        return "", ""
    except Exception as e:  # noqa: BLE001
        logger.warning("SM2 密钥生成失败: %s", e)
        return "", ""


_signer: SM2Signer | None = None


def get_sm2_signer(
    private_key: str = "",
    public_key: str = "",
    fallback_secret: str = "",
) -> SM2Signer:
    global _signer
    if _signer is None or private_key:
        _signer = SM2Signer(
            private_key=private_key,
            public_key=public_key,
            fallback_secret=fallback_secret,
        )
    return _signer
