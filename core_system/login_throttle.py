"""Server-side login throttling / lockout (brute-force guard).

Previously only the MFA *email* send was rate-limited; password guessing was
unbounded and ``LoginAttemptLog`` never blocked. This module enforces:

  * 5 failed password attempts per (username + IP) in 15 min -> 15-min lockout
  * 10 failed attempts per IP in 15 min -> 15-min IP lockout (credential stuffing)
  * counters live in Django cache (works with locmem; use Redis in prod via
    ``CACHES``) AND are mirrored into ``LoginAttemptLog`` for audit.

Wire-in: call :func:`check_throttle` BEFORE verifying the password in
``officer_login``; call :func:`record_failure` on bad password / disabled
account; call :func:`clear_principal` after a successful password check.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

MAX_ATTEMPTS_PER_PRINCIPAL = 5
MAX_ATTEMPTS_PER_IP = 10
WINDOW_SECONDS = 15 * 60
LOCKOUT_SECONDS = 15 * 60


def _principal_key(username: str, ip: str) -> str:
    return f"loginfail:u:{(username or '').strip().lower()}:{ip or ''}"


def _ip_key(ip: str) -> str:
    return f"loginfail:ip:{ip or ''}"


def _failures_since(username: str, ip: str, window_seconds: int = WINDOW_SECONDS) -> tuple[int, int]:
    """DB-backed count (audit of record) for (username+ip) and ip-wide."""
    try:
        from core_system.models import LoginAttemptLog

        cutoff = timezone.now() - timedelta(seconds=window_seconds)
        principal_qs = LoginAttemptLog.objects.filter(attempted_at__gte=cutoff)
        if username:
            principal_qs = principal_qs.filter(username_used__iexact=(username or "").strip())
        if ip:
            principal_qs = principal_qs.filter(ip_address=ip)
        principal_fails = principal_qs.exclude(result__in=("Success", "MFA_REQUIRED")).count()
        ip_fails = LoginAttemptLog.objects.filter(
            attempted_at__gte=cutoff, ip_address=ip
        ).exclude(result__in=("Success", "MFA_REQUIRED")).count()
        return principal_fails, ip_fails
    except Exception:
        return 0, 0


def check_throttle(username: str, ip: str) -> tuple[bool, str, int]:
    """Return (locked, reason, retry_after_seconds)."""
    p_count = cache.get(_principal_key(username, ip), 0)
    ip_count = cache.get(_ip_key(ip), 0)
    if p_count >= MAX_ATTEMPTS_PER_PRINCIPAL:
        return True, "account", LOCKOUT_SECONDS
    if ip_count >= MAX_ATTEMPTS_PER_IP:
        return True, "ip", LOCKOUT_SECONDS
    # Cache may be cold (restart) — fall back to DB counts so a restart
    # does not reset an active attack window.
    db_principal, db_ip = _failures_since(username, ip)
    if db_principal >= MAX_ATTEMPTS_PER_PRINCIPAL:
        return True, "account", LOCKOUT_SECONDS
    if db_ip >= MAX_ATTEMPTS_PER_IP:
        return True, "ip", LOCKOUT_SECONDS
    return False, "", 0


def record_failure(username: str, ip: str) -> None:
    try:
        p_key, i_key = _principal_key(username, ip), _ip_key(ip)
        try:
            cache.add(p_key, 0, LOCKOUT_SECONDS)
            cache.incr(p_key)
        except ValueError:
            cache.set(p_key, 1, LOCKOUT_SECONDS)
        try:
            cache.add(i_key, 0, LOCKOUT_SECONDS)
            cache.incr(i_key)
        except ValueError:
            cache.set(i_key, 1, LOCKOUT_SECONDS)
    except Exception:
        pass


def clear_principal(username: str, ip: str) -> None:
    try:
        cache.delete(_principal_key(username, ip))
    except Exception:
        pass
