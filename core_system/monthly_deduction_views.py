"""Monthly deduction assessment workflow.

Additive module implementing:

    President (set assessment + breakdown)
        -> Treasurer (records each member's actual deduction)
        -> Treasurer (deposits the recorded collection: ref + slip, no fund write)
        -> Auditor (verifies the recorded entries + deposit evidence)
        -> President (final approval -> fund reflects + member email notices)

The system auto-allocates each member's deduction across the assessment
breakdown items ordered by priority and tracks the per-item outstanding
balance. This module does not modify any existing dues, payroll, payment,
or fund-ledger flow.
"""

from __future__ import annotations

import json
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.utils import timezone
import re

from django.db import transaction, IntegrityError, DataError
from django.db.models import Q, Sum, Count, Prefetch
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from core_system.constants.policy_constants import get_monthly_dues_amount
from core_system.aid_setaside import (
    book_member_fund_rows,
    delete_member_fund_rows,
    recipient_member_lookup,
)
from core_system.guards import require_role
from core_system.ledger_utils import (
    approved_member_assessments,
    build_member_assessment_breakdown,
    member_balance,
    member_lifetime_owed,
    membership_fee_summary,
)
from core_system.models import (
    AssessmentItem,
    AssessmentWorkflowLog,
    Member,
    MemberAssessment,
    MemberAssessmentAllocation,
    MemberCatchupDue,
    MemberLedger,
    MonthlyAssessment,
    MonthlyAssessmentDocument,
    OfficerUser,
    MedicalAid,
    DeathAid,
    AidTrackingPost,
)
from core_system.services.email_service import flush_email_queue_async, send_html_email_async
import logging

from core_system.services.dues_status import dues_year_containers
from core_system.services.notifications import notify_member, notify_officer

logger = logging.getLogger(__name__)
from core_system.shared_view_utils import _record_audit_trail, resolve_officer_from_session

CENT = Decimal("0.01")
ACTIVE_MEMBERSHIP_STATUSES = ["Permanent", "Temporary"]

# Scanned documents the President attaches to an assessment: the signed
# ISUCauFA request letter and the source deducted-amount sheet. Images only
# so the Treasurer and Auditor can view them directly in the browser.
ASSESSMENT_DOC_KINDS = ("request_letter", "deduction_sheet")
# Treasurer's bank deposit slip: uploaded only via the deposit endpoint (not
# the President's document uploader), images or PDF, and kept forever even
# when the deposit is invalidated — immutable evidence of what was filed.
DEPOSIT_SLIP_KIND = "deposit_slip"
DEPOSIT_SLIP_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
DOC_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DOC_MAX_BYTES = 10 * 1024 * 1024

# Words that belong to a multi-word surname ("Juan Dela Cruz" -> "DELA CRUZ, Juan").
SURNAME_PARTICLES = {
    "de", "dela", "del", "delos", "delas", "los", "las", "la", "san",
    "santa", "sto", "sto.", "santo", "villa", "das", "dos",
}
NAME_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}


def _formatted_name(full_name: str) -> str:
    """Format a stored full name as 'SURNAME, Given Names' for roster display."""
    parts = (full_name or "").strip().split()
    if not parts:
        return ""
    suffix = ""
    while len(parts) > 1 and parts[-1].lower() in NAME_SUFFIXES:
        suffix = f" {parts.pop()}"
    if len(parts) == 1:
        return parts[0].upper() + suffix
    idx = len(parts) - 1
    # Walk the particle chain from the surname side: in "Maria Clara De Los
    # Santos" the surname starts at "De Los", not at "Santos" alone.
    while idx - 1 >= 0 and parts[idx - 1].lower().rstrip(".") in SURNAME_PARTICLES:
        idx -= 1
    surname = " ".join(parts[idx:])
    given = " ".join(parts[:idx])
    return f"{surname.upper()}, {given}{suffix}"

