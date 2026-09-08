"""计费服务（6b.1 多租户 SaaS，mock 实现）。

职责：
- 用量流水记录（``record_usage``），与配额计数器互补：
  计数器管"限流"，流水管"出账聚合"；
- 月度账单（``generate_bill``）：按账期 ``yyyy-mm``（UTC） upsert，
  mock 计费 = 套餐固定月费（trial 0 元），usage 列快照出账时用量；
- 账单查询（``get_bill`` / ``list_bills``）。

定价（CNY/月，mock，可在配置化阶段替换）：
    trial=0、starter=299、pro=999、enterprise=4999
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from common.constants import SubscriptionPlan
from common.exceptions import NotFoundError
from common.timeutils import from_iso, utc_now
from models.domain.billing import Bill, UsageRecord, current_period

logger = logging.getLogger("services.billing")

# mock 套餐月费（CNY）
PLAN_PRICES: dict[str, float] = {
    SubscriptionPlan.TRIAL.value: 0.0,
    SubscriptionPlan.STARTER.value: 299.0,
    SubscriptionPlan.PRO.value: 999.0,
    SubscriptionPlan.ENTERPRISE.value: 4999.0,
}


def plan_price(plan: str) -> float:
    """套餐月费（未知套餐按 0 处理，避免误收费）。"""
    return float(PLAN_PRICES.get(plan, 0.0))


class BillingService:
    """用量流水 + mock 月费账单。"""

    def __init__(self, repo: Any | None = None) -> None:
        self._repo = repo

    @property
    def repo(self) -> Any:
        if self._repo is None:
            from core.storage.tenant_repo import get_tenant_repository

            self._repo = get_tenant_repository()
        return self._repo

    async def record_usage(
        self,
        tenant_id: str,
        metric: str,
        amount: float,
        *,
        detail: dict[str, Any] | None = None,
        period: str | None = None,
    ) -> UsageRecord:
        """追加一条用量流水（不改变配额计数器）。"""
        record = UsageRecord(
            tenant_id=tenant_id,
            metric=metric,
            amount=float(amount),
            period=period or current_period(),
            detail=detail or {},
        )
        row = self.repo.add_usage_record(
            {
                "tenant_id": record.tenant_id,
                "metric": record.metric,
                "amount": record.amount,
                "period": record.period,
                "detail": record.detail,
                "occurred_at": record.recorded_at,
            }
        )
        return _usage_to_model(row)

    async def generate_bill(
        self, tenant_id: str, *, period: str | None = None
    ) -> Bill:
        """生成（或重算）指定账期账单：mock 金额 = 套餐固定月费。"""
        tenant = self.repo.get_tenant(tenant_id)
        if tenant is None:
            raise NotFoundError(
                f"租户不存在: {tenant_id}", details={"tenant_id": tenant_id}
            )
        bill_period = period or current_period()
        plan = tenant["plan"]
        cost = plan_price(plan)
        usage_snapshot = dict(tenant.get("quota_used") or {})
        row = self.repo.upsert_bill(
            {
                "tenant_id": tenant_id,
                "plan": plan,
                "period": bill_period,
                "usage": usage_snapshot,
                "cost": cost,
                "currency": "CNY",
                "status": "issued",
                "detail": {
                    "pricing": "mock_fixed_monthly_fee",
                    "monthly_fee": cost,
                },
            }
        )
        logger.info(
            "出账 tenant=%s period=%s plan=%s cost=%s",
            tenant_id,
            bill_period,
            plan,
            cost,
        )
        return _bill_to_model(row)

    async def get_bill(self, tenant_id: str, bill_id: str) -> Bill | None:
        row = self.repo.get_bill(tenant_id, bill_id)
        return _bill_to_model(row) if row else None

    async def list_bills(self, tenant_id: str) -> list[Bill]:
        rows = self.repo.list_bills(tenant_id)
        return [_bill_to_model(r) for r in rows]


# =====================================================
# dict → 模型
# =====================================================
def _usage_to_model(row: dict[str, Any]) -> UsageRecord:
    return UsageRecord(
        id=row.get("usage_id"),
        tenant_id=row["tenant_id"],
        metric=row["metric"],
        amount=float(row["amount"]),
        period=row.get("period"),
        detail=dict(row.get("detail") or {}),
        recorded_at=from_iso(row["occurred_at"]) if row.get("occurred_at") else utc_now(),
    )


def _bill_to_model(row: dict[str, Any]) -> Bill:
    return Bill(
        id=row.get("bill_id"),
        tenant_id=row["tenant_id"],
        plan=SubscriptionPlan(row["plan"]),
        period=row["period"],
        usage=dict(row.get("usage") or {}),
        cost=float(row["cost"]),
        currency=row.get("currency", "CNY"),
        status=row.get("status", "issued"),
        detail=dict(row.get("detail") or {}),
        created_at=from_iso(row["created_at"]) if row.get("created_at") else utc_now(),
    )


# =====================================================
# 单例 + 测试重置
# =====================================================
_service: BillingService | None = None
_service_lock = threading.Lock()


def get_billing_service() -> BillingService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = BillingService()
    return _service


def reset_billing_service() -> None:
    """测试用：重置单例。"""
    global _service
    with _service_lock:
        _service = None


__all__ = [
    "BillingService",
    "PLAN_PRICES",
    "plan_price",
    "get_billing_service",
    "reset_billing_service",
]
