"""计算工具适配模块（5b.6 实做，对齐 shu_zhuang_tu.txt 第 195 行）。

职责：
- 把 ``core/mcp/tools/calculation_tools.py`` 注册的 MCP 工具适配为 ``BusinessTool``；
- 不重复实现业务逻辑（荷载/风险/结构校核算法在 MCP 工具内）；
- 缺 MCP service 时降级 ``MockTool``。

注册工具名（白名单）：
- ``calculation.load``              结构荷载组合（DL + LL + W + S）
- ``calculation.risk``              危险源打分 → 风险等级（low/medium/high）
- ``calculation.structural_check``  结构最小校核（跨度/荷载合理性）
"""

from __future__ import annotations

from core.langchain.tools import MCPToolAdapter, register_tool


# 工具描述（对齐 core/mcp/tools/calculation_tools.py 的 register_tool description）
_DESC_LOAD = (
    "结构荷载组合（恒载 + 活载 + 风载 + 雪载）→ q = 1.2DL + 1.4LL + 0.6W + 0.7S"
)
_DESC_RISK = (
    "基于危险源打分评估风险等级（low < 5 / medium < 10 / high >= 10）"
)
_DESC_STRUCT = (
    "结构最小校核：跨度 / 荷载合理性 + 高危专项论证阈值检查"
)


def _register() -> None:
    """注册 calculation.* 系列业务工具（import 时调用一次）。"""
    register_tool("calculation.load", lambda: MCPToolAdapter("calculation.load", _DESC_LOAD))
    register_tool("calculation.risk", lambda: MCPToolAdapter("calculation.risk", _DESC_RISK))
    register_tool(
        "calculation.structural_check",
        lambda: MCPToolAdapter("calculation.structural_check", _DESC_STRUCT),
    )


_register()


__all__ = ["MCPToolAdapter"]
