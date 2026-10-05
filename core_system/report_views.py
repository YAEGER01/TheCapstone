from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone

from core_system.guards import require_role
from core_system.models import BudgetLine, OfficerUser, OrganizationFundReport
from core_system.services.association_reports import (
    GA_BUILDERS,
    build_ga_report,
    ga_reports_meta,
)
from core_system.services.oversight_reports import report_to_pdf, report_to_xlsx
from core_system.services.reporting import (
    REPORT_TYPES,
    generate_department_report,
    generate_contribution_report,
    generate_unified_report,
    resolve_report_range,
)


def _report_role_guard(request):
    """Officer reports are restricted to financial officers; members cannot download the roster workbook."""
    return require_role(request, role=["Treasurer", "Auditor", "President"])


def _download_response(wb, filename):
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@require_GET
def download_overall_report(request: HttpRequest):
    guard = _report_role_guard(request)
    if guard:
        return guard

    year = request.GET.get("year")
    month = request.GET.get("month")
    report_type = (request.GET.get("report_type") or "monthly").strip().lower()
    week = request.GET.get("week")
    if year:
        year = int(year)
    if month:
        month = int(month)
    if report_type not in REPORT_TYPES:
        report_type = "monthly"
    try:
        week_int = int(week) if week else None
    except (TypeError, ValueError):
        week_int = None

    wb = generate_unified_report(year, month, report_type=report_type, week=week_int)
    period = f"{year or 'current'}-{month or 'current'}"
    return _download_response(wb, f"unified_report_{report_type}_{period}.xlsx")


@require_GET
def download_department_report(request: HttpRequest, dept_id: int):
    guard = _report_role_guard(request)
    if guard:
        return guard

    year = request.GET.get("year")
    month = request.GET.get("month")
    if year:
        year = int(year)
    if month:
        month = int(month)

    wb = generate_department_report(dept_id=dept_id, year=year, month=month)
    if wb is None:
        return JsonResponse({"error": "Department not found."}, status=404)
    period = f"{year or 'current'}-{month or 'current'}"
    return _download_response(wb, f"department_report_{dept_id}_{period}.xlsx")


@require_GET
def download_contribution_report(request: HttpRequest):
    guard = _report_role_guard(request)
    if guard:
        return guard

    year = request.GET.get("year")
    month = request.GET.get("month")
    if year:
        year = int(year)
    if month:
        month = int(month)

    wb = generate_contribution_report()
    period = f"{year or 'current'}-{month or 'current'}"
    return _download_response(wb, f"contribution_report_{period}.xlsx")


@require_GET
def association_reports_meta(request: HttpRequest):
    """List the 16 association reports with groups, titles, and filter inputs."""
    guard = _report_role_guard(request)
    if guard:
        return guard
    return JsonResponse({"ok": True, "meta": ga_reports_meta()})


@require_GET
def association_report_preview(request: HttpRequest, report_key: str):
    """Preview one association report as JSON (normalized schema)."""
    guard = _report_role_guard(request)
    if guard:
        return guard
    if report_key not in GA_BUILDERS:
        return JsonResponse({"ok": False, "error": "Unknown report key."}, status=400)
    try:
        report = build_ga_report(request, report_key)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"Could not build report: {exc}"}, status=500)
    if report is None:
        return JsonResponse({"ok": False, "error": "Unknown report key."}, status=400)
    return JsonResponse({"ok": True, "report": report})


@require_GET
def association_report_export(request: HttpRequest, report_key: str):
    """Download one association report as XLSX (default) or PDF."""
    guard = _report_role_guard(request)
    if guard:
        return guard
    if report_key not in GA_BUILDERS:
        return JsonResponse({"ok": False, "error": "Unknown report key."}, status=400)
    fmt = (request.GET.get("format") or "xlsx").strip().lower()
    try:
        report = build_ga_report(request, report_key)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"Could not build report: {exc}"}, status=500)
    if report is None:
        return JsonResponse({"ok": False, "error": "Unknown report key."}, status=400)

    filename = f"{report_key}_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
    if fmt == "pdf":
        payload = report_to_pdf(report)
        response = HttpResponse(payload, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}.pdf"'
        return response

    wb = report_to_xlsx(report)
    return _download_response(wb, f"{filename}.xlsx")


@require_GET
def association_budget_lines(request: HttpRequest):
    """List budget lines for a fiscal year (for budget-vs-actual)."""
    guard = _report_role_guard(request)
    if guard:
        return guard
    try:
        year = int(request.GET.get("year") or timezone.localdate().year)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Year must be valid."}, status=400)
    lines = [
        {"category": line.category, "amount": float(line.amount), "notes": line.notes or ""}
        for line in BudgetLine.objects.filter(fiscal_year=year).order_by("category")
    ]
    return JsonResponse({"ok": True, "year": year, "lines": lines})


