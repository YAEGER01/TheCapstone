from __future__ import annotations

from decimal import Decimal

from core_system.constants.policy_constants import (
    get_membership_fee_amount,
    is_retired_member,
)
from core_system.models import (
    AssessmentItem,
    MemberAssessment,
    MemberLedger,
    MembershipFee,
    MonthlyAssessment,
)

MEMBERSHIP_FEE_PAID_STATUSES = frozenset({"Paid", "Full Payment"})


# Transaction types that are one-time fees paid to the association. They are
# recorded in the ledger for history, but must NOT inflate the member's running
# balance: a membership fee buys membership, it is not a fund credit that the
# member can carry as a positive balance.
NON_BALANCE_TRANSACTION_TYPES = frozenset({"membership_fee"})


def member_balance(member) -> Decimal:
    """Return the member's current running ledger balance.

    Credits add to the balance and debits subtract. Entries whose
    ``transaction_type`` is in ``NON_BALANCE_TRANSACTION_TYPES`` are skipped so
    one-time fees never create a balance.
    """
    balance = Decimal("0.00")
    entries = (
        MemberLedger.objects.filter(member_id_FK=member)
        .order_by("recorded_at", "ledger_id_PK")
    )
    for entry in entries:
        if entry.transaction_type in NON_BALANCE_TRANSACTION_TYPES:
            continue
        if entry.direction == "credit":
            balance += entry.amount
        else:
            balance -= entry.amount
    return balance


def _normalize_classification(value) -> str:
    return (value or "Teaching").strip() or "Teaching"


def assessment_item_required_amount(item, classification: str) -> Decimal:
    """Required amount for one assessment item and one classification.

    Retired members owe nothing. This is the same classification-aware rule
    the Treasurer recording flow enforces.
    """
    normalized = _normalize_classification(classification)
    if normalized == "Retired":
        return Decimal("0.00")
    return Decimal(str(item.amount or 0))


def _recorded_member_classification(member_assessment, assessment, member) -> str:
    """Infer the classification in effect when a month was assessed.

    Member records intentionally stay in the system after retirement or a
    classification change. The stored standard assessment reveals whether the
    member owed the full assessment or nothing at all.
    """
    current = _normalize_classification(getattr(member, "member_classification", None))
    if assessment is None:
        return "Retired" if is_retired_member(member) else current

    items = list(assessment.items.all())
    standard = Decimal(str(member_assessment.standard_assessment or 0))
    if standard <= 0:
        return "Retired"
    total = sum((Decimal(str(item.amount or 0)) for item in items), Decimal("0.00"))
    monthly_due = sum(
        (
            Decimal(str(item.amount or 0))
            for item in items
            if item.purpose == AssessmentItem.PURPOSE_MONTHLY_DUE
        ),
        Decimal("0.00"),
    )
    if monthly_due > 0:
        if standard == total:
            return "Teaching"
        for allocation in member_assessment.allocations.all():
            item = allocation.assessment_item_id_FK
            if (
                item.purpose == AssessmentItem.PURPOSE_MONTHLY_DUE
                and Decimal(str(allocation.amount_applied or 0)) > 0
            ):
                return "Teaching"
        return current
    if is_retired_member(member) and Decimal(str(member_assessment.actual_deduction or 0)) > 0:
        return "Teaching"
    return current if not is_retired_member(member) else "Retired"


