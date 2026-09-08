"""报告输出子包：日报 / 趋势 / 仪表板 / 签章。"""

from agents.site_monitor_agent.outputs.daily_report import (
    DailyReportGenerator,
)
from agents.site_monitor_agent.outputs.dashboard_data import (
    DashboardDataProvider,
)
from agents.site_monitor_agent.outputs.report_signer_adapter import (
    sign_for_alert,
)
from agents.site_monitor_agent.outputs.trend_analyzer import (
    TrendAnalyzer,
)

__all__ = [
    "DailyReportGenerator",
    "TrendAnalyzer",
    "DashboardDataProvider",
    "sign_for_alert",
]
