"""FastAPI 主应用（4d 聚合所有路由 + lifespan）。

启动：
    PYTHONPATH=. uvicorn api.main:app --host 0.0.0.0 --port 8000

设计原则（4d D1, D2, D3, D4）：
- lifespan：启动 AgentManager + Orchestrator + EventBus；
- 关闭：orchestrator.stop() + bus.reset() + agent_manager.shutdown()；
- 路由全部异步；
- 4d 默认挂载以下前缀：
  - /api/v1/a2a          智能体间通信（阶段二）
  - /api/v1/mcp          MCP 资源/工具/提示词（阶段二）
  - /api/v1/agents       业务智能体（4d）
  - /api/v1/tasks        异步任务状态（4d）
  - /api/v1/reports      审查报告（4d）
  - /api/v1/orchestrator 编排器 trigger / run / timeline（4d）
  - /api/v1/health       healthz / readyz（4d）
  - /api/v1/ws           实时事件 WebSocket（4d）
  - /                     根 banner
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI

from common.constants import APP_NAME, APP_VERSION

logger = logging.getLogger("api.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期：启动 AgentManager + Orchestrator，关闭清理。"""
    # ---------- 启动 ----------
    # 控制导入阶段噪音；仅在真实启动时输出关键日志
    from api.dependencies.agent_manager import init_agent_manager
    from api.dependencies.orchestrator_provider import init_orchestrator
    from core.events import get_event_bus

    init_agent_manager()
    init_orchestrator()
    bus = get_event_bus()
    logger.info(
        "lifespan: 启动 %s v%s (pid=%s)", APP_NAME, APP_VERSION, os.getpid()
    )
    yield

    # ---------- 关闭 ----------
    from api.dependencies.orchestrator_provider import shutdown_orchestrator

    await shutdown_orchestrator()
    try:
        await bus.reset()
    except Exception as e:  # noqa: BLE001
        logger.warning("EventBus.reset 失败: %s", e)
    logger.info("lifespan: 关闭 %s", APP_NAME)


def create_app() -> FastAPI:
    """构造 FastAPI 实例。供 uvicorn / pytest 复用。"""
    from api.routers import (
        build_a2a_router,
        build_agents_router,
        build_bim_router,
        build_health_router,
        build_mcp_router,
        build_mobile_router,
        build_orchestrator_router,
        build_reports_router,
        build_tasks_router,
        build_tenant_router,
        build_websocket_router,
    )
    from config import get_settings

    settings = get_settings()

    # 7a-5: 生产关闭 /docs 和 /redoc；dev/staging 保留
    docs_enabled = settings.app_env != "prod"

    app = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    # 7a-5: CORS 白名单（可配置）
    if settings.cors_origins:
        from fastapi.middleware.cors import CORSMiddleware

        origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # 7a-5: 安全审计日志中间件（记录写操作审计轨迹）
    from core.middleware import AuditLogMiddleware

    app.add_middleware(AuditLogMiddleware)

    app.include_router(build_a2a_router())
    app.include_router(build_mcp_router())
    app.include_router(build_agents_router())
    app.include_router(build_tasks_router())
    app.include_router(build_reports_router())
    app.include_router(build_orchestrator_router())
    app.include_router(build_health_router())
    app.include_router(build_websocket_router())
    # 6b.1 多租户 SaaS：注册 / 查询 / 升级 / 配额检查
    app.include_router(build_tenant_router())
    # 6c.1 移动端精简 API
    app.include_router(build_mobile_router())
    # 6d.1 BIM 数据 API（边缘端 / 移动端消费）
    app.include_router(build_bim_router())

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, Any]:
        return {
            "name": APP_NAME,
            "version": APP_VERSION,
            "stage": "6d",
            "endpoints": {
                "a2a": "/api/v1/a2a",
                "mcp": "/api/v1/mcp",
                "agents": "/api/v1/agents",
                "tasks": "/api/v1/tasks",
                "reports": "/api/v1/reports",
                "orchestrator": "/api/v1/orchestrator",
                "health": "/api/v1/health",
                "tenants": "/api/v1/tenants",
                "mobile": "/api/v1/mobile",
                "bim": "/api/v1/bim",
                "ws": "/api/v1/ws/events",
                "docs": "/docs",
            },
        }

    return app


# 进程级 app（uvicorn api.main:app 入口）
app = create_app()


__all__ = ["create_app", "app", "lifespan"]
