"""Field-encryption tests: ciphertext at rest, plaintext in app, legacy passthrough."""
from django.db import connection
from django.test import TestCase

from core_system.models import MedicalAid, Member, OfficerUser


def _raw(table, column, pk_col, pk):
    with connection.cursor() as c:
        c.execute(f"SELECT {column} FROM {table} WHERE {pk_col} = %s", [pk])
        return c.fetchone()[0]


class EncryptedFieldTests(TestCase):
    def test_mfa_secret_encrypted_at_rest_plaintext_in_app(self):
        from core_system.auth_utils import hash_password
        from core_system.services.mfa_service import generate_mfa_secret

        secret = generate_mfa_secret()
        o = OfficerUser.objects.create(
            full_name="Enc Test", username="enc_test", password_hash=hash_password("Str0ng!Pass"),
            role="Treasurer", account_status="Active", mfa_secret=secret,
            email="enc@isu.edu.ph",
        )
        self.assertTrue(_raw("officer_user", "mfa_secret", "user_id_PK", o.user_id_PK).startswith("enc1:"))
        o.refresh_from_db()
        self.assertEqual(o.mfa_secret, secret)

    def test_member_contacts_encrypted_and_empty_passthrough(self):
        from datetime import date

        m = Member.objects.create(
            full_name="Enc Member", contact_number="09170000001",
            emergency_number="", employment_status="Permanent",
            membership_status="Active", date_joined=date(2024, 1, 1),
        )
        self.assertTrue(_raw("member", "contact_number", "member_id_PK", m.member_id_PK).startswith("enc1:"))
        m.refresh_from_db()
        self.assertEqual(m.contact_number, "09170000001")
        self.assertEqual(m.emergency_number, "")  # empty never encrypted

    def test_legacy_plaintext_reads_back(self):
        from datetime import date

        m = Member.objects.create(
            full_name="Legacy Member", employment_status="Permanent",
            membership_status="Active", date_joined=date(2024, 1, 1),
        )
        with connection.cursor() as c:
            c.execute(
                "UPDATE member SET contact_number = %s WHERE member_id_PK = %s",
                ["09170000002", m.member_id_PK],
            )
        m.refresh_from_db()
        self.assertEqual(m.contact_number, "09170000002")
        m.save()  # re-save encrypts
        self.assertTrue(_raw("member", "contact_number", "member_id_PK", m.member_id_PK).startswith("enc1:"))

    def test_health_reason_encrypted(self):
        from datetime import date

        m = Member.objects.create(
            full_name="Aid Member", employment_status="Permanent",
            membership_status="Active", date_joined=date(2024, 1, 1),
        )
        aid = MedicalAid.objects.create(
            member_id_FK=m, request_date=date(2024, 5, 1),
            reason_for_request="confidential diagnosis",
            hospital_bill_amount=1000, claim_year=2024,
            document_status="Pending", policy_record_status="Pending",
            validated_aid_amount=1000, status="Pending",
        )
        self.assertTrue(
            _raw("medical_aid", "reason_for_request", "medical_aid_id_PK", aid.medical_aid_id_PK).startswith("enc1:")
        )
        aid.refresh_from_db()
        self.assertEqual(aid.reason_for_request, "confidential diagnosis")
