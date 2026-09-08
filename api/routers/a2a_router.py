"""A2A HTTP 路由：基于 core.a2a.server 的 FastAPI 路由。

端点（/api/v1/a2a 前缀）：
  POST /api/v1/a2a/agents                       智能体列表（基于 AgentRegistry）
  GET  /api/v1/a2a/agents/{name}                智能体详情（Card）
  GET  /api/v1/a2a/agents/{name}/card           仅返回 AgentCard 全文
  GET  /api/v1/a2a/agents/{name}/health         智能体健康探活
  POST /api/v1/a2a/agents/{name}/messages       发送消息（REST 包装）
  GET  /api/v1/a2a/tasks                        任务列表
  GET  /api/v1/a2a/tasks/{task_id}              查询任务
  POST /api/v1/a2a/tasks/{task_id}/cancel       取消任务
  POST /api/v1/a2a/rpc/{agent_name}/{method}    JSON-RPC 入口（透传）

设计原则：
- 本路由是 core.a2a.server 之上更友好、面向前端的 REST 包装；
- 所有响应包成 ApiResponse[T]；
- AppException 会被自动映射到对应 HTTP 状态码；
- 鉴权：所有端点强制 Depends(get_auth_context)，tenant_id 由 AuthContext
  覆盖请求体中的 tenant_id，杜绝客户端冒充任意租户。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from api.dependencies.auth import AuthContext, get_auth_context
from common.constants import AgentName
from common.exceptions import AppException
from common.ids import message_id as new_message_id
from common.timeutils import to_iso, utc_now
from core.a2a.message import A2AMessage, MessagePart
from core.a2a.protocol import PROTOCOL_VERSION
from core.a2a.server import A2AServer, get_registry
from api.schemas.a2a_schemas import (
    A2ACancelTaskRequest,
    A2ACancelTaskResponse,
    A2AGetTaskResponse,
    A2AListTasksResponse,
    A2AMessageDTO,
    A2AMessagePartDTO,
    A2ASendMessageRequest,
    A2ASendMessageResponse,
)
from api.schemas.response_schemas import ApiResponse

logger = logging.getLogger("api.routers.a2a")


# =====================================================
# 工具
# =====================================================
def _to_dto(message: A2AMessage | None) -> A2AMessageDTO | None:
    if message is None:
        return None
    return A2AMessageDTO(
        message_id=message.message_id,
        tenant_id=message.tenant_id,
        role=message.role,
        parts=[
            A2AMessagePartDTO(
                type=p.type, text=p.text, file_uri=p.file_uri, data=p.data
            )
            for p in message.parts
        ],
        metadata=message.metadata,
    )


def _task_to_response(task: Any) -> A2AGetTaskResponse:
    return A2AGetTaskResponse(
        task_id=task.task_id,
        agent=task.agent_name,
        tenant_id=task.tenant_id,
        state=task.state.value if hasattr(task.state, "value") else str(task.state),
        message_id=task.message_id,
        error=task.error,
        artifacts=[a.model_dump() if hasattr(a, "model_dump") else a for a in task.artifacts],
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _to_internal_message(dto: A2AMessageDTO) -> A2AMessage:
    return A2AMessage(
        message_id=dto.message_id or new_message_id(),
        tenant_id=dto.tenant_id,
        role=dto.role,
        parts=[MessagePart(type=p.type, text=p.text, file_uri=p.file_uri, data=p.data) for p in dto.parts],
        metadata=dto.metadata or {},
    )


def _raise_from_app_exc(exc: AppException) -> None:
    """将 AppException 转为 FastAPI HTTPException。"""
    raise HTTPException(status_code=exc.http_status, detail=exc.to_dict())


# =====================================================
# 路由构造
# =====================================================
def build_a2a_router() -> APIRouter:
    """构造 /api/v1/a2a 路由。"""
    router = APIRouter(prefix="/api/v1/a2a", tags=["a2a"])
    server = A2AServer()
    registry = get_registry()

    # ---------- 智能体元数据 ----------
    @router.get("/agents", response_model=ApiResponse[dict])
    async def list_agents(
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        from api.schemas.agent_schemas import (
            AgentCapabilitiesDTO,
            AgentListResponse,
            AgentSummary,
        )

        try:
            agents = registry.list_agents()
        except AppException as e:
            _raise_from_app_exc(e)
        out: list[AgentSummary] = []
        for a in agents:
            out.append(
                AgentSummary(
                    name=a.name,
                    version=a.card.version,
                    description=a.card.description,
                    protocol_version=a.card.protocol_version,
                    skill_count=len(a.card.skills),
                    capabilities=AgentCapabilitiesDTO(
                        streaming=a.card.capabilities.streaming,
                        push_notifications=a.card.capabilities.push_notifications,
                        multi_turn=a.card.capabilities.multi_turn,
                        async_tasks=a.card.capabilities.async_tasks,
                    ),
                    is_business=AgentName(a.name).is_business if a.name in AgentName._value2member_map_ else True,
                )
            )
        return ApiResponse[dict].ok(
            AgentListResponse(agents=out, total=len(out)).model_dump()
        )

    @router.get("/agents/{name}", response_model=ApiResponse[dict])
    async def get_agent(
        name: str,
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        try:
            agent = registry.get(name)
        except AppException as e:
            _raise_from_app_exc(e)
        from api.schemas.agent_schemas import (
            AgentCapabilitiesDTO,
            AgentCardDTO,
            AgentDetail,
            AgentSkillDTO,
        )

        card = agent.card
        card_dto = AgentCardDTO(
            card_id=card.card_id,
            name=card.name,
            version=card.version,
            description=card.description,
            protocol_version=card.protocol_version,
            url=str(card.url),
            card_path=card.card_path,
            skills=[
                AgentSkillDTO(
                    skill_id=s.skill_id,
                    name=s.name,
                    description=s.description,
                    input_schema=s.input_schema,
                    output_schema=s.output_schema,
                )
                for s in card.skills
            ],
            capabilities=AgentCapabilitiesDTO(
                streaming=card.capabilities.streaming,
                push_notifications=card.capabilities.push_notifications,
                multi_turn=card.capabilities.multi_turn,
                async_tasks=card.capabilities.async_tasks,
            ),
            issued_at=card.issued_at,
        )
        detail = AgentDetail(
            name=card.name,
            version=card.version,
            description=card.description,
            protocol_version=card.protocol_version,
            skill_count=len(card.skills),
            capabilities=AgentCapabilitiesDTO(
                streaming=card.capabilities.streaming,
                push_notifications=card.capabilities.push_notifications,
                multi_turn=card.capabilities.multi_turn,
                async_tasks=card.capabilities.async_tasks,
            ),
            is_business=AgentName(card.name).is_business if card.name in AgentName._value2member_map_ else True,
            card=card_dto,
            metadata={"tenant_id": getattr(agent, "tenant_id", None)},
        )
        return ApiResponse[dict].ok(detail.model_dump())

    @router.get("/agents/{name}/card")
    async def get_agent_card(
        name: str,
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        try:
            return server.get_card(name)
        except AppException as e:
            _raise_from_app_exc(e)
        return {}  # unreachable

    @router.get("/agents/{name}/health", response_model=ApiResponse[dict])
    async def agent_health(
        name: str,
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        from api.schemas.agent_schemas import AgentHealthResponse

        try:
            agent = registry.get(name)
        except AppException as e:
            _raise_from_app_exc(e)
        return ApiResponse[dict].ok(
            AgentHealthResponse(
                name=agent.name,
                healthy=True,
                version=agent.card.version,
                protocol_version=agent.card.protocol_version,
                tenant_id=getattr(agent, "tenant_id", None),
                message="ok",
            ).model_dump()
        )

    # ---------- 消息发送 ----------
    @router.post(
        "/agents/{name}/messages",
        response_model=ApiResponse[dict],
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def send_message(
        name: str,
        req: A2ASendMessageRequest,
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        try:
            agent = registry.get(name)
        except AppException as e:
            _raise_from_app_exc(e)

        message = _to_internal_message(req.message)
        # 鉴权强制覆盖 tenant_id，杜绝客户端冒充任意租户
        message.tenant_id = auth.tenant_id
        if not message.message_id:
            message.message_id = new_message_id()

        # 直接走 core.a2a.server 的核心逻辑（不经过 JSON-RPC 帧）
        from core.a2a.message import Task, TaskState
        from core.a2a.server import _to_artifact  # 复用内部工具

        task = await registry.create_task(name, message)
        task.transition(TaskState.RUNNING)
        try:
            response = await agent.handle(message, task)
        except AppException as e:
            task.transition(TaskState.FAILED, error=e.to_dict())
            _raise_from_app_exc(e)
        except Exception as e:  # noqa: BLE001
            task.transition(TaskState.FAILED, error={"message": str(e)})
            logger.exception("A2A handle 失败: agent=%s err=%s", name, e)
            raise HTTPException(status_code=500, detail={"message": str(e)}) from e

        task.transition(TaskState.COMPLETED)
        if response is not None:
            task.artifacts.append(_to_artifact(response))  # type: ignore[arg-type]

        resp = A2ASendMessageResponse(
            task_id=task.task_id,
            state=task.state.value,
            agent=name,
            response=_to_dto(response),
            artifacts=[a.model_dump() if hasattr(a, "model_dump") else a for a in task.artifacts],
        )
        return ApiResponse[dict].ok(resp.model_dump())

    # ---------- 任务查询 / 取消 ----------
    @router.get("/tasks", response_model=ApiResponse[dict])
    async def list_tasks(
        agent: str | None = Query(default=None, description="按智能体名过滤"),
        limit: int = Query(default=50, ge=1, le=500),
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        # 多租户隔离：仅返回当前租户的任务
        tasks = registry.list_tasks()
        tasks = [t for t in tasks if getattr(t, "tenant_id", "") == auth.tenant_id]
        if agent:
            tasks = [t for t in tasks if t.agent_name == agent]
        tasks = tasks[:limit]
        resp = A2AListTasksResponse(
            tasks=[_task_to_response(t) for t in tasks]
        )
        return ApiResponse[dict].ok(resp.model_dump())

    @router.get("/tasks/{task_id}", response_model=ApiResponse[dict])
    async def get_task(
        task_id: str,
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        try:
            task = registry.get_task(task_id)
        except AppException as e:
            _raise_from_app_exc(e)
        # 多租户隔离：跨租户访问视为不存在
        if getattr(task, "tenant_id", "") != auth.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "10003", "message": f"任务不存在: {task_id}"},
            )
        return ApiResponse[dict].ok(_task_to_response(task).model_dump())

    @router.post("/tasks/{task_id}/cancel", response_model=ApiResponse[dict])
    async def cancel_task(
        task_id: str,
        req: A2ACancelTaskRequest,
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        try:
            task = registry.get_task(task_id)
        except AppException as e:
            _raise_from_app_exc(e)
        # 多租户隔离：跨租户取消视为不存在
        if getattr(task, "tenant_id", "") != auth.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "10003", "message": f"任务不存在: {task_id}"},
            )
        agent = registry.get(task.agent_name)
        ok = await agent.cancel_task(task_id, req.reason)
        if not ok:
            # 尝试在 registry 层强制 cancel
            from core.a2a.message import TaskState
            try:
                task.transition(TaskState.CANCELLED, error={"reason": req.reason or "cancelled"})
                ok = True
            except Exception:  # noqa: BLE001
                ok = False
        resp = A2ACancelTaskResponse(
            task_id=task_id,
            cancelled=ok,
            state=task.state.value,
        )
        return ApiResponse[dict].ok(resp.model_dump())

    # ---------- JSON-RPC 透传 ----------
    @router.post("/rpc/{agent_name}/{method}")
    async def rpc_entry(
        agent_name: str,
        method: str,
        request: Request,
        auth: AuthContext = Depends(get_auth_context),
    ) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail={"message": f"invalid JSON: {e}"}) from e
        body.setdefault("method", method)
        body.setdefault("jsonrpc", "2.0")
        if "id" not in body:
            body["id"] = "0"
        body.setdefault("protocol_version", PROTOCOL_VERSION)
        # 多租户隔离：若消息体含 tenant_id，强制覆盖为鉴权租户
        if isinstance(body.get("params"), dict):
            body["params"].setdefault("tenant_id", auth.tenant_id)
        try:
            return await server.handle_raw(agent_name, body)
        except AppException as e:
            _raise_from_app_exc(e)

    return router


# =====================================================
# 直接挂载辅助
# =====================================================
def mount_a2a(app: Any) -> None:
    """把 A2A 路由挂到 FastAPI app 上。"""
    app.include_router(build_a2a_router())


__all__ = [
    "build_a2a_router",
    "mount_a2a",
]
