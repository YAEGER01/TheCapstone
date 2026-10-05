"""Other-campus (external) aid: declare once, collect together, turn over once.

Pins the orderly flow:
  President declares external aid on the breakdown (campus + beneficiary)
  -> final approval books set-asides linked by ITEM (never by member name)
  -> one external AidTrackingPost with contributions for every active member
  -> Treasurer turns over via ONE Other-Transaction outflow + proof receipt
  -> normal member release refuses external posts (no double outflow)
"""
import json
from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from core_system.aid_setaside import (
    book_member_fund_rows,
    link_set_asides_to_external_post,
    setaside_available_for_post,
)
from core_system.auth_utils import create_access_session
from core_system.external_aid import ensure_external_posts_for_assessment
from core_system.models import (
    AidSetAside,
    AidTrackingPost,
    AssessmentItem,
    Contribution,
    FundTransaction,
    Member,
    MemberAssessment,
    MemberAssessmentAllocation,
    MonthlyAssessment,
    OfficerUser,
)
from core_system.tests import _create_zt_verified_session


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


def _officer(role, username):
    return OfficerUser.objects.create(
        full_name=f"{role} Ext Test",
        username=username,
        password_hash="unused",
        role=role,
        account_status="Active",
    )


class ExternalAidDeclarationTests(TestCase):
    def setUp(self):
        self.president = _officer("President", "pres_ext_1")
        session, token = _create_zt_verified_session(self.president)
        s = self.client.session
        s["access_token"] = token
        s["officer_id"] = self.president.user_id_PK
        s["role"] = "President"
        s.save()

    def _save(self, items, draft=False):
        return self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({"month": "2026-09", "items": items, "draft": draft}),
            content_type="application/json",
        )

    def test_external_without_campus_is_rejected(self):
        resp = self._save([{
            "purpose": "death_aid_fund", "amount": 100,
            "recipient_type": "external", "external_campus": "", "external_beneficiary": "",
        }])
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("campus", resp.json()["error"].lower())

    def test_medical_external_is_rejected(self):
        resp = self._save([{
            "purpose": "medical_aid_fund", "amount": 100,
            "recipient_type": "external",
            "external_campus": "ISU Echague Campus",
            "external_beneficiary": "Juan Dela Cruz",
        }])
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("only available", resp.json()["error"])

    def test_external_with_campus_is_stored_and_serialized(self):
        resp = self._save(
            [{"purpose": "monthly_due", "amount": 200, "priority_order": 1}],
            draft=True,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        resp = self._save([
            {"purpose": "monthly_due", "amount": 200, "priority_order": 1},
            {"purpose": "death_aid_fund", "amount": 100, "priority_order": 2,
             "recipient_type": "external",
             "external_campus": "ISU Echague Campus",
             "external_beneficiary": "Juan Dela Cruz"},
        ])
        self.assertEqual(resp.status_code, 200, resp.content)
        items = resp.json()["assessment"]["items"]
        ext = next(i for i in items if i["purpose"] == "death_aid_fund")
        self.assertTrue(ext["is_external"])
        self.assertEqual(ext["external_campus"], "ISU Echague Campus")
        self.assertEqual(ext["external_beneficiary"], "Juan Dela Cruz")
        self.assertIn("ISU Echague", ext["recipient"])

    def test_monthly_due_cannot_be_external(self):
        resp = self._save([{
            "purpose": "monthly_due", "amount": 200,
            "recipient_type": "external",
            "external_campus": "ISU Echague Campus",
            "external_beneficiary": "Juan Dela Cruz",
        }])
        self.assertEqual(resp.status_code, 200, resp.content)
        item = AssessmentItem.objects.get()
        self.assertEqual(item.recipient, "ISUCauFA, Inc.")
        self.assertEqual(item.recipient_type, "member")


class ExternalAidBookingTests(TestCase):
    """External earmarks link by ITEM — a same-name local member captures nothing."""

    def setUp(self):
        self.officer = _officer("President", "pres_ext_2")
        # Local member shares the beneficiary's name: the trap.
        self.local = _member("Juan Dela Cruz", "EMP-EXT-001")
        self.payer = _member("Maria Santos", "EMP-EXT-002")
        self.assessment = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1), total_amount=Decimal("300.00"))
        self.ext_item = AssessmentItem.objects.create(
            assessment_id_FK=self.assessment,
            purpose=AssessmentItem.PURPOSE_DEATH_AID,
            amount=Decimal("100.00"),
            recipient="ISU Echague Campus — Juan Dela Cruz",
            recipient_type="external",
            external_campus="ISU Echague Campus",
            external_beneficiary="Juan Dela Cruz",
            priority_order=1,
        )
        self.ma = MemberAssessment.objects.create(
            assessment_id_FK=self.assessment, member_id_FK=self.payer,
            standard_assessment=Decimal("300.00"),
            actual_deduction=Decimal("300.00"),
            status=MemberAssessment.STATUS_APPROVED,
        )
        MemberAssessmentAllocation.objects.create(
            member_assessment_id_FK=self.ma,
            assessment_item_id_FK=self.ext_item,
            amount_applied=Decimal("100.00"),
            amount_remaining=Decimal("0.00"),
        )
        # An internal claim for the same-name local member (must stay empty).
        from core_system.models import TransactionArchive
        archive = TransactionArchive.objects.create(
            transaction_type="death_aid", record_id=777,
            member_id_FK=self.local, member_name=self.local.full_name,
            amount=Decimal("500.00"), status="Approved",
        )
        self.internal_post = AidTrackingPost.objects.create(
            archive_id_FK=archive, aid_type="death_aid",
            target_month="2026-09", total_expected=Decimal("500.00"),
            total_collected=Decimal("0.00"),
            source_type="death_aid", source_id=777,
            finish_status="pending_release",
            created_by_user_id_FK=self.officer,
        )

    def test_external_earmark_never_links_to_member_post(self):
        book_member_fund_rows(self.ma, self.officer, "COL-00077", "September 2026")
        row = AidSetAside.objects.get(member_assessment_id_FK=self.ma)
        self.assertIsNone(row.aid_tracking_post_id_FK)
        # The same-name member post captured nothing.
        self.assertEqual(
            AidSetAside.objects.filter(aid_tracking_post_id_FK=self.internal_post).count(), 0)

    def test_ensure_external_post_links_by_item_idempotent(self):
        posts = ensure_external_posts_for_assessment(self.assessment, self.officer)
        self.assertEqual(len(posts), 1)
        post = posts[0]
        self.assertEqual(post.source_type, "external_aid")
        self.assertEqual(post.external_campus, "ISU Echague Campus")
        # Every active member owes a share — nobody excluded.
        self.assertEqual(
            Contribution.objects.filter(aid_tracking_post_id_FK=post).count(), 2)
        self.assertEqual(
            Contribution.objects.filter(
                aid_tracking_post_id_FK=post,
                status=Contribution.STATUS_EXCLUDED_REQUESTER).count(), 0)
        # Idempotent: second call returns the same post, no duplicates.
        again = ensure_external_posts_for_assessment(self.assessment, self.officer)
        self.assertEqual([p.post_id_PK for p in again], [post.post_id_PK])
        self.assertEqual(
            AidTrackingPost.objects.filter(source_type="external_aid").count(), 1)

    def test_link_by_item_picks_up_previously_booked_earmarks(self):
        book_member_fund_rows(self.ma, self.officer, "COL-00078", "September 2026")
        posts = ensure_external_posts_for_assessment(self.assessment, self.officer)
        post = posts[0]
        # ensure_* already linked the pre-booked earmark by item.
        self.assertEqual(setaside_available_for_post(post), Decimal("100.00"))
        # A repeat link call is a harmless no-op (idempotent).
        self.assertEqual(link_set_asides_to_external_post(post, self.ext_item), 0)


