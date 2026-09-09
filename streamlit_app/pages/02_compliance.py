"""Page 02 - 合规校验工作台（5a）。

设计：与 01_safety_audit 同构，差异：
- AGENT_NAME = compliance_agent
- skill 列表来自 card，但兜底用 fire_review / seismic_review / energy_review
  / green_review（agents/compliance_agent/__init__.py 暴露的 4 个 PROMPT_*）。
"""

from __future__ import annotations

import time
from typing import Any

import streamlit as st

from streamlit_app.components import report_viewer
from streamlit_app.utils import (
    APIError,
    api_client,
    get_state,
)

AGENT_NAME = "compliance_agent"
PAGE_TITLE = "合规校验"
_FALLBACK_SKILLS = ["fire_review", "seismic_review", "energy_review", "green_review"]


def _api() -> Any:
    state = get_state()
    cli = api_client()
    cli.configure(base_url=state.api_base, token=state.token)
    return cli


def _load_agent_card(cli: Any) -> dict[str, Any]:
    try:
        return cli.get_agent_card(AGENT_NAME)
    except APIError as e:
        return {"error": e.message, "skills": []}


def _invoke_compliance(
    cli: Any,
    skill: str,
    message: str,
    project_id: str,
    inspection_id: str,
) -> dict[str, Any]:
    return cli._request(
        "POST",
        f"/api/v1/agents/{AGENT_NAME}/invoke",
        json_body={
            "method": "agent.send_message",
            "params": {
                "skill": skill,
                "project_id": project_id,
                "inspection_id": inspection_id,
                "message": {"text": message},
            },
        },
    )


def _poll_task(cli: Any, task_id: str, max_seconds: float = 15.0) -> dict[str, Any]:
    deadline = time.time() + max_seconds
    last: dict[str, Any] = {}
    while time.time() < deadline:
        try:
            last = cli._request("GET", f"/api/v1/tasks/{task_id}")
        except APIError as e:
            last = {"error": e.message, "state": "unknown"}
        state_val = str(last.get("state") or last.get("status") or "").lower()
        if state_val in ("completed", "failed", "cancelled", "success", "error"):
            break
        time.sleep(1.0)
    return last


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


def _render_invoke_form() -> None:
    st.markdown("### 触发合规校验")
    cli = _api()
    card = _load_agent_card(cli)

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
        key="compliance_skill",
        help="合规类型：防火 / 抗震 / 节能 / 绿色",
    )

    cols = st.columns(2)
    project_id = cols[0].text_input(
        "项目 ID", value="prj_demo", key="comp_prj"
    )
    inspection_id = cols[1].text_input(
        "巡检 ID", value="insp_demo", key="comp_insp"
    )

    default_msg = (
        f"请对项目 {project_id} 的巡检 {inspection_id} 执行 {skill}，"
        "依据 GB 50016（防火）/ GB 50011（抗震）/ GB 50189（节能）/"
        "GB 50378（绿色建筑）规范条款。"
    )
    message = st.text_area(
        "校验要求（文本）",
        value=default_msg,
        key="comp_msg",
        height=120,
    )

    if st.button("提交校验", type="primary", key="comp_submit"):
        try:
            resp = _invoke_compliance(cli, skill, message, project_id, inspection_id)
        except APIError as e:
            st.error(f"提交失败: {e.message} (code={e.code})")
            return

        task_id = resp.get("task_id") or resp.get("data", {}).get("task_id")
        if not task_id:
            st.warning("未返回 task_id，请检查后端日志")
            st.json(resp)
            return

        st.session_state["caai_active_run_id"] = task_id
        st.success(f"已提交! task_id=`{task_id}`，开始轮询...")

        with st.spinner("任务执行中..."):
            final = _poll_task(cli, task_id, max_seconds=15.0)

        st.markdown("**最终状态**")
        st.json(final)

        report_id = (
            (final.get("results") or {}).get("report_id")
            or (final.get("data") or {}).get("report_id")
        )
        if report_id:
            try:
                detail = cli._request("GET", f"/api/v1/reports/{report_id}")
                st.markdown("**生成报告**")
                report_viewer.render(detail, container_key="comp_report")
            except APIError as e:
                st.warning(f"报告拉取失败: {e.message}")


def _render_history() -> None:
    st.markdown("### 历史合规报告")
    cli = _api()
    try:
        page_data = cli.list_reports(project_id=None, page=1, page_size=20)
    except APIError as e:
        st.error(f"列表拉取失败: {e.message}")
        return
    items = []
    if isinstance(page_data, dict):
        items = page_data.get("items") or page_data.get("reports") or []
    if not items:
        st.info("尚无历史报告。")
        return

    rows: list[dict[str, Any]] = []
    for it in items:
        title = str(it.get("title", ""))
        if any(k in title.lower() for k in ("合规", "compliance", "fire", "seismic", "energy", "green")):
            rows.append(it)
    if not rows:
        rows = items[:10]

    report_viewer.render_list(
        rows, title="历史合规报告", container_key="comp_history"
    )


def render() -> None:
    state = get_state()
    st.markdown(f"## 📜 {PAGE_TITLE}")
    st.caption(f"agent = `{AGENT_NAME}` · tenant = `{state.tenant_id}`")

    tab_card, tab_invoke, tab_history = st.tabs(["卡片", "触发", "历史报告"])
    with tab_card:
        _render_agent_card(_load_agent_card(_api()))
    with tab_invoke:
        _render_invoke_form()
    with tab_history:
        _render_history()


__all__ = ["render"]
