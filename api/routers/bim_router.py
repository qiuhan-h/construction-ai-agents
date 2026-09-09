"""BIM 数据 API 路由（6d.1）。

端点（/api/v1/bim 前缀）：
  GET /api/v1/bim/projects/{project_id}/tree     项目构件树
  GET /api/v1/bim/elements/{element_id}            构件详情
  GET /api/v1/bim/progress/{project_id}            进度对比 + 偏差告警

设计：
- 复用 BIMConnector（mock）/ BIMRealConnector（APS）；
- 凭据缺失 → mock 降级（返回空壳结构，不抛错）；
- 边缘端可消费精简 BIM 数据，不依赖完整 BIM 平台。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from api.dependencies.auth import AuthContext, get_auth_context
from api.schemas.bim_schemas import (
    BIMElement,
    BIMProgressItem,
    BIMProgressResponse,
)
from api.schemas.response_schemas import ApiResponse

logger = logging.getLogger("api.routers.bim")


def build_bim_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/bim", tags=["bim"])

    @router.get(
        "/projects/{project_id}/tree",
        response_model=ApiResponse[list],
    )
    async def get_project_tree(
        project_id: str,
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        """获取 BIM 项目构件树（mock 降级）。"""
        tree = await _fetch_project_tree(auth.tenant_id, project_id)
        return ApiResponse.ok(
            tree, message=f"project tree ({len(tree)} roots)"
        ).model_dump(mode="json")

    @router.get(
        "/elements/{element_id}",
        response_model=ApiResponse[BIMElement],
    )
    async def get_element(
        element_id: str,
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        """获取 BIM 构件详情。"""
        element = await _fetch_element(auth.tenant_id, element_id)
        return ApiResponse.ok(
            element, message=f"element {element_id}"
        ).model_dump(mode="json")

    @router.get(
        "/progress/{project_id}",
        response_model=ApiResponse[BIMProgressResponse],
    )
    async def get_progress(
        project_id: str,
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        """进度对比（计划 vs 实际 + 偏差）。"""
        progress = _compute_progress(auth.tenant_id, project_id)
        return ApiResponse.ok(
            progress, message=f"progress for {project_id}"
        ).model_dump(mode="json")

    return router


# =====================================================
# BIM 数据获取（封装降级逻辑）
# =====================================================
async def _fetch_project_tree(
    tenant_id: str, project_id: str
) -> list[dict[str, Any]]:
    """获取项目构件树。BIM 平台不可达 → mock 降级。"""
    try:
        connector = _get_bim_connector(tenant_id)
        tree = await connector.get_project_tree(project_id)
        return tree or _mock_project_tree(project_id)
    except Exception as e:  # noqa: BLE001
        logger.debug("BIM project tree 降级: %s", e)
        return _mock_project_tree(project_id)


async def _fetch_element(
    tenant_id: str, element_id: str
) -> dict[str, Any]:
    """获取构件详情。BIM 平台不可达 → mock 降级。"""
    try:
        connector = _get_bim_connector(tenant_id)
        element = await connector.get_element(element_id)
        return element or _mock_element(element_id)
    except Exception as e:  # noqa: BLE001
        logger.debug("BIM element 降级: %s", e)
        return _mock_element(element_id)


def _compute_progress(
    tenant_id: str, project_id: str
) -> dict[str, Any]:
    """计算进度对比。无真实数据 → mock 计划 + 实际。"""
    # mock 计划进度
    plan = [
        {"element_id": f"{project_id}-bldg-1", "name": "主楼", "pct": 80.0},
        {"element_id": f"{project_id}-fl-1", "name": "1F", "pct": 100.0},
        {"element_id": f"{project_id}-fl-2", "name": "2F", "pct": 50.0},
    ]
    # mock 实际进度（模拟滞后）
    actual = [
        {"element_id": f"{project_id}-bldg-1", "name": "主楼", "pct": 65.0},
        {"element_id": f"{project_id}-fl-1", "name": "1F", "pct": 95.0},
        {"element_id": f"{project_id}-fl-2", "name": "2F", "pct": 30.0},
    ]

    try:
        from agents.site_monitor_agent.bim_integration import ProgressTracker

        tracker = ProgressTracker(deviation_threshold=10.0)
        items = tracker.compute(plan, actual)
        # 转为响应格式 + 级别
        result_items: list[BIMProgressItem] = []
        delayed = 0
        ahead = 0
        for it in items:
            level = "info"
            if it.deviation < -10:
                level = "critical"
                delayed += 1
            elif it.deviation > 10:
                level = "warning"
                ahead += 1
            result_items.append(
                BIMProgressItem(
                    element_id=it.element_id,
                    name=it.name,
                    plan_pct=it.plan_pct,
                    actual_pct=it.actual_pct,
                    deviation=round(it.deviation, 2),
                    level=level,
                )
            )
        return BIMProgressResponse(
            project_id=project_id,
            items=result_items,
            total=len(result_items),
            delayed=delayed,
            ahead=ahead,
            source="mock",
        ).model_dump()
    except Exception as e:  # noqa: BLE001
        logger.debug("BIM progress 降级: %s", e)
        return BIMProgressResponse(
            project_id=project_id, source="mock"
        ).model_dump()


# =====================================================
# BIM 连接器工厂（优先真实，降级 mock）
# =====================================================
def _get_bim_connector(tenant_id: str) -> Any:
    """获取 BIM 连接器。优先 BIMRealConnector，降级 BIMConnector。"""
    try:
        from agents.site_monitor_agent.bim_integration import (
            BIMConnector,
            make_bim_real_connector,
        )

        # 尝试真实连接器（凭据从 .env 读取，缺失会降级到 mock）
        real = make_bim_real_connector()
        if real is not None:
            return real
    except Exception as e:  # noqa: BLE001
        logger.debug("BIM real connector 不可用: %s", e)

    # 降级到 mock 连接器
    from agents.site_monitor_agent.bim_integration import BIMConnector

    return BIMConnector(tenant_id=tenant_id)


# =====================================================
# mock 数据（与 BIMConnector._mock_project_tree 一致）
# =====================================================
def _mock_project_tree(project_id: str) -> list[dict[str, Any]]:
    return [
        {
            "id": f"{project_id}-bldg-1",
            "type": "IfcBuilding",
            "name": "主楼",
            "children": [
                {
                    "id": f"{project_id}-fl-1",
                    "type": "IfcBuildingStorey",
                    "name": "1F",
                    "children": [],
                },
                {
                    "id": f"{project_id}-fl-2",
                    "type": "IfcBuildingStorey",
                    "name": "2F",
                    "children": [],
                },
            ],
        }
    ]


def _mock_element(element_id: str) -> dict[str, Any]:
    return {
        "element_id": element_id,
        "name": f"Mock-{element_id}",
        "type": "IfcBeam",
        "properties": {
            "material": "C30",
            "dimensions": "300x500",
            "load_bearing": True,
        },
    }


__all__ = ["build_bim_router"]
