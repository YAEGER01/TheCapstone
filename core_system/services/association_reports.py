"""Association-wide reports for the faculty association (16 builders).

Each builder takes a Django ``request`` (GET params as filters) and returns a
normalized ``report`` dict following the same schema as
``services/oversight_reports.py`` so the existing ``report_to_xlsx`` /
``report_to_pdf`` exporters and the generic frontend preview can render every
report uniformly::

    {
        "report_key": str, "report_name": str, "description": str,
        "generated_by": str, "generated_at": str,
        "filters": [{"label", "value"}],
        "summary": [{"label", "value", "type": count|currency|percent|string}],
        "columns": [{"key", "label", "align"}],
        "rows": [{key: value}],
        "sections": [...],  # optional
        "notes": [...],     # optional, documents methodology
    }

Money values are plain rounded floats (the exporters add the peso sign).
"""

from __future__ import annotations

from datetime import date, datetime

from django.db.models import Q, Sum
from django.utils import timezone

from core_system.constants.status_constants import Status
from core_system.models import (
    AidTrackingPost,
    AssessmentItem,
    BudgetLine,
    Contribution,
    DeathAid,
    FundTransaction,
    GlobalAuditTrail,
    MedicalAid,
    Member,
    MemberAssessment,
    MemberCatchupDue,
    MembershipFee,
    MonthlyAssessment,
    PayrollBatch,
    PayrollDeduction,
)

MAX_ROWS = 2000

RELEASED_CLAIM_STATUSES = {"Released", "Completed", "Complete"}
PENDING_CLAIM_STATUSES = set(Status.ALL_PENDING)
APPROVED_CLAIM_STATUSES = set(Status.ALL_APPROVED) | set(Status.ALL_AUDITOR_VERIFIED)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_str() -> str:
    return timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S")


def _get(request, key, default=""):
    return (request.GET.get(key) or "").strip() or default


def _report_base(report_key, report_name, description, request, filters):
    session = getattr(request, "session", None)
    generated_by = (
        getattr(request, "officer_name", None)
        or (session.get("officer_name") if session else None)
        or "Officer"
    )
    return {
        "report_key": report_key,
        "report_name": report_name,
        "description": description,
        "generated_by": generated_by,
        "generated_at": _now_str(),
        "filters": filters,
    }


def _col(key, label, align="left"):
    return {"key": key, "label": label, "align": align}


def _f(value) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _parse_date(value):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _month_start(value):
    """'YYYY-MM' -> date(YYYY, M, 1) or None."""
    try:
        year_s, month_s = (value or "").strip().split("-")[:2]
        return date(int(year_s), int(month_s), 1)
    except (ValueError, TypeError):
        return None


def _month_label(month_start) -> str:
    try:
        return month_start.strftime("%B %Y")
    except (ValueError, TypeError, AttributeError):
        return str(month_start or "N/A")


def _member_name(member) -> str:
    if member is None:
        return "N/A"
    return getattr(member, "full_name", None) or "N/A"


def _active_members():
    return Member.objects.exclude(membership_status__iexact="retired")


def _apply_department(qs, department, member_related="member_id_FK"):
    if department:
        return qs.filter(**{f"{member_related}__department__iexact": department})
    return qs


def _claim_released(claim) -> bool:
    if getattr(claim, "released_by_id_FK_id", None):
        return True
    if (getattr(claim, "release_reference", None) or "").strip():
        return True
    return (getattr(claim, "status", "") or "") in RELEASED_CLAIM_STATUSES


# ---------------------------------------------------------------------------
# Collections (1-5)
# ---------------------------------------------------------------------------


