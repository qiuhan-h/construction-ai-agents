"""日报生成。"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from agents.safety_audit_agent.outputs.report_signer import sign_report_content
from common.constants import AgentName, AuditConclusion, ReportStatus
from common.ids import inspection_id as _inspection_id_factory
from common.ids import report_id
from common.timeutils import utc_now
from models.domain import Inspection, ReviewReport

logger = logging.getLogger(__name__)


class DailyReportGenerator:
    def __init__(self, alert_repo: Any | None = None,
                 progress_tracker: Any | None = None) -> None:
        self._alerts = alert_repo
        self._progress = progress_tracker

    async def generate(self, tenant_id: str, project_id: str,
                      report_date: date) -> dict:
        alerts: list[dict] = []
        if self._alerts is not None:
            try:
                rows = await asyncio.to_thread(
                    self._alerts.list_active, tenant_id, project_id)
                alerts = rows
            except Exception as e:
                logger.warning("拉取活跃告警失败: %s", e)
        today = report_date.isoformat()
        active_count = len(alerts)
        md_lines = [
            f"# 现场日报 {today}（{project_id}）", "",
            f"- 活跃告警数：{active_count}",
            "- 设备状态：见 dashboard_data.project_overview",
            "- 进度偏差：见 ProgressTracker.compute", "",
            "## 告警明细",
        ]
        for a in alerts[:30]:
            _level = a.get("level", "info")
            _title = a.get("title", "")
            _source = a.get("source", "")
            md_lines.append(
                f"- [{_level}] {_title}（{_source}）")
        md = "\n".join(md_lines)
        insp = Inspection(
            id=_inspection_id_factory(),
            tenant_id=tenant_id, project_id=project_id,
            plan_id=f"daily-{today}",
            agent=AgentName.SITE_MONITOR,
            summary=md[:200], started_at=utc_now(),
        )
        rpt = ReviewReport(
            id=report_id(),
            tenant_id=tenant_id, project_id=project_id,
            inspection_id=insp.id,
            agent=AgentName.SITE_MONITOR,
            title=f"现场日报 {today}",
            content=md,
            conclusion=AuditConclusion.PASS,
            regulation_versions={},
            status=ReportStatus.DRAFT,
        )
        try:
            info = sign_report_content(md, tenant_id)
            rpt.signature = info.signature
        except Exception as e:
            logger.warning("日报签章失败: %s", e)
        return {
            "inspection": insp, "report": rpt,
            "markdown": md, "active_alerts": active_count,
        }
