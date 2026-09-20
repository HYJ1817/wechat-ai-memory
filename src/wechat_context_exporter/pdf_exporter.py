from __future__ import annotations

from pathlib import Path
from typing import Iterable

from reportlab import rl_config
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

# ReportLab ASCII85-encodes embedded image streams by default, which inflates
# them by ~25% and runs through a pure-Python implementation unless its
# optional C extension (_rl_accel) is present.  Measured on a 24-page export:
# 22.7s / 11.4 MB with A85, 20.7s / 9.4 MB without.  Binary streams are valid
# PDF and read fine by pypdf, Acrobat and browsers; A85 only matters for
# 7-bit-clean transports such as mail attachments, which do not apply here.
rl_config.useA85 = 0


class PdfExporter:
    def export(self, page_paths: Iterable[str | Path], output_path: str | Path, title: str) -> Path:
        paths = [Path(path) for path in page_paths]
        if not paths:
            raise ValueError("At least one rendered page is required")
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        document = canvas.Canvas(str(output), pagesize=A4, pageCompression=1)
        document.setTitle(title)
        document.setAuthor("WeChat AI Memory")
        document.setSubject("Local WeChat memory archive for AI agents")
        page_width, page_height = A4
        for path in paths:
            document.drawImage(
                ImageReader(str(path)),
                0,
                0,
                width=page_width,
                height=page_height,
                preserveAspectRatio=False,
                mask="auto",
            )
            document.showPage()
        document.save()
        return output
