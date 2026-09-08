"""法规/标准/方案类文档的向量记录模型（ChromaDB/Pinecone 通用）。

一条 DocumentVector 对应文档的一个切块（chunk），
embedding 本身不在此模型中——由向量库存储，本模型承载检索所需的元数据。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from common.constants import DocType
from common.ids import new_id
from common.timeutils import utc_now


class DocumentVector(BaseModel):
    """文档切块的向量记录元数据。"""

    id: str = Field(default_factory=lambda: new_id("docv"), description="向量记录 ID")
    tenant_id: str = Field(description="所属租户 ID（多租户检索隔离）")
    doc_id: str = Field(description="源文档 ID（法规/标准/方案标识）")
    doc_type: DocType = Field(description="文档类型")
    title: str = Field(min_length=1, description="文档标题")
    content: str = Field(min_length=1, description="切块正文（用于重排序/引用展示）")
    chunk_index: int = Field(default=0, ge=0, description="切块序号")
    # 版本/有效期：法规与标准必须携带（合规可追溯），方案类可为空
    version: str | None = Field(default=None, description="文档版本（法规版本/标准版本）")
    effective_date: datetime | None = Field(default=None, description="生效日期")
    source: str | None = Field(default=None, description="来源标识（文件名/文号）")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="附加元数据（章节号、关键词等）"
    )
    created_at: datetime = Field(default_factory=utc_now)
