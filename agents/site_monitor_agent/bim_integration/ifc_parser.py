"""IFC 文件解析。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class IFCParser:
    """IFC 解析（ifcopenshell 缺失时降级 mock）。"""

    def __init__(self) -> None:
        try:
            import ifcopenshell  # type: ignore

            self._ifc = ifcopenshell
        except ImportError:
            logger.warning("ifcopenshell 未安装；IFC 解析走 mock 模式")
            self._ifc = None

    def parse(self, file_path: str) -> dict:
        """解析 IFC 文件 → 简化 dict。"""
        if self._ifc is None:
            return {
                "elements": [],
                "count": 0,
                "file_path": file_path,
                "warning": "ifcopenshell not installed",
            }
        model = self._ifc.open(file_path)
        elements = [self._to_dict(e) for e in model.by_type("IfcElement")]
        return {
            "elements": elements,
            "count": len(elements),
            "file_path": file_path,
            "schema": getattr(model, "schema", "unknown"),
        }

    @staticmethod
    def _to_dict(element: Any) -> dict:
        try:
            type_name = element.is_a().__name__ if hasattr(element, "is_a") else "Unknown"
        except Exception:
            type_name = "Unknown"
        return {
            "id": str(getattr(element, "GlobalId", "")),
            "type": type_name,
            "name": str(getattr(element, "Name", "") or ""),
            "tag": str(getattr(element, "Tag", "") or ""),
            "object_type": str(getattr(element, "ObjectType", "") or ""),
        }
