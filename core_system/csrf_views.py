"""CSRF failure view that speaks JSON to AJAX callers.

Django's default 403 page is HTML. Every dashboard posts via fetch and calls
resp.json(), so an HTML 403 surfaces as "Unexpected token '<' ... is not
valid JSON" followed by a generic "Failed to save." toast — the officer never
learns it was a stale/missing CSRF token fixed by reloading the page.

With CSRF_FAILURE_VIEW pointed here, AJAX callers (X-Requested-With or
Accept: application/json) get {"ok": False, "csrf_failed": True, ...} and a
plain-language recovery step; normal navigations keep the default HTML page.
"""
from django.http import HttpRequest, JsonResponse
from django.views.defaults import permission_denied


def _wants_json(request: HttpRequest) -> bool:
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("Accept") or "")
    )


def csrf_failure(request: HttpRequest, reason: str = "") -> JsonResponse:
    if not _wants_json(request):
        return permission_denied(request, None)
    # An empty/garbled token almost always means the csrftoken cookie is
    # gone (cleared cookies, localhost<->127.0.0.1 host switch, expired tab)
    # — reloading re-issues it via @ensure_csrf_cookie on the dashboard.
    return JsonResponse(
        {
            "ok": False,
            "csrf_failed": True,
            "error": (
                "Security token check failed. Reload the page and try again. "
                f"({reason})" if reason else
                "Security token check failed. Reload the page and try again."
            ),
        },
        status=403,
    )
