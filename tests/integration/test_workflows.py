"""集成测试：WorkflowEngine 工作流注册 / 拓扑分层执行 / 参数渲染 / 失败传播。"""

from __future__ import annotations

import asyncio

import pytest

from core.a2a.message import A2AMessage
from core.orchestrator import WorkflowEngine
from core.orchestrator.workflow_engine import TaskSpec, Workflow


class _MockAgent:
    def __init__(self, name: str, fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.calls: list[dict] = []

    async def handle(self, message: A2AMessage, task) -> A2AMessage:
        data = message.parts[0].data if message.parts else {}
        self.calls.append(data)
        if self.fail:
            raise RuntimeError(f"{self.name} 处理失败")
        return A2AMessage(
            message_id=message.message_id + "-done",
            tenant_id=message.tenant_id,
            role="agent",
            parts=[],
            metadata={"agent": self.name},
        )


class _MockAM:
    def __init__(self, agents: dict[str, _MockAgent]) -> None:
        self._agents = agents

    async def get(self, name: str, tenant_id: str) -> _MockAgent:
        return self._agents[name]


def _two_node_workflow() -> Workflow:
    return Workflow(
        name="wf_chain",
        description="A → B 链式工作流",
        nodes=[
            TaskSpec(
                node_id="step_a",
                kind="agent",
                agent_name="safety_audit_agent",
                method="handle",
                params={"project_id": "${project_id}"},
            ),
            TaskSpec(
                node_id="step_b",
                kind="agent",
                agent_name="compliance_agent",
                method="handle",
                params={"project_id": "${project_id}"},
                depends_on=["step_a"],
            ),
        ],
    )


def test_workflow_register_and_list() -> None:
    engine = WorkflowEngine()
    wf = _two_node_workflow()
    engine.register(wf)
    assert "wf_chain" in engine.list_names()


def test_workflow_execute_chain_runs_both_agents() -> None:
    async def _run() -> None:
        engine = WorkflowEngine()
        safety = _MockAgent("safety_audit_agent")
        compliance = _MockAgent("compliance_agent")
        am = _MockAM({"safety_audit_agent": safety, "compliance_agent": compliance})
        run_id = await engine.execute(
            _two_node_workflow(),
            {"project_id": "P-100"},
            "tnt_wf",
            am,  # type: ignore[arg-type]
        )
        run = engine.get_run(run_id)
        assert run["status"] == "success", f"工作流应成功: {run.get('errors')}"
        assert len(safety.calls) == 1
        assert len(compliance.calls) == 1
        # 参数渲染：${project_id} 被 payload 替换
        assert safety.calls[0]["project_id"] == "P-100"
        assert compliance.calls[0]["project_id"] == "P-100"
        # 依赖顺序：B 收到的消息在 A 之后（拓扑分层保证）
        assert "step_a" in run["results"]
        assert "step_b" in run["results"]

    asyncio.run(_run())


def test_workflow_failure_marks_run_failed() -> None:
    async def _run() -> None:
        engine = WorkflowEngine()
        safety = _MockAgent("safety_audit_agent", fail=True)
        compliance = _MockAgent("compliance_agent")
        am = _MockAM({"safety_audit_agent": safety, "compliance_agent": compliance})
        with pytest.raises(RuntimeError):
            await engine.execute(
                _two_node_workflow(),
                {"project_id": "P-101"},
                "tnt_wf",
                am,  # type: ignore[arg-type]
            )
        # 失败节点下游不应执行
        assert compliance.calls == []

    asyncio.run(_run())


def test_workflow_parallel_nodes_all_run() -> None:
    async def _run() -> None:
        engine = WorkflowEngine()
        safety = _MockAgent("safety_audit_agent")
        compliance = _MockAgent("compliance_agent")
        am = _MockAM({"safety_audit_agent": safety, "compliance_agent": compliance})
        wf = Workflow(
            name="wf_parallel",
            description="两个无依赖节点并行",
            nodes=[
                TaskSpec(node_id="p1", kind="agent", agent_name="safety_audit_agent", method="handle"),
                TaskSpec(node_id="p2", kind="agent", agent_name="compliance_agent", method="handle"),
            ],
        )
        run_id = await engine.execute(wf, {}, "tnt_wf", am)  # type: ignore[arg-type]
        run = engine.get_run(run_id)
        assert run["status"] == "success"
        assert len(safety.calls) == 1
        assert len(compliance.calls) == 1

    asyncio.run(_run())
