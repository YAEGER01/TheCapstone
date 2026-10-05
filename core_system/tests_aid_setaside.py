"""Earmarked aid set-aside: split booking, claim linkage, FIFO release.

The President's final approval books a member's deduction as separate inflows
(dues + medical + death set-aside) that always sum back to the amount actually
withheld. These tests pin that invariant down, plus the machinery around it:
idempotency, cleanup on return/rejection, back-linking to a claim, and FIFO
consumption when the Treasurer releases a payout.
"""

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from core_system.aid_setaside import (
    BOOKING_SOURCE_TYPES,
    PURPOSE_TO_AID_TYPE,
    SETASIDE_SOURCE_TYPES,
    book_member_fund_rows,
    consume_set_asides,
    delete_member_fund_rows,
    derive_split,
    link_set_asides_to_post,
    open_aid_post_for,
    recipient_member_lookup,
    setaside_available_for_post,
    setaside_reserve_by_aid_type,
    setaside_totals_by_post,
    sync_post_contributions_from_setasides,
)
from core_system.auth_utils import create_access_session
from core_system.services.mfa_service import generate_otp
from core_system.models import (
    AidSetAside,
    AidTrackingPost,
    AssessmentItem,
    Contribution,
    FundTransaction,
    GlobalAuditTrail,
    Member,
    MemberAssessment,
    MemberAssessmentAllocation,
    MonthlyAssessment,
    OfficerUser,
    TransactionArchive,
)


def _officer(username="pres_split"):
    return OfficerUser.objects.create(
        full_name="President Split Test",
        username=username,
        password_hash="unused",
        role="President",
        account_status="Active",
    )


def _member(full_name, employee_id):
    return Member.objects.create(
        full_name=full_name,
        employee_id=employee_id,
        department="Finance",
        position="Staff",
        membership_status="Permanent",
        employment_status="Active",
        member_type="Member",
        email=f"{employee_id.lower()}@test.local",
        date_joined=timezone.now().date(),
    )


class AidSetAsideSplitTests(TestCase):
    """Approval-time split of one member's deduction into earmarked inflows."""

    def setUp(self):
        self.officer = _officer()
        self.member = _member("Josephine C. Cristobal", "EMP-SA-001")
        self.assessment = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1), total_amount=Decimal("500.00")
        )
        self.dues_item = AssessmentItem.objects.create(
            assessment_id_FK=self.assessment,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("200.00"),
            priority_order=1,
        )
        self.med_item = AssessmentItem.objects.create(
            assessment_id_FK=self.assessment,
            purpose=AssessmentItem.PURPOSE_MEDICAL_AID,
            amount=Decimal("100.00"),
            # Real keystrokes: the autocomplete stores "SURNAME, Given".
            recipient="CRISTOBAL, Josephine C.",
            priority_order=2,
        )
        self.death_item = AssessmentItem.objects.create(
            assessment_id_FK=self.assessment,
            purpose=AssessmentItem.PURPOSE_DEATH_AID,
            amount=Decimal("250.00"),
            recipient="CRISTOBAL, Josephine C.",
            priority_order=3,
        )

    def _ma(self, actual, dues_applied, med_applied, death_applied):
        ma = MemberAssessment.objects.create(
            assessment_id_FK=self.assessment,
            member_id_FK=self.member,
            standard_assessment=Decimal("550.00"),
            actual_deduction=Decimal(actual),
            status=MemberAssessment.STATUS_APPROVED,
        )
        for item, applied in (
            (self.dues_item, dues_applied),
            (self.med_item, med_applied),
            (self.death_item, death_applied),
        ):
            MemberAssessmentAllocation.objects.create(
                member_assessment_id_FK=ma,
                assessment_item_id_FK=item,
                amount_applied=Decimal(applied),
                amount_remaining=item.amount - Decimal(applied),
            )
        return ma

    def _rows(self, ma):
        return {
            r.source_type: r
            for r in FundTransaction.objects.filter(
                source_type__in=BOOKING_SOURCE_TYPES,
                source_id=ma.member_assessment_id_PK,
            )
        }

    def test_split_rows_sum_back_to_actual_deduction(self):
        ma = self._ma("500.00", "200.00", "100.00", "200.00")

        rows = book_member_fund_rows(ma, self.officer, "COL-00001", "September 2026")

        self.assertEqual(set(rows), set(BOOKING_SOURCE_TYPES))
        self.assertEqual(rows["monthly_dues"].amount, Decimal("200.00"))
        self.assertEqual(rows["aid_setaside_medical"].amount, Decimal("100.00"))
        self.assertEqual(rows["aid_setaside_death"].amount, Decimal("200.00"))
        self.assertEqual(
            sum((r.amount for r in rows.values()), Decimal("0.00")),
            ma.actual_deduction,
        )
        for row in rows.values():
            self.assertEqual(row.direction, "inflow")
            self.assertIn("COL-00001", row.reference_number or "")
            self.assertIn("September 2026", row.description)

    def test_partial_deduction_fills_aid_before_dues(self):
        # Only ₱150 was withheld against a ₱550 breakdown: the low-priority
        # dues line absorbs the shortfall first.
        ma = self._ma("150.00", "50.00", "100.00", "0.00")
        dues, medical, death, _ = derive_split(ma)

        self.assertEqual(dues, Decimal("50.00"))
        self.assertEqual(medical, Decimal("100.00"))
        self.assertEqual(death, Decimal("0.00"))
        self.assertEqual(dues + medical + death, ma.actual_deduction)

    def test_dues_portion_is_never_negative(self):
        # Over-stated allocations (the allocator never writes these) must not
        # produce a negative dues row.
        ma = self._ma("150.00", "0.00", "100.00", "100.00")
        dues, medical, death, _ = derive_split(ma)

        self.assertEqual(dues, Decimal("0.00"))
        self.assertEqual(medical, Decimal("100.00"))
        self.assertEqual(death, Decimal("100.00"))
        self.assertGreaterEqual(dues, Decimal("0.00"))

    def test_booking_is_idempotent(self):
        ma = self._ma("500.00", "200.00", "100.00", "200.00")
        book_member_fund_rows(ma, self.officer, "COL-00001", "September 2026")
        before = FundTransaction.objects.filter(
            source_type__in=BOOKING_SOURCE_TYPES, source_id=ma.member_assessment_id_PK
        ).count()
        self.assertEqual(before, 3)

        second = book_member_fund_rows(
            ma, self.officer, "COL-00001", "September 2026"
        )

        self.assertIsNone(second)
        self.assertEqual(
            FundTransaction.objects.filter(
                source_type__in=BOOKING_SOURCE_TYPES,
                source_id=ma.member_assessment_id_PK,
            ).count(),
            before,
        )
        self.assertEqual(AidSetAside.objects.count(), 2)

    def test_zero_deduction_books_nothing(self):
        ma = self._ma("0.00", "0.00", "0.00", "0.00")
        self.assertIsNone(
            book_member_fund_rows(ma, self.officer, "COL-00001", "September 2026")
        )
        self.assertEqual(FundTransaction.objects.count(), 0)

    def test_return_reject_cleanup_removes_every_earmark(self):
        ma = self._ma("500.00", "200.00", "100.00", "200.00")
        book_member_fund_rows(ma, self.officer, "COL-00001", "September 2026")
        self.assertEqual(
            FundTransaction.objects.filter(
                source_type__in=BOOKING_SOURCE_TYPES
            ).count(),
            3,
        )

        delete_member_fund_rows([ma.member_assessment_id_PK])

        self.assertFalse(
            FundTransaction.objects.filter(
                source_type__in=BOOKING_SOURCE_TYPES
            ).exists()
        )
        self.assertFalse(AidSetAside.objects.exists())


