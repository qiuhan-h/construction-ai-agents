"""任务调度：把 TaskSpec 提交到 TaskQueue（Celery），管理状态查询/取消。

设计原则（O3, O7）：
- task_scheduler 不直接执行 agent，只负责入队 / 优先级 / 重试；
- 实际执行交给 Celery worker（worker 在 4d start_worker.py 启动）；
- 任务名格式：orchestrator.<workflow_name>.<node_id>。
- 重试策略：指数退避，最多 3 次，base 1.0s（4c+ 可由配置覆盖）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from common.exceptions import AppException
from common.ids import new_id
from core.orchestrator.workflow_engine import TaskSpec

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1.0


class TaskSchedulerError(AppException):
    """任务调度异常。"""

    code = "70001"
    http_status = 500


class TaskScheduler:
    """任务调度（提交 / 状态 / 取消）。"""

    def __init__(self, queue: Any) -> None:
        self._queue = queue

    async def submit(
        self,
        task: TaskSpec,
        tenant_id: str,
        *,
        priority: int = 5,
        run_id: str | None = None,
        workflow_name: str | None = None,
    ) -> str:
        """提交到队列，返回 celery task_id（mock 模式下返回 mock-*）。"""
        name = self._build_task_name(workflow_name, task)
        attempt = 0
        last_exc: Exception | None = None
        while attempt <= min(task.retry, MAX_RETRIES):
            try:
                return await self._queue.submit(
                    name=name,
                    args=[task.params, tenant_id],
                    kwargs={"run_id": run_id, "node_id": task.node_id},
                    priority=priority,
                    run_id=run_id,
                    tenant_id=tenant_id,
                )
            except Exception as e:  # 提交失败：本地重试（与 Celery 内重试不同）
                last_exc = e
                attempt += 1
                backoff = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "任务提交失败 attempt=%d backoff=%.2fs err=%s",
                    attempt, backoff, e,
                )
                await asyncio.sleep(backoff)
        raise TaskSchedulerError(
            f"任务提交失败: {last_exc}",
            details={"task_name": name, "attempts": attempt},
        )

    async def get_status(self, task_id: str) -> dict:
        return await self._queue.get_status(task_id)

    async def cancel(self, task_id: str) -> bool:
        return await self._queue.cancel(task_id)

    @staticmethod
    def _build_task_name(workflow_name: str | None, task: TaskSpec) -> str:
        wf = workflow_name or "ad_hoc"
        return f"orchestrator.{wf}.{task.node_id}"


# =====================================================
# Celery 任务定义（worker 调用此执行 agent.handle）
# =====================================================
def register_celery_tasks(celery_app: Any) -> None:
    """把 orchestrator 节点包装成 Celery task 注册到 celery_app。

    worker 端执行流程：
    1) 反序列化 params + tenant_id + run_id + node_id
    2) 通过 agent_manager 拿 agent
    3) 调 agent.handle(msg, task)
    4) 发布 TOPIC_AGENT_TASK_DONE 事件

    依赖注入方式：
    - agent_manager 通过 celery_app.conf["agent_manager"] 在 worker 启动时设置。
    """
    if not hasattr(celery_app, "_orchestrator_registered"):
        celery_app._orchestrator_registered = True

    @celery_app.task(name="orchestrator._dispatch_node", bind=True, max_retries=MAX_RETRIES)
    def _dispatch_node(self, params: dict, tenant_id: str, **kw) -> dict:  # noqa: ANN001
        from core.a2a.message import A2AMessage, MessagePart, Task
        from common.ids import message_id, task_id
        from core.events import publish_sync, TOPIC_AGENT_TASK_DONE
        from common.timeutils import to_iso, utc_now

        node_id = kw.get("node_id", "")
        run_id = kw.get("run_id")
        agent_manager = celery_app.conf.get("agent_manager")

        if agent_manager is None:
            # worker 未注入 agent_manager → 退化为 mock 完成
            logger.warning("agent_manager 未注入，节点 %s 走 mock 完成", node_id)
            return {
                "node_id": node_id,
                "run_id": run_id,
                "tenant_id": tenant_id,
                "status": "mock_done",
                "params": params,
                "finished_at": to_iso(utc_now()),
            }

        # 通过 celery_app.conf["workflow_resolver"](run_id, node_id) 找到 TaskSpec
        # 4c 首版：调度由编排器同步完成，Celery 仅用于异步 / 重试场景
        # 此处仅占位，避免 worker 启动失败
        return {
            "node_id": node_id,
            "run_id": run_id,
            "tenant_id": tenant_id,
            "status": "skipped",
            "params": params,
        }
