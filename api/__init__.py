"""api HTTP 接入层。

阶段二仅包含 A2A / MCP 协议端点与对应 Pydantic Schemas，
业务侧路由（agents / tasks / reports / websocket）留到阶段四。
"""

from api.routers.a2a_router import build_a2a_router
from api.routers.mcp_router import build_mcp_router
from api.schemas import (
    ApiResponse,
    ErrorResponse,
    Page,
    PaginationQuery,
)

__all__ = [
    # 路由工厂
    "build_a2a_router",
    "build_mcp_router",
    # 通用响应 / 分页
    "ApiResponse",
    "ErrorResponse",
    "Page",
    "PaginationQuery",
]
