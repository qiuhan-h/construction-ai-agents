"""计费域模型（6b.1 多租户 SaaS）：用量流水 + 月度账单。

与 ``models.database.billing_models`` 的 ORM 表一一对应；
服务层以本模块的 Pydantic 模型为业务契约，仓储层负责 dict ↔ ORM 转换。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from common.constants import SubscriptionPlan
from common.timeutils import utc_now

# 用量指标：
# - api_calls          API 调用次数（累计增量）
# - storage_gb         存储用量（瞬时值，GB）
# - agent_concurrency  智能体并发槽位（+1/-1 瞬时）
USAGE_METRICS: tuple[str, ...] = (
    "api_calls",
    "storage_gb",
    "agent_concurrency",
)


def current_period(now: datetime | None = None) -> str:
    """当前账期标识（UTC，``yyyy-mm``）。"""
    return (now or utc_now()).strftime("%Y-%m")


class UsageRecord(BaseModel):
    """用量流水记录。"""

    id: str | None = Field(default=None, description="流水 ID (usg_ 前缀)")
    tenant_id: str = Field(..., description="租户 ID")
    metric: str = Field(..., description="指标名（见 USAGE_METRICS）")
    amount: float = Field(default=0.0, description="用量数值（增量或瞬时值）")
    period: str | None = Field(default=None, description="账期 yyyy-mm（UTC）")
    detail: dict[str, Any] = Field(default_factory=dict, description="附加上下文")
    recorded_at: datetime = Field(default_factory=utc_now, description="发生时间（UTC）")


class Bill(BaseModel):
    """月度账单（6b.1 mock：套餐固定月费）。"""

    id: str | None = Field(default=None, description="账单 ID (bill_ 前缀)")
    tenant_id: str = Field(..., description="租户 ID")
    plan: SubscriptionPlan = Field(..., description="出账时套餐")
    period: str = Field(..., description="账期 yyyy-mm（UTC）")
    usage: dict[str, float] = Field(
        default_factory=dict, description="出账时用量快照"
    )
    cost: float = Field(default=0.0, description="账单金额（mock 为套餐月费）")
    currency: str = Field(default="CNY", description="币种")
    status: str = Field(default="issued", description="账单状态（issued/paid）")
    detail: dict[str, Any] = Field(default_factory=dict, description="计费明细")
    created_at: datetime = Field(default_factory=utc_now)


__all__ = ["UsageRecord", "Bill", "USAGE_METRICS", "current_period"]
