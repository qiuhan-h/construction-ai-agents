"""fonts 占位说明（5b.1）。

部署时由 CI / 部署脚本把中文字体拷进此目录：

  cp /path/to/SourceHanSansSC-Regular.otf services/reportlab_assets/fonts/

PDFExporter 启动时会自动 glob ``fonts/*.ttf / *.otf`` 第一个匹配。
"""
