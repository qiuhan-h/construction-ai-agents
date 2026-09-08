"""移动端卡片组件（6c.2）。

提供三个 render 函数，供 07_mobile 页面调用：
- ``render_kpi_grid(kpis)``    KPI 卡片网格（2 列移动 / 4 列平板）
- ``render_alert_list(alerts)`` 告警卡片列表（左边框分级色）
- ``render_project_grid(projects)`` 项目卡片列表

设计：
- 用 ``st.markdown(unsafe_allow_html=True)`` 渲染原生 HTML + CSS，
  确保在窄屏（375px）下不溢出、可触控；
- 缺数据时渲染空状态占位（不报错）；
- 不依赖第三方组件库（纯 Streamlit + HTML/CSS）。
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

import streamlit as st

_MOBILE_CSS_PATH = (
    Path(__file__).resolve().parents[1] / "assets" / "css" / "mobile.css"
)


def _load_mobile_css() -> str:
    """读取移动端 CSS（缺失时返回空串，不阻断渲染）。"""
    try:
        return _MOBILE_CSS_PATH.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return ""


def inject_mobile_css() -> None:
    """将移动端 CSS 注入页面（页面渲染前调用一次）。"""
    css = _load_mobile_css()
    if css:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def _open_container() -> None:
    """打开移动端容器 div。"""
    st.markdown(
        '<div class="caai-mobile caai-mobile-container">',
        unsafe_allow_html=True,
    )


def _close_container() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


# =====================================================
# KPI 卡片网格
# =====================================================
def render_kpi_grid(kpis: list[dict[str, Any]]) -> None:
    """渲染 KPI 卡片网格。

    kpis: [{"label": str, "value": str|number, "tone": "danger|success|warning|info"}]
    """
    if not kpis:
        st.markdown(
            '<div class="caai-empty-state">暂无 KPI 数据</div>',
            unsafe_allow_html=True,
        )
        return

    cards_html = []
    for item in kpis:
        tone = escape(str(item.get("tone", "info")))
        label = escape(str(item.get("label", "")))
        value = escape(str(item.get("value", "--")))
        cards_html.append(
            f'<div class="caai-kpi-card caai-kpi-{tone}">'
            f'<div class="caai-kpi-value">{value}</div>'
            f'<div class="caai-kpi-label">{label}</div>'
            f"</div>"
        )
    st.markdown(
        f'<div class="caai-kpi-grid">{"".join(cards_html)}</div>',
        unsafe_allow_html=True,
    )


# =====================================================
# 告警卡片列表
# =====================================================
def render_alert_list(alerts: list[dict[str, Any]]) -> None:
    """渲染告警卡片列表（左边框分级色）。

    alerts: [{"id","level","title","source","status","occurred_at"}]
    """
    if not alerts:
        st.markdown(
            '<div class="caai-empty-state">暂无告警 🎉</div>',
            unsafe_allow_html=True,
        )
        return

    cards_html = []
    for a in alerts:
        level = escape(str(a.get("level", "info")).lower())
        title = escape(str(a.get("title", ""))[:50])
        source = escape(str(a.get("source") or "—"))
        occurred = escape(str(a.get("occurred_at") or "")[:19])
        cards_html.append(
            f'<div class="caai-alert-card caai-level-{level}">'
            f'<p class="caai-alert-title">{title}</p>'
            f'<div class="caai-alert-meta">'
            f"<span>{source}</span>"
            f"<span>{occurred}</span>"
            f"</div></div>"
        )
    st.markdown(
        f'<div class="caai-alert-list">{"".join(cards_html)}</div>',
        unsafe_allow_html=True,
    )


# =====================================================
# 项目卡片列表
# =====================================================
def render_project_grid(projects: list[dict[str, Any]]) -> None:
    """渲染项目卡片列表。

    projects: [{"id","name","status","safety_score","open_alerts"}]
    """
    if not projects:
        st.markdown(
            '<div class="caai-empty-state">暂无项目</div>',
            unsafe_allow_html=True,
        )
        return

    cards_html = []
    for p in projects:
        name = escape(str(p.get("name", "")))
        status = escape(str(p.get("status", "active")).lower())
        score = p.get("safety_score")
        score_str = f"{score}" if score is not None else "--"
        open_alerts = p.get("open_alerts", 0)
        cards_html.append(
            f'<div class="caai-project-card">'
            f'<span class="caai-project-name">{name}</span>'
            f'<span class="caai-project-badge caai-badge-{status}">{status}</span>'
            f'<div class="caai-alert-meta">'
            f"<span>安全评分: {escape(str(score_str))}</span>"
            f"<span>告警: {open_alerts}</span>"
            f"</div></div>"
        )
    st.markdown(
        f'<div class="caai-project-grid">{"".join(cards_html)}</div>',
        unsafe_allow_html=True,
    )


# =====================================================
# 刷新栏
# =====================================================
def render_refresh_row(updated_at: str | None) -> None:
    """渲染更新时间栏。"""
    ts = escape(str(updated_at or "—")[:19])
    st.markdown(
        f'<div class="caai-refresh-row">'
        f'<span class="caai-updated-time">更新于 {ts}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_dashboard(
    *,
    kpis: list[dict[str, Any]] | None = None,
    alerts: list[dict[str, Any]] | None = None,
    projects: list[dict[str, Any]] | None = None,
    updated_at: str | None = None,
) -> None:
    """一次性渲染完整移动端首页（CSS + 容器 + KPI + 告警 + 项目）。

    供 07_mobile.render() 调用；缺数据时各区块独立渲染空状态。
    """
    inject_mobile_css()
    _open_container()
    render_refresh_row(updated_at)
    render_kpi_grid(kpis or [])
    st.markdown("#### 告警")
    render_alert_list(alerts or [])
    st.markdown("#### 项目")
    render_project_grid(projects or [])
    _close_container()


__all__ = [
    "inject_mobile_css",
    "render_kpi_grid",
    "render_alert_list",
    "render_project_grid",
    "render_refresh_row",
    "render_dashboard",
]
