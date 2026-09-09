"""端到端冒烟：事件总线 → 编排器 → 工作流引擎 → 智能体 → 协作时间线 + 任务队列。

覆盖 verify_stage4c 内嵌冒烟的同一链路，以 pytest 形式固化：
现场告警 + 审查不通过两类事件都应驱动智能体协作并落时间线。
不依赖 LLM / 外部中间件：智能体用 Mock，事件与队列均为内存实现。
"""

from __future__ import annotations

import asyncio

from core.a2a.message import A2AMessage
from core.events import (
    TOPIC_ALERT_TRIGGERED,
    TOPIC_INSPECTION_COMPLETED,
    Event,
    get_event_bus,
    reset_event_bus,
)
from core.orchestrator import Orchestrator, WorkflowEngine
from services import TaskQueue


class _MockAgent:
    def __init__(self, name: str) -> None:
        self.name = name
        self.handled = 0

    async def handle(self, message: A2AMessage, task) -> A2AMessage:
        self.handled += 1
        return A2AMessage(
            message_id=message.message_id + "-reply",
            tenant_id=message.tenant_id,
            role="agent",
            parts=[],
            metadata={"agent": self.name},
        )


class _MockAM:
    def __init__(self) -> None:
        self.agents = {
            "safety_audit_agent": _MockAgent("safety_audit_agent"),
            "compliance_agent": _MockAgent("compliance_agent"),
        }

    async def get(self, name: str, tenant_id: str) -> _MockAgent:
        return self.agents[name]

    def list_for_tenant(self, tenant_id: str):
        return list(self.agents.values())

    async def shutdown(self) -> None:
        return None


async def _full_pipeline() -> tuple[Orchestrator, _MockAM, TaskQueue]:
    reset_event_bus()
    am = _MockAM()
    queue = TaskQueue()
    orch = Orchestrator(
        task_queue=queue,
        agent_manager=am,  # type: ignore[arg-type]
        workflow_engine=WorkflowEngine(),
        event_bus=get_event_bus(),
    )
    await orch.start()
    bus = get_event_bus()

    # 1) 现场告警事件
    await bus.publish(
        Event(
            event_id="evt-alert-1",
            topic=TOPIC_ALERT_TRIGGERED,
            source="site_monitor_agent",
            tenant_id="tnt_e2e",
            payload={"level": "critical", "alert_id": "alt-1"},
        )
    )
    # 2) 安全审查不通过事件
    await bus.publish(
        Event(
            event_id="evt-ins-1",
            topic=TOPIC_INSPECTION_COMPLETED,
            source="safety_audit_agent",
            tenant_id="tnt_e2e",
            payload={"inspection_id": "ins-1", "conclusion": "fail"},
        )
    )
    await asyncio.sleep(0.6)
    await orch.stop()
    return orch, am, queue


def test_full_pipeline_events_drive_agents() -> None:
    orch, am, _queue = asyncio.run(_full_pipeline())
    handled = {a.name: a.handled for a in am.agents.values()}
    assert sum(handled.values()) >= 2, f"两类事件应至少驱动 2 次智能体调用: {handled}"
    timeline = orch.collaboration.get_timeline_by_tenant("tnt_e2e")
    assert len(timeline) >= 2, f"协作时间线应记录至少 2 条交互，实际 {len(timeline)}"


def test_full_pipeline_timeline_isolated() -> None:
    orch, _am, _queue = asyncio.run(_full_pipeline())
    mine = orch.collaboration.get_timeline_by_tenant("tnt_e2e")
    other = orch.collaboration.get_timeline_by_tenant("tnt_other")
    assert len(mine) >= 2
    assert len(other) == 0, "端到端链路不得跨租户泄露时间线"


def test_task_queue_owner_tracking_in_pipeline() -> None:
    """P1-2 回归：任务队列记录任务属主，支持多租户反查。"""

    async def _run() -> None:
        queue = TaskQueue()

        async def _noop(**kwargs) -> dict:
            return {"done": True}

        tid = await queue.submit("services.echo", _noop, tenant_id="tnt_e2e")
        assert tid
        assert queue.owner_of(tid) == "tnt_e2e"

    asyncio.run(_run())
