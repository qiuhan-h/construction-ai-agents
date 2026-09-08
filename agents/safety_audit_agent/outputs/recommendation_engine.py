"""整改建议生成器。

根据风险等级 + 相似案例 + 法规版本，生成整改建议列表。
- CRITICAL：必须停工 + 通知人工复核（同时触发 TOPIC_ALERT_TRIGGERED）
- HIGH：限时整改 + 复查
- MEDIUM：提示建议
- LOW/NEGLIGIBLE：存档备查
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.safety_audit_agent.calculators.risk_assessor import (
    RiskAssessment,
    RiskLevel,
)

logger = logging.getLogger("agents.safety_audit_agent.outputs.recommendation")


class Severity(str, Enum):
    """整改建议严重程度。"""

    STOP_WORK = "stop_work"
    URGENT = "urgent"
    NORMAL = "normal"
    INFO = "info"


_SEVERITY_FOR_LEVEL: dict[RiskLevel, Severity] = {
    RiskLevel.CRITICAL: Severity.STOP_WORK,
    RiskLevel.HIGH: Severity.URGENT,
    RiskLevel.MEDIUM: Severity.NORMAL,
    RiskLevel.LOW: Severity.INFO,
    RiskLevel.NEGLIGIBLE: Severity.INFO,
}


@dataclass
class Recommendation:
    """一条整改建议。"""

    title: str
    detail: str
    severity: Severity
    source: str  # "risk" | "case" | "regulation" | "rule"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "detail": self.detail,
            "severity": self.severity.value,
            "source": self.source,
            "metadata": dict(self.metadata),
        }


@dataclass
class RecommendationSet:
    """整改建议集合。"""

    items: list[Recommendation]
    max_severity: Severity
    requires_alert: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [i.to_dict() for i in self.items],
            "count": len(self.items),
            "max_severity": self.max_severity.value,
            "requires_alert": self.requires_alert,
        }


class RecommendationEngine:
    """整改建议生成器。"""

    def from_risk(self, assessment: RiskAssessment) -> RecommendationSet:
        """基于风险评估生成建议。"""
        items: list[Recommendation] = []
        max_sev = Severity.INFO
        requires_alert = False

        for item in assessment.items:
            sev = _SEVERITY_FOR_LEVEL[item.level]
            if _sev_rank(sev) > _sev_rank(max_sev):
                max_sev = sev
            if item.level == RiskLevel.CRITICAL:
                requires_alert = True
            items.append(
                Recommendation(
                    title=f"风险：{item.name}",
                    detail=_detail_for(item),
                    severity=sev,
                    source="risk",
                    metadata={
                        "score": item.score,
                        "level": item.level.value,
                        "likelihood": item.likelihood,
                        "exposure": item.exposure,
                        "consequence": item.consequence,
                    },
                )
            )
        return RecommendationSet(
            items=items, max_severity=max_sev, requires_alert=requires_alert
        )

    def merge(
        self, primary: RecommendationSet, others: list[RecommendationSet]
    ) -> RecommendationSet:
        """合并多来源建议（primary 优先），按严重度降序。"""
        items = list(primary.items)
        max_sev = primary.max_severity
        requires_alert = primary.requires_alert
        for o in others:
            items.extend(o.items)
            if _sev_rank(o.max_severity) > _sev_rank(max_sev):
                max_sev = o.max_severity
            if o.requires_alert:
                requires_alert = True
        items.sort(key=lambda r: _sev_rank(r.severity), reverse=True)
        return RecommendationSet(
            items=items, max_severity=max_sev, requires_alert=requires_alert
        )


def _sev_rank(sev: Severity) -> int:
    return {
        Severity.STOP_WORK: 3,
        Severity.URGENT: 2,
        Severity.NORMAL: 1,
        Severity.INFO: 0,
    }[sev]


def _detail_for(item) -> str:
    note = f"（{item.note}）" if item.note else ""
    if item.level == RiskLevel.CRITICAL:
        return (
            f"L·E·C={item.score:.1f}（重大风险），必须立即停工并启动"
            f"人工复核及现场整改。{note}"
        )
    if item.level == RiskLevel.HIGH:
        return f"L·E·C={item.score:.1f}（较大风险），限 24 小时内完成整改并复查。{note}"
    if item.level == RiskLevel.MEDIUM:
        return f"L·E·C={item.score:.1f}（一般风险），建议在 7 日内整改。{note}"
    if item.level == RiskLevel.LOW:
        return f"L·E·C={item.score:.1f}（较低风险），纳入日常管理。{note}"
    return f"L·E·C={item.score:.1f}（轻微风险），存档备查。{note}"
