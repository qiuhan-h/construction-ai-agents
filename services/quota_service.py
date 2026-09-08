"""配额与限流服务（6b.1 多租户 SaaS）。

职责：
- 维护各套餐配额表 ``PLAN_QUOTAS``（-1 表示不限量）；
- API 调用计数（``consume``，累计增量）、存储上报（``report_storage``，
  瞬时 gauge）、智能体并发槽位（``acquire_slot`` / ``release_slot``）；
- 超额抛 ``QuotaExceededError``（错误码 30004，HTTP 429）；
- 试用到期 / 租户停用 → 拒绝服务（429 trial_expired / 403 suspended）；
- 每次用量同步追加 ``usage_records`` 流水，供 billing 按月聚合。

设计约定：
- 服务方法为 async（与项目其他 service 一致），内部仓储调用为同步；
- 配额计数器权威来源是租户 ``quota_used`` JSON 字段，更新时整体赋值；
- 无外部依赖：仓储层自动 ORM → 内存降级。
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from common.constants import SubscriptionPlan, TenantStatus
from common.exceptions import (
    NotFoundError,
    QuotaExceededError,
    TenantSuspendedError,
)
from common.timeutils import from_iso, utc_now
from models.domain.billing import current_period

logger = logging.getLogger("services.quota")

# 不限量哨兵值
UNLIMITED = -1

# 套餐配额表（与 spec FR-6b.1 对齐：trial 30 天 + 100 次调用）
PLAN_QUOTAS: dict[str, dict[str, float]] = {
    SubscriptionPlan.TRIAL.value: {
        "api_calls": 100,
        "storage_gb": 1.0,
        "agent_concurrency": 1,
    },
    SubscriptionPlan.STARTER.value: {
        "api_calls": 10_000,
        "storage_gb": 10.0,
        "agent_concurrency": 3,
    },
    SubscriptionPlan.PRO.value: {
        "api_calls": 100_000,
        "storage_gb": 100.0,
        "agent_concurrency": 10,
    },
    SubscriptionPlan.ENTERPRISE.value: {
        "api_calls": UNLIMITED,
        "storage_gb": 1_000.0,
        "agent_concurrency": 50,
    },
}

METRIC_API_CALLS = "api_calls"
METRIC_STORAGE_GB = "storage_gb"
METRIC_CONCURRENCY = "agent_concurrency"
METRICS: tuple[str, ...] = (
    METRIC_API_CALLS,
    METRIC_STORAGE_GB,
    METRIC_CONCURRENCY,
)


def plan_quota(plan: str) -> dict[str, float]:
    """返回套餐配额表（未知套餐按 trial 处理，fail-secure 取最小额度）。"""
    return dict(PLAN_QUOTAS.get(plan, PLAN_QUOTAS[SubscriptionPlan.TRIAL.value]))


def is_unlimited(value: float) -> bool:
    return value is not None and value < 0


class QuotaService:
    """配额检查 / 计数 / 并发槽位。"""

    def __init__(self, repo: Any | None = None) -> None:
        self._repo = repo  # 延迟注入；None 时走工厂

    # ---------- 仓储 ----------
    @property
    def repo(self) -> Any:
        if self._repo is None:
            from core.storage.tenant_repo import get_tenant_repository

            self._repo = get_tenant_repository()
        return self._repo

    # ---------- 查询 ----------
    async def snapshot(self, tenant_id: str) -> dict[str, Any]:
        """返回租户配额快照：used / limit / remaining（remaining=None 表示不限量）。"""
        tenant = self._load_tenant(tenant_id)
        plan = tenant["plan"]
        limits = plan_quota(plan)
        used = tenant.get("quota_used") or {}
        remaining: dict[str, float | None] = {}
        for metric in METRICS:
            limit = float(limits[metric])
            u = float(used.get(metric, 0))
            remaining[metric] = None if is_unlimited(limit) else max(0.0, limit - u)
        return {
            "tenant_id": tenant_id,
            "plan": plan,
            "status": tenant["status"],
            "trial_expires_at": tenant.get("trial_expires_at"),
            "used": {m: float(used.get(m, 0)) for m in METRICS},
            "limit": {m: float(limits[m]) for m in METRICS},
            "remaining": remaining,
        }

    async def check(
        self, tenant_id: str, metric: str = METRIC_API_CALLS, amount: float = 1.0
    ) -> bool:
        """仅检查是否允许（不变更计数）。trial 到期 / 停用 / 超额 → False。"""
        try:
            tenant = self._load_tenant(tenant_id)
            self._guard_status(tenant)
            self._guard_trial(tenant)
            self._guard_limit(tenant, metric, amount)
            return True
        except (QuotaExceededError, TenantSuspendedError, NotFoundError):
            return False

    # ---------- 计数 ----------
    async def consume(
        self,
        tenant_id: str,
        metric: str = METRIC_API_CALLS,
        amount: float = 1.0,
        *,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """消耗配额（累计增量，默认 api_calls +1）。

        超额 / 试用到期 / 停用 → 抛异常（API 层映射 429 / 403）；
        成功后写入用量流水并返回本次计数结果。
        """
        tenant = self._load_tenant(tenant_id)
        self._guard_status(tenant)
        self._guard_trial(tenant)
        self._guard_metric(metric)
        self._guard_limit(tenant, metric, amount)

        used = dict(tenant.get("quota_used") or {})
        new_used = float(used.get(metric, 0)) + float(amount)
        used[metric] = new_used
        self.repo.update_tenant(tenant_id, quota_used=used)
        self.repo.add_usage_record(
            {
                "tenant_id": tenant_id,
                "metric": metric,
                "amount": float(amount),
                "period": current_period(),
                "detail": detail or {"action": "consume"},
            }
        )
        limit = plan_quota(tenant["plan"])[metric]
        logger.info(
            "配额消耗 tenant=%s metric=%s used=%s limit=%s",
            tenant_id,
            metric,
            new_used,
            limit,
        )
        return {
            "allowed": True,
            "metric": metric,
            "used": new_used,
            "limit": float(limit),
            "remaining": None if is_unlimited(limit) else max(0.0, limit - new_used),
        }

    # ---------- 并发槽位 ----------
    async def acquire_slot(self, tenant_id: str) -> dict[str, Any]:
        """申请一个智能体并发槽位（agent_concurrency +1），超额 → 429。"""
        return await self.consume(
            tenant_id,
            METRIC_CONCURRENCY,
            1.0,
            detail={"action": "acquire_slot"},
        )

    async def release_slot(self, tenant_id: str) -> dict[str, Any]:
        """释放一个并发槽位（agent_concurrency -1，最低 0，不做限额拦截）。"""
        tenant = self._load_tenant(tenant_id)
        used = dict(tenant.get("quota_used") or {})
        current = max(0.0, float(used.get(METRIC_CONCURRENCY, 0)) - 1.0)
        used[METRIC_CONCURRENCY] = current
        self.repo.update_tenant(tenant_id, quota_used=used)
        self.repo.add_usage_record(
            {
                "tenant_id": tenant_id,
                "metric": METRIC_CONCURRENCY,
                "amount": -1.0,
                "period": current_period(),
                "detail": {"action": "release_slot"},
            }
        )
        limit = plan_quota(tenant["plan"])[METRIC_CONCURRENCY]
        return {
            "allowed": True,
            "metric": METRIC_CONCURRENCY,
            "used": current,
            "limit": float(limit),
            "remaining": None if is_unlimited(limit) else max(0.0, limit - current),
        }

    # ---------- 存储（瞬时 gauge） ----------
    async def report_storage(self, tenant_id: str, used_gb: float) -> dict[str, Any]:
        """上报当前存储用量（GB，瞬时值）；超套餐上限 → 429。"""
        tenant = self._load_tenant(tenant_id)
        self._guard_status(tenant)
        self._guard_trial(tenant)
        value = max(0.0, float(used_gb))
        self._guard_limit(tenant, METRIC_STORAGE_GB, value, gauge=True)

        used = dict(tenant.get("quota_used") or {})
        used[METRIC_STORAGE_GB] = value
        self.repo.update_tenant(tenant_id, quota_used=used)
        self.repo.add_usage_record(
            {
                "tenant_id": tenant_id,
                "metric": METRIC_STORAGE_GB,
                "amount": value,
                "period": current_period(),
                "detail": {"action": "report_storage"},
            }
        )
        limit = plan_quota(tenant["plan"])[METRIC_STORAGE_GB]
        return {
            "allowed": True,
            "metric": METRIC_STORAGE_GB,
            "used": value,
            "limit": float(limit),
            "remaining": None if is_unlimited(limit) else max(0.0, limit - value),
        }

    # ---------- 内部 ----------
    def _load_tenant(self, tenant_id: str) -> dict[str, Any]:
        tenant = self.repo.get_tenant(tenant_id)
        if tenant is None:
            raise NotFoundError(
                f"租户不存在: {tenant_id}", details={"tenant_id": tenant_id}
            )
        return tenant

    @staticmethod
    def _guard_metric(metric: str) -> None:
        if metric not in METRICS:
            from common.exceptions import ValidationError

            raise ValidationError(
                f"未知配额指标: {metric}（支持 {', '.join(METRICS)}）",
                details={"metric": metric},
            )

    @staticmethod
    def _guard_status(tenant: dict[str, Any]) -> None:
        status = tenant.get("status")
        if status in (TenantStatus.SUSPENDED.value, TenantStatus.CLOSED.value):
            raise TenantSuspendedError(
                f"租户已{ '停用' if status == TenantStatus.SUSPENDED.value else '注销' }，拒绝服务",
                details={"tenant_id": tenant["tenant_id"], "status": status},
            )

    @staticmethod
    def _guard_trial(tenant: dict[str, Any]) -> None:
        if tenant.get("plan") != SubscriptionPlan.TRIAL.value:
            return
        expires = tenant.get("trial_expires_at")
        if not expires:
            return
        try:
            if utc_now() >= from_iso(expires):
                raise QuotaExceededError(
                    "试用期已结束，请升级套餐",
                    details={
                        "tenant_id": tenant["tenant_id"],
                        "reason": "trial_expired",
                        "trial_expires_at": expires,
                    },
                )
        except QuotaExceededError:
            raise
        except Exception:  # noqa: BLE001
            logger.warning("trial_expires_at 解析失败，按未到期处理: %s", expires)

    @staticmethod
    def _guard_limit(
        tenant: dict[str, Any], metric: str, amount: float, *, gauge: bool = False
    ) -> None:
        limit = float(plan_quota(tenant["plan"]).get(metric, 0))
        if is_unlimited(limit):
            return
        used = float((tenant.get("quota_used") or {}).get(metric, 0))
        # gauge（存储）直接比较上报值；计数器比较 used + amount
        projected = amount if gauge else used + amount
        if projected > limit:
            raise QuotaExceededError(
                f"配额已用尽：{metric}（已用 {used}，上限 {limit}）",
                details={
                    "tenant_id": tenant["tenant_id"],
                    "metric": metric,
                    "used": used,
                    "limit": limit,
                    "requested": float(amount),
                    "remaining": max(0.0, limit - used),
                },
            )


# =====================================================
# 单例 + 测试重置
# =====================================================
_service: QuotaService | None = None
_service_lock = threading.Lock()


def get_quota_service() -> QuotaService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = QuotaService()
    return _service


def reset_quota_service() -> None:
    """测试用：重置单例（仓储 override 由 core.storage.tenant_repo 负责）。"""
    global _service
    with _service_lock:
        _service = None


__all__ = [
    "QuotaService",
    "PLAN_QUOTAS",
    "plan_quota",
    "is_unlimited",
    "UNLIMITED",
    "METRICS",
    "METRIC_API_CALLS",
    "METRIC_STORAGE_GB",
    "METRIC_CONCURRENCY",
    "get_quota_service",
    "reset_quota_service",
]
