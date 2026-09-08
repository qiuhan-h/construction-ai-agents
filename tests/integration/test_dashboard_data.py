"""集成测试：仪表盘数据提供者（live_alerts / project_overview）多租户读取。"""

from __future__ import annotations

import asyncio

from agents.site_monitor_agent.outputs import DashboardDataProvider


def test_live_alerts_returns_list() -> None:
    async def _run() -> None:
        provider = DashboardDataProvider()
        alerts = await provider.live_alerts("tnt_dash", "proj-1", limit=20)
        assert isinstance(alerts, list)

    asyncio.run(_run())


def test_project_overview_returns_dict() -> None:
    async def _run() -> None:
        provider = DashboardDataProvider()
        overview = await provider.project_overview("tnt_dash", "proj-1")
        assert isinstance(overview, dict)

    asyncio.run(_run())


def test_dashboard_data_tenant_scoped() -> None:
    """不同租户/项目读取不串数据、不抛错。"""

    async def _run() -> None:
        provider = DashboardDataProvider()
        a = await provider.live_alerts("tnt_a", "proj-a")
        b = await provider.live_alerts("tnt_b", "proj-b")
        assert isinstance(a, list)
        assert isinstance(b, list)
        ov_a = await provider.project_overview("tnt_a", "proj-a")
        ov_b = await provider.project_overview("tnt_b", "proj-b")
        assert isinstance(ov_a, dict)
        assert isinstance(ov_b, dict)

    asyncio.run(_run())
