"""Printable copy of the monthly deducted-amount sheet.

The document has two parts:

    Page 1 — a transmittal letter from ISUCauFA (signed by the association's
             signatory, by default "Ma'am Marisol") addressed to the
             University Accounting Office, respectfully requesting the salary
             deduction for the covered month.
    Page 2+ — the deducted amount sheet itself: one row per member with the
             amount actually deducted from their salary, plus a grand total.

The PDF is generated from the final Treasurer-recorded MemberAssessment rows
so it always matches what the Auditor verified. The signatory name/position
can be overridden with the system settings
`deduction_letter_signatory_name` / `deduction_letter_signatory_position`.
"""

from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

from django.conf import settings

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from core_system.models import SystemSetting

GREEN = colors.HexColor("#2d5016")
GOLD = colors.HexColor("#d4af37")
DARK = colors.HexColor("#333333")
LIGHT_ROW = colors.HexColor("#f3f8f3")

CAMPUS_ADDRESS = (
    "18 Dacanay Street, Barangay San Fermin, "
    "Cauayan City, Isabela, 3305, Philippines"
)

ORG_HEADER_1 = "ISABELA STATE UNIVERSITY  CAUAYAN"
ORG_HEADER_2 = "FACULTY ASSOCIATION (ISUCauFA)"

DEFAULT_SIGNATORY_NAME = "Marisol"
DEFAULT_SIGNATORY_POSITION = "President, ISUCauFA"

LETTER_ADDRESSEE_LINES = [
    "THE UNIVERSITY ACCOUNTING OFFICE",
    "Isabela State University — Cauayan Campus",
    "Cauayan City, Isabela",
]

M = 20 * mm  # page margin


def _setting(key: str, default: str) -> str:
    try:
        row = SystemSetting.objects.filter(setting_key=key).first()
    except Exception:
        return default
    value = (row.setting_value or "").strip() if row else ""
    return value or default


def _wrap(c, text, font, size, max_width):
    c.setFont(font, size)
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if c.stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_letterhead(c, w, h):
    """Shared ISUCauFA letterhead with both seals."""
    left_seal = Path(settings.BASE_DIR) / "static" / "img" / "isu_official_seal_flat.png"
    right_seal = Path(settings.BASE_DIR) / "static" / "img" / "isu_caufa_seal_flat.png"
    seal_y = h - M - 52
    for path, x in ((left_seal, M + 42), (right_seal, w - M - 42)):
        if not path.exists():
            continue
        try:
            c.saveState()
            clip = c.beginPath()
            clip.circle(x, seal_y, 30)
            c.clipPath(clip, stroke=0, fill=1)
            c.drawImage(
                str(path), x - 30, seal_y - 30, 60, 60,
                mask="auto", preserveAspectRatio=True, anchor="c",
            )
            c.restoreState()
        except Exception:
            pass

    c.setFont("Times-Bold", 8)
    c.setFillColor(GREEN)
    c.drawCentredString(w / 2, h - M - 22, "REPUBLIC OF THE PHILIPPINES")
    c.setFont("Times-Bold", 15)
    c.drawCentredString(w / 2, h - M - 42, ORG_HEADER_1)
    c.setFont("Times-Bold", 11)
    c.drawCentredString(w / 2, h - M - 55, ORG_HEADER_2)
    c.setFont("Times-Roman", 8)
    c.setFillColor(DARK)
    c.drawCentredString(w / 2, h - M - 67, CAMPUS_ADDRESS)
    c.setStrokeColor(GREEN)
    c.setLineWidth(2)
    c.line(M, h - M - 76, w - M, h - M - 76)
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    c.line(M, h - M - 78, w - M, h - M - 78)


