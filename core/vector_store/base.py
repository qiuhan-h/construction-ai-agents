"""向量库抽象（5b.2）。

设计：
- ``VectorStore`` Protocol：4 个核心方法 ``upsert`` / ``query`` / ``delete`` / ``count``；
- ``VectorRecord`` / ``VectorHit``：dataclass，字段与 4d 时期
  ``agents/safety_audit_agent/knowledge_base/vector_store.py`` 完全一致，
  业务层可平滑迁移；
- ``VectorStoreError``：包级异常，所有实现抛此异常的子类（NotImplementedError
  保留，用于"未实现"语义区分）。
- 不引入第三方依赖（typing.Protocol 已足够，3.8+）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol, runtime_checkable


class VectorStoreError(Exception):
    """所有 vector_store 异常的基类。"""


class BackendUnavailableError(VectorStoreError):
    """期望的后端不可用（如 chromadb 未安装且未允许降级）。"""


@dataclass
class VectorRecord:
    """一条向量记录。

    字段与 4d 时期完全一致，便于业务层向后兼容：
    - ``id``        唯一 ID（reg/code/version/case_id 等）
    - ``tenant_id`` 租户 ID（多租户隔离）
    - ``text``      原文（用于回显 / 兜底）
    - ``vector``    向量（可选；空时由 store 自动算）
    - ``metadata``  任意附加字段
    """

    id: str
    tenant_id: str
    text: str
    vector: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorHit:
    """一条检索结果。"""

    id: str
    tenant_id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class VectorStore(Protocol):
    """向量库统一协议。"""

    async def upsert(self, records: list[VectorRecord]) -> int:
        """写入或更新 records。返回写入条数（与 len(records) 相等，失败抛异常）。"""
        ...

    async def query(
        self,
        tenant_id: str,
        text: str,
        *,
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
        min_score: float = 0.0,
    ) -> list[VectorHit]:
        """按文本检索（异步）。返回 top_k 命中，按 score 降序。"""
        ...

    async def delete(self, ids: Iterable[str]) -> int:
        """按 id 删除。返回实际删除条数。"""
        ...

    def count(self, tenant_id: str | None = None) -> int:
        """记录条数（按租户可选过滤）。同步：用于运维 / 监控。"""
        ...
