"""MCP 法规资源。

URI 规范：regulation://{code}/{version}
        + regulation://_list           法规清单（4a 新增）
首版实现：从 data/regulations/{code}__{version}.md 读取；
        不存在时返回空内容 + metadata.available=False。
阶段四接 SQLAlchemy 与法规版本管理器。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from common.ids import regulation_id
from config import get_settings
from core.mcp.server import register_resource

REGULATION_URI_PREFIX: str = "regulation://"
REGULATION_LIST_URI: str = "regulation://_list"


def _regulations_dir() -> Path:
    settings = get_settings()
    return settings.project_root / "data" / "regulations"


def _parse_uri(uri: str) -> tuple[str, str]:
    """解析 regulation://{code}/{version} 为 (code, version)。"""
    if not uri.startswith(REGULATION_URI_PREFIX):
        raise ValueError(f"非法法规 URI: {uri}")
    body = uri[len(REGULATION_URI_PREFIX):].strip("/")
    parts = body.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"法规 URI 必须包含 code/version: {uri}")
    return parts[0], parts[1]


def list_regulations() -> list[dict[str, Any]]:
    """扫描本地法规文件目录，列出可用版本。"""
    base = _regulations_dir()
    out: list[dict[str, Any]] = []
    if not base.exists():
        return out
    for path in sorted(base.glob("*.md")):
        # 约定文件命名: {code}__{version}.md
        stem = path.stem
        if "__" in stem:
            code, version = stem.split("__", 1)
        else:
            code, version = stem, "latest"
        out.append({
            "regulation_id": regulation_id(),
            "code": code,
            "version": version,
            "uri": f"{REGULATION_URI_PREFIX}{code}/{version}",
            "path": str(path.relative_to(base.parent.parent)),
            "size_bytes": path.stat().st_size,
        })
    return out


@register_resource(
    uri=f"{REGULATION_URI_PREFIX}*",
    name="regulation",
    description="建筑工程法规条文（按 code/version 寻址）",
    mime_type="text/markdown",
)
async def read_regulation(uri: str) -> dict[str, Any]:
    """读取指定法规版本的全文。"""
    try:
        code, version = _parse_uri(uri)
    except ValueError as e:
        return {"available": False, "uri": uri, "error": str(e)}

    base = _regulations_dir()
    path = base / f"{code}__{version}.md"
    if not path.exists():
        return {
            "available": False,
            "uri": uri,
            "code": code,
            "version": version,
            "message": "法规文件不存在（仅占位，阶段四接 SQLAlchemy）",
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


# =========================================================
# 4a 新增：regulation://_list 资源（法规清单）
# =========================================================
@register_resource(
    uri=REGULATION_LIST_URI,
    name="regulation_list",
    description="所有可用法规清单（4a compliance_agent 使用）",
    mime_type="application/json",
)
async def read_regulation_list(uri: str) -> dict[str, Any]:
    """读取法规清单（regulation://_list 资源）。

    返回 {"content": [list_regulations()]}；外层字段与 MCPResourceReader 约定一致。
    失败/无文件时返回 {"content": []}。
    """
    try:
        regs = list_regulations()
        return {"content": regs, "count": len(regs)}
    except Exception as e:  # noqa: BLE001
        return {"content": [], "error": str(e)}
