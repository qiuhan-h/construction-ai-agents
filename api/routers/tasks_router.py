"""任务管理路由（4d）。

端点（/api/v1/tasks 前缀）：
  GET    /api/v1/tasks/{task_id}      查询任务状态（Celery 或 mock）
  DELETE /api/v1/tasks/{task_id}      取消任务

设计：
- 4d 通过 ``services.task_queue.get_task_queue()`` 走 mock / Celery；
- 多租户隔离：所有端点强制 Depends(get_auth_context)，并通过
  TaskQueue.owner_of 校验 task 归属，跨租户访问返回 404；
- 取消仅对未完成任务生效；已完成任务返回 ``cancelled=False``。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies.auth import AuthContext, get_auth_context
from api.schemas.response_schemas import ApiResponse

logger = logging.getLogger("api.routers.tasks")


def _enforce_owner_or_404(q: Any, task_id: str, auth: AuthContext) -> None:
    """校验 task 归属，跨租户访问视为不存在（避免信息泄漏）。"""
    owner = q.owner_of(task_id)
    if owner is not None and owner != auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "10003", "message": f"任务不存在: {task_id}"},
        )


def build_tasks_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

    @router.get("/{task_id}", response_model=ApiResponse[dict])
    async def get_task(
        task_id: str,
        auth: AuthContext = Depends(get_auth_context),
    ) -> ApiResponse[dict[str, Any]]:
        from services.task_queue import get_task_queue

        q = get_task_queue()
        _enforce_owner_or_404(q, task_id, auth)
        st = await q.get_status(task_id)
        return ApiResponse[dict].ok(
            {
                "task_id": task_id,
                "tenant_id": auth.tenant_id,
                "state": st.get("state", "UNKNOWN"),
                "result": st.get("result"),
                "is_mock": q.is_mock,
            }
        )

    @router.delete("/{task_id}", response_model=ApiResponse[dict])
    async def cancel_task(
        task_id: str,
        auth: AuthContext = Depends(get_auth_context),
    ) -> ApiResponse[dict[str, Any]]:
        from services.task_queue import get_task_queue

        q = get_task_queue()
        _enforce_owner_or_404(q, task_id, auth)
        ok = await q.cancel(task_id)
        return ApiResponse[dict].ok(
            {
                "task_id": task_id,
                "tenant_id": auth.tenant_id,
                "cancelled": ok,
            }
        )

    return router


__all__ = ["build_tasks_router"]
