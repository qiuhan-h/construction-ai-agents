"""空间监控：坐标范围 / 距离 / 区域计算。"""

from __future__ import annotations

import math

from models.domain import GeoPoint

EARTH_RADIUS_M = 6_371_008.8  # 平均地球半径（米）


class SpatialMonitor:
    """坐标 / 距离 / 区域工具（GCJ-02 投影，度为经纬度）。"""

    def point_in_polygon(self, point: GeoPoint, polygon: list[GeoPoint]) -> bool:
        """射线法判断点是否在多边形内。"""
        if not polygon or len(polygon) < 3:
            return False
        x, y = point.longitude, point.latitude
        inside = False
        n = len(polygon)
        for i in range(n):
            j = (i - 1) % n
            xi, yi = polygon[i].longitude, polygon[i].latitude
            xj, yj = polygon[j].longitude, polygon[j].latitude
            # L15 修补：首项 (yi > y) != (yj > y) 为 True 时，yi/yj 严格分居
            # 射线两侧，必有 yj != yi，分母不为 0；原 +1e-12 扰动会使交点
            # x 坐标产生系统偏差（数学上不正确），故移除。
            intersect = ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / (yj - yi) + xi
            )
            if intersect:
                inside = not inside
        return inside

    def distance_m(self, a: GeoPoint, b: GeoPoint) -> float:
        """Haversine 球面距离（米）。"""
        lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
        dlat = lat2 - lat1
        dlon = math.radians(b.longitude - a.longitude)
        h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))

    def bounding_box(
        self, points: list[GeoPoint],
    ) -> tuple[float, float, float, float]:
        """返回 (min_lon, min_lat, max_lon, max_lat)。空列表返回 (0,0,0,0)。"""
        if not points:
            return (0.0, 0.0, 0.0, 0.0)
        lons = [p.longitude for p in points]
        lats = [p.latitude for p in points]
        return (min(lons), min(lats), max(lons), max(lats))
