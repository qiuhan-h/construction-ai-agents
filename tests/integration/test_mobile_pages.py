"""集成测试：6c.2 响应式 Streamlit 移动端页面。

覆盖 TR-9.1 ~ TR-9.6：
- TR-9.1: 07_mobile 页面注册（_PAGE_MODULES / _IMPLEMENTED / PAGES 列表）
- TR-9.2: API 客户端 mobile_dashboard / mobile_alerts / mobile_projects 方法存在
- TR-9.3: mobile.css 含响应式断点（@media min-width）
- TR-9.4: mobile_card 组件 KPI/告警/项目卡片渲染正确 HTML 类名
- TR-9.5: KPI tone 映射正确（danger/success/warning/info）
- TR-9.6: 空数据渲染空状态占位（不报错）
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 项目根目录：tests/integration/test_mobile_pages.py → parents[2] = construction-ai-agents
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MOBILE_CSS = _PROJECT_ROOT / "streamlit_app" / "assets" / "css" / "mobile.css"


# =====================================================
# TR-9.1: 页面注册
# =====================================================
def test_mobile_page_registered_in_modules() -> None:
    """07_mobile 注册在 _PAGE_MODULES 中。"""
    from streamlit_app.pages import _PAGE_MODULES

    assert "07_mobile" in _PAGE_MODULES
    assert _PAGE_MODULES["07_mobile"] == "streamlit_app.pages.07_mobile"


def test_mobile_page_in_implemented() -> None:
    """07_mobile 在 _IMPLEMENTED 集合中（可路由）。"""
    from streamlit_app.pages import _IMPLEMENTED

    assert "07_mobile" in _IMPLEMENTED


def test_mobile_page_in_app_pages_list() -> None:
    """07_mobile 出现在 app.py PAGES 列表中。"""
    from streamlit_app.app import PAGES

    ids = [p["id"] for p in PAGES]
    assert "07_mobile" in ids
    # 确认标题与图标
    entry = next(p for p in PAGES if p["id"] == "07_mobile")
    assert "移动" in entry["title"]
    assert entry["icon"]


def test_mobile_page_importable() -> None:
    """07_mobile 模块可导入且暴露 render()。"""
    from streamlit_app.pages import _PAGE_MODULES
    import importlib

    module = importlib.import_module(_PAGE_MODULES["07_mobile"])
    assert hasattr(module, "render")
    assert callable(module.render)


# =====================================================
# TR-9.2: API 客户端移动端方法
# =====================================================
def test_api_client_mobile_methods_exist() -> None:
    """APIClient 含 mobile_dashboard / mobile_alerts / mobile_projects 方法。"""
    from streamlit_app.utils.api_client import APIClient

    assert hasattr(APIClient, "mobile_dashboard")
    assert hasattr(APIClient, "mobile_alerts")
    assert hasattr(APIClient, "mobile_projects")


def test_api_client_mobile_methods_callable() -> None:
    """三个移动端方法均可调用。"""
    from streamlit_app.utils.api_client import APIClient

    for name in ("mobile_dashboard", "mobile_alerts", "mobile_projects"):
        method = getattr(APIClient, name)
        assert callable(method)


# =====================================================
# TR-9.3: 响应式 CSS
# =====================================================
def test_mobile_css_file_exists() -> None:
    """mobile.css 文件存在且非空。"""
    assert _MOBILE_CSS.is_file(), f"mobile.css 不存在: {_MOBILE_CSS}"
    content = _MOBILE_CSS.read_text(encoding="utf-8")
    assert len(content) > 100, "mobile.css 内容过短"


def test_mobile_css_has_breakpoints() -> None:
    """mobile.css 含响应式断点 @media。"""
    content = _MOBILE_CSS.read_text(encoding="utf-8")
    assert "@media" in content, "mobile.css 缺少 @media 响应式断点"
    # 至少两个断点（平板 + 桌面）
    assert content.count("@media") >= 2


def test_mobile_css_has_card_styles() -> None:
    """mobile.css 含 KPI/告警/项目卡片样式类。"""
    content = _MOBILE_CSS.read_text(encoding="utf-8")
    for cls in ("caai-kpi-card", "caai-alert-card", "caai-project-card"):
        assert cls in content, f"mobile.css 缺少 {cls} 样式"


# =====================================================
# TR-9.4: mobile_card 组件 HTML 输出
# =====================================================
def test_mobile_card_module_importable() -> None:
    """mobile_card 组件可导入且暴露核心函数。"""
    from streamlit_app.components import mobile_card

    for func in (
        "render_kpi_grid",
        "render_alert_list",
        "render_project_grid",
        "render_dashboard",
        "inject_mobile_css",
    ):
        assert hasattr(mobile_card, func), f"mobile_card 缺少 {func}"


def test_render_kpi_grid_html() -> None:
    """KPI 网格渲染含 caai-kpi-card 类名。"""
    from streamlit_app.components import mobile_card

    with patch("streamlit.markdown") as mock_md:
        mobile_card.render_kpi_grid(
            [
                {"label": "告警", "value": 5, "tone": "danger"},
                {"label": "评分", "value": 88, "tone": "success"},
            ]
        )
        assert mock_md.called
        html_arg = mock_md.call_args.args[0]
        assert "caai-kpi-card" in html_arg
        assert "caai-kpi-danger" in html_arg
        assert "caai-kpi-success" in html_arg


def test_render_alert_list_html() -> None:
    """告警列表渲染含分级色类名。"""
    from streamlit_app.components import mobile_card

    with patch("streamlit.markdown"):
        mobile_card.render_alert_list(
            [
                {
                    "id": "a1",
                    "level": "critical",
                    "title": "高空未挂安全带",
                    "source": "site_monitor",
                    "status": "open",
                    "occurred_at": "2026-09-05T10:00:00",
                },
                {
                    "id": "a2",
                    "level": "warning",
                    "title": "临边防护缺失",
                    "source": "safety_audit",
                    "status": "open",
                    "occurred_at": "2026-09-05T11:00:00",
                },
            ]
        )
        # 验证 st.markdown 被调用（含 HTML）
        import streamlit as st

        assert st.markdown.called  # type: ignore[attr-defined]
        html_arg = st.markdown.call_args.args[0]  # type: ignore[attr-defined]
        assert "caai-alert-card" in html_arg
        assert "caai-level-critical" in html_arg
        assert "caai-level-warning" in html_arg


def test_render_project_grid_html() -> None:
    """项目卡片渲染含项目名 + 状态徽章。"""
    from streamlit_app.components import mobile_card

    with patch("streamlit.markdown"):
        mobile_card.render_project_grid(
            [
                {
                    "id": "p1",
                    "name": "科创园一期",
                    "status": "active",
                    "safety_score": 92.5,
                    "open_alerts": 2,
                },
            ]
        )
        import streamlit as st

        html_arg = st.markdown.call_args.args[0]  # type: ignore[attr-defined]
        assert "caai-project-card" in html_arg
        assert "科创园一期" in html_arg
        assert "caai-badge-active" in html_arg


# =====================================================
# TR-9.5: KPI tone 映射
# =====================================================
def test_kpi_tone_mapping() -> None:
    """KPI 卡片 tone 正确映射到 CSS 类名。"""
    from streamlit_app.components import mobile_card

    tones = ["danger", "success", "warning", "info"]
    with patch("streamlit.markdown") as mock_md:
        mobile_card.render_kpi_grid(
            [{"label": f"t{i}", "value": i, "tone": t} for i, t in enumerate(tones)]
        )
        html_arg = mock_md.call_args.args[0]
        for t in tones:
            assert f"caai-kpi-{t}" in html_arg, f"tone {t} 未映射"


# =====================================================
# TR-9.6: 空数据降级
# =====================================================
def test_empty_kpi_renders_empty_state() -> None:
    """空 KPI 数据渲染空状态占位（不报错）。"""
    from streamlit_app.components import mobile_card

    with patch("streamlit.markdown") as mock_md:
        mobile_card.render_kpi_grid([])
        assert mock_md.called
        html_arg = mock_md.call_args.args[0]
        assert "caai-empty-state" in html_arg


def test_empty_alerts_renders_empty_state() -> None:
    """空告警列表渲染空状态。"""
    from streamlit_app.components import mobile_card

    with patch("streamlit.markdown") as mock_md:
        mobile_card.render_alert_list([])
        assert mock_md.called
        html_arg = mock_md.call_args.args[0]
        assert "caai-empty-state" in html_arg


def test_empty_projects_renders_empty_state() -> None:
    """空项目列表渲染空状态。"""
    from streamlit_app.components import mobile_card

    with patch("streamlit.markdown") as mock_md:
        mobile_card.render_project_grid([])
        assert mock_md.called
        html_arg = mock_md.call_args.args[0]
        assert "caai-empty-state" in html_arg


def test_render_dashboard_with_none_data() -> None:
    """render_dashboard 全空数据不报错（最终降级）。"""
    from streamlit_app.components import mobile_card

    with patch("streamlit.markdown"):
        # 不应抛异常
        mobile_card.render_dashboard(
            kpis=None, alerts=None, projects=None, updated_at=None
        )


# =====================================================
# 回归：07_mobile 页面 render 不报错（mock Streamlit）
# =====================================================
def test_mobile_page_render_no_crash() -> None:
    """07_mobile.render() 在 mock 环境下不崩溃（API 不可达时降级）。"""
    from streamlit_app.pages import _PAGE_MODULES
    import importlib

    module = importlib.import_module(_PAGE_MODULES["07_mobile"])

    # mock Streamlit 全部 UI 调用 + API 返回空
    col_ctx = MagicMock()
    with patch("streamlit.markdown"), \
         patch("streamlit.title"), \
         patch("streamlit.caption"), \
         patch("streamlit.button", return_value=False), \
         patch("streamlit.columns", return_value=[col_ctx, col_ctx]), \
         patch("streamlit.divider"), \
         patch("streamlit.toast"):
        # 直接 patch _fetch_dashboard 返回 None（API 不可达）
        with patch.object(module, "_fetch_dashboard", return_value=None):
            try:
                module.render()
            except Exception as e:
                # Streamlit ScriptRunContext 缺失属预期，不计为失败
                if "ScriptRunContext" not in str(e):
                    pytest.fail(f"07_mobile.render() 异常: {e}")