class AidSetAsideClaimLinkTests(TestCase):
    """Earmarks find the recipient's open claim and draw down FIFO on release."""

    def setUp(self):
        self.officer = _officer("pres_link")
        self.member = _member("Josephine C. Cristobal", "EMP-SA-101")
        self.assessment = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1), total_amount=Decimal("300.00")
        )
        self.med_item = AssessmentItem.objects.create(
            assessment_id_FK=self.assessment,
            purpose=AssessmentItem.PURPOSE_MEDICAL_AID,
            amount=Decimal("100.00"),
            recipient="CRISTOBAL, Josephine C.",
            priority_order=1,
        )
        self.ma = MemberAssessment.objects.create(
            assessment_id_FK=self.assessment,
            member_id_FK=self.member,
            standard_assessment=Decimal("300.00"),
            actual_deduction=Decimal("300.00"),
            status=MemberAssessment.STATUS_APPROVED,
        )
        MemberAssessmentAllocation.objects.create(
            member_assessment_id_FK=self.ma,
            assessment_item_id_FK=self.med_item,
            amount_applied=Decimal("100.00"),
            amount_remaining=Decimal("0.00"),
        )

        self.archive = TransactionArchive.objects.create(
            transaction_type="medical_aid",
            record_id=1,
            member_id_FK=self.member,
            member_name=self.member.full_name,
            amount=Decimal("30000"),
            validated_amount=Decimal("30000"),
            status="Approved",
            verified_at=timezone.now(),
        )
        self.post = AidTrackingPost.objects.create(
            archive_id_FK=self.archive,
            aid_type="medical_aid",
            target_month="2026-09",
            finish_status="pending_release",
        )

    def _book(self):
        return book_member_fund_rows(
            self.ma, self.officer, "COL-00002", "September 2026"
        )

    def test_booker_links_earmark_to_the_recipients_open_claim(self):
        self._book()

        setaside = AidSetAside.objects.get(assessment_item_id_FK=self.med_item)
        self.assertEqual(setaside.aid_type, "medical_aid")
        self.assertEqual(setaside.amount, Decimal("100.00"))
        self.assertEqual(setaside.aid_tracking_post_id_FK_id, self.post.post_id_PK)
        self.assertEqual(setaside.amount_available, Decimal("100.00"))

    def test_booker_leaves_earmark_unlinked_when_no_claim_exists(self):
        self.post.finish_status = "repayment"
        self.post.save(update_fields=["finish_status"])

        self._book()

        setaside = AidSetAside.objects.get(assessment_item_id_FK=self.med_item)
        self.assertIsNone(setaside.aid_tracking_post_id_FK_id)
        # Still visible to the pooled reserve.
        reserve = setaside_reserve_by_aid_type()
        self.assertEqual(reserve["medical_aid"]["available"], Decimal("100.00"))

    def test_link_set_asides_backfills_earmarks_booked_before_the_claim(self):
        # Booked while no claim was in flight for this recipient.
        self.post.finish_status = "repayment"
        self.post.save(update_fields=["finish_status"])
        self._book()
        setaside = AidSetAside.objects.get(assessment_item_id_FK=self.med_item)
        self.assertIsNone(setaside.aid_tracking_post_id_FK_id)
        self.assertIsNone(open_aid_post_for(self.member.member_id_PK, "medical_aid"))

        # The claim opens later: the President's approval back-links the rows
        # that were booked before it existed.
        self.post.finish_status = "pending_release"
        self.post.save(update_fields=["finish_status"])
        linked = link_set_asides_to_post(self.post, self.member)

        self.assertEqual(linked, 1)
        setaside.refresh_from_db()
        self.assertEqual(setaside.aid_tracking_post_id_FK_id, self.post.post_id_PK)

    def test_release_consumes_linked_earmarks_oldest_first(self):
        self._book()
        # Two more earmarks for the same recipient so FIFO order is observable.
        for index, amount in enumerate(("60.00", "40.00"), start=2):
            item = AssessmentItem.objects.create(
                assessment_id_FK=self.assessment,
                purpose=AssessmentItem.PURPOSE_MEDICAL_AID,
                amount=Decimal(amount),
                recipient="CRISTOBAL, Josephine C.",
                priority_order=9,
            )
            ma = MemberAssessment.objects.create(
                assessment_id_FK=self.assessment,
                member_id_FK=_member(f"Earmark Payer {index}", f"EMP-SA-1{index}0"),
                standard_assessment=Decimal(amount),
                actual_deduction=Decimal(amount),
                status=MemberAssessment.STATUS_APPROVED,
            )
            MemberAssessmentAllocation.objects.create(
                member_assessment_id_FK=ma,
                assessment_item_id_FK=item,
                amount_applied=Decimal(amount),
                amount_remaining=Decimal("0.00"),
            )
            book_member_fund_rows(ma, self.officer, "COL-00003", "September 2026")

        rows = list(
            AidSetAside.objects.filter(aid_tracking_post_id_FK=self.post).order_by(
                "setaside_id_PK"
            )
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            [r.amount for r in rows],
            [Decimal("100.00"), Decimal("60.00"), Decimal("40.00")],
        )
        earmark_ids = [r.setaside_id_PK for r in rows]

        covered = consume_set_asides(self.post, Decimal("130.00"))

        self.assertEqual(covered, Decimal("130.00"))
        after = {
            r.setaside_id_PK: r
            for r in AidSetAside.objects.filter(setaside_id_PK__in=earmark_ids)
        }
        # Oldest first: the first earmark is drained, the second is part-drawn,
        # and the third is untouched.
        self.assertEqual(after[earmark_ids[0]].amount_released, Decimal("100.00"))
        self.assertEqual(after[earmark_ids[1]].amount_released, Decimal("30.00"))
        self.assertEqual(after[earmark_ids[2]].amount_released, Decimal("0.00"))
        # Anything this claim did not need is back in the pooled reserve.
        reserve = setaside_reserve_by_aid_type()
        self.assertEqual(reserve["medical_aid"]["released"], Decimal("130.00"))
        self.assertEqual(reserve["medical_aid"]["available"], Decimal("70.00"))

    def test_release_returns_unneeded_earmarks_to_the_pooled_reserve(self):
        self._book()
        self.assertEqual(
            AidSetAside.objects.filter(
                aid_tracking_post_id_FK=self.post
            ).count(),
            1,
        )

        covered = consume_set_asides(self.post, Decimal("40.00"))

        self.assertEqual(covered, Decimal("40.00"))
        row = AidSetAside.objects.get(assessment_item_id_FK=self.med_item)
        self.assertEqual(row.amount_released, Decimal("40.00"))
        # The ₱60 this claim did not need is free for the next claim.
        self.assertIsNone(row.aid_tracking_post_id_FK_id)
        reserve = setaside_reserve_by_aid_type()
        self.assertEqual(reserve["medical_aid"]["collected"], Decimal("100.00"))
        self.assertEqual(reserve["medical_aid"]["released"], Decimal("40.00"))
        self.assertEqual(reserve["medical_aid"]["available"], Decimal("60.00"))

    def test_release_short_of_the_setaside_reports_only_what_it_covered(self):
        self._book()
        covered = consume_set_asides(self.post, Decimal("500.00"))
        self.assertEqual(covered, Decimal("100.00"))
        reserve = setaside_reserve_by_aid_type()
        self.assertEqual(reserve["medical_aid"]["available"], Decimal("0.00"))

    def test_reserve_ignores_post_linkage_for_the_headline_total(self):
        self._book()
        AidSetAside.objects.filter(assessment_item_id_FK=self.med_item).update(
            aid_tracking_post_id_FK=None
        )
        reserve = setaside_reserve_by_aid_type()
        self.assertEqual(reserve["medical_aid"]["collected"], Decimal("100.00"))
        self.assertEqual(
            setaside_totals_by_post(),
            {},
        )


