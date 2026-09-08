"""GIS 数据加载：扫描 data/geodata/{geojson,shapefiles} → 注入 spatial_monitor + ORM upsert 围栏。

设计（4d D7 幂等，5b.3 升级 ORM）：
- 默认从 ``data/geodata/geojson/*.geojson`` / ``*.json`` 扫描 GeoJSON FeatureCollection；
- Shapefile 需要 ``pyshp``（shapefile）依赖，首版跳过并 warn；
- 把每个 Feature 的 geometry 解析为 ``GeoPoint`` 列表，注入到
  ``SpatialMonitor`` 的内存索引，并可选注册到 ``Geofencing`` 围栏表；
- 5b.3：围栏定义 upsert 到 ``GeofenceRepository``（SQLAlchemy ORM）；
  缺包 / 缺表时降级为只注入内存（4d 接口契约保留）；
- 重复执行等价于 upsert：feature_id 唯一。

用法：
    python scripts/load_gis_data.py
    python scripts/load_gis_data.py --dir data/geodata/geojson
    python scripts/load_gis_data.py --tenant tnt_x --fence-id mysite
    python scripts/load_gis_data.py --dry-run
    python scripts/load_gis_data.py --list         # 列出当前 fence 缓存

退出码：
    0  成功
    1  目录不存在 / 解析失败
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger("scripts.load_gis_data")


# =====================================================
# ORM 仓储获取（5b.3 新增）
# =====================================================
def _get_geofence_repo() -> Any:
    """返回 ``GeofenceRepository`` 或 None。"""
    try:
        from core.storage.sqlalchemy_repos import (
            BackendUnavailableError,
            get_geofence_repository,
            init_database_for_dev,
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("导入 ORM 仓储失败: %s", e)
        return None
    try:
        init_database_for_dev()
        return get_geofence_repository()
    except BackendUnavailableError:
        return None
    except Exception as e:  # noqa: BLE001
        logger.debug("ORM 初始化失败: %s", e)
        return None


# =====================================================
# GeoJSON 解析
# =====================================================
def _parse_geometry(coords: Any) -> list[tuple[float, float]]:
    """把 GeoJSON coordinates 拍平为 ``[(lon, lat), ...]``。

    支持：Point / LineString / Polygon / Multi*。
    """
    out: list[tuple[float, float]] = []

    def _walk(obj: Any) -> None:
        if obj is None:
            return
        if isinstance(obj, (int, float)):
            return
        if isinstance(obj, list):
            if len(obj) >= 2 and isinstance(obj[0], (int, float)):
                # [lon, lat] 或 [lon, lat, alt]
                out.append((float(obj[0]), float(obj[1])))
            else:
                for x in obj:
                    _walk(x)
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)

    _walk(coords)
    return out


def _scan_geojson_dir(data_dir: str) -> list[dict[str, Any]]:
    """扫描目录下所有 ``.geojson`` / ``.json`` 文件，提取 feature 列表。

    返回 ``[{file, feature_index, fid, name, points: [(lon, lat)], props}, ...]``。
    """
    results: list[dict[str, Any]] = []
    if not os.path.isdir(data_dir):
        return results
    for name in sorted(os.listdir(data_dir)):
        if not (name.endswith(".geojson") or name.endswith(".json")):
            continue
        path = os.path.join(data_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("读取 GeoJSON 失败 %s: %s", path, e)
            continue
        if not isinstance(doc, dict):
            continue
        if doc.get("type") == "FeatureCollection":
            features = doc.get("features") or []
        elif doc.get("type") == "Feature":
            features = [doc]
        else:
            # 纯 geometry
            features = [{"type": "Feature", "geometry": doc, "properties": {}}]
        for i, feat in enumerate(features):
            if not isinstance(feat, dict):
                continue
            geom = feat.get("geometry") or {}
            if not isinstance(geom, dict):
                continue
            coords = _parse_geometry(geom.get("coordinates"))
            if not coords:
                continue
            props = feat.get("properties") or {}
            fid = str(
                feat.get("id")
                or props.get("id")
                or props.get("name")
                or f"{name}#{i}"
            )
            results.append(
                {
                    "file": name,
                    "feature_index": i,
                    "fid": fid,
                    "name": str(props.get("name") or fid),
                    "points": coords,
                    "props": props,
                    "geometry": geom,
                }
            )
    return results


# =====================================================
# 注入到 spatial_monitor / geofencing
# =====================================================
def _inject_into_spatial_monitor(features: list[dict[str, Any]]) -> int:
    """把 features 注入到 SpatialMonitor 缓存（首版 in-memory）。"""
    try:
        from agents.site_monitor_agent.gis_monitoring.spatial_monitor import (
            SpatialMonitor,
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("SpatialMonitor 不可用: %s", e)
        return 0
    # 4d 不要求 SpatialMonitor 内置缓存；这里仅做"可用性探测"
    SpatialMonitor()
    return 1


def _inject_into_geofencing(
    fence_id: str, features: list[dict[str, Any]], tenant_id: str
) -> int:
    """尝试把 features 写入 Geofencing 围栏（in-memory 即可）。"""
    try:
        from agents.site_monitor_agent.gis_monitoring.geofencing import (
            Geofencing,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Geofencing 不可用: %s", e)
        return 0
    try:
        from models.domain import GeoPoint
    except Exception as e:  # noqa: BLE001
        logger.warning("models.domain.GeoPoint 不可用: %s", e)
        return 0

    # 复用单实例：在循环外创建一次 Geofencing，避免每个 feature 新建
    # 实例导致前序 define_fence 写入的围栏丢失。
    ge = Geofencing()
    if not hasattr(ge, "define_fence"):
        logger.warning("Geofencing 不支持 define_fence，跳过注入")
        return 0

    n_ok = 0
    for feat in features:
        try:
            polygon = [GeoPoint(lat=p[1], lon=p[0]) for p in feat["points"]]
        except Exception:  # noqa: BLE001
            continue
        try:
            # H16 修补：Geofencing 的真实 API 是 define_fence(fence_id,
            # polygon, name)；旧代码调不存在的 add_fence(tenant_id=...)，
            # hasattr 探测恒为 False → 注入静默失效、围栏计数永远为 0。
            # 内存围栏定义不带 tenant 维度；多租户持久化由 ORM 路径负责。
            ge.define_fence(
                fence_id=f"{fence_id}:{feat['fid']}",
                polygon=polygon,
                name=feat.get("name") or "",
            )
            # 仅当 define_fence 实际成功时计数为成功
            n_ok += 1
        except Exception as e:  # noqa: BLE001
            logger.debug("define_fence 失败 fid=%s: %s", feat.get("fid"), e)
    return n_ok


# =====================================================
# ORM upsert（5b.3 新增）
# =====================================================
def _upsert_into_orm(
    repo: Any, fence_id: str, features: list[dict[str, Any]], tenant_id: str
) -> int:
    """把 features 写入 ``GeofenceRepository``。"""
    n = 0
    for feat in features:
        try:
            points = feat["points"]
            center_lon = sum(p[0] for p in points) / len(points) if points else None
            center_lat = sum(p[1] for p in points) / len(points) if points else None
            repo.add(
                {
                    "tenant_id": tenant_id,
                    "fence_id": f"{fence_id}:{feat['fid']}",
                    "name": feat.get("name", ""),
                    "fence_type": "polygon",
                    "geometry": feat.get("geometry")
                    or {
                        "type": "Polygon",
                        "coordinates": [[list(p) for p in points]],
                    },
                    "source": "geojson",
                    "is_active": True,
                    "description": (feat.get("props") or {}).get("description"),
                    "center_lon": center_lon,
                    "center_lat": center_lat,
                }
            )
            n += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("ORM 围栏写入失败: %s", e)
    return n


# =====================================================
# 主流程
# =====================================================
def main(args: argparse.Namespace) -> int:
    project_root = _PROJECT_ROOT
    data_dir = (
        args.dir
        if os.path.isabs(args.dir)
        else os.path.join(project_root, args.dir)
    )
    if not os.path.isdir(data_dir):
        print(f"GIS 目录不存在: {data_dir}", file=sys.stderr)
        return 1

    features = _scan_geojson_dir(data_dir)
    if not features:
        print(f"目录 {data_dir} 未发现 GeoJSON 要素（空或全部解析失败）")
        return 0

    if args.dry_run:
        for f in features:
            print(
                f"  [DRY] {f['file']}#{f['feature_index']} fid={f['fid']} "
                f"points={len(f['points'])}"
            )
        return 0

    spatial_ok = _inject_into_spatial_monitor(features)
    fence_ok = _inject_into_geofencing(
        fence_id=args.fence_id, features=features, tenant_id=args.tenant
    )

    # 5b.3：ORM upsert
    n_orm = 0
    repo = _get_geofence_repo()
    if repo is not None:
        n_orm = _upsert_into_orm(repo, args.fence_id, features, args.tenant)
        print(f"\n✓ ORM upsert {n_orm} 围栏")
    else:
        print("\n⚠️ ORM 不可用，跳过 DB 写入（仅内存注入）")

    print(f"扫描 {data_dir} → 要素 {len(features)}")
    for f in features:
        print(
            f"  - {f['file']}#{f['feature_index']}  fid={f['fid']}  "
            f"name={f['name']}  points={len(f['points'])}"
        )
    print()
    print("=" * 60)
    print(
        f"GIS 加载完成: 目录={data_dir} 要素={len(features)} "
        f"spatial_probe={spatial_ok} fence_inject={fence_ok} "
        f"orm_writes={n_orm} fence_id={args.fence_id} tenant={args.tenant}"
    )
    return 0


def cli_entry() -> int:
    parser = argparse.ArgumentParser(description="阶段 4d / 5b.3：GIS 数据加载")
    parser.add_argument(
        "--dir",
        default="data/geodata/geojson",
        help="GeoJSON 目录（默认 data/geodata/geojson）",
    )
    parser.add_argument("--fence-id", default="site_default", help="围栏分组 ID")
    parser.add_argument("--tenant", default="tnt_default", help="租户 ID")
    parser.add_argument("--dry-run", action="store_true", help="只扫描不注入")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    return main(args)


if __name__ == "__main__":
    sys.exit(cli_entry())
