"""健康检查路由（4d D4）。

端点（/api/v1/health 前缀）：
  GET /api/v1/health/healthz   存活探针：进程在 → 200
  GET /api/v1/health/readyz    就绪探针：DB / Redis / Celery 状态聚合

设计：
- ``healthz`` 永远 200（除非进程崩溃）；
- ``readyz`` 在依赖缺失时返回 503 + 详细 checks；不阻塞启动。
- 4d DB / Redis 探针走 settings 占位符（``需要补充实际链接``）→ 视为未配置但不报错。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, Response, status

from api.schemas.response_schemas import ApiResponse
from common.timeutils import to_iso, utc_now

logger = logging.getLogger("api.routers.health")


_PLACEHOLDER_RE = re.compile(r"需要补充|placeholder|<.*>")


def _is_configured(value: str | None) -> bool:
    if not value:
        return False
    if _PLACEHOLDER_RE.search(value):
        return False
    return True


async def _check_celery() -> dict[str, Any]:
    try:
        from services.celery_app import app as celery_app
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"celery_app load failed: {e}"}
    broker = getattr(celery_app.conf, "broker_url", None) or ""
    return {
        "ok": True,
        "app": celery_app.main,
        "broker": broker,
        "is_mock": broker.startswith("memory"),
    }


async def _check_db() -> dict[str, Any]:
    try:
        from config import get_settings
        url = get_settings().database_url
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"settings load failed: {e}"}
    if not _is_configured(url):
        return {"ok": True, "configured": False, "mode": "placeholder"}
    # 4d 首版不真正连 DB（避免依赖缺包时阻塞）
    return {"ok": True, "configured": True, "mode": "configured"}


async def _check_redis() -> dict[str, Any]:
    try:
        from config import get_settings
        url = get_settings().redis_url
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"settings load failed: {e}"}
    if not _is_configured(url):
        return {"ok": True, "configured": False, "mode": "placeholder"}
    return {"ok": True, "configured": True, "mode": "configured"}


async def _check_event_bus() -> dict[str, Any]:
    try:
        from core.events import get_event_bus
        bus = get_event_bus()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"event_bus load failed: {e}"}
    return {
        "ok": True,
        "published_count": bus.published_count,
        "delivered_count": bus.delivered_count,
        "subscribers": sum(len(v) for v in bus._subs.values()),
    }


def build_health_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/health", tags=["health"])

    @router.get("/healthz", response_model=ApiResponse[dict])
    async def healthz() -> dict[str, Any]:
        return ApiResponse[dict].ok(
            {
                "status": "ok",
                "checked_at": to_iso(utc_now()),
            }
        )

    @router.get("/readyz", response_model=ApiResponse[dict])
    async def readyz(response: Response) -> dict[str, Any]:
        checks: dict[str, dict[str, Any]] = {}
        for name, fn in (
            ("database", _check_db),
            ("redis", _check_redis),
            ("celery", _check_celery),
            ("event_bus", _check_event_bus),
        ):
            try:
                checks[name] = await fn()
            except Exception as e:  # noqa: BLE001
                checks[name] = {"ok": False, "error": str(e)}

        # 占位符依赖视为 ok（readyz 不阻塞），其它失败视为 degraded
        all_ok = all(c.get("ok", False) for c in checks.values())
        response.status_code = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE
        return ApiResponse[dict].ok(
            {
                "status": "ok" if all_ok else "degraded",
                "checked_at": to_iso(utc_now()),
                "checks": checks,
            }
        )

    return router


__all__ = ["build_health_router"]
