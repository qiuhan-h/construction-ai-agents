"""仓储协议与异常（5b.3 引入）。

设计：
- ``Repository`` Protocol：所有仓储的最小契约（``add`` + ``get`` + ``list``）；
  - 不要求子类实现异步（业务仓储里多数是同步 SQLAlchemy 2.0 调用）；
- ``BackendUnavailableError``：缺 SQLAlchemy 包时抛出，调用方可降级；
- ``RepositoryError``：所有仓储异常的基类。

参考 5b.2 ``VectorStoreError`` / 5b.7 ``GeofenceHistoryStore`` 风格。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class RepositoryError(Exception):
    """所有仓储异常的基类。"""


class BackendUnavailableError(RepositoryError):
    """期望的存储后端不可用（缺 SQLAlchemy / 缺表 等）。"""


@runtime_checkable
class Repository(Protocol):
    """仓储协议：CRUD 最小集。

    各业务仓储按需扩展签名（``list(..., project_id=..., limit=..., offset=...)`` 等），
    但 ``add`` / ``get`` 是统一入口；不强制异步。
    """

    def add(self, item: dict[str, Any]) -> str:
        """新增一条；返回持久化后的主键。"""
        ...

    def get(self, key: str, *, tenant_id: str | None = None) -> dict[str, Any] | None:
        """按主键 + 租户取一条（找不到返回 None）。"""
        ...

    def list(
        self,
        tenant_id: str,
        *,
        project_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """按租户列表查询，返回 (items, total)。"""
        ...


__all__ = ["Repository", "RepositoryError", "BackendUnavailableError"]
