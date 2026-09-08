"""4e 阶段文件扫描：核对 Streamlit Dashboard + 后端 dashboard 配套所有交付文件存在且可导入。

退出码：
- 0  全部 OK
- 1  存在缺失/导入失败

运行：python tools/scan_stage4e.py
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
    # ---- streamlit_app/ 前端包 ----
    ("streamlit_app/__init__.py", "package"),
    ("streamlit_app/app.py", "module"),
    ("streamlit_app/utils/__init__.py", "package"),
    ("streamlit_app/utils/api_client.py", "module"),
    ("streamlit_app/utils/websocket_client.py", "module"),
    ("streamlit_app/utils/state_manager.py", "module"),
    ("streamlit_app/components/__init__.py", "package"),
    ("streamlit_app/pages/__init__.py", "package"),
    ("streamlit_app/pages/04_dashboard.py", "module"),
    # 其他 5 个 page（4e 阶段未实做但入口存在）
    ("streamlit_app/pages/01_safety_audit.py", "module"),
    ("streamlit_app/pages/02_compliance.py", "module"),
    ("streamlit_app/pages/03_site_monitor.py", "module"),
    ("streamlit_app/pages/05_gis_viewer.py", "module"),
    ("streamlit_app/pages/06_agent_management.py", "module"),
    # ---- 4d 后端 dashboard 配套（编排器扩展）----
    # /stats 端点已并入 orchestrator_router；这里只校验 router 存在
    ("api/routers/orchestrator_router.py", "module"),
    # ---- tests/ 4e 测试 ----
    ("tests/integration/test_dashboard_data.py", "module"),
    # ---- 4e 验收工具 ----
    ("tools/scan/scan_stage4e.py", "module"),
    ("tools/verify/verify_stage4e.py", "module"),
]

# =====================================================
# 期望能 import 的模块（必须可加载）
# 注：streamlit_app.app 在 streamlit 缺失时也能 import（仅 init_state 优雅退化）
# =====================================================
EXPECTED_MODULES: list[str] = [
    "streamlit_app.utils.api_client",
    "streamlit_app.utils.websocket_client",
    "streamlit_app.utils.state_manager",
    "streamlit_app.utils",  # re-export 包
    "streamlit_app.pages",
    "streamlit_app.pages.04_dashboard",
    "tests.integration.test_dashboard_data",
]

# =====================================================
# 4e 必需 export 符号
# =====================================================
EXPECTED_EXPORTS: list[tuple[str, str]] = [
    # utils 包级
    ("streamlit_app.utils", "APIClient"),
    ("streamlit_app.utils", "APIError"),
    ("streamlit_app.utils", "api_client"),
    ("streamlit_app.utils", "EventStreamClient"),
    ("streamlit_app.utils", "build_ws_base_from_http"),
    ("streamlit_app.utils", "StateManager"),
    ("streamlit_app.utils", "get_state"),
    ("streamlit_app.utils", "init_state"),
    # pages 渲染
    ("streamlit_app.pages", "render"),
    ("streamlit_app.pages.04_dashboard", "render"),
    # 后端 dashboard 配套
    ("api.routers.orchestrator_router", "build_orchestrator_router"),
]


def main() -> int:
    print("=" * 64)
    print("  4e Stage File Scan")
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


