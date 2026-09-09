"""审查报告生成器。

输入：
- plan_fields: PlanFields
- load_result: LoadResult | None
- risk_assessment: RiskAssessment | None
- related_cases: list[CaseHit]
- related_regulations: list[dict] (regulation 摘要)
- recommendations: RecommendationSet

输出：
- 结构化 ReviewReport（models.domain.ReviewReport）
- Markdown 文本

结论映射：
- 任意 CRITICAL 风险或 max_level == CRITICAL → FAIL
- max_level == HIGH 或 requires_alert → CONDITIONAL_PASS
- 其余 → PASS
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.safety_audit_agent.calculators.load_calculator import LoadResult
from agents.safety_audit_agent.calculators.risk_assessor import (
    RiskAssessment,
    RiskLevel,
)
from agents.safety_audit_agent.knowledge_base.case_retriever import CaseHit
from agents.safety_audit_agent.outputs.recommendation_engine import (
    RecommendationSet,
    Severity,
)
from agents.safety_audit_agent.parsers.plan_parser import PlanFields
from common.constants import (
    AgentName,
    AuditConclusion,
    ReportStatus,
    ViolationSeverity,
)
from common.ids import report_id
from common.timeutils import utc_now
from models.domain import Inspection, ReviewReport, Violation


@dataclass
class ReportArtifacts:
    """报告生成产物。"""

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


class ReportGenerator:
    """审查报告生成器。"""

    def __init__(self, *, agent: AgentName = AgentName.SAFETY_AUDIT) -> None:
        self._agent = agent

    def generate(
        self,
        *,
        tenant_id: str,
        project_id: str,
        plan_id: str,
        plan_fields: PlanFields,
        load_result: LoadResult | None = None,
        risk_assessment: RiskAssessment | None = None,
        related_cases: list[CaseHit] | None = None,
        related_regulations: list[dict[str, Any]] | None = None,
        recommendations: RecommendationSet | None = None,
    ) -> ReportArtifacts:
        related_cases = related_cases or []
        related_regulations = related_regulations or []
        recommendations = recommendations or RecommendationSet(
            items=[], max_severity=Severity.INFO, requires_alert=False
        )

        # 违规项：从 recommendations（source == risk）中拆出
        violations: list[Violation] = []
        for r in recommendations.items:
            if r.source != "risk":
                continue
            level = (r.metadata.get("level") or "").lower()
            sev_map = {
                "critical": ViolationSeverity.CRITICAL,
                "high": ViolationSeverity.HIGH,
                "medium": ViolationSeverity.MEDIUM,
                "low": ViolationSeverity.LOW,
            }
            severity = sev_map.get(level, ViolationSeverity.MEDIUM)
            # 必须有 regulation_version，否则抛 RegulationVersionMissingError
            # 首版：当且仅当 risk 提供 regulation_id/version 时才入库；否则只进 markdown
            reg_id = r.metadata.get("regulation_id") if r.metadata else None
            reg_version = r.metadata.get("regulation_version") if r.metadata else None
            if reg_id and reg_version:
                violations.append(
                    Violation(
                        tenant_id=tenant_id,
                        inspection_id="",  # 由调用方回填
                        regulation_id=reg_id,
                        regulation_version=reg_version,
                        clause=r.metadata.get("clause") if r.metadata else None,
                        description=r.detail,
                        severity=severity,
                        rectification=r.title,
                    )
                )

        # 法规版本快照
        regulation_versions: dict[str, str] = {}
        for reg in related_regulations:
            code = reg.get("code")
            version = reg.get("version")
            if code and version:
                regulation_versions[str(code)] = str(version)

        # 结论
        conclusion = self._conclude(recommendations, risk_assessment)
        # 标题
        title = f"施工安全审核报告（{plan_fields.project_name or plan_id}）"
        # Markdown
        markdown = self._render_markdown(
            plan_fields=plan_fields,
            load_result=load_result,
            risk_assessment=risk_assessment,
            related_cases=related_cases,
            related_regulations=related_regulations,
            recommendations=recommendations,
            conclusion=conclusion,
            regulation_versions=regulation_versions,
        )

        # 构建 Pydantic 实体
        insp = Inspection(
            tenant_id=tenant_id,
            project_id=project_id,
            plan_id=plan_id,
            agent=self._agent,
            status=Inspection.model_fields["status"].default,
            summary=markdown[:200] if markdown else None,
            started_at=utc_now(),
        )
        rpt = ReviewReport(
            id=report_id(),
            tenant_id=tenant_id,
            project_id=project_id,
            inspection_id=insp.id,
            agent=self._agent,
            title=title,
            content=markdown,
            conclusion=conclusion,
            regulation_versions=regulation_versions,
            status=ReportStatus.DRAFT,
        )
        # 把 inspection_id 回填到 violations
        for v in violations:
            v.inspection_id = insp.id

        return ReportArtifacts(
            inspection=insp,
            report=rpt,
            violations=violations,
            markdown=markdown,
            regulation_versions=regulation_versions,
        )

    @staticmethod
    def _conclude(
        recommendations: RecommendationSet,
        risk_assessment: RiskAssessment | None,
    ) -> AuditConclusion:
        if recommendations.requires_alert or (
            risk_assessment and risk_assessment.requires_alert
        ):
            return AuditConclusion.FAIL
        if (
            recommendations.max_severity == Severity.URGENT
            or (risk_assessment and risk_assessment.max_level == RiskLevel.HIGH)
        ):
            return AuditConclusion.CONDITIONAL_PASS
        return AuditConclusion.PASS

    @staticmethod
    def _render_markdown(
        *,
        plan_fields: PlanFields,
        load_result: LoadResult | None,
        risk_assessment: RiskAssessment | None,
        related_cases: list[CaseHit],
        related_regulations: list[dict[str, Any]],
        recommendations: RecommendationSet,
        conclusion: AuditConclusion,
        regulation_versions: dict[str, str],
    ) -> str:
        lines: list[str] = []
        lines.append(f"# {plan_fields.project_name or '施工安全审核报告'}")
        lines.append("")
        lines.append(f"- 阶段：{plan_fields.stage or '未识别'}")
        lines.append(f"- 审查结论：**{conclusion.value}**")
        lines.append(f"- 最大风险等级：{recommendations.max_severity.value}")
        if regulation_versions:
            rv = "、".join(f"{k} {v}" for k, v in regulation_versions.items())
            lines.append(f"- 依据法规/标准：{rv}")
        lines.append("")

        lines.append("## 一、方案摘要")
        lines.append("")
        if plan_fields.materials:
            lines.append(f"- 主要材料：{', '.join(plan_fields.materials)}")
        if plan_fields.loads:
            load_desc = "、".join(f"{k}={v}" for k, v in plan_fields.loads.items())
            lines.append(f"- 荷载参数：{load_desc}")
        if plan_fields.hazards:
            lines.append(f"- 危险源：{', '.join(h['name'] for h in plan_fields.hazards)}")
        lines.append("")

        if load_result is not None:
            lines.append("## 二、荷载组合")
            lines.append("")
            lines.append(
                f"- 公式：`{load_result.formula}`\n"
                f"- D = {load_result.dead_load_kpa} kN/m²\n"
                f"- L = {load_result.live_load_kpa} kN/m²\n"
                f"- W = {load_result.wind_pressure_kpa} kN/m²\n"
                f"- S = {load_result.snow_pressure_kpa} kN/m²\n"
                f"- **组合 q = {load_result.combined_kpa:.3f} kN/m²**"
            )
            lines.append("")

        if risk_assessment is not None:
            lines.append("## 三、风险评估（LEC）")
            lines.append("")
            lines.append(
                f"- 危险源数量：{len(risk_assessment.items)} | "
                f"最高分：{risk_assessment.max_score:.2f} | "
                f"最大等级：{risk_assessment.max_level.value}"
            )
            lines.append("")
            lines.append("| 危险源 | L | E | C | D | 等级 |")
            lines.append("|---|---|---|---|---|---|")
            for it in risk_assessment.items:
                lines.append(
                    f"| {it.name} | {it.likelihood} | {it.exposure} | {it.consequence} | "
                    f"{it.score:.1f} | {it.level.value} |"
                )
            lines.append("")

        if related_cases:
            lines.append("## 四、相似案例")
            lines.append("")
            for c in related_cases:
                lines.append(f"- **{c.title}**（score={c.score:.2f}）— {c.summary}")
            lines.append("")

        if related_regulations:
            lines.append("## 五、相关法规/标准")
            lines.append("")
            for r in related_regulations:
                lines.append(
                    f"- {r.get('code','?')} {r.get('version','?')} — {r.get('name','')}"
                )
            lines.append("")

        if recommendations.items:
            lines.append("## 六、整改建议")
            lines.append("")
            for rec in recommendations.items:
                lines.append(
                    f"- **[{rec.severity.value}]** {rec.title}：{rec.detail}"
                )
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("> 本报告由 safety_audit_agent 自动生成，最终解释权归人工复核。")
        return "\n".join(lines)
