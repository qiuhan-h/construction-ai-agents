"""结构分析（首版占位 + 接口）：构件反查 + 最小配筋率提示。

说明：
- 完整有限元 / GB 50010 / GB 50011 计算留到阶段四；
- 首版根据构件类型与截面尺寸，给出：
  1) 最小构造配筋率 ρ_min（参考 GB 50010 表 8.5.1）
  2) 跨高比合理性提示（梁/板常用 L/h 限值）
  3) 高跨结构警示（> 30m 提示专项论证）
- 所有计算为粗略合理性校验，**不替代**详细结构计算。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MemberType(str, Enum):
    """构件类型（节选）。"""

    BEAM = "beam"            # 梁
    SLAB = "slab"            # 板
    COLUMN = "column"        # 柱
    WALL = "wall"            # 剪力墙
    FOUNDATION = "foundation"  # 基础


# =====================================================
# GB 50010 表 8.5.1：受弯构件最小配筋率（节选）
# =====================================================
MIN_FLEXURAL_REINFORCEMENT_RATIO: dict[str, float] = {
    MemberType.BEAM.value: 0.0020,   # 0.20%
    MemberType.SLAB.value: 0.0020,   # 0.20%（常用 0.20%）
    MemberType.COLUMN.value: 0.0060,  # 全截面 0.6%（一侧 0.2%）
    MemberType.WALL.value: 0.0025,
    MemberType.FOUNDATION.value: 0.0020,
}

# 跨高比经验上限（首版：受弯构件）
SPAN_DEPTH_RATIO_LIMIT: dict[str, float] = {
    MemberType.BEAM.value: 12.0,    # 主梁 L/h ≤ 12
    MemberType.SLAB.value: 30.0,    # 单向板 L/h ≤ 30
}


@dataclass(frozen=True)
class StructuralCheckInput:
    plan_id: str
    member_type: MemberType
    span_m: float
    depth_m: float
    load_kpa: float = 0.0
    concrete_grade: str = "C30"  # 预留：阶段四参与计算


@dataclass(frozen=True)
class StructuralCheckResult:
    plan_id: str
    member_type: MemberType
    span_m: float
    depth_m: float
    span_depth_ratio: float
    span_depth_ok: bool
    min_reinforcement_ratio: float
    warnings: list[str] = field(default_factory=list)
    ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "member_type": self.member_type.value,
            "span_m": round(self.span_m, 3),
            "depth_m": round(self.depth_m, 3),
            "span_depth_ratio": round(self.span_depth_ratio, 2),
            "span_depth_ok": self.span_depth_ok,
            "min_reinforcement_ratio": round(self.min_reinforcement_ratio, 4),
            "warnings": list(self.warnings),
            "ok": self.ok,
        }


class StructuralAnalyzer:
    """结构粗略校验（首版）。"""

    async def check(self, inputs: StructuralCheckInput) -> StructuralCheckResult:
        return await asyncio.to_thread(self._check_sync, inputs)

    def _check_sync(self, inputs: StructuralCheckInput) -> StructuralCheckResult:
        if inputs.span_m <= 0 or inputs.depth_m <= 0:
            raise ValueError("span_m / depth_m 必须 > 0")

        ratio = inputs.span_m / inputs.depth_m
        warnings: list[str] = []

        limit = SPAN_DEPTH_RATIO_LIMIT.get(inputs.member_type.value)
        ok = True
        if limit is not None and ratio > limit:
            ok = False
            warnings.append(
                f"跨高比 {ratio:.2f} 超过限值 {limit:.2f}（{inputs.member_type.value}）"
            )

        if inputs.span_m > 30.0:
            warnings.append("跨度 > 30m，建议进一步专项论证")

        if inputs.load_kpa < 0:
            warnings.append("荷载不能为负")

        min_ratio = MIN_FLEXURAL_REINFORCEMENT_RATIO.get(inputs.member_type.value, 0.0020)
        return StructuralCheckResult(
            plan_id=inputs.plan_id,
            member_type=inputs.member_type,
            span_m=inputs.span_m,
            depth_m=inputs.depth_m,
            span_depth_ratio=ratio,
            span_depth_ok=ok,
            min_reinforcement_ratio=min_ratio,
            warnings=warnings,
            ok=ok and not any("不能为负" in w for w in warnings),
        )
