"""Standalone PDF exporter for CAUFA reports.

This file intentionally avoids the Unicode peso symbol and uses a plain
"P1,000.00" format so it remains visible in PDF viewers and cPanel environments
that do not render the peso glyph reliably.
"""

from __future__ import annotations

import base64
import html
from pathlib import Path


def _pdf_text(value):
    return str(value if value is not None else "").replace("₱", "P ")


def _currency_text(value):
    if value is None:
        return ""
    text = _pdf_text(value).strip()
    if not text:
        return ""
    cleaned = text.replace("₱", "").replace("PHP", "").replace("Php", "").replace("php", "")
    cleaned = cleaned.strip()
    if cleaned.startswith("P") and len(cleaned) > 1 and cleaned[1].isdigit():
        cleaned = cleaned[1:]
    try:
        amount = float(cleaned.replace(",", ""))
        return f"P{amount:,.2f}"
    except ValueError:
        return text


def _format_value(value, column=None):
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return _currency_text(value) if column and "amount" in str(column.get("key", "")).lower() else str(value)
    text = _pdf_text(value).strip()
    if not text:
        return ""
    column_name = str(column.get("key", "") or "").lower() if column else ""
    if "amount" in column_name or "total" in column_name or "balance" in column_name or "expected" in column_name or "paid" in column_name or "outstanding" in column_name:
        return _currency_text(text)
    return text


def _render_table(columns, rows):
    if not columns:
        return ""
    head = []
    for c in columns:
        label = html.escape(_pdf_text(c.get("label", "")))
        align = c.get("align", "left")
        head.append(f'<th class="report-align-{align}">{label}</th>')

    body_rows = []
    if not rows:
        body_rows.append(f'<tr><td colspan="{len(columns)}" class="report-empty">No records found</td></tr>')
    else:
        for row in rows:
            cells = []
            for c in columns:
                key = c.get("key")
                value = row.get(key, "") if isinstance(row, dict) else ""
                text = html.escape(_format_value(value, c))
                align = c.get("align", "left")
                cells.append(f'<td class="report-align-{align}">{text}</td>')
            body_rows.append(f'<tr>{"".join(cells)}</tr>')

    return (
        '<div class="report-table-wrap">'
        '<table class="report-table">'
        f'<thead><tr>{"".join(head)}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody>'
        '</table></div>'
    )


def _render_summary(summary):
    if not summary:
        return ""
    rows = []
    for item in summary:
        label = html.escape(_pdf_text(item.get("label", "")))
        value = html.escape(_currency_text(item.get("value")) if item.get("type") == "currency" else _pdf_text(item.get("value", "")))
        rows.append(f'<tr><td>{label}</td><td style="text-align:right; font-weight:700;">{value}</td></tr>')
    return (
        '<table class="report-summary-table">'
        '<thead><tr><th>Summary</th><th style="text-align:right;">Value</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table>'
    )


