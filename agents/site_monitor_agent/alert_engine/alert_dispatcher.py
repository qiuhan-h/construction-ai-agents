"""告警分发：去重 + 落库 + 升级 + 事件发布。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from common.constants import AlertLevel
from common.timeutils import utc_now
from core.events import get_event_bus
from core.events.events import (
    AlertResolvedEvent,
    AlertTriggeredEvent,
)

from agents.site_monitor_agent.alert_engine.alert_repository import (
    AlertRepository,
)

logger = logging.getLogger(__name__)


class AlertDispatcher:
    """告警分发：dedup_key + dedup_window 去重 → 落库 → 事件。"""

    def __init__(
        self,
        *,
        dedup_window_seconds: int = 300,
        alert_repo: AlertRepository | None = None,
        notifier: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        self._seen: dict[str, datetime] = {}
        self._window = dedup_window_seconds
        self._repo = alert_repo
        self._notifier = notifier
        self._bus = event_bus or get_event_bus()

    async def dispatch(self, alert: Any) -> bool:
        """返回 true=新告警（已发事件），false=去重命中。"""
        key = f"{alert.source}:{alert.dedup_key or alert.id}"
        now = utc_now()
        if key in self._seen and (now - self._seen[key]).total_seconds() < self._window:
            logger.debug("告警去重命中: key=%s", key)
            return False
        self._seen[key] = now
        self._prune_seen(now)
        if self._repo is not None:
            try:
                await asyncio.to_thread(self._repo.add, alert)
            except Exception as e:
                logger.warning("告警落库失败: %s", e)
        try:
            await self._bus.publish(AlertTriggeredEvent(
                topic="alert.triggered",
                tenant_id=alert.tenant_id,
                source="site_monitor_agent",
                payload=alert.model_dump(mode="json"),
            ))
        except Exception as e:
            logger.warning("alert.triggered 事件发布失败: %s", e)
        if alert.level == AlertLevel.CRITICAL and self._notifier is not None:
            try:
                await self._notifier.send(
                    tenant_id=alert.tenant_id,
                    event_type="alert.critical",
                    severity="critical",
                    title=f"[CRITICAL] {alert.title}",
                    body=alert.message or "",
                    channels=["dingtalk", "sms"],
                )
            except Exception as e:
                logger.warning("CRITICAL 通知发送失败: %s", e)
        return True

    def _prune_seen(self, now: datetime) -> None:
        """清理过期或超量条目，防止 _seen 无限增长。

        - 时间：移除超过 dedup_window_seconds * 2 的条目；
        - 数量：保留时间最近的 10000 条。
        """
        cutoff = now.timestamp() - self._window * 2
        pruned = {
            k: t for k, t in self._seen.items() if t.timestamp() >= cutoff
        }
        if len(pruned) > 10000:
            # 超量时按时间倒序保留最近 10000 条
            sorted_items = sorted(
                pruned.items(), key=lambda kv: kv[1], reverse=True
            )
            pruned = dict(sorted_items[:10000])
        self._seen = pruned

    async def resolve(
        self, alert_id: str, *, tenant_id: str | None = None
    ) -> bool:
        """解决告警。

        优先用传入的 tenant_id；未传时从仓储反查，避免事件总线
        订阅方按 tenant_id 过滤时失效。
        """
        tid = tenant_id
        if self._repo is not None:
            ok = await asyncio.to_thread(
                self._repo.update_status, alert_id, "resolved")
            if tid is None:
                row = await asyncio.to_thread(self._repo.get, alert_id)
                if isinstance(row, dict):
                    tid = row.get("tenant_id", "")
                elif row is not None:
                    tid = getattr(row, "tenant_id", "") or ""
        else:
            ok = True
        try:
            await self._bus.publish(AlertResolvedEvent(
                topic="alert.resolved",
                tenant_id=tid or "",
                source="site_monitor_agent",
                payload={"alert_id": alert_id},
            ))
        except Exception as e:
            logger.warning("alert.resolved 事件发布失败: %s", e)
        return ok
