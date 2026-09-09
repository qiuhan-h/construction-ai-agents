"""Prometheus 业务指标定义。

F3 原则：dev 环境用 NoOp 计数器（无 prometheus_client 依赖）；
prod 由 ENABLE_METRICS=1 启用真实 Counter / Gauge。
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("core.observability.metrics")

_metrics_enabled: bool | None = None


def _check_enabled() -> bool:
    global _metrics_enabled
    if _metrics_enabled is None:
        _metrics_enabled = os.environ.get("ENABLE_METRICS", "").lower() in (
            "1", "true", "yes",
        )
    return _metrics_enabled


class _NoOpMetric:
    """NoOp 指标：inc / set / observe / labels 全空实现。"""

    def inc(self, amount: float = 1.0) -> None:
        pass

    def set(self, value: float) -> None:
        pass

    def observe(self, amount: float) -> None:
        pass

    def labels(self, **kwargs: Any) -> _NoOpMetric:
        return self


def _make_counter(name: str, description: str, labelnames: list[str] | None = None) -> Any:
    if not _check_enabled():
        return _NoOpMetric()
    try:
        from prometheus_client import Counter
        return Counter(name, description, labelnames or [])
    except ImportError:
        logger.warning("prometheus_client 未安装 → %s 降级为 NoOp", name)
        return _NoOpMetric()


def _make_gauge(name: str, description: str, labelnames: list[str] | None = None) -> Any:
    if not _check_enabled():
        return _NoOpMetric()
    try:
        from prometheus_client import Gauge
        return Gauge(name, description, labelnames or [])
    except ImportError:
        return _NoOpMetric()


def _make_histogram(name: str, description: str, labelnames: list[str] | None = None) -> Any:
    if not _check_enabled():
        return _NoOpMetric()
    try:
        from prometheus_client import Histogram
        return Histogram(name, description, labelnames or [])
    except ImportError:
        return _NoOpMetric()


# ---- 业务指标 ----
request_total = _make_counter(
    "caai_request_total",
    "HTTP 请求总数",
    ["method", "path", "status"],
)

ws_connections = _make_gauge(
    "caai_ws_connections",
    "WebSocket 活跃连接数",
)

workflow_run_duration_seconds = _make_histogram(
    "caai_workflow_run_duration_seconds",
    "工作流执行耗时（秒）",
    ["workflow"],
)

event_bus_lag = _make_gauge(
    "caai_event_bus_lag",
    "事件总线积压量（未处理事件数）",
)

agent_invocation_total = _make_counter(
    "caai_agent_invocation_total",
    "智能体调用总数",
    ["agent", "status"],
)