def build_delinquency(request):
    """Members with unpaid balances at or above a threshold, for follow-up."""
    try:
        min_amount = float(_get(request, "min_amount") or 0)
    except (TypeError, ValueError):
        min_amount = 0.0
    department = _get(request, "department")

    assessed = _apply_department(
        MemberAssessment.objects.filter(outstanding_balance__gt=0), department
    ).values("member_id_FK").annotate(total=Sum("outstanding_balance"))

    totals: dict[int, float] = {}
    for entry in assessed:
        totals[entry["member_id_FK"]] = _f(entry["total"])
    catchups = MemberCatchupDue.objects.filter(amount__gt=0)
    if department:
        catchups = catchups.filter(member_id_FK__department__iexact=department)
    for due in catchups.values("member_id_FK").annotate(total=Sum("amount")):
        totals[due["member_id_FK"]] = round(totals.get(due["member_id_FK"], 0.0) + _f(due["total"]), 2)

    member_ids = [mid for mid, total in totals.items() if total >= min_amount]
    members = Member.objects.filter(member_id_PK__in=member_ids).order_by("full_name")
    if department:
        members = members.filter(department__iexact=department)

    oldest_by_member: dict[int, str] = {}
    for row in (
        MemberAssessment.objects.filter(member_id_FK_id__in=member_ids, outstanding_balance__gt=0)
        .select_related("assessment_id_FK")
        .order_by("assessment_id_FK__month")
        .values("member_id_FK_id", "assessment_id_FK__month")
    ):
        oldest_by_member.setdefault(row["member_id_FK_id"], _month_label(row["assessment_id_FK__month"]))
    for row in (
        MemberCatchupDue.objects.filter(member_id_FK_id__in=member_ids, amount__gt=0)
        .order_by("month")
        .values("member_id_FK_id", "month")
    ):
        current = oldest_by_member.get(row["member_id_FK_id"])
        label = _month_label(row["month"])
        if current is None or label < current:
            oldest_by_member[row["member_id_FK_id"]] = label

    rows = []
    for member in members[:MAX_ROWS]:
        rows.append({
            "member": member.full_name,
            "employee_id": member.employee_id or "N/A",
            "department": member.department or "Unassigned",
            "contact": member.contact_number or "N/A",
            "email": member.email or "N/A",
            "total_due": totals.get(member.member_id_PK, 0.0),
            "oldest_month": oldest_by_member.get(member.member_id_PK, "N/A"),
            "status": member.membership_status or "Unknown",
        })
    rows.sort(key=lambda r: r["total_due"], reverse=True)

    report = _report_base(
        "delinquency", "Delinquency / Defaulters Report",
        "Members with unpaid balances at or above the threshold, with contact info for follow-up.",
        request,
        [
            {"label": "Minimum amount", "value": f"PHP {min_amount:,.2f}"},
            {"label": "Department", "value": department or "All"},
        ],
    )
    report["summary"] = [
        {"label": "Delinquent members", "value": len(rows), "type": "count"},
        {"label": "Total collectible", "value": round(sum(r["total_due"] for r in rows), 2), "type": "currency"},
    ]
    report["columns"] = [
        _col("member", "Member"),
        _col("employee_id", "Employee ID"),
        _col("department", "Department"),
        _col("contact", "Contact"),
        _col("email", "Email"),
        _col("total_due", "Total Due (PHP)", "right"),
        _col("oldest_month", "Oldest Unpaid Month"),
        _col("status", "Status"),
    ]
    report["rows"] = rows
    return report


