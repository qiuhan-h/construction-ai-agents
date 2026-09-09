"""OpenTelemetry Tracer 封装（NoOp 默认，prod 由 ENABLE_OTEL=1 启用）。

F3 原则：dev 环境返回 NoOp tracer，不引入 opentelemetry 依赖；
prod 环境 ENABLE_OTEL=1 时初始化 SDK 并导出 OTLP。
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("core.observability.tracer")

_initialized = False
_provider: Any = None

APP_NAME = os.environ.get("OTEL_SERVICE_NAME", "construction-ai-agents")


def _otel_enabled() -> bool:
    return os.environ.get("ENABLE_OTEL", "").lower() in ("1", "true", "yes")


def get_tracer(name: str = APP_NAME) -> Any:
    """获取 tracer 实例。

    dev / 无 ENABLE_OTEL → 返回 opentelemetry NoOp tracer（或纯 Python 兜底）。
    prod / ENABLE_OTEL=1 → 初始化 TracerProvider + OTLP 导出。
    """
    if not _otel_enabled():
        return _NoOpTracer(name)

    global _initialized, _provider
    if not _initialized:
        try:
            from opentelemetry import trace  # type: ignore[import-not-found]
            from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
            from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
            from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore[import-not-found]

            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-not-found]
                    OTLPSpanExporter,
                )
                exporter = OTLPSpanExporter()
            except ImportError:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import-not-found]
                    OTLPSpanExporter,
                )
                exporter = OTLPSpanExporter()

            _provider = TracerProvider(
                resource=Resource.create({"service.name": APP_NAME})
            )
            _provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(_provider)
            _initialized = True
            logger.info("OpenTelemetry 已初始化: service=%s", APP_NAME)
        except ImportError:
            logger.warning(
                "opentelemetry 未安装 → tracer 降级为 NoOp（pip install opentelemetry-api opentelemetry-sdk）"
            )
            return _NoOpTracer(name)
        except Exception as e:  # noqa: BLE001
            logger.warning("OpenTelemetry 初始化失败: %s → NoOp 降级", e)
            return _NoOpTracer(name)

    from opentelemetry import trace
    return trace.get_tracer(name)


class _NoOpSpan:
    """NoOp span：所有方法空实现。"""

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, *args: Any, **kwargs: Any) -> None:
        pass

    def record_exception(self, exc: BaseException) -> None:
        pass

    def add_event(self, name: str, **kwargs: Any) -> None:
        pass


class _NoOpTracer:
    """NoOp tracer：start_as_current_span 返回上下文管理器。"""

    def __init__(self, name: str) -> None:
        self._name = name

    def start_as_current_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()

    def start_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()
