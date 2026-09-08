"""阶段四·子阶段 4b（site_monitor_agent）目标文件清单（28 个）。

按 stage4b_site_monitor_agent.txt §1 验收清单生成。

执行：python scan_stage4b.py
退出码：0 = 全部 OK；非 0 = 有空壳/缺失。
"""
import os
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[3] / "construction-ai-agents")
STAGE4B = [
    # 顶层 6 个
    "agents/site_monitor_agent/__init__.py",
    "agents/site_monitor_agent/agent.py",
    "agents/site_monitor_agent/a2a_handlers.py",
    "agents/site_monitor_agent/mcp_handlers.py",
    "agents/site_monitor_agent/langchain_agent.py",
    "agents/site_monitor_agent/prompts.py",
    # iot_integration/ 4 个
    "agents/site_monitor_agent/iot_integration/__init__.py",
    "agents/site_monitor_agent/iot_integration/mqtt_connector.py",
    "agents/site_monitor_agent/iot_integration/sensor_manager.py",
    "agents/site_monitor_agent/iot_integration/data_pipeline.py",
    "agents/site_monitor_agent/iot_integration/tsdb_writer.py",
    # bim_integration/ 3 个
    "agents/site_monitor_agent/bim_integration/__init__.py",
    "agents/site_monitor_agent/bim_integration/bim_connector.py",
    "agents/site_monitor_agent/bim_integration/ifc_parser.py",
    "agents/site_monitor_agent/bim_integration/progress_tracker.py",
    # gis_monitoring/ 3 个
    "agents/site_monitor_agent/gis_monitoring/__init__.py",
    "agents/site_monitor_agent/gis_monitoring/spatial_monitor.py",
    "agents/site_monitor_agent/gis_monitoring/geofencing.py",
    "agents/site_monitor_agent/gis_monitoring/risk_heatmap.py",
    # alert_engine/ 4 个
    "agents/site_monitor_agent/alert_engine/__init__.py",
    "agents/site_monitor_agent/alert_engine/rule_engine.py",
    "agents/site_monitor_agent/alert_engine/threshold_manager.py",
    "agents/site_monitor_agent/alert_engine/alert_dispatcher.py",
    "agents/site_monitor_agent/alert_engine/alert_repository.py",
    # outputs/ 4 个
    "agents/site_monitor_agent/outputs/__init__.py",
    "agents/site_monitor_agent/outputs/daily_report.py",
    "agents/site_monitor_agent/outputs/trend_analyzer.py",
    "agents/site_monitor_agent/outputs/dashboard_data.py",
    "agents/site_monitor_agent/outputs/report_signer_adapter.py",
    # tests/ 1 个
    "tests/site_monitor_agent/__init__.py",
    "tests/site_monitor_agent/test_agent.py",
]


def main() -> int:
    print(f"{'path':70} {'size':>8}  {'status'}")
    print("-" * 95)
    exists = empty = missing = 0
    missing_list: list[str] = []
    empty_list: list[str] = []
    for rel in STAGE4B:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            print(f"{rel:70} {'':>8}  MISSING")
            missing_list.append(rel)
            missing += 1
            continue
        size = os.path.getsize(p)
        if size == 0:
            print(f"{rel:70} {size:>8}  EMPTY")
            empty_list.append(rel)
            empty += 1
        else:
            print(f"{rel:70} {size:>8}  OK")
            exists += 1
    print("-" * 95)
    print(f"已实现: {exists}    0 字节占位: {empty}    不存在: {missing}    合计: {len(STAGE4B)}")
    if missing_list:
        print("\n缺失文件：")
        for m in missing_list:
            print(f"  - {m}")
    if empty_list:
        print("\n空壳文件：")
        for e in empty_list:
            print(f"  - {e}")
    return 0 if (missing == 0 and empty == 0) else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

