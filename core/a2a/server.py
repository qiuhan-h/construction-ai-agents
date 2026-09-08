"""A2A 服务端：挂载到 FastAPI 应用上，处理 JSON-RPC 请求。

端点：
  GET  /a2a/{agent_name}/agent.json    获取指定智能体的 Agent Card
  POST /a2a/{agent_name}/{method}      调用智能体方法

设计要点：
- AgentRegistry 单例管理已注册的 BaseAgent；
- 中间件链（auth/trace/rate_limit）由 middleware.py 提供插槽；
- 同步等待（wait=true）仅用于小任务，大任务走 task_id 异步查询。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

from common.exceptions import A2AAgentNotFoundError, A2AMessageInvalidError
from common.ids import task_id
from common.timeutils import to_iso, utc_now
from core.a2a.message import A2AMessage, Task, TaskState
from core.a2a.protocol import A2AMethod, PROTOCOL_VERSION, make_error
from core.a2a.serializers import (
    CancelTaskParams,
    GetTaskParams,
    JSONRPCError,
    JSONRPCRequest,
    SendMessageParams,
    decode_request,
    encode_response,
    make_error_response,
    make_success_response,
)

logger = logging.getLogger("core.a2a.server")


# =====================================================
# 智能体基类接口（仅协议所需；具体实现由 agents.base_agent.BaseAgent 提供）
# =====================================================
class A2AAgentProtocol:
    """A2A 视角下智能体需具备的能力（协议层抽象）。"""

    name: str
    card: Any  # core.a2a.agent_card.AgentCard

    async def handle(self, message: A2AMessage, task: Task) -> A2AMessage:
        raise NotImplementedError

    async def get_task(self, task_id: str) -> Task | None:  # noqa: A002
        return None

    async def cancel_task(self, task_id: str, reason: str | None = None) -> bool:  # noqa: A002
        return False

    def list_tasks(self) -> list[Task]:  # noqa: A002
        return []


# =====================================================
# 智能体注册表
# =====================================================
class AgentRegistry:
    """进程内单例：按 name 索引智能体。"""

    def __init__(self) -> None:
        self._agents: dict[str, A2AAgentProtocol] = {}
        self._tasks: dict[str, Task] = {}
        self._lock = asyncio.Lock()

    def register(self, agent: A2AAgentProtocol) -> None:
        self._agents[agent.name] = agent
        logger.info("A2A 注册智能体: %s", agent.name)

    def unregister(self, name: str) -> None:
        self._agents.pop(name, None)
        logger.info("A2A 注销智能体: %s", name)

    def get(self, name: str) -> A2AAgentProtocol:
        agent = self._agents.get(name)
        if agent is None:
            raise A2AAgentNotFoundError(
                f"智能体未注册: {name}", details={"name": name}
            )
        return agent

    def list_agents(self) -> list[A2AAgentProtocol]:
        return list(self._agents.values())

    async def create_task(self, agent_name: str, message: A2AMessage) -> Task:
        async with self._lock:
            task = Task(
                task_id=task_id(),
                agent_name=agent_name,
                tenant_id=message.tenant_id,
                state=TaskState.PENDING,
                message_id=message.message_id,
            )
            self._tasks[task.task_id] = task
            return task

    def get_task(self, task_id: str) -> Task:  # noqa: A002
        task = self._tasks.get(task_id)
        if task is None:
            raise A2AAgentNotFoundError(
                f"任务不存在: {task_id}", details={"task_id": task_id}
            )
        return task

    def list_tasks(self) -> list[Task]:
        return list(self._tasks.values())


# 全局单例
_registry: AgentRegistry | None = None


def get_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry


def reset_registry() -> None:
    """重置注册表（仅供测试使用）。"""
    global _registry
    _registry = None


# =====================================================
# 路由分发
# =====================================================
class A2AServer:
    """A2A 服务端：将 JSON-RPC 帧分发到对应智能体。"""

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self.registry = registry or get_registry()
        self._middleware: list[Callable[[JSONRPCRequest, str], Awaitable[None]]] = []

    def add_middleware(
        self, fn: Callable[[JSONRPCRequest, str], Awaitable[None]]
    ) -> None:
        """注册请求级中间件（按注册顺序执行）。"""
        self._middleware.append(fn)

    async def handle_raw(self, agent_name: str, body: dict[str, Any]) -> dict[str, Any]:
        """FastAPI 入口：处理原始请求体并返回 JSON-RPC 响应。"""
        req = decode_request(body)

        # 中间件链
        for mw in self._middleware:
            await mw(req, agent_name)

        try:
            result = await self._dispatch(agent_name, req)
        except A2AMessageInvalidError as e:
            payload = e.to_dict()
            err_obj = JSONRPCError(
                code=payload["code"],
                message=payload["message"],
                data=payload.get("details"),
            )
            return encode_response(make_error_response(req.id, err_obj))
        except Exception as e:  # 兜底为 A2A_CALL_FAILED
            logger.exception("A2A 调度失败: %s", e)
            err = make_error_payload("A2A 调用失败", e)
            err_obj = JSONRPCError(
                code=err["code"],
                message=err["message"],
                data=err.get("data"),
            )
            return encode_response(make_error_response(req.id, err_obj))

        return encode_response(make_success_response(req.id, result))

    def get_card(self, agent_name: str) -> dict[str, Any]:
        agent = self.registry.get(agent_name)
        return agent.card.to_public_dict()

    # ---------- 内部 ----------
    async def _dispatch(self, agent_name: str, req: JSONRPCRequest) -> Any:
        method = req.method
        if method == A2AMethod.DISCOVERY.value:
            # 允许查询指定 agent 的 card
            return self.get_card(agent_name)

        agent = self.registry.get(agent_name)

        if method == A2AMethod.SEND_MESSAGE.value:
            params = _validate_params(SendMessageParams, req.params)
            task = await self.registry.create_task(agent_name, params.message)
            # H4 修正：transition 在 registry._lock 下执行，防止并发状态错乱
            async with self.registry._lock:
                task.transition(TaskState.RUNNING)
            try:
                response = await agent.handle(params.message, task)
            except Exception as e:
                async with self.registry._lock:
                    task.transition(TaskState.FAILED, error={"message": str(e)})
                raise
            async with self.registry._lock:
                task.transition(TaskState.COMPLETED)
                if response is not None:
                    task.artifacts.append(  # type: ignore[arg-type]
                        _to_artifact(response)
                    )
            return {
                "task": task.model_dump(),
                "reply": response.model_dump() if response else None,
            }

        if method == A2AMethod.GET_TASK.value:
            params = _validate_params(GetTaskParams, req.params)
            task = self.registry.get_task(params.task_id)
            return task.model_dump()

        if method == A2AMethod.CANCEL_TASK.value:
            params = _validate_params(CancelTaskParams, req.params)
            ok = await agent.cancel_task(params.task_id, params.reason)
            if not ok:
                task = self.registry.get_task(params.task_id)
                if task.state in (TaskState.PENDING, TaskState.RUNNING):
                    task.transition(TaskState.CANCELLED)
            return {"cancelled": ok, "task_id": params.task_id}

        if method == A2AMethod.LIST_TASKS.value:
            return {"tasks": [t.model_dump() for t in self.registry.list_tasks()]}

        raise A2AMessageInvalidError(f"未知 A2A 方法: {method}")


# =====================================================
# 工具函数
# =====================================================
def _validate_params(model_cls: type, params: Any) -> Any:
    try:
        return model_cls.model_validate(params or {})
    except Exception as e:
        raise A2AMessageInvalidError(
            f"{model_cls.__name__} 参数非法",
            details={"error": str(e)},
        ) from e


def _to_artifact(message: A2AMessage) -> Any:
    from core.a2a.message import Artifact  # 局部导入避免循环

    text = "\n".join(p.text for p in message.parts if p.text) or None
    return Artifact(
        artifact_id=message.message_id,
        type="message",
        title="reply",
        text=text,
        data={"metadata": message.metadata} if message.metadata else None,
    )


def make_error_payload(message: str, exc: Exception) -> dict[str, Any]:
    return {
        "code": "50003",
        "message": message,
        "data": {"exception": exc.__class__.__name__, "text": str(exc)},
    }


def build_fastapi_router():
    """构造 FastAPI 路由（懒加载，避免启动时强依赖 fastapi）。

    使用方式：
        from core.a2a.server import build_fastapi_router
        app.include_router(build_fastapi_router(), prefix="/a2a")
    """
    try:
        from fastapi import APIRouter, HTTPException, Request
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("FastAPI 未安装，无法构建 A2A 路由") from e

    router = APIRouter()
    server = A2AServer()

    @router.get("/{agent_name}/agent.json")
    async def get_agent_card(agent_name: str) -> dict[str, Any]:
        try:
            return server.get_card(agent_name)
        except A2AAgentNotFoundError as e:
            raise HTTPException(status_code=404, detail=e.to_dict()) from e

    @router.post("/{agent_name}/{method}")
    async def post_method(agent_name: str, method: str, request: Request) -> dict[str, Any]:
        body = await request.json()
        # URL 上的 method 必须与帧中 method 一致
        body.setdefault("method", method)
        body.setdefault("jsonrpc", "2.0")
        if "id" not in body:
            body["id"] = "0"
        body.setdefault("protocol_version", PROTOCOL_VERSION)
        return await server.handle_raw(agent_name, body)

    return router
