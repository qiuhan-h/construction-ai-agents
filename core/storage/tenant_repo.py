"""租户/计费仓储（6b.1 多租户 SaaS）。

设计（与 5b.3 ``sqlalchemy_repos`` 同一套"无依赖可用"原则）：
- ``TenantRepository``      SQLAlchemy ORM 实现（tenants 扩展列 + usage_records + bills）；
- ``InMemoryTenantRepository`` 进程内字典实现，缺 SQLAlchemy / 旧库表结构缺失时的降级后端；
- ``get_tenant_repository()`` 工厂：优先 ORM（启动时探测，失败自动降级内存），
  支持 ``set_tenant_repository_override()`` 测试注入（与 auth override 同一模式）；
- 仓储统一以 **dict** 为契约，服务层负责 dict ↔ Pydantic 模型转换。

注意：
- 配额计数器 ``quota_used`` 为 JSON 列，SQLAlchemy 不追踪原地变更，
  更新时必须**整体赋值新 dict**（本仓储 ``update_tenant`` 已如此处理）；
- 时间列在 SQLite 下读回可能为 naive，统一经 ``common.timeutils`` 归一化。
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from common.timeutils import to_iso, utc_now

logger = logging.getLogger("core.storage.tenant_repo")

# 配额计数器键（与 models/domain/tenant.py QUOTA_METRICS 对齐）
QUOTA_METRICS: tuple[str, ...] = ("api_calls", "storage_gb", "agent_concurrency")


def _default_quota_used() -> dict[str, float]:
    return {"api_calls": 0, "storage_gb": 0.0, "agent_concurrency": 0}


def _iso_or_none(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return to_iso(value)
    except Exception:  # noqa: BLE001
        return str(value)


# =====================================================
# ORM 仓储
# =====================================================
class TenantRepository:
    """租户 / 用量 / 账单 ORM 仓储（后端名 sqlalchemy）。"""

    backend_name: str = "sqlalchemy"

    # ---------- 租户 ----------
    def create_tenant(self, data: dict[str, Any]) -> dict[str, Any]:
        from sqlalchemy.exc import IntegrityError

        from core.storage.sqlalchemy_repos import get_session_scope
        from models.database import TenantTable

        try:
            with get_session_scope() as s:
                row = TenantTable(
                    id=data["tenant_id"],
                    name=data["name"],
                    code=data["code"],
                    contact=data.get("contact"),
                    phone=data.get("phone"),
                    status=data.get("status", "trial"),
                    plan=data.get("plan", "trial"),
                    trial_expires_at=data.get("trial_expires_at"),
                    quota_used=dict(data.get("quota_used") or _default_quota_used()),
                )
                s.add(row)
                s.flush()
                return _tenant_row_to_dict(row)
        except IntegrityError as e:
            raise _conflict(e, data.get("code")) from e
        except Exception as e:  # noqa: BLE001
            # sqlalchemy_repos 会把异常包成 RepositoryError；唯一约束冲突也可能被包装
            if _is_unique_violation(e):
                raise _conflict(e, data.get("code")) from e
            raise

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        from core.storage.sqlalchemy_repos import get_session_scope
        from models.database import TenantTable

        with get_session_scope() as s:
            row = s.get(TenantTable, tenant_id)
            return _tenant_row_to_dict(row) if row is not None else None

    def get_tenant_by_code(self, code: str) -> dict[str, Any] | None:
        from core.storage.sqlalchemy_repos import get_session_scope
        from models.database import TenantTable

        with get_session_scope() as s:
            row = (
                s.query(TenantTable).filter(TenantTable.code == code).first()
            )
            return _tenant_row_to_dict(row) if row is not None else None

    def update_tenant(self, tenant_id: str, **fields: Any) -> dict[str, Any] | None:
        from core.storage.sqlalchemy_repos import get_session_scope
        from models.database import TenantTable

        allowed = {
            "name",
            "contact",
            "phone",
            "status",
            "plan",
            "trial_expires_at",
            "quota_used",
        }
        with get_session_scope() as s:
            row = s.get(TenantTable, tenant_id)
            if row is None:
                return None
            for key, value in fields.items():
                if key not in allowed:
                    continue
                if key == "quota_used":
                    # JSON 列必须整体赋值，SQLAlchemy 才能感知变更
                    row.quota_used = dict(value or _default_quota_used())
                else:
                    setattr(row, key, value)
            s.flush()
            return _tenant_row_to_dict(row)

    def list_tenants(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        from core.storage.sqlalchemy_repos import get_session_scope
        from models.database import TenantTable

        with get_session_scope() as s:
            q = s.query(TenantTable)
            total = q.count()
            rows = (
                q.order_by(TenantTable.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [_tenant_row_to_dict(r) for r in rows], total

    # ---------- 用量流水 ----------
    def add_usage_record(self, data: dict[str, Any]) -> dict[str, Any]:
        from core.storage.sqlalchemy_repos import get_session_scope
        from models.database import UsageRecordTable

        with get_session_scope() as s:
            row = UsageRecordTable(
                id=data.get("usage_id"),  # None 时由 default 生成 usg_
                tenant_id=data["tenant_id"],
                metric=data["metric"],
                amount=float(data.get("amount", 0.0)),
                period=data.get("period"),
                detail=dict(data.get("detail") or {}),
                occurred_at=data.get("occurred_at") or utc_now(),
            )
            s.add(row)
            s.flush()
            return _usage_row_to_dict(row)

    def list_usage(
        self,
        tenant_id: str,
        *,
        metric: str | None = None,
        period: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        from core.storage.sqlalchemy_repos import get_session_scope
        from models.database import UsageRecordTable

        with get_session_scope() as s:
            q = s.query(UsageRecordTable).filter(
                UsageRecordTable.tenant_id == tenant_id
            )
            if metric:
                q = q.filter(UsageRecordTable.metric == metric)
            if period:
                q = q.filter(UsageRecordTable.period == period)
            rows = (
                q.order_by(UsageRecordTable.occurred_at.desc()).limit(limit).all()
            )
            return [_usage_row_to_dict(r) for r in rows]

    def sum_usage(
        self, tenant_id: str, metric: str, *, period: str | None = None
    ) -> float:
        from sqlalchemy import func

        from core.storage.sqlalchemy_repos import get_session_scope
        from models.database import UsageRecordTable

        with get_session_scope() as s:
            q = s.query(func.coalesce(func.sum(UsageRecordTable.amount), 0.0)).filter(
                UsageRecordTable.tenant_id == tenant_id,
                UsageRecordTable.metric == metric,
            )
            if period:
                q = q.filter(UsageRecordTable.period == period)
            return float(q.scalar() or 0.0)

    # ---------- 账单 ----------
    def upsert_bill(self, data: dict[str, Any]) -> dict[str, Any]:
        from core.storage.sqlalchemy_repos import get_session_scope
        from models.database import BillTable

        with get_session_scope() as s:
            row = (
                s.query(BillTable)
                .filter(
                    BillTable.tenant_id == data["tenant_id"],
                    BillTable.period == data["period"],
                )
                .first()
            )
            if row is None:
                row = BillTable(
                    id=data.get("bill_id"),  # None 时由 default 生成 bill_
                    tenant_id=data["tenant_id"],
                    plan=data["plan"],
                    period=data["period"],
                )
                s.add(row)
            row.plan = data["plan"]
            row.usage = dict(data.get("usage") or {})
            row.cost = float(data.get("cost", 0.0))
            row.currency = data.get("currency", "CNY")
            row.status = data.get("status", "issued")
            row.detail = dict(data.get("detail") or {})
            s.flush()
            return _bill_row_to_dict(row)

    def get_bill(self, tenant_id: str, bill_id: str) -> dict[str, Any] | None:
        from core.storage.sqlalchemy_repos import get_session_scope
        from models.database import BillTable

        with get_session_scope() as s:
            row = s.get(BillTable, bill_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return _bill_row_to_dict(row)

    def list_bills(self, tenant_id: str) -> list[dict[str, Any]]:
        from core.storage.sqlalchemy_repos import get_session_scope
        from models.database import BillTable

        with get_session_scope() as s:
            rows = (
                s.query(BillTable)
                .filter(BillTable.tenant_id == tenant_id)
                .order_by(BillTable.period.desc())
                .all()
            )
            return [_bill_row_to_dict(r) for r in rows]


# =====================================================
# 内存降级仓储（接口与 ORM 仓储一致）
# =====================================================
class InMemoryTenantRepository:
    """进程内字典仓储：缺 SQLAlchemy / 表结构过旧时的降级后端。"""

    backend_name: str = "memory"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tenants: dict[str, dict[str, Any]] = {}
        self._usage: list[dict[str, Any]] = []
        self._bills: dict[str, dict[str, Any]] = {}
        self._usage_seq = 0
        self._bill_seq = 0

    # ---------- 租户 ----------
    def create_tenant(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if any(t["code"] == data["code"] for t in self._tenants.values()):
                from common.exceptions import TenantConflictError

                raise TenantConflictError(
                    f"租户编码已存在: {data['code']}",
                    details={"code": data["code"]},
                )
            now = to_iso(utc_now())
            row = {
                "tenant_id": data["tenant_id"],
                "name": data["name"],
                "code": data["code"],
                "contact": data.get("contact"),
                "phone": data.get("phone"),
                "status": data.get("status", "trial"),
                "plan": data.get("plan", "trial"),
                "trial_expires_at": _iso_or_none(data.get("trial_expires_at")),
                "quota_used": dict(data.get("quota_used") or _default_quota_used()),
                "created_at": now,
                "updated_at": now,
            }
            self._tenants[row["tenant_id"]] = dict(row)
            return dict(row)

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._tenants.get(tenant_id)
            return dict(row) if row else None

    def get_tenant_by_code(self, code: str) -> dict[str, Any] | None:
        with self._lock:
            for row in self._tenants.values():
                if row["code"] == code:
                    return dict(row)
        return None

    def update_tenant(self, tenant_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {
            "name",
            "contact",
            "phone",
            "status",
            "plan",
            "trial_expires_at",
            "quota_used",
        }
        with self._lock:
            row = self._tenants.get(tenant_id)
            if row is None:
                return None
            for key, value in fields.items():
                if key not in allowed:
                    continue
                if key == "trial_expires_at":
                    row[key] = _iso_or_none(value)
                elif key == "quota_used":
                    row[key] = dict(value or _default_quota_used())
                else:
                    row[key] = value
            row["updated_at"] = to_iso(utc_now())
            return dict(row)

    def list_tenants(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        with self._lock:
            rows = sorted(
                self._tenants.values(), key=lambda t: t["created_at"], reverse=True
            )
            total = len(rows)
            return [dict(r) for r in rows[offset : offset + limit]], total

    # ---------- 用量流水 ----------
    def add_usage_record(self, data: dict[str, Any]) -> dict[str, Any]:
        from common.ids import new_id

        with self._lock:
            self._usage_seq += 1
            row = {
                "usage_id": data.get("usage_id") or new_id("usg"),
                "tenant_id": data["tenant_id"],
                "metric": data["metric"],
                "amount": float(data.get("amount", 0.0)),
                "period": data.get("period"),
                "detail": dict(data.get("detail") or {}),
                "occurred_at": to_iso(data.get("occurred_at") or utc_now()),
                "created_at": to_iso(utc_now()),
            }
            self._usage.append(row)
            return dict(row)

    def list_usage(
        self,
        tenant_id: str,
        *,
        metric: str | None = None,
        period: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = [
                dict(r)
                for r in self._usage
                if r["tenant_id"] == tenant_id
                and (metric is None or r["metric"] == metric)
                and (period is None or r["period"] == period)
            ]
        rows.sort(key=lambda r: r["occurred_at"], reverse=True)
        return rows[:limit]

    def sum_usage(
        self, tenant_id: str, metric: str, *, period: str | None = None
    ) -> float:
        with self._lock:
            return sum(
                r["amount"]
                for r in self._usage
                if r["tenant_id"] == tenant_id
                and r["metric"] == metric
                and (period is None or r["period"] == period)
            )

    # ---------- 账单 ----------
    def upsert_bill(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            existing = next(
                (
                    b
                    for b in self._bills.values()
                    if b["tenant_id"] == data["tenant_id"]
                    and b["period"] == data["period"]
                ),
                None,
            )
            if existing is not None:
                existing.update(
                    {
                        "plan": data["plan"],
                        "usage": dict(data.get("usage") or {}),
                        "cost": float(data.get("cost", 0.0)),
                        "currency": data.get("currency", "CNY"),
                        "status": data.get("status", "issued"),
                        "detail": dict(data.get("detail") or {}),
                    }
                )
                return dict(existing)
            from common.ids import new_id

            row = {
                "bill_id": data.get("bill_id") or new_id("bill"),
                "tenant_id": data["tenant_id"],
                "plan": data["plan"],
                "period": data["period"],
                "usage": dict(data.get("usage") or {}),
                "cost": float(data.get("cost", 0.0)),
                "currency": data.get("currency", "CNY"),
                "status": data.get("status", "issued"),
                "detail": dict(data.get("detail") or {}),
                "created_at": to_iso(utc_now()),
            }
            self._bills[row["bill_id"]] = row
            return dict(row)

    def get_bill(self, tenant_id: str, bill_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._bills.get(bill_id)
            if row is None or row["tenant_id"] != tenant_id:
                return None
            return dict(row)

    def list_bills(self, tenant_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = [b for b in self._bills.values() if b["tenant_id"] == tenant_id]
        rows.sort(key=lambda b: b["period"], reverse=True)
        return [dict(r) for r in rows]


# =====================================================
# 工厂 + 测试 override
# =====================================================
_repo: Any = None
_repo_lock = threading.Lock()
_test_override: Any = None


def _probe_orm() -> bool:
    """探测 ORM 后端是否可用（建表 + 简单查询）。

    旧版 SQLite 文件缺 6b.1 新列时 ``create_all`` 不会自动 ALTER，
    探测查询会抛 OperationalError → 返回 False，工厂降级内存后端。
    """
    try:
        from core.storage.sqlalchemy_repos import (
            BackendUnavailableError,
            get_session_scope,
            init_database_for_dev,
        )
        from models.database import TenantTable

        init_database_for_dev()  # Base.metadata.create_all，幂等
        with get_session_scope() as s:
            s.query(TenantTable).first()
        return True
    except BackendUnavailableError as e:
        logger.warning("SQLAlchemy 不可用 → 租户仓储降级内存: %s", e)
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("租户 ORM 探测失败（旧库表结构?）→ 降级内存: %s", e)
        return False


def get_tenant_repository() -> Any:
    """获取租户仓储单例：测试 override 优先，否则 ORM 探测后降级内存。"""
    global _repo
    if _test_override is not None:
        return _test_override
    if _repo is None:
        with _repo_lock:
            if _repo is None:
                _repo = TenantRepository() if _probe_orm() else InMemoryTenantRepository()
                logger.info("租户仓储后端: %s", _repo.backend_name)
    return _repo


def set_tenant_repository_override(repo: Any | None) -> None:
    """测试用：注入自定义仓储（如 InMemoryTenantRepository）；传 None 清除。"""
    global _test_override
    with _repo_lock:
        _test_override = repo


def reset_tenant_repository() -> None:
    """测试用：清除 override 并重置单例（下次 get 重新探测）。"""
    global _repo, _test_override
    with _repo_lock:
        _test_override = None
        _repo = None


# =====================================================
# 内部：row → dict
# =====================================================
def _tenant_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "tenant_id": row.id,
        "name": row.name,
        "code": row.code,
        "contact": row.contact,
        "phone": row.phone,
        "status": row.status,
        "plan": row.plan,
        "trial_expires_at": _iso_or_none(row.trial_expires_at),
        "quota_used": dict(row.quota_used or _default_quota_used()),
        "created_at": _iso_or_none(row.created_at),
        "updated_at": _iso_or_none(row.updated_at),
    }


def _usage_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "usage_id": row.id,
        "tenant_id": row.tenant_id,
        "metric": row.metric,
        "amount": float(row.amount),
        "period": row.period,
        "detail": dict(row.detail or {}),
        "occurred_at": _iso_or_none(row.occurred_at),
        "created_at": _iso_or_none(row.created_at),
    }


def _bill_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "bill_id": row.id,
        "tenant_id": row.tenant_id,
        "plan": row.plan,
        "period": row.period,
        "usage": dict(row.usage or {}),
        "cost": float(row.cost),
        "currency": row.currency,
        "status": row.status,
        "detail": dict(row.detail or {}),
        "created_at": _iso_or_none(row.created_at),
    }


def _is_unique_violation(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}"
    return any(
        token in text
        for token in ("UNIQUE", "unique", "IntegrityError", "duplicate", "Duplicate")
    )


def _conflict(exc: BaseException, code: str | None) -> Exception:
    from common.exceptions import TenantConflictError

    return TenantConflictError(
        f"租户编码已存在: {code or '?'}",
        details={"code": code, "reason": "duplicate_code"},
    )


__all__ = [
    "TenantRepository",
    "InMemoryTenantRepository",
    "get_tenant_repository",
    "set_tenant_repository_override",
    "reset_tenant_repository",
    "QUOTA_METRICS",
]