class ContributionSyncTests(TestCase):
    """Earmark booking marks the payer's contribution row paid.

    The per-member Contribution rows the Aid Tracking dashboards display are
    normally only written by the manual record-payment flow, so a member who
    paid their aid share through the monthly dues read as NOT_PAID even after
    the claim was paid and released. Booking an earmark linked to a claim now
    syncs the payer's row, and a batch return/reject undoes it.
    """

    def setUp(self):
        self.officer = _officer("pres_sync")
        self.member = _member("Josephine C. Cristobal", "EMP-CS-001")
        self.assessment = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1), total_amount=Decimal("300.00")
        )
        self.med_item = AssessmentItem.objects.create(
            assessment_id_FK=self.assessment,
            purpose=AssessmentItem.PURPOSE_MEDICAL_AID,
            amount=Decimal("100.00"),
            recipient="CRISTOBAL, Josephine C.",
            priority_order=1,
        )
        self.ma = MemberAssessment.objects.create(
            assessment_id_FK=self.assessment,
            member_id_FK=self.member,
            standard_assessment=Decimal("300.00"),
            actual_deduction=Decimal("300.00"),
            status=MemberAssessment.STATUS_APPROVED,
        )
        MemberAssessmentAllocation.objects.create(
            member_assessment_id_FK=self.ma,
            assessment_item_id_FK=self.med_item,
            amount_applied=Decimal("100.00"),
            amount_remaining=Decimal("0.00"),
        )
        self.archive = TransactionArchive.objects.create(
            transaction_type="medical_aid",
            record_id=1,
            member_id_FK=self.member,
            member_name=self.member.full_name,
            amount=Decimal("30000"),
            validated_amount=Decimal("30000"),
            status="Approved",
            verified_at=timezone.now(),
        )
        self.post = AidTrackingPost.objects.create(
            archive_id_FK=self.archive,
            aid_type="medical_aid",
            target_month="2026-09",
            finish_status="pending_release",
            total_expected=Decimal("100.00"),
        )

    def _contribution(self, member, expected="100.00", status=Contribution.STATUS_NOT_PAID):
        return Contribution.objects.create(
            aid_tracking_post_id_FK=self.post,
            member_id_FK=member,
            expected_amount=Decimal(expected),
            paid_amount=0,
            status=status,
        )

    def test_booking_marks_the_paying_members_contribution_paid(self):
        contribution = self._contribution(self.member)

        book_member_fund_rows(self.ma, self.officer, "COL-00021", "September 2026")

        contribution.refresh_from_db()
        self.assertEqual(contribution.status, Contribution.STATUS_PAID)
        self.assertEqual(contribution.paid_amount, Decimal("100.00"))
        self.assertEqual(contribution.payment_date, timezone.now().date())
        self.post.refresh_from_db()
        self.assertEqual(self.post.total_collected, Decimal("100.00"))

    def test_partial_earmark_records_partial_payment_and_stays_unpaid(self):
        MemberAssessmentAllocation.objects.all().update(amount_applied=Decimal("40.00"))
        contribution = self._contribution(self.member, expected="500.00")

        book_member_fund_rows(self.ma, self.officer, "COL-00022", "September 2026")

        contribution.refresh_from_db()
        self.assertEqual(contribution.status, Contribution.STATUS_NOT_PAID)
        self.assertEqual(contribution.paid_amount, Decimal("40.00"))
        self.post.refresh_from_db()
        self.assertEqual(self.post.total_collected, Decimal("40.00"))

    def test_sync_leaves_manually_managed_rows_alone(self):
        skipped = self._contribution(self.member, status=Contribution.STATUS_SKIPPED)
        recorded = self._contribution(
            _member("Manual Payer", "EMP-CS-002"),
            status=Contribution.STATUS_RECORDED,
        )
        excluded = self._contribution(
            _member("Requesting Member", "EMP-CS-003"),
            status=Contribution.STATUS_EXCLUDED_REQUESTER,
        )

        book_member_fund_rows(self.ma, self.officer, "COL-00023", "September 2026")

        for row in (skipped, recorded, excluded):
            row.refresh_from_db()
        self.assertEqual(skipped.status, Contribution.STATUS_SKIPPED)
        self.assertEqual(skipped.paid_amount, Decimal("0.00"))
        self.assertEqual(recorded.status, Contribution.STATUS_RECORDED)
        self.assertEqual(recorded.paid_amount, Decimal("0.00"))
        self.assertEqual(excluded.status, Contribution.STATUS_EXCLUDED_REQUESTER)

    def test_sync_is_idempotent(self):
        self._contribution(self.member)
        book_member_fund_rows(self.ma, self.officer, "COL-00024", "September 2026")

        changed = sync_post_contributions_from_setasides(self.post)

        self.assertEqual(changed, 0)
        self.assertEqual(
            Contribution.objects.get(
                aid_tracking_post_id_FK=self.post, member_id_FK=self.member
            ).status,
            Contribution.STATUS_PAID,
        )

    def test_claim_approval_syncs_contributions_created_after_the_link(self):
        # The earmark was booked before the claim existed: closed post, so the
        # booking leaves it in the pooled reserve.
        self.post.finish_status = "repayment"
        self.post.save(update_fields=["finish_status"])
        book_member_fund_rows(self.ma, self.officer, "COL-00028", "September 2026")
        self.assertIsNone(
            AidSetAside.objects.get(assessment_item_id_FK=self.med_item).aid_tracking_post_id_FK_id
        )

        # The President's approval opens the claim, back-links the earmark and
        # bulk-creates the contribution rows — the sync only has something to
        # mark once those rows exist (as the view now does).
        self.post.finish_status = "pending_release"
        self.post.save(update_fields=["finish_status"])
        linked = link_set_asides_to_post(self.post, self.member)
        self.assertEqual(linked, 1)
        contribution = self._contribution(self.member)

        changed = sync_post_contributions_from_setasides(self.post)

        self.assertEqual(changed, 1)
        contribution.refresh_from_db()
        self.assertEqual(contribution.status, Contribution.STATUS_PAID)
        self.assertEqual(contribution.paid_amount, Decimal("100.00"))

    def test_return_reject_cleanup_reverts_the_synced_payment(self):
        contribution = self._contribution(self.member)
        book_member_fund_rows(self.ma, self.officer, "COL-00025", "September 2026")
        contribution.refresh_from_db()
        self.assertEqual(contribution.status, Contribution.STATUS_PAID)

        delete_member_fund_rows([self.ma.member_assessment_id_PK])

        contribution.refresh_from_db()
        self.assertEqual(contribution.status, Contribution.STATUS_NOT_PAID)
        self.assertEqual(contribution.paid_amount, Decimal("0.00"))
        self.assertIsNone(contribution.payment_date)
        self.post.refresh_from_db()
        self.assertEqual(self.post.total_collected, Decimal("0.00"))

    def test_revert_keeps_what_other_batches_still_cover(self):
        # The payer funded the claim twice (two booked batches); returning one
        # batch must only claw back that batch's share.
        contribution = self._contribution(self.member, expected="150.00")
        book_member_fund_rows(self.ma, self.officer, "COL-00026", "September 2026")

        second_assessment = MonthlyAssessment.objects.create(
            month=date(2026, 10, 1), total_amount=Decimal("50.00")
        )
        second_item = AssessmentItem.objects.create(
            assessment_id_FK=second_assessment,
            purpose=AssessmentItem.PURPOSE_MEDICAL_AID,
            amount=Decimal("50.00"),
            recipient="CRISTOBAL, Josephine C.",
            priority_order=2,
        )
        second_ma = MemberAssessment.objects.create(
            assessment_id_FK=second_assessment,
            member_id_FK=self.member,
            standard_assessment=Decimal("50.00"),
            actual_deduction=Decimal("50.00"),
            status=MemberAssessment.STATUS_APPROVED,
        )
        MemberAssessmentAllocation.objects.create(
            member_assessment_id_FK=second_ma,
            assessment_item_id_FK=second_item,
            amount_applied=Decimal("50.00"),
            amount_remaining=Decimal("0.00"),
        )
        book_member_fund_rows(second_ma, self.officer, "COL-00027", "September 2026")
        contribution.refresh_from_db()
        self.assertEqual(contribution.status, Contribution.STATUS_PAID)
        self.assertEqual(contribution.paid_amount, Decimal("150.00"))

        delete_member_fund_rows([second_ma.member_assessment_id_PK])

        contribution.refresh_from_db()
        self.assertEqual(contribution.status, Contribution.STATUS_NOT_PAID)
        self.assertEqual(contribution.paid_amount, Decimal("100.00"))
        self.post.refresh_from_db()
        self.assertEqual(self.post.total_collected, Decimal("100.00"))


