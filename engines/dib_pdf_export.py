"""
engines/dib_pdf_export.py — ported verbatim from
dib_monitor/dib_monitor/pdf_export.py (no config imports, nothing to fix).

ReportLab PDF generator for the Supplier Financial Resilience Report.
Same DEMO watermark pattern as CFIUS Screener and NCF TTX Generator.
"""
from __future__ import annotations
import io
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_RISK_COLORS = {
    "LOW": colors.HexColor("#2ecc71"),
    "MEDIUM": colors.HexColor("#f39c12"),
    "HIGH": colors.HexColor("#e74c3c"),
    "CRITICAL": colors.HexColor("#8e44ad"),
}


def _risk_color(level: str):
    return _RISK_COLORS.get(level, colors.grey)


def generate_resilience_pdf(
    supplier: dict,
    assessment: dict,
    owners: list[dict],
    demo_mode: bool = True,
) -> bytes:
    """
    Generate a Supplier Financial Resilience Report PDF.
    Returns PDF bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=f"DIB Financial Resilience Report — {supplier.get('name', 'Unknown')}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title", parent=styles["Title"], fontSize=16, spaceAfter=6
    )
    heading_style = ParagraphStyle(
        "Heading2", parent=styles["Heading2"], fontSize=12, spaceAfter=4
    )
    body_style = styles["BodyText"]
    body_style.fontSize = 9

    story = []

    # ── Header ──────────────────────────────────────────────────────────────
    story.append(Paragraph("DEFENSE INDUSTRIAL BASE", styles["Normal"]))
    story.append(Paragraph("Supplier Financial Resilience Report", title_style))
    if demo_mode:
        story.append(
            Paragraph(
                "⚠ DEMO — FOR ILLUSTRATIVE PURPOSES ONLY — NOT FOR OPERATIONAL USE",
                ParagraphStyle("Warning", parent=styles["Normal"], textColor=colors.red,
                               fontSize=9, spaceAfter=4),
            )
        )
    story.append(Spacer(1, 0.1 * inch))

    # ── Supplier overview table ──────────────────────────────────────────────
    risk_level = assessment.get("combined_risk_level", "UNKNOWN")
    overview_data = [
        ["Supplier", supplier.get("name", "N/A")],
        ["DIB Category", supplier.get("dib_category", "N/A")],
        ["Sector", supplier.get("sector", "N/A")],
        ["Assessment Date", assessment.get("assessed_at", datetime.utcnow().strftime("%Y-%m-%d"))[:10]],
        ["Combined Risk Level", risk_level],
        ["Combined Risk Score", f"{assessment.get('combined_risk_score', 'N/A')} / 100"],
    ]
    overview_table = Table(overview_data, colWidths=[2.0 * inch, 4.5 * inch])
    overview_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (1, 4), (1, 4), _risk_color(risk_level)),
        ("TEXTCOLOR", (1, 4), (1, 4), colors.white),
        ("FONTNAME", (1, 4), (1, 4), "Helvetica-Bold"),
    ]))
    story.append(overview_table)
    story.append(Spacer(1, 0.2 * inch))

    # ── Financial metrics ────────────────────────────────────────────────────
    story.append(Paragraph("Financial Metrics", heading_style))
    debt_ebitda = assessment.get("debt_to_ebitda")
    fin_data = [
        ["Metric", "Value"],
        ["Revenue (FY)", f"${assessment.get('revenue_mm', 'N/A')}M"],
        ["Total Debt", f"${assessment.get('total_debt_mm', 'N/A')}M"],
        ["Cash & Equivalents", f"${assessment.get('cash_mm', 'N/A')}M"],
        ["EBITDA", f"${assessment.get('ebitda_mm', 'N/A')}M"],
        ["Debt / EBITDA", f"{debt_ebitda:.1f}x" if debt_ebitda else "N/A"],
        ["Annual Debt Service", f"${assessment.get('debt_service_annual_mm', 'N/A')}M"],
        ["Near-Term Maturity", (
            f"${assessment.get('near_term_maturity_mm')}M due {assessment.get('near_term_maturity_date', '')}"
            if assessment.get("near_term_maturity_mm") else "None within 24 months"
        )],
        ["Going Concern Flag", "YES — SEE COVENANT NOTES" if assessment.get("going_concern_flag") else "No"],
        ["Financial Risk Score", f"{assessment.get('financial_risk_score', 'N/A')} / 100 ({assessment.get('financial_risk_level', 'N/A')})"],
    ]
    fin_table = Table(fin_data, colWidths=[2.5 * inch, 4.0 * inch])
    fin_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 1), (0, -1), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(fin_table)
    story.append(Spacer(1, 0.15 * inch))

    # ── Monte Carlo distress probabilities ──────────────────────────────────
    story.append(Paragraph("Monte Carlo Financial Distress Probabilities", heading_style))
    story.append(Paragraph(
        "Probability that EBITDA falls below annual debt-service obligation "
        "(GBM simulation, 10,000 paths). Illustrative only.",
        ParagraphStyle("Caption", parent=styles["Normal"], fontSize=8, textColor=colors.grey),
    ))
    story.append(Spacer(1, 0.05 * inch))
    mc_data = [
        ["Horizon", "P(Distress)", "Signal"],
        ["1 Year",
         f"{assessment.get('distress_prob_1yr', 0)*100:.1f}%",
         _distress_label(assessment.get("distress_prob_1yr", 0))],
        ["2 Years",
         f"{assessment.get('distress_prob_2yr', 0)*100:.1f}%",
         _distress_label(assessment.get("distress_prob_2yr", 0))],
        ["3 Years",
         f"{assessment.get('distress_prob_3yr', 0)*100:.1f}%",
         _distress_label(assessment.get("distress_prob_3yr", 0))],
    ]
    mc_table = Table(mc_data, colWidths=[1.5 * inch, 1.5 * inch, 3.5 * inch])
    mc_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
    ]))
    story.append(mc_table)
    story.append(Spacer(1, 0.15 * inch))

    # ── Covenant / going concern notes ───────────────────────────────────────
    if assessment.get("covenant_summary"):
        story.append(Paragraph("Covenant Summary", heading_style))
        story.append(Paragraph(assessment["covenant_summary"], body_style))
        story.append(Spacer(1, 0.1 * inch))

    if assessment.get("going_concern_quote"):
        story.append(Paragraph("Going Concern Language", heading_style))
        story.append(Paragraph(f'"{assessment["going_concern_quote"]}"', body_style))
        story.append(Spacer(1, 0.1 * inch))

    # ── Ownership analysis ───────────────────────────────────────────────────
    story.append(Paragraph("Institutional Ownership Analysis", heading_style))
    story.append(Paragraph(
        f"Ownership Risk Score: {assessment.get('ownership_risk_score', 'N/A')} / 100 "
        f"({assessment.get('ownership_risk_level', 'N/A')})",
        body_style,
    ))
    story.append(Spacer(1, 0.05 * inch))

    if owners:
        own_data = [["Owner", "% Held", "Country", "CFIUS Flag", "Notes"]]
        for o in owners:
            own_data.append([
                o.get("owner_name", ""),
                f"{o.get('pct_owned', 0):.1f}%",
                o.get("country") or "—",
                "⚠ YES" if o.get("cfius_flag") else "No",
                (o.get("flag_reason") or "")[:60],
            ])
        own_table = Table(own_data, colWidths=[2.0 * inch, 0.7 * inch, 0.9 * inch, 0.8 * inch, 2.1 * inch])
        own_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        # Highlight flagged owners in light red
        for i, o in enumerate(owners, start=1):
            if o.get("cfius_flag"):
                own_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fde8e8")),
                ]))
        story.append(own_table)
    else:
        story.append(Paragraph("No institutional ownership data available.", body_style))

    story.append(Spacer(1, 0.2 * inch))

    # ── Honest limitations ───────────────────────────────────────────────────
    story.append(Paragraph("Limitations", heading_style))
    limitations = [
        "Financial metrics extracted by Claude Haiku from SEC filings — verify against source filings.",
        "Monte Carlo model uses simplified GBM; it does not account for covenant triggers, "
        "asset disposals, refinancing, or macroeconomic conditions.",
        "Ownership data reflects 13F filings (institutional holders ≥$100M in AUM only) — "
        "significant ownership by smaller funds or individuals will not appear.",
        "CFIUS and ownership flags are for research purposes only, not legal advice.",
        "This tool does not constitute a professional financial opinion or valuation.",
    ]
    for lim in limitations:
        story.append(Paragraph(f"• {lim}", body_style))

    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(
        f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC  |  "
        "DoD Industrial Base Policy reference: Annual Industrial Capabilities Report to Congress",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7, textColor=colors.grey),
    ))

    doc.build(story)
    return buf.getvalue()


def _distress_label(prob: float) -> str:
    if prob >= 0.30:
        return "CRITICAL — immediate review warranted"
    if prob >= 0.15:
        return "HIGH — significant distress risk"
    if prob >= 0.05:
        return "MEDIUM — monitor closely"
    return "LOW — within normal range"