ASSESSMENT_TABLE = "monthly_assessments"
MEMBER_ASSESSMENT_TABLE = "member_assessments"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_body(request: HttpRequest) -> dict:
    """Parse a JSON request body; fall back to empty dict on failure."""
    try:
        payload = json.loads(request.body or "{}")
        return payload if isinstance(payload, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _parse_month(raw_value: str):
    """Convert a 'YYYY-MM' form value to the first day of that month."""
    try:
        return datetime.strptime((raw_value or "").strip(), "%Y-%m").date().replace(day=1)
    except ValueError:
        return None


def _parse_amount(raw_value) -> Decimal | None:
    try:
        amount = Decimal(str(raw_value)).quantize(CENT)
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount >= 0 else None


def _month_date_value(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _audit_safe(value):
    """Coerce Decimals/dates (incl. inside lists/dicts) for JSONField storage."""
    if isinstance(value, dict):
        return {key: _audit_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_audit_safe(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _serialize_item(item: AssessmentItem) -> dict:
    return {
        "item_id": item.item_id_PK,
        "purpose": item.purpose,
        "purpose_label": item.label,
        "custom_label": item.custom_label or "",
        "amount": float(item.amount),
        "recipient": item.recipient or "",
        "recipient_type": getattr(item, "recipient_type", "member") or "member",
        "is_external": getattr(item, "recipient_type", "member") == "external",
        "external_campus": getattr(item, "external_campus", None) or "",
        "external_beneficiary": getattr(item, "external_beneficiary", None) or "",
        "external_display": item.external_display if hasattr(item, "external_display") else (item.recipient or ""),
        "notes": item.notes or "",
        "priority_order": item.priority_order,
    }


def _assessment_images(assessment: MonthlyAssessment) -> dict:
    """Attached scan images grouped by kind, oldest first.

    ``sha256`` travels with each entry so the President's form can refuse a
    re-upload of an already-attached scan the moment it is picked, instead
    of colliding at upload time.
    """
    grouped = {kind: [] for kind in (*ASSESSMENT_DOC_KINDS, DEPOSIT_SLIP_KIND)}
    for doc in assessment.documents.all():
        grouped.setdefault(doc.kind, []).append({
            "id": doc.document_id_PK,
            "url": f"/api/officers/monthly-assessment/documents/{doc.document_id_PK}/file/",
            "name": Path(doc.image.name).name,
            "sha256": doc.content_sha256 or "",
            "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else "",
        })
    return grouped


def _serialize_assessment(assessment: MonthlyAssessment, *, include_items: bool = True) -> dict:
    images = _assessment_images(assessment)
    member_assessments = assessment.member_assessments.all()
    isu_caufa_fund = float(
        MemberAssessmentAllocation.objects.filter(
            assessment_item_id_FK__assessment_id_FK_id=assessment.assessment_id_PK,
            assessment_item_id_FK__purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
        ).aggregate(total=Sum("amount_applied"))["total"] or 0
    )
    data = {
        "assessment_id": assessment.assessment_id_PK,
        "month": _month_date_value(assessment.month),
        "month_label": assessment.month_label,
        "total_amount": float(assessment.total_amount),
        "status": assessment.status,
        "status_label": assessment.get_status_display(),
        "created_by": assessment.created_by_id_FK.full_name if assessment.created_by_id_FK else "",
        "treasurer_remarks": assessment.treasurer_remarks or "",
        "auditor_remarks": assessment.auditor_remarks or "",
        "president_remarks": assessment.president_remarks or "",
        "has_request_letter": bool(images["request_letter"]),
        "request_letter_images": images["request_letter"],
        "has_deduction_sheet": bool(images["deduction_sheet"]),
        "deduction_sheet_images": images["deduction_sheet"],
        "collection_reference": f"COL-{assessment.assessment_id_PK:05d}",
        "deposit_reference": assessment.deposit_reference or "",
        "deposited_amount": float(assessment.deposited_amount) if assessment.deposited_amount is not None else None,
        "deposited_at": assessment.deposited_at.isoformat() if assessment.deposited_at else "",
        "deposited_by": assessment.deposited_by_id_FK.full_name if assessment.deposited_by_id_FK else "",
        "deposit_slips": images.get(DEPOSIT_SLIP_KIND, []),
        "created_at": assessment.created_at.isoformat() if assessment.created_at else "",
        "updated_at": assessment.updated_at.isoformat() if assessment.updated_at else "",
        "recorded_count": assessment.member_assessments.count(),
        "total_recorded": float(
            sum(ma.actual_deduction for ma in member_assessments)
        ),
        "total_outstanding": float(
            sum(ma.outstanding_balance for ma in member_assessments)
        ),
        "isu_caufa_fund": isu_caufa_fund,
    }
    if include_items:
        data["items"] = [_serialize_item(i) for i in assessment.items.all()]

    # How much of the recorded total still has to reach the bank. A batch
    # may be deposited in parts; this drives the deposit form and panels.
    data["remaining_to_deposit"] = (
        max(
            0.0,
            float(data["total_recorded"])
            - float(
                assessment.deposited_amount
                if assessment.deposited_amount is not None
                else Decimal("0.00")
            ),
        )
        if assessment.status == MonthlyAssessment.STATUS_PENDING_DEPOSIT
        else 0.0
    )
    return data


def _serialize_allocation(alloc: MemberAssessmentAllocation, classification: str | None = None) -> dict:
    required = (
        _item_required_amount(alloc.assessment_item_id_FK, classification)
        if classification
        else alloc.assessment_item_id_FK.amount
    )
    return {
        "item_id": alloc.assessment_item_id_FK.item_id_PK,
        "purpose": alloc.assessment_item_id_FK.purpose,
        "purpose_label": alloc.assessment_item_id_FK.label,
        "recipient": alloc.assessment_item_id_FK.recipient or "",
        "priority_order": alloc.assessment_item_id_FK.priority_order,
        "required": float(required),
        "applied": float(alloc.amount_applied),
        "remaining": float(alloc.amount_remaining),
    }


def _serialize_member_assessment(ma: MemberAssessment, *, include_allocations: bool = True) -> dict:
    member = ma.member_id_FK
    classification = (getattr(member, "member_classification", "") or "Teaching")
    data = {
        "member_assessment_id": ma.member_assessment_id_PK,
        "member_id": member.member_id_PK,
        "member_name": _formatted_name(member.full_name),
        "employee_id": member.employee_id or "",
        "department": member.department or "",
        "email": member.email or "",
        "membership_status": member.membership_status or "",
        "classification": classification,
        "is_excluded": bool(ma.is_excluded),
        "standard_assessment": float(ma.standard_assessment),
        "actual_deduction": float(ma.actual_deduction),
        "outstanding_balance": float(ma.outstanding_balance),
        "prior_outstanding": float(ma.prior_outstanding),
        "prior_outstanding_collected": float(ma.prior_outstanding_collected),
        "prior_month_label": ma.prior_month or "",
        "prior_months": _clean_month_entries(ma.prior_months),
        "prior_collected_months": _clean_month_entries(ma.prior_collected_months),
        "change_amount": float(ma.change_amount),
        "status": ma.status,
        "status_label": ma.get_status_display(),
        "recorded_at": ma.recorded_at.isoformat() if ma.recorded_at else "",
        "verified_at": ma.verified_at.isoformat() if ma.verified_at else "",
        "approved_at": ma.approved_at.isoformat() if ma.approved_at else "",
    }
    if include_allocations:
        data["allocations"] = [
            _serialize_allocation(a, classification) for a in ma.allocations.all()
        ]
    return data


def _serialize_workflow_logs(assessment: MonthlyAssessment) -> list[dict]:
    return [
        {
            "log_id": log.pk,
            "action": log.action,
            "performed_by": log.performed_by_id_FK.full_name if log.performed_by_id_FK else "",
            "notes": log.notes or "",
            "created_at": log.created_at.isoformat() if log.created_at else "",
        }
        for log in assessment.workflow_logs.all()
    ]


def _notify_role(role: str, message: str, url: str = "/") -> None:
    """Notify every active officer holding the given role."""
    for officer in OfficerUser.objects.filter(
        role__iexact=role, account_status__iexact="active"
    ):
        notify_officer(
            officer,
            notification_type="Monthly Deduction",
            message=message,
            url=url,
        )


def _invalidate_deposit_evidence(assessment: MonthlyAssessment) -> str:
    """Null the active deposit fields after a reject/return (immutable slips).

    Returns a human-readable deposit label for the workflow log, or an empty
    string when the assessment had no deposit to invalidate. The uploaded
    slip documents are deliberately kept — evidence is never deleted.
    """
    if assessment.deposited_at is None and not assessment.deposit_reference:
        return ""
    label = assessment.deposit_reference or f"deposited {assessment.deposited_at:%Y-%m-%d}"
    assessment.deposit_reference = None
    assessment.deposited_amount = None
    assessment.deposited_at = None
    assessment.deposited_by_id_FK = None
    return label


def _broadcast_deduction_counts() -> None:
    """Push live sidebar badge counts to each dashboard after a workflow step.

    Runs after the current transaction commits so the counts reflect the
    saved state. President sees assessments awaiting final approval, Auditor
    sees entries awaiting verification, Treasurer sees entries sent back to
    them for revision.
    """
    def _push():
        from core_system.shared_view_utils import _broadcast_to_group

        president_count = MonthlyAssessment.objects.filter(
            status=MonthlyAssessment.STATUS_PENDING_FINAL
        ).count()
        auditor_count = MonthlyAssessment.objects.filter(
            status=MonthlyAssessment.STATUS_PENDING_AUDIT
        ).count()
        treasurer_count = MonthlyAssessment.objects.filter(
            status__in=[
                MonthlyAssessment.STATUS_PENDING_TREASURER,
                MonthlyAssessment.STATUS_PENDING_DEPOSIT,
                MonthlyAssessment.STATUS_REJECTED,
                MonthlyAssessment.STATUS_RETURNED,
            ]
        ).count()
        _broadcast_to_group("president_dashboard", {
            "type": "deduction_counts", "pending_final": president_count,
        })
        _broadcast_to_group("auditor_dashboard", {
            "type": "deduction_counts", "pending_audit": auditor_count,
        })
        _broadcast_to_group("treasurer_dashboard", {
            "type": "deduction_counts", "attention": treasurer_count,
        })

    transaction.on_commit(_push)


def _allocate_funds(funds: Decimal, items, required_fn=None) -> tuple[list[tuple[AssessmentItem, Decimal, Decimal]], Decimal]:
    """Allocate funds down the priority list — all or nothing, then stop.

    Items are funded fully in priority order; the first item the remaining
    money cannot fully cover stops the allocation: that item and everything
    after it stay fully outstanding, and the leftover money becomes the
    association funds. Returns
    (allocations, change_leftover) as (item, amount_applied, amount_remaining).

    required_fn(item) may override the per-item required amount (e.g. zero
    out items a member is not obliged to fund).
    """
    remaining = Decimal(str(funds))
    allocations: list[tuple[AssessmentItem, Decimal, Decimal]] = []
    stopped = False
    for item in items:
        required = Decimal(str(required_fn(item) if required_fn else item.amount))
        if not stopped and remaining >= required:
            allocations.append((item, required, Decimal("0.00")))
            remaining -= required
        else:
            # First shortfall stops everything: this item and every later one
            # stay fully outstanding (rows kept so reports show them).
            stopped = True
            allocations.append((item, Decimal("0.00"), required))
    return allocations, remaining.quantize(CENT)


def _catchup_eligible_filter() -> Q:
    """Members who can owe catch-up dues (By-Laws classification rules).

    Retired members owe nothing, so they never belong in the catch-up
    workflow.
    """
    return ~Q(member_classification="Retired") & ~Q(
        membership_status="Retired"
    )


def _catchup_window_keys(joined) -> set[str]:
    """Month keys (``YYYY-MM``) inside the member's catch-up window.

    Legacy rule, kept verbatim: Jan of the join year .. join month inclusive
    (empty for January joiners, who ride the regular roster). Year-container
    extension: months from the current dues container's start through the
    backend dues frontier, so a member enrolled while collections already run
    past their join year still gets every charged month they missed (e.g. a
    September 2026 joiner with dues charged through April 2027 also owes
    January–April 2027 — never months from a closed container's tail such as
    October–December 2026, and never uncharged future months). Empty when no
    month has been charged yet.

    Gated by the Superadmin back-dues chase switch (default OFF per
    client): when disabled, mid-year joiners pay current->future only and
    the window is empty.
    """
    from core_system.dues_backfill_guard import is_back_dues_chase_enabled

    if not is_back_dues_chase_enabled():
        return set()
    keys: set[str] = set()
    if joined:
        if joined.month > 1:
            cursor = date(joined.year, 1, 1)
            join_month = date(joined.year, joined.month, 1)
            while cursor <= join_month:
                keys.add(cursor.strftime("%Y-%m"))
                cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        frontier = (dues_year_containers()["frontier"] or "")
        if frontier:
            container_start = frontier[:4] + "-01"
            year, month = int(container_start[:4]), int(container_start[5:7])
            end_year, end_month = int(frontier[:4]), int(frontier[5:7])
            while (year < end_year) or (year == end_year and month <= end_month):
                key = f"{year}-{month:02d}"
                if key >= container_start:
                    keys.add(key)
                month += 1
                if month > 12:
                    month = 1
                    year += 1
    return keys


def _is_catchup_obligation(joined, month_start, assessment_status, member=None) -> bool:
    """True only for months inside the member's mid-year catch-up window.

    A draft assessment alone does not make a month "catch-up": a January joiner
    with an unpaid August is regular outstanding, not a backfill obligation.
    Mirrors _catchup_window_keys: Jan of join year .. join month inclusive
    (empty for January joiners when nothing was charged yet), plus the
    current dues container through the backend frontier — and only while not
    final-approved. Retired members are never catch-up (they owe no monthly
    dues), so their unpaid months stay "outstanding".
    """
    if assessment_status == MonthlyAssessment.STATUS_FINAL_APPROVED:
        return False
    if member is not None:
        classification = (getattr(member, "member_classification", "") or "Teaching")
        is_retired = classification == "Retired" or (
            getattr(member, "membership_status", "") or ""
        ) == "Retired"
        if is_retired:
            return False
    if not joined or not month_start:
        return False
    try:
        month_key = month_start.strftime("%Y-%m")
    except (AttributeError, TypeError, ValueError):
        return False
    return month_key in _catchup_window_keys(joined)


def _clean_month_entries(months) -> list[dict]:
    """Normalize a stored/derived month list to [{key, label, amount}].

    Drops malformed entries and quantizes amounts to cent precision so the
    result is safe to freeze into a JSONField snapshot. Component splits
    (``dues``/``aid``) ride along when present so the treasurer's
    dues-vs-aid picks keep their identity; entries without a split are
    treated as all-dues downstream (legacy whole-month behaviour).
    """
    cleaned: list[dict] = []
    for entry in months or []:
        if not isinstance(entry, dict):
            continue
        try:
            amount = Decimal(str(entry.get("amount") or 0)).quantize(CENT)
        except (InvalidOperation, TypeError, ValueError):
            continue
        cleaned.append({
            "key": str(entry.get("key") or ""),
            "label": str(entry.get("label") or ""),
            "amount": float(amount),
            "dues": float(_quantize_amount(entry.get("dues", amount))),
            "aid": float(_quantize_amount(entry.get("aid", 0))),
        })
    return cleaned


def _quantize_amount(value) -> Decimal:
    """Best-effort Decimal quantization; unparseable input becomes 0.00."""
    try:
        return Decimal(str(value or 0)).quantize(CENT)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def _split_row_own(row, own: Decimal) -> tuple:
    """Split a row's own new debt into (dues, aid) components.

    Uses the row's item allocations (exact per-item shortfall) when present,
    else the assessment's item amounts (draft rows), else all-dues. Dues
    absorb first so dues + aid always equals ``own`` — the split only ever
    re-labels the total, never changes it.
    """
    dues_remaining = aid_remaining = None
    try:
        allocs = list(row.allocations.all())
    except Exception:
        allocs = []
    if allocs:
        dues_remaining = Decimal("0.00")
        aid_remaining = Decimal("0.00")
        for alloc in allocs:
            item = getattr(alloc, "assessment_item_id_FK", None)
            remaining = _quantize_amount(getattr(alloc, "amount_remaining", 0))
            if item is not None and getattr(item, "purpose", "") == AssessmentItem.PURPOSE_MONTHLY_DUE:
                dues_remaining += remaining
            else:
                aid_remaining += remaining
    else:
        try:
            items = list(row.assessment_id_FK.items.all())
        except Exception:
            items = []
        if items:
            dues_remaining = sum(
                (_quantize_amount(item.amount) for item in items
                 if getattr(item, "purpose", "") == AssessmentItem.PURPOSE_MONTHLY_DUE),
                Decimal("0.00"),
            )
            aid_remaining = sum(
                (_quantize_amount(item.amount) for item in items
                 if getattr(item, "purpose", "") != AssessmentItem.PURPOSE_MONTHLY_DUE),
                Decimal("0.00"),
            )
    if dues_remaining is None:
        return own, Decimal("0.00")
    dues = min(max(dues_remaining, Decimal("0.00")), own)
    return dues.quantize(CENT), (own - dues).quantize(CENT)


def _reduce_open_entry(entry: dict, amount: Decimal, component: str) -> Decimal:
    """Reduce one open-month entry by ``amount``, honouring the component.

    ``component`` is ``""`` (whole month, legacy), ``"dues"`` or ``"aid"``.
    Whole-month reductions take dues first, then aid — totals match the
    legacy oldest-first sweep exactly. Returns the unapplied leftover.
    """
    if amount <= 0:
        return Decimal("0.00")
    # Legacy dicts without a component split behave as all-dues.
    if "dues" not in entry and "aid" not in entry:
        available = _quantize_amount(entry.get("amount", 0))
        take = min(amount, available).quantize(CENT)
        entry["amount"] = float((available - take).quantize(CENT))
        return (amount - take).quantize(CENT)
    left = amount
    # Component-targeted payments stay on their component (a dues-only pick
    # never settles aid); whole-month reductions take dues first, then aid.
    if component == "aid":
        targets = ["aid"]
    elif component == "dues":
        targets = ["dues"]
    else:
        targets = ["dues", "aid"]
    for comp in targets:
        if left <= 0:
            break
        available = _quantize_amount(entry.get(comp, 0))
        take = min(left, available)
        if take > 0:
            entry[comp] = float((available - take).quantize(CENT))
            left = (left - take).quantize(CENT)
    return left


def _split_month_key(key: str) -> tuple:
    """Split an unpaid-month selection key into (month_key, component).

    ``"2026-02"``        → ``("2026-02", "")``      (whole month, legacy)
    ``"2026-02:dues"``   → ``("2026-02", "dues")``
    ``"2026-02:aid"``    → ``("2026-02", "aid")``
    Unknown suffixes fall back to the whole month.
    """
    text = str(key or "")
    parent, sep, suffix = text.partition(":")
    if sep and suffix in ("dues", "aid"):
        return parent, suffix
    return text, ""


def _fit_month_label(months, legacy_label: str = "", limit: int = 50) -> str:
    """Build a ``MemberAssessment.prior_month`` label that fits the column.

    The row's authoritative month context lives in ``prior_months`` (JSON);
    ``prior_month`` is only the human-readable summary, and the column is
    ``max_length=50``. A long carry-over (many unpaid months) would overflow
    and abort the insert, so the label is compressed: the oldest and newest
    month plus a "+N more" count, with a hard truncation as last resort.
    """
    labels = [
        str(m.get("label") or "")
        for m in (months or [])
        if isinstance(m, dict) and m.get("label")
    ]
    text = ", ".join(labels) or (legacy_label or "")
    if len(text) <= limit:
        return text
    if len(labels) >= 2:
        extra = len(labels) - 2
        for separator in ("–", "-", "..."):
            candidate = (
                f"{labels[0]} {separator} {labels[-1]}"
                + (f" (+{extra} more)" if extra else "")
            )
            if len(candidate) <= limit:
                return candidate
    return text[:limit]


def _component_amount(month: dict, component: str) -> Decimal:
    """The collectible amount of one component of a carried month entry."""
    if not isinstance(month, dict):
        return Decimal("0.00")
    if component == "dues":
        return _quantize_amount(month.get("dues", month.get("amount", 0)))
    if component == "aid":
        return _quantize_amount(month.get("aid", 0))
    return _quantize_amount(month.get("amount", 0))


def _attribute_prior_collection(
    months: list[dict], collected: Decimal, selected_keys: list[str] | None
) -> list[dict]:
    """Split a recorded prior-balance payment across the carried months.

    months is the carried-in snapshot (oldest first). When the treasurer
    picked specific months (selected_keys), the payment is applied to exactly
    those months in the order listed, partially covering the last one it runs
    out on — mirroring the recorder UI's "covers N of M selected" preview.
    Without a selection (or when none matches the snapshot) the payment is
    applied oldest-first across every carried month, which is how balances
    were attributed before month context existed.

    Selection keys may target a whole month (``"2026-02"``) or one component
    (``"2026-02:dues"`` / ``"2026-02:aid"``); within a month dues settle
    before aid. Returned entries keep the component key plus the parent
    ``month_key`` so later derivations reduce exactly the picked component.

    Returns [{key, month_key, label, amount}] entries with amount > 0 only;
    the amounts sum to the collected figure actually applied.
    """
    collected = Decimal(str(collected or 0)).quantize(CENT)
    if collected <= 0 or not months:
        return []
    # Expand the snapshot into collectible units (dues before aid per month).
    units: list[dict] = []
    for m in months:
        if not isinstance(m, dict):
            continue
        units.append({
            "key": f"{m.get('key')}:dues",
            "month_key": str(m.get("key") or ""),
            "label": f"{m.get('label') or ''} — Due",
            "amount": _component_amount(m, "dues"),
        })
        units.append({
            "key": f"{m.get('key')}:aid",
            "month_key": str(m.get("key") or ""),
            "label": f"{m.get('label') or ''} — Aid",
            "amount": _component_amount(m, "aid"),
        })
    order = units
    if selected_keys:
        wanted: list[tuple] = [_split_month_key(k) for k in selected_keys]
        chosen: list[dict] = []
        for parent, component in wanted:
            for unit in units:
                if unit["month_key"] != parent:
                    continue
                if component and not unit["key"].endswith(f":{component}"):
                    continue
                if unit not in chosen:
                    chosen.append(unit)
        if chosen:
            order = chosen
    applied: list[dict] = []
    left = collected
    for entry in order:
        if left <= 0:
            break
        available = Decimal(str(entry.get("amount") or 0)).quantize(CENT)
        if available <= 0:
            continue
        take = min(left, available).quantize(CENT)
        applied.append({
            "key": str(entry.get("key") or ""),
            "month_key": str(entry.get("month_key") or entry.get("key") or ""),
            "label": str(entry.get("label") or ""),
            "amount": float(take),
        })
        left = (left - take).quantize(CENT)
    return applied


def _unpaid_months_by_member(exclude_assessment: MonthlyAssessment | None = None) -> dict[int, dict]:
    """Unified unpaid months per member: catch-up drafts + approved outstanding.

    Catch-up and prior outstanding are the same obligation (unpaid past months)
    under different names. Returns {member_id: {"amount", "month_label", "months"}}
    where months is oldest-first [{key, label, amount, source}] with source
    "catchup" (mid-year backfill window) or "outstanding" (approved unpaid).

    Assessment-month context (not wall-clock): only months strictly before
    exclude_assessment are listed, and never months from before the member's
    join year — a January joiner cannot owe August of the prior year.

    Each record's own new debt is outstanding − prior carried in + prior already
    collected on that row. Collections on a row are applied to the exact months
    recorded in its prior_collected_months snapshot (the treasurer's selected
    months, frozen at recording time); rows without a snapshot — legacy data —
    fall back to an oldest-first FIFO sweep, so a month settled as prior
    disappears from the list while the lifetime net (member_lifetime_owed)
    stays correct.
    """
    # A member who enrolled after earlier collections were final-approved has
    # no MemberAssessment rows for those months (and must never be added to
    # the already-approved batch).  Seed their separate historical dues here;
    # later MemberAssessment rows reduce these entries through the normal
    # prior_collected_months attribution below.
    catchup_qs = MemberCatchupDue.objects.select_related("member_id_FK")
    if exclude_assessment is not None:
        catchup_qs = catchup_qs.filter(month__lt=exclude_assessment.month)
    seeded_by_member: dict[int, list[dict]] = {}
    for due in catchup_qs.order_by("month", "catchup_due_id_PK"):
        member = due.member_id_FK
        joined = member.date_joined
        if joined and due.month < date(joined.year, 1, 1):
            continue
        amount = Decimal(str(due.amount or 0)).quantize(CENT)
        if amount <= Decimal("0.004"):
            continue
        seeded_by_member.setdefault(member.member_id_PK, []).append({
            "key": due.month.strftime("%Y-%m"),
            "label": due.month.strftime("%B %Y"),
            "amount": float(amount),
            "dues": float(amount),
            "aid": 0.0,
            "source": "catchup",
        })

    qs = MemberAssessment.objects.filter(
        Q(outstanding_balance__gt=0) | Q(prior_outstanding_collected__gt=0)
    ).select_related("assessment_id_FK", "member_id_FK").prefetch_related(
        Prefetch(
            "allocations",
            queryset=MemberAssessmentAllocation.objects.select_related(
                "assessment_item_id_FK"
            ),
        ),
        "assessment_id_FK__items",
    )
    if exclude_assessment is not None:
        qs = qs.filter(assessment_id_FK__month__lt=exclude_assessment.month)

    by_member: dict[int, list[MemberAssessment]] = {}
    for row in qs.order_by("assessment_id_FK__month", "member_assessment_id_PK"):
        by_member.setdefault(row.member_id_FK_id, []).append(row)

    result: dict[int, dict] = {}
    for member_id in set(seeded_by_member) | set(by_member):
        rows = by_member.get(member_id, [])
        open_months: list[dict] = [dict(entry) for entry in seeded_by_member.get(member_id, [])]
        for row in rows:
            pay = Decimal(str(row.prior_outstanding_collected or 0))
            if pay > 0:
                placed = Decimal("0.00")
                attributed = (
                    row.prior_collected_months
                    if isinstance(row.prior_collected_months, list)
                    else None
                )
                if attributed:
                    specs: dict[str, list] = {}
                    for spec in attributed:
                        if not isinstance(spec, dict):
                            continue
                        parent = str(spec.get("month_key") or spec.get("key") or "")
                        specs.setdefault(parent, []).append(spec)
                    for entry in open_months:
                        if pay - placed <= 0:
                            break
                        month_specs = specs.get(str(entry["key"]))
                        if not month_specs:
                            continue
                        for spec in month_specs:
                            if pay - placed <= 0:
                                break
                            _parent, component = _split_month_key(spec.get("key"))
                            take = min(
                                Decimal(str(spec.get("amount") or 0)),
                                pay - placed,
                            ).quantize(CENT)
                            if take > 0:
                                applied = take - _reduce_open_entry(entry, take, component)
                                placed = (placed + applied).quantize(CENT)
                leftover = pay - placed
                if leftover > 0:
                    # Legacy rows (no month snapshot) and any part of a
                    # payment the snapshot can no longer place: sweep the
                    # still-open months oldest-first as before.
                    for entry in open_months:
                        if leftover <= 0:
                            break
                        leftover = _reduce_open_entry(entry, leftover, "")
                        entry["amount"] = float(
                            (_quantize_amount(entry.get("dues", 0))
                             + _quantize_amount(entry.get("aid", 0))).quantize(CENT)
                        )
                open_months = [
                    e for e in open_months
                    if (_quantize_amount(e.get("dues", 0))
                        + _quantize_amount(e.get("aid", 0))) > Decimal("0.004")
                ]
                for e in open_months:
                    e["amount"] = float(
                        (_quantize_amount(e.get("dues", 0))
                         + _quantize_amount(e.get("aid", 0))).quantize(CENT)
                    )

            own = (
                Decimal(str(row.outstanding_balance or 0))
                - Decimal(str(row.prior_outstanding or 0))
                + Decimal(str(row.prior_outstanding_collected or 0))
            ).quantize(CENT)
            if own <= 0:
                continue
            assessment = row.assessment_id_FK
            joined = row.member_id_FK.date_joined
            # Never surface obligations from before the join year (stale rows,
            # imports, or a January joiner looking at a prior-year draft).
            if joined and assessment.month < date(joined.year, 1, 1):
                continue
            is_catchup = _is_catchup_obligation(
                joined,
                assessment.month,
                assessment.status,
                row.member_id_FK,
            )
            own_dues, own_aid = _split_row_own(row, own)
            open_months.append({
                "key": assessment.month.strftime("%Y-%m"),
                "label": assessment.month_label,
                "amount": float(own),
                "dues": float(own_dues),
                "aid": float(own_aid),
                "source": "catchup" if is_catchup else "outstanding",
            })

        if not open_months:
            continue
        total = float(sum(Decimal(str(e["amount"])) for e in open_months).quantize(CENT))
        if total <= 0.004:
            continue
        result[member_id] = {
            "amount": total,
            "month_label": ", ".join(e["label"] for e in open_months if e["label"]),
            "months": open_months,
        }
    try:
        from core_system.dues_backfill_guard import is_back_dues_chase_enabled

        if not is_back_dues_chase_enabled():
            for member_id in list(result.keys()):
                kept = [
                    e for e in result[member_id].get("months", [])
                    if not isinstance(e, dict) or e.get("source") != "catchup"
                ]
                if not kept:
                    del result[member_id]
                    continue
                result[member_id]["months"] = kept
                result[member_id]["amount"] = float(
                    sum(Decimal(str(e.get("amount", 0))) for e in kept).quantize(CENT)
                )
                result[member_id]["month_label"] = ", ".join(
                    e.get("label", "") for e in kept if e.get("label")
                )
    except Exception:
        pass
    return result


def _prior_outstanding_by_member(exclude_assessment: MonthlyAssessment | None = None) -> dict[int, dict]:
    """Collectible carry-over per member — unified catch-up + outstanding.

    Returns {member_id: {"amount": float, "month_label": str, "months": [...]}}.
    amount is the net unpaid across all past months except the one being
    recorded (see _unpaid_months_by_member / member_lifetime_owed), safe under
    out-of-order recording. There is no member credit: any excess collected
    goes to the ISUCauFA funds.
    """
    return _unpaid_months_by_member(exclude_assessment=exclude_assessment)


def _assessment_month_context(assessment: MonthlyAssessment, member_assessment: MemberAssessment) -> dict:
    """Build the email/in-app context for one member's deduction notice."""
    detail = build_member_assessment_breakdown(member_assessment)
    breakdown = [
        {
            "purpose": row["purpose"],
            "recipient": row["recipient"],
            "notes": row.get("notes", ""),
            "required": row["required"],
            "applied": row["applied"],
            "remaining": row["remaining"],
        }
        for row in detail["rows"]
    ]
    return {
        "member_name": member_assessment.member_id_FK.full_name,
        "month_label": assessment.month_label,
        "standard_assessment": detail["standard"],
        "prior_outstanding": float(member_assessment.prior_outstanding or 0),
        "prior_outstanding_collected": float(member_assessment.prior_outstanding_collected or 0),
        "prior_month_label": member_assessment.prior_month or "",
        "change_amount": detail["change"],
        "actual_deducted": detail["actual"],
        "outstanding_balance": detail["outstanding"],
        "total_required": detail["total_required"],
        "payment_status": detail["status"],
        "breakdown": breakdown,
    }


# ---------------------------------------------------------------------------
# President endpoints
# ---------------------------------------------------------------------------

@require_GET
def president_monthly_assessment_list(request: HttpRequest):
    """List every monthly assessment with its breakdown (President)."""
    guard = require_role(request, role="President")
    if guard is not None:
        return guard

    assessments = MonthlyAssessment.objects.prefetch_related("items", "member_assessments", "documents")

    # Active member names for the recipient autocomplete — breakdown recipients
    # are often actual members (aid claimants, retirees), but may also be the
    # association itself or an external body, so it stays free text.
    member_names = sorted(
        (
            _formatted_name(name)
            for name in Member.objects.filter(membership_status__in=ACTIVE_MEMBERSHIP_STATUSES)
            .values_list("full_name", flat=True)
        ),
        key=str.casefold,
    )

    return JsonResponse({
        "ok": True,
        "default_monthly_due": get_monthly_dues_amount(),
        "member_names": member_names,
        "external_campuses": [
            "ISU Echague Campus",
            "ISU Ilagan Campus",
            "ISU Jones Campus",
            "ISU San Mariano Campus",
            "ISU Cauayan Campus",
            "ISUFFAI Federation",
        ],
        "assessments": [
            _serialize_assessment(a) for a in assessments
        ],
    })


@require_POST
def president_save_monthly_assessment(request: HttpRequest):
    """Create or revise the assessment (breakdown) for one month (President)."""
    guard = require_role(request, role="President")
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)

    payload = _json_body(request)
    month = _parse_month(payload.get("month"))
    if month is None:
        return JsonResponse({"ok": False, "error": "A valid month (YYYY-MM) is required."}, status=400)

    # Draft mode saves the breakdown as-is: aid items may still be missing
    # their recipient and "Other" its label — those are only enforced when the
    # assessment is saved for the Treasurer to record against.
    draft_mode = payload.get("draft") is True

    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return JsonResponse({"ok": False, "error": "At least one breakdown item is required."}, status=400)

    # Token Incentive was retired as a President purpose: it is no longer in
    # PURPOSE_CHOICES, so it can never be added to a new or revised breakdown.
    # An assessment that already carries a token line may still be revised —
    # the stored line is re-attached verbatim below as read-only history.
    def _is_token_item(raw) -> bool:
        return (
            isinstance(raw, dict)
            and (raw.get("purpose") or "").strip() == AssessmentItem.PURPOSE_TOKEN_INCENTIVE
        )

    token_requested = [raw for raw in raw_items if _is_token_item(raw)]
    if token_requested:
        existing_assessment = MonthlyAssessment.objects.filter(month=month).first()
        keeps_history = bool(
            existing_assessment
            and existing_assessment.items.filter(purpose=AssessmentItem.PURPOSE_TOKEN_INCENTIVE).exists()
        )
        if not keeps_history:
            return JsonResponse({
                "ok": False,
                "error": "Token Incentive is no longer an assessment purpose and can no longer be added.",
            }, status=400)
        raw_items = [raw for raw in raw_items if not _is_token_item(raw)]
        if not raw_items:
            return JsonResponse({"ok": False, "error": "At least one breakdown item is required."}, status=400)

    valid_purposes = {choice[0] for choice in AssessmentItem.PURPOSE_CHOICES}
    parsed_items = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            return JsonResponse({"ok": False, "error": "Each breakdown item must be an object."}, status=400)
        purpose = (raw.get("purpose") or "").strip()
        if purpose not in valid_purposes:
            return JsonResponse({"ok": False, "error": f"Unknown breakdown purpose: {purpose or '(blank)'}."}, status=400)
        amount = _parse_amount(raw.get("amount"))
        if amount is None or amount <= 0:
            return JsonResponse({"ok": False, "error": f"Breakdown amount for {purpose} must be greater than zero."}, status=400)
        custom_label = (raw.get("custom_label") or "").strip()
        if purpose == AssessmentItem.PURPOSE_OTHER and not custom_label and not draft_mode:
            return JsonResponse({
                "ok": False,
                "error": "An item labeled 'Other' needs its specific name (e.g. 'ISUFFAI Federation Fee') so members know what it is.",
            }, status=400)
        # Standard purposes keep the label too — for Monthly Due it is the
        # covered month (picked from the month selector), shown as "July 2026".
        if purpose == AssessmentItem.PURPOSE_MONTHLY_DUE and custom_label:
            try:
                custom_label = datetime.strptime(custom_label, "%Y-%m").strftime("%B %Y")
            except ValueError:
                pass
        recipient = (raw.get("recipient") or "").strip() or None
        recipient_type = ((raw.get("recipient_type") or "").strip().lower() or "member")
        if recipient_type not in ("member", "external"):
            return JsonResponse({"ok": False, "error": "Unknown recipient type — choose Member or Other Campus."}, status=400)
        external_campus = (raw.get("external_campus") or "").strip() or None
        external_beneficiary = (raw.get("external_beneficiary") or "").strip() or None
        if purpose == AssessmentItem.PURPOSE_MONTHLY_DUE:
            # Monthly dues go to the association — never per-person, never external.
            recipient = "ISUCauFA, Inc."
            recipient_type = "member"
            external_campus = None
            external_beneficiary = None
        elif recipient_type == "external":
            # Other-campus aid (different campus beneficiary) is only
            # available for Death Aid and Other purposes — never Medical Aid.
            if purpose not in (AssessmentItem.PURPOSE_DEATH_AID, AssessmentItem.PURPOSE_OTHER):
                return JsonResponse({
                    "ok": False,
                    "error": "Other-campus aid (different campus beneficiary) is only available for Death Aid and Other purposes.",
                }, status=400)
            # Declared from the very start. Both halves are mandatory so
            # downstream modules never see a half-declared external collection.
            if not external_campus or not external_beneficiary:
                return JsonResponse({
                    "ok": False,
                    "error": "Other-campus aid needs both the campus and the beneficiary name (e.g. ISU Echague — Juan Dela Cruz).",
                }, status=400)
            # Canonical display so set-asides, payslips and queues read
            # identically: "CAMPUS — Beneficiary".
            recipient = f"{external_campus} — {external_beneficiary}"
        elif purpose in (AssessmentItem.PURPOSE_MEDICAL_AID, AssessmentItem.PURPOSE_DEATH_AID):
            if not recipient and not draft_mode:
                return JsonResponse({
                    "ok": False,
                    "error": "Every item needs a recipient — pick who receives it. "
                             "Medical Aid and Death Aid go to a specific member only.",
                }, status=400)
        elif not recipient and not draft_mode:
            return JsonResponse({
                "ok": False,
                "error": "Every item needs a recipient — pick who receives it. "
                         "Medical Aid and Death Aid go to a specific member only.",
            }, status=400)
        try:
            priority = int(raw.get("priority_order") or len(parsed_items) + 1)
        except (TypeError, ValueError):
            priority = len(parsed_items) + 1
        parsed_items.append({
            "purpose": purpose,
            "custom_label": custom_label,
            "amount": amount,
            "recipient": recipient,
            "recipient_type": recipient_type,
            "external_campus": external_campus,
            "external_beneficiary": external_beneficiary,
            "notes": (raw.get("notes") or "").strip() or None,
            "priority_order": max(1, priority),
        })

    total_amount = sum(item["amount"] for item in parsed_items).quantize(CENT)

    # Filled only when a real submit hands the month to the Treasurer.
    handoff_auto_notice = ""
    try:
        with transaction.atomic():
            assessment = MonthlyAssessment.objects.filter(month=month).first()
            created = assessment is None
            if created:
                assessment = MonthlyAssessment(month=month, created_by_id_FK=officer)
            elif assessment.status not in (
                MonthlyAssessment.STATUS_DRAFT,
                MonthlyAssessment.STATUS_REJECTED,
                MonthlyAssessment.STATUS_RETURNED,
            ):
                already_sent = assessment.status == MonthlyAssessment.STATUS_PENDING_TREASURER
                return JsonResponse({
                    "ok": False,
                    "error": (
                        f"{assessment.month_label} was already submitted to the Treasurer. "
                        f"Recall it back to draft from the form to make changes."
                        if already_sent
                        else f"{assessment.month_label} is already {assessment.get_status_display()} and can no longer be edited."
                    ),
                }, status=409)

            # Token lines can no longer be created or edited, but a revised
            # breakdown must not lose the ones already on the record: they are
            # read back before the wholesale replace and re-attached unchanged.
            stored_token_rows = []
            if not created:
                stored_token_rows = [
                    {
                        "purpose": row.purpose,
                        "custom_label": row.custom_label,
                        "amount": row.amount,
                        "recipient": row.recipient,
                        "notes": row.notes,
                        "priority_order": row.priority_order,
                    }
                    for row in assessment.items.filter(purpose=AssessmentItem.PURPOSE_TOKEN_INCENTIVE)
                ]
            if stored_token_rows:
                total_amount = (
                    sum((item["amount"] for item in parsed_items), Decimal("0.00"))
                    + sum((row["amount"] for row in stored_token_rows), Decimal("0.00"))
                ).quantize(CENT)

            assessment.total_amount = total_amount
            # "Save as draft" keeps the month private to the President; only a
            # real submit ("Save deduction") hands it to the Treasurer.
            assessment.status = (
                MonthlyAssessment.STATUS_DRAFT
                if draft_mode
                else MonthlyAssessment.STATUS_PENDING_TREASURER
            )
            assessment.created_by_id_FK = assessment.created_by_id_FK or officer
            assessment.save()

            # Replace the breakdown wholesale so revisions stay consistent.
            assessment.items.all().delete()
            AssessmentItem.objects.bulk_create([
                AssessmentItem(assessment_id_FK=assessment, **item)
                for item in parsed_items + stored_token_rows
            ])

            # Handoff automation: the moment a month is handed to the
            # Treasurer (never on draft saves), every still-flagged member
            # gets their missing Jan..join-month dues rows so the missed
            # months exist before recording starts. Strict: any unexpected
            # failure rolls the whole submit back — a partial handoff with
            # silently missing bills is worse than a visible error.
            if not draft_mode:
                pending_backfill = list(
                    Member.objects.filter(dues_backfill_pending=True)
                    .filter(_catchup_eligible_filter())
                )
                if pending_backfill:
                    try:
                        handoff_batch = _generate_catchup_for_members(
                            pending_backfill, officer, strict=True
                        )
                    except Exception as exc:
                        logger.exception(
                            "Handoff auto-create failed for %s", assessment.month_label
                        )
                        transaction.set_rollback(True)
                        return JsonResponse({
                            "ok": False,
                            "error": (
                                f"{assessment.month_label} could not be submitted: "
                                "automatic creation of missing dues rows failed "
                                f"({exc}). Nothing was saved — try submitting again."
                            ),
                        }, status=500)
                    handoff_auto_notice, _, _ = _auto_create_summary(handoff_batch)
                    if handoff_auto_notice:
                        AssessmentWorkflowLog.objects.create(
                            assessment_id_FK=assessment,
                            action="auto_catchup_on_handoff",
                            performed_by_id_FK=officer,
                            notes=handoff_auto_notice,
                        )

            AssessmentWorkflowLog.objects.create(
                assessment_id_FK=assessment,
                action="president_set_assessment" if created else "president_revise_assessment",
                performed_by_id_FK=officer,
                notes=(
                    f"Total assessment set to {total_amount} with "
                    f"{len(parsed_items) + len(stored_token_rows)} breakdown item(s)."
                    + (" Draft — details may still be incomplete." if draft_mode else "")
                ),
            )

            ip = request.META.get("REMOTE_ADDR")
            device_info = request.META.get("HTTP_USER_AGENT", "")
            _record_audit_trail(
                table=ASSESSMENT_TABLE,
                record_id=assessment.assessment_id_PK,
                action="CREATE" if created else "UPDATE",
                actor=officer,
                new=_audit_safe({
                    "month": month,
                    "total_amount": total_amount,
                    "items": parsed_items + stored_token_rows,
                }),
                ip=ip,
                device_info=device_info,
                notes="Monthly deduction assessment saved by President",
            )
    except IntegrityError:
        return JsonResponse({"ok": False, "error": "An assessment for this month already exists."}, status=409)

    assessment = MonthlyAssessment.objects.prefetch_related("items").get(pk=assessment.assessment_id_PK)
    _broadcast_deduction_counts()
    handoff_message = (
        f"Draft saved for {assessment.month_label} — complete the details before the Treasurer records."
        if draft_mode
        else f"Deduction for {assessment.month_label} submitted to the Treasurer."
    )
    if handoff_auto_notice:
        handoff_message += f" {handoff_auto_notice}"
    if not draft_mode:
        _notify_role(
            "Treasurer",
            f"Monthly deduction assessment for {assessment.month_label} is now available "
            f"(total {total_amount} per member)."
            + (f" {handoff_auto_notice}" if handoff_auto_notice else ""),
            url="/treasurer/",
        )

    return JsonResponse({
        "ok": True,
        "assessment": _serialize_assessment(assessment),
        "message": handoff_message,
        "auto_created": handoff_auto_notice,
    })


@require_POST
def president_recall_monthly_assessment(request: HttpRequest):
    """Pull a submitted assessment back to Draft (President).

    Allowed only while the month is still Pending Treasurer Review — the
    Treasurer has not recorded anything against it yet — so recalling can
    never orphan downstream records. The month becomes editable again
    through the normal save endpoint.
    """
    guard = require_role(request, role="President")
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)

    payload = _json_body(request)
    assessment = MonthlyAssessment.objects.filter(pk=payload.get("assessment_id")).first()
    if assessment is None:
        return JsonResponse({"ok": False, "error": "Assessment not found."}, status=404)

    if assessment.status != MonthlyAssessment.STATUS_PENDING_TREASURER:
        return JsonResponse({
            "ok": False,
            "error": (
                f"Only a deduction still awaiting the Treasurer can be recalled "
                f"(current: {assessment.get_status_display()})."
            ),
        }, status=409)

    if assessment.member_assessments.exists():
        return JsonResponse({
            "ok": False,
            "error": (
                f"The Treasurer already started recording {assessment.month_label} — "
                f"ask the Auditor to reject it if something has to change."
            ),
        }, status=409)

    old_status = assessment.status
    assessment.status = MonthlyAssessment.STATUS_DRAFT
    assessment.save(update_fields=["status", "updated_at"])

    AssessmentWorkflowLog.objects.create(
        assessment_id_FK=assessment,
        action="president_recall",
        performed_by_id_FK=officer,
        notes=f"Recalled {assessment.month_label} to draft for correction before recording.",
    )
    _record_audit_trail(
        table=ASSESSMENT_TABLE,
        record_id=assessment.assessment_id_PK,
        action="RECALL",
        actor=officer,
        old={"status": old_status},
        new={"status": assessment.status},
        ip=request.META.get("REMOTE_ADDR"),
        device_info=request.META.get("HTTP_USER_AGENT", ""),
        notes=f"President recalled {assessment.month_label} monthly deduction to draft",
    )
    _broadcast_deduction_counts()
    _notify_role(
        "Treasurer",
        f"President recalled the {assessment.month_label} monthly deduction back to draft for correction.",
        url="/treasurer/",
    )

    return JsonResponse({
        "ok": True,
        "assessment": _serialize_assessment(assessment),
        "message": f"{assessment.month_label} recalled to draft — you can now edit and resubmit it.",
    })


@require_GET
def president_monthly_assessment_detail(request: HttpRequest, assessment_id: int):
    """Full assessment detail including member deductions and allocations."""
    guard = require_role(request, role=["President", "Auditor", "Treasurer"])
    if guard is not None:
        return guard

    assessment = MonthlyAssessment.objects.filter(pk=assessment_id).prefetch_related(
        "items", "workflow_logs", "documents",
        "member_assessments__member_id_FK",
        "member_assessments__allocations__assessment_item_id_FK",
    ).first()
    if assessment is None:
        return JsonResponse({"ok": False, "error": "Assessment not found."}, status=404)

    member_assessments = [
        _serialize_member_assessment(ma)
        for ma in sorted(
            assessment.member_assessments.all(),
            key=lambda ma: _formatted_name(ma.member_id_FK.full_name).casefold(),
        )
    ]
    return JsonResponse({
        "ok": True,
        "assessment": _serialize_assessment(assessment),
        "member_assessments": member_assessments,
        "workflow_logs": _serialize_workflow_logs(assessment),
    })


@require_POST
def president_upload_assessment_documents(request: HttpRequest, assessment_id: int):
    """Attach scanned images of the request letter / deducted amount sheet.

    Multipart form: repeat the `request_letter` and/or `deduction_sheet`
    fields — every file in each group is stored, so a multi-page scan can be
    attached as several images. Images only (JPG/PNG/WEBP); uploading adds to
    the month's set (individual images can be removed afterwards).
    """
    guard = require_role(request, role="President")
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)

    assessment = MonthlyAssessment.objects.filter(pk=assessment_id).first()
    if assessment is None:
        return JsonResponse({"ok": False, "error": "Assessment not found."}, status=404)

    from core_system.secure_upload import SecureUploadError, validate_and_store

    # Hashes already attached to this month (any kind): the same scan must
    # not be attached twice, nor filed as both the letter and the sheet.
    existing_hashes: set[str] = set(
        MonthlyAssessmentDocument.objects.filter(
            assessment_id_FK=assessment,
        ).exclude(content_sha256__isnull=True).exclude(content_sha256="")
        .values_list("content_sha256", flat=True)
    )
    existing_norms: set[str] = set(
        MonthlyAssessmentDocument.objects.filter(
            assessment_id_FK=assessment,
        ).exclude(norm_sha256__isnull=True).exclude(norm_sha256="")
        .values_list("norm_sha256", flat=True)
    )

    to_create = []
    for kind in ASSESSMENT_DOC_KINDS:
        for file in request.FILES.getlist(kind):
            try:
                saved = validate_and_store(
                    file,
                    subdir="secure_uploads/assessment_documents",
                    allowed_extensions={"jpg", "jpeg", "png", "webp"},
                    max_bytes=DOC_MAX_BYTES,
                )
            except SecureUploadError as exc:
                return JsonResponse({"ok": False, "error": f"{file.name}: {exc.message}"}, status=exc.status)
            if saved["sha256"] in existing_hashes or (
                saved["norm_sha256"] and saved["norm_sha256"] in existing_norms
            ):
                return JsonResponse({
                    "ok": False,
                    "error": (
                        f"{saved['original_name']}: this image is already attached "
                        f"to {assessment.month_label} (same image content, "
                        "regardless of filename). Remove the duplicate instead."
                    ),
                }, status=409)
            existing_hashes.add(saved["sha256"])
            if saved["norm_sha256"]:
                existing_norms.add(saved["norm_sha256"])
            to_create.append(MonthlyAssessmentDocument(
                assessment_id_FK=assessment,
                kind=kind,
                image=saved["stored_name"],
                content_sha256=saved["sha256"],
                norm_sha256=saved["norm_sha256"] or "",
                uploaded_by_id_FK=officer,
            ))

    if not to_create:
        return JsonResponse({"ok": False, "error": "Choose at least one image to upload."}, status=400)

    from django.db.utils import DataError
    try:
        MonthlyAssessmentDocument.objects.bulk_create(to_create)
    except DataError:
        # Old deployments still have VARCHAR(100) on this column until
        # migration 0160 is applied. Remove the already-stored files so a
        # failed insert does not leave orphans, then tell the user to retry
        # with a shorter filename.
        from django.core.files.storage import default_storage
        for doc in to_create:
            try:
                if doc.image and doc.image.name:
                    default_storage.delete(doc.image.name)
            except Exception:
                pass
        return JsonResponse({
            "ok": False,
            "error": (
                "Upload failed: the generated file path is too long for the "
                "database. Rename the file to something shorter and try again, "
                "or ask the administrator to apply migration 0160."
            ),
        }, status=400)

    labels = {"request_letter": "request letter", "deduction_sheet": "deducted amount sheet"}
    by_kind = {kind: sum(1 for d in to_create if d.kind == kind) for kind in ASSESSMENT_DOC_KINDS}
    summary = ", ".join(f"{count} {labels[kind]} image(s)" for kind, count in by_kind.items() if count)
    AssessmentWorkflowLog.objects.create(
        assessment_id_FK=assessment,
        action="president_upload_documents",
        performed_by_id_FK=officer,
        notes=f"Attached {summary}.",
    )
    _record_audit_trail(
        table=ASSESSMENT_TABLE,
        record_id=assessment.assessment_id_PK,
        action="UPLOAD",
        actor=officer,
        new={"documents": {kind: count for kind, count in by_kind.items() if count}},
        ip=request.META.get("REMOTE_ADDR"),
        device_info=request.META.get("HTTP_USER_AGENT", ""),
        notes=f"President attached {summary} to {assessment.month_label}",
    )

    return JsonResponse({
        "ok": True,
        "message": f"Attached {summary} for {assessment.month_label}.",
    })


@require_POST
def president_delete_assessment_document(request: HttpRequest, document_id: int):
    """Remove one attached image (President)."""
    guard = require_role(request, role="President")
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)

    doc = MonthlyAssessmentDocument.objects.filter(pk=document_id).select_related("assessment_id_FK").first()
    if doc is None:
        return JsonResponse({"ok": False, "error": "Document not found."}, status=404)
    if doc.kind == DEPOSIT_SLIP_KIND:
        return JsonResponse({
            "ok": False,
            "error": "Deposit slips are immutable evidence and cannot be deleted.",
        }, status=403)

    assessment = doc.assessment_id_FK
    doc.image.delete(save=False)
    doc.delete()

    AssessmentWorkflowLog.objects.create(
        assessment_id_FK=assessment,
        action="president_delete_document",
        performed_by_id_FK=officer,
        notes=f"Removed a {doc.get_kind_display().lower()} image.",
    )
    _record_audit_trail(
        table=ASSESSMENT_TABLE,
        record_id=assessment.assessment_id_PK,
        action="DELETE",
        actor=officer,
        old={"document_id": document_id, "kind": doc.kind},
        ip=request.META.get("REMOTE_ADDR"),
        device_info=request.META.get("HTTP_USER_AGENT", ""),
        notes=f"President removed a {doc.get_kind_display().lower()} image from {assessment.month_label}",
    )
    return JsonResponse({"ok": True, "message": "Image removed."})


