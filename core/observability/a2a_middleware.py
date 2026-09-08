"""A2A 中间件 trace 接入（阶段二预留插槽填充）。

为每条 A2A 请求创建 span，记录 method / tenant_id / agent_name。
"""

from __future__ import annotations

from typing import Any

from core.observability.tracer import get_tracer

_tracer = None


def setup(tracer: Any = None) -> None:
    """初始化 A2A trace 中间件（幂等）。"""
    global _tracer
    _tracer = tracer or get_tracer("a2a")


async def trace_middleware(message: Any, next_handler: Any) -> Any:
    """A2A 请求级 trace 中间件。

    用法：在 A2AServer 中间件链注册。
    """
    if _tracer is None:
        setup()
    span = _tracer.start_as_current_span(  # type: ignore[union-attr]
        f"a2a.{getattr(message, 'method', 'request')}"
    )
    with span:
        try:
            span.set_attribute(  # type: ignore[union-attr]
                "a2a.tenant_id", getattr(message, "tenant_id", "")
            )
            result = await next_handler(message)
            return result
        except Exception as e:
            span.record_exception(e)  # type: ignore[union-attr]
            raise
