"""国标/行标加载：把 MCP 资源（regulation://、standard://）的能力桥接到
safety_audit_agent 内部计算流程。

设计：
- 通过 core.mcp.server.get_mcp_service() 调用资源；
- 失败抛 AgentParseError（业务可读）；
- 加载到内存向量库供后续检索。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from agents.safety_audit_agent.knowledge_base.vector_store import (
    VectorRecord,
    get_default_vector_store,
)
from common.constants import DocType, ResourceType
from common.exceptions import AgentParseError
from common.ids import project_id as _project_id_factory  # 防重名
from common.timeutils import to_iso, utc_now

logger = logging.getLogger("agents.safety_audit_agent.knowledge_base.standard_loader")


@dataclass
class RegulationSummary:
    """法规摘要。"""

    code: str
    version: str
    name: str
    effective_date: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def uri(self) -> str:
        return f"regulation://{self.code}/{self.version}"


@dataclass
class StandardSummary:
    """标准摘要。"""

    code: str
    version: str
    name: str
    effective_date: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def uri(self) -> str:
        return f"standard://{self.code}/{self.version}"


class StandardLoader:
    """标准/法规资源桥接：list + read + 加载到向量库。"""

    def __init__(self, vector_store=None) -> None:
        self._vector_store = vector_store or get_default_vector_store()

    @staticmethod
    def _mcp_service():
        from core.mcp.server import get_mcp_service
        return get_mcp_service()

    async def list_regulations(self, tenant_id: str) -> list[RegulationSummary]:
        """列出可用法规（首版经 regulation_resource 暴露；为空时返回 []）。"""
        try:
            svc = self._mcp_service()
            res = await svc.read_resource(
                "regulation://_list", tenant_id=tenant_id
            )
        except Exception as e:
            logger.info("list_regulations 退化返回空列表: %s", e)
            return []
        items = (res.get("content") or []) if isinstance(res, dict) else []
        out: list[RegulationSummary] = []
        for it in items:
            out.append(
                RegulationSummary(
                    code=str(it.get("code", "")),
                    version=str(it.get("version", "")),
                    name=str(it.get("name", "")),
                    effective_date=it.get("effective_date"),
                    metadata=it.get("metadata", {}) or {},
                )
            )
        return out

    async def list_standards(self, tenant_id: str) -> list[StandardSummary]:
        try:
            svc = self._mcp_service()
            res = await svc.read_resource(
                "standard://_list", tenant_id=tenant_id
            )
        except Exception as e:
            logger.info("list_standards 退化返回空列表: %s", e)
            return []
        items = (res.get("content") or []) if isinstance(res, dict) else []
        out: list[StandardSummary] = []
        for it in items:
            out.append(
                StandardSummary(
                    code=str(it.get("code", "")),
                    version=str(it.get("version", "")),
                    name=str(it.get("name", "")),
                    effective_date=it.get("effective_date"),
                    metadata=it.get("metadata", {}) or {},
                )
            )
        return out

    async def read_regulation(
        self, code: str, version: str, *, tenant_id: str = ""
    ) -> str:
        """按 URI 读法规全文。失败抛 AgentParseError。"""
        uri = f"regulation://{code}/{version}"
        try:
            svc = self._mcp_service()
            res = await svc.read_resource(uri, tenant_id=tenant_id)
        except Exception as e:
            raise AgentParseError(
                f"读取法规失败: {uri}",
                details={"uri": uri, "error": str(e)},
            ) from e
        content = res.get("content", "") if isinstance(res, dict) else ""
        if not content:
            raise AgentParseError(
                f"法规内容为空: {uri}", details={"uri": uri}
            )
        return str(content)

    async def load_to_vector_store(
        self,
        tenant_id: str,
        code: str,
        version: str,
        *,
        max_chunk_chars: int = 1000,
    ) -> int:
        """把法规全文切分后写入向量库。返回写入条数。"""
        text = await self.read_regulation(code, version, tenant_id=tenant_id)
        chunks = _chunk_text(text, max_chars=max_chunk_chars)
        records: list[VectorRecord] = []
        for i, c in enumerate(chunks):
            rid = f"{_project_id_factory()}_reg_{code}_{version}_{i}"
            records.append(
                VectorRecord(
                    id=rid,
                    tenant_id=tenant_id,
                    text=c,
                    metadata={
                        "doc_type": DocType.REGULATION.value,
                        "code": code,
                        "version": version,
                        "chunk_index": i,
                        "uri": f"regulation://{code}/{version}",
                        "loaded_at": to_iso(utc_now()),
                        "resource_type": ResourceType.REGULATION.value,
                    },
                )
            )
        if records:
            await self._vector_store.upsert(records)
        return len(records)


def _chunk_text(text: str, *, max_chars: int = 1000) -> list[str]:
    """按段落（空行）切分；单段超长则硬切。"""
    if not text:
        return []
    paragraphs = [p.strip() for p in re_split_paragraphs(text) if p.strip()]
    chunks: list[str] = []
    buf: list[str] = []
    cur = 0
    for p in paragraphs:
        if cur + len(p) > max_chars and buf:
            chunks.append("\n\n".join(buf))
            buf, cur = [], 0
        if len(p) > max_chars:
            # 单段硬切
            if buf:
                chunks.append("\n\n".join(buf))
                buf, cur = [], 0
            for k in range(0, len(p), max_chars):
                chunks.append(p[k : k + max_chars])
            continue
        buf.append(p)
        cur += len(p) + 2
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


def re_split_paragraphs(text: str) -> list[str]:
    # L13 修补：re 已在模块顶部导入，移除函数内 import。
    return re.split(r"\n\s*\n", text)
