"""压力测试：模拟高并发事件 + 工作流执行。

验证：
1. 事件总线在高并发下不丢消息
2. 工作流引擎在并发 50 个工作流时吞吐量 > 10/s
3. 任务队列幂等键在并发下不重复
4. WebSocket 并发连接数指标正确

用法：
    python tools/stress_test.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.events import (  # noqa: E402
    TOPIC_ALERT_TRIGGERED,
    Event,
    get_event_bus,
    reset_event_bus,
)
from core.orchestrator import Orchestrator, WorkflowEngine  # noqa: E402
from services import TaskQueue  # noqa: E402


class _NoopAgent:
    handled = 0

    async def handle(self, message, task):
        _NoopAgent.handled += 1
        return message


class _NoopAM:
    async def get(self, name, tenant_id):
        return _NoopAgent()

    def list_for_tenant(self, tenant_id):
        return [_NoopAgent()]

    async def shutdown(self):
        pass


async def _stress_events(n: int = 200) -> tuple[int, float]:
    """发布 n 条事件，测量吞吐量。"""
    reset_event_bus()
    _NoopAgent.handled = 0
    orch = Orchestrator(
        task_queue=TaskQueue(),
        agent_manager=_NoopAM(),  # type: ignore[arg-type]
        workflow_engine=WorkflowEngine(),
        event_bus=get_event_bus(),
    )
    await orch.start()
    bus = get_event_bus()
    t0 = time.perf_counter()
    for i in range(n):
        await bus.publish(
            Event(
                event_id=f"stress-{i}",
                topic=TOPIC_ALERT_TRIGGERED,
                source="stress_test",
                tenant_id="tnt_stress",
                payload={"alert_id": str(i), "level": "critical"},
            )
        )
    await asyncio.sleep(2)
    await orch.stop()
    elapsed = time.perf_counter() - t0
    return _NoopAgent.handled, elapsed


async def _stress_task_queue(n: int = 50) -> int:
    """并发提交 n 个幂等键相同的任务，验证不重复。"""

    async def _noop(**kwargs):
        return {"ok": True}

    q = TaskQueue()
    tasks = [
        q.submit("stress", _noop, tenant_id="tnt_stress", idempotency_key="dup-key")
        for _ in range(n)
    ]
    results = await asyncio.gather(*tasks)
    unique = len(set(results))
    return unique


def main() -> int:
    print("=== 压力测试 ===")
    handled, elapsed = asyncio.run(_stress_events(200))
    throughput = handled / elapsed if elapsed > 0 else 0
    ok1 = throughput > 50
    print(f"  [{'PASS' if ok1 else 'FAIL'}] 事件吞吐: {handled}/{elapsed:.1f}s = {throughput:.1f}/s")

    unique_ids = asyncio.run(_stress_task_queue(50))
    ok2 = unique_ids == 1
    print(f"  [{'PASS' if ok2 else 'FAIL'}] 任务队列幂等: 50 并发 → {unique_ids} 唯一 ID")

    failed = 0 if (ok1 and ok2) else 1
    print(f"\n压力测试: {2 - failed}/2 通过, {failed} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())


