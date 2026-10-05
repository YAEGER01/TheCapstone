"""Member Dashboard — financial transparency service layer.

Single source of truth for everything the Member Dashboard shows about the
association's funds and the member's own records.

Scoping rules that the officer endpoints keep:

* **Financial Overview is organisation-wide.** The fund balance, total
  collections, total inflows and total outflows are the association's figures —
  a member is entitled to see them.
* **Everything else is member-only.** Collections, cash flow and the personal
  record panels report only the signed-in member. No endpoint below accepts a
  member id from the client, so there is no parameter to tamper with.
* Officer URLs stay role-locked. The Member role reaches these aggregations
  only through this module, so nothing here widens an officer endpoint.
* Every read is logged by the calling view through `_log_sensitive_read` — a
  member checking the books is itself an auditable event.
"""

from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from core_system.constants.policy_constants import is_retired_member
from core_system.constants.status_constants import Status
from core_system.services.dues_status import dues_frontier_month
from core_system.models import (
    Contribution,
    DeathAid,
    FundTransaction,
    Member,
    MemberAssessment,
    MemberLedger,
    MedicalAid,
    MembershipFee,
    MonthlyDues,
    SalaryDeductionExemption,
    SystemSetting,
)

# Fund inflow source types that represent money COLLECTED from members through
# the monthly deduction/assessment batches and the one-time membership fee.
#
# `salary_deduction_remittance` and `payroll_batch` are deliberately excluded:
# they are legacy booking paths for the same money already written as
# `monthly_dues` / `aid_setaside_*`, so counting them here would double-count
# collections.
COLLECTION_SOURCE_TYPES = (
    "monthly_dues",
    "membership_fee",
    "aid_setaside_medical",
    "aid_setaside_death",
)

SOURCE_TYPE_LABELS = {
    "payroll_batch": "Payroll Batch",
    "death_aid": "Death Aid Disbursement",
    "medical_aid": "Medical Aid Disbursement",
    "membership_fee": "Membership Fee",
    "monthly_dues": "Monthly Dues",
    "aid_setaside_medical": "Medical Aid Set-Aside",
    "aid_setaside_death": "Death Aid Set-Aside",
    "contribution": "Contribution",
    "manual_adjustment": "Manual Adjustment",
    "aid_post_payment": "Aid Post Fund Payment",
    "salary_deduction_remittance": "Salary Deduction Remittance",
    "other_transaction": "Other Transaction",
}

# Member-facing ledger categories, used to label merged personal movements.
PERSONAL_TYPE_LABELS = {
    "membership_fee": "Membership Fee",
    "monthly_dues": "Monthly Dues",
    "contribution": "Contribution",
    "medical_aid": "Medical Aid",
    "death_aid": "Death Aid",
    "refund": "Refund",
    "adjustment": "Adjustment",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _day_start(day: date):
    """Aware start-of-day in the project timezone.

    Bare-date params must compare as aware datetimes: the `__date` lookup
    relies on MySQL named timezones (often unloaded -> matches nothing), and
    day boundaries belong to the user's locale, not UTC.
    """
    return timezone.make_aware(datetime.combine(day, dtime.min), timezone.get_current_timezone())


def _day_end(day: date):
    return timezone.make_aware(datetime.combine(day, dtime.max), timezone.get_current_timezone())


def _f(value) -> float:
    return round(float(value or 0), 2)


# Placeholders that must NEVER participate in aid de-duplication: matching
# on them would merge unrelated aids into one.
_AID_PARTY_PLACEHOLDERS = frozenset({"", "—", "-", "member", "general fund"})


def _aid_party_tokens(value) -> frozenset:
    """Order-insensitive name tokens: 'DELA CRUZ, Juan' == 'Juan Dela Cruz'."""
    return frozenset(
        t for t in str(value or "").lower().replace(",", " ").replace(".", " ").split() if t
    )


def _same_aid_party(a, b) -> bool:
    """True when two recipient spellings name the same party.

    Assessment-item recipients are stored formatted ('SURNAME, Given' via the
    President's autocomplete) while claim/post resolution yields the raw
    `full_name` ('Given M SURNAME'). A plain equality check never matches
    across that boundary, so the same collection used to be appended twice —
    once per source — in drawers, reports and the Aid page.
    """
    sa = str(a or "").strip().casefold()
    sb = str(b or "").strip().casefold()
    if sa in _AID_PARTY_PLACEHOLDERS or sb in _AID_PARTY_PLACEHOLDERS:
        return False
    if sa == sb:
        return True
    ka, kb = _aid_party_tokens(a), _aid_party_tokens(b)
    return bool(ka) and ka == kb


def _formatted_aid_name(full_name) -> str:
    """Local 'SURNAME, Given' replica (no views-layer import, no cycles)."""
    parts = str(full_name or "").strip().split()
    if len(parts) < 2:
        return str(full_name or "").strip()
    return f"{parts[-1].upper()}, {' '.join(parts[:-1])}"


_AID_NAME_SUFFIXES = frozenset({"JR", "SR", "II", "III", "IV", "V"})

# Particles that join a compound surname in raw full_names
# ('Juan Dela Cruz' -> surname 'Dela Cruz', not 'Cruz').
_AID_SURNAME_PARTICLES = frozenset({
    "DELA", "DEL", "DELOS", "DE", "LOS", "SAN", "SANTA", "SANTO",
    "STO", "STA", "ST", "VDA", "VAN", "VON",
})

_AID_NAME_PLACEHOLDERS = frozenset({"", "—", "-", "member", "general fund", "external campus aid"})


def short_aid_name(name) -> str:
    """Member-facing aid party name: 'Frederick Madayag' -> 'Madayag, F.'.

    Accepts both spellings in the system — raw `full_name`
    ('Frederick A. Madayag') and the stored 'SURNAME, Given' form
    ('MADAYAG, Frederick') — plus 'Campus — Person' composites (only the
    person segment is shortened). Placeholders and single-word names pass
    through untouched.

    Display-only: never feed this back into `_same_aid_party` matching,
    whose token equality needs the full spellings.
    """
    s = str(name or "").strip()
    if not s or s.casefold() in _AID_NAME_PLACEHOLDERS:
        return s
    if " — " in s:
        head, _, tail = s.partition(" — ")
        short_tail = short_aid_name(tail)
        return f"{head} — {short_tail}" if short_tail != tail else s
    if "," in s:
        surname, _, rest = s.partition(",")
        surname = surname.strip()
        given = rest.strip().split()
    else:
        parts = s.split()
        while len(parts) > 1 and parts[-1].rstrip(".").upper() in _AID_NAME_SUFFIXES:
            parts = parts[:-1]
        if len(parts) < 2:
            return s
        # Grow compound surnames leftwards over particles.
        surname_parts = [parts.pop()]
        while parts and parts[-1].rstrip(".").upper() in _AID_SURNAME_PARTICLES:
            surname_parts.insert(0, parts.pop())
        if not parts:
            return s
        surname = " ".join(surname_parts)
        given = parts
    if not surname or not given or not given[0]:
        return s
    return f"{surname.title()}, {given[0][0].upper()}."


def _item_display_recipient(item) -> str:
    """Recipient text for an assessment aid item (external-aware)."""
    if bool(getattr(item, "is_external_aid", False)):
        try:
            display = item.external_display
        except Exception:
            display = ""
        if display:
            return display
    return (getattr(item, "recipient", None) or "").strip() or "—"


def _post_external_display(post) -> str:
    """Recipient text for an external-aid tracking post."""
    campus = (getattr(post, "external_campus", None) or "").strip()
    beneficiary = (getattr(post, "external_beneficiary", None) or "").strip()
    if campus and beneficiary:
        return f"{campus} — {beneficiary}"
    archive = getattr(post, "archive_id_FK", None)
    archive_name = (getattr(archive, "member_name", None) or "").strip() if archive else ""
    return campus or beneficiary or archive_name or "External campus aid"


def _parse_date(value) -> date | None:
    try:
        return date.fromisoformat((str(value) if value else "").strip())
    except (ValueError, TypeError):
        return None


def _int_param(params: dict, name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(params.get(name, default) or default)))
    except (TypeError, ValueError):
        return default