@require_GET
def officer_assessment_document_file(request: HttpRequest, document_id: int):
    """Serve one attached assessment image inline (President / Treasurer / Auditor)."""
    from mimetypes import guess_type

    from django.core.files import File

    guard = require_role(request, role=["President", "Treasurer", "Auditor"])
    if guard is not None:
        return guard

    doc = MonthlyAssessmentDocument.objects.filter(pk=document_id).first()
    if doc is None:
        return JsonResponse({"ok": False, "error": "Document not found."}, status=404)

    content_type = guess_type(doc.image.name)[0] or "application/octet-stream"
    response = HttpResponse(File(doc.image.open("rb")), content_type=content_type)
    response["Content-Disposition"] = f'inline; filename="{Path(doc.image.name).name}"'
    return response


@require_POST
def president_approve_monthly_deductions(request: HttpRequest):
    """Final approval (or return) of a verified monthly deduction (President).

    On approval, every affected member receives an email + in-app notice with
    the deduction breakdown and outstanding balance.
    """
    guard = require_role(request, role="President")
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)

    payload = _json_body(request)
    action = (payload.get("action") or "").strip().lower()
    notes = (payload.get("notes") or "").strip()
    if action not in ("approve", "return"):
        return JsonResponse({"ok": False, "error": "Action must be 'approve' or 'return'."}, status=400)

    assessment = MonthlyAssessment.objects.filter(pk=payload.get("assessment_id")).first()
    if assessment is None:
        return JsonResponse({"ok": False, "error": "Assessment not found."}, status=404)
    if assessment.status != MonthlyAssessment.STATUS_PENDING_FINAL:
        return JsonResponse({
            "ok": False,
            "error": f"Only assessments pending final approval can be actioned (current: {assessment.get_status_display()}).",
        }, status=409)

    if action == "return":
        if not notes:
            return JsonResponse({"ok": False, "error": "Remarks are required when returning an entry."}, status=400)

        member_rows = list(assessment.member_assessments.all())
        for member_assessment in member_rows:
            member_assessment.status = MemberAssessment.STATUS_PENDING
            member_assessment.verified_by_id_FK = None
            member_assessment.verified_at = None
            member_assessment.approved_by_id_FK = None
            member_assessment.approved_at = None
        MemberAssessment.objects.bulk_update(
            member_rows,
            [
                "status",
                "verified_by_id_FK",
                "verified_at",
                "approved_by_id_FK",
                "approved_at",
            ],
        )

        member_ids = [row.member_assessment_id_PK for row in member_rows]
        if member_ids:
            MemberLedger.objects.filter(
                reference_type="MemberAssessment",
                reference_id__in=member_ids,
            ).delete()
            delete_member_fund_rows(member_ids)

        assessment.status = MonthlyAssessment.STATUS_RETURNED
        assessment.president_remarks = notes
        invalidated_ref = _invalidate_deposit_evidence(assessment)
        assessment.save()
        AssessmentWorkflowLog.objects.create(
            assessment_id_FK=assessment,
            action="president_return",
            performed_by_id_FK=officer,
            notes=notes,
        )
        if invalidated_ref:
            AssessmentWorkflowLog.objects.create(
                assessment_id_FK=assessment,
                action="deposit_invalidated",
                performed_by_id_FK=officer,
                notes=(
                    f"Deposit {invalidated_ref} invalidated by President return — "
                    "slip kept for trace; re-record then re-deposit required."
                ),
            )
        _record_audit_trail(
            table=ASSESSMENT_TABLE,
            record_id=assessment.assessment_id_PK,
            action="RETURN",
            actor=officer,
            old={"status": MonthlyAssessment.STATUS_PENDING_FINAL},
            new={"status": assessment.status, "president_remarks": notes},
            ip=request.META.get("REMOTE_ADDR"),
            device_info=request.META.get("HTTP_USER_AGENT", ""),
            notes="President returned monthly deduction for revision",
        )
        _broadcast_deduction_counts()
        _notify_role(
            "Treasurer",
            f"President returned the {assessment.month_label} monthly deduction: {notes}",
            url="/treasurer/",
        )
        return JsonResponse({
            "ok": True,
            "message": f"{assessment.month_label} deduction returned to the Treasurer for revision.",
        })

    # --- Final approval path: mark everything approved and notify members ---
    assessment.status = MonthlyAssessment.STATUS_FINAL_APPROVED
    assessment.president_remarks = notes or None
    assessment.save()

    member_assessments = list(assessment.member_assessments.select_related("member_id_FK"))
    now_timestamp = assessment.updated_at
    for member_assessment in member_assessments:
        member_assessment.status = MemberAssessment.STATUS_APPROVED
        member_assessment.approved_by_id_FK = officer
        member_assessment.approved_at = now_timestamp
    MemberAssessment.objects.bulk_update(
        member_assessments, ["status", "approved_by_id_FK", "approved_at"]
    )

    # The ISUCauFA, Inc. fund only reflects a month once it is final-approved.
    # Each member's deduction is booked as three separate inflows so the aid
    # portions stop reading as dues income: the dues remainder (plus prior
    # balance collected and change/excess) stays on "monthly_dues", while the
    # medical and death aid portions land on their own set-aside inflows and
    # get an AidSetAside ledger row linked to the recipient's claim. All three
    # sum back to the actual deduction — the amount that was deposited — so
    # bank reconciliation is unchanged. Aid money only leaves the fund when the
    # Treasurer releases it from the Release Queue. Idempotent per member row
    # so a re-approval can never double-book a movement. The reference stamps
    # the collection batch (and the deposit that put it in the bank) so every
    # fund row traces back to one Treasurer deposit and one President approval.
    collection_ref = f"COL-{assessment.assessment_id_PK:05d}"
    if assessment.deposit_reference:
        collection_ref = f"{collection_ref} / {assessment.deposit_reference}"
    recipient_lookup = recipient_member_lookup()
    for member_assessment in member_assessments:
        book_member_fund_rows(
            member_assessment,
            officer=officer,
            collection_ref=collection_ref,
            month_label=assessment.month_label,
            recipient_lookup=recipient_lookup,
        )

    # Other-campus aid consolidation: one tracking post per external aid item
    # (idempotent), contributions for every active member, and earmarks linked
    # by ITEM so external cash can never attach to a member's claim.
    external_posts = []
    try:
        from core_system.external_aid import ensure_external_posts_for_assessment
        external_posts = ensure_external_posts_for_assessment(assessment, officer) or []
    except Exception:
        logger.exception("External aid post creation failed for %s", assessment.month_label)

    # Member ledger postings so each member's Monthly Deductions History
    # reflects the approved months. One row per deducted member, idempotent
    # per member-assessment row so a re-approval can never double-post — the
    # same guard the legacy dues flow uses (there: MonthlyDues reference).
    for member_assessment in sorted(
        member_assessments, key=lambda ma: ma.member_assessment_id_PK
    ):
        if member_assessment.actual_deduction <= 0:
            continue
        if MemberLedger.objects.filter(
            reference_type="MemberAssessment",
            reference_id=member_assessment.member_assessment_id_PK,
        ).exists():
            continue
        member_ref = member_assessment.member_id_FK
        MemberLedger.objects.create(
            member_id_FK=member_ref,
            transaction_type="monthly_dues",
            amount=member_assessment.actual_deduction,
            direction="credit",
            balance_after=member_balance(member_ref) + member_assessment.actual_deduction,
            reference_id=member_assessment.member_assessment_id_PK,
            reference_type="MemberAssessment",
            description=f"Monthly Deduction - {assessment.month_label}",
            recorded_by_user_id_FK=officer,
        )

    AssessmentWorkflowLog.objects.create(
        assessment_id_FK=assessment,
        action="president_approve",
        notes=(notes or "Final approval with member email notices.") + (
            f" External aid posts: {len(external_posts)}." if external_posts else ""
        ),
    )
    _record_audit_trail(
        table=ASSESSMENT_TABLE,
        record_id=assessment.assessment_id_PK,
        action="APPROVE",
        actor=officer,
        old={"status": MonthlyAssessment.STATUS_PENDING_FINAL},
        new={"status": assessment.status},
        ip=request.META.get("REMOTE_ADDR"),
        device_info=request.META.get("HTTP_USER_AGENT", ""),
        notes=f"President final-approved {assessment.month_label} deductions ({len(member_assessments)} members)",
    )

    # Member notices (queued for background delivery so the request returns
    # fast). The subject carries the member's payment status so they know
    # before opening whether anything is owed.
    emails_queued = 0
    subject_by_status = {
        "full": "Monthly Deduction Notice",
        "partial": "Partial Deduction Notice",
        "none": "No Deduction Recorded",
    }
    for member_assessment in member_assessments:
        member = member_assessment.member_id_FK
        context = _assessment_month_context(assessment, member_assessment)
        status_key = context.get("payment_status") or "full"
        notify_member(
            member,
            notification_type="Monthly Deduction",
            message=(
                f"Your {assessment.month_label} monthly deduction of "
                f"₱{float(member_assessment.actual_deduction or 0):,.2f} was recorded "
                f"(outstanding: ₱{float(member_assessment.outstanding_balance or 0):,.2f})."
            ),
            category="finance",
            url="/member/",
            sender_name=officer.full_name,
            sender_role="President",
            # The branded breakdown email is queued below via
            # send_html_email_async; skip notify()'s plain-text fallback so
            # members receive only one email.
            send_email=False,
        )
        if member.email:
            # Deferred: queue the row now, flush ONCE after the loop so 120+
            # members share a single sequential SMTP drain instead of 120
            # racing worker threads (which throttles Gmail/cPanel and leaves
            # most rows PENDING when the page closes).
            send_html_email_async(
                subject=(
                    f"ISUCauFA, Inc. — {subject_by_status[status_key]}"
                    f" ({assessment.month_label})"
                ),
                recipient_list=[member.email],
                html_template="emails/monthly_deduction_notice.html",
                context=context,
                defer_worker=True,
            )
            emails_queued += 1

    if emails_queued:
        # One worker for the whole collection batch. The 2-min scheduler
        # drain + cPanel cron remain as backstops if this thread dies.
        flush_email_queue_async()

    _broadcast_deduction_counts()
    _notify_role(
        "Treasurer",
        f"President final-approved the {assessment.month_label} monthly deduction.",
        url="/treasurer/",
    )
    _notify_role(
        "Auditor",
        f"President final-approved the {assessment.month_label} monthly deduction.",
        url="/",
    )

    return JsonResponse({
        "ok": True,
        "message": (
            f"{assessment.month_label} deduction final-approved. "
            f"{emails_queued} member email notice(s) queued."
        ),
        "members_notified": emails_queued,
    })