class ExternalAidTurnoverTests(TestCase):
    def setUp(self):
        self.treasurer = OfficerUser.objects.create(
            full_name="Treasurer Ext Test", username="treas_ext_1",
            password_hash="unused", role="Treasurer",
            account_status="Active",
            mfa_secret="ext-turnover-secret",
        )
        session, token = create_access_session(
            officer=self.treasurer, ip_address="127.0.0.1", device_info="tests")
        session.trusted_device = True
        session.device_info = ""
        policy = session.session_policy or {}
        policy["zt_verified_at"] = timezone.now().isoformat()
        session.session_policy = policy
        session.save()
        self.token = token

        self.payer = _member("Ana Reyes", "EMP-EXT-101")
        self.assessment = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1), total_amount=Decimal("300.00"))
        self.ext_item = AssessmentItem.objects.create(
            assessment_id_FK=self.assessment,
            purpose=AssessmentItem.PURPOSE_MEDICAL_AID,
            amount=Decimal("100.00"),
            recipient="ISU Echague Campus — Ana Santos",
            recipient_type="external",
            external_campus="ISU Echague Campus",
            external_beneficiary="Ana Santos",
            priority_order=1,
        )
        self.ma = MemberAssessment.objects.create(
            assessment_id_FK=self.assessment, member_id_FK=self.payer,
            standard_assessment=Decimal("300.00"),
            actual_deduction=Decimal("300.00"),
            status=MemberAssessment.STATUS_APPROVED,
        )
        MemberAssessmentAllocation.objects.create(
            member_assessment_id_FK=self.ma,
            assessment_item_id_FK=self.ext_item,
            amount_applied=Decimal("100.00"),
            amount_remaining=Decimal("0.00"),
        )
        FundTransaction.objects.create(
            direction="inflow", amount=Decimal("1000.00"),
            source_type="manual_adjustment", source_id=4242,
            description="Seeded general fund",
            recorded_by_user_id_FK=self.treasurer,
        )
        book_member_fund_rows(self.ma, self.treasurer, "COL-00088", "September 2026")
        posts = ensure_external_posts_for_assessment(self.assessment, self.treasurer)
        self.post = posts[0]
        link_set_asides_to_external_post(self.post, self.ext_item)

    def _login(self):
        s = self.client.session
        s["access_token"] = self.token
        s["officer_id"] = self.treasurer.user_id_PK
        s["role"] = "Treasurer"
        s.save()

    def _proof(self, color="navy"):
        # Real decodable image: proof receipts pass the secure-upload
        # validators (magic bytes + Pillow verify + duplicate check).
        from io import BytesIO

        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (72, 54), color).save(buf, format="JPEG")
        proof = SimpleUploadedFile("ack.jpg", buf.getvalue(),
                                   content_type="image/jpeg")
        return proof

    def _turnover(self, **extra):
        self._login()
        payload = {"post_id": str(self.post.post_id_PK),
                   "received_by": "Echague Representative"}
        payload.update(extra)
        if "proof_receipt" not in payload:
            # attach via data dict merging below
            pass
        data = dict(payload)
        proof = data.pop("proof_receipt", self._proof())
        data["proof_receipt"] = proof
        return self.client.post("/api/treasurer/external-aid-turnover/", data)

    def test_turnover_requires_received_by(self):
        self._login()
        resp = self.client.post("/api/treasurer/external-aid-turnover/", {
            "post_id": str(self.post.post_id_PK),
            "proof_receipt": self._proof(),
        })
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(resp.json().get("requires_received_by"))

    def test_turnover_requires_proof(self):
        self._login()
        resp = self.client.post("/api/treasurer/external-aid-turnover/", {
            "post_id": str(self.post.post_id_PK),
            "received_by": "Echague Representative",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(resp.json().get("requires_proof"))

    def test_turnover_books_single_ot_outflow_and_closes_post(self):
        resp = self._turnover()
        self.assertEqual(resp.status_code, 200, resp.json())
        outflows = list(FundTransaction.objects.filter(
            direction="outflow").values_list("amount", "source_type", "source_id"))
        self.assertEqual(len(outflows), 1)
        amount, source_type, source_id = outflows[0]
        self.assertEqual(amount, Decimal("100.00"))
        self.assertEqual(source_type, "other_transaction")
        self.assertEqual(source_id, self.post.post_id_PK)
        self.post.refresh_from_db()
        self.assertEqual(self.post.finish_status, "approved")
        self.assertFalse(self.post.is_active)
        # Earmark drawn down, nothing left dangling.
        self.assertEqual(setaside_available_for_post(self.post), Decimal("0.00"))

    def test_second_turnover_is_refused(self):
        first = self._turnover()
        self.assertEqual(first.status_code, 200, first.json())
        # Post is closed now; endpoint reports not pending.
        second = self._turnover()
        self.assertIn(second.status_code, (400, 404))

    def test_member_release_refuses_external_post(self):
        self._login()
        session = self.client.session
        from core_system.services.mfa_service import generate_otp
        session["aid_release_otp"] = {
            "post_id": int(self.post.post_id_PK),
            "sent_at": timezone.now().timestamp(),
            "expires_at": (timezone.now() + timedelta(seconds=300)).isoformat(),
        }
        session.save()
        otp = generate_otp(self.treasurer.mfa_secret or "")
        resp = self.client.post("/api/treasurer/aid-post-release/", {
            "post_id": str(self.post.post_id_PK),
            "received_by": "Someone",
            "otp": otp,
        })
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertTrue(resp.json().get("is_external"))
        # No money moved through the member path.
        self.assertEqual(
            FundTransaction.objects.filter(direction="outflow").count(), 0)
