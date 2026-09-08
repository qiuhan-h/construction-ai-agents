"""多租户 SaaS 路由（6b.1）：租户注册 / 查询 / 升级 / 配额检查。

端点（/api/v1/tenants 前缀）：
  POST /api/v1/tenants                       自助注册（trial 30 天 + 100 次调用）
  GET  /api/v1/tenants/{tenant_id}           查询租户 + 配额快照
  POST /api/v1/tenants/{tenant_id}/upgrade   升级套餐（starter/pro/enterprise）
  POST /api/v1/tenants/{tenant_id}/quota-check 消耗一次配额（超额 → HTTP 429）

设计：
- 注册端点公开（自助开通）；其余端点需 Bearer token 且仅能操作本租户；
- 业务异常（AppException）统一映射为结构化错误体
  ``{"code", "message", "details"}``，HTTP 状态码取自错误码定义；
- 配额超限 → 429（code=30004），租户停用 → 403（code=30003）；
- 不改动既有智能体 / 路由逻辑；租户上下文自动注入在 Task 6 中间件完成。
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.dependencies.auth import AuthContext, get_auth_context
from api.schemas.response_schemas import ApiResponse
from common.exceptions import AppException

logger = logging.getLogger("api.routers.tenants")


# =====================================================
# 请求体（6b.1 内联 schema，避免新增 api/schemas 文件）
# =====================================================
class TenantCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="租户名称")
    code: str = Field(..., min_length=1, max_length=64, description="租户编码（唯一）")
    contact: str | None = Field(default=None, max_length=128, description="联系人")
    phone: str | None = Field(default=None, max_length=32, description="联系电话")


class PlanUpgradeRequest(BaseModel):
    plan: Literal["starter", "pro", "enterprise"] = Field(
        ..., description="目标套餐（付费套餐）"
    )


class QuotaCheckRequest(BaseModel):
    metric: Literal["api_calls", "storage_gb", "agent_concurrency"] = Field(
        default="api_calls", description="配额指标"
    )
    amount: float = Field(default=1.0, gt=0, description="本次消耗量")


# =====================================================
# 异常 → HTTP
# =====================================================
def _http_from_app_exc(exc: AppException) -> HTTPException:
    """AppException → FastAPI HTTPException（结构化 detail）。"""
    return HTTPException(
        status_code=exc.http_status,
        detail={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details or None,
        },
    )


def _ensure_same_tenant(auth: AuthContext, tenant_id: str) -> None:
    """租户隔离：token 中的 tenant_id 必须与路径租户一致。"""
    if auth.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "30002",
                "message": "无权操作其他租户资源",
                "details": {"token_tenant": auth.tenant_id, "path_tenant": tenant_id},
            },
        )


async def _tenant_payload(tenant: Any) -> dict[str, Any]:
    """租户模型 → API 输出（含配额快照）。"""
    from services.quota_service import get_quota_service

    snapshot = await get_quota_service().snapshot(tenant.id)
    return {"tenant": tenant.model_dump(mode="json"), "quota": snapshot}


# =====================================================
# 路由
# =====================================================
def build_tenant_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])

    @router.post(
        "",
        response_model=ApiResponse[dict],
        status_code=status.HTTP_201_CREATED,
    )
    async def register_tenant(body: TenantCreateRequest) -> dict[str, Any]:
        """自助注册：trial 套餐 30 天 + 初始配额。"""
        from services.tenant_service import get_tenant_service

        try:
            tenant = await get_tenant_service().register(
                name=body.name,
                code=body.code,
                contact=body.contact,
                phone=body.phone,
            )
        except AppException as e:
            raise _http_from_app_exc(e) from e
        return ApiResponse[dict].ok(
            await _tenant_payload(tenant),
            message="租户注册成功（trial 套餐，30 天试用）",
        )

    @router.get("/{tenant_id}", response_model=ApiResponse[dict])
    async def get_tenant(
        tenant_id: str,
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        _ensure_same_tenant(auth, tenant_id)
        from services.tenant_service import get_tenant_service

        tenant = await get_tenant_service().get(tenant_id)
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "10003", "message": f"租户不存在: {tenant_id}"},
            )
        return ApiResponse[dict].ok(await _tenant_payload(tenant))

    @router.post("/{tenant_id}/upgrade", response_model=ApiResponse[dict])
    async def upgrade_tenant(
        tenant_id: str,
        body: PlanUpgradeRequest,
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        _ensure_same_tenant(auth, tenant_id)
        from services.tenant_service import get_tenant_service

        try:
            tenant = await get_tenant_service().upgrade_plan(tenant_id, body.plan)
        except AppException as e:
            raise _http_from_app_exc(e) from e
        return ApiResponse[dict].ok(
            await _tenant_payload(tenant), message=f"套餐已升级为 {body.plan}"
        )

    @router.post("/{tenant_id}/quota-check", response_model=ApiResponse[dict])
    async def quota_check(
        tenant_id: str,
        body: QuotaCheckRequest,
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        """消耗一次配额；trial 第 101 次调用在此返回 429。"""
        _ensure_same_tenant(auth, tenant_id)
        from services.quota_service import get_quota_service

        try:
            result = await get_quota_service().consume(
                tenant_id, body.metric, body.amount
            )
        except AppException as e:
            raise _http_from_app_exc(e) from e
        return ApiResponse[dict].ok(result, message="配额消耗成功")

    return router


__all__ = ["build_tenant_router"]
