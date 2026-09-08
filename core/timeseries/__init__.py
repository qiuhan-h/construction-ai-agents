"""core.timeseries：时序数据库顶层入口。

P3-1 修正：InfluxDBWriter 实现从 agents/ 迁移到 core/timeseries/client.py，
遵守 core/ → agents/ 的分层约束。agent 侧 ``influxdb_writer.py`` 改为 re-export。
"""

from core.timeseries.client import (
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