# ---------------------------------------------------------------------------
# Treasurer endpoints
# ---------------------------------------------------------------------------

@require_GET
def treasurer_monthly_deductions_overview(request: HttpRequest):
    """List assessments the Treasurer can record against or track (Treasurer)."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    # Drafts belong to the President's workspace — the Treasurer only ever
    # sees months that were actually submitted.
    assessments = MonthlyAssessment.objects.exclude(
        status=MonthlyAssessment.STATUS_DRAFT
    ).prefetch_related("items", "member_assessments", "documents")
    recordable = {
        MonthlyAssessment.STATUS_PENDING_TREASURER,
        MonthlyAssessment.STATUS_REJECTED,
        MonthlyAssessment.STATUS_RETURNED,
    }
    data = []
    for assessment in assessments:
        serialized = _serialize_assessment(assessment)
        serialized["can_record"] = assessment.status in recordable
        serialized["can_deposit"] = assessment.status == MonthlyAssessment.STATUS_PENDING_DEPOSIT
        serialized["action_remarks"] = (
            assessment.auditor_remarks
            if assessment.status == MonthlyAssessment.STATUS_REJECTED
            else assessment.president_remarks
        ) or ""
        data.append(serialized)

    from core_system.dues_backfill_guard import is_back_dues_chase_enabled

    chase_enabled = is_back_dues_chase_enabled()
    return JsonResponse({
        "ok": True,
        "assessments": data,
        "catchup_pending_count": (
            Member.objects.filter(
                dues_backfill_pending=True
            ).filter(_catchup_eligible_filter()).count()
            if chase_enabled else 0
        ),
        "flags": {"require_back_dues": chase_enabled},
    })


@require_GET
def treasurer_year_tracker(request: HttpRequest):
    """Per-member Jan–Dec collection grid for one explicit year (Treasurer).

    ``?year=2026`` selects the year — there is deliberately no wall-clock
    default: without ``year`` the latest assessment year is used (400 when no
    assessments exist yet). A late joiner's obligation starts at their join
    month, never January: months before joining read ``"na"``, months with
    no assessment read ``"no_assessment"``, months with an assessment but no
    member row read ``"missing"``. Recorded months read ``"paid"`` /
    ``"partial"`` / ``"unpaid"`` from actual vs outstanding.
    """
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    raw_year = (request.GET.get("year") or "").strip()
    if raw_year:
        if not raw_year.isdigit() or not 2000 <= int(raw_year) <= 2100:
            return JsonResponse({"ok": False, "error": "year must be a YYYY year."}, status=400)
        year = int(raw_year)
    else:
        latest = MonthlyAssessment.objects.order_by("-month").values_list("month", flat=True).first()
        if latest is None:
            return JsonResponse({"ok": False, "error": "No assessments exist yet."}, status=400)
        year = latest.year

    assessments = {
        a.month.month: a
        for a in MonthlyAssessment.objects.filter(month__year=year).prefetch_related("items")
    }
    rows = (
        MemberAssessment.objects.filter(assessment_id_FK__month__year=year)
        .select_related("assessment_id_FK", "member_id_FK")
    )
    by_member: dict[int, dict] = {}
    for row in rows:
        by_member.setdefault(row.member_id_FK_id, {})[row.assessment_id_FK.month.month] = row

    member_ids = set(by_member)
    active = Member.objects.filter(employment_status="Active").values(
        "member_id_PK", "full_name", "department", "membership_status",
        "member_classification", "date_joined",
    )
    for info in active:
        member_ids.add(info["member_id_PK"])
    members = {
        m.member_id_PK: m
        for m in Member.objects.filter(member_id_PK__in=member_ids)
    }

    grid = []
    for member_id in sorted(members, key=lambda i: (members[i].full_name or "").casefold()):
        member = members[member_id]
        joined = member.date_joined
        classification = (getattr(member, "member_classification", "") or "Teaching")
        is_retired = classification == "Retired" or (member.membership_status or "") == "Retired"
        months = []
        paid_count = open_count = 0
        for month_no in range(1, 13):
            assessment = assessments.get(month_no)
            if is_retired or (joined and (joined.year > year or (joined.year == year and joined.month > month_no))):
                months.append({"month": month_no, "status": "na"})
                continue
            if assessment is None:
                months.append({"month": month_no, "status": "no_assessment"})
                continue
            row = by_member.get(member_id, {}).get(month_no)
            if row is None:
                months.append({
                    "month": month_no, "status": "missing",
                    "required": float(assessment.total_amount),
                })
                open_count += 1
                continue
            actual = Decimal(str(row.actual_deduction or 0))
            balance = Decimal(str(row.outstanding_balance or 0))
            if balance <= Decimal("0.004"):
                status = "paid"
                paid_count += 1
            elif actual > Decimal("0.004"):
                status = "partial"
                open_count += 1
            else:
                # Nothing collected (including excluded-from-batch rows whose
                # balance carries forward): still owed.
                status = "unpaid"
                open_count += 1
            months.append({
                "month": month_no,
                "status": status,
                "required": float(row.standard_assessment),
                "paid_amount": float(actual),
                "balance": float(balance),
            })
        grid.append({
            "member_id": member.member_id_PK,
            "member_name": _formatted_name(member.full_name),
            "department": member.department or "—",
            "classification": classification,
            "date_joined": member.date_joined.isoformat() if member.date_joined else None,
            "months": months,
            "paid_count": paid_count,
            "open_count": open_count,
        })

    available_years = sorted(
        {m.year for m in MonthlyAssessment.objects.values_list("month", flat=True)}
        | {d.year for d in Member.objects.exclude(date_joined__isnull=True).values_list("date_joined", flat=True)}
    )
    return JsonResponse({
        "ok": True,
        "year": year,
        "available_years": available_years,
        "members": grid,
    })


@require_GET
def treasurer_monthly_deduction_members(request: HttpRequest, assessment_id: int):
    """Member roster with the standard assessment for recording (Treasurer)."""
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    assessment = MonthlyAssessment.objects.filter(pk=assessment_id).prefetch_related(
        "items", "workflow_logs",
        "member_assessments", "member_assessments__allocations__assessment_item_id_FK",
    ).first()
    if assessment is None:
        return JsonResponse({"ok": False, "error": "Assessment not found."}, status=404)

    # Roster-load safety net: members enrolled after the handoff (or missed
    # by it) get their missing rows now, so the treasurer never faces an
    # uncollectible member. Lenient per member — a failure here must never
    # break roster loading; the digest tells the popup what happened.
    from core_system.dues_backfill_guard import is_back_dues_chase_enabled

    chase_enabled = is_back_dues_chase_enabled()
    officer = resolve_officer_from_session(request)
    auto_created_notice = ""
    auto_created_results: list = []
    if officer is not None and chase_enabled:
        pending_backfill = list(
            Member.objects.filter(dues_backfill_pending=True)
            .filter(_catchup_eligible_filter())
        )
        if pending_backfill:
            roster_batch = _generate_catchup_for_members(
                pending_backfill, officer, strict=False
            )
            auto_created_notice, _, _ = _auto_create_summary(roster_batch)
            auto_created_results = roster_batch.get("results") or []

    recordable = {
        MonthlyAssessment.STATUS_PENDING_TREASURER,
        MonthlyAssessment.STATUS_REJECTED,
        MonthlyAssessment.STATUS_RETURNED,
    }
    # Non-recordable months stay viewable (read-only) after submission.
    recordable_flag = assessment.status in recordable

    existing = {
        ma.member_id_FK_id: ma
        for ma in MemberAssessment.objects.filter(assessment_id_FK=assessment)
    }

    # Unpaid balances from prior approved months, collectible this month.
    prior_by_member = _prior_outstanding_by_member(exclude_assessment=assessment)

    # Active members, plus anyone already recorded for this month — a member
    # who was recorded while Permanent/Temporary but has since become Retired
    # (By-Laws Sec. 2: exempt from fees) keeps their historical rows visible.
    members = Member.objects.filter(
        Q(membership_status__in=ACTIVE_MEMBERSHIP_STATUSES)
        | Q(monthly_assessment_deductions__assessment_id_FK=assessment)
    ).distinct().order_by("full_name")

    # Strict snapshot: members who joined after this assessment was created
    # are not part of this collection — except anyone already recorded
    # (return/resubmit history is never removed). Their owed months are
    # collected as catch-up with the next month instead.
    excluded_not_joined: list[str] = []
    roster_members = []
    for member in members:
        if member.member_id_PK in existing or _member_eligible_for_assessment(member, assessment):
            roster_members.append(member)
        else:
            excluded_not_joined.append(_formatted_name(member.full_name))

    roster = []
    for member in roster_members:
        recorded = existing.get(member.member_id_PK)
        prior = prior_by_member.get(member.member_id_PK, {})
        # Payment obligation by classification (By-Laws):
        #   Teaching          → owes the FULL assessment (dues + aid funds).
        #   Retired           → owes nothing; kept out of active rosters.
        classification = (
            getattr(member, "member_classification", "") or "Teaching"
        )
        monthly_due_per_member = sum(
            float(item.amount)
            for item in assessment.items.all()
            if item.purpose == AssessmentItem.PURPOSE_MONTHLY_DUE
        )
        # Retired members stay on the roster for visibility but owe nothing
        # and their row is locked; their record is never removed.
        is_retired = classification == "Retired" or (member.membership_status or "") == "Retired"
        dues_required = not is_retired
        if is_retired:
            expected_total = 0.0
        else:
            expected_total = float(assessment.total_amount) - (
                0.0 if dues_required else monthly_due_per_member
            )
        prior_src = prior_by_member.get(member.member_id_PK, {})
        unpaid_months = prior_src.get("months") or []
        if not chase_enabled:
            unpaid_months = [
                um for um in unpaid_months
                if not isinstance(um, dict) or um.get("source") != "catchup"
            ]
        roster.append({
            "member_id": member.member_id_PK,
            "member_name": _formatted_name(member.full_name),
            "department": member.department or "—",
            "email": member.email or "",
            "membership_status": member.membership_status or "",
            "classification": classification,
            "dues_required": dues_required,
            "dues_backfill_pending": bool(
                getattr(member, "dues_backfill_pending", False)
            ) and dues_required and chase_enabled,
            "joined_after_month": _joined_after_month(member, assessment.month),
            "date_joined": member.date_joined.isoformat() if member.date_joined else None,
            # Joined after January of their join year — collection did not
            # start with the calendar year, so prior months may be owed.
            "mid_year_joiner": bool(member.date_joined and member.date_joined.month > 1),
            "monthly_due_per_member": monthly_due_per_member,
            "expected_total": round(expected_total, 2),
            "standard_assessment": float(assessment.total_amount),
            # Unified unpaid months (catch-up drafts + approved outstanding).
            "unpaid_months": unpaid_months,
            # Durable "new member owes back dues" signal for the roster
            # highlight: true while any catch-up-source month still has an
            # open balance. Clears itself the moment the back dues hit zero.
            "has_open_catchup": any(
                m.get("source") == "catchup" and float(m.get("amount", 0)) > 0.004
                for m in unpaid_months
                if isinstance(m, dict)
            ),
            "prior_outstanding": (
                float(recorded.prior_outstanding)
                if recorded
                else float(prior_src.get("amount", 0.0))
            ),
            "prior_month_label": (
                recorded.prior_month or ""
                if recorded
                else prior.get("month_label", "")
            ),

            "recorded_actual": float(recorded.actual_deduction) if recorded else None,
            "recorded_outstanding": float(recorded.outstanding_balance) if recorded else None,
            "recorded_excess": float(recorded.change_amount) if recorded else None,
            "recorded_status": recorded.status if recorded else None,
            "is_excluded": bool(recorded.is_excluded) if recorded else False,
            "recorded_at": recorded.recorded_at.isoformat() if recorded and recorded.recorded_at else None,
            "recorded_item_ids": list(
                recorded.allocations.filter(amount_applied__gt=0).values_list(
                    "assessment_item_id_FK_id", flat=True
                )
            ) if recorded else [],
            # What the member actually paid per deduction item, plus how much
            # of their prior balance this month's collection settled — this is
            # what View Only and the review dashboards display per member.
            # Required honours the member's classification: a Retired member's
            # rows show ₱0.00 required, never the raw item amount.
            "recorded_allocations": [
                {
                    "item_id": a.assessment_item_id_FK.item_id_PK,
                    "purpose_label": a.assessment_item_id_FK.label,
                    "recipient": a.assessment_item_id_FK.recipient or "",
                    "required": float(_item_required_amount(a.assessment_item_id_FK, classification)),
                    "applied": float(a.amount_applied),
                    "remaining": float(a.amount_remaining),
                }
                for a in recorded.allocations.all()
            ] if recorded else [],
            "recorded_prior_outstanding": float(recorded.prior_outstanding) if recorded else 0.0,
            "recorded_prior_collected": float(recorded.prior_outstanding_collected) if recorded else 0.0,
            "recorded_prior_month": (recorded.prior_month or "") if recorded else "",
            # Frozen month context of the recorded carry-over: which months the
            # pooled balance came from and how the payment was spread across
            # them — shown on submitted/read-only rows where the derived
            # unpaid-months list no longer applies.
            "recorded_prior_months": _clean_month_entries(recorded.prior_months) if recorded else [],
            "recorded_prior_collected_months": _clean_month_entries(recorded.prior_collected_months) if recorded else [],
        })

    roster.sort(key=lambda entry: entry["member_name"].casefold())

    return JsonResponse({
        "ok": True,
        "recordable": recordable_flag,
        "flags": {"require_back_dues": chase_enabled},
        "assessment": _serialize_assessment(assessment),
        "items": [_serialize_item(i) for i in assessment.items.all()],
        "members": roster,
        "excluded_not_joined": {
            "count": len(excluded_not_joined),
            "names": sorted(excluded_not_joined),
        },
        "workflow_logs": _serialize_workflow_logs(assessment),
        "auto_created": auto_created_notice,
        "auto_created_results": auto_created_results,
    })


def _member_required_assessment(assessment, classification, items):
    """The assessment amount a member is actually required to pay this month.

    By-Laws classification rules: Teaching members owe the full assessment;
    Retired members owe nothing but stay visible (read-only) so their record
    is never removed."""
    if (classification or "Teaching") == "Retired":
        return Decimal("0.00")
    return assessment.total_amount


def _item_required_amount(item, classification):
    """Per-item required amount for a member's classification."""
    if (classification or "Teaching") == "Retired":
        return Decimal("0.00")
    return item.amount


