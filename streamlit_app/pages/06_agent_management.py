"""Page 06 - 智能体管理（5a）。

设计：
- 4 区块:① 白名单 + 已实例化状态 ② 选定 agent 的 card 详情
  ③ 自定义调用（自由填 method + params） ④ 任务历史（按 agent 过滤）;
- 复用 utils/api_client.list_supported_agents + get_agent_card;
- 自由调用用于调试 / 高级用法。
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from streamlit_app.utils import (
    APIError,
    api_client,
    get_state,
)


PAGE_TITLE = "智能体管理"


def _api() -> Any:
    state = get_state()
    cli = api_client()
    cli.configure(base_url=state.api_base, token=state.token)
    return cli


def _render_agent_list() -> str | None:
    """渲染白名单 + 已实例化列表,返回用户点击的 agent_name。"""
    cli = _api()
    st.markdown("### 智能体清单")
    cols = st.columns(2)
    with cols[0]:
        st.markdown("**白名单（/api/v1/agents/supported）**")
        try:
            supported = cli.list_supported_agents()
        except APIError as e:
            st.error(f"加载失败: {e.message}")
            supported = []
        for name in supported:
            st.markdown(f"- `{name}`")
    with cols[1]:
        st.markdown("**当前租户已实例化（/api/v1/agents）**")
        try:
            data = cli._request("GET", "/api/v1/agents")
            agents = []
            if isinstance(data, dict):
                agents = data.get("agents") or []
            elif isinstance(data, list):
                agents = data
            for a in agents:
                if not isinstance(a, dict):
                    continue
                name = a.get("name", "?")
                ver = a.get("version", "?")
                inst = "✓" if a.get("instantiated") else "○"
                skills_n = len(a.get("skills") or [])
                st.markdown(
                    f"- {inst} `{name}` (v{ver}, {skills_n} skills)"
                )
            if not agents:
                st.info("尚无实例化记录")
        except APIError as e:
            st.error(f"加载失败: {e.message}")

    # 选定入口
    try:
        supported_now = cli.list_supported_agents()
    except APIError:
        supported_now = []
    if not supported_now:
        return None
    return st.selectbox(
        "选择智能体查看 card",
        options=supported_now,
        key="agent_mgmt_select",
    )


def _render_card(agent_name: str) -> None:
    """渲染选定的 agent card。"""
    cli = _api()
    st.markdown(f"### Card: `{agent_name}`")
    try:
        card = cli.get_agent_card(agent_name)
    except APIError as e:
        st.error(f"card 加载失败: {e.message}")
        return

    cols = st.columns(4)
    cols[0].markdown(f"**名称**\n\n`{card.get('name', agent_name)}`")
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


def _render_free_invoke() -> None:
    """自由调用表单（method + params JSON）。"""
    cli = _api()
    st.markdown("### 自由调用（高级）")
    state = get_state()
    try:
        supported = cli.list_supported_agents()
    except APIError:
        supported = ["safety_audit_agent", "compliance_agent", "site_monitor_agent"]

    cols = st.columns(2)
    agent = cols[0].selectbox(
        "agent", options=supported, key="agent_free_select"
    )
    method = cols[1].text_input(
        "method", value="agent.send_message", key="agent_free_method"
    )

    default_params = {
        "skill": "default",
        "project_id": "prj_demo",
        "message": {"text": "test"},
    }
    params_text = st.text_area(
        "params (JSON)",
        value=json.dumps(default_params, ensure_ascii=False, indent=2),
        key="agent_free_params",
        height=180,
    )

    if st.button("调用", type="primary", key="agent_free_submit"):
        try:
            parsed = json.loads(params_text) if params_text.strip() else {}
        except json.JSONDecodeError as e:
            st.error(f"params 不是 JSON: {e}")
            return
        try:
            resp = cli._request(
                "POST",
                f"/api/v1/agents/{agent}/invoke",
                json_body={"method": method, "params": parsed},
            )
        except APIError as e:
            st.error(f"调用失败: {e.message} (code={e.code})")
            return

        st.session_state["caai_active_run_id"] = resp.get("task_id")
        st.success(f"task_id=`{resp.get('task_id')}`")
        st.json(resp)


def _render_task_history() -> None:
    """显示与本租户相关的任务记录（来自 /api/v1/tasks 历史列表，4d 是否实现？）。"""
    cli = _api()
    state = get_state()
    st.markdown("### 最近任务")
    # 4d 已实做 /api/v1/tasks/{task_id} 查询，但 list 端点不一定有；
    # 这里展示 session_state.last_trigger_run_id 与轮询结果
    rid = state.last_trigger_run_id
    if not rid:
        st.info("尚无最近任务记录。请先触发智能体或工作流。")
        return
    st.markdown(f"最近 run_id: `{rid}`")
    if st.button("查询状态", key="agent_mgmt_query", type="secondary"):
        try:
            data = cli._request("GET", f"/api/v1/tasks/{rid}")
            st.json(data)
        except APIError as e:
            st.error(f"查询失败: {e.message}")


def render() -> None:
    state = get_state()
    st.markdown(f"## ⚙️ {PAGE_TITLE}")
    st.caption(
        f"tenant = `{state.tenant_id}` · "
        f"backend = `{state.api_base}`"
    )

    tab_list, tab_card, tab_invoke, tab_tasks = st.tabs(
        ["清单", "Card", "自由调用", "最近任务"]
    )
    with tab_list:
        _render_agent_list()
    with tab_card:
        sel = st.session_state.get("agent_mgmt_select")
        if sel:
            _render_card(sel)
        else:
            st.info("请先在『清单』中选择智能体")
    with tab_invoke:
        _render_free_invoke()
    with tab_tasks:
        _render_task_history()


__all__ = ["render"]