def build_collection_efficiency(request):
    """Expected vs collected per assessment month, with collection rate."""
    try:
        months = max(1, min(36, int(_get(request, "months") or 12)))
    except (TypeError, ValueError):
        months = 12
    department = _get(request, "department")
    date_from = _parse_date(_get(request, "date_from"))
    date_to = _parse_date(_get(request, "date_to"))

    assessments = MonthlyAssessment.objects.exclude(status="draft")
    if date_from or date_to:
        # Selected-period basis: the assessment months inside the Reporting
        # Period, not just the latest N — a February filter shows February.
        if date_from:
            assessments = assessments.filter(month__gte=date(date_from.year, date_from.month, 1))
        if date_to:
            assessments = assessments.filter(month__lte=date(date_to.year, date_to.month, 1))
    assessments = sorted(assessments.order_by("-month")[:months], key=lambda a: a.month)

    rows = []
    total_expected = total_collected = 0.0
    for assessment in assessments:
        members = MemberAssessment.objects.filter(assessment_id_FK=assessment)
        if department:
            members = members.filter(member_id_FK__department__iexact=department)
        agg = members.aggregate(expected=Sum("standard_assessment"), collected=Sum("actual_deduction"))
        expected = _f(agg["expected"])
        collected = _f(agg["collected"])
        rate = round((collected / expected * 100) if expected else 0.0, 1)
        total_expected += expected
        total_collected += collected
        rows.append({
            "month": assessment.month_label,
            "status": assessment.get_status_display() if hasattr(assessment, "get_status_display") else assessment.status,
            "expected": expected,
            "collected": collected,
            "uncollected": round(expected - collected, 2),
            "rate": f"{rate}%",
        })
    overall = round((total_collected / total_expected * 100) if total_expected else 0.0, 1)

    report = _report_base(
        "collection_efficiency", "Collection Efficiency Report",
        "Expected vs actually collected dues per assessment month with collection rate.",
        request,
        [
            {"label": "Months covered", "value": str(months)},
            {"label": "Department", "value": department or "All"},
            {"label": "From", "value": str(date_from or "Start")},
            {"label": "To", "value": str(date_to or "Today")},
        ],
    )
    report["summary"] = [
        {"label": "Total expected", "value": round(total_expected, 2), "type": "currency"},
        {"label": "Total collected", "value": round(total_collected, 2), "type": "currency"},
        {"label": "Overall rate", "value": f"{overall}%", "type": "percent"},
    ]
    report["columns"] = [
        _col("month", "Month"),
        _col("status", "Status"),
        _col("expected", "Expected (PHP)", "right"),
        _col("collected", "Collected (PHP)", "right"),
        _col("uncollected", "Uncollected (PHP)", "right"),
        _col("rate", "Rate", "right"),
    ]
    report["rows"] = rows
    return report


def build_member_soa(request):
    """Formal statement of account for one member."""
    member_id = _get(request, "member_id")
    try:
        member = Member.objects.get(member_id_PK=int(member_id))
    except (Member.DoesNotExist, TypeError, ValueError):
        report = _report_base(
            "member_soa", "Member Statement of Account",
            "Dues billed, paid, aid received, and balance for one member.",
            request, [{"label": "Member", "value": "Not selected"}],
        )
        report["summary"] = []
        report["columns"] = [_col("item", "Item")]
        report["rows"] = [{"item": "Select a member to generate the statement."}]
        report["notes"] = ["Pass ?member_id=<id>."]
        return report

    dues_rows = list(
        MemberAssessment.objects.filter(member_id_FK=member)
        .select_related("assessment_id_FK")
        .order_by("assessment_id_FK__month")
    )
    dues_section = [
        {
            "month": r.assessment_id_FK.month_label,
            "billed": _f(r.standard_assessment),
            "paid": _f(r.actual_deduction),
            "balance": _f(r.outstanding_balance),
            "status": r.status,
        }
        for r in dues_rows
    ]
    catchup_rows = list(MemberCatchupDue.objects.filter(member_id_FK=member).order_by("month"))
    catchup_section = [
        {"month": _month_label(d.month), "amount": _f(d.amount)} for d in catchup_rows
    ]

    medical = list(MedicalAid.objects.filter(member_id_FK=member).order_by("request_date"))
    death = list(DeathAid.objects.filter(member_id_FK=member).order_by("claim_date"))
    aid_section = [
        {
            "type": "Medical Aid",
            "date": str(a.request_date),
            "amount": _f(a.validated_aid_amount or a.requested_amount or a.hospital_bill_amount),
            "status": a.status,
        }
        for a in medical
    ] + [
        {
            "type": "Death Aid",
            "date": str(a.claim_date),
            "amount": _f(a.benefit_amount),
            "status": a.status,
        }
        for a in death
    ]

    billed = round(sum(r["billed"] for r in dues_section) + sum(r["amount"] for r in catchup_section), 2)
    paid = round(sum(r["paid"] for r in dues_section), 2)

    report = _report_base(
        "member_soa", f"Statement of Account — {member.full_name}",
        "Formal per-member statement: dues billed and paid, back dues, and aid claims.",
        request,
        [
            {"label": "Member", "value": member.full_name},
            {"label": "Employee ID", "value": member.employee_id or "N/A"},
            {"label": "Department", "value": member.department or "Unassigned"},
            {"label": "Status", "value": f"{member.membership_status or 'Unknown'} / {member.member_classification or 'Teaching'}"},
        ],
    )
    report["summary"] = [
        {"label": "Total billed", "value": billed, "type": "currency"},
        {"label": "Total paid", "value": paid, "type": "currency"},
        {"label": "Balance due", "value": round(billed - paid, 2), "type": "currency"},
    ]
    report["columns"] = [
        _col("month", "Month"),
        _col("billed", "Billed (PHP)", "right"),
        _col("paid", "Paid (PHP)", "right"),
        _col("balance", "Balance (PHP)", "right"),
        _col("status", "Status"),
    ]
    report["rows"] = dues_section
    report["sections"] = [
        {
            "title": "Back Dues",
            "columns": [_col("month", "Month"), _col("amount", "Amount (PHP)", "right")],
            "rows": catchup_section,
        },
        {
            "title": "Aid Claims",
            "columns": [
                _col("type", "Type"), _col("date", "Date"),
                _col("amount", "Amount (PHP)", "right"), _col("status", "Status"),
            ],
            "rows": aid_section,
        },
    ]
    return report


