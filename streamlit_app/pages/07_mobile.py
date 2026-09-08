"""Page 07 - 移动端响应式首页（6c.2）。

消费 6c.1 移动端精简 API：
  GET /api/v1/mobile/dashboard   聚合首页数据
  GET /api/v1/mobile/alerts      告警列表
  GET /api/v1/mobile/projects    项目卡片列表

设计：
- mobile-first 单列布局，窄屏（375px）不溢出；
- 用 mobile_card 组件渲染 KPI / 告警 / 项目卡片（原生 HTML+CSS）；
- API 不可达时渲染空状态占位（不报错），与降级策略一致；
- 顶部下拉刷新按钮（手动触发，不自动轮询）。
"""

from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from streamlit_app.components.mobile_card import (
    render_alert_list,
    render_kpi_grid,
    render_project_grid,
    render_refresh_row,
    inject_mobile_css,
)
from streamlit_app.utils import APIError, api_client, get_state

logger = logging.getLogger("streamlit_app.pages.07_mobile")

MOBILE_PAGE_ID = "07_mobile"


def _api() -> Any:
    """获取已配置的 API 客户端。"""
    state = get_state()
    cli = api_client()
    cli.configure(base_url=state.api_base, token=state.token)
    return cli


def _fetch_dashboard() -> dict | None:
    """拉取移动端首页聚合数据；失败返回 None。"""
    try:
        return _api().mobile_dashboard()
    except APIError as e:
        logger.debug("mobile_dashboard 失败: %s", e.message)
        st.toast(f"首页数据拉取失败: {e.message}", icon="⚠️")
        return None
    except Exception as e:  # noqa: BLE001
        logger.debug("mobile_dashboard 异常: %s", e)
        return None


def _build_kpis(dashboard: dict | None) -> list[dict[str, Any]]:
    """从 dashboard 聚合 KPI 卡片数据。"""
    if not dashboard:
        return []

    open_alerts = dashboard.get("open_alerts", 0)
    safety_score = dashboard.get("safety_score")
    score_display = f"{safety_score}" if safety_score is not None else "--"
    alert_tone = "danger" if open_alerts > 0 else "success"
    score_tone = "success"
    if safety_score is not None:
        if safety_score < 60:
            score_tone = "danger"
        elif safety_score < 80:
            score_tone = "warning"

    return [
        {"label": "未处置告警", "value": open_alerts, "tone": alert_tone},
        {"label": "安全评分", "value": score_display, "tone": score_tone},
        {"label": "项目数", "value": len(dashboard.get("projects", [])), "tone": "info"},
        {"label": "租户", "value": str(dashboard.get("tenant_name", ""))[:8], "tone": "info"},
    ]


def render() -> None:
    """渲染移动端响应式首页。"""
    state = get_state()
    inject_mobile_css()

    # 顶部标题 + 刷新
    st.markdown(
        f'<div class="caai-mobile caai-mobile-container">',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.title("📱 移动工作台")
    st.caption("6c.2 响应式移动端首页 · 数据来自 /api/v1/mobile/*")

    col_refresh, col_mode = st.columns([3, 1])
    with col_refresh:
        if st.button("🔄 刷新", use_container_width=True, type="primary"):
            st.session_state["caai_mobile_refresh"] = True
            st.rerun()
    with col_mode:
        if st.button("卡片/列表", use_container_width=True):
            st.session_state["caai_mobile_list_mode"] = not st.session_state.get(
                "caai_mobile_list_mode", False
            )

    st.divider()

    # 拉取数据
    dashboard = _fetch_dashboard()
    kpis = _build_kpis(dashboard)
    alerts = (dashboard or {}).get("alerts", [])
    projects = (dashboard or {}).get("projects", [])
    updated_at = (dashboard or {}).get("updated_at")

    # 如果列表模式下独立拉取告警/项目
    if st.session_state.get("caai_mobile_list_mode"):
        alerts = _fetch_alerts() or alerts
        projects = _fetch_projects() or projects

    # 渲染
    render_refresh_row(updated_at)
    render_kpi_grid(kpis)

    st.markdown("#### 🚨 告警")
    render_alert_list(alerts)

    st.markdown("#### 🏗️ 项目")
    render_project_grid(projects)

    # 底部说明
    st.caption("数据精简自桌面端共享仓储 · 响应体 < 5KB")


def _fetch_alerts() -> list:
    """独立拉取告警列表（列表模式）。"""
    try:
        return _api().mobile_alerts() or []
    except (APIError, Exception):  # noqa: BLE001
        return []


def _fetch_projects() -> list:
    """独立拉取项目列表（列表模式）。"""
    try:
        return _api().mobile_projects() or []
    except (APIError, Exception):  # noqa: BLE001
        return []


__all__ = ["render", "MOBILE_PAGE_ID"]
