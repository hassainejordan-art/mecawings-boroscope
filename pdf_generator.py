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
from constants import CERTIFICATION_TEXT, REPORT_SUBTITLE, REPORT_TITLE

SEVERITY_COLORS = {
    "Acceptable": colors.HexColor("#16A34A"),  # Green
    "Monitor": colors.HexColor("#EA580C"),     # Orange
    "Reject": colors.HexColor("#DC2626"),       # Red
}

SEVERITY_LABELS = {
    "Acceptable": "ACCEPTABLE",
    "Monitor": "MONITOR",
    "Reject": "REJECT",
}

BRAND_PRIMARY = colors.HexColor("#0B3D6B")
BRAND_ACCENT = colors.HexColor("#00A676")


def _resolve_logo(logo_path):
    """Return logo path for PDF or None if missing (placeholder used instead)."""
    if logo_path and os.path.exists(logo_path):
        return logo_path
    return None


def _logo_flowable(logo_path, sty, width=3.5 * cm, height=1.2 * cm):
    """Build logo image or placeholder for PDF header."""
    resolved = _resolve_logo(logo_path)
    if resolved:
        try:
            return RLImage(resolved, width=width, height=height, kind="proportional")
        except Exception:
            pass

    placeholder = Table(
        [[Paragraph('<font color="#0B3D6B" size="9"><b>MECAWINGS LOGO</b></font>', sty["body"])]],
        colWidths=[width],
        rowHeights=[height * 0.7],
    )
    placeholder.setStyle(
        TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
    )
    note = Paragraph(
        '<font size="6" color="#9CA3AF">Place logo at static/logo/mecawings_logo.png</font>',
        ParagraphStyle("LogoNote", alignment=TA_CENTER, fontSize=6),
    )
    return Table([[placeholder], [note]], colWidths=[width])


def _prepare_image(path, max_width=16.5 * cm, max_height=18 * cm):
    """Resize image for PDF — large display for one-page-per-photo layout."""
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


def _get_classification(photo):
    return photo.get("classification") or photo.get("severity", "Acceptable")


def _get_severity(photo):
    return _get_classification(photo)


def _get_comment(photo):
    return (photo.get("comment") or photo.get("defect_description", "")).strip()


def _get_defect(photo):
    return _get_comment(photo)


def _get_defect_category(photo):
    return photo.get("defect_category", "—")


def _get_area(photo):
    return photo.get("area", "—")


def _severity_counts(photos):
    counts = {"Acceptable": 0, "Monitor": 0, "Reject": 0}
    for photo in photos:
        cls = _get_classification(photo)
        if cls in counts:
            counts[cls] += 1
    return counts


class BorescopeDocTemplate(SimpleDocTemplate):
    """Document template that registers TOC entries and draws page footers."""

    def __init__(self, *args, report_number=None, **kwargs):
        self.report_number = report_number
        super().__init__(*args, **kwargs)

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and hasattr(flowable, "toc_level"):
            text = flowable.getPlainText()
            self.notify("TOCEntry", (flowable.toc_level, text, self.page))


def _draw_page_footer(canvas, doc, report_number=None):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#9CA3AF"))
    left = doc.leftMargin
    right = doc.pagesize[0] - doc.rightMargin
    y = 0.9 * cm
    if report_number:
        canvas.drawString(left, y, f"Report No. {report_number}")
    canvas.drawRightString(right, y, f"Page {doc.page}")
    canvas.restoreState()


def _page_callbacks(report_number):
    def on_page(canvas, doc):
        _draw_page_footer(canvas, doc, report_number)

    return on_page, on_page


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


