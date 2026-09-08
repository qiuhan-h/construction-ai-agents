"""项目域表模型：租户 / 项目 / 施工方案。

设计：tenant_id 是租户隔离键（非物理外键），
跨租户关联由应用层按 tenant_id 过滤完成，避免跨租户级联删除。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.constants import (
    PlanStatus,
    PlanType,
    ProjectStatus,
    SubscriptionPlan,
    TenantStatus,
)
from models.database.base import (
    Base,
    IDMixin,
    TenantMixin,
    TimestampMixin,
    enum_column,
)

# 6b.1：新租户配额计数器初值（api_calls 累计 / storage_gb 瞬时 / agent_concurrency 瞬时）
_DEFAULT_QUOTA_USED: dict = {
    "api_calls": 0,
    "storage_gb": 0.0,
    "agent_concurrency": 0,
}


class TenantTable(IDMixin, TimestampMixin, Base):
    """租户表。租户自身的 id 即主键。

    6b.1 多租户 SaaS 扩展列：
    - ``plan``             订阅套餐（trial/starter/pro/enterprise）
    - ``trial_expires_at`` 试用期到期时间（UTC）；付费套餐为 NULL
    - ``quota_used``       配额用量计数器（JSON），键见 ``_DEFAULT_QUOTA_USED``
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    contact: Mapped[str | None] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        enum_column(TenantStatus), nullable=False, default=TenantStatus.ACTIVE.value
    )
    # ---------- 6b.1 SaaS 字段（均有默认值，旧调用方无需改动）----------
    plan: Mapped[str] = mapped_column(
        enum_column(SubscriptionPlan),
        nullable=False,
        default=SubscriptionPlan.TRIAL.value,
    )
    trial_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    quota_used: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=lambda: dict(_DEFAULT_QUOTA_USED)
    )


class ProjectTable(TenantMixin, IDMixin, TimestampMixin, Base):
    """项目表。"""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    address: Mapped[str | None] = mapped_column(String(512))
    longitude: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(
        enum_column(ProjectStatus), nullable=False, default=ProjectStatus.DRAFT.value
    )
    description: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_tenant_project_code"),)

    # project_id -> plans 通过真实外键建立关系；
    # 跨租户通过 tenant_id 字段过滤（不建物理关系避免跨租户级联）
    plans: Mapped[list["ConstructionPlanTable"]] = relationship(back_populates="project")


class ConstructionPlanTable(TenantMixin, IDMixin, TimestampMixin, Base):
    """施工方案表。"""

    __tablename__ = "construction_plans"

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    plan_type: Mapped[str] = mapped_column(
        enum_column(PlanType), nullable=False, default=PlanType.OTHER.value
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    summary: Mapped[str | None] = mapped_column(Text)
    # 附件为存储键列表（core/storage），以 JSON 列存储
    attachments: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        enum_column(PlanStatus), nullable=False, default=PlanStatus.DRAFT.value
    )

    project: Mapped["ProjectTable"] = relationship(back_populates="plans")
