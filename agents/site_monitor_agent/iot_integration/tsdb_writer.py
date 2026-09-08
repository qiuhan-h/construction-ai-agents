"""InfluxDB 写入：时序数据落库。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from common.timeutils import from_iso

logger = logging.getLogger(__name__)


class TSDBWriter:
    """InfluxDB 写入：封装 influxdb-client（缺失时降级 mock）。"""

    def __init__(self, settings: Any | None = None) -> None:
        self._client: Any = None
        self._mock_mode = True
        self._settings = settings
        try:
            from config import get_settings  # noqa: F401
            # 真实接入留到阶段五；首版仅 mock
        except Exception:  # noqa: BLE001
            pass

    async def write_point(
        self,
        measurement: str,
        tags: dict,
        fields: dict,
        ts: datetime,
    ) -> bool:
        """写入单条数据点（mock 模式只记日志）。"""
        if self._mock_mode:
            logger.debug("TSDB mock 写入: m=%s tags=%s fields=%s ts=%s",
                         measurement, tags, fields, ts)
            return True
        # 真实模式（阶段五）：
        # from influxdb_client import InfluxDBClient, Point
        # ...
        return False

    async def query_range(
        self,
        measurement: str,
        tags: dict,
        start: datetime,
        end: datetime,
    ) -> list[dict]:
        """范围查询（mock 返回空）。"""
        if self._mock_mode:
            return []
        return []

    @staticmethod
    def parse_timestamp(ts_str: str) -> datetime:
        """工具方法：从清洗后的 ISO 字符串解析 datetime。"""
        return from_iso(ts_str)
