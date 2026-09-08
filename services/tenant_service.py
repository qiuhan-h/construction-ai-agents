"""租户管理服务（6b.1 多租户 SaaS）。

职责：
- 自助注册：trial 套餐 30 天试用期 + 初始配额（quota_used 归零）；
- 套餐升级：trial/starter/pro/enterprise，升级后状态机 trial → active；
- 状态机：trial → active → suspended → closed（closed 为终态）；
- 配额查询：委托 ``QuotaService``（snapshot / check）。

约定：
- 全部方法 async（与项目其他 service 一致）；
- 仓储层自动 ORM → 内存降级，无外部依赖可跑；
- 不改动既有智能体 / API 逻辑；租户上下文注入在 Task 6 中间件完成。
"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta
from typing import Any

from common.constants import SubscriptionPlan, TenantStatus
from common.exceptions import (
    NotFoundError,
    TenantConflictError,
    ValidationError,
)
from common.timeutils import from_iso, utc_now
from models.domain.tenant import Tenant, default_quota_used

logger = logging.getLogger("services.tenant")

# 试用时长（天）—— spec FR-6b.1：trial 套餐 30d
TRIAL_DAYS = 30

# 可升级的目标套餐（trial 仅由注册产生，不能"升级"回 trial）
_PAID_PLANS = {
    SubscriptionPlan.STARTER.value,
    SubscriptionPlan.PRO.value,
    SubscriptionPlan.ENTERPRISE.value,
}


def _to_model(row: dict[str, Any]) -> Tenant:
    """仓储 dict → 领域 Tenant 模型。"""
    return Tenant(
        id=row["tenant_id"],
        name=row["name"],
        code=row["code"],
        contact=row.get("contact"),
        phone=row.get("phone"),
        status=TenantStatus(row.get("status", TenantStatus.ACTIVE.value)),
        plan=SubscriptionPlan(row.get("plan", SubscriptionPlan.TRIAL.value)),
        trial_expires_at=(
            from_iso(row["trial_expires_at"])
            if row.get("trial_expires_at")
            else None
        ),
        quota_used=dict(row.get("quota_used") or default_quota_used()),
        created_at=from_iso(row["created_at"]) if row.get("created_at") else utc_now(),
        updated_at=from_iso(row["updated_at"]) if row.get("updated_at") else utc_now(),
    )


class TenantService:
    """租户注册 / 查询 / 升级 / 停用 / 注销。"""

    def __init__(self, repo: Any | None = None) -> None:
        self._repo = repo

    @property
    def repo(self) -> Any:
        if self._repo is None:
            from core.storage.tenant_repo import get_tenant_repository

            self._repo = get_tenant_repository()
        return self._repo

    # ---------- 注册 / 查询 ----------
    async def register(
        self,
        *,
        name: str,
        code: str,
        contact: str | None = None,
        phone: str | None = None,
    ) -> Tenant:
        """自助注册新租户：trial 套餐 + 30 天试用 + 初始零配额。"""
        if not name or not name.strip():
            raise ValidationError("租户名称不能为空", details={"field": "name"})
        if not code or not code.strip():
            raise ValidationError("租户编码不能为空", details={"field": "code"})
        code = code.strip()
        if self.repo.get_tenant_by_code(code) is not None:
            raise TenantConflictError(
                f"租户编码已存在: {code}",
                details={"code": code, "reason": "duplicate_code"},
            )

        tenant = Tenant(
            name=name.strip(),
            code=code,
            contact=contact,
            phone=phone,
            status=TenantStatus.TRIAL,
            plan=SubscriptionPlan.TRIAL,
            trial_expires_at=utc_now() + timedelta(days=TRIAL_DAYS),
            quota_used=default_quota_used(),
        )
        row = self.repo.create_tenant(
            {
                "tenant_id": tenant.id,
                "name": tenant.name,
                "code": tenant.code,
                "contact": tenant.contact,
                "phone": tenant.phone,
                "status": tenant.status.value,
                "plan": tenant.plan.value,
                "trial_expires_at": tenant.trial_expires_at,
                "quota_used": dict(tenant.quota_used),
            }
        )
        logger.info(
            "新租户注册 id=%s code=%s 试用至 %s",
            row["tenant_id"],
            row["code"],
            row["trial_expires_at"],
        )
        return _to_model(row)

    async def get(self, tenant_id: str) -> Tenant | None:
        row = self.repo.get_tenant(tenant_id)
        return _to_model(row) if row else None

    async def get_by_code(self, code: str) -> Tenant | None:
        row = self.repo.get_tenant_by_code(code)
        return _to_model(row) if row else None

    async def list(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[Tenant], int]:
        rows, total = self.repo.list_tenants(limit=limit, offset=offset)
        return [_to_model(r) for r in rows], total

    # ---------- 套餐 / 状态机 ----------
    async def upgrade_plan(self, tenant_id: str, plan: str) -> Tenant:
        """升级到付费套餐（starter/pro/enterprise）。

        - trial/active/suspended → 目标套餐 + status=active + 清除试用到期；
        - closed（已注销）→ 409 冲突；
        - 目标为 trial 或未知套餐 → 400 参数错误。
        """
        target = self._validate_paid_plan(plan)
        row = self.repo.get_tenant(tenant_id)
        if row is None:
            raise NotFoundError(
                f"租户不存在: {tenant_id}", details={"tenant_id": tenant_id}
            )
        if row["status"] == TenantStatus.CLOSED.value:
            raise TenantConflictError(
                "已注销租户不可变更套餐",
                details={"tenant_id": tenant_id, "status": row["status"]},
            )
        updated = self.repo.update_tenant(
            tenant_id,
            plan=target.value,
            status=TenantStatus.ACTIVE.value,
            trial_expires_at=None,
        )
        logger.info("租户 %s 升级套餐 → %s", tenant_id, target.value)
        return _to_model(updated)

    async def suspend(self, tenant_id: str) -> Tenant:
        """停用租户（trial/active → suspended）。"""
        row = self._require_tenant(tenant_id)
        if row["status"] not in (
            TenantStatus.TRIAL.value,
            TenantStatus.ACTIVE.value,
        ):
            raise TenantConflictError(
                f"当前状态 {row['status']} 不可停用（仅 trial/active 可停用）",
                details={"tenant_id": tenant_id, "status": row["status"]},
            )
        updated = self.repo.update_tenant(
            tenant_id, status=TenantStatus.SUSPENDED.value
        )
        return _to_model(updated)

    async def close(self, tenant_id: str) -> Tenant:
        """注销租户（任意非 closed 状态 → closed，终态）。"""
        row = self._require_tenant(tenant_id)
        if row["status"] == TenantStatus.CLOSED.value:
            raise TenantConflictError(
                "租户已注销，不可重复操作",
                details={"tenant_id": tenant_id, "status": row["status"]},
            )
        updated = self.repo.update_tenant(
            tenant_id, status=TenantStatus.CLOSED.value
        )
        return _to_model(updated)

    # ---------- 配额（委托 QuotaService） ----------
    async def check_quota(
        self,
        tenant_id: str,
        metric: str = "api_calls",
        amount: float = 1.0,
    ) -> bool:
        from services.quota_service import get_quota_service

        return await get_quota_service().check(tenant_id, metric, amount)

    async def quota_snapshot(self, tenant_id: str) -> dict[str, Any]:
        from services.quota_service import get_quota_service

        return await get_quota_service().snapshot(tenant_id)

    # ---------- 内部 ----------
    def _require_tenant(self, tenant_id: str) -> dict[str, Any]:
        row = self.repo.get_tenant(tenant_id)
        if row is None:
            raise NotFoundError(
                f"租户不存在: {tenant_id}", details={"tenant_id": tenant_id}
            )
        return row

    @staticmethod
    def _validate_paid_plan(plan: str) -> SubscriptionPlan:
        if not plan or plan not in _PAID_PLANS:
            raise ValidationError(
                f"仅支持升级到付费套餐: {sorted(_PAID_PLANS)}",
                details={"plan": plan},
            )
        return SubscriptionPlan(plan)


# =====================================================
# 单例 + 测试重置
# =====================================================
_service: TenantService | None = None
_service_lock = threading.Lock()


def get_tenant_service() -> TenantService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = TenantService()
    return _service


def reset_tenant_service() -> None:
    """测试用：重置单例。"""
    global _service
    with _service_lock:
        _service = None


__all__ = [
    "TenantService",
    "TRIAL_DAYS",
    "get_tenant_service",
    "reset_tenant_service",
]
