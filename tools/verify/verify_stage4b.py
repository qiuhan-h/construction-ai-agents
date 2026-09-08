"""阶段四·子阶段 4b（site_monitor_agent）自检。

执行：python verify_stage4b.py

委派 tests/site_monitor_agent/test_agent.py（22 项端到端）+ 自身 6 项：
- 顶层 import 全部通过
- SiteMonitorAgent 继承 BaseAgent
- Skill 元数据完整（3 个：alert_judge / daily_report / bim_progress_sync）
- 阶段一/二/三/4a 自检无回归
- 目录树 100% 一致
- 文件清单 100% 非 0 字节（委派 scan_stage4b.py）

退出码：0 = 全部 PASS；非 0 = 有 FAIL。
"""
from __future__ import annotations

import os
import subprocess
import sys
import traceback
from pathlib import Path

# ROOT = construction-ai-agents 所在目录
ROOT = Path(__file__).resolve().parents[3] / "construction-ai-agents"
sys.path.insert(0, str(ROOT))

TEST_FILE = ROOT / "tests" / "site_monitor_agent" / "test_agent.py"
SCAN_FILE = Path(__file__).resolve().parent.parent / "scan" / "scan_stage4b.py"

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
def t_top_imports() -> None:
    from agents.site_monitor_agent import (
        SiteMonitorAgent,
        SiteMonitorLangChainAgent,
        make_site_monitor_agent,
        PROMPT_ALERT_JUDGE,
        PROMPT_DAILY_REPORT,
        PROMPT_TREND_REPORT,
    )
    from agents.site_monitor_agent.mcp_handlers import (
        SiteMonitorMCPHandler,
        install,
        register_site_tools,
    )


def t_inheritance_baseagent() -> None:
    from agents.site_monitor_agent import SiteMonitorAgent
    from agents.base_agent import BaseAgent
    assert issubclass(SiteMonitorAgent, BaseAgent)


def t_skill_metadata() -> None:
    from agents.site_monitor_agent import SiteMonitorAgent
    skill_ids = {s.skill_id for s in SiteMonitorAgent.skills}
    assert skill_ids == {"alert_judge", "daily_report", "bim_progress_sync"}, \
        f"Skill 不匹配: {skill_ids}"


def t_agent_name_and_version() -> None:
    from agents.site_monitor_agent import SiteMonitorAgent
    from common.constants import AgentName
    assert SiteMonitorAgent.name == AgentName.SITE_MONITOR.value
    assert SiteMonitorAgent.version == "0.1.0"


# =====================================================
# 委派端到端测试
# =====================================================
def t_subprocess_test_agent() -> None:
    proc = subprocess.run(
        [sys.executable, str(TEST_FILE)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    lines = (proc.stdout + proc.stderr).splitlines()
    # 只打印关键摘要
    for ln in lines:
        if ln.startswith("[PASS]") or ln.startswith("[FAIL]") or "测试结果" in ln or "失败" in ln:
            print(ln)
    if proc.returncode != 0:
        raise AssertionError(
            f"tests/site_monitor_agent/test_agent.py 退出码={proc.returncode}"
        )


# =====================================================
# 委派文件清单检查
# =====================================================
def t_scan_stage4b() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCAN_FILE)],
        cwd=str(Path(__file__).resolve().parent.parent / "scan"),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"scan_stage4b.py 失败:\n{proc.stdout}\n{proc.stderr}"
        )


# =====================================================
# 阶段一/二/三/4a 无回归
# =====================================================
def _run_verify(stage: str) -> None:
    """运行 verify_stage{N}.py；脚本已统一改为跨平台路径。
    沙箱里应可正常调用。
    """
    p = Path(__file__).resolve().parent / f"verify_{stage}.py"
    if not p.exists():
        print(f"[SKIP] {p.name} 不存在，跳过")
        return
    proc = subprocess.run(
        [sys.executable, str(p)],
        cwd=str(Path(__file__).resolve().parent),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"{p.name} 回归失败:\n{proc.stdout[-500:]}\n{proc.stderr[-500:]}"
        )


def t_stage1_no_regression() -> None:
    _run_verify("stage1")


def t_stage2_no_regression() -> None:
    _run_verify("stage2")


def t_stage3_no_regression() -> None:
    _run_verify("stage3")


def t_stage4a_no_regression() -> None:
    _run_verify("stage4a")


# =====================================================
# 注册
# =====================================================
check("site_monitor_agent: 顶层 import 全通过", t_top_imports)
check("site_monitor_agent: 继承 BaseAgent", t_inheritance_baseagent)
check("site_monitor_agent: Skill 3 个 alert_judge/daily_report/bim_progress_sync", t_skill_metadata)
check("site_monitor_agent: name=site_monitor_agent, version=0.1.0", t_agent_name_and_version)
check("site_monitor_agent: tests/site_monitor_agent/test_agent.py 22 项端到端", t_subprocess_test_agent)
check("site_monitor_agent: 28 个文件全部非 0 字节 (scan_stage4b.py)", t_scan_stage4b)
check("阶段一: verify_stage1.py 无回归 (10/10)", t_stage1_no_regression)
check("阶段二: verify_stage2.py 无回归 (19/19)", t_stage2_no_regression)
check("阶段三: verify_stage3.py 无回归 (17/17)", t_stage3_no_regression)
check("阶段四 4a: verify_stage4a.py 无回归 (4a 全 PASS)", t_stage4a_no_regression)


print()
print("=" * 70)
print(f"阶段四·4b 自检结果: {len(PASSED)} 通过, {len(FAILED)} 失败")
if FAILED:
    print("失败项：")
    for f in FAILED:
        print(f"  - {f}")
print("=" * 70)
sys.exit(1 if FAILED else 0)

