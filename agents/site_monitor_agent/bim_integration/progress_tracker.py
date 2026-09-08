"""进度跟踪：BIM 构件计划 vs 实际 vs 偏差告警。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from common.constants import AlertLevel
from models.domain import Alert

logger = logging.getLogger(__name__)


@dataclass
class ProgressItem:
    """进度项。"""
    element_id: str
    name: str
    plan_pct: float        # 0-100
    actual_pct: float      # 0-100
    deviation: float = 0.0  # actual - plan，正数 = 超前，负数 = 滞后

    def to_dict(self) -> dict:
        return {
            "element_id": self.element_id,
            "name": self.name,
            "plan_pct": self.plan_pct,
            "actual_pct": self.actual_pct,
            "deviation": round(self.deviation, 2),
        }


class ProgressTracker:
    """进度跟踪 + 偏差检测 → 告警。"""

    def __init__(self, deviation_threshold: float = 10.0) -> None:
        self._deviation_threshold = deviation_threshold

    def compute(
        self,
        plan: list[dict],
        actual: list[dict],
    ) -> list[ProgressItem]:
        """合并计划与实际，计算偏差。

        plan / actual 每个 dict 含 element_id, name, pct(0-100)。
        缺失的实际进度按 0% 计。
        """
        plan_map = {p["element_id"]: p for p in plan}
        items: list[ProgressItem] = []
        for aid, a in plan_map.items():
            actual_entry = next((x for x in actual if x.get("element_id") == aid), None)
            plan_pct = float(a.get("pct", 0))
            actual_pct = float(actual_entry.get("pct", 0)) if actual_entry else 0.0
            deviation = actual_pct - plan_pct
            items.append(ProgressItem(
                element_id=aid, name=a.get("name", ""),
                plan_pct=plan_pct, actual_pct=actual_pct, deviation=deviation,
            ))
        return items

    def deviation_alerts(
        self,
        items: list[ProgressItem],
        *,
        tenant_id: str = "",
        project_id: str = "",
    ) -> list[Alert]:
        """偏差超阈值 → 告警。"""
        out: list[Alert] = []
        for it in items:
            if abs(it.deviation) < self._deviation_threshold:
                continue
            level = AlertLevel.CRITICAL if it.deviation < -self._deviation_threshold else AlertLevel.WARNING
            desc = (f"进度偏差 {it.deviation:+.1f}%："
                    f"计划 {it.plan_pct:.0f}% / 实际 {it.actual_pct:.0f}%")
            out.append(Alert(
                tenant_id=tenant_id, project_id=project_id,
                source="bim_progress",
                level=level,
                title=f"进度偏差：{it.name}",
                message=desc,
                metric={"deviation": it.deviation,
                        "plan_pct": it.plan_pct, "actual_pct": it.actual_pct},
                dedup_key=f"progress:{it.element_id}",
            ))
        return out
