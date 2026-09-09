"""core.vector_store 包级 API（5b.2 实做）。

设计：
- 5b.2 把 ``agents/safety_audit_agent/knowledge_base/vector_store.py`` 的
  抽象（VectorStore / VectorRecord / VectorHit）下沉到 ``core/vector_store``，
  解除 ``core`` → ``agents`` 的反向依赖；
- ``agents/.../vector_store.py`` 通过 re-export 保持向后兼容（4d 业务不变）；
- 后端双实现：
  - ``InMemoryVectorStore``  ‒ 纯 Python，无第三方依赖（沙箱 / 测试用）
  - ``ChromaVectorStore``    ‒ ChromaDB 持久化（生产；缺包时自动降级到 InMemory）
- 通过 ``factory.get_vector_store(backend)`` 选实现；
- 5b.2 不改 ``scripts/setup_vector_db.py`` 的接口（依然返回 (store, VectorRecord)）。

包结构：
  core/vector_store/
    __init__.py     re-export 统一 API
    base.py         Protocol + VectorRecord / VectorHit / 异常
    in_memory.py    内存版（从 agents/.../vector_store.py 迁移，逻辑不变）
    chroma_store.py ChromaDB 版（缺包时降级 InMemory）
    factory.py      get_vector_store(backend)
"""

from __future__ import annotations

from core.vector_store.base import (
    VectorHit,
    VectorRecord,
    VectorStore,
    VectorStoreError,
)
from core.vector_store.factory import (
    get_vector_store,
    list_backends,
    reset_default_vector_store,
)

__all__ = [
    "VectorHit",
    "VectorRecord",
    "VectorStore",
    "VectorStoreError",
    "get_vector_store",
    "list_backends",
    "reset_default_vector_store",
]
