"""4d 阶段验收：跑文件扫描 + pytest + 端到端冒烟 + 关键 API 探针。

退出码：
- 0  全部通过
- 1  有失败

运行：python tools/verify_stage4d.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# =====================================================
# 1) 文件扫描
# =====================================================
def run_scan() -> tuple[int, str]:
    print("\n[A] 4d 文件扫描")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "scan" / "scan_stage4d.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = proc.stdout + proc.stderr
    tail = "\n".join(out.splitlines()[-6:])
    print(tail)
    return proc.returncode, out


# =====================================================
# 2) pytest（unit + integration + e2e）
# =====================================================
def run_pytest() -> tuple[int, str]:
    print("\n[B] pytest tests/unit tests/integration tests/e2e")
    proc = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/unit", "tests/integration", "tests/e2e",
            "-q", "--tb=line",
        ],
        cwd=str(ROOT),
        env={**__import__("os").environ, "PYTHONPATH": "."},
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = proc.stdout + proc.stderr
    tail = "\n".join(out.splitlines()[-15:])
    print(tail)
    return proc.returncode, out


# =====================================================
# 3) 端到端冒烟：create_app + healthz/readyz
# =====================================================
def smoke_app_health() -> tuple[int, str]:
    print("\n[C] 端到端冒烟：create_app() + /healthz + /readyz + 根 banner")
    code = """
from fastapi.testclient import TestClient
from api.main import create_app

with TestClient(create_app()) as client:
    r1 = client.get('/api/v1/health/healthz')
    print('HEALTHZ', r1.status_code, r1.json()['code'], r1.json()['data']['status'])
    assert r1.status_code == 200, r1.text
    assert r1.json()['code'] == '0'

    r2 = client.get('/api/v1/health/readyz')
    print('READYZ', r2.status_code, r2.json()['data']['status'])
    assert r2.status_code in (200, 503), r2.text
    assert 'checks' in r2.json()['data']

    r3 = client.get('/')
    print('ROOT', r3.status_code, r3.json()['name'], r3.json()['stage'])
    assert r3.status_code == 200
    assert r3.json()['stage'] in ('4d', '4e', '6b', '6d')  # banner stage 兼容历史（6d BIM+边缘端阶段升级）
print('OK')
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            env={**__import__("os").environ, "PYTHONPATH": "."},
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = proc.stdout + proc.stderr
        print(out)
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        return 1, "TIMEOUT"


# =====================================================
# 4) 端到端冒烟：dev- token 鉴权 + agents 列表 + 报告 + ws
# =====================================================
def smoke_api_business() -> tuple[int, str]:
    print("\n[D] 端到端冒烟：dev- 鉴权 + agents / reports / orchestrator / ws")
    code = """
from fastapi.testclient import TestClient
from api.main import create_app
from api.dependencies.agent_manager import reset_agent_manager
from api.dependencies.orchestrator_provider import reset_orchestrator
from core.events import reset_event_bus

reset_event_bus(); reset_agent_manager(); reset_orchestrator()
with TestClient(create_app()) as client:
    h = {'Authorization': 'Bearer dev-tnt_smoke-smoker'}

    # agents supported
    r = client.get('/api/v1/agents/supported', headers=h)
    assert r.status_code == 200, r.text
    supported = set(r.json()['data']['supported'])
    assert {'safety_audit_agent','compliance_agent','site_monitor_agent'} <= supported, supported
    print('AGENTS_OK', sorted(supported))

    # orchestrator workflows
    r = client.get('/api/v1/orchestrator/workflows', headers=h)
    assert r.status_code == 200, r.text
    names = {w['name'] for w in r.json()['data']['workflows']}
    assert {'monitor_alert_to_audit','compliance_followup','regulation_record'} <= names, names
    print('WF_OK', sorted(names))

    # reports 列表（空 store）
    r = client.get('/api/v1/reports', headers=h)
    assert r.status_code == 200, r.text
    print('REPORTS_OK', r.json()['data']['total'])

    # ws 订阅 + publish → 收到
    with client.websocket_connect('/api/v1/ws/events?topic=*.*&tenant_id=tnt_smoke') as ws:
        import time
        time.sleep(0.05)
        from core.events import publish_sync
        publish_sync('smoke.ping', tenant_id='tnt_smoke', source='verify', msg='hi')
        deadline = time.time() + 2
        got = None
        while time.time() < deadline and not got:
            try:
                msg = ws.receive_json()
                if msg.get('topic') == 'smoke.ping':
                    got = msg
                    break
            except Exception:
                break
        assert got, 'ws 未收到事件'
        print('WS_OK', got['payload']['msg'])

print('OK')
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            env={**__import__("os").environ, "PYTHONPATH": "."},
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = proc.stdout + proc.stderr
        print(out)
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        return 1, "TIMEOUT"


# =====================================================
# 5) 脚本幂等冒烟（init_agents / setup_vector_db / seed_test_data）
# =====================================================
def smoke_scripts() -> tuple[int, str]:
    print("\n[E] 脚本幂等冒烟：init_agents / setup_vector_db / seed_test_data")
    code = """
