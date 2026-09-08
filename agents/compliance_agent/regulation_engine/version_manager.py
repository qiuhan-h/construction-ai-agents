"""法规版本管理：增/废/替 → 触发 regulation.updated 事件。"""

from __future__ import annotations

import logging
from typing import Any

from common.timeutils import to_iso, utc_now
from core.events import get_event_bus

from agents.compliance_agent.regulation_engine.mcp_loader import (
    RegulationLoader,
)

logger = logging.getLogger(__name__)


class VersionManager:
    """法规版本管理：增/废/替 → 触发 regulation.updated 事件。"""

    def __init__(self, tenant_id: str, loader: RegulationLoader,
                 event_bus=None):
        self._tenant_id = tenant_id
        self._loader = loader
        self._bus = event_bus or get_event_bus()

    async def add_regulation(self, code: str, version: str, **meta: Any) -> None:
        """注册新版本：写入 loader + 触发 regulation.updated 事件。"""
        self._loader.add(code=code, version=version, **meta)
        await self._publish("added", code, version, **meta)
        logger.info("法规新增: %s-%s tenant=%s", code, version, self._tenant_id)

    async def deprecate(self, code: str, version: str, reason: str) -> None:
        ok = self._loader.deprecate(code, version, reason=reason)
        if ok:
            await self._publish("deprecated", code, version, reason=reason)
            logger.info("法规废止: %s-%s reason=%s", code, version, reason)

    async def replace(self, old: tuple[str, str], new: tuple[str, str]) -> None:
        self._loader.replace(old, new)
        await self._publish(
            "replaced",
            new[0],
            new[1],
            old_version=old[1],
            new_version=new[1],
        )
        logger.info("法规替换: %s-%s → %s-%s", old[0], old[1], new[0], new[1])

    async def _publish(self, action: str, code: str, version: str, **meta: Any) -> None:
        # 动态 import 避免循环（events.py 中定义）
        from core.events.events import RegulationUpdatedEvent
        await self._bus.publish(RegulationUpdatedEvent(
            topic="regulation.updated",
            tenant_id=self._tenant_id,
            source="compliance_agent",
            payload={"action": action, "code": code, "version": version, **meta},
        ))
