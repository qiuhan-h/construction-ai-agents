"""Streamlit 多页应用入口（4e）。

布局：
- sidebar：环境配置（API base / token / 租户 / 用户）→ 一键保存到 session_state；
- 顶部 banner：当前 app 名 + 版本 + health 状态（按钮触发 refresh）；
- 主体：pages/ 下的 6 个页面通过顶部按钮切换（4e 默认停在 04_dashboard）。

设计：
- 不依赖 orchestrator 内部模块，仅通过 ``api_client`` 与后端交互；
- 4e 仅实现 04_dashboard，其它 5 个 page 留占位文本（5a 阶段实做）。
"""

from __future__ import annotations

import streamlit as st

from streamlit_app.utils import (
    APIError,
    api_client,
    get_state,
    init_state,
)

APP_NAME = "建筑工程智能体集群"
APP_VERSION = "0.4.0-e"

PAGES = [
    {"id": "01_safety_audit", "title": "01 安全审核", "icon": "🛡️"},
    {"id": "02_compliance", "title": "02 合规校验", "icon": "📋"},
    {"id": "03_site_monitor", "title": "03 现场监控", "icon": "📡"},
    {"id": "04_dashboard", "title": "04 编排可视化", "icon": "📊"},
    {"id": "05_gis_viewer", "title": "05 GIS 视图", "icon": "🗺️"},
    {"id": "06_agent_management", "title": "06 智能体管理", "icon": "⚙️"},
    {"id": "07_mobile", "title": "07 移动工作台", "icon": "📱"},
]


def _render_sidebar(state) -> None:
    """渲染左侧配置面板。"""
    with st.sidebar:
        st.markdown(f"### {APP_NAME}")
        st.caption(f"v{APP_VERSION} (4e: 编排可视化)")
        st.divider()
        st.markdown("**连接配置**")
        api_base = st.text_input(
            "API Base URL", value=state.api_base, key="_in_api_base"
        )
        token = st.text_input(
            "Authorization Token", value=state.token, type="password",
            key="_in_token",
        )
        tenant_id = st.text_input(
            "Tenant ID", value=state.tenant_id, key="_in_tenant"
        )
        user_id = st.text_input(
            "User ID", value=state.user_id, key="_in_user"
        )
        if st.button("保存并连接", type="primary", use_container_width=True):
            state.api_base = api_base
            state.token = token
            state.tenant_id = tenant_id
            state.user_id = user_id
            api_client().configure(base_url=api_base, token=token)
            st.success("已保存配置")
            st.rerun()

        st.divider()
        st.markdown("**健康检查**")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("healthz", use_container_width=True):
                _check_health(only="healthz")
        with c2:
            if st.button("readyz", use_container_width=True):
                _check_health(only="readyz")


def _check_health(*, only: str) -> None:
    api = api_client()
    api.configure(base_url=get_state().api_base, token=get_state().token)
    try:
        if only == "healthz":
            data = api.healthz()
            st.toast(f"healthz: {data.get('status', '?')}", icon="✅")
        else:
            data = api.readyz()
            ready = data.get("status", "?")
            subs = data.get("subscribers", "?")
            st.toast(f"readyz: {ready} (subscribers={subs})", icon="��")
    except APIError as e:
        st.error(f"{only} 失败: {e.message}")


def _route() -> None:
    """侧边栏选择路由到对应页面。"""
    state = get_state()
    _render_sidebar(state)

    st.title(f"�� {APP_NAME}")
    st.caption(f"v{APP_VERSION} · 4e 编排可视化 Dashboard")

    with st.container(border=True):
        cols = st.columns(3)
        # 当前激活页 id（与 _render_active_page 保持一致，默认 04_dashboard）
        active_page = st.session_state.get("caai_active_page", "04_dashboard")
        for i, p in enumerate(PAGES):
            with cols[i % 3]:
                # 用页 id 而非硬编码下标判断，避免重排 PAGES 后默认按钮失效
                is_active = (p["id"] == active_page)
                btn_label = f"**{p['title']}**" if is_active else p["title"]
                if st.button(
                    f"{p['icon']} {btn_label}",
                    key=f"goto_{p['id']}",
                    disabled=bool(is_active),
                    use_container_width=True,
                ):
                    st.session_state["caai_active_page"] = p["id"]
                    st.rerun()

    st.divider()
    _render_active_page()


def _render_active_page() -> None:
    active = st.session_state.get("caai_active_page", "04_dashboard")
    from streamlit_app.pages import render as _render

    _render(active)


def main() -> None:
    st.set_page_config(
        page_title=f"{APP_NAME} {APP_VERSION}",
        page_icon="🏗️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    # --- PWA 注入：manifest + service worker + 移动端 meta ---
    _inject_pwa()
    # --- 移动端样式 ---
    st.markdown(
        '<link rel="stylesheet" href="assets/css/mobile.css">',
        unsafe_allow_html=True,
    )
    init_state(force=False)
    st.session_state.setdefault("caai_active_page", "04_dashboard")
    _route()


def _inject_pwa() -> None:
    """注入 PWA 相关的 HTML 头元素（manifest + 移动端 meta）。"""
    pwa_html = """
    <head>
        <link rel="manifest" href="assets/manifest.json">
        <meta name="theme-color" content="#2c3e50">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="default">
        <meta name="mobile-web-app-capable" content="yes">
    </head>
    <script>
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', function() {
            navigator.serviceWorker.register('assets/service-worker.js')
                .catch(function(err) { console.log('SW registration failed:', err); });
        });
    }
    </script>
    """
    st.markdown(pwa_html, unsafe_allow_html=True)


main()