def _paginate(items: list, page: int, per_page: int) -> dict:
    total = len(items)
    return {
        "items": items[(page - 1) * per_page: page * per_page],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if per_page else 1,
    }


# ---------------------------------------------------------------------------
# 1. Financial Overview — organisation-wide
# ---------------------------------------------------------------------------

def _setting(key: str, default: str) -> str:
    row = SystemSetting.objects.filter(setting_key=key).first()
    return row.setting_value if row is not None else default


def fund_totals(qs=None) -> dict:
    """Lifetime cash in / out / balance over the fund ledger."""
    base = FundTransaction.objects.all() if qs is None else qs
    totals = base.aggregate(
        total_in=Sum("amount", filter=Q(direction="inflow")),
        total_out=Sum("amount", filter=Q(direction="outflow")),
    )
    total_in = _f(totals["total_in"])
    total_out = _f(totals["total_out"])
    return {
        "total_in": total_in,
        "total_out": total_out,
        "balance": round(total_in - total_out, 2),
    }


def total_collections() -> float:
    """Lifetime money collected from members.

    Derived from the fund ledger rather than from the assessment tables so the
    card a member sees always reconciles line-for-line with the cash movement
    recorded underneath it.
    """
    total = FundTransaction.objects.filter(
        direction="inflow", source_type__in=COLLECTION_SOURCE_TYPES
    ).aggregate(t=Sum("amount"))["t"]
    return _f(total)


def safety_threshold() -> float:
    raw = _setting("safety_threshold", "20000")
    try:
        return _f(Decimal(str(raw)))
    except (ArithmeticError, ValueError, TypeError):
        return 0.0


def fund_summary() -> dict:
    """The Financial Overview cards — the association's own position."""
    lifetime = fund_totals()
    now = timezone.localtime()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    mtd = fund_totals(FundTransaction.objects.filter(recorded_at__gte=month_start))
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    ytd = fund_totals(FundTransaction.objects.filter(recorded_at__gte=year_start))
    threshold = safety_threshold()
    collections = total_collections()

    return {
        "ok": True,
        "scope": "organization",
        "generated_at": now.isoformat(),
        "balance": lifetime["balance"],
        "total_collections": collections,
        "total_in": lifetime["total_in"],
        "total_out": lifetime["total_out"],
        "month_in": mtd["total_in"],
        "month_out": mtd["total_out"],
        "year_in": ytd["total_in"],
        "year_out": ytd["total_out"],
        "safety_threshold": threshold,
        "headroom": round(lifetime["balance"] - threshold, 2),
        "collection_share": (
            round(collections / lifetime["total_in"] * 100, 1)
            if lifetime["total_in"] > 0 else 0
        ),
        "period_label": now.strftime("%B %Y"),
    }


def monthly_trend(months: int = 12) -> dict:
    """Per-month inflow / outflow / running balance, oldest first.

    Year extraction happens in Python, not SQL: this server's MySQL has no
    timezone tables loaded, so CONVERT_TZ-based bucketing returns NULL. The
    window is range-filtered first, so the row count stays small.
    """
    months = _int_param({"months": months}, "months", 12, 1, 36)
    now = timezone.localtime()
    cursor = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for _ in range(months - 1):
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    window_start = _day_start(cursor.date())

    rows = list(
        FundTransaction.objects.filter(recorded_at__gte=window_start)
        .order_by("recorded_at", "transaction_id_PK")
        .values_list("recorded_at", "direction", "amount")
    )

    buckets: dict[tuple[int, int], dict] = {}
    for _ in range(months):
        buckets[(cursor.year, cursor.month)] = {
            "total_in": 0.0, "total_out": 0.0, "count": 0,
        }
        cursor = (cursor + timedelta(days=32)).replace(day=1)

    for recorded_at, direction, amount in rows:
        if recorded_at is None:
            continue
        local = timezone.localtime(recorded_at)
        bucket = buckets.get((local.year, local.month))
        if bucket is None:
            continue
        value = float(amount or 0)
        if direction == "inflow":
            bucket["total_in"] = round(bucket["total_in"] + value, 2)
        else:
            bucket["total_out"] = round(bucket["total_out"] + value, 2)
        bucket["count"] += 1

    # Carry the true opening position into the first visible month so the
    # running balance starts truthfully instead of at zero.
    prior = FundTransaction.objects.filter(recorded_at__lt=window_start).aggregate(
        t=Sum("amount", filter=Q(direction="inflow")),
        o=Sum("amount", filter=Q(direction="outflow")),
    )
    running = _f(prior["t"]) - _f(prior["o"])

    series = []
    for key in sorted(buckets):
        bucket = buckets[key]
        running = round(running + bucket["total_in"] - bucket["total_out"], 2)
        series.append({
            "key": f"{key[0]}-{key[1]:02d}",
            "label": date(key[0], key[1], 1).strftime("%b %Y"),
            "year": key[0],
            "month": key[1],
            "total_in": bucket["total_in"],
            "total_out": bucket["total_out"],
            "balance": running,
            "count": bucket["count"],
        })

    return {
        "ok": True,
        "scope": "organization",
        "months": months,
        "opening_balance": _f(prior["t"]) - _f(prior["o"]),
        "current_balance": fund_totals()["balance"],
        "series": series,
    }



# ---------------------------------------------------------------------------
# 2. Cash flow — member-only
# ---------------------------------------------------------------------------

def _credit(direction: str) -> bool:
    """Member-ledger direction is credit/debit; normalise to money in/out."""
    return (direction or "").strip().lower() in ("credit", "inflow", "in")


