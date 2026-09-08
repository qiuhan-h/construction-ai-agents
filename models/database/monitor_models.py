"""监控域表模型：告警事件 / 传感器设备台账。

高频原始传感数据不落关系库（走 core/timeseries 时序库），
此处只存低频、需长期检索的事件与台账。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.constants import AlertLevel, AlertStatus
from common.ids import alert_id
from common.timeutils import utc_now
from models.database.base import Base, IDMixin, TenantMixin, TimestampMixin, enum_column


class AlertTable(TenantMixin, IDMixin, Base):
    """告警事件表。"""

    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: alert_id()
    )
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[str] = mapped_column(
        enum_column(AlertLevel), nullable=False, default=AlertLevel.WARNING.value
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    # 位置与指标快照均为 JSON 列（结构与 domain GeoPoint / dict 对齐）
    location: Mapped[dict | None] = mapped_column(JSON)
    metric: Mapped[dict | None] = mapped_column(JSON)
    dedup_key: Mapped[str | None] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(
        enum_column(AlertStatus), nullable=False, default=AlertStatus.ACTIVE.value
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SensorDeviceTable(TenantMixin, IDMixin, TimestampMixin, Base):
    """传感器设备台账（与 IoT 集成模块共用）。"""

    __tablename__ = "sensor_devices"

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id"), nullable=False, index=True
    )
    device_name: Mapped[str] = mapped_column(String(128), nullable=False)
    device_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # MQTT 主题（iot_integration 的接入标识）
    mqtt_topic: Mapped[str | None] = mapped_column(String(256))
    longitude: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)
    # 是否在线（由 sensor_manager 心跳维护）
    online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extra: Mapped[dict | None] = mapped_column(JSON)
