"""移动端精简路由（6c.1）。

端点（/api/v1/mobile 前缀）：
  GET /api/v1/mobile/dashboard   首页仪表盘（聚合 KPI + 最近 5 条告警 + 项目卡片）
  GET /api/v1/mobile/alerts      告警列表（≤20 条精简字段）
  GET /api/v1/mobile/projects    项目卡片列表（≤10 个）

设计：
- 响应体 < 5KB（TR-8.1）：字段精简 + 列表截断；
- 无外部数据源时返回空壳结构（不抛错，移动端可渲染空状态）；
- 数据来自既有仓储/服务（共享桌面端数据源，仅裁剪输出字段）。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Response

from api.dependencies.auth import AuthContext, get_auth_context
from api.schemas.mobile_schemas import (
    MobileAlertListItem,
    MobileDashboard,
    MobileProjectCard,
)
from api.schemas.response_schemas import ApiResponse
from common.timeutils import to_iso, utc_now

logger = logging.getLogger("api.routers.mobile")

# 移动端截断常量
MAX_ALERTS_DASHBOARD = 5
MAX_ALERTS_LIST = 20
MAX_PROJECTS = 10


def build_mobile_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/mobile", tags=["mobile"])

    @router.get("/dashboard", response_model=ApiResponse[MobileDashboard])
    async def get_dashboard(
        response: Response,
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        """移动端首页仪表盘（精简聚合，< 5KB）。"""
        dashboard = _build_dashboard(auth)
        body = ApiResponse[MobileDashboard].ok(dashboard, message="mobile dashboard")
        # 设置 Content-Length 供客户端校验
        body_json = body.model_dump_json()
        response.headers["Content-Length"] = str(len(body_json.encode()))
        return body.model_dump(mode="json")

    @router.get("/alerts", response_model=ApiResponse[list])
    async def get_alerts(
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        """移动端告警列表（≤20 条精简字段）。"""
        alerts = _fetch_alerts(auth.tenant_id, limit=MAX_ALERTS_LIST)
        return ApiResponse.ok(alerts, message=f"{len(alerts)} alerts").model_dump(
            mode="json"
        )

    @router.get("/projects", response_model=ApiResponse[list])
    async def get_projects(
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        """移动端项目卡片列表（≤10 个）。"""
        projects = _fetch_projects(auth.tenant_id, limit=MAX_PROJECTS)
        return ApiResponse.ok(
            projects, message=f"{len(projects)} projects"
        ).model_dump(mode="json")

    return router


# =====================================================
# 数据组装（从既有仓储获取，裁剪为移动端精简字段）
# =====================================================
def _build_dashboard(auth: AuthContext) -> MobileDashboard:
    """聚合移动端首页数据。"""
    alerts = _fetch_alerts(auth.tenant_id, limit=MAX_ALERTS_DASHBOARD)
    projects = _fetch_projects(auth.tenant_id, limit=MAX_PROJECTS)
    open_alerts = sum(1 for a in alerts if a.get("status") == "open")
    safety_score = _aggregate_safety_score(projects)

    return MobileDashboard(
        tenant_name=auth.tenant_id,
        open_alerts=open_alerts,
        safety_score=safety_score,
        alerts=[MobileAlertListItem(**a) for a in alerts],
        projects=[MobileProjectCard(**p) for p in projects],
        updated_at=to_iso(utc_now()),
    )


def _fetch_alerts(tenant_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """从告警仓储获取精简告警列表。"""
    try:
        from core.storage.sqlalchemy_repos import get_session_scope
        from models.database import AlertTable

        with get_session_scope() as s:
            rows = (
                s.query(AlertTable)
                .filter(AlertTable.tenant_id == tenant_id)
                .order_by(AlertTable.triggered_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "level": getattr(r, "severity", "info"),
                    "title": (getattr(r, "message", "") or "")[:50],
                    "source": getattr(r, "source", None),
                    "status": getattr(r, "status", "open"),
                    "occurred_at": to_iso(r.triggered_at) if r.triggered_at else None,
                }
                for r in rows
            ]
    except Exception as e:  # noqa: BLE001
        logger.debug("移动端告警查询降级: %s", e)
        return []


def _fetch_projects(tenant_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """从项目仓储获取精简项目卡片。"""
    try:
        from core.storage.sqlalchemy_repos import get_session_scope
        from models.database import ProjectTable

        with get_session_scope() as s:
            rows = (
                s.query(ProjectTable)
                .filter(ProjectTable.tenant_id == tenant_id)
                .order_by(ProjectTable.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "status": getattr(r, "status", "active"),
                    "safety_score": getattr(r, "safety_score", None),
                    "open_alerts": 0,
                }
                for r in rows
            ]
    except Exception as e:  # noqa: BLE001
        logger.debug("移动端项目查询降级: %s", e)
        return []


def _aggregate_safety_score(projects: list[dict[str, Any]]) -> float | None:
    """从项目卡片聚合安全评分（均值）。"""
    scores = [
        p["safety_score"]
        for p in projects
        if p.get("safety_score") is not None
    ]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 1)


__all__ = ["build_mobile_router"]
