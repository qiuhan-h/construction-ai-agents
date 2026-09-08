"""4c 阶段文件扫描：核对编排器 + services 所有交付文件存在且可导入。

退出码：
- 0  全部 OK
- 1  存在缺失/导入失败

运行：python tools/scan_stage4c.py
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# 期望文件清单（相对 ROOT）
EXPECTED_FILES: list[tuple[str, str]] = [
    # ---- 编排器 ----
    ("core/orchestrator/__init__.py", "package"),
    ("core/orchestrator/workflow_engine.py", "module"),
    ("core/orchestrator/task_scheduler.py", "module"),
    ("core/orchestrator/orchestrator.py", "module"),
    ("core/orchestrator/collaboration_manager.py", "module"),
    ("core/orchestrator/human_interaction.py", "module"),
    ("core/orchestrator/a2a_handlers.py", "module"),
    # ---- 服务层 ----
    ("services/__init__.py", "package"),
    ("services/celery_app.py", "module"),
    ("services/task_queue.py", "module"),
    ("services/service_registry.py", "module"),
    ("services/human_review_service.py", "module"),
    ("services/human_review_repository.py", "module"),
    ("services/document_service.py", "module"),
    ("services/notification_service.py", "module"),
    ("services/notification_channels/__init__.py", "package"),
    ("services/notification_channels/base_channel.py", "module"),
    ("services/notification_channels/dingtalk_channel.py", "module"),
    ("services/notification_channels/sms_channel.py", "module"),
    ("services/notification_channels/wecom_channel.py", "module"),
    ("services/data_ingestion.py", "module"),
    # ---- 测试 ----
    ("tests/orchestrator/test_orchestrator.py", "module"),
]

# 期望能 import 的模块（必须可加载）
EXPECTED_MODULES: list[str] = [
    "core.orchestrator",
    "core.orchestrator.workflow_engine",
    "core.orchestrator.task_scheduler",
    "core.orchestrator.orchestrator",
    "core.orchestrator.collaboration_manager",
    "core.orchestrator.human_interaction",
    "core.orchestrator.a2a_handlers",
    "services",
    "services.service_registry",
    "services.task_queue",
    "services.human_review_service",
    "services.human_review_repository",
    "services.document_service",
    "services.notification_service",
    "services.notification_channels",
    "services.notification_channels.base_channel",
    "services.notification_channels.dingtalk_channel",
    "services.notification_channels.sms_channel",
    "services.notification_channels.wecom_channel",
    "services.data_ingestion",
]

# 4c 必需 export 符号
EXPECTED_EXPORTS: list[tuple[str, str]] = [
    ("core.orchestrator", "Orchestrator"),
    ("core.orchestrator", "WorkflowEngine"),
    ("core.orchestrator", "TaskScheduler"),
    ("core.orchestrator", "CollaborationManager"),
    ("core.orchestrator", "HumanReviewServiceAdapter"),
    ("core.orchestrator", "TaskSpec"),
    ("core.orchestrator", "Workflow"),
    ("core.orchestrator.workflow_engine", "AgentManagerProtocol"),
    ("services", "ServiceRegistry"),
    ("services", "NotificationService"),
    ("services", "HumanReviewService"),
    ("services", "DocumentService"),
    ("services", "TaskQueue"),
    ("services", "DataIngestionService"),
]


def main() -> int:
    print("=" * 64)
    print("  4c Stage File Scan")
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
    print(f"  SCAN 通过：{len(EXPECTED_FILES)} 文件 / "
          f"{len(EXPECTED_MODULES)} 模块 / "
          f"{len(EXPECTED_EXPORTS)} export 全部就位")
    return 0


if __name__ == "__main__":
    sys.exit(main())


