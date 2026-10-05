"""Rejection notes must reach the Treasurer's Active Entry view.

When the Auditor rejects (or the President returns) a monthly deduction with
remarks, the Treasurer's roster payload must carry those remarks so the
rejection-note banner can show exactly what to fix. This is a regression net
for the "Rejected by Auditor" workflow: the note must survive the round-trip
Auditor -> backend -> Treasurer roster, and must clear on resubmission.
"""
import json

from django.test import TestCase
from django.utils import timezone

from core_system.models import Member, MonthlyAssessment, OfficerUser
from core_system.tests import _create_zt_verified_session, deposit_monthly_batch


class RejectionNotesVisibleTests(TestCase):
    def setUp(self):
        self.members = []
        for index in range(1, 4):
            self.members.append(
                Member.objects.create(
                    full_name=f"Reject Note Member {index}",
                    employee_id=f"EMP-RN-{index:03d}",
                    department="Finance",
                    position="Staff",
                    membership_status="Permanent",
                    employment_status="Active",
                    member_type="Member",
                    email=f"rn_member_{index}@test.local",
                    date_joined=timezone.now().date(),
                )
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
            full_name=f"{role} RN Test {suffix}",
            username=f"{role.lower()}_rn_{suffix}_{timezone.now().timestamp()}",
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

    def _treasurer_records(self, assessment_id, amounts):
        self._login("Treasurer", "record")
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": assessment_id,
                "members": [
                    {"member_id": m.member_id_PK, "actual_deduction": amount}
                    for m, amount in zip(self.members, amounts)
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _treasurer_roster(self, assessment_id):
        self._login("Treasurer", "roster")
        response = self.client.get(f"/api/treasurer/deductions/members/{assessment_id}/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["ok"])
        return data

    def test_auditor_rejection_note_reaches_treasurer_roster(self):
        assessment_id = self._president_saves_assessment()
        self._treasurer_records(assessment_id, [350, 350, 350])
        deposit_monthly_batch(self.client, assessment_id)

        self._login("Auditor", "reject")
        response = self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({
                "assessment_id": assessment_id,
                "action": "reject",
                "notes": "kulang si versoza, dapat 130 sya",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        # Treasurer roster carries the auditor note for the banner.
        data = self._treasurer_roster(assessment_id)
        self.assertTrue(data["recordable"])
        self.assertEqual(data["assessment"]["status"], "rejected")
        self.assertEqual(
            data["assessment"]["auditor_remarks"],
            "kulang si versoza, dapat 130 sya",
        )

        # Overview also exposes it as the action_remarks column.
        self._login("Treasurer", "overview")
        response = self.client.get("/api/treasurer/deductions/overview/")
        by_id = {a["assessment_id"]: a for a in response.json()["assessments"]}
        self.assertEqual(
            by_id[assessment_id]["action_remarks"],
            "kulang si versoza, dapat 130 sya",
        )

        # Resubmitting clears the remarks — the banner disappears.
        self._treasurer_records(assessment_id, [350, 350, 350])
        data = self._treasurer_roster(assessment_id)
        self.assertEqual(data["assessment"]["status"], "pending_deposit")
        self.assertEqual(data["assessment"]["auditor_remarks"], "")
        assessment = MonthlyAssessment.objects.get(pk=assessment_id)
        self.assertIsNone(assessment.auditor_remarks)

    def test_president_return_note_reaches_treasurer_roster(self):
        assessment_id = self._president_saves_assessment()
        self._treasurer_records(assessment_id, [350, 350, 350])
        deposit_monthly_batch(self.client, assessment_id)

        self._login("Auditor", "verify")
        response = self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({"assessment_id": assessment_id, "action": "approve", "notes": "ok"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        self._login("President", "return")
        response = self.client.post(
            "/api/president/deductions/approve/",
            json.dumps({
                "assessment_id": assessment_id,
                "action": "return",
                "notes": "Please recheck member 3.",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        # Treasurer roster carries the president note for the banner.
        data = self._treasurer_roster(assessment_id)
        self.assertTrue(data["recordable"])
        self.assertEqual(data["assessment"]["status"], "returned")
        self.assertEqual(
            data["assessment"]["president_remarks"],
            "Please recheck member 3.",
        )
