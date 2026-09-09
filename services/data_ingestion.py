"""数据接入服务（IoT / 文件 / API 三类数据规范化）。

设计原则（O1, O6）：
- 对外：3 个统一入口（ingest_iot / ingest_file / ingest_api）；
- 对内：把异构数据归一化 → 写"传感器点 / 文件指纹 / API 记录"三类轻量模型；
- 4c 首版：内存仓储 + mock TSDB；4c+ 可在仓储层切到 InfluxDB / OSS / HTTPClient；
- 多租户：所有入口必传 tenant_id；规则触发通过 ServiceRegistry。
"""

from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from common.ids import new_id
from common.timeutils import to_iso, utc_now

logger = logging.getLogger(__name__)


# =====================================================
# 数据模型
# =====================================================
@dataclass
class SensorPoint:
    """单条 IoT 传感器读数（已规范化）。"""

    point_id: str
    tenant_id: str
    project_id: str
    sensor_id: str
    metric: str
    value: float
    unit: str
    ts: datetime
    quality: str = "good"  # good | uncertain | bad
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_id": self.point_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "sensor_id": self.sensor_id,
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "ts": to_iso(self.ts),
            "quality": self.quality,
        }


@dataclass
class FileArtifact:
    """文件类数据（图纸/法规 PDF/项目报告等）。"""

    artifact_id: str
    tenant_id: str
    project_id: str
    kind: str           # regulation | drawing | report | case
    filename: str
    size: int
    fingerprint: str    # sha256
    storage_key: str
    uploaded_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "kind": self.kind,
            "filename": self.filename,
            "size": self.size,
            "fingerprint": self.fingerprint,
            "storage_key": self.storage_key,
            "uploaded_at": to_iso(self.uploaded_at),
        }


@dataclass
class APIRecord:
    """第三方 API 拉取的标准化记录。"""

    record_id: str
    tenant_id: str
    endpoint: str
    payload: dict[str, Any]
    fetched_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "tenant_id": self.tenant_id,
            "endpoint": self.endpoint,
            "payload": self.payload,
            "fetched_at": to_iso(self.fetched_at),
        }


