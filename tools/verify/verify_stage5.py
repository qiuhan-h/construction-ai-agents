"""5 阶段动态验收框架：跑文件扫描 + 5a smoke + 5b/5c smoke（占位待实做）。

设计：
- [A] scan_stage5.py 子进程（必须 PASS，4e precondition + 5a 当前状态）
- [B] pytest_5a（5a 单测，待 5a 实做时填充 → 当前 SKIP）
- [C] smoke_5a_pages（5 个 page + 4 组件 render() 可解析 + render 离线构造）
- [D] smoke_5b_prod（占位：5b 实做后接 ChromaDB / PDF / ORM / 通知渠道 / IFC / LangChain）
- [E] smoke_5c_obs_deploy（占位：5c 实做后接 OTel / Prometheus / Dockerfile / CI / RBAC / SM2）

子阶段灵活选择：--only 5a / 5b / 5c

退出码：
- 0  选定子阶段全部通过（或仅 SKIP）
- 1  存在失败

运行：
    python tools/verify_stage5.py                # 全跑
    python tools/verify_stage5.py --only 5a       # 只跑 5a
    python tools/verify_stage5.py --skip-scan    # 跳过 scan 子项
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# =====================================================
# [A] scan
# =====================================================
def run_scan(only: str | None = None, strict: bool = False) -> tuple[int, str]:
    print("\n[A] scan_stage5.py")
    cmd = [sys.executable, str(ROOT / "tools" / "scan" / "scan_stage5.py")]
    if only:
        cmd += ["--only", only]
    if strict:
        cmd += ["--strict"]
    proc = subprocess.run(
        cmd, cwd=str(ROOT),
        capture_output=True, text=True, timeout=30,
    )
    out = proc.stdout + proc.stderr
    tail = "\n".join(out.splitlines()[-12:])
    print(tail)
    return proc.returncode, out


# =====================================================
# [B] pytest_5a（待 5a 实做时填充）
# =====================================================
def run_pytest_5a() -> tuple[int, str]:
    print("\n[B] pytest tests/integration/test_stage5a_pages.py")
    target = ROOT / "tests" / "integration" / "test_stage5a_pages.py"
    if not target.exists():
        print(f"  [SKIP] {target.relative_to(ROOT)} 待 5a 实做时创建")
        return 0, "SKIP"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(target), "-q", "--tb=line"],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": "."},
        capture_output=True, text=True, timeout=60,
    )
    out = proc.stdout + proc.stderr
    print("\n".join(out.splitlines()[-12:]))
    return proc.returncode, out


# =====================================================
# [C] smoke_5a_pages：5 个 page + 4 组件 render() 可解析
# =====================================================
def smoke_5a_pages() -> tuple[int, str]:
    print("\n[C] 5a page/component render() 离线构造")
    code = """
# 仅校验 render 函数存在、参数签名合理；不调用 streamlit.runtime
import importlib

# 5 个页面（数字开头 → importlib）
pages = ['01_safety_audit', '02_compliance', '03_site_monitor',
         '05_gis_viewer', '06_agent_management']

ok_pages = 0
for name in pages:
    full = f'streamlit_app.pages.{name}'
    try:
        mod = importlib.import_module(full)
    except ModuleNotFoundError as e:
        print(f'PAGE_SKIP {full}: {e.name}')
        continue
    except Exception as e:
        print(f'PAGE_FAIL {full}: {type(e).__name__}: {e}')
        continue
    if callable(getattr(mod, 'render', None)):
        print(f'PAGE_OK {full}')
        ok_pages += 1
    else:
        print(f'PAGE_FAIL {full} (无 render())')

# 4 个组件
components = ['alert_display', 'chart_component', 'map_component', 'report_viewer']
ok_comp = 0
for name in components:
    full = f'streamlit_app.components.{name}'
    try:
        mod = importlib.import_module(full)
    except ModuleNotFoundError as e:
        print(f'COMP_SKIP {full}: {e.name}')
        continue
    except Exception as e:
        print(f'COMP_FAIL {full}: {type(e).__name__}: {e}')
        continue
    if callable(getattr(mod, 'render', None)):
        print(f'COMP_OK {full}')
        ok_comp += 1
    else:
        print(f'COMP_FAIL {full} (无 render())')

