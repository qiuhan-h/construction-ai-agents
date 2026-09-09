"""MCP HTTP 路由：基于 core.mcp.server 的 FastAPI 路由。

端点（/api/v1/mcp 前缀）：
  GET  /api/v1/mcp/resources          列出资源（可按 ?prefix=regulation:// 过滤）
  GET  /api/v1/mcp/resources/read     读取资源（?uri=regulation://xxx）
  GET  /api/v1/mcp/tools              列出工具
  POST /api/v1/mcp/tools/call         调用工具
  GET  /api/v1/mcp/prompts            列出提示词
  POST /api/v1/mcp/prompts/get        渲染提示词
  POST /api/v1/mcp/rpc                JSON-RPC 入口（透传所有方法）
  GET  /api/v1/mcp/health             健康探活

阶段二未引入鉴权；MCP 通常部署在内网，仅可信服务调用。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status

from api.schemas.response_schemas import ApiResponse
from common.exceptions import AppException
from core.mcp.server import MCPServer, get_mcp_service

logger = logging.getLogger("api.routers.mcp")


# =====================================================
# 工具
# =====================================================
def _raise_from_app_exc(exc: AppException) -> None:
    raise HTTPException(status_code=exc.http_status, detail=exc.to_dict())


# =====================================================
# 路由构造
# =====================================================
def build_mcp_router() -> APIRouter:
    """构造 /api/v1/mcp 路由。"""
    router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])
    server = MCPServer()
    service = get_mcp_service()

    # ---------- 资源 ----------
    @router.get("/resources", response_model=ApiResponse[dict])
    async def list_resources(
        prefix: str | None = Query(default=None, description="按 URI 前缀过滤"),
    ) -> ApiResponse[dict[str, Any]]:
        return ApiResponse[dict].ok({"resources": service.list_resources(prefix)})

    @router.get("/resources/read", response_model=ApiResponse[dict])
    async def read_resource(uri: str = Query(..., description="资源 URI")) -> ApiResponse[dict[str, Any]]:
        try:
            data = await service.read_resource(uri)
        except AppException as e:
            _raise_from_app_exc(e)
        return ApiResponse[dict].ok(data)

    # ---------- 工具 ----------
    @router.get("/tools", response_model=ApiResponse[dict])
    async def list_tools() -> ApiResponse[dict[str, Any]]:
        return ApiResponse[dict].ok({"tools": service.list_tools()})

    @router.post("/tools/call", response_model=ApiResponse[dict])
    async def call_tool(payload: dict[str, Any]) -> ApiResponse[dict[str, Any]]:
        name = payload.get("name")
        arguments = payload.get("arguments") or {}
        if not name:
            raise HTTPException(
                status_code=400,
                detail={"code": "10002", "message": "name 不能为空"},
            )
        try:
            data = await service.call_tool(name, arguments)
        except AppException as e:
            _raise_from_app_exc(e)
        return ApiResponse[dict].ok(data)

    # ---------- 提示词 ----------
    @router.get("/prompts", response_model=ApiResponse[dict])
    async def list_prompts() -> ApiResponse[dict[str, Any]]:
        return ApiResponse[dict].ok({"prompts": service.list_prompts()})

    @router.post("/prompts/get", response_model=ApiResponse[dict])
    async def get_prompt(payload: dict[str, Any]) -> ApiResponse[dict[str, Any]]:
        name = payload.get("name")
        arguments = payload.get("arguments") or {}
        if not name:
            raise HTTPException(
                status_code=400,
                detail={"code": "10002", "message": "name 不能为空"},
            )
        try:
            data = await service.render_prompt(name, arguments)
        except AppException as e:
            _raise_from_app_exc(e)
        return ApiResponse[dict].ok(data)

    # ---------- JSON-RPC 透传 ----------
    @router.post("/rpc", status_code=status.HTTP_200_OK)
    async def rpc_entry(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail={"message": f"invalid JSON: {e}"}) from e
        return await server.handle_raw(body)

    # ---------- 健康 ----------
    @router.get("/health", response_model=ApiResponse[dict])
    async def health() -> ApiResponse[dict[str, Any]]:
        from common.timeutils import to_iso, utc_now
        from core.mcp.server import MCP_PROTOCOL_VERSION

        return ApiResponse[dict].ok({
            "healthy": True,
            "protocol_version": MCP_PROTOCOL_VERSION,
            "resource_count": len(service.list_resources()),
            "tool_count": len(service.list_tools()),
            "prompt_count": len(service.list_prompts()),
            "checked_at": to_iso(utc_now()),
        })

    return router


def mount_mcp(app: Any) -> None:
    """把 MCP 路由挂到 FastAPI app 上。"""
    app.include_router(build_mcp_router())


__all__ = [
    "build_mcp_router",
    "mount_mcp",
]
