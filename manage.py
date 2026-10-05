#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path

import uvicorn

def _parse_runserver_args(argv):
    """Parse `manage.py runserver [addrport] [flags]` the Django way.

    Returns (host, port, reload_enabled). Unknown Django-only flags
    (--skip-checks, --nothreading, --insecure, ...) are ignored because
    uvicorn is serving, not Django's runserver.
    """
    host = "127.0.0.1"
    port = "8000"
    # Dev default: auto-reload ON. Pass --noreload to turn it off
    # (e.g. while testing forms so the page never refreshes under you).
    reload_enabled = True

    for arg in argv[2:]:
        low = arg.lower()
        if low in ("--noreload", "--no-reload"):
            reload_enabled = False
        elif low.startswith("--noreload=") or low.startswith("--no-reload="):
            val = low.split("=", 1)[1].strip()
            # --noreload=0 / =false / =no  => reload stays ON
            # --noreload / =1 / =true / =yes => reload OFF
            reload_enabled = val in ("0", "false", "no", "off")
        elif low in ("--reload", "--reload=1", "--reload=true"):
            reload_enabled = True
        elif low.startswith("--"):
            continue  # Django-only flag, ignore for uvicorn
        elif ":" in arg:
            host, port = arg.split(":", 1)
        elif arg and arg[0].isdigit():
            port = arg
    return host, port, reload_enabled


def _install_dev_noise_filters() -> None:
    """Silence two known-harmless dev-only noise sources (runserver path only).

    1. ``CancelledError`` tracebacks from ``/__reload__/events/``: the
       django-browser-reload SSE stream is an *infinite* generator, so it can
       never drain within any graceful-shutdown window. Uvicorn therefore
       always cancels those 2 tasks on restart and Django's ASGI handler logs
       ``Exception in ASGI application`` + ``Cancel N running task(s)``.
       This happens strictly in the shutdown path *after* in-flight requests
       (e.g. your ``POST /login/ 302``) already completed — never a request
       failure. The filter matches only that exact shutdown signature.
    2. The one-per-process ``StreamingHttpResponse must consume synchronous
       iterators`` warning from Django's dev static-file serving
       (``staticfiles_urlpatterns`` -> FileResponse) under ASGI. Benign in
       local dev; production serves static via nginx/whitenoise, not this.
    """
    import asyncio
    import logging
    import warnings

    warnings.filterwarnings(
        "ignore",
        message=".*StreamingHttpResponse must consume synchronous iterators.*",
    )

    class _ReloadShutdownNoiseFilter(logging.Filter):
        def filter(self, record):
            try:
                msg = record.getMessage()
            except Exception:
                return True
            if "timeout graceful shutdown exceeded" in msg:
                return False
            exc = record.exc_info[1] if record.exc_info else None
            if isinstance(exc, asyncio.CancelledError) and "Exception in ASGI application" in msg:
                return False
            return True

    for _name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(_name).addFilter(_ReloadShutdownNoiseFilter())


def _run_uvicorn_devserver(host: str, port: int, reload_enabled: bool) -> None:
    base = Path(__file__).parent
    _install_dev_noise_filters()
    if reload_enabled:
        # NOTE: watch *.py ONLY. Template/static edits (*.html/*.js/*.css)
        # are picked up live by Django's template/static loaders and do NOT
        # need a server restart. Watching them caused the "wild" behaviour:
        # every frontend save killed uvicorn, dropped the
        # /__reload__/events/ SSE streams, and django-browser-reload then
        # force-refreshed the page (losing form state mid-test).
        # For frontend tweaks just save + F5; the server stays up.
        print(
            "[runserver] uvicorn reload ON  (Python *.py only). "
            "Use `runserver --noreload` for zero restarts while testing forms.",
            flush=True,
        )
        uvicorn.run(
            "caufa_portal.asgi:application",
            host=host,
            port=int(port),
            reload=True,
            # Debounce atomic-save editors (VS Code etc. emit 2 write
            # events per save -> previously 2 back-to-back restarts).
            reload_delay=0.5,
            # Grace period so the long-lived /__reload__/events/ SSE
            # streams close cleanly. The old value 0 cancelled them
            # instantly -> "Cancel 2 running task(s)" + CancelledError
            # tracebacks on EVERY reload.
            timeout_graceful_shutdown=5,
            lifespan="off",  # silences "lifespan protocol appears unsupported"
            reload_dirs=[
                str(base / "core_system"),
                str(base / "caufa_portal"),
            ],
            reload_includes=[
                "*.py",
            ],
            reload_excludes=[
                "*.pyc", "*.pyo", "__pycache__", ".git", ".venv",
                "venv", "node_modules", ".kilo", ".opencode",
                ".aider*", "migrations", "*.log",
                "*.sqlite3", "*.db", "*.sqlite3-journal",
                "media", "static", "templates",
                "BACKUP_RUNSERVER_FIX_*",
            ],
        )
    else:
        print(
            "[runserver] uvicorn reload OFF (--noreload). "
            "Server will NOT restart and the page will NOT refresh on save.",
            flush=True,
        )
        uvicorn.run(
            "caufa_portal.asgi:application",
            host=host,
            port=int(port),
            reload=False,
            timeout_graceful_shutdown=5,
            lifespan="off",
        )

def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "caufa_portal.settings")

    if len(sys.argv) > 1 and sys.argv[1] == "runserver":
        if any(a in sys.argv for a in ("--help", "-h")):
            print(
                "Usage: python manage.py runserver [addrport] [--noreload]\n"
                "  addrport        e.g. 8000 or 127.0.0.1:8000 (default 127.0.0.1:8000)\n"
                "  --noreload      disable auto-restart (stable while testing forms;\n"
                "                  the page will NOT refresh on save)\n"
                "  (default)       auto-restart on *.py changes only; .html/.js/.css\n"
                "                  edits do NOT restart the server (just F5)."
            )
            return
        host, port, reload_enabled = _parse_runserver_args(sys.argv)
        _run_uvicorn_devserver(host, port, reload_enabled)
        return

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
