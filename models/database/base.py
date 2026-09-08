"""SQLAlchemy 2.0 声明式基类与公共 Mixin。

约定：
- 主键为字符串 ID（common.ids 生成的 ULID），不暴露自增序列；
- 所有时间列为 UTC（DateTime(timezone=True)）；
- 枚举列以字符串值存储（native_enum=False），跨数据库可移植；
- 命名规范统一约束索引/约束名，保证 Alembic 生成确定性迁移。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, Enum as SAEnum, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from common.ids import new_id
from common.timeutils import utc_now

# 约束/索引命名规范：Alembic 依赖确定性名称生成可复现的迁移
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """全平台 ORM 模型基类。"""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IDMixin:
    """字符串主键（ULID），默认前缀 obj_，各表用 default 覆盖。"""

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("obj"))


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class TenantMixin:
    """多租户隔离：业务表统一携带 tenant_id 并建索引。"""

    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)


def enum_column(enum_cls: type[Enum], **kwargs: Any) -> Any:
    """构造以字符串值存储的枚举列（避免依赖数据库原生 ENUM 类型）。"""

    return SAEnum(
        enum_cls,
        values_callable=lambda obj: [m.value for m in obj],
        native_enum=False,
        length=32,
        **kwargs,
    )