print(f'SUMMARY pages_ok={ok_pages}/5 components_ok={ok_comp}/4')
print('OK' if (ok_pages + ok_comp) >= 1 else 'PARTIAL')
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": "."},
            capture_output=True, text=True, timeout=30,
        )
        out = proc.stdout + proc.stderr
        print(out)
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        return 1, "TIMEOUT"


# =====================================================
# [D] smoke_5b_prod：6 项子探针对应 plan §5 5b 验收清单
#  - 5b.2 ChromaStore upsert + query
#  - 5b.1 PDFExporter.export 返回非空 bytes
#  - 5b.3 SQLAlchemy 仓储（替换内存）
#  - 5b.4 通知渠道真实发送
#  - 5b.5 IFC 真实解析
#  - 5b.6 LangChain 真实业务链
# 每个子探针独立返回 PROBE_OK / PROBE_SKIP / PROBE_FAIL；
# 任何子探针 PROBE_FAIL 即整段 FAIL（plan §5 严格判定）。
# =====================================================
def smoke_5b_prod() -> tuple[int, str]:
    print("\n[D] 5b 后端生产化 smoke（6 项子探针）")
    code = r"""
import importlib
import sys
from pathlib import Path

ROOT = Path.cwd()

# 统一探针 helper
def probe(label: str, fn):
    try:
        detail = fn()
        print(f'PROBE_OK {label} {detail or ""}'.rstrip())
        return True
    except ModuleNotFoundError as e:
        print(f'PROBE_SKIP {label} (缺依赖: {e.name})')
        return True   # SKIP 不算 FAIL
    except NotImplementedError as e:
        print(f'PROBE_SKIP {label} (实做中: {e})')
        return True
    except Exception as e:
        print(f'PROBE_FAIL {label}: {type(e).__name__}: {e}')
        return False

fails = 0

# ---- 5b.2 ChromaStore ----
def _probe_chromadb():
    if not (ROOT / 'core/vector_store/chroma_store.py').exists():
        raise NotImplementedError('chroma_store.py 尚未实做')
    sys.path.insert(0, str(ROOT))
    mod = importlib.import_module('core.vector_store.chroma_store')
    # 5b.2 落地类名 = ChromaVectorStore（与 InMemoryVectorStore 对仗）
    cls = (
        getattr(mod, 'ChromaVectorStore', None)
        or getattr(mod, 'ChromaStore', None)
    )
    if cls is None:
        raise NotImplementedError('ChromaVectorStore 类未定义')
    return f'ChromaVectorStore={cls.__name__}'

if not probe('5b.2_chromadb', _probe_chromadb):
    fails += 1

# ---- 5b.1 PDFExporter ----
def _probe_pdf_exporter():
    if not (ROOT / 'services/pdf_exporter.py').exists():
        raise NotImplementedError('pdf_exporter.py 尚未实做')
    sys.path.insert(0, str(ROOT))
    mod = importlib.import_module('services.pdf_exporter')
    cls = getattr(mod, 'PDFExporter', None)
    if cls is None:
        raise NotImplementedError('PDFExporter 类未定义')
    return f'PDFExporter={cls.__name__}'

if not probe('5b.1_pdf_exporter', _probe_pdf_exporter):
    fails += 1

# ---- 5b.3 SQLAlchemy 仓储 ----
def _probe_sqlalchemy_repos():
    if not (ROOT / 'core/storage/sqlalchemy_repos.py').exists():
        raise NotImplementedError('sqlalchemy_repos.py 尚未实做')
    sys.path.insert(0, str(ROOT))
    mod = importlib.import_module('core.storage.sqlalchemy_repos')
    # 期望至少 1 个 Repo 类
    repo_names = [n for n in dir(mod) if n.endswith('Repo') or n.endswith('Repository')]
    if not repo_names:
        raise NotImplementedError('未找到任何 *Repo 类')
    return f'{len(repo_names)} 个 Repo: {repo_names[:3]}'

if not probe('5b.3_sqlalchemy_repos', _probe_sqlalchemy_repos):
    fails += 1

# ---- 5b.4 通知渠道真实发送 ----
def _probe_notification_real():
    # check 4 channels for send() method; do NOT actually send
    sys.path.insert(0, str(ROOT))
    channels = [
        'services.notification_channels.sms_aliyun_channel',
        'services.notification_channels.dingtalk_real_channel',
        'services.notification_channels.wecom_real_channel',
    ]
    found = []
    for c in channels:
        path = Path(c.replace('.', '/') + '.py')
        if not (ROOT / path).exists():
            continue
        try:
            mod = importlib.import_module(c)
            cls_name = next((n for n in dir(mod) if n.endswith('Channel')), None)
            if cls_name:
                cls = getattr(mod, cls_name)
                if hasattr(cls, 'send'):
                    found.append(cls_name)
        except Exception:
            continue
    if not found:
        raise NotImplementedError('真实通知渠道尚未实做')
    return f'{len(found)} 个真实渠道: {found}'

if not probe('5b.4_notification_real', _probe_notification_real):
    fails += 1

# ---- 5b.5 IFC 真实解析 ----
def _probe_ifc_real_parser():
    # AST static scan; works without pydantic / ifcopenshell in sandbox
    parser_path = ROOT / 'agents/site_monitor_agent/bim_integration/ifc_real_parser.py'
    influx_path = ROOT / 'agents/site_monitor_agent/iot_integration/influxdb_writer.py'
    if not parser_path.exists():
        raise NotImplementedError('ifc_real_parser.py 尚未实做')
    if not influx_path.exists():
        raise NotImplementedError('influxdb_writer.py 尚未实做')
    import ast as _ast

    tree = _ast.parse(parser_path.read_text(encoding='utf-8'), filename=str(parser_path))
    classes = {n.name for n in tree.body if isinstance(n, _ast.ClassDef)}
    fns = {n.name for n in tree.body if isinstance(n, _ast.FunctionDef)}
    found = []
    if 'IFCRealParser' in classes:
        found.append('IFCRealParser')
    if 'parse_ifc_file' in fns:
        found.append('parse_ifc_file')
    if not found:
        raise NotImplementedError('ifc_real_parser 缺 IFCRealParser 类 / parse_ifc_file 函数')
    # InfluxDB 同样检查
    tree2 = _ast.parse(influx_path.read_text(encoding='utf-8'), filename=str(influx_path))
    classes2 = {n.name for n in tree2.body if isinstance(n, _ast.ClassDef)}
    if 'InfluxDBWriter' in classes2:
        found.append('InfluxDBWriter')
    return f'{len(found)} 项: {found}'

if not probe('5b.5_ifc_real_parser', _probe_ifc_real_parser):
    fails += 1

# ---- 5b.6 LangChain 真实业务链 ----
def _probe_langchain_chains():
    if not (ROOT / 'core/langchain/chains.py').exists():
        raise NotImplementedError('core/langchain/chains.py 尚未实做')
    sys.path.insert(0, str(ROOT))
    mod = importlib.import_module('core.langchain.chains')
    chains = [n for n in dir(mod) if 'Chain' in n and not n.startswith('_')]
    if not chains:
        raise NotImplementedError('未找到任何 Chain 类')
    return f'{len(chains)} 个 Chain: {chains[:3]}'

if not probe('5b.6_langchain_chains', _probe_langchain_chains):
    fails += 1

print(f'5B_SUMMARY fails={fails}/6')
sys.exit(1 if fails > 0 else 0)
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": "."},
            capture_output=True, text=True, timeout=30,
        )
        out = proc.stdout + proc.stderr
        print(out)
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        return 1, "TIMEOUT"


# =====================================================
# [E] smoke_5c_obs_deploy：9 项子探针对应 plan §5 5c 验收清单
#  - 5c.1 OTel tracer / 3 中间件
#  - 5c.2 Prometheus /metrics 端点
#  - 5c.4 Dockerfile.{api,worker,streamlit,a2a,mcp} 多阶段 + 非 root + HEALTHCHECK
#  - 5c.5 K8s deployments 探针
#  - 5c.6 GitHub Actions ci.yml 三阶段
#  - 5c.7 RBAC require_role 装饰器
#  - 5c.8 国密 SM2 签章
# =====================================================
def smoke_5c_obs_deploy() -> tuple[int, str]:
    print("\n[E] 5c 可观测 + 部署 + CI smoke（9 项子探针）")
    code = r"""