# ---------------------------------------------------------------------------
# Aid funds (6-7)
# ---------------------------------------------------------------------------

def _aid_collected(aid_type, date_from=None, date_to=None) -> float:
    from core_system.models import AidSetAside

    qs = AidSetAside.objects.filter(aid_type=aid_type)
    if date_from or date_to:
        # Covered-month basis: a set-aside is part of a member's deduction
        # for one assessment month, whenever it was booked — a February
        # earmark recorded in October still belongs to February.
        if date_from:
            qs = qs.filter(
                member_assessment_id_FK__assessment_id_FK__month__gte=date(
                    date_from.year, date_from.month, 1
                )
            )
        if date_to:
            qs = qs.filter(
                member_assessment_id_FK__assessment_id_FK__month__lte=date(
                    date_to.year, date_to.month, 1
                )
            )
    return _f(qs.aggregate(total=Sum("amount"))["total"])


def _aid_released_amount(claim):
    for field in ("validated_aid_amount", "benefit_amount", "requested_amount", "hospital_bill_amount"):
        value = getattr(claim, field, None)
        if value:
            return _f(value)
    return 0.0


def build_aid_fund_utilization(request):
    """Collected vs disbursed vs remaining per aid fund."""
    aid_type = _get(request, "aid_type", "all").lower()
    date_from = _parse_date(_get(request, "date_from"))
    date_to = _parse_date(_get(request, "date_to"))

    kinds = []
    if aid_type in ("medical", "medical_aid"):
        kinds = [("medical_aid", "Medical Aid")]
    elif aid_type in ("death", "death_aid"):
        kinds = [("death_aid", "Death Aid")]
    else:
        kinds = [("medical_aid", "Medical Aid"), ("death_aid", "Death Aid")]

    rows = []
    total_collected = total_released = 0.0
    for key, label in kinds:
        collected = _aid_collected(key, date_from, date_to)
        claims = MedicalAid.objects.all() if key == "medical_aid" else DeathAid.objects.all()
        if date_from:
            field = "request_date" if key == "medical_aid" else "claim_date"
            claims = claims.filter(**{f"{field}__gte": date_from})
        if date_to:
            field = "request_date" if key == "medical_aid" else "claim_date"
            claims = claims.filter(**{f"{field}__lte": date_to})
        released = pending = 0.0
        released_n = pending_n = 0
        for claim in claims:
            amount = _aid_released_amount(claim)
            if _claim_released(claim):
                released += amount
                released_n += 1
            elif (claim.status or "") in PENDING_CLAIM_STATUSES:
                pending += amount
                pending_n += 1
        released = round(released, 2)
        pending = round(pending, 2)
        total_collected += collected
        total_released += released
        rows.append({
            "fund": label,
            "collected": collected,
            "released": released,
            "released_count": released_n,
            "pending_amount": pending,
            "pending_count": pending_n,
            "remaining": round(collected - released, 2),
        })

    report = _report_base(
        "aid_fund_utilization", "Aid Fund Utilization Report",
        "Per aid fund: collected (set-asides) vs released claims vs remaining.",
        request,
        [
            {"label": "Aid type", "value": aid_type},
            {"label": "From", "value": str(date_from or "Start")},
            {"label": "To", "value": str(date_to or "Today")},
        ],
    )
    report["summary"] = [
        {"label": "Total collected", "value": round(total_collected, 2), "type": "currency"},
        {"label": "Total released", "value": round(total_released, 2), "type": "currency"},
        {"label": "Total remaining", "value": round(total_collected - total_released, 2), "type": "currency"},
    ]
    report["columns"] = [
        _col("fund", "Fund"),
        _col("collected", "Collected (PHP)", "right"),
        _col("released", "Released (PHP)", "right"),
        _col("released_count", "Released Claims", "right"),
        _col("pending_amount", "Pending (PHP)", "right"),
        _col("pending_count", "Pending Claims", "right"),
        _col("remaining", "Remaining (PHP)", "right"),
    ]
    report["rows"] = rows
    report["notes"] = [
        "Released = claim has a release reference, released-by officer, or Released/Completed status.",
        "Collected counts set-asides by the assessment month they were deducted for (covered month), not the booking date.",
    ]
    return report