def _header_block(logo_path, sty, report_number=None):
    cells = [_logo_flowable(logo_path, sty)]

    header_lines = []
    if report_number:
        header_lines.append(
            f'<font size="10" color="#0B3D6B"><b>Report No. {report_number}</b></font>'
        )
    header_lines.append(
        f'<font size="8" color="#6B7280">Generated: {datetime.now().strftime("%d %b %Y %H:%M")}</font>'
    )
    cells.append(
        Paragraph("<br/>".join(header_lines), ParagraphStyle("HeaderDate", alignment=TA_RIGHT, fontSize=8))
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
    inspected = report_data.get("inspected_areas") or []
    inspected_text = ", ".join(inspected) if inspected else "—"
    inspected_cell = Paragraph(
        inspected_text,
        ParagraphStyle("InfoInspected", fontSize=8, leading=10),
    )

    info_data = [
        ["Report Number", report_data.get("report_number", "—"), "Customer", report_data.get("customer", "—")],
        ["Aircraft Type", report_data.get("aircraft", "—"), "Engine Type", report_data.get("engine_type", "—")],
        ["Registration", report_data.get("registration", "—"), "MSN", report_data.get("msn", "—")],
        ["Engine S/N", report_data.get("engine_sn", "—"), "Engine Position", report_data.get("engine_position", "—")],
        ["Inspection Date", report_data.get("date", "—"), "P/O Reference", report_data.get("po", "—")],
        ["Inspector", report_data.get("inspector", "—"), "Inspected Areas", inspected_cell],
    ]

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


def _summary_page(counts, total, sty):
    """Dedicated inspection summary page."""
    story = []
    story.append(_toc_paragraph("Inspection Summary", level=0))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(
        "Overview of all borescope findings documented in this report.",
        sty["body"],
    ))
    story.append(Spacer(1, 0.5 * cm))

    summary_data = [[
        Paragraph('<font size="11"><b>Total Photos</b></font>', sty["body"]),
        Paragraph('<font size="11" color="#16A34A"><b>Acceptable</b></font>', sty["body"]),
        Paragraph('<font size="11" color="#EA580C"><b>Monitor</b></font>', sty["body"]),
        Paragraph('<font size="11" color="#DC2626"><b>Reject</b></font>', sty["body"]),
    ], [
        Paragraph(f'<font size="20"><b>{total}</b></font>', sty["body"]),
        Paragraph(f'<font size="20" color="#16A34A"><b>{counts["Acceptable"]}</b></font>', sty["body"]),
        Paragraph(f'<font size="20" color="#EA580C"><b>{counts["Monitor"]}</b></font>', sty["body"]),
        Paragraph(f'<font size="20" color="#DC2626"><b>{counts["Reject"]}</b></font>', sty["body"]),
    ]]
    summary_table = Table(summary_data, colWidths=[4.25 * cm, 4.25 * cm, 4.25 * cm, 4.25 * cm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F0F8")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.6 * cm))

    legend = (
        "<b>Classification legend:</b> "
        '<font color="#16A34A">Green = Acceptable</font> — within limits; '
        '<font color="#EA580C">Orange = Monitor</font> — requires follow-up; '
        '<font color="#DC2626">Red = Reject</font> — exceeds acceptable limits.'
    )
    story.append(Paragraph(legend, sty["body"]))
    return story


def _findings_summary_table(photos, sty):
    header = ["#", "Area", "Defect Category", "Comment", "Classification"]
    rows = [header]
    for idx, photo in enumerate(photos, start=1):
        classification = _get_classification(photo)
        color = SEVERITY_COLORS.get(classification, colors.grey).hexval()
        comment = _get_comment(photo) or "—"
        rows.append([
            str(idx),
            _get_area(photo),
            _get_defect_category(photo),
            comment[:60] + ("…" if len(comment) > 60 else ""),
            Paragraph(f'<font color="{color}"><b>{classification.upper()}</b></font>', sty["body"]),
        ])

    table = Table(rows, colWidths=[1 * cm, 3 * cm, 3.5 * cm, 6 * cm, 3 * cm], repeatRows=1)
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


def _signature_flowable(signature_path):
    line_style = ParagraphStyle("SigLine", fontSize=9, textColor=colors.HexColor("#1F2937"))
    if signature_path and os.path.exists(signature_path):
        try:
            return RLImage(signature_path, width=7 * cm, height=2.5 * cm, kind="proportional")
        except Exception:
            pass
    return Paragraph("_" * 52, line_style)


def _signature_block(sty, signature_path=None, inspector_name=None, report_date=None):
    story = []
    story.append(Spacer(1, 0.5 * cm))
    story.append(_toc_paragraph("Certification", level=0))
    story.append(Spacer(1, 0.3 * cm))

    cert_box = Table(
        [[Paragraph(CERTIFICATION_TEXT, sty["body"])]],
        colWidths=[17 * cm],
    )
    cert_box.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 0.75, BRAND_PRIMARY),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ])
    )
    story.append(cert_box)
    story.append(Spacer(1, 0.6 * cm))

    signature_cell = _signature_flowable(signature_path)
    cert_details = Table(
        [
            [
                Paragraph("<b>Inspector Name</b>", sty["body"]),
                Paragraph(inspector_name or "—", sty["body"]),
            ],
            [
                Paragraph("<b>Signature</b>", sty["body"]),
                signature_cell,
            ],
            [
                Paragraph("<b>Date</b>", sty["body"]),
                Paragraph(report_date or "—", sty["body"]),
            ],
        ],
        colWidths=[4.5 * cm, 12.5 * cm],
    )
    cert_details.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8F0F8")),
            ("TEXTCOLOR", (0, 0), (0, -1), BRAND_PRIMARY),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 1), (1, 1), "LEFT"),
        ])
    )
    story.append(cert_details)

    footer = Paragraph(
        '<font size="7" color="#9CA3AF">Mecawings — Aircraft Engine Borescope Inspection Report — Confidential</font>',
        ParagraphStyle("Footer", alignment=TA_CENTER, fontSize=7),
    )
    story.append(Spacer(1, 1 * cm))
    story.append(footer)
    return story


