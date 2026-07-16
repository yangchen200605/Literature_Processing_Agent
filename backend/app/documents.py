"""Word / PDF 文本提取与摘要结果导出。"""

from __future__ import annotations

import io
import re
from pathlib import Path

import fitz  # PyMuPDF
from docx import Document
from docx.shared import Pt, RGBColor
from fastapi import HTTPException, UploadFile
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


async def extract_text_from_upload(file: UploadFile) -> tuple[str, str]:
    """从上传的 PDF / Word 提取纯文本，返回 (text, filename)。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件名")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="仅支持 PDF (.pdf) 或 Word (.docx) 文件",
        )
    if suffix == ".doc":
        raise HTTPException(
            status_code=400,
            detail="暂不支持旧版 .doc，请另存为 .docx 后上传",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件过大，请控制在 20MB 以内")

    try:
        if suffix == ".pdf":
            text = _extract_pdf(data)
        else:
            text = _extract_docx(data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法解析文件: {e}") from e

    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="未能从文件中提取到文本内容")

    return text, file.filename


def _extract_pdf(data: bytes) -> str:
    parts: list[str] = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            parts.append(page.get_text("text"))
    return "\n\n".join(p.strip() for p in parts if p.strip())


def _extract_docx(data: bytes) -> str:
    document = Document(io.BytesIO(data))
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                paragraphs.append("\t".join(cells))
    return "\n\n".join(paragraphs)


def export_docx(content: str) -> bytes:
    """将摘要 Markdown/纯文本导出为 Word。"""
    document = Document()
    style = document.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(12)

    title = document.add_heading("文献摘要", level=1)
    for run in title.runs:
        run.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            document.add_paragraph("")
            continue
        if stripped.startswith("### "):
            document.add_heading(_plain_md(stripped[4:].strip()), level=3)
        elif stripped.startswith("## "):
            document.add_heading(_plain_md(stripped[3:].strip()), level=2)
        elif stripped.startswith("# "):
            document.add_heading(_plain_md(stripped[2:].strip()), level=1)
        elif stripped.startswith(("- ", "* ")):
            p = document.add_paragraph(style="List Bullet")
            _apply_bold_runs(p, stripped[2:].strip())
        else:
            p = document.add_paragraph()
            _apply_bold_runs(p, stripped)

    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def _plain_md(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def _apply_bold_runs(paragraph, text: str) -> None:
    parts = re.split(r"(\*\*.+?\*\*)", text)
    for part in parts:
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part:
            paragraph.add_run(part)


def export_pdf(content: str) -> bytes:
    """将摘要导出为 PDF（支持中文）。"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "CNBody",
        parent=styles["Normal"],
        fontName="STSong-Light",
        fontSize=11,
        leading=18,
    )
    h1 = ParagraphStyle(
        "CNH1",
        parent=styles["Heading1"],
        fontName="STSong-Light",
        fontSize=16,
        leading=22,
        spaceAfter=10,
    )
    h2 = ParagraphStyle(
        "CNH2",
        parent=styles["Heading2"],
        fontName="STSong-Light",
        fontSize=13,
        leading=20,
        spaceAfter=8,
    )

    story = [Paragraph("文献摘要", h1), Spacer(1, 8)]
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 6))
            continue
        safe = (
            stripped.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)

        if stripped.startswith("### "):
            story.append(Paragraph(safe[4:].strip(), h2))
        elif stripped.startswith("## "):
            story.append(Paragraph(safe[3:].strip(), h2))
        elif stripped.startswith("# "):
            story.append(Paragraph(safe[2:].strip(), h1))
        elif stripped.startswith(("- ", "* ")):
            story.append(Paragraph(f"• {safe[2:].strip()}", body))
        else:
            story.append(Paragraph(safe, body))
        story.append(Spacer(1, 4))

    doc.build(story)
    return buf.getvalue()
