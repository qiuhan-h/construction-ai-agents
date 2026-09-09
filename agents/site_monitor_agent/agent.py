"""施工现场监控智能体主类（SiteMonitorAgent）。"""

from __future__ import annotations

import logging
from typing import Any

from agents.base_agent import BaseAgent, register_agent
from agents.site_monitor_agent.alert_engine import (
    AlertDispatcher,
    AlertRepository,
    AlertRule,
    RuleEngine,
    ThresholdManager,
    default_alert_rules,
)
from agents.site_monitor_agent.bim_integration import (
    BIMConnector,
    IFCParser,
    ProgressTracker,
)
from agents.site_monitor_agent.gis_monitoring import (
    Geofencing,
    RiskHeatmap,
    SpatialMonitor,
)
from agents.site_monitor_agent.iot_integration import (
    DataPipeline,
    MQTTConnector,
    SensorManager,
    TSDBWriter,
)
from agents.site_monitor_agent.outputs import (
    DailyReportGenerator,
    DashboardDataProvider,
    TrendAnalyzer,
)
from agents.site_monitor_agent.prompts import list_prompts as _list_prompts
from common.constants import AgentName
from common.exceptions import AgentParseError, AppException
from common.ids import message_id
from common.timeutils import to_iso, utc_now
from core.a2a.agent_card import Skill
from core.a2a.message import A2AMessage, MessagePart, Task

logger = logging.getLogger("agents.site_monitor_agent")