def _joined_after_month(member, month_start) -> bool:
    """True when the member joined after the calendar month being assessed."""
    if not member.date_joined or not month_start:
        return False
    month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return member.date_joined > month_end


def _assessment_snapshot_date(assessment) -> date | None:
    """Calendar date the assessment was created (membership snapshot point)."""
    created = getattr(assessment, "created_at", None)
    if created is None:
        return None
    try:
        return created.date() if hasattr(created, "date") else created
    except Exception:
        return None


def _member_eligible_for_assessment(member, assessment) -> bool:
    """Strict snapshot rule: only members present at assessment creation are recordable on it.

    A member added after the President created the month's assessment belongs
    to the next collection — even if the month is still unrecorded. Months
    they owe become MemberCatchupDue through the normal catch-up path and are
    collected with their first eligible month. Members without a join date
    stay eligible (legacy rows); a missing creation timestamp also keeps the
    member eligible rather than blocking recording.
    """
    joined = getattr(member, "date_joined", None)
    if not joined:
        return True
    snapshot = _assessment_snapshot_date(assessment)
    if snapshot is None:
        return True
    return joined <= snapshot


def _catchup_month_starts(member) -> list[date]:
    """Mid-year catch-up window as month-start dates, oldest first.

    Legacy Jan-of-join-year .. join-month slice plus the current dues
    container through the backend frontier (see _catchup_window_keys), so a
    member enrolled while collections already run past their join year gets
    every charged month they missed instead of stopping at September 2026.
    """
    joined = getattr(member, "date_joined", None)
    if not joined:
        return []
    keys = sorted(_catchup_window_keys(joined))
    starts = []
    for key in keys:
        try:
            year, month = key.split("-")
            starts.append(date(int(year), int(month), 1))
        except (ValueError, TypeError):
            continue
    return starts


_CATCHUP_RECORDABLE = {
    MonthlyAssessment.STATUS_DRAFT,
    MonthlyAssessment.STATUS_PENDING_TREASURER,
    MonthlyAssessment.STATUS_REJECTED,
    MonthlyAssessment.STATUS_RETURNED,
}


def _ensure_catchup_assessment(month_start, officer) -> MonthlyAssessment:
    """get_or_create a dues-only MonthlyAssessment for a past month (draft if new)."""
    assessment = MonthlyAssessment.objects.filter(month=month_start).first()
    created = False
    if assessment is None:
        dues_amount = Decimal(str(get_monthly_dues_amount())).quantize(CENT)
        assessment = MonthlyAssessment.objects.create(
            month=month_start,
            total_amount=dues_amount,
            status=MonthlyAssessment.STATUS_DRAFT,
            created_by_id_FK=officer,
        )
        created = True
    if not assessment.items.filter(purpose=AssessmentItem.PURPOSE_MONTHLY_DUE).exists():
        dues_amount = Decimal(str(get_monthly_dues_amount())).quantize(CENT)
        AssessmentItem.objects.create(
            assessment_id_FK=assessment,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            custom_label=month_start.strftime("%B %Y"),
            amount=dues_amount,
            recipient="ISUCauFA, Inc.",
            priority_order=1,
        )
        if created or assessment.total_amount <= 0:
            assessment.total_amount = dues_amount
            assessment.save(update_fields=["total_amount"])
    return assessment


def _compact_month_span(months: list) -> str:
    """Compact "2026-01..2026-04" window label for processing popups."""
    keys = [str(m) for m in (months or []) if m]
    if not keys:
        return ""
    try:
        first = datetime.strptime(keys[0], "%Y-%m")
        last = datetime.strptime(keys[-1], "%Y-%m")
    except ValueError:
        return keys[0] if len(keys) == 1 else f"{keys[0]}–{keys[-1]}"
    if keys[0] == keys[-1]:
        return first.strftime("%b %Y")
    if first.year == last.year:
        return f"{first.strftime('%b')}–{last.strftime('%b %Y')}"
    return f"{first.strftime('%b %Y')}–{last.strftime('%b %Y')}"


def _auto_create_summary(batch: dict) -> tuple:
    """Popup-ready summary of a bulk auto-create batch.

    Returns (notice, generated_count, skipped_count) where notice is "" when
    nothing was created — callers stay silent on no-op runs.
    """
    results = batch.get("results") or []
    created = [r for r in results if r.get("generated")]
    if not created:
        return "", 0, batch.get("skipped", 0)
    total = sum(r.get("generated", 0) for r in created)
    parts = [
        f"{r.get('member_name', 'member')}: {_compact_month_span(r.get('months') or [])}"
        for r in created
    ]
    notice = (
        f"{total} missing dues row(s) auto-created for "
        f"{len(created)} new member(s) ({'; '.join(parts)})."
    )
    skipped = batch.get("skipped", 0)
    if skipped:
        notice += f" {skipped} month(s) skipped (already closed)."
    return notice, total, skipped


def _generate_catchup_for_member(member, officer) -> dict:
    """Create Jan..enroll-month dues rows for one mid-year joiner.

    Shared by the manual button, the president-handoff automation, and the
    roster-load safety net so all three behave identically. Returns the
    per-member result dict (generated / already / skipped / message).
    Raises on unexpected errors — callers decide whether one member's
    failure aborts the batch (handoff) or is reported per member (button).

    Gated by the Superadmin back-dues chase switch (default OFF): when
    disabled the flag is cleared and no rows are generated.
    """
    from core_system.dues_backfill_guard import is_back_dues_chase_enabled

    if not is_back_dues_chase_enabled():
        if member.dues_backfill_pending:
            member.dues_backfill_pending = False
            member.save(update_fields=["dues_backfill_pending"])
        return {
            "member_id": member.member_id_PK,
            "member_name": _formatted_name(member.full_name),
            "generated": 0,
            "already": 0,
            "skipped": [],
            "message": "Back-dues chase is disabled — member pays current dues forward.",
        }
    classification = (getattr(member, "member_classification", "") or "Teaching")
    is_retired = classification == "Retired" or (member.membership_status or "") == "Retired"
    months_owed = not is_retired
    window = _catchup_month_starts(member)

    if not window:
        if member.dues_backfill_pending:
            member.dues_backfill_pending = False
            member.save(update_fields=["dues_backfill_pending"])
        return {
            "member_id": member.member_id_PK,
            "member_name": _formatted_name(member.full_name),
            "generated": 0,
            "already": 0,
            "skipped": [],
            "message": "Joined in January — no catch-up months.",
        }

    if not months_owed:
        if member.dues_backfill_pending:
            member.dues_backfill_pending = False
            member.save(update_fields=["dues_backfill_pending"])
        reason = "Retired members owe no monthly dues."
        return {
            "member_id": member.member_id_PK,
            "member_name": _formatted_name(member.full_name),
            "generated": 0,
            "already": 0,
            "skipped": [m.strftime("%Y-%m") for m in window],
            "message": reason,
        }

    generated = 0
    already = 0
    skipped: list[dict] = []

    with transaction.atomic():
        for month_start in window:
            month_key = month_start.strftime("%Y-%m")
            existing_assessment = MonthlyAssessment.objects.filter(month=month_start).first()
            if existing_assessment is not None and (
                existing_assessment.status not in _CATCHUP_RECORDABLE
                or not _member_eligible_for_assessment(member, existing_assessment)
            ):
                # The monthly collection was already deposited/approved before
                # this member enrolled — or it was created before they joined
                # (strict snapshot: they are not part of that collection even
                # while it is still unrecorded).  Do not alter that batch and
                # never add them to it: create a member-specific historical
                # due instead.  It will appear in the next open month as a
                # selectable catch-up item (e.g. Jan–Aug + current September),
                # and payment is booked with the new collection rather than
                # rewriting old ledgers.
                due_item = existing_assessment.items.filter(
                    purpose=AssessmentItem.PURPOSE_MONTHLY_DUE
                ).first()
                amount = (
                    Decimal(str(due_item.amount)).quantize(CENT)
                    if due_item is not None
                    else Decimal(str(get_monthly_dues_amount())).quantize(CENT)
                )
                _due, was_created = MemberCatchupDue.objects.get_or_create(
                    member_id_FK=member,
                    month=month_start,
                    defaults={"amount": amount, "created_by_id_FK": officer},
                )
                if was_created:
                    generated += 1
                    AssessmentWorkflowLog.objects.create(
                        assessment_id_FK=existing_assessment,
                        action="catchup_backfill",
                        performed_by_id_FK=officer,
                        notes=(
                            f"Historical catch-up due created for {_formatted_name(member.full_name)} "
                            f"({member.date_joined.isoformat() if member.date_joined else 'n/a'}), "
                            f"month {month_key}; closed collection was not changed."
                        ),
                    )
                else:
                    already += 1
                continue

            assessment = _ensure_catchup_assessment(month_start, officer)
            dues_item = assessment.items.filter(
                purpose=AssessmentItem.PURPOSE_MONTHLY_DUE
            ).first()
            standard = (
                Decimal(str(dues_item.amount)).quantize(CENT)
                if dues_item
                else Decimal(str(get_monthly_dues_amount())).quantize(CENT)
            )

            _row, created = MemberAssessment.objects.get_or_create(
                assessment_id_FK=assessment,
                member_id_FK=member,
                defaults={
                    "standard_assessment": standard,
                    "actual_deduction": Decimal("0.00"),
                    "outstanding_balance": standard,
                    "status": MemberAssessment.STATUS_PENDING,
                    "recorded_by_id_FK": officer,
                },
            )
            if created:
                generated += 1
                AssessmentWorkflowLog.objects.create(
                    assessment_id_FK=assessment,
                    action="catchup_backfill",
                    performed_by_id_FK=officer,
                    notes=(
                        f"Catch-up dues created for {_formatted_name(member.full_name)} "
                        f"({member.date_joined.isoformat() if member.date_joined else 'n/a'}), "
                        f"month {month_key}."
                    ),
                )
            else:
                already += 1

        # Clear the flag only after every owed month was handled
        # (created, already present, or intentionally skipped).
        if member.dues_backfill_pending:
            member.dues_backfill_pending = False
            member.save(update_fields=["dues_backfill_pending"])

    return {
        "member_id": member.member_id_PK,
        "member_name": _formatted_name(member.full_name),
        "generated": generated,
        "already": already,
        "skipped": skipped,
        "months": [m.strftime("%Y-%m") for m in window],
        "message": (
            f"Created {generated} catch-up month(s)"
            + (f", {already} already present" if already else "")
            + (f", {len(skipped)} skipped" if skipped else "")
            + "."
        ),
    }


def _generate_catchup_for_members(members, officer, *, strict=False) -> dict:
    """Run `_generate_catchup_for_member` over a member list.

    With ``strict=False`` one member's unexpected error is captured into
    their result and the batch continues (manual button, roster safety net).
    With ``strict=True`` the first error propagates so the caller's
    transaction rolls back whole (president handoff: all-or-nothing).
    """
    results = []
    any_generated = False
    for member in members:
        try:
            result = _generate_catchup_for_member(member, officer)
        except Exception as exc:
            logger.exception("Catch-up generation failed for member %s", member.member_id_PK)
            if strict:
                raise
            result = {
                "member_id": member.member_id_PK,
                "member_name": _formatted_name(member.full_name),
                "generated": 0,
                "already": 0,
                "skipped": [],
                "error": str(exc),
            }
        if result.get("generated"):
            any_generated = True
        results.append(result)
    return {
        "results": results,
        "generated": sum(r.get("generated", 0) for r in results),
        "skipped": sum(len(r.get("skipped") or []) for r in results),
        "any_generated": any_generated,
    }


@require_POST
def treasurer_generate_catchup_dues(request: HttpRequest):
    """Create Jan..enroll-month dues rows for mid-year joiners (Treasurer).

    Body: {"member_ids": [int, ...]} or {"all_pending": true}

    Auto-creates missing MonthlyAssessment months as draft with a Monthly Due
    item, then get_or_create's a pending MemberAssessment per owed month.
    """
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session not found."}, status=401)

    from core_system.dues_backfill_guard import is_back_dues_chase_enabled

    if not is_back_dues_chase_enabled():
        return JsonResponse(
            {"ok": False, "error": "Back-dues chase is disabled — members pay current dues forward."},
            status=403,
        )

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)

    member_ids = payload.get("member_ids") or []
    if isinstance(member_ids, (int, str)):
        member_ids = [member_ids]
    try:
        member_ids = [int(mid) for mid in member_ids]
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "member_ids must be a list of integers."}, status=400)

    if not member_ids and payload.get("all_pending"):
        member_ids = list(
            Member.objects.filter(dues_backfill_pending=True)
            .filter(_catchup_eligible_filter())
            .values_list("member_id_PK", flat=True)
        )
    if not member_ids:
        return JsonResponse(
            {"ok": False, "error": "Select at least one member with catch-up dues pending."},
            status=400,
        )

    members = list(Member.objects.filter(member_id_PK__in=member_ids))
    if not members:
        return JsonResponse({"ok": False, "error": "Members not found."}, status=404)

    batch = _generate_catchup_for_members(members, officer)
    results = batch["results"]
    total_generated = batch["generated"]
    total_skipped = batch["skipped"]

    message = (
        f"Created {total_generated} missing dues row(s) across "
        f"{len(results)} member(s)."
        if total_generated
        else "No missing dues rows needed creating."
    )
    if total_skipped:
        message += f" {total_skipped} month(s) skipped (already closed or not owed)."

    if batch["any_generated"]:
        _broadcast_deduction_counts()

    return JsonResponse({
        "ok": True,
        "message": message,
        "generated": total_generated,
        "results": results,
    })


