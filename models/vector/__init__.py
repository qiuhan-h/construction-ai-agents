"""向量模型：文档/案例向量记录的元数据定义（embedding 由向量库存储）。"""

from models.vector.case_vectors import CaseVector
from models.vector.document_vectors import DocumentVector

__all__ = [
    "CaseVector",
    "DocumentVector",
]