def build_member_assessment_breakdown(member_assessment) -> dict:
    """Return the member-facing allocation breakdown for one assessed month.

    Required amounts use the classification in effect when the month was
    assessed, so retirement or a later classification change never rewrites
    history. Lines a member was not required to pay are omitted unless money
    was actually applied to them. A prior-month carry-over is a distinct row.
    """
    member = member_assessment.member_id_FK
    assessment = member_assessment.assessment_id_FK
    classification = _recorded_member_classification(member_assessment, assessment, member)
    rows = []
    allocations = (
        member_assessment.allocations.select_related("assessment_item_id_FK").order_by(
            "assessment_item_id_FK__priority_order", "allocation_id_PK"
        )
    )
    included_item_ids = set()
    for allocation in allocations:
        item = allocation.assessment_item_id_FK
        required = assessment_item_required_amount(item, classification)
        applied = Decimal(str(allocation.amount_applied or 0))
        remaining = max(Decimal("0.00"), required - applied)
        if required <= 0 and applied <= 0:
            included_item_ids.add(item.item_id_PK)
            continue
        rows.append(
            {
                "item_id": item.item_id_PK,
                "purpose": item.label,
                "recipient": item.recipient or "",
                "notes": item.notes or "",
                "required": float(required),
                "applied": float(applied),
                "remaining": float(remaining),
                "kind": "item",
            }
        )
        included_item_ids.add(item.item_id_PK)

    # Include every assessment line even if its allocation row is unexpectedly
    # missing, so the member always sees the complete assessed obligation.
    if assessment is not None:
        for item in assessment.items.all().order_by("priority_order", "item_id_PK"):
            if item.item_id_PK in included_item_ids:
                continue
            required = assessment_item_required_amount(item, classification)
            if required <= 0:
                continue
            rows.append(
                {
                    "item_id": item.item_id_PK,
                    "purpose": item.label,
                    "recipient": item.recipient or "",
                    "notes": item.notes or "",
                    "required": float(required),
                    "applied": 0.0,
                    "remaining": float(required),
                    "kind": "item",
                }
            )

    prior = float(member_assessment.prior_outstanding or 0)
    prior_collected = float(member_assessment.prior_outstanding_collected or 0)
    if prior > 0:
        prior_month_rows = (
            member_assessment.prior_months
            if isinstance(member_assessment.prior_months, list)
            else None
        )
        if prior_month_rows:
            # The pooled carry-over keeps its months context: one row per
            # unpaid month it is made of, each settled by its recorded share
            # of the collection. Legacy rows without a snapshot fall through
            # to the single lump-sum row below.
            collected_by_key: dict[str, float] = {}
            if isinstance(member_assessment.prior_collected_months, list):
                for spec in member_assessment.prior_collected_months:
                    if isinstance(spec, dict) and spec.get("key"):
                        key = str(spec["key"])
                        collected_by_key[key] = collected_by_key.get(key, 0.0) + float(
                            spec.get("amount") or 0
                        )
            for spec in prior_month_rows:
                if not isinstance(spec, dict) or not spec.get("key"):
                    continue
                required = round(float(spec.get("amount") or 0), 2)
                if required <= 0:
                    continue
                applied = round(
                    min(collected_by_key.get(str(spec["key"]), 0.0), required), 2
                )
                rows.append(
                    {
                        "purpose": f"Unpaid balance from {spec.get('label') or spec['key']}",
                        "recipient": "",
                        "required": required,
                        "applied": applied,
                        "remaining": round(required - applied, 2),
                        "kind": "prior",
                    }
                )
        else:
            rows.append(
                {
                    "purpose": f"Outstanding from {member_assessment.prior_month or 'previous month'}",
                    "recipient": "",
                    "required": prior,
                    "applied": prior_collected,
                    "remaining": round(prior - prior_collected, 2),
                    "kind": "prior",
                }
            )

    standard = float(member_assessment.standard_assessment or 0)
    actual = float(member_assessment.actual_deduction or 0)
    outstanding = float(member_assessment.outstanding_balance or 0)
    change = float(member_assessment.change_amount or 0)
    if actual <= 0:
        status = "none"
    elif outstanding <= 0:
        status = "full"
    else:
        status = "partial"

    return {
        "month_label": assessment.month_label if assessment is not None else "",
        "classification": classification,
        "rows": rows,
        "standard": standard,
        "actual": actual,
        "change": change,
        "outstanding": outstanding,
        "status": status,
        "total_required": round(standard + prior, 2),
        "total_remaining": round(sum(row["remaining"] for row in rows), 2),
    }


def approved_member_assessments(member):
    """Final-approved salary-deduction months for one member, oldest first."""
    return (
        MemberAssessment.objects.filter(
            member_id_FK=member,
            assessment_id_FK__status=MonthlyAssessment.STATUS_FINAL_APPROVED,
            status=MemberAssessment.STATUS_APPROVED,
        )
        .select_related("assessment_id_FK", "member_id_FK", "approved_by_id_FK")
        .order_by("assessment_id_FK__month", "member_assessment_id_PK")
    )


def member_lifetime_owed(member, exclude_assessment=None, approved_only=True) -> float:
    """True current outstanding across the member's deduction months.

    Each record stores its own month remainder (`outstanding_balance`) plus
    whatever carry-over it took in (`prior_outstanding`). The carry-over is
    not a new obligation — it is an older month's remainder resurfaced — so
    the member's real balance nets it back out:

        owed = SUM(outstanding_balance) - SUM(prior_outstanding)

    This stays correct no matter the order months were recorded in. Taking
    only the latest record's frozen outstanding instead goes stale the moment
    an earlier month is recorded late and collects that same balance as
    prior: the frozen later record keeps reporting it owed forever (phantom
    balance), and the debt could even be collected twice. This helper is the
    single source for "how much does the member still owe".

    `approved_only=True` (default) counts final-approved months — used for
    member-facing balances and collectible priors. Officer working screens
    pass `approved_only=False` so months the Treasurer just recorded (not yet
    final-approved) are included too.
    """
    if approved_only:
        records = approved_member_assessments(member)
    else:
        records = (
            MemberAssessment.objects.filter(member_id_FK=member)
            .select_related("assessment_id_FK")
            .order_by("assessment_id_FK__month", "member_assessment_id_PK")
        )
    if exclude_assessment is not None:
        records = records.exclude(assessment_id_FK=exclude_assessment)
    total = Decimal("0.00")
    for record in records:
        total += Decimal(str(record.outstanding_balance or 0)) - Decimal(
            str(record.prior_outstanding or 0)
        )
    return max(0.0, round(float(total), 2))