@require_POST
def treasurer_record_monthly_deductions(request: HttpRequest):
    """Record actual deductions per member, auto-allocating by priority (Treasurer).

    Body: {"assessment_id": int, "members": [{"member_id": int,
    "actual_deduction": "350.00"}, ...]}

    Recording replaces any previous (unapproved) entries for the assessment and
    moves it to Pending Auditor Verification.
    """
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)

    payload = _json_body(request)
    assessment = MonthlyAssessment.objects.filter(pk=payload.get("assessment_id")).first()
    if assessment is None:
        return JsonResponse({"ok": False, "error": "Assessment not found."}, status=404)

    recordable = {
        MonthlyAssessment.STATUS_PENDING_TREASURER,
        MonthlyAssessment.STATUS_REJECTED,
        MonthlyAssessment.STATUS_RETURNED,
    }
    if assessment.status not in recordable:
        return JsonResponse({
            "ok": False,
            "error": f"Deductions for {assessment.month_label} can no longer be recorded (current: {assessment.get_status_display()}).",
        }, status=409)

    raw_members = payload.get("members")
    if not isinstance(raw_members, list) or not raw_members:
        return JsonResponse({"ok": False, "error": "At least one member deduction is required."}, status=400)

    # Members the Treasurer left out of this collection batch ("Exclude from
    # Batch"). They still owe the month, so they get zero-amount rows that
    # carry the full expected balance forward and stay visible to the
    # Auditor and President as unpaid.
    excluded_raw = payload.get("excluded_member_ids") or []
    if not isinstance(excluded_raw, list):
        return JsonResponse({"ok": False, "error": "excluded_member_ids must be a list."}, status=400)
    excluded_ids: list[int] = []
    for value in excluded_raw:
        try:
            excluded_id = int(value)
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "excluded_member_ids must be member ids."}, status=400)
        if excluded_id in excluded_ids:
            return JsonResponse({"ok": False, "error": "Duplicate member in excluded_member_ids."}, status=400)
        excluded_ids.append(excluded_id)

    items = list(assessment.items.all())
    if not items:
        return JsonResponse({"ok": False, "error": "This assessment has no breakdown items yet."}, status=400)

    # Snapshot of the collectible carry-over per member, taken once so
    # validation, the write, and the audit entry agree.
    prior_snapshot = _prior_outstanding_by_member(exclude_assessment=assessment)
    returned_prior_snapshot = {
        row.member_id_FK_id: {
            "amount": row.prior_outstanding,
            "month_label": row.prior_month or "",
            "months": _clean_month_entries(row.prior_months),
        }
        for row in MemberAssessment.objects.filter(assessment_id_FK=assessment)
    }

    member_ids = []
    parsed_members = []
    for raw in raw_members:
        if not isinstance(raw, dict):
            return JsonResponse({"ok": False, "error": "Each member entry must be an object."}, status=400)
        try:
            member_id = int(raw.get("member_id"))
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "Each member entry needs a valid member_id."}, status=400)
        if member_id in member_ids:
            return JsonResponse({"ok": False, "error": "Duplicate member in the submission."}, status=400)
        member_ids.append(member_id)

        # The amount typed from the accounting paper.
        actual = _parse_amount(raw.get("actual_deduction"))
        if actual is None:
            return JsonResponse({"ok": False, "error": "Actual deduction amounts must be valid numbers."}, status=400)

        # Optional manual allocation: the treasurer may select exactly which
        # items were funded when the paper disagrees with priority order.
        # Unselected items stay fully outstanding.
        selected_raw = raw.get("selected_item_ids")
        selected_set = None
        selected_total = Decimal("0.00")
        if isinstance(selected_raw, list):
            try:
                selected_set = {int(value) for value in selected_raw}
            except (TypeError, ValueError):
                return JsonResponse({"ok": False, "error": "selected_item_ids must be item ids."}, status=400)
            valid_item_ids = {item.item_id_PK for item in items}
            if not selected_set.issubset(valid_item_ids):
                return JsonResponse({"ok": False, "error": "A selected breakdown item does not belong to this assessment."}, status=400)
            selected_total = sum(
                (item.amount for item in items if item.item_id_PK in selected_set),
                Decimal("0.00"),
            ).quantize(CENT)

        # Partial distribution: the treasurer types how much of the amount
        # deducted lands on each breakdown item. Amounts cannot exceed the
        # item's required figure, and the total cannot exceed the deduction.
        item_amounts_raw = raw.get("item_amounts")
        item_amounts = None
        if isinstance(item_amounts_raw, list):
            item_amounts = {}
            for spec in item_amounts_raw:
                if not isinstance(spec, dict):
                    return JsonResponse({"ok": False, "error": "Each item amount must be an object."}, status=400)
                try:
                    item_id = int(spec.get("item_id"))
                except (TypeError, ValueError):
                    return JsonResponse({"ok": False, "error": "Each item amount needs a valid item_id."}, status=400)
                amount = _parse_amount(spec.get("amount"))
                if amount is None or amount < 0:
                    return JsonResponse({"ok": False, "error": "Item amounts cannot be negative."}, status=400)
                item_amounts[item_id] = amount
            valid_item_ids = {item.item_id_PK for item in items}
            if not set(item_amounts).issubset(valid_item_ids):
                return JsonResponse({"ok": False, "error": "An allocated breakdown item does not belong to this assessment."}, status=400)
            for item in items:
                allocated = item_amounts.get(item.item_id_PK, Decimal("0.00"))
                if allocated > item.amount + Decimal("0.005"):
                    return JsonResponse({
                        "ok": False,
                        "error": f"The allocation for {item.label} exceeds its {item.amount} requirement.",
                    }, status=400)
            applied_total = sum(item_amounts.values(), Decimal("0.00")).quantize(CENT)
            if applied_total > actual + Decimal("0.005"):
                return JsonResponse({
                    "ok": False,
                    "error": "The item allocations add up to more than the amount deducted.",
                }, status=400)

        prior_source = returned_prior_snapshot.get(member_id) or prior_snapshot.get(member_id, {})
        prior_available = Decimal(str(prior_source.get("amount", 0.0)))
        unpaid_month_keys_raw = raw.get("unpaid_month_keys")
        if isinstance(unpaid_month_keys_raw, list) and unpaid_month_keys_raw:
            try:
                selected_keys = {str(k) for k in unpaid_month_keys_raw}
            except (TypeError, ValueError):
                return JsonResponse({"ok": False, "error": "unpaid_month_keys must be month keys."}, status=400)
            available_months = prior_source.get("months") or []
            # Selection keys may target whole months ("2026-02") or one
            # component ("2026-02:dues" / "2026-02:aid"); the cap sums exactly
            # the picked components.
            keyed_months = {
                str(m.get("key")): m for m in available_months
                if isinstance(m, dict)
            }
            selected_total = sum(
                (
                    _component_amount(keyed_months.get(parent), component)
                    if parent in keyed_months
                    else Decimal("0.00")
                )
                for parent, component in
                (_split_month_key(k) for k in selected_keys)
            ).quantize(CENT)
            if selected_keys and available_months:
                prior_available = min(prior_available, selected_total)
        prior_requested = _parse_amount(raw.get("prior_balance_amount")) or Decimal("0.00")
        prior_month_keys = (
            [str(k) for k in unpaid_month_keys_raw]
            if isinstance(unpaid_month_keys_raw, list) and unpaid_month_keys_raw
            else []
        )
        member_row = (
            Member.objects.filter(member_id_PK=member_id)
            .values_list("full_name", "member_classification", "membership_status")
            .first()
        )
        member_name = ((member_row[0] if member_row else None) or f"member #{member_id}")
        member_classification = (member_row[1] if member_row else "") or "Teaching"
        member_status = (member_row[2] if member_row else "") or ""
        member_standard = _member_required_assessment(assessment, member_classification, items)
        # Classification lock: retired members owe nothing at all. The
        # recording table locks these inputs; the server rejects them as a
        # backstop.
        member_is_retired = member_classification == "Retired" or member_status == "Retired"
        if member_is_retired:
            if actual > 0 or prior_requested > 0:
                return JsonResponse({
                    "ok": False,
                    "error": f"{member_name} is retired and cannot be recorded for new months — record 0.00. Earlier records stay visible.",
                }, status=400)
            if item_amounts is not None and any(v > 0 for v in item_amounts.values()):
                return JsonResponse({
                    "ok": False,
                    "error": f"{member_name} is retired and cannot be recorded for new months — record 0.00. Earlier records stay visible.",
                }, status=400)
            if selected_set:
                return JsonResponse({
                    "ok": False,
                    "error": f"{member_name} is retired and cannot be recorded for new months — record 0.00. Earlier records stay visible.",
                }, status=400)
        if prior_requested < 0:
            return JsonResponse({"ok": False, "error": "Prior balance amounts cannot be negative."}, status=400)
        if prior_requested > prior_available + Decimal("0.005"):
            return JsonResponse({"ok": False, "error": "The requested prior balance exceeds the member's available balance."}, status=400)
        if (
            prior_requested > 0
            and item_amounts is None
            and actual + Decimal("0.005") < member_standard + prior_requested
        ):
            return JsonResponse({
                "ok": False,
                "error": f"The deduction for {member_name} must cover their required assessment ({member_standard}) plus the requested prior balance ({prior_requested}).",
            }, status=400)
        if item_amounts is not None:
            item_total = sum(item_amounts.values(), Decimal("0.00"))
            # With new allocation order: prior collected first, then items from remainder
            if item_total > actual - prior_requested + Decimal("0.005"):
                return JsonResponse({
                    "ok": False,
                    "error": "The item allocations exceed the amount available after prior balance payment.",
                }, status=400)
        if selected_set is not None:
            # With new allocation order: prior collected first, then items from remainder
            if selected_total > actual - prior_requested + Decimal("0.005"):
                return JsonResponse({
                    "ok": False,
                    "error": f"The selected items for {member_name} cost more than the money available after prior balance payment.",
                }, status=400)
        parsed_members.append({
            "member_id": member_id,
            "actual_deduction": actual,
            "prior_balance_amount": prior_requested,
            "prior_month_keys": prior_month_keys,
            "selected_ids": sorted(selected_set) if selected_set is not None else None,
            "item_amounts": item_amounts,
        })

    valid_members = Member.objects.filter(member_id_PK__in=member_ids)
    if valid_members.count() != len(set(member_ids)):
        return JsonResponse({"ok": False, "error": "One or more members could not be found."}, status=400)
    overlap = set(member_ids) & set(excluded_ids)
    if overlap:
        return JsonResponse({"ok": False, "error": "A member cannot be both recorded and excluded."}, status=400)
    if excluded_ids:
        existing_excluded = Member.objects.filter(member_id_PK__in=excluded_ids)
        if existing_excluded.count() != len(set(excluded_ids)):
            return JsonResponse({"ok": False, "error": "One or more excluded members could not be found."}, status=400)
    # Strict snapshot backstop: members added after this collection was
    # created cannot be recorded (or excluded) on it — they belong to the
    # next collection, with owed months collected as catch-up.
    ineligible_names = [
        _formatted_name(m.full_name)
        for m in list(valid_members)
        + list(Member.objects.filter(member_id_PK__in=excluded_ids))
        if not _member_eligible_for_assessment(m, assessment)
    ]
    if ineligible_names:
        return JsonResponse({
            "ok": False,
            "error": "These members joined after this collection was created and cannot be recorded on it: "
            + ", ".join(sorted(set(ineligible_names)))
            + ". Their dues will be collected as catch-up with the next month.",
        }, status=409)

    ip = request.META.get("REMOTE_ADDR")
    device_info = request.META.get("HTTP_USER_AGENT", "")

    with transaction.atomic():
        # A resubmission after reject/return replaces the previous entries.
        MemberAssessment.objects.filter(assessment_id_FK=assessment).delete()

        for entry in parsed_members:
            actual = entry["actual_deduction"]
            member_classification = (
                Member.objects.filter(member_id_PK=entry["member_id"])
                .values_list("member_classification", flat=True)
                .first()
                or "Teaching"
            )
            standard = _member_required_assessment(assessment, member_classification, items)
            member_prior = returned_prior_snapshot.get(entry["member_id"]) or prior_snapshot.get(entry["member_id"], {})
            prior_available = Decimal(str(member_prior.get("amount", 0.0)))
            available_months = _clean_month_entries(member_prior.get("months"))
            # Selected unpaid months (unified catch-up + outstanding): when the
            # treasurer picked months to collect, the row's carried snapshot is
            # exactly those months — narrowed to the picked components when
            # only dues or only aid was ticked; otherwise the whole pooled
            # balance carries forward with its months context intact.
            selected_month_keys = entry.get("prior_month_keys") or []
            if selected_month_keys and available_months:
                picked = [_split_month_key(k) for k in selected_month_keys]
                picked_parents = {parent for parent, _comp in picked}
                prior_months_snapshot = []
                for m in available_months:
                    if m["key"] not in picked_parents:
                        continue
                    wanted = {
                        comp for parent, comp in picked
                        if parent == m["key"]
                    }
                    if "" in wanted or wanted >= {"dues", "aid"}:
                        prior_months_snapshot.append(m)
                        continue
                    narrowed = dict(m)
                    narrowed["dues"] = float(
                        _component_amount(m, "dues")) if "dues" in wanted else 0.0
                    narrowed["aid"] = float(
                        _component_amount(m, "aid")) if "aid" in wanted else 0.0
                    narrowed["amount"] = round(
                        narrowed["dues"] + narrowed["aid"], 2)
                    prior_months_snapshot.append(narrowed)
                if prior_months_snapshot:
                    selected_available = sum(
                        (Decimal(str(m["amount"])) for m in prior_months_snapshot),
                        Decimal("0.00"),
                    ).quantize(CENT)
                    prior_available = min(prior_available, selected_available)
                else:
                    prior_months_snapshot = available_months
            else:
                prior_months_snapshot = available_months
            # The display label keeps the months context ("August 2026,
            # September 2026"); legacy rows without a snapshot keep the stored
            # single label. It is compressed to the column width by
            # _fit_month_label (the full list stays in prior_months).
            prior_label = _fit_month_label(
                prior_months_snapshot, member_prior.get("month_label") or ""
            )

            # The frontend sends actual_deduction = the member's real total
            # collection and prior_balance_amount = the portion of it that
            # settles the ticked unpaid months (capped at that total).
            # We split funds: prior_collected comes out of the deduction
            # first (oldest selected month first), then the remainder goes
            # to current month's items — so a dues-only collection clears
            # the oldest unsettled month and this month carries over.
            funds = actual
            prior_requested = entry["prior_balance_amount"]

            # Prior balance is paid from the deduction directly (up to what's available)
            prior_collected = min(prior_requested, prior_available, funds).quantize(CENT)
            current_month_funds = funds - prior_collected

            if entry.get("item_amounts") is not None:
                # Manual partial distribution: each item receives exactly the
                # amount the treasurer typed; the remainder stays outstanding
                # on that item.
                applied_map = {int(k): v for k, v in entry["item_amounts"].items()}
                allocations = [
                    (
                        item,
                        applied_map.get(item.item_id_PK, Decimal("0.00")),
                        (_item_required_amount(item, member_classification) - applied_map.get(item.item_id_PK, Decimal("0.00"))).quantize(CENT),
                    )
                    for item in items
                ]
                applied_total = sum((applied for _, applied, _ in allocations), Decimal("0.00"))
                # This month's shortfall measured against what landed on items
                outstanding_current = max(Decimal("0.00"), standard - applied_total)
            elif entry["selected_ids"] is not None:
                # Manual allocation: exactly the items the treasurer selected
                # are funded (validated to fit within current_month_funds); all
                # other items stay fully outstanding.
                allocations = [
                    (
                        item,
                        _item_required_amount(item, member_classification) if item.item_id_PK in entry["selected_ids"] else Decimal("0.00"),
                        Decimal("0.00") if item.item_id_PK in entry["selected_ids"] else _item_required_amount(item, member_classification),
                    )
                    for item in items
                ]
                applied_total = sum((applied for _, applied, _ in allocations), Decimal("0.00"))
                outstanding_current = max(Decimal("0.00"), standard - applied_total)
            else:
                allocations, _ = _allocate_funds(
                    current_month_funds,
                    items,
                    lambda item: _item_required_amount(item, member_classification),
                )
                outstanding_current = max(Decimal("0.00"), standard - current_month_funds)

            applied_total = sum((applied for _, applied, _ in allocations), Decimal("0.00"))
            # Excess collected beyond the breakdown and prior balance goes to
            # the association funds (stored on the record for reporting).
            excess_to_fund = (funds - applied_total - prior_collected).quantize(CENT)
            if excess_to_fund < 0:
                excess_to_fund = Decimal("0.00")

            # Freeze the pooled carry-over's month context on the row: which
            # months make up prior_outstanding, and how the recorded payment
            # was spread across them. Next month's derivation uses this to
            # settle exactly those months instead of guessing oldest-first.
            prior_collected_months = _attribute_prior_collection(
                prior_months_snapshot, prior_collected, selected_month_keys
            )

            member_assessment = MemberAssessment.objects.create(
                assessment_id_FK=assessment,
                member_id_FK_id=entry["member_id"],
                standard_assessment=standard,
                actual_deduction=actual,
                # This month's shortfall (if any) plus any prior balance left
                # uncollected — this is what carries into next month.
                outstanding_balance=(
                    outstanding_current
                    + (prior_available - prior_collected)
                ).quantize(CENT),
                status=MemberAssessment.STATUS_PENDING,
                recorded_by_id_FK=officer,
                prior_outstanding=prior_available,
                prior_outstanding_collected=prior_collected,
                prior_month=prior_label or None,
                prior_months=prior_months_snapshot or None,
                prior_collected_months=prior_collected_months or None,
                change_amount=excess_to_fund,
            )
            MemberAssessmentAllocation.objects.bulk_create([
                MemberAssessmentAllocation(
                    member_assessment_id_FK=member_assessment,
                    assessment_item_id_FK=item,
                    amount_applied=applied,
                    amount_remaining=remaining,
                )
                for item, applied, remaining in allocations
            ])

            # NOTE: no FundTransaction entries here. The ISUCauFA, Inc. fund only
            # reflects a month once the President final-approves it (same rule
            # as every other money-in flow) — the entries are written in
            # president_approve_monthly_deductions.

        # Zero-amount rows for members excluded from this batch: nothing was
        # deducted, so the full classification-adjusted standard plus any
        # collectible prior carries forward, and the row stays visible
        # downstream (Auditor / President / heatmap / ledgers) as unpaid.
        for excluded_id in excluded_ids:
            excluded_classification = (
                Member.objects.filter(member_id_PK=excluded_id)
                .values_list("member_classification", flat=True)
                .first()
                or "Teaching"
            )
            excluded_standard = _member_required_assessment(
                assessment, excluded_classification, items
            )
            # Use returned_prior_snapshot (from previously recorded rows) so that
            # resubmitting a rejected/returned assessment preserves the prior
            # balance for excluded members. Fall back to prior_snapshot for new exclusions.
            excluded_prior = returned_prior_snapshot.get(excluded_id) or prior_snapshot.get(excluded_id, {})
            excluded_prior_available = Decimal(str(excluded_prior.get("amount", 0.0)))
            excluded_months = _clean_month_entries(excluded_prior.get("months"))
            excluded_prior_label = _fit_month_label(
                excluded_months, excluded_prior.get("month_label") or ""
            )
            excluded_assessment = MemberAssessment.objects.create(
                assessment_id_FK=assessment,
                member_id_FK_id=excluded_id,
                standard_assessment=excluded_standard,
                actual_deduction=Decimal("0.00"),
                outstanding_balance=(
                    excluded_standard + excluded_prior_available
                ).quantize(CENT),
                status=MemberAssessment.STATUS_PENDING,
                recorded_by_id_FK=officer,
                prior_outstanding=excluded_prior_available,
                prior_outstanding_collected=Decimal("0.00"),
                prior_month=excluded_prior_label or None,
                prior_months=excluded_months or None,
                change_amount=Decimal("0.00"),
                is_excluded=True,
            )
            MemberAssessmentAllocation.objects.bulk_create([
                MemberAssessmentAllocation(
                    member_assessment_id_FK=excluded_assessment,
                    assessment_item_id_FK=item,
                    amount_applied=Decimal("0.00"),
                    amount_remaining=_item_required_amount(item, excluded_classification),
                )
                for item in items
            ])

        # Default behaviour submits the recorded batch for deposit; the
        # overview's "Save Draft" passes submit:false and keeps the month
        # recordable. The Auditor only sees it after the Treasurer deposits.
        submit = payload.get("submit") is not False
        if submit:
            assessment.status = MonthlyAssessment.STATUS_PENDING_DEPOSIT
            assessment.auditor_remarks = None
            assessment.president_remarks = None
        assessment.save()

        log_action = "treasurer_submit" if submit else "treasurer_save_draft"
        excluded_note = f" ({len(excluded_ids)} excluded from batch)" if excluded_ids else ""
        log_notes = (
            f"Recorded deductions for {len(parsed_members)} member(s){excluded_note} and submitted for deposit."
            if submit
            else f"Saved draft deductions for {len(parsed_members)} member(s){excluded_note}."
        )
        AssessmentWorkflowLog.objects.create(
            assessment_id_FK=assessment,
            action=log_action,
            performed_by_id_FK=officer,
            notes=log_notes,
        )
        _record_audit_trail(
            table=ASSESSMENT_TABLE,
            record_id=assessment.assessment_id_PK,
            action="SUBMIT" if submit else "SAVE_DRAFT",
            actor=officer,
            new=_audit_safe({"status": assessment.status, "members": parsed_members}),
            ip=ip,
            device_info=device_info,
            notes=log_notes,
        )

    _broadcast_deduction_counts()
    member_records = MemberAssessment.objects.filter(assessment_id_FK=assessment)
    total_recorded = sum(
        (ma.actual_deduction for ma in member_records),
        Decimal("0.00"),
    ).quantize(CENT)
    total_outstanding = sum(
        (ma.outstanding_balance for ma in member_records),
        Decimal("0.00"),
    ).quantize(CENT)
    total_change = sum(
        (ma.change_amount for ma in member_records),
        Decimal("0.00"),
    ).quantize(CENT)

    _notify_role(
        "Treasurer",
        f"The {assessment.month_label} monthly deduction batch ({len(parsed_members)} member(s)) "
        f"is ready for deposit.",
        url="/treasurer/",
    )

    return JsonResponse({
        "ok": True,
        "message": (
            f"{len(parsed_members)} deduction(s) recorded for {assessment.month_label} and "
            + ("submitted for deposit." if submit else "saved as draft.")
            + (f" {len(excluded_ids)} member(s) excluded from the batch (carried as unpaid)." if excluded_ids else "")
            + f" Total deducted: {total_recorded}, total outstanding: {total_outstanding}, excess to ISUCauFA funds: {total_change}."
        ),
        "total_recorded": float(total_recorded),
        "total_outstanding": float(total_outstanding),
        "total_change": float(total_change),
    })


# ---------------------------------------------------------------------------
# Deposit step (Treasurer) — evidence only, no fund write here
# ---------------------------------------------------------------------------

@require_GET
def treasurer_pending_deposit_collections(request: HttpRequest):
    """Month-batches the Treasurer recorded but has not yet deposited."""
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    assessments = MonthlyAssessment.objects.filter(
        status=MonthlyAssessment.STATUS_PENDING_DEPOSIT
    ).prefetch_related("items", "member_assessments", "documents").order_by("-month")
    return JsonResponse({
        "ok": True,
        "collections": [_serialize_assessment(a) for a in assessments],
    })