def _personal_movements(member: Member) -> list[dict]:
    """Every money movement attributable to one member, newest first.

    ``MemberLedger`` is the canonical record and is the only source of rows
    that money actually moved. The approval views mirror each approved
    ``MembershipFee``, ``MonthlyDues`` and ``MemberAssessment`` into the ledger
    keyed by ``(reference_type, reference_id)``, so those three tables are read
    here purely as a **backstop**: a row is added only when no ledger entry
    references it.

    Without that guard the same ₱100 fee is counted twice — once from the ledger
    row written at approval and once from the fee itself — which is exactly the
    kind of figure a member cannot check and therefore never should see.

    A backstop row carries ``outstanding``, because an approval that has not
    happened yet is money the member owes and has not paid.

    Each row's ``id`` names its own table (``ledger_12``, ``fee_4``) so the
    detail endpoint can be addressed without guessing.
    """
    movements: list[dict] = []
    mirrored: set[tuple[str, int]] = set()

    for entry in MemberLedger.objects.filter(
        member_id_FK=member
    ).select_related("recorded_by_user_id_FK").order_by("-recorded_at", "-ledger_id_PK"):
        if entry.reference_type and entry.reference_id:
            mirrored.add((entry.reference_type, entry.reference_id))
        movements.append({
            "id": f"ledger_{entry.ledger_id_PK}",
            "kind": entry.transaction_type or "transaction",
            "kind_label": PERSONAL_TYPE_LABELS.get(
                entry.transaction_type, (entry.transaction_type or "Transaction").replace("_", " ").title()
            ),
            "direction": "in" if _credit(entry.direction) else "out",
            "amount": _f(entry.amount),
            "description": entry.description or PERSONAL_TYPE_LABELS.get(
                entry.transaction_type, "Transaction"
            ),
            "reference": entry.reference_type or "",
            "reference_id": entry.reference_id,
            "notes": entry.notes or "",
            "date": entry.recorded_at.isoformat() if entry.recorded_at else "",
            "recorded_by": entry.recorded_by_user_id_FK.full_name if entry.recorded_by_user_id_FK else "System",
            "balance_after": _f(entry.balance_after),
        })

    # A salary deduction is owed whether or not it has been approved, so this
    # backstop row also carries the outstanding balance.
    for ma in MemberAssessment.objects.filter(
        member_id_FK=member
    ).select_related("assessment_id_FK").order_by("assessment_id_FK__month"):
        if ("MemberAssessment", ma.member_assessment_id_PK) in mirrored:
            continue
        movements.append({
            "id": f"assessment_{ma.member_assessment_id_PK}",
            "kind": "monthly_dues",
            "kind_label": "Monthly Dues",
            "direction": "in",
            "amount": _f(ma.actual_deduction),
            "description": f"Monthly Deduction — {ma.assessment_id_FK.month_label}",
            "reference": ma.assessment_id_FK.month_label,
            "reference_id": ma.member_assessment_id_PK,
            "notes": ma.get_status_display(),
            "date": (ma.approved_at or ma.recorded_at).isoformat()
            if (ma.approved_at or ma.recorded_at) else "",
            "recorded_by": ma.recorded_by_id_FK.full_name if ma.recorded_by_id_FK else "",
            "outstanding": _f(ma.outstanding_balance),
        })

    for dues in MonthlyDues.objects.filter(
        member_id_FK=member, month_covered__isnull=False
    ):
        if ("MonthlyDues", dues.dues_id_PK) in mirrored:
            continue
        paid = (dues.payment_status or "") in Status.ALL_AUDITOR_VERIFIED
        if not paid:
            continue
        movements.append({
            "id": f"dues_{dues.dues_id_PK}",
            "kind": "monthly_dues",
            "kind_label": "Monthly Dues",
            "direction": "in",
            "amount": _f(dues.amount),
            "description": f"Monthly Dues — {dues.month_covered}",
            "reference": dues.receipt_number or dues.month_covered,
            "reference_id": dues.dues_id_PK,
            "notes": dues.payment_status or "",
            "date": dues.payment_date.isoformat() if dues.payment_date else "",
            "recorded_by": "",
            "outstanding": 0.0,
        })

    for fee in MembershipFee.objects.filter(member_id_FK=member):
        if ("MembershipFee", fee.fee_id_PK) in mirrored:
            continue
        movements.append({
            "id": f"fee_{fee.fee_id_PK}",
            "kind": "membership_fee",
            "kind_label": "Membership Fee",
            "direction": "in",
            "amount": _f(fee.amount),
            "description": "Membership Fee",
            "reference": fee.receipt_number or fee.deposit_reference or "",
            "reference_id": fee.fee_id_PK,
            "notes": fee.payment_status or "",
            "date": fee.payment_date.isoformat() if fee.payment_date else "",
            "recorded_by": fee.recorded_by_user_id_FK.full_name if fee.recorded_by_user_id_FK else "",
            "outstanding": 0.0,
        })

    medical_ids = set(
        MedicalAid.objects.filter(member_id_FK=member)
        .values_list("medical_aid_id_PK", flat=True)
    )
    death_ids = set(
        DeathAid.objects.filter(member_id_FK=member)
        .values_list("death_aid_id_PK", flat=True)
    )
    for c in Contribution.objects.filter(
        member_id_FK=member
    ).select_related("aid_tracking_post_id_FK"):
        post = c.aid_tracking_post_id_FK
        # A contribution that is only the bookkeeping echo of this member's own
        # medical/death aid claim is not a separate payment they made.
        if post is not None and (
            (post.source_type == "medical_aid" and post.source_id in medical_ids)
            or (post.source_type == "death_aid" and post.source_id in death_ids)
        ):
            continue
        movements.append({
            "id": f"contribution_{c.contribution_id_PK}",
            "kind": "contribution",
            "kind_label": "Contribution",
            "direction": "in",
            "amount": _f(c.paid_amount),
            "description": "Contribution — {}".format(
                (post.aid_type if post else "") or "general"
            ),
            "reference": (post.target_month if post else "") or "",
            "reference_id": c.contribution_id_PK,
            "notes": c.status or "",
            "date": c.payment_date.isoformat() if c.payment_date else "",
            "recorded_by": "",
            "outstanding": round(_f(c.expected_amount) - _f(c.paid_amount), 2),
        })

    movements.sort(key=lambda m: (m["date"] or "", m["id"]), reverse=True)
    return movements


def _with_running_net(movements: list[dict]) -> list[dict]:
    """Attach a cumulative net to each movement, newest row first.

    Walking newest-to-oldest and accumulating means each row carries the net up
    to and including itself — the position the member was in at that point.
    """
    running = 0.0
    for m in movements:
        running = round(running + (m["amount"] if m["direction"] == "in" else -m["amount"]), 2)
        m["running_net"] = running
    return movements


def member_cash_flow(member: Member, params: dict) -> dict:
    """The member's own money in / money out, with a running personal total.

    Filters: `kind`, `direction`, `year`, `date_from`, `date_to`, `page`,
    `per_page`.
    """
    # Fetched once and filtered in place: the running total and the lifetime
    # totals both need the unfiltered set, while the page needs it narrowed.
    everything = _with_running_net(_personal_movements(member))
    movements = list(everything)

    kind = (params.get("kind") or "").strip()
    if kind:
        movements = [m for m in movements if m["kind"] == kind]

    direction = (params.get("direction") or "").strip()
    if direction in ("in", "out"):
        movements = [m for m in movements if m["direction"] == direction]

    year = (params.get("year") or "").strip()
    if year.isdigit():
        movements = [m for m in movements if (m["date"] or "")[:4] == year]

    date_from = _parse_date(params.get("date_from"))
    date_to = _parse_date(params.get("date_to"))
    if date_from:
        movements = [m for m in movements if (m["date"] or "")[:10] >= date_from.isoformat()]
    if date_to:
        movements = [m for m in movements if (m["date"] or "")[:10] <= date_to.isoformat()]

    # Totals describe the member's lifetime position, not just the filtered
    # window, so the cards do not jump around when a filter is applied.
    total_in = round(sum(m["amount"] for m in everything if m["direction"] == "in"), 2)
    total_out = round(sum(m["amount"] for m in everything if m["direction"] == "out"), 2)
    outstanding = round(
        sum(m.get("outstanding") or 0 for m in everything), 2
    )

    page = _int_param(params, "page", 1, 1, 100000)
    per_page = _int_param(params, "per_page", 25, 5, 200)
    paged = _paginate(movements, page, per_page)

    kinds = sorted({m["kind"] for m in everything})
    return {
        "ok": True,
        "scope": "member",
        **paged,
        "summary": {
            "total_in": total_in,
            "total_out": total_out,
            "net": round(total_in - total_out, 2),
            "outstanding": max(outstanding, 0.0),
            "count": len(everything),
        },
        "filters": {
            "kind": kind,
            "direction": direction,
            "year": year,
            "date_from": params.get("date_from") or "",
            "date_to": params.get("date_to") or "",
        },
        "kinds": [
            {"value": k, "label": PERSONAL_TYPE_LABELS.get(k, k.replace("_", " ").title())}
            for k in kinds
        ],
        "years": sorted({(m["date"] or "")[:4] for m in everything if (m["date"] or "")[:4]}, reverse=True),
    }


def member_transaction_detail(member: Member, movement_id: str) -> dict | None:
    """One of the member's own movements, with its supporting remarks.

    The lookup runs through the member's own movement list, so a movement id
    belonging to another member simply is not found — there is no unscoped
    query for an id to escape through.
    """
    for m in _with_running_net(_personal_movements(member)):
        if m["id"] == movement_id:
            detail = dict(m)
            detail["ok"] = True
            detail["scope"] = "member"
            detail["remarks"] = m.get("notes") or ""
            return detail
    return None


