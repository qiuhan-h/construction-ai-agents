"""阶段三目标文件清单（21 个）。"""
import os
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[3] / "construction-ai-agents")  # 跨平台
STAGE3 = [
    "agents/safety_audit_agent/__init__.py",
    "agents/safety_audit_agent/agent.py",
    "agents/safety_audit_agent/a2a_handlers.py",
    "agents/safety_audit_agent/mcp_handlers.py",
    "agents/safety_audit_agent/langchain_agent.py",
    "agents/safety_audit_agent/prompts.py",
    "agents/safety_audit_agent/knowledge_base/__init__.py",
    "agents/safety_audit_agent/knowledge_base/vector_store.py",
    "agents/safety_audit_agent/knowledge_base/standard_loader.py",
    "agents/safety_audit_agent/knowledge_base/case_retriever.py",
    "agents/safety_audit_agent/calculators/__init__.py",
    "agents/safety_audit_agent/calculators/load_calculator.py",
    "agents/safety_audit_agent/calculators/risk_assessor.py",
    "agents/safety_audit_agent/calculators/structural_analyzer.py",
    "agents/safety_audit_agent/parsers/__init__.py",
    "agents/safety_audit_agent/parsers/spec_parser.py",
    "agents/safety_audit_agent/parsers/plan_parser.py",
    "agents/safety_audit_agent/parsers/drawing_parser.py",
    "agents/safety_audit_agent/outputs/__init__.py",
    "agents/safety_audit_agent/outputs/report_signer.py",
    "agents/safety_audit_agent/outputs/recommendation_engine.py",
    "agents/safety_audit_agent/outputs/report_generator.py",
    "tests/safety_audit_agent/test_agent.py",
]

print(f"{'path':60} {'size':>8}  {'status'}")
print("-" * 90)
exists = empty = missing = 0
for rel in STAGE3:
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
print(f"已实现: {exists}    0 字节占位: {empty}    不存在: {missing}    合计: {len(STAGE3)}")

