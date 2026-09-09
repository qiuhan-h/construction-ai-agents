"""工作流引擎：DAG 描述 + 模板渲染 + 拓扑排序 + 并行派发。

设计原则（O1-O2）：
- 编排器只通过 A2A 调度智能体（节点 = agent 调用），或 system 动作。
- 节点依赖 = depends_on 列表；执行时分层并行。
- params 支持 ${var} 占位符 → 渲染自 payload，缺失抛 ValueError。
- 节点重试由调用方决定（task_scheduler 负责指数退避）。

依赖：
- 阶段一 common.ids（task_id / message_id）
- 阶段二 core.a2a（A2AMessage/MessagePart/Task）
- 阶段二 core.events（不直接使用，但需要 EventBus 实例在 Orchestrator 层）
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from common.ids import message_id, new_id, task_id
from core.a2a.message import A2AMessage, MessagePart, Task

logger = logging.getLogger(__name__)


# =====================================================
# 节点类型
# =====================================================
NodeKind = Literal["agent", "system"]


@dataclass
class TaskSpec:
    """工作流单个节点。

    节点分两种：
    - agent: 通过 A2A 调 agent_manager.get(name).handle(msg)
    - system: 通过 ServiceRegistry.dispatch(system_action, params, tenant_id)

    params 字段支持 ${var} 占位符，渲染时从 payload 取。
    """

    node_id: str
    kind: NodeKind = "agent"
    agent_name: str = ""        # kind=agent 时必填
    method: str = ""            # kind=agent 时必填
    system_action: str = ""     # kind=system 时必填
    params: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    retry: int = 0
    timeout_seconds: int = 300

    def validate(self) -> None:
        if not self.node_id:
            raise ValueError("TaskSpec.node_id 不能为空")
        if self.kind == "agent":
            if not self.agent_name or not self.method:
                raise ValueError(
                    f"TaskSpec(node_id={self.node_id}) kind=agent 须设置 agent_name + method"
                )
        elif self.kind == "system":
            if not self.system_action:
                raise ValueError(
                    f"TaskSpec(node_id={self.node_id}) kind=system 须设置 system_action"
                )
        else:
            raise ValueError(f"未知节点类型: {self.kind}")


@dataclass
class Workflow:
    """工作流定义（DAG）。

    边由节点的 depends_on 字段推导；engine 不单独维护边。
    """

    name: str
    description: str
    nodes: list[TaskSpec] = field(default_factory=list)

    def validate(self) -> None:
        ids: set[str] = set()
        for n in self.nodes:
            n.validate()
            if n.node_id in ids:
                raise ValueError(f"Workflow 节点 ID 重复: {n.node_id}")
            ids.add(n.node_id)
        # 校验依赖引用存在
        for n in self.nodes:
            for d in n.depends_on:
                if d not in ids:
                    raise ValueError(
                        f"Workflow {self.name} 节点 {n.node_id} 依赖 {d} 不存在"
                    )


# =====================================================
# 协议（解耦：4c 不依赖 4d AgentManager 具体类）
# =====================================================
class AgentManagerProtocol(Protocol):
    """AgentManager 抽象接口（4c 用 Protocol，4d 提供实现）。"""

    async def get(self, name: str, tenant_id: str) -> Any:  # pragma: no cover - 协议
        ...

    def list_for_tenant(self, tenant_id: str) -> list[Any]:  # pragma: no cover - 协议
        ...

    async def shutdown(self) -> None:  # pragma: no cover - 协议
        ...


# =====================================================
# 工作流引擎
# =====================================================
class WorkflowEngine:
    """工作流注册表 + 执行器。"""

    def __init__(self) -> None:
        self._workflows: dict[str, Workflow] = {}
        self._runs: dict[str, dict] = {}  # run_id -> {workflow, status, results}
        self._register_default_workflows()

    # ---------- 注册表 ----------
    def register(self, wf: Workflow) -> None:
        wf.validate()
        if wf.name in self._workflows:
            logger.warning("覆盖已存在的工作流: %s", wf.name)
        self._workflows[wf.name] = wf

    def get(self, name: str) -> Workflow:
        if name not in self._workflows:
            raise KeyError(f"工作流未注册: {name}")
        return self._workflows[name]

    def list_names(self) -> list[str]:
        return sorted(self._workflows.keys())

    def list_workflows(self) -> list[Workflow]:
        return list(self._workflows.values())

    def get_run(self, run_id: str) -> dict | None:
        return self._runs.get(run_id)

    # ---------- 执行 ----------
    async def execute(
        self,
        wf: Workflow,
        payload: dict,
        tenant_id: str,
        agent_manager: AgentManagerProtocol,
    ) -> str:
        """执行工作流，返回 run_id。"""
        wf.validate()
        rendered: dict[str, dict] = {}
        for n in wf.nodes:
            try:
                rendered[n.node_id] = self._render_params(n.params, payload)
            except ValueError as e:
                raise ValueError(f"节点 {n.node_id} 参数渲染失败: {e}") from e

        layers = self._topo_layers(wf.nodes)
        run_id = new_id("run")
        self._runs[run_id] = {
            "workflow": wf.name,
            "tenant_id": tenant_id,
            "status": "running",
            "results": {},
            "errors": {},
        }

        # 按层并行派发
        try:
            for layer in layers:
                await asyncio.gather(
                    *[
                        self._dispatch(
                            n, rendered[n.node_id], tenant_id, agent_manager, run_id
                        )
                        for n in layer
                    ],
                    return_exceptions=False,
                )
            self._runs[run_id]["status"] = "success"
        except Exception as e:
            self._runs[run_id]["status"] = "failed"
            self._runs[run_id]["errors"]["__workflow__"] = repr(e)
            logger.exception("工作流执行失败 run_id=%s wf=%s", run_id, wf.name)
            raise
        return run_id

    # ---------- 渲染 ----------
    @staticmethod
    def _render_params(params: dict, payload: dict) -> dict:
        """${var} → payload[var]；缺失抛 ValueError。"""

        def _sub(v: Any) -> Any:
            if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                key = v[2:-1]
                if key not in payload:
                    raise ValueError(f"工作流模板变量未提供: {key}")
                return payload[key]
            if isinstance(v, dict):
                return {k: _sub(vv) for k, vv in v.items()}
            if isinstance(v, list):
                return [_sub(x) for x in v]
            return v

        return _sub(params)

    # ---------- 拓扑排序（Kahn 算法按层分组） ----------
    @staticmethod
    def _topo_layers(nodes: list[TaskSpec]) -> list[list[TaskSpec]]:
        """Kahn 算法按入度分层，返回可并行的层序列表。"""
        # 空工作流：返回空 layers（不算环）。原实现 any(v == 0 for v in
        # in_deg.values()) 对空 dict 返回 False → 误判为环。
        if not nodes:
            return []
        in_deg: dict[str, int] = {n.node_id: 0 for n in nodes}
        children: dict[str, list[str]] = {n.node_id: [] for n in nodes}
        for n in nodes:
            for d in n.depends_on:
                in_deg[n.node_id] += 1
                children[d].append(n.node_id)
        layers: list[list[TaskSpec]] = []
        by_id = {n.node_id: n for n in nodes}
        current = [nid for nid, d in in_deg.items() if d == 0]
        visited = 0
        while current:
            layers.append([by_id[nid] for nid in current])
            visited += len(current)
            next_layer: list[str] = []
            for nid in current:
                for ch in children[nid]:
                    in_deg[ch] -= 1
                    if in_deg[ch] == 0:
                        next_layer.append(ch)
            current = next_layer
        if visited != len(nodes):
            raise ValueError(f"工作流存在环，无法拓扑排序；节点数 {len(nodes)} 访问 {visited}")
        return layers

    # ---------- 派发 ----------
    async def _dispatch(
        self,
        node: TaskSpec,
        params: dict,
        tenant_id: str,
        agent_manager: AgentManagerProtocol,
        run_id: str,
    ) -> Any:
        if node.kind == "agent":
            return await self._dispatch_agent(
                node, params, tenant_id, agent_manager, run_id
            )
        if node.kind == "system":
            return await self._dispatch_system(params, tenant_id, run_id, node)
        raise ValueError(f"未知节点类型: {node.kind}")

    async def _dispatch_agent(
        self,
        node: TaskSpec,
        params: dict,
        tenant_id: str,
        agent_manager: AgentManagerProtocol,
        run_id: str,
    ) -> Any:
        agent = await agent_manager.get(node.agent_name, tenant_id)
        msg = A2AMessage(
            message_id=message_id(),
            tenant_id=tenant_id,
            role="orchestrator",
            parts=[MessagePart(type="data", data=params)],
            metadata={"workflow_run_id": run_id, "node_id": node.node_id},
        )
        task = Task(
            task_id=task_id(),
            agent_name=node.agent_name,
            tenant_id=tenant_id,
            message_id=msg.message_id,
        )
        try:
            result = await agent.handle(msg, task)
            self._runs[run_id]["results"][node.node_id] = {
                "kind": "agent",
                "agent_name": node.agent_name,
                "message_id": getattr(result, "message_id", None) or msg.message_id,
            }
            return result
        except Exception as e:
            self._runs[run_id]["errors"][node.node_id] = repr(e)
            raise

    async def _dispatch_system(
        self, params: dict, tenant_id: str, run_id: str, node: TaskSpec
    ) -> Any:
        # 通过 ServiceRegistry 调 system 动作
        from services.service_registry import ServiceRegistry

        result = ServiceRegistry.dispatch(node.system_action, params, tenant_id)
        # 兼容同步/异步 handler
        if asyncio.iscoroutine(result):
            result = await result
        self._runs[run_id]["results"][node.node_id] = {
            "kind": "system",
            "system_action": node.system_action,
            "result": result,
        }
        return result

    # ---------- 默认工作流 ----------
    def _register_default_workflows(self) -> None:
        # 现场告警 → 启动安全审查
        self.register(
            Workflow(
                name="monitor_alert_to_audit",
                description="现场告警 → 启动安全审查",
                nodes=[
                    TaskSpec(
                        node_id="notify",
                        kind="system",
                        system_action="services.notify",
                        params={
                            "channel": "dingtalk",
                            "title": "新审查任务",
                            "body": "${alert_id}",
                        },
                    ),
                    TaskSpec(
                        node_id="start_audit",
                        kind="agent",
                        agent_name="safety_audit_agent",
                        method="agent.send_message",
                        params={
                            "plan_id": "auto",
                            "hazards": ["${alert_id}"],
                        },
                        depends_on=["notify"],
                    ),
                ],
            )
        )
        # 审查未通过 → 合规复审
        self.register(
            Workflow(
                name="compliance_followup",
                description="审查未通过 → 合规复审",
                nodes=[
                    TaskSpec(
                        node_id="re_check",
                        kind="agent",
                        agent_name="compliance_agent",
                        method="agent.send_message",
                        params={"plan_id": "from_inspection"},
                    ),
                ],
            )
        )
        # 法规更新 → 记录 + 通知（无业务 Agent，纯 system）
        self.register(
            Workflow(
                name="regulation_record",
                description="法规更新事件记录",
                nodes=[
                    TaskSpec(
                        node_id="record",
                        kind="system",
                        system_action="services.notify",
                        params={
                            "channel": "wecom",
                            "title": "法规库更新",
                            "body": "${code} v${version}",
                        },
                    ),
                ],
            )
        )
