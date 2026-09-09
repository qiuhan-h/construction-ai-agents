"""合规报告生成器：结构化 ReviewReport + Markdown。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agents.compliance_agent.regulation_engine.mcp_loader import (
    RegulationSummary,
)
from common.constants import AgentName, AuditConclusion, ReportStatus, ViolationSeverity
from common.ids import inspection_id as _inspection_id_factory
from common.ids import report_id
from common.timeutils import utc_now
from models.domain import Inspection, ReviewReport, Violation

logger = logging.getLogger(__name__)


@dataclass
class ReportArtifacts:
    """合规报告生成产物。"""

    inspection: Inspection
    report: ReviewReport
    violations: list[Violation] = field(default_factory=list)
    markdown: str = ""
    regulation_versions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "inspection": self.inspection.model_dump(),
            "report": self.report.model_dump(),
            "violations": [v.model_dump() for v in self.violations],
            "regulation_versions": self.regulation_versions,
            "markdown_length": len(self.markdown),
        }


class ComplianceReporter:
    """合规报告生成器：ReviewReport + Markdown。"""

    def __init__(self) -> None:
        pass

    def generate(
        self,
        *,
        tenant_id: str,
        project_id: str,
        plan_id: str,
        design_doc: dict[str, Any],
        violations: list[Violation] | None = None,
        regulations: list[RegulationSummary] | None = None,
    ) -> ReportArtifacts:
        violations = violations or []
        regulations = regulations or []

        # 法规版本快照
        regulation_versions: dict[str, str] = {}
        for r in regulations:
            regulation_versions[r.code] = r.version

        # 结论
        conclusion = self._conclude(violations)

        # Markdown
        markdown = self._render_markdown(
            design_doc=design_doc, violations=violations,
            regulations=regulations, regulation_versions=regulation_versions,
            conclusion=conclusion,
        )

        # 标题
        title = f"合规审查报告（{design_doc.get('project_name', plan_id)}）"

        insp = Inspection(
            id=_inspection_id_factory(),
            tenant_id=tenant_id,
            project_id=project_id,
            plan_id=plan_id,
            agent=AgentName.COMPLIANCE,
            summary=markdown[:200] if markdown else None,
            started_at=utc_now(),
        )
        rpt = ReviewReport(
            id=report_id(),
            tenant_id=tenant_id,
            project_id=project_id,
            inspection_id=insp.id,
            agent=AgentName.COMPLIANCE,
            title=title,
            content=markdown,
            conclusion=conclusion,
            regulation_versions=regulation_versions,
            status=ReportStatus.DRAFT,
        )
        return ReportArtifacts(
            inspection=insp,
            report=rpt,
            violations=violations,
            markdown=markdown,
            regulation_versions=regulation_versions,
        )

    @staticmethod
    def _conclude(violations: list[Violation]) -> AuditConclusion:
        if any(v.severity == ViolationSeverity.CRITICAL for v in violations):
            return AuditConclusion.FAIL
        if any(v.severity == ViolationSeverity.HIGH for v in violations):
            return AuditConclusion.CONDITIONAL_PASS
        return AuditConclusion.PASS

    @staticmethod
    def _render_markdown(
        *,
        design_doc: dict[str, Any],
        violations: list[Violation],
        regulations: list[RegulationSummary],
        regulation_versions: dict[str, str],
        conclusion: AuditConclusion,
    ) -> str:
        lines: list[str] = []
        lines.append(f"# {design_doc.get('project_name', '合规审查报告')}")
        lines.append("")
        lines.append(f"- 审查结论：**{conclusion.value}**")
        lines.append(f"- 违规项数量：{len(violations)}")
        if regulation_versions:
            rv = "、".join(f"{k} {v}" for k, v in regulation_versions.items())
            lines.append(f"- 依据法规/标准：{rv}")
        lines.append("")

        lines.append("## 一、设计文件摘要")
        lines.append("")
        for k in ("project_name", "stage", "design_unit"):
            v = design_doc.get(k)
            if v:
                lines.append(f"- {k}: {v}")
        lines.append("")

        if regulations:
            lines.append("## 二、依据法规")
            lines.append("")
            for r in regulations:
                lines.append(f"- {r.code} {r.version} — {r.name}")
            lines.append("")

        if violations:
            lines.append("## 三、违规清单")
            lines.append("")
            lines.append("| # | 法规 | 条款 | 严重度 | 描述 |")
            lines.append("|---|------|------|--------|------|")
            for i, v in enumerate(violations, 1):
                lines.append(
                    f"| {i} | {v.regulation_id or '-'} {v.regulation_version or ''} | "
                    f"{v.clause or '-'} | {v.severity.value} | {v.description} |"
                )
            lines.append("")

        lines.append("## 四、整改建议")
        lines.append("")
        for v in violations:
            lines.append(f"- **[{v.severity.value}]** {v.rectification or '按法规整改'}")
        lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("> 本报告由 compliance_agent 自动生成，最终解释权归人工复核。")
        return "\n".join(lines)