# ---------------------------------------------------------------------------
# 4. Personal member records — member-only
# ---------------------------------------------------------------------------

def _contribution_post_recipient(post) -> tuple[str | None, str]:
    """(kind label, recipient name) for an aid tracking post.

    Mirrors the recipient resolution used by the DUE drawer so the Aid page
    can de-duplicate collections recorded through both the monthly
    assessment and the aid-tracking post.
    """
    if post is None:
        return None, ""
    if post.source_type == "medical_aid" and post.source_id:
        med = (
            MedicalAid.objects.filter(medical_aid_id_PK=post.source_id)
            .select_related("member_id_FK")
            .first()
        )
        if med is not None:
            return "Medical Aid", (med.member_id_FK.full_name or "").strip() or "Member"
    if post.source_type == "death_aid" and post.source_id:
        death = (
            DeathAid.objects.filter(death_aid_id_PK=post.source_id)
            .select_related("member_id_FK")
            .first()
        )
        if death is not None:
            return (
                "Death Aid",
                (death.deceased_name or "").strip()
                or (death.member_id_FK.full_name or "").strip()
                or "Member",
            )
    if (post.source_type or "") == "external_aid":
        aid_label = "Medical Aid" if (post.aid_type or "") == "medical_aid" else "Death Aid"
        return aid_label, _post_external_display(post)
    return None, ""


def _assessment_aid_kind(purpose: str) -> str:
    """Aid-page aid_type for an assessment item purpose."""
    from core_system.models import AssessmentItem

    if purpose == AssessmentItem.PURPOSE_MEDICAL_AID:
        return "medical_aid"
    if purpose == AssessmentItem.PURPOSE_DEATH_AID:
        return "death_aid"
    return "other_aid"


def contributions(member: Member) -> dict:
    """Contribution history, excluding rows that are only bookkeeping echoes
    of this member's own medical/death aid claims.

    Covers BOTH collection flows: OTC aid-tracking-post contributions AND
    salary-deduction aids (aid-purpose assessment items). Without the second
    source the Aid page is empty for members whose aids were collected
    through the monthly assessment — the same data the DUE drawer shows.
    """
    from core_system.ledger_utils import build_member_assessment_breakdown
    from core_system.models import AssessmentItem, MemberAssessment

    medical_ids = set(
        MedicalAid.objects.filter(member_id_FK=member)
        .values_list("medical_aid_id_PK", flat=True)
    )
    death_ids = set(
        DeathAid.objects.filter(member_id_FK=member)
        .values_list("death_aid_id_PK", flat=True)
    )

    items = []
    total_paid = 0.0

    # --- Salary-deduction aids (assessment allocations), newest first ---
    seen: set[tuple[str, str, str]] = set()
    seen_item_ids: set[int] = set()
    member_assessments = (
        MemberAssessment.objects.filter(member_id_FK=member)
        .select_related("assessment_id_FK")
        .prefetch_related("allocations__assessment_item_id_FK")
        .order_by("-assessment_id_FK__month", "-member_assessment_id_PK")
    )
    for ma in member_assessments:
        assessment = ma.assessment_id_FK
        if assessment is None or assessment.month is None:
            continue
        target_month = assessment.month.strftime("%Y-%m")
        detail = build_member_assessment_breakdown(ma)
        rows_by_label = {
            row.get("purpose"): row for row in detail["rows"] if row.get("kind") == "item"
        }
        pay_dt = ma.approved_at or ma.recorded_at
        for alloc in ma.allocations.all():
            item = alloc.assessment_item_id_FK
            if item.purpose == AssessmentItem.PURPOSE_MONTHLY_DUE:
                continue
            row = rows_by_label.get(item.label, {})
            expected = _f(row.get("required", item.amount or 0))
            paid = _f(row.get("applied", alloc.amount_applied or 0))
            if expected <= 0 and paid <= 0:
                continue
            kind_label = (
                "Medical Aid"
                if item.purpose == AssessmentItem.PURPOSE_MEDICAL_AID
                else "Death Aid"
                if item.purpose == AssessmentItem.PURPOSE_DEATH_AID
                else item.purpose_display()
            )
            recipient = _item_display_recipient(item)
            seen.add((kind_label.casefold(), recipient.casefold(), target_month))
            seen_item_ids.add(item.item_id_PK)
            total_paid += paid
            items.append({
                "id": f"assessment_{ma.member_assessment_id_PK}_{item.item_id_PK}",
                "aid_type": _assessment_aid_kind(item.purpose),
                "aid_type_label": kind_label,
                "recipient": recipient,
                "target_month": target_month,
                "expected": round(expected, 2),
                "paid": round(paid, 2),
                "balance": round(max(0.0, expected - paid), 2),
                "payment_date": pay_dt.date().isoformat() if pay_dt else "",
                "status": ma.get_status_display(),
                "notes": "",
            })

    # --- OTC aid-tracking-post contributions (existing behavior) ---
    rows = (
        Contribution.objects.filter(member_id_FK=member)
        .exclude(
            Q(aid_tracking_post_id_FK__source_type="medical_aid",
              aid_tracking_post_id_FK__source_id__in=medical_ids)
            | Q(aid_tracking_post_id_FK__source_type="death_aid",
                aid_tracking_post_id_FK__source_id__in=death_ids)
        )
        .select_related("aid_tracking_post_id_FK")
        .order_by("-payment_date", "-contribution_id_PK")
    )

    for c in rows:
        post = c.aid_tracking_post_id_FK
        if post is not None:
            linked_item_id = getattr(post, "assessment_item_id_FK_id", None)
            if linked_item_id and linked_item_id in seen_item_ids:
                # Same collection already shown via the monthly assessment
                # (exact linkage — immune to recipient spelling differences).
                continue
        kind_label, recipient = _contribution_post_recipient(post)
        target_month = post.target_month if post else ""
        if kind_label and any(
            _same_aid_party(recipient, seen_recipient)
            and kind_label.casefold() == seen_kind.casefold()
            and target_month == seen_month
            for seen_kind, seen_recipient, seen_month in seen
        ):
            # Same collection already shown via the monthly assessment.
            continue
        paid = _f(c.paid_amount)
        total_paid += paid
        items.append({
            "id": c.contribution_id_PK,
            "aid_type": post.aid_type if post else "",
            "aid_type_label": (post.aid_type if post else "").replace("_", " ").title(),
            "recipient": recipient,
            "target_month": post.target_month if post else "",
            "expected": _f(c.expected_amount),
            "paid": paid,
            "balance": round(_f(c.expected_amount) - paid, 2),
            "payment_date": c.payment_date.isoformat() if c.payment_date else "",
            "status": c.status,
            "notes": c.notes or "",
        })

    items.sort(key=lambda i: (i["payment_date"] or "", str(i["id"])), reverse=True)

    # Member-facing Aid page names read 'Surname, F.' — applied here, after
    # all de-duplication matching above ran on the raw spellings.
    for i in items:
        i["recipient"] = short_aid_name(i.get("recipient"))

    return {
        "ok": True,
        "scope": "member",
        "items": items,
        "total_paid": round(total_paid, 2),
        "count": len(items),
    }


