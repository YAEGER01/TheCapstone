"""The Treasurer must see the President's uploaded attachments.

The model contract says it outright ("The Treasurer and Auditor view them
read-only"): the request letter and deduction sheet images belong to the
month, not to a role. These tests pin the treasurer roster payload to carry
the same image lists the Auditor/President review panels render, so the
"Attachments to Review" card in Active Entry always has data to show.
"""
import json

from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone

from core_system.models import (
    Member,
    MonthlyAssessment,
    MonthlyAssessmentDocument,
    OfficerUser,
)
from core_system.tests import _create_zt_verified_session


class TreasurerAttachmentsVisibleTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(
            full_name="Attachment View Member",
            employee_id="EMP-AV-001",
            department="Finance",
            position="Staff",
            membership_status="Permanent",
            employment_status="Active",
            member_type="Member",
            email="av_member@test.local",
            date_joined=timezone.now().date(),
        )
        self.assessment_payload = {
            "month": "2026-09",
            "items": [
                {"purpose": "monthly_due", "amount": 200, "priority_order": 1},
                {"purpose": "medical_aid_fund", "amount": 100, "priority_order": 2,
                 "recipient": "Josephine C. Cristobal"},
            ],
        }

    def _login(self, role, suffix):
        officer = OfficerUser.objects.create(
            full_name=f"{role} AV Test {suffix}",
            username=f"{role.lower()}_av_{suffix}_{timezone.now().timestamp()}",
            password_hash="unused",
            role=role,
            account_status="Active",
        )
        session, token = _create_zt_verified_session(officer)
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer

    def _president_saves_assessment(self):
        self._login("President", "setup")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(self.assessment_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["assessment"]["assessment_id"]

    def _attach(self, assessment_id, kind, name):
        assessment = MonthlyAssessment.objects.get(pk=assessment_id)
        return MonthlyAssessmentDocument.objects.create(
            assessment_id_FK=assessment,
            kind=kind,
            image=ContentFile(b"fake-image-bytes", name=name),
        )

    def _treasurer_roster(self, assessment_id):
        self._login("Treasurer", "roster")
        response = self.client.get(f"/api/treasurer/deductions/members/{assessment_id}/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["ok"])
        return data["assessment"]

    def test_treasurer_roster_carries_president_attachments(self):
        assessment_id = self._president_saves_assessment()
        self._attach(assessment_id, "request_letter", "letter1.png")
        self._attach(assessment_id, "request_letter", "letter2.png")
        self._attach(assessment_id, "deduction_sheet", "sheet1.png")

        assessment = self._treasurer_roster(assessment_id)
        self.assertTrue(assessment["has_request_letter"])
        self.assertTrue(assessment["has_deduction_sheet"])
        self.assertEqual(len(assessment["request_letter_images"]), 2)
        self.assertEqual(len(assessment["deduction_sheet_images"]), 1)
        for img in assessment["request_letter_images"] + assessment["deduction_sheet_images"]:
            self.assertIn("url", img)
            self.assertTrue(
                img["url"].startswith("/api/officers/monthly-assessment/documents/"),
                img["url"],
            )
            self.assertIn("name", img)
            self.assertTrue(img["name"].endswith(".png"), img["name"])
        names = [img["name"] for img in assessment["request_letter_images"]]
        self.assertTrue(any("letter1" in n for n in names))
        self.assertTrue(any("letter2" in n for n in names))

    def test_roster_without_attachments_reports_empty_lists(self):
        """No uploads -> empty lists so the frontend hides the card."""
        assessment_id = self._president_saves_assessment()
        assessment = self._treasurer_roster(assessment_id)
        self.assertFalse(assessment["has_request_letter"])
        self.assertFalse(assessment["has_deduction_sheet"])
        self.assertEqual(assessment["request_letter_images"], [])
        self.assertEqual(assessment["deduction_sheet_images"], [])
