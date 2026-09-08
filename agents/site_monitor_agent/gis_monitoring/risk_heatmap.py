"""风险热力图：聚合告警 + 设备位置 → GeoJSON。"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class RiskHeatmap:
    def generate(self, project_id: str, *, hours: int = 24) -> dict:
        return {
            "type": "FeatureCollection",
            "project_id": project_id,
            "hours": hours,
            "features": [
                {"type": "Feature",
                 "properties": {"intensity": 0.0, "alert_count": 0},
                 "geometry": {"type": "Point", "coordinates": [0.0, 0.0]}}
            ],
        }
