"""仪表板数据。"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

logger = logging.getLogger(__name__)


class DashboardDataProvider:
    def __init__(self, alert_repo=None, sensor_manager=None) -> None:
        self._alerts = alert_repo
        self._sensors = sensor_manager

    async def project_overview(self, tenant_id: str, project_id: str) -> dict:
        all_alerts: list[dict] = []
        if self._alerts is not None:
            try:
                all_alerts = await asyncio.to_thread(
                    self._alerts.list_by_tenant, tenant_id, limit=1000)
            except Exception as e:
                logger.warning("project_overview 失败: %s", e)
        today = date.today().isoformat()
        active = sum(1 for a in all_alerts
                     if a.get("status") == "active"
                     and a.get("project_id") == project_id)
        today_count = sum(1 for a in all_alerts
                          if a.get("status") == "active"
                          and str(a.get("triggered_at", "")).startswith(today)
                          and a.get("project_id") == project_id)
        total_sensors = 0
        if self._sensors is not None:
            try:
                sensors = await self._sensors.list_active(tenant_id, project_id)
                total_sensors = len(sensors)
            except Exception as e:
                logger.warning("sensors 失败: %s", e)
        return {
            "active_alerts": active,
            "today_alerts": today_count,
            "total_sensors": total_sensors,
        }

    async def live_alerts(self, tenant_id: str, project_id: str,
                          limit: int = 50) -> list[dict]:
        if self._alerts is None:
            return []
        try:
            rows = await asyncio.to_thread(
                self._alerts.list_active, tenant_id, project_id)
        except Exception as e:
            logger.warning("live_alerts 失败: %s", e)
            return []
        return [
            {"id": r.get("id"), "level": r.get("level"),
             "title": r.get("title"), "source": r.get("source"),
             "triggered_at": str(r.get("triggered_at", ""))}
            for r in rows[:limit]
        ]
