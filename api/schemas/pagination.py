"""分页响应：Page[T]。

设计要点：
- 使用泛型 Page[T]，T 为列表元素类型；
- items / total / page / page_size / total_pages 五字段；
- 业务层通过 Page.of(items, total, page, page_size) 构造；
- 配套 PaginationQuery 用于请求参数校验。
"""

from __future__ import annotations

import math
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginationQuery(BaseModel):
    """通用分页请求参数。"""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1, description="页码（从 1 开始）")
    page_size: int = Field(default=20, ge=1, le=200, description="每页条数（1-200）")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class Page(BaseModel, Generic[T]):
    """通用分页响应。"""

    model_config = ConfigDict(extra="forbid")

    items: list[T] = Field(default_factory=list, description="当前页数据")
    total: int = Field(default=0, ge=0, description="总记录数")
    page: int = Field(default=1, ge=1, description="当前页码")
    page_size: int = Field(default=20, ge=1, description="每页条数")
    total_pages: int = Field(default=0, ge=0, description="总页数")
    has_next: bool = Field(default=False, description="是否有下一页")
    has_prev: bool = Field(default=False, description="是否有上一页")

    @classmethod
    def of(
        cls,
        items: list[T],
        total: int,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> "Page[T]":
        total_pages = math.ceil(total / page_size) if page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )

    @classmethod
    def empty(cls, *, page: int = 1, page_size: int = 20) -> "Page[T]":
        return cls.of([], 0, page=page, page_size=page_size)


__all__ = [
    "Page",
    "PaginationQuery",
]
