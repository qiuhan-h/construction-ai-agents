"""向量库抽象与首版（内存版）实现。

设计：
- VectorStore：抽象接口（upsert / query / delete / count）
- InMemoryVectorStore：纯 Python + 数学库实现（无第三方依赖）
  - 分词：unicode 字符 + 简单停用词过滤
  - 向量化：词袋 + 词频 → L2 归一化
  - 相似度：cosine

阶段四将用 ChromaDB 替换 InMemoryVectorStore，对外接口保持不变。
"""

from __future__ import annotations

import asyncio
import math
import re
import threading
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

# 极简中文停用词（首版，避免对常见虚词过敏感）
_STOP_WORDS: set[str] = {
    "的", "了", "和", "与", "或", "在", "是", "我", "你", "他", "她", "它",
    "我们", "你们", "他们", "这", "那", "这个", "那个", "以及", "等", "为",
    "于", "由", "从", "向", "对", "按", "以", "可", "能", "会", "应", "须",
    "需", "要", "不", "没", "无", "的", "了", "过", "着", "吗", "呢",
}

# 中英文字符 token 切分（连续中英/数字归为一个 token）
_TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    """简单分词：unicode 词字符 + 去停用词 + 小写。"""
    if not text:
        return []
    tokens: list[str] = []
    for m in _TOKEN_PATTERN.finditer(text):
        t = m.group(0).lower()
        if t in _STOP_WORDS or len(t) < 2:
            continue
        tokens.append(t)
    return tokens


@dataclass
class VectorRecord:
    """一条向量记录。"""

    id: str
    tenant_id: str
    text: str
    vector: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorHit:
    """一条检索结果。"""

    id: str
    tenant_id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(ABC):
    """向量库抽象接口（阶段四 ChromaDB 实现将继承此）。"""

    @abstractmethod
    async def upsert(self, records: list[VectorRecord]) -> int:
        ...

    @abstractmethod
    async def query(
        self,
        tenant_id: str,
        text: str,
        *,
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
        min_score: float = 0.0,
    ) -> list[VectorHit]:
        ...

    @abstractmethod
    async def delete(self, ids: Iterable[str]) -> int:
        ...

    @abstractmethod
    def count(self, tenant_id: str | None = None) -> int:
        ...


class InMemoryVectorStore(VectorStore):
    """内存版向量库（首版，无第三方依赖）。"""

    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}
        self._lock = threading.RLock()

    async def upsert(self, records: list[VectorRecord]) -> int:
        return await asyncio.to_thread(self._upsert_sync, records)

    def _upsert_sync(self, records: list[VectorRecord]) -> int:
        with self._lock:
            for r in records:
                if not r.id:
                    raise ValueError("VectorRecord.id 不能为空")
                if not r.tenant_id:
                    raise ValueError("VectorRecord.tenant_id 不能为空（多租户隔离）")
                if not r.vector:
                    r.vector = _to_vector(_tokenize(r.text))
                self._records[r.id] = r
            return len(records)

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

    async def delete(self, ids: Iterable[str]) -> int:
        ids = list(ids)
        return await asyncio.to_thread(self._delete_sync, ids)

    def _delete_sync(self, ids: list[str]) -> int:
        removed = 0
        with self._lock:
            for i in ids:
                if i in self._records:
                    self._records.pop(i, None)
                    removed += 1
        return removed

    def count(self, tenant_id: str | None = None) -> int:
        with self._lock:
            if tenant_id is None:
                return len(self._records)
            return sum(1 for r in self._records.values() if r.tenant_id == tenant_id)

    def all_records(self, tenant_id: str | None = None) -> list[VectorRecord]:
        """测试用：导出全部记录。"""
        with self._lock:
            if tenant_id is None:
                return list(self._records.values())
            return [r for r in self._records.values() if r.tenant_id == tenant_id]


# =====================================================
# 单例
# =====================================================
_default: InMemoryVectorStore | None = None
_default_lock = threading.Lock()


def get_default_vector_store() -> InMemoryVectorStore:
    global _default
    with _default_lock:
        if _default is None:
            _default = InMemoryVectorStore()
        return _default


def reset_default_vector_store() -> None:
    """测试用：重置默认向量库。"""
    global _default
    with _default_lock:
        _default = None


# =====================================================
# 内部：词袋向量化 + 余弦相似度
# =====================================================
def _to_vector(tokens: list[str]) -> dict[str, float]:
    """词频向量（dict[token, count]）。

    P0-4 修补：旧实做把 Counter.items() 排序后丢弃 token 名，仅保留
    counts 列表，按位置 zip 配对——两个完全不相关单 token 文档会
    得到 1.0 相似度。改为保留 token 名做 dict，按 key 交集算内积。
    """
    if not tokens:
        return {}
    counter = Counter(tokens)
    return {k: float(v) for k, v in counter.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    """两个 dict[str, float] 间的余弦相似度。

    按 key 交集算内积（token 名对齐，避免位置错配）。
    """
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _match_filter(metadata: dict[str, Any], flt: dict[str, Any]) -> bool:
    """简单 metadata 过滤（值完全相等）。"""
    for k, v in flt.items():
        if metadata.get(k) != v:
            return False
    return True