def build_claims_register(request):
    """Every aid claim with member, dates, amounts, and status."""
    aid_type = _get(request, "aid_type", "all").lower()
    status = _get(request, "status")
    date_from = _parse_date(_get(request, "date_from"))
    date_to = _parse_date(_get(request, "date_to"))
    department = _get(request, "department")

    rows = []

    def _collect(qs, kind, date_field, amount_fn, extra_fn):
        for claim in qs.select_related("member_id_FK")[:MAX_ROWS]:
            member = claim.member_id_FK
            if department and (not member or (member.department or "").lower() != department.lower()):
                continue
            claim_date = getattr(claim, date_field)
            if date_from and claim_date and claim_date < date_from:
                continue
            if date_to and claim_date and claim_date > date_to:
                continue
            if status and (claim.status or "") != status:
                continue
            rows.append({
                "type": kind,
                "member": _member_name(member),
                "department": (member.department if member else None) or "Unassigned",
                "claim_date": str(claim_date or "N/A"),
                "amount": amount_fn(claim),
                "status": claim.status or "Unknown",
                "detail": extra_fn(claim),
            })

    if aid_type in ("all", "medical", "medical_aid"):
        _collect(
            MedicalAid.objects.all().order_by("-request_date"),
            "Medical Aid", "request_date",
            lambda c: _f(c.validated_aid_amount or c.requested_amount or c.hospital_bill_amount),
            lambda c: (c.hospital_name or "N/A"),
        )
    if aid_type in ("all", "death", "death_aid"):
        _collect(
            DeathAid.objects.all().order_by("-claim_date"),
            "Death Aid", "claim_date",
            lambda c: _f(c.benefit_amount),
            lambda c: f"{c.deceased_name or 'N/A'} ({c.relationship_to_member or 'N/A'})",
        )

    rows.sort(key=lambda r: r["claim_date"], reverse=True)
    rows = rows[:MAX_ROWS]

    report = _report_base(
        "claims_register", "Aid Claims Register",
        "Every medical and death aid claim with member, dates, amounts, and status.",
        request,
        [
            {"label": "Aid type", "value": aid_type},
            {"label": "Status", "value": status or "All"},
            {"label": "From", "value": str(date_from or "Start")},
            {"label": "To", "value": str(date_to or "Today")},
            {"label": "Department", "value": department or "All"},
        ],
    )
    report["summary"] = [
        {"label": "Claims", "value": len(rows), "type": "count"},
        {"label": "Total amount", "value": round(sum(r["amount"] for r in rows), 2), "type": "currency"},
    ]
    report["columns"] = [
        _col("type", "Type"),
        _col("member", "Member"),
        _col("department", "Department"),
        _col("claim_date", "Claim Date"),
        _col("amount", "Amount (PHP)", "right"),
        _col("status", "Status"),
        _col("detail", "Detail"),
    ]
    report["rows"] = rows
    return report


