"""Page 路由分发（5a）。

6 个页面全部实做：
  01_safety_audit        安全审核工作台
  02_compliance          合规校验工作台
  03_site_monitor        现场监控工作台（带实时告警 + WS 事件流）
  04_dashboard           编排可视化 Dashboard（4e 已就位）
  05_gis_viewer          GIS 视图（demo + 上传）
  06_agent_management    智能体管理（清单 + Card + 自由调用）

本 dispatcher 把 page_id 路由到对应模块的 render()，与 app.py 解耦。
"""

from __future__ import annotations

import importlib

import streamlit as st

# 各 page 路径；key 是 page_id，value 是模块路径（无 .py 后缀）。
_PAGE_MODULES: dict[str, str] = {
    "01_safety_audit": "streamlit_app.pages.01_safety_audit",
    "02_compliance": "streamlit_app.pages.02_compliance",
    "03_site_monitor": "streamlit_app.pages.03_site_monitor",
    "04_dashboard": "streamlit_app.pages.04_dashboard",
    "05_gis_viewer": "streamlit_app.pages.05_gis_viewer",
    "06_agent_management": "streamlit_app.pages.06_agent_management",
    "07_mobile": "streamlit_app.pages.07_mobile",
}

# 5a 实做 6 个核心页面；6c.2 新增 07_mobile 移动端响应式页面
_IMPLEMENTED = {
    "01_safety_audit",
    "02_compliance",
    "03_site_monitor",
    "04_dashboard",
    "05_gis_viewer",
    "06_agent_management",
    "07_mobile",
}


def render(page_id: str = "04_dashboard") -> None:
    """根据 page_id 渲染页面。

    未实现的页面 → 友好提示占位文案（5a 阶段不应触发）；
    已实现的页面 → importlib 动态 import + 调 module.render()。
    """
    if page_id not in _PAGE_MODULES:
        st.error(f"未知 page_id: {page_id}")
        return
    if page_id not in _IMPLEMENTED:
        nice = page_id.replace("_", " ")
        st.info(
            f"**{nice}** 页面将在后续阶段落地。"
            "当前 5a 已实做 6 个核心页面。",
            icon="ℹ️",
        )
        return
    module = importlib.import_module(_PAGE_MODULES[page_id])
    module.render()


__all__ = ["render", "_IMPLEMENTED"]
