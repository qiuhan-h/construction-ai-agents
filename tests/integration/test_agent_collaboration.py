"""集成测试：事件驱动的多智能体协作（Orchestrator → Workflow → Agent → 时间线）。

不依赖 LLM / 外部 broker：智能体用 Mock，事件走内存总线。
"""

from __future__ import annotations

import asyncio

from core.a2a.message import A2AMessage
from core.events import (
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
        self.tenant_ids: list[str] = []

    async def handle(self, message: A2AMessage, task) -> A2AMessage:
        self.handled += 1
        self.tenant_ids.append(message.tenant_id)
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


async def _publish_inspection(tenant_id: str, conclusion: str) -> tuple[Orchestrator, _MockAM]:
    reset_event_bus()
    am = _MockAM()
    orch = Orchestrator(
        task_queue=TaskQueue(),
        agent_manager=am,  # type: ignore[arg-type]
        workflow_engine=WorkflowEngine(),
        event_bus=get_event_bus(),
    )
    await orch.start()
    await get_event_bus().publish(
        Event(
            event_id=f"ins-{tenant_id}-{conclusion}",
            topic=TOPIC_INSPECTION_COMPLETED,
            source="safety_audit_agent",
            tenant_id=tenant_id,
            payload={"inspection_id": "ins-1", "conclusion": conclusion},
        )
    )
    await asyncio.sleep(0.5)
    await orch.stop()
    return orch, am


def test_failed_inspection_triggers_compliance_followup() -> None:
    """审查不通过 → 编排器启动合规复审工作流 → compliance 智能体被调用。"""
    orch, am = asyncio.run(_publish_inspection("tnt_col", "fail"))
    compliance = am.agents["compliance_agent"]
    assert compliance.handled >= 1, "fail 结论应触发合规复审"
    timeline = orch.collaboration.get_timeline_by_tenant("tnt_col")
    assert len(timeline) >= 1, "协作时间线应记录交互"


def test_passed_inspection_does_not_trigger_followup() -> None:
    """审查通过 → 不应启动合规复审（负向断言）。"""
    _orch, am = asyncio.run(_publish_inspection("tnt_col2", "pass"))
    compliance = am.agents["compliance_agent"]
    assert compliance.handled == 0, "pass 结论不应触发合规复审"


def test_collaboration_timeline_tenant_isolation() -> None:
    """协作时间线严格按租户隔离：B 租户看不到 A 租户的交互。"""
    orch, _am = asyncio.run(_publish_inspection("tnt_alpha", "fail"))
    ta = orch.collaboration.get_timeline_by_tenant("tnt_alpha")
    tb = orch.collaboration.get_timeline_by_tenant("tnt_beta")
    assert len(ta) >= 1
    assert len(tb) == 0, f"租户隔离失效: tnt_beta 看到 {len(tb)} 条 tnt_alpha 的交互"


def test_agent_receives_correct_tenant_id() -> None:
    """工作流派发给智能体的消息必须携带事件所属租户（P1 多租户回归）。"""
    _orch, am = asyncio.run(_publish_inspection("tnt_tid", "fail"))
    for agent in am.agents.values():
        for tid in agent.tenant_ids:
            assert tid == "tnt_tid", f"{agent.name} 收到错误租户: {tid}"