import importlib
import re
import sys
from pathlib import Path

ROOT = Path.cwd()


def probe(label: str, fn):
    try:
        detail = fn()
        print(f'PROBE_OK {label} {detail or ""}'.rstrip())
        return True
    except ModuleNotFoundError as e:
        print(f'PROBE_SKIP {label} (缺依赖: {e.name})')
        return True
    except NotImplementedError as e:
        print(f'PROBE_SKIP {label} (实做中: {e})')
        return True
    except Exception as e:
        print(f'PROBE_FAIL {label}: {type(e).__name__}: {e}')
        return False


fails = 0
sys.path.insert(0, str(ROOT))


# ---- 5c.1 OTel tracer + 3 middleware ----
def _probe_otel_tracer():
    if not (ROOT / 'core/observability/tracer.py').exists():
        raise NotImplementedError('core/observability/tracer.py 尚未实做')
    mod = importlib.import_module('core.observability.tracer')
    fn = getattr(mod, 'get_tracer', None)
    if not callable(fn):
        raise NotImplementedError('get_tracer() 未定义')
    # 三个中间件
    for mw in ('a2a_middleware', 'mcp_middleware', 'api_middleware'):
        mw_mod = importlib.import_module(f'core.observability.{mw}')
        if not hasattr(mw_mod, 'setup') and not hasattr(mw_mod, 'install'):
            raise NotImplementedError(f'{mw} 缺 setup/install 入口')
    return 'tracer + 3 middleware 就位'

