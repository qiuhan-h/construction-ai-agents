"""施工方案解析（plan_parser）。

输入：方案文件（Markdown / DOCX / TXT）。DOCX 解析需 python-docx，
未安装时降级为文本读取。

输出：PlanFields 结构化字段：
- project_name
- stage
- hazards: list[{name, ...}]
- materials: list[str]
- loads: dict（dead/live/wind/snow 等）

首版实现：基于 Markdown 段落 + 简单关键字匹配。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 常见危险源关键字（首版，未覆盖到的可由 LLM 补全）
_HAZARD_KEYWORDS: list[str] = [
    "高处坠落", "高坠", "坍塌", "触电", "物体打击", "机械伤害",
    "起重伤害", "火灾", "中毒", "窒息", "透水", "滑坡", "倾覆",
    "坠落", "倒塔", "断绳", "电击", "灼伤", "烫伤",
]

# 阶段关键字
_STAGE_KEYWORDS: list[str] = [
    "基坑", "基础", "主体", "装饰", "装修", "屋面", "机电",
    "安装", "拆除", "幕墙", "钢结构", "脚手架", "模板",
]

_MATERIAL_PATTERN = re.compile(
    r"(?:主要|使用|采用)?\s*(材料|材质)[:：]?\s*([^\n。；;]+)", re.UNICODE
)
_LOAD_PATTERN = re.compile(
    r"(恒荷载|永久荷载|D[：:=]?\s*[\d.]+|活荷载|可变荷载|L[：:=]?\s*[\d.]+|"
    r"风荷载|W[：:=]?\s*[\d.]+|雪荷载|S[：:=]?\s*[\d.]+)\s*k?[NnN/]?",
    re.UNICODE,
)


@dataclass
class PlanFields:
    """方案结构化字段。"""

    project_name: str | None = None
    stage: str | None = None
    hazards: list[dict[str, Any]] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    loads: dict[str, float] = field(default_factory=dict)
    raw_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class PlanParser:
    """施工方案解析器。"""

    def parse_text(self, text: str, *, project_name: str | None = None) -> PlanFields:
        fields = PlanFields(
            project_name=project_name or _extract_project_name(text),
            stage=_extract_stage(text),
            hazards=_extract_hazards(text),
            materials=_extract_materials(text),
            loads=_extract_loads(text),
            raw_text=text,
        )
        return fields

    def parse_file(self, path: str | Path, *, project_name: str | None = None) -> PlanFields:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(str(p))
        suffix = p.suffix.lower()
        if suffix in {".md", ".markdown", ".txt"}:
            text = p.read_text(encoding="utf-8", errors="ignore")
        elif suffix == ".docx":
            text = _read_docx(p)
        else:
            text = p.read_text(encoding="utf-8", errors="ignore")
        return self.parse_text(text, project_name=project_name)


def _extract_project_name(text: str) -> str | None:
    m = re.search(r"项目名称[:：]?\s*([^\n。；;]+)", text)
    return m.group(1).strip() if m else None


def _extract_stage(text: str) -> str | None:
    for kw in _STAGE_KEYWORDS:
        if kw in text:
            return kw
    m = re.search(r"施工阶段[:：]?\s*([^\n。；;]+)", text)
    return m.group(1).strip() if m else None


def _extract_hazards(text: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for kw in _HAZARD_KEYWORDS:
        if kw in text and kw not in seen:
            seen.add(kw)
            out.append({"name": kw, "source": "keyword_match"})
    return out


def _extract_materials(text: str) -> list[str]:
    out: list[str] = []
    for m in _MATERIAL_PATTERN.finditer(text):
        seg = m.group(2).strip()
        for part in re.split(r"[、，,；;]", seg):
            p = part.strip()
            if 1 < len(p) <= 32 and p not in out:
                out.append(p)
    return out


# L12 修补：荷载正则提为模块级常量，避免每次调用 _extract_loads 重新编译。
_LOAD_VALUE_PATTERNS: dict[str, re.Pattern[str]] = {
    "dead": re.compile(r"(?:恒|永久)荷载[^0-9]{0,5}(\d+(?:\.\d+)?)"),
    "live": re.compile(r"(?:活|可变)荷载[^0-9]{0,5}(\d+(?:\.\d+)?)"),
    "wind": re.compile(r"风\s*荷载[^0-9]{0,5}(\d+(?:\.\d+)?)"),
    "snow": re.compile(r"雪\s*荷载[^0-9]{0,5}(\d+(?:\.\d+)?)"),
}


def _extract_loads(text: str) -> dict[str, float]:
    """从文本中提取 D / L / W / S 数值（kN/m²）。"""
    out: dict[str, float] = {}
    for key, pat in _LOAD_VALUE_PATTERNS.items():
        m = pat.search(text)
        if m:
            try:
                out[key] = float(m.group(1))
            except ValueError:
                continue
    return out


def _read_docx(p: Path) -> str:
    """读取 DOCX 文本（需 python-docx；不可用时抛 AgentParseError）。"""
    try:
        from docx import Document  # type: ignore
    except ImportError as e:
        raise ImportError(
            "解析 DOCX 需安装 python-docx（pip install python-docx）"
        ) from e
    doc = Document(str(p))
    parts: list[str] = []
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                if cell.text.strip():
                    parts.append(cell.text)
    return "\n".join(parts)
