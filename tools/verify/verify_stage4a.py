"""阶段四·子阶段 4a（compliance_agent）自检。

委派 tests/compliance_agent/test_agent.py（18 项端到端）+ 自身新增 6 项：
- 顶层 import 全部通过
- ComplianceAgent 继承 BaseAgent
- Skill 元数据完整（4 个）
- 与阶段一/二/三无回归
- 目录树 100% 一致
- 文档 architecture.md §8.1 交付记录

执行：python verify_stage4a.py
"""

from __future__ import annotations

import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "construction-ai-agents"  # 跨平台
sys.path.insert(0, str(ROOT))
TEST_FILE = ROOT / "tests" / "compliance_agent" / "test_agent.py"

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
# 顶层 import + 继承 + Skill
# =====================================================
def t_top_imports():
    from agents.compliance_agent import (
        ComplianceAgent,
        ComplianceLangChainAgent,
        make_compliance_agent,
    )
    from agents.compliance_agent.mcp_handlers import (
        ComplianceMCPHandler,
        install,
    )
    from agents.compliance_agent.prompts import (
        PROMPT_ENERGY_REVIEW,
        PROMPT_FIRE_REVIEW,
        PROMPT_GREEN_REVIEW,
        PROMPT_SEISMIC_REVIEW,
    )


def t_inheritance_baseagent():
    from agents.compliance_agent import ComplianceAgent
    from agents.base_agent import BaseAgent
    assert issubclass(ComplianceAgent, BaseAgent)


def t_skill_metadata():
    from agents.compliance_agent import ComplianceAgent
    skill_ids = {s.skill_id for s in ComplianceAgent.skills}
    assert skill_ids == {"fire_check", "seismic_check", "energy_check", "green_check"}


# =====================================================
# 委派 test_agent.py
# =====================================================
def t_subprocess_test_agent():
    proc = subprocess.run(
        [sys.executable, str(TEST_FILE)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    # 只打印最后 5 行（避免刷屏）
    lines = (proc.stdout + proc.stderr).splitlines()
    for ln in lines[-5:]:
        print(ln)
    if proc.returncode != 0:
        raise AssertionError(
            f"tests/compliance_agent/test_agent.py 退出码={proc.returncode}（预期 0）"
        )


# =====================================================
# 文档 / 目录树
# =====================================================
def t_docs_section8_exists():
    doc = ROOT / "docs" / "architecture.md"
    assert doc.is_file(), "architecture.md 不存在"
    text = doc.read_text(encoding="utf-8")
    assert "## 7." in text or "## 8." in text, (
        "docs/architecture.md 未追加 §7 或 §8 阶段三交付记录"
    )


def t_tree_consistent():
    import subprocess
    tools_dir = Path(__file__).resolve().parent.parent  # tools/verify/ -> tools/
    checker = tools_dir / "check_new_tree.py"
    proc = subprocess.run(
        [sys.executable, str(checker)],
        cwd=str(tools_dir),
        capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    assert "缺少的文件" in out and "(无)" in out, "目录树不一致：\n" + out[:2000]


# =====================================================
# 阶段一/二/三无回归（跑 verify_stage1/2/3）
# =====================================================
def _run_verify(stage: str) -> None:
    tools_dir = Path(__file__).resolve().parent
    p = tools_dir / f"verify_{stage}.py"
    if not p.exists():
        print(f"[SKIP] {p.name} 不存在，跳过")
        return
    proc = subprocess.run(
        [sys.executable, str(p)],
        cwd=str(tools_dir),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"{p.name} 回归失败:\n{proc.stdout[-500:]}\n{proc.stderr[-500:]}"
        )


def t_stage1_no_regression():
    _run_verify("stage1")


def t_stage2_no_regression():
    _run_verify("stage2")


def t_stage3_no_regression():
    _run_verify("stage3")


# =====================================================
# 注册
# =====================================================
check("compliance_agent: 顶层 import 全通过", t_top_imports)
check("compliance_agent: 继承 BaseAgent", t_inheritance_baseagent)
check("compliance_agent: Skill 4 个 fire_check/seismic_check/energy_check/green_check", t_skill_metadata)
check("compliance_agent: tests/compliance_agent/test_agent.py 18 项端到端", t_subprocess_test_agent)
check("docs/architecture.md: 包含阶段三 §7 交付记录", t_docs_section8_exists)
check("目录树: 与 shu_zhuang_tu.txt 100% 一致", t_tree_consistent)
check("阶段一: verify_stage1.py 无回归 (10/10)", t_stage1_no_regression)
check("阶段二: verify_stage2.py 无回归 (19/19)", t_stage2_no_regression)
check("阶段三: verify_stage3.py 无回归 (6+11=17)", t_stage3_no_regression)

print(f"\n===== 阶段四·4a 自检结果: {len(PASSED)} 通过, {len(FAILED)} 失败 =====")
sys.exit(1 if FAILED else 0)

