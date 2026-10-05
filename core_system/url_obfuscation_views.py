"""Views for the URL encryption & obfuscation service.

- ``obfuscated_not_found_view``: branded 404 for unknown routes AND
  tampered obfuscated URLs (wired as ``handler404`` in both URLconfs).
- ``session_expired_envelope``: public helper returning the opaque
  ``/?x=...`` session-expired link for JS-driven redirects (the session
  is already dead in that flow, so no auth is required — the payload is
  a static flag, not data).
- ``sign_urls``: batch URL signer for scripts that must build a signed
  link synchronously (uses the caller's per-session subkey).
"""
from __future__ import annotations

import json
import logging

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from core_system import url_obfuscation as obf

logger = logging.getLogger(__name__)


def obfuscated_not_found_view(request: HttpRequest, exception=None) -> HttpResponse:
    try:
        logger.warning("URL-OBF 404: %s", request.get_full_path())
    except Exception:
        pass
    try:
        return render(request, "404.html", status=404)
    except Exception:
        return HttpResponse("<h1>404 — Page not found</h1>", status=404)


@require_GET
def session_expired_envelope(request: HttpRequest) -> JsonResponse:
    """Return the obfuscated session-expired landing URL (no auth needed)."""
    if not obf.is_enabled():
        return JsonResponse({"ok": True, "url": "/?session_expired=1"})
    return JsonResponse({"ok": True, "url": obf.session_expired_url()})


@require_POST
def sign_urls(request: HttpRequest) -> JsonResponse:
    """Sign one batch of URLs with the caller's session subkey."""
    if not obf.is_enabled():
        return JsonResponse({"ok": False, "error": "URL obfuscation is disabled."}, status=400)
    key = obf.get_session_key(request)
    if not key:
        return JsonResponse({"ok": False, "error": "No signing key for this session."}, status=401)
    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, TypeError):
        payload = {}
    urls = payload.get("urls")
    if isinstance(urls, str):
        urls = [urls]
    if not isinstance(urls, list) or not urls or len(urls) > 50:
        return JsonResponse({"ok": False, "error": "Provide 1–50 urls."}, status=400)
    signed = []
    for raw in urls:
        try:
            signed.append(obf.sign_url(str(raw), key))
        except Exception:
            signed.append(str(raw))
    if isinstance(payload.get("urls"), str):
        return JsonResponse({"ok": True, "url": signed[0]})
    return JsonResponse({"ok": True, "urls": signed})