def _draw_letter_page(c, w, h, month_label, total_amount, member_count, generated_for):
    """Page 1: transmittal letter requesting the salary deduction."""
    signatory_name = _setting("deduction_letter_signatory_name", DEFAULT_SIGNATORY_NAME)
    signatory_position = _setting("deduction_letter_signatory_position", DEFAULT_SIGNATORY_POSITION)

    _draw_letterhead(c, w, h)

    y = h - M - 108
    c.setFont("Times-Roman", 11)
    c.setFillColor(DARK)
    for line in LETTER_ADDRESSEE_LINES:
        c.drawString(M, y, line)
        y -= 15

    y -= 10
    c.setFont("Times-Bold", 11)
    c.drawString(M, y, "SUBJECT: ")
    subj_w = c.stringWidth("SUBJECT: ", "Times-Bold", 11)
    c.setFont("Times-Roman", 11)
    c.drawString(
        M + subj_w, y,
        f"Request for Salary Deduction — ISUCauFA Monthly Dues and Fund Contributions, {month_label}",
    )
    y -= 15
    c.setFont("Times-Bold", 11)
    c.drawString(M, y, "DATE: ")
    date_w = c.stringWidth("DATE: ", "Times-Bold", 11)
    c.setFont("Times-Roman", 11)
    c.drawString(M + date_w, y, generated_for)
    y -= 26

    salutation = "Dear Sir/Madam:"
    c.setFont("Times-Roman", 11)
    c.drawString(M, y, salutation)
    y -= 20

    amount_str = f"PHP {total_amount:,.2f}"
    body = (
        f"Greetings from the Isabela State University — Cauayan Campus Faculty "
        f"Association (ISUCauFA).\n\n"
        f"In behalf of the association, we respectfully request your good office to "
        f"deduct from the salaries of the {member_count} bonafide member(s) listed on the "
        f"attached sheet their monthly dues and fund contributions for the month of "
        f"{month_label}, amounting to a total of {amount_str}. "
        f"The attached deducted-amount sheet, marked as Annex A, reflects each member's "
        f"name, employee number, department, and the exact amount to be deducted.\n\n"
        f"May we likewise request that the total amount collected be remitted to the "
        f"ISUCauFA Treasurer immediately after the payroll for the stated period has been "
        f"processed. A copy of this letter and the accompanying sheet is retained by the "
        f"association for its financial records and for verification by the Auditor.\n\n"
        f"We hope for your favorable action on this matter. Thank you very much for your "
        f"continued support of the association's programs for its members."
    )
    font, size, leading = "Times-Roman", 11, 15
    for paragraph in body.split("\n\n"):
        lines = _wrap(c, paragraph.replace("\n", " "), font, size, w - 2 * M)
        c.setFont(font, size)
        for ln in lines:
            c.drawString(M, y, ln)
            y -= leading
        y -= 8

    y -= 14
    c.setFont("Times-Roman", 11)
    c.drawString(M, y, "Very truly yours,")
    y -= 52

    sig_name = signatory_name.upper()
    c.setFont("Times-Bold", 11)
    c.drawString(M, y, sig_name)
    c.setStrokeColor(DARK)
    c.setLineWidth(0.8)
    c.line(M, y + 14, M + 170, y + 14)
    y -= 13
    c.setFont("Times-Roman", 10)
    c.drawString(M, y, signatory_position)
    y -= 12
    c.drawString(M, y, "Isabela State University — Cauayan Campus Faculty Association (ISUCauFA)")

    c.setFont("Times-Italic", 8)
    c.setFillColor(colors.HexColor("#777777"))
    c.drawCentredString(w / 2, M - 6, "Annex A — Deducted Amount Sheet follows on the next page.")


