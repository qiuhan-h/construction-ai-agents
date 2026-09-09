"""绿色建筑合规核查（GB/T 50378）。"""

from __future__ import annotations

import logging
from typing import Any

from agents.compliance_agent.regulation_engine.mcp_loader import RegulationSummary
from common.constants import ViolationSeverity
from core.rules.rule import ComplianceRule, compare
from models.domain import Violation

logger = logging.getLogger(__name__)


class GreenChecker:
    """绿色建筑合规核查（GB/T 50378）首版。"""

    code: str = "GB50378"
    design_type: str = "green"

    def __init__(self) -> None:
        self._rules: list[ComplianceRule] = self._load_default_rules()

    def _load_default_rules(self) -> list[ComplianceRule]:
        return [
            ComplianceRule(
                id="GB50378-3.1.1-score", code="GB50378", version="2019", clause="3.1.1",
                severity="high", field="green_score", operator=">=", threshold=60,
                message="绿色建筑评分 ≥ 60（一星级）",
            ),
            ComplianceRule(
                id="GB50378-4.1.1-recycle", code="GB50378", version="2019", clause="4.1.1",
                severity="medium", field="recycle_water_ratio", operator=">=", threshold=0.30,
                message="非传统水源利用率 ≥ 30%",
            ),
            ComplianceRule(
                id="GB50378-4.2.1-greening", code="GB50378", version="2019", clause="4.2.1",
                severity="medium", field="greening_ratio", operator=">=", threshold=0.30,
                message="绿地率 ≥ 30%",
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