def generate_borescope_report(report_data, photos, output_path, logo_path=None, signature_path=None):
    """
    Generate a professional aircraft engine borescope inspection PDF report.

    report_data: report_number, customer, aircraft, engine_type, registration, msn,
                 engine_sn, engine_position, inspected_areas, date, po, inspector
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
        bottomMargin=2 * cm,
        report_number=report_data.get("report_number"),
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
    story.append(_header_block(logo_path, sty, report_data.get("report_number")))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(REPORT_TITLE.upper(), sty["title"]))
    story.append(Paragraph(REPORT_SUBTITLE, sty["subtitle"]))
    story.append(_info_table(report_data, sty))
    story.append(PageBreak())

    # Table of contents
    story.append(Paragraph("Table of Contents", sty["toc_title"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(toc)
    story.append(PageBreak())

    # Dedicated summary page
    story.extend(_summary_page(counts, len(photos), sty))
    story.append(Spacer(1, 0.4 * cm))
    story.append(_findings_summary_table(photos, sty))
    story.append(PageBreak())

    # Detailed photo findings — one page per photo
    story.append(_toc_paragraph("Detailed Photo Findings", level=0))

    for idx, photo in enumerate(photos, start=1):
        if idx > 1:
            story.append(PageBreak())

        classification = _get_classification(photo)
        cls_color = SEVERITY_COLORS.get(classification, colors.grey)
        cls_label = SEVERITY_LABELS.get(classification, classification.upper())
        area = _get_area(photo)
        category = _get_defect_category(photo)
        comment = _get_comment(photo) or "No comment provided."

        story.append(_toc_paragraph(f"Photo {idx} — {area}", level=1))
        story.append(Spacer(1, 0.2 * cm))

        # Classification banner with color
        banner = Table(
            [[Paragraph(
                f'<font color="white"><b>Photo {idx:02d} — {cls_label}</b></font>',
                ParagraphStyle("Banner", alignment=TA_CENTER, fontSize=11, fontName="Helvetica-Bold"),
            )]],
            colWidths=[17 * cm],
        )
        banner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), cls_color),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(banner)

        meta_row = Table(
            [[
                Paragraph(f"<b>Area:</b> {area}", sty["body"]),
                Paragraph(f"<b>Defect Category:</b> {category}", sty["body"]),
            ]],
            colWidths=[8.5 * cm, 8.5 * cm],
        )
        meta_row.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E8F0F8")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(meta_row)
        story.append(Spacer(1, 0.25 * cm))

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
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(img_table)
            except Exception:
                story.append(Paragraph("<i>Image could not be loaded</i>", sty["small"]))
        else:
            story.append(Paragraph("<i>Image not available</i>", sty["small"]))

        story.append(Spacer(1, 0.3 * cm))
        comment_box = Table(
            [[Paragraph(f"<b>Comment:</b> {comment}", sty["body"])]],
            colWidths=[17 * cm],
        )
        comment_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(comment_box)

    story.append(PageBreak())
    story.extend(_signature_block(
        sty,
        signature_path=signature_path,
        inspector_name=report_data.get("inspector"),
        report_date=report_data.get("date"),
    ))

    on_first, on_later = _page_callbacks(report_data.get("report_number"))
    doc.multiBuild(story, onFirstPage=on_first, onLaterPages=on_later)

    for temp in temp_files:
        try:
            os.remove(temp)
        except OSError:
            pass

    return output_path