def _draw_sheet_pages(c, w, h, rows, month_label, standard_amount):
    """Page 2+: the deducted amount sheet itself (Annex A)."""
    usable = w - 2 * M
    col_widths = [14 * mm, 64 * mm, 30 * mm, 42 * mm, usable - 150 * mm]
    headers = ["No.", "Member Name", "Employee No.", "Department", "Amount Deducted"]

    def start_page():
        c.showPage()
        _draw_letterhead(c, w, h)
        y = h - M - 106
        c.setFont("Times-Bold", 12)
        c.setFillColor(GREEN)
        c.drawCentredString(w / 2, y, "ANNEX A — DEDUCTED AMOUNT SHEET")
        y -= 16
        c.setFont("Times-Roman", 10)
        c.setFillColor(DARK)
        c.drawCentredString(w / 2, y, f"Monthly Deductions for {month_label}")
        y -= 20
        # header row
        c.setFillColor(GREEN)
        c.rect(M, y - 5, usable, 18, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Times-Bold", 9.5)
        x = M
        for header, col_w in zip(headers, col_widths):
            if header == "Amount Deducted":
                c.drawRightString(x + col_w - 6, y, header)
            else:
                c.drawString(x + 6, y, header)
            x += col_w
        return y - 5 - 14

    y = start_page()
    c.setFillColor(DARK)

    def trunc(text, font, size, max_w):
        if c.stringWidth(text, font, size) <= max_w:
            return text
        while text and c.stringWidth(text + "…", font, size) > max_w:
            text = text[:-1]
        return text + "…"

    for idx, row in enumerate(rows, start=1):
        if y < M + 92:
            y = start_page()
        if idx % 2 == 0:
            c.setFillColor(LIGHT_ROW)
            c.rect(M, y - 4, usable, 15, stroke=0, fill=1)
        c.setFillColor(DARK)
        c.setFont("Times-Roman", 9.5)
        x = M
        cells = [str(idx), row["name"], row["employee_id"] or "—", row["department"] or "—"]
        for value, col_w in zip(cells, col_widths):
            c.drawString(x + 6, y, trunc(value, "Times-Roman", 9.5, col_w - 12))
            x += col_w
        c.setFont("Times-Bold", 9.5)
        c.drawRightString(M + usable - 6, y, f"{row['amount']:,.2f}")
        y -= 15

    if y < M + 120:
        y = start_page()

    # Totals block
    y -= 8
    c.setStrokeColor(DARK)
    c.setLineWidth(0.8)
    c.line(M + 110 * mm, y + 12, M + usable, y + 12)
    c.setFont("Times-Bold", 10)
    c.drawString(M + 110 * mm, y, "TOTAL DEDUCTIONS")
    c.drawRightString(M + usable - 6, y, f"PHP {sum(r['amount'] for r in rows):,.2f}")
    y -= 18
    c.setFont("Times-Roman", 9)
    c.drawString(
        M + 110 * mm, y,
        f"{len(rows)} member(s) × PHP {standard_amount:,.2f} standard assessment",
    )

    # Certification strip
    y -= 34
    c.setFont("Times-Italic", 8.5)
    c.setFillColor(colors.HexColor("#555555"))
    cert = _wrap(
        c,
        "This sheet is a true and correct copy of the deductions recorded in the "
        "ISUCauFA Panel System for the period stated above, as verified by the "
        "association Auditor.",
        "Times-Italic", 8.5, usable,
    )
    for ln in cert:
        c.drawCentredString(w / 2, y, ln)
        y -= 11

    # Signature blocks: Treasurer (prepared by) and Auditor (verified by)
    y -= 34
    block_w = usable / 2
    for label_x, name, position in (
        (M + block_w / 2 - 70, _setting("deduction_sheet_prepared_by_name", ""), "Prepared by: ISUCauFA Treasurer"),
        (w - M - block_w / 2 - 70, "", "Verified by: ISUCauFA Auditor"),
    ):
        c.setStrokeColor(DARK)
        c.setLineWidth(0.8)
        c.line(label_x, y, label_x + 140, y)
        c.setFont("Times-Bold", 9)
        c.setFillColor(DARK)
        c.drawString(label_x, y - 11, (name or "\u00a0").upper())
        c.setFont("Times-Roman", 8.5)
        c.drawString(label_x, y - 21, position)


def _draw_uploaded_documents(c, w, h, assessment, finish_previous_page=False) -> None:
    """Render the President's uploaded scans (signed request letter and the
    source deducted-amount sheet), one image per page. When
    `finish_previous_page` is True a page break is emitted before the first
    image (used when generated pages precede the uploads)."""
    from core_system.models import MonthlyAssessmentDocument

    margin = 15 * mm
    label_y_offset = 14 * mm
    groups = [
        (MonthlyAssessmentDocument.KIND_REQUEST_LETTER, "Request Letter — signed copy"),
        (MonthlyAssessmentDocument.KIND_DEDUCTION_SHEET, "Deducted Amount Sheet"),
    ]

    pending_break = finish_previous_page
    for kind, label in groups:
        docs = list(
            assessment.documents.filter(kind=kind).order_by("uploaded_at", "document_id_PK")
        )
        total = len(docs)
        for idx, doc in enumerate(docs, start=1):
            try:
                reader = ImageReader(doc.image.path)
                iw, ih = reader.getSize()
            except Exception:
                continue

            if pending_break:
                c.showPage()
            pending_break = True

            c.setFont("Helvetica-Bold", 9)
            c.setFillColor(GREEN)
            page_label = f"{label}" if total == 1 else f"{label} — page {idx} of {total}"
            c.drawString(margin, h - label_y_offset, page_label)
            c.setFont("Helvetica", 7.5)
            c.setFillColor(colors.HexColor("#777777"))
            c.drawRightString(
                w - margin,
                h - label_y_offset,
                f"Uploaded by the President · {assessment.month_label}",
            )

            avail_w = w - margin * 2
            avail_h = h - margin * 2 - label_y_offset
            scale = min(avail_w / iw, avail_h / ih)
            draw_w, draw_h = iw * scale, ih * scale
            c.drawImage(
                reader,
                (w - draw_w) / 2,
                margin + (avail_h - draw_h) / 2,
                width=draw_w,
                height=draw_h,
                preserveAspectRatio=True,
                mask="auto",
            )


def build_deduction_sheet_pdf(assessment) -> bytes:
    """Render the transmittal letter + deducted amount sheet for one assessment."""
    from django.utils.timezone import localtime

    rows = []
    member_rows = (
        assessment.member_assessments.select_related("member_id_FK")
        .order_by("member_id_FK__full_name")
    )
    for ma in member_rows:
        member = ma.member_id_FK
        rows.append({
            "name": member.full_name,
            "employee_id": member.employee_id or "",
            "department": member.department or "",
            "amount": float(ma.actual_deduction),
        })
    rows.sort(key=lambda r: r["name"].casefold())

    buf = io.BytesIO()
    w, h = A4
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"ISUCauFA Deduction Sheet {assessment.month_label}")

    generated_for = localtime(assessment.updated_at).strftime("%B %d, %Y") if assessment.updated_at else ""

    if assessment.documents.exists():
        # The President already uploaded the signed request letter and the
        # deducted-amount sheet scans — the packet is those documents only.
        _draw_uploaded_documents(c, w, h, assessment)
    else:
        # Fallback for months without uploads: generate the letter + sheet.
        _draw_letter_page(
            c, w, h,
            month_label=assessment.month_label,
            total_amount=float(assessment.total_amount),
            member_count=len(rows),
            generated_for=generated_for,
        )

        _draw_sheet_pages(
            c, w, h, rows=rows,
            month_label=assessment.month_label,
            standard_amount=float(assessment.total_amount),
        )
        _draw_uploaded_documents(c, w, h, assessment, finish_previous_page=True)

    c.save()
    return buf.getvalue()
