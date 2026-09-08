"""编排器（Orchestrator）端到端自检。

执行方式：
    cd construction-ai-agents
    python tests/orchestrator/test_orchestrator.py

覆盖：
- TaskQueue 提交 / 状态查询 / 幂等键（H12 回归）；
- WorkflowEngine 拓扑分层（含 M9 空工作流不报环回归）；
- Orchestrator 事件路由：EventBus → 智能体 → 协作时间线；
- CollaborationManager 多租户时间线隔离。

不依赖外部 broker / DB / LLM：智能体用 Mock，事件走内存总线。
自检仅在 __main__ 下执行；pytest 收集时跑 ``main()``。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from common.ids import message_id  # noqa: E402
from core.a2a.message import A2AMessage  # noqa: E402
from core.events import (  # noqa: E402
    Event,
    TOPIC_ALERT_TRIGGERED,
    TOPIC_INSPECTION_COMPLETED,
    get_event_bus,
    reset_event_bus,
)
from core.orchestrator import Orchestrator, WorkflowEngine  # noqa: E402
from services import TaskQueue  # noqa: E402


class _MockAgent:
    """记录被调用次数的 Mock 智能体。"""

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


class _MockAgentManager:
    def __init__(self) -> None:
        self.agents = {
            "safety_audit_agent": _MockAgent("safety_audit_agent"),
            "compliance_agent": _MockAgent("compliance_agent"),
        }

    async def get(self, name: str, tenant_id: str):
        return self.agents[name]

    def list_for_tenant(self, tenant_id: str):
        return list(self.agents.values())

    async def shutdown(self) -> None:
        return None


def test_task_queue_submit_and_status() -> None:
    """TaskQueue：提交 → 查询；幂等键复用 task_id（H12 回归）。"""
    async def _run() -> None:
        q = TaskQueue()

        async def _noop(**kwargs) -> dict:
            return {"ok": True}

        tid1 = await q.submit("system_action", _noop, tenant_id="tnt_q")
        assert tid1, "submit 应返回 task_id"
        # 幂等键：同 key 重试复用同一 task_id，不重复执行
        tid2 = await q.submit(
            "system_action", _noop, tenant_id="tnt_q", idempotency_key="k-1"
        )
        tid3 = await q.submit(
            "system_action", _noop, tenant_id="tnt_q", idempotency_key="k-1"
        )
        assert tid2 == tid3, f"幂等键应复用 task_id: {tid2} != {tid3}"
        # owner 映射（P1-2 回归）
        assert q.owner_of(tid1) == "tnt_q"

    asyncio.run(_run())


def test_workflow_engine_empty_workflow_no_cycle() -> None:
    """M9 回归：空工作流不得误报"存在环"。"""
    engine = WorkflowEngine()
    # 空节点 / 单节点工作流都应能正常分层
    layers_empty = engine._topo_layers([])  # type: ignore[attr-defined]
    assert layers_empty == [] or layers_empty == [[]]


async def _run_orchestrator_smoke() -> tuple[int, dict]:
    """事件 → 编排器 → 智能体 → 时间线。返回 (timeline_count, handled)。"""
    reset_event_bus()
    am = _MockAgentManager()
    orch = Orchestrator(
        task_queue=TaskQueue(),
        agent_manager=am,  # type: ignore[arg-type]
        workflow_engine=WorkflowEngine(),
        event_bus=get_event_bus(),
    )
    await orch.start()
    bus = get_event_bus()
    await bus.publish(
        Event(
            event_id="s1",
            topic=TOPIC_ALERT_TRIGGERED,
            source="site_monitor_agent",
            tenant_id="tnt_smoke",
            payload={"level": "critical", "alert_id": "a1"},
        )
    )
    await bus.publish(
        Event(
            event_id="s2",
            topic=TOPIC_INSPECTION_COMPLETED,
            source="safety_audit_agent",
            tenant_id="tnt_smoke",
            payload={"conclusion": "fail", "inspection_id": "i1"},
        )
    )
    await asyncio.sleep(0.4)
    await orch.stop()
    timeline = orch.collaboration.get_timeline_by_tenant("tnt_smoke")
    handled = {a.name: a.handled for a in am.agents.values()}
    return len(timeline), handled


def test_orchestrator_event_routing() -> None:
    """事件驱动智能体协作：时间线 + Mock 智能体被调用。"""
    tl_count, handled = asyncio.run(_run_orchestrator_smoke())
    assert tl_count >= 2, f"时间线应记录 2 条交互，实际 {tl_count}"
    assert sum(handled.values()) >= 2, f"智能体应被调用: {handled}"


def test_collaboration_timeline_tenant_isolation() -> None:
    """协作时间线按租户隔离。"""
    async def _run() -> None:
        reset_event_bus()
        am = _MockAgentManager()
        orch = Orchestrator(
            task_queue=TaskQueue(),
            agent_manager=am,  # type: ignore[arg-type]
            workflow_engine=WorkflowEngine(),
            event_bus=get_event_bus(),
        )
        await orch.start()
        bus = get_event_bus()
        await bus.publish(
            Event(
                event_id="x1",
                topic=TOPIC_INSPECTION_COMPLETED,
                source="safety_audit_agent",
                tenant_id="tnt_a",
                payload={"inspection_id": "ins-1", "conclusion": "fail"},
            )
        )
        await asyncio.sleep(0.6)
        await orch.stop()
        ta = orch.collaboration.get_timeline_by_tenant("tnt_a")
        tb = orch.collaboration.get_timeline_by_tenant("tnt_b")
        assert len(ta) >= 1, "tnt_a 应有时间线"
        assert len(tb) == 0, f"tnt_b 不应看到 tnt_a 的交互: {len(tb)}"

    asyncio.run(_run())


# =====================================================
# 脚本式自检（verify_stage4c 以子进程调用 main()）
# =====================================================
def main() -> int:
    cases = [
        ("TaskQueue 提交/状态/幂等", test_task_queue_submit_and_status),
        ("WorkflowEngine 空工作流无环（M9）", test_workflow_engine_empty_workflow_no_cycle),
        ("Orchestrator 事件路由", test_orchestrator_event_routing),
        ("协作时间线多租户隔离", test_collaboration_timeline_tenant_isolation),
    ]
    failed = 0
    for name, fn in cases:
        try:
            fn()
            print(f"[PASS] {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback

            print(f"[FAIL] {name}: {e}")
            traceback.print_exc()
    print(f"\n编排器自检结果: {len(cases) - failed} 通过, {failed} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
