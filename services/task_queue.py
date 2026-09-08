"""Celery 异步任务封装。

设计原则（O3）：
- task_queue 是 TaskScheduler 与 Celery 之间的桥梁；
- celery_app 未启动 / broker 不可达 → 自动降级为 mock 模式（返回 mock-* id）；
- get_status / cancel 在 mock 模式也走"已 done"路径。
"""

from __future__ import annotations

import logging
import secrets
import threading
from typing import Any

logger = logging.getLogger(__name__)


class TaskQueue:
    """Celery 任务队列封装（自带 mock 降级）。"""

    def __init__(self, broker_url: str | None = None, backend_url: str | None = None) -> None:
        self._broker = broker_url
        self._backend = backend_url
        self._app: Any = None
        self._mock: bool = False
        # 多租户隔离：记录 task_id → tenant_id 映射，查询/取消时校验
        self._owner: dict[str, str] = {}
        # 幂等：idempotency_key → task_id，避免上游重试触发重复 SMS / 通知
        self._idempotency: dict[str, str] = {}
        self._owner_lock = threading.Lock()
        try:
            from services.celery_app import app as celery_app
            self._app = celery_app
            # memory:// 视为 mock（无 worker 也无需真发）
            if isinstance(self._app.conf.broker_url, str) and self._app.conf.broker_url.startswith(
                "memory"
            ):
                self._mock = True
        except Exception as e:  # noqa: BLE001
            logger.warning("celery_app 加载失败，TaskQueue 走 mock 模式: %s", e)
            self._mock = True

    @property
    def is_mock(self) -> bool:
        return self._mock or self._app is None

    async def submit(
        self,
        name: str,
        args: list,
        kwargs: dict | None = None,
        *,
        priority: int = 5,
        run_id: str | None = None,
        tenant_id: str = "",
        idempotency_key: str = "",
    ) -> str:
        """提交到 Celery / 返回 mock id。

        若传入 ``idempotency_key`` 且此前已用同 key 提交过，直接复用旧 task_id，
        避免上游重试触发重复 SMS / 通知等副作用。
        """
        # 幂等检查：同 key 已提交则直接复用旧 task_id
        if idempotency_key:
            with self._owner_lock:
                existing = self._idempotency.get(idempotency_key)
            if existing is not None:
                logger.info(
                    "幂等命中，复用旧 task_id=%s (key=%s)", existing, idempotency_key
                )
                return existing
        if self.is_mock:
            tid = f"mock-{run_id or secrets.token_hex(4)}"
        else:
            try:
                async_result = self._app.send_task(
                    name,
                    args=args,
                    kwargs=kwargs or {},
                    priority=priority,
                )
                tid = async_result.id
            except Exception as e:  # noqa: BLE001
                logger.warning("Celery send_task 失败，降级 mock: %s", e)
                tid = f"mock-fallback-{secrets.token_hex(4)}"
        # 记录租户归属，供查询/取消时校验
        if tenant_id:
            with self._owner_lock:
                self._owner[tid] = tenant_id
        # 记录幂等键 → task_id，供后续重试复用
        if idempotency_key:
            with self._owner_lock:
                # 二次检查，避免并发提交同 key 时重复写入
                self._idempotency.setdefault(idempotency_key, tid)
        return tid

    def owner_of(self, task_id: str) -> str | None:
        """查询任务所属租户，未记录返回 None。"""
        with self._owner_lock:
            return self._owner.get(task_id)

    async def get_status(self, task_id: str) -> dict:
        """查询任务状态。"""
        if self.is_mock or task_id.startswith("mock-"):
            return {"state": "PENDING", "result": None, "task_id": task_id}
        try:
            res = self._app.AsyncResult(task_id)
            return {"state": res.state, "result": res.result, "task_id": task_id}
        except Exception as e:  # noqa: BLE001
            return {"state": "UNKNOWN", "error": repr(e), "task_id": task_id}

    async def cancel(self, task_id: str) -> bool:
        """取消任务。"""
        if self.is_mock or task_id.startswith("mock-"):
            return True
        try:
            self._app.control.revoke(task_id, terminate=True)
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("Celery revoke 失败: %s", e)
            return False


# 单例
_default_queue: TaskQueue | None = None


def get_task_queue() -> TaskQueue:
    """获取默认任务队列（单例）。"""
    global _default_queue
    if _default_queue is None:
        _default_queue = TaskQueue()
    return _default_queue


def reset_task_queue() -> None:
    """重置单例（测试用）。"""
    global _default_queue
    _default_queue = None
