"""审查报告领域模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from common.constants import AgentName, AuditConclusion, ReportStatus
from common.ids import report_id
from common.timeutils import utc_now


class ReviewReport(BaseModel):
    """审查报告（安全审核/合规校验的正式输出物）。

    regulation_versions: {法规ID: 版本} 快照，保证报告结论可追溯；
    signature: 由 report_signer 生成的电子签章指纹，status 升到
    SIGNED 后 content 不得再修改（改则须重新签章）。
    """

    id: str = Field(default_factory=report_id, description="报告 ID (rpt_ 前缀)")
    tenant_id: str = Field(description="所属租户 ID")
    project_id: str = Field(description="所属项目 ID")
    inspection_id: str = Field(description="来源审查 ID")
    agent: AgentName = Field(description="产出智能体")
    title: str = Field(min_length=1, max_length=256, description="报告标题")
    content: str = Field(min_length=1, description="报告正文（Markdown）")
    conclusion: AuditConclusion = Field(description="审查结论")
    regulation_versions: dict[str, str] = Field(
        default_factory=dict, description="法规ID -> 版本 快照（合规报告必填）"
    )
    signature: str | None = Field(default=None, description="电子签章指纹（SIGNED 后必填）")
    status: ReportStatus = Field(default=ReportStatus.DRAFT)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _validate_regulation_versions(self) -> "ReviewReport":
        # L5 修补：法规版本快照是结论可追溯的依据。规范库未加载 / 无匹配
        # 法规时报告结论为 PASS，允许空快照；但 FAIL / CONDITIONAL_PASS
        # 必然源自具体法规条文，必须携带版本快照，否则结论不可追溯。
        if (
            self.agent == AgentName.COMPLIANCE
            and self.conclusion in (AuditConclusion.FAIL, AuditConclusion.CONDITIONAL_PASS)
            and not self.regulation_versions
        ):
            raise ValueError(
                "合规报告结论为不通过/有条件通过时，regulation_versions 不得为空"
                "（需记录引用法规的版本快照）"
            )
        return self
