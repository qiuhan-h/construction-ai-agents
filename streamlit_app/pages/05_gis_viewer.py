"""Page 05 - GIS 视图（5a）。

设计：
- 复用 components/map_component 渲染 markers / heatmap / polygon;
- 默认演示数据:北京若干工地坐标(模拟);
- 上传 GeoJSON / CSV 按钮 → 替换 demo 数据;
- 切换 kind / zoom / center 操作;
- 5c GIS 数据源接入（deployment/gis/*）后续可对接。
"""

from __future__ import annotations

import io
from typing import Any

import pandas as pd
import streamlit as st

from streamlit_app.components import map_component


PAGE_TITLE = "GIS 视图"

# 北京示例数据（5a 默认演示）
_DEMO_SITES: list[dict[str, Any]] = [
    {"name": "国贸三期工地", "lat": 39.9085, "lon": 116.4584, "level": "info",
     "status": "正常"},
    {"name": "中关村工地", "lat": 39.9847, "lon": 116.3095, "level": "warning",
     "status": "基坑变形"},
    {"name": "望京 SOHO 工地", "lat": 39.9972, "lon": 116.4769, "level": "info",
     "status": "正常"},
    {"name": "丰台科技园工地", "lat": 39.8329, "lon": 116.2776, "level": "critical",
     "status": "塔吊异常"},
    {"name": "通州副中心工地", "lat": 39.9097, "lon": 116.6575, "level": "info",
     "status": "正常"},
    {"name": "大兴机场工地", "lat": 39.5097, "lon": 116.4108, "level": "warning",
     "status": "噪声超标"},
    {"name": "朝阳公园工地", "lat": 39.9388, "lon": 116.4783, "level": "info",
     "status": "正常"},
    {"name": "五道口工地", "lat": 39.9929, "lon": 116.3389, "level": "critical",
     "status": "高空坠物"},
]


def _default_df() -> pd.DataFrame:
    return pd.DataFrame(_DEMO_SITES)


def _render_data_source() -> pd.DataFrame:
    """选择数据源 → 返回 DataFrame。"""
    src = st.radio(
        "数据源",
        options=["demo", "csv_upload", "json_upload"],
        format_func=lambda x: {
            "demo": "内置 demo（北京工地）",
            "csv_upload": "上传 CSV (lat, lon, name, level, ...)",
            "json_upload": "上传 GeoJSON",
        }.get(x, x),
        horizontal=True,
        key="gis_src",
    )

    if src == "demo":
        return _default_df()

    if src == "csv_upload":
        f = st.file_uploader(
            "上传 CSV", type=["csv"], key="gis_csv"
        )
        if f is None:
            st.info("未上传，使用 demo 数据。")
            return _default_df()
        try:
            df = pd.read_csv(io.BytesIO(f.read()))
            if "lat" not in df.columns or "lon" not in df.columns:
                st.warning("CSV 必须含 lat / lon 列")
                return _default_df()
            return df
        except Exception as e:  # noqa: BLE001
            st.error(f"CSV 解析失败: {e}")
            return _default_df()

    if src == "json_upload":
        f = st.file_uploader(
            "上传 GeoJSON", type=["json", "geojson"], key="gis_json"
        )
        if f is None:
            return _default_df()
        try:
            import json

            geo = json.loads(f.read())
            # 提取 lat/lon from GeoJSON
            rows = []
            for feat in geo.get("features", []):
                geom = feat.get("geometry", {})
                coords = geom.get("coordinates", [])
                if geom.get("type") == "Point" and len(coords) >= 2:
                    props = feat.get("properties") or {}
                    rows.append(
                        {
                            "lat": coords[1],
                            "lon": coords[0],
                            "name": props.get("name", ""),
                            "level": props.get("level", "info"),
                            "status": props.get("status", ""),
                        }
                    )
            if not rows:
                st.warning("GeoJSON 中未发现 Point 几何")
                return _default_df()
            return pd.DataFrame(rows)
        except Exception as e:  # noqa: BLE001
            st.error(f"GeoJSON 解析失败: {e}")
            return _default_df()

    return _default_df()


def _render_controls() -> tuple[str, int, tuple[float, float] | None]:
    cols = st.columns(3)
    kind = cols[0].selectbox(
        "图层类型",
        options=["markers", "heatmap"],
        format_func=lambda x: {"markers": "标记点", "heatmap": "热力图"}[x],
        key="gis_kind",
    )
    zoom = cols[1].slider(
        "缩放", min_value=8, max_value=18, value=11, key="gis_zoom"
    )
    use_auto_center = cols[2].checkbox(
        "自动中心", value=True, key="gis_auto_center"
    )
    center: tuple[float, float] | None = None
    if not use_auto_center:
        cc = st.columns(2)
        lat = cc[0].number_input(
            "中心 lat", value=39.9042, format="%.4f", key="gis_lat"
        )
        lon = cc[1].number_input(
            "中心 lon", value=116.4074, format="%.4f", key="gis_lon"
        )
        center = (float(lat), float(lon))
    return kind, zoom, center


def _render_summary(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return
    cols = st.columns(4)
    cols[0].metric("点位", len(df))
    if "level" in df.columns:
        critical_n = int((df["level"] == "critical").sum())
        warning_n = int((df["level"] == "warning").sum())
        info_n = int((df["level"] == "info").sum())
        cols[1].metric("critical", critical_n)
        cols[2].metric("warning", warning_n)
        cols[3].metric("info", info_n)
    st.dataframe(df, use_container_width=True, hide_index=True)


def render() -> None:
    st.markdown(f"## 🗺️ {PAGE_TITLE}")
    st.caption("施工现场地理信息视图（5a demo + 上传）")

    df = _render_data_source()
    kind, zoom, center = _render_controls()

    st.divider()
    _render_summary(df)

    map_component.render(
        df,
        kind=kind,  # type: ignore[arg-type]
        lat_col="lat",
        lon_col="lon",
        name_col="name" if "name" in df.columns else None,
        color_col="level" if "level" in df.columns else None,
        title=f"{len(df)} 个点位 · {kind}",
        center=center,
        zoom=zoom,
        container_key="gis_map",
    )


__all__ = ["render"]