@require_POST
def association_budget_save(request: HttpRequest):
    """Replace the budget lines for a fiscal year. Treasurer only."""
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    import json as _json
    from decimal import Decimal, InvalidOperation

    try:
        payload = _json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)
    try:
        year = int(payload.get("year") or 0)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Year must be valid."}, status=400)
    if not 2000 <= year <= 2100:
        return JsonResponse({"ok": False, "error": "Year must be between 2000 and 2100."}, status=400)

    raw_lines = payload.get("lines")
    if not isinstance(raw_lines, list):
        return JsonResponse({"ok": False, "error": "lines must be a list."}, status=400)
    valid_categories = {key for key, _label in BudgetLine.CATEGORY_CHOICES}
    cleaned = []
    for entry in raw_lines:
        if not isinstance(entry, dict):
            return JsonResponse({"ok": False, "error": "Each line must be an object."}, status=400)
        category = str(entry.get("category") or "")
        if category not in valid_categories:
            return JsonResponse({"ok": False, "error": f"Unknown budget category: {category}."}, status=400)
        try:
            amount = Decimal(str(entry.get("amount") or 0))
        except (InvalidOperation, TypeError, ValueError):
            return JsonResponse({"ok": False, "error": f"Invalid amount for {category}."}, status=400)
        if amount < 0:
            return JsonResponse({"ok": False, "error": f"Amount for {category} cannot be negative."}, status=400)
        cleaned.append((category, amount, str(entry.get("notes") or "")[:255]))

    BudgetLine.objects.filter(fiscal_year=year).delete()
    for category, amount, notes in cleaned:
        BudgetLine.objects.create(fiscal_year=year, category=category, amount=amount, notes=notes or None)
    return JsonResponse({"ok": True, "year": year, "saved": len(cleaned)})


@require_POST
def generate_unified_report_view(request: HttpRequest):
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    year = (request.POST.get("year") or "").strip()
    month = (request.POST.get("month") or "").strip()
    week = (request.POST.get("week") or "").strip()
    report_type = (request.POST.get("report_type") or "monthly").strip().lower()

    if not year:
        return JsonResponse({"error": "Year is required."}, status=400)
    if report_type not in REPORT_TYPES:
        return JsonResponse({"error": "report_type must be 'weekly', 'monthly' or 'yearly'."}, status=400)
    if report_type != "yearly" and not month:
        return JsonResponse({"error": "Month is required for weekly and monthly reports."}, status=400)
    if report_type == "weekly" and not week:
        return JsonResponse({"error": "Week is required for weekly reports."}, status=400)

    try:
        year_int = int(year)
        month_int = int(month) if month else timezone.localdate().month
        week_int = int(week) if week else None
    except (ValueError, TypeError):
        return JsonResponse({"error": "Year, month and week must be valid numbers."}, status=400)

    if not 1 <= year_int <= 9999:
        return JsonResponse({"error": "Year must be valid."}, status=400)
    if not 1 <= month_int <= 12:
        return JsonResponse({"error": "Month must be between 1 and 12."}, status=400)
    if report_type == "weekly" and (week_int is None or not 1 <= week_int <= 5):
        return JsonResponse({"error": "Week must be between 1 and 5."}, status=400)

    officer_id = request.session.get("officer_id")
    try:
        officer = OfficerUser.objects.get(user_id_PK=int(officer_id))
    except OfficerUser.DoesNotExist:
        return JsonResponse({"error": "Officer not found."}, status=400)

    wb = generate_unified_report(year_int, month_int, report_type=report_type, week=week_int)
    period = resolve_report_range(report_type, year_int, month_int, week_int)[2]
    filename = f"unified_report_{report_type}_{period}.xlsx"
    file_path = f"reports/{filename}"

    import os
    from django.conf import settings
    default_storage_path = getattr(settings, "MEDIA_ROOT", "")
    full_path = os.path.join(str(default_storage_path), file_path) if default_storage_path else file_path
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    wb.save(full_path)

    # Optional custom report content from Reports Management — when present,
    # the workflow shows THIS filtered report instead of the generic summary.
    import json as _json
    report_rows = ""
    raw_rows = (request.POST.get("rows") or "").strip()
    if raw_rows:
        try:
            parsed = _json.loads(raw_rows)
            if isinstance(parsed, dict) and isinstance(parsed.get("headers"), list) and isinstance(parsed.get("rows"), list):
                parsed["headers"] = [str(h) for h in parsed["headers"]][:12]
                parsed["rows"] = [[str(c) for c in row] for row in parsed["rows"]][:300]
                parsed["total_label"] = str(parsed.get("total_label") or "")[:100]
                report_rows = _json.dumps(parsed)
        except (ValueError, TypeError):
            report_rows = ""

    report = OrganizationFundReport.objects.create(
        report_period=period,
        report_type=report_type,
        report_status="Draft",
        file_path=file_path,
        prepared_by_user_id_FK=officer,
        report_title=(request.POST.get("title") or "").strip()[:200],
        report_filters=(request.POST.get("filters") or "").strip()[:300],
        report_rows=report_rows,
    )

    return JsonResponse({
        "report_id": report.report_id_PK,
        "period": report.report_period,
        "report_type": report.report_type,
        "status": report.report_status,
        "file_path": report.file_path,
    })
