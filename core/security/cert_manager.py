"""证书管理：本地文件 / Vault 注入二选一。

prod 环境从 Vault / K8s Secret 注入 SM2 密钥；
dev 环境从本地文件读取（或用 fallback HMAC）。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("core.security.cert_manager")

# 默认证书路径（dev 环境本地文件）
DEFAULT_CERT_DIR = Path(os.environ.get("SM2_CERT_DIR", ".certs"))


class CertManager:
    """SM2 证书管理器。"""

    def __init__(self, cert_dir: Path | str = DEFAULT_CERT_DIR) -> None:
        self._cert_dir = Path(cert_dir)
        self._keys: dict[str, dict[str, str]] = {}

    def load_from_file(self, tenant_id: str) -> dict[str, str]:
        """从本地文件加载 SM2 密钥对。

        文件路径：{cert_dir}/{tenant_id}.json
        格式：{"private_key": "...", "public_key": "..."}
        """
        if tenant_id in self._keys:
            return self._keys[tenant_id]
        path = self._cert_dir / f"{tenant_id}.json"
        if not path.exists():
            logger.warning("SM2 证书文件不存在: %s", path)
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._keys[tenant_id] = data
            return data
        except Exception as e:  # noqa: BLE001
            logger.warning("SM2 证书加载失败: %s → %s", path, e)
            return {}

    def load_from_env(self) -> dict[str, str]:
        """从环境变量加载全局 SM2 密钥对。"""
        return {
            "private_key": os.environ.get("SM2_PRIVATE_KEY", ""),
            "public_key": os.environ.get("SM2_PUBLIC_KEY", ""),
        }

    def save_to_file(self, tenant_id: str, private_key: str, public_key: str) -> None:
        """保存 SM2 密钥对到本地文件（仅 dev 使用）。"""
        self._cert_dir.mkdir(parents=True, exist_ok=True)
        path = self._cert_dir / f"{tenant_id}.json"
        path.write_text(
            json.dumps({"private_key": private_key, "public_key": public_key}, indent=2),
            encoding="utf-8",
        )
        self._keys[tenant_id] = {"private_key": private_key, "public_key": public_key}
        logger.info("SM2 证书已保存: %s", path)


_manager: CertManager | None = None


def get_cert_manager() -> CertManager:
    global _manager
    if _manager is None:
        _manager = CertManager()
    return _manager
