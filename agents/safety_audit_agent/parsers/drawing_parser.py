"""图纸元数据解析（首版）。

输入：IFC 文件（*.ifc）或标题栏文本。
输出：DrawingMetadata（图纸元数据）。

阶段三实现：
- 纯文本标题栏：正则抽取 project / drawing_no / revision / designer；
- IFC：ifcopenshell 未安装时，仅做文件存在性校验 + 头部 IPTS 文本抽取。
  完整几何解析留到阶段四。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PROJECT_RE = re.compile(r"PROJECT[：:=]?\s*([^\n\r]+)", re.IGNORECASE)
_DRAWING_NO_RE = re.compile(r"(?:DRAWING[_-]?NO|图号)[：:=]?\s*([A-Z0-9\-_/]+)", re.IGNORECASE)
_REVISION_RE = re.compile(r"REVISION[：:=]?\s*([A-Z0-9]+)", re.IGNORECASE)
_DESIGNER_RE = re.compile(r"DESIGN(?:ER)?[：:=]?\s*([^\n\r]+)", re.IGNORECASE)


@dataclass
class DrawingMetadata:
    """图纸元数据。"""

    file_path: str
    project: str | None = None
    drawing_no: str | None = None
    revision: str | None = None
    designer: str | None = None
    raw_header: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class DrawingParser:
    """图纸解析器（首版：标题栏 + IFC 头部）。"""

    def parse_file(self, path: str | Path) -> DrawingMetadata:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(str(p))
        suffix = p.suffix.lower()
        if suffix == ".ifc":
            return self._parse_ifc(p)
        return self._parse_text(p)

    def parse_text(self, text: str, *, file_path: str = "<text>") -> DrawingMetadata:
        # L11 修补：每个正则只 search 一次（原三元表达式条件与取值各调一次）。
        def _group1(pattern: re.Pattern[str]) -> str | None:
            m = pattern.search(text)
            return m.group(1).strip() if m else None

        return DrawingMetadata(
            file_path=file_path,
            project=_group1(_PROJECT_RE),
            drawing_no=_group1(_DRAWING_NO_RE),
            revision=_group1(_REVISION_RE),
            designer=_group1(_DESIGNER_RE),
            raw_header=text[:2000],
        )

    def _parse_text(self, p: Path) -> DrawingMetadata:
        text = p.read_text(encoding="utf-8", errors="ignore")
        return self.parse_text(text, file_path=str(p))

    def _parse_ifc(self, p: Path) -> DrawingMetadata:
        """IFC：抽取头部 IPTS 文本（含 FILE_DESCRIPTION / FILE_NAME 等）。"""
        try:
            with p.open("r", encoding="utf-8", errors="ignore") as f:
                head = "".join(f.readline() for _ in range(80))
        except Exception as e:
            return DrawingMetadata(
                file_path=str(p), raw_header="", metadata={"error": str(e)}
            )
        return self.parse_text(head, file_path=str(p))
