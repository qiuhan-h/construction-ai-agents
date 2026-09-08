"""荷载计算：GB 50009-2012《建筑结构荷载规范》核心公式的首版实现。

覆盖：
- 永久荷载 D（按材料自重表查得）
- 活荷载 L（按房间类别查表）
- 风荷载 W = βz·μs·μz·w0
- 雪荷载 S = μr·Ce·Ct·sk
- 基本组合：1.2D + 1.4L + 0.6W + 0.7S

首版说明：
- 系数表为典型值（办公室/住宅/风敏感结构等），覆盖 80% 业务场景；
- 阶段四将按 GB 50009 完整附表 A/B/C 替换为可配置数据集。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


# =====================================================
# 典型材料自重（kN/m³）— 节选自 GB 50009 附录 A
# =====================================================
MATERIAL_SELF_WEIGHT_KN_M3: dict[str, float] = {
    "钢筋混凝土": 25.0,
    "素混凝土": 24.0,
    "水泥砂浆": 20.0,
    "钢": 78.5,
    "木材（松木）": 5.0,
    "普通砖": 18.0,
    "花岗岩": 28.0,
}


# =====================================================
# 楼面活荷载（kN/m²）— 节选自 GB 50009 表 5.1.1
# =====================================================
FLOOR_LIVE_LOAD_KPA: dict[str, float] = {
    "住宅": 2.0,
    "办公": 2.5,
    "教室": 2.5,
    "商场": 3.5,
    "车库": 4.0,
    "楼梯/走廊（办公/住宅）": 2.0,
    "楼梯/走廊（学校/商场）": 3.5,
    "上人屋面": 2.0,
    "不上人屋面": 0.5,
}


# =====================================================
# 基本风压 / 基本雪压（kN/m²）— 阶段四接 config 注入
# =====================================================
DEFAULT_BASIC_WIND_PRESSURE_KPA: float = 0.45
DEFAULT_BASIC_SNOW_PRESSURE_KPA: float = 0.30


# =====================================================
# 输入 / 输出
# =====================================================
@dataclass(frozen=True)
class LoadInputs:
    """荷载计算输入（kPa = kN/m²）。"""

    plan_id: str
    dead_load_kpa: float = 0.0
    live_load_kpa: float = 0.0
    wind_pressure_kpa: float = DEFAULT_BASIC_WIND_PRESSURE_KPA
    snow_pressure_kpa: float = DEFAULT_BASIC_SNOW_PRESSURE_KPA
    # 可选：风荷载体型系数 μs 与高度系数 μz（默认 1.0）
    wind_shape_coef: float = 1.0
    wind_height_coef: float = 1.0
    wind_vibration_coef: float = 1.0
    # 可选：雪荷载分布系数 μr
    snow_shape_coef: float = 1.0


@dataclass(frozen=True)
class LoadResult:
    """荷载计算结果。"""

    plan_id: str
    dead_load_kpa: float
    live_load_kpa: float
    wind_pressure_kpa: float
    snow_pressure_kpa: float
    combined_kpa: float
    formula: str = "1.2D + 1.4L + 0.6W + 0.7S"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "dead_load_kpa": round(self.dead_load_kpa, 3),
            "live_load_kpa": round(self.live_load_kpa, 3),
            "wind_pressure_kpa": round(self.wind_pressure_kpa, 3),
            "snow_pressure_kpa": round(self.snow_pressure_kpa, 3),
            "combined_kpa": round(self.combined_kpa, 3),
            "formula": self.formula,
            "metadata": self.metadata,
        }


# =====================================================
# 计算器
# =====================================================
class LoadCalculator:
    """GB 50009 首版荷载组合计算器（async 接口，内部计算用 to_thread）。"""

    async def combined_load(self, inputs: LoadInputs) -> LoadResult:
        """基本组合 1.2D + 1.4L + 0.6W + 0.7S。"""
        return await asyncio.to_thread(self._combined_load_sync, inputs)

    def _combined_load_sync(self, inputs: LoadInputs) -> LoadResult:
        for name, v in (
            ("dead_load_kpa", inputs.dead_load_kpa),
            ("live_load_kpa", inputs.live_load_kpa),
            ("wind_pressure_kpa", inputs.wind_pressure_kpa),
            ("snow_pressure_kpa", inputs.snow_pressure_kpa),
        ):
            if v < 0:
                raise ValueError(f"{name} 不能为负（实际={v}）")

        # 风荷载调整：w = βz · μs · μz · w0
        w = (
            inputs.wind_vibration_coef
            * inputs.wind_shape_coef
            * inputs.wind_height_coef
            * inputs.wind_pressure_kpa
        )
        # 雪荷载调整：s = μr · sk
        s = inputs.snow_shape_coef * inputs.snow_pressure_kpa
        # 组合
        combo = 1.2 * inputs.dead_load_kpa + 1.4 * inputs.live_load_kpa + 0.6 * w + 0.7 * s

        return LoadResult(
            plan_id=inputs.plan_id,
            dead_load_kpa=inputs.dead_load_kpa,
            live_load_kpa=inputs.live_load_kpa,
            wind_pressure_kpa=w,
            snow_pressure_kpa=s,
            combined_kpa=combo,
            metadata={
                "wind_raw_kpa": inputs.wind_pressure_kpa,
                "snow_raw_kpa": inputs.snow_pressure_kpa,
                "wind_shape_coef": inputs.wind_shape_coef,
                "wind_height_coef": inputs.wind_height_coef,
                "wind_vibration_coef": inputs.wind_vibration_coef,
                "snow_shape_coef": inputs.snow_shape_coef,
            },
        )

    @staticmethod
    def material_self_weight(material: str) -> float | None:
        """按材料名查自重（kN/m³）；未收录返回 None。"""
        return MATERIAL_SELF_WEIGHT_KN_M3.get(material)

    @staticmethod
    def live_load(category: str) -> float | None:
        """按房间类别查活荷载（kN/m²）。"""
        return FLOOR_LIVE_LOAD_KPA.get(category)
