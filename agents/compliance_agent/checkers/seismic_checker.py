"""抗震合规核查（GB 50011）。"""

from __future__ import annotations

import logging
from typing import Any

from agents.compliance_agent.regulation_engine.mcp_loader import RegulationSummary
from common.constants import ViolationSeverity
from core.rules.rule import ComplianceRule, compare
from models.domain import Violation

logger = logging.getLogger(__name__)


class SeismicChecker:
    """抗震合规核查（GB 50011）首版。"""

    code: str = "GB50011"
    design_type: str = "seismic"

    def __init__(self) -> None:
        self._rules: list[ComplianceRule] = self._load_default_rules()

    def _load_default_rules(self) -> list[ComplianceRule]:
        return [
            ComplianceRule(
                id="GB50011-3.1.1-fortify", code="GB50011", version="2010", clause="3.1.1",
                severity="high", field="seismic_intensity", operator=">=", threshold=6,
                message="抗震设防烈度 ≥ 6 度（必须进行抗震设计）",
            ),
            ComplianceRule(
                id="GB50011-5.1.1-story", code="GB50011", version="2010", clause="5.1.1",
                severity="high", field="max_story_height", operator="<=", threshold=80,
                message="最大适用高度 ≤ 80m（混凝土结构）",
            ),
            ComplianceRule(
                id="GB50011-5.2.1-ratio", code="GB50011", version="2010", clause="5.2.1",
                severity="medium", field="story_height_ratio", operator="<=", threshold=2.0,
                message="层间位移角 ≤ 1/500（≈ 0.002）",
            ),
        ]

    async def check(
        self,
        design_doc: dict[str, Any],
        regulations: list[RegulationSummary] | None = None,
        *,
        tenant_id: str = "",
    ) -> list[Violation]:
        return self._run_rules(design_doc, tenant_id=tenant_id)

    def _run_rules(
        self, design_doc: dict[str, Any], *, tenant_id: str = "",
    ) -> list[Violation]:
        violations: list[Violation] = []
        for rule in self._rules:
            actual = design_doc.get(rule.field)
            if actual is None:
                continue
            if compare(actual, rule.operator, rule.threshold):
                continue
            violations.append(
                self._make_violation(rule, actual, tenant_id=tenant_id)
            )
        return violations

    @staticmethod
    def _make_violation(
        rule: ComplianceRule, actual: Any, *, tenant_id: str = "",
    ) -> Violation:
        severity_map = {
            "low": ViolationSeverity.LOW,
            "medium": ViolationSeverity.MEDIUM,
            "high": ViolationSeverity.HIGH,
            "critical": ViolationSeverity.CRITICAL,
        }
        return Violation(
            tenant_id=tenant_id,
            inspection_id="",
            regulation_id=rule.code,
            regulation_version=rule.version,
            clause=rule.clause,
            description=f"{rule.message}（实际={actual}，要求{rule.operator}{rule.threshold}）",
            severity=severity_map.get(rule.severity, ViolationSeverity.MEDIUM),
            rectification=f"按 {rule.code} 第 {rule.clause} 条整改",
        )
