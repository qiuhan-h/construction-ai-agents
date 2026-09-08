"""传感器注册表。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from common.timeutils import utc_now
from models.domain import GeoPoint

logger = logging.getLogger(__name__)


@dataclass
class Sensor:
    device_id: str
    sensor_type: str
    tenant_id: str
    project_id: str
    location: GeoPoint | None = None
    metrics: list[str] = field(default_factory=list)
    status: str = "active"
    registered_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


class SensorManager:
    def __init__(self) -> None:
        self._sensors: dict[str, Sensor] = {}
        self._lock = asyncio.Lock()

    async def register(self, sensor: Sensor) -> None:
        async with self._lock:
            self._sensors[sensor.device_id] = sensor

    async def unregister(self, device_id: str) -> bool:
        async with self._lock:
            return self._sensors.pop(device_id, None) is not None

    def get(self, device_id: str) -> Sensor | None:
        return self._sensors.get(device_id)

    async def list_active(self, tenant_id: str, project_id: str | None = None) -> list[Sensor]:
        async with self._lock:
            return [s for s in self._sensors.values()
                    if s.tenant_id == tenant_id
                    and s.status == "active"
                    and (project_id is None or s.project_id == project_id)]

    async def list_all(self, tenant_id: str | None = None) -> list[Sensor]:
        async with self._lock:
            if tenant_id is None:
                return list(self._sensors.values())
            return [s for s in self._sensors.values() if s.tenant_id == tenant_id]

    async def update_status(self, device_id: str, status: str) -> bool:
        async with self._lock:
            s = self._sensors.get(device_id)
            if s is None:
                return False
            s.status = status
            return True
