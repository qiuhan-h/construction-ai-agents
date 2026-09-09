"""SQLAlchemy ORM 业务仓储（5b.3 实做）。

设计：
- 进程级单例 engine + SessionLocal（懒加载）；
- ``get_session_scope()`` 同步上下文管理器：自动 commit/rollback/close；
- ``DATABASE_URL`` 占位 → 回退 SQLite + 警告（与 5b.2 / 5b.7 一致的"无依赖可用"原则）；
- 5 个业务仓储：
    - ``ReviewReportRepository``     审查报告
    - ``ViolationRepository``        违规项
    - ``RegulationRepository``       法规条文
    - ``GeofenceRepository``         围栏定义
    - ``GeofenceViolationRepository`` 围栏越界事件
- 5b.7 ``GeofenceHistoryStore`` ORM 实现 ``ORMGeofenceHistoryStore`` 也放在本文件
  （避免循环依赖 + 集中所有 ORM 仓储入口）。
- 业务仓储以**纯 dict** 形式返回（与 4d 时期 reports_router 兼容）。

为什么不用 async：
- FastAPI 路由已经跑在事件循环里，``run_in_executor`` 即可；
- 5b.3 阶段 SQLAlchemy 2.0 同步会话 + 显式 session_scope 简单可靠；
- 后续可在此基础上加 ``async_scoped_session``，5b.3 暂不引入。
"""

from __future__ import annotations

import builtins
import logging
import os
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any, Protocol, runtime_checkable

from common.timeutils import to_iso
from core.storage.base import (
    BackendUnavailableError,
    Repository,
    RepositoryError,
)
from models.database import (
    Base,
    GeofenceTable,
    GeofenceViolationTable,
    RegulationTable,
    ReviewReportTable,
    ViolationTable,
)

logger = logging.getLogger("core.storage.sqlalchemy_repos")

# =====================================================
# 配置
# =====================================================
# 沙箱 / dev 默认 SQLite；生产由 DATABASE_URL 覆盖
_FALLBACK_URL = "sqlite:///./data/caai.db"
# 与 .env.example 对齐：所有凭据占位为 "需要补充实际链接"
_PLACEHOLDER = "需要补充实际链接"


def _resolve_database_url() -> str:
    """解析 DATABASE_URL：占位 → 警告 + 退回 SQLite。"""
    url = os.environ.get("DATABASE_URL", _FALLBACK_URL)
    if not url or url == _PLACEHOLDER:
        logger.warning(
            "DATABASE_URL 未配置或为占位值 → fallback SQLite: %s",
            _FALLBACK_URL,
        )
        return _FALLBACK_URL
    return url


# =====================================================
# 引擎 / Session（懒加载单例）
# =====================================================
_engine = None
_SessionLocal = None
_init_lock = threading.Lock()


def _sqlalchemy_available() -> bool:
    try:
        import sqlalchemy  # type: ignore  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _init_engine() -> None:
    """初始化进程级 engine + SessionLocal。"""
    global _engine, _SessionLocal
    if _engine is not None:
        return
    with _init_lock:
        if _engine is not None:
            return
        if not _sqlalchemy_available():
            raise BackendUnavailableError("SQLAlchemy 未安装")
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        url = _resolve_database_url()
        # SQLite 需要 check_same_thread=False；其他 DB 走 pool_pre_ping
        connect_args: dict[str, Any] = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(
            url,
            pool_pre_ping=not url.startswith("sqlite"),
            connect_args=connect_args,
        )
        _SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=_engine, expire_on_commit=False
        )
        logger.info("SQLAlchemy engine 已初始化: %s", url)


def _ensure_schema() -> None:
    """开发环境用：``Base.metadata.create_all``。生产靠 Alembic 迁移。"""
    _init_engine()
    assert _engine is not None
    Base.metadata.create_all(_engine)


@contextmanager
def get_session_scope() -> Iterator[Any]:
    """同步会话上下文管理器（自动 commit / rollback / close）。"""
    _init_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise RepositoryError(f"SQL 操作失败: {e}") from e
    finally:
        session.close()


# =====================================================
# 工具：record ↔ dict
# =====================================================
def _to_iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return to_iso(value)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        return str(value)


