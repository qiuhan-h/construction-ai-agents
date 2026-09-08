"""地理围栏越界历史持久化（5b.7）。

设计：
- ``GeofenceHistoryStore`` Protocol：统一持久化接口，4d 时期
  ``Geofencing.list_violations_since`` 始终返回空 → 5b.7 让它可以
  从 ``store`` 取真实历史；
- 内存实现 ``InMemoryGeofenceHistoryStore``：环形 buffer（按 fence_id
  分桶，最多 ``max_per_fence`` 条；超出丢弃最旧），线程安全；
- 5b.3 接 ORM 时实现 ``ORMGeofenceHistoryStore``，本模块**预留 factory
  函数** ``get_geofence_history_store()``，环境变量
  ``GEOFENCE_HISTORY_BACKEND=memory`` 切换；
- 5b.7 与 5b.3 解耦：4d ``Geofencing`` 只需把 ``store`` 注入即可，
  4d 接口契约不变（F2 兼容）。

字段：
- 每条 ``FenceViolation`` 历史记录 = 4d 时期 ``FenceViolation`` + ``id`` + ``tenant_id``。
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Iterable, Protocol, runtime_checkable

from agents.site_monitor_agent.gis_monitoring.geofencing import FenceViolation
from common.timeutils import utc_now
from models.domain import GeoPoint

logger = logging.getLogger(__name__)


# =====================================================
# 协议
# =====================================================
@runtime_checkable
class GeofenceHistoryStore(Protocol):
    """地理围栏历史持久化协议。"""

    async def record(self, violation: FenceViolation, *, tenant_id: str) -> str:
        """记录一条越界，返回 id。"""
        ...

    async def list_since(
        self,
        tenant_id: str,
        since: datetime,
        *,
        fence_id: str | None = None,
        device_id: str | None = None,
        limit: int = 100,
    ) -> list[FenceViolation]:
        """列出指定时间之后的历史。"""
        ...

    def count(self, tenant_id: str | None = None) -> int:
        """总条数（按租户可选过滤）。"""
        ...


# =====================================================
# 内存实现（沙箱 / 4d 兼容 / 5b.3 之前的默认）
# =====================================================
class InMemoryGeofenceHistoryStore:
    """内存环形 buffer 实现（线程安全；最大 ``max_per_fence`` 条/fence）。"""

    backend_name: str = "memory"

    def __init__(self, *, max_per_fence: int = 1000) -> None:
        self._max = max_per_fence
        self._lock = threading.RLock()
        # (tenant_id, fence_id) -> deque[FenceViolation]
        self._buckets: dict[tuple[str, str], deque[FenceViolation]] = defaultdict(
            deque
        )
        # id -> (tenant_id, fence_id)
        self._index: dict[str, tuple[str, str]] = {}
        # 全局插入顺序（按 ts 排序兜底用）
        self._order: list[str] = []

    async def record(
        self,
        violation: FenceViolation,
        *,
        tenant_id: str,
    ) -> str:
        if not violation.fence_id:
            raise ValueError("FenceViolation.fence_id 不能为空")
        if not tenant_id:
            raise ValueError("tenant_id 不能为空（多租户隔离）")
        vid = uuid.uuid4().hex
        # 不修改 4d 时期的 FenceViolation；只把 tenant_id 单独存到 index
        with self._lock:
            key = (tenant_id, violation.fence_id)
            bucket = self._buckets[key]
            bucket.append(violation)
            while len(bucket) > self._max:
                bucket.popleft()
            self._index[vid] = key
            self._order.append(vid)
        logger.debug(
            "GeofenceHistory 记录: tenant=%s fence=%s device=%s",
            tenant_id, violation.fence_id, violation.device_id,
        )
        return vid

    async def list_since(
        self,
        tenant_id: str,
        since: datetime,
        *,
        fence_id: str | None = None,
        device_id: str | None = None,
        limit: int = 100,
    ) -> list[FenceViolation]:
        out: list[FenceViolation] = []
        with self._lock:
            # 选桶：(tenant, fence) 二元组
            if fence_id:
                bucket_keys = [(tenant_id, fence_id)]
            else:
                bucket_keys = [
                    k for k in self._buckets.keys() if k[0] == tenant_id
                ]
            for k in bucket_keys:
                for vio in self._buckets.get(k, deque()):
                    if vio.ts < since:
                        continue
                    if device_id and vio.device_id != device_id:
                        continue
                    out.append(vio)
        # 按 ts 倒序
        out.sort(key=lambda v: v.ts, reverse=True)
        return out[:limit]

    def count(self, tenant_id: str | None = None) -> int:
        with self._lock:
            if tenant_id is None:
                return len(self._order)
            return sum(
                1 for (tid, _fid) in self._index.values() if tid == tenant_id
            )


# =====================================================
# 工厂
# =====================================================
_default: GeofenceHistoryStore | None = None
_default_lock = threading.Lock()


def get_geofence_history_store() -> GeofenceHistoryStore:
    """获取进程级单例；环境变量 ``GEOFENCE_HISTORY_BACKEND`` 切换实现。"""
    global _default
    backend = (os.environ.get("GEOFENCE_HISTORY_BACKEND") or "memory").strip().lower()
    with _default_lock:
        if _default is not None:
            return _default
        if backend == "orm":
            try:
                # 5b.3 落地后此分支激活；当前为占位 fallback
                from core.storage.sqlalchemy_repos import (  # type: ignore  # noqa: F401
                    ORMGeofenceHistoryStore,
                )
                _default = ORMGeofenceHistoryStore()  # type: ignore[abstract]
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "ORMGeofenceHistoryStore 不可用（%s）→ fallback memory",
                    e,
                )
                _default = InMemoryGeofenceHistoryStore()
        else:
            _default = InMemoryGeofenceHistoryStore()
        return _default


def reset_default_geofence_history_store() -> None:
    """测试用：重置单例。"""
    global _default
    with _default_lock:
        _default = None
