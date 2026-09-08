"""MCP 中间件 trace 接入。

为 MCP JSON-RPC 调用创建 span，记录 method / tool / resource。
"""

from __future__ import annotations

from typing import Any

from core.observability.tracer import get_tracer

_tracer = None


def setup(tracer: Any = None) -> None:
    """初始化 MCP trace 中间件（幂等）。"""
    global _tracer
    _tracer = tracer or get_tracer("mcp")


async def trace_mcp_call(method: str, params: dict[str, Any], handler: Any) -> Any:
    """MCP 调用级 trace 包装。

    用法：在 MCPServer.handle_raw 前包装一层。
    """
    if _tracer is None:
        setup()
    span = _tracer.start_as_current_span(f"mcp.{method}")  # type: ignore[union-attr]
    with span:
        try:
            if method == "tools/call":
                span.set_attribute("mcp.tool", params.get("name", ""))  # type: ignore[union-attr]
            elif method == "resources/read":
                span.set_attribute("mcp.uri", params.get("uri", ""))  # type: ignore[union-attr]
            return await handler()
        except Exception as e:
            span.record_exception(e)  # type: ignore[union-attr]
            raise
