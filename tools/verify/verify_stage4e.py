"""4e 阶段验收：跑文件扫描 + dashboard 单测 + 端到端冒烟 + API 形状探针。

退出码：
- 0  全部通过
- 1  有失败

运行：python tools/verify_stage4e.py
"""

from __future__ import annotations

import os
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
    print("\n[A] 4e 文件扫描")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "scan" / "scan_stage4e.py")],
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
# 2) pytest：dashboard 数据形状单测（4e 专属）
# =====================================================
def run_pytest_dashboard() -> tuple[int, str]:
    print("\n[B] pytest tests/integration/test_dashboard_data.py")
    proc = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/integration/test_dashboard_data.py",
            "-q", "--tb=line",
        ],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": "."},
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = proc.stdout + proc.stderr
    tail = "\n".join(out.splitlines()[-12:])
    print(tail)
    return proc.returncode, out


# =====================================================
# 3) 端到端冒烟：4d dashboard 配套 API 探针
# 校验 /stats /workflows /timeline /runs 全链路 OK
# =====================================================
def smoke_dashboard_api() -> tuple[int, str]:
    print("\n[C] 端到端冒烟：dashboard 4 个核心 API（/stats /workflows /timeline /runs）")
    code = """
from fastapi.testclient import TestClient
from api.main import create_app
from api.dependencies.agent_manager import reset_agent_manager
from api.dependencies.orchestrator_provider import reset_orchestrator
from core.events import reset_event_bus

reset_event_bus(); reset_agent_manager(); reset_orchestrator()

with TestClient(create_app()) as client:
    h = {'Authorization': 'Bearer dev-tnt_e2e-admin'}

    # /stats
    r = client.get('/api/v1/orchestrator/stats', headers=h)
    assert r.status_code == 200, r.text
    data = r.json()['data']
    for k in ('workflows','runs','today_triggers','collaboration_entries','failed','last_run_id','last_run_status','is_running','as_of'):
        assert k in data, k
    print('STATS_OK', data['workflows'], 'wf,', data['runs'], 'runs,', data['failed'], 'failed')

    # /workflows
    r = client.get('/api/v1/orchestrator/workflows', headers=h)
    assert r.status_code == 200, r.text
    wfs = r.json()['data']['workflows']
    assert len(wfs) >= 1, wfs
    print('WF_LIST_OK', [w['name'] for w in wfs])

    # /workflows/{name}
    target = wfs[0]['name']
    r = client.get(f'/api/v1/orchestrator/workflows/{target}', headers=h)
    assert r.status_code == 200, r.text
    print('WF_DETAIL_OK', target)

    # /trigger + /timeline + /runs/{id} 全链路
    payload = {'alert_id': 'al-e2e', 'level': 'critical'} if target == 'monitor_alert_to_audit' else {}
    r = client.post(f'/api/v1/orchestrator/workflows/{target}/trigger',
                    json=payload, headers=h)
    assert r.status_code == 200, r.text
    run_id = r.json()['data']['run_id']
    print('TRIGGER_OK', target, run_id)

    r = client.get('/api/v1/orchestrator/timeline?limit=10', headers=h)
    assert r.status_code == 200, r.text
    tl = r.json()['data']
    assert tl['truncated'] is True
    assert any(e.get('metadata', {}).get('run_id') == run_id for e in tl['timeline'])
    print('TIMELINE_OK', tl['total'], 'entries, truncated=', tl['truncated'])

    r = client.get(f'/api/v1/orchestrator/runs/{run_id}', headers=h)
    assert r.status_code == 200, r.text
    info = r.json()['data']
    assert info['workflow'] == target
    print('RUN_OK', run_id, info['status'])

print('OK')
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": "."},
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
# 4) 端到端冒烟：streamlit utils 离线构造
# =====================================================
def smoke_streamlit_utils() -> tuple[int, str]:
    print("\n[D] streamlit utils 离线构造：APIClient / StateManager / EventStreamClient")
    code = """
# 直接构造 utils（无 streamlit runtime），验证 4e 离线可调用
from streamlit_app.utils import (
    APIClient, APIError, api_client,
    EventStreamClient, build_ws_base_from_http,
    DEFAULTS,
)
import inspect