def dues_matrix(member: Member, months: int = 24) -> dict:
    """Month x status grid for the member's monthly dues, oldest first.

    Exempted and retired members are marked as such rather than being shown a
    wall of unpaid months they will never be charged for.
    """
    months = _int_param({"months": months}, "months", 24, 6, 60)

    # The last `months` calendar months, ending with the backend dues
    # frontier (the latest charged month, e.g. April 2027) — never the
    # machine date alone, so months everyone already paid are actually
    # shown. Falls back to today when nothing was charged yet. Walking
    # backwards from the 1st and then reversing keeps this correct across year
    # boundaries without any date arithmetic on day-of-month.
    horizon = dues_frontier_month()
    cursor = date(int(horizon[:4]), int(horizon[5:7]), 1)
    window = []
    for _ in range(months):
        window.append((cursor.year, cursor.month))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    window.reverse()

    dues_by_month = {
        d.month_covered: d
        for d in MonthlyDues.objects.filter(
            member_id_FK=member, month_covered__isnull=False
        )
    }
    assessment_by_month = {
        a.assessment_id_FK.month.strftime("%Y-%m"): a
        for a in MemberAssessment.objects.filter(
            member_id_FK=member
        ).select_related("assessment_id_FK")
    }
    exempt_months = set(
        SalaryDeductionExemption.objects.filter(
            member_id_FK=member, status__in=["Pending", "Approved"]
        ).values_list("month_covered", flat=True)
    )
    exempt_months.discard(None)

    retired = is_retired_member(member)
    joined_period = member.date_joined.strftime("%Y-%m") if member.date_joined else None

    grid = []
    totals = {"paid": 0.0, "pending": 0.0, "unpaid": 0.0, "outstanding": 0.0}
    for year, month in window:
        key = f"{year}-{month:02d}"

        dues = dues_by_month.get(key)
        assessment = assessment_by_month.get(key)
        amount = 0.0
        status = "Not Due"
        detail = ""

        if assessment is not None:
            amount = _f(assessment.actual_deduction)
            outstanding = _f(assessment.outstanding_balance)
            if outstanding > 0:
                status = "Partial"
                detail = f"₱{outstanding:,.2f} outstanding"
            else:
                status = "Paid"
        elif dues is not None:
            amount = _f(dues.amount)
            status = dues.payment_status or "Unpaid"
        elif key in exempt_months:
            status = "Exempt"
        elif retired:
            status = "Retired"
        elif joined_period and key < joined_period:
            status = "Not Due"
        else:
            status = "Unpaid"

        if status in Status.ALL_AUDITOR_VERIFIED:
            totals["paid"] += amount
        elif status in ("Pending", "Pending Verification"):
            totals["pending"] += amount
        elif status == "Unpaid":
            totals["unpaid"] += amount

        grid.append({
            "key": key,
            "label": date(year, month, 1).strftime("%b %Y"),
            "status": status,
            "amount": amount,
            "detail": detail,
        })

    if retired:
        totals["pending"] = 0.0
        totals["unpaid"] = 0.0
        totals["outstanding"] = 0.0

    return {
        "ok": True,
        "scope": "member",
        "months": months,
        "grid": grid,
        "totals": {k: round(v, 2) for k, v in totals.items()},
        "is_retired": retired,
    }


def payments(member: Member, params: dict) -> dict:
    """Combined payment records: one-time membership fee + monthly dues, with
    the Treasurer / Auditor / President verification columns."""
    method = (params.get("method") or "").strip().lower()

    rows = []
    for fee in MembershipFee.objects.filter(member_id_FK=member):
        fee_method = (fee.payment_method or "").lower()
        if method and method != fee_method:
            continue
        rows.append({
            "kind": "Membership Fee",
            "period": "One-time",
            "amount": _f(fee.amount),
            "method": fee.payment_method or "",
            "status": fee.payment_status or "",
            "date": fee.payment_date.isoformat() if fee.payment_date else "",
            "reference": fee.receipt_number or fee.deposit_reference or "",
            "treasurer_status": "",
            "auditor_status": "",
            "president_status": "",
            "_sort": fee.payment_date,
        })

    for dues in MonthlyDues.objects.filter(member_id_FK=member):
        dues_method = (dues.payment_method or "").lower()
        if method and method != dues_method:
            continue
        rows.append({
            "kind": "Monthly Dues",
            "period": dues.month_covered or "",
            "amount": _f(dues.amount),
            "method": dues.payment_method or "",
            "status": dues.payment_status or "",
            "date": dues.payment_date.isoformat() if dues.payment_date else "",
            "reference": dues.receipt_number or "",
            "treasurer_status": dues.treasurer_status or "",
            "auditor_status": dues.auditor_status or "",
            "president_status": dues.president_status or "",
            "_sort": dues.payment_date,
        })

    for assessment in MemberAssessment.objects.filter(
        member_id_FK=member
    ).select_related("assessment_id_FK"):
        period = assessment.assessment_id_FK.month.strftime("%Y-%m")
        if method and method != "salary deduction":
            continue
        rows.append({
            "kind": "Monthly Dues",
            "period": period,
            "amount": _f(assessment.actual_deduction),
            "method": "Salary Deduction",
            "status": assessment.get_status_display(),
            "date": (
                (assessment.approved_at or assessment.recorded_at).date().isoformat()
                if (assessment.approved_at or assessment.recorded_at) else ""
            ),
            "reference": assessment.assessment_id_FK.month_label,
            "treasurer_status": assessment.get_status_display(),
            "auditor_status": assessment.get_status_display(),
            "president_status": assessment.assessment_id_FK.get_status_display(),
            "_sort": (assessment.approved_at or assessment.recorded_at).date()
            if (assessment.approved_at or assessment.recorded_at) else date.min,
        })

    rows.sort(key=lambda r: (r["_sort"] or date.min, r["reference"]), reverse=True)
    for row in rows:
        row.pop("_sort", None)

    page = _int_param(params, "page", 1, 1, 100000)
    per_page = _int_param(params, "per_page", 25, 5, 100)
    return {
        "ok": True,
        "scope": "member",
        **_paginate(rows, page, per_page),
    }