class ReconcileAidSetAsidesCommandTests(TestCase):
    """The reconciliation report is read-only and classifies legacy bookings."""

    def setUp(self):
        self.officer = _officer("pres_recon")
        self.member = _member("Recon Member One", "EMP-RC-001")
        self.assessment = MonthlyAssessment.objects.create(
            month=date(2026, 8, 1), total_amount=Decimal("300.00")
        )
        self.med_item = AssessmentItem.objects.create(
            assessment_id_FK=self.assessment,
            purpose=AssessmentItem.PURPOSE_MEDICAL_AID,
            amount=Decimal("100.00"),
            recipient="RECON MEMBER, One",
            priority_order=1,
        )
        self.dues_item = AssessmentItem.objects.create(
            assessment_id_FK=self.assessment,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("200.00"),
            priority_order=2,
        )
        self.ma = MemberAssessment.objects.create(
            assessment_id_FK=self.assessment,
            member_id_FK=self.member,
            standard_assessment=Decimal("300.00"),
            actual_deduction=Decimal("300.00"),
            status=MemberAssessment.STATUS_APPROVED,
        )
        MemberAssessmentAllocation.objects.create(
            member_assessment_id_FK=self.ma,
            assessment_item_id_FK=self.dues_item,
            amount_applied=Decimal("200.00"),
            amount_remaining=Decimal("0.00"),
        )
        MemberAssessmentAllocation.objects.create(
            member_assessment_id_FK=self.ma,
            assessment_item_id_FK=self.med_item,
            amount_applied=Decimal("100.00"),
            amount_remaining=Decimal("0.00"),
        )

    def _run(self, **kwargs):
        out = StringIO()
        call_command("reconcile_aid_setasides", stdout=out, **kwargs)
        return out.getvalue()

    def test_legacy_single_row_is_reported_without_writing(self):
        # Pre-split month: the whole figure sits on one monthly_dues row.
        FundTransaction.objects.create(
            direction="inflow",
            amount=Decimal("300.00"),
            source_type="monthly_dues",
            source_id=self.ma.member_assessment_id_PK,
            reference_number="COL-00009",
            description="Monthly dues for August 2026 — member 1",
            recorded_by_user_id_FK=self.officer,
        )
        before_tx = FundTransaction.objects.count()
        before_sa = AidSetAside.objects.count()

        output = self._run(month=["2026-08"])

        self.assertIn("LEGACY", output)
        self.assertIn("100.00", output)
        self.assertIn("aid portion currently booked as monthly_dues: 100.00", output)
        # Read-only: nothing new was written.
        self.assertEqual(FundTransaction.objects.count(), before_tx)
        self.assertEqual(AidSetAside.objects.count(), before_sa)

    def test_correct_split_is_reported_as_ok(self):
        book_member_fund_rows(
            self.ma, self.officer, "COL-00010", "August 2026"
        )
        before_tx = FundTransaction.objects.count()

        output = self._run(show_ok=True, month=["2026-08"])

        self.assertIn("OK", output)
        self.assertIn("mismatch=0", output)
        self.assertNotIn("mismatch=1", output)
        self.assertEqual(FundTransaction.objects.count(), before_tx)

    def test_unapproved_month_is_skipped(self):
        self.ma.status = MemberAssessment.STATUS_PENDING
        self.ma.save(update_fields=["status"])

        output = self._run(month=["2026-08"])

        self.assertIn("rows=0", output)

    def test_json_output_carries_the_derived_split(self):
        import json as _json

        out = StringIO()
        call_command("reconcile_aid_setasides", as_json=True, month=["2026-08"], stdout=out)
        payload = _json.loads(out.getvalue())

        self.assertEqual(payload["summary"]["rows"], 1)
        row = payload["rows"][0]
        self.assertEqual(row["status"], "MISSING")
        self.assertEqual(row["derived"]["aid_setaside_medical"], "100.00")
        self.assertEqual(row["derived"]["total"], "300.00")


