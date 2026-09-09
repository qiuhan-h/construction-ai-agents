"""规范条文解析（spec_parser）。

输入：国标/行标的纯文本（Markdown / TXT）。
输出：按章节切分的 SpecChunk 列表。

切分规则：
- 一级章节以 `# 1` / `## 1.1` / `## 第N章` 等开头；
- 单 chunk 不超过 max_chars（默认 1000 字）；
- 保留章节标题作为元数据。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# 章节起始模式（兼容 Markdown 标题、GB "第 N 章/条"）
_SECTION_PATTERN = re.compile(
    r"^(?:#{1,3}\s*[\d.]+|第[\d一二三四五六七八九十百]+(?:章|条|节))\s*",
    re.UNICODE,
)


@dataclass
class SpecChunk:
    """一条规范片段。"""

    chunk_id: str
    code: str
    version: str
    clause: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class SpecParser:
    """规范条文解析器。"""

    def parse(
        self,
        text: str,
        *,
        code: str,
        version: str,
        max_chars: int = 1000,
    ) -> list[SpecChunk]:
        """按章节切分；返回 SpecChunk 列表。"""
        if not text or not text.strip():
            return []
        sections = _split_sections(text)
        chunks: list[SpecChunk] = []
        idx = 0
        for clause, body in sections:
            if not body.strip():
                continue
            for piece in _split_long(body, max_chars):
                idx += 1
                chunks.append(
                    SpecChunk(
                        chunk_id=f"{code}-{version}-{idx:04d}",
                        code=code,
                        version=version,
                        clause=clause,
                        text=piece,
                        metadata={"idx": idx, "length": len(piece)},
                    )
                )
        return chunks


def _split_sections(text: str) -> list[tuple[str, str]]:
    """切出 (章节标题, 正文) 列表。"""
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_title = ""
    current_body: list[str] = []
    for ln in lines:
        if _SECTION_PATTERN.match(ln.strip()):
            if current_title or current_body:
                sections.append((current_title, current_body))
            current_title = ln.strip().lstrip("#").strip()
            current_body = []
        else:
            current_body.append(ln)
    if current_title or current_body:
        sections.append((current_title, current_body))
    # 兜底：未识别章节
    if not sections:
        return [("", text)]
    return [(title, "\n".join(body).strip()) for title, body in sections]


def _split_long(text: str, max_chars: int) -> list[str]:
    """超长正文按 max_chars 硬切。"""
    if len(text) <= max_chars:
        return [text]
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]
