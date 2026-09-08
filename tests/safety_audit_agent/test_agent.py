"""阶段三（safety_audit_agent）端到端自检。

执行方式：
    cd construction-ai-agents
    python tests/safety_audit_agent/test_agent.py

覆盖方案解析 / 荷载组合 / LEC 风险评估 / 结构校核 / 向量库余弦相似度
（P0-4 回归）/ 案例检索 / 报告签章 / 整改建议 / 报告生成 / Agent 端到端
（A2A → 签章 → 事件）/ MCP 工具与提示词注册，共 11 项。

全部用例不依赖外部 LLM / DB / broker；向量库走内存，签章用测试密钥。
可直接 ``python`` 运行，也可被 pytest 收集（自检仅在 __main__ 下执行，
避免模块级 sys.exit 触发 INTERNALERROR）。
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path

# 文件路径：tests/safety_audit_agent/test_agent.py
# parents[0] = safety_audit_agent/  parents[1] = tests/
# parents[2] = construction-ai-agents/（项目根）
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []


def check(name: str, fn) -> None:
    try:
        fn()
        PASSED.append(name)
        print(f"[PASS] {name}")
    except Exception as e:  # noqa: BLE001
        FAILED.append((name, f"{type(e).__name__}: {e}"))
        print(f"[FAIL] {name}: {e}")
        traceback.print_exc()


# =====================================================
# a) PlanParser：方案文本解析（阶段/危险源/荷载）
# =====================================================
def t_plan_parser() -> None:
    from agents.safety_audit_agent.parsers import PlanParser

    text = (
        "工程名称：测试大厦工程\n"
        "施工阶段：主体结构\n"
        "本工程涉及高处坠落、坍塌、触电等危险源。\n"
        "恒荷载标准值 5.0 kPa，活荷载标准值 2.0 kPa。\n"
    )
    pf = PlanParser().parse_text(text)
    assert pf.stage, "stage 应被解析出"
    hazard_names = {h["name"] for h in pf.hazards}
    assert "高处坠落" in hazard_names, f"危险源解析失败: {hazard_names}"
    assert float(pf.loads.get("dead", 0)) == 5.0, "恒荷载解析失败"
    assert float(pf.loads.get("live", 0)) == 2.0, "活荷载解析失败"


# =====================================================
# b) LoadCalculator：GB 50009 荷载组合（async）
# =====================================================
def t_load_calculator() -> None:
    from agents.safety_audit_agent.calculators import (
        LoadCalculator,
        LoadInputs,
    )

    async def _run() -> None:
        calc = LoadCalculator()
        result = await calc.combined_load(
            LoadInputs(
                plan_id="plan-b",
                dead_load_kpa=5.0,
                live_load_kpa=2.0,
                wind_pressure_kpa=0.45,
                snow_pressure_kpa=0.30,
            )
        )
        assert result is not None
        # 组合值必须不小于任一单工况
        combo = result.combined_kpa if hasattr(result, "combined_kpa") else None
        if combo is None:
            # 兼容字段名差异：取数值型结果
            nums = [
                v for v in vars(result).values()
                if isinstance(v, (int, float))
            ]
            assert nums, f"LoadResult 无数值字段: {vars(result)}"
            combo = max(nums)
        assert combo >= 5.0, f"荷载组合异常: {combo}"

    asyncio.run(_run())


# =====================================================
# c) LECAssessor：高风险危险源 → CRITICAL + requires_alert
# =====================================================
def t_lec_assessor() -> None:
    from agents.safety_audit_agent.calculators import (
        HazardInput,
        LECAssessor,
        RiskLevel,
    )

    async def _run() -> None:
        risk = await LECAssessor().assess(
            [
                HazardInput(
                    name="高处坠落",
                    likelihood=6.0,
                    exposure=6.0,
                    consequence=40.0,
                )
            ]
        )
        assert risk.items, "风险项不应为空"
        assert risk.max_score >= 160, f"LEC 高分未识别: {risk.max_score}"
        assert risk.max_level == RiskLevel.CRITICAL
        assert risk.requires_alert is True

    asyncio.run(_run())


# =====================================================
# d) StructuralAnalyzer：梁构件结构校核
# =====================================================
def t_structural_analyzer() -> None:
    from agents.safety_audit_agent.calculators import (
        MemberType,
        StructuralAnalyzer,
        StructuralCheckInput,
    )

    async def _run() -> None:
        result = await StructuralAnalyzer().check(
            StructuralCheckInput(
                plan_id="plan-d",
                member_type=MemberType.BEAM,
                span_m=6.0,
                depth_m=0.6,
                load_kpa=10.0,
                concrete_grade="C30",
            )
        )
        assert result is not None

    asyncio.run(_run())


# =====================================================
# e) 向量库余弦相似度（P0-4 回归）：
#    不相关文档相似度不得为 1.0，相关文档应排在前面
# =====================================================
def t_vector_store_cosine() -> None:
    from agents.safety_audit_agent.knowledge_base import (
        InMemoryVectorStore,
        VectorRecord,
    )

    async def _run() -> None:
        store = InMemoryVectorStore()
        await store.upsert(
            [
                VectorRecord(
                    id="r1", tenant_id="tnt_e",
                    text="高处坠落 安全网 防护栏杆 脚手架",
                ),
                VectorRecord(
                    id="r2", tenant_id="tnt_e",
                    text="混凝土 配合比 坍落度 试块",
                ),
            ]
        )
        hits = await store.query(
            "tnt_e", "高处坠落 防护栏杆", top_k=2
        )
        assert hits, "应检索到结果"
        assert hits[0].id == "r1", (
            f"语义相关文档应排第一，实际: {[h.id for h in hits]}"
        )
        # 完全不相关的查询不应得到 1.0（P0-4 位置错配 bug 回归）
        unrelated = await store.query("tnt_e", "完全无关词汇xyz", top_k=2)
        for h in unrelated:
            assert h.score < 0.999, (
                f"不相关文档相似度异常为 ~1.0: {h.id}={h.score}"
            )

    asyncio.run(_run())


# =====================================================
# f) CaseRetriever：案例检索可调用并返回列表
# =====================================================
def t_case_retriever() -> None:
    from agents.safety_audit_agent.knowledge_base import CaseRetriever

    async def _run() -> None:
        retriever = CaseRetriever()
        cases = await retriever.search_cases(
            "tnt_f", "高处坠落 防护", top_k=3
        )
        assert isinstance(cases, list)

    asyncio.run(_run())


# =====================================================
# g) ReportSigner：签章/验签往返 + 篡改检测
# =====================================================
def t_report_signer() -> None:
    from agents.safety_audit_agent.outputs import (
        sign_report_content,
        verify_signature,
    )

    info = sign_report_content("# 报告内容", "tnt_g", secret="stage3-test")
    assert info.signature, "签名不应为空"
    assert verify_signature(
        "# 报告内容", "tnt_g", info.signed_at, info.signature,
        secret="stage3-test",
    )
    # 内容被篡改 → 验签失败
    assert not verify_signature(
        "# 被篡改内容", "tnt_g", info.signed_at, info.signature,
        secret="stage3-test",
    )
    # 跨租户 → 验签失败
    assert not verify_signature(
        "# 报告内容", "tnt_other", info.signed_at, info.signature,
        secret="stage3-test",
    )


# =====================================================
# h) RecommendationEngine：风险 → 整改建议
# =====================================================
def t_recommendation_engine() -> None:
    from agents.safety_audit_agent.calculators import (
        HazardInput,
        LECAssessor,
    )
    from agents.safety_audit_agent.outputs import RecommendationEngine

    async def _run() -> None:
        risk = await LECAssessor().assess(
            [HazardInput(name="坍塌", likelihood=3.0, exposure=6.0, consequence=15.0)]
        )
        rec_set = RecommendationEngine().from_risk(risk)
        assert rec_set is not None
        recs = getattr(rec_set, "recommendations", None) or getattr(
            rec_set, "items", []
        )
        assert isinstance(recs, list)

    asyncio.run(_run())


# =====================================================
# i) ReportGenerator：生成 ReportArtifacts（markdown + 结构化报告）
# =====================================================
def t_report_generator() -> None:
    from agents.safety_audit_agent.calculators import (
        HazardInput,
        LECAssessor,
    )
    from agents.safety_audit_agent.outputs import (
        RecommendationEngine,
        ReportGenerator,
    )
    from agents.safety_audit_agent.parsers import PlanParser
    from common.constants import AgentName

    plan_fields = PlanParser().parse_text(
        "工程名称：报告测试\n施工阶段：主体\n涉及高处坠落危险源。"
    )

    async def _run() -> None:
        risk = await LECAssessor().assess(
            [HazardInput(name="高处坠落", likelihood=6.0, exposure=6.0, consequence=40.0)]
        )
        recs = RecommendationEngine().from_risk(risk)
        gen = ReportGenerator(agent=AgentName.SAFETY_AUDIT)
        artifacts = gen.generate(
            tenant_id="tnt_i",
            project_id="proj-i",
            plan_id="plan-i",
            plan_fields=plan_fields,
            load_result=None,
            risk_assessment=risk,
            related_cases=[],
            related_regulations=[
                {"code": "JGJ80", "version": "2011", "name": "高处作业安全技术规范"}
            ],
            recommendations=recs,
        )
        assert artifacts.report is not None
        assert artifacts.markdown, "markdown 不应为空"
        assert artifacts.report.id

    asyncio.run(_run())


# =====================================================
# j) SafetyAuditAgent 端到端：A2AMessage → 签章报告 + inspection.completed 事件
# =====================================================
def t_agent_end_to_end() -> None:
    from agents.safety_audit_agent import SafetyAuditAgent
    from common.ids import message_id
    from core.a2a.message import A2AMessage, MessagePart, Task, TaskState
    from core.events import get_event_bus, reset_event_bus

    async def _run() -> None:
        reset_event_bus()
        bus = get_event_bus()
        seen: list[str] = []

        async def _capture(evt) -> None:
            seen.append(evt.topic)

        await bus.subscribe("inspection.completed", _capture)
        await bus.subscribe("report.signed", _capture)

        agent = SafetyAuditAgent(
            tenant_id="tnt_j", auto_register=False, signer_secret="stage3-test"
        )
        msg = A2AMessage(
            message_id=message_id(),
            tenant_id="tnt_j",
            role="user",
            parts=[
                MessagePart(
                    type="data",
                    data={
                        "project_id": "proj-j",
                        "plan_id": "plan-j",
                        "plan_text": (
                            "工程名称：端到端审核测试\n"
                            "施工阶段：主体结构\n"
                            "涉及高处坠落、坍塌危险源。\n"
                            "恒荷载 5.0 kPa，活荷载 2.0 kPa。"
                        ),
                        "hazards": [
                            {"name": "高处坠落", "likelihood": 6,
                             "exposure": 6, "consequence": 40}
                        ],
                    },
                )
            ],
        )
        reply = await agent.handle(
            msg,
            Task(
                task_id="task-j",
                agent_name="safety_audit_agent",
                tenant_id="tnt_j",
                state=TaskState.RUNNING,
            ),
        )
        assert reply is not None
        # 高风险 → 应有报告签名与审查完成事件
        assert "report.signed" in seen, f"未发布 report.signed: {seen}"
        assert "inspection.completed" in seen, (
            f"未发布 inspection.completed: {seen}"
        )

    asyncio.run(_run())


# =====================================================
# k) MCP 工具安装 + 提示词注册
# =====================================================
def t_mcp_and_prompts() -> None:
    from agents.safety_audit_agent.mcp_handlers import install
    from agents.safety_audit_agent.prompts import list_prompts
    from core.llm import get_prompt_manager

    handler = install()
    assert handler is not None
    names = list_prompts()
    pm = get_prompt_manager()
    registered = pm.list_names()
    for n in names:
        assert n in registered, f"提示词未注册: {n}"


_SELF_TEST_CASES = [
    ("a) PlanParser 方案文本解析", t_plan_parser),
    ("b) LoadCalculator GB50009 荷载组合", t_load_calculator),
    ("c) LECAssessor 高风险 → CRITICAL", t_lec_assessor),
    ("d) StructuralAnalyzer 梁校核", t_structural_analyzer),
    ("e) 向量库余弦相似度（P0-4 回归）", t_vector_store_cosine),
    ("f) CaseRetriever 案例检索", t_case_retriever),
    ("g) ReportSigner 签章/验签/防篡改", t_report_signer),
    ("h) RecommendationEngine 整改建议", t_recommendation_engine),
    ("i) ReportGenerator 报告生成", t_report_generator),
    ("j) SafetyAuditAgent 端到端 → 签章 + 事件", t_agent_end_to_end),
    ("k) MCP 工具安装 + 提示词注册", t_mcp_and_prompts),
]


def _run_self_test() -> int:
    """脚本式自检：逐条运行用例，返回退出码（0=全过，1=有失败）。"""
    PASSED.clear()
    FAILED.clear()
    for name, fn in _SELF_TEST_CASES:
        check(name, fn)

    print()
    print("=" * 70)
    print(f"阶段三端到端测试结果: {len(PASSED)} 通过, {len(FAILED)} 失败")
    if FAILED:
        print("失败用例：")
        for name, reason in FAILED:
            print(f"  - {name}: {reason}")
    print("=" * 70)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(_run_self_test())
