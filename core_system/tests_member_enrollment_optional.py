import json

from django.test import TestCase
from django.urls import reverse

from core_system.auth_utils import create_access_session, hash_password
from core_system.models import Member, OfficerUser


class MemberEnrollmentOptionalFieldsTests(TestCase):
    """Member photo and contact number are optional on every enrollment path."""

    def _login_treasurer(self):
        officer = OfficerUser.objects.create(
            full_name="Treasurer Tester",
            username="treasurer_tester",
            password_hash=hash_password("TreasurerPass123!"),
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

    def test_create_member_new_without_contact_or_photo(self):
        self._login_treasurer()

        response = self.client.post(
            reverse("treasurer_create_member"),
            data={
                "first_name": "No Photo",
                "last_name": "No Contact",
                "email": "no.photo.contact@isu.edu.ph",
                "department": "CCSICT",
                "position": "Instructor",
                "membership_category": "Permanent",
                "classification": "Teaching",
                "amount": "100.00",
                "payment_method": "Cash",
            },
        )

        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertTrue(response.json()["ok"])
        member = Member.objects.get(email="no.photo.contact@isu.edu.ph")
        self.assertEqual(member.contact_number or "", "")
        self.assertFalse(bool(member.profile_picture))

    def test_create_member_new_simple_password_hidden_from_response(self):
        """Password is ISUCauFA_YYMMDD, never returned to the Treasurer's screen."""
        from django.utils import timezone
        from core_system.auth_utils import verify_password
        from core_system.models import OutgoingEmail

        self._login_treasurer()

        response = self.client.post(
            reverse("treasurer_create_member"),
            data={
                "first_name": "Simple",
                "last_name": "Password",
                "email": "simple.password@isu.edu.ph",
                "department": "CCSICT",
                "position": "Instructor",
                "membership_category": "Permanent",
                "classification": "Teaching",
                "amount": "100.00",
                "payment_method": "Cash",
            },
        )

        self.assertEqual(response.status_code, 200, response.content[:500])
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertNotIn("password", body)
        self.assertIn("check the email inbox/spam", body["message"])

        expected = "ISUCauFA_" + timezone.now().date().strftime("%y%m%d")
        officer_user = OfficerUser.objects.get(email="simple.password@isu.edu.ph")
        self.assertTrue(verify_password(expected, officer_user.password_hash))

        queued = None
        for candidate in OutgoingEmail.objects.order_by("-outgoing_email_id")[:5]:
            if "simple.password@isu.edu.ph" in (candidate.recipient_list or []):
                queued = candidate
                break
        self.assertIsNotNone(queued)
        self.assertEqual(queued.context.get("generated_password"), expected)
        self.assertTrue(
            str(queued.context.get("login_url", "")).endswith("/login/")
        )

    def test_create_member_old_without_contact_or_photo(self):
        self._login_treasurer()

        response = self.client.post(
            reverse("treasurer_create_member_old"),
            data={
                "first_name": "Old No Photo",
                "last_name": "Old No Contact",
                "email": "old.no.photo.contact@isu.edu.ph",
                "department": "CCSICT",
                "position": "Instructor",
                "membership_category": "Permanent",
                "classification": "Teaching",
            },
        )

        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertTrue(response.json()["ok"])
        member = Member.objects.get(email="old.no.photo.contact@isu.edu.ph")
        self.assertEqual(member.contact_number or "", "")
        self.assertFalse(bool(member.profile_picture))

    def test_batch_add_without_contact(self):
        self._login_treasurer()

        response = self.client.post(
            reverse("treasurer_member_batch_add"),
            data=json.dumps({
                "member_kind": "old",
                "entries": [
                    {
                        "first_name": "Batch",
                        "last_name": "NoContact",
                        "username": "batchnocontact",
                        "email": "batch.nocontact@isu.edu.ph",
                        "prof_dept": "CCSICT",
                        "prof_pos": "Instructor",
                    },
                ],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content[:500])
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["ok"], results[0])
        member = Member.objects.get(email="batch.nocontact@isu.edu.ph")
        self.assertTrue(member.contact_number in (None, ""))

    def test_batch_upload_csv_without_contact_column(self):
        self._login_treasurer()
        from django.core.files.uploadedfile import SimpleUploadedFile

        csv_content = (
            "first_name,last_name,username,email,department,position\n"
            "Csv,NoContact,csvnocontact,csv.nocontact@isu.edu.ph,CCSICT,Instructor\n"
        )
        response = self.client.post(
            reverse("treasurer_member_batch_upload"),
            data={
                "member_kind": "old",
                "file": SimpleUploadedFile("members.csv", csv_content.encode("utf-8"), content_type="text/csv"),
            },
        )

        self.assertEqual(response.status_code, 200, response.content[:500])
        payload = response.json()
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(len(payload["results"]), 1)
        self.assertTrue(payload["results"][0]["ok"], payload["results"][0])
        member = Member.objects.get(email="csv.nocontact@isu.edu.ph")
        self.assertTrue(member.contact_number in (None, ""))

    def test_create_member_new_requires_academic_rank(self):
        self._login_treasurer()

        response = self.client.post(
            reverse("treasurer_create_member"),
            data={
                "first_name": "No",
                "last_name": "Rank",
                "email": "no.rank@isu.edu.ph",
                "department": "CCSICT",
                "position": "",
                "membership_category": "Permanent",
                "classification": "Teaching",
                "amount": "100.00",
                "payment_method": "Cash",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Academic Rank", response.json()["error"])
        self.assertFalse(Member.objects.filter(email="no.rank@isu.edu.ph").exists())

    def test_create_member_old_requires_academic_rank(self):
        self._login_treasurer()

        response = self.client.post(
            reverse("treasurer_create_member_old"),
            data={
                "first_name": "Old No",
                "last_name": "Rank",
                "email": "old.no.rank@isu.edu.ph",
                "department": "CCSICT",
                "position": "",
                "membership_category": "Permanent",
                "classification": "Teaching",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Academic Rank", response.json()["error"])
        self.assertFalse(Member.objects.filter(email="old.no.rank@isu.edu.ph").exists())

    def test_batch_add_requires_academic_rank(self):
        self._login_treasurer()

        response = self.client.post(
            reverse("treasurer_member_batch_add"),
            data=json.dumps({
                "member_kind": "old",
                "entries": [
                    {
                        "first_name": "Batch",
                        "last_name": "NoRank",
                        "username": "batchnorank",
                        "email": "batch.norank@isu.edu.ph",
                        "prof_dept": "CCSICT",
                        "prof_pos": "",
                    },
                ],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["ok"])
        self.assertIn("Academic Rank", results[0]["error"])
        self.assertFalse(Member.objects.filter(email="batch.norank@isu.edu.ph").exists())
