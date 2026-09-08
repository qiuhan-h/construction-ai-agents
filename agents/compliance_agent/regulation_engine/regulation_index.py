"""法规索引：按 design_type + tenant_id 返回适用法规清单。"""

from __future__ import annotations

import logging
from typing import Any

from agents.compliance_agent.regulation_engine.mcp_loader import (
    RegulationLoader,
    RegulationSummary,
)

logger = logging.getLogger(__name__)


class RegulationIndex:
    """按 design_type 查适用法规。

    多租户：4a 首版共享全租户可见（不按 tenant_id 过滤）；
    4c+ 可通过 loader 增加租户元数据后做隔离。
    """

    def __init__(self, loader: RegulationLoader):
        self._loader = loader

    def search(self, design_type: str) -> list[RegulationSummary]:
        """按 design_type（fire/seismic/energy/green/general）查法规。"""
        all_regs = self._loader.list_all()
        out: list[RegulationSummary] = []
        for it in all_regs:
            if self._matches(it, design_type):
                out.append(RegulationSummary(
                    code=it["code"], version=it["version"],
                    name=it["name"], effective_date=it.get("effective_date"),
                    metadata=it.get("metadata", {}) or {},
                ))
        return out

    def list_all(self) -> list[RegulationSummary]:
        return [
            RegulationSummary(
                code=it["code"], version=it["version"], name=it["name"],
                metadata=it.get("metadata", {}) or {},
            )
            for it in self._loader.list_all()
        ]

    def _matches(self, item: dict[str, Any], design_type: str) -> bool:
        categories = item.get("categories") or []
        # general 类别对所有 design_type 可见
        if "general" in categories:
            return True
        return design_type in categories
