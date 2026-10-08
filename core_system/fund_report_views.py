import json
import os
import re

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import HttpRequest, JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone

from core_system.guards import require_role, check_zero_trust
from core_system.models import OfficerUser, OrganizationFundReport, Member, Document, DocumentActivity
from core_system.services.reporting import (
    REPORT_TYPES,
    build_aid_payout_rows,
    build_aid_setaside_rows,
    generate_unified_report,
    months_covered_by,
    parse_report_period,
    report_type_label as format_report_type_label,
    resolve_report_range,
    resolve_report_range_from_period,
)
from core_system.services.email_service import send_html_email


def _archive_approved_report_document(report, approving_officer):
    """File an approved fund report into the Treasurer's and President's
    Document Repositories (idempotent per repository — skips if already
    archived there). Returns the number of documents created."""
    import logging

    logger = logging.getLogger(__name__)
    created = 0
    try:
        file_path = report.file_path or ""
        file_name = os.path.basename(file_path) if file_path else ""
        if not file_name:
            return 0
        # Unique, human-readable title per report — the custom report's own
        # title when it came from Reports Management, otherwise the org report.
        if report.report_title:
            title = f"{report.report_title} - {_period_words(report.report_period)}"
        else:
            title = f"Organization Fund Report - {_period_words(report.report_period)}"
        fr_reference = f"Reference: FR-{report.report_id_PK:05d}."
        description = (
            f"Official fund report for {report.report_period}, approved by "
            f"{approving_officer.full_name if approving_officer else 'the President'} "
            f"on {timezone.now().strftime('%B %d, %Y')}. {fr_reference}"
        )
        file_size = None
        try:
            if file_path and os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
        except OSError:
            file_size = None

        # Prefer a generated PDF of the official report for the repositories.
        doc_file_path, doc_file_name, doc_file_type = file_path, file_name, "xlsx"
        pdf_bytes = None
        try:
            pdf_bytes = _build_report_pdf_bytes(report)
        except Exception:
            logger.exception("PDF build failed while archiving fund report %s", report.report_id_PK)
        if pdf_bytes:
            pdf_rel = f"reports/FR-{report.report_id_PK:05d}_{report.report_period}.pdf"
            try:
                pdf_full = os.path.join(str(getattr(settings, "MEDIA_ROOT", "")), pdf_rel)
                os.makedirs(os.path.dirname(pdf_full), exist_ok=True)
                with open(pdf_full, "wb") as fh:
                    fh.write(pdf_bytes)
                doc_file_path = pdf_rel
                doc_file_name = os.path.basename(pdf_rel)
                doc_file_type = "pdf"
                file_size = len(pdf_bytes)
            except OSError:
                logger.exception("Could not write archived PDF for fund report %s", report.report_id_PK)

        targets = []
        # Treasurer's repository (owner = the officer who prepared the report)
        if report.prepared_by_user_id_FK:
            targets.append(("Treasurer", report.prepared_by_user_id_FK))
        # President's repository (owner = the approving President)
        if approving_officer:
            targets.append(("President", approving_officer))

        for role, owner in targets:
            try:
                exists = Document.objects.filter(
                    description__contains=fr_reference,
                    uploaded_by_user_id_FK=owner,
                ).exists()
                if exists:
                    continue
                doc = Document.objects.create(
                    title=title,
                    description=description,
                    document_type="Financial Document",
                    category="Fund Reports",
                    keywords=f"fund report, {report.report_period}, {report.report_type}",
                    file_path=doc_file_path,
                    file_name=doc_file_name,
                    file_size=file_size,
                    file_type=doc_file_type,
                    uploaded_by_user_id_FK=owner,
                )
                DocumentActivity.objects.create(
                    document_id_FK=doc,
                    action="archived",
                    officer_id_FK=approving_officer,
                    officer_name=approving_officer.full_name if approving_officer else "President",
                    details=f"Approved fund report {report.report_period} filed to {role} repository",
                )
                created += 1
                logger.info(
                    "Archived approved fund report %s to the %s repository (document %s)",
                    report.report_id_PK, role, doc.document_id_PK,
                )
            except Exception:
                # One repository failing must not prevent the other from
                # receiving its copy.
                logger.exception(
                    "Failed to archive approved fund report %s to the %s repository",
                    report.report_id_PK, role,
                )
        return created
    except Exception:
        logger.exception("Failed to archive approved fund report %s to document repositories", report.report_id_PK)
        return created


# ==========================================================================
# TREASURER: Create / List / Download Fund Reports
# ==========================================================================

@require_GET
def treasurer_fund_reports_list(request: HttpRequest):
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    reports = OrganizationFundReport.objects.all().order_by("-created_at")
    data = []
    for r in reports:
        data.append({
            "report_id": r.report_id_PK,
            "period": r.report_period,
            "report_type": r.report_type,
            "status": r.report_status,
            "file_path": r.file_path,
            "prepared_by": r.prepared_by_user_id_FK.full_name if r.prepared_by_user_id_FK else "",
            "verified_by": r.auditor_verified_by_user_id_FK.full_name if r.auditor_verified_by_user_id_FK else "",
            "verified_at": r.auditor_verified_at.isoformat() if r.auditor_verified_at else "",
            "return_reason": r.return_reason or "",
            "approved_by": r.approved_by_user_id_FK.full_name if r.approved_by_user_id_FK else "",
            "approved_at": r.approved_at.isoformat() if r.approved_at else "",
            "report_title": r.report_title or "",
            "report_filters": r.report_filters or "",
            "report_rows": r.report_rows or "",
            "created_at": r.created_at.isoformat(),
        })
    return JsonResponse({"ok": True, "reports": data})


@require_POST
def treasurer_create_fund_report(request: HttpRequest):
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

    default_storage_path = getattr(settings, "MEDIA_ROOT", "")
    full_path = os.path.join(str(default_storage_path), file_path) if default_storage_path else file_path
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    wb.save(full_path)

    # Optional custom report content from the Reports Management builder —
    # when present, the whole workflow shows THIS report instead of the
    # organization-wide summary.
    report_title = (request.POST.get("title") or "").strip()[:200]
    report_filters = (request.POST.get("filters") or "").strip()[:300]
    report_rows = ""
    raw_rows = (request.POST.get("rows") or "").strip()
    if raw_rows:
        try:
            parsed = json.loads(raw_rows)
            if isinstance(parsed, dict) and isinstance(parsed.get("headers"), list) and isinstance(parsed.get("rows"), list):
                parsed["headers"] = [str(h) for h in parsed["headers"]][:12]
                parsed["rows"] = [[str(c) for c in row] for row in parsed["rows"]][:300]
                parsed["total_label"] = str(parsed.get("total_label") or "")[:100]
                report_rows = json.dumps(parsed)
        except (ValueError, TypeError):
            report_rows = ""

    report = OrganizationFundReport.objects.create(
        report_period=period,
        report_type=report_type,
        report_status="Draft",
        file_path=file_path,
        prepared_by_user_id_FK=officer,
        report_title=report_title,
        report_filters=report_filters,
        report_rows=report_rows,
    )

    return JsonResponse({
        "report_id": report.report_id_PK,
        "period": report.report_period,
        "report_type": report.report_type,
        "status": report.report_status,
        "file_path": report.file_path,
    })


@require_GET
def treasurer_download_fund_report(request: HttpRequest, report_id: int):
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    return _download_report_file(report_id)


