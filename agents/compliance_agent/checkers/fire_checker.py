"""防火合规核查（GB 50016）。"""

from __future__ import annotations

import logging
from typing import Any

from common.constants import ViolationSeverity
from core.rules.rule import ComplianceRule, compare
from models.domain import Violation

from agents.compliance_agent.regulation_engine.mcp_loader import RegulationSummary

logger = logging.getLogger(__name__)


class FireChecker:
    """防火合规核查（GB 50016）首版。"""

    code: str = "GB50016"
    design_type: str = "fire"

    def __init__(self) -> None:
        self._rules: list[ComplianceRule] = self._load_default_rules()

    def _load_default_rules(self) -> list[ComplianceRule]:
        return [
            ComplianceRule(
                id="GB50016-3.3.1-area", code="GB50016", version="2014", clause="3.3.1",
                severity="high", field="fire_zone_area", operator="<=", threshold=3000,
                message="防火分区面积 ≤ 3000 m²",
            ),
            ComplianceRule(
                id="GB50016-5.5.17-exit", code="GB50016", version="2014", clause="5.5.17",
                severity="high", field="exit_distance_m", operator="<=", threshold=30,
                message="安全疏散距离 ≤ 30m（办公）",
            ),
            ComplianceRule(
                id="GB50016-3.3.1-wall", code="GB50016", version="2014", clause="3.3.1",
                severity="high", field="fire_wall_hours", operator=">=", threshold=3,
                message="防火墙耐火极限 ≥ 3h",
            ),
            ComplianceRule(
                id="GB50016-6.5.1-door", code="GB50016", version="2014", clause="6.5.1",
                severity="medium", field="fire_door_hours", operator=">=", threshold=1,
                message="防火门等级 ≥ 1h",
            ),
            ComplianceRule(
                id="GB50016-5.5.13-stair", code="GB50016", version="2014", clause="5.5.13",
                severity="medium", field="stair_form", operator="==", threshold="封闭楼梯间",
                message="楼梯间形式应为封闭楼梯间",
            ),
        ]

    async def check(
        self,
        design_doc: dict[str, Any],
        regulations: list[RegulationSummary] | None = None,
        *,
        tenant_id: str = "",
    ) -> list[Violation]:
        """对 design_doc 执行所有 fire 规则；返回违规项列表。"""
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
                continue  # 合规
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
            tenant_id=tenant_id,            # 由调用方回填
            inspection_id="",
            regulation_id=rule.code,
            regulation_version=rule.version,
            clause=rule.clause,
            description=f"{rule.message}（实际值={actual}，要求{rule.operator}{rule.threshold}）",
            severity=severity_map.get(rule.severity, ViolationSeverity.MEDIUM),
            rectification=f"按 {rule.code} 第 {rule.clause} 条整改",
        )
