"""事故/案例类向量记录模型（案例检索的知识库单元）。

案例向量供安全审核智能体的 case_retriever 使用：
输入同类工况描述，检索历史事故案例辅助风险评估。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from common.ids import new_id
from common.timeutils import utc_now


class CaseVector(BaseModel):
    """一条事故/工程案例的向量记录元数据。"""

    id: str = Field(default_factory=lambda: new_id("casev"), description="向量记录 ID")
    tenant_id: str | None = Field(
        default=None, description="所属租户 ID（平台级案例库可为空，表示全租户共享）"
    )
    case_id: str = Field(description="案例业务 ID")
    case_type: str = Field(min_length=1, max_length=64, description="事故类型（坍塌/高处坠落/触电/机械伤害等）")
    title: str = Field(min_length=1, description="案例标题")
    summary: str = Field(min_length=1, description="案例摘要（检索主文本）")
    # 结构化要素：支撑"同类工况"匹配与报告引用
    location: str | None = Field(default=None, description="发生地点/项目")
    year: int | None = Field(default=None, ge=1900, le=2100, description="发生年份")
    consequence: str | None = Field(default=None, description="后果（伤亡/损失）")
    cause: str | None = Field(default=None, description="直接原因")
    measures: str | None = Field(default=None, description="防范/整改措施")
    severity: str | None = Field(default=None, max_length=32, description="事故等级（一般/较大/重大/特别重大）")
    metadata: dict[str, Any] = Field(default_factory=dict, description="附加元数据")
    created_at: datetime = Field(default_factory=utc_now)
