"""移动端精简 Schema（6c.1）。

设计原则：
- 字段 ≤15 个（TR-8.4），只保留移动端首屏必需信息；
- 告警/项目卡片用 list + 最少字段，响应体 < 5KB（TR-8.1）；
- 与桌面端 Dashboard 共享数据源，仅裁剪输出字段。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MobileAlertListItem(BaseModel):
    """移动端告警列表项（精简）。"""

    id: str = Field(..., description="告警 ID")
    level: str = Field(..., description="告警级别 (critical/warning/info)")
    title: str = Field(..., description="告警标题（≤50 字）")
    source: str | None = Field(default=None, description="来源设备/智能体")
    status: str = Field(default="open", description="处置状态")
    occurred_at: str | None = Field(default=None, description="发生时间 ISO")


class MobileProjectCard(BaseModel):
    """移动端项目卡片（精简）。"""

    id: str = Field(..., description="项目 ID")
    name: str = Field(..., description="项目名称")
    status: str = Field(default="active", description="项目状态")
    safety_score: float | None = Field(default=None, description="安全评分")
    open_alerts: int = Field(default=0, description="未处置告警数")


class MobileDashboard(BaseModel):
    """移动端首页仪表盘（精简聚合）。

    总字段数 = 6（远 ≤15）：
    tenant_name, open_alerts, safety_score, alerts[], projects[], updated_at
    """

    tenant_name: str = Field(default="", description="租户名称")
    open_alerts: int = Field(default=0, description="未处置告警总数")
    safety_score: float | None = Field(default=None, description="安全评分")
    alerts: list[MobileAlertListItem] = Field(
        default_factory=list, description="最近 5 条告警"
    )
    projects: list[MobileProjectCard] = Field(
        default_factory=list, description="项目卡片（最多 10 个）"
    )
    updated_at: str | None = Field(default=None, description="数据更新时间 ISO")


__all__ = ["MobileDashboard", "MobileAlertListItem", "MobileProjectCard"]
