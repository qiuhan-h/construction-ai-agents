"""通用告警展示组件（5a）。

设计：
- 与 site_monitor 联动：从 session_state.caai_timeline 过滤 site_monitor_agent
  / alert.* 主题的事件 → 卡片化渲染；
- 也支持外部传入任意 events 列表（兼容 03 之外页面复用）；
- 按 severity（critical / warning / info）自动配色 + icon；
- 点击"标记已读"按钮把事件从 caai_timeline 中删除；
- 不依赖第三方可视化库（纯 Streamlit 原生组件），沙箱装不上也能渲染。
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from streamlit_app.utils import get_state

# =====================================================
# severity 配置
# =====================================================
_SEVERITY_STYLES: dict[str, dict[str, str]] = {
    "critical": {"color": "#ff4b4b", "icon": "🔥", "label": "严重"},
    "warning": {"color": "#ffa500", "icon": "⚠️", "label": "警告"},
    "info": {"color": "#1e88e5", "icon": "ℹ️", "label": "提示"},
}


def _detect_severity(event: dict[str, Any]) -> str:
    """从 event.topic / payload 推断 severity。默认 info。"""
    topic = (event.get("topic") or "").lower()
    payload = event.get("payload") or {}
    if isinstance(payload, dict):
        level = str(payload.get("level") or payload.get("severity") or "").lower()
        if level in _SEVERITY_STYLES:
            return level
    if "critical" in topic or "alert.critical" in topic:
        return "critical"
    if "warn" in topic or "alert.warning" in topic:
        return "warning"
    return "info"


def _format_event(event: dict[str, Any]) -> dict[str, str]:
    """把 event 整理成渲染友好字段。"""
    sev = _detect_severity(event)
    style = _SEVERITY_STYLES[sev]
    payload = event.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {"data": payload}
    return {
        "severity": sev,
        "icon": style["icon"],
        "color": style["color"],
        "label": style["label"],
        "topic": str(event.get("topic") or ""),
        "source": str(event.get("source") or ""),
        "tenant": str(event.get("tenant_id") or ""),
        "ts": str(event.get("occurred_at") or event.get("ts") or ""),
        "message": str(
            payload.get("message")
            or payload.get("text")
            or payload.get("alert_message")
            or ""
        ),
        "summary": str(payload.get("summary") or payload.get("title") or ""),
    }


def _alert_identity(event: dict[str, Any]) -> tuple:
    """事件的稳定标识，用于精确定位"标记已读"目标。

    优先用业务 id 字段；缺失时回退到 topic+source+ts+payload 的组合哈希。
    """
    eid = event.get("id") or event.get("event_id") or event.get("eid")
    if eid:
        return ("id", str(eid))
    payload = event.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {"data": payload}
    return (
        "hash",
        str(event.get("topic") or ""),
        str(event.get("source") or ""),
        str(event.get("occurred_at") or event.get("ts") or ""),
        str(payload.get("message") or payload.get("text") or ""),
        str(payload.get("summary") or payload.get("title") or ""),
    )


# =====================================================
# public API
# =====================================================
def render(
    events: list[dict[str, Any]] | None = None,
    *,
    title: str = "实时告警",
    max_items: int = 50,
    show_filters: bool = True,
    show_ack_button: bool = True,
    container_key: str = "alert_display_root",
) -> None:
    """渲染告警面板。

    Parameters
    ----------
    events : list[dict] | None
        事件列表；None 表示从 session_state.caai_timeline 取
        （默认过滤 source 包含 site_monitor_agent 或 topic 以 alert. 开头）。
    title : str
        卡片标题。
    max_items : int
        最多展示多少条（按时间倒序）。
    show_filters : bool
        是否展示 severity 过滤多选框。
    show_ack_button : bool
        是否展示"标记已读"按钮（仅当 events 为 None 时生效——删除 session_state
        中对应事件）。
    container_key : str
        容器 key 前缀，避免多实例冲突。
    """
    state = get_state()
    if events is None:
        all_events = state.events()
        events = [
            e for e in all_events
            if "site_monitor" in str(e.get("source", "")).lower()
            or str(e.get("topic", "")).startswith("alert.")
        ]

    st.markdown(f"### {title}")
    if not events:
        st.info("暂无告警事件。可触发 site_monitor_agent 工作流或等待现场上报。")
        return

    # severity 过滤
    if show_filters:
        sev_counts = {s: 0 for s in _SEVERITY_STYLES}
        for e in events[:max_items]:
            sev_counts[_detect_severity(e)] += 1
        selected = st.multiselect(
            "按严重度过滤",
            options=list(_SEVERITY_STYLES.keys()),
            default=list(_SEVERITY_STYLES.keys()),
            format_func=lambda s: f"{_SEVERITY_STYLES[s]['icon']} {_SEVERITY_STYLES[s]['label']} ({sev_counts[s]})",
            key=f"{container_key}_filter",
        )
    else:
        selected = list(_SEVERITY_STYLES.keys())

    rendered = 0
    for i, event in enumerate(events[:max_items]):
        row = _format_event(event)
        if row["severity"] not in selected:
            continue
        with st.container(border=True):
            cols = st.columns([1, 6, 2])
            with cols[0]:
                st.markdown(
                    f"<div style='font-size:2em;text-align:center'>{row['icon']}</div>",
                    unsafe_allow_html=True,
                )
            with cols[1]:
                st.markdown(
                    f"<span style='color:{row['color']};font-weight:bold'>"
                    f"{row['label']}</span> &nbsp; "
                    f"<code>{row['topic']}</code>",
                    unsafe_allow_html=True,
                )
                if row["summary"]:
                    st.markdown(f"**{row['summary']}**")
                if row["message"]:
                    st.caption(row["message"])
                meta_bits = []
                if row["source"]:
                    meta_bits.append(f"src=`{row['source']}`")
                if row["tenant"]:
                    meta_bits.append(f"tenant=`{row['tenant']}`")
                if row["ts"]:
                    meta_bits.append(f"ts=`{row['ts']}`")
                if meta_bits:
                    st.caption(" · ".join(meta_bits))
            with cols[2]:
                if show_ack_button and events is None:
                    ack_key = f"{container_key}_ack_{i}_{hash(str(event)) % 100000}"
                    if st.button("标记已读", key=ack_key, use_container_width=True):
                        # 仅移除当前点击的告警，不影响其他告警
                        target_id = _alert_identity(event)
                        remaining = [
                            e for e in state.events()
                            if _alert_identity(e) != target_id
                        ]
                        state._set("caai_timeline", remaining)
                        st.rerun()
        rendered += 1

    if rendered == 0:
        st.info("当前过滤条件下无告警。")
    else:
        st.caption(f"共 {rendered} 条告警（事件缓冲 {len(events)} 条）")


__all__ = ["render", "_SEVERITY_STYLES", "_detect_severity"]
