"""通用图表组件（5a）。

设计：
- 双引擎:plotly(交互式) / altair(声明式) / 兜底 streamlit 原生 line_chart;
  按依赖可用性自动选择最优引擎;
- 4 类图表:line / bar / pie / scatter;
- 统一接口 render(kind="line", data=df, x="col", y=["col1","col2"], ...);
- 不强制任何依赖——第三方包缺时退化到 st.line_chart / st.bar_chart 原生组件。
"""

from __future__ import annotations

from typing import Any, Literal

import pandas as pd
import streamlit as st


ChartKind = Literal["line", "bar", "pie", "scatter"]


# =====================================================
# 引擎检测（一次性）
# =====================================================
def _detect_engines() -> dict[str, bool]:
    engines: dict[str, bool] = {"plotly": False, "altair": False}
    try:
        import plotly.express as px  # noqa: F401

        engines["plotly"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        import altair as alt  # noqa: F401

        engines["altair"] = True
    except Exception:  # noqa: BLE001
        pass
    return engines


_ENGINES = _detect_engines()


# =====================================================
# public API
# =====================================================
def render(
    data: pd.DataFrame,
    *,
    kind: ChartKind = "line",
    x: str | None = None,
    y: str | list[str] | None = None,
    title: str | None = None,
    color: str | None = None,
    height: int = 380,
    engine: Literal["auto", "plotly", "altair", "native"] = "auto",
    container_key: str = "chart_root",
) -> None:
    """渲染通用图表。

    Parameters
    ----------
    data : pd.DataFrame
        已聚合好的数据帧。
    kind : {"line","bar","pie","scatter"}
        图表类型。
    x : str | None
        X 轴字段；pie 图时用作 name 参数。
    y : str | list[str] | None
        Y 轴字段；单值或多值。pie 图时只取第一个作为 value。
    title : str | None
        图表标题（render 渲染到上方）。
    color : str | None
        分组字段。
    height : int
        plotly 高度（像素）。
    engine : {"auto","plotly","altair","native"}
        强制引擎；auto 按可用性自动选择。
    container_key : str
        容器 key 前缀。
    """
    if data is None or data.empty:
        st.info("无数据可绘制。")
        return

    # 标准化 y
    if isinstance(y, str):
        y_list: list[str] = [y]
    else:
        y_list = list(y or [])

    # auto 引擎选择
    chosen = engine
    if chosen == "auto":
        if _ENGINES["plotly"]:
            chosen = "plotly"
        elif _ENGINES["altair"]:
            chosen = "altair"
        else:
            chosen = "native"

    if title:
        st.markdown(f"**{title}**")

    if chosen == "plotly":
        _render_plotly(data, kind, x, y_list, color, height)
    elif chosen == "altair":
        _render_altair(data, kind, x, y_list, color)
    else:
        _render_native(data, kind, x, y_list, color)


# =====================================================
# engines
# =====================================================
def _render_plotly(
    data: pd.DataFrame,
    kind: ChartKind,
    x: str | None,
    y: list[str],
    color: str | None,
    height: int,
) -> None:
    import plotly.express as px

    try:
        if kind == "pie":
            if not y:
                st.warning("pie 图需要 y（value 字段）")
                return
            fig = px.pie(data, names=x, values=y[0], color=color)
        elif kind == "bar":
            fig = px.bar(data, x=x, y=y, color=color, barmode="group")
        elif kind == "scatter":
            fig = px.scatter(data, x=x, y=y, color=color)
        else:
            fig = px.line(data, x=x, y=y, color=color)
        fig.update_layout(height=height, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:  # noqa: BLE001
        st.warning(f"plotly 渲染失败，降级到原生: {e}")
        _render_native(data, kind, x, y, color)


def _render_altair(
    data: pd.DataFrame,
    kind: ChartKind,
    x: str | None,
    y: list[str],
    color: str | None,
) -> None:
    import altair as alt

    try:
        # 缺 x 字段时注入行号作为占位，避免 alt.value("") 被用作位置通道
        # （alt.value 仅用于颜色/大小等视觉属性，不能用作 X/Y 通道）。
        if not x and kind != "pie":
            data = data.reset_index().rename(columns={"index": "_row_idx"})
            x_field: str = "_row_idx"
            x_type = "O"  # ordinal
        else:
            x_field = x or ""
            x_type = "T" if kind == "line" else ("Q" if kind == "scatter" else "N")

        if kind == "pie":
            if not y:
                st.warning("pie 图需要 y（value 字段）")
                return
            base = alt.Chart(data).encode(
                theta=alt.Theta(field=y[0], type="quantitative"),
                color=alt.Color(field=x, type="nominal") if x else alt.value("#1f77b4"),
            )
            chart = base.mark_arc()
        elif kind == "bar":
            if not y:
                st.warning("bar 图需要 y（value 字段）")
                return
            chart = (
                alt.Chart(data)
                .mark_bar()
                .encode(
                    x=alt.X(f"{x_field}:{x_type}"),
                    y=alt.Y(f"{y[0]}:Q"),
                    color=alt.Color(color) if color else alt.value("#1f77b4"),
                )
            )
        elif kind == "scatter":
            if not y:
                st.warning("scatter 图需要 y（value 字段）")
                return
            chart = (
                alt.Chart(data)
                .mark_circle()
                .encode(
                    x=alt.X(f"{x_field}:{x_type}"),
                    y=alt.Y(f"{y[0]}:Q"),
                    color=alt.Color(color) if color else alt.value("#1f77b4"),
                )
            )
        else:
            # 兜底 line:单 y 列；多 y 用 plotly 路径已覆盖
            if not y:
                st.warning("line 图需要 y（value 字段）")
                return
            chart = (
                alt.Chart(data)
                .mark_line()
                .encode(
                    x=alt.X(f"{x_field}:{x_type}"),
                    y=alt.Y(f"{y[0]}:Q"),
                )
            )
        st.altair_chart(chart, use_container_width=True)
    except Exception as e:  # noqa: BLE001
        st.warning(f"altair 渲染失败，降级到原生: {e}")
        _render_native(data, kind, x, y, color)


def _render_native(
    data: pd.DataFrame,
    kind: ChartKind,
    x: str | None,
    y: list[str],
    color: str | None,
) -> None:
    """兜底:用 st 原生 line_chart / bar_chart / dataframe。"""
    plot_data = data.copy()
    if x and x in plot_data.columns:
        plot_data = plot_data.set_index(x)
    if kind == "pie":
        st.dataframe(plot_data, use_container_width=True)
    elif kind == "bar":
        st.bar_chart(plot_data[y] if y else plot_data, use_container_width=True)
    elif kind == "scatter":
        st.dataframe(plot_data, use_container_width=True)
    else:
        st.line_chart(plot_data[y] if y else plot_data, use_container_width=True)


# =====================================================
# helpers
# =====================================================
def render_kpi_row(metrics: dict[str, Any], *, container_key: str = "kpi_root") -> None:
    """渲染一行 KPI 指标卡（4 列布局）。"""
    cols = st.columns(min(4, max(1, len(metrics))))
    for col, (label, value) in zip(cols, metrics.items()):
        with col:
            st.metric(label=label, value=value)


def render_event_timeline(
    events: list[dict[str, Any]],
    *,
    ts_field: str = "ts",
    bucket_field: str | None = None,
    container_key: str = "timeline_root",
) -> None:
    """把事件按时间桶统计，画出 line/bar 图。

    events 形如 [{"ts": "...", "topic": "...", "payload": {...}}, ...]
    """
    import collections

    if not events:
        st.info("无事件数据。")
        return
    rows: list[dict[str, Any]] = []
    for e in events:
        ts = e.get(ts_field) or e.get("occurred_at") or ""
        bucket = e.get(bucket_field) if bucket_field else (e.get("topic") or "event")
        rows.append({"ts": str(ts)[:16], "bucket": str(bucket), "n": 1})
    if not rows:
        st.info("事件缺时间字段。")
        return
    df = pd.DataFrame(rows)
    grouped = df.groupby(["ts", "bucket"]).size().reset_index(name="count")
    pivot = grouped.pivot(index="ts", columns="bucket", values="count").fillna(0)
    st.line_chart(pivot, use_container_width=True)


__all__ = [
    "render",
    "render_kpi_row",
    "render_event_timeline",
    "ChartKind",
]
