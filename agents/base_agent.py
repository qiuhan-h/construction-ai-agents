"""智能体抽象基类。

设计目标：
- 业务智能体（safety_audit / compliance / site_monitor）通过继承
  BaseAgent 获得"被 A2A 路由、被 MCP 调用、发事件"的统一能力；
- 基类不依赖 core.llm / core.mcp / core.events 的具体实现（保持解耦），
  业务层按需 import；
- 阶段二仅提供骨架与 A2A 接入骨架；
  阶段三/四在子类中实现 handle / get_task / cancel_task 等业务方法。

约定：
- 子类必须设置类属性 name（与 AgentName 枚举一致）；
- 子类必须设置类属性 version；
- 构造时必传 tenant_id（每个智能体实例绑定到一个租户）；
- 子类通过 self.publish_event(...) 发事件，self.a2a 客户端调用其它智能体，
  self.mcp 客户端调用 MCP 工具/资源（按需注入，避免硬依赖）。
"""

from __future__ import annotations

import abc
import asyncio
import logging
from typing import Any

from common.exceptions import A2AError
from common.ids import task_id
from common.timeutils import to_iso, utc_now
from core.a2a.agent_card import AgentCard, Capabilities, Skill
from core.a2a.message import A2AMessage, MessagePart, Task, TaskState
from core.a2a.protocol import PROTOCOL_VERSION
from core.a2a.server import A2AAgentProtocol, get_registry

logger = logging.getLogger("agents.base_agent")


# =====================================================
# 装饰器：register_agent
# =====================================================
def register_agent(cls: type["BaseAgent"]) -> type["BaseAgent"]:
    """装饰器：把 BaseAgent 子类自动注册到全局 AgentRegistry。

    使用：
        @register_agent
        class SafetyAuditAgent(BaseAgent):
            name = "safety_audit_agent"
            ...
    """
    if not (issubclass(cls, BaseAgent) and cls is not BaseAgent):
        raise TypeError("register_agent 只能装饰 BaseAgent 的子类")

    # 仅在 name/version 合法时注册
    if getattr(cls, "name", None) and getattr(cls, "version", None):
        try:
            # 实例化一个用于生成 Card 的"无租户骨架"不会被注册；
            # 真实注册发生在具体租户实例化时（见 bind_to_tenant）。
            logger.debug(
                "智能体类已声明: name=%s version=%s class=%s",
                cls.name, cls.version, cls.__name__,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("智能体类元数据检查失败: %s", e)
    return cls


# =====================================================
# 抽象基类
# =====================================================
class BaseAgent(A2AAgentProtocol, abc.ABC):
    """业务智能体抽象基类。

    子类必填：
        name: str                与 AgentName 枚举一致
        version: str             智能体版本
        description: str         一句话简介
        skills: list[Skill]      能力声明

    子类按需重写：
        async handle(message, task) -> A2AMessage
        async get_task(task_id) -> Task | None
        async cancel_task(task_id, reason) -> bool
        def list_tasks() -> list[Task]
    """

    # ---- 类级元数据（子类必须覆盖） ----
    name: str = ""
    version: str = "0.1.0"
    description: str = ""
    skills: list[Skill] = []
    capabilities: Capabilities = Capabilities()

    # ---- 实例级 ----
    def __init__(
        self,
        *,
        tenant_id: str,
        a2a_url: str = "http://localhost:9101",
        card_path: str = "/agent.json",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self.name:
            raise ValueError(f"{type(self).__name__} 必须设置 name")
        if not self.version:
            raise ValueError(f"{type(self).__name__} 必须设置 version")
        if not tenant_id:
            raise ValueError("tenant_id 不能为空")

        self.tenant_id = tenant_id
        self.metadata = metadata or {}

        # Agent Card：每个实例一份，便于携带租户信息
        self.card: AgentCard = AgentCard(
            name=self.name,
            version=self.version,
            description=self.description,
            skills=list(self.skills),
            capabilities=self.capabilities,
            url=a2a_url,
            card_path=card_path,
            metadata={
                "tenant_id": tenant_id,
                "instance_id": self._instance_id(),
            },
        )

        # 异步锁：保护内部任务表
        self._lock = asyncio.Lock()
        self._tasks: dict[str, Task] = {}
        # 事件钩子（业务层可重写）
        self.on_event: Any = None  # async def on_event(event) -> None

    # =====================================================
    # A2AAgentProtocol 协议实现
    # =====================================================
    async def handle(self, message: A2AMessage, task: Task) -> A2AMessage:
        """处理一条 A2A 消息；默认行为：把 message 原样回显（仅占位）。

        子类应重写此方法实现具体业务逻辑。
        """
        logger.info(
            "BaseAgent.handle 占位: agent=%s task=%s message=%s",
            self.name, task.task_id, message.message_id,
        )
        return _echo_message(message, self.name, self.version)

    async def get_task(self, task_id: str) -> Task | None:  # noqa: A002
        async with self._lock:
            return self._tasks.get(task_id)

    async def cancel_task(self, task_id: str, reason: str | None = None) -> bool:  # noqa: A002
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.is_terminal():
                return False
            try:
                task.transition(TaskState.CANCELLED, error={"reason": reason or "cancelled"})
            except Exception:  # noqa: BLE001
                return False
            return True

    def list_tasks(self) -> list[Task]:  # noqa: A002
        return list(self._tasks.values())

    # =====================================================
    # 便捷方法
    # =====================================================
    def register(self) -> None:
        """把本实例注册到全局 AgentRegistry（每租户一个实例）。"""
        get_registry().register(self)
        logger.info(
            "智能体已注册: name=%s tenant=%s version=%s",
            self.name, self.tenant_id, self.version,
        )

    def unregister(self) -> None:
        """从全局 AgentRegistry 注销。"""
        get_registry().unregister(self.name)

    def to_card_dict(self) -> dict[str, Any]:
        """对外暴露 Agent Card（去除内部 metadata）。"""
        return self.card.to_public_dict()

    # =====================================================
    # 内部：构建任务
    # =====================================================
    async def new_task(self, message: A2AMessage) -> Task:
        async with self._lock:
            task = Task(
                task_id=task_id(),
                agent_name=self.name,
                tenant_id=self.tenant_id,
                state=TaskState.PENDING,
                message_id=message.message_id,
            )
            self._tasks[task.task_id] = task
            return task

    # =====================================================
    # 内部工具
    # =====================================================
    def _instance_id(self) -> str:
        # 简单的实例标识（实例化时间 + 类名 + tenant）
        return f"{type(self).__name__}@{self.tenant_id}@{to_iso(utc_now())}"


# =====================================================
# 辅助
# =====================================================
def _echo_message(src: A2AMessage, agent_name: str, agent_version: str) -> A2AMessage:
    """默认 handle 的回显实现（占位用）。"""
    from common.ids import message_id  # 局部 import 避免循环

    return A2AMessage(
        message_id=message_id(),
        tenant_id=src.tenant_id,
        role="agent",
        parts=[
            MessagePart(
                type="text",
                text=(
                    f"[{agent_name}@{agent_version}] 已收到消息 {src.message_id}。"
                    "该智能体尚未实现具体业务逻辑。"
                ),
            )
        ],
        metadata={
            "echo_of": src.message_id,
            "received_at": to_iso(utc_now()),
        },
    )


# =====================================================
# 公共异常再导出
# =====================================================
__all__ = [
    "BaseAgent",
    "register_agent",
]
