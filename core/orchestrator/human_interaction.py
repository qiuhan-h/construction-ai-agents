"""人机交互适配层：编排器 ↔ 人工复核服务。

设计原则（O5）：
- 适配器只负责把编排器侧的语义映射到 services/human_review_service；
- 不在适配层持久化，所有存储由 human_review_service 负责；
- 多租户硬隔离：所有接口必传 tenant_id。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class HumanReviewServiceAdapter:
    """编排器 ↔ 人工复核服务适配层。"""

    def __init__(self, service: Any | None = None) -> None:
        # service 为 None 时，按需 get_human_review_service() 取默认实例
        self._service = service

    def _get_service(self) -> Any:
        if self._service is not None:
            return self._service
        from services.human_review_service import get_human_review_service
        self._service = get_human_review_service()
        return self._service

    async def request_human_review(
        self,
        *,
        tenant_id: str,
        task_id: str,
        reason: str,
        context: dict,
    ) -> str:
        """发起人工复核请求，返回 request_id。"""
        svc = self._get_service()
        return await svc.create(
            tenant_id=tenant_id,
            task_id=task_id,
            reason=reason,
            context=context,
        )

    async def list_pending(self, tenant_id: str) -> list[dict]:
        svc = self._get_service()
        rows = await svc.list_pending(tenant_id)
        # L10 修补：service 可能返回 dataclass/ORM（带 to_dict）或已是 dict，
        # 不再无条件假设 to_dict 存在。
        return [
            r.to_dict() if hasattr(r, "to_dict") else dict(r)
            for r in rows
        ]

    async def approve(
        self,
        request_id: str,
        reviewer: str,
        *,
        tenant_id: str,
        comment: str = "",
    ) -> bool:
        return await self._get_service().approve(
            request_id, reviewer, tenant_id=tenant_id, comment=comment
        )

    async def reject(
        self,
        request_id: str,
        reviewer: str,
        *,
        tenant_id: str,
        comment: str = "",
    ) -> bool:
        return await self._get_service().reject(
            request_id, reviewer, tenant_id=tenant_id, comment=comment
        )


# =====================================================
# 单例
# =====================================================
_default_adapter: HumanReviewServiceAdapter | None = None


def get_human_review_adapter() -> HumanReviewServiceAdapter:
    """获取默认适配器（单例）。"""
    global _default_adapter
    if _default_adapter is None:
        _default_adapter = HumanReviewServiceAdapter()
    return _default_adapter


def reset_human_review_adapter() -> None:
    """重置默认适配器（测试用）。"""
    global _default_adapter
    _default_adapter = None