@require_POST
def treasurer_update_fund_report(request: HttpRequest, report_id: int):
    """Treasurer EDITS a Draft/Rejected report: replaces title, filters and the
    full report content (summary/sections/rows) before resubmitting for audit."""
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    report = get_object_or_404(OrganizationFundReport, pk=report_id)
    if report.report_status not in ("Draft", "Rejected", "Returned for Revision"):
        return JsonResponse({"error": "Only Draft, Returned for Revision or Rejected reports can be edited."}, status=400)

    officer_id = request.session.get("officer_id")
    officer = None
    if officer_id:
        try:
            officer = OfficerUser.objects.get(user_id_PK=int(officer_id))
        except OfficerUser.DoesNotExist:
            return JsonResponse({"error": "Officer not found."}, status=400)

    old_snapshot = {
        "report_title": report.report_title,
        "report_filters": report.report_filters,
        "report_rows": (report.report_rows or "")[:300],
    }

    new_title = (request.POST.get("title") or "").strip()[:200]
    new_filters = (request.POST.get("filters") or "").strip()[:300]
    raw_rows = (request.POST.get("rows") or "").strip()
    new_rows = report.report_rows
    if raw_rows:
        import json as _json
        try:
            parsed = _json.loads(raw_rows)
            if isinstance(parsed, dict):
                parsed["headers"] = [str(h) for h in parsed.get("headers", [])][:12]
                parsed["rows"] = [[str(c) for c in row] for row in parsed.get("rows", [])][:300]
                parsed["total_label"] = str(parsed.get("total_label") or "")[:100]
                summary = parsed.get("summary")
                if isinstance(summary, list):
                    parsed["summary"] = [[str(s[0]), str(s[1])] for s in summary if isinstance(s, (list, tuple)) and len(s) >= 2][:20]
                else:
                    parsed.pop("summary", None)
                sections = parsed.get("sections")
                if isinstance(sections, list):
                    cleaned = []
                    for s in sections:
                        if not isinstance(s, dict):
                            continue
                        # Wide sections (Fund Overview's 5-column month table,
                        # 4-column transactions) are legitimate — cap at 8.
                        heads = [str(h) for h in s.get("headers") or []][:8] if isinstance(s.get("headers"), list) else []
                        ncols = len(heads) if heads else 3
                        rows_out = []
                        for c in s.get("rows", []):
                            if isinstance(c, (list, tuple)) and len(c) >= ncols:
                                rows_out.append([str(x) for x in c[:ncols]])
                        cleaned.append({
                            "title": str(s.get("title") or "")[:100],
                            "headers": heads,
                            "rows": rows_out[:300],
                        })
                    parsed["sections"] = cleaned[:24]  # one section per department (Masterlist) can exceed 10
                else:
                    parsed.pop("sections", None)
                new_rows = _json.dumps(parsed)
        except (ValueError, TypeError):
            return JsonResponse({"error": "Invalid report rows payload."}, status=400)

    report.report_title = new_title or report.report_title
    report.report_filters = new_filters
    report.report_rows = new_rows
    report.save(update_fields=["report_title", "report_filters", "report_rows", "updated_at"])

    try:
        from core_system.shared_view_utils import _record_audit_trail
        _record_audit_trail(
            table="organization_fund_report",
            record_id=report.report_id_PK,
            action="REVISED",
            actor=officer,
            old=old_snapshot,
            new={"report_title": report.report_title, "report_filters": report.report_filters},
            ip=request.META.get("REMOTE_ADDR"),
            notes=f"Fund report {report.report_period} revised by Treasurer",
        )
    except Exception:
        pass

    return JsonResponse({"ok": True, "report_id": report.report_id_PK, "status": report.report_status})


@require_POST
def treasurer_submit_fund_report(request: HttpRequest, report_id: int):
    """Treasurer submits a Draft/Rejected report for Auditor verification (maker step)."""
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    report = get_object_or_404(OrganizationFundReport, pk=report_id)
    if report.report_status not in ("Draft", "Rejected", "Returned for Revision"):
        return JsonResponse({"error": "Only Draft, Returned for Revision or Rejected reports can be submitted for audit."}, status=400)

    officer_id = request.session.get("officer_id")
    officer = None
    if officer_id:
        try:
            officer = OfficerUser.objects.get(user_id_PK=int(officer_id))
        except OfficerUser.DoesNotExist:
            return JsonResponse({"error": "Officer not found."}, status=400)

    old_status = report.report_status
    report.report_status = "Submitted"
    report.save(update_fields=["report_status", "updated_at"])

    try:
        from core_system.shared_view_utils import _record_audit_trail
        _record_audit_trail(
            table="organization_fund_report",
            record_id=report.report_id_PK,
            action="SUBMITTED_FOR_AUDIT",
            actor=officer,
            old={"report_status": old_status},
            new={"report_status": report.report_status},
            ip=request.META.get("REMOTE_ADDR"),
            notes=f"Fund report {report.report_period} submitted for audit",
        )
    except Exception:
        pass

    return JsonResponse({"ok": True, "status": report.report_status})


# ==========================================================================
# AUDITOR: Submit Fund Report for President Approval
# ==========================================================================

@require_GET
def auditor_fund_reports_list(request: HttpRequest):
    """Reports submitted by the Treasurer awaiting Auditor verification,
    plus verification history (Auditor Verified / Rejected / Approved)."""
    guard = require_role(request, role="Auditor")
    if guard is not None:
        return guard

    reports = OrganizationFundReport.objects.exclude(
        report_status="Draft"
    ).order_by("-created_at")
    data = []
    for r in reports:
        data.append({
            "report_id": r.report_id_PK,
            "period": r.report_period,
            "report_type": r.report_type,
            "status": r.report_status,
            "file_path": r.file_path,
            "prepared_by": r.prepared_by_user_id_FK.full_name if r.prepared_by_user_id_FK else "",
            "verified_by": r.auditor_verified_by_user_id_FK.full_name if r.auditor_verified_by_user_id_FK else "",
            "verified_at": r.auditor_verified_at.isoformat() if r.auditor_verified_at else "",
            "return_reason": r.return_reason or "",
            "approved_by": r.approved_by_user_id_FK.full_name if r.approved_by_user_id_FK else "",
            "approved_at": r.approved_at.isoformat() if r.approved_at else "",
            "report_title": r.report_title or "",
            "report_filters": r.report_filters or "",
            "report_rows": r.report_rows or "",
            "created_at": r.created_at.isoformat(),
        })
    return JsonResponse({"ok": True, "reports": data})


@require_POST
def auditor_verify_fund_report(request: HttpRequest, report_id: int):
    """Auditor verifies a Treasurer-submitted report and forwards it to the
    President for final approval (mockup: Submitted -> Auditor Verified)."""
    guard = require_role(request, role="Auditor")
    if guard is not None:
        return guard
    guard = check_zero_trust(request, level="approve")
    if guard is not None:
        return guard

    officer_id = request.session.get("officer_id")
    officer = None
    if officer_id:
        try:
            officer = OfficerUser.objects.get(user_id_PK=int(officer_id))
        except OfficerUser.DoesNotExist:
            return JsonResponse({"error": "Officer not found."}, status=400)

    report = get_object_or_404(OrganizationFundReport, pk=report_id)
    if report.report_status != "Submitted":
        return JsonResponse({"error": "Only Submitted reports can be verified."}, status=400)

    old_status = report.report_status
    report.report_status = "Auditor Verified"
    report.auditor_verified_by_user_id_FK = officer
    report.auditor_verified_at = timezone.now()
    report.return_reason = ""
    report.save(update_fields=[
        "report_status", "auditor_verified_by_user_id_FK", "auditor_verified_at",
        "return_reason", "updated_at",
    ])

    try:
        from core_system.shared_view_utils import _record_audit_trail
        _record_audit_trail(
            table="organization_fund_report",
            record_id=report.report_id_PK,
            action="AUDITOR_VERIFIED",
            actor=officer,
            old={"report_status": old_status},
            new={"report_status": report.report_status},
            ip=request.META.get("REMOTE_ADDR"),
            notes=f"Fund report {report.report_period} verified by Auditor — forwarded to President",
        )
    except Exception:
        pass

    return JsonResponse({"ok": True, "status": report.report_status})


