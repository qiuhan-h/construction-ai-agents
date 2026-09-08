"""启动 MCP 服务（独立 HTTP 服务，承载 MCP 资源/工具/提示词）。

使用：
    python -m scripts.start_mcp_server
    # 或
    python scripts/start_mcp_server.py

环境变量：
    MCP_HOST        监听地址，默认 0.0.0.0
    MCP_PORT        监听端口，默认 9201
    LOG_LEVEL       日志级别

注意：
    启动时会自动通过 _bootstrap_default_registry 触发
    core.mcp.resources / tools / prompts 三组子模块的注册。
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from common.constants import APP_NAME, APP_VERSION  # noqa: E402
from common.timeutils import to_iso, utc_now  # noqa: E402
from core.mcp.server import get_mcp_service  # noqa: E402

logger = logging.getLogger("scripts.start_mcp_server")


def build_app() -> Any:
    """构造 FastAPI app。"""
    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
    except ImportError as e:
        raise RuntimeError("FastAPI 未安装，无法启动 MCP 服务") from e

    from api.routers.mcp_router import build_mcp_router

    service = get_mcp_service()  # 触发资源/工具/提示词自注册

    app = FastAPI(
        title=f"{APP_NAME} MCP Server",
        version=APP_VERSION,
        description="模型上下文协议服务（资源/工具/提示词统一访问）",
    )

    @app.get("/")
    async def root() -> dict[str, Any]:
        return {
            "service": "mcp",
            "app": APP_NAME,
            "version": APP_VERSION,
            "status": "ok",
            "checked_at": to_iso(utc_now()),
        }

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "service": "mcp",
            "status": "ok",
            "resource_count": len(service.list_resources()),
            "tool_count": len(service.list_tools()),
            "prompt_count": len(service.list_prompts()),
            "checked_at": to_iso(utc_now()),
        }

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Any, exc: Exception) -> JSONResponse:
        logger.exception("MCP 入口未捕获异常: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"code": "10001", "message": "internal error", "detail": str(exc)},
        )

    app.include_router(build_mcp_router())
    return app


def main() -> None:
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "9201"))
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    app = build_app()

    try:
        import uvicorn
    except ImportError as e:
        raise RuntimeError("uvicorn 未安装，无法启动 HTTP 服务") from e

    logger.info("MCP 服务启动: http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level=log_level.lower())


if __name__ == "__main__":
    main()
