"""主编排器：订阅事件 → 触发工作流 → 调度任务 → 协调多智能体协作。

设计原则（O1, O2, O5, O6, O7）：
- 编排器只通过 A2A 调度智能体；
- 订阅 4 类业务事件（alert/inspection/violation/regulation），按规则触发工作流；
- 所有触发带 tenant_id，硬隔离；
- 失败显式化（记录到 collaboration_manager 时间线 + 返回 run_id）。
"""

from __future__ import annotations

import logging
from typing import Any

from common.ids import new_id
from common.timeutils import utc_now
from core.events import (
    TOPIC_ALERT_TRIGGERED,
    TOPIC_INSPECTION_COMPLETED,
    TOPIC_REGULATION_UPDATED,
    TOPIC_VIOLATION_CREATED,
    Event,
    get_event_bus,
)
from core.orchestrator.collaboration_manager import CollaborationManager
from core.orchestrator.workflow_engine import (
    AgentManagerProtocol,
    Workflow,
    WorkflowEngine,
)

logger = logging.getLogger(__name__)


class Orchestrator:
    """主编排器。"""

    def __init__(
        self,
        *,
        task_queue: Any,
        agent_manager: AgentManagerProtocol,
        workflow_engine: WorkflowEngine,
        collaboration: CollaborationManager | None = None,
        event_bus: Any | None = None,
    ) -> None:
        self._queue = task_queue
        self._agents = agent_manager
        self._workflow = workflow_engine
        self._collab = collaboration or CollaborationManager()
        self._bus = event_bus or get_event_bus()
        self._running = False
        self._subscribed_handlers: list[tuple[str, Any]] = []

    # ---------- 生命周期 ----------
    async def start(self) -> None:
        """订阅所有 TOPIC_* 事件 → 映射到工作流。"""
        subs = [
            (TOPIC_ALERT_TRIGGERED, self._on_alert),
            (TOPIC_INSPECTION_COMPLETED, self._on_inspection),
            (TOPIC_VIOLATION_CREATED, self._on_violation),
            (TOPIC_REGULATION_UPDATED, self._on_regulation),
        ]
        for topic, handler in subs:
            await self._bus.subscribe(topic, handler)
            self._subscribed_handlers.append((topic, handler))
        self._running = True
        logger.info("Orchestrator 已启动，订阅 4 类事件")

    async def stop(self) -> None:
        self._running = False
        for topic, handler in self._subscribed_handlers:
            try:
                await self._bus.unsubscribe(topic, handler)
            except Exception as e:  # noqa: BLE001
                logger.warning("退订 %s 失败: %s", topic, e)
        self._subscribed_handlers.clear()
        logger.info("Orchestrator 已停止")

    # ---------- 手动触发 ----------
    async def trigger_workflow(
        self, name: str, payload: dict, tenant_id: str
    ) -> str:
        """手动触发工作流，返回 workflow_run_id。

        4e 起：手动路径也写入协作时间线，dashboard 才能看到操作记录。
        失败不影响主流程，仅 warning 日志。
        """
        wf = self._workflow.get(name)
        run_id = await self._workflow.execute(wf, payload, tenant_id, self._agents)
        try:
            self._collab.record_interaction(
                from_agent="manual",
                to_agent="orchestrator",
                task_id=str(payload.get("alert_id") or payload.get("inspection_id") or run_id),
                status="manual_trigger",
                tenant_id=tenant_id,
                metadata={
                    "run_id": run_id,
                    "workflow": name,
                    "payload_keys": sorted(payload.keys()),
                },
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("手动触发时间线写入失败（不影响主流程）: %s", e)
        return run_id

    def list_workflows(self) -> list[dict]:
        return [
            {
                "name": w.name,
                "description": w.description,
                "nodes": [n.node_id for n in w.nodes],
            }
            for w in self._workflow.list_workflows()
        ]

    def get_run(self, run_id: str) -> dict | None:
        return self._workflow.get_run(run_id)

    def stats(self, tenant_id: str | None = None) -> dict:
        """编排器运行统计（4e dashboard 使用）。

        返回：
          - workflows: int 已注册工作流数
          - runs: int 内存中的运行总数（按 tenant 过滤时仅统计该租户）
          - today_triggers: int 今日（按 ts 日期前缀匹配）触发次数
          - failed: int 状态为 failed 的运行数
          - last_run_id: str 最近一次运行 id（按 _runs dict 插入序）
          - last_run_status: str 最近一次运行状态
        """
        wf_count = len(self._workflow.list_workflows())
        today_prefix = utc_now().date().isoformat()  # YYYY-MM-DD
        runs_total = 0
        failed_n = 0
        last_run_id: str | None = None
        for rid, info in self._workflow._runs.items():  # noqa: SLF001
            if tenant_id and info.get("tenant_id") != tenant_id:
                continue
            runs_total += 1
            if info.get("status") == "failed":
                failed_n += 1
            last_run_id = rid
        # 协作时间线里 today triggers
        collab_total = 0
        collab_today = 0
        for entries in self._collab._store.values():  # noqa: SLF001
            for e in entries:
                if tenant_id and e.tenant_id != tenant_id:
                    continue
                collab_total += 1
                if e.ts.startswith(today_prefix):
                    collab_today += 1
        last_status = (
            self._workflow._runs[last_run_id]["status"]  # noqa: SLF001
            if last_run_id
            else None
        )
        return {
            "workflows": wf_count,
            "runs": runs_total,
            "today_triggers": collab_today,
            "collaboration_entries": collab_total,
            "failed": failed_n,
            "last_run_id": last_run_id,
            "last_run_status": last_status,
            "is_running": self._running,
            "as_of": utc_now().isoformat(),
        }

    # ---------- 事件回调 ----------
    async def _on_alert(self, event: Event) -> None:
        """告警事件 → critical 时启动安全审查工作流。"""
        payload = event.payload or {}
        if payload.get("level") != "critical":
            return
        run_id = await self.trigger_workflow(
            "monitor_alert_to_audit",
            {
                "alert_id": payload.get("alert_id") or event.event_id,
                "tenant_id": event.tenant_id,
                "source": event.source,
            },
            event.tenant_id,
        )
        self._collab.record_interaction(
            from_agent=event.source,
            to_agent="orchestrator",
            task_id=str(payload.get("alert_id") or event.event_id),
            status="triggered",
            tenant_id=event.tenant_id,
            metadata={"run_id": run_id, "workflow": "monitor_alert_to_audit"},
        )

    async def _on_inspection(self, event: Event) -> None:
        """审查完成事件 → 不通过/有条件通过时启动合规复审。"""
        payload = event.payload or {}
        if payload.get("conclusion") not in ("fail", "conditional_pass"):
            return
        run_id = await self.trigger_workflow(
            "compliance_followup",
            {
                "inspection_id": payload.get("inspection_id"),
                "report_id": payload.get("report_id"),
                "tenant_id": event.tenant_id,
            },
            event.tenant_id,
        )
        self._collab.record_interaction(
            from_agent=event.source,
            to_agent="orchestrator",
            task_id=str(payload.get("inspection_id") or event.event_id),
            status="triggered",
            tenant_id=event.tenant_id,
            metadata={"run_id": run_id, "workflow": "compliance_followup"},
        )

    async def _on_violation(self, event: Event) -> None:
        """违规新建 → 记录 + 通知（4c 通过 system 动作发通知，4d API 路由也可触发）。"""
        payload = event.payload or {}
        self._collab.record_interaction(
            from_agent=event.source,
            to_agent="orchestrator",
            task_id=str(payload.get("violation_id") or event.event_id),
            status="received",
            tenant_id=event.tenant_id,
            metadata={"event_id": event.event_id, "ts": utc_now().isoformat()},
        )
        # 异步触发通知（fire-and-forget）
        try:
            from services.service_registry import ServiceRegistry
            await ServiceRegistry.dispatch(
                "services.notify",
                {
                    "channel": "dingtalk",
                    "title": "新违规项",
                    "body": f"{payload.get('violation_id', event.event_id)}",
                    "tenant_id": event.tenant_id,
                    "severity": "warning",
                    "event_type": "violation.created",
                },
                event.tenant_id,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("违规通知失败（不影响记录）: %s", e)

    async def _on_regulation(self, event: Event) -> None:
        """法规更新 → 记录 + 通知。"""
        payload = event.payload or {}
        self._collab.record_interaction(
            from_agent=event.source,
            to_agent="orchestrator",
            task_id=str(payload.get("code") or event.event_id),
            status="regulation_updated",
            tenant_id=event.tenant_id,
            metadata={
                "action": payload.get("action"),
                "version": payload.get("version"),
            },
        )
        logger.info(
            "regulation.updated: action=%s code=%s version=%s",
            payload.get("action"),
            payload.get("code"),
            payload.get("version"),
        )
        # 4c+ 可触发批量重审：monitor → safety → compliance 链式回放
        # 4c 首版仅记录 + 通知
        try:
            from services.service_registry import ServiceRegistry
            await ServiceRegistry.dispatch(
                "services.notify",
                {
                    "channel": "wecom",
                    "title": "法规库更新",
                    "body": f"{payload.get('code', '')} v{payload.get('version', '')}",
                    "tenant_id": event.tenant_id,
                    "severity": "info",
                    "event_type": "regulation.updated",
                },
                event.tenant_id,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("法规更新通知失败: %s", e)

    # ---------- 状态查询 ----------
    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def workflow_engine(self) -> WorkflowEngine:
        return self._workflow

    @property
    def collaboration(self) -> CollaborationManager:
        return self._collab