@register_agent
class SiteMonitorAgent(BaseAgent):
    """施工现场监控智能体（IoT/BIM/GIS + 告警 + 日报）。"""

    name = AgentName.SITE_MONITOR.value
    version = "0.1.0"
    description = "施工现场 IoT/BIM/GIS 监控与告警"
    skills = [
        Skill(skill_id="alert_judge", name="告警研判", description="基于规则引擎评估传感器数据是否触发告警"),
        Skill(skill_id="daily_report", name="日报生成", description="按项目/班组生成施工日报"),
        Skill(skill_id="bim_progress_sync", name="BIM 进度同步", description="从 BIM 模型拉取构件进度并比对计划"),
    ]

    def __init__(
        self,
        *,
        tenant_id: str,
        a2a_url: str = "http://localhost:9101",
        card_path: str = "/agent.json",
        metadata: dict[str, Any] | None = None,
        auto_register: bool = True,
        mqtt_client: MQTTConnector | None = None,
        bim_client: BIMConnector | None = None,
        rules: list[AlertRule] | None = None,
    ) -> None:
        super().__init__(
            tenant_id=tenant_id, a2a_url=a2a_url,
            card_path=card_path, metadata=metadata,
        )
        # IoT
        self._sensors = SensorManager()
        self._pipeline = DataPipeline()
        self._tsdb = TSDBWriter()
        self._mqtt = mqtt_client or MQTTConnector(tenant_id=tenant_id)
        # BIM
        self._bim = bim_client or BIMConnector(tenant_id=tenant_id)
        self._ifc = IFCParser()
        self._progress = ProgressTracker()
        # GIS
        self._spatial = SpatialMonitor()
        self._geofence = Geofencing()
        self._heatmap = RiskHeatmap()
        # 告警
        # H22 修补：默认注入施工现场阈值规则（塔吊/风速/扬尘/噪声/高温/基坑），
        # 规则引擎不再空跑；调用方可通过 rules= 传入自定义规则覆盖，
        # 运行时也可由配置中心 / ThresholdManager 经 add() 追加。
        self._rules = RuleEngine(
            rules if rules is not None else default_alert_rules()
        )
        self._thresholds = ThresholdManager()
        self._alert_repo = AlertRepository()
        self._dispatcher = AlertDispatcher(alert_repo=self._alert_repo)
        # Outputs
        self._daily = DailyReportGenerator(alert_repo=self._alert_repo)
        self._trend = TrendAnalyzer()
        self._dashboard = DashboardDataProvider(
            alert_repo=self._alert_repo, sensor_manager=self._sensors,
        )
        # 提示词注册
        _ = _list_prompts()
        if auto_register:
            self.register()

    async def handle(self, message: A2AMessage, task: Task) -> A2AMessage:
        try:
            payload = self._extract_payload(message)
            kind = payload.get("kind", "alert")
            if kind == "alert":
                artifacts = await self._run_alert(payload)
            elif kind == "daily_report":
                artifacts = await self._run_daily_report(payload)
            elif kind == "bim_sync":
                artifacts = await self._run_bim_sync(payload)
            else:
                raise AgentParseError(f"未知 kind: {kind}")
            return self._build_reply(artifacts, message, kind)
        except AgentParseError as e:
            logger.warning("解析失败: %s", e)
            return self._error_reply(message, str(e))
        except AppException as e:
            return self._error_reply(message, f"{e.code}: {e.message}")
        except Exception as e:  # noqa: BLE001
            logger.exception("site_monitor_agent 执行失败: %s", e)
            return self._error_reply(message, f"internal error: {e!s}")

    def _extract_payload(self, message: A2AMessage) -> dict[str, Any]:
        md = dict(message.metadata or {})
        for p in message.parts:
            if p.type == "data" and p.data:
                md.update(p.data)
        return md

    async def _run_alert(self, payload: dict[str, Any]) -> dict[str, Any]:
        from common.constants import AlertLevel
        from models.domain import Alert
        device_id = payload.get("device_id", "unknown")
        metric = payload.get("metric", "")
        try:
            value = float(payload.get("value", 0))
        except (TypeError, ValueError):
            value = 0.0
        severity = payload.get("severity", "info")
        level_map = {
            "info": AlertLevel.INFO,
            "warning": AlertLevel.WARNING,
            "critical": AlertLevel.CRITICAL,
        }
        level = level_map.get(severity, AlertLevel.WARNING)
        title = payload.get("title", f"{device_id} {metric}={value}")
        alert = Alert(
            tenant_id=self.tenant_id,
            project_id=payload.get("project_id", ""),
            source="site_monitor_agent",
            level=level,
            title=title,
            message=payload.get("message", title),
            metric={metric: value} if metric else {},
            dedup_key=payload.get("dedup_key", f"{device_id}:{metric}"),
        )
        new = await self._dispatcher.dispatch(alert)
        matched = self._rules.evaluate(metric, value) if metric else []
        return {
            "kind": "alert",
            "alert_id": alert.id,
            "level": level.value,
            "deduplicated": not new,
            "matched_rules": [r.id for r in matched],
        }

    async def _run_daily_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        from datetime import date as _date
        project_id = payload.get("project_id", "")
        date_str = payload.get("date", _date.today().isoformat())
        return await self._daily.generate(
            self.tenant_id, project_id, _date.fromisoformat(date_str),
        )

    async def _run_bim_sync(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan = payload.get("plan", [])
        actual = payload.get("actual", [])
        items = self._progress.compute(plan, actual)
        alerts = self._progress.deviation_alerts(
            items, tenant_id=self.tenant_id,
            project_id=payload.get("project_id", ""),
        )
        for a in alerts:
            await self._dispatcher.dispatch(a)
        return {
            "kind": "bim_sync",
            "items": [i.to_dict() for i in items],
            "alerts": [a.id for a in alerts],
        }

    def _build_reply(
        self, artifacts: dict[str, Any], src: A2AMessage, kind: str,
    ) -> A2AMessage:
        return A2AMessage(
            message_id=message_id(),
            tenant_id=src.tenant_id,
            role="agent",
            parts=[
                MessagePart(type="text", text=f"现场监控处理完成 kind={kind}"),
                MessagePart(type="data", data=artifacts),
            ],
            metadata={"kind": kind, "received_at": to_iso(utc_now())},
        )

    def _error_reply(self, src: A2AMessage, reason: str) -> A2AMessage:
        return A2AMessage(
            message_id=message_id(),
            tenant_id=src.tenant_id,
            role="agent",
            parts=[MessagePart(type="text", text=f"处理失败：{reason}")],
            metadata={"error": reason, "received_at": to_iso(utc_now())},
        )


def make_site_monitor_agent(
    tenant_id: str,
    *,
    a2a_url: str = "http://localhost:9101",
) -> SiteMonitorAgent:
    return SiteMonitorAgent(tenant_id=tenant_id, a2a_url=a2a_url)


__all__ = ["SiteMonitorAgent", "make_site_monitor_agent"]
