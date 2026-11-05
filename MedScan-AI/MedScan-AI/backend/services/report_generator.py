"""PDF medical report (ReportLab)."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.config import settings
from backend.models.database_models import AnalysisResult

NAVY = colors.HexColor("#0B1F3A")
BLUE = colors.HexColor("#2F7DD1")
LIGHT = colors.HexColor("#EAF3FC")

DISCLAIMER = ("This AI-generated result is intended for research and educational assistance only. "
              "It is not a definitive medical diagnosis and must be reviewed by a qualified medical professional.")

SUMMARY_TEXT = {
    "findings_flagged": "One or more labels scored above their published operating threshold (see table).",
    "no_findings_flagged": "No label scored above its published operating threshold.",
}


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("H", parent=s["Heading2"], textColor=NAVY, spaceBefore=10, spaceAfter=4, fontSize=12))
    s.add(ParagraphStyle("Small", parent=s["BodyText"], fontSize=8.5, leading=11, textColor=colors.HexColor("#44546A")))
    s.add(ParagraphStyle("Box", parent=s["BodyText"], fontSize=9.5, leading=13, textColor=NAVY))
    return s


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#6B7A90"))
    canvas.drawString(18 * mm, 10 * mm, "MedScan AI  |  Research and educational use only  |  Not a diagnosis")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_report(analysis: AnalysisResult, dest: Path) -> Path:
    s = _styles()
    img = analysis.image
    mi = analysis.model_info or {}
    doc = SimpleDocTemplate(str(dest), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm, title="MedScan AI Report", author="MedScan AI")
    el = []

    head = Table([[Paragraph("<font color='white' size=18><b>MedScan AI</b></font>", s["Normal"]),
                   Paragraph("<font color='#BFD9F5' size=10>AI-assisted imaging analysis report</font>", s["Normal"])]],
                 colWidths=[70 * mm, 104 * mm])
    head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 10),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 10), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    el += [head, Spacer(1, 6)]

    el.append(Paragraph("Examination information", s["H"]))
    rows = [
        ["Analysis ID", analysis.id],
        ["Image reference", f"{img.id}  (SHA-256 {img.sha256[:16]}...)"],
        ["Imaging task", {"chest_xray": "Chest X-ray"}.get(analysis.category, analysis.category.replace("_", " ").title())],
        ["Image size", f"{img.width} x {img.height} px  ({img.source_format})"],
        ["Analysis date (UTC)", analysis.completed_at.strftime("%Y-%m-%d %H:%M:%S") if analysis.completed_at else "n/a"],
        ["Model", mi.get("display_name", analysis.model_id)],
        ["Model source", mi.get("source", "")],
        ["Result type", "Real model inference (no demo or placeholder data)"],
    ]
    t = Table([[Paragraph(f"<b>{a}</b>", s["Small"]), Paragraph(str(b), s["Small"])] for a, b in rows],
              colWidths=[38 * mm, 136 * mm])
    t.setStyle(TableStyle([("ROWBACKGROUNDS", (0, 0), (-1, -1), [LIGHT, colors.white]),
                           ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CFDCEB")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el.append(t)

    el.append(Paragraph("Images", s["H"]))
    cells, caps = [], []
    orig = settings.upload_dir / f"{img.id}.png"
    if orig.exists():
        cells.append(Image(str(orig), width=78 * mm, height=78 * mm, kind="proportional")); caps.append("Uploaded image")
    if analysis.heatmap_path and Path(analysis.heatmap_path).exists():
        cells.append(Image(analysis.heatmap_path, width=78 * mm, height=78 * mm, kind="proportional"))
        caps.append(f"Grad-CAM for '{analysis.heatmap_label}' (centre-cropped model input)")
    if cells:
        tt = Table([cells, [Paragraph(c, s["Small"]) for c in caps]], colWidths=[87 * mm] * len(cells))
        tt.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        el.append(tt)

    el.append(Paragraph("AI analysis findings", s["H"]))
    el.append(Paragraph(SUMMARY_TEXT.get(analysis.summary or "", ""), s["Box"]))
    el.append(Spacer(1, 4))
    data = [["Finding", "Model score", "Operating threshold", "Above threshold"]]
    for f in analysis.findings or []:
        data.append([f["label"].replace("_", " "), f"{f['score']:.3f}", f"{f['threshold']:.3f}", "Yes" if f["flagged"] else "No"])
    ft = Table(data, colWidths=[62 * mm, 30 * mm, 42 * mm, 40 * mm], repeatRows=1)
    ft.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CFDCEB"))]))
    el.append(ft)
    el.append(Spacer(1, 4))
    el.append(Paragraph("<b>Confidence information.</b> Scores are raw outputs of a multi-label neural network on a 0-1 scale. "
                        "They are <b>not</b> calibrated probabilities that a patient has a condition. The operating threshold is the "
                        "value published with the model weights; a score above it means the label was flagged, nothing more. "
                        "The model has no 'normal' class.", s["Small"]))

    lim = [Paragraph("Limitations and medical disclaimer", s["H"])]
    lim += [Paragraph("&bull; " + x, s["Small"]) for x in (mi.get("limitations") or [])]
    lim += [Paragraph(w, s["Small"]) for w in (analysis.warnings or [])]
    lim += [Spacer(1, 6), Table([[Paragraph(f"<b>{DISCLAIMER}</b>", s["Box"])]], colWidths=[174 * mm],
                                style=TableStyle([("BOX", (0, 0), (-1, -1), 1, BLUE), ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                                                  ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 8),
                                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))]
    el.append(KeepTogether(lim))
    doc.build(el, onFirstPage=_footer, onLaterPages=_footer)
    return dest
