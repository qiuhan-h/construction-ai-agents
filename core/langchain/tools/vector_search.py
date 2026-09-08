"""向量检索工具适配模块（5b.6 实做，对齐 shu_zhuang_tu.txt 第 198 行）。

职责：
- 把 5b.2 ChromaDB 向量库适配为 ``BusinessTool``；
- 桥接 LangChain 业务链与 ``core/vector_store/`` 真实向量库；
- 缺 ChromaDB 客户端时降级 ``MockTool``。

注册工具名（白名单）：
- ``vector.search``    向量相似度检索（top-k 法规 / 案例）
- ``vector.upsert``    向量入库（法规文本 → embedding → ChromaDB）

依赖：
- ``core/vector_store/factory.get_vector_store(backend="chroma")``
  在调用时惰性 import；缺 chromadb 包时返回 InMemoryVectorStore 兜底。
"""

from __future__ import annotations

import logging
from typing import Any

from core.langchain.tools import MockTool, register_tool

logger = logging.getLogger(__name__)


_DESC_SEARCH = "向量相似度检索：top-k 法规 / 案例匹配（基于 5b.2 ChromaDB）"
_DESC_UPSERT = "向量入库：法规 / 案例文本 → embedding → ChromaDB upsert"


class _VectorSearchTool:
    """向量检索业务工具（包装 5b.2 ChromaDB）。"""

    backend_name: str = "vector_store"

    def __init__(self) -> None:
        self.name = "vector.search"
        self.description = _DESC_SEARCH
        self._store: Any | None = None
        self._init_attempted = False

    def _ensure_store(self) -> Any | None:
        """惰性初始化向量库客户端；失败返回 None（触发 Mock 降级）。"""
        if self._init_attempted:
            return self._store
        self._init_attempted = True
        try:
            from core.vector_store.factory import get_vector_store  # type: ignore
            # 优先 chroma；缺 chromadb 时 factory 会自动 fallback 到 in_memory
            self._store = get_vector_store(backend="chroma")
        except Exception as e:  # noqa: BLE001
            logger.warning("向量库初始化失败 → 降级 Mock: %s", e)
            self._store = None
        return self._store

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        """调用 ``store.query(tenant_id, text, top_k, filter)``。

        对齐 5b.2 ``VectorStore`` 协议（``base.py:58-83``）——不存在的
        ``store.search(...)`` 已弃用。
        """
        store = self._ensure_store()
        if store is None:
            return await MockTool(self.name, self.description).run(**kwargs)
        query = kwargs.get("query") or kwargs.get("text") or ""
        top_k = int(kwargs.get("top_k") or 5)
        tenant_id = kwargs.get("tenant_id") or ""
        filter_dict = kwargs.get("filter") or None
        try:
            result = store.query(
                tenant_id=tenant_id,
                text=query,
                top_k=top_k,
                filter=filter_dict,
            )
            if hasattr(result, "__await__"):
                result = await result
        except Exception as e:  # noqa: BLE001
            logger.warning("vector.search 调用失败: %s → 降级 Mock", e)
            return await MockTool(self.name, self.description).run(**kwargs)
        # ``store.query`` 返回 list[VectorHit]；VectorHit 有 id/text/score/metadata
        matches: list[dict[str, Any]] = []
        if isinstance(result, list):
            for h in result:
                if isinstance(h, dict):
                    matches.append({
                        "id": h.get("id", ""),
                        "text": h.get("text", ""),
                        "score": h.get("score", 0.0),
                        "metadata": h.get("metadata", {}),
                    })
                else:
                    # VectorHit dataclass / pydantic
                    matches.append({
                        "id": getattr(h, "id", ""),
                        "text": getattr(h, "text", ""),
                        "score": getattr(h, "score", 0.0),
                        "metadata": getattr(h, "metadata", {}) or {},
                    })
        elif isinstance(result, dict):
            # 兼容某些实现返回 dict 的情况
            result.setdefault("tool", self.name)
            result.setdefault("backend", self.backend_name)
            return result
        return {
            "ok": True,
            "tool": self.name,
            "backend": self.backend_name,
            "matches": matches,
            "query": query,
            "top_k": top_k,
            "tenant_id": tenant_id,
        }


class _VectorUpsertTool:
    """向量入库业务工具（包装 5b.2 ChromaDB）。"""

    backend_name: str = "vector_store"

    def __init__(self) -> None:
        self.name = "vector.upsert"
        self.description = _DESC_UPSERT
        self._store: Any | None = None
        self._init_attempted = False

    def _ensure_store(self) -> Any | None:
        if self._init_attempted:
            return self._store
        self._init_attempted = True
        try:
            from core.vector_store.factory import get_vector_store  # type: ignore
            self._store = get_vector_store(backend="chroma")
        except Exception as e:  # noqa: BLE001
            logger.warning("向量库初始化失败 → 降级 Mock: %s", e)
            self._store = None
        return self._store

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        """调用 ``store.upsert(records: list[VectorRecord]) -> int``。

        对齐 5b.2 ``VectorStore`` 协议——不再使用 chromadb 原生参数签名。
        """
        store = self._ensure_store()
        if store is None:
            return await MockTool(self.name, self.description).run(**kwargs)
        from core.vector_store.base import VectorRecord  # type: ignore
        documents = kwargs.get("documents") or []
        metadatas = kwargs.get("metadatas") or []
        ids = kwargs.get("ids") or []
        tenant_id = kwargs.get("tenant_id") or ""
        # 构造 VectorRecord 列表（按协议要求）
        records: list[Any] = []
        for i, doc in enumerate(documents):
            rid = ids[i] if i < len(ids) else f"{tenant_id}-{i}"
            meta = metadatas[i] if i < len(metadatas) else {}
            if not rid:
                logger.warning("vector.upsert 跳过缺 id 项 index=%d", i)
                continue
            records.append(VectorRecord(
                id=rid,
                tenant_id=tenant_id,
                text=doc if isinstance(doc, str) else str(doc),
                vector=[],  # 由 store 自行 embedding
                metadata=meta or {},
            ))
        try:
            result = store.upsert(records=records)
            if hasattr(result, "__await__"):
                result = await result
        except Exception as e:  # noqa: BLE001
            logger.warning("vector.upsert 调用失败: %s → 降级 Mock", e)
            return await MockTool(self.name, self.description).run(**kwargs)
        # store.upsert 返回 int（实际写入数量）
        upserted = int(result) if isinstance(result, int) else len(records)
        return {
            "ok": True,
            "tool": self.name,
            "backend": self.backend_name,
            "upserted": upserted,
            "tenant_id": tenant_id,
        }


def _register() -> None:
    """注册 vector.* 系列业务工具（import 时调用一次）。"""
    register_tool("vector.search", _VectorSearchTool)
    register_tool("vector.upsert", _VectorUpsertTool)


_register()


__all__ = ["_VectorSearchTool", "_VectorUpsertTool"]
