"""施工安全审核智能体的 A2A 处理器：注册与路由挂载。"""

from __future__ import annotations

import logging
from typing import Any

from common.exceptions import A2AAgentNotFoundError
from core.a2a.server import (
    A2AServer,
    AgentRegistry,
    get_registry,
    reset_registry,
)

from agents.safety_audit_agent.agent import SafetyAuditAgent

logger = logging.getLogger("agents.safety_audit_agent.a2a_handlers")


def register_safety_audit_agent(
    agent: SafetyAuditAgent,
    registry: AgentRegistry | None = None,
) -> AgentRegistry:
    """把 SafetyAuditAgent 注册到 AgentRegistry。"""
    reg = registry or get_registry()
    reg.register(agent)
    logger.info(
        "SafetyAuditAgent 已注册: name=%s tenant=%s",
        agent.name, agent.tenant_id,
    )
    return reg


def build_a2a_router(
    agent: SafetyAuditAgent,
    registry: AgentRegistry | None = None,
):
    """构造 A2A 路由（FastAPI Router）。

    使用方式：
        app.include_router(build_a2a_router(agent), prefix="/api/v1/a2a")
    """
    try:
        from fastapi import APIRouter, HTTPException, Request
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("FastAPI 未安装，无法构建 A2A 路由") from e

    from core.a2a.protocol import PROTOCOL_VERSION

    register_safety_audit_agent(agent, registry)
    server = A2AServer(registry=registry or get_registry())
    router = APIRouter()

    @router.get("/{agent_name}/agent.json")
    async def get_card(agent_name: str) -> dict[str, Any]:
        try:
            return server.get_card(agent_name)
        except A2AAgentNotFoundError as e:
            raise HTTPException(status_code=404, detail=e.to_dict()) from e

    @router.post("/{agent_name}/{method}")
    async def post_method(
        agent_name: str, method: str, request: Request
    ) -> dict[str, Any]:
        body = await request.json()
        body.setdefault("method", method)
        body.setdefault("jsonrpc", "2.0")
        if "id" not in body:
            body["id"] = "0"
        body.setdefault("protocol_version", PROTOCOL_VERSION)
        return await server.handle_raw(agent_name, body)

    return router


__all__ = [
    "register_safety_audit_agent",
    "build_a2a_router",
    "reset_registry",
]
