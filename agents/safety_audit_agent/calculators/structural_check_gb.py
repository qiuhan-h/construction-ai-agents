"""GB 50010-2010《混凝土结构设计规范》承载力校核（阶段六增强版）。

覆盖矩形截面受弯构件正截面承载力基本公式：
  α1·f_c·b·x·(h0 − x/2) ≤ M_u
  ξ_b = β1·ε_cu / (ε_cu + ε_y)       适筋梁上限
  x = (f_y·A_s) / (α1·f_c·b)         由平衡方程解得

本类为 **6a 新增独立类**，不替换现有 StructuralAnalyzer。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .structural_analyzer import MemberType


# =====================================================
# GB 50010-2010 混凝土强度设计值 f_c (N/mm² = MPa)
# =====================================================
CONCRETE_DESIGN_FC_MPA: dict[str, float] = {
    "C15": 7.2,  "C20": 9.6,  "C25": 11.9,
    "C30": 14.3, "C35": 16.7, "C40": 19.1,
    "C45": 21.1, "C50": 23.1, "C55": 25.3,
    "C60": 27.5, "C65": 29.7, "C70": 31.8,
    "C75": 33.8, "C80": 35.9,
}

# 钢筋抗拉强度设计值 f_y (MPa)
STEEL_FY_MPA: dict[str, float] = {
    "HPB300": 270,   # 光圆
    "HRB335": 300,   # 带肋
    "HRB400": 360,
    "HRB500": 435,
    "HRBF400": 360,
}

# α1 / β1（GB 50010 表 6.2.1）
# ≤C50: α1=1.0, β1=0.8
# C55-C80: α1 线性插值 1.0→0.8, β1 线性插值 0.8→0.7
def _alpha1_beta1(concrete_grade: str) -> tuple[float, float]:
    fc = CONCRETE_DESIGN_FC_MPA.get(concrete_grade, 14.3)
    if fc <= 23.1:      # ≤ C50
        return 1.0, 0.8
    # C55~C80: f_c 从 25.3→35.9, α1 从 1.0→0.8, β1 从 0.8→0.7
    # 归一化 t ∈ [0, 1]
    t = (fc - 25.3) / (35.9 - 25.3)
    alpha1 = 1.0 - 0.2 * t
    beta1 = 0.8 - 0.1 * t
    return max(alpha1, 0.8), max(beta1, 0.7)

# ε_cu = 0.0033, ε_y = f_y / E_s (E_s ≈ 2.0×10⁵)
E_S_MPA = 2.0e5
EPS_CU = 0.0033


@dataclass(frozen=True)
class ConcreteBeamInput:
    """矩形截面受弯构件正截面承载力计算输入。

    所有单位：mm（几何）、MPa（应力）、N（力）。

    load_kN_per_m 为 **线荷载**（kN/m）— 即面荷载 × 梁分担宽度。
    跨中弯矩 M = w·L²/8，w = load_kN_per_m × 1000（N/mm），L = span_mm（mm）。

    若你手头只有面荷载（kN/m²），用 面荷载 × 梁间距(m) 换算成线荷载。
    """
    plan_id: str
    b_mm: float                 # 截面宽度 mm
    h_mm: float                 # 截面高度 mm
    span_mm: float              # 跨度 mm
    load_kN_per_m: float        # 线荷载 kN/m（面荷载 × 梁间距）
    concrete_grade: str = "C30"
    steel_grade: str = "HRB400"
    cover_mm: float = 25.0      # 保护层 mm
    as_mm2: float | None = None # 受拉钢筋面积（可选，None 时计算最小配筋）

    @property
    def h0_mm(self) -> float:
        return self.h_mm - self.cover_mm - 10.0  # 粗估：保护层 + 箍筋直径

    @property
    def moment_Nmm(self) -> float:
        """跨中弯矩 M = w·L²/8。w 单位 N/mm，L 单位 mm。"""
        w_N_per_mm = self.load_kN_per_m * 1000 / 1000.0  # kN/m → N/mm
        L = self.span_mm
        return w_N_per_mm * L * L / 8


@dataclass(frozen=True)
class BearingCheckResult:
    """GB 50010 结构校核结果。"""

    # 输入回显
    plan_id: str
    b_mm: float
    h_mm: float
    span_mm: float
    load_kN_per_m: float
    concrete_grade: str
    steel_grade: str

    # 计算值
    alpha1: float
    beta1: float
    fc_mpa: float
    fy_mpa: float
    xi_b: float                        # 相对界限受压区高度
    mu: float                          # 相对受压区高度 x/h0（按最小配筋算 ξ）
    as_required_mm2: float              # 所需受拉钢筋面积
    as_provided_mm2: float | None
    moment_applied_kN_m: float         # 施加弯矩 kN·m
    moment_capacity_kN_m: float        # 极限承载弯矩 kN·m
    utilization_ratio: float            # 使用率 M / M_u
    is_ductile: bool                   # 适筋梁（延性）？
    is_sufficient: bool                 # 配筋足够承载？
    warnings: list[str] = field(default_factory=list)
    formula: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            k: (round(v, 3) if isinstance(v, float) else v)
            for k, v in self.__dict__.items()
        }


class GB50010StructuralAnalyzer:
    """GB 50010-2010 混凝土矩形截面受弯构件增强版校验。"""

    async def check_bearing_capacity(self, inputs: ConcreteBeamInput) -> BearingCheckResult:
        return await asyncio.to_thread(self._check_sync, inputs)

    def _check_sync(self, i: ConcreteBeamInput) -> BearingCheckResult:
        if i.b_mm <= 0 or i.h_mm <= 0 or i.span_mm <= 0:
            raise ValueError("b_mm / h_mm / span_mm 必须 > 0")

        fc = CONCRETE_DESIGN_FC_MPA.get(i.concrete_grade, 14.3)
        fy = STEEL_FY_MPA.get(i.steel_grade, 360)
        alpha1, beta1 = _alpha1_beta1(i.concrete_grade)
        eps_y = fy / E_S_MPA
        xi_b = beta1 * EPS_CU / (EPS_CU + eps_y)
        h0 = i.h0_mm

        M_applied = i.moment_Nmm             # N·mm
        as_req = (alpha1 * fc * i.b_mm * xi_b * h0) / fy  # 受拉钢筋按适筋上限

        # 极限承载弯矩 M_u = α1·f_c·b·ξ·h0²·(1−ξ/2)
        xi = as_req * fy / (alpha1 * fc * i.b_mm * h0)     # 按最小配筋反推
        xi = min(xi, xi_b)                                  # 适筋上限截断
        M_u = alpha1 * fc * i.b_mm * xi * h0 * h0 * (1.0 - xi / 2.0)

        utilization = M_applied / M_u if M_u > 0 else 1.0
        as_provided = i.as_mm2
        warnings: list[str] = []

        # --- 判断 ---
        is_ductile = xi <= xi_b
        is_sufficient = utilization <= 1.05

        if not is_ductile:
            warnings.append(
                f"超筋：ξ={xi:.3f} > ξ_b={xi_b:.3f}，呈脆性破坏，建议增大截面或提高混凝土强度"
            )
        if not is_sufficient:
            warnings.append(
                f"配筋不足：使用率 {utilization*100:.0f}% > 105%，建议增加钢筋面积或增大截面"
            )
        if as_provided is not None and as_provided < as_req:
            warnings.append(
                f"实际配筋 {as_provided:.0f}mm² < 所需 {as_req:.0f}mm²"
            )

        return BearingCheckResult(
            plan_id=i.plan_id,
            b_mm=i.b_mm, h_mm=i.h_mm, span_mm=i.span_mm,
            load_kN_per_m=i.load_kN_per_m, concrete_grade=i.concrete_grade,
            steel_grade=i.steel_grade,
            alpha1=alpha1, beta1=beta1, fc_mpa=fc, fy_mpa=fy,
            xi_b=xi_b, mu=xi,
            as_required_mm2=as_req, as_provided_mm2=as_provided,
            moment_applied_kN_m=M_applied / 1e6,
            moment_capacity_kN_m=M_u / 1e6,
            utilization_ratio=utilization,
            is_ductile=is_ductile, is_sufficient=is_sufficient,
            warnings=warnings,
            formula=f"α1·f_c·b·ξ·h0²·(1−ξ/2), ξ=min(ξ, ξ_b={xi_b:.3f})",
        )

    # ------------------------------------------------------------------
    # 查表工具
    # ------------------------------------------------------------------
    @staticmethod
    def concrete_fc(grade: str) -> float | None:
        return CONCRETE_DESIGN_FC_MPA.get(grade)

    @staticmethod
    def steel_fy(grade: str) -> float | None:
        return STEEL_FY_MPA.get(grade)
