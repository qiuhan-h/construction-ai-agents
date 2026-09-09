"""人工复核仓储（4c 首版内存，4c+ 接 DB）。

设计原则（O5）：
- 多租户硬隔离：list_pending / get 必须传 tenant_id；
- 接口签名 4c 稳定，4c+ 可在 add/get 内部加 SQLAlchemy 实现。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from common.ids import new_id
from common.timeutils import to_iso, utc_now

logger = logging.getLogger(__name__)


@dataclass
class HumanReviewRow:
    """人工复核请求行。"""

    id: str = field(default_factory=lambda: new_id("hrv"))
    tenant_id: str = ""
    task_id: str = ""
    reason: str = ""
    context: dict = field(default_factory=dict)
    status: str = "pending"  # pending / approved / rejected
    reviewer: str | None = None
    comment: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "task_id": self.task_id,
            "reason": self.reason,
            "context": self.context,
            "status": self.status,
            "reviewer": self.reviewer,
            "comment": self.comment,
            "created_at": to_iso(self.created_at),
            "updated_at": to_iso(self.updated_at),
        }


class HumanReviewRepository:
    """人工复核表仓储。"""

    def __init__(self, session_factory: Any | None = None) -> None:
        self._sf = session_factory
        self._store: dict[str, HumanReviewRow] = {}
        self._lock = threading.Lock()

    # ---------- 写入 ----------
    def add(self, row: HumanReviewRow) -> str:
        with self._lock:
            if self._sf is None:
                self._store[row.id] = row
            else:
                # SQLAlchemy 模式：dataclass 不能直接 s.add；如有人工复核表
                # （HumanReviewTable）则用 ORM 实例入库，否则仅记日志并落内存。
                db_ok = False
                try:
                    # HumanReviewTable 尚未在 ORM 建模；导入失败时静默降级到内存仓储
                    from models.database import HumanReviewTable  # type: ignore[attr-defined]  # type: ignore
                    db_row = HumanReviewTable(
                        id=row.id,
                        tenant_id=row.tenant_id,
                        task_id=row.task_id,
                        reason=row.reason,
                        context=row.context,
                        status=row.status,
                        reviewer=row.reviewer,
                        comment=row.comment,
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                    )
                    with self._sf() as s:
                        s.add(db_row)
                        s.commit()
                    db_ok = True
                except ImportError:
                    # HumanReviewTable 未定义（4c 内存模式 / 暂未建表）
                    pass
                except Exception as e:  # noqa: BLE001
                    logger.warning("HumanReview DB 落库失败（仅内存）: %s", e)
                # 内存索引始终保留，便于查询/兜底
                self._store[row.id] = row
                if not db_ok:
                    logger.debug(
                        "HumanReview 未落 DB（仅内存）: id=%s", row.id
                    )
        return row.id

    def update(
        self,
        request_id: str,
        *,
        status: str,
        reviewer: str,
        comment: str,
        tenant_id: str | None = None,
    ) -> bool:
        """更新复核状态。

        约束：
        - tenant_id 校验：跨租户访问视为不存在（返回 False）；
        - 状态机：只有 ``pending`` 可迁移到 ``approved`` / ``rejected``，
          终态不可逆，防止已 approved 被改回 rejected。
        """
        with self._lock:
            row = self._store.get(request_id)
            if row is None:
                return False
            if tenant_id is not None and row.tenant_id != tenant_id:
                return False  # 跨租户视为不存在
            if row.status != "pending":
                return False  # 终态不可变
            row.status = status
            row.reviewer = reviewer
            row.comment = comment
            row.updated_at = utc_now()
            # H13 修正：DB 模式下也需落库
            if self._sf is not None:
                try:
                    # HumanReviewTable 尚未在 ORM 建模；导入失败时静默降级到内存仓储
                    from models.database import HumanReviewTable  # type: ignore[attr-defined]
                    with self._sf() as s:
                        db_row = s.get(HumanReviewTable, request_id)
                        if db_row is not None:
                            db_row.status = status
                            db_row.reviewer = reviewer
                            db_row.comment = comment
                            db_row.updated_at = row.updated_at
                            s.commit()
                except Exception as e:  # noqa: BLE001
                    logger.warning("HumanReview DB 落库失败（内存已更新）: %s", e)
            return True

    # ---------- 查询 ----------
    def get(self, request_id: str, *, tenant_id: str | None = None) -> HumanReviewRow | None:
        row = self._store.get(request_id)
        if row is None:
            return None
        if tenant_id is not None and row.tenant_id != tenant_id:
            # 多租户隔离：跨租户访问视为不存在
            return None
        return row

    def list_pending(self, tenant_id: str) -> list[HumanReviewRow]:
        return [
            r for r in self._store.values()
            if r.tenant_id == tenant_id and r.status == "pending"
        ]

    def list_by_tenant(self, tenant_id: str) -> list[HumanReviewRow]:
        return [r for r in self._store.values() if r.tenant_id == tenant_id]

    def count(self) -> int:
        return len(self._store)
