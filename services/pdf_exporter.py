"""报告 PDF 导出（5b.1）。

设计：
- 双路径：
  - **reportlab** 真路径：仅当 reportlab + 中文字体都齐备时启用；
  - **Markdown 兜底**：缺包时导出 ``.md`` 字节流，HTTP 路由层
    （``api/routers/reports_router.py``）根据 ``?format=`` 自动选
    ``application/pdf`` 或 ``text/markdown`` Content-Type。
- ``PDFExporter`` 是无状态服务，可并发；不依赖 ORM / DB。
- 字体策略：默认从 ``services/reportlab_assets/fonts/`` 找 ``*.ttf``；
  沙箱 / dev 没放字体时走``Helvetica``（无中文支持，但保证 PDF 不抛错）。
- ``export(report_id, title, markdown, **meta)`` → ``bytes`` + 后缀。

为什么不用 weasyprint：
- weasyprint 强依赖 cairo / pango / glib，Docker 镜像层 +150MB；
- reportlab 纯 Python，wheels 易装，国产化 Linux 兼容性更好；
- 业务对 PDF 排版无强版式需求 → platypus 简单流式即可。
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)


ExportFormat = Literal["pdf", "md"]

_ASSETS_DIR = Path(__file__).resolve().parent / "reportlab_assets"
_FONTS_DIR = _ASSETS_DIR / "fonts"


def _reportlab_available() -> bool:
    try:
        import reportlab  # type: ignore  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _find_cjk_font() -> str | None:
    """从 reportlab_assets/fonts/ 找 .ttf / .otf；找不到返回 None。"""
    if not _FONTS_DIR.exists():
        return None
    for ext in ("*.ttf", "*.otf", "*.TTF", "*.OTF"):
        for p in _FONTS_DIR.glob(ext):
            return str(p)
    return None


# =====================================================
# 导出结果
# =====================================================
@dataclass
class ExportResult:
    """PDF / Markdown 导出结果。"""

    bytes: bytes
    format: ExportFormat
    filename: str
    report_id: str
    backend: str
    warning: str | None = None


# =====================================================
# 导出器
# =====================================================
class PDFExporter:
    """报告导出器。"""

    backend_name: str = "reportlab"

    def __init__(self, *, font_path: str | None = None) -> None:
        self._font_path = font_path
        self._registered_font: str | None = None
        self._reportlab_ok: bool = _reportlab_available()
        if self._reportlab_ok and font_path is None:
            self._font_path = _find_cjk_font()
        if self._reportlab_ok and self._font_path:
            self._register_font()

    def _register_font(self) -> None:
        if not self._reportlab_ok or not self._font_path:
            return
        try:
            from reportlab.pdfbase import pdfmetrics  # type: ignore
            from reportlab.pdfbase.ttfonts import TTFont  # type: ignore

            name = "CAAICJK"
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, self._font_path))
            self._registered_font = name
            logger.info("PDFExporter 注册中文字体: %s", self._font_path)
        except Exception as e:  # noqa: BLE001
            logger.warning("PDFExporter 字体注册失败：%s", e)
            self._registered_font = None

    @property
    def can_export_pdf(self) -> bool:
        return self._reportlab_ok

    async def export(
        self,
        report_id: str,
        title: str,
        markdown: str,
        *,
        meta: dict[str, Any] | None = None,
        force_format: ExportFormat | None = None,
    ) -> ExportResult:
        """导出报告。

        参数：
        - ``report_id``     — 报告 ID（用于文件名）
        - ``title``         — 报告标题
        - ``markdown``      — 报告 Markdown 原文
        - ``meta``          — 任意附加元信息（创建人 / 时间 / 项目等）
        - ``force_format``  — ``"pdf"`` 强制 PDF 路径（缺包时抛错）；
                              ``"md"`` 强制 Markdown；
                              ``None`` 按能力自动选。
        """
        if force_format == "pdf" and not self.can_export_pdf:
            raise RuntimeError("reportlab 不可用，无法强制导出 PDF")
        meta = meta or {}
        if force_format == "md" or not self.can_export_pdf:
            return await asyncio.to_thread(
                self._export_markdown, report_id, title, markdown, meta
            )
        try:
            return await asyncio.to_thread(
                self._export_pdf, report_id, title, markdown, meta
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "PDF 导出失败（%s: %s）→ fallback Markdown",
                type(e).__name__, e,
            )
            return await asyncio.to_thread(
                self._export_markdown, report_id, title, markdown, meta,
                warning=f"PDF 失败 fallback Markdown: {e}",
            )

    # =====================================================
    # PDF 路径（reportlab platypus）
    # =====================================================
    def _export_pdf(
        self,
        report_id: str,
        title: str,
        markdown: str,
        meta: dict[str, Any],
    ) -> ExportResult:
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
        from reportlab.lib.units import cm  # type: ignore
        from reportlab.pdfbase import pdfmetrics  # type: ignore
        from reportlab.platypus import (  # type: ignore
            Paragraph,
            SimpleDocTemplate,
            Spacer,
        )

        # 字体
        font_name = self._registered_font or "Helvetica"
        cjk_supported = self._registered_font is not None

        styles = getSampleStyleSheet()
        body = ParagraphStyle(
            "CAAIBody",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=10.5,
            leading=15,
        )
        h1 = ParagraphStyle(
            "CAAIH1",
            parent=styles["Heading1"],
            fontName=font_name,
            fontSize=18,
            leading=22,
            spaceAfter=12,
        )
        h2 = ParagraphStyle(
            "CAAIH2",
            parent=styles["Heading2"],
            fontName=font_name,
            fontSize=14,
            leading=18,
            spaceAfter=8,
        )
        code = ParagraphStyle(
            "CAAICode",
            parent=styles["Code"],
            fontName=font_name,
            fontSize=9,
            leading=12,
        )

        buf = io.BytesIO()
        try:
            doc = SimpleDocTemplate(
                buf,
                pagesize=A4,
                leftMargin=2 * cm,
                rightMargin=2 * cm,
                topMargin=2 * cm,
                bottomMargin=2 * cm,
                title=title,
                author=str(meta.get("author", "caai")),
            )

            story: list[Any] = []
            story.append(Paragraph(_esc(title), h1))
            if meta:
                bits = [f"{k}={v}" for k, v in meta.items()]
                story.append(Paragraph(_esc(" · ".join(bits)), body))
                story.append(Spacer(1, 0.4 * cm))

            for block in _md_to_blocks(markdown):
                if block["kind"] == "h1":
                    story.append(Paragraph(_esc(block["text"]), h1))
                elif block["kind"] == "h2":
                    story.append(Paragraph(_esc(block["text"]), h2))
                elif block["kind"] == "h3":
                    story.append(Paragraph(_esc(block["text"]), h2))
                elif block["kind"] == "code":
                    story.append(Paragraph(_esc(block["text"]), code))
                elif block["kind"] == "li":
                    story.append(Paragraph(_esc("• " + block["text"]), body))
                elif block["kind"] == "blank":
                    story.append(Spacer(1, 0.3 * cm))
                else:
                    story.append(Paragraph(_esc(block["text"]), body))

            doc.build(story)
            out = buf.getvalue()
        finally:
            # 显式释放 BytesIO 缓冲，避免并发导出内存堆积
            buf.close()
        warn = None
        if not cjk_supported:
            warn = "reportlab 中文字体未注册（缺少 .ttf / .otf），中文显示为方块"
        return ExportResult(
            bytes=out,
            format="pdf",
            filename=f"{report_id}.pdf",
            report_id=report_id,
            backend=self.backend_name,
            warning=warn,
        )

    # =====================================================
    # Markdown 兜底
    # =====================================================
    def _export_markdown(
        self,
        report_id: str,
        title: str,
        markdown: str,
        meta: dict[str, Any],
        warning: str | None = None,
    ) -> ExportResult:
        if warning is None and not self.can_export_pdf:
            warning = "reportlab 未安装，回退为 Markdown 输出"
        lines: list[str] = [f"# {title}", ""]
        if meta:
            lines.append("---")
            for k, v in meta.items():
                lines.append(f"- **{k}**: {v}")
            lines.append("")
        lines.append(markdown)
        if warning:
            lines.extend(["", "---", f"> ⚠️ {warning}"])
        text = "\n".join(lines).encode("utf-8")
        return ExportResult(
            bytes=text,
            format="md",
            filename=f"{report_id}.md",
            report_id=report_id,
            backend="markdown",
            warning=warning,
        )


# =====================================================
# 内部：Markdown → 块
# =====================================================
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^```")


def _esc(text: str) -> str:
    """reportlab Paragraph XML 转义。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _md_to_blocks(md: str) -> list[dict[str, str]]:
    """极简 Markdown → block 列表（够报告导出用，不覆盖完整 GFM）。"""
    blocks: list[dict[str, str]] = []
    if not md:
        return blocks
    in_code = False
    code_buf: list[str] = []
    for raw in md.splitlines():
        line = raw.rstrip()
        if in_code:
            if _FENCE_RE.match(line):
                blocks.append({"kind": "code", "text": "\n".join(code_buf)})
                code_buf = []
                in_code = False
            else:
                code_buf.append(line)
            continue
        if _FENCE_RE.match(line):
            in_code = True
            continue
        if not line.strip():
            blocks.append({"kind": "blank", "text": ""})
            continue
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            kind = {1: "h1", 2: "h2", 3: "h3"}.get(level, "h3")
            blocks.append({"kind": kind, "text": m.group(2).strip()})
            continue
        if line.lstrip().startswith(("- ", "* ", "1. ", "2. ")):
            text = line.lstrip()
            for prefix in ("- ", "* "):
                if text.startswith(prefix):
                    text = text[len(prefix):]
                    break
            else:
                if len(text) > 3 and text[0].isdigit() and text[1] == ".":
                    text = text[2:].lstrip()
            blocks.append({"kind": "li", "text": text})
            continue
        blocks.append({"kind": "p", "text": line})
    if in_code and code_buf:
        blocks.append({"kind": "code", "text": "\n".join(code_buf)})
    return blocks
