"""Monthly-deduction document re-upload guard.

The President's form refuses a previously attached scan client-side by
comparing the picked file's SHA-256 against the hashes the list endpoint
reports. These tests pin the server side of that contract:

* the list payload carries ``sha256`` for every attached image
* uploading the same content again — even renamed — is rejected with 409
  and the stored set does not grow
"""

import base64
import hashlib
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from core_system.models import MonthlyAssessmentDocument, OfficerUser
from core_system.tests import _create_zt_verified_session

# Smallest valid 1x1 PNG — validate_and_store sniffs magic bytes and decodes.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

UPLOAD_URL = "/api/president/monthly-assessment/{aid}/upload-documents/"
LIST_URL = "/api/president/monthly-assessment/list/"


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="ma-doc-test-"))
class MonthlyAssessmentDocHashTests(TestCase):
    def _login_president(self, suffix):
        officer = OfficerUser.objects.create(
            full_name=f"President DocHash {suffix}",
            username=f"president_dh_{suffix}_{timezone.now().timestamp()}",
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

    def _create_assessment(self):
        self._login_president("create")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            data='{"month": "2026-10", "items": [{"purpose": "monthly_due", "amount": 100, "priority_order": 1}]}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["assessment"]["assessment_id"]

    def _list_assessment(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        return next(
            a for a in payload["assessments"] if a["month"].startswith("2026-10")
        )

    def _upload(self, assessment_id, filename, content, kind="request_letter"):
        return self.client.post(
            UPLOAD_URL.format(aid=assessment_id),
            data={kind: SimpleUploadedFile(filename, content, content_type="image/png")},
            format="multipart",
        )

    def test_uploaded_image_sha256_is_exposed_by_list(self):
        aid = self._create_assessment()
        response = self._upload(aid, "letter.png", PNG_1X1)
        self.assertEqual(response.status_code, 200, response.content)

        entry = self._list_assessment()["request_letter_images"][0]
        self.assertEqual(entry["sha256"], hashlib.sha256(PNG_1X1).hexdigest())

    def test_reupload_same_content_renamed_is_rejected(self):
        aid = self._create_assessment()
        first = self._upload(aid, "letter.png", PNG_1X1)
        self.assertEqual(first.status_code, 200, first.content)

        # Same bytes under a different filename — must not attach twice.
        second = self._upload(aid, "totally-different-name.png", PNG_1X1)
        self.assertEqual(second.status_code, 409, second.content)
        self.assertIn("already attached", second.json()["error"])

        month = self._list_assessment()
        self.assertEqual(len(month["request_letter_images"]), 1)
        self.assertEqual(
            MonthlyAssessmentDocument.objects.filter(assessment_id_FK_id=aid).count(), 1
        )
