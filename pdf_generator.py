import os
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

SEVERITY_COLORS = {
    "Acceptable": colors.HexColor("#16A34A"),
    "Monitor": colors.HexColor("#D97706"),
    "Reject": colors.HexColor("#DC2626"),
}

SEVERITY_LABELS = {
    "Acceptable": "ACCEPTABLE",
    "Monitor": "MONITOR",
    "Reject": "REJECT",
}

BRAND_PRIMARY = colors.HexColor("#0B3D6B")
BRAND_ACCENT = colors.HexColor("#00A676")


def _ensure_logo_png(logo_path):
    """Return a PNG logo path usable by ReportLab (SVG is not supported)."""
    if logo_path and logo_path.endswith(".png") and os.path.exists(logo_path):
        return logo_path

    png_path = logo_path.replace(".svg", ".png") if logo_path else "logo.png"
    if os.path.exists(png_path):
        return png_path

    img = Image.new("RGB", (400, 80), color=(11, 61, 107))
    draw = ImageDraw.Draw(img)
    try:
        font_lg = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
        font_sm = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except OSError:
        font_lg = ImageFont.load_default()
        font_sm = ImageFont.load_default()

    draw.text((16, 14), "MECAWINGS", fill=(255, 255, 255), font=font_lg)
    draw.text((16, 50), "AEROSPACE MRO", fill=(0, 166, 118), font=font_sm)
    draw.rectangle([(320, 20), (380, 60)], outline=(0, 166, 118), width=2)
    draw.polygon([(350, 28), (340, 52), (360, 52)], fill=(0, 166, 118))

    os.makedirs(os.path.dirname(png_path) or ".", exist_ok=True)
    img.save(png_path, "PNG")
    return png_path


def _prepare_image(path, max_width=14 * cm, max_height=7.5 * cm):
    """Resize image for PDF while preserving aspect ratio."""
    with Image.open(path) as img:
        img = img.convert("RGB")
        w, h = img.size
        ratio = min(max_width / w, max_height / h, 1.0)
        new_w, new_h = int(w * ratio), int(h * ratio)
        if ratio < 1.0:
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            temp_path = path + "_pdf.jpg"
            img.save(temp_path, "JPEG", quality=85)
            return temp_path, new_w, new_h
        return path, w, h


def _severity_counts(photos):
    counts = {"Acceptable": 0, "Monitor": 0, "Reject": 0}
    for photo in photos:
        sev = photo.get("severity") or photo.get("classification", "Acceptable")
        if sev in counts:
            counts[sev] += 1
    return counts


def _get_severity(photo):
    return photo.get("severity") or photo.get("classification", "Acceptable")


def _get_defect(photo):
    return (photo.get("defect_description") or photo.get("comment", "")).strip()


def _get_area(photo):
    return photo.get("area", "—")


class BorescopeDocTemplate(SimpleDocTemplate):
    """Document template that registers TOC entries."""

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and hasattr(flowable, "toc_level"):
            text = flowable.getPlainText()
            self.notify("TOCEntry", (flowable.toc_level, text, self.page))


def _build_styles():
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=styles["Heading1"],
            fontSize=16,
            textColor=BRAND_PRIMARY,
            alignment=TA_CENTER,
            spaceAfter=4,
            fontName="Helvetica-Bold",
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#4B5563"),
            alignment=TA_CENTER,
            spaceAfter=12,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=styles["Heading2"],
            fontSize=11,
            textColor=BRAND_PRIMARY,
            spaceBefore=8,
            spaceAfter=6,
            fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#1F2937"),
        ),
        "small": ParagraphStyle(
            "Small",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.HexColor("#6B7280"),
        ),
        "toc_title": ParagraphStyle(
            "TOCTitle",
            parent=styles["Heading1"],
            fontSize=13,
            textColor=BRAND_PRIMARY,
            spaceAfter=10,
            fontName="Helvetica-Bold",
        ),
    }


def _toc_paragraph(text, level=0):
    p = Paragraph(text, ParagraphStyle(f"toc_{level}", fontSize=9))
    p.toc_level = level
    return p


def _header_block(logo_path, sty):
    cells = []
    resolved_logo = _ensure_logo_png(logo_path) if logo_path else None
    if resolved_logo and os.path.exists(resolved_logo):
        cells.append(RLImage(resolved_logo, width=3.5 * cm, height=1.2 * cm, kind="proportional"))
    else:
        cells.append(Paragraph('<font color="#0B3D6B" size="14"><b>MECAWINGS</b></font>', sty["body"]))

    cells.append(
        Paragraph(
            f'<font size="8" color="#6B7280">Report generated: {datetime.now().strftime("%d %b %Y %H:%M")}</font>',
            ParagraphStyle("HeaderDate", alignment=TA_RIGHT, fontSize=8),
        )
    )

    table = Table([cells], colWidths=[10 * cm, 7 * cm])
    table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, 0), 1.5, BRAND_PRIMARY),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ])
    )
    return table


