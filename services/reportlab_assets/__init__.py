"""reportlab 资源占位（5b.1）。

设计：
- ``fonts/`` 子目录用于放置中文字体（生产环境由部署脚本注入；
  沙箱 / dev 留空时，``PDFExporter`` 自动 fallback ``Helvetica`` 并
  标记 ``warning``）。
- 字体放置规范：
  - 首选 ``NotoSansCJK-Regular.ttc`` 或 ``SourceHanSansSC-Regular.otf``；
  - 若使用 TTC 须修改 ``pdf_exporter.py:TTFont`` 改用 ``TTFont(..., subfontIndex=0)``；
  - 字体文件大小写不敏感（脚本里 ``*.TTF / *.OTF / *.ttf / *.otf`` 都搜）。
- 本包不引入任何第三方依赖；仅为目录占位 + ``__all__``。
"""

from __future__ import annotations

from pathlib import Path

# 包级常量：字体目录
FONTS_DIR: Path = Path(__file__).resolve().parent / "fonts"

__all__ = ["FONTS_DIR"]