@require_POST
def auditor_return_fund_report(request: HttpRequest, report_id: int):
    """Auditor returns a Treasurer-submitted report for revision
    (mockup: Submitted -> Returned to Treasurer, reason required)."""
    guard = require_role(request, role="Auditor")
    if guard is not None:
        return guard
    guard = check_zero_trust(request, level="approve")
    if guard is not None:
        return guard

    officer_id = request.session.get("officer_id")
    officer = None
    if officer_id:
        try:
            officer = OfficerUser.objects.get(user_id_PK=int(officer_id))
        except OfficerUser.DoesNotExist:
            return JsonResponse({"error": "Officer not found."}, status=400)

    remarks = (request.POST.get("remarks") or "").strip()
    if not remarks:
        return JsonResponse({"error": "A return reason is required."}, status=400)

    report = get_object_or_404(OrganizationFundReport, pk=report_id)
    if report.report_status != "Submitted":
        return JsonResponse({"error": "Only Submitted reports can be returned."}, status=400)

    old_status = report.report_status
    # RETURNED FOR REVISION ≠ REJECTED: returned reports go back to the
    # Treasurer for source-data correction + resubmission; Rejected is the
    # terminal decision (President reject / Treasurer claim reject). Both are
    # preserved as historical records — resubmission always creates a NEW row.
    report.report_status = "Returned for Revision"
    report.return_reason = remarks
    report.save(update_fields=["report_status", "return_reason", "updated_at"])

    try:
        from core_system.shared_view_utils import _record_audit_trail
        _record_audit_trail(
            table="organization_fund_report",
            record_id=report.report_id_PK,
            action="RETURNED_TO_TREASURER",
            actor=officer,
            old={"report_status": old_status},
            new={"report_status": report.report_status},
            ip=request.META.get("REMOTE_ADDR"),
            notes=f"Fund report {report.report_period} returned to Treasurer: {remarks}",
        )
    except Exception:
        pass

    return JsonResponse({"ok": True, "status": report.report_status})


@require_GET
def auditor_download_fund_report(request: HttpRequest, report_id: int):
    guard = require_role(request, role="Auditor")
    if guard is not None:
        return guard
    return _download_report_file(report_id)


@require_GET
def president_download_fund_report(request: HttpRequest, report_id: int):
    guard = require_role(request, role="President")
    if guard is not None:
        return guard
    return _download_report_file(report_id)


