"""阈值管理：按 device_id + metric 查询阈值。"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class ThresholdManager:
    def __init__(self) -> None:
        self._thresholds: dict[tuple[str, str], float] = {}
        self._lock = asyncio.Lock()

    async def set(self, device_id: str, metric: str, value: float) -> None:
        async with self._lock:
            self._thresholds[(device_id, metric)] = float(value)

    async def get(self, device_id: str, metric: str) -> float | None:
        async with self._lock:
            return self._thresholds.get((device_id, metric))

    async def delete(self, device_id: str, metric: str) -> bool:
        async with self._lock:
            return self._thresholds.pop((device_id, metric), None) is not None

    def list_all(self) -> dict[tuple[str, str], float]:
        return dict(self._thresholds)