def _due_month_breakdown(member: Member, year: int, month: int) -> dict:
    """One month of the DUE drawer: due + aids with per-member and whole-month totals.

    Canonical sources only:
    - MonthlyAssessment + MemberAssessment (+ build_member_assessment_breakdown)
      for what THIS member owed / paid, split by AssessmentItem purpose
      (monthly_due vs medical/death aid fund, recipient on the item).
    - MemberAssessmentAllocation sums across ALL members for the whole-month
      "total collected" figures.
    - MonthlyDues legacy rows when no assessment month exists.
    - AidTrackingPost + Contribution rows when aids were tracked outside the
      monthly assessment (OTC aid posts for the same target month).
    """
    from core_system.ledger_utils import build_member_assessment_breakdown
    from core_system.models import (
        AidTrackingPost,
        AssessmentItem,
        DeathAid,
        MedicalAid,
        MemberAssessment,
        MemberAssessmentAllocation,
        MonthlyAssessment,
        MonthlyDues,
    )

    month_key = f"{year}-{month:02d}"
    month_label = date(year, month, 1).strftime("%b %Y").upper()

    monthly_assessment = MonthlyAssessment.objects.filter(
        month__year=year, month__month=month
    ).prefetch_related("items").first()

    mine = None
    detail = None
    if monthly_assessment is not None:
        mine = (
            MemberAssessment.objects.filter(
                member_id_FK=member, assessment_id_FK=monthly_assessment
            )
            .select_related("assessment_id_FK")
            .prefetch_related("allocations__assessment_item_id_FK")
            .first()
        )
        if mine is not None:
            detail = build_member_assessment_breakdown(mine)

    # --- This member's monthly-due slice (expected / deducted / outstanding) ---
    due_expected = 0.0
    due_deducted = 0.0
    due_outstanding = 0.0
    due_status = "No record"
    due_paid_date = None
    if detail is not None:
        for row in detail["rows"]:
            if row.get("kind") == "prior":
                continue
            item_purpose = ""
            if mine is not None:
                for alloc in mine.allocations.all():
                    if alloc.assessment_item_id_FK.label == row.get("purpose"):
                        item_purpose = alloc.assessment_item_id_FK.purpose
                        break
            if item_purpose in ("", AssessmentItem.PURPOSE_MONTHLY_DUE):
                # Rows without a matched allocation are monthly-due lines only
                # when the assessment itself carries a monthly-due item.
                if item_purpose == "" and monthly_assessment is not None and not monthly_assessment.items.filter(
                    purpose=AssessmentItem.PURPOSE_MONTHLY_DUE
                ).exists():
                    continue
                due_expected += _f(row.get("required"))
                due_deducted += _f(row.get("applied"))
                due_outstanding += _f(row.get("remaining"))
        due_outstanding = round(max(0.0, due_expected - due_deducted), 2)
        due_expected = round(due_expected, 2)
        due_deducted = round(due_deducted, 2)
        due_status = mine.get_status_display() if mine else "No record"
        due_paid_date = (
            (mine.approved_at or mine.recorded_at).isoformat()
            if mine and (mine.approved_at or mine.recorded_at)
            else None
        )

    dues_row = MonthlyDues.objects.filter(
        member_id_FK=member, month_covered=month_key
    ).first()
    if mine is None and dues_row is not None:
        due_expected = _f(dues_row.amount)
        paid_like = (dues_row.payment_status or "") in list(Status.ALL_AUDITOR_VERIFIED)
        due_deducted = _f(dues_row.amount) if paid_like else 0.0
        due_outstanding = round(due_expected - due_deducted, 2)
        due_status = dues_row.payment_status or "Unpaid"
        due_paid_date = dues_row.payment_date.isoformat() if dues_row.payment_date else None

    # --- Whole-month total collected for the monthly due (all members) ---
    total_due_collected = 0.0
    due_payer_count = 0
    if monthly_assessment is not None:
        due_items = list(
            monthly_assessment.items.filter(purpose=AssessmentItem.PURPOSE_MONTHLY_DUE)
        )
        if due_items:
            agg = MemberAssessmentAllocation.objects.filter(
                assessment_item_id_FK__in=due_items
            ).aggregate(total=Sum("amount_applied"))
            total_due_collected = _f(agg["total"] or 0)
            due_payer_count = (
                MemberAssessment.objects.filter(assessment_id_FK=monthly_assessment)
                .values("member_id_FK")
                .distinct()
                .count()
            )
        else:
            agg = MemberAssessment.objects.filter(
                assessment_id_FK=monthly_assessment
            ).aggregate(total=Sum("actual_deduction"))
            total_due_collected = _f(agg["total"] or 0)
            due_payer_count = MemberAssessment.objects.filter(
                assessment_id_FK=monthly_assessment
            ).count()
    elif dues_row is not None:
        agg = MonthlyDues.objects.filter(
            month_covered=month_key,
            payment_status__in=list(Status.ALL_AUDITOR_VERIFIED),
        ).aggregate(total=Sum("amount"))
        total_due_collected = _f(agg["total"] or 0)
        due_payer_count = MonthlyDues.objects.filter(
            month_covered=month_key,
            payment_status__in=list(Status.ALL_AUDITOR_VERIFIED),
        ).count()

    # --- Aids for this month ---
    # (a) aid-purpose assessment items (salary-deduction flow — the norm), then
    # (b) OTC aid tracking posts for the same target month not already covered.
    aids: list[dict] = []
    seen_aid_keys: set[str] = set()
    aid_expected_total = 0.0
    aid_paid_total = 0.0

    def _aid_kind_label(purpose: str) -> str:
        if purpose == AssessmentItem.PURPOSE_MEDICAL_AID:
            return "Medical Aid"
        if purpose == AssessmentItem.PURPOSE_DEATH_AID:
            return "Death Aid"
        return "Aid"

    if monthly_assessment is not None:
        aid_items = list(
            monthly_assessment.items.exclude(purpose=AssessmentItem.PURPOSE_MONTHLY_DUE).order_by(
                "priority_order", "item_id_PK"
            )
        )
        for item in aid_items:
            alloc_totals = MemberAssessmentAllocation.objects.filter(
                assessment_item_id_FK=item
            ).aggregate(total=Sum("amount_applied"))
            item_total_collected = _f(alloc_totals["total"] or 0)
            item_member_count = (
                MemberAssessment.objects.filter(assessment_id_FK=monthly_assessment)
                .values("member_id_FK")
                .distinct()
                .count()
            )
            my_required = 0.0
            my_paid = 0.0
            if detail is not None:
                for row in detail["rows"]:
                    if row.get("purpose") == item.label:
                        my_required = _f(row.get("required"))
                        my_paid = _f(row.get("applied"))
                        break
            aid_expected_total += my_required
            aid_paid_total += my_paid
            # Recipient is excluded from paying their own aid: payers =
            # members minus the recipient.
            payer_count = max(0, item_member_count - 1)
            per_member = _f(item.amount)
            seen_aid_keys.add(f"item:{item.item_id_PK}")
            aids.append({
                "key": f"item:{item.item_id_PK}",
                "aid_type": item.purpose,
                "aid_type_label": _aid_kind_label(item.purpose),
                "recipient_name": _item_display_recipient(item),
                "aid_amount": per_member,
                "member_expected": my_required,
                "member_paid": my_paid,
                "member_balance": round(max(0.0, my_required - my_paid), 2),
                "total_collected": round(item_total_collected, 2),
                "expected_total": round(per_member * payer_count, 2),
                "member_count": item_member_count,
                "payer_count": payer_count,
                "formula_note": (
                    f"₱{per_member:,.2f} × {payer_count} payers "
                    f"({item_member_count} members − recipient)"
                ),
            })

    aid_posts = (
        AidTrackingPost.objects.filter(target_month=month_key, is_active=True)
        .prefetch_related("contributions")
        .order_by("aid_type")
    )
    for post in aid_posts:
        # Exact linkage first: a post created for an assessment item (external
        # aids always are) is the SAME collection already listed above —
        # skipping by item PK is immune to recipient spelling differences.
        linked_item_id = getattr(post, "assessment_item_id_FK_id", None)
        if linked_item_id and f"item:{linked_item_id}" in seen_aid_keys:
            continue
        contribution = Contribution.objects.filter(
            member_id_FK=member, aid_tracking_post_id_FK=post
        ).first()

        def _already_listed(label, *candidates) -> bool:
            # Same collection shown via the assessment when any candidate
            # party name matches a listed aid of the same kind. Tolerant of
            # 'SURNAME, Given' (assessment free text) vs raw full_name.
            return any(
                a.get("aid_type_label") == label
                and any(_same_aid_party(a.get("recipient_name"), cand) for cand in candidates)
                for a in aids
            )

        recipient_name = ""
        aid_amount = 0.0
        if post.source_type == "medical_aid" and post.source_id:
            med = MedicalAid.objects.filter(
                medical_aid_id_PK=post.source_id
            ).select_related("member_id_FK").first()
            if med is not None:
                raw_name = (med.member_id_FK.full_name or "").strip() or "Member"
                recipient_name = raw_name
                aid_amount = _f(med.validated_aid_amount or med.requested_amount or 0)
                # Skip posts already represented by an assessment aid item for
                # the same recipient (same collection shown twice otherwise).
                if _already_listed("Medical Aid", raw_name, _formatted_aid_name(raw_name)):
                    continue
        elif post.source_type == "death_aid" and post.source_id:
            death = DeathAid.objects.filter(
                death_aid_id_PK=post.source_id
            ).select_related("member_id_FK").first()
            member_raw = ""
            if death is not None:
                member_raw = (death.member_id_FK.full_name or "").strip()
                recipient_name = (
                    (death.deceased_name or "").strip() or member_raw or "Member"
                )
                aid_amount = _f(death.benefit_amount or 0)
                if _already_listed(
                    "Death Aid",
                    recipient_name,
                    member_raw,
                    _formatted_aid_name(member_raw),
                ):
                    continue
        elif (post.source_type or "") == "external_aid":
            recipient_name = _post_external_display(post)
            aid_amount = _f(post.total_expected or 0)
            post_label = (post.aid_type or "aid").replace("_", " ").title()
            if _already_listed(post_label, recipient_name):
                continue
        else:
            recipient_name = "General Fund"
            aid_amount = _f(post.total_expected or 0)
        if not recipient_name:
            recipient_name = "—"

        qs = Contribution.objects.filter(aid_tracking_post_id_FK=post)
        post_total = _f(qs.aggregate(total=Sum("paid_amount"))["total"] or 0)
        post_members = qs.count()
        # Recipient rows carry EXCLUDED_REQUESTER and are not payers.
        payer_qs = qs.exclude(status=Contribution.STATUS_EXCLUDED_REQUESTER)
        post_payers = payer_qs.count()
        post_expected_total = _f(
            payer_qs.aggregate(total=Sum("expected_amount"))["total"] or 0
        )
        my_expected = _f(contribution.expected_amount) if contribution else 0.0
        my_paid = _f(contribution.paid_amount) if contribution else 0.0
        if contribution is not None and contribution.status == Contribution.STATUS_EXCLUDED_REQUESTER:
            # The recipient does not owe their own aid.
            my_expected = 0.0
            my_paid = 0.0
        aid_expected_total += my_expected
        aid_paid_total += my_paid
        per_member_amt = my_expected or (aid_amount / post_payers if post_payers else aid_amount)
        aids.append({
            "key": f"post:{post.post_id_PK}",
            "aid_type": post.aid_type or "aid",
            "aid_type_label": (post.aid_type or "aid").replace("_", " ").title(),
            "recipient_name": recipient_name,
            "aid_amount": round(my_expected or _f(post.total_expected or 0), 2),
            "member_expected": round(my_expected, 2),
            "member_paid": round(my_paid, 2),
            "member_balance": round(max(0.0, my_expected - my_paid), 2),
            "total_collected": round(post_total, 2),
            "expected_total": round(post_expected_total, 2),
            "member_count": post_members,
            "payer_count": post_payers,
            "formula_note": (
                f"₱{per_member_amt:,.2f} × {post_payers} payers "
                f"({post_members} members − recipient)"
            ),
        })

    aid_outstanding_total = round(max(0.0, aid_expected_total - aid_paid_total), 2)
    month_my_total = round(due_expected + aid_expected_total, 2)
    month_my_paid = round(due_deducted + aid_paid_total, 2)
    month_my_outstanding = round(max(0.0, month_my_total - month_my_paid), 2)

    has_record = (
        mine is not None or dues_row is not None or bool(aids) or monthly_assessment is not None
    )
    if due_status == "No record" and has_record and not aids and not due_expected:
        due_status = "No record"

    # Member-facing DUE drawer / movement-modal names read 'Surname, F.' —
    # applied here, after all de-duplication matching above ran raw.
    for a in aids:
        a["recipient_name"] = short_aid_name(a.get("recipient_name"))

    return {
        "month": month_key,
        "month_label": month_label,
        "has_record": has_record,
        "due": {
            "expected": round(due_expected, 2),
            "deducted": round(due_deducted, 2),
            "outstanding": round(due_outstanding, 2),
            "status": due_status,
            "paid_date": due_paid_date,
            "total_collected": round(total_due_collected, 2),
            "member_count": due_payer_count,
        },
        "aids": aids,
        "totals": {
            "due_expected": round(due_expected, 2),
            "due_paid": round(due_deducted, 2),
            "due_outstanding": round(due_outstanding, 2),
            "total_due_collected": round(total_due_collected, 2),
            "aid_expected": round(aid_expected_total, 2),
            "aid_paid": round(aid_paid_total, 2),
            "aid_outstanding": aid_outstanding_total,
            "month_total_expected": month_my_total,
            "month_total_paid": month_my_paid,
            "month_total_outstanding": month_my_outstanding,
        },
    }


