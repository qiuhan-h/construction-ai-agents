"""趋势分析。"""

from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    def __init__(self, tsdb=None) -> None:
        self._tsdb = tsdb

    def analyze(self, metric: str, *, days: int = 7) -> dict:
        today = date.today()
        return {
            "metric": metric,
            "days": days,
            "data_points": [
                {"date": (today - timedelta(days=i)).isoformat(),
                 "avg": 0.0, "max": 0.0, "min": 0.0}
                for i in range(days)
            ],
            "trend": "stable",
            "change_pct": 0.0,
        }
