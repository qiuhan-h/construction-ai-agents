"""阶段六·子阶段 6a（业务算法升级 + 真实 LLM 注入）目标文件清单。

覆盖：
- 6a.1 GB 规则结构化（5 本国标 YAML + RuleChecker）
- 6a.2 GB50009 荷载组合 + GB50010 结构校核 + 标准知识库
- 6a.3 真实 LLM 注入（injector + 双语 prompts + chains LCEL 改造）

执行：python scan_stage6a.py
退出码：0 = 全部就位且非空；非 0 = 有缺失/空壳。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "construction-ai-agents"

# 6a 新增文件（必须存在且非空）
STAGE6A_NEW = [
    # 6a.1 规则结构化
    "agents/compliance_agent/regulation_engine/rules/__init__.py",
    "agents/compliance_agent/regulation_engine/rules/gb50016_fire.yml",
    "agents/compliance_agent/regulation_engine/rules/gb50011_seismic.yml",
    "agents/compliance_agent/regulation_engine/rules/gb50189_energy.yml",
    "agents/compliance_agent/regulation_engine/rules/gb50378_green.yml",
    "agents/compliance_agent/regulation_engine/rules/gb50009_load.yml",
    "agents/compliance_agent/regulation_engine/rule_checker.py",
    # 6a.2 国标算法叠加 + 知识库
    "agents/safety_audit_agent/calculators/load_calc_gb.py",
    "agents/safety_audit_agent/calculators/structural_check_gb.py",
    "agents/safety_audit_agent/knowledge_base/standard_kb.py",
    # 6a.3 LLM 注入
    "core/llm/injector.py",
    "core/llm/prompts/__init__.py",
    "core/llm/prompts/safety_prompt.py",
    "core/llm/prompts/compliance_prompt.py",
]

# 6a 改造文件（必须存在且非空；内容已由 verify_stage6a 运行期校验）
STAGE6A_MODIFIED = [
    "agents/compliance_agent/regulation_engine/mcp_loader.py",
    "core/langchain/chains/__init__.py",
    "core/langchain/chains/compliance_chain.py",
    "core/langchain/chains/monitoring_chain.py",
    "config/settings.py",
]


def main() -> int:
    print(f"{'path':78} {'size':>8}  status")
    print("-" * 96)
    missing = 0
    empty = 0
    ok = 0
    for rel in STAGE6A_NEW + STAGE6A_MODIFIED:
        p = ROOT / rel
        if not p.is_file():
            print(f"{rel:78} {'-':>8}  MISSING")
            missing += 1
            continue
        size = p.stat().st_size
        if size == 0:
            print(f"{rel:78} {size:>8}  EMPTY")
            empty += 1
        else:
            tag = "OK " if rel in STAGE6A_NEW else "OK*"
            print(f"{rel:78} {size:>8}  {tag}")
            ok += 1
    total = len(STAGE6A_NEW) + len(STAGE6A_MODIFIED)
    print("-" * 96)
    print(f"已实现: {ok}   0 字节占位: {empty}   不存在: {missing}   合计: {total}")
    print("(OK* = 6a 改造文件，运行期行为由 verify_stage6a.py 校验)")
    return 0 if missing == 0 and empty == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
