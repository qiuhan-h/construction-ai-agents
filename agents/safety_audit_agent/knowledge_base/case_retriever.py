"""案例检索：在知识库中按相似度检索 Top-K 事故案例。

数据来源：
- 阶段三：默认 InMemoryVectorStore；可注入外部数据
- 阶段四：接 ChromaDB（仍走 VectorStore 抽象）

多租户隔离：query 时强制 tenant_id 过滤。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.safety_audit_agent.knowledge_base.vector_store import (
    VectorHit,
    VectorRecord,
    VectorStore,
    get_default_vector_store,
)


@dataclass
class CaseHit:
    """单个检索到的案例。"""

    case_id: str
    title: str
    summary: str
    score: float
    case_type: str | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "summary": self.summary,
            "score": round(self.score, 4),
            "case_type": self.case_type,
            "metadata": self.metadata or {},
        }


class CaseRetriever:
    """案例检索器（按相似度 Top-K）。"""

    def __init__(self, vector_store: VectorStore | None = None) -> None:
        self._vector_store = vector_store or get_default_vector_store()

    async def index_cases(
        self,
        tenant_id: str,
        cases: list[dict[str, Any]],
    ) -> int:
        """把一批 case 灌入向量库。"""
        records: list[VectorRecord] = []
        for c in cases:
            cid = c["case_id"]
            records.append(
                VectorRecord(
                    id=f"case_{tenant_id}_{cid}",
                    tenant_id=tenant_id,
                    text=_compose_case_text(c),
                    metadata={
                        "case_id": cid,
                        "title": c.get("title", ""),
                        "case_type": c.get("case_type"),
                        "summary": c.get("summary", ""),
                        "doc_type": "case",
                    },
                )
            )
        if records:
            await self._vector_store.upsert(records)
        return len(records)

    async def search_cases(
        self,
        tenant_id: str,
        query: str,
        *,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[CaseHit]:
        """按相似度返回案例 Top-K。"""
        hits: list[VectorHit] = await self._vector_store.query(
            tenant_id,
            query,
            top_k=top_k,
            filter={"doc_type": "case"},
            min_score=min_score,
        )
        return [
            CaseHit(
                case_id=h.metadata.get("case_id", h.id),
                title=h.metadata.get("title", ""),
                summary=h.metadata.get("summary", h.text[:200]),
                score=h.score,
                case_type=h.metadata.get("case_type"),
                metadata=dict(h.metadata),
            )
            for h in hits
        ]


def _compose_case_text(case: dict[str, Any]) -> str:
    parts = [
        case.get("title", ""),
        case.get("case_type", ""),
        case.get("summary", ""),
        case.get("description", ""),
    ]
    return "\n".join(p for p in parts if p)