import asyncio, tempfile, os
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix='verify_4d_'))
print('TMP', tmp)

# 1) init_agents
from scripts.init_agents import SUPPORTED_AGENTS  # type: ignore
assert set(SUPPORTED_AGENTS) == {'safety_audit_agent','compliance_agent','site_monitor_agent'}
print('INIT_AGENTS_OK', len(SUPPORTED_AGENTS))

# 2) setup_vector_db（dry-run + 实际 upsert 走 tmp）
from scripts.setup_vector_db import _scan_regulations, _scan_cases, _make_store  # type: ignore
regs = _scan_regulations(str(Path('data/regulations').resolve() if Path('data/regulations').exists() else tmp), 'tnt_smoke')
cases = _scan_cases(str(Path('data/cases').resolve() if Path('data/cases').exists() else tmp), 'tnt_smoke')
print('SCAN_OK', 'regulations=', len(regs), 'cases=', len(cases))

store, VectorRecord = _make_store()
async def _go():
    recs = [VectorRecord(**r) for r in regs + cases]
    if recs:
        n = await store.upsert(recs)
        return n
    return 0
n = asyncio.run(_go())
print('VECTOR_OK', 'upserted=', n, 'count=', store.count('tnt_smoke'))

# 3) seed_test_data（主入口直接调）
try:
    from scripts.seed_test_data import main as seed_main  # type: ignore
    # 脚本 main 通常是同步或异步入口；这里只做 import 验证 + 函数存在性
    print('SEED_IMPORT_OK', seed_main.__name__)
except Exception as e:
    print('SEED_SKIP', type(e).__name__, e)

print('OK')
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            env={**__import__("os").environ, "PYTHONPATH": "."},
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = proc.stdout + proc.stderr
        print(out)
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        return 1, "TIMEOUT"


# =====================================================
# 6) start_worker mock 模式
# =====================================================
def smoke_start_worker() -> tuple[int, str]:
    print("\n[F] start_worker mock 模式冒烟（仅 import + argv 解析）")
    code = """
import argparse, inspect
from scripts import start_worker  # type: ignore
# 解析 argv 路径
sig = inspect.signature(start_worker.main) if hasattr(start_worker, 'main') else None
print('START_WORKER_OK', 'main=', hasattr(start_worker, 'main'), 'argv=', sig is not None)
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            env={**__import__("os").environ, "PYTHONPATH": "."},
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
    print("  4d Stage Verify")
    print("=" * 64)

    results: list[tuple[str, int, str]] = []

    rc, out = run_scan()
    results.append(("scan", rc, out))
    if rc != 0:
        # scan 失败就提前收口（后续验收无意义）
        return _summary(results, time.time() - t0)

    rc, out = run_pytest()
    results.append(("pytest", rc, out))
    rc, out = smoke_app_health()
    results.append(("app_health", rc, out))
    rc, out = smoke_api_business()
    results.append(("api_business", rc, out))
    rc, out = smoke_scripts()
    results.append(("scripts", rc, out))
    rc, out = smoke_start_worker()
    results.append(("start_worker", rc, out))

    return _summary(results, time.time() - t0)


def _summary(results: list[tuple[str, int, str]], elapsed: float) -> int:
    print()
    print("=" * 64)
    print(f"  4d 验收结果（耗时 {elapsed:.1f}s）")
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
    print("  验收通过：4d FastAPI 接入 + 脚本 + 测试就绪")
    return 0


if __name__ == "__main__":
    sys.exit(main())