def member_deduction_overview(member) -> dict | None:
    """Return overview numbers sourced from final-approved deduction months.

    Returns None when the member has no final-approved deduction record, in
    which case callers keep the legacy MonthlyDues calculation. The
    outstanding balance is the lifetime net across every approved month (see
    member_lifetime_owed), so late/backdated recordings can never leave a
    phantom balance or double-collect a frozen debt. Retired members keep
    their paid history, but their current obligation is zero.
    """
    records = approved_member_assessments(member)
    if not records.exists():
        return None

    latest = records.last()
    outstanding = member_lifetime_owed(member)
    if is_retired_member(member):
        outstanding = 0.0
    return {
        "source": "deduction",
        "months_recorded": records.count(),
        "total_paid": round(
            sum(float(record.actual_deduction or 0) for record in records), 2
        ),
        "outstanding_balance": outstanding,
        "latest_month": latest.assessment_id_FK.month_label,
    }


def member_unpaid_months(member) -> list[dict]:
    """Months (oldest first) making up the member's pooled unpaid balance.

    Member-facing twin of the Treasurer-side pool derivation
    (`_unpaid_months_by_member`), restricted to final-approved months so the
    dashboard only shows obligations the President has approved. A month's own
    remainder is `outstanding_balance - prior_outstanding +
    prior_outstanding_collected`; collections recorded against the carry-over
    settle the exact months frozen in the paying row's prior_collected_months
    snapshot (legacy rows without a snapshot sweep oldest-first). The returned
    amounts sum to member_lifetime_owed(member), so the Unpaid Balance shown
    with its months context always agrees with the Overview number.
    """
    cent = Decimal("0.01")
    open_months: list[dict] = []
    for record in approved_member_assessments(member):
        pay = Decimal(str(record.prior_outstanding_collected or 0))
        if pay > 0:
            placed = Decimal("0.00")
            attributed = (
                record.prior_collected_months
                if isinstance(record.prior_collected_months, list)
                else None
            )
            if attributed:
                specs = {
                    str(spec.get("key")): spec
                    for spec in attributed
                    if isinstance(spec, dict)
                }
                for entry in open_months:
                    if pay - placed <= 0:
                        break
                    spec = specs.get(str(entry["key"]))
                    if not spec:
                        continue
                    take = min(
                        Decimal(str(spec.get("amount") or 0)),
                        Decimal(str(entry["amount"])),
                        pay - placed,
                    ).quantize(cent)
                    if take > 0:
                        entry["amount"] = float(
                            (Decimal(str(entry["amount"])) - take).quantize(cent)
                        )
                        placed = (placed + take).quantize(cent)
            leftover = pay - placed
            if leftover > 0:
                for entry in open_months:
                    if leftover <= 0:
                        break
                    applied = min(leftover, Decimal(str(entry["amount"])))
                    entry["amount"] = float(
                        (Decimal(str(entry["amount"])) - applied).quantize(cent)
                    )
                    leftover = (leftover - applied).quantize(cent)
            open_months = [e for e in open_months if e["amount"] > 0.004]

        own = (
            Decimal(str(record.outstanding_balance or 0))
            - Decimal(str(record.prior_outstanding or 0))
            + Decimal(str(record.prior_outstanding_collected or 0))
        ).quantize(cent)
        if own <= 0:
            continue
        assessment = record.assessment_id_FK
        open_months.append({
            "key": assessment.month.strftime("%Y-%m"),
            "label": assessment.month_label,
            "amount": float(own),
        })
    return [e for e in open_months if e["amount"] > 0.004]


def membership_fee_summary(member) -> dict | None:
    """Separate one-time membership-fee status from monthly deductions.

    Only NEW members have a membership-fee record; OLD/existing members were
    registered without one. Returns None when there is no fee to display.
    """
    latest = (
        MembershipFee.objects.filter(member_id_FK=member)
        .order_by("-payment_date", "-fee_id_PK")
        .first()
    )
    if latest is None:
        return None
    required_amount = float(get_membership_fee_amount())
    status = latest.payment_status or ""
    return {
        "status": status or "Unpaid",
        "paid": status in MEMBERSHIP_FEE_PAID_STATUSES,
        "amount": float(latest.amount or 0),
        "required_amount": required_amount,
        "payment_date": latest.payment_date.isoformat() if latest.payment_date else "",
        "payment_method": latest.payment_method or "",
        "reference": latest.receipt_number or latest.deposit_reference or "",
    }
