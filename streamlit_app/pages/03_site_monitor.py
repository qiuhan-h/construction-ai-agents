"""Page 03 - 现场监控工作台（5a）。

设计：
- 5 区块:① 智能体卡片 ② WS 实时事件流（启动/停止 + 状态指示）
  ③ 实时告警面板（复用 components/alert_display） ④ 触发监控工作流
  ⑤ 历史报告;
- WS 客户端复用 utils.websocket_client.EventStreamClient（同 04_dashboard）;
- 过滤 source=site_monitor_agent 的事件推到 alert_display。
"""

from __future__ import annotations

import time
from typing import Any

import streamlit as st

from streamlit_app.components import alert_display, report_viewer
from streamlit_app.utils import (
    APIError,
    EventStreamClient,
    api_client,
    build_ws_base_from_http,
    get_state,
)


AGENT_NAME = "site_monitor_agent"
PAGE_TITLE = "现场监控"
_FALLBACK_SKILLS = ["alert_judge", "daily_report", "trend_report"]


def _api() -> Any:
    state = get_state()
    cli = api_client()
    cli.configure(base_url=state.api_base, token=state.token)
    return cli


def _on_event(event: dict[str, Any]) -> None:
    """WS 事件回调：推到 session_state.caai_timeline。"""
    get_state().push_event(event)


def _get_event_client(state: Any) -> EventStreamClient:
    cached = state._get("caai_event_client")
    if cached is None:
        ws_base = build_ws_base_from_http(state.api_base)
        client = EventStreamClient(
            ws_url=ws_base,
            topic=state.ws_topic,
            tenant_id=state.tenant_id,
            on_event=_on_event,
            reconnect_max_delay=5.0,
        )
        state._set("caai_event_client", client)
        cached = client
    return cached  # type: ignore[return-value]


def _render_agent_card(card: dict[str, Any]) -> None:
    st.markdown("### 智能体卡片")
    if "error" in card:
        st.error(f"卡片加载失败: {card['error']}")
        return
    cols = st.columns(4)
    cols[0].markdown(f"**名称**\n\n`{card.get('name', AGENT_NAME)}`")
    cols[1].markdown(f"**版本**\n\n`{card.get('version', '?')}`")
    cols[2].markdown(f"**协议**\n\n`{card.get('protocol_version', '?')}`")
    cols[3].markdown(f"**技能数**\n\n`{len(card.get('skills') or [])}`")
    if card.get("description"):
        st.caption(card["description"])
    skills = card.get("skills") or []
    if skills:
        with st.expander(f"技能列表 ({len(skills)})", expanded=False):
            for s in skills:
                if isinstance(s, dict):
                    st.markdown(
                        f"- **{s.get('skill_id', s.get('id', '?'))}** — "
                        f"{s.get('description', '')}"
                    )


def _render_ws_panel(state: Any) -> None:
    st.markdown("### 事件流（WebSocket）")
    ws_base = build_ws_base_from_http(state.api_base)
    sub_url = (
        f"{ws_base}/api/v1/ws/events?topic={state.ws_topic}"
        f"&tenant_id={state.tenant_id}"
    )
    cols = st.columns([3, 1, 1, 1])
    cols[0].caption(f"订阅: `{sub_url}`")
    if cols[1].button("Start", key="site_ws_start", use_container_width=True):
        ok = _get_event_client(state).start()
        st.toast(
            "started" if ok else "websocket-client 未安装",
            icon="ok" if ok else "warn",
        )
    if cols[2].button("Stop", key="site_ws_stop", use_container_width=True):
        _get_event_client(state).stop()
        st.toast("stopped", icon="ok")
    if cols[3].button("Refresh", key="site_ws_refresh", use_container_width=True):
        st.rerun()

    evc = _get_event_client(state)
    is_conn = evc.is_connected()
    st.markdown(
        f"- 连接状态: **{'connected' if is_conn else 'disconnected'}** · "
        f"缓冲事件: **{len(state.events())}**"
    )


def _render_invoke_form() -> None:
    st.markdown("### 触发监控")
    cli = _api()
    card: dict[str, Any] = {}
    try:
        card = cli.get_agent_card(AGENT_NAME)
    except APIError as e:
        st.error(f"卡片加载失败: {e.message}")

    skill_options: list[str] = []
    for s in card.get("skills") or []:
        if isinstance(s, dict):
            sid = s.get("skill_id") or s.get("id")
            if sid:
                skill_options.append(str(sid))
        else:
            skill_options.append(str(s))
    if not skill_options:
        skill_options = list(_FALLBACK_SKILLS)

    skill = st.selectbox(
        "选择 skill",
        options=skill_options,
        key="site_skill",
        help="监控类型：告警判断 / 日报 / 趋势",
    )

    cols = st.columns(2)
    project_id = cols[0].text_input(
        "项目 ID", value="prj_demo", key="site_prj"
    )
    alert_id = cols[1].text_input(
        "告警 ID", value="alt_demo", key="site_alt"
    )

    default_msg = (
        "请对项目 {prj} 的告警 {alt} 执行 {sk}。"
        "若为 critical 级别，立即触发 safety_audit_agent 复审。"
    ).format(prj=project_id, alt=alert_id, sk=skill)
    message = st.text_area(
        "监控要求（文本）",
        value=default_msg,
        key="site_msg",
        height=100,
    )

    if st.button("触发", type="primary", key="site_submit"):
        try:
            resp = cli._request(
                "POST",
                f"/api/v1/agents/{AGENT_NAME}/invoke",
                json_body={
                    "method": "agent.send_message",
                    "params": {
                        "skill": skill,
                        "project_id": project_id,
                        "alert_id": alert_id,
                        "message": {"text": message},
                    },
                },
            )
        except APIError as e:
            st.error(f"触发失败: {e.message} (code={e.code})")
            return
        st.session_state["caai_active_run_id"] = resp.get("task_id")
        st.success(f"已触发! task_id=`{resp.get('task_id')}`")
        st.json(resp)


def _render_history() -> None:
    st.markdown("### 历史监控报告")
    cli = _api()
    try:
        page_data = cli.list_reports(project_id=None, page=1, page_size=20)
    except APIError as e:
        st.error(f"列表拉取失败: {e.message}")
        return
    items: list[dict[str, Any]] = []
    if isinstance(page_data, dict):
        items = page_data.get("items") or page_data.get("reports") or []
    if not items:
        st.info("尚无历史报告。")
        return

    rows: list[dict[str, Any]] = []
    for it in items:
        title = str(it.get("title", ""))
        if any(k in title.lower() for k in ("监控", "monitor", "alert", "日报", "daily", "trend")):
            rows.append(it)
    if not rows:
        rows = items[:10]

    report_viewer.render_list(
        rows, title="历史监控报告", container_key="site_history"
    )


def render() -> None:
    state = get_state()
    st.markdown(f"## 📹 {PAGE_TITLE}")
    st.caption(f"agent = `{AGENT_NAME}` · tenant = `{state.tenant_id}`")

    tab_alert, tab_ws, tab_invoke, tab_history = st.tabs(
        ["实时告警", "事件流", "触发监控", "历史报告"]
    )
    with tab_alert:
        alert_display.render(title="现场告警", container_key="site_alert_root")
    with tab_ws:
        _render_ws_panel(state)
    with tab_invoke:
        _render_invoke_form()
    with tab_history:
        _render_history()


__all__ = ["render"]