def build_report_html(report):
    report_name = _pdf_text(report.get("report_name") or "Report")
    generated_by = _pdf_text(report.get("generated_by") or "System")
    generated_at = _pdf_text(report.get("generated_at") or "")

    summary_html = _render_summary(report.get("summary", []))
    table_html = _render_table(report.get("columns", []), report.get("rows", []))
    filters_html = ""
    filters = report.get("filters", [])
    if filters:
        parts = []
        for f in filters:
            label = html.escape(_pdf_text(f.get("label", "")))
            value = html.escape(_pdf_text(f.get("value", "")))
            parts.append(f'<span><b>{label}:</b> {value}</span>')
        filters_html = f'<div class="report-filters">{"".join(parts)}</div>'

    logo_path = Path(__file__).resolve().parents[2] / "static" / "img" / "isu_caufa_seal_flat.png"
    logo_src = ""
    if logo_path.exists():
        try:
            logo_bytes = logo_path.read_bytes()
            logo_src = "data:image/png;base64," + base64.b64encode(logo_bytes).decode("ascii")
        except Exception:
            logo_src = "/static/img/isu_caufa_official.png"
    else:
        logo_src = "/static/img/isu_caufa_official.png"

    html_doc = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>{html.escape(report_name)}</title>
  <style>
    @page {{ size: A4 landscape; margin: 10mm; }}
    html, body {{ margin: 0; padding: 0; background: #fff; color: #111827; font-family: "DejaVu Sans", "Arial Unicode MS", "Segoe UI Symbol", Arial, sans-serif; }}
    body {{ line-height: 1.4; }}
    * {{ box-sizing: border-box; }}
    .report-page {{ width: 100%; }}
    .report-sheet {{ width: 100%; background: #fff; padding: 10px 12px; }}
    .report-header {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; border-bottom: 2px solid #0f5e3d; padding-bottom: 8px; margin-bottom: 8px; }}
    .report-brand {{ display: flex; align-items: center; gap: 12px; min-width: 0; }}
    .report-brand img {{ width: 52px; height: 52px; object-fit: contain; border-radius: 50%; background: #f4f7f5; border: 1px solid #d9e5dd; }}
    .report-brand-name {{ font-size: 29px; font-weight: 800; letter-spacing: 0.05em; color: #111827; }}
    .report-brand-sub {{ font-size: 10px; letter-spacing: 0.08em; color: #4b5563; text-transform: uppercase; margin-top: 4px; }}
    .report-meta {{ font-size: 12px; color: #374151; text-align: right; line-height: 1.5; }}
    .report-title {{ font-size: 26px; font-weight: 800; letter-spacing: 0.06em; text-transform: uppercase; text-align: center; margin: 14px 0 12px; color: #111827; }}
    .report-filters {{ display: flex; flex-wrap: wrap; gap: 8px 12px; padding: 10px 0; margin-bottom: 12px; border-top: 1px solid #d0d7de; border-bottom: 1px solid #d0d7de; font-size: 12px; color: #4b5563; }}
    .report-filters span {{ background: #f3f4f6; border: 1px solid #e5e7eb; border-radius: 4px; padding: 4px 8px; }}
    .report-summary-table {{ width: 100%; border-collapse: collapse; margin-bottom: 14px; border: 1px solid #d0d7de; }}
    .report-summary-table th, .report-summary-table td {{ border: 1px solid #d0d7de; padding: 8px 10px; text-align: left; }}
    .report-summary-table th {{ background: #0f5e3d; color: white; font-weight: 700; }}
    .report-table-wrap {{ overflow: hidden; border: 1px solid #d0d7de; margin-bottom: 16px; }}
    .report-table {{ width: 100%; border-collapse: collapse; table-layout: auto; }}
    .report-table th {{ background: #0f5e3d; color: white; padding: 8px 10px; font-weight: 700; text-align: left; }}
    .report-table td {{ padding: 7px 9px; border-top: 1px solid #e5e7eb; color: #1f2937; vertical-align: top; word-wrap: break-word; }}
    .report-table tbody tr:nth-child(even) {{ background: #f9fafb; }}
    .report-align-left {{ text-align: left; }}
    .report-align-right {{ text-align: right; }}
    .report-align-center {{ text-align: center; }}
    .report-empty {{ text-align: center; color: #6b7280; padding: 20px; }}
    @media print {{
      html, body {{ background: #fff; }}
      .report-sheet {{ padding: 0; }}
    }}
  </style>
</head>
<body>
  <div class="report-page">
    <div class="report-sheet">
      <div class="report-header">
        <div class="report-brand">
          <img src="{logo_src}" alt="ISUCauFA, Inc. Logo" />
          <div>
            <div class="report-brand-name">ISUCauFA, Inc.</div>
            <div class="report-brand-sub">Isabela State University – Cauayan Campus Faculty Association</div>
          </div>
        </div>
        <div class="report-meta">
          <div>Date Generated: {html.escape(generated_at)}</div>
          <div>Generated By: {html.escape(generated_by)}</div>
        </div>
      </div>
      <div class="report-title">{html.escape(report_name.upper())}</div>
      {filters_html}
      {summary_html}
      {table_html}
    </div>
  </div>
</body>
</html>'''
    return html_doc


def safe_report_pdf(report, output_path=None):
    html_doc = build_report_html(report)
    try:
        from weasyprint import HTML
        pdf = HTML(string=html_doc, base_url="").write_pdf()
    except Exception:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        import io

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=12 * mm,
            leftMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
        )
        base = ParagraphStyle("Base", fontName="Helvetica", fontSize=9, textColor=colors.black)
        title_style = ParagraphStyle("Title", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=22, alignment=1, textColor=colors.black)
        story = [Paragraph(html.escape(report.get("report_name") or "Report").upper(), title_style), Spacer(1, 10)]

        if report.get("summary"):
            data = [["Summary", "Value"]]
            for item in report["summary"]:
                label = str(item.get("label", ""))
                value = _currency_text(item.get("value")) if item.get("type") == "currency" else str(item.get("value", ""))
                data.append([label, value])
            tbl = Table(data, colWidths=[120, 200])
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f5e3d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.8, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 10))

        if report.get("columns"):
            rows = []
            headers = [str(c.get("label", "")) for c in report["columns"]]
            rows.append(headers)
            for row in report.get("rows", []):
                values = []
                for c in report["columns"]:
                    key = c.get("key")
                    value = row.get(key, "") if isinstance(row, dict) else ""
                    values.append(_format_value(value, c))
                rows.append(values)
            table = Table(rows, repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f5e3d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.8, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ]))
            story.append(table)

        doc.build(story)
        pdf = buffer.getvalue()

    if output_path:
        Path(output_path).write_bytes(pdf)
    return pdf


if __name__ == "__main__":
    sample = {
        "report_name": "Sample Report",
        "generated_by": "Treasurer",
        "generated_at": "2026-09-21 12:00:00",
        "filters": [{"label": "Month", "value": "September"}],
        "summary": [{"label": "Total", "value": 1000, "type": "currency"}],
        "columns": [{"label": "Member", "key": "member", "align": "left"}, {"label": "Amount", "key": "amount", "align": "right"}],
        "rows": [{"member": "Jane", "amount": "₱2500.00"}, {"member": "John", "amount": 1000}],
    }
    out = Path(__file__).resolve().with_name("sample_report.pdf")
    safe_report_pdf(sample, str(out))
    print(f"Generated {out}")
