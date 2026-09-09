"""GB 50009-2012《建筑结构荷载规范》荷载组合（阶段六增强版）。

替换 / 叠加现有 LoadCalculator 简化公式。
系数严格按 GB 50009-2012 §3.2.4 取值：
- 永久荷载 γG = 1.2（不利）/ 1.0（有利）/ 0.9（对抗倾覆/滑移有利）
- 可变荷载 γQ = 1.4（一般）/ 1.35（用于 1.35G + 1.4×0.7Q 组合）
- 组合值系数 ψc = 0.7（两个可变荷载）/ 0.6（风与雪同时）
- 准永久系数 ψq = 0.5（楼盖活载）/ 0（屋面活载）

本类为 **6a 新增独立类**，不替换现有 LoadCalculator。
SafetyAuditAgent 按精度需求路由调用。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal

from .load_calculator import (
    FLOOR_LIVE_LOAD_KPA,
    MATERIAL_SELF_WEIGHT_KN_M3,
    LoadInputs,
)

# =====================================================
# GB 50009-2012 §3.2.4 系数表
# =====================================================
GAMMA_G_UNFAVORABLE = 1.2        # 永久荷载不利组合系数
GAMMA_G_FAVORABLE = 1.0           # 永久荷载有利组合系数
GAMMA_G_OVERTURN = 0.9            # 抗倾覆/滑移时永久荷载有利系数
GAMMA_Q = 1.4                     # 可变荷载基本系数
GAMMA_Q_LOW = 1.35                # 1.35G 组合时的 Q 系数
PSI_C_TWO = 0.7                   # 两个可变荷载同时作用时的组合值系数
PSI_C_WIND_SNOW = 0.6             # 风与雪同时作用
PSI_Q_FLOOR = 0.5                 # 楼盖活载准永久系数
PSI_Q_ROOF = 0.0                  # 屋面活载准永久系数

# 典型基本风压（kN/m²）— GB 50009 附录 E
BASIC_WIND_PRESSURE_BY_REGION: dict[str, float] = {
    "北京": 0.45, "上海": 0.55, "广州": 0.55, "深圳": 0.75,
    "武汉": 0.35, "重庆": 0.40, "成都": 0.30, "西安": 0.35,
    "哈尔滨": 0.55, "沈阳": 0.50, "昆明": 0.25, "乌鲁木齐": 0.60,
}

# 典型基本雪压（kN/m²）
BASIC_SNOW_PRESSURE_BY_REGION: dict[str, float] = {
    "北京": 0.40, "上海": 0.20, "广州": 0.00, "深圳": 0.00,
    "武汉": 0.15, "重庆": 0.00, "成都": 0.10, "西安": 0.35,
    "哈尔滨": 0.75, "沈阳": 0.55, "昆明": 0.00, "乌鲁木齐": 0.65,
}


LoadCombinationType = Literal["basic", "standard", "quasi_permanent", "overturn"]


@dataclass(frozen=True)
class LoadCombinationResult:
    """多种组合同时计算的结果。"""

    plan_id: str
    basic_combos: dict[str, float] = field(default_factory=dict)      # 基本组合（承载能力极限状态）
    standard_combo: float = 0.0                                       # 标准组合（正常使用极限状态）
    quasi_permanent_combo: float = 0.0                                # 准永久组合
    overturn_check: dict[str, float] = field(default_factory=dict)    # 抗倾覆验算结果
    formulae: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "basic_combos": {k: round(v, 3) for k, v in self.basic_combos.items()},
            "standard_combo": round(self.standard_combo, 3),
            "quasi_permanent_combo": round(self.quasi_permanent_combo, 3),
            "overturn_check": {k: round(v, 3) for k, v in self.overturn_check.items()},
            "formulae": dict(self.formulae),
        }


class GB50009LoadCalculator:
    """GB 50009-2012 荷载组合增强版计算器。

    覆盖 §3.2.4 全部四种组合 + 抗倾覆验算。
    与现有 LoadCalculator 并存，按需路由调用。
    """

    async def combine_loads(
        self,
        inputs: LoadInputs,
        region: str | None = None,
    ) -> LoadCombinationResult:
        """计算 GB 50009 全套荷载组合。

        用法::

            gb = GB50009LoadCalculator()
            result = await gb.combine_loads(LoadInputs(plan_id="p1", dead_load_kpa=3.0, live_load_kpa=2.5))
            print(result.basic_combos["G+Q"])   # 1.2D + 1.4L
            print(result.basic_combos["1.35G+0.7×1.4Q"])  # 1.35D + 0.98L
        """
        return await asyncio.to_thread(self._combine_loads_sync, inputs, region)

    def _combine_loads_sync(
        self, inputs: LoadInputs, region: str | None
    ) -> LoadCombinationResult:
        d = inputs.dead_load_kpa
        live = inputs.live_load_kpa
        w = (
            inputs.wind_vibration_coef
            * inputs.wind_shape_coef
            * inputs.wind_height_coef
            * inputs.wind_pressure_kpa
        )
        s = inputs.snow_shape_coef * inputs.snow_pressure_kpa

        # 基本风压/雪压按地区查表（若 region 提供且 inputs 中未覆盖默认值）
        if region and inputs.wind_pressure_kpa == 0.45:
            w0 = BASIC_WIND_PRESSURE_BY_REGION.get(region, inputs.wind_pressure_kpa)
            w = inputs.wind_vibration_coef * inputs.wind_shape_coef * inputs.wind_height_coef * w0
        if region and inputs.snow_pressure_kpa == 0.30:
            s0 = BASIC_SNOW_PRESSURE_BY_REGION.get(region, inputs.snow_pressure_kpa)
            s = inputs.snow_shape_coef * s0

        # --- §3.2.3 基本组合（承载能力极限状态）---
        basic: dict[str, float] = {}
        formulae: dict[str, str] = {}

        # 1) 1.2G + 1.4Q（Q 取控制可变荷载）
        q_max = max(live, w, s)
        basic["G+Q"] = GAMMA_G_UNFAVORABLE * d + GAMMA_Q * q_max
        formulae["G+Q"] = "1.2·G + 1.4·Q"

        # 2) 1.2G + 1.4L + 0.6·1.4W（风与活载）
        basic["G+L+0.6W"] = GAMMA_G_UNFAVORABLE * d + GAMMA_Q * live + GAMMA_Q * PSI_C_TWO * w
        formulae["G+L+0.6W"] = "1.2·G + 1.4·L + 1.4×0.7·W"

        # 3) 1.2G + 1.4W + 0.6·1.4L（风控制）
        basic["G+W+0.6L"] = GAMMA_G_UNFAVORABLE * d + GAMMA_Q * w + GAMMA_Q * PSI_C_TWO * live
        formulae["G+W+0.6L"] = "1.2·G + 1.4·W + 1.4×0.7·L"

        # 4) 1.2G + 1.4W + 0.6·1.4S（风+雪）
        basic["G+W+0.6S"] = GAMMA_G_UNFAVORABLE * d + GAMMA_Q * w + GAMMA_Q * PSI_C_WIND_SNOW * s
        formulae["G+W+0.6S"] = "1.2·G + 1.4·W + 1.4×0.6·S"

        # 5) 1.2G + 1.4S + 0.6·1.4W（雪+风）
        basic["G+S+0.6W"] = GAMMA_G_UNFAVORABLE * d + GAMMA_Q * s + GAMMA_Q * PSI_C_WIND_SNOW * w
        formulae["G+S+0.6W"] = "1.2·G + 1.4·S + 1.4×0.6·W"

        # 6) 1.35G + 1.4×0.7·Q（永久荷载控制）
        basic["1.35G+0.7Q"] = 1.35 * d + GAMMA_Q * PSI_C_TWO * live
        formulae["1.35G+0.7Q"] = "1.35·G + 1.4×0.7·Q"

        # --- §3.2.7 标准组合（正常使用极限状态）---
        standard = d + live + PSI_C_TWO * w

        # --- §3.2.8 准永久组合 ---
        psi_q = PSI_Q_ROOF if inputs.snow_pressure_kpa > 0 else PSI_Q_FLOOR
        quasi_perm = d + psi_q * live + 0.2 * w + 0.2 * s

        # --- 抗倾覆验算 ---
        overturn = {
            "stabilizing": GAMMA_G_OVERTURN * d,
            "destabilizing": GAMMA_Q * w + GAMMA_Q * live,
        }

        return LoadCombinationResult(
            plan_id=inputs.plan_id,
            basic_combos=basic,
            standard_combo=standard,
            quasi_permanent_combo=quasi_perm,
            overturn_check=overturn,
            formulae=formulae,
        )

    # ------------------------------------------------------------------
    # 查表工具
    # ------------------------------------------------------------------
    @staticmethod
    def basic_wind_pressure(region: str) -> float:
        """按地区查基本风压（kN/m²）。"""
        return BASIC_WIND_PRESSURE_BY_REGION.get(region, 0.45)

    @staticmethod
    def basic_snow_pressure(region: str) -> float:
        """按地区查基本雪压（kN/m²）。"""
        return BASIC_SNOW_PRESSURE_BY_REGION.get(region, 0.30)

    @staticmethod
    def live_load(category: str) -> float | None:
        """按房间类别查活荷载（kN/m²）。与 LoadCalculator 共享表。"""
        return FLOOR_LIVE_LOAD_KPA.get(category)

    @staticmethod
    def material_self_weight(material: str) -> float | None:
        """按材料名查自重（kN/m³）。"""
        return MATERIAL_SELF_WEIGHT_KN_M3.get(material)
