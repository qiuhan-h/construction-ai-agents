"""启动 A2A 服务（独立 HTTP 服务，承载智能体 A2A 通信）。

使用：
    python -m scripts.start_a2a_server
    # 或
    python scripts/start_a2a_server.py

环境变量（与 .env / config/settings 对齐）：
    A2A_HOST        监听地址，默认 0.0.0.0
    A2A_PORT        监听端口，默认 9101
    APP_ENV         dev / staging / prod

占位说明：
    主机 / 端口均为内网地址，本地默认 0.0.0.0:9101；容器化时由 docker-compose 注入。
    阶段二不预置任何业务智能体，注册逻辑由调用方在
    register_business_agents() 中按需开启。
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

# 允许以 `python scripts/start_a2a_server.py` 形式运行
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from common.constants import APP_NAME, APP_VERSION  # noqa: E402
from common.timeutils import to_iso, utc_now  # noqa: E402
from core.a2a.server import get_registry  # noqa: E402

logger = logging.getLogger("scripts.start_a2a_server")


# =====================================================
# 智能体注册（占位：阶段三/四接入）
# =====================================================
def register_business_agents() -> None:
    """注册业务智能体到全局 AgentRegistry。

    阶段二仅做"空跑"——不注册任何业务智能体，仅暴露空 Card 列表。
    阶段三开始接入 safety_audit_agent / compliance_agent / site_monitor_agent。
    """
    registry = get_registry()
    # 当前没有任何业务智能体可注册；
    # 后续实装示意：
    #     from agents.safety_audit_agent import SafetyAuditAgent
    #     registry.register(SafetyAuditAgent(tenant_id="tnt_default"))
    logger.info(
        "A2A 启动时注册的智能体数: %d（阶段二未注入业务智能体）",
        len(registry.list_agents()),
    )


# =====================================================
# 启动入口
# =====================================================
def build_app() -> Any:
    """构造 FastAPI app。"""
    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
    except ImportError as e:
        raise RuntimeError("FastAPI 未安装，无法启动 A2A 服务") from e

    from api.routers.a2a_router import build_a2a_router

    app = FastAPI(
        title=f"{APP_NAME} A2A Server",
        version=APP_VERSION,
        description="智能体间 A2A 协议服务（JSON-RPC 2.0 over HTTP）",
    )

    @app.get("/")
    async def root() -> dict[str, Any]:
        return {
            "service": "a2a",
            "app": APP_NAME,
            "version": APP_VERSION,
            "status": "ok",
            "checked_at": to_iso(utc_now()),
        }

    @app.get("/health")
    async def health() -> dict[str, Any]:
        registry = get_registry()
        return {
            "service": "a2a",
            "status": "ok",
            "agents": len(registry.list_agents()),
            "tasks": len(registry.list_tasks()),
            "checked_at": to_iso(utc_now()),
        }

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Any, exc: Exception) -> JSONResponse:
        logger.exception("A2A 入口未捕获异常: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"code": "10001", "message": "internal error", "detail": str(exc)},
        )

    app.include_router(build_a2a_router())
    return app


def main() -> None:
    host = os.getenv("A2A_HOST", "0.0.0.0")
    port = int(os.getenv("A2A_PORT", "9101"))
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    register_business_agents()
    app = build_app()

    try:
        import uvicorn
    except ImportError as e:
        raise RuntimeError("uvicorn 未安装，无法启动 HTTP 服务") from e

    logger.info("A2A 服务启动: http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level=log_level.lower())


if __name__ == "__main__":
    main()
