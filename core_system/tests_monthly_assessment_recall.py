import json
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_system.auth_utils import create_access_session, hash_password
from core_system.models import (
    AssessmentWorkflowLog,
    Member,
    MonthlyAssessment,
    MonthlyAssessmentDocument,
    OfficerUser,
)


class PresidentRecallAssessmentTests(TestCase):
    def _login(self, role="President", username="president_recall"):
        officer = OfficerUser.objects.create(
            full_name="Recall Tester",
            username=username,
            password_hash=hash_password("RecallPass123!"),
            role=role,
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

    def _make_assessment(self, officer, status):
        return MonthlyAssessment.objects.create(
            month=date(2026, 9, 1),
            total_amount=Decimal("100.00"),
            status=status,
            created_by_id_FK=officer,
        )

    def _recall(self, assessment_id):
        return self.client.post(
            reverse("president_monthly_assessment_recall"),
            data=json.dumps({"assessment_id": assessment_id}),
            content_type="application/json",
        )

    def test_recall_pending_returns_to_draft(self):
        officer = self._login()
        assessment = self._make_assessment(officer, MonthlyAssessment.STATUS_PENDING_TREASURER)

        response = self._recall(assessment.assessment_id_PK)

        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertTrue(response.json()["ok"])
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, MonthlyAssessment.STATUS_DRAFT)
        self.assertTrue(
            AssessmentWorkflowLog.objects.filter(
                assessment_id_FK=assessment, action="president_recall"
            ).exists()
        )

    def test_recalled_month_can_be_edited_again(self):
        officer = self._login()
        assessment = self._make_assessment(officer, MonthlyAssessment.STATUS_PENDING_TREASURER)
        self._recall(assessment.assessment_id_PK)

        response = self.client.post(
            reverse("president_save_monthly_assessment"),
            data=json.dumps({
                "month": "2026-09",
                "draft": True,
                "items": [{"purpose": "monthly_due", "amount": "150.00"}],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertTrue(response.json()["ok"])
        assessment.refresh_from_db()
        self.assertEqual(assessment.total_amount, Decimal("150.00"))

    def test_recall_draft_is_rejected(self):
        officer = self._login()
        assessment = self._make_assessment(officer, MonthlyAssessment.STATUS_DRAFT)

        response = self._recall(assessment.assessment_id_PK)

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["ok"])

    def test_recall_missing_is_not_found(self):
        self._login()

        response = self._recall(999999)

        self.assertEqual(response.status_code, 404)

    def test_recall_requires_president(self):
        officer = self._login(role="Treasurer", username="treasurer_recall")
        assessment = self._make_assessment(officer, MonthlyAssessment.STATUS_PENDING_TREASURER)

        response = self._recall(assessment.assessment_id_PK)

        self.assertNotEqual(response.status_code, 200)
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, MonthlyAssessment.STATUS_PENDING_TREASURER)

    def _make_document(self, assessment, officer):
        return MonthlyAssessmentDocument.objects.create(
            assessment_id_FK=assessment,
            kind=MonthlyAssessmentDocument.KIND_REQUEST_LETTER,
            image=SimpleUploadedFile("letter.png", b"\x89PNG\r\n\x1a\n", content_type="image/png"),
            uploaded_by_id_FK=officer,
        )

    def test_delete_document_from_draft_is_allowed(self):
        officer = self._login()
        assessment = self._make_assessment(officer, MonthlyAssessment.STATUS_DRAFT)
        doc = self._make_document(assessment, officer)

        response = self.client.post(
            reverse("president_delete_assessment_document", kwargs={"document_id": doc.document_id_PK})
        )

        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertTrue(response.json()["ok"])
        self.assertFalse(MonthlyAssessmentDocument.objects.filter(pk=doc.document_id_PK).exists())

    def test_delete_document_from_submitted_still_allowed(self):
        # Attachments stay manageable after submit (a wrong scan can be
        # fixed); only the money breakdown locks. Matches the legacy
        # AssessmentDocumentUploadTests behavior.
        officer = self._login()
        assessment = self._make_assessment(officer, MonthlyAssessment.STATUS_PENDING_TREASURER)
        doc = self._make_document(assessment, officer)

        response = self.client.post(
            reverse("president_delete_assessment_document", kwargs={"document_id": doc.document_id_PK})
        )

        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertTrue(response.json()["ok"])
        self.assertFalse(MonthlyAssessmentDocument.objects.filter(pk=doc.document_id_PK).exists())


class TreasurerDeductionMembersTests(TestCase):
    """Regression: the treasurer member roster must not 500 (wrong model was
    referenced for the monthly-due purpose constant)."""

    def test_members_roster_loads_for_submitted_assessment(self):
        from core_system.models import AssessmentItem

        officer = OfficerUser.objects.create(
            full_name="Roster Treasurer",
            username="roster_treasurer",
            password_hash=hash_password("RosterPass123!"),
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

        assessment = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1),
            total_amount=Decimal("250.00"),
            status=MonthlyAssessment.STATUS_PENDING_TREASURER,
            created_by_id_FK=officer,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=assessment,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"),
            priority_order=1,
        )
        Member.objects.create(
            full_name="Roster Member",
            employment_status="Active",
            membership_status="Permanent",
            member_type="",
            date_joined=timezone.now().date(),
        )

        response = self.client.get(
            reverse(
                "treasurer_monthly_deduction_members",
                kwargs={"assessment_id": assessment.assessment_id_PK},
            )
        )

        self.assertEqual(response.status_code, 200, response.content[:500])
        payload = response.json()
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(len(payload["members"]), 1)
        self.assertEqual(payload["members"][0]["monthly_due_per_member"], 100.0)
