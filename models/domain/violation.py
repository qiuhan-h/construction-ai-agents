"""违规项领域模型（合规校验智能体的输出单元）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from common.constants import ViolationSeverity, ViolationStatus
from common.ids import violation_id
from common.timeutils import utc_now


class Violation(BaseModel):
    """单条违规项。

    合规可追溯要求：regulation_version 必须记录结论产生时依据的
    法规版本（法规会更新/废止），为空即违反平台约束
    （见 error_codes 70003）。
    """

    id: str = Field(default_factory=violation_id, description="违规项 ID (vio_ 前缀)")
    tenant_id: str = Field(description="所属租户 ID")
    inspection_id: str = Field(description="来源审查 ID")
    regulation_id: str | None = Field(
        default=None, description="依据的法规/标准 ID（MCP 资源标识）"
    )
    regulation_version: str | None = Field(
        default=None, description="依据的法规版本（可追溯，审查场景必填）"
    )
    clause: str | None = Field(default=None, max_length=256, description="条款编号/名称")
    description: str = Field(min_length=1, description="违规事实描述")
    severity: ViolationSeverity = Field(default=ViolationSeverity.MEDIUM)
    status: ViolationStatus = Field(default=ViolationStatus.OPEN)
    rectification: str | None = Field(default=None, description="整改要求")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
