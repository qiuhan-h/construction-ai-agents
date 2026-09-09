"""GIS 工具适配模块（5b.6 实做，对齐 shu_zhuang_tu.txt 第 197 行）。

职责：
- 把 ``core/mcp/tools/analysis_tools.py`` 注册的 MCP 工具适配为 ``BusinessTool``；
- 桥接 site_monitor_agent 的 GIS 集成（geofence / 空间监测 / 风险热图）；
- 不重复实现业务逻辑（聚合/汇总算法在 MCP 工具内）；
- 缺 MCP service 时降级 ``MockTool``。

注册工具名（白名单）：
- ``analysis.aggregate_risk``  多源风险聚合（塔吊 + 高支模 + 深基坑 ...）
"""

from __future__ import annotations

from core.langchain.tools import MCPToolAdapter, register_tool

_DESC_AGGREGATE = "多源风险聚合：合并塔吊/高支模/深基坑等危险源 → 综合风险评分"


def _register() -> None:
    """注册 analysis.* 系列业务工具（import 时调用一次）。"""
    register_tool(
        "analysis.aggregate_risk",
        lambda: MCPToolAdapter("analysis.aggregate_risk", _DESC_AGGREGATE),
    )


_register()


__all__ = ["MCPToolAdapter"]