def due_breakdown(member: Member, year: int, month: int) -> dict:
    """Combined due + aid breakdown for a specific month (DUE drawer)."""
    data = _due_month_breakdown(member, year, month)
    return {"ok": True, "scope": "member", **data}


def due_year_breakdown(member: Member, year: int) -> dict:
    """Whole-year DUE drawer payload: 12 monthly breakdowns + year totals."""
    months = [_due_month_breakdown(member, year, m) for m in range(1, 13)]
    year_due_expected = round(sum(m["totals"]["due_expected"] for m in months), 2)
    year_due_paid = round(sum(m["totals"]["due_paid"] for m in months), 2)
    year_aid_expected = round(sum(m["totals"]["aid_expected"] for m in months), 2)
    year_aid_paid = round(sum(m["totals"]["aid_paid"] for m in months), 2)
    year_collected_due = round(sum(m["due"]["total_collected"] for m in months), 2)
    year_collected_aid = round(
        sum(a.get("total_collected", 0.0) for m in months for a in m["aids"]), 2
    )
    return {
        "ok": True,
        "scope": "member",
        "year": year,
        "months": months,
        "year_totals": {
            "due_expected": year_due_expected,
            "due_paid": year_due_paid,
            "due_outstanding": round(max(0.0, year_due_expected - year_due_paid), 2),
            "aid_expected": year_aid_expected,
            "aid_paid": year_aid_paid,
            "aid_outstanding": round(max(0.0, year_aid_expected - year_aid_paid), 2),
            "month_total_expected": round(year_due_expected + year_aid_expected, 2),
            "month_total_paid": round(year_due_paid + year_aid_paid, 2),
            "total_due_collected": year_collected_due,
            "total_aid_collected": year_collected_aid,
            "grand_total_collected": round(year_collected_due + year_collected_aid, 2),
        },
    }


# ---------------------------------------------------------------------------
# Fund movements — aggregated organisation-wide ledger for the member
# FUND Movement card
# ---------------------------------------------------------------------------

_DUES_SOURCE_TYPES = ("monthly_dues",)
_AID_SETASIDE_SOURCE_TYPES = ("aid_setaside_medical", "aid_setaside_death")
_AID_PAYOUT_SOURCE_TYPES = ("medical_aid", "death_aid", "aid_post_payment")

_SOURCE_GROUP_TITLES = {
    "monthly_dues": "Monthly Dues",
    "aid_setaside_medical": "Medical Aid Set-Aside",
    "aid_setaside_death": "Death Aid Set-Aside",
    "membership_fee": "Membership Fee",
    "contribution": "Contribution",
    "payroll_batch": "Payroll Batch",
    "salary_deduction_remittance": "Salary Deduction Remittance",
    "medical_aid": "Medical Aid Released",
    "death_aid": "Death Aid Released",
    "aid_post_payment": "Aid Released",
    "other_transaction": "Other Transaction",
    "manual_adjustment": "Manual Adjustment",
}


def _movement_month_label(year: int | None, month: int | None) -> str:
    if not year or not month:
        return ""
    try:
        return date(year, month, 1).strftime("%B %Y")
    except ValueError:
        return ""