# =====================================================
# 审查报告仓储
# =====================================================
class ReviewReportRepository(Repository):
    """审查报告 ORM 仓储（5b.3 替代 4d 时期 ``_REPORT_STORE``）。"""

    backend_name: str = "sqlalchemy"

    # ---- Repository 协议 ----
    def add(self, item: dict[str, Any]) -> str:
        rid = item.get("report_id") or item.get("id")
        if not rid:
            raise ValueError("report_id 不能为空")
        with get_session_scope() as s:
            existing = s.get(ReviewReportTable, rid)
            if existing is not None:
                # 幂等 upsert：同 id 覆盖
                existing.tenant_id = item.get("tenant_id", existing.tenant_id)
                existing.project_id = item.get("project_id", existing.project_id)
                existing.inspection_id = item.get(
                    "inspection_id", existing.inspection_id
                )
                existing.agent = item.get("agent", existing.agent)
                existing.title = item.get("title", existing.title)
                existing.content = item.get("content", existing.content)
                existing.conclusion = item.get("conclusion", existing.conclusion)
                existing.regulation_versions = item.get(
                    "regulation_versions", existing.regulation_versions or {}
                )
                existing.signature = item.get("signature", existing.signature)
                existing.status = item.get("status", existing.status)
                return existing.id
            row = ReviewReportTable(
                id=rid,
                tenant_id=item["tenant_id"],
                project_id=item["project_id"],
                inspection_id=item.get("inspection_id", "insp_unknown"),
                agent=item.get("agent", "safety_audit_agent"),
                title=item["title"],
                content=item["content"],
                conclusion=item.get("conclusion", "pass"),
                regulation_versions=item.get("regulation_versions", {}),
                signature=item.get("signature"),
                status=item.get("status", "draft"),
            )
            s.add(row)
            return row.id

    def get(self, key: str, *, tenant_id: str | None = None) -> dict[str, Any] | None:
        with get_session_scope() as s:
            row = s.get(ReviewReportTable, key)
            if row is None:
                return None
            if tenant_id is not None and row.tenant_id != tenant_id:
                return None
            return _report_to_dict(row)

    def list(
        self,
        tenant_id: str,
        *,
        project_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        with get_session_scope() as s:
            q = s.query(ReviewReportTable).filter(
                ReviewReportTable.tenant_id == tenant_id
            )
            if project_id:
                q = q.filter(ReviewReportTable.project_id == project_id)
            total = q.count()
            rows = (
                q.order_by(ReviewReportTable.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            items = [_report_to_dict(r) for r in rows]
            return items, total

    # ---- 业务便捷方法 ----
    def count(self, tenant_id: str | None = None) -> int:
        with get_session_scope() as s:
            q = s.query(ReviewReportTable)
            if tenant_id:
                q = q.filter(ReviewReportTable.tenant_id == tenant_id)
            return q.count()


# =====================================================
# 违规项仓储
# =====================================================
class ViolationRepository(Repository):
    """违规项 ORM 仓储。"""

    backend_name: str = "sqlalchemy"

    def add(self, item: dict[str, Any]) -> str:
        vid = item.get("violation_id") or item.get("id")
        if not vid:
            raise ValueError("violation_id 不能为空")
        with get_session_scope() as s:
            existing = s.get(ViolationTable, vid)
            if existing is not None:
                existing.description = item.get("description", existing.description)
                existing.severity = item.get("severity", existing.severity)
                existing.status = item.get("status", existing.status)
                existing.rectification = item.get(
                    "rectification", existing.rectification
                )
                existing.regulation_version = item.get(
                    "regulation_version", existing.regulation_version
                )
                return existing.id
            row = ViolationTable(
                id=vid,
                tenant_id=item["tenant_id"],
                inspection_id=item["inspection_id"],
                regulation_id=item.get("regulation_id"),
                regulation_version=item.get("regulation_version"),
                clause=item.get("clause"),
                description=item["description"],
                severity=item.get("severity", "medium"),
                status=item.get("status", "open"),
                rectification=item.get("rectification"),
            )
            s.add(row)
            return row.id

    def get(self, key: str, *, tenant_id: str | None = None) -> dict[str, Any] | None:
        with get_session_scope() as s:
            row = s.get(ViolationTable, key)
            if row is None or (
                tenant_id is not None and row.tenant_id != tenant_id
            ):
                return None
            return {
                "violation_id": row.id,
                "tenant_id": row.tenant_id,
                "inspection_id": row.inspection_id,
                "regulation_id": row.regulation_id,
                "regulation_version": row.regulation_version,
                "clause": row.clause,
                "description": row.description,
                "severity": row.severity,
                "status": row.status,
                "rectification": row.rectification,
                "created_at": _to_iso(row.created_at),
                "updated_at": _to_iso(row.updated_at),
            }

    def list(
        self,
        tenant_id: str,
        *,
        project_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        with get_session_scope() as s:
            q = s.query(ViolationTable).filter(ViolationTable.tenant_id == tenant_id)
            # Violation 无 project_id 字段；如有需要通过 inspection 关联过滤
            total = q.count()
            rows = q.order_by(ViolationTable.created_at.desc()).offset(offset).limit(limit).all()
            items = [
                {
                    "violation_id": r.id,
                    "tenant_id": r.tenant_id,
                    "inspection_id": r.inspection_id,
                    "regulation_id": r.regulation_id,
                    "regulation_version": r.regulation_version,
                    "clause": r.clause,
                    "description": r.description,
                    "severity": r.severity,
                    "status": r.status,
                    "rectification": r.rectification,
                    "created_at": _to_iso(r.created_at),
                }
                for r in rows
            ]
            return items, total


# =====================================================
# 法规条文仓储
# =====================================================
class RegulationRepository(Repository):
    """法规条文 ORM 仓储。"""

    backend_name: str = "sqlalchemy"

    def add(self, item: dict[str, Any]) -> str:
        with get_session_scope() as s:
            tenant_id = item["tenant_id"]
            code = item["code"]
            version = item["version"]
            article = item.get("article")
            existing = (
                s.query(RegulationTable)
                .filter(
                    RegulationTable.tenant_id == tenant_id,
                    RegulationTable.code == code,
                    RegulationTable.version == version,
                    RegulationTable.article == article,
                )
                .first()
            )
            if existing is not None:
                existing.title = item.get("title", existing.title)
                existing.chapter = item.get("chapter", existing.chapter)
                existing.content = item.get("content", existing.content)
                existing.keywords = item.get("keywords", existing.keywords or [])
                existing.related_regulations = item.get(
                    "related_regulations", existing.related_regulations or []
                )
                return existing.id
            row = RegulationTable(
                tenant_id=tenant_id,
                code=code,
                version=version,
                title=item.get("title", ""),
                chapter=item.get("chapter"),
                article=article,
                content=item.get("content", ""),
                keywords=item.get("keywords", []),
                related_regulations=item.get("related_regulations", []),
            )
            s.add(row)
            s.flush()
            return row.id

    def get(self, key: str, *, tenant_id: str | None = None) -> dict[str, Any] | None:
        with get_session_scope() as s:
            row = s.get(RegulationTable, key)
            if row is None or (
                tenant_id is not None and row.tenant_id != tenant_id
            ):
                return None
            return _regulation_to_dict(row)

    def list(
        self,
        tenant_id: str,
        *,
        project_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        with get_session_scope() as s:
            q = s.query(RegulationTable).filter(RegulationTable.tenant_id == tenant_id)
            if project_id:
                # 法规域不直接关联 project，project_id 参数保留兼容
                pass
            total = q.count()
            rows = q.order_by(RegulationTable.code, RegulationTable.version).offset(offset).limit(limit).all()
            return [_regulation_to_dict(r) for r in rows], total

    # ---- 业务便捷 ----
    def find_by_code(
        self, tenant_id: str, code: str, *, version: str | None = None
    ) -> builtins.list[dict[str, Any]]:
        with get_session_scope() as s:
            q = s.query(RegulationTable).filter(
                RegulationTable.tenant_id == tenant_id,
                RegulationTable.code == code,
            )
            if version:
                q = q.filter(RegulationTable.version == version)
            return [_regulation_to_dict(r) for r in q.all()]


# =====================================================
# 地理围栏仓储
# =====================================================
class GeofenceRepository(Repository):
    """地理围栏 ORM 仓储。"""

    backend_name: str = "sqlalchemy"

    def add(self, item: dict[str, Any]) -> str:
        fid = item.get("fence_id") or item.get("id")
        with get_session_scope() as s:
            if fid:
                existing = s.get(GeofenceTable, fid)
                if existing is not None:
                    if (
                        item.get("tenant_id")
                        and existing.tenant_id != item["tenant_id"]
                    ):
                        raise RepositoryError(
                            f"fence_id={fid} 已存在但 tenant_id 不一致"
                        )
                    existing.name = item.get("name", existing.name)
                    existing.fence_type = item.get("fence_type", existing.fence_type)
                    existing.geometry = item.get("geometry", existing.geometry)
                    existing.source = item.get("source", existing.source)
                    existing.is_active = item.get("is_active", existing.is_active)
                    existing.description = item.get(
                        "description", existing.description
                    )
                    existing.project_id = item.get(
                        "project_id", existing.project_id
                    )
                    existing.center_lon = item.get(
                        "center_lon", existing.center_lon
                    )
                    existing.center_lat = item.get(
                        "center_lat", existing.center_lat
                    )
                    return existing.id
            row = GeofenceTable(
                id=fid,  # None 时由 default 生成
                tenant_id=item["tenant_id"],
                name=item["name"],
                fence_type=item.get("fence_type", "polygon"),
                geometry=item["geometry"],
                source=item.get("source", "manual"),
                is_active=item.get("is_active", True),
                description=item.get("description"),
                project_id=item.get("project_id"),
                center_lon=item.get("center_lon"),
                center_lat=item.get("center_lat"),
            )
            s.add(row)
            s.flush()
            return row.id

    def get(self, key: str, *, tenant_id: str | None = None) -> dict[str, Any] | None:
        with get_session_scope() as s:
            row = s.get(GeofenceTable, key)
            if row is None or (
                tenant_id is not None and row.tenant_id != tenant_id
            ):
                return None
            return _geofence_to_dict(row)

    def list(
        self,
        tenant_id: str,
        *,
        project_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        with get_session_scope() as s:
            q = s.query(GeofenceTable).filter(GeofenceTable.tenant_id == tenant_id)
            if project_id:
                q = q.filter(GeofenceTable.project_id == project_id)
            total = q.count()
            rows = q.order_by(GeofenceTable.created_at.desc()).offset(offset).limit(limit).all()
            return [_geofence_to_dict(r) for r in rows], total


# =====================================================
# 地理围栏越界仓储
# =====================================================
class GeofenceViolationRepository(Repository):
    """地理围栏越界事件 ORM 仓储。"""

    backend_name: str = "sqlalchemy"

    def add(self, item: dict[str, Any]) -> str:
        with get_session_scope() as s:
            row = GeofenceViolationTable(
                id=item.get("violation_id") or item.get("id"),
                tenant_id=item["tenant_id"],
                geofence_id=item["geofence_id"],
                project_id=item.get("project_id"),
                device_id=item["device_id"],
                location=item["location"],
                status=item.get("status", "open"),
                occurred_at=item.get("occurred_at"),
                acknowledged_at=item.get("acknowledged_at"),
                resolved_at=item.get("resolved_at"),
                note=item.get("note"),
                extra=item.get("extra", {}),
            )
            s.add(row)
            s.flush()
            return row.id

    def get(self, key: str, *, tenant_id: str | None = None) -> dict[str, Any] | None:
        with get_session_scope() as s:
            row = s.get(GeofenceViolationTable, key)
            if row is None or (
                tenant_id is not None and row.tenant_id != tenant_id
            ):
                return None
            return _geofence_violation_to_dict(row)

    def list(
        self,
        tenant_id: str,
        *,
        project_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        with get_session_scope() as s:
            q = s.query(GeofenceViolationTable).filter(
                GeofenceViolationTable.tenant_id == tenant_id
            )
            if project_id:
                q = q.filter(GeofenceViolationTable.project_id == project_id)
            total = q.count()
            rows = (
                q.order_by(GeofenceViolationTable.occurred_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [_geofence_violation_to_dict(r) for r in rows], total

    # ---- 业务便捷：按 fence 列表 ----
    def list_by_fence(
        self,
        tenant_id: str,
        fence_id: str,
        *,
        limit: int = 100,
    ) -> builtins.list[dict[str, Any]]:
        with get_session_scope() as s:
            rows = (
                s.query(GeofenceViolationTable)
                .filter(
                    GeofenceViolationTable.tenant_id == tenant_id,
                    GeofenceViolationTable.geofence_id == fence_id,
                )
                .order_by(GeofenceViolationTable.occurred_at.desc())
                .limit(limit)
                .all()
            )
            return [_geofence_violation_to_dict(r) for r in rows]


# =====================================================
# 5b.7 ORM 适配：GeofenceHistoryStore ORM 实现
# =====================================================
@runtime_checkable
class _GeofenceHistoryStoreProto(Protocol):
    async def record(self, violation: Any, *, tenant_id: str) -> str: ...
    async def list_since(
        self,
        tenant_id: str,
        since: Any,
        *,
        fence_id: str | None = None,
        device_id: str | None = None,
        limit: int = 100,
    ) -> list[Any]: ...
    def count(self, tenant_id: str | None = None) -> int: ...


class ORMGeofenceHistoryStore:
    """5b.7 ``GeofenceHistoryStore`` ORM 实现（5b.3 落地）。

    - 与 ``InMemoryGeofenceHistoryStore`` 接口 100% 一致；
    - 4d ``Geofencing`` 通过 ``get_geofence_history_store()`` 工厂选择后端，
      不需要改任何业务代码；
    - ``FenceViolation`` 来自 ``agents.site_monitor_agent.gis_monitoring.geofencing``，
      与本仓储解耦。
    """

    backend_name: str = "orm"

    def __init__(self) -> None:
        self._violations = GeofenceViolationRepository()
        self._geofences = GeofenceRepository()

    async def record(self, violation: Any, *, tenant_id: str) -> str:
        # 延迟 import：FenceViolation 与 GeoPoint 在 4d 由业务链导入，
        # 沙箱缺 pydantic 时整条 import 链会爆；故推迟到调用时再 import
        from common.timeutils import utc_now

        point = getattr(violation, "point", None)
        location: dict[str, Any] = {}
        if point is not None:
            location = {
                "lon": float(getattr(point, "lon", 0.0)),
                "lat": float(getattr(point, "lat", 0.0)),
            }
        extra = dict(getattr(violation, "metadata", {}) or {})
        # 将 fence 名 / 类型 一并塞进 extra，方便回查
        try:
            fence = self._geofences.get(violation.fence_id, tenant_id=tenant_id)
            if fence is not None:
                extra.setdefault("fence_name", fence.get("name"))
                extra.setdefault("fence_type", fence.get("fence_type"))
        except Exception:  # noqa: BLE001
            pass
        return self._violations.add(
            {
                "tenant_id": tenant_id,
                "geofence_id": violation.fence_id,
                "device_id": violation.device_id,
                "location": location,
                "status": "open",
                "occurred_at": getattr(violation, "ts", None) or utc_now(),
                "extra": extra,
            }
        )

    async def list_since(
        self,
        tenant_id: str,
        since: Any,
        *,
        fence_id: str | None = None,
        device_id: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        from agents.site_monitor_agent.gis_monitoring.geofencing import FenceViolation
        from common.timeutils import ensure_utc, from_iso, utc_now
        from models.domain import GeoPoint

        since = ensure_utc(since) if since is not None else None
        # 直接走 violation 仓储的 list_by_fence；如需跨 fence 聚合，走 list()
        rows: list[dict[str, Any]]
        if fence_id:
            rows = self._violations.list_by_fence(tenant_id, fence_id, limit=limit)
        else:
            rows, _ = self._violations.list(tenant_id, limit=limit)
        out: list[FenceViolation] = []
        for r in rows:
            if since is not None:
                ts_iso = r.get("occurred_at")
                if not ts_iso:
                    continue
                # r["occurred_at"] 已经是 ISO 字符串
                if from_iso(ts_iso) < since:
                    continue
            if device_id and r.get("device_id") != device_id:
                continue
            loc = r.get("location") or {}
            # location 兼容两种键：GeoPoint 序列化（longitude/latitude）与旧格式（lon/lat）
            point = GeoPoint(
                longitude=float(loc.get("longitude", loc.get("lon", 0.0))),
                latitude=float(loc.get("latitude", loc.get("lat", 0.0))),
            )
            occurred = r.get("occurred_at")
            out.append(
                FenceViolation(
                    fence_id=r["geofence_id"],
                    device_id=r["device_id"],
                    point=point,
                    ts=from_iso(occurred) if occurred else utc_now(),
                    metadata=r.get("extra") or {},
                )
            )
        return out

    def count(self, tenant_id: str | None = None) -> int:
        with get_session_scope() as s:
            q = s.query(GeofenceViolationTable)
            if tenant_id:
                q = q.filter(GeofenceViolationTable.tenant_id == tenant_id)
            return q.count()


# =====================================================
# 工厂
# =====================================================
_review_reports: ReviewReportRepository | None = None
_violations: ViolationRepository | None = None
_regulations: RegulationRepository | None = None
_geofences: GeofenceRepository | None = None
_geofence_violations: GeofenceViolationRepository | None = None
_factory_lock = threading.Lock()


def get_review_report_repository() -> ReviewReportRepository:
    global _review_reports
    with _factory_lock:
        if _review_reports is None:
            _review_reports = ReviewReportRepository()
        return _review_reports


def get_violation_repository() -> ViolationRepository:
    global _violations
    with _factory_lock:
        if _violations is None:
            _violations = ViolationRepository()
        return _violations


def get_regulation_repository() -> RegulationRepository:
    global _regulations
    with _factory_lock:
        if _regulations is None:
            _regulations = RegulationRepository()
        return _regulations


def get_geofence_repository() -> GeofenceRepository:
    global _geofences
    with _factory_lock:
        if _geofences is None:
            _geofences = GeofenceRepository()
        return _geofences


def get_geofence_violation_repository() -> GeofenceViolationRepository:
    global _geofence_violations
    with _factory_lock:
        if _geofence_violations is None:
            _geofence_violations = GeofenceViolationRepository()
        return _geofence_violations


def reset_default_repositories() -> None:
    """测试用：重置全部仓储单例 + 引擎（必须重启进程级 engine 才能连新库）。"""
    global _review_reports, _violations, _regulations, _geofences, _geofence_violations
    with _factory_lock:
        _review_reports = None
        _violations = None
        _regulations = None
        _geofences = None
        _geofence_violations = None


def init_database_for_dev() -> None:
    """开发用：Base.metadata.create_all 全部表。生产请走 Alembic 迁移。"""
    _ensure_schema()


# =====================================================
# 内部：to_dict 辅助
# =====================================================
def _report_to_dict(row: Any) -> dict[str, Any]:
    return {
        "report_id": row.id,
        "tenant_id": row.tenant_id,
        "project_id": row.project_id,
        "inspection_id": row.inspection_id,
        "agent": row.agent,
        "title": row.title,
        "content": row.content,
        "conclusion": row.conclusion,
        "regulation_versions": row.regulation_versions or {},
        "signature": row.signature,
        "status": row.status,
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
    }


def _regulation_to_dict(row: Any) -> dict[str, Any]:
    return {
        "regulation_id": row.id,
        "tenant_id": row.tenant_id,
        "code": row.code,
        "version": row.version,
        "title": row.title,
        "chapter": row.chapter,
        "article": row.article,
        "content": row.content,
        "keywords": row.keywords or [],
        "related_regulations": row.related_regulations or [],
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
    }


def _geofence_to_dict(row: Any) -> dict[str, Any]:
    return {
        "fence_id": row.id,
        "tenant_id": row.tenant_id,
        "project_id": row.project_id,
        "name": row.name,
        "fence_type": row.fence_type,
        "geometry": row.geometry,
        "source": row.source,
        "is_active": row.is_active,
        "description": row.description,
        "center_lon": row.center_lon,
        "center_lat": row.center_lat,
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
    }


def _geofence_violation_to_dict(row: Any) -> dict[str, Any]:
    return {
        "violation_id": row.id,
        "tenant_id": row.tenant_id,
        "geofence_id": row.geofence_id,
        "project_id": row.project_id,
        "device_id": row.device_id,
        "location": row.location,
        "status": row.status,
        "occurred_at": _to_iso(row.occurred_at),
        "acknowledged_at": _to_iso(row.acknowledged_at),
        "resolved_at": _to_iso(row.resolved_at),
        "note": row.note,
        "extra": row.extra or {},
        "created_at": _to_iso(row.created_at),
    }


# 兼容 Iterable 协议使用
_ = Iterable  # noqa: F841  保留供将来扩展


__all__ = [
    "ReviewReportRepository",
    "ViolationRepository",
    "RegulationRepository",
    "GeofenceRepository",
    "GeofenceViolationRepository",
    "ORMGeofenceHistoryStore",
    "get_review_report_repository",
    "get_violation_repository",
    "get_regulation_repository",
    "get_geofence_repository",
    "get_geofence_violation_repository",
    "reset_default_repositories",
    "init_database_for_dev",
    "get_session_scope",
    "Repository",
    "RepositoryError",
    "BackendUnavailableError",
]
