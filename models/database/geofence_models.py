"""地理围栏域表模型（5b.3 新增）：围栏定义 / 越界事件。

设计：
- 围栏几何用 JSON 列存 GeoJSON（不引入 PostGIS 依赖；可移植 SQLite/PG）；
- 越界事件有独立的状态机（OPEN / ACKNOWLEDGED / RESOLVED 等），
  字段对齐 ``ViolationStatus``。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from common.constants import FenceSource, GeofenceType, ViolationStatus
from common.ids import geofence_id, geofence_violation_id
from common.timeutils import utc_now
from models.database.base import (
    Base,
    IDMixin,
    TenantMixin,
    TimestampMixin,
    enum_column,
)


class GeofenceTable(TenantMixin, IDMixin, TimestampMixin, Base):
    """地理围栏定义表。"""

    __tablename__ = "geofences"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: geofence_id()
    )
    project_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("projects.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    fence_type: Mapped[str] = mapped_column(
        enum_column(GeofenceType),
        nullable=False,
        default=GeofenceType.POLYGON.value,
    )
    # GeoJSON Geometry：polygon / circle / rect 由应用层定义
    geometry: Mapped[dict] = mapped_column(JSON, nullable=False)
    # 数据来源：人工 / 导入 / 自动
    source: Mapped[str] = mapped_column(
        enum_column(FenceSource),
        nullable=False,
        default=FenceSource.MANUAL.value,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(String(512))
    # 中心点（便于 GIS 视图 / 围栏列表快速展示）
    center_lon: Mapped[float | None] = mapped_column(Float)
    center_lat: Mapped[float | None] = mapped_column(Float)


class GeofenceViolationTable(TenantMixin, IDMixin, Base):
    """地理围栏越界事件表。

    与 4d 时期 ``FenceViolation`` 的区别：
    - 持久化（含 tenant_id / 状态机 / 业务字段）；
    - 与 5b.7 ``GeofenceHistoryStore.record/list_since`` 接口契约一致。
    """

    __tablename__ = "geofence_violations"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: geofence_violation_id()
    )
    geofence_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("geofences.id"), nullable=False, index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("projects.id"), index=True
    )
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 触发点（GeoPoint：{"lon": float, "lat": float}）
    location: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        enum_column(ViolationStatus),
        nullable=False,
        default=ViolationStatus.OPEN.value,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String(512))
    extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


__all__ = ["GeofenceTable", "GeofenceViolationTable"]
