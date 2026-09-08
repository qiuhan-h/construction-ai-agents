"""通用报告查看器组件（5a）。

设计：
- 接受 report 字典(从 /api/v1/reports/{id} 拉取)→ 自动识别 Markdown / HTML / 纯文本;
- 渲染:Markdown → st.markdown;HTML → components.v1.html(沙箱模式);
- 下载:提供 st.download_button,按报告 metadata.format 选择 md / html / json;
- 若未来 5b.1 实做 PDF,可扩展 format=pdf → st.download_button 拉 bytes;
- 不强制依赖 markdown 库（用 st.markdown 原生支持）。
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from streamlit_app.utils import APIError, api_client


# =====================================================
# 报告内容提取
# =====================================================
def _extract_content(report: dict[str, Any]) -> tuple[str, str]:
    """从报告字典提取内容 + 推断格式(md / html / text / json)。

    返回 (content, format)。
    """
    # 常见字段顺序尝试
    for key in ("content_md", "markdown", "content_markdown", "content"):
        v = report.get(key)
        if isinstance(v, str) and v.strip():
            return v, "md"

    for key in ("content_html", "html", "html_content"):
        v = report.get(key)
        if isinstance(v, str) and v.strip():
            return v, "html"

    # data 字段内嵌套
    data = report.get("data") or {}
    if isinstance(data, dict):
        for key in ("content_md", "markdown", "content", "content_html", "html"):
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                return v, "md" if "md" in key or "markdown" in key or key == "content" else "html"

    # report.data 嵌套
    nested = report.get("report") or {}
    if isinstance(nested, dict):
        v = nested.get("content") or nested.get("markdown")
        if isinstance(v, str) and v.strip():
            return v, "md"

    # 兜底:把整个 report 序列化为 JSON
    return json.dumps(report, ensure_ascii=False, indent=2), "json"


# =====================================================
# public API
# =====================================================
def render(
    report: dict[str, Any] | None,
    *,
    title: str | None = None,
    show_metadata: bool = True,
    show_download: bool = True,
    container_key: str = "report_root",
) -> None:
    """渲染单份报告。

    Parameters
    ----------
    report : dict | None
        来自 /api/v1/reports/{id} 的完整报告字典。
    title : str | None
        渲染顶部标题（默认用 report.title）。
    show_metadata : bool
        是否展示 report_id / tenant_id / conclusion / status 等元数据。
    show_download : bool
        是否展示"下载"按钮（按 format 走 md / html / json）。
    container_key : str
        容器 key 前缀。
    """
    if report is None:
        st.info("无报告数据。")
        return

    # 元数据
    rid = report.get("report_id", "?")
    rtitle = title or report.get("title", f"报告 {rid}")

    if show_metadata:
        st.markdown(f"### {rtitle}")
        meta_cols = st.columns(4)
        meta_cols[0].markdown(f"**ID**\n\n`{rid}`")
        meta_cols[1].markdown(f"**结论**\n\n`{report.get('conclusion', '?')}`")
        meta_cols[2].markdown(f"**状态**\n\n`{report.get('status', '?')}`")
        meta_cols[3].markdown(f"**项目**\n\n`{report.get('project_id', '?')}`")
        ts_bits: list[str] = []
        if report.get("created_at"):
            ts_bits.append(f"created_at=`{report['created_at']}`")
        if report.get("tenant_id"):
            ts_bits.append(f"tenant=`{report['tenant_id']}`")
        if ts_bits:
            st.caption(" · ".join(ts_bits))
        st.divider()

    content, fmt = _extract_content(report)

    # 渲染
    if fmt == "html":
        # HTML 内容用 iframe 隔离渲染（沙箱）
        st.components.v1.html(content, height=600, scrolling=True)
    elif fmt == "json":
        st.json(content)
    else:
        # Markdown / 纯文本
        st.markdown(content)

    # 下载
    if show_download:
        render_download_buttons(report, content, fmt, container_key=container_key)


def render_download_buttons(
    report: dict[str, Any],
    content: str | None = None,
    fmt: str | None = None,
    *,
    container_key: str = "report_root",
) -> None:
    """渲染下载按钮。"""
    if content is None or fmt is None:
        content, fmt = _extract_content(report)

    rid = str(report.get("report_id", "report"))
    mime = {
        "md": "text/markdown",
        "html": "text/html",
        "json": "application/json",
        "text": "text/plain",
    }.get(fmt, "application/octet-stream")

    ext = fmt if fmt != "text" else "txt"
    filename = f"{rid}.{ext}"

    st.download_button(
        label=f"⬇️ 下载 {fmt.upper()}",
        data=content.encode("utf-8"),
        file_name=filename,
        mime=mime,
        key=f"{container_key}_dl",
        use_container_width=False,
    )


def render_list(
    reports: list[dict[str, Any]] | None,
    *,
    title: str = "报告列表",
    on_select_key: str = "caai_selected_report",
    container_key: str = "report_list_root",
) -> None:
    """渲染报告列表 + 点击展开详情。"""
    if not reports:
        st.info("无报告。")
        return

    st.markdown(f"### {title}")
    rows = []
    for r in reports:
        rows.append(
            {
                "report_id": r.get("report_id"),
                "title": r.get("title"),
                "conclusion": r.get("conclusion"),
                "status": r.get("status"),
                "project_id": r.get("project_id"),
                "created_at": r.get("created_at"),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    # 选择器
    ids = [r.get("report_id") for r in reports if r.get("report_id")]
    if not ids:
        return
    selected = st.selectbox(
        "选择 report_id 查看详情",
        options=ids,
        key=f"{container_key}_sel",
    )
    if st.button("查看详情", key=f"{container_key}_view", type="primary") and selected:
        try:
            # 必须先 configure：会话中的 api_client 可能由其他页面/初始化时
            # 用旧 base_url/token 构造，未同步当前 state 时会请求到错误后端。
            from streamlit_app.utils.state_manager import get_state
            cli = api_client()
            cli.configure(
                base_url=get_state().api_base, token=get_state().token
            )
            detail = cli._request("GET", f"/api/v1/reports/{selected}")
        except APIError as e:
            st.error(f"详情拉取失败: {e.message}")
            return
        st.session_state[on_select_key] = selected
        render(detail, container_key=f"{container_key}_detail")


__all__ = ["render", "render_download_buttons", "render_list", "_extract_content"]