# ---------------------------------------------------------------------------
# Money in/out (8-11)
# ---------------------------------------------------------------------------


BUDGET_ACTUAL_SOURCES = {
    "monthly_dues": ("inflow", ["monthly_dues"]),
    "membership_fee": ("inflow", ["membership_fee"]),
    "contributions": ("inflow", ["contribution"]),
    "aid_medical": ("outflow", ["medical_aid", "aid_setaside_medical"]),
    "aid_death": ("outflow", ["death_aid", "aid_setaside_death"]),
    "operations": ("outflow", ["manual_adjustment", "other_transaction", "salary_deduction_remittance", "payroll_batch", "aid_post_payment"]),
}


def _booking_year_sum(source_types, year, direction="inflow") -> float:
    """Sum booking transactions attributed to their COVERED year.

    Every dues/set-aside booking row carries ``source_id = MemberAssessment
    PK``, so a December assessment booked in January still counts for the
    prior year. Rows whose source_id is not a member assessment (legacy
    bookings) stay on their recorded year so nothing silently vanishes.
    """
    from core_system.models import MemberAssessment

    base = FundTransaction.objects.filter(direction=direction, source_type__in=source_types)
    year_ma_ids = list(
        MemberAssessment.objects.filter(
            assessment_id_FK__month__year=year
        ).values_list("member_assessment_id_PK", flat=True)
    )
    covered = _f(base.filter(source_id__in=year_ma_ids).aggregate(total=Sum("amount"))["total"])
    all_ma_ids = list(MemberAssessment.objects.values_list("member_assessment_id_PK", flat=True))
    legacy = _f(
        base.exclude(source_id__in=all_ma_ids)
        .filter(recorded_at__year=year)
        .aggregate(total=Sum("amount"))["total"]
    )
    return round(covered + legacy, 2)


