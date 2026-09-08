"""4c 阶段验收：跑自检 + 端到端冒烟，输出可读报告。

退出码：
- 0  全部通过
- 1  有失败

运行：python tools/verify_stage4c.py
"""

from __future__ import annotations

import asyncio
import importlib
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# =====================================================
# 1) 调 self-test
# =====================================================
def run_self_test() -> tuple[int, str]:
    """调用 tests/orchestrator/test_orchestrator.py 的 main()，返回 (rc, output)。"""
    test = ROOT / "tests" / "orchestrator" / "test_orchestrator.py"
    print(f"\n[A] 跑 4c 自检: {test.relative_to(ROOT)}")
    proc = subprocess.run(
        [sys.executable, str(test)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = proc.stdout + proc.stderr
    # 只保留最后 30 行
    tail = "\n".join(out.splitlines()[-30:])
    print(tail)
    return proc.returncode, out


# =====================================================
# 2) 端到端冒烟
# =====================================================
def smoke_e2e() -> tuple[int, str]:
    """端到端冒烟：EventBus → Orchestrator → Workflow → AgentManager → Timeline。"""
    print("\n[B] 端到端冒烟（EventBus→Orchestrator→Workflow→AgentManager）")
    code = """
import asyncio
from core.events import Event, TOPIC_ALERT_TRIGGERED, TOPIC_INSPECTION_COMPLETED, get_event_bus
from core.orchestrator import Orchestrator, WorkflowEngine
from services import TaskQueue

class MockAgent:
    def __init__(self, name): self.name = name; self.handled = 0
    async def handle(self, message, task):
        from core.a2a.message import A2AMessage
        self.handled += 1
        return A2AMessage(message_id=message.message_id+'-reply', tenant_id=message.tenant_id, role='agent', parts=[], metadata={'agent': self.name})

class MockAM:
    def __init__(self):
        self.agents = {'safety_audit_agent': MockAgent('safety_audit_agent'),
                       'compliance_agent': MockAgent('compliance_agent')}
    async def get(self, name, tenant_id): return self.agents[name]
    def list_for_tenant(self, tenant_id): return list(self.agents.values())
    async def shutdown(self): pass

async def main():
    am = MockAM()
    orch = Orchestrator(task_queue=TaskQueue(), agent_manager=am, workflow_engine=WorkflowEngine(), event_bus=get_event_bus())
    await orch.start()
    bus = get_event_bus()
    await bus.publish(Event(event_id='s1', topic=TOPIC_ALERT_TRIGGERED, source='site_monitor_agent', tenant_id='tnt_smoke', payload={'level':'critical','alert_id':'a1'}))
    await bus.publish(Event(event_id='s2', topic=TOPIC_INSPECTION_COMPLETED, source='safety_audit_agent', tenant_id='tnt_smoke', payload={'conclusion':'fail','inspection_id':'i1'}))
    await asyncio.sleep(0.4)
    await orch.stop()
    tl = orch.collaboration.get_timeline_by_tenant('tnt_smoke')
    handled = {a.name: a.handled for a in am.agents.values()}
    print('TIMELINE_COUNT', len(tl))
    print('HANDLED', handled)
    print('WORKFLOWS', [w['name'] for w in orch.list_workflows()])
    # 4e 起 trigger_workflow 也落时间线（事件接收 + 工作流触发各 1 条），
    # 两事件至少 2 条；允许实现记录更细粒度交互。
    assert len(tl) >= 2, f'expected >= 2, got {len(tl)}'
    assert sum(handled.values()) >= 2, handled

asyncio.run(main())
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = proc.stdout + proc.stderr
        tail = "\n".join(out.splitlines()[-15:])
        print(tail)
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        return 1, "TIMEOUT"


# =====================================================
# 3) ServiceRegistry 路由冒烟
# =====================================================
def smoke_service_registry() -> tuple[int, str]:
    """确认所有 6 个 system action 都注册成功。"""
    print("\n[C] ServiceRegistry 路由冒烟")
    code = """
from services.service_registry import ServiceRegistry, list_services
expected = {
    'services.notify', 'services.human_review', 'services.document.upload',
    'services.ingest.iot', 'services.ingest.file', 'services.ingest.api',
}
got = set(list_services())
print('REGISTERED', sorted(got))
missing = expected - got
assert not missing, f'missing: {missing}'
print('OK')
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        out = proc.stdout + proc.stderr
        print(out)
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        return 1, "TIMEOUT"


# =====================================================
# main
# =====================================================
def main() -> int:
    t0 = time.time()
    print("=" * 64)
    print("  4c Stage Verify")
    print("=" * 64)

    results: list[tuple[str, int, str]] = []

    rc, out = run_self_test()
    results.append(("self_test", rc, out))
    rc, out = smoke_service_registry()
    results.append(("service_registry", rc, out))
    rc, out = smoke_e2e()
    results.append(("e2e_smoke", rc, out))

    elapsed = time.time() - t0
    print()
    print("=" * 64)
    print(f"  4c 验收结果（耗时 {elapsed:.1f}s）")
    print("=" * 64)
    fails: list[str] = []
    for name, rc, _ in results:
        tag = "OK " if rc == 0 else "FAIL"
        print(f"  [{tag}] {name}")
        if rc != 0:
            fails.append(name)
    if fails:
        print()
        print(f"  验收未通过：{len(fails)} 项失败 -> {fails}")
        return 1
    print()
    print("  验收通过：4c 编排器 + services 就绪")
    return 0


if __name__ == "__main__":
    sys.exit(main())


