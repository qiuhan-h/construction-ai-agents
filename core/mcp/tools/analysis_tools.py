"""MCP 分析工具：风险聚合 / 违规汇总。

首版为占位聚合，阶段四接 orchestrator 工作流后接真实数据。
"""

from __future__ import annotations

from typing import Any

from common.timeutils import to_iso, utc_now
from core.mcp.server import register_tool


@register_tool(
    name="analysis.aggregate_risk",
    description="按 plan/tenant 聚合风险分数（首版占位）",
)
async def aggregate_risk(
    tenant_id: str,
    plan_id: str = "",
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sources = sources or []
    total = sum(float(s.get("score", 0)) for s in sources)
    n = len(sources)
    avg = total / n if n else 0.0
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "plan_id": plan_id,
        "source_count": n,
        "total_score": round(total, 2),
        "avg_score": round(avg, 2),
        "computed_at": to_iso(utc_now()),
    }


@register_tool(
    name="analysis.summarize_violations",
    description="违规项汇总（按严重度计数，首版占位）",
)
async def summarize_violations(
    tenant_id: str,
    violations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    violations = violations or []
    by_severity: dict[str, int] = {}
    for v in violations:
        sev = str(v.get("severity", "unknown"))
        by_severity[sev] = by_severity.get(sev, 0) + 1
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "total": len(violations),
        "by_severity": by_severity,
        "computed_at": to_iso(utc_now()),
    }
