"""通用地图组件（5a）。

设计：
- 引擎优先级:streamlit-folium(交互式) > folium(静态图片) > st.map(原生);
- 通用 render(data, lat_col, lon_col, kind="markers"|"heatmap"|"polygon");
- 兜底:不依赖 folium/st_folium 时显示 dataframe + 提示;
- 支持传入 GeoJSON 字典作为 polygon 边界（5c.5 GIS 数据源对接）。
"""

from __future__ import annotations

from typing import Any, Literal

import pandas as pd
import streamlit as st

MapKind = Literal["markers", "heatmap", "polygon"]


def _detect_engines() -> dict[str, bool]:
    engines: dict[str, bool] = {"folium": False, "st_folium": False}
    try:
        import folium  # noqa: F401

        engines["folium"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        from streamlit_folium import st_folium  # noqa: F401

        engines["st_folium"] = True
    except Exception:  # noqa: BLE001
        pass
    return engines


_ENGINES = _detect_engines()


# =====================================================
# public API
# =====================================================
def render(
    data: pd.DataFrame | dict[str, Any] | None,
    *,
    kind: MapKind = "markers",
    lat_col: str = "lat",
    lon_col: str = "lon",
    name_col: str | None = None,
    color_col: str | None = None,
    title: str | None = None,
    center: tuple[float, float] | None = None,
    zoom: int = 14,
    height: int = 480,
    geojson: dict[str, Any] | None = None,
    container_key: str = "map_root",
) -> None:
    """渲染地图。

    Parameters
    ----------
    data : DataFrame | dict | None
        - markers / heatmap: DataFrame（必须含 lat/lon 列）
        - polygon: dict（GeoJSON FeatureCollection）或 DataFrame（自动包成 GeoJSON）
    kind : {"markers","heatmap","polygon"}
    lat_col / lon_col : str
        经纬度列名（markers / heatmap 模式用）。
    name_col : str | None
        弹窗显示名称（markers 模式）。
    color_col : str | None
        按此列着色（markers / heatmap）。
    title : str | None
    center : (lat, lon) | None
        中心点；None 自动按 data 平均。
    zoom : int
    height : int
        folium 高度（像素）。
    geojson : dict | None
        polygon 模式下额外叠加的 GeoJSON 边界。
    container_key : str
    """
    if title:
        st.markdown(f"**{title}**")

    if data is None or (isinstance(data, pd.DataFrame) and data.empty):
        st.info("无地理数据。")
        return

    # auto 引擎
    if kind == "polygon":
        chosen = "folium" if _ENGINES["folium"] else "native"
    else:
        chosen = "st_folium" if _ENGINES["st_folium"] else (
            "folium" if _ENGINES["folium"] else "native"
        )

    if chosen == "native":
        _render_native(data, kind, lat_col, lon_col, container_key)
        return

    if not _ENGINES["folium"]:
        _render_native(data, kind, lat_col, lon_col, container_key)
        return

    import folium
    from folium.plugins import HeatMap  # type: ignore

    # 计算中心
    if center is None and isinstance(data, pd.DataFrame) and lat_col in data.columns:
        try:
            center = (float(data[lat_col].mean()), float(data[lon_col].mean()))
        except Exception:  # noqa: BLE001
            center = (39.9042, 116.4074)  # 北京默认
    if center is None:
        center = (39.9042, 116.4074)

    fmap = folium.Map(location=list(center), zoom_start=zoom, height=height)

    if kind == "markers" and isinstance(data, pd.DataFrame):
        for _, row in data.iterrows():
            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
            except (KeyError, ValueError, TypeError):
                continue
            popup = str(row[name_col]) if name_col and name_col in row else None
            color = "#1e88e5"
            if color_col and color_col in row:
                color = _severity_to_color(str(row[color_col]))
            folium.CircleMarker(
                location=[lat, lon],
                radius=6,
                popup=popup,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.7,
            ).add_to(fmap)

    elif kind == "heatmap" and isinstance(data, pd.DataFrame):
        pts: list[list[float]] = []
        for _, row in data.iterrows():
            try:
                pts.append([float(row[lat_col]), float(row[lon_col])])
            except (KeyError, ValueError, TypeError):
                continue
        if pts:
            HeatMap(pts, radius=18, blur=22).add_to(fmap)

    elif kind == "polygon":
        geo = _to_geojson(data)
        if geo:
            folium.GeoJson(geo, name="polygon").add_to(fmap)

    if geojson:
        folium.GeoJson(geojson, name="overlay").add_to(fmap)

    # 渲染
    if _ENGINES["st_folium"]:
        from streamlit_folium import st_folium

        st_folium(fmap, height=height, returned_objects=[], key=container_key)
    else:
        # folium 没装 st_folium 时退化为 HTML iframe（无需 st_folium）
        html = fmap.get_root().render()
        st.components.v1.html(html, height=height)


# =====================================================
# helpers
# =====================================================
def _severity_to_color(level: str) -> str:
    level = level.lower()
    if level in ("critical", "severe", "high", "3"):
        return "#ff4b4b"
    if level in ("warning", "warn", "medium", "2"):
        return "#ffa500"
    if level in ("info", "low", "1"):
        return "#1e88e5"
    return "#888"


def _to_geojson(data: pd.DataFrame | dict[str, Any]) -> dict[str, Any] | None:
    """把 DataFrame 或 dict 转成 GeoJSON FeatureCollection。"""
    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        return data
    if isinstance(data, dict):
        return {"type": "FeatureCollection", "features": [data]}
    if isinstance(data, pd.DataFrame):
        features: list[dict[str, Any]] = []
        for _, row in data.iterrows():
            props = {k: str(v) for k, v in row.items() if k not in ("lat", "lon")}
            geom_type = row.get("geometry_type", "Point")
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
            except (KeyError, ValueError, TypeError):
                continue
            if geom_type == "Point":
                geom = {"type": "Point", "coordinates": [lon, lat]}
            else:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": props,
                    "geometry": geom,
                }
            )
        return {"type": "FeatureCollection", "features": features}
    return None


def _render_native(
    data: pd.DataFrame | dict[str, Any],
    kind: MapKind,
    lat_col: str,
    lon_col: str,
    container_key: str,
) -> None:
    """兜底:不依赖 folium 时,用 st.map + dataframe。"""
    if isinstance(data, pd.DataFrame):
        if kind == "markers" and lat_col in data.columns and lon_col in data.columns:
            st.map(data, latitude=lat_col, longitude=lon_col, size=20)
        else:
            st.dataframe(data, use_container_width=True)
    else:
        st.json(data)


__all__ = ["render", "MapKind"]
