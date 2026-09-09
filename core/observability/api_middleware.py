"""FastAPI HTTP middleware trace 接入。

为每个 HTTP 请求创建 span，记录 route / method / status_code。
"""

from __future__ import annotations

from typing import Any

from core.observability.tracer import get_tracer

_tracer = None


def setup(tracer: Any = None) -> None:
    """初始化 API trace 中间件（幂等）。"""
    global _tracer
    _tracer = tracer or get_tracer("api")


def install(app: Any) -> None:
    """向 FastAPI app 注册 trace 中间件。"""
    if _tracer is None:
        setup()
    from starlette.requests import Request  # type: ignore
    from starlette.responses import Response  # type: ignore

    @app.middleware("http")
    async def _trace_http(request: Request, call_next: Any) -> Response:
        span = _tracer.start_as_current_span(  # type: ignore[union-attr]
            f"HTTP {request.method} {request.url.path}"
        )
        with span:
            try:
                span.set_attribute("http.method", request.method)  # type: ignore[union-attr]
                span.set_attribute("http.path", request.url.path)  # type: ignore[union-attr]
                response = await call_next(request)
                span.set_attribute("http.status_code", response.status_code)  # type: ignore[union-attr]
                return response
            except Exception as e:
                span.record_exception(e)  # type: ignore[union-attr]
                raise
