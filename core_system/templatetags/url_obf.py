"""Template tags for URL encryption & obfuscation.

Usage:
    {% load url_obf %}
    <a href="{% obf_url '/auditor/reports/?year=2026' %}">…</a>
    <a href="{% obf_envelope '/' 'session_expired=1' %}">…</a>

``obf_url`` appends the tamper-proof ``_s`` signature using the viewer's
per-session subkey (falls back to the plain URL when obfuscation is off
or the session has no key). ``obf_envelope`` hides every key/value in an
opaque ``?x=`` blob for address-bar links.
"""
from __future__ import annotations

from django import template
from urllib.parse import parse_qsl

from core_system import url_obfuscation as obf

register = template.Library()


@register.simple_tag(takes_context=True)
def obf_url(context, url: str) -> str:
    try:
        if not obf.is_enabled():
            return url
        request = context.get("request")
        key = obf.get_session_key(request) if request is not None else None
        if not key:
            return url
        if "?" not in str(url):
            return url
        return obf.sign_url(str(url), key)
    except Exception:
        return url


@register.simple_tag
def obf_envelope(path: str, query: str = "") -> str:
    try:
        if not obf.is_enabled():
            return path + ("?" + query if query else "")
        params = dict(parse_qsl(str(query), keep_blank_values=True))
        return obf.opaque_url(str(path), params)
    except Exception:
        return path
