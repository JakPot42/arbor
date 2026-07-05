"""engines/cfius_pdf_export.py — ported verbatim from
cfius_screener/pdf_export.py (import paths only).

ReportLab PDF export for CFIUS screening memoranda. Every page carries a
diagonal DEMO watermark. The document contains:
- Header: deal parties, date, determination
- The Claude-drafted narrative
- The deterministic findings trail with citations
"""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from engines.cfius_screening_service import findings_of
from models.cfius import Screening

_OUTCOME_LABELS = {
    "NOT_COVERED": "Not a covered transaction",
    "COVERED_VOLUNTARY": "Covered — voluntary filing available",
    "MANDATORY_DECLARATION": "Mandatory declaration required",
}


def _watermark(canvas_obj, _doc):
    """Diagonal DEMO watermark on every page."""
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica-Bold", 80)
    canvas_obj.setFillGray(0.82)
    canvas_obj.translate(LETTER[0] / 2, LETTER[1] / 2)
    canvas_obj.rotate(45)
    canvas_obj.drawCentredString(0, 0, "DEMO")
    canvas_obj.restoreState()


def render_memo_pdf(row: Screening, memo_text: str) -> bytes:
    """Return PDF bytes for the screening memorandum."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
        title=f"CFIUS Screening Memorandum — {row.us_business_name}",
        author="CFIUS Screener (AI-Assisted)",
    )

    ss = getSampleStyleSheet()

    title_s = ParagraphStyle(
        "CTitle", parent=ss["Heading1"],
        alignment=TA_CENTER, fontSize=15, spaceAfter=4,
    )
    subtitle_s = ParagraphStyle(
        "CSubtitle", parent=ss["Normal"],
        alignment=TA_CENTER, fontSize=9,
        textColor=colors.HexColor("#475569"), spaceAfter=16,
    )
    section_s = ParagraphStyle(
        "CSection", parent=ss["Heading2"],
        fontSize=10, spaceBefore=14, spaceAfter=6,
        textColor=colors.HexColor("#1d3a5f"),
    )
    body_s = ParagraphStyle(
        "CBody", parent=ss["Normal"],
        alignment=TA_JUSTIFY, fontSize=10, leading=15, spaceAfter=10,
    )
    finding_q_s = ParagraphStyle(
        "CFindQ", parent=ss["Normal"],
        fontSize=9, fontName="Helvetica-Bold", spaceAfter=2,
    )
    finding_a_s = ParagraphStyle(
        "CFindA", parent=ss["Normal"],
        fontSize=9, leftIndent=14, spaceAfter=2,
    )
    citation_s = ParagraphStyle(
        "CCite", parent=ss["Normal"],
        fontSize=8, textColor=colors.HexColor("#475569"),
        leftIndent=14, spaceAfter=10,
    )

    created = row.created_at.strftime("%B %d, %Y") if row.created_at else ""
    outcome_label = _OUTCOME_LABELS.get(row.outcome, row.outcome)

    story = [
        Paragraph("CFIUS SCREENING MEMORANDUM", title_s),
        Paragraph(
            f"{row.acquirer_name} &nbsp;/&nbsp; {row.us_business_name}"
            + (f" &nbsp;·&nbsp; {created}" if created else ""),
            subtitle_s,
        ),
        Paragraph(f"<b>Determination:</b> {outcome_label}", body_s),
        HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#d7dee8")),
        Spacer(1, 10),
        Paragraph("SCREENING NARRATIVE", section_s),
    ]

    for para in memo_text.split("\n\n"):
        para = para.strip()
        if para:
            story.append(Paragraph(para, body_s))

    story += [
        Spacer(1, 6),
        HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#d7dee8")),
        Paragraph("DETERMINISTIC FINDINGS TRAIL", section_s),
        Paragraph(
            "The determinations below are produced by deterministic code — "
            "same facts, same answer every time. No AI is involved in the "
            "legal tests.",
            body_s,
        ),
    ]

    for f in findings_of(row):
        story.append(Paragraph(f["question"], finding_q_s))
        story.append(Paragraph(f["answer"], finding_a_s))
        story.append(Paragraph(f["determination"], finding_a_s))
        story.append(Paragraph(f["citation"], citation_s))

    doc.build(story, onFirstPage=_watermark, onLaterPages=_watermark)
    return buf.getvalue()