@require_POST
def treasurer_deposit_collection(request: HttpRequest):
    """Record the bank deposit of a recorded batch (Treasurer).

    Creates zero fund rows — the deposit is evidence (reference, slip,
    timestamp). The fund only moves when the President final-approves.
    The amount is locked to the batch's recorded total; a batch can be
    deposited exactly once (409 on any later attempt).
    """
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)

    ip = request.META.get("REMOTE_ADDR")
    device_info = request.META.get("HTTP_USER_AGENT", "")

    def _failed(error: str, assessment=None, status: int = 400) -> JsonResponse:
        if assessment is not None:
            _record_audit_trail(
                table=ASSESSMENT_TABLE,
                record_id=assessment.assessment_id_PK,
                action="DEPOSIT",
                actor=officer,
                result="Failed",
                ip=ip,
                device_info=device_info,
                notes=f"Deposit attempt failed: {error}",
            )
        return JsonResponse({"ok": False, "error": error}, status=status)

    assessment_id = (request.POST.get("assessment_id") or "").strip()
    if not assessment_id.isdigit():
        return _failed("assessment_id is required.")
    assessment = MonthlyAssessment.objects.filter(pk=int(assessment_id)).first()
    if assessment is None:
        return JsonResponse({"ok": False, "error": "Assessment not found."}, status=404)
    if assessment.status != MonthlyAssessment.STATUS_PENDING_DEPOSIT:
        return _failed(
            f"Only batches pending deposit can be actioned (current: {assessment.get_status_display()}).",
            assessment=assessment,
            status=409,
        )

    recorded_total = sum(
        (ma.actual_deduction for ma in assessment.member_assessments.all()),
        Decimal("0.00"),
    ).quantize(CENT)

    already_deposited = (
        assessment.deposited_amount
        if assessment.deposited_amount is not None
        else Decimal("0.00")
    )
    remaining_total = (recorded_total - already_deposited).quantize(CENT)
    if remaining_total <= 0:
        return _failed(
            "This batch is already fully deposited and awaits verification.",
            assessment=assessment,
            status=409,
        )

    deposit_reference = (request.POST.get("deposit_reference") or "").strip()
    if not deposit_reference:
        return _failed("Deposit reference is required.", assessment=assessment)
    if len(deposit_reference) > 100:
        return _failed("Deposit reference is too long (max 100 characters).", assessment=assessment)

    # Partial deposits are allowed: the amount defaults to the full remaining
    # balance, and anything between 0.01 and the remaining balance is accepted.
    # The batch only moves to the Auditor once the cumulative deposits reach
    # the recorded total.
    raw_amount = (request.POST.get("deposited_amount") or "").strip()
    if raw_amount:
        try:
            given_amount = Decimal(raw_amount).quantize(CENT)
        except (InvalidOperation, ValueError):
            return _failed("Deposited amount must be a number.", assessment=assessment)
        if given_amount <= 0:
            return _failed("Deposited amount must be greater than zero.", assessment=assessment)
        if given_amount > remaining_total:
            return _failed(
                f"Deposited amount exceeds the remaining balance to deposit (₱{remaining_total}). "
                f"Partial deposits are allowed up to that amount.",
                assessment=assessment,
            )
    else:
        given_amount = remaining_total

    new_deposited_total = (already_deposited + given_amount).quantize(CENT)
    deposit_complete = new_deposited_total >= recorded_total

    slip = request.FILES.get("proof")
    if slip is None:
        return _failed("Deposit slip is required.", assessment=assessment)
    from core_system.secure_upload import SecureUploadError, validate_and_store

    try:
        saved_slip = validate_and_store(
            slip,
            subdir="secure_uploads/assessment_documents",
            allowed_extensions={"jpg", "jpeg", "png", "webp", "gif", "pdf"},
            max_bytes=DOC_MAX_BYTES,
        )
    except SecureUploadError as exc:
        return _failed(exc.message, assessment=assessment, status=exc.status)
    # Same slip must not be filed twice on one month (exact bytes or the
    # same image under a different filename).
    dup_q = Q(content_sha256=saved_slip["sha256"])
    if saved_slip["norm_sha256"]:
        dup_q |= Q(norm_sha256=saved_slip["norm_sha256"])
    dup_exists = MonthlyAssessmentDocument.objects.filter(
        assessment_id_FK=assessment,
    ).filter(dup_q).exists()
    if dup_exists:
        return _failed(
            "This deposit slip image is already filed for "
            f"{assessment.month_label} (same image content, regardless of filename).",
            assessment=assessment,
            status=409,
        )

    collection_ref = f"COL-{assessment.assessment_id_PK:05d}"
    try:
        with transaction.atomic():
            locked = MonthlyAssessment.objects.select_for_update().get(pk=assessment.pk)
            if locked.status != MonthlyAssessment.STATUS_PENDING_DEPOSIT:
                return _failed(
                    f"Batch was actioned elsewhere (current: {locked.get_status_display()}).",
                    assessment=locked,
                    status=409,
                )
            # Re-derive the remaining balance under the row lock so two
            # simultaneous partial deposits can never overshoot the total.
            locked_already = (
                locked.deposited_amount
                if locked.deposited_amount is not None
                else Decimal("0.00")
            )
            locked_remaining = (recorded_total - locked_already).quantize(CENT)
            if given_amount > locked_remaining:
                return _failed(
                    f"Deposited amount exceeds the remaining balance to deposit (₱{locked_remaining}).",
                    assessment=locked,
                    status=409,
                )
            locked_new_total = (locked_already + given_amount).quantize(CENT)
            locked_complete = locked_new_total >= recorded_total

            now = timezone.now()
            locked.deposit_reference = deposit_reference
            locked.deposited_amount = locked_new_total
            locked.deposited_at = now
            locked.deposited_by_id_FK = officer
            if locked_complete:
                locked.status = MonthlyAssessment.STATUS_PENDING_AUDIT
            locked.save(update_fields=[
                "deposit_reference", "deposited_amount", "deposited_at",
                "deposited_by_id_FK", "status", "updated_at",
            ])

            MonthlyAssessmentDocument.objects.create(
                assessment_id_FK=locked,
                kind=DEPOSIT_SLIP_KIND,
                image=saved_slip["stored_name"],
                content_sha256=saved_slip["sha256"],
                norm_sha256=saved_slip["norm_sha256"] or "",
                uploaded_by_id_FK=officer,
            )
            if locked_complete:
                workflow_note = (
                    f"Deposited {collection_ref} — ref {deposit_reference}, "
                    f"₱{locked_new_total}, slip: {Path(slip.name).name}. Submitted for audit."
                )
            else:
                locked_remaining_after = (recorded_total - locked_new_total).quantize(CENT)
                workflow_note = (
                    f"Partial deposit for {collection_ref} — ref {deposit_reference}, "
                    f"₱{given_amount} (cumulative ₱{locked_new_total} of ₱{recorded_total}), "
                    f"slip: {Path(slip.name).name}. Remaining to deposit: ₱{locked_remaining_after}."
                )
            AssessmentWorkflowLog.objects.create(
                assessment_id_FK=locked,
                action="treasurer_deposit",
                performed_by_id_FK=officer,
                notes=workflow_note,
            )
            _record_audit_trail(
                table=ASSESSMENT_TABLE,
                record_id=locked.assessment_id_PK,
                action="DEPOSIT",
                actor=officer,
                old={"status": MonthlyAssessment.STATUS_PENDING_DEPOSIT},
                new={
                    "status": locked.status,
                    "deposit_reference": deposit_reference,
                    "deposited_amount": float(locked_new_total),
                    "deposited_this_transaction": float(given_amount),
                    "partial": not locked_complete,
                },
                ip=ip,
                device_info=device_info,
                notes=(
                    f"Treasurer deposited {collection_ref} ({assessment.month_label})"
                    + ("" if locked_complete else " — partial")
                ),
            )
    except IntegrityError:
        return _failed("Deposit could not be saved.", assessment=assessment, status=500)
    except DataError:
        from django.core.files.storage import default_storage
        try:
            default_storage.delete(saved_slip["stored_name"])
        except Exception:
            pass
        return _failed(
            "Deposit slip upload failed: the generated file path is too long for the "
            "database. Rename the file to something shorter and try again.",
            assessment=assessment,
            status=400,
        )

    _broadcast_deduction_counts()
    if deposit_complete:
        _notify_role(
            "Auditor",
            f"The {assessment.month_label} monthly deduction batch ({collection_ref}) was "
            f"deposited in full (ref {deposit_reference}, ₱{new_deposited_total}) and awaits verification.",
            url="/auditor/",
        )
    assessment.refresh_from_db()
    remaining_after = max(
        0.0,
        float(recorded_total) - float(assessment.deposited_amount or 0),
    )
    return JsonResponse({
        "ok": True,
        "completed": deposit_complete,
        "remaining_to_deposit": remaining_after,
        "message": (
            (
                f"{collection_ref} deposited in full (ref {deposit_reference}, "
                f"₱{new_deposited_total}) and submitted to the Auditor."
            )
            if deposit_complete
            else (
                f"Partial deposit recorded — ₱{given_amount} received "
                f"(₱{remaining_after} still to deposit for {collection_ref})."
            )
        ),
        "assessment": _serialize_assessment(assessment),
    })


# ---------------------------------------------------------------------------
# Auditor endpoints
# ---------------------------------------------------------------------------

@require_GET
def auditor_monthly_deductions_queue(request: HttpRequest):
    """Assessments awaiting verification, plus recently actioned ones (Auditor)."""
    guard = require_role(request, role=["Auditor", "President"])
    if guard is not None:
        return guard

    pending = MonthlyAssessment.objects.filter(
        status=MonthlyAssessment.STATUS_PENDING_AUDIT
    ).prefetch_related("items", "member_assessments", "documents")

    recent = MonthlyAssessment.objects.exclude(
        status=MonthlyAssessment.STATUS_PENDING_AUDIT
    ).exclude(status=MonthlyAssessment.STATUS_DRAFT).prefetch_related(
        "items", "member_assessments", "documents"
    )[:10]

    return JsonResponse({
        "ok": True,
        "pending": [_serialize_assessment(a) for a in pending],
        "recent": [_serialize_assessment(a) for a in recent],
    })


@require_GET
def auditor_monthly_deduction_detail(request: HttpRequest, assessment_id: int):
    """Full detail of one assessment for verification (Auditor)."""
    guard = require_role(request, role=["Auditor", "President"])
    if guard is not None:
        return guard

    assessment = MonthlyAssessment.objects.filter(pk=assessment_id).prefetch_related(
        "items", "workflow_logs", "documents",
        "member_assessments__member_id_FK",
        "member_assessments__allocations__assessment_item_id_FK",
    ).first()
    if assessment is None:
        return JsonResponse({"ok": False, "error": "Assessment not found."}, status=404)

    return JsonResponse({
        "ok": True,
        "assessment": _serialize_assessment(assessment),
        "member_assessments": [
            _serialize_member_assessment(ma)
            for ma in sorted(
                assessment.member_assessments.all(),
                key=lambda ma: _formatted_name(ma.member_id_FK.full_name).casefold(),
            )
        ],
        "workflow_logs": _serialize_workflow_logs(assessment),
    })


@require_POST
def auditor_verify_monthly_deductions(request: HttpRequest):
    """Verify or reject the Treasurer's recorded deductions (Auditor)."""
    guard = require_role(request, role="Auditor")
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)

    payload = _json_body(request)
    action = (payload.get("action") or "").strip().lower()
    notes = (payload.get("notes") or "").strip()
    if action not in ("approve", "reject"):
        return JsonResponse({"ok": False, "error": "Action must be 'approve' or 'reject'."}, status=400)

    assessment = MonthlyAssessment.objects.filter(pk=payload.get("assessment_id")).first()
    if assessment is None:
        return JsonResponse({"ok": False, "error": "Assessment not found."}, status=404)
    if assessment.status != MonthlyAssessment.STATUS_PENDING_AUDIT:
        return JsonResponse({
            "ok": False,
            "error": f"Only assessments pending verification can be actioned (current: {assessment.get_status_display()}).",
        }, status=409)

    if action == "reject" and not notes:
        return JsonResponse({"ok": False, "error": "Remarks are required when rejecting an entry."}, status=400)

    ip = request.META.get("REMOTE_ADDR")
    device_info = request.META.get("HTTP_USER_AGENT", "")

    if action == "approve":
        assessment.status = MonthlyAssessment.STATUS_PENDING_FINAL
        assessment.auditor_remarks = notes or None
        assessment.save()

        member_assessments = list(assessment.member_assessments.all())
        for member_assessment in member_assessments:
            member_assessment.status = MemberAssessment.STATUS_VERIFIED
            member_assessment.verified_by_id_FK = officer
            member_assessment.verified_at = assessment.updated_at
        MemberAssessment.objects.bulk_update(
            member_assessments, ["status", "verified_by_id_FK", "verified_at"]
        )

        AssessmentWorkflowLog.objects.create(
            assessment_id_FK=assessment,
            action="auditor_verify",
            performed_by_id_FK=officer,
            notes=notes or "Entries verified.",
        )
        _record_audit_trail(
            table=ASSESSMENT_TABLE,
            record_id=assessment.assessment_id_PK,
            action="VERIFY",
            actor=officer,
            old={"status": MonthlyAssessment.STATUS_PENDING_AUDIT},
            new={"status": assessment.status},
            ip=ip,
            device_info=device_info,
            notes=f"Auditor verified {assessment.month_label} monthly deduction entries",
        )
        _broadcast_deduction_counts()
        _notify_role(
            "President",
            f"The {assessment.month_label} monthly deduction is verified and awaiting your final approval.",
            url="/president/",
        )
        message = f"{assessment.month_label} entries verified and endorsed to the President."
    else:
        member_rows = list(assessment.member_assessments.all())
        for member_assessment in member_rows:
            member_assessment.status = MemberAssessment.STATUS_PENDING
            member_assessment.verified_by_id_FK = None
            member_assessment.verified_at = None
            member_assessment.approved_by_id_FK = None
            member_assessment.approved_at = None
        MemberAssessment.objects.bulk_update(
            member_rows,
            ["status", "verified_by_id_FK", "verified_at", "approved_by_id_FK", "approved_at"],
        )

        member_ids = [row.member_assessment_id_PK for row in member_rows]
        if member_ids:
            MemberLedger.objects.filter(
                reference_type="MemberAssessment",
                reference_id__in=member_ids,
            ).delete()
            delete_member_fund_rows(member_ids)

        assessment.status = MonthlyAssessment.STATUS_REJECTED
        assessment.auditor_remarks = notes
        invalidated_ref = _invalidate_deposit_evidence(assessment)
        assessment.save()

        AssessmentWorkflowLog.objects.create(
            assessment_id_FK=assessment,
            action="auditor_reject",
            performed_by_id_FK=officer,
            notes=notes,
        )
        if invalidated_ref:
            AssessmentWorkflowLog.objects.create(
                assessment_id_FK=assessment,
                action="deposit_invalidated",
                performed_by_id_FK=officer,
                notes=(
                    f"Deposit {invalidated_ref} invalidated by auditor rejection — "
                    "slip kept for trace; re-record then re-deposit required."
                ),
            )
        _record_audit_trail(
            table=ASSESSMENT_TABLE,
            record_id=assessment.assessment_id_PK,
            action="REJECT",
            actor=officer,
            old={"status": MonthlyAssessment.STATUS_PENDING_AUDIT},
            new={"status": assessment.status, "auditor_remarks": notes},
            ip=ip,
            device_info=device_info,
            notes=f"Auditor rejected {assessment.month_label} monthly deduction entries",
        )
        _broadcast_deduction_counts()
        _notify_role(
            "Treasurer",
            f"Auditor rejected the {assessment.month_label} monthly deduction: {notes}",
            url="/treasurer/",
        )
        message = f"{assessment.month_label} entries rejected and returned to the Treasurer."

    return JsonResponse({"ok": True, "message": message})


# ---------------------------------------------------------------------------
# Deduction compliance heatmap + member notifications (Auditor)
# ---------------------------------------------------------------------------

@require_GET
def deduction_compliance_heatmap(request: HttpRequest):
    """Department and member compliance for one monthly assessment.

    GET params: assessment_id (optional — defaults to the latest month).
    Members are classified as full / partial / zero / pending, departments
    get a collection rate = collected / expected, and each member row carries
    its outstanding balance so the Auditor can notify non-payers.
    """
    guard = require_role(request, role=["Auditor", "President", "Treasurer"])
    if guard is not None:
        return guard

    assessments = list(MonthlyAssessment.objects.order_by("-month"))
    if not assessments:
        return JsonResponse({
            "ok": True, "assessments": [], "assessment": None,
            "departments": [], "members": [], "totals": {},
            "notify_allowed": False,
            "notice": "No monthly assessments yet.",
        })

    raw_id = (request.GET.get("assessment_id") or "").strip()
    assessment = None
    if raw_id.isdigit():
        assessment = next(
            (a for a in assessments if a.assessment_id_PK == int(raw_id)), None
        )
    if assessment is None:
        assessment = assessments[0]

    # Until the Treasurer records the deductions, there is nothing to audit
    # or notify about — members and the notify button stay hidden.
    notify_allowed = assessment.status not in (
        MonthlyAssessment.STATUS_DRAFT,
        MonthlyAssessment.STATUS_PENDING_TREASURER,
    )

    # Approved months are frozen history: every member displays exactly as
    # they were when the month was approved, even if someone retired
    # afterwards. Only live (still processing) months apply the current
    # retired status.
    frozen = assessment.status == MonthlyAssessment.STATUS_FINAL_APPROVED

    standard = float(assessment.total_amount)
    items = list(assessment.items.all())
    # Active members, plus retired members who already have a record for
    # this month — a member retired after being recorded keeps their
    # historical rows visible; retired members with no record here are
    # skipped in the loop below (they belong to no roster this month).
    members = list(Member.objects.filter(
        Q(membership_status__in=ACTIVE_MEMBERSHIP_STATUSES)
        | Q(monthly_assessment_deductions__assessment_id_FK=assessment)
    ).distinct())
    members.sort(key=lambda m: _formatted_name(m.full_name).casefold())
    records = {
        ma.member_id_FK_id: ma
        for ma in assessment.member_assessments.select_related("member_id_FK")
    }

    dept_order = []
    dept_map: dict[str, dict] = {}
    member_rows = []
    totals = {"expected": 0.0, "collected": 0.0, "counted": 0.0, "outstanding": 0.0,
              "full": 0, "partial": 0, "zero": 0, "pending": 0, "retired": 0,
              "v_pending": 0, "v_verified": 0, "v_approved": 0, "v_none": 0,
              "credit": 0.0, "returned_months": 0}

    for member in members:
        classification = (getattr(member, "member_classification", "") or "Teaching")
        currently_retired = classification == "Retired" or (member.membership_status or "") == "Retired"
        ma = records.get(member.member_id_PK)
        if currently_retired and ma is None:
            # Retired with no history this month: in no roster, skip entirely.
            continue
        # Live months show retired members as "Retired" (they owe nothing
        # more); approved months stay exactly as approved, ignoring any
        # retirement that happened afterwards.
        is_retired = (not frozen) and currently_retired
        dept = member.department or "Unassigned"
        if dept not in dept_map:
            dept_map[dept] = {
                "department": dept, "members": 0, "full": 0, "partial": 0,
                "zero": 0, "pending": 0, "retired": 0, "expected": 0.0, "collected": 0.0,
                "counted": 0.0, "outstanding": 0.0,
            }
            dept_order.append(dept)
        bucket = dept_map[dept]
        bucket["members"] += 1
        # Obligation by classification (By-Laws): Teaching owes the full
        # assessment. A retired member with a record keeps their historical
        # row visible as-is with a "retired" status — they owe nothing
        # further, so they never count as paid/partial/unpaid. A member who
        # owes nothing counts as fully paid — never "Unpaid".
        if is_retired:
            required = 0.0
            actual = float(ma.actual_deduction)
            outstanding = float(ma.outstanding_balance)
            change = float(ma.change_amount)
            status = "retired"
        elif ma is not None:
            required = float(ma.standard_assessment)
        else:
            required = float(_member_required_assessment(assessment, classification, items))
        bucket["expected"] += required
        totals["expected"] += required

        if not is_retired:
            if ma is None:
                status = "pending"
                actual = 0.0
                outstanding = required
                change = 0.0
            else:
                actual = float(ma.actual_deduction)
                outstanding = float(ma.outstanding_balance)
                change = float(ma.change_amount)
                if required <= 0 and outstanding <= 0:
                    status = "full"
                elif actual <= 0:
                    status = "zero"
                elif actual < required:
                    status = "partial"
                else:
                    status = "full"

        bucket[status] += 1
        # "Collected" reports the money actually deducted, but the collection
        # rate counts at most this month's standard per member: an
        # over-deduction settles a prior month's carry-over, not this
        # month's assessment, so it must not push the rate past 100%.
        bucket["collected"] += actual
        bucket["counted"] += min(actual, required)
        bucket["outstanding"] += outstanding
        totals[status] += 1
        totals["collected"] += actual
        totals["counted"] += min(actual, required)
        totals["outstanding"] += outstanding

        vkey = "v_" + (ma.status if ma is not None else "none")
        bucket[vkey] = bucket.get(vkey, 0) + 1
        totals[vkey] = totals.get(vkey, 0) + 1
        if ma is not None:
            totals["credit"] += change

        if not notify_allowed:
            continue
        allocations = []
        if ma is not None:
            for al in ma.allocations.select_related("assessment_item_id_FK").order_by(
                "assessment_item_id_FK__priority_order", "allocation_id_PK"
            ):
                allocations.append({
                    "label": al.assessment_item_id_FK.label,
                    "applied": float(al.amount_applied),
                    "remaining": float(al.amount_remaining),
                })

        member_rows.append({
            "member_id": member.member_id_PK,
            "member_name": _formatted_name(member.full_name),
            "department": dept,
            "status": status,
            "verify_status": ma.status if ma is not None else None,
            "recorded": ma is not None,
            "standard": required,
            "actual": actual,
            "outstanding": outstanding,
            "credit": change,
            "allocations": allocations,
            "email": member.email or "",
        })

    departments = []
    for dept in dept_order:
        bucket = dept_map[dept]
        if bucket["expected"] > 0:
            rate = bucket["counted"] / bucket["expected"] * 100
        else:
            # Nothing was owed in this department — trivially fully collected.
            rate = 100.0
        departments.append({**bucket, "rate": round(rate, 1)})
    departments.sort(key=lambda d: d["rate"])  # worst first — problems surface
    totals["returned_months"] = sum(
        1 for a in assessments
        if a.status in (MonthlyAssessment.STATUS_REJECTED, MonthlyAssessment.STATUS_RETURNED)
    )

    overall_rate = (totals["counted"] / totals["expected"] * 100) if totals["expected"] else 100.0

    member_count = len(member_rows)
    # Obligation-aware expected per item: Retired members owe nothing — a
    # plain per-member x headcount would overstate the expected total.
    member_classes = []
    for m in members:
        cls = (getattr(m, "member_classification", "") or "Teaching")
        m_retired = cls == "Retired" or (m.membership_status or "") == "Retired"
        if m_retired and not frozen:
            # Live months: retired members owe nothing, so they add no
            # expected amount. Approved months stay as approved instead.
            continue
        member_classes.append(cls)
    applied_by_item = {
        row["assessment_item_id_FK_id"]: float(row["applied"] or 0)
        for row in MemberAssessmentAllocation.objects.filter(
            member_assessment_id_FK__assessment_id_FK=assessment
        ).values("assessment_item_id_FK_id").annotate(applied=Sum("amount_applied"))
    }
    breakdown = []
    other_rows = []
    other_purposes = {AssessmentItem.PURPOSE_OTHER, AssessmentItem.PURPOSE_TOKEN_INCENTIVE}
    for item in assessment.items.all():
        amount = float(item.amount)
        collected = applied_by_item.get(item.item_id_PK, 0.0)
        item_expected = round(
            sum(float(_item_required_amount(item, c)) for c in member_classes), 2
        )
        row = {
            "label": item.label,
            "per_member": amount,
            "expected": item_expected,
            "collected": round(collected, 2),
            "pct": round(
                (collected / item_expected * 100) if item_expected else 0, 1
            ),
        }
        if item.purpose in other_purposes:
            other_rows.append(row)
        else:
            breakdown.append(row)
    if other_rows:
        other_expected = sum(r["expected"] for r in other_rows)
        other_collected = sum(r["collected"] for r in other_rows)
        breakdown.append({
            "label": "Other",
            "per_member": round(sum(r["per_member"] for r in other_rows), 2),
            "expected": round(other_expected, 2),
            "collected": round(other_collected, 2),
            "pct": round(
                (other_collected / other_expected * 100) if other_expected else 0, 1
            ),
            "sub_items": [
                {k: r[k] for k in ("label", "per_member", "expected", "collected", "pct")}
                for r in sorted(other_rows, key=lambda r: -r["per_member"])
            ],
        })
    # Prior-balance money collected with this month's deductions is part of
    # the collected total but belongs to no allocation item — list it on its
    # own row so per-item collected sums reconcile with the totals.
    prior_collected = (
        MemberAssessment.objects.filter(assessment_id_FK=assessment)
        .aggregate(t=Sum("prior_outstanding_collected"))["t"]
        or 0
    )
    if float(prior_collected) > 0.005:
        breakdown.append({
            "label": "Prior Balance Collected",
            "per_member": 0.0,
            "expected": 0.0,
            "collected": round(float(prior_collected), 2),
            "pct": 0.0,
        })
    per_assessment = {
        row["assessment_id_PK"]: row
        for row in MonthlyAssessment.objects.annotate(
            collected=Sum("member_assessments__actual_deduction"),
            recorded=Count("member_assessments"),
        ).values("assessment_id_PK", "collected", "recorded")
    }
    returned_months = sum(
        1 for a in assessments
        if a.status in (MonthlyAssessment.STATUS_REJECTED, MonthlyAssessment.STATUS_RETURNED)
    )

    # ISUCauFA funds view of the monthly deductions: collections only count
    # as fund money once the President gives the final approval; until then
    # they sit in the awaiting-approval bucket.
    funds = {"finalized": 0.0, "pending_approval": 0.0}
    for a in assessments:
        collected = float((per_assessment.get(a.assessment_id_PK) or {}).get("collected") or 0)
        if a.status == MonthlyAssessment.STATUS_FINAL_APPROVED:
            funds["finalized"] += collected
        elif a.status in (
            MonthlyAssessment.STATUS_PENDING_AUDIT,
            MonthlyAssessment.STATUS_PENDING_FINAL,
            MonthlyAssessment.STATUS_PENDING_TREASURER,
            MonthlyAssessment.STATUS_PENDING_DEPOSIT,
        ):
            funds["pending_approval"] += collected
    funds["finalized"] = round(funds["finalized"], 2)
    funds["pending_approval"] = round(funds["pending_approval"], 2)

    return JsonResponse({
        "ok": True,
        "funds": funds,
        "notify_allowed": notify_allowed,
        "breakdown": breakdown,
        "notice": "" if notify_allowed else "Members will appear here once the Treasurer records this month's deductions.",
        "assessments": [
            {
                "assessment_id": a.assessment_id_PK,
                "month": _month_date_value(a.month),
                "month_label": a.month_label,
                "status": a.status,
                "status_label": a.get_status_display(),
                "total_amount": float(a.total_amount),
                "recorded": int((per_assessment.get(a.assessment_id_PK) or {}).get("recorded") or 0),
                "collected": round(float((per_assessment.get(a.assessment_id_PK) or {}).get("collected") or 0), 2),
                "expected": round(float(a.total_amount) * int((per_assessment.get(a.assessment_id_PK) or {}).get("recorded") or 0), 2),
            }
            for a in assessments
        ],
        "assessment": {
            "assessment_id": assessment.assessment_id_PK,
            "month": _month_date_value(assessment.month),
            "month_label": assessment.month_label,
            "status": assessment.status,
            "status_label": assessment.get_status_display(),
            "total_amount": float(assessment.total_amount),
        },
        "departments": departments,
        "members": member_rows,
        "totals": {**totals, "rate": round(overall_rate, 1)},
    })


