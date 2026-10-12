"""Pre-login proof-of-work challenge minting (offline Turnstile fallback)."""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from core_system import offline_botcheck


@require_GET
def bot_challenge(request: HttpRequest):
    """Mint (or reuse) a bot-check challenge for the typed username.

    No login needed — this runs before authentication. Challenges are bound
    to the username, expire in 10 minutes, and burn on first verification.
    """
    username = (request.GET.get("username") or "").strip()
    if not username:
        return JsonResponse({"ok": False, "error": "Type your username first."}, status=400)
    if len(username) > 150:
        return JsonResponse({"ok": False, "error": "Username too long."}, status=400)
    try:
        return JsonResponse({"ok": True, **offline_botcheck.mint_challenge(username)})
    except Exception:
        return JsonResponse({"ok": False, "error": "Could not start the offline check."}, status=500)
