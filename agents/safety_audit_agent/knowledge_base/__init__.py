"""施工安全审核智能体：知识库。

设计要点：
- 阶段三实现：内存版向量库 + 余弦相似度（不引入 numpy/scipy 等重型依赖）；
- 阶段四将替换为 ChromaDB（已预留在 core.langchain.tools.vector_search）。
"""

from agents.safety_audit_agent.knowledge_base.case_retriever import (
    CaseRetriever,
)
from agents.safety_audit_agent.knowledge_base.standard_loader import (
    StandardLoader,
)
from agents.safety_audit_agent.knowledge_base.vector_store import (
    InMemoryVectorStore,
    VectorHit,
    VectorRecord,
    VectorStore,
    get_default_vector_store,
)

__all__ = [
    "CaseRetriever",
    "StandardLoader",
    "VectorStore",
    "InMemoryVectorStore",
    "VectorRecord",
    "VectorHit",
    "get_default_vector_store",
]
