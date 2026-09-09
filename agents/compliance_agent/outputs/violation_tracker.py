"""违规追踪：落库 + 状态变更 + 事件发布。"""

from __future__ import annotations

import asyncio
import logging

from agents.compliance_agent.outputs.violation_repository import (
    ViolationRepository,
)
from core.events import get_event_bus
from core.events.events import ViolationCreatedEvent, ViolationRectifiedEvent
from models.domain import Violation

logger = logging.getLogger(__name__)


class ViolationTracker:
    """违规追踪：落库 + 状态变更 + 事件发布。"""

    def __init__(self, tenant_id: str, repo: ViolationRepository,
                 event_bus=None) -> None:
        self._tenant_id = tenant_id
        self._repo = repo
        self._bus = event_bus or get_event_bus()

    async def record(
        self, violations: list[Violation], inspection_id: str,
    ) -> list[str]:
        """落库 + 回填 inspection_id + 触发 violation.created 事件。
        返回入库的 violation_id 列表。
        """
        if not violations:
            return []
        for v in violations:
            v.inspection_id = inspection_id
            if not v.tenant_id:
                v.tenant_id = self._tenant_id
        await asyncio.to_thread(self._repo.add, violations)
        for v in violations:
            try:
                await self._bus.publish(ViolationCreatedEvent(
                    topic="violation.created",
                    tenant_id=v.tenant_id,
                    source="compliance_agent",
                    payload={
                        "violation_id": v.id,
                        "severity": v.severity.value,
                        "code": v.regulation_id,
                        "version": v.regulation_version,
                    },
                ))
            except Exception as e:
                logger.warning("violation.created 事件发布失败: %s", e)
        return [v.id for v in violations]

    async def mark_rectifying(self, violation_id: str) -> bool:
        ok = await asyncio.to_thread(
            self._repo.update_status, violation_id, "rectifying"
        )
        if ok:
            try:
                await self._bus.publish(ViolationRectifiedEvent(
                    topic="violation.rectified",
                    tenant_id=self._tenant_id,
                    source="compliance_agent",
                    payload={"violation_id": violation_id, "status": "rectifying"},
                ))
            except Exception as e:
                logger.warning("violation.rectified 事件发布失败: %s", e)
        return ok

    async def mark_closed(self, violation_id: str, note: str) -> bool:
        return await asyncio.to_thread(
            self._repo.update_status, violation_id, "closed", note=note
        )

    async def mark_waived(self, violation_id: str, reason: str) -> bool:
        return await asyncio.to_thread(
            self._repo.update_status, violation_id, "waived", note=reason
        )
