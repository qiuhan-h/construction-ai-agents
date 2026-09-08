"""编排器 A2A handler：让业务智能体可以通过 A2A 反向调用编排器（触发工作流 / 查任务）。

设计原则（O1, O5）：
- 编排器本身以 A2AAgentProtocol 形态注册到 AgentRegistry；
- 业务 Agent 可通过 `orchestrator.send_message`（method=agent.send_message）触发工作流；
- 4c 暴露 3 个 method：
  - agent.send_message   通用入口：metadata 携带 workflow_name 触发工作流
  - workflow.list        列出已注册工作流
  - workflow.get_run     按 run_id 取执行结果

依赖：
- 阶段一 common.ids / common.timeutils
- 阶段二 core.a2a.message / core.a2a.server
- 阶段四 core.orchestrator.orchestrator
"""

from __future__ import annotations

import logging
from typing import Any

from common.ids import new_id
from common.timeutils import to_iso, utc_now
from core.a2a.message import A2AMessage, Artifact, Task
from core.a2a.server import A2AAgentProtocol, get_registry

logger = logging.getLogger(__name__)


class OrchestratorA2AHandler(A2AAgentProtocol):
    """编排器 A2A handler：把编排器的能力通过 A2A 协议对外暴露。"""

    def __init__(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator
        self.name = "orchestrator"
        self.card = _build_orchestrator_card()

    # ---------- A2AAgentProtocol ----------
    async def handle(self, message: A2AMessage, task: Task) -> A2AMessage:
        """分发到对应 method。"""
        # metadata 中 method 字段；URL method 默认是 agent.send_message
        method = (message.metadata or {}).get("method", "agent.send_message")
        try:
            if method == "agent.send_message":
                reply = await self._handle_send_message(message, task)
            elif method == "workflow.list":
                reply = await self._handle_workflow_list(message)
            elif method == "workflow.get_run":
                reply = await self._handle_workflow_get_run(message)
            else:
                raise ValueError(f"未知 method: {method}")
        except Exception as e:  # noqa: BLE001
            logger.exception("OrchestratorA2AHandler 失败: %s", e)
            return _reply(
                message,
                role="agent",
                data={"ack": False, "error": str(e), "method": method},
            )
        return _reply(message, role="agent", data=reply)

    async def get_task(self, task_id: str) -> Task | None:  # noqa: A002
        return None

    async def cancel_task(self, task_id: str, reason: str | None = None) -> bool:  # noqa: A002
        return False

    def list_tasks(self) -> list[Task]:  # noqa: A002
        return []

    # ---------- 具体 method ----------
    async def _handle_send_message(
        self, message: A2AMessage, task: Task
    ) -> dict[str, Any]:
        """metadata.workflow_name 必填；payload 由 message.parts 提取。"""
        meta = message.metadata or {}
        wf_name = meta.get("workflow_name")
        if not wf_name:
            return {
                "ack": False,
                "error": "metadata.workflow_name 必填",
                "supported_methods": [
                    "agent.send_message",
                    "workflow.list",
                    "workflow.get_run",
                ],
            }
        # 解析 payload：data part → dict
        payload: dict[str, Any] = {}
        for p in message.parts:
            if p.type == "data" and isinstance(p.data, dict):
                payload.update(p.data)
        # 自动补 alert_id / event_id 等标识
        if "alert_id" not in payload and task.task_id:
            payload["alert_id"] = task.task_id
        run_id = await self._orchestrator.trigger_workflow(
            wf_name, payload, message.tenant_id
        )
        task.metadata["workflow_run_id"] = run_id
        return {
            "ack": True,
            "workflow": wf_name,
            "workflow_run_id": run_id,
            "task_id": task.task_id,
        }

    async def _handle_workflow_list(self, message: A2AMessage) -> dict[str, Any]:
        return {
            "ack": True,
            "workflows": self._orchestrator.list_workflows(),
        }

    async def _handle_workflow_get_run(self, message: A2AMessage) -> dict[str, Any]:
        meta = message.metadata or {}
        run_id = meta.get("run_id")
        if not run_id:
            return {"ack": False, "error": "metadata.run_id 必填"}
        run = self._orchestrator.get_run(run_id)
        if run is None:
            return {"ack": False, "error": f"run_id 不存在: {run_id}"}
        return {"ack": True, "run": run}


# =====================================================
# 工具
# =====================================================
def _build_orchestrator_card() -> Any:
    """构造编排器的 Agent Card（最小可用，4c+ 可改为从 yaml 加载）。"""
    from core.a2a.agent_card import AgentCard, Capabilities, Skill

    return AgentCard(
        name="orchestrator",
        version="0.1.0",
        description="多智能体编排器（工作流引擎 + 任务调度 + 协作时间线）",
        url="http://orchestrator.local:8000",
        skills=[
            Skill(
                skill_id="workflow.trigger",
                name="trigger_workflow",
                description="按 workflow_name 触发已注册工作流",
            ),
            Skill(
                skill_id="workflow.list",
                name="list_workflows",
                description="列出全部已注册工作流",
            ),
            Skill(
                skill_id="workflow.get_run",
                name="get_workflow_run",
                description="按 run_id 取工作流执行结果",
            ),
        ],
        capabilities=Capabilities(
            streaming=False, push_notifications=False, multi_turn=True, async_tasks=True
        ),
        metadata={"agent_type": "coordinator", "stage": "4c"},
        issued_at=to_iso(utc_now()),
    )


def _reply(src: A2AMessage, *, role: str, data: dict) -> A2AMessage:
    from core.a2a.message import MessagePart

    return A2AMessage(
        message_id=new_id("msg"),
        tenant_id=src.tenant_id,
        role=role,
        parts=[MessagePart(type="data", data=data)],
        metadata={"in_reply_to": src.message_id, "ts": to_iso(utc_now())},
    )


# =====================================================
# 便捷注册
# =====================================================
def register_orchestrator_a2a(orchestrator: Any) -> OrchestratorA2AHandler:
    """把编排器注册为 A2A 智能体；返回 handler 便于测试。"""
    handler = OrchestratorA2AHandler(orchestrator)
    get_registry().register(handler)
    return handler
