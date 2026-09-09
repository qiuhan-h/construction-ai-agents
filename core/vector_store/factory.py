"""VectorStore 工厂（5b.2）。

设计：
- ``get_vector_store(backend=None)``：
  - ``None``（默认）→ 读环境变量 ``VECTOR_STORE_BACKEND``；未设或
    ``"memory"`` / ``"in_memory"`` → InMemory；``"chroma"`` → Chroma；
  - 显式 ``"memory"`` / ``"in_memory"`` / ``"chroma"`` → 直接选后端；
- ``list_backends()`` → 返回当前进程已注册的后端名（用于健康检查 / 运维）；
- ``reset_default_vector_store()`` → 测试用，重置单例；
- 工厂**永不抛 ImportError**——后端缺失一律降级为 InMemory；
  业务层只需 ``store = get_vector_store()``。
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Literal

from core.vector_store.base import VectorStore

logger = logging.getLogger(__name__)

BackendName = Literal["memory", "in_memory", "chroma"]

_VALID = {"memory", "in_memory", "chroma"}

# 进程级单例：按 backend 名缓存实例。
# 旧实现只保留单个 _default，切换 backend 时会丢弃旧实例 →
# 切回原 backend 时新建空实例，丢失已写入数据；
# 改为 dict 按名缓存，切换 backend 不丢实例，切回仍拿到原实例。
_instances: dict[str, VectorStore] = {}
_default_lock = threading.Lock()


def _normalize(name: str | None) -> str:
    if not name:
        return "memory"
    n = name.strip().lower()
    if n == "in_memory":
        n = "memory"
    if n not in _VALID:
        logger.warning("未知 VECTOR_STORE_BACKEND=%s → fallback memory", n)
        return "memory"
    return n


def get_vector_store(backend: str | None = None) -> VectorStore:
    """获取向量库实例（进程级单例，按 backend 缓存）。

    参数：
    - ``backend``：
      - ``None``     → 读环境变量 ``VECTOR_STORE_BACKEND``
      - ``"memory"`` → InMemoryVectorStore
      - ``"chroma"`` → ChromaVectorStore（缺 chromadb 时自动 fallback）

    切换 backend 不会丢失旧实例：每个 backend 各自缓存一份单例，
    切回原 backend 仍返回原实例（含已写入数据）。
    """
    chosen = _normalize(backend or os.environ.get("VECTOR_STORE_BACKEND"))
    with _default_lock:
        cached = _instances.get(chosen)
        if cached is not None:
            return cached
        if chosen == "chroma":
            from core.vector_store.chroma_store import ChromaVectorStore

            inst: VectorStore = ChromaVectorStore(allow_fallback=True)
        else:
            from core.vector_store.in_memory import InMemoryVectorStore

            inst = InMemoryVectorStore()
        _instances[chosen] = inst
        return inst


def list_backends() -> list[str]:
    """返回后端能力列表（含缺包标记）。"""
    out: list[str] = ["memory"]
    try:
        import chromadb  # type: ignore  # noqa: F401

        out.append("chroma")
    except Exception:  # noqa: BLE001
        pass
    return out


def reset_default_vector_store() -> None:
    """重置单例（测试 / 重启场景）。"""
    with _default_lock:
        _instances.clear()
