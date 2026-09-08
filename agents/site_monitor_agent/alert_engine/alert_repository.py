"""告警表 SQLAlchemy 仓储（首版内存，阶段五接 DB）。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AlertRepository:
    """告警表仓储（首版内存模式，阶段五接 AlertTable）。"""

    def __init__(self, session_factory: Any | None = None) -> None:
        self._sf = session_factory
        self._mock_store: dict[str, dict[str, Any]] = {}

    def add(self, alert: Any) -> str:
        """落库：返回 alert.id。"""
        if self._sf is not None:
            from models.database import AlertTable

            row = AlertTable(
                id=alert.id, tenant_id=alert.tenant_id,
                project_id=alert.project_id, source=alert.source,
                level=alert.level.value, title=alert.title,
                message=alert.message,
                location_lat=getattr(alert.location, "latitude", None) if getattr(alert, "location", None) else None,
                location_lon=getattr(alert.location, "longitude", None) if getattr(alert, "location", None) else None,
                metric=getattr(alert, "metric", None) or {},
                dedup_key=alert.dedup_key,
                status=alert.status.value,
                triggered_at=alert.triggered_at,
            )
            with self._sf() as s:
                s.add(row)
                s.commit()
            return alert.id
        # Mock 模式
        self._mock_store[alert.id] = {
            "id": alert.id, "tenant_id": alert.tenant_id,
            "project_id": alert.project_id, "source": alert.source,
            "level": alert.level.value, "title": alert.title,
            "message": alert.message,
            "metric": getattr(alert, "metric", None) or {},
            "dedup_key": alert.dedup_key,
            "status": alert.status.value,
            "triggered_at": alert.triggered_at,
        }
        return alert.id

    def get(self, alert_id: str) -> dict | None:
        if self._sf is not None:
            from models.database import AlertTable
            with self._sf() as s:
                row = s.get(AlertTable, alert_id)
                return self._from_row(row) if row else None
        return self._mock_store.get(alert_id)

    def list_by_tenant(
        self, tenant_id: str, *, status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        if self._sf is not None:
            from models.database import AlertTable
            with self._sf() as s:
                q = s.query(AlertTable).filter_by(tenant_id=tenant_id)
                if status:
                    q = q.filter_by(status=status)
                return [self._from_row(r) for r in q.limit(limit).all()]
        out = [r for r in self._mock_store.values() if r["tenant_id"] == tenant_id]
        if status:
            out = [r for r in out if r["status"] == status]
        return out[:limit]

    def list_active(self, tenant_id: str, project_id: str | None = None) -> list[dict]:
        rows = self.list_by_tenant(tenant_id, status="active", limit=500)
        if project_id is None:
            return rows
        return [r for r in rows if r.get("project_id") == project_id]

    def update_status(self, alert_id: str, status: str) -> bool:
        if self._sf is not None:
            from models.database import AlertTable
            with self._sf() as s:
                row = s.get(AlertTable, alert_id)
                if row is None:
                    return False
                row.status = status
                s.commit()
            return True
        row = self._mock_store.get(alert_id)
        if row is None:
            return False
        row["status"] = status
        return True

    @staticmethod
    def _from_row(row: Any) -> dict:
        return {
            "id": row.id, "tenant_id": row.tenant_id,
            "project_id": row.project_id, "source": row.source,
            "level": row.level, "title": row.title,
            "message": row.message,
            "metric": row.metric or {},
            "dedup_key": row.dedup_key,
            "status": row.status,
            "triggered_at": row.triggered_at,
        }
