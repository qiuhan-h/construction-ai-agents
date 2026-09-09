"""图纸元数据校验：标题栏必填 + 图层命名 + 标注完整性。"""

from __future__ import annotations

import logging
from typing import Any

from common.constants import ViolationSeverity
from models.domain import Violation

logger = logging.getLogger(__name__)


# 必填标题栏字段
_REQUIRED_TITLE_FIELDS = ("project", "drawing_no", "revision", "designer")
# 合法的图层名前缀（首版硬编码；4c 可走 config）
_VALID_LAYER_PREFIXES = ("STRU", "ARCH", "MEP", "ELEC", "PLUMB", "HVAC")


class DrawingValidator:
    """图纸元数据校验器（首版占位）。"""

    def __init__(self) -> None:
        self._required_fields = _REQUIRED_TITLE_FIELDS
        self._valid_layer_prefixes = _VALID_LAYER_PREFIXES

    async def validate(
        self, drawing_meta: dict[str, Any] | None, *, tenant_id: str = "",
    ) -> list[Violation]:
        """对单张图纸元数据校验。"""
        if drawing_meta is None:
            return []
        if not isinstance(drawing_meta, dict):
            # H19：非 dict（str/数值等）直接跳过，避免 .get 抛 AttributeError
            logger.debug(
                "validate 跳过非 dict 图纸元数据: %r",
                type(drawing_meta).__name__,
            )
            return []
        violations: list[Violation] = []
        violations.extend(self._check_title_block(drawing_meta, tenant_id=tenant_id))
        violations.extend(self._check_layers(drawing_meta, tenant_id=tenant_id))
        violations.extend(self._check_annotations(drawing_meta, tenant_id=tenant_id))
        return violations

    async def validate_batch(
        self, drawings: list[dict[str, Any]], *, tenant_id: str = "",
    ) -> list[Violation]:
        """批量校验。

        H19 修补（validator 层防御）：跳过非 dict 元素（str/None/数值），
        避免 ``_check_title_block`` 对非 dict 调用 ``.get`` 抛
        AttributeError。agent 层已做归一化，这里保证公开入口同样健壮。
        """
        out: list[Violation] = []
        for d in drawings:
            if not isinstance(d, dict):
                logger.debug(
                    "validate_batch 跳过非 dict 图纸元数据（tenant=%s）: %r",
                    tenant_id, type(d).__name__,
                )
                continue
            out.extend(await self.validate(d, tenant_id=tenant_id))
        return out

    def _check_title_block(
        self, meta: dict[str, Any], *, tenant_id: str = "",
    ) -> list[Violation]:
        out: list[Violation] = []
        for f in self._required_fields:
            v = meta.get(f)
            if v is None or (isinstance(v, str) and not v.strip()):
                out.append(self._mk_violation(
                    f"图纸标题栏缺失字段: {f}",
                    severity="medium",
                    tenant_id=tenant_id,
                ))
        return out

    def _check_layers(
        self, meta: dict[str, Any], *, tenant_id: str = "",
    ) -> list[Violation]:
        out: list[Violation] = []
        layers = meta.get("layers") or []
        if not layers:
            out.append(self._mk_violation(
                "图纸未声明任何图层",
                severity="low",
                tenant_id=tenant_id,
            ))
            return out
        # 至少一个图层名前缀匹配
        if not any(_layer_prefix(layer) for layer in layers):
            out.append(self._mk_violation(
                f"图层命名不合法：至少应包含 {self._valid_layer_prefixes} 之一",
                severity="low",
                tenant_id=tenant_id,
            ))
        return out

    def _check_annotations(
        self, meta: dict[str, Any], *, tenant_id: str = "",
    ) -> list[Violation]:
        out: list[Violation] = []
        annotations = meta.get("annotations") or {}
        required = ("dimensions", "index", "legend")
        for k in required:
            if not annotations.get(k):
                out.append(self._mk_violation(
                    f"图纸标注不完整：缺少 {k}",
                    severity="low",
                    tenant_id=tenant_id,
                ))
        return out

    @staticmethod
    def _mk_violation(
        description: str, severity: str = "low", *, tenant_id: str = "",
    ) -> Violation:
        sev_map = {
            "low": ViolationSeverity.LOW,
            "medium": ViolationSeverity.MEDIUM,
            "high": ViolationSeverity.HIGH,
            "critical": ViolationSeverity.CRITICAL,
        }
        return Violation(
            tenant_id=tenant_id,
            inspection_id="",
            regulation_id="DRAWING-META",
            regulation_version="1.0",
            clause="-",
            description=description,
            severity=sev_map.get(severity, ViolationSeverity.LOW),
            rectification="补全图纸元数据",
        )


def _layer_prefix(name: str) -> bool:
    """检查图层名是否以合法前缀开头。"""
    if not isinstance(name, str):
        return False
    upper = name.upper()
    return any(upper.startswith(p) for p in _VALID_LAYER_PREFIXES)
