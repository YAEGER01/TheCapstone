import ipaddress
import json
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from django.conf import settings

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def _host_of(request) -> str:
    return getattr(request, "get_host", lambda: "")()


def _is_localhost_host(host: str | None) -> bool:
    if not host:
        return False
    host_value = host.split(":", 1)[0].strip().lower()
    return host_value in {"localhost", "127.0.0.1", "::1"}


def _is_private_network_host(host: str | None) -> bool:
    """True for LAN/dev hosts where Cloudflare Turnstile cannot run.

    Turnstile needs a public, allow-listed domain. A phone opening the dev
    server over Wi-Fi uses a bare private IP (e.g. 192.168.1.4), which makes
    the widget fail with a "troubleshooting" error. Treat those like localhost
    so devices on the same network can still sign in.
    """
    if not host:
        return False
    host_value = host.split(":", 1)[0].strip().lower()
    if host_value.endswith(".local") or _is_localhost_host(host_value):
        return True
    try:
        ip = ipaddress.ip_address(host_value)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def is_localhost_request(request=None) -> bool:
    if request is None:
        return False
    return _is_localhost_host(_host_of(request))


def is_private_network_request(request=None) -> bool:
    if request is None:
        return False
    return _is_private_network_host(_host_of(request))


def is_turnstile_enabled(request=None) -> bool:
    site_key = (getattr(settings, "TURNSTILE_SITE_KEY", "") or "").strip()
    secret_key = (getattr(settings, "TURNSTILE_SECRET_KEY", "") or "").strip()
    if not site_key or not secret_key:
        return False

    host = _host_of(request) if request is not None else ""
    if _is_localhost_host(host):
        return getattr(settings, "TURNSTILE_REQUIRE_ON_LOCALHOST", False)
    if _is_private_network_host(host):
        # Turnstile cannot run on a bare LAN IP, so never block phones on the
        # same Wi-Fi from signing in. Public domains are still enforced below.
        return False

    return True


def get_turnstile_site_key() -> str:
    return (getattr(settings, "TURNSTILE_SITE_KEY", "") or "").strip()


def _post_turnstile_siteverify(token: str, remote_ip: str | None = None) -> dict:
    secret_key = (getattr(settings, "TURNSTILE_SECRET_KEY", "") or "").strip()
    if not token or not secret_key:
        return {"success": False}

    payload = {
        "secret": secret_key,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    body = urllib_parse.urlencode(payload).encode("utf-8")
    req = urllib_request.Request(
        TURNSTILE_VERIFY_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib_request.urlopen(req, timeout=3) as response:
            data = response.read().decode("utf-8")
            return json.loads(data)
    except (urllib_error.URLError, urllib_error.HTTPError, json.JSONDecodeError, TimeoutError):
        return {"success": False}


def validate_turnstile_token(token: str, remote_ip: str | None = None, request=None) -> bool:
    if not token:
        return False
    if not is_turnstile_enabled(request):
        return True
    return bool(_post_turnstile_siteverify(token, remote_ip=remote_ip).get("success"))
