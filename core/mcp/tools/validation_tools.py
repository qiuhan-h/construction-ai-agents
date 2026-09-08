"""MCP 校验工具：方案 / 图纸 / 文档一致性。

首版实现为占位校验：仅做必填字段检查与轻量元数据核验。
阶段三 safety_audit_agent 完善图纸解析与方案校验算法。
"""

from __future__ import annotations

from typing import Any

from common.timeutils import to_iso, utc_now
from core.mcp.server import register_tool


@register_tool(
    name="validation.plan",
    description="施工方案必填字段与一致性校验（首版）",
)
async def validate_plan(
    plan_id: str,
    title: str = "",
    risk_level: str = "",
    hazards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    issues: list[str] = []
    if not title.strip():
        issues.append("title 不能为空")
    if risk_level not in {"low", "medium", "high"}:
        issues.append("risk_level 必须是 low/medium/high")
    if not hazards:
        issues.append("hazards 至少 1 条")
    return {
        "ok": len(issues) == 0,
        "plan_id": plan_id,
        "issues": issues,
        "validated_at": to_iso(utc_now()),
    }


@register_tool(
    name="validation.drawing",
    description="图纸基础元数据校验（首版仅检查文件存在）",
)
async def validate_drawing(
    drawing_id: str,
    file_uri: str = "",
) -> dict[str, Any]:
    issues: list[str] = []
    if not file_uri:
        issues.append("file_uri 不能为空")
    elif not (file_uri.startswith("file://") or file_uri.startswith("http")):
        issues.append("file_uri 协议必须是 file:// 或 http(s)://")
    return {
        "ok": len(issues) == 0,
        "drawing_id": drawing_id,
        "issues": issues,
        "validated_at": to_iso(utc_now()),
    }


@register_tool(
    name="validation.document",
    description="通用文档完整性校验（首版占位）",
)
async def validate_document(
    document_id: str,
    size_bytes: int = 0,
    mime_type: str = "",
) -> dict[str, Any]:
    issues: list[str] = []
    if size_bytes <= 0:
        issues.append("size_bytes 必须 > 0")
    if not mime_type:
        issues.append("mime_type 不能为空")
    return {
        "ok": len(issues) == 0,
        "document_id": document_id,
        "issues": issues,
        "validated_at": to_iso(utc_now()),
    }
