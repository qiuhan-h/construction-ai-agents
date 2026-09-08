"""MCP 案例资源（事故/合规案例摘要）。

URI 规范：case://{case_id}
首版实现：从 data/cases/{case_id}.json 读取；
        不存在时返回空内容 + available=False。
阶段三/四与 models.vector.CaseVector 对齐。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common.ids import case_id
from config import get_settings
from core.mcp.server import register_resource

CASE_URI_PREFIX: str = "case://"


def _cases_dir() -> Path:
    return get_settings().project_root / "data" / "cases"


def _parse_uri(uri: str) -> str:
    if not uri.startswith(CASE_URI_PREFIX):
        raise ValueError(f"非法案例 URI: {uri}")
    return uri[len(CASE_URI_PREFIX):].strip("/")


def list_cases(tenant_id: str | None = None) -> list[dict[str, Any]]:
    """列出案例；按 tenant_id 过滤。"""
    base = _cases_dir()
    out: list[dict[str, Any]] = []
    if not base.exists():
        return out
    for path in sorted(base.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if tenant_id and data.get("tenant_id") and data["tenant_id"] != tenant_id:
            continue
        out.append({
            "case_id": data.get("case_id", path.stem),
            "title": data.get("title", ""),
            "tenant_id": data.get("tenant_id"),
            "uri": f"{CASE_URI_PREFIX}{data.get('case_id', path.stem)}",
        })
    return out


@register_resource(
    uri=f"{CASE_URI_PREFIX}*",
    name="case",
    description="工程事故/合规案例摘要（多租户隔离）",
    mime_type="application/json",
)
async def read_case(uri: str, tenant_id: str | None = None) -> dict[str, Any]:
    try:
        cid = _parse_uri(uri)
    except ValueError as e:
        return {"available": False, "uri": uri, "error": str(e)}

    base = _cases_dir()
    path = base / f"{cid}.json"
    if not path.exists():
        # 占位：返回结构化空壳，便于上层 RAG
        return {
            "available": False,
            "uri": uri,
            "case_id": cid,
            "case_id_new": case_id(),
            "title": "",
            "summary": "案例尚未登记（阶段四批量灌入）",
            "tenant_id": tenant_id,
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    if tenant_id and data.get("tenant_id") and data["tenant_id"] != tenant_id:
        # 多租户隔离：不可越权读
        return {
            "available": False,
            "uri": uri,
            "error": "租户隔离：当前租户无权访问该案例",
        }
    return {"available": True, "uri": uri, **data}
