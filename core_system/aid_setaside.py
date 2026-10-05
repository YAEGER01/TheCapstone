"""Earmarked medical/death-aid set-aside booked with a month's deduction.

The President's final approval used to book a member's whole
``MemberAssessment.actual_deduction`` as a single ``monthly_dues`` inflow, so
every peso — including the medical/death-aid portions — read as dues income.
This module splits that one figure at approval time:

    dues portion (non-aid allocations + prior collected + change)
        -> inflow source_type="monthly_dues"
    medical aid portion
        -> inflow source_type="aid_setaside_medical"
    death aid portion
        -> inflow source_type="aid_setaside_death"

The three rows always sum back to ``actual_deduction`` (the amount that was
physically deposited), so bank reconciliation is untouched — only the *label*
on the money changes. Each aid row also writes an :class:`AidSetAside` ledger
row pointing at the recipient's claim, which is what lets the Release Queue
show "set aside against this claim" and draw the earmark down when the
Treasurer releases the payout.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from core_system.models import (
    AidSetAside,
    AidTrackingPost,
    AssessmentItem,
    Contribution,
    FundTransaction,
    Member,
    MemberAssessmentAllocation,
)

CENT = Decimal("0.01")

# source_type of each aid earmark inflow.
SETASIDE_SOURCE_TYPES = ("aid_setaside_medical", "aid_setaside_death")

PURPOSE_TO_SOURCE = {
    AssessmentItem.PURPOSE_MEDICAL_AID: "aid_setaside_medical",
    AssessmentItem.PURPOSE_DEATH_AID: "aid_setaside_death",
}
PURPOSE_TO_AID_TYPE = {
    AssessmentItem.PURPOSE_MEDICAL_AID: "medical_aid",
    AssessmentItem.PURPOSE_DEATH_AID: "death_aid",
}
AID_PURPOSES = tuple(PURPOSE_TO_SOURCE)

# Every source_type the President books for one member_assessment row — the
# guard set for idempotency and the delete set for a return/rejection.
BOOKING_SOURCE_TYPES = ("monthly_dues",) + SETASIDE_SOURCE_TYPES

# finish_status values that still mean "the claim is in flight". Terminal
# states ("approved", "repayment", "rejected") already had their payout, so
# an earmark never points at them.
OPEN_FINISH_STATUSES = (
    "pending_approval",
    "pending_release",
    "pending_auditor",
    "pending_president",
)

_AID_LABEL_BY_PURPOSE = {
    AssessmentItem.PURPOSE_MEDICAL_AID: "Medical aid",
    AssessmentItem.PURPOSE_DEATH_AID: "Death aid",
}


def recipient_name_keys(member) -> set[str]:
    """Case-folded recipient spellings that identify this member.

    Breakdown recipients are typed into the autocomplete as
    ``SURNAME, Given`` (see ``monthly_deduction_views._formatted_name``), but
    a President may just as well paste the plain full name — accept both.
    """
    if member is None:
        return set()
    from core_system.monthly_deduction_views import _formatted_name

    full_name = member.full_name or ""
    keys = set()
    for raw in (full_name, _formatted_name(full_name)):
        key = (raw or "").strip().casefold()
        if key:
            keys.add(key)
    return keys


def recipient_member_lookup() -> dict:
    """Case-folded recipient string -> member PK, for aid-item claim linkage.

    Built once per approval run so linking does not query per member row.
    """
    from core_system.monthly_deduction_views import _formatted_name

    lookup: dict = {}
    for pk, full_name in Member.objects.values_list("member_id_PK", "full_name"):
        for raw in (full_name, _formatted_name(full_name or "")):
            key = (raw or "").strip().casefold()
            if key and key not in lookup:
                lookup[key] = pk
    return lookup


def open_aid_post_for(member_id, aid_type: str):
    """The claim of this member/aid type that is still awaiting release."""
    if not member_id or not aid_type:
        return None
    return (
        AidTrackingPost.objects.filter(
            aid_type=aid_type,
            archive_id_FK__member_id_FK_id=member_id,
            finish_status__in=OPEN_FINISH_STATUSES,
        )
        .order_by("-created_at")
        .first()
    )


def derive_split(member_assessment):
    """``(dues_portion, medical_total, death_total, allocations)`` for one row.

    Single source of truth for how a member's peso divides, shared by the
    approval booking and the read-only reconciliation report so the two can
    never drift apart.
    """
    actual = member_assessment.actual_deduction or Decimal("0.00")

    allocations = list(
        MemberAssessmentAllocation.objects.filter(
            member_assessment_id_FK=member_assessment
        ).select_related("assessment_item_id_FK")
    )

    aid_totals: dict = {}
    for alloc in allocations:
        purpose = alloc.assessment_item_id_FK.purpose
        if purpose in PURPOSE_TO_SOURCE:
            aid_totals[purpose] = aid_totals.get(purpose, Decimal("0.00")) + (
                alloc.amount_applied or Decimal("0.00")
            )

    medical_total = aid_totals.get(AssessmentItem.PURPOSE_MEDICAL_AID, Decimal("0.00")).quantize(CENT)
    death_total = aid_totals.get(AssessmentItem.PURPOSE_DEATH_AID, Decimal("0.00")).quantize(CENT)
    # Everything the member's peso actually paid for that is not an aid
    # earmark: the dues allocation, any prior balance collected and the
    # change/excess — so the three rows sum back to actual_deduction exactly.
    dues_portion = (actual - medical_total - death_total).quantize(CENT)
    if dues_portion < 0:
        dues_portion = Decimal("0.00")
    return dues_portion, medical_total, death_total, allocations


def _refresh_post_total_collected(post) -> None:
    post.total_collected = (
        Contribution.objects.filter(aid_tracking_post_id_FK=post).aggregate(
            collected=Sum("paid_amount")
        )["collected"]
        or Decimal("0.00")
    )
    post.save(update_fields=["total_collected"])


def _sync_contribution_row(post, member_id, amount, pay_date) -> bool:
    """Reflect one payer's earmark total on their Contribution row for the post.

    The per-member Contribution rows the dashboards display are normally only
    written by the manual record-payment flow — so a member who paid their aid
    share through the monthly dues (an earmark) read as NOT_PAID forever. Only
    NOT_PAID rows are touched: RECORDED / PENDING_VERIFICATION belong to the
    manual collection flow (marking them PAID here would skip the Auditor's
    verify inflow), and SKIPPED / EXCLUDED_REQUESTER are deliberate officer
    decisions.
    """
    if post is None or not member_id:
        return False
    contribution = Contribution.objects.filter(
        aid_tracking_post_id_FK=post, member_id_FK_id=member_id
    ).first()
    if contribution is None or contribution.status != Contribution.STATUS_NOT_PAID:
        return False
    expected = (contribution.expected_amount or Decimal("0.00")).quantize(CENT)
    applied = (amount or Decimal("0.00")).quantize(CENT)
    if applied <= 0:
        return False
    paid = min(expected, (contribution.paid_amount or Decimal("0.00")) + applied)
    contribution.paid_amount = paid
    contribution.payment_date = pay_date
    if expected > 0 and paid >= expected:
        contribution.status = Contribution.STATUS_PAID
    contribution.save(update_fields=["paid_amount", "payment_date", "status", "updated_at"])
    return True


def sync_post_contributions_from_setasides(post) -> int:
    """Mark payers' contribution rows paid from the earmarks linked to ``post``.

    Called whenever earmarks get linked to a claim: at booking time (the
    member's dues included an aid allocation for this recipient) and after the
    President's approval creates the post's contribution rows. Idempotent —
    rows already synced or manually managed are left alone.
    """
    if post is None:
        return 0
    totals: dict = {}
    for payer_id, amount in AidSetAside.objects.filter(
        aid_tracking_post_id_FK=post
    ).values_list("member_assessment_id_FK__member_id_FK_id", "amount"):
        totals[payer_id] = totals.get(payer_id, Decimal("0.00")) + (amount or Decimal("0.00"))
    if not totals:
        return 0
    pay_date = timezone.now().date()
    changed = sum(
        1
        for payer_id, amount in totals.items()
        if _sync_contribution_row(post, payer_id, amount, pay_date)
    )
    if changed:
        _refresh_post_total_collected(post)
    return changed


def _revert_contribution_rows(post, removed_amounts: dict) -> None:
    """Undo sync'd paid amounts when a payer's earmarks are deleted.

    A batch return/reject deletes the earmark rows (and their inflows), so the
    paid state the sync wrote must go back too. Recomputed from what is still
    linked to the claim; rows the officers manage themselves are untouched.
    """
    if post is None or not removed_amounts:
        return
    for payer_id in removed_amounts:
        contribution = Contribution.objects.filter(
            aid_tracking_post_id_FK=post, member_id_FK_id=payer_id
        ).first()
        if contribution is None:
            continue
        if contribution.is_manually_overridden or contribution.status not in (
            Contribution.STATUS_PAID,
            Contribution.STATUS_NOT_PAID,
        ):
            continue
        remaining = sum(
            (
                (amount or Decimal("0.00"))
                for amount in AidSetAside.objects.filter(
                    aid_tracking_post_id_FK=post,
                    member_assessment_id_FK__member_id_FK_id=payer_id,
                ).values_list("amount", flat=True)
            ),
            Decimal("0.00"),
        ).quantize(CENT)
        expected = (contribution.expected_amount or Decimal("0.00")).quantize(CENT)
        paid = min(expected, remaining).quantize(CENT)
        if paid == (contribution.paid_amount or Decimal("0.00")).quantize(CENT):
            continue
        contribution.paid_amount = paid
        if expected > 0 and paid >= expected:
            contribution.status = Contribution.STATUS_PAID
        else:
            contribution.status = Contribution.STATUS_NOT_PAID
            contribution.payment_date = None
        contribution.save(update_fields=["paid_amount", "payment_date", "status", "updated_at"])
    _refresh_post_total_collected(post)


def book_member_fund_rows(member_assessment, officer, collection_ref: str, month_label: str, recipient_lookup: dict | None = None, external_post_by_item: dict | None = None):
    """Book one member's deduction split into dues + aid set-aside inflows.

    Idempotent per member-assessment row: returns ``None`` when its rows
    already exist, so a re-approval can never double-book. Wrapped in one
    transaction so the inflow rows and their :class:`AidSetAside` ledger rows
    are always written together.

    External (other-campus) aid items link by assessment ITEM — never by
    member name — so external cash can never attach to a member's claim.
    Pass ``external_post_by_item`` ({item_PK: post}) when the caller already
    ensured external posts; otherwise the earmark stays pooled until the
    post exists and :func:`link_set_asides_to_external_post` picks it up.
    """
    ma_id = member_assessment.member_assessment_id_PK
    if FundTransaction.objects.filter(
        source_type__in=BOOKING_SOURCE_TYPES, source_id=ma_id
    ).exists():
        return None

    actual = member_assessment.actual_deduction or Decimal("0.00")
    if actual <= 0:
        return None

    dues_portion, medical_total, death_total, allocations = derive_split(member_assessment)
    aid_totals = {
        AssessmentItem.PURPOSE_MEDICAL_AID: medical_total,
        AssessmentItem.PURPOSE_DEATH_AID: death_total,
    }

    member_ref = member_assessment.member_id_FK_id
    if recipient_lookup is None:
        recipient_lookup = recipient_member_lookup()

    with transaction.atomic():
        # Re-check inside the transaction: two racing approvals must not both
        # pass the guard above and book the month twice.
        if FundTransaction.objects.filter(
            source_type__in=BOOKING_SOURCE_TYPES, source_id=ma_id
        ).exists():
            return None

        rows_by_source: dict = {}
        if dues_portion > 0:
            rows_by_source["monthly_dues"] = FundTransaction.objects.create(
                direction="inflow",
                amount=dues_portion,
                source_type="monthly_dues",
                source_id=ma_id,
                reference_number=collection_ref,
                description=f"Monthly dues for {month_label} — member {member_ref}",
                recorded_by_user_id_FK=officer,
            )
        for purpose, source_type in PURPOSE_TO_SOURCE.items():
            total = aid_totals.get(purpose, Decimal("0.00")).quantize(CENT)
            if total <= 0:
                continue
            aid_label = _AID_LABEL_BY_PURPOSE[purpose]
            rows_by_source[source_type] = FundTransaction.objects.create(
                direction="inflow",
                amount=total,
                source_type=source_type,
                source_id=ma_id,
                reference_number=collection_ref,
                description=(
                    f"{aid_label} set-aside for {month_label} — member {member_ref}"
                ),
                recorded_by_user_id_FK=officer,
            )

        linked_posts: dict = {}
        for alloc in allocations:
            purpose = alloc.assessment_item_id_FK.purpose
            source_type = PURPOSE_TO_SOURCE.get(purpose)
            if source_type is None:
                continue
            applied = alloc.amount_applied or Decimal("0.00")
            if applied <= 0:
                continue
            fund_row = rows_by_source.get(source_type)
            if fund_row is None:
                continue
            recipient_key = (alloc.assessment_item_id_FK.recipient or "").strip().casefold()
            allocation_item = alloc.assessment_item_id_FK
            if getattr(allocation_item, "recipient_type", "member") == "external":
                # Other-campus cash: link by ITEM, never by member name.
                post = None
                if external_post_by_item is not None:
                    post = external_post_by_item.get(allocation_item.item_id_PK)
                if post is None:
                    post = AidTrackingPost.objects.filter(
                        source_type="external_aid",
                        assessment_item_id_FK=allocation_item,
                        finish_status__in=OPEN_FINISH_STATUSES,
                    ).order_by("-created_at").first()
            else:
                post = open_aid_post_for(
                    recipient_lookup.get(recipient_key),
                    PURPOSE_TO_AID_TYPE[purpose],
                )
            AidSetAside.objects.create(
                member_assessment_id_FK=member_assessment,
                assessment_item_id_FK=alloc.assessment_item_id_FK,
                fund_transaction_id_FK=fund_row,
                aid_tracking_post_id_FK=post,
                aid_type=PURPOSE_TO_AID_TYPE[purpose],
                amount=applied.quantize(CENT),
            )
            if post is not None:
                linked_posts[post.post_id_PK] = post

        # The payer's share of the claim's collection arrived with this dues
        # batch — reflect it on the post's contribution rows so the Aid
        # Tracking dashboards stop reading the member as unpaid.
        for post in linked_posts.values():
            sync_post_contributions_from_setasides(post)

        return rows_by_source


def delete_member_fund_rows(member_assessment_ids) -> None:
    """Undo a member's booking — used when a batch is returned or rejected."""
    member_assessment_ids = list(member_assessment_ids)
    if not member_assessment_ids:
        return
    # Snapshot which claims were being funded by these earmarks so the
    # contribution rows the booking sync marked paid can be reverted too.
    removed: dict = {}
    for post_id, payer_id, amount in AidSetAside.objects.filter(
        member_assessment_id_FK_id__in=member_assessment_ids,
        aid_tracking_post_id_FK__isnull=False,
    ).values_list(
        "aid_tracking_post_id_FK_id",
        "member_assessment_id_FK__member_id_FK_id",
        "amount",
    ):
        payers = removed.setdefault(post_id, {})
        payers[payer_id] = payers.get(payer_id, Decimal("0.00")) + (amount or Decimal("0.00"))
    AidSetAside.objects.filter(
        member_assessment_id_FK_id__in=member_assessment_ids
    ).delete()
    FundTransaction.objects.filter(
        source_type__in=BOOKING_SOURCE_TYPES,
        source_id__in=member_assessment_ids,
    ).delete()
    for post_id, payer_amounts in removed.items():
        post = AidTrackingPost.objects.filter(post_id_PK=post_id).first()
        _revert_contribution_rows(post, payer_amounts)


def link_set_asides_to_post(post, member) -> int:
    """Point every still-unlinked earmark for this claim at its release row.

    Called when the President approves a claim, covering earmarks booked in
    months that predate the claim. Months booked after approval are linked at
    booking time by :func:`book_member_fund_rows`.
    """
    if post is None or member is None:
        return 0
    keys = sorted(recipient_name_keys(member))
    if not keys:
        return 0
    recipient_q = Q()
    for key in keys:
        recipient_q |= Q(assessment_item_id_FK__recipient__iexact=key)
    return AidSetAside.objects.filter(
        aid_type=post.aid_type,
        aid_tracking_post_id_FK__isnull=True,
    ).filter(recipient_q).update(aid_tracking_post_id_FK=post)


def link_set_asides_to_external_post(post, item) -> int:
    """Point still-unlinked earmarks for one external item at its post.

    External linkage is by assessment ITEM (the declared other-campus
    collection), never by recipient name — so a same-name local member can
    never capture another campus's money. Covers earmarks booked before the
    post existed (months approved earlier) as well as re-approval repairs.
    """
    if post is None or item is None:
        return 0
    return AidSetAside.objects.filter(
        aid_type=post.aid_type,
        aid_tracking_post_id_FK__isnull=True,
        assessment_item_id_FK=item,
    ).update(aid_tracking_post_id_FK=post)


def consume_set_asides(post, amount) -> Decimal:
    """Draw down this claim's earmarks oldest-first (FIFO).

    Returns how much of ``amount`` the set-aside covered; the caller books the
    remainder as general-fund outflow as before. Rows left over after the
    payout are released back to the pooled reserve.
    """
    if post is None:
        return Decimal("0.00")
    remaining = Decimal(str(amount)).quantize(CENT)
    if remaining <= 0:
        return Decimal("0.00")

    covered = Decimal("0.00")
    rows = AidSetAside.objects.filter(
        aid_tracking_post_id_FK=post,
        amount_released__lt=F("amount"),
    ).order_by("setaside_id_PK")
    for row in rows:
        if remaining <= 0:
            break
        take = min(row.amount - row.amount_released, remaining)
        if take <= 0:
            continue
        AidSetAside.objects.filter(pk=row.setaside_id_PK).update(
            amount_released=F("amount_released") + take
        )
        covered += take
        remaining -= take

    # Whatever this claim did not need goes back to the pooled reserve so it
    # still shows as available for the next claim of the same aid type.
    AidSetAside.objects.filter(
        aid_tracking_post_id_FK=post, amount_released__lt=F("amount")
    ).update(aid_tracking_post_id_FK=None)

    return covered


def setaside_available_for_post(post) -> Decimal:
    """Aid cash this claim is currently holding.

    Sum of the set-asides booked from members' monthly deduction that are
    still linked to this claim and not yet drawn — the amount a release
    defaults to, because it is literally the money that was collected for
    this recipient.
    """
    if post is None:
        return Decimal("0.00")
    held = AidSetAside.objects.filter(
        aid_tracking_post_id_FK=post
    ).aggregate(held=Sum(F("amount") - F("amount_released")))["held"]
    return (held or Decimal("0.00")).quantize(CENT)


def setaside_totals_by_post() -> dict:
    """``{post_id: {"collected": …, "released": …}}`` for linked earmarks."""
    return {
        row["aid_tracking_post_id_FK_id"]: row
        for row in AidSetAside.objects.filter(
            aid_tracking_post_id_FK__isnull=False
        )
        .values("aid_tracking_post_id_FK_id")
        .annotate(collected=Sum("amount"), released=Sum("amount_released"))
    }


def setaside_reserve_by_aid_type() -> dict:
    """``{aid_type: {"collected": …, "released": …, "available": …}}``.

    Covers every earmark of that type, linked or pooled — the headline
    "Aid Reserve" figure on the Release Queue.
    """
    reserve: dict = {}
    for row in AidSetAside.objects.values("aid_type").annotate(
        collected=Sum("amount"), released=Sum("amount_released")
    ):
        collected = row["collected"] or Decimal("0.00")
        released = row["released"] or Decimal("0.00")
        reserve[row["aid_type"]] = {
            "collected": collected,
            "released": released,
            "available": collected - released,
        }
    return reserve
