"""智能体管理路由（4d）。

端点（/api/v1/agents 前缀）：
  GET  /api/v1/agents                  列出当前租户可用的业务智能体（含全局元数据）
  GET  /api/v1/agents/supported        列出 AgentManager 支持的智能体白名单
  POST /api/v1/agents/{name}/invoke    通过 HTTP 触发智能体方法（A2A send_message 包装）
  GET  /api/v1/agents/{name}/card      读取 Agent Card 简化版

设计：
- 4d 调用 AgentManager.get() 懒加载智能体实例；
- /invoke 把入参包成 A2AMessage，调 BaseAgent.handle()；
- 复用 ApiResponse[dict] 统一包装。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies.agent_manager import AgentManager, get_agent_manager
from api.dependencies.auth import AuthContext, get_auth_context
from api.schemas.response_schemas import ApiResponse
from common.exceptions import AppException
from common.ids import message_id as new_message_id
from common.ids import task_id as new_task_id
from core.a2a.message import A2AMessage, MessagePart, Task, TaskState

logger = logging.getLogger("api.routers.agents")


def _raise_from_app_exc(exc: AppException) -> None:
    raise HTTPException(status_code=exc.http_status, detail=exc.to_dict())


def build_agents_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

    @router.get("", response_model=ApiResponse[dict])
    async def list_agents(
        auth: AuthContext = Depends(get_auth_context),
        mgr: AgentManager = Depends(get_agent_manager),
    ) -> ApiResponse[dict[str, Any]]:
        # 1) 列出 AgentManager 白名单 + 当前租户已实例化
        supported = mgr.list_supported()
        cached = {a.name: a for a in mgr.list_for_tenant(auth.tenant_id)}
        items: list[dict[str, Any]] = []
        for name in supported:
            agent = cached.get(name)
            card = getattr(agent, "card", None)
            items.append(
                {
                    "name": name,
                    "version": getattr(agent, "version", None) or (card.version if card else None),
                    "description": getattr(agent, "description", "")
                    or (card.description if card else ""),
                    "skills": [s.skill_id for s in (card.skills if card else [])],
                    "instantiated": agent is not None,
                }
            )
        return ApiResponse[dict].ok(
            {
                "tenant_id": auth.tenant_id,
                "agents": items,
                "total": len(items),
            }
        )

    @router.get("/supported", response_model=ApiResponse[dict])
    async def list_supported(
        mgr: AgentManager = Depends(get_agent_manager),
    ) -> ApiResponse[dict[str, Any]]:
        return ApiResponse[dict].ok({"supported": mgr.list_supported()})

    @router.get("/{name}/card", response_model=ApiResponse[dict])
    async def get_agent_card(
        name: str,
        auth: AuthContext = Depends(get_auth_context),
        mgr: AgentManager = Depends(get_agent_manager),
    ) -> ApiResponse[dict[str, Any]]:
        try:
            agent = await mgr.get(name, auth.tenant_id)
        except AppException as e:
            _raise_from_app_exc(e)
        card = getattr(agent, "card", None)
        if card is None:
            return ApiResponse[dict].ok(
                {
                    "name": name,
                    "version": getattr(agent, "version", None),
                    "description": getattr(agent, "description", ""),
                    "skills": [],
                }
            )
        return ApiResponse[dict].ok(
            {
                "name": card.name,
                "version": card.version,
                "description": card.description,
                "protocol_version": card.protocol_version,
                "skills": [
                    {
                        "skill_id": s.skill_id,
                        "name": s.name,
                        "description": s.description,
                    }
                    for s in card.skills
                ],
            }
        )

    @router.post("/{name}/invoke", response_model=ApiResponse[dict])
    async def invoke_agent(
        name: str,
        payload: dict[str, Any],
        auth: AuthContext = Depends(get_auth_context),
        mgr: AgentManager = Depends(get_agent_manager),
    ) -> ApiResponse[dict[str, Any]]:
        """通过 HTTP 触发智能体方法。

        payload 形如：
          {
            "method": "agent.send_message",     # 可选，默认 agent.send_message
            "params": {                          # 透传到 A2AMessage.metadata / parts
                "project_id": "prj_xxx",
                "plan_id": "plan_xxx",
                "message": {"text": "..."}       # 可选纯文本
            }
          }
        """
        try:
            agent = await mgr.get(name, auth.tenant_id)
        except AppException as e:
            _raise_from_app_exc(e)

        method = str(payload.get("method") or "agent.send_message")
        params = payload.get("params") or {}
        # 构造 A2AMessage
        text = None
        if isinstance(params.get("message"), dict):
            text = str(params["message"].get("text") or "")
        elif isinstance(params.get("message"), str):
            text = params["message"]
        elif "text" in params:
            text = str(params.get("text") or "")

        parts: list[MessagePart] = []
        if text:
            parts.append(MessagePart(type="text", text=text))
        # data 载荷：除 message 外的全部 params
        data_payload = {k: v for k, v in params.items() if k != "message"}
        if data_payload:
            parts.append(MessagePart(type="data", data=data_payload))

        # 注入租户：不允许客户端伪造 tenant_id
        metadata = dict(data_payload.get("metadata") or {})
        metadata.setdefault("project_id", data_payload.get("project_id"))
        metadata.setdefault("plan_id", data_payload.get("plan_id"))
        metadata.setdefault("via", "api/agents/invoke")

        msg = A2AMessage(
            message_id=new_message_id(),
            tenant_id=auth.tenant_id,
            role="user",
            parts=parts,
            metadata=metadata,
        )
        task = Task(
            task_id=new_task_id(),
            agent_name=name,
            tenant_id=auth.tenant_id,
            message_id=msg.message_id,
        )
        task.transition(TaskState.RUNNING)
        try:
            reply = await agent.handle(msg, task)
        except AppException as e:
            task.transition(TaskState.FAILED, error=e.to_dict())
            _raise_from_app_exc(e)
        except Exception as e:  # noqa: BLE001
            task.transition(TaskState.FAILED, error={"message": str(e)})
            logger.exception("智能体调用失败: name=%s err=%s", name, e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "10001", "message": f"agent failed: {e!s}"},
            ) from e
        task.transition(TaskState.COMPLETED)

        return ApiResponse[dict].ok(
            {
                "task_id": task.task_id,
                "agent": name,
                "method": method,
                "tenant_id": auth.tenant_id,
                "state": task.state.value,
                "reply": {
                    "message_id": reply.message_id if reply else None,
                    "parts": [p.to_payload() for p in (reply.parts if reply else [])],
                    "metadata": reply.metadata if reply else {},
                },
            }
        )

    return router


__all__ = ["build_agents_router"]