def build_budget_vs_actual(request):
    """Budget lines vs actual fund flows per category for a fiscal year."""
    try:
        year = int(_get(request, "year") or timezone.localdate().year)
    except (TypeError, ValueError):
        year = timezone.localdate().year

    budgeted = {
        line.category: _f(line.amount)
        for line in BudgetLine.objects.filter(fiscal_year=year)
    }

    rows = []
    total_budgeted = total_actual = 0.0
    for category, _label in BudgetLine.CATEGORY_CHOICES:
        direction, sources = BUDGET_ACTUAL_SOURCES.get(category, ("inflow", []))
        if category == "monthly_dues":
            # Covered-year basis (see _booking_year_sum).
            actual = _booking_year_sum(sources, year, direction)
        else:
            actual = _f(
                FundTransaction.objects.filter(
                    direction=direction, source_type__in=sources, recorded_at__year=year
                ).aggregate(total=Sum("amount"))["total"]
            )
        planned = budgeted.get(category, 0.0)
        total_budgeted += planned
        total_actual += actual
        variance = round(actual - planned, 2)
        attainment = round((actual / planned * 100) if planned else 0.0, 1)
        rows.append({
            "category": dict(BudgetLine.CATEGORY_CHOICES)[category],
            "budgeted": planned,
            "actual": actual,
            "variance": variance,
            "attainment": f"{attainment}%",
        })

    report = _report_base(
        "budget_vs_actual", f"Budget vs Actual {year}",
        "Budget lines against actual fund flows per category for the fiscal year.",
        request,
        [{"label": "Fiscal year", "value": str(year)}],
    )
    report["summary"] = [
        {"label": "Total budgeted", "value": round(total_budgeted, 2), "type": "currency"},
        {"label": "Total actual", "value": round(total_actual, 2), "type": "currency"},
        {"label": "Variance", "value": round(total_actual - total_budgeted, 2), "type": "currency"},
    ]
    report["columns"] = [
        _col("category", "Category"),
        _col("budgeted", "Budgeted (PHP)", "right"),
        _col("actual", "Actual (PHP)", "right"),
        _col("variance", "Variance (PHP)", "right"),
        _col("attainment", "Attainment", "right"),
    ]
    report["rows"] = rows
    if not budgeted:
        report["notes"] = ["No budget lines set for this year — post them via the budget save endpoint first."]
    report["notes"] = (report.get("notes") or []) + [
        "Actuals map fund transactions to budget categories (see report documentation).",
        "Monthly-dues actuals count bookings by the assessment month they were deducted for (covered year), not the booking year.",
    ]
    return report


def build_membership_registry(request):
    """Official membership masterlist with profile filters."""
    status = _get(request, "membership_status")
    classification = _get(request, "classification")
    department = _get(request, "department")
    date_from = _parse_date(_get(request, "date_from"))
    date_to = _parse_date(_get(request, "date_to"))

    members = Member.objects.all().order_by("full_name")
    if status:
        members = members.filter(membership_status__iexact=status)
    if classification:
        members = members.filter(member_classification__iexact=classification)
    if department:
        members = members.filter(department__iexact=department)
    if date_from:
        members = members.filter(date_joined__gte=date_from)
    if date_to:
        members = members.filter(date_joined__lte=date_to)

    rows = []
    for member in members[:MAX_ROWS]:
        rows.append({
            "member": member.full_name,
            "employee_id": member.employee_id or "N/A",
            "department": member.department or "Unassigned",
            "position": member.position or "N/A",
            "classification": member.member_classification or "N/A",
            "status": member.membership_status or "Unknown",
            "email": member.email or "N/A",
            "date_joined": str(member.date_joined or "N/A"),
        })

    report = _report_base(
        "membership_registry", "Membership Registry",
        "Official membership masterlist with profile filters.",
        request,
        [
            {"label": "Status", "value": status or "All"},
            {"label": "Classification", "value": classification or "All"},
            {"label": "Department", "value": department or "All"},
            {"label": "Joined from", "value": str(date_from or "Start")},
            {"label": "Joined to", "value": str(date_to or "Today")},
        ],
    )
    report["summary"] = [
        {"label": "Members listed", "value": len(rows), "type": "count"},
    ]
    report["columns"] = [
        _col("member", "Member"),
        _col("employee_id", "Employee ID"),
        _col("department", "Department"),
        _col("position", "Position"),
        _col("classification", "Classification"),
        _col("status", "Status"),
        _col("email", "Email"),
        _col("date_joined", "Date Joined"),
    ]
    report["rows"] = rows
    return report


