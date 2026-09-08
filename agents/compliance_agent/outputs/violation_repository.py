"""违规表 SQLAlchemy 仓储：落库 + 状态变更。"""

from __future__ import annotations

import logging
from typing import Any

from models.database import ViolationTable

logger = logging.getLogger(__name__)


class ViolationRepository:
    """违规表仓储（首版支持 session_factory 注入；无 session_factory 时走 mock）。"""

    def __init__(self, session_factory: Any | None = None) -> None:
        self._sf = session_factory  # SQLAlchemy sessionmaker；None = mock 内存
        self._mock_store: dict[str, dict[str, Any]] = {}

    def add(self, violations: list[Any]) -> int:
        """批量插入 violations 表。返回写入条数。"""
        if not violations:
            return 0
        if self._sf is not None:
            with self._sf() as s:
                rows = [self._to_row(v) for v in violations]
                s.add_all(rows)
                s.commit()
            return len(rows)
        # Mock 模式
        for v in violations:
            vid = getattr(v, "id", None) or f"vio_mock_{id(v)}"
            self._mock_store[vid] = {
                "id": vid,
                "tenant_id": getattr(v, "tenant_id", ""),
                "inspection_id": getattr(v, "inspection_id", ""),
                "regulation_id": getattr(v, "regulation_id", ""),
                "regulation_version": getattr(v, "regulation_version", ""),
                "clause": getattr(v, "clause", ""),
                "description": getattr(v, "description", ""),
                "severity": getattr(v.severity, "value", "") if getattr(v, "severity", None) else "",
                "status": getattr(v.status, "value", "open") if getattr(v, "status", None) else "open",
                "rectification": getattr(v, "rectification", None),
            }
        return len(violations)

    def get(self, violation_id: str) -> dict[str, Any] | None:
        if self._sf is not None:
            with self._sf() as s:
                row = s.get(ViolationTable, violation_id)
                return self._from_row(row) if row else None
        return self._mock_store.get(violation_id)

    def list_by_inspection(self, inspection_id: str) -> list[dict[str, Any]]:
        if self._sf is not None:
            with self._sf() as s:
                rows = s.query(ViolationTable).filter_by(inspection_id=inspection_id).all()
                return [self._from_row(r) for r in rows]
        return [r for r in self._mock_store.values()
                if r["inspection_id"] == inspection_id]

    def list_by_tenant(
        self, tenant_id: str, *, status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if self._sf is not None:
            with self._sf() as s:
                q = s.query(ViolationTable).filter_by(tenant_id=tenant_id)
                if status:
                    q = q.filter_by(status=status)
                return [self._from_row(r) for r in q.limit(limit).all()]
        out = [r for r in self._mock_store.values() if r["tenant_id"] == tenant_id]
        if status:
            out = [r for r in out if r["status"] == status]
        return out[:limit]

    def update_status(
        self, violation_id: str, status: str, note: str | None = None,
    ) -> bool:
        if self._sf is not None:
            with self._sf() as s:
                row = s.get(ViolationTable, violation_id)
                if row is None:
                    return False
                row.status = status
                if note:
                    row.rectification = (row.rectification or "") + f"\n[{status}] {note}"
                s.commit()
            return True
        row = self._mock_store.get(violation_id)
        if row is None:
            return False
        row["status"] = status
        if note:
            row["rectification"] = (row.get("rectification") or "") + f"\n[{status}] {note}"
        return True

    @staticmethod
    def _to_row(v: Any) -> ViolationTable:
        return ViolationTable(
            id=v.id,
            tenant_id=v.tenant_id,
            project_id=getattr(v, "project_id", ""),
            inspection_id=v.inspection_id,
            regulation_id=v.regulation_id,
            regulation_version=v.regulation_version,
            clause=v.clause,
            description=v.description,
            severity=v.severity.value,
            status=v.status.value,
            rectification=v.rectification,
        )

    @staticmethod
    def _from_row(row: ViolationTable) -> dict[str, Any]:
        return {
            "id": row.id, "tenant_id": row.tenant_id, "project_id": row.project_id,
            "inspection_id": row.inspection_id,
            "regulation_id": row.regulation_id, "regulation_version": row.regulation_version,
            "clause": row.clause, "description": row.description,
            "severity": row.severity, "status": row.status,
            "rectification": row.rectification,
        }
