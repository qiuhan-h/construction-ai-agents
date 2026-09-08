"""InfluxDB 写入器（5b.5）— re-export shim。

P3-1 修正：实现已迁移到 ``core/timeseries/client.py``，遵守 core/ → agents/
的分层约束。本文件仅做 re-export，保持 agent 侧引用路径不变。

旧引用方式 ``from agents.site_monitor_agent.iot_integration.influxdb_writer
import InfluxDBWriter`` 继续可用；新代码应直接用 ``from core.timeseries
import InfluxDBWriter``。
"""

from __future__ import annotations

from core.timeseries.client import (  # noqa: F401
    InfluxDBWriter,
    InfluxWriteError,
    build_line_protocol,
    write_point,
)

__all__ = [
    "InfluxDBWriter",
    "InfluxWriteError",
    "build_line_protocol",
    "write_point",
]