# 1) APIClient 基本属性
c = APIClient(base_url='http://127.0.0.1:9999', token='dev-tnt_x-u')
assert c.base_url == 'http://127.0.0.1:9999'
assert c.auth_headers == {'Authorization': 'Bearer dev-tnt_x-u'}
print('APICLIENT_OK', c.base_url)

# 2) WS 协议转换
ws = build_ws_base_from_http('http://a.b:8000')
assert ws == 'ws://a.b:8000', ws
ws = build_ws_base_from_http('https://a.b')
assert ws == 'wss://a.b', ws
print('WS_BASE_OK', ws)

# 3) EventStreamClient 构造（不启动线程）
evc = EventStreamClient(ws_url='ws://localhost:8000', topic='*.*', tenant_id='tnt_x')
assert evc.topic == '*.*' and evc.tenant_id == 'tnt_x'
print('EVCLIENT_OK', type(evc).__name__)

# 4) DEFAULTS 含 dashboard 关键 key
for k in ('caai_tenant_id', 'caai_api_base', 'caai_token', 'caai_ws_topic', 'caai_timeline'):
    assert k in DEFAULTS, k
print('DEFAULTS_OK', list(DEFAULTS.keys())[:4], '...')

# 5) 单例 api_client()
c2 = api_client()
assert isinstance(c2, APIClient)
print('SINGLETON_OK', c2 is api_client())

# 6) APIClient 业务方法签名存在
for name in ('healthz', 'readyz', 'list_workflows', 'get_workflow', 'trigger_workflow',
             'get_run', 'list_timeline', 'get_stats', 'list_reports', 'list_supported_agents'):
    assert hasattr(c, name), name
print('APICLIENT_METHODS_OK')

# 7) trigger_workflow 接受 via_query 参数
sig = inspect.signature(c.trigger_workflow)
assert 'via_query' in sig.parameters
print('TRIGGER_VIA_QUERY_OK')

print('OK')
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": "."},
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
# 5) 端到端冒烟：04_dashboard render() 路径可解析
# =====================================================
def smoke_dashboard_render() -> tuple[int, str]:
    print("\n[E] 04_dashboard.render() 路径校验（不实际渲染 Streamlit）")
    code = """
# 仅校验 render 函数存在、参数签名合理；不调用 streamlit.runtime
import importlib

# 04_dashboard 模块名以数字开头，必须用 importlib
dashboard_mod = importlib.import_module("streamlit_app.pages.04_dashboard")
render = dashboard_mod.render
_suggest_default_payload = dashboard_mod._suggest_default_payload

assert callable(render)
print('RENDER_OK')

# 4 个 tab 暗示函数
for name in ('_render_overview', '_render_workflows', '_render_runs', '_render_events'):
    assert hasattr(dashboard_mod, name), name
print('TAB_FUNCS_OK')

# 默认 payload 适配 3 类内置工作流
for wf in ('monitor_alert_to_audit', 'compliance_followup', 'regulation_record'):
    p = _suggest_default_payload(wf)
    assert isinstance(p, dict)
    print('PAYLOAD_OK', wf, list(p.keys()))

print('OK')
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": "."},
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
# main
# =====================================================
def main() -> int:
    t0 = time.time()
    print("=" * 64)
    print("  4e Stage Verify")
    print("=" * 64)

    results: list[tuple[str, int, str]] = []

    rc, out = run_scan()
    results.append(("scan", rc, out))
    if rc != 0:
        return _summary(results, time.time() - t0)

    rc, out = run_pytest_dashboard()
    results.append(("pytest_dashboard", rc, out))

    rc, out = smoke_dashboard_api()
    results.append(("dashboard_api", rc, out))

    rc, out = smoke_streamlit_utils()
    results.append(("streamlit_utils", rc, out))

    rc, out = smoke_dashboard_render()
    results.append(("dashboard_render", rc, out))

    return _summary(results, time.time() - t0)


def _summary(results: list[tuple[str, int, str]], elapsed: float) -> int:
    print()
    print("=" * 64)
    print(f"  4e 验收结果（耗时 {elapsed:.1f}s）")
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
    print("  验收通过：4e Streamlit Dashboard 编排可视化就绪")
    return 0


if __name__ == "__main__":
    sys.exit(main())


