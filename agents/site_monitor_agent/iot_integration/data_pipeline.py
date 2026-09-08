"""原始数据 → 清洗 → 时序库管道。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from common.timeutils import ensure_utc, from_iso, to_iso, utc_now

logger = logging.getLogger(__name__)


class DataPipeline:
    """asyncio.Queue 缓冲 + on_event 回调。"""

    def __init__(self, queue_size: int = 10_000) -> None:
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self._dropped = 0
        self._running = False

    async def ingest(self, raw: dict) -> None:
        try:
            self._queue.put_nowait(raw)
        except asyncio.QueueFull:
            self._dropped += 1
            if self._dropped % 1000 == 0:
                logger.warning("pipeline 队列满，已丢弃 %d 条", self._dropped)

    async def run(self, on_event: Callable) -> None:
        """持续消费；on_event 签名 async def on_event(cleaned: dict) -> None。"""
        self._running = True
        while self._running:
            raw = await self._queue.get()
            try:
                cleaned = self._clean(raw)
                if cleaned:
                    await on_event(cleaned)
            except Exception as e:  # noqa: BLE001
                logger.warning("pipeline 处理失败: %s", e)

    def stop(self) -> None:
        self._running = False

    @property
    def dropped_count(self) -> int:
        return self._dropped

    @staticmethod
    def _clean(raw: dict) -> dict:
        """归一化：必填字段校验 + 时间戳统一为 UTC ISO。

        必填字段：device_id, metric, value
        输出字段：
          {
            "device_id": str, "metric": str, "value": float,
            "unit": str, "timestamp": str (ISO-8601 UTC),
            "tenant_id": str, "project_id": str, "tags": dict,
          }
        """
        if not isinstance(raw, dict):
            return {}
        if "device_id" not in raw or "metric" not in raw or "value" not in raw:
            logger.debug("丢弃缺必填字段的记录: %s", raw)
            return {}
        try:
            value = float(raw["value"])
        except (TypeError, ValueError):
            return {}
        ts_raw = raw.get("timestamp")
        if isinstance(ts_raw, (int, float)):
            ts = datetime.fromtimestamp(ts_raw, tz=timezone.utc).isoformat()
        elif isinstance(ts_raw, str) and ts_raw:
            try:
                ts = ensure_utc(from_iso(ts_raw)).isoformat()
            except Exception:  # noqa: BLE001
                ts = to_iso(utc_now())
        else:
            ts = to_iso(utc_now())
        return {
            "device_id": str(raw["device_id"]),
            "metric": str(raw["metric"]),
            "value": value,
            "unit": str(raw.get("unit", "")),
            "timestamp": ts,
            "tenant_id": str(raw.get("tenant_id", "")),
            "project_id": str(raw.get("project_id", "")),
            "tags": {k: v for k, v in raw.items()
                     if k not in {"device_id", "metric", "value", "unit",
                                  "timestamp", "tenant_id", "project_id"}},
        }