def _regenerate_report_file(report) -> bool:
    """Regenerate the workbook for a report whose media file is missing."""
    parsed = parse_report_period(report.report_period)
    if not parsed:
        return False
    report_type, year, month, week = parsed

    if not report.file_path:
        return False

    wb = generate_unified_report(year, month, report_type=report_type, week=week)
    full_path = os.path.join(str(getattr(settings, "MEDIA_ROOT", "")), report.file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    wb.save(full_path)
    return True


def _download_report_file(report_id: int):
    report = get_object_or_404(OrganizationFundReport, pk=report_id)

    # Preferred: a freshly generated PDF of the official report (same content
    # as the View Sheet preview) so the download is never an empty/stale file.
    try:
        pdf_bytes = _build_report_pdf_bytes(report)
    except Exception:
        pdf_bytes = None
    if pdf_bytes:
        filename = f"FR-{report.report_id_PK:05d}_{report.report_period}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    # Fallback: the stored workbook.
    if not report.file_path:
        return HttpResponse("Report file not found.", status=404)

    full_path = os.path.join(settings.MEDIA_ROOT, report.file_path)
    if not os.path.exists(full_path):
        # Historical reports may reference files lost between deploys;
        # regenerate from the report period before giving up.
        try:
            _regenerate_report_file(report)
        except Exception:
            pass
        if not os.path.exists(full_path):
            return HttpResponse("Report file not found on disk.", status=404)

    with open(full_path, "rb") as f:
        data = f.read()

    filename = os.path.basename(report.file_path)
    response = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# ==========================================================================
# PRESIDENT: Approve / Reject Fund Reports
# ==========================================================================

@require_GET
def president_fund_reports_list(request: HttpRequest):
    """Reports verified by the Auditor awaiting President final approval,
    plus recently finalized ones for history."""
    guard = require_role(request, role="President")
    if guard is not None:
        return guard

    reports = OrganizationFundReport.objects.exclude(
        report_status__in=["Draft", "Submitted"]
    ).order_by("-created_at")
    data = []
    for r in reports:
        data.append({
            "report_id": r.report_id_PK,
            "period": r.report_period,
            "report_type": r.report_type,
            "status": r.report_status,
            "file_path": r.file_path,
            "prepared_by": r.prepared_by_user_id_FK.full_name if r.prepared_by_user_id_FK else "",
            "verified_by": r.auditor_verified_by_user_id_FK.full_name if r.auditor_verified_by_user_id_FK else "",
            "verified_at": r.auditor_verified_at.isoformat() if r.auditor_verified_at else "",
            "approved_by": r.approved_by_user_id_FK.full_name if r.approved_by_user_id_FK else "",
            "approved_at": r.approved_at.isoformat() if r.approved_at else "",
            "return_reason": r.return_reason or "",
            "report_title": r.report_title or "",
            "report_filters": r.report_filters or "",
            "report_rows": r.report_rows or "",
            "created_at": r.created_at.isoformat(),
        })
    return JsonResponse({"ok": True, "reports": data})


@require_POST
def president_approve_fund_report(request: HttpRequest, report_id: int):
    guard = require_role(request, role="President")
    if guard is not None:
        return guard
    guard = check_zero_trust(request, level="approve")
    if guard is not None:
        return guard

    officer_id = request.session.get("officer_id")
    try:
        officer = OfficerUser.objects.get(user_id_PK=int(officer_id))
    except OfficerUser.DoesNotExist:
        return JsonResponse({"error": "Officer not found."}, status=400)

    report = get_object_or_404(OrganizationFundReport, pk=report_id)
    if report.report_status not in ("Auditor Verified", "Submitted"):
        return JsonResponse({"error": "Only Auditor Verified reports can be approved."}, status=400)

    report.report_status = "Approved"
    report.approved_by_user_id_FK = officer
    report.approved_at = timezone.now()
    report.save(update_fields=["report_status", "approved_by_user_id_FK", "approved_at", "updated_at"])

    # File the approved report into the Treasurer's and President's Document
    # Repositories so it is viewable/downloadable from each dashboard.
    _archive_approved_report_document(report, officer)

    return JsonResponse({"ok": True, "status": report.report_status})


@require_POST
def president_reject_fund_report(request: HttpRequest, report_id: int):
    guard = require_role(request, role="President")
    if guard is not None:
        return guard
    guard = check_zero_trust(request, level="approve")
    if guard is not None:
        return guard

    remarks = (request.POST.get("remarks") or "").strip()

    report = get_object_or_404(OrganizationFundReport, pk=report_id)
    if report.report_status not in ("Auditor Verified", "Submitted"):
        return JsonResponse({"error": "Only Auditor Verified reports can be rejected."}, status=400)

    report.report_status = "Rejected"
    report.return_reason = remarks or report.return_reason
    report.save(update_fields=["report_status", "return_reason", "updated_at"])

    from core_system.shared_view_utils import _record_audit_trail
    _record_audit_trail(
        table="organization_fund_report",
        record_id=report.report_id_PK,
        action="REJECTED_BY_PRESIDENT",
        actor=officer,
        ip=request.META.get("REMOTE_ADDR"),
        notes=f"Fund report {report.report_period} rejected by President: {remarks or '(no remarks)'}",
    )
    return JsonResponse({"ok": True, "status": report.report_status})


# ==========================================================================
# REPORT CONTENT (shared by Treasurer / Auditor / President sheet preview)
# ==========================================================================

@require_GET
def fund_report_workflow_counts(request: HttpRequest):
    """Pending counts for the report workflow notification dots:
    Treasurer (returned/rejected) -> Auditor (submitted) -> President (verified)."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard
    return JsonResponse({
        "ok": True,
        "submitted": OrganizationFundReport.objects.filter(report_status="Submitted").count(),
        "auditor_verified": OrganizationFundReport.objects.filter(report_status="Auditor Verified").count(),
        "returned": OrganizationFundReport.objects.filter(report_status="Returned for Revision").count(),
        "rejected": OrganizationFundReport.objects.filter(report_status="Rejected").count(),
    })


@require_GET
def fund_report_data(request: HttpRequest, report_id: int):
    """Live financial content behind a fund report — used by the official
    sheet preview so reviewers see actual numbers, not just metadata."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    report = get_object_or_404(OrganizationFundReport, pk=report_id)
    data = _fund_report_financials(report)
    if data is None:
        return JsonResponse({"error": "Invalid report period."}, status=400)
    data["ok"] = True
    # Custom report content (Reports Management) — the sheet renderers and the
    # PDF builder prefer this when present.
    data["report_title"] = report.report_title or ""
    data["report_filters"] = report.report_filters or ""
    if report.report_rows:
        try:
            parsed = json.loads(report.report_rows)
            # Summary-only reports (Monthly Deduction Summary, Masterlist, …)
            # store no flat rows — summary/sections alone are still custom
            # content and must reach the sheet renderers.
            if isinstance(parsed, dict) and (parsed.get("rows") or parsed.get("summary") or parsed.get("sections")):
                data["report_rows"] = parsed
        except (ValueError, TypeError):
            pass
    return JsonResponse(data)


def _fund_report_financials(report):
    import pytz
    from datetime import date, datetime

    from core_system.models import (
        Contribution, FundTransaction, MonthlyDues,
        MonthlyAssessment, MemberAssessment,
    )

    period_range = resolve_report_range_from_period(report.report_period)
    if period_range is None:
        return None
    period_start, period_end, _ = period_range

    start_dt = pytz.UTC.localize(datetime.combine(period_start, datetime.min.time()))
    end_dt = pytz.UTC.localize(datetime.combine(period_end, datetime.max.time().replace(microsecond=0)))

    transactions = FundTransaction.objects.filter(
        recorded_at__gte=start_dt,
        recorded_at__lte=end_dt,
    ).select_related("recorded_by_user_id_FK").order_by("recorded_at")

    inflows = [t for t in transactions if t.direction == "inflow"]
    outflows = [t for t in transactions if t.direction == "outflow"]

    contributions = Contribution.objects.filter(
        payment_date__gte=period_start,
        payment_date__lte=period_end,
        status__in=["PAID", "RECORDED", "PENDING_VERIFICATION"],
    ).select_related("member_id_FK", "aid_tracking_post_id_FK").order_by("payment_date")

    # Monthly dues matched by the month they COVER (YYYY-MM), regardless of
    # when the fund_transaction entry was recorded — this is what the
    # treasurer's Monthly Dues Summary shows for the same period. A weekly
    # report covers the month containing that week; a yearly report covers
    # every month of the year.
    dues = MonthlyDues.objects.filter(
        month_covered__in=months_covered_by(period_start, period_end),
    ).exclude(payment_status__iexact="rejected").select_related("member_id_FK").order_by("member_id_FK__full_name")

    dues_rows = [{
        "member": d.member_id_FK.full_name if d.member_id_FK else "",
        "month": d.month_covered,
        "amount": float(d.amount),
        "method": d.payment_method or "",
        "status": d.payment_status or "",
    } for d in dues]
    dues_total = sum(r["amount"] for r in dues_rows)

    # Outstanding balances for the covered months — mirrors the "Outstanding
    # Balances" sheet of the Excel workbook: every member deduction row in
    # the period's assessment batches, with what is still uncollected.
    month_starts = [
        date(int(ym[:4]), int(ym[5:7]), 1) for ym in months_covered_by(period_start, period_end)
    ]
    period_assessments = MonthlyAssessment.objects.filter(month__in=month_starts).exclude(
        status__in=[MonthlyAssessment.STATUS_REJECTED, MonthlyAssessment.STATUS_RETURNED]
    )
    outstanding_mas = (
        MemberAssessment.objects.filter(assessment_id_FK__in=period_assessments)
        .select_related("member_id_FK", "assessment_id_FK")
        .order_by("member_id_FK__full_name", "assessment_id_FK__month")
    )
    outstanding_rows = [{
        "member": ma.member_id_FK.full_name if ma.member_id_FK else "",
        "month": ma.assessment_id_FK.month_label,
        "expected": float(ma.standard_assessment),
        "recorded": float(ma.actual_deduction),
        "outstanding": float(ma.outstanding_balance),
        "status": ma.get_status_display(),
    } for ma in outstanding_mas]
    total_outstanding = sum(r["outstanding"] for r in outstanding_rows)

    def tx_rows(rows):
        return [{
            "date": str(t.recorded_at.date()) if t.recorded_at else "",
            "source_type": t.get_source_type_display() or "",
            "amount": float(t.amount),
            "description": t.description or "",
            "recorded_by": t.recorded_by_user_id_FK.full_name if t.recorded_by_user_id_FK else "",
        } for t in rows]

    contrib_rows = [{
        "date": str(c.payment_date) if c.payment_date else "",
        "member": c.member_id_FK.full_name if c.member_id_FK else "",
        "post": c.aid_tracking_post_id_FK.post_id_PK if c.aid_tracking_post_id_FK else "",
        "aid_type": c.aid_tracking_post_id_FK.aid_type if c.aid_tracking_post_id_FK else "",
        "expected": float(c.expected_amount),
        "paid": float(c.paid_amount),
        "status": c.status,
    } for c in contributions]

    total_in = sum(float(t.amount) for t in inflows)
    total_out = sum(float(t.amount) for t in outflows)

    # Aid sheets — actual disbursements in the period plus the running
    # set-aside reserve behind them (mirrors sheets 8 and 9 of the workbook).
    aid_payouts = build_aid_payout_rows(start_dt, end_dt)
    aid_setaside_summary, aid_setaside_detail = build_aid_setaside_rows()

    return {
        "period": report.report_period,
        "report_type": report.report_type,
        "total_inflow": total_in,
        "total_outflow": total_out,
        "net": total_in - total_out,
        "total_contributions": sum(float(c.paid_amount) for c in contributions),
        "total_dues": dues_total,
        "transaction_count": len(transactions),
        "dues_count": len(dues_rows),
        "total_outstanding": total_outstanding,
        "outstanding_count": len(outstanding_rows),
        "total_aid_payout": sum(r["paid"] for r in aid_payouts),
        "aid_payout_count": len(aid_payouts),
        "inflows": tx_rows(inflows),
        "outflows": tx_rows(outflows),
        "contributions": contrib_rows,
        "dues": dues_rows,
        "outstanding": outstanding_rows,
        "aid_payouts": aid_payouts,
        "aid_setaside_summary": aid_setaside_summary,
        "aid_setaside_detail": aid_setaside_detail,
    }


_MONTH_WORDS = ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"]


def _period_words(period):
    """Human label for a stored report period.

    '2026-09' -> 'September 2026', '2026-09-W2' -> 'Week 2 of September 2026',
    '2026' -> '2026' (falls back to the raw value).
    """
    text = str(period or "")
    week = ""
    if "-W" in text:
        text, _, week = text.rpartition("-W")
    parts = text.split("-")
    try:
        if len(parts) == 2:
            label = f"{_MONTH_WORDS[int(parts[1]) - 1]} {parts[0]}"
        elif len(parts) == 1 and parts[0]:
            label = parts[0]
        else:
            return str(period or "")
        if week:
            return f"Week {week} of {label}"
        return label
    except (ValueError, TypeError, IndexError):
        return str(period or "")


def _build_report_pdf_bytes(report):
    """Render the official fund report as a PDF — mirrors the View Sheet
    preview (same content and styling). Returns bytes, or None when the
    period is invalid."""
    from io import BytesIO
    from xml.sax.saxutils import escape as xml_escape

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.units import mm
    from reportlab.platypus import (HRFlowable, Image, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)

    data = _fund_report_financials(report)
    if data is None:
        return None
    data["report_title"] = report.report_title or ""
    data["report_filters"] = report.report_filters or ""
    if report.report_rows:
        try:
            parsed = json.loads(report.report_rows)
            # Reports without a detail table (summary-only, e.g. Financial
            # Transparency Summary) still render from summary/sections.
            if isinstance(parsed, dict) and (parsed.get("rows") or parsed.get("summary") or parsed.get("sections")):
                data["report_rows"] = parsed
        except (ValueError, TypeError):
            pass
    green = colors.HexColor("#1e5c38")
    ink = colors.HexColor("#1a1a1a")
    period_words = _period_words(report.report_period)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=14 * mm, bottomMargin=14 * mm, leftMargin=16 * mm, rightMargin=16 * mm,
        title=f"ISUCauFA, Inc. {str(data['report_type']).upper()} Fund Report - {period_words}",
        author="ISUCauFA, Inc.",
    )

    serif = "Times-Roman"
    serif_b = "Times-Bold"
    peso_symbol = "P "
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        font_pairs = [
            (r"C:\Windows\Fonts\times.ttf", r"C:\Windows\Fonts\timesbd.ttf"),
            (r"C:\Windows\Fonts\georgia.ttf", r"C:\Windows\Fonts\georgiab.ttf"),
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
        ]
        for reg_path, bold_path in font_pairs:
            try:
                if os.path.exists(reg_path) and os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont("RptSerif", reg_path))
                    pdfmetrics.registerFont(TTFont("RptSerifBold", bold_path))
                    serif, serif_b = "RptSerif", "RptSerifBold"
                    break
            except Exception:
                continue
    except Exception:
        pass

    center = ParagraphStyle("c", alignment=TA_CENTER, fontName=serif, fontSize=16, leading=19, textColor=ink)
    center_small = ParagraphStyle("cs", parent=center, fontSize=11, leading=14)
    center_title = ParagraphStyle("ct", parent=center, fontName=serif_b, fontSize=14, leading=17, spaceBefore=12)
    center_meta = ParagraphStyle("cm", parent=center_small, fontSize=11, textColor=colors.HexColor("#333333"), spaceBefore=3)
    sec_cell = ParagraphStyle("secc", fontName=serif_b, fontSize=9.5, leading=12, textColor=colors.white)
    # Report tables: TEXT left, NUMERICALS right (matches the on-screen
    # sheets); amount columns use cell_right.
    cell = ParagraphStyle("cell", fontName=serif, fontSize=9, leading=11.5, alignment=TA_LEFT)
    cell_right = ParagraphStyle("cellr", parent=cell, alignment=TA_RIGHT)
    cell_strong = ParagraphStyle("cells", parent=cell, fontName=serif_b)
    meta_k = ParagraphStyle("mk", fontName=serif_b, fontSize=10, leading=13)
    meta_v = ParagraphStyle("mv", fontName=serif, fontSize=10, leading=13)

    def esc(v):
        # Keep every custom report value readable on cPanel fonts that render
        # the Unicode peso glyph as a black square.
        return xml_escape(str(v if v is not None else "").replace("₱", "P "))

    import re as _re

    def clean_filters(v):
        s = str(v or "").strip()
        if not s or s.lower() == "none":
            return ""
        s = _re.sub(r"\bdate:\s*", "", s, flags=_re.I)
        s = _re.sub(r"\s*\+\s*None\b", "", s, flags=_re.I)
        s = s.replace(" + ", ", ")
        s = _re.sub(r"(\d{4})-(\d{1,2})-(\d{1,2})", lambda m: f"{_MONTH_WORDS[int(m.group(2)) - 1]} {int(m.group(3))}, {m.group(1)}", s)
        return s.strip()

    def section(title_text):
        t = Table([[Paragraph(esc(title_text).upper(), sec_cell)]], colWidths=[178 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), green),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    def meta_table(rows):
        t = Table(
            [[Paragraph(f"<b>{esc(k)}</b>", meta_k), Paragraph(esc(v), meta_v)] for k, v in rows],
            colWidths=[62 * mm, 116 * mm],
        )
        t.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb"), "butt", (1, 2)),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return t

    def styled_table(headers, rows, widths, right_cols=(), strong_rows=()):
        body = [[Paragraph(esc(h), cell_strong) for h in headers]]
        for ri, r in enumerate(rows):
            st = cell_strong if ri in strong_rows else cell
            body.append([
                Paragraph(esc(c), cell_right if i in right_cols else st)
                for i, c in enumerate(r)
            ])
        if len(body) == 1:
            body.append([Paragraph("No records for this period.", cell)] + [""] * (len(headers) - 1))
        t = Table(body, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8efe9")),
            ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#333333")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ] + [("BACKGROUND", (0, ri + 1), (-1, ri + 1), colors.HexColor("#eef5ee")) for ri in strong_rows]))
        return t

    def peso(n):
        return peso_symbol + f"{float(n or 0):,.2f}"

    prepared_by = report.prepared_by_user_id_FK.full_name if report.prepared_by_user_id_FK else ""
    verified_by = report.auditor_verified_by_user_id_FK.full_name if report.auditor_verified_by_user_id_FK else ""
    approved_by = report.approved_by_user_id_FK.full_name if report.approved_by_user_id_FK else ""

    def capped(rows, formatter, cap=15):
        shown = rows[:cap]
        return [formatter(r) for r in shown], len(rows) - len(shown)

    inflow_rows, inflow_extra = capped(data["inflows"], lambda t: [t["date"], t["source_type"], t["description"] or t["recorded_by"] or "-", peso(t["amount"])])
    outflow_rows, outflow_extra = capped(data["outflows"], lambda t: [t["date"], t["source_type"], t["description"] or t["recorded_by"] or "-", peso(t["amount"])])
    contrib_rows, contrib_extra = capped(data["contributions"], lambda c: [c["date"], c["member"], c["aid_type"] or "-", peso(c["expected"]), peso(c["paid"]), c["status"]])
    dues_rows, dues_extra = capped(data["dues"], lambda d: [d["member"], _period_words(d["month"]), peso(d["amount"]), d["method"] or "-", d["status"]])
    outstanding_rows, outstanding_extra = capped(data["outstanding"], lambda o: [o["member"], o["month"], peso(o["expected"]), peso(o["recorded"]), peso(o["outstanding"]), o["status"]])
    aid_payout_rows, aid_payout_extra = capped(
        data["aid_payouts"],
        lambda p: [p["date"], p["aid_type"], p["reference"], p["recipient"] or "-",
                   peso(p["approved"]) if p["approved"] is not None else "-",
                   peso(p["paid"]),
                   peso(p["variance"]) if p["variance"] is not None else "-",
                   p["disbursement"], p["released_by"]],
    )
    aid_setaside = data["aid_setaside_summary"]
    aid_setaside_rows = [
        [r["aid_type"], str(r["posts"]), peso(r["setaside_collected"]),
         peso(r["setaside_released"]), peso(r["remaining"]),
         peso(r["from_general_fund"]), peso(r["members_still_owe"])]
        for r in aid_setaside
    ]
    aid_setaside_extra = len(data["aid_setaside_detail"])

    summary_meta = meta_table([
        ("Prepared By (Treasurer)", prepared_by or "-"),
        ("Verified By (Auditor)", verified_by or "-"),
        ("Status", report.report_status or "-"),
    ])

    fs_rows = [
        ("Total Inflows", peso(data["total_inflow"]), False),
        ("Total Outflows", peso(data["total_outflow"]), False),
        ("Net Fund Position", peso(data["net"]), True),
        ("Total Contributions Collected", peso(data["total_contributions"]), False),
        ("Monthly Dues Collected (covered month)", f"{peso(data['total_dues'])} ({data['dues_count']} record(s))", False),
        ("Total Outstanding Balance", peso(data["total_outstanding"]), False),
        ("Aid Disbursed This Period", peso(data["total_aid_payout"]), False),
        ("Aid Set-Aside Reserve Remaining", peso(aid_setaside[-1]["remaining"]), False),
        ("Number of Transactions", str(data["transaction_count"]), False),
    ]
    fund_summary_rows = []
    for k, v, strong in fs_rows:
        kst = meta_k if strong else cell
        vst = meta_k if strong else cell_right
        fund_summary_rows.append([
            Paragraph(f"<b>{esc(k)}</b>" if strong else esc(k), kst),
            Paragraph(f"<b>{esc(v)}</b>" if strong else esc(v), vst),
        ])
    fund_summary = Table(fund_summary_rows, colWidths=[95 * mm, 83 * mm], hAlign="LEFT")
    fund_summary.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#333333")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))

    # Signatory boxes — approved guide design: three side-by-side bordered
    # cells, "Prepared by:/Verified by:/Approved by:" label top-left, blank
    # signature space, bold printed name, officer title under the name.
    sig_label_style = ParagraphStyle("slbl", fontName=serif, fontSize=9, leading=12, textColor=ink)
    sig_name_style = ParagraphStyle("sn", alignment=TA_CENTER, fontName=serif_b, fontSize=10.5, leading=13)
    sig_role_style = ParagraphStyle("sr", alignment=TA_CENTER, fontName=serif, fontSize=9, leading=12, textColor=ink)

    def _sig_cell(label, name, role):
        return [
            Paragraph(esc(label), sig_label_style),
            Spacer(1, 11 * mm),
            Paragraph(esc(name) if name else "&nbsp;", sig_name_style),
            Paragraph(esc(role), sig_role_style),
        ]

    signatures = Table(
        [[
            _sig_cell("Prepared by:", prepared_by, "Treasurer, ISUCauFA"),
            _sig_cell("Verified by:", verified_by, "Auditor, ISUCauFA"),
            _sig_cell("Approved by:", approved_by, "President, ISUCauFA"),
        ]],
        colWidths=[59.4 * mm, 59.4 * mm, 59.4 * mm],
    )
    signatures.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#b7c4ba")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    note = ParagraphStyle("note", fontName=serif, fontSize=8.5, leading=11, textColor=colors.HexColor("#555555"))

    def extra_note(count):
        return Paragraph(f"+ {count} more record(s) in this period.", note)

    custom = data.get("report_rows") or {}
    story = []
    # Official letterhead — matches the deduction letter + sheet PDF: seals at
    # the sides, Republic line / green university name / association line /
    # address at the center. Flattened seal images (white background) avoid
    # reportlab rendering PNG transparency as black.
    try:
        isu_path = os.path.join(str(settings.BASE_DIR), "static", "img", "isu_official_seal_flat.png")
        caufa_path = os.path.join(str(settings.BASE_DIR), "static", "img", "isu_caufa_seal_flat.png")
        if not os.path.exists(isu_path):
            isu_path = os.path.join(str(settings.BASE_DIR), "static", "img", "isu_official.png")
        if not os.path.exists(caufa_path):
            caufa_path = os.path.join(str(settings.BASE_DIR), "static", "img", "isu_caufa_official.png")
        left_img = Image(isu_path, width=20 * mm, height=20 * mm) if os.path.exists(isu_path) else Paragraph("", cell)
        right_img = Image(caufa_path, width=20 * mm, height=20 * mm) if os.path.exists(caufa_path) else Paragraph("", cell)
        univ_name = ParagraphStyle("univ", alignment=TA_CENTER, fontName=serif_b, fontSize=16, leading=19, textColor=colors.HexColor("#2d5016"))
        assoc_name = ParagraphStyle("assoc", alignment=TA_CENTER, fontName=serif_b, fontSize=11, leading=13, textColor=colors.HexColor("#2d5016"))
        rep_line = ParagraphStyle("repline", alignment=TA_CENTER, fontName=serif_b, fontSize=9, leading=11, textColor=colors.HexColor("#2d5016"))
        addr_line = ParagraphStyle("addrline", alignment=TA_CENTER, fontName=serif, fontSize=8.5, leading=10.5, textColor=colors.HexColor("#444444"))
        header = Table(
            [[
                left_img,
                [
                    Paragraph("REPUBLIC OF THE PHILIPPINES", rep_line),
                    Spacer(1, 3),
                    Paragraph("ISABELA STATE UNIVERSITY&nbsp;&nbsp;CAUAYAN", univ_name),
                    Paragraph("FACULTY ASSOCIATION (ISUCauFA)", assoc_name),
                    Spacer(1, 3),
                    Paragraph("18 Dacanay Street, Barangay San Fermin, Cauayan City, Isabela, 3305, Philippines", addr_line),
                ],
                right_img,
            ]],
            colWidths=[28 * mm, 122 * mm, 28 * mm],
        )
        header.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ]))
        story.append(header)
        story.append(Spacer(1, 5))
    except Exception:
        pass

    if custom:
        # Custom report from Reports Management — render its own title,
        # filters and records instead of the organization-wide summary.
        head_cells = [str(h) for h in (custom.get("headers") or [])]
        body_cells = [[str(c) for c in row] for row in (custom.get("rows") or [])]
        right_idx = {
            i for i, h in enumerate(head_cells)
            if str(h).strip().lower() in {"amount", "expected", "paid", "required", "inflow", "outflow", "balance", "benefit", "collected", "deducted", "owed"}
        }
        doc_title = str(data.get("report_title") or "Custom Report").upper()
        col_count = max(1, len(head_cells))
        col_w = 178 * mm / col_count
        custom_period = _period_words(report.report_period) if report.report_period else ""
        custom_filters = clean_filters(report.report_filters)
        story += [
            Paragraph(esc(doc_title), center_title),
            Spacer(1, 4),
            Paragraph(
                esc(
                    "Reporting Period: " + (custom_period or str(report.report_period or "All Time"))
                    + ("  ·  Filters: " + custom_filters if custom_filters else "")
                ),
                center_meta,
            ),
            Spacer(1, 8),
        ]
        # Summary cards — same values the Treasurer previewed. Strong rows
        # (e.g. "Current Balance") render bold on the #eef5ee tint, matching
        # the on-screen sheet.
        summary_rows = custom.get("summary") or []
        if summary_rows:
            # NOTE: Table.setStyle() returns None in reportlab 4.x — never
            # chain it inline into the story or the table silently vanishes.
            summary_table = Table(
                [
                    [
                        Paragraph(esc(s[0]), cell_strong if len(s) > 2 and s[2] else cell),
                        Paragraph(esc(s[1]), cell_right),
                    ]
                    for s in summary_rows
                ],
                colWidths=[100 * mm, 78 * mm], hAlign="LEFT",
            )
            strong_idx = [i for i, s in enumerate(summary_rows) if len(s) > 2 and s[2]]
            summary_table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#333333")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ] + [("BACKGROUND", (0, i + 1), (-1, i + 1), colors.HexColor("#eef5ee")) for i in strong_idx]))
            story += [
                section("Summary"),
                Spacer(1, 6),
                summary_table,
                Spacer(1, 4),
            ]
        # Group sections (Collections / Disbursements / By Type … / Monthly
        # Dues Coverage / per-department member tables / 2-column count
        # summaries). A section may carry custom "headers" — use them when
        # provided; right-align numeric columns only.
        for gsec in (custom.get("sections") or []):
            raw_rows = gsec.get("rows") or []
            heads = [str(h) for h in (gsec.get("headers") or [])]
            # Strong (TOTAL) row indices — parallel "strong" array saved by the
            # Treasurer's submission; absent on older records, which render
            # with no highlighted rows.
            strong_flags = [bool(f) for f in (gsec.get("strong") or [])]

            def build_rows(ncols):
                rows, strong_rows = [], []
                for ri, r in enumerate(raw_rows):
                    if isinstance(r, (list, tuple)) and len(r) >= ncols:
                        rows.append([str(c) for c in list(r)[:ncols]])
                        if ri < len(strong_flags) and strong_flags[ri]:
                            strong_rows.append(len(rows) - 1)
                return rows, tuple(strong_rows)

            title = section(str(gsec.get("title") or "Summary"))
            if len(heads) == 2:
                g_rows, strong_rows = build_rows(2)
                story += [
                    title,
                    Spacer(1, 6),
                    styled_table(heads, g_rows, [118 * mm, 60 * mm], right_cols=(1,), strong_rows=strong_rows),
                    Spacer(1, 4),
                ]
            elif len(heads) >= 3:
                # Wide sections (Fund Overview month table, transactions, …):
                # equal column widths, a wider Details/Description column when
                # present, amount columns right-aligned.
                ncols = len(heads)
                g_rows, strong_rows = build_rows(ncols)
                right_cols = tuple(
                    i for i, h in enumerate(heads)
                    if re.search(r"amount|expected|collected|deducted|paid|money in|money out|fund growth|fund balance|balance", str(h), re.I)
                )
                wide_idx = next(
                    (i for i, h in enumerate(heads) if re.search(r"details|description", str(h), re.I)),
                    None,
                )
                if wide_idx is not None and ncols > 1:
                    # Widths are in mm — bare floats would be read as points
                    # and shrink the table to a third of the page width.
                    other_w = (178 - 70) / (ncols - 1)
                    col_widths = [other_w * mm] * ncols
                    col_widths[wide_idx] = (178 - (other_w * (ncols - 1))) * mm
                else:
                    col_widths = [(178 / ncols) * mm] * ncols
                story += [
                    title,
                    Spacer(1, 6),
                    styled_table(heads, g_rows, col_widths, right_cols=right_cols, strong_rows=strong_rows),
                    Spacer(1, 4),
                ]
            else:
                g_rows, strong_rows = build_rows(3)
                story += [
                    title,
                    Spacer(1, 6),
                    styled_table(["Category", "Count", "Amount"], g_rows, [88 * mm, 30 * mm, 60 * mm], right_cols=(1, 2), strong_rows=strong_rows),
                    Spacer(1, 4),
                ]
        if head_cells:
            story += [
                section("Records"),
                Spacer(1, 6),
                styled_table(head_cells, body_cells, [col_w] * col_count, right_cols=right_idx),
            ]
        total_label = str(custom.get("total_label") or "")
        if total_label:
            story += [Spacer(1, 4), Paragraph(f"<b>{esc(total_label)}</b>", meta_k)]
        # Signature lines only — no green section bar above them.
        story += [signatures]
        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

    # Same official letterhead as the deduction sheet / custom reports.
    isu_path = os.path.join(str(settings.BASE_DIR), "static", "img", "isu_official_seal_flat.png")
    caufa_path = os.path.join(str(settings.BASE_DIR), "static", "img", "isu_caufa_seal_flat.png")
    if not os.path.exists(isu_path):
        isu_path = os.path.join(str(settings.BASE_DIR), "static", "img", "isu_official.png")
    if not os.path.exists(caufa_path):
        caufa_path = os.path.join(str(settings.BASE_DIR), "static", "img", "isu_caufa_official.png")
    rep_line = ParagraphStyle("repline2", alignment=TA_CENTER, fontName=serif_b, fontSize=9, leading=11, textColor=colors.HexColor("#2d5016"))
    univ_name2 = ParagraphStyle("univname2", alignment=TA_CENTER, fontName=serif_b, fontSize=16, leading=19, textColor=colors.HexColor("#2d5016"))
    assoc_name2 = ParagraphStyle("assocname2", alignment=TA_CENTER, fontName=serif_b, fontSize=11, leading=13, textColor=colors.HexColor("#2d5016"))
    addr_line2 = ParagraphStyle("addrline2", alignment=TA_CENTER, fontName=serif, fontSize=8.5, leading=10.5, textColor=colors.HexColor("#444444"))
    header_cells = [
        Image(isu_path, width=20 * mm, height=20 * mm) if os.path.exists(isu_path) else Paragraph("", center_small),
        [
            Paragraph("REPUBLIC OF THE PHILIPPINES", rep_line),
            Spacer(1, 3),
            Paragraph("ISABELA STATE UNIVERSITY&nbsp;&nbsp;CAUAYAN", univ_name2),
            Paragraph("FACULTY ASSOCIATION (ISUCauFA)", assoc_name2),
            Spacer(1, 3),
            Paragraph("18 Dacanay Street, Barangay San Fermin, Cauayan City, Isabela, 3305, Philippines", addr_line2),
        ],
        Image(caufa_path, width=20 * mm, height=20 * mm) if os.path.exists(caufa_path) else Paragraph("", center_small),
    ]
    generic_header = Table([[header_cells]], colWidths=[28 * mm, 122 * mm, 28 * mm])
    generic_header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
    ]))
    story += [
        generic_header,
        Spacer(1, 5),
        HRFlowable(width="100%", thickness=1.4, color=ink, spaceAfter=1.5),
        HRFlowable(width="100%", thickness=0.6, color=ink, spaceAfter=0),
        Paragraph(str(data['report_type']).upper() + " ORGANIZATION FUND REPORT", center_title),
        Paragraph("Period: " + period_words, center_meta),
        Spacer(1, 8),
        section("Summary"),
        Spacer(1, 6),
        summary_meta,
        section("Fund Summary"),
        Spacer(1, 6),
        fund_summary,
        section("Inflows"),
        Spacer(1, 6),
        styled_table(["Date", "Source", "Description", "Amount"], inflow_rows, [24 * mm, 30 * mm, 90 * mm, 34 * mm], right_cols=(3,)),
    ] + ([extra_note(inflow_extra)] if inflow_extra else []) + [
        section("Outflows"),
        Spacer(1, 6),
        styled_table(["Date", "Source", "Description", "Amount"], outflow_rows, [24 * mm, 30 * mm, 90 * mm, 34 * mm], right_cols=(3,)),
    ] + ([extra_note(outflow_extra)] if outflow_extra else []) + [
        section("Contributions"),
        Spacer(1, 6),
        styled_table(["Date", "Member", "Aid Type", "Expected", "Paid", "Status"], contrib_rows, [24 * mm, 46 * mm, 32 * mm, 25 * mm, 25 * mm, 26 * mm], right_cols=(3, 4)),
    ] + ([extra_note(contrib_extra)] if contrib_extra else []) + [
        section("Monthly Dues"),
        Spacer(1, 6),
        styled_table(["Member", "Month Covered", "Amount", "Method", "Status"], dues_rows, [50 * mm, 34 * mm, 26 * mm, 34 * mm, 34 * mm], right_cols=(2,)),
    ] + ([extra_note(dues_extra)] if dues_extra else []) + [
        section("Outstanding Balances"),
        Spacer(1, 6),
        styled_table(
            ["Member", "Month", "Expected", "Recorded", "Outstanding", "Status"],
            outstanding_rows,
            [40 * mm, 28 * mm, 24 * mm, 24 * mm, 28 * mm, 32 * mm],
            right_cols=(2, 3, 4),
        ),
    ] + ([extra_note(outstanding_extra)] if outstanding_extra else []) + [
        section("Aid Payouts by Claim"),
        Spacer(1, 6),
        styled_table(
            ["Date", "Aid Type", "Reference", "Recipient", "Approved", "Disbursed", "Variance", "Disbursed From", "Released By"],
            aid_payout_rows,
            [18 * mm, 22 * mm, 18 * mm, 32 * mm, 18 * mm, 18 * mm, 16 * mm, 16 * mm, 20 * mm],
            right_cols=(4, 5, 6),
        ),
    ] + ([extra_note(aid_payout_extra)] if aid_payout_extra else []) + [
        section("Aid Set-Aside Balance"),
        Spacer(1, 6),
        styled_table(
            ["Aid Type", "Claims", "Set-Aside Collected", "Set-Aside Released", "Remaining Reserve", "From General Fund", "Members Still Owe"],
            aid_setaside_rows,
            [40 * mm, 12 * mm, 26 * mm, 26 * mm, 24 * mm, 25 * mm, 25 * mm],
            right_cols=(1, 2, 3, 4, 5, 6),
            strong_rows=(len(aid_setaside_rows) - 1,) if aid_setaside_rows else (),
        ),
        Paragraph(
            f"{aid_setaside_extra} claim(s) reconciled — per-claim detail is in the workbook's \"Aid Set-Aside Balance\" sheet.",
            note,
        ),
        # Signature lines only — no green section bar above them.
        signatures,
    ]

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
def _send_fund_report_email(report):
    if not report.file_path:
        return False

    try:
        from core_system.email_killswitch import is_email_sending_enabled

        if not is_email_sending_enabled():
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "Email kill switch is OFF — fund report email for %s blocked.",
                getattr(report, "report_id_PK", "?"),
            )
            return False
    except Exception:
        pass

    full_path = os.path.join(settings.MEDIA_ROOT, report.file_path)
    if not os.path.exists(full_path):
        return False

    members = Member.objects.exclude(
        membership_status__iexact="Retired"
    ).exclude(email__isnull=True).exclude(email__exact="")

    recipient_emails = list(members.values_list("email", flat=True))
    if not recipient_emails:
        return False

    period_label = report.report_period
    report_type_label = format_report_type_label(report.report_type)

    context = {
        "period": period_label,
        "report_type": report_type_label,
        "prepared_by": report.prepared_by_user_id_FK.full_name if report.prepared_by_user_id_FK else "ISUCauFA, Inc.",
    }

    try:
        html_content = render_to_string("emails/fund_contribution_report.html", context)
    except Exception:
        html_content = (
            f"<p>Dear Member,</p>"
            f"<p>The {report_type_label} Organization Fund Report for {period_label} has been approved and is attached.</p>"
        )

    text_content = (
        f"ISUCauFA, Inc. {report_type_label} Fund Report - {period_label}\n"
        f"Prepared by: {context['prepared_by']}\n"
        "---\n"
        "This email was sent by ISUCauFA, Inc..\n"
    )

    from email.mime.image import MIMEImage
    from pathlib import Path

    from django.core.mail import EmailMultiAlternatives

    # Attach the report as PDF (falls back to the stored workbook only if
    # PDF generation fails for some reason).
    pdf_bytes = None
    try:
        pdf_bytes = _build_report_pdf_bytes(report)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("PDF build failed for fund report %s", report.report_id_PK)

    if pdf_bytes:
        attachment_name = f"FR-{report.report_id_PK:05d}_{report.report_period}.pdf"
        attachment_bytes = pdf_bytes
        attachment_type = "application/pdf"
    else:
        try:
            with open(full_path, "rb") as f:
                attachment_bytes = f.read()
            attachment_name = os.path.basename(report.file_path)
            attachment_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        except OSError:
            attachment_bytes = None

    logo_data = None
    logo_path = Path(settings.BASE_DIR) / "static" / "images" / "isu_caufa_official.png"
    if logo_path.exists():
        logo_data = logo_path.read_bytes()

    # Data privacy: send one email PER MEMBER so no recipient can see the
    # other members' email addresses (nothing is exposed in To/Cc/Bcc).
    import logging
    sent = 0
    for email_addr in recipient_emails:
        try:
            msg = EmailMultiAlternatives(
                subject=f"ISUCauFA, Inc. {report_type_label} Fund Report - {period_label}",
                body=text_content,
                to=[email_addr],
            )
            msg.attach_alternative(html_content, "text/html")
            if attachment_bytes:
                msg.attach(attachment_name, attachment_bytes, attachment_type)
            if logo_data:
                image = MIMEImage(logo_data)
                image.add_header("Content-ID", "<logo_cid>")
                image.add_header("Content-Disposition", "inline", filename="isu_caufa_official.png")
                msg.attach(image)
            msg.send(fail_silently=False)
            sent += 1
        except Exception as exc:
            logging.getLogger(__name__).error("Failed to send fund report email to %s: %s", email_addr, exc)
    return sent > 0
