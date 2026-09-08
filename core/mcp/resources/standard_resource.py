"""MCP 标准资源（国标/行标等）。

URI 规范：standard://{code}/{version}
首版实现：从 data/regulations/standards/{code}__{version}.md 读取。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from common.ids import standard_id
from config import get_settings
from core.mcp.server import register_resource

STANDARD_URI_PREFIX: str = "standard://"


def _standards_dir() -> Path:
    return get_settings().project_root / "data" / "regulations" / "standards"


def _parse_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith(STANDARD_URI_PREFIX):
        raise ValueError(f"非法标准 URI: {uri}")
    body = uri[len(STANDARD_URI_PREFIX):].strip("/")
    parts = body.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"标准 URI 必须包含 code/version: {uri}")
    return parts[0], parts[1]


def list_standards() -> list[dict[str, Any]]:
    base = _standards_dir()
    out: list[dict[str, Any]] = []
    if not base.exists():
        return out
    for path in sorted(base.glob("*.md")):
        stem = path.stem
        if "__" in stem:
            code, version = stem.split("__", 1)
        else:
            code, version = stem, "latest"
        out.append({
            "standard_id": standard_id(),
            "code": code,
            "version": version,
            "uri": f"{STANDARD_URI_PREFIX}{code}/{version}",
            "size_bytes": path.stat().st_size,
        })
    return out


@register_resource(
    uri=f"{STANDARD_URI_PREFIX}*",
    name="standard",
    description="建筑工程标准（国标/行标，按 code/version 寻址）",
    mime_type="text/markdown",
)
async def read_standard(uri: str) -> dict[str, Any]:
    try:
        code, version = _parse_uri(uri)
    except ValueError as e:
        return {"available": False, "uri": uri, "error": str(e)}

    base = _standards_dir()
    path = base / f"{code}__{version}.md"
    if not path.exists():
        return {
            "available": False,
            "uri": uri,
            "code": code,
            "version": version,
            "message": "标准文件不存在（仅占位）",
        }
    text = path.read_text(encoding="utf-8")
    return {
        "available": True,
        "uri": uri,
        "code": code,
        "version": version,
        "length": len(text),
        "text": text,
    }
