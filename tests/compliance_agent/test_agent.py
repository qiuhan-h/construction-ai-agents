"""阶段四·4a（compliance_agent）端到端自检。

执行方式：
    cd construction-ai-agents
    python tests/compliance_agent/test_agent.py

覆盖法规索引 / 4 类检查器（消防/抗震/节能/绿建）/ 图纸 + 文档校验器 /
法规版本管理（含 H6 replace 事件参数回归）/ ComplianceAgent 端到端 /
payload 解析（H18/H19 回归）/ 多租户隔离 / MCP 工具 / 提示词 /
Skill 元数据，共 18 项。

全部用例不依赖外部 LLM / DB / broker。可直接 python 运行，也可被
pytest 收集（自检仅在 __main__ 下执行，避免模块级 sys.exit）。
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path

# 文件路径：tests/compliance_agent/test_agent.py
# parents[0] = compliance_agent/  parents[1] = tests/
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
# a) 法规库 bootstrap + 索引检索
# =====================================================
def t_regulation_index() -> None:
    from agents.compliance_agent.regulation_engine import RegulationLoader
    from agents.compliance_agent.regulation_engine.regulation_index import (
        RegulationIndex,
    )

    loader = RegulationLoader()
    loader.bootstrap()
    index = RegulationIndex(loader)
    fire = index.search("fire")
    assert isinstance(fire, list)
    assert len(index.list_all()) >= 0  # list_all 可调用


# =====================================================
# b-e) 4 类检查器均可调用并返回 list[Violation]（async）
# =====================================================
def _run_checker(checker_cls, design_type: str) -> None:
    from agents.compliance_agent.regulation_engine import RegulationLoader
    from agents.compliance_agent.regulation_engine.regulation_index import (
        RegulationIndex,
    )

    async def _run() -> None:
        loader = RegulationLoader()
        loader.bootstrap()
        regs = RegulationIndex(loader).search(design_type)
        checker = checker_cls()
        result = await checker.check(
            {"project_name": "测试项目", "building_height_m": 50},
            regs,
            tenant_id="tnt_checker",
        )
        assert isinstance(result, list)

    asyncio.run(_run())


def t_fire_checker() -> None:
    from agents.compliance_agent.checkers.fire_checker import FireChecker
    _run_checker(FireChecker, "fire")


def t_seismic_checker() -> None:
    from agents.compliance_agent.checkers.seismic_checker import SeismicChecker
    _run_checker(SeismicChecker, "seismic")


def t_energy_checker() -> None:
    from agents.compliance_agent.checkers.energy_checker import EnergyChecker
    _run_checker(EnergyChecker, "energy")


def t_green_checker() -> None:
    from agents.compliance_agent.checkers.green_checker import GreenChecker
    _run_checker(GreenChecker, "green")


# =====================================================
# f) 图纸校验器：title block 批量校验
# =====================================================
def t_drawing_validator() -> None:
    from agents.compliance_agent.validators.drawing_validator import (
        DrawingValidator,
    )

    async def _run() -> None:
        v = DrawingValidator()
        result = await v.validate_batch(
            [
                {"drawing_no": "JS-01", "title": "一层平面图", "scale": "1:100"},
                {"drawing_no": "JS-02", "title": "消防总图", "scale": "1:200"},
            ],
            tenant_id="tnt_f",
        )
        assert isinstance(result, list)

    asyncio.run(_run())


# =====================================================
# g) H19 回归：drawings 含非 dict 元素不得抛 AttributeError
# =====================================================
def t_drawing_validator_non_dict() -> None:
    from agents.compliance_agent.validators.drawing_validator import (
        DrawingValidator,
    )

    async def _run() -> None:
        v = DrawingValidator()
        # 混入非法元素（字符串 / None），应被跳过而非崩溃
        result = await v.validate_batch(
            [
                {"drawing_no": "JS-01", "title": "平面图"},
                "not-a-dict",
                None,
                12345,
            ],
            tenant_id="tnt_g",
        )
        assert isinstance(result, list)

    asyncio.run(_run())


# =====================================================
# h) 文档校验器
# =====================================================
def t_document_validator() -> None:
    from agents.compliance_agent.validators.document_validator import (
        DocumentValidator,
    )

    async def _run() -> None:
        v = DocumentValidator()
        result = await v.validate(
            {"doc_name": "施工组织设计", "doc_no": "SG-001"},
            tenant_id="tnt_h",
        )
        assert isinstance(result, list)

    asyncio.run(_run())


# =====================================================
# i) VersionManager.add_regulation → regulation.updated(added) 事件
# =====================================================
def t_version_manager_add() -> None:
    from agents.compliance_agent.regulation_engine import RegulationLoader
    from agents.compliance_agent.regulation_engine.version_manager import (
        VersionManager,
    )
    from core.events import get_event_bus, reset_event_bus

    async def _run() -> None:
        reset_event_bus()
        bus = get_event_bus()
        captured: list[dict] = []

        async def _cap(evt) -> None:
            captured.append({"topic": evt.topic, "payload": evt.payload})

        await bus.subscribe("regulation.updated", _cap)
        vm = VersionManager("tnt_i", RegulationLoader())
        await vm.add_regulation("GBTEST99", "2026", name="测试规范")
        assert captured, "add_regulation 应发布 regulation.updated 事件"
        assert captured[0]["payload"]["action"] == "added"
        assert captured[0]["payload"]["code"] == "GBTEST99"

    asyncio.run(_run())


# =====================================================
# j) H6 回归：replace 事件载荷必须是新 code + 新 version，
#    旧版本号放在 meta（不得出现旧 code + 新 version 错配）
# =====================================================
def t_version_manager_replace() -> None:
    from agents.compliance_agent.regulation_engine import RegulationLoader
    from agents.compliance_agent.regulation_engine.version_manager import (
        VersionManager,
    )
    from core.events import get_event_bus, reset_event_bus

    async def _run() -> None:
        reset_event_bus()
        bus = get_event_bus()
        captured: list[dict] = []

        async def _cap(evt) -> None:
            if evt.payload.get("action") == "replaced":
                captured.append(evt.payload)

        await bus.subscribe("regulation.updated", _cap)
        loader = RegulationLoader()
        loader.bootstrap()
        vm = VersionManager("tnt_j", loader)
        # 先注册旧版本，再替换
        await vm.add_regulation("GBTEST01", "2020", name="旧版")
        await vm.replace(
            ("GBTEST01", "2020"), ("GBTEST02", "2026")
        )
        assert captured, "replace 应发布 replaced 事件"
        p = captured[-1]
        assert p["code"] == "GBTEST02", (
            f"replace 事件 code 应为新版本 code，实际: {p['code']}"
        )
        assert p["version"] == "2026", (
            f"replace 事件 version 应为新版本，实际: {p['version']}"
        )
        assert p.get("old_version") == "2020"
        assert p.get("new_version") == "2026"

    asyncio.run(_run())


# =====================================================
# k) ComplianceAgent 端到端：A2AMessage → report_id + conclusion
# =====================================================
def t_agent_end_to_end() -> None:
    from agents.compliance_agent import ComplianceAgent
    from common.ids import message_id
    from core.a2a.message import A2AMessage, MessagePart, Task, TaskState
    from core.events import reset_event_bus

    async def _run() -> None:
        reset_event_bus()
        agent = ComplianceAgent(
            tenant_id="tnt_k", auto_register=False
        )
        msg = A2AMessage(
            message_id=message_id(),
            tenant_id="tnt_k",
            role="user",
            parts=[
                MessagePart(
                    type="data",
                    data={
                        "project_id": "proj-k",
                        "plan_id": "plan-k",
                        "design_doc": {
                            "project_name": "端到端合规项目",
                            "fire_rating": "二级",
                            "building_height_m": 50,
                        },
                    },
                )
            ],
        )
        reply = await agent.handle(
            msg,
            Task(
                task_id="task-k",
                agent_name="compliance_agent",
                tenant_id="tnt_k",
                state=TaskState.RUNNING,
            ),
        )
        assert reply is not None
        assert reply.metadata.get("report_id"), (
            f"reply 应带 report_id: {reply.metadata}"
        )
        assert "conclusion" in reply.metadata

    asyncio.run(_run())


# =====================================================
# l) 缺 project_id/plan_id → AgentParseError（不崩溃，走错误回复）
# =====================================================
def t_agent_missing_params() -> None:
    from agents.compliance_agent import ComplianceAgent
    from common.exceptions import AgentParseError
    from common.ids import message_id
    from core.a2a.message import A2AMessage, MessagePart

    agent = ComplianceAgent(tenant_id="tnt_l", auto_register=False)
    msg = A2AMessage(
        message_id=message_id(),
        tenant_id="tnt_l",
        role="user",
        parts=[MessagePart(type="data", data={"design_doc": {}})],
    )
    try:
        agent._extract_payload(msg)
        raised = False
    except AgentParseError:
        raised = True
    assert raised, "缺 project_id/plan_id 应抛 AgentParseError"


# =====================================================
# m) H18 回归：text parts + data.design_doc 同时存在时
#    design_doc 字段不得被丢弃
# =====================================================
def t_extract_payload_merges_text_and_data() -> None:
    from agents.compliance_agent import ComplianceAgent
    from common.ids import message_id
    from core.a2a.message import A2AMessage, MessagePart

    agent = ComplianceAgent(tenant_id="tnt_m", auto_register=False)
    msg = A2AMessage(
        message_id=message_id(),
        tenant_id="tnt_m",
        role="user",
        parts=[
            MessagePart(type="text", text="方案正文：消防设计说明"),
            MessagePart(
                type="data",
                data={
                    "project_id": "p",
                    "plan_id": "pl",
                    "design_doc": {"fire_rating": "一级", "building_height_m": 80},
                },
            ),
        ],
    )
    payload = agent._extract_payload(msg)
    dd = payload["design_doc"]
    assert "_text" in dd and "消防设计说明" in dd["_text"], (
        "文本部分应并入 design_doc._text"
    )
    assert dd.get("fire_rating") == "一级", (
        "data.design_doc 字段不得被文本部分覆盖丢失"
    )


# =====================================================
# n) H19 回归：drawings 为非 dict / 非法类型时规整不崩溃
# =====================================================
def t_extract_payload_drawings_normalized() -> None:
    from agents.compliance_agent import ComplianceAgent
    from common.ids import message_id
    from core.a2a.message import A2AMessage, MessagePart

    agent = ComplianceAgent(tenant_id="tnt_n", auto_register=False)
    msg = A2AMessage(
        message_id=message_id(),
        tenant_id="tnt_n",
        role="user",
        parts=[
            MessagePart(
                type="data",
                data={
                    "project_id": "p",
                    "plan_id": "pl",
                    "drawings": ["not-dict", {"drawing_no": "JS-01"}, 123],
                },
            )
        ],
    )
    # 不应抛 AttributeError
    payload = agent._extract_payload(msg)
    assert payload["drawings"] is not None


# =====================================================
# o) 多租户隔离：两个租户的报告 ID 独立
# =====================================================
def t_multi_tenant_isolation() -> None:
    from agents.compliance_agent import ComplianceAgent
    from common.ids import message_id
    from core.a2a.message import A2AMessage, MessagePart, Task, TaskState
    from core.events import reset_event_bus

    async def _one(tenant: str) -> str:
        agent = ComplianceAgent(tenant_id=tenant, auto_register=False)
        msg = A2AMessage(
            message_id=message_id(),
            tenant_id=tenant,
            role="user",
            parts=[
                MessagePart(
                    type="data",
                    data={
                        "project_id": f"proj-{tenant}",
                        "plan_id": "plan-o",
                        "design_doc": {"project_name": tenant},
                    },
                )
            ],
        )
        reply = await agent.handle(
            msg,
            Task(
                task_id=f"task-{tenant}",
                agent_name="compliance_agent",
                tenant_id=tenant,
                state=TaskState.RUNNING,
            ),
        )
        return str(reply.metadata.get("report_id", ""))

    async def _run() -> None:
        reset_event_bus()
        id_a = await _one("tnt_a")
        id_b = await _one("tnt_b")
        assert id_a and id_b, "两个租户都应生成报告"
        assert id_a != id_b, "不同租户报告 ID 不应相同"

    asyncio.run(_run())


# =====================================================
# p) MCP 工具安装
# =====================================================
def t_mcp_install() -> None:
    from agents.compliance_agent.mcp_handlers import install

    handler = install()
    assert handler is not None


# =====================================================
# q) 4 个合规提示词注册
# =====================================================
def t_prompts_registered() -> None:
    from agents.compliance_agent.prompts import list_prompts
    from core.llm import get_prompt_manager

    names = list_prompts()
    assert len(names) == 4, f"应注册 4 个提示词，实际: {names}"
    registered = get_prompt_manager().list_names()
    for n in names:
        assert n in registered, f"提示词未注册: {n}"


# =====================================================
# r) Skill 元数据：4 个 check skill
# =====================================================
def t_skill_metadata() -> None:
    from agents.compliance_agent import ComplianceAgent

    skill_ids = {s.skill_id for s in ComplianceAgent.skills}
    expected = {"fire_check", "seismic_check", "energy_check", "green_check"}
    assert expected <= skill_ids, (
        f"Skill 缺失: {expected - skill_ids}"
    )


_SELF_TEST_CASES = [
    ("a) 法规库 bootstrap + RegulationIndex 检索", t_regulation_index),
    ("b) FireChecker 消防检查器", t_fire_checker),
    ("c) SeismicChecker 抗震检查器", t_seismic_checker),
    ("d) EnergyChecker 节能检查器", t_energy_checker),
    ("e) GreenChecker 绿建检查器", t_green_checker),
    ("f) DrawingValidator 图纸批量校验", t_drawing_validator),
    ("g) H19 回归：非 dict 图纸不崩溃", t_drawing_validator_non_dict),
    ("h) DocumentValidator 文档校验", t_document_validator),
    ("i) VersionManager.add_regulation 事件", t_version_manager_add),
    ("j) H6 回归：replace 事件新 code/version 不错配", t_version_manager_replace),
    ("k) ComplianceAgent 端到端 → report_id", t_agent_end_to_end),
    ("l) 缺 project_id/plan_id → AgentParseError", t_agent_missing_params),
    ("m) H18 回归：text + data.design_doc 合并", t_extract_payload_merges_text_and_data),
    ("n) H19 回归：drawings 非法类型规整", t_extract_payload_drawings_normalized),
    ("o) 多租户报告 ID 隔离", t_multi_tenant_isolation),
    ("p) MCP 工具安装", t_mcp_install),
    ("q) 4 个合规提示词注册", t_prompts_registered),
    ("r) Skill 元数据 4 个 check", t_skill_metadata),
]


def _run_self_test() -> int:
    """脚本式自检：逐条运行用例，返回退出码（0=全过，1=有失败）。"""
    PASSED.clear()
    FAILED.clear()
    for name, fn in _SELF_TEST_CASES:
        check(name, fn)

    print()
    print("=" * 70)
    print(f"阶段四·4a 端到端测试结果: {len(PASSED)} 通过, {len(FAILED)} 失败")
    if FAILED:
        print("失败用例：")
        for name, reason in FAILED:
            print(f"  - {name}: {reason}")
    print("=" * 70)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(_run_self_test())
