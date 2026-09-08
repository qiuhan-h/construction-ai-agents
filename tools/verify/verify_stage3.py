"""阶段三（safety_audit_agent 全流程）自检。

覆盖：
- calculators: load_calculator / risk_assessor / structural_analyzer
- knowledge_base: vector_store / case_retriever / standard_loader
- parsers: spec_parser / plan_parser / drawing_parser
- outputs: report_signer / recommendation_engine / report_generator
- prompts: 3 个模板注册
- agent: SafetyAuditAgent 端到端（A2A + 事件 + 签章）
- mcp_handlers: safety.search_case / safety.match_regulation 注册
- a2a_handlers: 路由构造
- langchain_agent: 适配层（langchain 缺失时降级）

执行：python verify_stage3.py
"""

from __future__ import annotations

import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "construction-ai-agents"  # 跨平台
sys.path.insert(0, str(ROOT))  # 让顶层 verify_stage3.py 能 import agents.*
TEST_FILE = ROOT / "tests" / "safety_audit_agent" / "test_agent.py"

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, fn) -> None:
    try:
        fn()
        PASSED.append(name)
        print(f"[PASS] {name}")
    except Exception:
        FAILED.append(name)
        print(f"[FAIL] {name}")
        traceback.print_exc()


# =====================================================
# 全部委派给 tests/safety_audit_agent/test_agent.py
# =====================================================
def t_subprocess_test_agent():
    """直接执行 tests/safety_audit_agent/test_agent.py 并透传结果。"""
    proc = subprocess.run(
        [sys.executable, str(TEST_FILE)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    out = proc.stdout + proc.stderr
    print(out)
    if proc.returncode != 0:
        raise AssertionError(
            f"test_agent.py 退出码={proc.returncode}（预期 0）"
        )


# =====================================================
# 自身新增断言（不重复 test_agent.py 已覆盖的项）
# =====================================================
def t_agents_module_importable():
    from agents.safety_audit_agent import (
        SafetyAuditAgent,
        make_safety_audit_agent,
        SafetyAuditLangChainAgent,
        PROMPT_PLAN_REVIEW,
        PROMPT_DRAWING_REVIEW,
        PROMPT_REPORT_DRAFT,
    )
    from agents.safety_audit_agent.mcp_handlers import (
        SafetyAuditMCPHandler,
        install,
    )
    from agents.safety_audit_agent.a2a_handlers import (
        register_safety_audit_agent,
        build_a2a_router,
    )
    from agents.safety_audit_agent.calculators import (
        LoadCalculator, LECAssessor, StructuralAnalyzer,
        LoadInputs, HazardInput, MemberType,
        RiskAssessment, RiskLevel,
    )
    from agents.safety_audit_agent.knowledge_base import (
        InMemoryVectorStore, CaseRetriever, StandardLoader,
        VectorRecord, VectorHit,
    )
    from agents.safety_audit_agent.parsers import (
        PlanParser, SpecParser, DrawingParser,
        PlanFields, SpecChunk, DrawingMetadata,
    )
    from agents.safety_audit_agent.outputs import (
        ReportSigner, ReportGenerator, RecommendationEngine,
        SignInfo, Recommendation, RecommendationSet, Severity,
        ReportArtifacts,
        sign_report_content, verify_signature,
    )

    # 公开类至少可实例化（除 LangChainAgent 必须有 base_agent）
    calc = LoadCalculator()
    risk = LECAssessor()
    struct = StructuralAnalyzer()
    assert calc is not None
    assert risk is not None
    assert struct is not None


def t_sign_report_content_module_helper():
    """模块级便捷函数签名正确。"""
    from agents.safety_audit_agent.outputs import (
        sign_report_content, verify_signature, default_signer,
    )
    signer = default_signer(secret="stage3-test")
    info = sign_report_content("# 内容", "tnt_x", secret="stage3-test")
    assert verify_signature(
        "# 内容", "tnt_x", info.signed_at, info.signature,
        secret="stage3-test",
    ) is True


def t_inheritance_to_base_agent():
    """SafetyAuditAgent 必须继承自 agents.base_agent.BaseAgent。"""
    from agents.safety_audit_agent import SafetyAuditAgent
    from agents.base_agent import BaseAgent

    assert issubclass(SafetyAuditAgent, BaseAgent)


def t_skill_metadata_defined():
    """skills 元数据完整（用于 Agent Card 暴露）。"""
    from agents.safety_audit_agent import SafetyAuditAgent

    skill_ids = {s.skill_id for s in SafetyAuditAgent.skills}
    assert "plan_review" in skill_ids
    assert "load_combination" in skill_ids


def t_idempotent_register():
    """重复 import prompts 不会抛错（已用 overwrite=True 兜底）。"""
    import importlib

    import agents.safety_audit_agent.prompts as p1
    importlib.reload(p1)
    import agents.safety_audit_agent.prompts as p2
    importlib.reload(p2)
    # 模板仍在
    from core.llm import get_prompt_manager
    pm = get_prompt_manager()
    for name in (
        "safety.plan_review",
        "safety.drawing_review",
        "safety.report_draft",
    ):
        assert name in pm.list_names()


# =====================================================
# 注册
# =====================================================
check("agents.safety_audit_agent: 顶层 import 全通过", t_agents_module_importable)
check("agents.safety_audit_agent: 继承 BaseAgent", t_inheritance_to_base_agent)
check("SafetyAuditAgent.skills: plan_review / load_combination", t_skill_metadata_defined)
check("outputs: sign/verify 模块级函数", t_sign_report_content_module_helper)
check("prompts: 重复 import 幂等", t_idempotent_register)
check("tests/safety_audit_agent/test_agent.py: 11 项端到端", t_subprocess_test_agent)

print(f"\n===== 阶段三自检结果: {len(PASSED)} 通过, {len(FAILED)} 失败 =====")
sys.exit(1 if FAILED else 0)