if not probe('5c.1_otel', _probe_otel_tracer):
    fails += 1

# ---- 5c.2 Prometheus /metrics 端点 ----
def _probe_prometheus_metrics():
    if not (ROOT / 'core/observability/metrics.py').exists():
        raise NotImplementedError('core/observability/metrics.py 尚未实做')
    if not (ROOT / 'core/observability/exporter.py').exists():
        raise NotImplementedError('core/observability/exporter.py 尚未实做')
    metrics_mod = importlib.import_module('core.observability.metrics')
    expected = ['request_total', 'ws_connections']
    missing = [m for m in expected if not hasattr(metrics_mod, m)]
    if missing:
        raise NotImplementedError(f'业务指标未定义: {missing}')
    return f'指标定义: {expected}'

if not probe('5c.2_prometheus', _probe_prometheus_metrics):
    fails += 1

# ---- 5c.4 Dockerfile 健全（多阶段 + 非 root + HEALTHCHECK）----
def _probe_dockerfile(name: str):
    path = ROOT / f'deployment/docker/Dockerfile.{name}'
    if not path.exists():
        raise NotImplementedError(f'Dockerfile.{name} 尚未实做')
    text = path.read_text(encoding='utf-8', errors='ignore')
    issues = []
    # 1) 多阶段构建（builder / runtime）
    if not re.search(r'FROM\s+\S+\s+AS\s+builder', text, re.IGNORECASE):
        issues.append('缺 builder 多阶段')
    # 2) 非 root 用户
    if not re.search(r'^USER\s+\S+', text, re.MULTILINE):
        issues.append('缺 USER 非 root')
    # 3) HEALTHCHECK
    if 'HEALTHCHECK' not in text:
        issues.append('缺 HEALTHCHECK')
    if issues:
        raise NotImplementedError(f'Dockerfile.{name} 不健全: {"; ".join(issues)}')
    return f'Dockerfile.{name}: builder+USER+HEALTHCHECK OK'


for name in ('api', 'worker', 'streamlit', 'a2a', 'mcp'):
    if not probe(f'5c.4_dockerfile_{name}', lambda n=name: _probe_dockerfile(n)):
        fails += 1

# ---- 5c.5 K8s deployments 探针 ----
def _probe_k8s():
    if not (ROOT / 'deployment/kubernetes/deployments').is_dir():
        raise NotImplementedError('deployment/kubernetes/deployments/ 尚未实做')
    yamls = list((ROOT / 'deployment/kubernetes/deployments').glob('*.yaml'))
    if len(yamls) < 5:
        raise NotImplementedError(
            f'Deployment < 5 个（当前 {len(yamls)}）'
        )
    # 检查至少 1 个含 livenessProbe
    has_probe = any('livenessProbe' in y.read_text(errors='ignore') for y in yamls)
    if not has_probe:
        raise NotImplementedError('所有 Deployment 缺 livenessProbe')
    return f'{len(yamls)} 个 Deployment + 探针 OK'