def fund_movements(max_groups: int = 5, scan_rows: int = 1500) -> dict:
    """Aggregate FundTransactions into batch-level movements, newest first.

    Per-member booking rows (e.g. one "Medical aid set-aside — member 56"
    row per payer) collapse into a single movement showing the FULL batch
    total and payer count. Groups key on (source_type, reference_number);
    rows without a reference stay individual.

    Each movement carries enough linkage for the detail modal:
    - dues / aid set-aside groups resolve the assessment year+month, so the
      modal reads the canonical due_breakdown (per-member share, collected
      vs remaining, recipients, which monthly due);
    - aid groups additionally resolve recipient names + post totals;
    - aid payouts resolve the claim recipient + released amount.
    """
    from core_system.models import (
        AidSetAside,
        AidTrackingPost,
        AssessmentItem,
        DeathAid,
        MedicalAid,
        MemberAssessment,
        MonthlyAssessment,
    )

    rows = list(
        FundTransaction.objects.order_by("-recorded_at", "-transaction_id_PK")[:scan_rows]
    )

    # Group preserving newest-first order.
    groups: dict[tuple, dict] = {}
    order: list[tuple] = []
    for t in rows:
        ref = (t.reference_number or "").strip()
        key = (t.source_type, ref) if ref else (t.source_type, f"#txn:{t.transaction_id_PK}")
        g = groups.get(key)
        if g is None:
            g = {"rows": [], "source_type": t.source_type, "reference": ref,
                 "direction": t.direction}
            groups[key] = g
            order.append(key)
        g["rows"].append(t)

    movements: list[dict] = []
    for key in order[:max_groups]:
        g = groups[key]
        grows = g["rows"]
        stype = g["source_type"]
        direction = grows[0].direction
        total = round(sum(_f(r.amount) for r in grows), 2)
        count = len(grows)
        distinct_amounts = {round(_f(r.amount), 2) for r in grows}
        per_member = next(iter(distinct_amounts)) if len(distinct_amounts) == 1 else None
        latest = max((r.recorded_at for r in grows if r.recorded_at), default=None)
        earliest = min((r.recorded_at for r in grows if r.recorded_at), default=None)

        year = month = None
        month_label = ""
        recipients: list[str] = []
        post_summary: dict | None = None
        payout: dict | None = None

        # --- Which monthly due was this collected under? ---
        if stype in _DUES_SOURCE_TYPES + _AID_SETASIDE_SOURCE_TYPES:
            ma_ids = {r.source_id for r in grows if r.source_id}
            months = list(
                MemberAssessment.objects.filter(member_assessment_id_PK__in=ma_ids)
                .exclude(assessment_id_FK__isnull=True)
                .values_list("assessment_id_FK__month", flat=True)
            )
            if months:
                from collections import Counter
                top = Counter(months).most_common(1)[0][0]
                if top:
                    year, month = top.year, top.month
                    month_label = top.strftime("%B %Y")

        # --- Aid groups: who receives it + collected vs remaining ---
        if stype in _AID_SETASIDE_SOURCE_TYPES:
            setasides = list(
                AidSetAside.objects.filter(
                    fund_transaction_id_FK__in=[r.transaction_id_PK for r in grows]
                ).select_related("assessment_item_id_FK", "aid_tracking_post_id_FK")
            )
            names: list[str] = []
            post_ids: list[int] = []
            for s in setasides:
                item = s.assessment_item_id_FK
                if item is not None:
                    label = (item.external_display or item.recipient or "").strip()
                    if label and label not in names:
                        names.append(label)
                pid = s.aid_tracking_post_id_FK_id
                if pid and pid not in post_ids:
                    post_ids.append(pid)
            recipients = names[:3]
            if post_ids:
                posts = list(AidTrackingPost.objects.filter(post_id_PK__in=post_ids))
                collected = round(sum(_f(p.total_collected) for p in posts), 2)
                expected = round(sum(_f(p.total_expected) for p in posts), 2)
                post_summary = {
                    "expected": expected,
                    "collected": collected,
                    "remaining": round(max(0.0, expected - collected), 2),
                    "post_count": len(posts),
                }
                if not recipients:
                    for p in posts:
                        label = _post_recipient_label(p)
                        if label and label not in recipients and len(recipients) < 3:
                            recipients.append(label)
            # Member-facing movement names read 'Surname, F.' — formatted
            # here (display-only), de-duplicated after formatting since two
            # raw spellings can shorten to the same name.
            seen_short: list[str] = []
            for n in recipients:
                short = short_aid_name(n)
                if short not in seen_short:
                    seen_short.append(short)
            recipients = seen_short[:3]

        # --- Aid payouts: who received the released aid ---
        if stype in _AID_PAYOUT_SOURCE_TYPES and grows:
            payout = _payout_detail(grows[0])

        base_title = _SOURCE_GROUP_TITLES.get(stype, (stype or "").replace("_", " ").title())
        if month_label and stype in _DUES_SOURCE_TYPES + _AID_SETASIDE_SOURCE_TYPES:
            title = f"{base_title} — {month_label}"
        elif count > 1:
            title = f"{base_title} — batch of {count}"
        else:
            title = (grows[0].description or base_title).strip() or base_title

        if stype in _DUES_SOURCE_TYPES + _AID_SETASIDE_SOURCE_TYPES:
            kind = "dues" if stype in _DUES_SOURCE_TYPES else "aid"
        elif direction == "outflow" and stype in _AID_PAYOUT_SOURCE_TYPES:
            kind = "payout"
        else:
            kind = "other"

        preview = [
            {
                "date": r.recorded_at.strftime("%b %d, %Y") if r.recorded_at else "",
                "description": (r.description or "").strip(),
                "amount": round(_f(r.amount), 2),
            }
            for r in grows[:8]
        ]

        movements.append({
            "key": f"{stype}|{g['reference'] or grows[0].transaction_id_PK}",
            "kind": kind,
            "direction": direction,
            "source_type": stype,
            "reference": g["reference"],
            "title": title,
            "subtitle": (
                f"{count} member{'s' if count != 1 else ''}"
                if kind in ("dues", "aid") and count > 1 else
                (recipients[0] if recipients else "")
            ),
            "total": total,
            "count": count,
            "per_member": per_member,
            "date": latest.strftime("%Y-%m-%d") if latest else "",
            "date_label": latest.strftime("%b %d, %Y") if latest else "",
            "year": year,
            "month": month,
            "month_label": month_label,
            "recipients": recipients,
            "post_summary": post_summary,
            "payout": payout,
            "preview": preview,
        })

    return {"ok": True, "movements": movements}


def _post_recipient_label(post) -> str:
    """Best-effort recipient name for an aid tracking post (member-safe)."""
    from core_system.models import DeathAid, MedicalAid

    if post.is_external_aid and (post.external_display or "").strip():
        return post.external_display.strip()
    if post.source_type == "medical_aid" and post.source_id:
        med = MedicalAid.objects.filter(
            medical_aid_id_PK=post.source_id
        ).select_related("member_id_FK").first()
        if med is not None and med.member_id_FK:
            return (med.member_id_FK.full_name or "").strip() or "Member"
    if post.source_type == "death_aid" and post.source_id:
        death = DeathAid.objects.filter(
            death_aid_id_PK=post.source_id
        ).select_related("member_id_FK").first()
        if death is not None:
            return ((death.deceased_name or "").strip()
                    or (death.member_id_FK.full_name or "").strip()
                    or "Member")
    return ""


def _payout_detail(t) -> dict | None:
    """Recipient + released amount for an aid outflow row (member-safe)."""
    from core_system.models import AidTrackingPost, DeathAid, MedicalAid

    label = ""
    expected = None
    if t.source_type == "aid_post_payment" and t.source_id:
        post = AidTrackingPost.objects.filter(post_id_PK=t.source_id).first()
        if post is not None:
            label = _post_recipient_label(post)
            expected = _f(post.total_expected)
    elif t.source_type == "medical_aid" and t.source_id:
        med = MedicalAid.objects.filter(
            medical_aid_id_PK=t.source_id
        ).select_related("member_id_FK").first()
        if med is not None:
            label = (med.member_id_FK.full_name or "").strip() if med.member_id_FK else ""
            expected = _f(med.validated_aid_amount or med.requested_amount or 0)
    elif t.source_type == "death_aid" and t.source_id:
        death = DeathAid.objects.filter(
            death_aid_id_PK=t.source_id
        ).select_related("member_id_FK").first()
        if death is not None:
            label = ((death.deceased_name or "").strip()
                     or (death.member_id_FK.full_name or "").strip())
            expected = _f(death.benefit_amount or 0)
    if not label and not expected:
        return None
    return {
        "recipient": short_aid_name(label) if label else "—",
        "released": round(_f(t.amount), 2),
        "expected": round(expected, 2) if expected else None,
        "date": t.recorded_at.strftime("%b %d, %Y") if t.recorded_at else "",
        "reference": (t.reference_number or "").strip(),
    }