class FundSourceLabelTests(TestCase):
    """The new source types resolve to display labels everywhere."""

    def test_source_choices_include_both_earmarks(self):
        labels = dict(FundTransaction.SOURCE_TYPES)
        self.assertEqual(labels["aid_setaside_medical"], "Medical Aid Set-Aside")
        self.assertEqual(labels["aid_setaside_death"], "Death Aid Set-Aside")
        self.assertEqual(
            SETASIDE_SOURCE_TYPES,
            ("aid_setaside_medical", "aid_setaside_death"),
        )
        self.assertEqual(PURPOSE_TO_AID_TYPE[AssessmentItem.PURPOSE_DEATH_AID], "death_aid")


class AidReleaseDefaultsToHeldSetAsideTests(TestCase):
    """The release endpoint disburses what the claim is actually holding.

    Money is collected once at final approval (dues + earmarked aid). When the
    Treasurer releases, the payout defaults to the set-asides linked to that
    claim — the cash that was collected for this recipient — and is booked as a
    Medical Aid / Death Aid disbursement. Contributions are a separate, legacy
    collection and only apply when no earmark exists.
    """

    def setUp(self):
        self.treasurer = OfficerUser.objects.create(
            full_name="Treasurer Release Test",
            username="treas_rel",
            password_hash="unused",
            role="Treasurer",
            account_status="Active",
            mfa_secret="release-otp-test-secret",
        )
        session, token = create_access_session(
            officer=self.treasurer,
            ip_address="127.0.0.1",
            device_info="tests",
        )
        session.trusted_device = True
        session.device_info = ""
        policy = session.session_policy or {}
        policy["zt_verified_at"] = timezone.now().isoformat()
        session.session_policy = policy
        session.save()
        self.token = token

        self.member = _member("Josephine C. Cristobal", "EMP-SA-201")
        self.assessment = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1), total_amount=Decimal("300.00")
        )
        self.med_item = AssessmentItem.objects.create(
            assessment_id_FK=self.assessment,
            purpose=AssessmentItem.PURPOSE_MEDICAL_AID,
            amount=Decimal("100.00"),
            recipient="CRISTOBAL, Josephine C.",
            priority_order=1,
        )
        self.ma = MemberAssessment.objects.create(
            assessment_id_FK=self.assessment,
            member_id_FK=self.member,
            standard_assessment=Decimal("300.00"),
            actual_deduction=Decimal("300.00"),
            status=MemberAssessment.STATUS_APPROVED,
        )
        MemberAssessmentAllocation.objects.create(
            member_assessment_id_FK=self.ma,
            assessment_item_id_FK=self.med_item,
            amount_applied=Decimal("100.00"),
            amount_remaining=Decimal("0.00"),
        )

        self.archive = TransactionArchive.objects.create(
            transaction_type="medical_aid",
            record_id=1,
            member_id_FK=self.member,
            member_name=self.member.full_name,
            amount=Decimal("100.00"),
            validated_amount=Decimal("100.00"),
            status="Approved",
            verified_at=timezone.now(),
        )
        self.post = AidTrackingPost.objects.create(
            archive_id_FK=self.archive,
            aid_type="medical_aid",
            target_month="2026-09",
            finish_status="pending_release",
            # Benefit amount x contributing members — the hard release ceiling.
            total_expected=Decimal("1000.00"),
            total_collected=Decimal("0.00"),
        )

        # General fund so the balance guard has something to check against.
        # Deliberately NOT a BOOKING_SOURCE_TYPE with source_id=1: that would
        # trip book_member_fund_rows' idempotency guard for this assessment.
        FundTransaction.objects.create(
            direction="inflow",
            amount=Decimal("1000.00"),
            source_type="manual_adjustment",
            source_id=9999,
            description="Seeded general fund",
            recorded_by_user_id_FK=self.treasurer,
        )

    def _login(self):
        session = self.client.session
        session["access_token"] = self.token
        session["officer_id"] = self.treasurer.user_id_PK
        session["role"] = "Treasurer"
        session.save()

    def _issue_otp(self, post_id=None):
        """Stand in for the email round trip: bind a code to one claim."""
        session = self.client.session
        session["aid_release_otp"] = {
            "post_id": int(post_id or self.post.post_id_PK),
            "sent_at": timezone.now().timestamp(),
            "expires_at": (timezone.now() + timedelta(seconds=300)).isoformat(),
        }
        session.save()
        return generate_otp(self.treasurer.mfa_secret or "")

    def _release(self, otp=None, **extra):
        self._login()
        payload = {
            "post_id": str(self.post.post_id_PK),
            "received_by": "Maria Santos",
        }
        if otp is not None:
            payload["otp"] = otp
        payload.update(extra)
        return self.client.post("/api/treasurer/aid-post-release/", payload)

    def _outflows(self):
        return list(
            FundTransaction.objects.filter(direction="outflow").values_list(
                "amount", "source_type"
            )
        )

    def test_release_disburses_the_held_set_aside_not_the_legacy_contributions(self):
        book_member_fund_rows(self.ma, self.treasurer, "COL-0009", "September 2026")
        self.assertEqual(setaside_available_for_post(self.post), Decimal("100.00"))

        response = self._release(otp=self._issue_otp())

        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(self._outflows(), [(Decimal("100.00"), "medical_aid")])
        # The earmark is spent, not left dangling.
        self.assertEqual(
            AidSetAside.objects.get(aid_tracking_post_id_FK=self.post).amount_released,
            Decimal("100.00"),
        )

    def test_release_falls_back_to_contributions_when_no_earmark_exists(self):
        self.post.total_collected = Decimal("500.00")
        self.post.save(update_fields=["total_collected"])

        response = self._release(
            otp=self._issue_otp(),
            ack_fund_deduction="1",
            override_reason="No set-aside was linked to this claim.",
        )

        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(self._outflows(), [(Decimal("500.00"), "medical_aid")])

    def test_manual_amount_still_wins_over_the_held_set_aside(self):
        book_member_fund_rows(self.ma, self.treasurer, "COL-0010", "September 2026")

        response = self._release(
            otp=self._issue_otp(),
            release_amount="250.00",
            ack_fund_deduction="1",
            override_reason="Treasurer authorised the uncovered remainder.",
        )

        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(self._outflows(), [(Decimal("250.00"), "medical_aid")])
        # The ₱100 earmark is drawn first; the rest came from the general fund.
        self.assertEqual(
            AidSetAside.objects.get(aid_tracking_post_id_FK=self.post).amount_released,
            Decimal("100.00"),
        )

    def test_setaside_available_is_zero_before_anything_is_booked(self):
        self.assertEqual(setaside_available_for_post(self.post), Decimal("0.00"))
        self.assertEqual(setaside_available_for_post(None), Decimal("0.00"))

    # --- traps: nothing moves without all four controls in place ---------

    def test_release_without_a_verification_code_is_rejected(self):
        response = self._release()

        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.json()["requires_otp"])
        self.assertEqual(FundTransaction.objects.filter(direction="outflow").count(), 0)

    def test_release_without_received_by_is_rejected(self):
        self._login()
        otp = self._issue_otp()

        response = self.client.post(
            "/api/treasurer/aid-post-release/",
            {"post_id": str(self.post.post_id_PK), "otp": otp},
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["requires_received_by"])
        self.assertEqual(FundTransaction.objects.filter(direction="outflow").count(), 0)

    def test_code_issued_for_another_claim_is_rejected(self):
        otp = self._issue_otp(post_id=999999)

        response = self._release(otp=otp)

        self.assertEqual(response.status_code, 403)
        self.assertIn("different claim", response.json()["error"])
        self.assertEqual(FundTransaction.objects.filter(direction="outflow").count(), 0)

    def test_expired_code_is_rejected(self):
        session = self.client.session
        session["aid_release_otp"] = {
            "post_id": int(self.post.post_id_PK),
            "sent_at": (timezone.now() - timedelta(seconds=400)).timestamp(),
            "expires_at": (timezone.now() - timedelta(seconds=1)).isoformat(),
        }
        session.save()

        response = self._release(otp=generate_otp(self.treasurer.mfa_secret or ""))

        self.assertEqual(response.status_code, 403)
        self.assertIn("expired", response.json()["error"])

    def test_manual_amount_above_the_benefit_ceiling_is_released_as_typed(self):
        # Ceiling = benefit amount x members = post.total_expected = 1,000.
        # A typed amount is taken at face value (the fund balance is the real
        # limit) and the over-ceiling release is recorded in the audit trail.
        FundTransaction.objects.create(
            direction="inflow",
            amount=Decimal("1000.00"),
            source_type="manual_adjustment",
            source_id=9998,
            description="Top-up so the payout clears the balance guard",
            recorded_by_user_id_FK=self.treasurer,
        )
        response = self._release(
            otp=self._issue_otp(), release_amount="1500.00", ack_fund_deduction="1"
        )

        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(self._outflows(), [(Decimal("1500.00"), "medical_aid")])
        trails = GlobalAuditTrail.objects.filter(
            table_name="AID_TRACKING_POST", record_id=self.post.post_id_PK
        )
        self.assertTrue(
            any("above the approved benefit" in (t.notes or "") for t in trails)
        )

    def test_dipping_into_the_general_fund_requires_an_acknowledgement(self):
        # Nothing earmarked for this claim, so the whole payout leaves the
        # general fund — the release must be confirmed before it happens.
        response = self._release(otp=self._issue_otp(), release_amount="300.00")

        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertTrue(payload["requires_ack"])
        self.assertEqual(round(payload["shortfall"], 2), 300.0)
        self.assertEqual(FundTransaction.objects.filter(direction="outflow").count(), 0)

        # Acknowledged, it goes through.
        response = self._release(
            otp=self._issue_otp(),
            release_amount="300.00",
            ack_fund_deduction="1",
            override_reason="Claim has no set-aside behind it.",
        )
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(self._outflows(), [(Decimal("300.00"), "medical_aid")])

    def test_release_with_nothing_collected_is_refused(self):
        response = self._release(otp=self._issue_otp())

        self.assertEqual(response.status_code, 400)
        self.assertIn("Nothing has been collected", response.json()["error"])
        self.assertEqual(FundTransaction.objects.filter(direction="outflow").count(), 0)

    def test_general_fund_deduction_reason_is_optional(self):
        # Reason is optional now: acknowledged, it goes through even with the
        # old auto-filled boilerplate (or no reason at all) — the ack confirm
        # is the fund-protection gate.
        response = self._release(
            otp=self._issue_otp(),
            release_amount="300.00",
            ack_fund_deduction="1",
            override_reason="Manual amount",
        )

        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(self._outflows(), [(Decimal("300.00"), "medical_aid")])

    def test_earmark_larger_than_the_benefit_pays_only_the_benefit(self):
        # Members contributed ₱1,500 for a ₱1,000 benefit: the automatic
        # default must not blow the ceiling, it is trimmed to the benefit and
        # the surplus goes back to the pooled reserve.
        book_member_fund_rows(self.ma, self.treasurer, "COL-0011", "September 2026")
        row = AidSetAside.objects.get(aid_tracking_post_id_FK=self.post)
        AidSetAside.objects.filter(pk=row.pk).update(amount=Decimal("1500.00"))
        self.assertEqual(setaside_available_for_post(self.post), Decimal("1500.00"))

        response = self._release(otp=self._issue_otp())

        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(self._outflows(), [(Decimal("1000.00"), "medical_aid")])
        # Only the benefit was drawn; the ₱500 surplus is unlinked back to the
        # pooled reserve instead of being paid out.
        row.refresh_from_db()
        self.assertEqual(row.amount_released, Decimal("1000.00"))
        self.assertIsNone(row.aid_tracking_post_id_FK)
