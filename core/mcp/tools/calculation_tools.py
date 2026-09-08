"""MCP 计算工具：荷载 / 风险评估 / 结构检查。

首版使用简化公式与占位常量；阶段三/四替换为符合国标的真实算法。
所有工具返回 dict，调用方应通过 MCPToolExecutionError 捕获失败。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from common.timeutils import to_iso, utc_now
from core.mcp.server import register_tool


@register_tool(
    name="calculation.load",
    description="根据方案参数计算恒/活/风/雪荷载组合（首版简化公式）",
)
async def calculate_load(
    plan_id: str,
    dead_load_kpa: float = 0.0,
    live_load_kpa: float = 0.0,
    wind_pressure_kpa: float = 0.0,
    snow_pressure_kpa: float = 0.0,
) -> dict[str, Any]:
    """结构荷载组合（简化）：q = 1.2*DL + 1.4*LL + 0.6*W + 0.7*S"""
    if any(v < 0 for v in (dead_load_kpa, live_load_kpa, wind_pressure_kpa, snow_pressure_kpa)):
        return {
            "ok": False,
            "error": "荷载输入不能为负",
            "plan_id": plan_id,
        }
    combo = 1.2 * dead_load_kpa + 1.4 * live_load_kpa + 0.6 * wind_pressure_kpa + 0.7 * snow_pressure_kpa
    return {
        "ok": True,
        "plan_id": plan_id,
        "dead_load_kpa": dead_load_kpa,
        "live_load_kpa": live_load_kpa,
        "wind_pressure_kpa": wind_pressure_kpa,
        "snow_pressure_kpa": snow_pressure_kpa,
        "combined_kpa": round(combo, 3),
        "formula": "q = 1.2DL + 1.4LL + 0.6W + 0.7S",
        "computed_at": to_iso(utc_now()),
    }


@register_tool(
    name="calculation.risk",
    description="基于危险源打分评估风险等级（low/medium/high）",
)
async def assess_risk(
    plan_id: str,
    hazards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """危险源打分：score = sum(severity * likelihood)，分级阈值 5 / 10。"""
    hazards = hazards or []
    score = 0.0
    breakdown: list[dict[str, Any]] = []
    for h in hazards:
        sev = float(h.get("severity", 0))
        lik = float(h.get("likelihood", 0))
        contrib = sev * lik
        score += contrib
        breakdown.append({
            "name": h.get("name", ""),
            "severity": sev, "likelihood": lik, "score": contrib,
        })
    if score < 5:
        level = "low"
    elif score < 10:
        level = "medium"
    else:
        level = "high"
    return {
        "ok": True,
        "plan_id": plan_id,
        "hazard_count": len(hazards),
        "score": round(score, 2),
        "level": level,
        "breakdown": breakdown,
        "computed_at": to_iso(utc_now()),
    }


@register_tool(
    name="calculation.structural_check",
    description="结构最小校核（首版仅做空壳校验，阶段三/四实装）",
)
async def structural_check(
    plan_id: str,
    span_m: float = 0.0,
    load_kpa: float = 0.0,
) -> dict[str, Any]:
    """首版空壳：根据跨度和荷载给出粗略合理性提示。"""
    warnings: list[str] = []
    if span_m <= 0 or load_kpa <= 0:
        warnings.append("跨度/荷载输入不合法（需 > 0）")
    if span_m > 30:
        warnings.append("跨度 > 30m，建议进一步专项论证")
    return {
        "ok": len(warnings) == 0,
        "plan_id": plan_id,
        "span_m": span_m,
        "load_kpa": load_kpa,
        "warnings": warnings,
        "computed_at": to_iso(utc_now()),
    }