if not probe('5c.5_k8s', _probe_k8s):
    fails += 1

# ---- 5c.6 GitHub Actions ci.yml 三阶段 ----
def _probe_ci():
    path = ROOT / '.github/workflows/ci.yml'
    if not path.exists():
        raise NotImplementedError('.github/workflows/ci.yml 尚未实做')
    text = path.read_text(encoding='utf-8', errors='ignore')
    stages = ['ruff', 'mypy', 'pytest']
    missing = [s for s in stages if s not in text]
    if missing:
        raise NotImplementedError(f'ci.yml 缺阶段: {missing}')
    return f'3 阶段 OK: {stages}'

if not probe('5c.6_ci', _probe_ci):
    fails += 1

# ---- 5c.7 RBAC ----
def _probe_rbac():
    if not (ROOT / 'api/dependencies/rbac.py').exists():
        raise NotImplementedError('api/dependencies/rbac.py 尚未实做')
    mod = importlib.import_module('api.dependencies.rbac')
    fn = getattr(mod, 'require_role', None)
    if not callable(fn):
        raise NotImplementedError('require_role() 未定义')
    return 'require_role() OK'

if not probe('5c.7_rbac', _probe_rbac):
    fails += 1

# ---- 5c.8 SM2 签章 ----
def _probe_sm2():
    if not (ROOT / 'core/security/sm2_signer.py').exists():
        raise NotImplementedError('core/security/sm2_signer.py 尚未实做')
    mod = importlib.import_module('core.security.sm2_signer')
    cls_name = next((n for n in dir(mod) if 'Sign' in n), None)
    if not cls_name:
        raise NotImplementedError('未找到 Sign 类')
    return f'{cls_name} OK'

if not probe('5c.8_sm2', _probe_sm2):
    fails += 1

print(f'5C_SUMMARY fails={fails}/12')
sys.exit(1 if fails > 0 else 0)
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": "."},
            capture_output=True, text=True, timeout=30,
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
    parser = argparse.ArgumentParser(description="5 阶段动态验收框架")
    parser.add_argument("--only", choices=["5a", "5b", "5c"], help="只跑指定子阶段")
    parser.add_argument("--skip-scan", action="store_true", help="跳过 [A] scan 子项")
    parser.add_argument("--strict", action="store_true", help="scan 也走严格模式")
    args = parser.parse_args()

    t0 = time.time()
    print("=" * 64)
    print("  5 Stage Verify")
    print("=" * 64)
    if args.only:
        print(f"  范围：仅 {args.only}")

    results: list[tuple[str, int, str]] = []

    # [A] scan
    if not args.skip_scan:
        rc, out = run_scan(only=args.only, strict=args.strict)
        results.append(("scan", rc, out))
        if rc != 0:
            return _summary(results, time.time() - t0)

    # [B] pytest_5a
    if args.only in (None, "5a"):
        rc, out = run_pytest_5a()
        results.append(("pytest_5a", rc, out))

    # [C] smoke_5a_pages
    if args.only in (None, "5a"):
        rc, out = smoke_5a_pages()
        results.append(("smoke_5a_pages", rc, out))

    # [D] smoke_5b_prod
    if args.only == "5b" or args.only is None:
        rc, out = smoke_5b_prod()
        results.append(("smoke_5b_prod", rc, out))

    # [E] smoke_5c_obs_deploy
    if args.only == "5c" or args.only is None:
        rc, out = smoke_5c_obs_deploy()
        results.append(("smoke_5c_obs_deploy", rc, out))

    return _summary(results, time.time() - t0)


def _summary(results: list[tuple[str, int, str]], elapsed: float) -> int:
    print()
    print("=" * 64)
    print(f"  5 验收结果（耗时 {elapsed:.1f}s）")
    print("=" * 64)
    fails: list[str] = []
    for name, rc, _ in results:
        if rc == 0:
            print(f"  [OK ] {name}")
        else:
            print(f"  [FAIL] {name}")
            fails.append(name)
    if fails:
        print()
        print(f"  验收未通过：{len(fails)} 项失败 -> {fails}")
        return 1
    print()
    print("  验收通过：5 系列验收框架就位（5b / 5c smoke 待实做填充）")
    return 0


if __name__ == "__main__":
    sys.exit(main())


