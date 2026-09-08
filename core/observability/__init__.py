"""可观测性包：OpenTelemetry tracing + Prometheus metrics。

F3 设计原则：
- dev 环境默认 NoOp（零开销）；
- prod 由环境变量 ENABLE_OTEL=1 / ENABLE_METRICS=1 启用；
- 无环境变量时默认可用且开销可忽略。
"""

from __future__ import annotations

__all__ = ["get_tracer", "get_metrics"]
