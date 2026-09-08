"""阶段四·子阶段 4a（compliance_agent）目标文件清单。"""
import os
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[3] / "construction-ai-agents")  # 跨平台
STAGE4A = [
    "agents/compliance_agent/__init__.py",
    "agents/compliance_agent/agent.py",
    "agents/compliance_agent/a2a_handlers.py",
    "agents/compliance_agent/mcp_handlers.py",
    "agents/compliance_agent/langchain_agent.py",
    "agents/compliance_agent/prompts.py",
    "agents/compliance_agent/regulation_engine/__init__.py",
    "agents/compliance_agent/regulation_engine/regulation_index.py",
    "agents/compliance_agent/regulation_engine/version_manager.py",
    "agents/compliance_agent/regulation_engine/mcp_loader.py",
    "agents/compliance_agent/regulation_engine/rule_parser.py",
    "agents/compliance_agent/checkers/__init__.py",
    "agents/compliance_agent/checkers/fire_checker.py",
    "agents/compliance_agent/checkers/seismic_checker.py",
    "agents/compliance_agent/checkers/energy_checker.py",
    "agents/compliance_agent/checkers/green_checker.py",
    "agents/compliance_agent/validators/__init__.py",
    "agents/compliance_agent/validators/drawing_validator.py",
    "agents/compliance_agent/validators/document_validator.py",
    "agents/compliance_agent/outputs/__init__.py",
    "agents/compliance_agent/outputs/compliance_report.py",
    "agents/compliance_agent/outputs/violation_tracker.py",
    "agents/compliance_agent/outputs/violation_repository.py",
    "tests/compliance_agent/test_agent.py",
]

print(f"{'path':60} {'size':>8}  {'status'}")
print("-" * 90)
exists = empty = missing = 0
for rel in STAGE4A:
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        print(f"{rel:60} {'':>8}  MISSING")
        missing += 1
        continue
    size = os.path.getsize(p)
    if size == 0:
        print(f"{rel:60} {size:>8}  EMPTY")
        empty += 1
    else:
        print(f"{rel:60} {size:>8}  OK")
        exists += 1
print("-" * 90)
print(f"已实现: {exists}    0 字节占位: {empty}    不存在: {missing}    合计: {len(STAGE4A)}")

