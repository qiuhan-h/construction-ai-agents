"""法规域表模型（5b.3 新增）：法规条文 / 标准 / 案例。

设计：
- 与现有 ``models/domain/regulation.py``（Pydantic）解耦，本模块只负责
  持久化形态；
- 每条记录 ``tenant_id + (code, version[, article])`` 唯一；
- 关键词 / 引用法规用 JSON 列存储，避免关联表复杂度。
"""

from __future__ import annotations

from sqlalchemy import JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from common.ids import case_id, regulation_id, standard_id
from models.database.base import Base, IDMixin, TenantMixin, TimestampMixin


class RegulationTable(TenantMixin, IDMixin, TimestampMixin, Base):
    """法规条文表。"""

    __tablename__ = "regulations"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: regulation_id()
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    chapter: Mapped[str | None] = mapped_column(String(128))
    article: Mapped[str | None] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 关键词 / 分类标签（用于向量检索与 fasttext 过滤）
    keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # 关联条文（仅 ID 列表，避免跨表强外键）
    related_regulations: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "code", "version", "article",
            name="uq_regulation_tenant_code_version_article",
        ),
    )


class StandardTable(TenantMixin, IDMixin, TimestampMixin, Base):
    """标准表（GB / JGJ 等强制 / 推荐性标准）。"""

    __tablename__ = "standards"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: standard_id()
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 强制 / 推荐
    mandatory: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "code", "version", name="uq_standard_tenant_code_version"
        ),
    )


class CaseTable(TenantMixin, IDMixin, TimestampMixin, Base):
    """案例表（历史审查 / 复盘记录）。"""

    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: case_id()
    )
    case_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    judgment: Mapped[str] = mapped_column(Text, nullable=False)
    # 关联的法规 ID 列表（与 regulations.id 软关联）
    related_regulations: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    __table_args__ = (
        UniqueConstraint("tenant_id", "case_no", name="uq_case_tenant_no"),
    )


__all__ = ["RegulationTable", "StandardTable", "CaseTable"]
