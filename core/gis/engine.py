"""GIS 引擎基类（5b 占位，5c 实装）。

计划接口（5c）：
    class GISEngine:
        def transform_coord(self, lng: float, lat: float, *,
                            from_crs: str, to_crs: str) -> tuple[float, float]: ...
        def spatial_index(self, points: list[GeoPoint]) -> SpatialIndex: ...
        def add_layer(self, layer: GeoLayer) -> None: ...
        def query_layers(self, bbox: BBox) -> list[GeoLayer]: ...

当前 GIS 引擎能力在 ``agents.site_monitor_agent.gis_monitoring/`` 的
``geofencing.py`` / ``spatial_monitor.py`` 中以 agent 级实现提供。
core 层抽象将在 5c 可观测 + GIS 集成阶段补齐。
"""

from __future__ import annotations


class GISEngine:
    """GIS 引擎基类（占位）。5c 阶段实装。"""

    def __init__(self) -> None:
        raise NotImplementedError(
            "core.gis.engine.GISEngine 尚未实装（5b 占位）；"
            "请从 agents.site_monitor_agent.gis_monitoring 导入 GIS 工具"
        )