def build_audit_trail_export(request):
    """Filterable system activity log export."""
    date_from = _parse_date(_get(request, "date_from"))
    date_to = _parse_date(_get(request, "date_to"))
    table_name = _get(request, "table_name")
    action = _get(request, "action")
    try:
        limit = max(1, min(2000, int(_get(request, "limit") or 500)))
    except (TypeError, ValueError):
        limit = 500

    qs = GlobalAuditTrail.objects.all().order_by("-timestamp")
    if date_from:
        qs = qs.filter(timestamp__date__gte=date_from)
    if date_to:
        qs = qs.filter(timestamp__date__lte=date_to)
    if table_name:
        qs = qs.filter(table_name__iexact=table_name)
    if action:
        qs = qs.filter(action__icontains=action)

    rows = []
    for trail in qs[:limit]:
        rows.append({
            "timestamp": trail.timestamp.strftime("%Y-%m-%d %H:%M:%S") if trail.timestamp else "N/A",
            "actor": trail.actor_name or "System",
            "action": trail.action,
            "table": trail.table_name,
            "record_id": trail.record_id,
            "result": trail.result or "N/A",
            "notes": (trail.notes or "")[:200],
        })

    report = _report_base(
        "audit_trail_export", "Audit Trail Export",
        "Who did what, when: filterable system activity log.",
        request,
        [
            {"label": "From", "value": str(date_from or "Start")},
            {"label": "To", "value": str(date_to or "Today")},
            {"label": "Table", "value": table_name or "All"},
            {"label": "Action contains", "value": action or "All"},
            {"label": "Limit", "value": str(limit)},
        ],
    )
    report["summary"] = [
        {"label": "Entries", "value": len(rows), "type": "count"},
    ]
    report["columns"] = [
        _col("timestamp", "Timestamp"),
        _col("actor", "Actor"),
        _col("action", "Action"),
        _col("table", "Table"),
        _col("record_id", "Record ID", "right"),
        _col("result", "Result"),
        _col("notes", "Notes"),
    ]
    report["rows"] = rows
    return report


# ---------------------------------------------------------------------------
# Registry + UI metadata
# ---------------------------------------------------------------------------

GA_BUILDERS = {
    "delinquency": build_delinquency,
    "collection_efficiency": build_collection_efficiency,
    "member_soa": build_member_soa,
    "aid_fund_utilization": build_aid_fund_utilization,
    "claims_register": build_claims_register,
    "budget_vs_actual": build_budget_vs_actual,
    "membership_registry": build_membership_registry,
    "audit_trail_export": build_audit_trail_export,
}

GA_TITLES = {
    "delinquency": "Delinquency / Defaulters Report",
    "collection_efficiency": "Collection Efficiency Report",
    "member_soa": "Member Statement of Account",
    "aid_fund_utilization": "Aid Fund Utilization Report",
    "claims_register": "Aid Claims Register",
    "budget_vs_actual": "Budget vs Actual",
    "membership_registry": "Membership Registry",
    "audit_trail_export": "Audit Trail Export",
}

# Filter input names each report accepts (drives the generic viewer UI).
GA_FILTERS = {
    "delinquency": ["min_amount", "department"],
    "collection_efficiency": ["months", "department"],
    "member_soa": ["member_id"],
    "aid_fund_utilization": ["aid_type", "date_from", "date_to"],
    "claims_register": ["aid_type", "status", "date_from", "date_to", "department"],
    "budget_vs_actual": ["year"],
    "membership_registry": ["membership_status", "classification", "department", "date_from", "date_to"],
    "audit_trail_export": ["date_from", "date_to", "table_name", "action", "limit"],
}

GA_GROUPS = [
    ("Collections", ["delinquency", "collection_efficiency", "member_soa"]),
    ("Aid Funds", ["aid_fund_utilization", "claims_register"]),
    ("Governance", ["budget_vs_actual", "membership_registry", "audit_trail_export"]),
]


def build_ga_report(request, report_key):
    """Return a normalized report dict or None if the key is unknown."""
    builder = GA_BUILDERS.get(report_key)
    if builder is None:
        return None
    return builder(request)


def ga_reports_meta():
    """UI metadata: groups of {key, title, filters} for the generic viewer."""
    return {
        "groups": [
            {
                "label": label,
                "reports": [
                    {"key": key, "title": GA_TITLES[key], "filters": GA_FILTERS[key]}
                    for key in keys
                ],
            }
            for label, keys in GA_GROUPS
        ]
    }

