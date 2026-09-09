"""施工现场监控智能体的 MCP 处理器：桥接 + 业务工具。"""

from __future__ import annotations

import logging

from agents.site_monitor_agent.alert_engine import AlertRepository
from agents.site_monitor_agent.gis_monitoring import Geofencing, RiskHeatmap
from agents.site_monitor_agent.outputs import (
    DailyReportGenerator,
)
from core.mcp.server import (
    MCPService,
    get_mcp_service,
)

logger = logging.getLogger("agents.site_monitor_agent.mcp_handlers")


class SiteMonitorMCPHandler:
    def __init__(self, service: MCPService | None = None) -> None:
        self._service = service or get_mcp_service()

    async def list_active_alerts(self, tenant_id, project_id=None, limit=50):
        repo = AlertRepository()
        rows = repo.list_active(tenant_id, project_id=project_id)
        return {"tool": "site.list_active_alerts", "tenant_id": tenant_id,
                "count": len(rows[:limit]), "items": rows[:limit]}

    async def compute_heatmap(self, project_id, hours=24):
        return {"tool": "site.compute_heatmap", "project_id": project_id,
                "geojson": RiskHeatmap().generate(project_id, hours=hours)}

    async def daily_report(self, tenant_id, project_id, date):
        from datetime import date as _date
        gen = DailyReportGenerator(alert_repo=AlertRepository())
        art = await gen.generate(tenant_id, project_id, _date.fromisoformat(date))
        return {"tool": "site.daily_report", "tenant_id": tenant_id,
                "report_id": art["report"].id,
                "active_alerts": art["active_alerts"],
                "markdown_length": len(art["markdown"])}

    async def get_sensor_status(self, device_id):
        return {"tool": "site.get_sensor_status", "device_id": device_id, "status": "active"}

    async def check_geofence(self, fence_id, lon, lat, device_id=""):
        from models.domain import GeoPoint
        return {"tool": "site.check_geofence", "fence_id": fence_id,
                "violation": Geofencing().check_violation(
                    fence_id, GeoPoint(latitude=lat, longitude=lon), device_id)}


def register_site_tools(service: MCPService | None = None) -> None:
    svc = service or get_mcp_service()
    handler = SiteMonitorMCPHandler(svc)

    @svc.register_tool(name="site.list_active_alerts",
        description="按 tenant + project 查活跃告警",
        input_schema={"type": "object",
            "properties": {"tenant_id": {"type": "string"},
                           "project_id": {"type": "string"},
                           "limit": {"type": "integer", "default": 50}},
            "required": ["tenant_id"]})
    async def _list(tenant_id, project_id=None, limit=50):
        return await handler.list_active_alerts(tenant_id, project_id, limit)

    @svc.register_tool(name="site.compute_heatmap",
        description="生成项目风险热力图（GeoJSON）",
        input_schema={"type": "object",
            "properties": {"project_id": {"type": "string"},
                           "hours": {"type": "integer", "default": 24}},
            "required": ["project_id"]})
    async def _heat(project_id, hours=24):
        return await handler.compute_heatmap(project_id, hours)

    @svc.register_tool(name="site.daily_report",
        description="生成现场日报",
        input_schema={"type": "object",
            "properties": {"tenant_id": {"type": "string"},
                           "project_id": {"type": "string"},
                           "date": {"type": "string"}},
            "required": ["tenant_id", "project_id", "date"]})
    async def _daily(tenant_id, project_id, date):
        return await handler.daily_report(tenant_id, project_id, date)

    @svc.register_tool(name="site.get_sensor_status",
        description="查设备状态",
        input_schema={"type": "object",
            "properties": {"device_id": {"type": "string"}},
            "required": ["device_id"]})
    async def _status(device_id):
        return await handler.get_sensor_status(device_id)

    @svc.register_tool(name="site.check_geofence",
        description="检查点位是否越界",
        input_schema={"type": "object",
            "properties": {"fence_id": {"type": "string"},
                           "lon": {"type": "number"},
                           "lat": {"type": "number"},
                           "device_id": {"type": "string"}},
            "required": ["fence_id", "lon", "lat"]})
    async def _fence(fence_id, lon, lat, device_id=""):
        return await handler.check_geofence(fence_id, lon, lat, device_id)


def install() -> SiteMonitorMCPHandler:
    register_site_tools()
    return SiteMonitorMCPHandler()


__all__ = ["SiteMonitorMCPHandler", "register_site_tools", "install"]