# =====================================================
# 仓储（进程内）
# =====================================================
class IngestionRepository:
    """3 类数据统一仓储（线程安全）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._points: dict[str, SensorPoint] = {}
        self._files: dict[str, FileArtifact] = {}
        self._api: dict[str, APIRecord] = {}

    # ---------- 写 ----------
    def add_point(self, p: SensorPoint) -> str:
        with self._lock:
            self._points[p.point_id] = p
        return p.point_id

    def add_file(self, f: FileArtifact) -> str:
        with self._lock:
            self._files[f.artifact_id] = f
        return f.artifact_id

    def add_api(self, r: APIRecord) -> str:
        with self._lock:
            self._api[r.record_id] = r
        return r.record_id

    # ---------- 查 ----------
    def list_points(
        self, tenant_id: str, project_id: str | None = None
    ) -> list[SensorPoint]:
        return [
            p
            for p in self._points.values()
            if p.tenant_id == tenant_id
            and (project_id is None or p.project_id == project_id)
        ]

    def list_files(
        self, tenant_id: str, project_id: str | None = None
    ) -> list[FileArtifact]:
        return [
            f
            for f in self._files.values()
            if f.tenant_id == tenant_id
            and (project_id is None or f.project_id == project_id)
        ]

    def list_api(self, tenant_id: str) -> list[APIRecord]:
        return [r for r in self._api.values() if r.tenant_id == tenant_id]

    def count(self) -> dict[str, int]:
        with self._lock:
            return {
                "points": len(self._points),
                "files": len(self._files),
                "api": len(self._api),
            }


# =====================================================
# 服务
# =====================================================
class DataIngestionService:
    """数据接入服务（3 类入口）。"""

    def __init__(self, repo: IngestionRepository | None = None) -> None:
        self._repo = repo or IngestionRepository()

    @property
    def repo(self) -> IngestionRepository:
        return self._repo

    # ---------- IoT ----------
    async def ingest_iot(
        self,
        *,
        tenant_id: str,
        project_id: str,
        sensor_id: str,
        metric: str,
        value: float,
        unit: str = "",
        ts: datetime | None = None,
        quality: str = "good",
        raw: dict | None = None,
    ) -> SensorPoint:
        """接入一条 IoT 读数。"""
        if not tenant_id or not project_id or not sensor_id or not metric:
            raise ValueError("tenant_id / project_id / sensor_id / metric 必填")
        try:
            v = float(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"value 必须可转 float: {value!r}") from e
        if not isinstance(quality, str) or quality not in ("good", "uncertain", "bad"):
            raise ValueError(f"quality 非法: {quality!r}")
        p = SensorPoint(
            point_id=new_id("pnt"),
            tenant_id=tenant_id,
            project_id=project_id,
            sensor_id=sensor_id,
            metric=metric,
            value=v,
            unit=unit,
            ts=ts or utc_now(),
            quality=quality,
            raw=raw or {},
        )
        self._repo.add_point(p)
        # 4c+：写入 TSDB；此处仅记录日志
        logger.debug(
            "ingest_iot tenant=%s project=%s sensor=%s metric=%s value=%s",
            tenant_id, project_id, sensor_id, metric, v,
        )
        return p

    # ---------- 文件 ----------
    async def ingest_file(
        self,
        *,
        tenant_id: str,
        project_id: str,
        kind: str,
        filename: str,
        content: bytes,
        storage_key: str | None = None,
    ) -> FileArtifact:
        """接入一个文件（计算 fingerprint + 索引）。"""
        if not tenant_id or not project_id or not filename:
            raise ValueError("tenant_id / project_id / filename 必填")
        if kind not in ("regulation", "drawing", "report", "case"):
            raise ValueError(f"kind 非法: {kind!r}")
        if not isinstance(content, bytes | bytearray):
            raise TypeError("content 须为 bytes")
        fp = hashlib.sha256(content).hexdigest()
        art = FileArtifact(
            artifact_id=new_id("art"),
            tenant_id=tenant_id,
            project_id=project_id,
            kind=kind,
            filename=filename,
            size=len(content),
            fingerprint=fp,
            storage_key=storage_key or f"blob-{fp[:16]}",
            uploaded_at=utc_now(),
        )
        self._repo.add_file(art)
        return art

    # ---------- API ----------
    async def ingest_api(
        self,
        *,
        tenant_id: str,
        endpoint: str,
        payload: dict,
    ) -> APIRecord:
        """接入一条 API 拉取记录。"""
        if not tenant_id or not endpoint:
            raise ValueError("tenant_id / endpoint 必填")
        if not isinstance(payload, dict):
            raise TypeError("payload 须为 dict")
        rec = APIRecord(
            record_id=new_id("rec"),
            tenant_id=tenant_id,
            endpoint=endpoint,
            payload=payload,
            fetched_at=utc_now(),
        )
        self._repo.add_api(rec)
        return rec

    # ---------- 批 / 触发 ----------
    async def bulk_ingest_iot(
        self, tenant_id: str, project_id: str, points: list[dict]
    ) -> list[SensorPoint]:
        """批量接入 IoT 点。"""
        out: list[SensorPoint] = []
        for pt in points:
            out.append(
                await self.ingest_iot(tenant_id=tenant_id, project_id=project_id, **pt)
            )
        return out

    def stats(self, tenant_id: str | None = None) -> dict[str, Any]:
        """租户维度的统计。"""
        c = self._repo.count()
        if tenant_id is None:
            return c
        return {
            "tenant_id": tenant_id,
            "points": len(self._repo.list_points(tenant_id)),
            "files": len(self._repo.list_files(tenant_id)),
            "api": len(self._repo.list_api(tenant_id)),
        }


# =====================================================
# 单例
# =====================================================
_default_service: DataIngestionService | None = None


def get_data_ingestion_service() -> DataIngestionService:
    global _default_service
    if _default_service is None:
        _default_service = DataIngestionService()
    return _default_service


def reset_data_ingestion_service() -> None:
    global _default_service
    _default_service = None
