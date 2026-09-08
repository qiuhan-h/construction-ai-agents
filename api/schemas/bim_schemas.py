"""BIM 数据 Schema（6d.1）。

设计原则：
- 字段精简，适配边缘端 / 移动端消费（响应体尽量小）；
- 与 BIMConnector / BIMRealConnector 返回结构对齐；
- 进度项含偏差 + 级别，便于边缘端直接告警。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BIMElement(BaseModel):
    """BIM 构件详情。"""

    element_id: str = Field(..., description="构件 ID")
    name: str = Field(default="", description="构件名称")
    type: str = Field(default="", description="IFC 类型（IfcBeam / IfcColumn …）")
    properties: dict = Field(default_factory=dict, description="属性键值对")


class BIMProjectTreeNode(BaseModel):
    """BIM 项目树节点（递归）。"""

    id: str = Field(..., description="节点 ID")
    type: str = Field(default="", description="IFC 类型")
    name: str = Field(default="", description="节点名称")
    children: list["BIMProjectTreeNode"] = Field(
        default_factory=list, description="子节点"
    )


BIMProjectTreeNode.model_rebuild()


class BIMProgressItem(BaseModel):
    """进度项（计划 vs 实际 + 偏差）。"""

    element_id: str = Field(..., description="构件 ID")
    name: str = Field(default="", description="构件名称")
    plan_pct: float = Field(default=0.0, description="计划进度 0-100")
    actual_pct: float = Field(default=0.0, description="实际进度 0-100")
    deviation: float = Field(default=0.0, description="偏差（正=超前，负=滞后）")
    level: str = Field(default="info", description="告警级别（critical/warning/info）")


class BIMProgressResponse(BaseModel):
    """进度对比响应。"""

    project_id: str = Field(..., description="项目 ID")
    items: list[BIMProgressItem] = Field(
        default_factory=list, description="进度项列表"
    )
    total: int = Field(default=0, description="构件总数")
    delayed: int = Field(default=0, description="滞后构件数")
    ahead: int = Field(default=0, description="超前构件数")
    source: str = Field(default="mock", description="数据来源（mock/aps/bim360）")


__all__ = [
    "BIMElement",
    "BIMProjectTreeNode",
    "BIMProgressItem",
    "BIMProgressResponse",
]
