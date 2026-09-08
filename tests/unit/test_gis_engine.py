"""GIS 引擎单元测试：空间几何（点在多边形内 / 距离 / 包围盒）+ 电子围栏。"""

from __future__ import annotations

import asyncio

from agents.site_monitor_agent.gis_monitoring.geofencing import Geofencing
from agents.site_monitor_agent.gis_monitoring.spatial_monitor import (
    GeoPoint,
    SpatialMonitor,
)

# 100m × 100m 正方形工地围栏（经纬度近似 0.001° ≈ 111m / 111m）
SQUARE = [
    GeoPoint(longitude=116.0, latitude=39.0),
    GeoPoint(longitude=116.001, latitude=39.0),
    GeoPoint(longitude=116.001, latitude=39.001),
    GeoPoint(longitude=116.0, latitude=39.001),
]
INSIDE = GeoPoint(longitude=116.0005, latitude=39.0005)
OUTSIDE = GeoPoint(longitude=116.01, latitude=39.01)

MONITOR = SpatialMonitor()


def test_point_in_polygon_inside() -> None:
    assert MONITOR.point_in_polygon(INSIDE, SQUARE) is True


def test_point_in_polygon_outside() -> None:
    assert MONITOR.point_in_polygon(OUTSIDE, SQUARE) is False


def test_distance_m_positive_and_order_independent() -> None:
    a = GeoPoint(longitude=116.0, latitude=39.0)
    b = GeoPoint(longitude=116.0, latitude=39.001)
    d = MONITOR.distance_m(a, b)
    # 纬度差 0.001° ≈ 111m
    assert 100 < d < 125
    assert MONITOR.distance_m(a, b) == MONITOR.distance_m(b, a)


def test_bounding_box_covers_all_points() -> None:
    bbox = MONITOR.bounding_box(SQUARE)
    lons = [p.longitude for p in SQUARE]
    lats = [p.latitude for p in SQUARE]
    # 包围盒两个值分别为 min/max，不依赖返回顺序
    assert min(bbox[0], bbox[2]) <= min(lons)
    assert max(bbox[0], bbox[2]) >= max(lons)
    assert min(bbox[1], bbox[3]) <= min(lats)
    assert max(bbox[1], bbox[3]) >= max(lats)


def test_define_fence_roundtrip() -> None:
    g = Geofencing()
    g.define_fence("f-1", SQUARE, name="一号工地")
    poly = g.get_polygon("f-1")
    assert len(poly) == 4
    assert g.remove_fence("f-1") is True
    assert g.get_polygon("f-1") == []


def test_check_violation_inside_and_outside() -> None:
    g = Geofencing()
    g.define_fence("f-2", SQUARE)
    # 围栏内：不越界
    assert g.check_violation("f-2", INSIDE) is False
    # 围栏外：越界
    assert g.check_violation("f-2", OUTSIDE) is True


def test_check_violation_unknown_fence_no_crash() -> None:
    g = Geofencing()
    # 围栏不存在时不得抛异常（返回 False）
    assert g.check_violation("missing", INSIDE) is False


def test_record_violation_async_p05() -> None:
    """P0-5 回归：record_violation 必须是 async 且内部 await 存储。

    围栏内 → 返回 None；围栏外 → 返回违规 id（或存储可用时非 None）。
    """

    async def _run() -> None:
        g = Geofencing()
        g.define_fence("f-3", SQUARE)
        inside_result = await g.record_violation(
            "f-3", INSIDE, device_id="d1", tenant_id="tnt_gis"
        )
        assert inside_result is None, "围栏内不应记录越界"
        outside_result = await g.record_violation(
            "f-3", OUTSIDE, device_id="d2", tenant_id="tnt_gis"
        )
        # 内存存储可用时应返回 id；即使外部存储未配置也不应返回 coroutine
        assert not asyncio.iscoroutine(outside_result)

    asyncio.run(_run())
