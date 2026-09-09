"""计费域表模型（6b.1 多租户 SaaS）：用量流水 + 月度账单。

设计：
- ``usage_records`` 用量流水：每次 API 调用 / 存储上报 / 并发槽位占用
  追加一条（metric + amount + period），计费按月聚合；
- ``bills`` 月度账单：(tenant_id, period) 唯一，mock 计费为套餐固定月费，
  ``usage`` 列快照出账时的用量计数；
- 与既有表一致：字符串 ULID 主键、UTC 时间、枚举以字符串存储；
- 不建物理外键到 tenants，跨表关联由应用层按 tenant_id 过滤（与
  project_models 的多租户约定一致）。
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from common.ids import new_id
from common.timeutils import utc_now
from models.database.base import (
    Base,
    IDMixin,
    TenantMixin,
    TimestampMixin,
)


def bill_id_factory() -> str:
    """账单 ID 工厂（bill_ 前缀）。"""
    return new_id("bill")


def usage_record_id_factory() -> str:
    """用量流水 ID 工厂（usg_ 前缀）。"""
    return new_id("usg")


class UsageRecordTable(TenantMixin, IDMixin, TimestampMixin, Base):
    """用量流水表（6b.1）。

    metric 取值：``api_calls``（调用次数，amount 为增量）/
    ``storage_gb``（存储量，amount 为上报瞬时值 GB）/
    ``agent_concurrency``（并发槽位，amount 为 +1/-1）。
    period 为账期 ``yyyy-mm``（UTC），便于按月聚合出账。
    """

    __tablename__ = "usage_records"

    # 覆盖 IDMixin 默认 obj_ 前缀为 usg_
    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=usage_record_id_factory
    )
    metric: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    period: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class BillTable(IDMixin, TimestampMixin, Base):
    """月度账单表（6b.1 mock 计费：套餐固定月费）。"""

    __tablename__ = "bills"

    # 覆盖 IDMixin 默认 obj_ 前缀为 bill_
    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=bill_id_factory
    )
    # 账单自身携带 tenant_id（不使用 TenantMixin 仅因需自定义唯一约束）
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(32), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    usage: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="CNY")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="issued")
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "period", name="uq_bill_tenant_period"),
    )


__all__ = [
    "UsageRecordTable",
    "BillTable",
    "bill_id_factory",
    "usage_record_id_factory",
]
