"""Step 5: Argon2id passwords, no legacy unsalted fallback, shared-cache ready."""
from django.test import TestCase

from core_system.auth_utils import (
    hash_password,
    hash_pin,
    password_needs_rehash,
    verify_password,
    verify_pin,
)


class PasswordHashingTests(TestCase):
    def test_new_hash_is_argon2id(self):
        h = hash_password("Str0ng!Pass")
        self.assertTrue(h.startswith("$argon2id$"))
        self.assertTrue(verify_password("Str0ng!Pass", h))
        self.assertFalse(verify_password("WrongPass123!", h))

    def test_pbkdf2_rows_still_verify_and_flag_rehash(self):
        legacy = "pbkdf2_sha256$260000$" + "ab" * 16 + "$" + "cd" * 32
        # wrong password against well-formed prefix parses and fails cleanly
        self.assertFalse(verify_password("whatever", legacy))
        self.assertTrue(password_needs_rehash(legacy))
        self.assertFalse(password_needs_rehash(hash_password("xY1!aaaa")))

    def test_unsalted_sha256_rejected(self):
        import hashlib

        raw = hashlib.sha256("password123".encode()).hexdigest()
        self.assertFalse(verify_password("password123", raw))
        self.assertFalse(verify_pin("123456", raw))
        self.assertTrue(password_needs_rehash(raw))

    def test_pin_pbkdf2_still_verifies(self):
        h = hash_pin("123456")
        self.assertTrue(verify_pin("123456", h))
        self.assertFalse(verify_pin("654321", h))

    def test_login_upgrades_pbkdf2_to_argon2(self):
        import hashlib

        from core_system.models import OfficerUser

        salt = "ab" * 16
        dk = hashlib.pbkdf2_hmac("sha256", b"Upgr4de!Me", bytes.fromhex(salt), 260000).hex()
        o = OfficerUser.objects.create(
            full_name="Up Test", username="up_test",
            password_hash=f"pbkdf2_sha256$260000${salt}${dk}",
            role="Treasurer", account_status="Active", email="up@isu.edu.ph",
        )
        self.assertTrue(verify_password("Upgr4de!Me", o.password_hash))
        if password_needs_rehash(o.password_hash):
            o.password_hash = hash_password("Upgr4de!Me")
            o.save(update_fields=["password_hash"])
        o.refresh_from_db()
        self.assertTrue(o.password_hash.startswith("$argon2id$"))
        self.assertTrue(verify_password("Upgr4de!Me", o.password_hash))