def _info_table(report_data, sty):
    info_data = [
        ["Customer", report_data.get("customer", "—"), "Aircraft Type", report_data.get("aircraft", "—")],
        ["Registration", report_data.get("registration", "—"), "MSN", report_data.get("msn", "—")],
        ["Engine S/N", report_data.get("engine_sn", "—"), "Engine Position", report_data.get("engine_position", "—")],
        ["Inspection Date", report_data.get("date", "—"), "P/O Reference", report_data.get("po", "—")],
    ]
    if report_data.get("inspector"):
        info_data.append(["Inspector", report_data.get("inspector", "—"), "", ""])

    table = Table(info_data, colWidths=[3.5 * cm, 5 * cm, 3.5 * cm, 5 * cm])
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8F0F8")),
            ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#E8F0F8")),
            ("TEXTCOLOR", (0, 0), (0, -1), BRAND_PRIMARY),
            ("TEXTCOLOR", (2, 0), (2, -1), BRAND_PRIMARY),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    return table


def _severity_summary_table(counts, total, sty):
    data = [[
        Paragraph(f'<font color="#16A34A"><b>Acceptable: {counts["Acceptable"]}</b></font>', sty["body"]),
        Paragraph(f'<font color="#D97706"><b>Monitor: {counts["Monitor"]}</b></font>', sty["body"]),
        Paragraph(f'<font color="#DC2626"><b>Reject: {counts["Reject"]}</b></font>', sty["body"]),
        Paragraph(f'<b>Total Findings: {total}</b>', sty["body"]),
    ]]
    table = Table(data, colWidths=[4 * cm, 4 * cm, 4 * cm, 4.5 * cm])
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    return table


def _findings_summary_table(photos, sty):
    header = ["Photo #", "Area Inspected", "Defect Description", "Severity"]
    rows = [header]
    for idx, photo in enumerate(photos, start=1):
        severity = _get_severity(photo)
        color = SEVERITY_COLORS.get(severity, colors.grey).hexval()
        defect = _get_defect(photo) or "—"
        rows.append([
            str(idx),
            _get_area(photo),
            defect[:80] + ("…" if len(defect) > 80 else ""),
            Paragraph(f'<font color="{color}"><b>{severity.upper()}</b></font>', sty["body"]),
        ])

    table = Table(rows, colWidths=[1.5 * cm, 3.5 * cm, 8 * cm, 3.5 * cm], repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ])
    )
    return table


def _signature_block(sty):
    story = []
    story.append(Spacer(1, 0.5 * cm))
    story.append(_toc_paragraph("Signatures", level=0))
    story.append(Spacer(1, 0.3 * cm))

    cert = (
        "This borescope inspection report documents visual findings observed during the "
        "CFM56 engine inspection performed by Mecawings. Severity classifications follow "
        "standard MRO guidelines: <b>Acceptable</b> — within limits; "
        "<b>Monitor</b> — requires follow-up inspection; "
        "<b>Reject</b> — exceeds acceptable limits."
    )
    story.append(Paragraph(cert, sty["body"]))
    story.append(Spacer(1, 1 * cm))

    sig_table = Table(
        [
            ["_" * 38, "_" * 38],
            ["Inspector Signature", "Customer Signature"],
            ["", ""],
            ["_" * 38, "_" * 38],
            ["Print Name / Date", "Print Name / Date"],
        ],
        colWidths=[8.25 * cm, 8.25 * cm],
    )
    sig_table.setStyle(
        TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#374151")),
            ("TEXTCOLOR", (0, 4), (-1, 4), colors.HexColor("#6B7280")),
            ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 1), (-1, 1), 6),
            ("TOPPADDING", (0, 4), (-1, 4), 6),
            ("BOTTOMPADDING", (0, 2), (-1, 2), 12),
            ("LINEBELOW", (0, 0), (0, 0), 0.5, colors.HexColor("#CBD5E1")),
            ("LINEBELOW", (1, 0), (1, 0), 0.5, colors.HexColor("#CBD5E1")),
            ("LINEBELOW", (0, 3), (0, 3), 0.5, colors.HexColor("#CBD5E1")),
            ("LINEBELOW", (1, 3), (1, 3), 0.5, colors.HexColor("#CBD5E1")),
        ])
    )
    story.append(sig_table)

    footer = Paragraph(
        '<font size="7" color="#9CA3AF">Mecawings — CFM56 Borescope Inspection Report — Confidential</font>',
        ParagraphStyle("Footer", alignment=TA_CENTER, fontSize=7),
    )
    story.append(Spacer(1, 1 * cm))
    story.append(footer)
    return story


