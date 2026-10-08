"""Dev-only live-reload watcher for ``START.ps1``.

``manage.py runserver`` is served by uvicorn (see ``manage.py``), whose
reloader watches ``*.py`` only — template/static edits (``*.html``,
``*.js``, ``*.css``) never restart the server, so nothing tells the
browser to refresh. ``django-browser-reload`` is installed and its
middleware auto-injects the listener script into every HTML page, but
its change signals hook into *Django's* reloader, which isn't running
here — so template/static saves go unnoticed.

This module closes that gap with a tiny daemon thread (``watchfiles``)
that watches the template + static roots and pokes
``django_browser_reload.views.trigger_reload_soon()`` on change. The
result: save an ``.html``/``.js``/``.css`` file and the open browser tab
refreshes by itself — no server restart, no manual F5.

Started only when ALL of these hold (see ``apps.py``)::

    * ``settings.DEBUG`` is True,
    * env ``CAUFA_DEV_WATCH=1`` (set by ``START.ps1`` only),
    * the command is ``runserver``.

``*.py`` edits still restart the server via uvicorn (unavoidable for
Python); everything else refreshes the browser in place with the
server process untouched.
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

_WATCH_EXTENSIONS = (".html", ".htm", ".js", ".css")

_started = False
_started_lock = threading.Lock()


def _watch_roots() -> list:
    """Template + static directories worth watching (existing ones only)."""
    from pathlib import Path

    from django.conf import settings

    roots: set[Path] = set()

    for backend in settings.TEMPLATES:
        for d in backend.get("DIRS", []) or []:
            p = Path(d)
            if p.is_dir():
                roots.add(p.resolve())

    for d in getattr(settings, "STATICFILES_DIRS", []) or []:
        p = Path(d[1] if isinstance(d, (list, tuple)) else d)
        if p.is_dir():
            roots.add(p.resolve())

    # App-level templates/ + static/ (e.g. core_system/templates).
    from django.apps import apps as django_apps

    base = Path(settings.BASE_DIR)
    for app_config in django_apps.get_app_configs():
        for sub in ("templates", "static"):
            p = Path(app_config.path) / sub
            if p.is_dir():
                roots.add(p.resolve())

    # Fallback: whole project templates/ + static/ dirs.
    for sub in ("templates", "static"):
        p = base / sub
        if p.is_dir():
            roots.add(p.resolve())

    return sorted(str(p) for p in roots)


def _watch_loop(roots: list) -> None:
    try:
        from watchfiles import watch

        from django_browser_reload.views import trigger_reload_soon
    except Exception:
        logger.exception("dev watcher: missing dependency, live-reload disabled")
        return

    logger.warning("dev watcher: live browser refresh ON for %s", ", ".join(roots))
    try:
        for changes in watch(*roots):
            try:
                if any(
                    str(path).lower().endswith(_WATCH_EXTENSIONS)
                    for _, path in changes
                ):
                    trigger_reload_soon()
            except Exception:
                logger.exception("dev watcher: error handling change batch")
    except Exception:
        logger.exception("dev watcher stopped")


def maybe_start_dev_watcher() -> bool:
    """Start the watcher thread once. Returns True when started."""
    global _started
    with _started_lock:
        if _started:
            return False
        _started = True

    try:
        from django.conf import settings

        if not getattr(settings, "DEBUG", False):
            return False
        if os.environ.get("CAUFA_DEV_WATCH") != "1":
            return False

        roots = _watch_roots()
        if not roots:
            logger.warning("dev watcher: no template/static roots found")
            return False

        thread = threading.Thread(
            target=_watch_loop,
            args=(roots,),
            name="caufa-dev-reload-watcher",
            daemon=True,
        )
        thread.start()
        return True
    except Exception:
        logger.exception("dev watcher failed to start")
        return False
