"""Prometheus /metrics 端点导出器。

F3 原则：dev 环境返回空 200；prod 由 ENABLE_METRICS=1 返回真实指标。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("core.observability.exporter")


def _metrics_enabled() -> bool:
    return os.environ.get("ENABLE_METRICS", "").lower() in ("1", "true", "yes")


def generate_latest() -> str:
    """生成 Prometheus exposition 格式文本。"""
    if not _metrics_enabled():
        return "# metrics disabled (set ENABLE_METRICS=1 to enable)\n"
    try:
        from prometheus_client import generate_latest as _gen
        return _gen().decode("utf-8")
    except ImportError:
        return "# prometheus_client not installed\n"


def mount_metrics_endpoint(app) -> None:
    """向 FastAPI app 挂载 /metrics 端点。"""
    from fastapi import Response

    @app.get("/metrics", tags=["monitoring"])
    async def _metrics() -> Response:
        return Response(content=generate_latest(), media_type="text/plain; version=0.0.4")
