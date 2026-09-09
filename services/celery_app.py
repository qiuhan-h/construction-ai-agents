"""Celery 应用实例（4d start_worker.py 引用）。

broker / backend 走配置；首版可仅内存 mock（broker='memory://'）。
autodiscover_tasks(["services"]) 自动发现 services/ 下的 @app.task 函数。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _build_celery_app() -> Any:
    """构造 Celery 实例；broker 未配置时使用 memory://。"""
    from celery import Celery  # type: ignore[import-not-found]

    # 配置：缺凭据时退回 memory://
    try:
        from config import get_settings
        settings = get_settings()
        broker = (
            settings.celery_broker_url
            if settings.celery_broker_url
            and not str(settings.celery_broker_url).startswith("需要补充")
            else "memory://"
        )
        backend = (
            settings.celery_result_backend
            if settings.celery_result_backend
            and not str(settings.celery_result_backend).startswith("需要补充")
            else "cache+memory://"
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("settings 加载失败，使用 memory://: %s", e)
        broker = "memory://"
        backend = "cache+memory://"

    app = Celery(
        "construction_ai_agents",
        broker=broker,
        backend=backend,
    )
    app.autodiscover_tasks(["services"])

    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Shanghai",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        # worker 丢失（OOM/kill -9/容器被驱逐）时拒绝任务并重新入队，
        # 配合 task_acks_late=True 避免消息丢失；否则任务会"既不 ack 也
        # 不重投"，造成数据空洞。
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
    )

    # 注册编排器节点任务
    try:
        from core.orchestrator.task_scheduler import register_celery_tasks
        register_celery_tasks(app)
    except ImportError as e:
        logger.warning("orchestrator 任务注册失败（可忽略）: %s", e)

    return app


# 进程级单例
_app: Any | None = None


def get_celery_app() -> Any:
    """获取 Celery 应用单例。"""
    global _app
    if _app is None:
        _app = _build_celery_app()
    return _app


def reset_celery_app() -> None:
    """重置单例（测试用）。"""
    global _app
    _app = None


# 模块级绑定（兼容 4d start_worker.py 直接 `from services.celery_app import app`）
app = get_celery_app()
