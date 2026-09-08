"""文档服务：上传/下载/列表（首版 mock，4c+ 接 storage）。"""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from typing import Any

from common.timeutils import to_iso, utc_now

logger = logging.getLogger(__name__)


@dataclass
class DocumentMeta:
    """文档元数据。"""

    storage_key: str
    tenant_id: str
    project_id: str
    filename: str
    size: int
    content_hash: str
    uploaded_at: str = field(default_factory=lambda: to_iso(utc_now()))

    def to_dict(self) -> dict:
        return {
            "storage_key": self.storage_key,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "filename": self.filename,
            "size": self.size,
            "content_hash": self.content_hash,
            "uploaded_at": self.uploaded_at,
        }


class DocumentService:
    """文档服务（mock 模式：内存存储 + 假 storage_key）。"""

    def __init__(self) -> None:
        # storage_key -> bytes；项目维度索引 project_id -> [storage_key]
        self._blobs: dict[str, bytes] = {}
        self._meta: dict[str, DocumentMeta] = {}
        self._by_project: dict[str, list[str]] = {}

    async def upload(
        self,
        tenant_id: str,
        project_id: str,
        file: bytes,
        filename: str,
    ) -> str:
        """上传并返回 storage_key。"""
        if not isinstance(file, (bytes, bytearray)):
            raise TypeError("file 须为 bytes")
        storage_key = f"doc-{secrets.token_hex(8)}"
        self._blobs[storage_key] = bytes(file)
        h = hashlib.sha256(file).hexdigest()
        meta = DocumentMeta(
            storage_key=storage_key,
            tenant_id=tenant_id,
            project_id=project_id,
            filename=filename,
            size=len(file),
            content_hash=h,
        )
        self._meta[storage_key] = meta
        self._by_project.setdefault(f"{tenant_id}:{project_id}", []).append(storage_key)
        return storage_key

    async def download(self, storage_key: str) -> bytes:
        if storage_key not in self._blobs:
            raise KeyError(f"storage_key 不存在: {storage_key}")
        return self._blobs[storage_key]

    async def get_meta(self, storage_key: str) -> DocumentMeta | None:
        return self._meta.get(storage_key)

    async def list_by_project(self, tenant_id: str, project_id: str) -> list[DocumentMeta]:
        keys = self._by_project.get(f"{tenant_id}:{project_id}", [])
        return [self._meta[k] for k in keys if k in self._meta]

    async def delete(self, storage_key: str) -> bool:
        if storage_key not in self._blobs:
            return False
        meta = self._meta.pop(storage_key, None)
        self._blobs.pop(storage_key, None)
        if meta:
            key = f"{meta.tenant_id}:{meta.project_id}"
            if key in self._by_project and storage_key in self._by_project[key]:
                self._by_project[key].remove(storage_key)
        return True


# 单例
_default_service: DocumentService | None = None


def get_document_service() -> DocumentService:
    global _default_service
    if _default_service is None:
        _default_service = DocumentService()
    return _default_service


def reset_document_service() -> None:
    global _default_service
    _default_service = None
