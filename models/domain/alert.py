"""告警领域模型（现场监控智能体的输出单元）。

高频原始传感器数据走时序库（core/timeseries），
此处只保存低频、需长期检索的告警事件。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from common.constants import AlertLevel, AlertStatus
from common.ids import alert_id
from common.timeutils import utc_now


class GeoPoint(BaseModel):
    """经纬度坐标（GCJ-02，与国内地图服务对齐）。"""

    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)


class Alert(BaseModel):
    """一条告警事件。"""

    id: str = Field(default_factory=alert_id, description="告警 ID (alert_ 前缀)")
    tenant_id: str = Field(description="所属租户 ID")
    project_id: str = Field(description="所属项目 ID")
    source: str = Field(min_length=1, max_length=64, description="告警来源（传感器/规则/BIM/GIS）")
    level: AlertLevel = Field(default=AlertLevel.WARNING)
    title: str = Field(min_length=1, max_length=256, description="告警标题")
    message: str | None = Field(default=None, description="告警详情")
    location: GeoPoint | None = Field(default=None, description="告警位置")
    metric: dict[str, float] | None = Field(
        default=None, description="触发告警的指标快照（如 {load: 1.35}）"
    )
    dedup_key: str | None = Field(
        default=None, max_length=128, description="去重键（同一事件在去重窗口内只报一次）"
    )
    status: AlertStatus = Field(default=AlertStatus.ACTIVE)
    triggered_at: datetime = Field(default_factory=utc_now, description="触发时间")
    acknowledged_at: datetime | None = Field(default=None, description="确认时间")
    resolved_at: datetime | None = Field(default=None, description="解除时间")
