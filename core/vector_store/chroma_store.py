"""ChromaDB 向量库（5b.2 实做）。

设计：
- 包 ``chromadb`` 缺失时，**不抛错**而是 fallback 到 ``InMemoryVectorStore``
  并打 WARNING；这是 5b.2 F2（后端生产化不破坏 4d 接口契约）的关键：
  即使生产环境没装 chromadb，业务层仍可用；
- 包存在时尝试 ``PersistentClient(path=persist_dir)`` 落盘；
  - 客户端初始化失败（版本不兼容 / 端口占用）→ 同样 fallback；
- 与 ``InMemoryVectorStore`` 接口 100% 一致；
  - ``upsert`` 写入时把 ``vector`` 传给 chromadb（无 vector 时跳过
    ``embeddings`` 字段，让 chromadb 用 embedding function）；
  - ``query`` 用 ``tenant_id`` + ``filter`` 实现多租户隔离 + 元数据过滤；
  - 评分：chroma 返回 ``distance``，本类转 ``score = 1 / (1 + distance)``，
    使之与 InMemory 的 cosine 一样数值越大越相关。
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import Iterable
from typing import Any

from core.vector_store.base import (
    BackendUnavailableError,
    VectorHit,
    VectorRecord,
    VectorStoreError,
)
from core.vector_store.in_memory import InMemoryVectorStore

logger = logging.getLogger(__name__)


def _chroma_available() -> bool:
    """探测 chromadb 是否可用。"""
    try:
        import chromadb  # type: ignore  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


class ChromaVectorStore:
    """ChromaDB 持久化向量库（生产首选）。

    属性：
    - ``backend_name`` = ``"chroma"``
    - 缺包 / 初始化失败 → ``InMemoryVectorStore``（通过 ``_fallback``）
    """

    backend_name: str = "chroma"

    def __init__(
        self,
        *,
        persist_dir: str = "./data/chroma",
        collection_name: str = "caai",
        allow_fallback: bool = True,
    ) -> None:
        self._persist_dir = persist_dir
        self._collection_name = collection_name
        self._allow_fallback = allow_fallback
        self._client: Any | None = None
        self._collection: Any | None = None
        self._fallback: InMemoryVectorStore | None = None
        self._lock = threading.RLock()
        self._init_backend()

    # =====================================================
    # 内部：初始化
    # =====================================================
    def _init_backend(self) -> None:
        if not _chroma_available():
            self._fallback_or_raise(
                "chromadb 未安装；ChromaVectorStore 不可用"
            )
            return
        try:
            import chromadb  # type: ignore

            os.makedirs(self._persist_dir, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self._persist_dir)
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
            )
            logger.info(
                "ChromaVectorStore 初始化 OK：persist=%s collection=%s",
                self._persist_dir,
                self._collection_name,
            )
        except Exception as e:  # noqa: BLE001
            self._fallback_or_raise(
                f"Chroma 客户端初始化失败：{type(e).__name__}: {e}"
            )

    def _fallback_or_raise(self, reason: str) -> None:
        if not self._allow_fallback:
            raise BackendUnavailableError(reason)
        logger.warning("%s → fallback InMemoryVectorStore", reason)
        self._fallback = InMemoryVectorStore()

    # =====================================================
    # 协议方法
    # =====================================================
    async def upsert(self, records: list[VectorRecord]) -> int:
        if self._fallback is not None:
            return await self._fallback.upsert(records)
        if self._collection is None:
            raise VectorStoreError("Chroma collection 未初始化")
        return await asyncio.to_thread(self._upsert_sync, records)

    def _upsert_sync(self, records: list[VectorRecord]) -> int:
        assert self._collection is not None
        ids: list[str] = []
        documents: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict[str, Any]] = []
        has_emb = True
        for r in records:
            if not r.id:
                raise VectorStoreError("VectorRecord.id 不能为空")
            if not r.tenant_id:
                raise VectorStoreError(
                    "VectorRecord.tenant_id 不能为空（多租户隔离）"
                )
            ids.append(r.id)
            documents.append(r.text)
            if r.vector:
                embeddings.append(list(r.vector))
            else:
                has_emb = False
            meta = dict(r.metadata)
            meta["tenant_id"] = r.tenant_id
            metadatas.append(meta)
        kwargs: dict[str, Any] = {
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
        }
        if has_emb and embeddings:
            kwargs["embeddings"] = embeddings
        # 缺 embeddings 时让 chromadb 用内置 embedding_function
        self._collection.upsert(**kwargs)
        return len(records)

    async def query(
        self,
        tenant_id: str,
        text: str,
        *,
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
        min_score: float = 0.0,
    ) -> list[VectorHit]:
        if self._fallback is not None:
            return await self._fallback.query(
                tenant_id=tenant_id,
                text=text,
                top_k=top_k,
                filter=filter,
                min_score=min_score,
            )
        if self._collection is None:
            raise VectorStoreError("Chroma collection 未初始化")
        return await asyncio.to_thread(
            self._query_sync, tenant_id, text, top_k, filter, min_score
        )

    def _query_sync(
        self,
        tenant_id: str,
        text: str,
        top_k: int,
        filter: dict[str, Any] | None,
        min_score: float,
    ) -> list[VectorHit]:
        assert self._collection is not None
        where: dict[str, Any] = {"tenant_id": tenant_id}
        if filter:
            where.update(filter)
        res = self._collection.query(
            query_texts=[text],
            n_results=top_k,
            where=where,
        )
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        hits: list[VectorHit] = []
        for i, _id in enumerate(ids):
            distance = float(dists[i]) if i < len(dists) else 0.0
            score = 1.0 / (1.0 + max(distance, 0.0))
            if score < min_score:
                continue
            md = dict(metas[i]) if i < len(metas) else {}
            md.pop("tenant_id", None)
            hits.append(
                VectorHit(
                    id=_id,
                    tenant_id=tenant_id,
                    text=docs[i] if i < len(docs) else "",
                    score=score,
                    metadata=md,
                )
            )
        return hits

    async def delete(self, ids: Iterable[str]) -> int:
        ids = list(ids)
        if self._fallback is not None:
            return await self._fallback.delete(ids)
        if self._collection is None:
            raise VectorStoreError("Chroma collection 未初始化")
        return await asyncio.to_thread(self._delete_sync, ids)

    def _delete_sync(self, ids: list[str]) -> int:
        assert self._collection is not None
        # Chroma delete 按 id；不存在的 id 静默忽略。
        self._collection.delete(ids=ids)
        return len(ids)

    def count(self, tenant_id: str | None = None) -> int:
        if self._fallback is not None:
            return self._fallback.count(tenant_id)
        if self._collection is None:
            raise VectorStoreError("Chroma collection 未初始化")
        with self._lock:
            if tenant_id is None:
                return self._collection.count()
            res = self._collection.get(where={"tenant_id": tenant_id})
            return len(res.get("ids") or [])
