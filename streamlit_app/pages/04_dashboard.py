"""Page 04 - orchestration visualization dashboard (stage 4e).

Four tabs:
  1. Overview: 4 KPI cards + last run + system status
  2. Workflows: registered workflow list + trigger form
  3. Runs: query by run_id, render run details
  4. Events: WS live stream (manual + auto reconnect)
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from streamlit_app.utils import (
    APIError,
    EventStreamClient,
    api_client,
    build_ws_base_from_http,
    get_state,
)

_TAB_NAMES = ["Overview", "Workflows", "Runs", "Events"]


def _api() -> Any:
    state = get_state()
    cli = api_client()
    cli.configure(base_url=state.api_base, token=state.token)
    return cli


def _event_client() -> EventStreamClient:
    state = get_state()
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
    return cached


def _on_event(event: dict[str, Any]) -> None:
    get_state().push_event(event)


def render() -> None:
    state = get_state()
    tabs = st.tabs(_TAB_NAMES)
    with tabs[0]:
        _render_overview(state)
    with tabs[1]:
        _render_workflows(state)
    with tabs[2]:
        _render_runs(state)
    with tabs[3]:
        _render_events(state)


def _render_overview(state) -> None:
    st.subheader("Overview")
    cli = _api()

    cards = {"workflows": 0, "runs": 0, "today": 0, "failed": 0}
    last_run_id = None
    last_status = None
    health = "?"
    ready = "?"

    try:
        stats = cli.get_stats()
        cards["workflows"] = stats.get("workflows", 0)
        cards["runs"] = stats.get("runs", 0)
        cards["today"] = stats.get("today_triggers", 0)
        cards["failed"] = stats.get("failed", 0)
        last_run_id = stats.get("last_run_id")
        last_status = stats.get("last_run_status")
    except APIError as e:
        st.error(f"stats failed: {e.message}")

    try:
        h = cli.healthz()
        health = h.get("status", "?")
    except APIError:
        health = "down"
    try:
        r = cli.readyz()
        ready = r.get("status", "?")
    except APIError:
        ready = "down"

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Workflows", cards["workflows"])
    col_b.metric("Runs (total)", cards["runs"])
    col_c.metric("Triggers today", cards["today"])
    col_d.metric("Failed runs", cards["failed"])

    st.divider()
    st.markdown("**System status**")
    c1, c2, c3 = st.columns(3)
    c1.write(f"- healthz: `{health}`")
    c2.write(f"- readyz: `{ready}`")
    c3.write(f"- backend: `{state.api_base}`")

    if last_run_id:
        st.success(f"Last run: `{last_run_id}` -> `{last_status}`")
        if st.button("Open last run", key="btn_last_run"):
            st.session_state["caai_active_run_id"] = last_run_id
            st.rerun()

    if st.button("Refresh", key="refresh_overview", type="secondary"):
        st.rerun()


def _render_workflows(state) -> None:
    st.subheader("Workflows (list + trigger)")
    cli = _api()
    try:
        wf_data = cli.list_workflows()
        items = (wf_data or {}).get("workflows", []) if isinstance(wf_data, dict) else []
    except APIError as e:
        st.error(f"workflow list failed: {e.message}")
        return

    if not items:
        st.info("no workflows")
        return

    cols = st.columns([1, 2])
    with cols[0]:
        st.markdown("**Registered**")
        for w in items:
            label = f"{w.get('name')} ({len(w.get('nodes', []))} nodes)"
            if st.button(label, key=f"wf_pick_{w.get('name')}", use_container_width=True):
                st.session_state["caai_selected_wf"] = w.get("name")
                st.rerun()

    with cols[1]:
        if "caai_selected_wf" not in st.session_state:
            st.session_state["caai_selected_wf"] = items[0]["name"]
        selected = st.session_state["caai_selected_wf"]
        st.markdown(f"**Detail / Trigger: `{selected}`**")
        wf_detail = {}
        try:
            wf_detail = cli.get_workflow(selected)
        except APIError as e:
            st.warning(f"workflow detail failed (using list): {e.message}")
        if wf_detail:
            st.json(wf_detail)

        st.markdown("---")
        st.markdown("**Trigger payload**")
        default_payload = _suggest_default_payload(selected)
        payload_text = st.text_area(
            "payload (JSON)",
            value=json.dumps(default_payload, ensure_ascii=False, indent=2),
            key=f"payload_{selected}",
            height=160,
        )
        c1, c2 = st.columns([1, 1])
        with c1:
            via_query = st.checkbox(
                "use ?payload={} (legacy URL)",
                value=False,
                key=f"via_query_{selected}",
                help="URL compat; otherwise JSON body (recommended)",
            )
        with c2:
            if st.button(
                f"Trigger {selected}",
                type="primary",
                key=f"trigger_{selected}",
                use_container_width=True,
            ):
                try:
                    parsed = json.loads(payload_text) if payload_text.strip() else {}
                except json.JSONDecodeError as e:
                    st.error(f"payload not JSON: {e}")
                    return
                try:
                    resp = cli.trigger_workflow(selected, parsed, via_query=via_query)
                except APIError as e:
                    state.last_error = e.message
                    st.error(f"trigger failed: {e.message} (code={e.code})")
                    return
                state.last_error = None
                run_id = resp.get("run_id")
                state.last_trigger_run_id = run_id
                st.session_state["caai_active_run_id"] = run_id
                st.success(f"triggered! run_id={run_id} state={resp.get('state')}")
                st.rerun()


def _suggest_default_payload(workflow_name: str) -> dict:
    if workflow_name == "monitor_alert_to_audit":
        return {"alert_id": "alt_demo", "level": "critical"}
    if workflow_name == "compliance_followup":
        return {"inspection_id": "insp_demo", "report_id": "rpt_demo"}
    if workflow_name == "regulation_record":
        return {"code": "GB-50068-2018", "version": "v1.0"}
    return {}


def _render_runs(state) -> None:
    st.subheader("Run history")
    cli = _api()

    rid = st.text_input(
        "Run ID",
        value=st.session_state.get("caai_active_run_id")
        or state.last_trigger_run_id
        or "",
        key="rid_input",
        placeholder="e.g. run_01M1...",
    )
    if st.button("Query", key="rid_query", type="primary") and rid:
        st.session_state["caai_active_run_id"] = rid
        st.rerun()

    st.divider()
    active = st.session_state.get("caai_active_run_id")
    if not active:
        st.info("enter a Run ID or trigger one from Workflows tab")
        return

    st.markdown(f"### Run `{active}`")
    try:
        run_info = cli.get_run(active)
    except APIError as e:
        st.error(f"query failed: {e.message}")
        return

    c1, c2, c3 = st.columns(3)
    c1.write(f"- status: `{run_info.get('status')}`")
    c2.write(f"- workflow: `{run_info.get('workflow')}`")
    c3.write(f"- tenant_id: `{run_info.get('tenant_id')}`")

    results = run_info.get("results") or {}
    errors = run_info.get("errors") or {}
    started_at = run_info.get("started_at")
    finished_at = run_info.get("finished_at")
    if started_at:
        st.caption(f"started_at = `{started_at}`")
    if finished_at:
        st.caption(f"finished_at = `{finished_at}`")

    st.markdown("**Node results**")
    if results:
        st.json(results)
    else:
        st.info("no node results yet")

    if errors:
        st.markdown("**Node errors**")
        st.json(errors)


def _render_events(state) -> None:
    st.subheader("Event stream (live)")
    ws_base = build_ws_base_from_http(state.api_base)

    cols = st.columns([2, 1, 1])
    with cols[0]:
        st.caption(
            f"subscribe `{ws_base}/api/v1/ws/events?topic={state.ws_topic}&tenant_id={state.tenant_id}`"
        )
    with cols[1]:
        if st.button("Start", key="ws_start", use_container_width=True):
            ok = _event_client().start()
            st.toast(
                "started" if ok else "websocket-client not installed",
                icon="ok" if ok else "warn",
            )
    with cols[2]:
        if st.button("Stop", key="ws_stop", use_container_width=True):
            _event_client().stop()
            st.toast("stopped", icon="ok")

    evc = _event_client()
    is_conn = evc.is_connected()
    st.markdown(
        f"- connection: {'connected' if is_conn else 'disconnected'}",
        help="WS background thread keeps heartbeat; auto-reconnect on close",
    )

    if st.button("Refresh events", key="ws_refresh"):
        st.rerun()

    events = state.events()
    if not events:
        st.info("no events yet (trigger a workflow or publish via API)")
        return

    rows = []
    for e in events[:100]:
        rows.append(
            {
                "type": e.get("type", "event"),
                "topic": e.get("topic", ""),
                "source": e.get("source", ""),
                "tenant_id": e.get("tenant_id", ""),
                "ts": e.get("occurred_at") or e.get("ts", ""),
                "payload": json.dumps(e.get("payload", {}), ensure_ascii=False)[:200],
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)
