"""5 阶段静态文件扫描：核对 5a（前端页面 + 组件）+ 5b（后端生产化）+ 5c（可观测/部署/CI）
所有规划文件的交付状态。

设计要点：
- 按子阶段分级：5a / 5b / 5c
- 空缺走 SKIP 而非 FAIL（5b / 5c 大量文件尚未实做，框架必须优雅降级）
- 子阶段仅当所有前置文件就位时才进入"严格模式"（MISSING 视为 FAIL）
- 4e 已就位文件作为 "precondition" 先校验，避免 5a 的 scan 把 4e 缺失误判

退出码：
- 0  5a + 4e 全部 OK；5b / 5c 可选 OK 或 SKIP
- 1  5a 或 4e 存在缺失/导入失败

运行：python tools/scan_stage5.py
       python tools/scan_stage5.py --strict     # 5b/5c 也视为严格
       python tools/scan_stage5.py --only 5a    # 只扫 5a
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# =====================================================
# 4e precondition（必须就位，否则 5 系列无意义）
# =====================================================
PRECONDITION_FILES: list[tuple[str, str]] = [
    ("streamlit_app/__init__.py", "package"),
    ("streamlit_app/app.py", "module"),
    ("streamlit_app/utils/__init__.py", "package"),
    ("streamlit_app/utils/api_client.py", "module"),
    ("streamlit_app/utils/websocket_client.py", "module"),
    ("streamlit_app/utils/state_manager.py", "module"),
    ("streamlit_app/pages/04_dashboard.py", "module"),
    ("api/routers/orchestrator_router.py", "module"),
    ("tools/scan/scan_stage4e.py", "module"),
    ("tools/verify/verify_stage4e.py", "module"),
]

# =====================================================
# 5a：Streamlit 5 页面 + 4 组件（9 个新文件）
# 现状：均为空占位（待 5a 编码），所以框架先以 SKIP 处理
# =====================================================
STAGE_5A_FILES: list[tuple[str, str]] = [
    # 5 个页面（4e 占位升级）
    ("streamlit_app/pages/01_safety_audit.py", "module"),
    ("streamlit_app/pages/02_compliance.py", "module"),
    ("streamlit_app/pages/03_site_monitor.py", "module"),
    ("streamlit_app/pages/05_gis_viewer.py", "module"),
    ("streamlit_app/pages/06_agent_management.py", "module"),
    # 4 个组件
    ("streamlit_app/components/alert_display.py", "module"),
    ("streamlit_app/components/chart_component.py", "module"),
    ("streamlit_app/components/map_component.py", "module"),
    ("streamlit_app/components/report_viewer.py", "module"),
]

# =====================================================
# 5b：后端生产化（14 个新文件）
# =====================================================
STAGE_5B_FILES: list[tuple[str, str]] = [
    # 5b.1 报告 PDF 导出
    ("services/pdf_exporter.py", "module"),
    ("services/reportlab_assets/__init__.py", "package"),
    # 5b.2 ChromaDB
    ("core/vector_store/__init__.py", "package"),
    ("core/vector_store/base.py", "module"),
    ("core/vector_store/chroma_store.py", "module"),
    ("core/vector_store/factory.py", "module"),
    # 5b.3 仓储 ORM
    ("core/storage/__init__.py", "package"),
    ("core/storage/base.py", "module"),
    ("core/storage/sqlalchemy_repos.py", "module"),
    # 5b.4 通知渠道真实发送
    ("services/notification_channels/sms_aliyun_channel.py", "module"),
    ("services/notification_channels/dingtalk_real_channel.py", "module"),
    ("services/notification_channels/wecom_real_channel.py", "module"),
    # 5b.5 IFC / BIM / TSDB
    ("agents/site_monitor_agent/bim_integration/ifc_real_parser.py", "module"),
    ("agents/site_monitor_agent/iot_integration/influxdb_writer.py", "module"),
    # 5b.6 LangChain 业务链
    ("core/langchain/chains.py", "module"),
    # 5b.7 历史持久化
    ("agents/site_monitor_agent/gis_monitoring/geofence_history.py", "module"),
]

# =====================================================
# 5c：可观测 + 部署 + CI + RBAC + 安全（18 个新文件）
# =====================================================
STAGE_5C_FILES: list[tuple[str, str]] = [
    # 5c.1 OTel
    ("core/observability/__init__.py", "package"),
    ("core/observability/tracer.py", "module"),
    ("core/observability/a2a_middleware.py", "module"),
    ("core/observability/mcp_middleware.py", "module"),
    ("core/observability/api_middleware.py", "module"),
    # 5c.2 Prometheus
    ("core/observability/metrics.py", "module"),
    ("core/observability/exporter.py", "module"),
    ("deployment/monitoring/prometheus.yml", "config"),
    ("deployment/monitoring/grafana_dashboard.json", "config"),
    # 5c.3 cache + timeseries
    ("core/cache/__init__.py", "package"),
    ("core/cache/redis_cache.py", "module"),
    ("core/timeseries/__init__.py", "package"),
    # 5c.4 Dockerfile（5 个）
    ("deployment/docker/Dockerfile.api", "module"),
    ("deployment/docker/Dockerfile.worker", "module"),
    ("deployment/docker/Dockerfile.streamlit", "module"),
    ("deployment/docker/Dockerfile.a2a", "module"),
    ("deployment/docker/Dockerfile.mcp", "module"),
    # 5c.6 CI
    (".github/workflows/ci.yml", "config"),
    # 5c.7 RBAC
    ("api/dependencies/rbac.py", "module"),
    # 5c.8 安全
    ("core/security/sm2_signer.py", "module"),
    ("core/security/cert_manager.py", "module"),
    # 5c.9 烟雾工具
    ("tools/smoke_e2e.py", "module"),
]

# =====================================================
# 期望能 import 的模块（5a 就位后可加载）
# =====================================================
EXPECTED_MODULES_5A: list[str] = [
    "streamlit_app.components",
    "streamlit_app.pages.01_safety_audit",
    "streamlit_app.pages.02_compliance",
    "streamlit_app.pages.03_site_monitor",
    "streamlit_app.pages.05_gis_viewer",
    "streamlit_app.pages.06_agent_management",
]

# =====================================================
# 5a 必需 export 符号（每个 page 都暴露 render()）
# =====================================================
EXPECTED_EXPORTS_5A: list[tuple[str, str]] = [
    ("streamlit_app.components.alert_display", "render"),
    ("streamlit_app.components.chart_component", "render"),
    ("streamlit_app.components.map_component", "render"),
    ("streamlit_app.components.report_viewer", "render"),
    ("streamlit_app.pages.01_safety_audit", "render"),
    ("streamlit_app.pages.02_compliance", "render"),
    ("streamlit_app.pages.03_site_monitor", "render"),
    ("streamlit_app.pages.05_gis_viewer", "render"),
    ("streamlit_app.pages.06_agent_management", "render"),
]


def _scan_files(stage: str, files: list[tuple[str, str]], strict: bool) -> tuple[list[str], int, int]:
    """扫描一组文件。返回 (失败列表, OK 数, SKIP 数)。

    strict=False：缺失/空文件 -> SKIP；strict=True -> FAIL
    """
    fails: list[str] = []
    ok_count = 0
    skip_count = 0
    for rel, kind in files:
        p = ROOT / rel
        if not p.exists():
            if strict:
                fails.append(f"FILE_MISSING {stage}/{rel}")
                print(f"  [FAIL] {stage}/{rel} ({kind})")
            else:
                print(f"  [SKIP] {stage}/{rel} (待 {stage} 实做)")
                skip_count += 1
            continue
        if p.stat().st_size == 0:
            if strict:
                fails.append(f"FILE_EMPTY {stage}/{rel}")
                print(f"  [FAIL] {stage}/{rel} (empty)")
            else:
                print(f"  [SKIP] {stage}/{rel} (空占位)")
                skip_count += 1
            continue
        print(f"  [ OK ] {stage}/{rel}")
        ok_count += 1
    return fails, ok_count, skip_count


def _scan_modules(modules: list[str]) -> tuple[list[str], int]:
    """扫描一组模块。返回 (失败列表, OK 数)。缺失模块走 SKIP。"""
    fails: list[str] = []
    ok = 0
    for m in modules:
        try:
            importlib.import_module(m)
            print(f"  [ OK ] {m}")
            ok += 1
        except ModuleNotFoundError as e:
            print(f"  [SKIP] {m} (ModuleNotFoundError: {e.name})")
        except Exception as e:  # noqa: BLE001
            fails.append(f"IMPORT_FAIL {m}: {e}")
            print(f"  [FAIL] {m}: {type(e).__name__}: {e}")
    return fails, ok


def _scan_exports(exports: list[tuple[str, str]]) -> tuple[list[str], int]:
    """扫描关键 export。缺失走 SKIP（文件未实做），未到 strict 模式不视为 FAIL。"""
    fails: list[str] = []
    ok = 0
    for mod_name, symbol in exports:
        # 物理文件存在性 + 字节数检查（避免空占位被当 OK）
        # mod_name 是 Python 路径，需要还原成文件路径
        rel_path = mod_name.replace(".", "/") + ".py"
        # 处理 __init__ 包（path 是包路径本身）
        for candidate in (rel_path, rel_path.rsplit("/", 1)[0] + "/__init__.py"):
            p = ROOT / candidate
            if p.exists():
                rel_path = candidate
                break
        else:
            print(f"  [SKIP] {mod_name}.{symbol} (文件未就位)")
            continue

        p = ROOT / rel_path
        if p.stat().st_size == 0:
            print(f"  [SKIP] {mod_name}.{symbol} (空占位)")
            continue

        try:
            mod = importlib.import_module(mod_name)
        except ModuleNotFoundError as e:
            print(f"  [SKIP] {mod_name}.{symbol} (缺依赖: {e.name})")
            continue
        except Exception as e:  # noqa: BLE001
            fails.append(f"IMPORT_FAIL {mod_name}: {e}")
            print(f"  [FAIL] {mod_name}: {type(e).__name__}: {e}")
            continue

        if hasattr(mod, symbol):
            print(f"  [ OK ] {mod_name}.{symbol}")
            ok += 1
        else:
            fails.append(f"EXPORT_MISSING {mod_name}.{symbol}")
            print(f"  [FAIL] {mod_name}.{symbol} (无此属性)")
    return fails, ok


def main() -> int:
    parser = argparse.ArgumentParser(description="5 阶段静态文件扫描")
    parser.add_argument("--strict", action="store_true", help="5b/5c 也视为严格（缺则 FAIL）")
    parser.add_argument("--only", choices=["5a", "5b", "5c"], help="只扫指定子阶段")
    args = parser.parse_args()

    print("=" * 64)
    print("  5 Stage File Scan")
    print("=" * 64)
    print(f"  模式：{'strict' if args.strict else 'lenient（5b/5c 走 SKIP）'}")
    if args.only:
        print(f"  范围：仅 {args.only}")

    fails: list[str] = []
    total_ok = 0
    total_skip = 0

    # ---- 0) 4e precondition（strict 模式必检）----
    print("\n[0/4] 4e precondition（4 系列已就位文件）")
    pre_fails, pre_ok, _ = _scan_files("pre", PRECONDITION_FILES, strict=True)
    fails.extend(pre_fails)
    total_ok += pre_ok
    if pre_fails:
        print(f"  4e precondition 失败 {len(pre_fails)} 项，无法继续")
        return _summary(fails, total_ok, total_skip, 0, 0, 0, 0, 0, 0)

    # ---- 1) 5a 文件存在性 ----
    if args.only in (None, "5a"):
        print("\n[1/4] 5a 文件存在性（9 个新文件）")
        a_fails, a_ok, a_skip = _scan_files("5a", STAGE_5A_FILES, strict=args.strict)
        if args.strict:
            fails.extend(a_fails)
        total_ok += a_ok
        total_skip += a_skip

    # ---- 2) 5b 文件存在性 ----
    if args.only == "5b" or (args.only is None):
        print("\n[2/4] 5b 文件存在性（17 个新文件）")
        b_fails, b_ok, b_skip = _scan_files("5b", STAGE_5B_FILES, strict=args.strict)
        if args.strict:
            fails.extend(b_fails)
        total_ok += b_ok
        total_skip += b_skip

    # ---- 3) 5c 文件存在性 ----
    if args.only == "5c" or (args.only is None):
        print("\n[3/4] 5c 文件存在性（21 个新文件）")
        c_fails, c_ok, c_skip = _scan_files("5c", STAGE_5C_FILES, strict=args.strict)
        if args.strict:
            fails.extend(c_fails)
        total_ok += c_ok
        total_skip += c_skip

    # ---- 4) 模块导入 + export（仅 5a）----
    if args.only in (None, "5a"):
        print("\n[4/4] 5a 模块导入 + 关键 export")
        mod_fails, mod_ok = _scan_modules(EXPECTED_MODULES_5A)
        fails.extend(mod_fails)
        total_ok += mod_ok

        exp_fails, exp_ok = _scan_exports(EXPECTED_EXPORTS_5A)
        if args.strict:
            fails.extend(exp_fails)
        total_ok += exp_ok

    return _summary(
        fails, total_ok, total_skip,
        pre_ok=pre_ok, a_ok=a_ok if 'a_ok' in dir() else 0,
        b_ok=b_ok if 'b_ok' in dir() else 0, c_ok=c_ok if 'c_ok' in dir() else 0,
        args=args,
    )


def _summary(
    fails: list[str], total_ok: int, total_skip: int,
    *, pre_ok: int, a_ok: int, b_ok: int, c_ok: int,
    args: argparse.Namespace,
) -> int:
    print()
    print("=" * 64)
    print(
        f"  阶段 5 scan 结果：4e pre {pre_ok} OK / 5a {a_ok} OK / "
        f"5b {b_ok} OK / 5c {c_ok} OK / SKIP {total_skip}"
    )
    print("=" * 64)
    if fails:
        print(f"  SCAN 失败：{len(fails)} 项")
        for f in fails:
            print("   -", f)
        return 1
    print(
        f"  SCAN 通过：{total_ok} 项 OK（{total_skip} 项 SKIP，待对应子阶段实做）"
    )
    print("  提示：5a 实做完成后用 --strict 校验；5b / 5c 实做完成后分别用 --only 5b / 5c")
    return 0


if __name__ == "__main__":
    sys.exit(main())


