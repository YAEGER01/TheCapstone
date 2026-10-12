"""Tests for the offline proof-of-work bot check (Turnstile fallback)."""

import hashlib
import json

from django.test import TestCase, override_settings
from django.utils import timezone

from core_system import offline_botcheck as botcheck
from core_system.auth_utils import hash_password
from core_system.models import OfflineBotChallenge, OfficerUser


def _solve(salt, bits):
    """Reference solver (mirrors the login page algorithm)."""
    full, rest = divmod(bits, 8)
    nonce = 0
    while True:
        d = hashlib.sha256(f"{salt}:{nonce}".encode()).digest()
        if d[:full] == b"\x00" * full and (not rest or (d[full] >> (8 - rest)) == 0):
            return str(nonce)
        nonce += 1


class OfflineBotcheckServiceTests(TestCase):
    def test_mint_verify_burn(self):
        pub = botcheck.mint_challenge("alice")
        self.assertIn("id", pub)
        self.assertEqual(pub["difficulty"], botcheck.get_difficulty())
        nonce = _solve(pub["salt"], pub["difficulty"])
        ok, method = botcheck.verify_proof(challenge_id=pub["id"], username="alice", nonce=nonce)
        self.assertTrue(ok)
        self.assertEqual(method, "offline_pow")
        # Replay burns.
        ok, reason = botcheck.verify_proof(challenge_id=pub["id"], username="alice", nonce=nonce)
        self.assertFalse(ok)
        self.assertEqual(reason, "reused")

    def test_username_binding(self):
        pub = botcheck.mint_challenge("alice")
        nonce = _solve(pub["salt"], pub["difficulty"])
        ok, reason = botcheck.verify_proof(challenge_id=pub["id"], username="bob", nonce=nonce)
        self.assertFalse(ok)
        self.assertEqual(reason, "username_mismatch")

    def test_insufficient_work_rejected(self):
        pub = botcheck.mint_challenge("alice")
        ok, reason = botcheck.verify_proof(challenge_id=pub["id"], username="alice", nonce="0")
        # Nonce 0 almost surely lacks 16 leading zero bits; if it flukes, skip.
        row = OfflineBotChallenge.objects.get(challenge_id=pub["id"])
        d = hashlib.sha256(f"{row.salt}:0".encode()).digest()
        if botcheck.digest_meets_difficulty(d, row.difficulty):
            self.skipTest("nonce 0 fluked a valid proof")
        self.assertFalse(ok)
        self.assertEqual(reason, "insufficient_work")

    def test_expiry(self):
        pub = botcheck.mint_challenge("alice")
        row = OfflineBotChallenge.objects.get(challenge_id=pub["id"])
        nonce = _solve(row.salt, row.difficulty)
        row.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        row.save(update_fields=["expires_at"])
        ok, reason = botcheck.verify_proof(challenge_id=pub["id"], username="alice", nonce=nonce)
        self.assertFalse(ok)
        self.assertEqual(reason, "expired")


@override_settings(TURNSTILE_SITE_KEY="test-key", TURNSTILE_SECRET_KEY="test-secret")
class OfflineBotcheckLoginTests(TestCase):
    def _officer(self):
        return OfficerUser.objects.create(
            full_name="Bot Test",
            username="botofficer",
            password_hash=hash_password("TestPass123!"),
            role="Secretary",
            account_status="Active",
            email="bot@example.com",
        )

    def test_challenge_endpoint_needs_username(self):
        r = self.client.get("/api/auth/bot-check/challenge/")
        self.assertEqual(r.status_code, 400)
        r = self.client.get("/api/auth/bot-check/challenge/", {"username": "botofficer"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        self.assertIn("salt", r.json())

    def test_login_with_offline_proof_and_bad_turnstile(self):
        self._officer()
        chal = self.client.get("/api/auth/bot-check/challenge/", {"username": "botofficer"}).json()
        nonce = _solve(chal["salt"], chal["difficulty"])
        proof = json.dumps({"id": chal["id"], "nonce": nonce})
        # Wrong password + valid proof -> password error, NOT turnstile error.
        r = self.client.post("/login/", {
            "username": "botofficer",
            "password": "Wrong123!",
            "cf-turnstile-response": "",
            "offline_bot_proof": proof,
        })
        body = r.content.decode()
        self.assertNotIn("turnstile_failed", body)
        self.assertNotIn("Security Verification Failed", body)

    def test_login_without_any_proof_still_blocked(self):
        self._officer()
        r = self.client.post("/login/", {
            "username": "botofficer",
            "password": "TestPass123!",
            "cf-turnstile-response": "",
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json().get("error_code"), "turnstile_failed")
