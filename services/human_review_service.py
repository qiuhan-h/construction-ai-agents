"""人工复核服务（编排器 / 业务侧统一入口）。

设计原则（O5）：
- 多租户硬隔离：create / list_pending / approve / reject 全部带 tenant_id 校验；
- 仓储层为 HumanReviewRepository（4c 内存 / 4c+ DB）；
- 异步：所有调用通过 asyncio.to_thread 包装，避免阻塞事件循环。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from common.ids import new_id
from services.human_review_repository import HumanReviewRepository, HumanReviewRow

logger = logging.getLogger(__name__)


class HumanReviewService:
    """人工复核业务服务。"""

    def __init__(self, repo: HumanReviewRepository | None = None) -> None:
        self._repo = repo or HumanReviewRepository()

    @property
    def repo(self) -> HumanReviewRepository:
        return self._repo

    async def create(
        self,
        *,
        tenant_id: str,
        task_id: str,
        reason: str,
        context: dict,
    ) -> str:
        """创建复核请求，返回 request_id。"""
        row = HumanReviewRow(
            id=new_id("hrv"),
            tenant_id=tenant_id,
            task_id=task_id,
            reason=reason,
            context=context or {},
        )
        return await asyncio.to_thread(self._repo.add, row)

    async def get(self, request_id: str, *, tenant_id: str | None = None) -> HumanReviewRow | None:
        return await asyncio.to_thread(self._repo.get, request_id, tenant_id=tenant_id)

    async def list_pending(self, tenant_id: str) -> list[HumanReviewRow]:
        return await asyncio.to_thread(self._repo.list_pending, tenant_id)

    async def list_by_tenant(self, tenant_id: str) -> list[HumanReviewRow]:
        return await asyncio.to_thread(self._repo.list_by_tenant, tenant_id)

    async def approve(
        self,
        request_id: str,
        reviewer: str,
        *,
        tenant_id: str,
        comment: str = "",
    ) -> bool:
        """批准复核请求，强制 tenant_id 校验 + 状态机约束。"""
        return await asyncio.to_thread(
            self._repo.update, request_id,
            status="approved", reviewer=reviewer, comment=comment,
            tenant_id=tenant_id,
        )

    async def reject(
        self,
        request_id: str,
        reviewer: str,
        *,
        tenant_id: str,
        comment: str = "",
    ) -> bool:
        """驳回复核请求，强制 tenant_id 校验 + 状态机约束。"""
        return await asyncio.to_thread(
            self._repo.update, request_id,
            status="rejected", reviewer=reviewer, comment=comment,
            tenant_id=tenant_id,
        )


# 单例
_default_service: HumanReviewService | None = None


def get_human_review_service() -> HumanReviewService:
    """获取默认人工复核服务（单例）。"""
    global _default_service
    if _default_service is None:
        _default_service = HumanReviewService()
    return _default_service


def reset_human_review_service() -> None:
    """重置单例（测试用）。"""
    global _default_service
    _default_service = None
