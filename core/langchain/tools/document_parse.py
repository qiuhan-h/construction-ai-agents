"""文档解析工具适配模块（5b.6 实做，对齐 shu_zhuang_tu.txt 第 196 行）。

职责：
- 把 ``core/mcp/tools/validation_tools.py`` 注册的 MCP 工具适配为 ``BusinessTool``；
- 不重复实现业务逻辑（方案/图纸/文档校验算法在 MCP 工具内）；
- 缺 MCP service 时降级 ``MockTool``。

注册工具名（白名单）：
- ``validation.plan``      施工方案必填字段 + 一致性校验
- ``validation.drawing``   图纸基础元数据校验（file_uri 协议 + 文件存在）
- ``validation.document``  通用文档完整性校验（size / mime_type）
"""

from __future__ import annotations

from core.langchain.tools import MCPToolAdapter, register_tool


_DESC_PLAN = "施工方案校验：title 非空 + risk_level 枚举 + hazards 至少 1 条"
_DESC_DRAWING = "图纸校验：file_uri 必须是 file:// 或 http(s)://"
_DESC_DOCUMENT = "文档校验：size_bytes > 0 + mime_type 非空"


def _register() -> None:
    """注册 validation.* 系列业务工具（import 时调用一次）。"""
    register_tool("validation.plan", lambda: MCPToolAdapter("validation.plan", _DESC_PLAN))
    register_tool("validation.drawing", lambda: MCPToolAdapter("validation.drawing", _DESC_DRAWING))
    register_tool(
        "validation.document",
        lambda: MCPToolAdapter("validation.document", _DESC_DOCUMENT),
    )


_register()


__all__ = ["MCPToolAdapter"]
