import json
from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_system.auth_utils import create_access_session, hash_password
from core_system.constants.policy_constants import get_monthly_dues_amount
from core_system.models import (
    AssessmentItem,
    AssessmentWorkflowLog,
    Member,
    MemberAssessment,
    MemberCatchupDue,
    MonthlyAssessment,
    OfficerUser,
)


class DuesCatchupBackfillTests(TestCase):
    """Mid-year joiners: Treasurer generates Jan..enroll-month dues rows."""

    def setUp(self):
        from core_system.dues_backfill_guard import set_back_dues_chase_enabled

        set_back_dues_chase_enabled(True)

    def _login_treasurer(self):
        officer = OfficerUser.objects.create(
            full_name="Catchup Treasurer",
            username="catchup_treasurer",
            password_hash=hash_password("CatchupPass123!"),
            role="Treasurer",
            account_status="Active",
            mfa_enabled=False,
        )
        session, token = create_access_session(
            officer=officer,
            ip_address="127.0.0.1",
            device_info="tests",
        )
        session.save()

        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer

    def _make_member(self, name, email, classification, joined, status="Permanent", backfill=False):
        return Member.objects.create(
            full_name=name,
            employment_status="Active",
            membership_status=status,
            member_classification=classification,
            member_type="",
            date_joined=joined,
            email=email,
            dues_backfill_pending=backfill,
        )

    def _post_catchup(self, body):
        return self.client.post(
            reverse("treasurer_generate_catchup_dues"),
            data=json.dumps(body),
            content_type="application/json",
        )

    def test_teaching_june_joiner_gets_six_draft_months(self):
        self._login_treasurer()
        member = self._make_member(
            "June Joiner",
            "june.catchup@isu.edu.ph",
            "Teaching",
            date(2026, 6, 15),
            backfill=True,
        )

        response = self._post_catchup({"member_ids": [member.member_id_PK]})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["generated"], 6)

        months = sorted(
            MonthlyAssessment.objects.filter(
                month__year=2026,
                member_assessments__member_id_FK=member,
            ).values_list("month", flat=True)
        )
        self.assertEqual(
            months,
            [date(2026, m, 1) for m in range(1, 7)],
        )
        for assessment in MonthlyAssessment.objects.filter(month__year=2026):
            if assessment.month.month <= 6:
                self.assertEqual(assessment.status, MonthlyAssessment.STATUS_DRAFT)
                self.assertTrue(
                    assessment.items.filter(purpose=AssessmentItem.PURPOSE_MONTHLY_DUE).exists()
                )

        row = MemberAssessment.objects.filter(member_id_FK=member).first()
        self.assertIsNotNone(row)
        expected = Decimal(str(get_monthly_dues_amount())).quantize(Decimal("0.01"))
        self.assertEqual(row.standard_assessment, expected)
        self.assertEqual(row.status, MemberAssessment.STATUS_PENDING)
        self.assertEqual(row.outstanding_balance, expected)

        member.refresh_from_db()
        self.assertFalse(member.dues_backfill_pending)

        self.assertTrue(
            AssessmentWorkflowLog.objects.filter(
                action="catchup_backfill",
                assessment_id_FK__member_assessments__member_id_FK=member,
            ).exists()
        )

    def test_rerun_is_idempotent(self):
        self._login_treasurer()
        member = self._make_member(
            "Idem Member",
            "idem.catchup@isu.edu.ph",
            "Teaching",
            date(2026, 4, 10),
            backfill=True,
        )
        first = self._post_catchup({"member_ids": [member.member_id_PK]})
        self.assertEqual(first.json()["generated"], 4)

        second = self._post_catchup({"member_ids": [member.member_id_PK]})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["generated"], 0)
        self.assertEqual(
            MemberAssessment.objects.filter(member_id_FK=member).count(),
            4,
        )
        self.assertEqual(
            MonthlyAssessment.objects.filter(month__year=2026).count(),
            4,
        )

    def test_retired_skipped_and_flag_cleared(self):
        self._login_treasurer()
        member = self._make_member(
            "Retired Catchup",
            "retired.catchup@isu.edu.ph",
            "Retired",
            date(2026, 5, 1),
            status="Retired",
            backfill=True,
        )
        response = self._post_catchup({"member_ids": [member.member_id_PK]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["generated"], 0)
        member.refresh_from_db()
        self.assertFalse(member.dues_backfill_pending)
        self.assertEqual(MemberAssessment.objects.filter(member_id_FK=member).count(), 0)

    def test_january_joiner_has_no_window(self):
        self._login_treasurer()
        member = self._make_member(
            "Jan Joiner",
            "jan.catchup@isu.edu.ph",
            "Teaching",
            date(2026, 1, 5),
            backfill=False,
        )
        response = self._post_catchup({"member_ids": [member.member_id_PK]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["generated"], 0)
        self.assertEqual(MemberAssessment.objects.filter(member_id_FK=member).count(), 0)

    def test_january_joiner_unpaid_ignores_prior_year_draft(self):
        """Recording Jan 2027 must not surface Aug 2026 for a Jan 2027 joiner."""
        officer = self._login_treasurer()
        stale = MonthlyAssessment.objects.create(
            month=date(2026, 8, 1),
            total_amount=Decimal("100.00"),
            status=MonthlyAssessment.STATUS_DRAFT,
            created_by_id_FK=officer,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=stale,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"),
            priority_order=1,
        )
        current = MonthlyAssessment.objects.create(
            month=date(2027, 1, 1),
            total_amount=Decimal("100.00"),
            status=MonthlyAssessment.STATUS_PENDING_TREASURER,
            created_by_id_FK=officer,
        )
        # Pin creation dates so the strict snapshot rule is deterministic:
        # the joiner (Jan 5) was present when January was created (Jan 10).
        MonthlyAssessment.objects.filter(pk=stale.pk).update(
            created_at=timezone.make_aware(datetime(2026, 8, 5, 8, 0, 0))
        )
        MonthlyAssessment.objects.filter(pk=current.pk).update(
            created_at=timezone.make_aware(datetime(2027, 1, 10, 8, 0, 0))
        )
        AssessmentItem.objects.create(
            assessment_id_FK=current,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"),
            priority_order=1,
        )
        joiner = self._make_member(
            "Jan 2027 Joiner",
            "jan2027.catchup@isu.edu.ph",
            "Teaching",
            date(2027, 1, 5),
            backfill=False,
        )
        MemberAssessment.objects.create(
            member_id_FK=joiner,
            assessment_id_FK=stale,
            actual_deduction=Decimal("0.00"),
            outstanding_balance=Decimal("100.00"),
            standard_assessment=Decimal("100.00"),
            status=MemberAssessment.STATUS_PENDING,
        )

        response = self.client.get(
            reverse("treasurer_monthly_deduction_members", kwargs={"assessment_id": current.assessment_id_PK})
        )
        self.assertEqual(response.status_code, 200)
        rows = {m["member_id"]: m for m in response.json()["members"]}
        row = rows[joiner.member_id_PK]
        unpaid_keys = [u["key"] for u in (row.get("unpaid_months") or [])]
        self.assertNotIn("2026-08", unpaid_keys)
        self.assertNotIn("2026-08", [u for u in unpaid_keys])

    def test_same_year_draft_after_january_is_outstanding_not_catchup(self):
        """Jan joiner with unpaid August is outstanding, not a catch-up label."""
        officer = self._login_treasurer()
        aug = MonthlyAssessment.objects.create(
            month=date(2026, 8, 1),
            total_amount=Decimal("100.00"),
            status=MonthlyAssessment.STATUS_DRAFT,
            created_by_id_FK=officer,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=aug,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"),
            priority_order=1,
        )
        current = MonthlyAssessment.objects.create(
            month=date(2027, 1, 1),
            total_amount=Decimal("100.00"),
            status=MonthlyAssessment.STATUS_PENDING_TREASURER,
            created_by_id_FK=officer,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=current,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"),
            priority_order=1,
        )
        joiner = self._make_member(
            "Jan 2026 Starter",
            "jan2026.unpaid@isu.edu.ph",
            "Teaching",
            date(2026, 1, 5),
            backfill=False,
        )
        MemberAssessment.objects.create(
            member_id_FK=joiner,
            assessment_id_FK=aug,
            actual_deduction=Decimal("0.00"),
            outstanding_balance=Decimal("100.00"),
            standard_assessment=Decimal("100.00"),
            status=MemberAssessment.STATUS_PENDING,
        )

        response = self.client.get(
            reverse("treasurer_monthly_deduction_members", kwargs={"assessment_id": current.assessment_id_PK})
        )
        self.assertEqual(response.status_code, 200)
        rows = {m["member_id"]: m for m in response.json()["members"]}
        row = rows[joiner.member_id_PK]
        unpaid = row.get("unpaid_months") or []
        self.assertEqual([u["key"] for u in unpaid], ["2026-08"])
        self.assertEqual(unpaid[0]["source"], "outstanding")

    def test_existing_final_approved_month_is_skipped(self):
        officer = self._login_treasurer()
        closed = MonthlyAssessment.objects.create(
            month=date(2026, 2, 1),
            total_amount=Decimal("100.00"),
            status=MonthlyAssessment.STATUS_FINAL_APPROVED,
            created_by_id_FK=officer,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=closed,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"),
            priority_order=1,
        )
        member = self._make_member(
            "Closed Month Joiner",
            "closed.catchup@isu.edu.ph",
            "Teaching",
            date(2026, 5, 20),
            backfill=True,
        )

        response = self._post_catchup({"member_ids": [member.member_id_PK]})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Jan, Mar, Apr, May created; Feb skipped as final_approved.
        self.assertEqual(data["generated"], 4)
        self.assertFalse(
            MemberAssessment.objects.filter(
                assessment_id_FK=closed,
                member_id_FK=member,
            ).exists()
        )
        skipped = data["results"][0]["skipped"]
        self.assertEqual(skipped[0]["month"], "2026-02")

    def test_september_joiner_can_select_closed_january_to_august_dues(self):
        """Closed months become selectable catch-up, never reopened batches."""
        officer = self._login_treasurer()
        for month_no in range(1, 9):
            assessment = MonthlyAssessment.objects.create(
                month=date(2026, month_no, 1),
                total_amount=Decimal("100.00"),
                status=MonthlyAssessment.STATUS_FINAL_APPROVED,
                created_by_id_FK=officer,
            )
            AssessmentItem.objects.create(
                assessment_id_FK=assessment,
                purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
                amount=Decimal("100.00"),
                priority_order=1,
            )
        september = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1),
            total_amount=Decimal("100.00"),
            status=MonthlyAssessment.STATUS_PENDING_TREASURER,
            created_by_id_FK=officer,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=september,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"),
            priority_order=1,
        )
        joiner = self._make_member(
            "September Joiner",
            "september.joiner@isu.edu.ph",
            "Teaching",
            date(2026, 9, 10),
            backfill=True,
        )

        generated = self._post_catchup({"member_ids": [joiner.member_id_PK]})
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(generated.json()["generated"], 9)
        self.assertEqual(
            list(MemberCatchupDue.objects.filter(member_id_FK=joiner).values_list("month", flat=True)),
            [date(2026, m, 1) for m in range(1, 9)],
        )
        self.assertFalse(
            MemberAssessment.objects.filter(
                member_id_FK=joiner,
                assessment_id_FK__month__lt=date(2026, 9, 1),
            ).exists(),
        )

        roster_response = self.client.get(
            reverse("treasurer_monthly_deduction_members", kwargs={"assessment_id": september.assessment_id_PK})
        )
        self.assertEqual(roster_response.status_code, 200)
        row = next(m for m in roster_response.json()["members"] if m["member_id"] == joiner.member_id_PK)
        self.assertEqual([m["key"] for m in row["unpaid_months"]], [f"2026-{m:02d}" for m in range(1, 9)])
        self.assertEqual(row["prior_outstanding"], 800.0)
        self.assertEqual(row["expected_total"], 100.0)

        record = self.client.post(
            reverse("treasurer_record_monthly_deductions"),
            data=json.dumps({
                "assessment_id": september.assessment_id_PK,
                "members": [{
                    "member_id": joiner.member_id_PK,
                    "actual_deduction": "900.00",
                    "prior_balance_amount": "800.00",
                    "unpaid_month_keys": [f"2026-{m:02d}" for m in range(1, 9)],
                }],
                "submit": False,
            }),
            content_type="application/json",
        )
        self.assertEqual(record.status_code, 200)
        member_record = MemberAssessment.objects.get(
            member_id_FK=joiner, assessment_id_FK=september
        )
        self.assertEqual(member_record.prior_outstanding_collected, Decimal("800.00"))
        self.assertEqual(member_record.actual_deduction, Decimal("900.00"))
        self.assertEqual(member_record.outstanding_balance, Decimal("0.00"))

    def test_all_pending_batch_flag(self):
        self._login_treasurer()
        a = self._make_member("Batch A", "batch.a@isu.edu.ph", "Teaching", date(2026, 3, 1), backfill=True)
        b = self._make_member("Batch B", "batch.b@isu.edu.ph", "Teaching", date(2026, 3, 1), backfill=True)
        response = self._post_catchup({"all_pending": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["generated"], 6)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertFalse(a.dues_backfill_pending)
        self.assertFalse(b.dues_backfill_pending)

    def test_roster_exposes_backfill_and_joined_after_flags(self):
        officer = self._login_treasurer()
        assessment = MonthlyAssessment.objects.create(
            month=date(2026, 3, 1),
            total_amount=Decimal("100.00"),
            status=MonthlyAssessment.STATUS_PENDING_TREASURER,
            created_by_id_FK=officer,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=assessment,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"),
            priority_order=1,
        )
        joiner = self._make_member(
            "March Mid",
            "march.mid@isu.edu.ph",
            "Teaching",
            date(2026, 6, 15),
            backfill=True,
        )
        present = self._make_member(
            "March Present",
            "march.present@isu.edu.ph",
            "Teaching",
            date(2026, 1, 10),
        )

        response = self.client.get(
            reverse("treasurer_monthly_deduction_members", kwargs={"assessment_id": assessment.assessment_id_PK})
        )
        self.assertEqual(response.status_code, 200)
        rows = {m["member_id"]: m for m in response.json()["members"]}
        self.assertTrue(rows[joiner.member_id_PK]["dues_backfill_pending"])
        self.assertTrue(rows[joiner.member_id_PK]["joined_after_month"])
        self.assertTrue(rows[joiner.member_id_PK]["mid_year_joiner"])
        self.assertEqual(rows[joiner.member_id_PK]["date_joined"], "2026-06-15")
        self.assertFalse(rows[present.member_id_PK]["joined_after_month"])
        self.assertFalse(rows[present.member_id_PK]["dues_backfill_pending"])
        self.assertFalse(rows[present.member_id_PK]["mid_year_joiner"])

    def test_roster_unifies_catchup_and_outstanding_as_unpaid_months(self):
        """Catch-up drafts show in the same unpaid_months list as prior outstanding."""
        officer = self._login_treasurer()
        # Current month the treasurer is recording.
        current = MonthlyAssessment.objects.create(
            month=date(2026, 7, 1),
            total_amount=Decimal("100.00"),
            status=MonthlyAssessment.STATUS_PENDING_TREASURER,
            created_by_id_FK=officer,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=current,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"),
            priority_order=1,
        )
        joiner = self._make_member(
            "Unified Joiner",
            "unified.catchup@isu.edu.ph",
            "Teaching",
            date(2026, 6, 15),
            backfill=True,
        )
        # Generate Jan..Jun catch-up rows (draft months).
        response = self._post_catchup({"member_ids": [joiner.member_id_PK]})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        response = self.client.get(
            reverse("treasurer_monthly_deduction_members", kwargs={"assessment_id": current.assessment_id_PK})
        )
        self.assertEqual(response.status_code, 200)
        rows = {m["member_id"]: m for m in response.json()["members"]}
        row = rows[joiner.member_id_PK]
        unpaid = row.get("unpaid_months") or []
        self.assertTrue(unpaid, "catch-up months must appear as unpaid_months")
        self.assertEqual(
            [u["key"] for u in unpaid],
            [f"2026-{m:02d}" for m in range(1, 7)],
        )
        self.assertTrue(all(u["source"] == "catchup" for u in unpaid))
        dues = float(get_monthly_dues_amount())
        self.assertAlmostEqual(float(row["prior_outstanding"]), dues * 6, places=2)
        self.assertAlmostEqual(
            sum(float(u["amount"]) for u in unpaid),
            float(row["prior_outstanding"]),
            places=2,
        )

    def test_empty_member_ids_rejected(self):
        self._login_treasurer()
        response = self._post_catchup({"member_ids": []})
        self.assertEqual(response.status_code, 400)

    def _make_split_assessment(self, officer, month, dues, aid):
        assessment = MonthlyAssessment.objects.create(
            month=month,
            total_amount=Decimal(str(dues + aid)),
            status=MonthlyAssessment.STATUS_PENDING_TREASURER,
            created_by_id_FK=officer,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=assessment,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal(str(dues)),
            priority_order=1,
        )
        if aid:
            AssessmentItem.objects.create(
                assessment_id_FK=assessment,
                purpose=AssessmentItem.PURPOSE_MEDICAL_AID,
                amount=Decimal(str(aid)),
                priority_order=2,
            )
        return assessment

    def _roster_row(self, assessment_id, member_id):
        response = self.client.get(
            reverse("treasurer_monthly_deduction_members", kwargs={"assessment_id": assessment_id})
        )
        self.assertEqual(response.status_code, 200)
        rows = {m["member_id"]: m for m in response.json()["members"]}
        return rows[member_id]

    # -- Strict snapshot: members added after assessment creation ---------

    def _make_dues_assessment(self, officer, month, created_on):
        """Pending dues assessment backdated to a fixed creation date."""
        assessment = MonthlyAssessment.objects.create(
            month=month,
            total_amount=Decimal("100.00"),
            status=MonthlyAssessment.STATUS_PENDING_TREASURER,
            created_by_id_FK=officer,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=assessment,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"),
            priority_order=1,
        )
        MonthlyAssessment.objects.filter(pk=assessment.pk).update(
            created_at=timezone.make_aware(datetime(
                created_on.year, created_on.month, created_on.day, 8, 0, 0
            ))
        )
        assessment.refresh_from_db()
        return assessment

    def test_post_creation_joiner_excluded_from_roster(self):
        """Sep 1 assessment + Sep 5 joiner: joiner hidden, counted in note."""
        officer = self._login_treasurer()
        september = self._make_dues_assessment(officer, date(2026, 9, 1), date(2026, 9, 1))
        joiner = self._make_member(
            "Late September", "late.september@isu.edu.ph", "Teaching", date(2026, 9, 5)
        )
        veteran = self._make_member(
            "August Veteran", "august.veteran@isu.edu.ph", "Teaching", date(2026, 8, 20)
        )

        response = self.client.get(
            reverse("treasurer_monthly_deduction_members", kwargs={"assessment_id": september.assessment_id_PK})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        member_ids = [m["member_id"] for m in data["members"]]
        self.assertNotIn(joiner.member_id_PK, member_ids)
        self.assertIn(veteran.member_id_PK, member_ids)
        excluded = data["excluded_not_joined"]
        self.assertEqual(excluded["count"], 1)
        self.assertEqual(len(excluded["names"]), 1)

    def test_post_creation_joiner_month_becomes_catchup(self):
        """Sep 5 joiner: September owed as MemberCatchupDue, never a row on it."""
        officer = self._login_treasurer()
        september = self._make_dues_assessment(officer, date(2026, 9, 1), date(2026, 9, 1))
        joiner = self._make_member(
            "Catchup September", "catchup.september@isu.edu.ph", "Teaching",
            date(2026, 9, 5), backfill=True,
        )

        response = self._post_catchup({"member_ids": [joiner.member_id_PK]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["generated"], 9)
        self.assertTrue(
            MemberCatchupDue.objects.filter(member_id_FK=joiner, month=date(2026, 9, 1)).exists()
        )
        self.assertFalse(
            MemberAssessment.objects.filter(member_id_FK=joiner, assessment_id_FK=september).exists()
        )

    def test_record_rejects_post_creation_joiner(self):
        """Recording a post-creation joiner on that month is a 409."""
        officer = self._login_treasurer()
        september = self._make_dues_assessment(officer, date(2026, 9, 1), date(2026, 9, 1))
        joiner = self._make_member(
            "Rejected September", "rejected.september@isu.edu.ph", "Teaching", date(2026, 9, 5)
        )

        response = self.client.post(
            reverse("treasurer_record_monthly_deductions"),
            data=json.dumps({
                "assessment_id": september.assessment_id_PK,
                "members": [{"member_id": joiner.member_id_PK, "actual_deduction": "100.00"}],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("joined after", response.json()["error"])
        self.assertFalse(
            MemberAssessment.objects.filter(member_id_FK=joiner, assessment_id_FK=september).exists()
        )

    def test_pre_creation_joiner_records_normally(self):
        """Aug 20 joiner on a Sep 1 assessment records like everyone else."""
        officer = self._login_treasurer()
        september = self._make_dues_assessment(officer, date(2026, 9, 1), date(2026, 9, 1))
        veteran = self._make_member(
            "Normal Veteran", "normal.veteran@isu.edu.ph", "Teaching", date(2026, 8, 20)
        )

        response = self.client.post(
            reverse("treasurer_record_monthly_deductions"),
            data=json.dumps({
                "assessment_id": september.assessment_id_PK,
                "members": [{"member_id": veteran.member_id_PK, "actual_deduction": "100.00"}],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        row = MemberAssessment.objects.get(member_id_FK=veteran, assessment_id_FK=september)
        self.assertEqual(row.actual_deduction, Decimal("100.00"))
        self.assertEqual(row.outstanding_balance, Decimal("0.00"))

    def test_unpaid_months_carry_dues_aid_split(self):
        """A past month with aid reconciles into Due / Aid components."""
        officer = self._login_treasurer()
        past = self._make_split_assessment(officer, date(2026, 2, 1), 100, 50)
        current = self._make_split_assessment(officer, date(2026, 3, 1), 100, 50)
        member = self._make_member(
            "Split Member", "split@isu.edu.ph", "Teaching", date(2026, 1, 10)
        )
        MemberAssessment.objects.create(
            assessment_id_FK=past,
            member_id_FK=member,
            standard_assessment=Decimal("150.00"),
            actual_deduction=Decimal("0.00"),
            outstanding_balance=Decimal("150.00"),
            status=MemberAssessment.STATUS_PENDING,
            recorded_by_id_FK=officer,
        )

        row = self._roster_row(current.assessment_id_PK, member.member_id_PK)
        unpaid = row.get("unpaid_months") or []
        self.assertEqual(len(unpaid), 1)
        feb = unpaid[0]
        self.assertEqual(feb["key"], "2026-02")
        self.assertAlmostEqual(feb["amount"], 150.0, places=2)
        self.assertAlmostEqual(feb["dues"], 100.0, places=2)
        self.assertAlmostEqual(feb["aid"], 50.0, places=2)
        self.assertAlmostEqual(
            feb["dues"] + feb["aid"], feb["amount"], places=2
        )

    def test_year_tracker_pays_since_january_join_aware(self):
        """Year grid: paid/partial/unpaid per month, join-month floor, no clock."""
        officer = self._login_treasurer()
        jan = self._make_split_assessment(officer, date(2026, 1, 1), 100, 50)
        feb = self._make_split_assessment(officer, date(2026, 2, 1), 100, 50)
        veteran = self._make_member(
            "Veteran", "veteran@isu.edu.ph", "Teaching", date(2026, 1, 5)
        )
        joiner = self._make_member(
            "Feb Joiner", "feb.joiner@isu.edu.ph", "Teaching", date(2026, 2, 10)
        )
        MemberAssessment.objects.create(
            assessment_id_FK=jan, member_id_FK=veteran,
            standard_assessment=Decimal("150.00"), actual_deduction=Decimal("150.00"),
            outstanding_balance=Decimal("0.00"), status=MemberAssessment.STATUS_PENDING,
            recorded_by_id_FK=officer,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=feb, member_id_FK=veteran,
            standard_assessment=Decimal("150.00"), actual_deduction=Decimal("100.00"),
            outstanding_balance=Decimal("50.00"), status=MemberAssessment.STATUS_PENDING,
            recorded_by_id_FK=officer,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=feb, member_id_FK=joiner,
            standard_assessment=Decimal("150.00"), actual_deduction=Decimal("0.00"),
            outstanding_balance=Decimal("150.00"), status=MemberAssessment.STATUS_PENDING,
            recorded_by_id_FK=officer,
        )

        response = self.client.get(reverse("treasurer_year_tracker") + "?year=2026")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["year"], 2026)
        self.assertIn(2026, data["available_years"])
        grid = {m["member_id"]: m for m in data["members"]}

        vet = {c["month"]: c["status"] for c in grid[veteran.member_id_PK]["months"]}
        self.assertEqual(vet[1], "paid")
        self.assertEqual(vet[2], "partial")
        self.assertEqual(grid[veteran.member_id_PK]["paid_count"], 1)
        self.assertEqual(grid[veteran.member_id_PK]["open_count"], 1)

        # Joined in February: January is n/a, February unpaid.
        new = {c["month"]: c["status"] for c in grid[joiner.member_id_PK]["months"]}
        self.assertEqual(new[1], "na")
        self.assertEqual(new[2], "unpaid")

        # Explicit year only: 2027 with no assessments reports no_assessment.
        response = self.client.get(reverse("treasurer_year_tracker") + "?year=2027")
        data = response.json()
        grid = {m["member_id"]: m for m in data["members"]}
        self.assertEqual(
            {c["month"]: c["status"] for c in grid[veteran.member_id_PK]["months"]}[1],
            "no_assessment",
        )

        # Bad year rejected.
        response = self.client.get(reverse("treasurer_year_tracker") + "?year=soon")
        self.assertEqual(response.status_code, 400)

    def test_dues_only_component_key_leaves_aid_open(self):
        """Ticking only Due settles dues; the Aid stays collectible."""
        officer = self._login_treasurer()
        self._make_split_assessment(officer, date(2026, 2, 1), 100, 50)
        current = self._make_split_assessment(officer, date(2026, 3, 1), 100, 50)
        member = self._make_member(
            "Dues Only", "dues.only@isu.edu.ph", "Teaching", date(2026, 1, 10)
        )
        MemberAssessment.objects.create(
            assessment_id_FK=MonthlyAssessment.objects.get(month=date(2026, 2, 1)),
            member_id_FK=member,
            standard_assessment=Decimal("150.00"),
            actual_deduction=Decimal("0.00"),
            outstanding_balance=Decimal("150.00"),
            status=MemberAssessment.STATUS_PENDING,
            recorded_by_id_FK=officer,
        )

        response = self.client.post(
            reverse("treasurer_record_monthly_deductions"),
            data=json.dumps({
                "assessment_id": current.assessment_id_PK,
                "members": [{
                    "member_id": member.member_id_PK,
                    "actual_deduction": "250.00",
                    "prior_balance_amount": "100.00",
                    "unpaid_month_keys": ["2026-02:dues"],
                }],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        recorded = MemberAssessment.objects.get(
            assessment_id_FK=current, member_id_FK=member
        )
        collected = recorded.prior_collected_months or []
        self.assertEqual(len(collected), 1)
        self.assertEqual(collected[0]["key"], "2026-02:dues")
        self.assertAlmostEqual(collected[0]["amount"], 100.0, places=2)

        following = self._make_split_assessment(officer, date(2026, 4, 1), 100, 50)
        row = self._roster_row(following.assessment_id_PK, member.member_id_PK)
        unpaid = row.get("unpaid_months") or []
        self.assertEqual(len(unpaid), 1)
        feb = unpaid[0]
        self.assertEqual(feb["key"], "2026-02")
        self.assertAlmostEqual(feb["dues"], 0.0, places=2)
        self.assertAlmostEqual(feb["aid"], 50.0, places=2)
        self.assertAlmostEqual(feb["amount"], 50.0, places=2)

    # -- Backend year containers: dues timeline past the join year --------

    def _make_approved_assessment(self, officer, month):
        assessment = MonthlyAssessment.objects.create(
            month=month,
            total_amount=Decimal("100.00"),
            status=MonthlyAssessment.STATUS_FINAL_APPROVED,
            created_by_id_FK=officer,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=assessment,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"),
            priority_order=1,
        )
        return assessment

    def _make_charged_calendar(self, officer):
        for month_no in range(1, 13):
            self._make_approved_assessment(officer, date(2026, month_no, 1))
        for month_no in range(1, 5):
            self._make_approved_assessment(officer, date(2027, month_no, 1))
        # May 2027 exists but was never charged: never part of containers.
        MonthlyAssessment.objects.create(
            month=date(2027, 5, 1),
            total_amount=Decimal("100.00"),
            status=MonthlyAssessment.STATUS_PENDING_TREASURER,
            created_by_id_FK=officer,
        )

    def test_year_containers_group_charged_months_and_frontier(self):
        from core_system.services.dues_status import dues_year_containers

        officer = self._login_treasurer()
        self._make_charged_calendar(officer)

        calendar = dues_year_containers()
        self.assertEqual(calendar["frontier"], "2027-04")
        self.assertEqual(calendar["current_year"], 2027)
        self.assertEqual(
            [c["year"] for c in calendar["containers"]], [2026, 2027]
        )
        closed = calendar["containers"][0]
        self.assertTrue(closed["closed"])
        self.assertEqual(closed["start"], "2026-01")
        self.assertEqual(closed["end"], "2026-12")
        current = calendar["containers"][1]
        self.assertFalse(current["closed"])
        self.assertEqual(current["start"], "2027-01")
        self.assertEqual(current["end"], "2027-04")

    def test_empty_calendar_has_no_frontier(self):
        from core_system.services.dues_status import (
            dues_frontier_month,
            dues_year_containers,
        )

        calendar = dues_year_containers()
        self.assertIsNone(calendar["frontier"])
        self.assertEqual(calendar["containers"], [])
        # Falls back to the machine month (greenfield behaviour).
        self.assertEqual(dues_frontier_month(), timezone.now().strftime("%Y-%m"))

    def test_september_joiner_catchup_crosses_into_current_container(self):
        """New member while dues run past the join year.

        Collections charged through April 2027 must backfill January–April
        2027 for a September 2026 joiner — never stop at September 2026,
        never touch the closed 2026 tail (Oct–Dec), and never the uncharged
        May 2027 draft.
        """
        officer = self._login_treasurer()
        self._make_charged_calendar(officer)
        joiner = self._make_member(
            "Cross Year Joiner",
            "cross.year@isu.edu.ph",
            "Teaching",
            date(2026, 9, 10),
            backfill=True,
        )

        response = self._post_catchup({"member_ids": [joiner.member_id_PK]})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["generated"], 13)

        catchup_months = sorted(
            MemberCatchupDue.objects.filter(member_id_FK=joiner).values_list(
                "month", flat=True
            )
        )
        self.assertEqual(
            catchup_months,
            [date(2026, m, 1) for m in range(1, 10)]
            + [date(2027, m, 1) for m in range(1, 5)],
        )
        keys = [d.strftime("%Y-%m") for d in catchup_months]
        for closed_tail in ("2026-10", "2026-11", "2026-12", "2027-05"):
            self.assertNotIn(closed_tail, keys)
        self.assertFalse(
            MemberAssessment.objects.filter(member_id_FK=joiner).exists()
        )

        from core_system.monthly_deduction_views import _unpaid_months_by_member

        entry = _unpaid_months_by_member().get(joiner.member_id_PK, {})
        self.assertEqual(
            [m["key"] for m in entry.get("months", [])],
            [d.strftime("%Y-%m") for d in catchup_months],
        )
        dues = float(get_monthly_dues_amount())
        self.assertAlmostEqual(entry.get("amount", 0.0), dues * 13, places=2)

    def test_row_less_joiner_summary_covers_current_container(self):
        """Treasurer record-dues outstanding for a member with no rows."""
        officer = self._login_treasurer()
        self._make_charged_calendar(officer)
        joiner = self._make_member(
            "Summary Joiner",
            "summary.joiner@isu.edu.ph",
            "Teaching",
            date(2026, 9, 28),
        )

        from core_system.member_views import _compute_dues_summary

        summary = _compute_dues_summary(joiner)
        dues = float(get_monthly_dues_amount())
        self.assertAlmostEqual(summary["outstanding_balance"], dues * 4, places=2)

        response = self.client.get(
            reverse(
                "treasurer_member_unpaid_months",
                kwargs={"member_id": joiner.member_id_PK},
            )
        )
        self.assertEqual(response.status_code, 200, response.content)
        months = response.json()["unpaid_months"]
        overdue = [m["value"] for m in months if not m.get("is_advance")]
        self.assertEqual(overdue, ["2027-01", "2027-02", "2027-03", "2027-04"])
        advance = [m["value"] for m in months if m.get("is_advance")]
        self.assertTrue(advance)
        self.assertEqual(advance[0], "2027-05")


class BackDuesChaseDisabledTests(TestCase):
    """Default OFF: mid-year joiners pay current->future only."""

    def _login_treasurer(self):
        officer = OfficerUser.objects.create(
            full_name="No Chase Treasurer",
            username="no_chase_treasurer",
            password_hash=hash_password("NoChasePass123!"),
            role="Treasurer",
            account_status="Active",
            mfa_enabled=False,
        )
        session, token = create_access_session(
            officer=officer,
            ip_address="127.0.0.1",
            device_info="tests",
        )
        session.save()

        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer

    def test_default_is_off(self):
        from core_system.dues_backfill_guard import (
            is_back_dues_chase_enabled,
            should_flag_backfill,
        )

        self.assertFalse(is_back_dues_chase_enabled())
        self.assertFalse(should_flag_backfill(date(2026, 9, 15), "Teaching"))
        self.assertFalse(should_flag_backfill(date(2026, 1, 15), "Teaching"))

    def test_window_empty_when_disabled(self):
        from core_system.monthly_deduction_views import _catchup_window_keys

        self.assertEqual(_catchup_window_keys(date(2026, 9, 15)), set())

    def test_manual_endpoint_rejected_when_disabled(self):
        self._login_treasurer()
        member = Member.objects.create(
            full_name="Sep Joiner",
            employment_status="Active",
            membership_status="Permanent",
            member_classification="Teaching",
            member_type="",
            date_joined=date(2026, 9, 15),
            email="sep.nochase@isu.edu.ph",
            dues_backfill_pending=True,
        )
        response = self.client.post(
            reverse("treasurer_generate_catchup_dues"),
            data=json.dumps({"member_ids": [member.member_id_PK]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("disabled", response.json().get("error", "").lower())

    def test_overview_reports_disabled_flag(self):
        self._login_treasurer()
        Member.objects.create(
            full_name="Flagged Joiner",
            employment_status="Active",
            membership_status="Permanent",
            member_classification="Teaching",
            member_type="",
            date_joined=date(2026, 9, 15),
            email="flagged.nochase@isu.edu.ph",
            dues_backfill_pending=True,
        )
        response = self.client.get(reverse("treasurer_monthly_deductions_overview"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["flags"]["require_back_dues"])
        self.assertEqual(data["catchup_pending_count"], 0)

    def test_catchup_source_excluded_from_unpaid_when_disabled(self):
        from core_system.monthly_deduction_views import _unpaid_months_by_member

        self._login_treasurer()
        member = Member.objects.create(
            full_name="Seeded Joiner",
            employment_status="Active",
            membership_status="Permanent",
            member_classification="Teaching",
            member_type="",
            date_joined=date(2026, 9, 15),
            email="seeded.nochase@isu.edu.ph",
        )
        MemberCatchupDue.objects.create(
            member_id_FK=member,
            month=date(2026, 1, 1),
            amount=Decimal("100.00"),
        )
        result = _unpaid_months_by_member()
        self.assertNotIn(member.member_id_PK, result)