def generate_borescope_report(report_data, photos, output_path, logo_path=None):
    """
    Generate a professional CFM56 borescope inspection PDF report.

    report_data: customer, aircraft, registration, msn, engine_sn,
                 engine_position, date, po, inspector
    photos: path, filename, area, defect_description, severity
    """
    sty = _build_styles()
    counts = _severity_counts(photos)
    temp_files = []

    doc = BorescopeDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            "TOCLevel0",
            fontName="Helvetica",
            fontSize=10,
            leftIndent=0,
            spaceBefore=4,
            textColor=BRAND_PRIMARY,
        ),
        ParagraphStyle(
            "TOCLevel1",
            fontName="Helvetica",
            fontSize=9,
            leftIndent=16,
            spaceBefore=2,
            textColor=colors.HexColor("#374151"),
        ),
    ]

    story = []

    # Cover / title page
    story.append(_header_block(logo_path, sty))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("BORESCOPE INSPECTION REPORT", sty["title"]))
    story.append(Paragraph("CFM56 Engine — Mecawings Visual Inspection Findings", sty["subtitle"]))
    story.append(_info_table(report_data, sty))
    story.append(Spacer(1, 0.5 * cm))
    story.append(_severity_summary_table(counts, len(photos), sty))

    story.append(PageBreak())

    # Table of contents
    story.append(Paragraph("Table of Contents", sty["toc_title"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(toc)
    story.append(PageBreak())

    # Findings summary section
    story.append(_toc_paragraph("Findings Summary", level=0))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        f"Total findings documented: <b>{len(photos)}</b> — "
        f"Acceptable: <b>{counts['Acceptable']}</b>, "
        f"Monitor: <b>{counts['Monitor']}</b>, "
        f"Reject: <b>{counts['Reject']}</b>",
        sty["body"],
    ))
    story.append(Spacer(1, 0.3 * cm))
    story.append(_findings_summary_table(photos, sty))
    story.append(PageBreak())

    # Detailed photo findings
    story.append(_toc_paragraph("Detailed Photo Findings", level=0))
    story.append(Spacer(1, 0.3 * cm))

    for idx, photo in enumerate(photos, start=1):
        severity = _get_severity(photo)
        sev_color = SEVERITY_COLORS.get(severity, colors.grey)
        sev_label = SEVERITY_LABELS.get(severity, severity.upper())
        area = _get_area(photo)
        defect = _get_defect(photo) or "No defect description provided."

        story.append(_toc_paragraph(f"Photo {idx} — {area}", level=1))

        header = Table(
            [[
                Paragraph(f"<b>Photo {idx:02d}</b> — {photo.get('filename', '')}", sty["body"]),
                Paragraph(f'<font color="{sev_color.hexval()}"><b>{sev_label}</b></font>',
                          ParagraphStyle("Sev", alignment=TA_CENTER, fontSize=9)),
            ]],
            colWidths=[12 * cm, 5 * cm],
        )
        header.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (0, 0), 6),
        ]))
        story.append(header)

        meta_row = Table(
            [[
                Paragraph(f"<b>Area Inspected:</b> {area}", sty["body"]),
                Paragraph(f"<b>Severity:</b> {severity}", sty["body"]),
            ]],
            colWidths=[10 * cm, 7 * cm],
        )
        meta_row.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E8F0F8")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(meta_row)

        img_path = photo.get("path")
        if img_path and os.path.exists(img_path):
            try:
                prepared_path, img_w, img_h = _prepare_image(img_path)
                if prepared_path != img_path:
                    temp_files.append(prepared_path)
                rl_img = RLImage(prepared_path, width=img_w, height=img_h)
                img_table = Table([[rl_img]], colWidths=[17 * cm])
                img_table.setStyle(TableStyle([
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(img_table)
            except Exception:
                story.append(Paragraph("<i>Image could not be loaded</i>", sty["small"]))

        defect_box = Table(
            [[Paragraph(f"<b>Defect Description:</b> {defect}", sty["body"])]],
            colWidths=[17 * cm],
        )
        defect_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(defect_box)
        story.append(Spacer(1, 0.4 * cm))

        if idx < len(photos):
            story.append(PageBreak())

    story.append(PageBreak())
    story.extend(_signature_block(sty))

    doc.multiBuild(story)

    for temp in temp_files:
        try:
            os.remove(temp)
        except OSError:
            pass

    return output_path
