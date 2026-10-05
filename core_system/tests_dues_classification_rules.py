import json
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_system.auth_utils import create_access_session, hash_password
from core_system.constants.policy_constants import is_retired_member
from core_system.models import AssessmentItem, Member, MonthlyAssessment, OfficerUser


class DuesClassificationRulesTests(TestCase):
    """Teaching pays everything; Retired owes nothing but keeps their record."""

    def _login_treasurer(self):
        officer = OfficerUser.objects.create(
            full_name="Dues Treasurer",
            username="dues_treasurer",
            password_hash=hash_password("DuesPass123!"),
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

    def _make_member(self, name, email, classification, status="Permanent"):
        return Member.objects.create(
            full_name=name,
            employment_status="Active",
            membership_status=status,
            member_classification=classification,
            member_type="",
            date_joined=timezone.now().date(),
            email=email,
        )

    def _make_assessment(self, officer):
        assessment = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1),
            total_amount=Decimal("150.00"),
            status=MonthlyAssessment.STATUS_PENDING_TREASURER,
            created_by_id_FK=officer,
        )
        dues = AssessmentItem.objects.create(
            assessment_id_FK=assessment,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"),
            priority_order=1,
        )
        aid = AssessmentItem.objects.create(
            assessment_id_FK=assessment,
            purpose=AssessmentItem.PURPOSE_MEDICAL_AID,
            amount=Decimal("50.00"),
            recipient="Some Member",
            priority_order=2,
        )
        return assessment, dues, aid

    def test_roster_expected_totals_follow_classification(self):
        officer = self._login_treasurer()
        assessment, dues, aid = self._make_assessment(officer)
        teaching = self._make_member("Teach Member", "teach.rules@isu.edu.ph", "Teaching")
        retired = self._make_member("Retired Member", "retired.rules@isu.edu.ph", "Retired")

        response = self.client.get(
            reverse("treasurer_monthly_deduction_members", kwargs={"assessment_id": assessment.assessment_id_PK})
        )

        self.assertEqual(response.status_code, 200, response.content[:500])
        by_id = {m["member_id"]: m for m in response.json()["members"]}
        self.assertEqual(by_id[teaching.member_id_PK]["expected_total"], 150.0)
        # Retired stays listed (record kept) but owes nothing.
        self.assertEqual(by_id[retired.member_id_PK]["expected_total"], 0.0)

    def test_record_rejects_any_amount_for_retired(self):
        officer = self._login_treasurer()
        assessment, dues, aid = self._make_assessment(officer)
        member = self._make_member("Retired Two", "retired2.rules@isu.edu.ph", "Retired")

        response = self.client.post(
            reverse("treasurer_record_monthly_deductions"),
            data=json.dumps({
                "assessment_id": assessment.assessment_id_PK,
                "members": [{"member_id": member.member_id_PK, "actual_deduction": "100.00"}],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400, response.content[:500])
        self.assertIn("retired", response.json()["error"].lower())

    def test_member_profiles_include_classification(self):
        self._login_treasurer()
        self._make_member("Prof Emeritus", "prof.emeritus@isu.edu.ph", "Retired")

        response = self.client.get(reverse("treasurer_member_profiles"))

        self.assertEqual(response.status_code, 200, response.content[:500])
        rows = {m["email"]: m for m in response.json()["members"]}
        self.assertEqual(rows["prof.emeritus@isu.edu.ph"]["classification"], "Retired")

    def test_is_retired_member_covers_status_and_classification(self):
        class Fake:
            def __init__(self, status, classification):
                self.membership_status = status
                self.member_classification = classification

        self.assertTrue(is_retired_member(Fake("Retired", "Teaching")))
        self.assertTrue(is_retired_member(Fake("Permanent", "Retired")))
        self.assertFalse(is_retired_member(Fake("Permanent", "Teaching")))

    def test_partial_payment_leaves_remaining_outstanding(self):
        # A member who pays less than the assessment keeps the difference as
        # outstanding — 80 collected of a 200 assessment leaves 120 owed.
        from core_system.models import MemberAssessment

        officer = self._login_treasurer()
        assessment = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1),
            total_amount=Decimal("200.00"),
            status=MonthlyAssessment.STATUS_PENDING_TREASURER,
            created_by_id_FK=officer,
        )
        dues = AssessmentItem.objects.create(
            assessment_id_FK=assessment,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"),
            priority_order=1,
        )
        aid = AssessmentItem.objects.create(
            assessment_id_FK=assessment,
            purpose=AssessmentItem.PURPOSE_MEDICAL_AID,
            amount=Decimal("100.00"),
            recipient="Some Member",
            priority_order=2,
        )
        member = self._make_member("Partial Payer", "partial.rules@isu.edu.ph", "Teaching")

        response = self.client.post(
            reverse("treasurer_record_monthly_deductions"),
            data=json.dumps({
                "assessment_id": assessment.assessment_id_PK,
                "members": [{
                    "member_id": member.member_id_PK,
                    "actual_deduction": "80.00",
                    "item_amounts": [
                        {"item_id": dues.item_id_PK, "amount": "0.00"},
                        {"item_id": aid.item_id_PK, "amount": "80.00"},
                    ],
                }],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertTrue(response.json()["ok"], response.json())
        ma = MemberAssessment.objects.get(assessment_id_FK=assessment, member_id_FK=member)
        self.assertEqual(float(ma.actual_deduction), 80.0)
        self.assertEqual(float(ma.outstanding_balance), 120.0)
