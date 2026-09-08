"""审查/检查记录领域模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from common.constants import AgentName, AuditConclusion, InspectionStatus
from common.ids import inspection_id
from common.timeutils import utc_now


class Inspection(BaseModel):
    """一次审查任务（由某个智能体执行）。

    生命周期：PENDING -> RUNNING -> COMPLETED/FAILED；
    COMPLETED 时 conclusion 必达（三值之一）。
    """

    id: str = Field(default_factory=inspection_id, description="审查 ID (insp_ 前缀)")
    tenant_id: str = Field(description="所属租户 ID")
    project_id: str = Field(description="所属项目 ID")
    plan_id: str | None = Field(default=None, description="被审方案 ID（合规/安全审核必填）")
    agent: AgentName = Field(description="执行智能体")
    status: InspectionStatus = Field(default=InspectionStatus.PENDING)
    conclusion: AuditConclusion | None = Field(
        default=None, description="审查结论（完成时必填）"
    )
    summary: str | None = Field(default=None, description="审查摘要")
    report_id: str | None = Field(default=None, description="关联报告 ID")
    started_at: datetime | None = Field(default=None, description="开始时间")
    finished_at: datetime | None = Field(default=None, description="结束时间")
    created_at: datetime = Field(default_factory=utc_now)
