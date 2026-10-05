import sys
from pathlib import Path

import uvicorn

BASE = Path(__file__).parent
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
do_reload = len(sys.argv) > 2 and sys.argv[2] == "--reload"

if __name__ == "__main__":
    kwargs = {
        "host": "127.0.0.1",
        "port": port,
        "lifespan": "off",
        "timeout_graceful_shutdown": 5,
        "reload_dirs": [
            str(BASE / "caufa_portal"),
            str(BASE / "core_system"),
        ] if do_reload else None,
    }
    if do_reload:
        print(f"[reload] Watching *.py only (templates/static do NOT restart server)")
        kwargs["reload"] = True
        kwargs["reload_delay"] = 0.5
        kwargs["reload_includes"] = [
            "*.py",
        ]
        kwargs["reload_excludes"] = [
            "*.pyc", "*.pyo", "__pycache__", ".git", ".venv",
            "venv", "node_modules", ".kilo", ".opencode",
            ".aider*", "migrations", "*.log",
            "*.sqlite3", "*.db", "*.sqlite3-journal",
            "media", "static", "templates",
            "BACKUP_RUNSERVER_FIX_*",
        ]
    else:
        print(f"[reload] No file watching (use -NoReload to enable)")
    print(f"[reload] Use Ctrl+C to stop")
    uvicorn.run("caufa_portal.asgi:application", **kwargs)
