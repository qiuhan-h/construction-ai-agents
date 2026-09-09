"""IFC 真实解析器（5b.5）。

设计：
- 优先用 ``ifcopenshell`` 打开 .ifc 文件；
- ``ifcopenshell`` 缺失 → 走 **Mock 模式**（与 4c ``IFCParser`` 行为兼容）；
- 提取 3 类信息：
    1. **空间结构**（``IfcProject`` / ``IfcSite`` / ``IfcBuilding`` / ``IfcBuildingStorey`` / ``IfcSpace``）
    2. **构件**（``IfcElement`` 子类，按类型分类）
    3. **几何**（``Representation`` 简化：取 ``IfcExtrudedAreaSolid`` 的 depth）
- 返回结构化 dict（与 4c ``IFCParser.parse()`` 兼容 + 扩展字段）。
- 顶层 ``parse_ifc_file()`` 便利函数（verify_stage5 探针通过）。

为什么不用 4c ``IFCParser``：
- 4c 是首版 mock 演示，只取 ``GlobalId`` / ``Name``；
- 5b.5 要给进度对比（``ProgressTracker``）提供更丰富的几何 / 空间信息。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)


# =====================================================
# 配置 / 状态
# =====================================================
# 工程上关注的 IFC 元素类型白名单（按类别）
_STRUCTURE_TYPES: tuple[str, ...] = (
    "IfcProject",
    "IfcSite",
    "IfcBuilding",
    "IfcBuildingStorey",
    "IfcSpace",
)
_ELEMENT_TYPES: tuple[str, ...] = (
    "IfcWall",
    "IfcSlab",
    "IfcBeam",
    "IfcColumn",
    "IfcDoor",
    "IfcWindow",
    "IfcStair",
    "IfcRailing",
    "IfcRoof",
    "IfcCovering",
    "IfcMember",
    "IfcPlate",
)


def _ifcopenshell_available() -> bool:
    try:
        import ifcopenshell  # type: ignore  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


# =====================================================
# 工具：字符串安全化
# =====================================================
def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        s = str(value).strip()
        return s or default
    except Exception:  # noqa: BLE001
        return default


# =====================================================
# 几何提取
# =====================================================
def _extract_depth(element: Any) -> float | None:
    """提取 ``IfcExtrudedAreaSolid.Depth`` 作为构件高度/厚度的近似。"""
    try:
        reps = getattr(element, "Representation", None)
        if reps is None:
            return None
        for rep in reps.Representations or []:
            for item in rep.Items or []:
                if item.is_a("IfcExtrudedAreaSolid"):
                    depth = getattr(item, "Depth", None)
                    if depth is not None:
                        try:
                            return float(depth)
                        except (TypeError, ValueError):
                            return None
    except Exception:  # noqa: BLE001
        return None
    return None


# =====================================================
# 主类
# =====================================================
class IFCRealParser:
    """IFC 真实解析器。

    使用方式：
        parser = IFCRealParser()
        result = parser.parse("model.ifc")
        # 或者：
        result = parse_ifc_file("model.ifc")
    """

    backend_name: str = "ifcopenshell"

    def __init__(self, *, force_mock: bool = False) -> None:
        self.force_mock = force_mock
        self._ifc_module: Any = None
        if force_mock:
            logger.info("IFCRealParser 强制 mock 模式")
            return
        try:
            import ifcopenshell  # type: ignore
            self._ifc_module = ifcopenshell
            logger.info("ifcopenshell 加载成功（真实 IFC 解析）")
        except Exception as e:  # noqa: BLE001
            logger.warning("ifcopenshell 不可用: %s → mock 模式", e)
            self._ifc_module = None

    @property
    def is_mock(self) -> bool:
        return self._ifc_module is None

    # ---- 公开 API ----
    def parse(self, file_path: str) -> dict[str, Any]:
        """解析 IFC 文件。

        返回：
            {
                "file_path": str,
                "schema": str | None,
                "structure": [...],   # IfcProject/Site/Building/Storey/Space
                "elements": [...],    # IfcWall/Slab/Beam/Column/...
                "by_type": {type: count},
                "count": int,
                "warning": str | None,
            }
        """
        if self.is_mock:
            return self._mock_result(file_path)

        if not os.path.isfile(file_path):
            logger.warning("IFC 文件不存在: %s → mock 兜底", file_path)
            return self._mock_result(file_path, warning=f"file not found: {file_path}")

        try:
            model = self._ifc_module.open(file_path)
        except Exception as e:  # noqa: BLE001
            logger.warning("IFC 打开失败: %s → mock 兜底", e)
            return self._mock_result(file_path, warning=f"open failed: {e}")

        structure = [self._structure_to_dict(e) for e in self._iter_type(model, _STRUCTURE_TYPES)]
        elements = [self._element_to_dict(e) for e in self._iter_type(model, _ELEMENT_TYPES)]
        by_type: dict[str, int] = {}
        for el in elements:
            t = el["type"]
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "file_path": file_path,
            "schema": _safe_str(getattr(model, "schema", None), default="unknown"),
            "structure": structure,
            "elements": elements,
            "by_type": by_type,
            "count": len(elements),
            "warning": None,
        }

    def parse_bytes(self, content: bytes, *, source_name: str = "<bytes>") -> dict[str, Any]:
        """从字节流解析（用于上传场景）。"""
        if self.is_mock:
            return self._mock_result(source_name, warning="mock mode (ifcopenshell missing)")
        try:
            import io
            model = self._ifc_module.open(io.BytesIO(content))
            return self._from_model(model, source_name)
        except Exception as e:  # noqa: BLE001
            logger.warning("IFC 字节流解析失败: %s → mock 兜底", e)
            return self._mock_result(source_name, warning=f"parse_bytes failed: {e}")

    # ---- 内部 ----
    def _iter_type(self, model: Any, types: Iterable[str]) -> Iterable[Any]:
        seen: set[str] = set()
        for t in types:
            try:
                for inst in model.by_type(t):
                    gid = _safe_str(getattr(inst, "GlobalId", None))
                    if gid and gid in seen:
                        continue
                    if gid:
                        seen.add(gid)
                    yield inst
            except Exception:  # noqa: BLE001
                continue

    def _structure_to_dict(self, inst: Any) -> dict[str, Any]:
        try:
            type_name = inst.is_a().__name__ if hasattr(inst, "is_a") else "Unknown"
        except Exception:  # noqa: BLE001
            type_name = "Unknown"
        return {
            "global_id": _safe_str(getattr(inst, "GlobalId", None)),
            "type": type_name,
            "name": _safe_str(getattr(inst, "Name", None)),
            "long_name": _safe_str(getattr(inst, "LongName", None)),
        }

    def _element_to_dict(self, inst: Any) -> dict[str, Any]:
        try:
            type_name = inst.is_a().__name__ if hasattr(inst, "is_a") else "Unknown"
        except Exception:  # noqa: BLE001
            type_name = "Unknown"
        return {
            "global_id": _safe_str(getattr(inst, "GlobalId", None)),
            "type": type_name,
            "name": _safe_str(getattr(inst, "Name", None)),
            "tag": _safe_str(getattr(inst, "Tag", None)),
            "object_type": _safe_str(getattr(inst, "ObjectType", None)),
            "depth_m": _extract_depth(inst),
        }

    def _from_model(self, model: Any, source_name: str) -> dict[str, Any]:
        structure = [self._structure_to_dict(e) for e in self._iter_type(model, _STRUCTURE_TYPES)]
        elements = [self._element_to_dict(e) for e in self._iter_type(model, _ELEMENT_TYPES)]
        by_type: dict[str, int] = {}
        for el in elements:
            t = el["type"]
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "file_path": source_name,
            "schema": _safe_str(getattr(model, "schema", None), default="unknown"),
            "structure": structure,
            "elements": elements,
            "by_type": by_type,
            "count": len(elements),
            "warning": None,
        }

    @staticmethod
    def _mock_result(file_path: str, *, warning: str | None = None) -> dict[str, Any]:
        return {
            "file_path": file_path,
            "schema": None,
            "structure": [],
            "elements": [],
            "by_type": {},
            "count": 0,
            "warning": warning or "ifcopenshell not installed",
        }


# =====================================================
# 顶层函数（verify_stage5 探针通过 + 业务便利）
# =====================================================
def parse_ifc_file(file_path: str, *, force_mock: bool = False) -> dict[str, Any]:
    """便利函数：单次解析。"""
    return IFCRealParser(force_mock=force_mock).parse(file_path)


__all__ = [
    "IFCRealParser",
    "parse_ifc_file",
]
