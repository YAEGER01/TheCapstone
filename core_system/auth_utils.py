import hashlib
import secrets
from datetime import timedelta
from ipaddress import ip_address

from typing import Optional


from django.db import transaction
from django.utils import timezone

from core_system.models import AccessSession, LoginAttemptLog, OfficerUser


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _argon2_hasher():
    from argon2 import PasswordHasher

    # OWASP Argon2id defaults (m=64MiB, t=3, p=4). Login is infrequent;
    # ~0.3s per verify is the brute-force price attackers pay, not users.
    return PasswordHasher()


_PIN_PBKDF2_ITERATIONS = 200_000
_PIN_PREFIX = "pin_pbkdf2_sha256"


def hash_pin(pin: str) -> str:
    """Hash a 6-digit PIN using salted PBKDF2-HMAC-SHA256.

    Format: pin_pbkdf2_sha256$<iterations>$<salt_hex>$<dk_hex>
    This replaces the old unsalted SHA-256 scheme to prevent offline
    brute-force of the 1M possible 6-digit PINs.
    """
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("utf-8"),
        bytes.fromhex(salt),
        _PIN_PBKDF2_ITERATIONS,
    )
    return f"{_PIN_PREFIX}${_PIN_PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    """Verify a PIN against a salted PBKDF2 hash. Legacy unsalted SHA-256
    hashes are REJECTED (step 5) — those rows were neutralized, see
    SECURITY_MANUAL_STEPS.md."""
    if not stored:
        return False
    if not stored.startswith(_PIN_PREFIX + "$"):
        return False
    try:
        _prefix, iterations_s, salt_hex, expected_hex = stored.split("$", 3)
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            pin.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations_s),
        )
        return secrets.compare_digest(dk.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


_PBKDF2_ITERATIONS = 260_000
_PBKDF2_PREFIX = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    """Hash a password with Argon2id (PHC string, e.g. ``$argon2id$v=19$...``).

    Existing PBKDF2 rows keep verifying (below) and are transparently
    upgraded to Argon2id on next successful login.
    """
    return _argon2_hasher().hash(password)


def verify_password(password: str, stored: str) -> bool:
    """Verify against Argon2id, then legacy salted PBKDF2. Raw unsalted
    SHA-256 hashes are REJECTED (step 5)."""
    if not stored:
        return False
    if stored.startswith("$argon2"):
        try:
            return _argon2_hasher().verify(stored, password)
        except Exception:
            return False
    if stored.startswith(_PBKDF2_PREFIX + "$"):
        try:
            _prefix, iterations_s, salt_hex, expected_hex = stored.split("$", 3)
            dk = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                bytes.fromhex(salt_hex),
                int(iterations_s),
            )
            return secrets.compare_digest(dk.hex(), expected_hex)
        except (ValueError, TypeError):
            return False
    return False


def password_needs_rehash(stored: str) -> bool:
    """True when a verified hash should be upgraded to current Argon2id params."""
    if not stored or not stored.startswith("$argon2"):
        return True
    try:
        return _argon2_hasher().check_needs_rehash(stored)
    except Exception:
        return True


# Canonical password-strength rules. These mirror the client-side meter on
# the reset/change password pages and MUST be enforced server-side everywhere
# a user-chosen password is set (reset, change, officer create/edit, profile
# updates) — never just length-checked in one place.
PASSWORD_MIN_LENGTH = 8
PASSWORD_SPECIAL_CHARS = "!@#$%^&*"


def validate_new_password(password: str) -> list[str]:
    """Return a list of unmet strength requirements (empty = strong enough)."""
    errors: list[str] = []
    pw = password or ""
    if len(pw) < PASSWORD_MIN_LENGTH:
        errors.append(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
    if not any(c.isupper() for c in pw):
        errors.append("Password must contain at least 1 uppercase letter.")
    if not any(c.islower() for c in pw):
        errors.append("Password must contain at least 1 lowercase letter.")
    if not any(c.isdigit() for c in pw):
        errors.append("Password must contain at least 1 number.")
    if not any((not c.isalnum()) for c in pw):
        errors.append(f"Password must contain at least 1 special character ({PASSWORD_SPECIAL_CHARS}).")
    return errors


@transaction.atomic
def create_access_session(
    *,
    officer: OfficerUser,
    ip_address: str | None = None,
    device_info: str | None = None,
    device_id: str | None = None,
    device_secret: str | None = None,
    mtls_fp: str | None = None,
):
    """Creates an ACCESS_SESSION row and returns (session, token). Revokes all existing sessions for the user to enforce NO MULTI-LOGIN.

    When ``device_id``/``device_secret`` are supplied (see
    ``core_system.device_binding``), the session is cryptographically bound:
    only ``session_policy["device_bound"]["device_secret_hash"]`` is stored,
    and per-request proofs are verified in ``ZeroTrustMiddleware``.
    """

    # Revoke all existing active sessions for this user (NO MULTI-LOGIN)
    AccessSession.objects.filter(
        user_id_FK=officer,
        session_status="Active"
    ).update(
        session_status="Revoked",
        revoked_at=timezone.now(),
        expires_at=timezone.now()  # Immediately expire old sessions
    )

    token_id = secrets.token_urlsafe(32)

    session_policy: dict = {}
    if device_id and device_secret:
        from core_system.device_binding import bind_session_policy

        session_policy = bind_session_policy(
            session_policy, device_id=device_id,
            secret=device_secret, mtls_fp=mtls_fp or "",
        )

    session = AccessSession.objects.create(
        user_id_FK=officer,
        token_id=token_id,
        ip_address=ip_address or "0.0.0.0",
        device_info=device_info,
        expires_at=timezone.now() + timedelta(hours=8),
        session_status="Active",
        last_activity_at=timezone.now(),
        trusted_device=False,
        session_policy=session_policy,
    )
    return session, token_id


def verify_officer_password(*, officer: OfficerUser, password_input: str) -> bool:
    if not officer.account_status or officer.account_status.lower() != "active":
        return False
    return verify_password(password_input, officer.password_hash)


@transaction.atomic
def log_login_attempt(
    *,
    username: str,
    ip_address: str,
    device_info: str | None,
    result: str,
    user_id: int | None
):
    LoginAttemptLog.objects.create(
        user_id_FK_id=user_id,
        username_used=username,
        ip_address=ip_address,
        device_info=device_info,
        result=result,
    )
