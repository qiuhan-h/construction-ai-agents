"""通用组件包（5a 实做 + 6c.2 移动端卡片）。

组件清单：
- alert_display   告警展示（与 site_monitor 联动）
- chart_component  通用图表封装（plotly / altair / native 三引擎）
- map_component   地图组件（folium + streamlit-folium + native 三引擎）
- report_viewer  报告查看器（Markdown / HTML / JSON + 下载按钮）
- mobile_card    移动端卡片组件（6c.2：KPI / 告警 / 项目卡片）

每个组件均暴露 render() 入口；5a 阶段不依赖任何第三方可视化库的硬依赖，
缺包时自动降级（plotly / folium / streamlit-folium 任一缺失不报错）。
"""

from streamlit_app.components import (
    alert_display,
    chart_component,
    map_component,
    mobile_card,
    report_viewer,
)

__all__ = [
    "alert_display",
    "chart_component",
    "map_component",
    "mobile_card",
    "report_viewer",
]
