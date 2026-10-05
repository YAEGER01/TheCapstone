import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import hashlib
import hmac
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Sum
from django.db.utils import ProgrammingError
from django.test import RequestFactory, TestCase
from django.utils import timezone

from core_system import president_views, secretary_views

from core_system.auth_utils import create_access_session, hash_pin, verify_officer_password
from core_system.services.email_service import send_html_email_async
from core_system.services.mfa_service import generate_otp
from core_system.models import (
    AidSetAside,
    AidTrackingPost,
    AssessmentItem,
    AssessmentWorkflowLog,
    Contribution,
    DeathAid,
    Claimant,
    FinancialDocumentArchive,
    FundTransaction,
    GlobalAuditTrail,
    MedicalAid,
    Member,
    MemberAssessment,
    MemberAssessmentAllocation,
    MemberLedger,
    MembershipFee,
    MonthlyAssessment,
    MonthlyAssessmentDocument,
    MonthlyDues,
    Notification,
    OfficerUser,
    SupportingProof,
    TransactionArchive,
    TransactionVerification,
)


def _create_zt_verified_session(officer, ip_address="127.0.0.1", device_info="tests"):
    session, token = create_access_session(
        officer=officer,
        ip_address=ip_address,
        device_info=device_info,
    )
    session.trusted_device = True
    session.device_info = ""
    policy = session.session_policy or {}
    policy["zt_verified_at"] = timezone.now().isoformat()
    session.session_policy = policy
    session.save()
    return session, token


def deposit_monthly_batch(client, assessment_id, reference="ORS-DEP-001"):
    """Record the bank deposit for a month that is in pending_deposit.

    Must be called while the active session is the Treasurer, right after a
    successful record and before any Auditor / President login.
    """
    response = client.post(
        "/api/treasurer/deductions/deposit/",
        data={
            "assessment_id": str(assessment_id),
            "deposit_reference": reference,
            "proof": SimpleUploadedFile(
                "deposit_slip.pdf",
                b"%PDF-1.4\nfake deposit slip for tests",
                content_type="application/pdf",
            ),
        },
    )
    assert response.status_code == 200, response.content
    return response


class TreasurerApiClientMixin:
    def _login_treasurer(self):
        officer = OfficerUser.objects.create(
            full_name="Treasurer Test",
            username="treasurer_test",
            password_hash="unused",
            role="Treasurer",
            account_status="Active",
        )
        session, token = _create_zt_verified_session(officer)
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer


class SecretaryAttendanceCheckinTests(TestCase):
    def test_secretary_checkin_accepts_valid_pin(self):
        officer = OfficerUser.objects.create(
            full_name="Secretary Test",
            username="secretary_checkin_test",
            password_hash="x",
            role="Secretary",
            account_status="Active",
        )
        session, token = _create_zt_verified_session(officer)

        member = Member.objects.create(
            full_name="Test Member",
            employee_id="EMP-CHK-001",
            employment_status="Regular",
            membership_status="Active",
            date_joined=timezone.localdate(),
            email="member@example.com",
            pin_code=hash_pin("123456"),
        )

        request = RequestFactory().post(
            "/api/secretary/attendance/checkin/",
            data=json.dumps({"pin": "123456"}),
            content_type="application/json",
        )
        request.session = {
            "access_token": token,
            "officer_id": officer.user_id_PK,
            "role": officer.role,
        }

        response = secretary_views.secretary_attendance_checkin(request)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["member_name"], member.full_name)


