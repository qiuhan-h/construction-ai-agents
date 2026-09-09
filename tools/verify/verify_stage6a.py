"""阶段六·子阶段 6a 验收：业务算法升级 + 真实 LLM 注入。

验收项：
- [A] scan_stage6a 文件清单全部就位
- [B] 6a.1 GB 规则结构化：RuleChecker 加载 ≥50 条、5 本国标各 ≥10、不合规文档检出 Violation
- [C] 6a.2 GB50009 荷载组合 + GB50010 结构校核 + 标准知识库
- [D] 6a.3 LLM 注入：settings.llm_provider=mock、injector 四 provider 降级、chains 走 LCEL、
      chains/__init__.py 无 FakeListLLM、双语 prompts
- [E] 回归：verify_stage1/2/3 无回归（全套 1-5 见 Task 14）

执行：python verify_stage6a.py
退出码：0 = 全部通过；非 0 = 有失败项。
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "construction-ai-agents"
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PASSED = 0
FAILED = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
    else:
        FAILED += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


# =====================================================
# [A] 文件清单
# =====================================================
def check_scan() -> None:
    print("\n[A] 文件清单 scan_stage6a")
    r = subprocess.run(
        [sys.executable, str(TOOLS_DIR.parent / "scan" / "scan_stage6a.py")],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    check("scan_stage6a 退出码 0", r.returncode == 0,
          "全部文件就位非空" if r.returncode == 0 else "存在缺失/空壳，见 scan 输出")


# =====================================================
# [B] 6a.1 GB 规则结构化
# =====================================================
def check_rules() -> None:
    print("\n[B] 6a.1 GB 规则结构化")
    from agents.compliance_agent.regulation_engine.rule_checker import RuleChecker

    rc = RuleChecker()
    n = rc.rules_count()
    check("RuleChecker 加载规则 ≥50 条", n >= 50, f"实际 {n} 条")

    # 5 本国标各 ≥10 条（按 clause_id 前缀统计）
    prefixes = {
        "GB50016": "防火", "GB50011": "抗震", "GB50189": "节能",
        "GB50378": "绿建", "GB50009": "荷载",
    }
    counts = {p: 0 for p in prefixes}
    for r in rc._rules:
        for p in prefixes:
            if r.clause_id.startswith(p):
                counts[p] += 1
    for p, label in prefixes.items():
        check(f"{p}（{label}）≥10 条", counts[p] >= 10, f"{counts[p]} 条")

    # 不合规文档检出：耐火极限 2.0h < 3.0h 应触发 critical
    violations = rc.check({"fire_resistance_rating": 2.0})
    has_fire = any("GB50016" in v.clause_id for v in violations)
    check("不合规文档检出 GB50016 Violation", has_fire,
          f"共 {len(violations)} 条违规")
    if violations:
        v0 = violations[0]
        check("Violation 含 clause_id/severity/reason",
              bool(v0.clause_id and v0.severity and getattr(v0, "reason", "")),
              f"clause={v0.clause_id} severity={v0.severity}")


# =====================================================
# [C] 6a.2 GB50009 + GB50010 + 知识库
# =====================================================
def check_gb_algorithms() -> None:
    print("\n[C] 6a.2 GB 国标算法叠加")
    from agents.safety_audit_agent.calculators.load_calc_gb import GB50009LoadCalculator
    from agents.safety_audit_agent.calculators.load_calculator import LoadInputs
    from agents.safety_audit_agent.calculators.structural_check_gb import (
        ConcreteBeamInput,
        GB50010StructuralAnalyzer,
    )
    from agents.safety_audit_agent.knowledge_base.standard_kb import StandardKnowledgeBase

    # GB50009：D=3, L=2.5 → G+Q = 1.2*3 + 1.4*2.5 = 7.1
    gb = GB50009LoadCalculator()
    r = asyncio.run(gb.combine_loads(LoadInputs(
        plan_id="v6a", dead_load_kpa=3.0, live_load_kpa=2.5,
        wind_pressure_kpa=0.0, snow_pressure_kpa=0.0)))
    gq = r.basic_combos.get("G+Q", 0.0)
    check("GB50009 G+Q = 1.2D+1.4L = 7.1 kPa", abs(gq - 7.1) < 0.05, f"实际 {gq:.2f}")
    check("GB50009 含 6 种基本组合", len(r.basic_combos) >= 6,
          f"{len(r.basic_combos)} 种")
    check("GB50009 标准组合/准永久组合已算",
          r.standard_combo > 0 and r.quasi_permanent_combo > 0,
          f"标准={r.standard_combo:.2f} 准永久={r.quasi_permanent_combo:.2f}")

    # GB50010：3m 跨 250x500 C30/HRB400 线载 7.5kN/m → M≈8.44 kN·m，ξ_b≈0.518
    sa = GB50010StructuralAnalyzer()
    br = asyncio.run(sa.check_bearing_capacity(ConcreteBeamInput(
        plan_id="v6a", b_mm=250, h_mm=500, span_mm=3000,
        load_kN_per_m=7.5, concrete_grade="C30", steel_grade="HRB400")))
    check("GB50010 跨中弯矩 ≈8.44 kN·m", abs(br.moment_applied_kN_m - 8.44) < 0.1,
          f"实际 {br.moment_applied_kN_m:.2f}")
    check("GB50010 ξ_b ≈ 0.518（C30/HRB400）", abs(br.xi_b - 0.518) < 0.01,
          f"实际 {br.xi_b:.3f}")
    check("GB50010 适筋梁判定", br.is_ductile and br.is_sufficient,
          f"ductile={br.is_ductile} sufficient={br.is_sufficient}")

    # 知识库
    kb = StandardKnowledgeBase()
    check("StandardKnowledgeBase 加载 ≥50 条", kb.count() >= 50, f"{kb.count()} 条")
    hit = kb.by_clause("GB50016-2014-5.1.1-1")
    check("知识库 by_clause 精确检索", hit is not None and "耐火" in hit.title,
          hit.title if hit else "未命中")
    check("知识库关键词检索", len(kb.search("耐火")) >= 1,
          f"{len(kb.search('耐火'))} 条")


# =====================================================
# [D] 6a.3 LLM 注入
# =====================================================
def check_llm_injection() -> None:
    print("\n[D] 6a.3 真实 LLM 注入")
    from config import get_settings
    check("settings.llm_provider 默认 mock",
          get_settings().llm_provider == "mock",
          f"实际 {get_settings().llm_provider!r}")

    from core.llm.injector import get_injector, reset_injector
    reset_injector()
    inj = get_injector()

    llm_mock = inj.get_llm("mock")
    check("injector.get_llm('mock') 返回 FakeListLLM",
          "FakeListLLM" in type(llm_mock).__name__,
          type(llm_mock).__name__)

    # openai/anthropic/vllm 未配 key → 降级不抛错
    for prov in ("openai", "anthropic", "vllm"):
        reset_injector()
        try:
            llm = get_injector().get_llm(prov)
            ok = llm is not None
            check(f"injector.get_llm('{prov}') 降级不抛错", ok,
                  f"→ {type(llm).__name__}")
        except Exception as e:  # noqa: BLE001
            check(f"injector.get_llm('{prov}') 降级不抛错", False, f"抛错 {e}")

    # chains 三链走 LangChain 路径（backend 含 langchain）
    from core.langchain.chains import get_chain, reset_default_chains
    reset_default_chains()
    reset_injector()
    payload = {
        "document": "测试", "project_name": "项目", "artifact_kind": "方案",
        "check_kind": "消防", "regulation_codes": "GB50016", "content": "内容",
        "alert_payload": "告警", "history": "无",
    }
    for name in ("safety_audit", "compliance", "site_monitor"):
        ch = get_chain(name)
        out = asyncio.run(ch.run("tenant-v6a", payload))
        backend = out.get("backend", "")
        check(f"chain '{name}' 走 LangChain 路径", "langchain" in backend,
              f"backend={backend}")

    # chains/__init__.py 源码无 FakeListLLM 硬编码
    src = (ROOT / "core/langchain/chains/__init__.py").read_text(encoding="utf-8")
    check("chains/__init__.py 无 FakeListLLM 硬编码", "FakeListLLM" not in src)

    # 双语 prompts
    from core.llm.prompts import (
        build_compliance_messages,
        build_safety_messages,
    )
    zh = build_safety_messages("文档", lang="zh")
    en = build_safety_messages("doc", lang="en")
    check("safety prompt 中文 system", "安全审核专家" in zh[0].content)
    check("safety prompt English system", "safety audit expert" in en[0].content.lower())
    cz = build_compliance_messages("文档", regulations_context="GB50016", lang="zh")
    check("compliance prompt 注入法规上下文", "GB50016" in cz[1].content)


# =====================================================
# [E] 回归（核心地基 + 智能体；全套 1-5 见 Task 14）
# =====================================================
def check_regression() -> None:
    print("\n[E] 回归 verify_stage1/2/3")
    for script in ("verify_stage1.py", "verify_stage2.py", "verify_stage3.py"):
        r = subprocess.run(
            [sys.executable, str(TOOLS_DIR / script)],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        check(f"{script} 退出码 0", r.returncode == 0,
              "无回归" if r.returncode == 0 else "有失败，需排查")


def main() -> int:
    print("=" * 60)
    print("阶段六·6a 验收：业务算法升级 + 真实 LLM 注入")
    print("=" * 60)
    check_scan()
    check_rules()
    check_gb_algorithms()
    check_llm_injection()
    check_regression()
    print("\n" + "=" * 60)
    print(f"6a 自检结果: {PASSED} 通过, {FAILED} 失败")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