@require_POST
def notify_outstanding_members(request: HttpRequest):
    """Auditor sends outstanding-balance reminders to selected members.

    Body: {"assessment_id": int, "member_ids": [int],
           "notify_type": "reminder" | "urgent" | "custom",
           "custom_message": str}
    Members with no outstanding balance are skipped. Each notified member
    gets a branded email with their breakdown plus an in-app notification;
    the action is written to the workflow log and the audit trail.
    """
    guard = require_role(request, role="Auditor")
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)

    payload = _json_body(request)
    assessment = MonthlyAssessment.objects.filter(pk=payload.get("assessment_id")).first()
    if assessment is None:
        return JsonResponse({"ok": False, "error": "Assessment not found."}, status=404)

    member_ids = payload.get("member_ids")
    if not isinstance(member_ids, list) or not member_ids:
        return JsonResponse({"ok": False, "error": "Select at least one member."}, status=400)
    try:
        member_ids = {int(value) for value in member_ids}
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "member_ids must be member ids."}, status=400)

    if assessment.status in (
        MonthlyAssessment.STATUS_DRAFT,
        MonthlyAssessment.STATUS_PENDING_TREASURER,
    ):
        return JsonResponse({
            "ok": False,
            "error": "The Treasurer has not recorded this month's deductions yet — there is nothing to notify about.",
        }, status=409)

    notify_type = (payload.get("notify_type") or "reminder").strip().lower()
    if notify_type not in ("reminder", "urgent", "custom"):
        notify_type = "reminder"
    custom_message = (payload.get("custom_message") or "").strip()
    if notify_type == "custom" and not custom_message:
        return JsonResponse({"ok": False, "error": "Write the custom message first."}, status=400)

    items = list(assessment.items.all())
    recorded = {
        ma.member_id_FK_id: ma
        for ma in assessment.member_assessments.filter(
            member_id_FK_id__in=member_ids
        ).select_related("member_id_FK")
    }
    results = []
    subject_tone = "Urgent" if notify_type == "urgent" else "Action Required"

    # Members with no recorded deduction are still notified: they owe the
    # full standard assessment with every item unpaid.
    for member in Member.objects.filter(member_id_PK__in=member_ids).order_by("full_name"):
        ma = recorded.get(member.member_id_PK)
        classification = (getattr(member, "member_classification", "") or "Teaching")
        prior_outstanding = 0.0
        prior_collected = 0.0
        prior_month_label = ""
        if ma is not None:
            outstanding = float(ma.outstanding_balance)
            actual = float(ma.actual_deduction)
            standard = float(ma.standard_assessment)
            prior_outstanding = float(ma.prior_outstanding)
            prior_collected = float(ma.prior_outstanding_collected)
            prior_month_label = ma.prior_month or ""
            breakdown = [
                {
                    "purpose": alloc["purpose_label"],
                    "required": alloc["required"],
                    "applied": alloc["applied"],
                    "remaining": alloc["remaining"],
                }
                for alloc in (
                    _serialize_allocation(a, classification) for a in ma.allocations.all()
                )
            ]
        else:
            # No record for this month: the member owes their classification
            # share (Retired members owe nothing).
            required_total = _member_required_assessment(assessment, classification, items)
            outstanding = float(required_total)
            actual = 0.0
            standard = float(required_total)
            breakdown = [
                {
                    "purpose": item.label,
                    "required": float(_item_required_amount(item, classification)),
                    "applied": 0.0,
                    "remaining": float(_item_required_amount(item, classification)),
                }
                for item in items
            ]
        # The stored outstanding includes any carry-over from an earlier
        # month, but the allocation rows only cover this month's items.
        # Append the carry-over as its own row so the email totals
        # reconcile with the headline outstanding figure.
        if ma is not None and prior_outstanding > 0:
            breakdown.append({
                "purpose": f"Carried-over balance from {prior_month_label or 'a previous month'}",
                "required": prior_outstanding,
                "applied": prior_collected,
                "remaining": prior_outstanding - prior_collected,
            })
        if outstanding <= 0:
            continue  # nothing owed — nothing to remind about
        excess_to_fund = float(ma.change_amount) if ma is not None else 0.0
        context = {
            "member_name": member.full_name,
            "month_label": assessment.month_label,
            "standard_assessment": standard,
            "actual_deducted": actual,
            "outstanding_balance": outstanding,
            "prior_outstanding": prior_outstanding,
            "prior_collected": prior_collected,
            "prior_month_label": prior_month_label or "a previous month",
            "prior_remaining": prior_outstanding - prior_collected,
            "excess_to_fund": excess_to_fund,
            "breakdown": breakdown,
            "notify_type": notify_type,
            "custom_message": custom_message,
            "auditor_name": officer.full_name,
        }
        email_sent = False
        in_app_sent = False
        try:
            if member.email:
                email_sent = send_html_email_async(
                    subject=f"ISUCauFA, Inc. - {subject_tone}: Outstanding Balance for {assessment.month_label}",
                    recipient_list=[member.email],
                    html_template="emails/monthly_deduction_reminder.html",
                    context=context,
                    defer_worker=True,
                )
        except Exception:
            logger.exception("Reminder email queueing failed for member %s", member.member_id_PK)
        try:
            notify_member(
                member,
                notification_type="Outstanding Reminder",
                message=(
                    f"The Auditor reviewed your {assessment.month_label} deduction: "
                    f"outstanding balance ₱{outstanding:.2f}."
                    + " Please coordinate with the Treasurer to settle."
                ),
                category="finance",
                url="/member/",
                sender_name=officer.full_name,
                sender_role="Auditor",
                send_email=False,
            )
            in_app_sent = True
        except Exception:
            logger.exception("In-app notification failed for member %s", member.member_id_PK)
        results.append({
            "member_id": member.member_id_PK,
            "member_name": member.full_name,
            "outstanding": outstanding,
            "email_sent": email_sent,
            "in_app_sent": in_app_sent,
        })

    skipped = len(member_ids) - len(results)
    if results:
        try:
            AssessmentWorkflowLog.objects.create(
                assessment_id_FK=assessment,
                action="auditor_notify_members",
                performed_by_id_FK=officer,
                notes=(
                    f"Notified {len(results)} member(s) ({notify_type}) about outstanding "
                    f"balances totalling {sum(r['outstanding'] for r in results):.2f}."
                ),
            )
        except Exception:
            logger.exception("Workflow log failed for notify on assessment %s", assessment.assessment_id_PK)
        try:
            _record_audit_trail(
                table=ASSESSMENT_TABLE,
                record_id=assessment.assessment_id_PK,
                action="NOTIFY",
                actor=officer,
                new={"notify_type": notify_type, "members": sorted(member_ids & {r["member_id"] for r in results})},
                ip=request.META.get("REMOTE_ADDR"),
                device_info=request.META.get("HTTP_USER_AGENT", ""),
                notes=f"Auditor notified {len(results)} member(s) about {assessment.month_label} outstanding balances",
            )
        except Exception:
            logger.exception("Audit trail failed for notify on assessment %s", assessment.assessment_id_PK)

    if any(r.get("email_sent") for r in results):
        # Single sequential drain for the whole reminder batch (see
        # final-approval path above).
        flush_email_queue_async()

    return JsonResponse({
        "ok": True,
        "sent": len(results),
        "skipped": skipped,
        "results": results,
        "total_outstanding": sum(r["outstanding"] for r in results),
    })


# ---------------------------------------------------------------------------
# Overview dashboard helpers: per-member verify/return + notification history
# ---------------------------------------------------------------------------

@require_POST
def auditor_verify_selected_members(request: HttpRequest):
    """Auditor verifies or returns selected member records in one batch.

    Body: {"assessment_id": int, "member_ids": [int],
           "action": "verify" | "return", "notes": str}
    Verify marks the selected records verified; when every record of the
    month is verified the assessment moves to Pending President Approval.
    Return sends the selected records back to Pending status with remarks.
    """
    guard = require_role(request, role="Auditor")
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)

    payload = _json_body(request)
    assessment = MonthlyAssessment.objects.filter(pk=payload.get("assessment_id")).first()
    if assessment is None:
        return JsonResponse({"ok": False, "error": "Assessment not found."}, status=404)
    if assessment.status != MonthlyAssessment.STATUS_PENDING_AUDIT:
        return JsonResponse({
            "ok": False,
            "error": f"Only months pending audit can be actioned (current: {assessment.get_status_display()}).",
        }, status=409)

    member_ids = payload.get("member_ids")
    if not isinstance(member_ids, list) or not member_ids:
        return JsonResponse({"ok": False, "error": "Select at least one member."}, status=400)
    try:
        member_ids = {int(value) for value in member_ids}
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "member_ids must be member ids."}, status=400)

    action = (payload.get("action") or "").strip().lower()
    if action not in ("verify", "return"):
        return JsonResponse({"ok": False, "error": "Action must be 'verify' or 'return'."}, status=400)
    notes = (payload.get("notes") or "").strip()
    if action == "return" and not notes:
        return JsonResponse({"ok": False, "error": "A reason is required when returning records."}, status=400)

    records = list(
        assessment.member_assessments.filter(member_id_FK_id__in=member_ids)
    )
    if not records:
        return JsonResponse({"ok": False, "error": "No matching records found."}, status=404)

    now = timezone.now()
    if action == "verify":
        for ma in records:
            ma.status = MemberAssessment.STATUS_VERIFIED
            ma.verified_by_id_FK = officer
            ma.verified_at = now
        MemberAssessment.objects.bulk_update(records, ["status", "verified_by_id_FK", "verified_at"])
        remaining = assessment.member_assessments.filter(
            status=MemberAssessment.STATUS_PENDING
        ).count()
        if remaining == 0:
            assessment.status = MonthlyAssessment.STATUS_PENDING_FINAL
            assessment.auditor_remarks = notes or None
    else:
        for ma in records:
            ma.status = MemberAssessment.STATUS_PENDING
        MemberAssessment.objects.bulk_update(records, ["status"])
        assessment.status = MonthlyAssessment.STATUS_PENDING_AUDIT
        assessment.auditor_remarks = notes
    assessment.save()

    log_action = "auditor_verify_members" if action == "verify" else "auditor_return_members"
    AssessmentWorkflowLog.objects.create(
        assessment_id_FK=assessment,
        action=log_action,
        performed_by_id_FK=officer,
        notes=(
            f"{action.capitalize()}ed {len(records)} member record(s)."
            + (f" {notes}" if notes else "")
        ),
    )
    _record_audit_trail(
        table=ASSESSMENT_TABLE,
        record_id=assessment.assessment_id_PK,
        action="VERIFY" if action == "verify" else "RETURN",
        actor=officer,
        new={"action": action, "members": sorted(member_ids & {ma.member_id_FK_id for ma in records})},
        ip=request.META.get("REMOTE_ADDR"),
        device_info=request.META.get("HTTP_USER_AGENT", ""),
        notes=f"Auditor {action}ed {len(records)} member record(s) for {assessment.month_label}",
    )
    _broadcast_deduction_counts()

    return JsonResponse({
        "ok": True,
        "updated": len(records),
        "assessment_status": assessment.status,
    })


@require_GET
def deduction_notification_history(request: HttpRequest):
    """Notification history for one assessment (from the workflow log)."""
    guard = require_role(request, role=["Auditor", "President", "Treasurer"])
    if guard is not None:
        return guard

    assessments = list(MonthlyAssessment.objects.order_by("-month"))
    if not assessments:
        return JsonResponse({"ok": True, "assessment": None, "notifications": [], "total": 0})

    raw_id = (request.GET.get("assessment_id") or "").strip()
    assessment = None
    if raw_id.isdigit():
        assessment = next(
            (a for a in assessments if a.assessment_id_PK == int(raw_id)), None
        )
    if assessment is None:
        assessment = assessments[0]

    logs = AssessmentWorkflowLog.objects.filter(
        assessment_id_FK=assessment, action="auditor_notify_members"
    ).order_by("-created_at")[:20]

    notifications = []
    for log in logs:
        match = re.search(r"Notified (\d+) member\(s\) \((\w+)\)", log.notes or "")
        notifications.append({
            "id": log.pk,
            "date": log.created_at.isoformat() if log.created_at else "",
            "members": int(match.group(1)) if match else 0,
            "type": match.group(2) if match else "reminder",
            "status": "Sent",
            "notes": log.notes or "",
            "by": log.performed_by_id_FK.full_name if log.performed_by_id_FK else "",
        })

    return JsonResponse({
        "ok": True,
        "assessment": {
            "assessment_id": assessment.assessment_id_PK,
            "month_label": assessment.month_label,
        },
        "notifications": notifications,
        "total": sum(n["members"] for n in notifications),
    })


# ---------------------------------------------------------------------------
# Member ledger history: per-month deducted / credit / remaining balance,
# with the member's full profile, for any officer to consult.
# ---------------------------------------------------------------------------

def _serialize_member_profile(member: Member) -> dict:
    return {
        "member_id": member.member_id_PK,
        "full_name": member.full_name,
        "employee_id": member.employee_id or "",
        "department": member.department or "",
        "position": member.position or "",
        "email": member.email or "",
        "contact_number": member.contact_number or "",
        "employment_status": member.employment_status or "",
        "membership_status": member.membership_status or "",
        "member_type": member.member_type or "",
        "date_joined": member.date_joined.isoformat() if member.date_joined else "",
        "emergency_contact": member.emergency_contact or "",
        "emergency_number": member.emergency_number or "",
    }


@require_GET
def officer_member_ledger_history(request: HttpRequest):
    """Month-by-month deduction ledger for one member (all officers).

    Without ?member_id= returns the member picker list. With it, returns the
    member's full profile plus one row per recorded month: what was deducted
    from them, their credit ("change"), and their remaining balance.
    """
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    raw_id = (request.GET.get("member_id") or "").strip()
    if not raw_id:
        # History view: every member is listed, including Retired ones —
        # retirement stops future deductions but never hides past records.
        members = Member.objects.all().order_by("full_name")
        return JsonResponse({
            "ok": True,
            "members": [
                {
                    "member_id": m.member_id_PK,
                    "member_name": _formatted_name(m.full_name),
                    "employee_id": m.employee_id or "",
                    "department": m.department or "",
                    "membership_status": m.membership_status or "",
                }
                for m in members
            ],
        })

    if not raw_id.isdigit():
        return JsonResponse({"ok": False, "error": "member_id must be a number."}, status=400)
    member = Member.objects.filter(member_id_PK=int(raw_id)).first()
    if member is None:
        return JsonResponse({"ok": False, "error": "Member not found."}, status=404)

    records = approved_member_assessments(member).prefetch_related(
        "allocations__assessment_item_id_FK",
        "assessment_id_FK__items",
    )

    months = []
    total_deducted = Decimal("0.00")
    total_credit = Decimal("0.00")
    latest = None
    for ma in records:
        assessment = ma.assessment_id_FK
        total_deducted += ma.actual_deduction
        total_credit += ma.change_amount
        latest = ma
        months.append({
            "assessment_id": assessment.assessment_id_PK,
            "month": _month_date_value(assessment.month),
            "month_label": assessment.month_label,
            "assessment_status": assessment.status,
            "assessment_status_label": assessment.get_status_display(),
            "standard": float(ma.standard_assessment),
            "deducted": float(ma.actual_deduction),
            "prior_outstanding": float(ma.prior_outstanding),
            "prior_collected": float(ma.prior_outstanding_collected),
            "prior_months": _clean_month_entries(ma.prior_months),
            "prior_collected_months": _clean_month_entries(ma.prior_collected_months),
            "credit": float(ma.change_amount),
            "remaining_balance": float(ma.outstanding_balance),
            "status": ma.status,
            "status_label": ma.get_status_display(),
            "recorded_at": ma.recorded_at.isoformat() if ma.recorded_at else "",
            "verified_at": ma.verified_at.isoformat() if ma.verified_at else "",
            "approved_at": ma.approved_at.isoformat() if ma.approved_at else "",
            # Canonical per-item due vs aid split (purpose, recipient,
            # required / applied / remaining) for the expandable breakdown.
            "breakdown": build_member_assessment_breakdown(ma),
        })

    return JsonResponse({
        "ok": True,
        "member": _serialize_member_profile(member),
        # One-time membership fee, shown as its own Monthly Payment Log row.
        "membership_fee": membership_fee_summary(member),
        "months": months,
        "totals": {
            "months_recorded": len(months),
            "total_deducted": float(total_deducted),
            "credit": float(total_credit),
            # Only final-approved months are visible in Member Ledger History.
            "remaining_balance": member_lifetime_owed(member),
            "credit_note": float(latest.change_amount) if latest else 0.0,
        },
    })


@require_GET
def officer_deduction_sheet_pdf(request: HttpRequest, assessment_id: int):
    """Download the transmittal letter + deducted amount sheet (Annex A) as PDF."""
    from core_system.services.deduction_sheet_pdf import build_deduction_sheet_pdf

    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    assessment = MonthlyAssessment.objects.filter(pk=assessment_id).first()
    if assessment is None:
        return JsonResponse({"ok": False, "error": "Assessment not found."}, status=404)

    try:
        pdf_bytes = build_deduction_sheet_pdf(assessment)
    except Exception:
        logger.exception("Deduction sheet PDF failed for assessment %s", assessment_id)
        return JsonResponse({"ok": False, "error": "Could not generate the deduction sheet."}, status=500)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="ISUCauFA_Deduction_Letter_{assessment.month.strftime("%Y-%m")}.pdf"'
    )
    return response
