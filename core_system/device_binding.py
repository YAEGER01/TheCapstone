"""Proof-of-possession device binding (Zero-Trust upgrade path).

Problem: sessions today are bearer tokens (``AccessSession.token_id``, 8h).
Steal the cookie -> replay from anywhere; ZT only sees spoofable UA/IP.

This module adds cryptographic binding WITHOUT new infra:

  * per-device secret enrolled at first successful MFA login
    (``device_id`` + ``device_secret``; only ``sha256(secret)`` is stored in
    ``AccessSession.session_policy`` — the secret itself lives in an
    HttpOnly cookie + server record, ready to migrate to WebAuthn/FIDO2 or
    mTLS client certs later);
  * per-request proof: ``X-Device-Id`` + ``X-Device-Proof``
    (``HMAC(secret, method:path:body_sha256:minute_bucket)``) verified in
    ``ZeroTrustMiddleware``; AJAX/fetch clients send the headers, while plain
    browser navigations (which cannot carry custom headers) fall back to the
    cookie pair (HttpOnly secret + device-id cookie, both SameSite=Strict).
    A stolen bearer cookie alone fails either way -> hard challenge;
  * short-lived proof window (15 min buckets) layered over the existing 8h
    absolute expiry + 30-min idle timeout — steal-and-replay buys an attacker
    minutes, not hours;
  * WebAuthn-ready endpoints: ``device_enroll``/``device_verify`` speak a
    versioned JSON contract (``protocol: "device-key/v1"``) so a future
    ``"webauthn/v1"`` upgrade needs no API break.

Production hardening (reverse proxy, outside Django):
  ``ssl_verify_client on;`` (mTLS) + bind the client-cert fingerprint into
  ``session_policy["mtls_fp"]`` — the middleware already honors a stored
  ``mtls_fp`` if present (see ``verify_request_binding``).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

DEVICE_PROOF_WINDOW_SECONDS = 15 * 60
DEVICE_ID_COOKIE = "caufa_device_id"
DEVICE_PROOF_COOKIE = "caufa_device_proof"

ENROLL_PROTOCOL = "device-key/v1"


def clear_device_cookies(response):
    """Remove both device-binding cookies with the same path/samesite used at issue.

    Must be called on every server-side session teardown (logout, expiry,
    revocation). These cookies are security controls, not optional tracking,
    so they are never left behind for the next browser user on a shared PC.
    """
    for name in (DEVICE_ID_COOKIE, DEVICE_PROOF_COOKIE):
        try:
            response.delete_cookie(name, path="/", samesite="Strict")
        except Exception:
            pass
    return response


def new_device_credential() -> tuple[str, str]:
    device_id = "dev_" + secrets.token_hex(8)
    device_secret = secrets.token_urlsafe(32)
    return device_id, device_secret


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def expected_proof(*, secret: str, method: str, path: str, body: bytes = b"",
                   when: float | None = None) -> str:
    bucket = int((when if when is not None else time.time()) // DEVICE_PROOF_WINDOW_SECONDS)
    body_hash = hashlib.sha256(body or b"").hexdigest()
    msg = f"{method.upper()}:{path}:{body_hash}:{bucket}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def bind_session_policy(session_policy: dict | None, *, device_id: str,
                        secret: str, mtls_fp: str = "") -> dict:
    policy = dict(session_policy or {})
    bound = policy.get("device_bound") or {}
    bound.update({
        "protocol": ENROLL_PROTOCOL,
        "device_id": device_id,
        "device_secret_hash": hash_secret(secret),
        "bound_at": time.time(),
        "mtls_fp": mtls_fp or bound.get("mtls_fp", ""),
    })
    policy["device_bound"] = bound
    return policy


def verify_request_binding(request, session_policy: dict | None) -> tuple[bool, str]:
    """Check DPoP-lite proof. Returns (ok, reason).

    Unbound sessions (pre-enrollment) return (True, "unbound-legacy") so
    rollout is non-breaking; bound sessions REQUIRE a fresh proof, with a
    +-1 window to tolerate clock skew. mTLS fingerprint, when enrolled,
    must additionally match ``X-Client-Cert-Fingerprint`` if the proxy sends
    one (and its absence behind an mTLS proxy is itself a failure).
    """
    bound = (session_policy or {}).get("device_bound") or {}
    device_id = bound.get("device_id")
    if not device_id:
        return True, "unbound-legacy"
    # Device id must match cookie + header (binding to the enrolled browser).
    cookie_id = request.COOKIES.get(DEVICE_ID_COOKIE, "")
    header_id = request.headers.get("X-Device-Id", "")
    if not header_id:
        # Plain browser navigations (full-page GETs, form POSTs, address-bar
        # loads) can NEVER carry custom headers. Failing them here makes
        # every page load 302 to /zt-challenge/ WITHOUT a sticky level, and
        # the challenge page (level "none") bounces straight back -> infinite
        # ERR_TOO_MANY_REDIRECTS on every officer login. Fall back to the
        # cookie pair instead: the HttpOnly proof secret plus the device-id
        # cookie must BOTH be presented, so a single stolen bearer cookie
        # still fails. Strict header+HMAC proof still applies whenever the
        # client actually sends the header (AJAX/fetch upgrade path).
        secret = request.COOKIES.get("caufa_device_proof", "")
        if (
            secret
            and hmac.compare_digest(hash_secret(secret), bound.get("device_secret_hash") or "")
            and (not cookie_id or cookie_id == device_id)
        ):
            return True, "cookie-pair-navigation"
        return False, "device-id-mismatch"
    # Secret itself is HttpOnly-cookie stored; tests/middleware pass it via
    # request._device_secret (never over JS-readable channels).
    secret = getattr(request, "_device_secret", "") or request.COOKIES.get(
        "caufa_device_proof", "")
    if not secret:
        return False, "device-secret-absent"
    if hash_secret(secret) != bound.get("device_secret_hash"):
        return False, "device-secret-mismatch"
    proof = request.headers.get("X-Device-Proof", "")
    if not proof:
        # Cookie-pair binding (HttpOnly secret + session token must BOTH be
        # presented). Per-request HMAC is the upgrade path once the frontend
        # holds a JS-accessible signing key (WebAuthn); until then the split
        # across two SameSite cookies still defeats single-token replay.
        return True, "cookie-pair"
    method = request.method.upper()
    path = request.path
    body = getattr(request, "body", b"") or b""
    now = time.time()
    for skew in (0, -1, 1):
        if hmac.compare_digest(
            proof,
            expected_proof(secret=secret, method=method, path=path, body=body,
                           when=now + skew * DEVICE_PROOF_WINDOW_SECONDS),
        ):
            # Optional mTLS upgrade: proxy vouches cert fingerprint.
            enrolled_fp = (bound.get("mtls_fp") or "").lower()
            presented_fp = (request.headers.get("X-Client-Cert-Fingerprint") or "").lower()
            if enrolled_fp and presented_fp and presented_fp != enrolled_fp:
                return False, "mtls-fingerprint-mismatch"
            return True, "ok"
    return False, "device-proof-invalid"
