"""4d 阶段文件扫描：核对 FastAPI 业务接入 + 脚本 + 测试所有交付文件存在且可导入。

退出码：
- 0  全部 OK
- 1  存在缺失/导入失败

运行：python tools/scan_stage4d.py
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# =====================================================
# 期望文件清单（相对 ROOT）
# =====================================================
EXPECTED_FILES: list[tuple[str, str]] = [
    # ---- api/ 主应用 + 依赖 ----
    ("api/__init__.py", "package"),
    ("api/main.py", "module"),
    ("api/dependencies/__init__.py", "package"),
    ("api/dependencies/auth.py", "module"),
    ("api/dependencies/agent_manager.py", "module"),
    ("api/dependencies/orchestrator_provider.py", "module"),
    # ---- api/ 路由 ----
    ("api/routers/__init__.py", "package"),
    ("api/routers/agents_router.py", "module"),
    ("api/routers/tasks_router.py", "module"),
    ("api/routers/reports_router.py", "module"),
    ("api/routers/health_router.py", "module"),
    ("api/routers/websocket_router.py", "module"),
    ("api/routers/orchestrator_router.py", "module"),
    # ---- scripts/ 运维脚本 ----
    ("scripts/init_agents.py", "module"),
    ("scripts/load_regulations.py", "module"),
    ("scripts/load_gis_data.py", "module"),
    ("scripts/setup_vector_db.py", "module"),
    ("scripts/seed_test_data.py", "module"),
    ("scripts/start_worker.py", "module"),
    # ---- tests/ 测试 ----
    ("tests/conftest.py", "module"),
    ("tests/unit/test_a2a_protocol.py", "module"),
    ("tests/unit/test_mcp_handlers.py", "module"),
    ("tests/unit/test_gis_engine.py", "module"),
    ("tests/integration/test_workflows.py", "module"),
    ("tests/integration/test_agent_collaboration.py", "module"),
    ("tests/e2e/test_full_pipeline.py", "module"),
]

# =====================================================
# 期望能 import 的模块（必须可加载）
# =====================================================
EXPECTED_MODULES: list[str] = [
    # api 主入口 + 依赖
    "api.main",
    "api.dependencies.auth",
    "api.dependencies.agent_manager",
    "api.dependencies.orchestrator_provider",
    # 路由
    "api.routers.agents_router",
    "api.routers.tasks_router",
    "api.routers.reports_router",
    "api.routers.health_router",
    "api.routers.websocket_router",
    "api.routers.orchestrator_router",
    # 脚本（直接 import 会触发 __main__ 守卫；改为文件存在性检查，
    #     真正执行在 verify_stage4d.py 中以子进程方式）
]

# =====================================================
# 4d 必需 export 符号
# =====================================================
EXPECTED_EXPORTS: list[tuple[str, str]] = [
    # api
    ("api.main", "create_app"),
    ("api.main", "app"),
    # auth
    ("api.dependencies.auth", "AuthContext"),
    ("api.dependencies.auth", "get_auth_context"),
    # agent manager
    ("api.dependencies.agent_manager", "AgentManager"),
    ("api.dependencies.agent_manager", "init_agent_manager"),
    ("api.dependencies.agent_manager", "get_agent_manager"),
    # orchestrator provider
    ("api.dependencies.orchestrator_provider", "init_orchestrator"),
    ("api.dependencies.orchestrator_provider", "get_orchestrator"),
    # 路由
    ("api.routers.agents_router", "build_agents_router"),
    ("api.routers.tasks_router", "build_tasks_router"),
    ("api.routers.reports_router", "build_reports_router"),
    ("api.routers.health_router", "build_health_router"),
    ("api.routers.websocket_router", "build_websocket_router"),
    ("api.routers.orchestrator_router", "build_orchestrator_router"),
]


def main() -> int:
    print("=" * 64)
    print("  4d Stage File Scan")
    print("=" * 64)

    fails: list[str] = []

    # ---- 1) 文件存在性 ----
    print("\n[1/3] 期望文件存在性")
    for rel, kind in EXPECTED_FILES:
        p = ROOT / rel
        if not p.exists():
            fails.append(f"FILE_MISSING {rel}")
            print(f"  [FAIL] {rel} ({kind})")
        elif p.stat().st_size == 0:
            fails.append(f"FILE_EMPTY {rel}")
            print(f"  [FAIL] {rel} (empty)")
        else:
            print(f"  [ OK ] {rel}")

    # ---- 2) 模块可导入 ----
    print("\n[2/3] 模块可导入")
    for m in EXPECTED_MODULES:
        try:
            importlib.import_module(m)
            print(f"  [ OK ] {m}")
        except Exception as e:  # noqa: BLE001
            fails.append(f"IMPORT_FAIL {m}: {e}")
            print(f"  [FAIL] {m}: {type(e).__name__}: {e}")

    # ---- 3) 关键 export 存在 ----
    print("\n[3/3] 关键 export 存在")
    for mod_name, symbol in EXPECTED_EXPORTS:
        try:
            mod = importlib.import_module(mod_name)
            ok = hasattr(mod, symbol)
            if ok:
                print(f"  [ OK ] {mod_name}.{symbol}")
            else:
                fails.append(f"EXPORT_MISSING {mod_name}.{symbol}")
                print(f"  [FAIL] {mod_name}.{symbol} (无此属性)")
        except Exception as e:  # noqa: BLE001
            fails.append(f"IMPORT_FAIL {mod_name}: {e}")
            print(f"  [FAIL] {mod_name}: {type(e).__name__}: {e}")

    print()
    print("=" * 64)
    if fails:
        print(f"  SCAN 失败：{len(fails)} 项")
        for f in fails:
            print("   -", f)
        return 1
    print(
        f"  SCAN 通过：{len(EXPECTED_FILES)} 文件 / "
        f"{len(EXPECTED_MODULES)} 模块 / "
        f"{len(EXPECTED_EXPORTS)} export 全部就位"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())


