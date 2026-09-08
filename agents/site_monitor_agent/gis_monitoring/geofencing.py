"""地理围栏：定义 + 检测越界。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from common.timeutils import utc_now
from models.domain import GeoPoint

logger = logging.getLogger(__name__)


@dataclass
class FenceViolation:
    """围栏越界记录。"""
    fence_id: str
    device_id: str
    point: GeoPoint
    ts: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


class Geofencing:
    """地理围栏：定义 polygon + 检测点是否在多边形内。"""

    def __init__(
        self,
        history_store: "GeofenceHistoryStore | None" = None,
    ) -> None:
        self._fences: dict[str, dict] = {}  # fence_id -> {name, polygon}
        # 5b.7：注入持久化 store；None 时按需懒加载
        self._history_store = history_store

    def _store(self):
        if self._history_store is None:
            from agents.site_monitor_agent.gis_monitoring.geofence_history import (
                get_geofence_history_store,
            )
            self._history_store = get_geofence_history_store()
        return self._history_store

    def define_fence(
        self, fence_id: str, polygon: list[GeoPoint], name: str = "",
    ) -> None:
        self._fences[fence_id] = {"name": name, "polygon": list(polygon)}
        logger.info("围栏定义: id=%s 顶点数=%d", fence_id, len(polygon))

    def remove_fence(self, fence_id: str) -> bool:
        return self._fences.pop(fence_id, None) is not None

    def get_polygon(self, fence_id: str) -> list[GeoPoint]:
        f = self._fences.get(fence_id)
        return list(f["polygon"]) if f else []

    def check_violation(
        self, fence_id: str, point: GeoPoint, device_id: str = "",
    ) -> bool:
        """点在 polygon 外 = 越界。"""
        poly = self.get_polygon(fence_id)
        if not poly:
            return False
        from agents.site_monitor_agent.gis_monitoring.spatial_monitor import (
            SpatialMonitor,
        )
        return not SpatialMonitor().point_in_polygon(point, poly)

    async def record_violation(
        self,
        fence_id: str,
        point: GeoPoint,
        device_id: str = "",
        tenant_id: str = "t-default",
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """5b.7 新增：把一条越界写入历史。返回 id，越界未发生返回 None。

        P0-5 修补：原同步 ``def`` 内部调 ``await self._store().record(...)``
        返回的是 coroutine 对象未 await，5b.7 接口契约彻底失效。
        改为 ``async def`` + ``await``。
        """
        if not self.check_violation(fence_id, point, device_id):
            return None
        vio = FenceViolation(
            fence_id=fence_id,
            device_id=device_id,
            point=point,
            metadata=metadata or {},
        )
        return await self._store().record(vio, tenant_id=tenant_id)

    async def list_violations_since(
        self, since: datetime, device_id: str = "",
        *, tenant_id: str = "t-default",
        fence_id: str | None = None,
        limit: int = 100,
    ) -> list[FenceViolation]:
        """4d 时期接口契约保留；5b.7 起从 ``history_store`` 真实取数。

        P0-5 修补：同 ``record_violation``，改 ``async def`` + ``await``。
        """
        return await self._store().list_since(
            tenant_id=tenant_id,
            since=since,
            fence_id=fence_id,
            device_id=device_id or None,
            limit=limit,
        )
