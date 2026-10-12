"""Offline bot check: proof-of-work fallback when Cloudflare is unreachable.

Turnstile needs the device to reach challenges.cloudflare.com. When it can't
(ad-blocker, filtered network, offline LAN), the login page offers this
second option instead of dead-ending:

  1. Browser fetches a challenge bound to the typed username:
     ``GET /api/auth/bot-check/challenge/?username=...``
  2. Browser finds a nonce (fully offline, WebCrypto SHA-256) such that
     ``SHA256("<salt>:<nonce>")`` has ``difficulty`` leading zero bits.
     At 16 bits that is ~65k hashes — under a second on desktop, a few
     seconds on a phone. The page shows live progress.
  3. Browser posts ``offline_bot_proof = {"id": ..., "nonce": "..."}``
     with the login form. The server re-hashes ONCE, checks the username
     binding, expiry and single-use, then burns the challenge.

Combined with the existing login throttle (repeated bad passwords still lock
the account), this raises bulk-attack cost without any third party.
"""

from __future__ import annotations

import hashlib
import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core_system.models import OfflineBotChallenge

CHALLENGE_TTL_SECONDS = 10 * 60
MAX_ACTIVE_PER_USER = 5


def get_difficulty() -> int:
    try:
        return max(8, min(24, int(getattr(settings, "OFFLINE_BOTCHECK_BITS", 16))))
    except (TypeError, ValueError):
        return 16


def digest_meets_difficulty(digest: bytes, bits: int) -> bool:
    """True when the digest has at least `bits` leading zero bits."""
    full_zero_bytes, rest_bits = divmod(bits, 8)
    if digest[:full_zero_bytes] != b"\x00" * full_zero_bytes:
        return False
    if rest_bits:
        if len(digest) <= full_zero_bytes:
            return False
        return (digest[full_zero_bytes] >> (8 - rest_bits)) == 0
    return True


def preimage(salt: str, nonce: str) -> bytes:
    return f"{salt}:{nonce}".encode("utf-8")


def _cleanup(username: str) -> None:
    now = timezone.now()
    OfflineBotChallenge.objects.filter(
        username=username,
    ).filter(
        expires_at__lte=now,
    ).delete()


@transaction.atomic
def mint_challenge(username: str) -> dict:
    """Create (or reuse) a challenge for `username`. Never raises."""
    username = (username or "").strip()[:150]
    _cleanup(username)
    existing = (
        OfflineBotChallenge.objects
        .filter(username=username, used_at__isnull=True, expires_at__gt=timezone.now())
        .order_by("-created_at")
        .first()
    )
    if existing is not None:
        return _public(existing)
    if OfflineBotChallenge.objects.filter(
        username=username, used_at__isnull=True, expires_at__gt=timezone.now()
    ).count() >= MAX_ACTIVE_PER_USER:
        oldest = (
            OfflineBotChallenge.objects
            .filter(username=username, used_at__isnull=True)
            .order_by("created_at")
            .first()
        )
        if oldest is not None:
            return _public(oldest)
    row = OfflineBotChallenge.objects.create(
        challenge_id=secrets.token_hex(16),
        username=username,
        salt=secrets.token_hex(16),
        difficulty=get_difficulty(),
        expires_at=timezone.now() + timezone.timedelta(seconds=CHALLENGE_TTL_SECONDS),
    )
    return _public(row)


def _public(row: OfflineBotChallenge) -> dict:
    return {
        "id": row.challenge_id,
        "salt": row.salt,
        "difficulty": row.difficulty,
        "expires_in": max(0, int((row.expires_at - timezone.now()).total_seconds())),
    }


@transaction.atomic
def verify_proof(*, challenge_id: str, username: str, nonce: str) -> tuple[bool, str]:
    """Check a submitted proof. Burns the challenge on success.

    Returns (ok, method_or_reason). `method_or_reason` is "offline_pow" on
    success (for audit notes) or a short machine-readable reason otherwise.
    """
    cid = (challenge_id or "").strip()
    nonce = (nonce or "").strip()
    username = (username or "").strip()
    if not cid or not nonce or not username or len(nonce) > 64:
        return False, "malformed"
    try:
        row = OfflineBotChallenge.objects.select_for_update().get(challenge_id=cid)
    except OfflineBotChallenge.DoesNotExist:
        return False, "unknown"
    if row.used_at is not None:
        return False, "reused"
    if row.expires_at <= timezone.now():
        return False, "expired"
    if row.username.lower() != username.lower():
        return False, "username_mismatch"
    digest = hashlib.sha256(preimage(row.salt, nonce)).digest()
    if not digest_meets_difficulty(digest, row.difficulty):
        return False, "insufficient_work"
    row.used_at = timezone.now()
    row.save(update_fields=["used_at"])
    return True, "offline_pow"
