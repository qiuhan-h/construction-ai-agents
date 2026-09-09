"""风险评估：作业条件危险性评价法（LEC）。

公式：D = L · E · C
  L = 事故发生的可能性（likelihood）
  E = 暴露于危险环境的频繁程度（exposure）
  C = 发生事故可能造成的后果（consequence）

风险等级：
  D ≥ 320   重大风险（CRITICAL）→ 必须停工 + 触发告警
  160 ≤ D < 320  较大风险（HIGH）
  70  ≤ D < 160  一般风险（MEDIUM）
  20  ≤ D < 70   较低风险（LOW）
  D < 20          轻微风险（NEGLIGIBLE）
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any

# =====================================================
# LEC 评分参考（节选自 GB/T 27921-2011 与行业常用表）
# =====================================================
LIKELIHOOD_SCORES: dict[str, float] = {
    "极不可能": 0.1,
    "可能性小": 0.5,
    "可能": 1.0,
    "较可能": 3.0,
    "很可能": 6.0,
    "极可能": 10.0,
}

EXPOSURE_SCORES: dict[str, float] = {
    "非常罕见暴露": 0.5,
    "每年几次": 1.0,
    "每月几次": 2.0,
    "每周几次": 3.0,
    "每天工作时间内": 6.0,
    "连续暴露": 10.0,
}

CONSEQUENCE_SCORES: dict[str, float] = {
    "轻微（轻伤/小损失）": 1.0,
    "较小（局部停工/中等损失）": 3.0,
    "严重（重伤/较大损失）": 7.0,
    "很严重（1人死亡/重大损失）": 15.0,
    "灾难性（多人死亡）": 40.0,
}


class RiskLevel(str, Enum):
    """风险等级（D 值划分）。"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NEGLIGIBLE = "negligible"


def classify(score: float) -> RiskLevel:
    if score >= 320:
        return RiskLevel.CRITICAL
    if score >= 160:
        return RiskLevel.HIGH
    if score >= 70:
        return RiskLevel.MEDIUM
    if score >= 20:
        return RiskLevel.LOW
    return RiskLevel.NEGLIGIBLE


# =====================================================
# 输入 / 输出
# =====================================================
@dataclass(frozen=True)
class HazardInput:
    """单个危险源。"""

    name: str
    likelihood: float  # L：事故可能性
    exposure: float    # E：暴露频繁度
    consequence: float  # C：后果严重度
    note: str | None = None


@dataclass(frozen=True)
class RiskItem:
    """单个危险源的风险评估结果。"""

    name: str
    likelihood: float
    exposure: float
    consequence: float
    score: float
    level: RiskLevel
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "likelihood": self.likelihood,
            "exposure": self.exposure,
            "consequence": self.consequence,
            "score": round(self.score, 2),
            "level": self.level.value,
            "note": self.note,
        }


@dataclass(frozen=True)
class RiskAssessment:
    """一批危险源的整体评估。"""

    items: list[RiskItem]
    max_score: float
    max_level: RiskLevel
    requires_alert: bool  # 任意 CRITICAL → True

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [i.to_dict() for i in self.items],
            "max_score": round(self.max_score, 2),
            "max_level": self.max_level.value,
            "requires_alert": self.requires_alert,
            "hazard_count": len(self.items),
        }


# =====================================================
# 评估器
# =====================================================
class LECAssessor:
    """LEC 风险评估器（async）。"""

    async def assess(self, hazards: list[HazardInput]) -> RiskAssessment:
        return await asyncio.to_thread(self._assess_sync, hazards)

    def _assess_sync(self, hazards: list[HazardInput]) -> RiskAssessment:
        items: list[RiskItem] = []
        max_score = 0.0
        max_level = RiskLevel.NEGLIGIBLE
        requires_alert = False

        for h in hazards:
            for name, v in (
                ("likelihood", h.likelihood),
                ("exposure", h.exposure),
                ("consequence", h.consequence),
            ):
                if v < 0:
                    raise ValueError(f"风险评分不能为负: {h.name}.{name}={v}")
            score = h.likelihood * h.exposure * h.consequence
            level = classify(score)
            items.append(
                RiskItem(
                    name=h.name,
                    likelihood=h.likelihood,
                    exposure=h.exposure,
                    consequence=h.consequence,
                    score=score,
                    level=level,
                    note=h.note,
                )
            )
            if score > max_score:
                max_score = score
            if _level_rank(level) > _level_rank(max_level):
                max_level = level
            if level == RiskLevel.CRITICAL:
                requires_alert = True

        return RiskAssessment(
            items=items,
            max_score=max_score,
            max_level=max_level,
            requires_alert=requires_alert,
        )

    @staticmethod
    def from_text(hazards: list[dict[str, Any]]) -> list[HazardInput]:
        """从 dict 列表构造 HazardInput（便利方法）。"""
        return [
            HazardInput(
                name=h["name"],
                likelihood=float(h.get("likelihood", 0)),
                exposure=float(h.get("exposure", 0)),
                consequence=float(h.get("consequence", 0)),
                note=h.get("note"),
            )
            for h in hazards
        ]


def _level_rank(level: RiskLevel) -> int:
    return {
        RiskLevel.NEGLIGIBLE: 0,
        RiskLevel.LOW: 1,
        RiskLevel.MEDIUM: 2,
        RiskLevel.HIGH: 3,
        RiskLevel.CRITICAL: 4,
    }[level]