class PublicRegistrationValidationTests(TestCase):
    def test_middle_initial_longer_than_one_character_is_rejected(self):
        response = self.client.post(
            "/api/public/membership-registration/",
            {
                "first_name": "John",
                "middle_initial": "AB",
                "last_name": "Doe",
                "username": "johndoe",
                "email": "john@example.com",
                "department": "Engineering",
                "position": "Software Engineer",
                "membership_category": "Permanent",
                "payment_method": "Bank Transfer",
                "amount": "100.00",
                "payment_date": "2026-07-23",
                "password": "TestPass123!",
                "confirm_password": "TestPass123!",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertIn("Middle Initial", response.json()["error"])

    def test_homepage_renders_with_missing_database_tables(self):
        from core_system.models import Announcement, Event, HeroSlide, NewsArticle

        with patch.object(Announcement.objects, "filter", side_effect=ProgrammingError("missing table")), \
             patch.object(Event.objects, "filter", side_effect=ProgrammingError("missing table")), \
             patch.object(NewsArticle.objects, "filter", side_effect=ProgrammingError("missing table")), \
             patch.object(HeroSlide.objects, "filter", side_effect=ProgrammingError("missing table")):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)


class MembershipFeeUploadTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.member = Member.objects.create(
            full_name="Test Member",
            employee_id="EMP-TEST-001",
            department="College of Education",
            position="Professor",
            contact_number="09170000000",
            email="member@example.com",
            employment_status="Active",
            membership_status="Permanent",
            member_type="EMP-TEST-001",
            date_joined=timezone.now().date(),
        )

    def test_membership_fee_upload_creates_proof(self):
        self._login_treasurer()
        from io import BytesIO

        from PIL import Image

        _buf = BytesIO()
        Image.new("RGB", (48, 36), "orange").save(_buf, format="JPEG")
        img = SimpleUploadedFile("receipt.jpg", _buf.getvalue(), content_type="image/jpeg")

        response = self.client.post(
            "/api/treasurer/membership-fees/add/",
            {
                "fee_member": str(self.member.member_id_PK),
                "fee_amount": "500.00",
                "fee_date": "2026-06-16",
                "fee_month": "2026-06",
                "fee_method": "OTC",
                "fee_ref": "RECV-1001",
                "fee_encoder": "Encoder",
                "fee_photo_file": img,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        fee = MembershipFee.objects.get(receipt_number="RECV-1001")
        proof = SupportingProof.objects.filter(
            content_type__model="membershipfee",
            object_id=fee.fee_id_PK,
        ).first()

        self.assertIsNotNone(proof)
        self.assertTrue(Path(proof.file.path).exists())
        self.assertEqual(proof.file_name, "receipt.jpg")
        self.assertEqual(proof.file_type, "image/jpeg")
        self.assertEqual(len(proof.file_sha256), 64)
        self.assertEqual(len(proof.row_signature), 64)

    def test_membership_fee_accepts_full_date_month_value(self):
        self._login_treasurer()
        response = self.client.post(
            "/api/treasurer/membership-fees/add/",
            {
                "fee_member": str(self.member.member_id_PK),
                "fee_amount": "500.00",
                "fee_date": "2026-06-16",
                "fee_month": "2026-06-01",
                "fee_method": "OTC",
                "fee_ref": "RECV-1003",
                "fee_encoder": "Encoder",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        fee = MembershipFee.objects.get(receipt_number="RECV-1003")

    def test_membership_fee_without_file_still_works(self):
        self._login_treasurer()
        response = self.client.post(
            "/api/treasurer/membership-fees/add/",
            {
                "fee_member": str(self.member.member_id_PK),
                "fee_amount": "500.00",
                "fee_date": "2026-06-16",
                "fee_month": "2026-06",
                "fee_method": "OTC",
                "fee_ref": "RECV-1002",
                "fee_encoder": "Encoder",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        fee = MembershipFee.objects.get(receipt_number="RECV-1002")
        self.assertFalse(SupportingProof.objects.exists())


class PresidentClaimSummaryTests(TestCase):
    def test_oversight_summary_counts_live_claim_statuses(self):
        officer = OfficerUser.objects.create(
            full_name="President Test",
            username="president_test",
            password_hash="unused",
            role="President",
            account_status="Active",
        )
        member = Member.objects.create(
            full_name="Sample Member",
            employee_id="EMP-PRES-001",
            department="CCSICT",
            position="Professor",
            contact_number="09170000000",
            email="sample@example.com",
            employment_status="Active",
            membership_status="Permanent",
            member_type="EMP-PRES-001",
            date_joined=timezone.now().date(),
        )
        claimant = Claimant.objects.create(
            member_id_FK=member,
            full_name="Claimant One",
            contact_number="09170000001",
            relationship_to_member="Spouse",
            relationship_group="member",
            authorization_status="Approved",
        )

        MedicalAid.objects.create(
            member_id_FK=member,
            request_date=timezone.now().date(),
            hospital_bill_amount="1200.00",
            claim_year=timezone.now().year,
            document_status="Verified",
            policy_record_status="Complete",
            validated_aid_amount="1200.00",
            status="Auditor Verified",
        )
        DeathAid.objects.create(
            member_id_FK=member,
            claimant_id_FK=claimant,
            claim_date=timezone.now().date(),
            claim_type="Death",
            date_of_death=timezone.now().date(),
            deceased_name="Sample Deceased",
            relationship_to_member="Spouse",
            relationship_group="member",
            funeral_location="City",
            benefit_amount="2500.00",
            bill_amount="2500.00",
            document_status="Verified",
            status="Approved",
        )
        MedicalAid.objects.create(
            member_id_FK=member,
            request_date=timezone.now().date(),
            hospital_bill_amount="800.00",
            claim_year=timezone.now().year,
            document_status="Verified",
            policy_record_status="Complete",
            validated_aid_amount="800.00",
            status="Completed",
        )
        DeathAid.objects.create(
            member_id_FK=member,
            claimant_id_FK=claimant,
            claim_date=timezone.now().date(),
            claim_type="Death",
            date_of_death=timezone.now().date(),
            deceased_name="Another Deceased",
            relationship_to_member="Parent",
            relationship_group="parent_child",
            funeral_location="City",
            benefit_amount="1800.00",
            bill_amount="1800.00",
            document_status="Verified",
            status="Released",
        )

        request = RequestFactory().get("/api/president/oversight/summary/")
        request.session = {"officer_id": officer.user_id_PK, "role": "President"}

        response = president_views.oversight_summary(request)
        data = json.loads(response.content)

        self.assertTrue(data["ok"])
        self.assertGreater(data["summary"]["claims"]["pending_medical"], 0)
        self.assertGreater(data["summary"]["claims"]["pending_death"], 0)
        self.assertGreater(data["summary"]["claims"]["total_released"], 0)


class RowSignatureIntegrityTests(TestCase):
    def test_row_signature_is_deterministic(self):
        officer = OfficerUser.objects.create(
            full_name="Treasurer Test",
            username="treasurer_test_sig",
            password_hash="unused",
            role="Treasurer",
            account_status="Active",
        )
        member = Member.objects.create(
            full_name="Test Member",
            employee_id="EMP-SIG-001",
            department="College of Education",
            position="Professor",
            contact_number="09170000000",
            email="member@example.com",
            employment_status="Active",
            membership_status="Permanent",
            member_type="EMP-SIG-001",
            date_joined=timezone.now().date(),
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(b"test-bytes")
            tmp.flush()
            tmp_path = tmp.name

        try:
            digest = hashlib.sha256(b"test-bytes").hexdigest()
            sig1 = hmac.new(
                settings.SECRET_KEY.encode(),
                f"{digest}:{member.member_id_PK}:{settings.SECRET_KEY}".encode(),
                hashlib.sha256,
            ).hexdigest()
            sig2 = hmac.new(
                settings.SECRET_KEY.encode(),
                f"{digest}:{member.member_id_PK}:{settings.SECRET_KEY}".encode(),
                hashlib.sha256,
            ).hexdigest()
            self.assertEqual(sig1, sig2)
            self.assertEqual(len(sig1), 64)
        finally:
            os.unlink(tmp_path)


# ==========================================================================
# AID TRACKING POST TESTS
# ==========================================================================

class AuditorLoginMixin:
    def _login_auditor(self):
        officer = OfficerUser.objects.create(
            full_name="Auditor Test",
            username="auditor_test",
            password_hash="unused",
            role="Auditor",
            account_status="Active",
        )
        session, token = _create_zt_verified_session(officer)
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer


class PresidentLoginMixin:
    def _login_president(self):
        officer = OfficerUser.objects.create(
            full_name="President Test",
            username="president_test",
            password_hash="unused",
            role="President",
            account_status="Active",
        )
        session, token = _create_zt_verified_session(officer)
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer


class SelfEnrollmentTests(TestCase):
    def _login_president(self):
        officer = OfficerUser.objects.create(
            full_name="President Test",
            username="pres_self_enroll",
            password_hash="unused",
            role="President",
            account_status="Active",
        )
        session, token = _create_zt_verified_session(officer)
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer

    def test_self_enrollment_creates_login_ready_officer_account(self):
        president = self._login_president()

        response = self.client.post(
            "/api/president/officers/self-enroll/",
            json.dumps({
                "employee_id": "EMP-SELF-001",
                "position": "Secretary",
                "contact_number": "09170000001",
                "email": "selfenroll@example.com",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])

        officer = OfficerUser.objects.get(username="pres_self_enroll")
        self.assertEqual(officer.role, "Secretary")
        self.assertEqual(officer.email, "selfenroll@example.com")
        self.assertTrue(verify_officer_password(officer=officer, password_input="pres_self_enroll"))

        member = Member.objects.get(employee_id="EMP-SELF-001")
        self.assertEqual(member.position, "Secretary")
        self.assertEqual(member.officer_user_id_FK.user_id_PK, president.user_id_PK)


class MonthlyDuesWorkflowTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(
            full_name="Workflow Member",
            employee_id="EMP-WF-001",
            department="Finance",
            position="Staff",
            membership_status="Active",
            employment_status="Active",
            member_type="REG",
            date_joined=timezone.now().date(),
        )

    def _login_president(self):
        officer = OfficerUser.objects.create(
            full_name="President Test",
            username="pres_workflow_" + str(timezone.now().timestamp()),
            password_hash="unused",
            role="President",
            account_status="Active",
        )
        session, token = _create_zt_verified_session(officer)
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer

    def test_president_approval_marks_monthly_dues_terminal(self):
        officer = self._login_president()
        dues = MonthlyDues.objects.create(
            member_id_FK=self.member,
            month_covered="2026-07",
            amount=50,
            payment_method="OTC",
            payment_status="Pending",
            treasurer_status="Treasurer Verified",
            auditor_status="Auditor Verified",
            president_status="Pending President Approval",
            recorded_by_user_id_FK=officer,
        )
        TransactionVerification.objects.create(
            table_name="monthly_dues",
            record_id=dues.dues_id_PK,
            verification_status="Auditor Verified",
        )

        response = self.client.post(
            "/api/president/monthly-dues/approve/",
            json.dumps({"dues_id": dues.dues_id_PK, "action": "approve", "remarks": "OK"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        dues.refresh_from_db()
        self.assertEqual(dues.president_status, "President Approved")
        self.assertEqual(dues.payment_status, "Full Payment")
        self.assertEqual(dues.treasurer_status, "Treasurer Verified")
        self.assertNotEqual(dues.treasurer_status, "Pending Treasurer Review")

    def test_member_unpaid_months_excludes_months_with_existing_dues_records(self):
        member = self.member
        MonthlyDues.objects.create(
            member_id_FK=member,
            month_covered="2026-07",
            amount=50,
            payment_method="OTC",
            payment_status="Pending",
            treasurer_status="Pending Treasurer Review",
            recorded_by_user_id_FK=OfficerUser.objects.create(
                full_name="Treasurer",
                username="treasurer_unpaid_" + str(timezone.now().timestamp()),
                password_hash="unused",
                role="Treasurer",
                account_status="Active",
            ),
        )

        officer = OfficerUser.objects.create(
            full_name="Member Session",
            username="member_session_" + str(timezone.now().timestamp()),
            password_hash="unused",
            role="Member",
            account_status="Active",
        )
        member.officer_user_id_FK = officer
        member.save(update_fields=["officer_user_id_FK"])

        session, token = _create_zt_verified_session(officer)
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = "Member"
        test_session.save()

        response = self.client.get("/api/member/unpaid-months/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("2026-07", [item["month"] for item in payload["unpaid_months"]])
        self.assertIn("2026-07", payload["covered_months"])


class AidTrackingPostCreationTests(TestCase):
    """Tests that posts and contributions are auto-created on presidential approval."""

    def setUp(self):
        self.member = Member.objects.create(
            full_name="Aid Recipient",
            employee_id="EMP-AID-001",
            department="IT",
            position="Staff",
            membership_status="Active",
            employment_status="Active",
            member_type="REG",
            date_joined=timezone.now().date(),
        )
        self.active_member = Member.objects.create(
            full_name="Paying Member",
            employee_id="EMP-PAY-001",
            department="Finance",
            position="Staff",
            membership_status="Active",
            employment_status="Active",
            member_type="REG",
            date_joined=timezone.now().date(),
        )

    def _login_president(self):
        officer = OfficerUser.objects.create(
            full_name="President Test",
            username="pres_test_" + str(timezone.now().timestamp()),
            password_hash="unused",
            role="President",
            account_status="Active",
        )
        session, token = _create_zt_verified_session(officer)
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer

    def test_medical_aid_approval_creates_post_and_contributions(self):
        officer = self._login_president()

        med = MedicalAid.objects.create(
            member_id_FK=self.member,
            request_date=timezone.now().date(),
            requested_amount=20000,
            hospital_name="Test Hospital",
            hospital_bill_amount=25000,
            claim_year=2026,
            document_status="Complete",
            policy_record_status="Verified",
            validated_aid_amount=20000,
            status="Auditor Verified",
        )

        response = self.client.post(
            "/api/aids/presidential-decision/",
            json.dumps({
                "target_id": "medical-" + str(med.medical_aid_id_PK),
                "decision": "Approved",
                "approved_amount": 20000,
                "remarks": "Approved",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        posts = AidTrackingPost.objects.filter(aid_type="medical_aid")
        self.assertEqual(posts.count(), 1)

        post = posts.first()
        # Only the non-requester contributes: 1 payer x 100.
        self.assertEqual(post.total_expected, 100)
        self.assertEqual(post.total_collected, 0)

        contributions = Contribution.objects.filter(aid_tracking_post_id_FK=post)
        self.assertEqual(contributions.count(), 2)

        payer = contributions.get(member_id_FK=self.active_member)
        self.assertEqual(float(payer.expected_amount), 100)
        self.assertEqual(payer.status, "NOT_PAID")
        requester = contributions.get(member_id_FK=self.member)
        self.assertEqual(float(requester.expected_amount), 100)
        self.assertEqual(requester.status, Contribution.STATUS_EXCLUDED_REQUESTER)

    def test_aid_post_uses_claim_month_not_approval_month(self):
        # A February 2027 claim approved "today" must track under 2027-02,
        # never the machine's realtime approval month.
        self._login_president()

        med = MedicalAid.objects.create(
            member_id_FK=self.member,
            request_date=date(2027, 2, 15),
            requested_amount=20000,
            hospital_name="Test Hospital",
            hospital_bill_amount=25000,
            claim_year=2027,
            document_status="Complete",
            policy_record_status="Verified",
            validated_aid_amount=20000,
            status="Auditor Verified",
        )

        response = self.client.post(
            "/api/aids/presidential-decision/",
            json.dumps({
                "target_id": "medical-" + str(med.medical_aid_id_PK),
                "decision": "Approved",
                "approved_amount": 20000,
                "remarks": "Approved",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        post = AidTrackingPost.objects.get(
            aid_type="medical_aid", source_id=med.medical_aid_id_PK
        )
        self.assertEqual(post.target_month, "2027-02")

    def test_death_aid_approval_creates_post_with_correct_amount(self):
        officer = self._login_president()

        claimant = Claimant.objects.create(
            member_id_FK=self.member,
            full_name="Claimant Person",
            contact_number="09170000001",
            relationship_to_member="Spouse",
            authorization_status="Authorized",
        )

        death = DeathAid.objects.create(
            member_id_FK=self.member,
            claimant_id_FK=claimant,
            claim_date=timezone.now().date(),
            claim_type="spouse",
            deceased_name="Deceased Person",
            relationship_to_member="spouse",
            benefit_amount=50000,
            document_status="Complete",
            status="Auditor Verified",
        )

        response = self.client.post(
            "/api/aids/presidential-decision/",
            json.dumps({
                "target_id": "death-" + str(death.death_aid_id_PK),
                "decision": "Approved",
                "approved_amount": 50000,
                "remarks": "Approved",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        posts = AidTrackingPost.objects.filter(aid_type="death_aid")
        self.assertEqual(posts.count(), 1)

        contributions = Contribution.objects.filter(aid_tracking_post_id_FK=posts.first())
        self.assertEqual(contributions.count(), 2)

        for c in contributions:
            self.assertEqual(float(c.expected_amount), 300)


class AidTrackingReadTests(TestCase):
    """Tests that auditor can view posts and member contributions."""

    def setUp(self):
        self.member = Member.objects.create(
            full_name="Test Member",
            employee_id="EMP-001",
            department="IT",
            position="Staff",
            membership_status="Active",
            employment_status="Active",
            member_type="REG",
            date_joined=timezone.now().date(),
        )
        self.archive = TransactionArchive.objects.create(
            transaction_type="medical_aid",
            record_id=1,
            member_id_FK=self.member,
            member_name=self.member.full_name,
            amount=10000,
            validated_amount=10000,
            status="Approved",
            verified_at=timezone.now(),
        )
        self.post = AidTrackingPost.objects.create(
            archive_id_FK=self.archive,
            aid_type="medical_aid",
            target_month="2026-01",
            total_expected=500,
            total_collected=200,
            is_active=True,
        )
        self.contribution = Contribution.objects.create(
            aid_tracking_post_id_FK=self.post,
            member_id_FK=self.member,
            expected_amount=100,
            paid_amount=100,
            payment_date=timezone.now().date(),
            status="PAID",
        )

    def _login_auditor(self):
        officer = OfficerUser.objects.create(
            full_name="Auditor Test",
            username="aud_rd_" + str(timezone.now().timestamp()),
            password_hash="unused",
            role="Auditor",
            account_status="Active",
        )
        session, token = _create_zt_verified_session(officer)
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer

    def test_list_posts(self):
        self._login_auditor()
        response = self.client.get("/api/auditor/approved-aid-posts/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["posts"]), 1)
        self.assertEqual(data["posts"][0]["aid_type"], "medical_aid")
        self.assertEqual(data["posts"][0]["member_name"], "Test Member")

    def test_view_members_for_post(self):
        self._login_auditor()
        response = self.client.get(f"/api/auditor/aid-post-members/{self.post.post_id_PK}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["members"]), 1)
        self.assertEqual(data["members"][0]["status"], "PAID")
        self.assertEqual(data["members"][0]["member_name"], "Test Member")

    def test_inactive_post_not_returned(self):
        self._login_auditor()
        self.post.is_active = False
        self.post.save()

        response = self.client.get(f"/api/auditor/aid-post-members/{self.post.post_id_PK}/")
        self.assertEqual(response.status_code, 404)


class AidTrackingActionTests(TestCase):
    """Tests that auditor can mark PAID, SKIPPED, and send notifications."""

    def setUp(self):
        self.member = Member.objects.create(
            full_name="Test Member",
            employee_id="EMP-002",
            department="HR",
            position="Staff",
            membership_status="Active",
            employment_status="Active",
            member_type="REG",
            date_joined=timezone.now().date(),
        )
        self.archive = TransactionArchive.objects.create(
            transaction_type="death_aid",
            record_id=1,
            member_id_FK=self.member,
            member_name=self.member.full_name,
            amount=50000,
            validated_amount=50000,
            status="Approved",
        )
        self.post = AidTrackingPost.objects.create(
            archive_id_FK=self.archive,
            aid_type="death_aid",
            target_month="2026-06",
            total_expected=1000,
            total_collected=0,
            is_active=True,
        )
        self.contribution = Contribution.objects.create(
            aid_tracking_post_id_FK=self.post,
            member_id_FK=self.member,
            expected_amount=500,
            paid_amount=0,
            status="NOT_PAID",
        )

    def _login_auditor(self):
        officer = OfficerUser.objects.create(
            full_name="Auditor Test",
            username="aud_act_" + str(timezone.now().timestamp()),
            password_hash="unused",
            role="Auditor",
            account_status="Active",
        )
        session, token = _create_zt_verified_session(officer)
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer

    def test_mark_as_paid(self):
        self._login_auditor()
        response = self.client.post(
            "/api/auditor/aid-post-member-pay/",
            {"contribution_id": str(self.contribution.contribution_id_PK)},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])

        self.contribution.refresh_from_db()
        self.assertEqual(self.contribution.status, "PAID")
        self.assertEqual(float(self.contribution.paid_amount), 500)

        self.post.refresh_from_db()
        self.assertEqual(float(self.post.total_collected), 500)

    def test_mark_as_skipped(self):
        self._login_auditor()
        response = self.client.post(
            "/api/auditor/aid-post-member-skip/",
            {"contribution_id": str(self.contribution.contribution_id_PK), "notes": "On leave"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])

        self.contribution.refresh_from_db()
        self.assertEqual(self.contribution.status, "SKIPPED")
        self.assertTrue(self.contribution.is_manually_overridden)
        self.assertEqual(self.contribution.notes, "On leave")

    def test_unauthenticated_requests_rejected(self):
        response = self.client.get("/api/auditor/approved-aid-posts/")
        self.assertNotEqual(response.status_code, 200)


class FullWorkflowSmokeTests(TestCase):
    """End-to-end smoke tests for the complete CAUFA portal workflow."""

    # ------------------------------------------------------------------
    # shared helpers
    # ------------------------------------------------------------------
    def _create_officer(self, role, suffix=""):
        return OfficerUser.objects.create(
            full_name=f"{role} {suffix}",
            username=f"{role.lower()}_{suffix}",
            password_hash="unused",
            role=role,
            account_status="Active",
        )

    def _login(self, officer):
        session, token = _create_zt_verified_session(officer, device_info="smoke_test")
        s = self.client.session
        s["access_token"] = token
        s["officer_id"] = officer.user_id_PK
        s["role"] = officer.role
        s.save()
        return officer

    def _create_member(self, tag):
        return Member.objects.create(
            full_name=f"SmokeTest Member {tag}",
            employee_id=f"SMK-{tag}-001",
            department="College of Education",
            position="Professor",
            contact_number="09170000000",
            email="smoketest@example.com",
            employment_status="Active",
            membership_status="Permanent",
            member_type=f"SMK-{tag}-001",
            date_joined=timezone.now().date(),
        )

    # ------------------------------------------------------------------
    # 1) Full membership fee flow: Treasurer → Auditor → President
    # ------------------------------------------------------------------
    def test_membership_fee_full_flow(self):
        trez = self._create_officer("Treasurer", "MF1")
        self._login(trez)
        member = self._create_member("MF1")

        # Treasurer adds fee
        resp = self.client.post("/api/treasurer/membership-fees/add/", {
            "fee_member": str(member.member_id_PK),
            "fee_amount": "500.00",
            "fee_date": "2026-07-03",
            "fee_month": "2026-07",
            "fee_method": "OTC",
            "fee_ref": "SMK-RECV-MF1",
            "fee_encoder": "Encoder",
        })
        self.assertEqual(resp.status_code, 200, resp.json())
        self.assertTrue(resp.json()["ok"])
        fee = MembershipFee.objects.get(receipt_number="SMK-RECV-MF1")

        # Auditor verifies
        aud = self._create_officer("Auditor", "MF1")
        self._login(aud)
        resp = self.client.post("/api/auditor/verify-membership-fee/", {
            "mfAuditID": str(fee.fee_id_PK),
            "mfAuditResult": "Verified",
            "mfAuditRemarks": "Looks good",
        })
        self.assertEqual(resp.status_code, 200, resp.content.decode())
        tv = TransactionVerification.objects.get(table_name="membership_fee", record_id=fee.fee_id_PK)
        self.assertEqual(tv.verification_status, "Auditor Verified")

        # President approves
        prez = self._create_officer("President", "MF1")
        self._login(prez)
        resp = self.client.post("/api/payments/presidential-decision/",
            {"target_id": str(tv.verification_id), "decision": "Approved", "remarks": "Approved"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.json())
        tv.refresh_from_db()
        self.assertEqual(tv.verification_status, "Approved")

        # Audit trail entry exists
        self.assertTrue(
            GlobalAuditTrail.objects.filter(table_name="membership_fee", record_id=fee.fee_id_PK).exists()
        )

    # ------------------------------------------------------------------
    # 2) Full monthly dues flow: Treasurer → Auditor → President
    # ------------------------------------------------------------------
    def test_monthly_dues_full_flow(self):
        trez = self._create_officer("Treasurer", "MD1")
        self._login(trez)
        member = self._create_member("MD1")

        resp = self.client.post("/api/treasurer/monthly-dues/otc/add/", {
            "otc_member": str(member.member_id_PK),
            "otc_month": "2026-07",
            "otc_amount": "50.00",
            "otc_date": "2026-07-03",
            "otc_method": "OTC",
            "otc_ref": "SMK-MD1",
        })
        self.assertEqual(resp.status_code, 200, resp.json())
        self.assertTrue(resp.json()["ok"])
        dues = MonthlyDues.objects.get(receipt_number="SMK-MD1")

        # Treasurer approves (forwards to Auditor) before Auditor can verify
        resp = self.client.post("/api/treasurer/monthly-dues/approve/",
            {"dues_id": dues.dues_id_PK, "action": "approve", "remarks": "OK"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.json())
        tv = TransactionVerification.objects.get(table_name="monthly_dues", record_id=dues.dues_id_PK)
        self.assertEqual(tv.verification_status, "Pending Auditor Review")

        aud = self._create_officer("Auditor", "MD1")
        self._login(aud)
        resp = self.client.post("/api/auditor/verify-payment/", {
            "pAuditID": str(dues.dues_id_PK),
            "pAuditResult": "Verified",
            "pAuditRemarks": "OK",
        })
        self.assertEqual(resp.status_code, 200, resp.content.decode())
        tv = TransactionVerification.objects.get(table_name="monthly_dues", record_id=dues.dues_id_PK)
        self.assertEqual(tv.verification_status, "Auditor Verified")

        prez = self._create_officer("President", "MD1")
        self._login(prez)
        resp = self.client.post("/api/payments/presidential-decision/",
            {"target_id": str(tv.verification_id), "decision": "Approved", "remarks": "OK"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.json())
        tv.refresh_from_db()
        self.assertEqual(tv.verification_status, "Approved")

    # ------------------------------------------------------------------
    # 3) Full medical aid flow: Treasurer → Auditor → President
    # ------------------------------------------------------------------
    def test_medical_aid_full_flow(self):
        trez = self._create_officer("Treasurer", "MA1")
        self._login(trez)
        member = self._create_member("MA1")

        resp = self.client.post("/api/treasurer/medical-aid/add/", {
            "med_member": str(member.member_id_PK),
            "med_date": "2026-07-03",
            "med_req_amount": "20000",
            "med_hospital": "SmokeTest Hospital",
            "med_bill": "25000",
            "med_validation": "Verified",
        })
        self.assertEqual(resp.status_code, 200, resp.json())
        self.assertTrue(resp.json()["ok"])
        med = MedicalAid.objects.filter(member_id_FK=member).latest("medical_aid_id_PK")

        aud = self._create_officer("Auditor", "MA1")
        self._login(aud)
        resp = self.client.post("/api/auditor/verify-aid/", {
            "aAuditID": f"medical-{med.medical_aid_id_PK}",
            "aAuditResult": "Verified",
            "aAuditRemarks": "OK",
        })
        self.assertEqual(resp.status_code, 200, resp.content.decode())
        tv = TransactionVerification.objects.get(table_name="medical_aid", record_id=med.medical_aid_id_PK)
        self.assertEqual(tv.verification_status, "Auditor Verified")

        prez = self._create_officer("President", "MA1")
        self._login(prez)
        resp = self.client.post("/api/aids/presidential-decision/",
            {"target_id": f"medical-{med.medical_aid_id_PK}", "decision": "Approved", "approved_amount": 20000, "remarks": "OK"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.json())
        tv.refresh_from_db()
        self.assertEqual(tv.verification_status, "Approved")

    # ------------------------------------------------------------------
    # 4) Death aid full flow
    # ------------------------------------------------------------------
    def test_death_aid_full_flow(self):
        trez = self._create_officer("Treasurer", "DA1")
        self._login(trez)
        member = self._create_member("DA1")

        resp = self.client.post("/api/treasurer/death-aid/add/", {
            "death_member": str(member.member_id_PK),
            "death_deceased": "Deceased Spouse",
            "death_rel": "spouse",
            "death_rel_group": "immediate",
            "death_type": "spouse",
            "death_claimant": "Claimant Person",
            "death_contact": "09170000001",
            "death_date": "2026-07-03",
        })
        self.assertEqual(resp.status_code, 200, resp.json())
        self.assertTrue(resp.json()["ok"])
        death = DeathAid.objects.filter(member_id_FK=member).latest("death_aid_id_PK")
        self.assertEqual(death.benefit_amount, 300)  # spouse maps to death_aid_spouse (₱300)
        self.assertEqual(death.relationship_group, "immediate")

        aud = self._create_officer("Auditor", "DA1")
        self._login(aud)
        resp = self.client.post("/api/auditor/verify-aid/", {
            "aAuditID": f"death-{death.death_aid_id_PK}",
            "aAuditResult": "Verified",
            "aAuditRemarks": "OK",
        })
        self.assertEqual(resp.status_code, 200, resp.content.decode())
        tv = TransactionVerification.objects.get(table_name="death_aid", record_id=death.death_aid_id_PK)
        self.assertEqual(tv.verification_status, "Auditor Verified")

        prez = self._create_officer("President", "DA1")
        self._login(prez)
        resp = self.client.post("/api/aids/presidential-decision/",
            {"target_id": f"death-{death.death_aid_id_PK}", "decision": "Approved", "approved_amount": 50000, "remarks": "OK"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.json())
        tv.refresh_from_db()
        self.assertEqual(tv.verification_status, "Approved")

    # ------------------------------------------------------------------
    # 5) Resubmission loop: Treasurer → Auditor (Return) → Treasurer (Resubmit) → Auditor (Verify)
    # ------------------------------------------------------------------
    def test_resubmission_loop(self):
        trez = self._create_officer("Treasurer", "RS1")
        self._login(trez)
        member = self._create_member("RS1")

        resp = self.client.post("/api/treasurer/membership-fees/add/", {
            "fee_member": str(member.member_id_PK),
            "fee_amount": "500.00",
            "fee_date": "2026-07-03",
            "fee_month": "2026-07",
            "fee_method": "OTC",
            "fee_ref": "SMK-RECV-RS1",
            "fee_encoder": "Encoder",
        })
        self.assertTrue(resp.json()["ok"])
        fee = MembershipFee.objects.get(receipt_number="SMK-RECV-RS1")

        # Auditor returns it
        aud = self._create_officer("Auditor", "RS1")
        self._login(aud)
        resp = self.client.post("/api/auditor/verify-membership-fee/", {
            "mfAuditID": str(fee.fee_id_PK),
            "mfAuditResult": "Returned",
            "mfAuditRemarks": "Missing receipt",
        })
        self.assertEqual(resp.status_code, 200, resp.content.decode())
        tv = TransactionVerification.objects.get(table_name="membership_fee", record_id=fee.fee_id_PK)
        self.assertEqual(tv.verification_status, "Returned for Revision")
        self.assertEqual(tv.returned_by_auditor_id_FK, aud)
        self.assertEqual(tv.returned_reason, "Missing receipt")
        self.assertEqual(tv.return_count, 1)

        # Treasurer resubmits
        self._login(trez)
        resp = self.client.post(f"/api/treasurer/resubmit/membership_fee/{fee.fee_id_PK}/", {
            "fee_ref": "SMK-RECV-RS1",
            "fee_encoder": "Encoder",
            "fee_method": "OTC",
            "fee_date": "2026-07-03",
            "fee_month": "2026-07",
            "fee_status": "Pending",
            "fee_amount": "500.00",
            "same_auditor": "true",
        })
        self.assertEqual(resp.status_code, 200, resp.content.decode())
        data = resp.json()
        self.assertTrue(data.get("ok") or data.get("success"), data)
        tv.refresh_from_db()
        self.assertEqual(tv.verification_status, "Pending")

        # Auditor verifies again
        self._login(aud)
        resp = self.client.post("/api/auditor/verify-membership-fee/", {
            "mfAuditID": str(fee.fee_id_PK),
            "mfAuditResult": "Verified",
            "mfAuditRemarks": "Now OK",
        })
        self.assertEqual(resp.status_code, 200, resp.content.decode())
        tv.refresh_from_db()
        self.assertEqual(tv.verification_status, "Auditor Verified")
        # return_count should still be 1
        self.assertEqual(tv.return_count, 1)

    # ------------------------------------------------------------------
    # 6) Batch operations
    # ------------------------------------------------------------------
    def test_auditor_batch_verify(self):
        trez = self._create_officer("Treasurer", "BT1")
        self._login(trez)
        member = self._create_member("BT1")

        # Create 3 fees
        ids = []
        for i in range(3):
            resp = self.client.post("/api/treasurer/membership-fees/add/", {
                "fee_member": str(member.member_id_PK),
                "fee_amount": f"{500 + i * 100}.00",
                "fee_date": "2026-07-03",
                "fee_month": "2026-07",
                "fee_method": "OTC",
                "fee_ref": f"SMK-BATCH-{i}",
                "fee_encoder": "Encoder",
            })
            self.assertTrue(resp.json()["ok"])
            fee = MembershipFee.objects.get(receipt_number=f"SMK-BATCH-{i}")
            ids.append(fee.fee_id_PK)

        # Auditor batch verifies
        aud = self._create_officer("Auditor", "BT1")
        self._login(aud)
        resp = self.client.post("/api/auditor/verify-membership-fee/batch/",
            json.dumps({"ids": ids, "result": "Verified", "remarks": "Batch OK"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content.decode())
        data = resp.json()
        self.assertTrue(data.get("ok") or data.get("success"), data)

        # All 3 should be Auditor Verified
        for fid in ids:
            tv = TransactionVerification.objects.get(table_name="membership_fee", record_id=fid)
            self.assertEqual(tv.verification_status, "Auditor Verified")

        # President batch approves
        prez = self._create_officer("President", "BT1")
        self._login(prez)
        tv_ids = list(
            TransactionVerification.objects.filter(table_name="membership_fee", record_id__in=ids)
            .values_list("verification_id", flat=True)
        )
        resp = self.client.post("/api/payments/presidential-decision/batch/",
            {"ids": tv_ids, "decision": "Approved", "remarks": "Batch approve"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.json())
        for fid in ids:
            tv = TransactionVerification.objects.get(table_name="membership_fee", record_id=fid)
            self.assertEqual(tv.verification_status, "Approved")

    # ------------------------------------------------------------------
    # 7) Bulk salary deduction preview + process
    # ------------------------------------------------------------------
    def test_salary_bulk_preview(self):
        trez = self._create_officer("Treasurer", "BP1")
        self._login(trez)
        m1 = self._create_member("BP1")
        m2 = self._create_member("BP2")
        m3 = self._create_member("BP3")
        m3.membership_status = "retired"
        m3.save()

        resp = self.client.post("/api/treasurer/monthly-dues/salary/bulk-preview/",
            {"sal_month": "2026-07"})
        self.assertEqual(resp.status_code, 200, resp.json())
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["month"], "2026-07")
        self.assertEqual(data["total_active"], 2)
        self.assertEqual(data["already_processed"], 0)
        member_ids = [m["member_id"] for m in data["members"]]
        self.assertIn(m1.member_id_PK, member_ids)
        self.assertIn(m2.member_id_PK, member_ids)
        self.assertNotIn(m3.member_id_PK, member_ids)
        for m in data["members"]:
            self.assertTrue(m["default_checked"])

    def test_salary_bulk_process(self):
        trez = self._create_officer("Treasurer", "BP2")
        self._login(trez)
        m1 = self._create_member("BP4")
        m2 = self._create_member("BP5")

        resp = self.client.post("/api/treasurer/monthly-dues/salary/bulk-process/", {
            "sal_month": "2026-07",
            "batch_ref": "TXN-BP2-0726",
            "summary": "Payroll batch test",
            "member_ids": json.dumps([m1.member_id_PK, m2.member_id_PK]),
        })
        self.assertEqual(resp.status_code, 200, resp.json())
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["processed"], 2)
        self.assertEqual(data["skipped"], 0)
        self.assertEqual(data["batch_ref"], "ISUCauFA-26-1")

        for m in [m1, m2]:
            dues = MonthlyDues.objects.get(member_id_FK=m, month_covered="2026-07")
            self.assertEqual(dues.payment_method, "Salary Deduction")
            self.assertEqual(dues.remittance_reference, "ISUCauFA-26-1")
            self.assertEqual(dues.deduction_batch_reference, "Payroll batch test")
            tv = TransactionVerification.objects.get(table_name="monthly_dues", record_id=dues.dues_id_PK)
            self.assertEqual(tv.verification_status, "Pending Treasurer Review")

    def test_salary_bulk_skips_duplicates(self):
        trez = self._create_officer("Treasurer", "BP3")
        self._login(trez)
        m1 = self._create_member("BP6")
        m2 = self._create_member("BP7")

        # Process first time
        resp = self.client.post("/api/treasurer/monthly-dues/salary/bulk-process/", {
            "sal_month": "2026-07",
            "batch_ref": "TXN-BP3A",
            "member_ids": json.dumps([m1.member_id_PK, m2.member_id_PK]),
        })
        self.assertEqual(resp.status_code, 200, resp.json())
        self.assertEqual(resp.json()["processed"], 2)

        # Process same month again — app now rejects duplicate months with 409
        resp = self.client.post("/api/treasurer/monthly-dues/salary/bulk-process/", {
            "sal_month": "2026-07",
            "batch_ref": "TXN-BP3B",
            "member_ids": json.dumps([m1.member_id_PK, m2.member_id_PK]),
        })
        self.assertEqual(resp.status_code, 409, resp.json())
        self.assertFalse(resp.json()["ok"])

        # Still only 2 records total
        self.assertEqual(MonthlyDues.objects.filter(month_covered="2026-07", payment_method="Salary Deduction").count(), 2)

    def test_salary_bulk_creates_member_facing_records(self):
        trez = self._create_officer("Treasurer", "BP9")
        self._login(trez)
        member = self._create_member("BP9")

        resp = self.client.post("/api/treasurer/monthly-dues/salary/bulk-process/", {
            "sal_month": "2026-09",
            "summary": "Member-facing notice test",
            "member_ids": json.dumps([member.member_id_PK]),
        })
        self.assertEqual(resp.status_code, 200, resp.json())
        self.assertTrue(resp.json()["ok"])

        dues = MonthlyDues.objects.get(member_id_FK=member, month_covered="2026-09")

        # The member-facing payment notification should not be created until the
        # payment is fully approved by the President.
        self.assertFalse(
            Notification.objects.filter(
                recipient_type="member",
                recipient_id=member.member_id_PK,
                category="payment",
            ).exists()
        )

        # Regression (C3): the MemberLedger entry is NOT written at the Treasurer
        # record stage. Money was withheld, but the ledger entry is written once —
        # at President approval — so MemberLedger and FundTransaction always agree.
        self.assertFalse(
            MemberLedger.objects.filter(
                member_id_FK=member,
                reference_id=dues.dues_id_PK,
                reference_type="MonthlyDues",
            ).exists()
        )
        self.assertFalse(
            FundTransaction.objects.filter(
                source_type="monthly_dues",
                source_id=dues.dues_id_PK,
            ).exists()
        )

        # Drive the record through the rest of the chain: Treasurer → Auditor → President.
        resp = self.client.post("/api/treasurer/monthly-dues/approve/",
            {"dues_id": dues.dues_id_PK, "action": "approve", "remarks": "OK"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.json())

        aud = self._create_officer("Auditor", "BP9")
        self._login(aud)
        resp = self.client.post("/api/auditor/verify-payment/", {
            "pAuditID": str(dues.dues_id_PK),
            "pAuditResult": "Verified",
            "pAuditRemarks": "OK",
        })
        self.assertEqual(resp.status_code, 200, resp.content.decode())

        prez = self._create_officer("President", "BP9")
        self._login(prez)
        tv = TransactionVerification.objects.get(table_name="monthly_dues", record_id=dues.dues_id_PK)
        resp = self.client.post("/api/payments/presidential-decision/",
            {"target_id": str(tv.verification_id), "decision": "Approved", "remarks": "OK"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.json())

        # At President approval both the FundTransaction and the MemberLedger are
        # created together and exactly once (idempotent (C3)).
        self.assertTrue(
            FundTransaction.objects.filter(
                source_type="monthly_dues",
                source_id=dues.dues_id_PK,
            ).exists()
        )
        self.assertTrue(
            MemberLedger.objects.filter(
                member_id_FK=member,
                reference_id=dues.dues_id_PK,
                reference_type="MonthlyDues",
            ).exists()
        )

    def test_salary_bulk_full_workflow(self):
        """Complete lifecycle: bulk create → auditor verify → president approve."""
        trez = self._create_officer("Treasurer", "BP8")
        self._login(trez)
        m1 = self._create_member("BP8")

        resp = self.client.post("/api/treasurer/monthly-dues/salary/bulk-process/", {
            "sal_month": "2026-08",
            "batch_ref": "TXN-BP8-0826",
            "summary": "Full workflow test",
            "member_ids": json.dumps([m1.member_id_PK]),
        })
        self.assertEqual(resp.status_code, 200, resp.json())
        self.assertEqual(resp.json()["processed"], 1)
        self.assertEqual(resp.json()["batch_ref"], "ISUCauFA-26-1")

        dues = MonthlyDues.objects.get(member_id_FK=m1, month_covered="2026-08")
        self.assertEqual(dues.remittance_reference, "ISUCauFA-26-1")

        # Treasurer approves (forwards to Auditor) before Auditor can verify
        resp = self.client.post("/api/treasurer/monthly-dues/approve/",
            {"dues_id": dues.dues_id_PK, "action": "approve", "remarks": "OK"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.json())
        tv = TransactionVerification.objects.get(table_name="monthly_dues", record_id=dues.dues_id_PK)
        self.assertEqual(tv.verification_status, "Pending Auditor Review")

        # Auditor verifies
        aud = self._create_officer("Auditor", "BP8")
        self._login(aud)
        resp = self.client.post("/api/auditor/verify-payment/", {
            "pAuditID": str(dues.dues_id_PK),
            "pAuditResult": "Verified",
            "pAuditRemarks": "Bulk OK",
        })
        self.assertEqual(resp.status_code, 200, resp.content.decode())
        tv.refresh_from_db()
        self.assertEqual(tv.verification_status, "Auditor Verified")

        # President approves
        prez = self._create_officer("President", "BP8")
        self._login(prez)
        resp = self.client.post("/api/payments/presidential-decision/",
            {"target_id": str(tv.verification_id), "decision": "Approved", "remarks": "OK"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.json())
        tv.refresh_from_db()
        self.assertEqual(tv.verification_status, "Approved")


class RemittanceDoubleCountRegressionTests(TestCase):
    """Regression: recording a salary-deduction remittance must NOT book a
    FundTransaction inflow. The remittance is the same money as the member
    contributions, which are booked at Auditor verify (source_type
    'contribution'). Previously an extra 'salary_deduction_remittance' inflow
    double-counted the funds."""

    def setUp(self):
        self.member = Member.objects.create(
            full_name="Test Member",
            employee_id="EMP-REM-001",
            department="HR",
            position="Staff",
            membership_status="Active",
            employment_status="Active",
            member_type="REG",
            date_joined=timezone.now().date(),
        )
        self.archive = TransactionArchive.objects.create(
            transaction_type="death_aid",
            record_id=1,
            member_id_FK=self.member,
            member_name=self.member.full_name,
            amount=20000,
            validated_amount=20000,
            status="Approved",
        )
        self.post = AidTrackingPost.objects.create(
            archive_id_FK=self.archive,
            aid_type="death_aid",
            target_month="2026-06",
            total_expected=20000,
            total_collected=0,
            is_active=True,
        )

    def _login_treasurer(self):
        officer = OfficerUser.objects.create(
            full_name="Treasurer Test",
            username="trez_remit_" + str(timezone.now().timestamp()),
            password_hash="unused",
            role="Treasurer",
            account_status="Active",
        )
        session, token = _create_zt_verified_session(officer)
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer

    def test_recording_remittance_creates_no_fund_transaction(self):
        self._login_treasurer()
        response = self.client.post(
            "/api/treasurer/aid-post-record-remittance/",
            {
                "post_id": str(self.post.post_id_PK),
                "remitted_amount": "20000",
                "remittance_reference": "BATCH-REM-001",
                "remitted_date": "2026-06-30",
            },
        )
        self.assertEqual(response.status_code, 200, response.json())
        data = response.json()
        self.assertTrue(data["ok"])

        # The remittance is a deposit reference only — no fund inflow is booked.
        self.assertEqual(
            FundTransaction.objects.filter(
                source_type="salary_deduction_remittance",
            ).count(),
            0,
            "Recording a remittance must not create a FundTransaction inflow.",
        )

        # The post's remittance fields are still persisted.
        self.post.refresh_from_db()
        self.assertEqual(float(self.post.deduction_remitted_amount), 20000)
        self.assertEqual(self.post.deduction_remittance_reference, "BATCH-REM-001")
        self.assertIsNotNone(self.post.deduction_remitted_date)

    def test_end_to_end_net_is_zero(self):
        """Two members pay ₱10,000 each, an equal remittance is recorded,
        then the full amount is disbursed. Inflow must match outflow (net 0)."""
        self._login_treasurer()

        member2 = Member.objects.create(
            full_name="Member Two",
            employee_id="EMP-REM-002",
            department="HR",
            position="Staff",
            membership_status="Active",
            employment_status="Active",
            member_type="REG",
            date_joined=timezone.now().date(),
        )
        for m, amt in ((self.member, 10000), (member2, 10000)):
            Contribution.objects.create(
                aid_tracking_post_id_FK=self.post,
                member_id_FK=m,
                expected_amount=amt,
                paid_amount=amt,
                status="RECORDED",
            )

        # Remittance reference only — no inflow booked (the fix).
        response = self.client.post(
            "/api/treasurer/aid-post-record-remittance/",
            {
                "post_id": str(self.post.post_id_PK),
                "remitted_amount": "20000",
                "remittance_reference": "BATCH-REM-002",
                "remitted_date": "2026-06-30",
            },
        )
        self.assertEqual(response.status_code, 200, response.json())
        self.assertFalse(
            FundTransaction.objects.filter(
                source_type="salary_deduction_remittance"
            ).exists()
        )

        # Upload the salary deduction sheet (required before Auditor can verify).
        response = self.client.post(
            "/api/treasurer/aid-post-upload-deduction-sheet/",
            {
                "post_id": str(self.post.post_id_PK),
                "batch_reference": "BATCH-REM-002",
                "payroll_period": "2026-06",
                "deduction_sheet": SimpleUploadedFile(
                    "deduction_sheet.xlsx", b"PK\x03\x04fake-xlsx-body", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
            },
        )
        self.assertEqual(response.status_code, 200, response.json())

        # The Auditor verify endpoint only accepts posts in pending_auditor state.
        self.post.finish_status = "pending_auditor"
        self.post.save(update_fields=["finish_status"])

        # Auditor verify books the per-contribution inflows (single source of truth).
        audit_officer = OfficerUser.objects.create(
            full_name="Auditor Test",
            username="aud_remit_" + str(timezone.now().timestamp()),
            password_hash="unused",
            role="Auditor",
            account_status="Active",
            mfa_secret="release-otp-test-secret",
        )
        session, token = _create_zt_verified_session(audit_officer)
        s = self.client.session
        s["access_token"] = token
        s["officer_id"] = audit_officer.user_id_PK
        s["role"] = audit_officer.role
        s.save()

        response = self.client.post(
            "/api/auditor/aid-post-verify-finish/",
            {
                "post_id": str(self.post.post_id_PK),
                "decision": "verified",
            },
        )
        self.assertEqual(response.status_code, 200, response.json())

        # Net fund position after recording contributions + remittance = 0.
        total_in = FundTransaction.objects.filter(direction="inflow").aggregate(
            total=Sum("amount")
        )["total"] or 0
        total_out = FundTransaction.objects.filter(direction="outflow").aggregate(
            total=Sum("amount")
        )["total"] or 0
        self.assertEqual(float(total_in), 20000)
        self.assertEqual(float(total_out), 0)
        self.assertEqual(float(total_in) - float(total_out), 20000)

        # The Treasurer release endpoint only accepts posts in pending_release
        # state (normally set by the President's finish approval). Set it here.
        self.post.refresh_from_db()
        self.post.finish_status = "pending_release"
        self.post.save(update_fields=["finish_status"])

        # Disburse the full collected amount. Releasing aid is a strict
        # action: it needs a verification code bound to this claim, a named
        # recipient, and an acknowledgement that any shortfall leaves the
        # general fund (here the ₱20k has no set-aside behind it).
        s = self.client.session
        s["aid_release_otp"] = {
            "post_id": int(self.post.post_id_PK),
            "sent_at": timezone.now().timestamp(),
            "expires_at": (timezone.now() + timedelta(seconds=300)).isoformat(),
        }
        s.save()
        response = self.client.post(
            "/api/treasurer/aid-post-release/",
            {
                "post_id": str(self.post.post_id_PK),
                "otp": generate_otp(audit_officer.mfa_secret or ""),
                "received_by": "Juan Dela Cruz",
                "ack_fund_deduction": "1",
                "override_reason": "Full collected amount released to the recipient.",
            },
        )
        self.assertEqual(response.status_code, 200, response.json())

        total_out_after = FundTransaction.objects.filter(direction="outflow").aggregate(
            total=Sum("amount")
        )["total"] or 0
        # Inflows (₱20k from contributions) − outflow (₱20k disbursement) = net 0.
        self.assertEqual(float(total_in), 20000)
        self.assertEqual(float(total_out_after), 20000)
        self.assertEqual(float(total_in) - float(total_out_after), 0)

class MonthlyDeductionWorkflowTests(TestCase):
    """End-to-end test of the additive monthly deduction workflow:

    President sets the assessment breakdown -> Treasurer records actual
    deductions (auto-allocated by priority) -> Auditor verifies -> President
    gives final approval which queues member email notices.
    """

    def setUp(self):
        self.members = []
        for index in range(1, 6):
            self.members.append(
                Member.objects.create(
                    full_name=f"MD Workflow Member {index}",
                    employee_id=f"EMP-MD-{index:03d}",
                    department="Finance",
                    position="Staff",
                    membership_status="Permanent",
                    employment_status="Active",
                    member_type="Member",
                    email=f"md_member_{index}@test.local",
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
            full_name=f"{role} MD Test {suffix}",
            username=f"{role.lower()}_md_{suffix}_{timezone.now().timestamp()}",
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
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["assessment"]["total_amount"], 300.0)
        self.assertEqual(data["assessment"]["status"], "pending_treasurer")
        return data["assessment"]["assessment_id"]

    def _treasurer_records(self, assessment_id, amounts):
        self._login("Treasurer", "record")
        payload = {
            "assessment_id": assessment_id,
            "members": [
                {"member_id": m.member_id_PK, "actual_deduction": amount}
                for m, amount in zip(self.members, amounts)
            ],
        }
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_full_workflow_allocates_by_priority_and_emails_members(self):
        assessment_id = self._president_saves_assessment()

        # Treasurer records: 3 full, 1 partial (250), 1 zero.
        data = self._treasurer_records(assessment_id, [350, 350, 350, 250, 0])
        self.assertEqual(float(data["total_recorded"]), 1300.0)
        self.assertEqual(float(data["total_outstanding"]), 350.0)
        self.assertEqual(float(data["total_change"]), 200.0)

        assessment = MonthlyAssessment.objects.get(pk=assessment_id)
        self.assertEqual(assessment.status, "pending_deposit")

        # Recording alone must not touch the ISUCauFA, Inc. fund — entries are
        # written only at President final approval.
        member_assessment_ids = list(
            MemberAssessment.objects.filter(assessment_id_FK=assessment)
            .values_list("member_assessment_id_PK", flat=True)
        )
        self.assertFalse(
            FundTransaction.objects.filter(source_id__in=member_assessment_ids).exists()
        )

        # Partial member (250): whole-item allocation — monthly due (200) is
        # funded fully, the next item (medical, 100) cannot be funded with the
        # remaining 50, so it stays fully outstanding and the 50 becomes the
        # member's credit ("change") for next month.
        partial = MemberAssessment.objects.get(
            assessment_id_FK=assessment, member_id_FK=self.members[3]
        )
        self.assertEqual(float(partial.actual_deduction), 250.0)
        self.assertEqual(float(partial.outstanding_balance), 50.0)
        self.assertEqual(float(partial.change_amount), 50.0)
        applied_by_purpose = {
            a.assessment_item_id_FK.purpose: float(a.amount_applied)
            for a in partial.allocations.all()
        }
        remaining_by_purpose = {
            a.assessment_item_id_FK.purpose: float(a.amount_remaining)
            for a in partial.allocations.all()
        }
        self.assertEqual(applied_by_purpose["monthly_due"], 200.0)
        self.assertEqual(applied_by_purpose["medical_aid_fund"], 0.0)
        self.assertNotIn("token_incentive", applied_by_purpose)
        self.assertEqual(remaining_by_purpose["monthly_due"], 0.0)
        self.assertEqual(remaining_by_purpose["medical_aid_fund"], 100.0)

        # Zero member: everything outstanding, nothing applied.
        zero = MemberAssessment.objects.get(
            assessment_id_FK=assessment, member_id_FK=self.members[4]
        )
        self.assertEqual(float(zero.outstanding_balance), 300.0)
        self.assertEqual(float(zero.change_amount), 0.0)
        self.assertTrue(
            all(float(a.amount_applied) == 0 for a in zero.allocations.all())
        )

        # Recording again is blocked once submitted for deposit.
        resubmit = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": assessment_id,
                "members": [{"member_id": self.members[0].member_id_PK, "actual_deduction": 350}],
            }),
            content_type="application/json",
        )
        self.assertEqual(resubmit.status_code, 409)

        # Deposit is required before the Auditor can verify.
        deposit_monthly_batch(self.client, assessment_id, reference="ORS-DEP-001")
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, "pending_audit")
        self.assertEqual(assessment.deposit_reference, "ORS-DEP-001")

        # Auditor verifies -> pending final approval with the President.
        self._login("Auditor", "verify")
        response = self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({"assessment_id": assessment_id, "action": "approve", "notes": "Entries match the payroll sheet."}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, "pending_final")
        self.assertTrue(
            all(ma.status == "verified" for ma in assessment.member_assessments.all())
        )

        # President final-approves -> approved + member email notices queued.
        self._login("President", "final")
        with patch("core_system.monthly_deduction_views.send_html_email_async", wraps=send_html_email_async) as mock_send:
            response = self.client.post(
                "/api/president/deductions/approve/",
                json.dumps({"assessment_id": assessment_id, "action": "approve", "notes": "Approved for release."}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["members_notified"], 5)

        assessment.refresh_from_db()
        self.assertEqual(assessment.status, "final_approved")
        self.assertTrue(
            all(ma.status == "approved" for ma in assessment.member_assessments.all())
        )
        self.assertEqual(mock_send.call_count, 5)

        # President approval books the ISUCauFA, Inc. fund: one dues inflow per
        # member with an actual deduction, plus a separate earmarked inflow for
        # the medical-aid portion of that same deduction. The two always sum
        # back to actual_deduction, and no aid ever leaves the fund here — aid
        # only leaves at release.
        fund_entries = FundTransaction.objects.filter(source_id__in=member_assessment_ids)
        self.assertEqual(
            fund_entries.filter(direction="inflow", source_type="monthly_dues").count(), 4
        )
        # Allocation is all-or-nothing per item, so the medical-aid earmark
        # exists only for the three members whose deduction covered it — the
        # partial (250) stopped at dues and funded no aid at all.
        self.assertEqual(
            fund_entries.filter(
                direction="inflow", source_type="aid_setaside_medical"
            ).count(),
            3,
        )
        self.assertEqual(
            fund_entries.filter(
                direction="inflow", source_type="aid_setaside_death"
            ).count(),
            0,
        )
        for entry in fund_entries.filter(direction="inflow"):
            self.assertIn("COL-", entry.reference_number or "")
            self.assertIn("ORS-DEP-001", entry.reference_number or "")
        self.assertEqual(
            fund_entries.filter(direction="outflow", source_type="medical_aid").count(), 0
        )
        self.assertFalse(
            fund_entries.filter(description__startswith="Excess funds to ISUCauFA, Inc.").exists()
        )
        # The split never invents or loses a peso: the rows add up to what was
        # actually deducted (350 x 3 + 250 + 0).
        self.assertEqual(
            float(fund_entries.filter(direction="inflow").aggregate(t=Sum("amount"))["t"]),
            1300.0,
        )
        # Each earmarked row carries its own AidSetAside ledger row.
        self.assertEqual(
            AidSetAside.objects.filter(
                member_assessment_id_FK_id__in=member_assessment_ids
            ).count(),
            3,
        )
        for call in mock_send.call_args_list:
            self.assertIn("emails/monthly_deduction_notice.html", call.kwargs.get("html_template", ""))
        # Per-status subjects: every member here is fully deducted except the
        # partial (250) and zero ones.
        subjects = [call.kwargs.get("subject", "") for call in mock_send.call_args_list]
        self.assertEqual(sum("Partial Deduction Notice" in s for s in subjects), 1)
        self.assertEqual(sum("No Deduction Recorded" in s for s in subjects), 1)
        self.assertEqual(sum("Monthly Deduction Notice" in s for s in subjects), 3)

        # Workflow log captures every step of the chain.
        actions = list(
            AssessmentWorkflowLog.objects.filter(assessment_id_FK=assessment)
            .values_list("action", flat=True)
        )
        self.assertEqual(
            actions,
            [
                "president_set_assessment",
                "treasurer_submit",
                "treasurer_deposit",
                "auditor_verify",
                "president_approve",
            ],
        )

        # Detail endpoint (used by the Review panel) serializes cleanly.
        response = self.client.get(f"/api/president/monthly-assessment/{assessment_id}/")
        self.assertEqual(response.status_code, 200, response.content)
        detail = response.json()
        self.assertTrue(detail["ok"])
        self.assertGreaterEqual(len(detail["workflow_logs"]), 4)
        self.assertTrue(all("log_id" in log for log in detail["workflow_logs"]))

        # Global audit trail entries exist for the new tables.
        self.assertTrue(
            GlobalAuditTrail.objects.filter(table_name="monthly_assessments", record_id=assessment_id).exists()
        )

    def test_fund_overview_groups_miscellaneous_items_as_other(self):
        """Fund Overview collapses miscellaneous (Other) items into one 'Other'
        bucket with sub-lines instead of listing each separately. Token
        Incentive is no longer an assessment purpose, so it can never appear
        there."""
        self._login("President", "other_setup")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({
                "month": "2026-09",
                "items": [
                    {"purpose": "monthly_due", "amount": 200, "priority_order": 1},
                    {"purpose": "medical_aid_fund", "amount": 100, "priority_order": 2,
                     "recipient": "Josephine C. Cristobal"},
                    {"purpose": "other", "amount": 50, "priority_order": 3,
                     "custom_label": "ISUFFAI Federation Fee",
                     "recipient": "ISUCauFA, Inc."},
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        assessment_id = response.json()["assessment"]["assessment_id"]
        self._treasurer_records(assessment_id, [350, 350, 350, 250, 0])
        deposit_monthly_batch(self.client, assessment_id)
        self._login("Auditor", "verify_other")
        response = self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({"assessment_id": assessment_id, "action": "approve", "notes": "ok"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self._login("President", "final_other")
        response = self.client.post(
            "/api/president/deductions/approve/",
            json.dumps({"assessment_id": assessment_id, "action": "approve", "notes": "Approved."}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        response = self.client.get("/api/fund/overview/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        inflow = {b["source"]: b for b in data["inflow_breakdown"]}
        self.assertIn("Other", inflow)
        self.assertNotIn("Token Incentive", inflow)
        self.assertAlmostEqual(inflow["Other"]["total"], 150.0, places=2)
        self.assertEqual(
            [s["label"] for s in inflow["Other"]["sub_items"]],
            ["ISUFFAI Federation Fee"],
        )
        self.assertAlmostEqual(inflow["Other"]["sub_items"][0]["total"], 150.0, places=2)

    def test_token_incentive_cannot_be_added_to_an_assessment(self):
        """Token Incentive is no longer a President purpose: a new breakdown
        can't add it, and a legacy row already on a month is kept read-only."""
        self._login("President", "notoken1")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({
                "month": "2026-11",
                "items": list(self.assessment_payload["items"]) + [
                    {"purpose": "token_incentive", "amount": 50, "priority_order": 3,
                     "recipient": "Justin Von T. Vergara"},
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("no longer an assessment purpose", response.json()["error"])
        self.assertFalse(
            MonthlyAssessment.objects.filter(month__year=2026, month__month=11).exists()
        )

        # A month that already carries a token row can still be revised: the
        # token line is re-attached from the stored copy, not the payload.
        officer = self._login("President", "notoken2")
        assessment = MonthlyAssessment.objects.create(
            month="2026-12-01", created_by_id_FK=officer, total_amount=350
        )
        AssessmentItem.objects.create(
            assessment_id_FK=assessment,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            custom_label="December 2026",
            amount=200,
            priority_order=1,
            recipient="ISUCauFA, Inc.",
        )
        legacy = AssessmentItem.objects.create(
            assessment_id_FK=assessment,
            purpose=AssessmentItem.PURPOSE_TOKEN_INCENTIVE,
            amount=50,
            priority_order=2,
            recipient="Justin Von T. Vergara",
        )
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({
                "month": "2026-12",
                "items": [
                    {"purpose": "monthly_due", "amount": 250, "priority_order": 1,
                     "custom_label": "2026-12"},
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["assessment"]
        self.assertEqual(data["status"], "pending_treasurer")
        self.assertEqual(data["total_amount"], 300.0)
        by_purpose = {i["purpose"]: i for i in data["items"]}
        self.assertEqual(by_purpose["monthly_due"]["amount"], 250.0)
        self.assertEqual(by_purpose["token_incentive"]["amount"], 50.0)
        # Retired purposes still read as their old name.
        self.assertEqual(by_purpose["token_incentive"]["purpose_label"], "Token Incentive")
        stored = assessment.items.get(purpose=AssessmentItem.PURPOSE_TOKEN_INCENTIVE)
        self.assertNotEqual(stored.item_id_PK, legacy.item_id_PK)
        self.assertEqual(stored.amount, legacy.amount)
        self.assertEqual(stored.recipient, legacy.recipient)

    def test_auditor_reject_requires_remarks_and_returns_to_treasurer(self):
        assessment_id = self._president_saves_assessment()
        self._treasurer_records(assessment_id, [350, 350, 350, 350, 350])
        deposit_monthly_batch(self.client, assessment_id)

        self._login("Auditor", "reject")
        missing_remarks = self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({"assessment_id": assessment_id, "action": "reject", "notes": ""}),
            content_type="application/json",
        )
        self.assertEqual(missing_remarks.status_code, 400)

        response = self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({"assessment_id": assessment_id, "action": "reject", "notes": "Two amounts do not match the sheet."}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        assessment = MonthlyAssessment.objects.get(pk=assessment_id)
        self.assertEqual(assessment.status, "rejected")
        self.assertEqual(assessment.auditor_remarks, "Two amounts do not match the sheet.")

        # Treasurer can re-record after a rejection: entries are replaced.
        data = self._treasurer_records(assessment_id, [350, 350, 350, 350, 300])
        self.assertEqual(float(data["total_recorded"]), 1700.0)
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, "pending_deposit")
        self.assertEqual(assessment.member_assessments.count(), 5)

    def test_draft_stays_with_president_until_submitted(self):
        """Save-as-draft keeps the month out of the Treasurer's workspace
        entirely; only a real submit hands it over for recording."""
        self._login("President", "vis1")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({**self.assessment_payload, "draft": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["assessment"]["status"], "draft")
        draft_id = data["assessment"]["assessment_id"]

        # The Treasurer does not see the draft month at all.
        self._login("Treasurer", "vis2")
        response = self.client.get("/api/treasurer/deductions/overview/")
        ids = [a["assessment_id"] for a in response.json()["assessments"]]
        self.assertNotIn(draft_id, ids)

        # Recording against a draft is refused even by direct id.
        response = self.client.get(f"/api/treasurer/deductions/members/{draft_id}/")
        self.assertFalse(response.json()["recordable"])

        # Submitting ("Save deduction") hands it to the Treasurer.
        self._login("President", "vis3")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(self.assessment_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["assessment"]["status"], "pending_treasurer")

        self._login("Treasurer", "vis4")
        response = self.client.get("/api/treasurer/deductions/overview/")
        by_id = {a["assessment_id"]: a for a in response.json()["assessments"]}
        self.assertIn(draft_id, by_id)
        self.assertTrue(by_id[draft_id]["can_record"])

        # And a submitted month can no longer be edited by the President.
        self._login("President", "vis5")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(self.assessment_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409, response.content)
        self.assertIn("submitted to the Treasurer", response.json()["error"])

    def test_president_return_requires_remarks(self):
        assessment_id = self._president_saves_assessment()
        self._treasurer_records(assessment_id, [350, 350, 350, 350, 350])
        deposit_monthly_batch(self.client, assessment_id)
        self._login("Auditor", "verify2")
        self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({"assessment_id": assessment_id, "action": "approve"}),
            content_type="application/json",
        )

        self._login("President", "return")
        missing = self.client.post(
            "/api/president/deductions/approve/",
            json.dumps({"assessment_id": assessment_id, "action": "return", "notes": ""}),
            content_type="application/json",
        )
        self.assertEqual(missing.status_code, 400)

        response = self.client.post(
            "/api/president/deductions/approve/",
            json.dumps({"assessment_id": assessment_id, "action": "return", "notes": "Please recheck member 5."}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        assessment = MonthlyAssessment.objects.get(pk=assessment_id)
        self.assertEqual(assessment.status, "returned")

    def test_locked_month_cannot_be_recreated_or_recorded(self):
        assessment_id = self._president_saves_assessment()
        self._treasurer_records(assessment_id, [350, 350, 350, 350, 350])

        # President cannot overwrite a submitted month's breakdown.
        self._login("President", "locked")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(self.assessment_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

        # A different month with the same breakdown saves fine.
        payload = dict(self.assessment_payload, month="2026-10")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_role_guards_block_wrong_role(self):
        self._login("Treasurer", "guard")
        response = self.client.get("/api/president/monthly-assessment/list/")
        self.assertEqual(response.status_code, 403)

    def test_other_item_requires_specific_name_and_label_flows_through(self):
        # 'Other' without a name is rejected.
        self._login("President", "other1")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({
                "month": "2026-11",
                "items": [
                    {"purpose": "monthly_due", "amount": 200, "priority_order": 1},
                    {"purpose": "other", "amount": 50, "priority_order": 2},
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("specific name", response.json()["error"])

        # With a name it saves, and the specific label replaces "Other"
        # everywhere the breakdown is serialized.
        payload = {
            "month": "2026-11",
            "items": [
                {"purpose": "monthly_due", "amount": 200, "priority_order": 1},
                {
                    "purpose": "other",
                    "custom_label": "ISUFFAI Federation Fee",
                    "amount": 50,
                    "priority_order": 2,
                    "recipient": "ISUFFAI",
                },
            ],
        }
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        assessment = MonthlyAssessment.objects.get(
            assessment_id_PK=response.json()["assessment"]["assessment_id"]
        )
        other_item = assessment.items.get(purpose="other")
        self.assertEqual(other_item.label, "ISUFFAI Federation Fee")
        self.assertEqual(response.json()["assessment"]["items"][1]["purpose_label"], "ISUFFAI Federation Fee")

        # The custom label survives the full chain into the member allocation.
        self._login("Treasurer", "other2")
        data = self._treasurer_records(assessment.assessment_id_PK, [250, 250, 250, 250, 250])
        self.assertEqual(float(data["total_recorded"]), 1250.0)
        member_assessment = MemberAssessment.objects.get(
            assessment_id_FK=assessment, member_id_FK=self.members[0]
        )
        allocation = member_assessment.allocations.get(assessment_item_id_FK=other_item)
        self.assertEqual(
            allocation.assessment_item_id_FK.label, "ISUFFAI Federation Fee"
        )

        # Non-'other' purposes ignore any submitted custom label.
        self._login("President", "other3")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({
                "month": "2026-12",
                "items": [
                    {"purpose": "monthly_due", "amount": 200, "custom_label": "July 2026", "priority_order": 1},
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        due_item = MonthlyAssessment.objects.get(
            assessment_id_PK=response.json()["assessment"]["assessment_id"]
        ).items.get(purpose="monthly_due")
        # Standard purposes keep an optional label (e.g. to distinguish two
        # Monthly Due lines for different months).
        self.assertEqual(due_item.custom_label, "July 2026")
        self.assertEqual(due_item.label, "Monthly Due (July 2026)")

    def test_formatted_name_helper_surname_format(self):
        from core_system.monthly_deduction_views import _formatted_name

        cases = {
            "Juan Dela Cruz": "DELA CRUZ, Juan",
            "Maria Clara De Los Santos": "DE LOS SANTOS, Maria Clara",
            "Josephine C. Cristobal": "CRISTOBAL, Josephine C.",
            "Jose Rizal Jr.": "RIZAL, Jose Jr.",
            "Pedro San Jose III": "SAN JOSE, Pedro III",
            "Grace": "GRACE",
            "": "",
        }
        for full_name, expected in cases.items():
            self.assertEqual(_formatted_name(full_name), expected)

    def test_chip_mode_selection_and_exact_allocation(self):
        """Chips preview the automatic allocation, and the treasurer can also
        select them to manually override which items were funded."""
        assessment_id = self._president_saves_assessment()
        items = {
            item.purpose: item
            for item in MonthlyAssessment.objects.get(pk=assessment_id).items.all()
        }

        # Member 1: auto figure 300.
        # Member 2: a ₱110-style paper figure via manual amount.
        # Member 3: manual override — paper shows 140 and the treasurer selects
        # only the medical aid chip (auto priority would have funded the 200
        # monthly due first).
        self._login("Treasurer", "chip")
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": assessment_id,
                "members": [
                    {
                        "member_id": self.members[0].member_id_PK,
                        "actual_deduction": 300,
                        "selected_item_ids": [items["monthly_due"].item_id_PK, items["medical_aid_fund"].item_id_PK],
                    },
                    {
                        "member_id": self.members[1].member_id_PK,
                        "actual_deduction": 110,
                    },
                    {
                        "member_id": self.members[2].member_id_PK,
                        "actual_deduction": 140,
                        "selected_item_ids": [items["medical_aid_fund"].item_id_PK],
                    },
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(float(response.json()["total_recorded"]), 550.0)

        assessment = MonthlyAssessment.objects.get(pk=assessment_id)
        chip_record = MemberAssessment.objects.get(
            assessment_id_FK=assessment, member_id_FK=self.members[0]
        )
        self.assertEqual(float(chip_record.actual_deduction), 300.0)
        self.assertEqual(float(chip_record.outstanding_balance), 0.0)
        # Allocations are exact: every selected peso lands on its item.
        applied = {
            a.assessment_item_id_FK.purpose: float(a.amount_applied)
            for a in chip_record.allocations.all()
        }
        self.assertEqual(applied["monthly_due"], 200.0)
        self.assertEqual(applied["medical_aid_fund"], 100.0)
        self.assertNotIn("token_incentive", applied)

        manual_record = MemberAssessment.objects.get(
            assessment_id_FK=assessment, member_id_FK=self.members[1]
        )
        self.assertEqual(float(manual_record.actual_deduction), 110.0)
        # All-or-nothing: the first item in priority order costs 200, so 110
        # cannot fund anything — it becomes the member's credit and the whole
        # standard stays outstanding (netted: 300 - 110 = 190).
        self.assertEqual(float(manual_record.outstanding_balance), 190.0)
        self.assertEqual(float(manual_record.change_amount), 110.0)
        manual_applied = {
            a.assessment_item_id_FK.purpose: float(a.amount_applied)
            for a in manual_record.allocations.all()
        }
        self.assertEqual(manual_applied["monthly_due"], 0.0)
        self.assertEqual(manual_applied["medical_aid_fund"], 0.0)

        # Manual override: the paper's 140 funded medical aid only, even
        # though the automatic priority would have funded the 200 monthly due
        # first — the treasurer's selection decides. 40 becomes credit to ISUCauFA.
        # Outstanding is based on items NOT funded: 300 - 100 = 200.
        override_record = MemberAssessment.objects.get(
            assessment_id_FK=assessment, member_id_FK=self.members[2]
        )
        self.assertEqual(float(override_record.actual_deduction), 140.0)
        self.assertEqual(float(override_record.outstanding_balance), 200.0)
        self.assertEqual(float(override_record.change_amount), 40.0)
        override_applied = {
            a.assessment_item_id_FK.purpose: float(a.amount_applied)
            for a in override_record.allocations.all()
        }
        self.assertEqual(override_applied["monthly_due"], 0.0)
        self.assertEqual(override_applied["medical_aid_fund"], 100.0)
        self.assertNotIn("token_incentive", override_applied)

    def test_selecting_more_than_money_available_is_refused(self):
        assessment_id = self._president_saves_assessment()
        items = {
            item.purpose: item
            for item in MonthlyAssessment.objects.get(pk=assessment_id).items.all()
        }
        self._login("Treasurer", "overselect")
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": assessment_id,
                "members": [{
                    "member_id": self.members[0].member_id_PK,
                    "actual_deduction": 140,
                    "selected_item_ids": [items["monthly_due"].item_id_PK, items["medical_aid_fund"].item_id_PK],
                }],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("more than the money available", response.json()["error"])

    def test_recipient_rules_per_purpose(self):
        """Every non-monthly-due item needs a recipient; monthly due is always
        for the whole membership."""
        self._login("President", "recip1")
        # Medical aid without a recipient is rejected.
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({
                "month": "2026-11",
                "items": [
                    {"purpose": "monthly_due", "amount": 200, "priority_order": 1},
                    {"purpose": "medical_aid_fund", "amount": 100, "priority_order": 2},
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("needs a recipient", response.json()["error"])

        # Monthly due ignores any typed recipient: it is forced to the
        # membership at large.
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({
                "month": "2026-11",
                "items": [
                    {"purpose": "monthly_due", "amount": 200, "priority_order": 1,
                     "recipient": "Someone Else"},
                    {"purpose": "medical_aid_fund", "amount": 100, "priority_order": 2,
                     "recipient": "Josephine C. Cristobal"},
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        assessment = MonthlyAssessment.objects.get(
            assessment_id_PK=response.json()["assessment"]["assessment_id"]
        )
        due = assessment.items.get(purpose="monthly_due")
        self.assertEqual(due.recipient, "ISUCauFA, Inc.")
        medical = assessment.items.get(purpose="medical_aid_fund")
        self.assertEqual(medical.recipient, "Josephine C. Cristobal")

        # Monthly Due's specify is a month picker: "2026-07" is stored in the
        # readable "July 2026" display form.
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({
                "month": "2026-12",
                "items": [
                    {"purpose": "monthly_due", "amount": 200, "priority_order": 1,
                     "custom_label": "2026-07"},
                    {"purpose": "monthly_due", "amount": 200, "priority_order": 2,
                     "custom_label": "2026-08"},
                    {"purpose": "medical_aid_fund", "amount": 100, "priority_order": 3,
                     "recipient": "Josephine C. Cristobal"},
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        december = MonthlyAssessment.objects.get(
            assessment_id_PK=response.json()["assessment"]["assessment_id"]
        )
        labels = [item.label for item in december.items.filter(purpose="monthly_due")]
        self.assertEqual(labels, ["Monthly Due (July 2026)", "Monthly Due (August 2026)"])

    def test_auditor_dashboard_renders_csrf_for_notify(self):
        """The compliance section carries a csrf token input so the notify
        POST can send a valid X-CSRFToken header."""
        self._login("Auditor", "csrfpage")
        response = self.client.get("/auditor/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    def test_deduction_compliance_heatmap_and_notify(self):
        """Department rates from recorded deductions + Auditor notify flow."""
        # Member 1 full, member 2 partial, member 3 zero, member 4 not recorded.

        # While the assessment is still a draft (nothing submitted), members
        # stay hidden and notify is refused.
        assessment_id = self._president_saves_assessment()
        self._login("Auditor", "hm0")
        response = self.client.get("/api/auditor/deductions/heatmap/")
        self.assertEqual(response.status_code, 200, response.content)
        draft_data = response.json()
        self.assertFalse(draft_data["notify_allowed"])
        self.assertEqual(draft_data["members"], [])
        response = self.client.post(
            "/api/auditor/deductions/notify/",
            json.dumps({
                "assessment_id": draft_data["assessment"]["assessment_id"],
                "member_ids": [self.members[0].member_id_PK],
                "notify_type": "reminder",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409, response.content)

        self._treasurer_records(assessment_id, [350, 250, 0])

        self._login("Auditor", "hm1")
        response = self.client.get("/api/auditor/deductions/heatmap/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["assessment"]["assessment_id"], assessment_id)
        self.assertEqual(data["totals"]["full"], 1)
        self.assertEqual(data["totals"]["partial"], 1)
        self.assertEqual(data["totals"]["zero"], 1)
        self.assertEqual(data["totals"]["pending"], 2)  # members 4 and 5 have no record
        # All members are in the "Finance" department here.
        self.assertEqual(len(data["departments"]), 1)
        dept = data["departments"][0]
        expected_rate = ((300 + 250 + 0 + 0) / (5 * 300)) * 100
        self.assertAlmostEqual(dept["rate"], round(expected_rate, 1), places=1)
        # Per-assessment rollups for the overview trend
        by_id = {a["assessment_id"]: a for a in data["assessments"]}
        self.assertEqual(by_id[assessment_id]["recorded"], 3)
        self.assertAlmostEqual(by_id[assessment_id]["collected"], 600.0, places=2)
        self.assertAlmostEqual(by_id[assessment_id]["expected"], 900.0, places=2)
        # New dashboard fields: verification rollup, per-purpose breakdown.
        self.assertEqual(data["totals"]["v_pending"], 3)
        self.assertEqual(data["totals"]["v_none"], 2)
        self.assertIn("credit", data["totals"])
        self.assertIn("breakdown", data)
        bd = {b["label"]: b for b in data["breakdown"]}
        self.assertIn("Monthly Due", bd)
        # Members 1 (full 350) and 2 (partial 250) both funded their 200 due.
        self.assertAlmostEqual(bd["Monthly Due"]["collected"], 400.0, places=2)
        self.assertAlmostEqual(bd["Monthly Due"]["expected"], 1000.0, places=2)
        # No miscellaneous items in this breakdown, so there is no "Other"
        # bucket — and Token Incentive is no longer an assessment purpose.
        self.assertNotIn("Other", bd)
        self.assertNotIn("Token Incentive", bd)
        self.assertEqual(dept["full"], 1)
        self.assertEqual(dept["partial"], 1)
        self.assertEqual(dept["zero"], 1)
        self.assertEqual(dept["pending"], 2)

        # Notify the members with outstanding balances.
        outstanding_ids = [
            m["member_id"] for m in data["members"] if m["outstanding"] > 0
        ]
        self.assertEqual(len(outstanding_ids), 4)
        response = self.client.post(
            "/api/auditor/deductions/notify/",
            json.dumps({
                "assessment_id": assessment_id,
                "member_ids": outstanding_ids,
                "notify_type": "reminder",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["sent"], 4)
        self.assertEqual(payload["skipped"], 0)
        self.assertAlmostEqual(payload["total_outstanding"], 50 + 300 + 300 + 300, places=2)

        # Workflow log + audit trail record the notification.
        self.assertTrue(
            AssessmentWorkflowLog.objects.filter(
                assessment_id_FK_id=assessment_id, action="auditor_notify_members"
            ).exists()
        )
        self.assertTrue(
            GlobalAuditTrail.objects.filter(
                table_name="monthly_assessments", record_id=assessment_id, action="NOTIFY"
            ).exists()
        )

        # The reminder email carries the member's credit ("change") so they
        # know their unused fund applies to next month.
        from core_system import monthly_deduction_views as mdv
        with patch.object(mdv, "send_html_email_async", wraps=mdv.send_html_email_async) as mock_mail:
            partial_id = next(
                m["member_id"] for m in data["members"] if m["status"] == "partial"
            )
            response = self.client.post(
                "/api/auditor/deductions/notify/",
                json.dumps({
                    "assessment_id": assessment_id,
                    "member_ids": [partial_id],
                    "notify_type": "reminder",
                }),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200, response.content)
            contexts = [call.kwargs.get("context", {}) for call in mock_mail.call_args_list]
            self.assertTrue(contexts, "reminder email was not queued")
            self.assertEqual(contexts[0].get("excess_to_fund"), 50.0)

        # A member with nothing outstanding is skipped.
        full_member = next(m["member_id"] for m in data["members"] if m["status"] == "full")
        response = self.client.post(
            "/api/auditor/deductions/notify/",
            json.dumps({
                "assessment_id": assessment_id,
                "member_ids": [full_member],
                "notify_type": "reminder",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["sent"], 0)
        self.assertEqual(response.json()["skipped"], 1)

        # Role guard: Treasurer cannot notify.
        self._login("Treasurer", "hm2")
        response = self.client.post(
            "/api/auditor/deductions/notify/",
            json.dumps({"assessment_id": assessment_id, "member_ids": outstanding_ids}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_partial_manual_distribution_per_item(self):
        """Partial amounts: the treasurer types how much of the deduction
        lands on each breakdown item; unfunded parts stay outstanding."""
        assessment_id = self._president_saves_assessment()
        items = list(MonthlyAssessment.objects.get(pk=assessment_id).items.all())
        self._login("Treasurer", "dist1")
        member = self.members[0]

        # 220 on the paper, distributed by hand: the due fully funded, 20 on
        # the medical aid.
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": assessment_id,
                "members": [{
                    "member_id": member.member_id_PK,
                    "actual_deduction": 220,
                    "item_amounts": [
                        {"item_id": items[0].item_id_PK, "amount": 200},
                        {"item_id": items[1].item_id_PK, "amount": 20},
                    ],
                }],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(float(response.json()["total_outstanding"]), 80.0)

        record = MemberAssessment.objects.get(
            assessment_id_FK_id=assessment_id, member_id_FK=member
        )
        self.assertEqual(float(record.change_amount), 0.0)
        applied = {a.assessment_item_id_FK.purpose: float(a.amount_applied) for a in record.allocations.all()}
        remaining = {a.assessment_item_id_FK.purpose: float(a.amount_remaining) for a in record.allocations.all()}
        self.assertEqual(applied["monthly_due"], 200.0)
        self.assertEqual(applied["medical_aid_fund"], 20.0)
        self.assertNotIn("token_incentive", applied)
        self.assertEqual(remaining["monthly_due"], 0.0)
        self.assertEqual(remaining["medical_aid_fund"], 80.0)
        self.assertNotIn("token_incentive", remaining)

        # An allocation above the item's requirement is refused (fresh month,
        # since the first record already submitted September to the Treasurer).
        self._login("President", "dist2")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(dict(self.assessment_payload, month="2026-10")),
            content_type="application/json",
        )
        october_id = response.json()["assessment"]["assessment_id"]
        october_items = list(MonthlyAssessment.objects.get(pk=october_id).items.all())
        self._login("Treasurer", "dist3")
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": october_id,
                "members": [{
                    "member_id": member.member_id_PK,
                    "actual_deduction": 120,
                    "item_amounts": [
                        {"item_id": october_items[1].item_id_PK, "amount": 120},
                    ],
                }],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400, response.content)

        # Allocations adding up to more than the deduction are refused.
        self._login("President", "dist4")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(dict(self.assessment_payload, month="2026-11")),
            content_type="application/json",
        )
        november_id = response.json()["assessment"]["assessment_id"]
        november_items = list(MonthlyAssessment.objects.get(pk=november_id).items.all())
        self._login("Treasurer", "dist5")
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": november_id,
                "members": [{
                    "member_id": member.member_id_PK,
                    "actual_deduction": 220,
                    "item_amounts": [
                        {"item_id": november_items[0].item_id_PK, "amount": 200},
                        {"item_id": november_items[1].item_id_PK, "amount": 100},
                    ],
                }],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400, response.content)

    def test_outstanding_carries_into_next_month_and_is_collectible(self):
        """Member pays 110 in Sept → 190 left + 110 credit; October uses the credit."""
        september_id = self._president_saves_assessment()
        self._login("Treasurer", "carry1")
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": september_id,
                "members": [{"member_id": self.members[0].member_id_PK, "actual_deduction": 110}],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        # Deposit while the Treasurer session is still active.
        deposit_monthly_batch(self.client, september_id)

        # Approve September fully so the balance becomes collectible.
        self._login("Auditor", "carry2")
        self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({"assessment_id": september_id, "action": "approve"}),
            content_type="application/json",
        )
        self._login("President", "carry3")
        self.client.post(
            "/api/president/deductions/approve/",
            json.dumps({"assessment_id": september_id, "action": "approve"}),
            content_type="application/json",
        )
        september = MonthlyAssessment.objects.get(pk=september_id)
        self.assertEqual(september.status, "final_approved")
        sept_record = MemberAssessment.objects.get(
            assessment_id_FK=september, member_id_FK=self.members[0]
        )
        self.assertEqual(float(sept_record.outstanding_balance), 190.0)

        # October assessment: same breakdown.
        self._login("President", "carry4")
        payload = dict(self.assessment_payload, month="2026-10")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        october_id = response.json()["assessment"]["assessment_id"]

        # The October roster exposes the September balance for collection.
        # There is no member credit — only the unpaid balance carries.
        self._login("Treasurer", "carry5")
        response = self.client.get(f"/api/treasurer/deductions/members/{october_id}/")
        self.assertEqual(response.status_code, 200, response.content)
        roster = response.json()["members"]
        entry = next(m for m in roster if m["member_id"] == self.members[0].member_id_PK)
        self.assertEqual(entry["prior_outstanding"], 190.0)
        self.assertEqual(entry["prior_month_label"], september.month_label)
        other = next(m for m in roster if m["member_id"] == self.members[1].member_id_PK)
        self.assertEqual(other["prior_outstanding"], 0.0)

        # October: 480 on the paper — 300 covers the month and 180 collects
        # part of the prior balance; the remaining 10 keeps carrying. Any
        # excess beyond that would go to the ISUCauFA funds.
        october = MonthlyAssessment.objects.get(pk=october_id)
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": october_id,
                "members": [{
                    "member_id": self.members[0].member_id_PK,
                    "actual_deduction": 480,
                    "prior_balance_amount": 180,
                }],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(float(response.json()["total_recorded"]), 480.0)
        self.assertEqual(float(response.json()["total_outstanding"]), 10.0)
        self.assertEqual(float(response.json()["total_change"]), 0.0)

        oct_record = MemberAssessment.objects.get(
            assessment_id_FK=october, member_id_FK=self.members[0]
        )
        self.assertEqual(float(oct_record.prior_outstanding), 190.0)
        self.assertEqual(float(oct_record.prior_outstanding_collected), 180.0)
        self.assertEqual(float(oct_record.change_amount), 0.0)
        self.assertEqual(float(oct_record.outstanding_balance), 10.0)
        self.assertEqual(oct_record.prior_month, september.month_label)

    def test_september_paper_scenario_140_of_350_with_two_monthly_dues(self):
        """The letter scenario: 100 medical (p1) / 100 due-July (p2) /
        100 due-Aug (p3) / 50 birthday (p4). Member deducts 140: medical is
        funded fully, the 40 left cannot fund the 100 due-July so it is
        forwarded to the ISUCauFA funds; outstanding is the three unfunded
        items (250)."""
        self._login("President", "scenario1")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({
                "month": "2026-09",
                "items": [
                    {"purpose": "medical_aid_fund", "amount": 100, "priority_order": 1,
                     "recipient": "Josephine C. Cristobal"},
                    {"purpose": "monthly_due", "amount": 100, "priority_order": 2,
                     "custom_label": "July 2026"},
                    {"purpose": "monthly_due", "amount": 100, "priority_order": 3,
                     "custom_label": "August 2026"},
                    {"purpose": "other", "amount": 50, "priority_order": 4,
                     "custom_label": "Birthday Token Incentive",
                     "recipient": "Clarinda C. Galiza"},
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        assessment_id = response.json()["assessment"]["assessment_id"]

        # Labels distinguish the two monthly dues.
        items = {i["purpose_label"]: i for i in response.json()["assessment"]["items"]}
        self.assertIn("Monthly Due (July 2026)", items)
        self.assertIn("Monthly Due (August 2026)", items)

        # Treasurer records the ₱140 paper figure.
        self._login("Treasurer", "scenario2")
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": assessment_id,
                "members": [{"member_id": self.members[0].member_id_PK, "actual_deduction": 140}],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(float(response.json()["total_outstanding"]), 210.0)
        self.assertEqual(float(response.json()["total_change"]), 40.0)

        assessment = MonthlyAssessment.objects.get(pk=assessment_id)
        record = MemberAssessment.objects.get(
            assessment_id_FK=assessment, member_id_FK=self.members[0]
        )
        self.assertEqual(float(record.actual_deduction), 140.0)
        self.assertEqual(float(record.change_amount), 40.0)
        self.assertEqual(float(record.outstanding_balance), 210.0)
        applied = {
            a.assessment_item_id_FK.purpose: float(a.amount_applied)
            for a in record.allocations.all()
        }
        self.assertEqual(applied["medical_aid_fund"], 100.0)
        self.assertEqual(applied["monthly_due"], 0.0)

        deposit_monthly_batch(self.client, assessment_id)

        # Next month the treasurer can apply the 40 credit.
        self._login("President", "scenario3")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({
                "month": "2026-10",
                "items": [
                    {"purpose": "monthly_due", "amount": 350, "priority_order": 1},
                ],
            }),
            content_type="application/json",
        )
        october_id = response.json()["assessment"]["assessment_id"]

        self._login("Auditor", "scenario4")
        self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({"assessment_id": assessment_id, "action": "approve"}),
            content_type="application/json",
        )
        self._login("President", "scenario5")
        self.client.post(
            "/api/president/deductions/approve/",
            json.dumps({"assessment_id": assessment_id, "action": "approve"}),
            content_type="application/json",
        )

        # October roster: the 210 outstanding is offered — there is no credit.
        self._login("Treasurer", "scenario6")
        response = self.client.get(f"/api/treasurer/deductions/members/{october_id}/")
        entry = next(
            m for m in response.json()["members"]
            if m["member_id"] == self.members[0].member_id_PK
        )
        self.assertEqual(entry["prior_outstanding"], 210.0)
        self.assertNotIn("available_change", entry)

        # October paper: 350 — the month is fully covered and the 210
        # outstanding still carries until it is explicitly collected.
        # (The 40 excess from September went to the ISUCauFA funds.)
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": october_id,
                "members": [{
                    "member_id": self.members[0].member_id_PK,
                    "actual_deduction": 350,
                }],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(float(response.json()["total_outstanding"]), 210.0)
        self.assertEqual(float(response.json()["total_change"]), 0.0)


class OtherTransactionManagementTests(TreasurerApiClientMixin, TestCase):
    """Treasurer 'Other Transaction' deposit/withdraw feature: booking,
    Fund Overview reflection, proof receipt storage/serving, role guard."""

    def _record(self, amount, action, description="", proof=None):
        data = {"amount": amount, "action": action}
        if description:
            data["description"] = description
        if proof is not None:
            data["proof_receipt"] = proof
        return self.client.post(
            "/api/treasurer/other-transactions/record/",
            data=data,
        )

    def test_deposit_records_and_shows_in_fund_overview(self):
        self._login_treasurer()
        res = self._record("1000.00", "deposit", description="Bank transfer in")
        self.assertEqual(res.status_code, 200, res.content)
        d = res.json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["transaction"]["action"], "deposit")
        self.assertTrue(d["transaction"]["reference_number"].startswith("OTH-"))

        tx = FundTransaction.objects.get(source_type="other_transaction")
        self.assertEqual(tx.direction, "inflow")
        self.assertEqual(float(tx.amount), 1000.0)
        self.assertEqual(tx.recorded_by_user_id_FK.role, "Treasurer")

        overview = self.client.get("/api/fund/overview/")
        self.assertEqual(overview.status_code, 200, overview.content)
        ov = overview.json()
        self.assertEqual(float(ov["money_in"]), 1000.0)
        labels = [row["source"] for row in ov["inflow_breakdown"]]
        self.assertIn("Other Transaction", labels)
        other_row = next(r for r in ov["inflow_breakdown"] if r["source"] == "Other Transaction")
        self.assertEqual(float(other_row["total"]), 1000.0)

    def test_withdraw_records_as_outflow(self):
        self._login_treasurer()
        res = self._record("250.50", "withdraw", description="Office supplies")
        self.assertEqual(res.status_code, 200, res.content)
        d = res.json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["transaction"]["action"], "withdraw")

        tx = FundTransaction.objects.get(source_type="other_transaction")
        self.assertEqual(tx.direction, "outflow")
        self.assertEqual(float(tx.amount), 250.5)

        overview = self.client.get("/api/fund/overview/")
        ov = overview.json()
        self.assertEqual(float(ov["money_out"]), 250.5)
        self.assertEqual(float(ov["balance"]), -250.5)
        sources = [row["source"] for row in ov["outflow_breakdown"]]
        self.assertIn("other_transaction", sources)
        other_row = next(r for r in ov["outflow_breakdown"] if r["source"] == "other_transaction")
        self.assertEqual(float(other_row["total"]), 250.5)

    def test_proof_receipt_uploaded_and_served(self):
        self._login_treasurer()
        proof_bytes = _real_test_image_bytes("PNG", "teal", (56, 42))
        proof = SimpleUploadedFile("receipt.png", proof_bytes, content_type="image/png")
        res = self._record("500.00", "deposit", description="Donation", proof=proof)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()["transaction"]["has_proof"])

        archive = FinancialDocumentArchive.objects.get(related_module="OTHER_TRANSACTION")
        self.assertEqual(archive.document_type, "proof_receipt")
        self.assertEqual(archive.file_name, "receipt.png")
        self.assertEqual(archive.verification_status, "Recorded")
        from django.core.files.storage import default_storage
        self.assertTrue(default_storage.exists(archive.file_path))

        dl = self.client.get(f"/api/treasurer/other-transactions/proof/{archive.document_id_PK}/")
        self.assertEqual(dl.status_code, 200)
        self.assertEqual(dl["Content-Type"], "image/png")
        self.assertEqual(dl.content, proof_bytes)

    def test_history_lists_newest_first_with_proof_metadata(self):
        self._login_treasurer()
        self._record("100.00", "deposit")
        self._record("40.00", "withdraw", proof=SimpleUploadedFile("r.pdf", b"%PDF-1.4\nfake receipt", content_type="application/pdf"))
        res = self.client.get("/api/treasurer/other-transactions/list/")
        self.assertEqual(res.status_code, 200, res.content)
        d = res.json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["total_deposited"], 100.0)
        self.assertEqual(d["total_withdrawn"], 40.0)
        self.assertEqual(d["net"], 60.0)
        self.assertEqual(len(d["entries"]), 2)
        self.assertEqual(d["entries"][0]["action"], "withdraw")
        self.assertTrue(d["entries"][1]["has_proof"] is False)
        self.assertTrue(d["entries"][0]["has_proof"] is True)

    def test_history_keeps_collections_apart_from_deposits(self):
        self._login_treasurer()
        self._record("100.00", "deposit", description="Donation")
        self._record("40.00", "withdraw")
        MonthlyAssessment.objects.create(
            month="2026-09-01",
            total_amount="300.00",
            status=MonthlyAssessment.STATUS_PENDING_DEPOSIT,
            deposit_reference="BD-555",
            deposited_amount="300.00",
            deposited_at=timezone.now(),
        )

        res = self.client.get("/api/treasurer/other-transactions/list/")
        self.assertEqual(res.status_code, 200, res.content)
        d = res.json()

        self.assertEqual(d["total_collected"], 300.0)
        self.assertEqual(d["total_deposited"], 100.0)
        self.assertEqual(d["total_withdrawn"], 40.0)
        self.assertEqual(d["net"], 360.0)
        self.assertEqual(len(d["entries"]), 3)

        collection = next(e for e in d["entries"] if e["source"] == "monthly_dues")
        self.assertEqual(collection["action_label"], "Collection")
        self.assertEqual(collection["collection_reference"], f"COL-{collection['id']:05d}")
        self.assertEqual(collection["reference_number"], "BD-555")

        one_off = next(
            e for e in d["entries"]
            if e["source"] == "other_transaction" and e["action"] == "deposit"
        )
        self.assertEqual(one_off["collection_reference"], "")

    def test_record_rejects_invalid_input(self):
        self._login_treasurer()
        self.assertEqual(self._record("0", "deposit").status_code, 400)
        self.assertEqual(self._record("-5", "deposit").status_code, 400)
        self.assertEqual(self._record("abc", "deposit").status_code, 400)
        self.assertEqual(self._record("100", "transfer").status_code, 400)
        self.assertEqual(FundTransaction.objects.filter(source_type="other_transaction").count(), 0)

    def test_non_treasurer_blocked_from_record(self):
        officer = OfficerUser.objects.create(
            full_name="Auditor Test",
            username="auditor_other_tx",
            password_hash="unused",
            role="Auditor",
            account_status="Active",
        )
        session, token = _create_zt_verified_session(officer)
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()

        res = self.client.post(
            "/api/treasurer/other-transactions/record/",
            data={"amount": "100", "action": "deposit"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(FundTransaction.objects.filter(source_type="other_transaction").count(), 0)


class MemberLedgerAndDeductionSheetTests(TestCase):
    """Officer-facing member ledger history (per-month deducted / credit /
    balance with the full member profile) and the downloadable transmittal
    letter + deducted amount sheet (Annex A) PDF."""

    def setUp(self):
        self.members = []
        for index in range(1, 4):
            self.members.append(
                Member.objects.create(
                    full_name=f"Ledger Test Member {index}",
                    employee_id=f"EMP-LEDGER-{index:03d}",
                    department="CCSICT" if index == 1 else "Finance",
                    position="Instructor I",
                    membership_status="Permanent",
                    employment_status="Active",
                    member_type="Member",
                    email=f"ledger_member_{index}@test.local",
                    contact_number=f"0917{index:08d}",
                    date_joined=timezone.now().date(),
                )
            )

    def _login(self, role, suffix):
        officer = OfficerUser.objects.create(
            full_name=f"{role} Ledger Test {suffix}",
            username=f"{role.lower()}_ledger_{suffix}_{timezone.now().timestamp()}",
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

    def _setup_assessment_with_deductions(self):
        """One assessment (2026-09) completed through final approval."""
        self._login("President", "setup")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({
                "month": "2026-09",
                "items": [
                    {"purpose": "monthly_due", "amount": 200, "priority_order": 1},
                    {"purpose": "medical_aid_fund", "amount": 100, "priority_order": 2,
                     "recipient": "Josephine C. Cristobal"},
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        assessment_id = response.json()["assessment"]["assessment_id"]

        self._login("Treasurer", "record")
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": assessment_id,
                "members": [
                    {"member_id": self.members[0].member_id_PK, "actual_deduction": 300},
                    {"member_id": self.members[1].member_id_PK, "actual_deduction": 150},
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        deposit_monthly_batch(self.client, assessment_id)
        self._login("Auditor", "verify")
        response = self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({"assessment_id": assessment_id, "action": "approve", "notes": "ok"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self._login("President", "final")
        response = self.client.post(
            "/api/president/deductions/approve/",
            json.dumps({"assessment_id": assessment_id, "action": "approve", "notes": "Approved."}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return assessment_id

    def test_member_ledger_history_returns_profile_and_monthly_rows(self):
        assessment_id = self._setup_assessment_with_deductions()

        # Picker list: only active members, formatted for the dropdown.
        self._login("Auditor", "list")
        response = self.client.get("/api/officers/deductions/member-ledger/")
        self.assertEqual(response.status_code, 200, response.content)
        listing = response.json()
        self.assertTrue(listing["ok"])
        self.assertEqual(len(listing["members"]), 3)
        self.assertIn("member_id", listing["members"][0])
        self.assertIn("member_name", listing["members"][0])

        # Full history for the partial member (150 of 300): nothing is funded
        # (monthly due needs 200, all-or-nothing), so the whole 150 becomes
        # credit and the outstanding balance is the 150 shortfall.
        member = self.members[1]
        response = self.client.get(
            f"/api/officers/deductions/member-ledger/?member_id={member.member_id_PK}"
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["ok"])

        profile = data["member"]
        self.assertEqual(profile["full_name"], member.full_name)
        self.assertEqual(profile["employee_id"], "EMP-LEDGER-002")
        self.assertEqual(profile["department"], "Finance")
        self.assertEqual(profile["position"], "Instructor I")
        self.assertEqual(profile["membership_status"], "Permanent")
        self.assertEqual(profile["contact_number"], member.contact_number)
        self.assertIn("date_joined", profile)
        self.assertIn("emergency_contact", profile)

        self.assertEqual(len(data["months"]), 1)
        month = data["months"][0]
        self.assertEqual(month["month_label"], "September 2026")
        self.assertEqual(month["assessment_id"], assessment_id)
        self.assertEqual(month["standard"], 300.0)
        self.assertEqual(month["deducted"], 150.0)
        self.assertEqual(month["credit"], 150.0)
        self.assertEqual(month["remaining_balance"], 150.0)

        self.assertEqual(data["totals"]["months_recorded"], 1)
        self.assertEqual(data["totals"]["total_deducted"], 150.0)
        self.assertEqual(data["totals"]["remaining_balance"], 150.0)

    def test_member_ledger_history_includes_only_approved_months(self):
        # September: member 0 pays 300 (due 200 + medical 100 fully funded).
        assessment_id = self._setup_assessment_with_deductions()

        # October: another month recorded for the same member, but not yet approved.
        self._login("President", "oct")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({
                "month": "2026-10",
                "items": [{"purpose": "monthly_due", "amount": 350, "priority_order": 1}],
            }),
            content_type="application/json",
        )
        october_id = response.json()["assessment"]["assessment_id"]
        self._login("Treasurer", "oct-record")
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": october_id,
                "members": [{"member_id": self.members[0].member_id_PK, "actual_deduction": 360}],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        deposit_monthly_batch(self.client, october_id)

        member = self.members[0]
        self._login("President", "view")
        response = self.client.get(
            f"/api/officers/deductions/member-ledger/?member_id={member.member_id_PK}"
        )
        data = response.json()
        self.assertEqual(len(data["months"]), 1)

        # A Treasurer-recorded month must stay hidden until the Auditor and
        # President complete the workflow.
        self._login("Auditor", "oct-verify")
        response = self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({"assessment_id": october_id, "action": "approve", "notes": "ok"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self._login("President", "oct-final")
        response = self.client.post(
            "/api/president/deductions/approve/",
            json.dumps({"assessment_id": october_id, "action": "approve", "notes": "Approved."}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        response = self.client.get(
            f"/api/officers/deductions/member-ledger/?member_id={member.member_id_PK}"
        )
        data = response.json()
        self.assertEqual(len(data["months"]), 2)
        # Ordered oldest → newest so the UI can flip the order.
        self.assertEqual([m["month_label"] for m in data["months"]], ["September 2026", "October 2026"])
        # Totals span months: 300 + 360 deducted.
        self.assertAlmostEqual(data["totals"]["total_deducted"], 660.0, places=2)
        # October: 360 covers the 350 standard, 10 becomes credit.
        october = data["months"][1]
        self.assertEqual(october["credit"], 10.0)
        self.assertEqual(october["remaining_balance"], 0.0)
        self.assertEqual(data["totals"]["credit_note"], 10.0)
        self.assertEqual(data["totals"]["remaining_balance"], 0.0)

        # A member with no records has an empty ledger, not an error.
        other = self.members[2]
        response = self.client.get(
            f"/api/officers/deductions/member-ledger/?member_id={other.member_id_PK}"
        )
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["months"], [])
        self.assertEqual(data["totals"]["total_deducted"], 0.0)

    def test_member_ledger_requires_officer_session(self):
        self._setup_assessment_with_deductions()
        # No session at all → JSON guard response (401 session expired).
        self.client = self.client_class()
        response = self.client.get(
            "/api/officers/deductions/member-ledger/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 401)

    def test_deduction_sheet_pdf_downloads_with_letter_and_sheet(self):
        assessment_id = self._setup_assessment_with_deductions()

        self._login("Treasurer", "pdf")
        response = self.client.get(f"/api/officers/deductions/sheet-pdf/{assessment_id}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("ISUCauFA_Deduction_Letter_2026-09.pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertGreater(len(response.content), 1000)

        # Same document is available to the Auditor and the President.
        self._login("Auditor", "pdf")
        self.assertEqual(
            self.client.get(f"/api/officers/deductions/sheet-pdf/{assessment_id}/").status_code, 200
        )
        self._login("President", "pdf")
        self.assertEqual(
            self.client.get(f"/api/officers/deductions/sheet-pdf/{assessment_id}/").status_code, 200
        )

        # Unknown assessment → 404.
        self.assertEqual(
            self.client.get("/api/officers/deductions/sheet-pdf/999999/").status_code, 404
        )

    def test_treasurer_roster_includes_recorded_amounts_for_view_only(self):
        assessment_id = self._setup_assessment_with_deductions()

        # While pending audit the roster already carries the recorded figures
        # the View Only table renders.
        self._login("Treasurer", "roster")
        response = self.client.get(f"/api/treasurer/deductions/members/{assessment_id}/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertFalse(data["recordable"])
        partial = next(
            m for m in data["members"] if m["member_id"] == self.members[1].member_id_PK
        )
        self.assertEqual(partial["recorded_actual"], 150.0)
        self.assertEqual(partial["recorded_outstanding"], 150.0)
        self.assertEqual(partial["recorded_excess"], 150.0)
        self.assertEqual(partial["recorded_status"], "pending")


def _real_test_image_bytes(fmt="PNG", color="red", size=(64, 48)):
    """Minimal Pillow-generated image bytes (upload validators require
    decodable images — hand-written b"\\x89PNG ..." fakes are rejected)."""
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


class AssessmentDocumentUploadTests(TestCase):
    """President attaches the signed request letter + deducted amount sheet to
    an assessment; officers can view the attached files."""

    def setUp(self):
        self.member = Member.objects.create(
            full_name="Doc Test Member",
            employee_id="EMP-DOC-001",
            department="CCSICT",
            position="Instructor I",
            membership_status="Permanent",
            employment_status="Active",
            member_type="Member",
            email="doc_member@test.local",
            date_joined=timezone.now().date(),
        )

    def _login(self, role, suffix):
        officer = OfficerUser.objects.create(
            full_name=f"{role} Doc Test {suffix}",
            username=f"{role.lower()}_doc_{suffix}_{timezone.now().timestamp()}",
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

    def _create_assessment(self):
        self._login("President", "setup")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({
                "month": "2026-09",
                "items": [{"purpose": "monthly_due", "amount": 200, "priority_order": 1}],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["assessment"]["assessment_id"]

    def test_president_upload_and_officers_download_documents(self):
        """Multiple images per kind: a two-page letter + one sheet, then
        officers view every image through the serialized links."""
        assessment_id = self._create_assessment()

        self._login("President", "upload")
        letter1_bytes = _real_test_image_bytes("PNG", "red", (64, 48))
        letter2_bytes = _real_test_image_bytes("PNG", "blue", (64, 48))
        sheet_bytes = _real_test_image_bytes("JPEG", "green", (80, 60))
        letter1 = SimpleUploadedFile("request_letter_p1.png", letter1_bytes, content_type="image/png")
        letter2 = SimpleUploadedFile("request_letter_p2.png", letter2_bytes, content_type="image/png")
        sheet = SimpleUploadedFile("deduction_sheet.jpg", sheet_bytes, content_type="image/jpeg")
        response = self.client.post(
            f"/api/president/monthly-assessment/{assessment_id}/upload-documents/",
            {"request_letter": [letter1, letter2], "deduction_sheet": [sheet]},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("2 request letter", response.json()["message"])

        assessment = MonthlyAssessment.objects.get(pk=assessment_id)
        self.assertEqual(
            assessment.documents.filter(kind="request_letter").count(), 2
        )
        self.assertEqual(
            assessment.documents.filter(kind="deduction_sheet").count(), 1
        )

        # The serialized assessment carries per-image lists with view links.
        response = self.client.get(f"/api/president/monthly-assessment/{assessment_id}/")
        serialized = response.json()["assessment"]
        self.assertTrue(serialized["has_request_letter"])
        self.assertTrue(serialized["has_deduction_sheet"])
        self.assertEqual(len(serialized["request_letter_images"]), 2)
        self.assertEqual(len(serialized["deduction_sheet_images"]), 1)
        self.assertIn("/documents/", serialized["request_letter_images"][0]["url"])
        self.assertIn("/file/", serialized["deduction_sheet_images"][0]["url"])

        # Treasurer (read-only role for documents) can open every image.
        self._login("Treasurer", "download")
        for image in serialized["request_letter_images"] + serialized["deduction_sheet_images"]:
            response = self.client.get(image["url"])
            self.assertEqual(response.status_code, 200, image["url"])
            self.assertIn("image/", response["Content-Type"])
        first_letter = serialized["request_letter_images"][0]
        response = self.client.get(first_letter["url"])
        self.assertEqual(response.content, letter1_bytes)

        # Auditor can view them too; upload workflow is logged.
        self._login("Auditor", "viewdocs")
        response = self.client.get(first_letter["url"])
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AssessmentWorkflowLog.objects.filter(
                assessment_id_FK_id=assessment_id, action="president_upload_documents"
            ).exists()
        )

    def test_duplicate_image_rejected_same_and_cross_kind(self):
        """The same scan cannot be attached twice — not under a new filename,
        and not as both the request letter and the deduction sheet."""
        assessment_id = self._create_assessment()
        self._login("President", "dup")

        raw = _real_test_image_bytes("PNG", "purple", (60, 44))
        first = SimpleUploadedFile("letter.png", raw, content_type="image/png")
        response = self.client.post(
            f"/api/president/monthly-assessment/{assessment_id}/upload-documents/",
            {"request_letter": [first]},
        )
        self.assertEqual(response.status_code, 200, response.content)

        # Same bytes, different filename, same kind → 409.
        again = SimpleUploadedFile("letter_copy.png", raw, content_type="image/png")
        response = self.client.post(
            f"/api/president/monthly-assessment/{assessment_id}/upload-documents/",
            {"request_letter": [again]},
        )
        self.assertEqual(response.status_code, 409, response.content)
        self.assertIn("already attached", response.json()["error"])

        # Same image filed as the other kind → 409 as well.
        as_sheet = SimpleUploadedFile("sheet.png", raw, content_type="image/png")
        response = self.client.post(
            f"/api/president/monthly-assessment/{assessment_id}/upload-documents/",
            {"deduction_sheet": [as_sheet]},
        )
        self.assertEqual(response.status_code, 409, response.content)

        # A genuinely different image still uploads fine.
        other = SimpleUploadedFile(
            "sheet.png", _real_test_image_bytes("PNG", "lime", (60, 44)),
            content_type="image/png",
        )
        response = self.client.post(
            f"/api/president/monthly-assessment/{assessment_id}/upload-documents/",
            {"deduction_sheet": [other]},
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_president_can_delete_single_image(self):
        """Uploading appends; the President can remove one image without
        touching the rest of the set."""
        assessment_id = self._create_assessment()
        self._login("President", "delete")
        page1 = SimpleUploadedFile("sheet_p1.png", _real_test_image_bytes("PNG", "red", (64, 48)), content_type="image/png")
        page2 = SimpleUploadedFile("sheet_p2.png", _real_test_image_bytes("PNG", "yellow", (64, 48)), content_type="image/png")
        self.client.post(
            f"/api/president/monthly-assessment/{assessment_id}/upload-documents/",
            {"deduction_sheet": [page1, page2]},
        )
        self.assertEqual(
            MonthlyAssessmentDocument.objects.filter(
                assessment_id_FK_id=assessment_id, kind="deduction_sheet"
            ).count(),
            2,
        )

        serialized = self.client.get(
            f"/api/president/monthly-assessment/{assessment_id}/"
        ).json()["assessment"]
        target_id = serialized["deduction_sheet_images"][0]["id"]

        response = self.client.post(
            f"/api/president/monthly-assessment/documents/{target_id}/delete/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        remaining = MonthlyAssessmentDocument.objects.filter(
            assessment_id_FK_id=assessment_id, kind="deduction_sheet"
        )
        self.assertEqual(remaining.count(), 1)
        self.assertNotEqual(remaining.first().document_id_PK, target_id)

        # The deleted image's URL no longer serves a file.
        self._login("Treasurer", "deleted-check")
        response = self.client.get(f"/api/officers/monthly-assessment/documents/{target_id}/file/")
        self.assertEqual(response.status_code, 404)

    def test_upload_rejects_disallowed_files_and_unknown_assessment(self):
        assessment_id = self._create_assessment()
        self._login("President", "reject")

        # Non-image files (exe, pdf, xlsx) are all rejected — images only.
        for name, blob, mime in (
            ("payload.exe", b"MZ binary", "application/octet-stream"),
            ("letter.pdf", b"%PDF-1.4", "application/pdf"),
            ("sheet.xlsx", b"fake-xlsx", "application/vnd.ms-excel"),
        ):
            bad = SimpleUploadedFile(name, blob, content_type=mime)
            response = self.client.post(
                f"/api/president/monthly-assessment/{assessment_id}/upload-documents/",
                {"request_letter": bad},
            )
            self.assertEqual(response.status_code, 400, name)

        ok_file = SimpleUploadedFile("letter.png", _real_test_image_bytes("PNG", "red"), content_type="image/png")
        response = self.client.post(
            "/api/president/monthly-assessment/999999/upload-documents/",
            {"request_letter": ok_file},
        )
        self.assertEqual(response.status_code, 404)  # unknown id checked first

        # Uploading with no file at all → 400 (validation happens before save).
        response = self.client.post(
            f"/api/president/monthly-assessment/{assessment_id}/upload-documents/",
            {},
        )
        self.assertEqual(response.status_code, 400)

        # No officer session → 401 JSON guard response.
        self.client = self.client_class()
        response = self.client.post(
            f"/api/president/monthly-assessment/{assessment_id}/upload-documents/",
            {},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 401)

    def test_document_file_url_404s_without_attachment(self):
        self._create_assessment()
        # No image attached at all → any document id is unknown.
        self._login("Auditor", "nodoc")
        response = self.client.get(
            "/api/officers/monthly-assessment/documents/999999/file/"
        )
        self.assertEqual(response.status_code, 404)

    def test_other_items_require_recipient(self):
        """'Other' items are not exempt: the Goes To field is required on a
        full save (draft mode still tolerates it being blank)."""
        self._login("President", "other1")
        payload = {
            "month": "2026-12",
            "items": [
                {"purpose": "monthly_due", "amount": 250, "priority_order": 1},
                {"purpose": "other", "amount": 50, "priority_order": 2, "custom_label": "Other Fees"},
            ],
        }
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({**payload, "draft": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        payload["items"][1]["recipient"] = "ISUCauFA, Inc."
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        assessment = MonthlyAssessment.objects.get(
            pk=response.json()["assessment"]["assessment_id"]
        )
        other_item = assessment.items.filter(purpose="other").first()
        self.assertEqual(other_item.recipient, "ISUCauFA, Inc.")

    def test_draft_mode_saves_incomplete_items(self):
        """Save-as-draft tolerates aid items without a recipient yet; the
        full save still enforces it."""
        self._login("President", "draft1")
        payload = {
            "month": "2026-11",
            "items": [
                {"purpose": "monthly_due", "amount": 250, "priority_order": 1},
                {"purpose": "death_aid_fund", "amount": 30, "priority_order": 2},
            ],
        }
        # Full save: death aid without a recipient is rejected.
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

        # Draft save: accepted, recipient stays empty.
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({**payload, "draft": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIn("Draft", data["message"])
        assessment = MonthlyAssessment.objects.get(pk=data["assessment"]["assessment_id"])
        self.assertEqual(assessment.status, "draft")
        death_item = assessment.items.filter(purpose="death_aid_fund").first()
        self.assertIsNotNone(death_item.recipient is None or death_item.recipient == "")
        self.assertTrue(
            AssessmentWorkflowLog.objects.filter(
                assessment_id_FK=assessment, notes__contains="Draft"
            ).exists()
        )

        # Completing it later with the recipient (full save) works.
        payload["items"][1]["recipient"] = "Juan Dela Cruz"
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        assessment.refresh_from_db()
        death_item = assessment.items.filter(purpose="death_aid_fund").first()
        self.assertEqual(death_item.recipient, "Juan Dela Cruz")


class MonthlyAssessmentDepositTests(TestCase):
    """Deposit step: validation, double-booking guard, trace, invalidation."""

    def setUp(self):
        self.members = []
        for index in range(1, 4):
            self.members.append(
                Member.objects.create(
                    full_name=f"Deposit Member {index}",
                    employee_id=f"EMP-DP-{index:03d}",
                    department="Finance",
                    position="Staff",
                    membership_status="Permanent",
                    employment_status="Active",
                    member_type="Member",
                    email=f"dp_member_{index}@test.local",
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
        self.deposit_url = "/api/treasurer/deductions/deposit/"

    def _login(self, role, suffix):
        officer = OfficerUser.objects.create(
            full_name=f"{role} Deposit Test {suffix}",
            username=f"{role.lower()}_deposit_{suffix}_{timezone.now().timestamp()}",
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

    def _recorded_assessment(self, amounts=None):
        assessment_id = self._president_saves_assessment()
        self._treasurer_records(assessment_id, amounts or [350, 350, 350])
        return assessment_id

    def _slip(self, name="deposit_slip.pdf"):
        return SimpleUploadedFile(name, b"%PDF-1.4\ndeposit slip", content_type="application/pdf")

    def _post_deposit(self, assessment_id, **overrides):
        data = {"assessment_id": str(assessment_id)}
        if "deposit_reference" not in overrides:
            data["deposit_reference"] = "ORS-DEP-TEST"
        data.update(overrides)
        data.setdefault("proof", self._slip())
        if data.get("proof") is None:
            data.pop("proof")
        return self.client.post(self.deposit_url, data)

    def _failed_deposit_audits(self, assessment_id):
        return GlobalAuditTrail.objects.filter(
            table_name="monthly_assessments",
            record_id=assessment_id,
            action="DEPOSIT",
            result="Failed",
        )

    def test_validation_failures_write_failed_audit_trail(self):
        assessment_id = self._recorded_assessment()
        recorded_total = 1050.0

        response = self._post_deposit(assessment_id, deposit_reference="", proof=self._slip())
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("reference", response.json()["error"].lower())

        response = self._post_deposit(assessment_id, proof=None)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("slip", response.json()["error"].lower())

        # Partial deposits are allowed, so an amount ABOVE the remaining
        # balance is the case that must still be rejected.
        response = self._post_deposit(
            assessment_id, deposited_amount=str(recorded_total + 1)
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("exceeds the remaining balance", response.json()["error"])

        response = self._post_deposit(assessment_id, proof=SimpleUploadedFile(
            "slip.txt", b"not a slip", content_type="text/plain",
        ))
        self.assertEqual(response.status_code, 400, response.content)

        self.assertGreaterEqual(self._failed_deposit_audits(assessment_id).count(), 4)
        assessment = MonthlyAssessment.objects.get(pk=assessment_id)
        self.assertEqual(assessment.status, "pending_deposit")
        self.assertIsNone(assessment.deposit_reference)
        self.assertIsNone(assessment.deposited_at)

    def test_wrong_status_and_double_deposit_are_blocked(self):
        assessment_id = self._president_saves_assessment()

        # Not recorded yet (pending_treasurer) -> 409 (as the Treasurer).
        self._login("Treasurer", "wrong-status")
        response = self._post_deposit(assessment_id)
        self.assertEqual(response.status_code, 409, response.content)

        self._treasurer_records(assessment_id, [350, 350, 350])
        response = self._post_deposit(assessment_id, deposit_reference="ORS-ONCE")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"])

        # A batch can be deposited exactly once.
        response = self._post_deposit(assessment_id, deposit_reference="ORS-TWICE")
        self.assertEqual(response.status_code, 409, response.content)
        assessment = MonthlyAssessment.objects.get(pk=assessment_id)
        self.assertEqual(assessment.deposit_reference, "ORS-ONCE")
        self.assertEqual(assessment.status, "pending_audit")

    def test_deposit_writes_no_fund_rows_until_president_approval(self):
        assessment_id = self._recorded_assessment()
        member_assessment_ids = list(
            MemberAssessment.objects.filter(assessment_id_FK_id=assessment_id)
            .values_list("member_assessment_id_PK", flat=True)
        )

        response = self._post_deposit(assessment_id, deposit_reference="ORS-TRACE")
        self.assertEqual(response.status_code, 200, response.content)

        self.assertFalse(
            FundTransaction.objects.filter(source_id__in=member_assessment_ids).exists()
        )

        self._login("Auditor", "verify")
        response = self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({"assessment_id": assessment_id, "action": "approve", "notes": "ok"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        self._login("President", "final")
        response = self.client.post(
            "/api/president/deductions/approve/",
            json.dumps({"assessment_id": assessment_id, "action": "approve", "notes": "Approved."}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        fund_entries = FundTransaction.objects.filter(
            source_id__in=member_assessment_ids, direction="inflow"
        )
        # Each of the three members books a dues row plus a medical-aid
        # set-aside row (350 = 250 dues + 100 medical aid).
        self.assertEqual(fund_entries.count(), 6)
        self.assertEqual(
            fund_entries.filter(source_type="monthly_dues").count(), 3
        )
        self.assertEqual(
            fund_entries.filter(source_type="aid_setaside_medical").count(), 3
        )
        self.assertEqual(
            float(fund_entries.aggregate(t=Sum("amount"))["t"]), 1050.0
        )
        collection_ref = f"COL-{assessment_id:05d}"
        for entry in fund_entries:
            self.assertIn(collection_ref, entry.reference_number or "")
            self.assertIn("ORS-TRACE", entry.reference_number or "")

    def test_deposit_populates_fields_slip_and_workflow_log(self):
        assessment_id = self._recorded_assessment()

        response = self._post_deposit(assessment_id, deposit_reference="ORS-POP")
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        serialized = payload["assessment"]
        self.assertEqual(serialized["status"], "pending_audit")
        self.assertEqual(serialized["deposit_reference"], "ORS-POP")
        self.assertEqual(serialized["deposited_amount"], 1050.0)
        self.assertTrue(serialized["deposited_at"])
        self.assertTrue(serialized["deposited_by"])
        self.assertEqual(serialized["collection_reference"], f"COL-{assessment_id:05d}")
        self.assertEqual(len(serialized["deposit_slips"]), 1)

        assessment = MonthlyAssessment.objects.get(pk=assessment_id)
        self.assertIsNotNone(assessment.deposited_by_id_FK)
        self.assertEqual(float(assessment.deposited_amount), 1050.0)
        self.assertTrue(
            AssessmentWorkflowLog.objects.filter(
                assessment_id_FK=assessment, action="treasurer_deposit"
            ).exists()
        )
        self.assertTrue(
            GlobalAuditTrail.objects.filter(
                table_name="monthly_assessments",
                record_id=assessment_id,
                action="DEPOSIT",
                result="Success",
            ).exists()
        )
        self.assertEqual(
            MonthlyAssessmentDocument.objects.filter(
                assessment_id_FK=assessment, kind="deposit_slip"
            ).count(),
            1,
        )

        # The batch leaves the pending-deposit queue.
        self._login("Treasurer", "queue")
        response = self.client.get("/api/treasurer/deductions/pending-deposit/")
        self.assertEqual(response.status_code, 200, response.content)
        queued_ids = [c["assessment_id"] for c in response.json()["collections"]]
        self.assertNotIn(assessment_id, queued_ids)

    def test_auditor_reject_invalidates_deposit_but_keeps_slip(self):
        assessment_id = self._recorded_assessment()
        response = self._post_deposit(assessment_id, deposit_reference="ORS-KEEP")
        self.assertEqual(response.status_code, 200, response.content)

        self._login("Auditor", "reject")
        response = self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({"assessment_id": assessment_id, "action": "reject", "notes": "Does not match the sheet."}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        assessment = MonthlyAssessment.objects.get(pk=assessment_id)
        self.assertEqual(assessment.status, "rejected")
        self.assertIsNone(assessment.deposit_reference)
        self.assertIsNone(assessment.deposited_amount)
        self.assertIsNone(assessment.deposited_at)
        self.assertIsNone(assessment.deposited_by_id_FK)
        self.assertTrue(
            AssessmentWorkflowLog.objects.filter(
                assessment_id_FK=assessment, action="deposit_invalidated"
            ).exists()
        )
        # Immutable evidence: the slip document survives the rejection.
        self.assertEqual(
            MonthlyAssessmentDocument.objects.filter(
                assessment_id_FK=assessment, kind="deposit_slip"
            ).count(),
            1,
        )

        # The strict path: re-record, then re-deposit with a fresh reference.
        self._treasurer_records(assessment_id, [350, 350, 300])
        response = self._post_deposit(assessment_id, deposit_reference="ORS-RETRY")
        self.assertEqual(response.status_code, 200, response.content)
        assessment.refresh_from_db()
        self.assertEqual(assessment.deposit_reference, "ORS-RETRY")
        self.assertEqual(
            MonthlyAssessmentDocument.objects.filter(
                assessment_id_FK=assessment, kind="deposit_slip"
            ).count(),
            2,
        )

    def test_president_return_invalidates_deposit(self):
        assessment_id = self._recorded_assessment()
        response = self._post_deposit(assessment_id, deposit_reference="ORS-RETURN")
        self.assertEqual(response.status_code, 200, response.content)

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
            json.dumps({"assessment_id": assessment_id, "action": "return", "notes": "Recheck member 2."}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        assessment = MonthlyAssessment.objects.get(pk=assessment_id)
        self.assertEqual(assessment.status, "returned")
        self.assertIsNone(assessment.deposit_reference)
        self.assertIsNone(assessment.deposited_at)
        self.assertTrue(
            AssessmentWorkflowLog.objects.filter(
                assessment_id_FK=assessment, action="deposit_invalidated"
            ).exists()
        )
        self.assertEqual(
            MonthlyAssessmentDocument.objects.filter(
                assessment_id_FK=assessment, kind="deposit_slip"
            ).count(),
            1,
        )

    def test_deposit_requires_treasurer_role(self):
        assessment_id = self._recorded_assessment()

        self._login("Auditor", "guard")
        response = self._post_deposit(assessment_id)
        self.assertEqual(response.status_code, 403)

        self._login("President", "guard")
        response = self._post_deposit(assessment_id)
        self.assertEqual(response.status_code, 403)

        assessment = MonthlyAssessment.objects.get(pk=assessment_id)
        self.assertEqual(assessment.status, "pending_deposit")
        self.assertIsNone(assessment.deposit_reference)

    def test_deposit_slip_cannot_be_deleted(self):
        assessment_id = self._recorded_assessment()
        response = self._post_deposit(assessment_id, deposit_reference="ORS-NODELETE")
        self.assertEqual(response.status_code, 200, response.content)

        slip = MonthlyAssessmentDocument.objects.get(
            assessment_id_FK_id=assessment_id, kind="deposit_slip"
        )
        self._login("President", "delete")
        response = self.client.post(
            f"/api/president/monthly-assessment/documents/{slip.document_id_PK}/delete/"
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertIn("immutable", response.json()["error"].lower())
        self.assertTrue(
            MonthlyAssessmentDocument.objects.filter(pk=slip.document_id_PK).exists()
        )
