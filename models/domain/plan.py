"""施工方案领域模型（安全审核智能体的主要输入）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from common.constants import PlanStatus, PlanType
from common.ids import plan_id
from common.timeutils import utc_now


class ConstructionPlan(BaseModel):
    """专项施工方案。

    attachments 存储文件存储键（core/storage），不直接存磁盘路径，
    以便在本地存储/对象存储之间切换。
    """

    id: str = Field(default_factory=plan_id, description="方案 ID (plan_ 前缀)")
    tenant_id: str = Field(description="所属租户 ID")
    project_id: str = Field(description="所属项目 ID")
    name: str = Field(min_length=1, max_length=256, description="方案名称")
    plan_type: PlanType = Field(default=PlanType.OTHER, description="方案类型")
    version: str = Field(default="1.0", max_length=32, description="方案版本号")
    summary: str | None = Field(default=None, description="方案摘要")
    attachments: list[str] = Field(
        default_factory=list, description="附件存储键列表（方案文本/图纸）"
    )
    status: PlanStatus = Field(default=PlanStatus.DRAFT)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
