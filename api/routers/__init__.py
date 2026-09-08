"""api.routers 包：FastAPI 路由聚合。"""

from api.routers.a2a_router import build_a2a_router
from api.routers.agents_router import build_agents_router
from api.routers.bim_router import build_bim_router
from api.routers.health_router import build_health_router
from api.routers.mcp_router import build_mcp_router
from api.routers.mobile_router import build_mobile_router
from api.routers.orchestrator_router import build_orchestrator_router
from api.routers.reports_router import build_reports_router
from api.routers.tasks_router import build_tasks_router
from api.routers.tenant_router import build_tenant_router
from api.routers.websocket_router import build_websocket_router

__all__ = [
    "build_a2a_router",
    "build_agents_router",
    "build_bim_router",
    "build_health_router",
    "build_mcp_router",
    "build_mobile_router",
    "build_orchestrator_router",
    "build_reports_router",
    "build_tasks_router",
    "build_tenant_router",
    "build_websocket_router",
]
