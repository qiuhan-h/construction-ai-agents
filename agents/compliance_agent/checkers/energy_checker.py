"""节能合规核查（GB 50189）。"""

from __future__ import annotations

import logging
from typing import Any

from agents.compliance_agent.regulation_engine.mcp_loader import RegulationSummary
from common.constants import ViolationSeverity
from core.rules.rule import ComplianceRule, compare
from models.domain import Violation

logger = logging.getLogger(__name__)


class EnergyChecker:
    """节能合规核查（GB 50189 公共建筑节能设计标准）首版。"""

    code: str = "GB50189"
    design_type: str = "energy"

    def __init__(self) -> None:
        self._rules: list[ComplianceRule] = self._load_default_rules()

    def _load_default_rules(self) -> list[ComplianceRule]:
        return [
            ComplianceRule(
                id="GB50189-3.2.1-envelope", code="GB50189", version="2015", clause="3.2.1",
                severity="high", field="wall_k", operator="<=", threshold=0.6,
                message="外墙传热系数 K ≤ 0.6 W/(m²·K)（夏热冬冷地区）",
            ),
            ComplianceRule(
                id="GB50189-3.2.2-roof", code="GB50189", version="2015", clause="3.2.2",
                severity="high", field="roof_k", operator="<=", threshold=0.5,
                message="屋面传热系数 K ≤ 0.5 W/(m²·K)",
            ),
            ComplianceRule(
                id="GB50189-3.3.1-window", code="GB50189", version="2015", clause="3.3.1",
                severity="medium", field="window_k", operator="<=", threshold=2.0,
                message="外窗传热系数 K ≤ 2.0 W/(m²·K)",
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
