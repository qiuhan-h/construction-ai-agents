"""多租户模型：多个项目/施工单位并发使用时的数据隔离单元。

6b.1 多租户 SaaS 扩展：
- ``plan``             订阅套餐（trial/starter/pro/enterprise）
- ``trial_expires_at`` 试用期到期时间（UTC）；付费套餐为 None
- ``quota_used``       配额用量计数器：
    * api_calls          周期内 API 调用累计次数
    * storage_gb        当前存储用量（瞬时值，GB）
    * agent_concurrency 当前智能体并发占用（瞬时值）
- 配额上限由 ``services.quota_service.plan_quota(plan)`` 给出，
  领域模型不反向依赖服务层。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from common.constants import SubscriptionPlan, TenantStatus
from common.ids import tenant_id
from common.timeutils import utc_now

# 配额计数器键与初值（与 ORM 层 _DEFAULT_QUOTA_USED 保持一致）
QUOTA_METRICS: tuple[str, ...] = ("api_calls", "storage_gb", "agent_concurrency")


def default_quota_used() -> dict[str, float]:
    """新租户配额计数器初值。"""
    return {"api_calls": 0, "storage_gb": 0.0, "agent_concurrency": 0}


class Tenant(BaseModel):
    """租户（施工单位/咨询机构等使用方）。"""

    id: str = Field(default_factory=tenant_id, description="租户 ID (tnt_ 前缀)")
    name: str = Field(min_length=1, max_length=128, description="租户名称")
    code: str = Field(min_length=1, max_length=64, description="租户编码（唯一业务标识）")
    contact: str | None = Field(default=None, max_length=128, description="联系人")
    phone: str | None = Field(default=None, max_length=32, description="联系电话")
    status: TenantStatus = Field(default=TenantStatus.ACTIVE)
    # ---------- 6b.1 SaaS 字段 ----------
    plan: SubscriptionPlan = Field(
        default=SubscriptionPlan.TRIAL, description="订阅套餐"
    )
    trial_expires_at: datetime | None = Field(
        default=None, description="试用期到期时间（UTC）；付费套餐为 None"
    )
    quota_used: dict[str, float] = Field(
        default_factory=default_quota_used, description="配额用量计数器"
    )
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def is_trial_expired(self, *, now: datetime | None = None) -> bool:
        """试用期是否已到期（非 trial 套餐或无到期时间 → False）。"""
        if self.plan != SubscriptionPlan.TRIAL or self.trial_expires_at is None:
            return False
        return (now or utc_now()) >= self.trial_expires_at

    def quota_value(self, metric: str) -> float:
        """读取某项配额当前用量（缺失键按 0 处理）。"""
        return float(self.quota_used.get(metric, 0))

    def to_public_dict(self) -> dict[str, Any]:
        """API 输出用 dict（枚举转值、时间转 ISO 字符串由 pydantic 处理）。"""
        return self.model_dump(mode="json")


__all__ = ["Tenant", "QUOTA_METRICS", "default_quota_used"]
