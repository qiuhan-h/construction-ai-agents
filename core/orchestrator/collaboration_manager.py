"""多智能体协作时间线。

设计原则（O5）：
- 记录'谁跟谁交互 / 何时 / 状态'；
- 默认内存 dict；4c+ 可注入 persist_path 落 JSON；
- 多租户硬隔离：record_interaction 必须带 tenant_id（在调用方强约束）。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from common.timeutils import to_iso, utc_now

logger = logging.getLogger(__name__)


@dataclass
class CollaborationEntry:
    """一次协作交互记录。"""

    from_agent: str
    to_agent: str
    task_id: str
    status: str
    tenant_id: str = ""
    ts: str = field(default_factory=lambda: to_iso(utc_now()))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "from": self.from_agent,
            "to": self.to_agent,
            "task_id": self.task_id,
            "status": self.status,
            "tenant_id": self.tenant_id,
            "ts": self.ts,
            "metadata": self.metadata,
        }


class CollaborationManager:
    """多智能体协作时间线（task_id → 交互序列）。"""

    def __init__(
        self,
        storage: dict | None = None,
        persist_path: str | None = None,
    ) -> None:
        # task_id -> list[CollaborationEntry]
        self._store: dict[str, list[CollaborationEntry]] = storage or {}
        self._persist_path = persist_path
        if persist_path and os.path.exists(persist_path):
            self._load_from_disk()

    # ---------- 写入 ----------
    def record_interaction(
        self,
        *,
        from_agent: str,
        to_agent: str,
        task_id: str,
        status: str,
        tenant_id: str = "",
        metadata: dict | None = None,
    ) -> None:
        """记录一次交互。"""
        entry = CollaborationEntry(
            from_agent=from_agent,
            to_agent=to_agent,
            task_id=task_id,
            status=status,
            tenant_id=tenant_id,
            metadata=metadata or {},
        )
        self._store.setdefault(task_id, []).append(entry)
        if self._persist_path:
            self._flush_to_disk()

    # ---------- 查询 ----------
    def get_timeline(self, task_id: str) -> list[dict]:
        """获取某个任务的全量交互时间线。"""
        return [e.to_dict() for e in self._store.get(task_id, [])]

    def get_timeline_by_tenant(self, tenant_id: str) -> list[dict]:
        """按租户聚合时间线（多任务汇总）。"""
        out: list[dict] = []
        for entries in self._store.values():
            for e in entries:
                if e.tenant_id == tenant_id:
                    out.append(e.to_dict())
        return out

    def list_task_ids(self) -> list[str]:
        return list(self._store.keys())

    def count(self, task_id: str | None = None) -> int:
        if task_id is None:
            return sum(len(v) for v in self._store.values())
        return len(self._store.get(task_id, []))

    def clear(self) -> None:
        self._store.clear()
        if self._persist_path and os.path.exists(self._persist_path):
            os.remove(self._persist_path)

    # ---------- 持久化 ----------
    def _flush_to_disk(self) -> None:
        if not self._persist_path:
            return
        try:
            data = {
                tid: [e.to_dict() for e in entries]
                for tid, entries in self._store.items()
            }
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning("协作时间线落盘失败: %s", e)

    def _load_from_disk(self) -> None:
        if not self._persist_path:
            return
        try:
            with open(self._persist_path, encoding="utf-8") as f:
                data = json.load(f)
            self._store = {
                tid: [
                    CollaborationEntry(
                        from_agent=d["from"],
                        to_agent=d["to"],
                        task_id=d["task_id"],
                        status=d["status"],
                        tenant_id=d.get("tenant_id", ""),
                        ts=d.get("ts", to_iso(utc_now())),
                        metadata=d.get("metadata", {}),
                    )
                    for d in entries
                ]
                for tid, entries in data.items()
            }
        except (FileNotFoundError, json.JSONDecodeError):
            self._store = {}
