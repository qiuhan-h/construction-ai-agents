"""InMemoryVectorStore（5b.2 迁移版）。

来源：
- 4d 时期位于 ``agents/safety_audit_agent/knowledge_base/vector_store.py``；
- 5b.2 把它迁到 ``core/vector_store/in_memory.py``，并实现新协议
  ``core.vector_store.base.VectorStore``。

行为：
- 词袋 + 词频 → L2 归一化（与 4d 完全一致，业务层检索结果不变）；
- 多租户严格隔离（query 时 ``r.tenant_id != tenant_id`` 直接跳过）；
- ``upsert`` 同步路径放线程池，避免阻塞事件循环。
"""

from __future__ import annotations

import asyncio
import math
import re
import threading
from collections import Counter
from typing import Any, Iterable

from core.vector_store.base import VectorHit, VectorRecord, VectorStoreError

# 极简中文停用词（与 4d 时期一致，避免行为偏移）
_STOP_WORDS: set[str] = {
    "的", "了", "和", "与", "或", "在", "是", "我", "你", "他", "她", "它",
    "我们", "你们", "他们", "这", "那", "这个", "那个", "以及", "等", "为",
    "于", "由", "从", "向", "对", "按", "以", "可", "能", "会", "应", "须",
    "需", "要", "不", "没", "无", "的", "了", "过", "着", "吗", "呢",
}

_TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    tokens: list[str] = []
    for m in _TOKEN_PATTERN.finditer(text):
        t = m.group(0).lower()
        if t in _STOP_WORDS or len(t) < 2:
            continue
        tokens.append(t)
    return tokens


def _to_vector(tokens: list[str]) -> list[float]:
    if not tokens:
        return []
    counter = Counter(tokens)
    return [float(c) for _, c in sorted(counter.items())]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _match_filter(metadata: dict[str, Any], flt: dict[str, Any]) -> bool:
    for k, v in flt.items():
        if metadata.get(k) != v:
            return False
    return True


class InMemoryVectorStore:
    """内存版向量库（无第三方依赖；沙箱 / 测试用）。"""

    backend_name: str = "memory"

    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}
        self._lock = threading.RLock()

    # ---- 协议方法 ----
    async def upsert(self, records: list[VectorRecord]) -> int:
        return await asyncio.to_thread(self._upsert_sync, records)

    async def query(
        self,
        tenant_id: str,
        text: str,
        *,
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
        min_score: float = 0.0,
    ) -> list[VectorHit]:
        return await asyncio.to_thread(
            self._query_sync, tenant_id, text, top_k, filter, min_score
        )

    async def delete(self, ids: Iterable[str]) -> int:
        ids = list(ids)
        return await asyncio.to_thread(self._delete_sync, ids)

    def count(self, tenant_id: str | None = None) -> int:
        with self._lock:
            if tenant_id is None:
                return len(self._records)
            return sum(1 for r in self._records.values() if r.tenant_id == tenant_id)

    # ---- 同步实现 ----
    def _upsert_sync(self, records: list[VectorRecord]) -> int:
        with self._lock:
            for r in records:
                if not r.id:
                    raise VectorStoreError("VectorRecord.id 不能为空")
                if not r.tenant_id:
                    raise VectorStoreError(
                        "VectorRecord.tenant_id 不能为空（多租户隔离）"
                    )
                if not r.vector:
                    r.vector = _to_vector(_tokenize(r.text))
                self._records[r.id] = r
            return len(records)

    def _query_sync(
        self,
        tenant_id: str,
        text: str,
        top_k: int,
        filter: dict[str, Any] | None,
        min_score: float,
    ) -> list[VectorHit]:
        q_vec = _to_vector(_tokenize(text))
        if not q_vec:
            return []
        candidates: list[tuple[float, VectorRecord]] = []
        with self._lock:
            for r in self._records.values():
                if r.tenant_id != tenant_id:
                    continue
                if filter and not _match_filter(r.metadata, filter):
                    continue
                score = _cosine(q_vec, r.vector)
                if score < min_score:
                    continue
                candidates.append((score, r))
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [
            VectorHit(
                id=r.id,
                tenant_id=r.tenant_id,
                text=r.text,
                score=score,
                metadata=dict(r.metadata),
            )
            for score, r in candidates[:top_k]
        ]

    def _delete_sync(self, ids: list[str]) -> int:
        removed = 0
        with self._lock:
            for i in ids:
                if i in self._records:
                    self._records.pop(i, None)
                    removed += 1
        return removed

    # ---- 辅助（测试 / 运维）----
    def all_records(self, tenant_id: str | None = None) -> list[VectorRecord]:
        with self._lock:
            if tenant_id is None:
                return list(self._records.values())
            return [r for r in self._records.values() if r.tenant_id == tenant_id]
