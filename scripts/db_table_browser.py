"""CAUFA themed Tkinter DB table browser + truncate tool.

Run from project root:
    venv\\Scripts\\python.exe scripts\\db_table_browser.py
    python scripts/db_table_browser.py --help

- Lists ALL tables via Django's DB connection (respects .env / settings.py,
  so it works against the live MySQL DB, not the stale db.sqlite3).
- One checkbox per table + live row counts + search filter.
- Truncate selected with FK-safe handling + double confirmation.
- Protected tables (migrations / permissions) are flagged and need typing YES.
- officer_user (officer accounts) is NEVER truncated — checkbox disabled,
  hard-blocked in truncate_tables() + CLI.

Automated presets (GUI buttons + headless CLI):
    --wipe-all-keep-officers  truncate everything except officer_user
    --wipe-transactional      sessions/devices/members/transacts/aid/funds
    --wipe-sessions           sessions/devices/login traces only
    Combine with --include-protected to also wipe infra tables,
    and --yes to skip the interactive YES prompt.
"""
from __future__ import annotations

import argparse
import os
import queue
import re
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# ---------------------------------------------------------------- Django boot
ENGINE = "unknown"
DB_NAME = "unknown"


def boot_django():
    global ENGINE, DB_NAME
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "caufa_portal.settings")
    import django

    django.setup()
    from django.db import connection

    ENGINE = connection.vendor  # mysql / sqlite
    DB_NAME = connection.settings_dict.get("NAME", "?")
    return connection


# Tables you almost never want to wipe. They stay checkable but trigger an
# extra typed confirmation and a red flag in the UI.
PROTECTED_TABLES = {
    "django_migrations",
    "django_content_type",
    "auth_permission",
    "sqlite_sequence",
}

# NEVER truncate these — hard-blocked in GUI + CLI. Officer logins live here.
NEVER_TRUNCATE_TABLES = {
    "officer_user",
}

# --- Automated wipe presets (all exclude NEVER_TRUNCATE_TABLES) -------------
# Quick sessions/devices-only clear (safe, no member/transaction loss).
SESSION_WIPE_TABLES = [
    "access_session",
    "login_attempt_log",
    "django_session",
    "push_subscription",
    "authtoken_token",
]

# Transactional wipe: sessions + devices + members + transacts, but keeps
# officer_user (+ infra/protected tables unless explicitly included).
TRANSACTIONAL_WIPE_TABLES = [
    # sessions / devices / auth traces
    "access_session",
    "login_attempt_log",
    "django_session",
    "push_subscription",
    "authtoken_token",
    # members + related
    "member",
    "claimant",
    "attendance",
    "member_registration_request",
    "salary_deduction_exemption",
    # dues / fees / ledger / transacts
    "monthly_dues",
    "membership_fee",
    "member_ledger",
    "fund_transaction",
    "transaction_verification",
    "transaction_archive",
    "payroll_batch",
    "payroll_deduction",
    # aid workflows
    "medical_aid",
    "death_aid",
    "aid_tracking_post",
    "contribution",
    "aid_set_asides",
    # monthly assessments
    "monthly_assessments",
    "monthly_assessment_documents",
    "assessment_items",
    "member_assessments",
    "member_catchup_dues",
    "member_assessment_allocations",
    # comms / mail generated from transacts
    "notification",
    "outgoing_email",
    "global_audit_trail",
    "sensitive_read_log",
    "supporting_proof",
    "financial_document_archive",
    "revision_log",
    "workflow_logs",
]


def resolve_preset_tables(all_tables: list[str], preset: str,
                           include_protected: bool = False) -> list[str]:
    """Return the table list for an automated preset.

    preset: 'all' | 'transactional' | 'sessions'
    Always excludes NEVER_TRUNCATE_TABLES. Excludes PROTECTED_TABLES
    unless include_protected=True.
    """
    available = set(all_tables)
    if preset == "all":
        wanted = [t for t in all_tables]
    elif preset == "transactional":
        wanted = [t for t in TRANSACTIONAL_WIPE_TABLES if t in available]
        # also pick up any stray session tables present in DB
        for t in SESSION_WIPE_TABLES:
            if t in available and t not in wanted:
                wanted.append(t)
    elif preset == "sessions":
        wanted = [t for t in SESSION_WIPE_TABLES if t in available]
    else:
        raise ValueError(f"unknown preset {preset!r}")
    return sorted(
        t for t in wanted
        if t not in NEVER_TRUNCATE_TABLES
        and (include_protected or t not in PROTECTED_TABLES)
    )


def assert_not_protected_never(tables: list[str]):
    bad = [t for t in tables if t in NEVER_TRUNCATE_TABLES]
    if bad:
        raise SystemExit(
            f"Refusing to truncate NEVER_TRUNCATE tables: {', '.join(bad)} "
            "(officer user accounts are always preserved)."
        )

# ---------------------------------------------------------------- DB helpers

def list_tables(connection):
    with connection.cursor() as cur:
        tables = sorted(connection.introspection.table_names(cur))
    return tables


def count_rows(connection, table: str) -> int | None:
    try:
        with connection.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM `{table}`")
            row = cur.fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return None


def truncate_tables(connection, tables: list[str], log) -> dict[str, str]:
    """FK-safe truncate. Returns {table: 'ok' | error message}.

    NEVER_TRUNCATE_TABLES (officer_user) are silently skipped here as a
    last line of defence — callers should already have filtered them.
    """
    tables = [t for t in tables if t not in NEVER_TRUNCATE_TABLES]
    results: dict[str, str] = {}
    vendor = connection.vendor
    with connection.cursor() as cur:
        # If we keep officer_user but wipe department, null the officers'
        # department FK first so we don't leave dangling references.
        if "department" in tables:
            try:
                cur.execute("UPDATE `officer_user` SET `department_id_FK` = NULL;")
            except Exception as e_dep:
                log(f"[warn] could not null officer department FKs: {e_dep}")
        try:
            if vendor == "mysql":
                cur.execute("SET FOREIGN_KEY_CHECKS=0;")
            elif vendor == "sqlite":
                cur.execute("PRAGMA foreign_keys=OFF;")

            for tbl in tables:
                try:
                    if vendor == "mysql":
                        # TRUNCATE resets AUTO_INCREMENT; fallback to DELETE if
                        # the engine (e.g. a VIEW) rejects it.
                        try:
                            cur.execute(f"TRUNCATE TABLE `{tbl}`;")
                        except Exception as e1:
                            log(f"[fallback] TRUNCATE failed on {tbl}: {e1}; using DELETE")
                            cur.execute(f"DELETE FROM `{tbl}`;")
                    elif vendor == "sqlite":
                        cur.execute(f'DELETE FROM "{tbl}";')
                        try:
                            cur.execute("DELETE FROM sqlite_sequence WHERE name=%s;", [tbl])
                        except Exception:
                            pass
                    else:
                        cur.execute(f'DELETE FROM "{tbl}";')
                    results[tbl] = "ok"
                except Exception as exc:  # per-table error, keep going
                    results[tbl] = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                if vendor == "mysql":
                    cur.execute("SET FOREIGN_KEY_CHECKS=1;")
                elif vendor == "sqlite":
                    cur.execute("PRAGMA foreign_keys=ON;")
            except Exception:
                pass
    return results


# ---------------------------------------------------------------- Theme
CAUFA_GREEN = "#1b5e20"
CAUFA_GREEN_2 = "#2e7d32"
CAUFA_MINT = "#e8f5e9"
CAUFA_BG = "#f4f7f5"
CAUFA_INK = "#1e3421"
CAUFA_LINE = "#d9e5da"
CAUFA_RED = "#c62828"


def apply_theme(root: tk.Tk):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    root.configure(bg=CAUFA_BG)
    style.configure(".", background=CAUFA_BG, foreground=CAUFA_INK,
                    font=("Segoe UI", 10))
    style.configure("Header.TLabel", background=CAUFA_GREEN, foreground="white",
                    font=("Segoe UI", 13, "bold"))
    style.configure("SubHeader.TLabel", background=CAUFA_GREEN, foreground="#c8e6c9",
                    font=("Segoe UI", 9))
    style.configure("Card.TFrame", background="white", relief="flat")
    style.configure("TButton", padding=(12, 7), font=("Segoe UI", 10))
    style.configure("Green.TButton", background=CAUFA_GREEN, foreground="white",
                    borderwidth=0, focusthickness=3, focuscolor=CAUFA_GREEN_2)
    style.map("Green.TButton", background=[("active", CAUFA_GREEN_2), ("disabled", "#9db79a")])
    style.configure("Danger.TButton", background=CAUFA_RED, foreground="white", borderwidth=0)
    style.map("Danger.TButton", background=[("active", "#a92323"), ("disabled", "#d99a9a")])
    style.configure("Ghost.TButton", background="#eef3ee", foreground=CAUFA_GREEN)
    style.configure("Row.TCheckbutton", background="white", font=("Segoe UI", 10))
    style.configure("Count.TLabel", background="#eef3ee", foreground="#37503a",
                    font=("Consolas", 9), padding=(6, 2))
    style.configure("Prot.TLabel", background="#fdecea", foreground=CAUFA_RED,
                    font=("Segoe UI", 8, "bold"), padding=(5, 2))
    style.configure("Keep.TLabel", background="#e8f5e9", foreground=CAUFA_GREEN,
                    font=("Segoe UI", 8, "bold"), padding=(5, 2))


# ---------------------------------------------------------------- App
class DBBrowser(tk.Tk):
    def __init__(self, connection):
        super().__init__()
        self.conn = connection
        self.title(f"CAUFA DB Browser — {DB_NAME} ({ENGINE})")
        self.geometry("1020x700")
        self.minsize(820, 560)
        apply_theme(self)

        self.tables: list[str] = []
        self.counts: dict[str, int | None] = {}
        self.vars: dict[str, tk.BooleanVar] = {}
        self.row_widgets: dict[str, ttk.Frame] = {}
        self._filter = tk.StringVar()
        self._ui_queue: queue.Queue = queue.Queue()
        self._busy = False

        self._build()
        self.after(100, self._pump_queue)
        self.refresh_async()

    # -- layout -----------------------------------------------------
    def _build(self):
        # header banner
        banner = ttk.Frame(self, style="Card.TFrame")
        banner.pack(fill="x")
        inner = tk.Frame(banner, bg=CAUFA_GREEN, padx=16, pady=12)
        inner.pack(fill="x")
        tk.Label(inner, text="CAUFA  •  Database Table Browser",
                 bg=CAUFA_GREEN, fg="white",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        self.db_label = tk.Label(inner, text=f"{DB_NAME}  •  engine={ENGINE}",
                                 bg=CAUFA_GREEN, fg="#c8e6c9", font=("Segoe UI", 9))
        self.db_label.pack(anchor="w")
        banner.configure(style="Card.TFrame")

        # toolbar
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=12, pady=(10, 6))
        ttk.Label(bar, text="Search:").pack(side="left", padx=(0, 6))
        search = ttk.Entry(bar, textvariable=self._filter, width=32)
        search.pack(side="left")
        search.bind("<KeyRelease>", lambda _e: self._apply_filter())
        ttk.Button(bar, text="Refresh", command=self.refresh_async).pack(side="left", padx=8)
        ttk.Button(bar, text="Select all", command=lambda: self._set_all(True)).pack(side="left")
        ttk.Button(bar, text="Clear", command=lambda: self._set_all(False)).pack(side="left", padx=6)
        self.stats_label = ttk.Label(bar, text="—")
        self.stats_label.pack(side="right")

        # preset row: automated wipes (officer_user is always excluded)
        presets = ttk.Frame(self)
        presets.pack(fill="x", padx=12, pady=(0, 2))
        ttk.Label(presets, text="Presets (keep officers):",
                  font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
        ttk.Button(presets, text="Wipe all (keep officers)",
                   style="Ghost.TButton",
                   command=lambda: self._select_preset("all")).pack(side="left")
        ttk.Button(presets, text="Transactional wipe",
                   style="Ghost.TButton",
                   command=lambda: self._select_preset("transactional")).pack(side="left", padx=6)
        ttk.Button(presets, text="Sessions/devices only",
                   style="Ghost.TButton",
                   command=lambda: self._select_preset("sessions")).pack(side="left")

        # checkbox list (scrollable)
        list_card = ttk.Frame(self, style="Card.TFrame", padding=6)
        list_card.pack(fill="both", expand=True, padx=12, pady=6)
        self.canvas = tk.Canvas(list_card, bg="white", highlightthickness=1,
                                highlightbackground=CAUFA_LINE)
        vsb = ttk.Scrollbar(list_card, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.rows_frame = tk.Frame(self.canvas, bg="white")
        self._win = self.canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.rows_frame.bind("<Configure>",
                             lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self._win, width=e.width))
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))

        # bottom: actions + log
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=12, pady=(0, 6))
        self.truncate_btn = ttk.Button(bottom, text="Truncate selected",
                                       style="Danger.TButton", command=self._on_truncate)
        self.truncate_btn.pack(side="left")
        ttk.Label(bottom, text="TRUNCATE wipes rows + resets AUTO_INCREMENT. FK checks off during run.",
                  font=("Segoe UI", 8)).pack(side="left", padx=10)
        self.sel_label = ttk.Label(bottom, text="0 selected")
        self.sel_label.pack(side="right")

        log_card = ttk.Frame(self, style="Card.TFrame", padding=6)
        log_card.pack(fill="both", expand=False, padx=12, pady=(0, 12))
        self.log = tk.Text(log_card, height=7, wrap="word", bg="#0f1f12", fg="#c9e7cc",
                           insertbackground="white", font=("Consolas", 9), relief="flat")
        self.log.pack(fill="both", expand=True)
        self._log(f"Connected: {DB_NAME} (engine={ENGINE}). Loading tables…")

    # -- data -------------------------------------------------------
    def _log(self, msg: str):
        self.log.insert("end", msg + "\n")
        self.log.see("end")

    def refresh_async(self):
        if self._busy:
            return
        self._busy = True
        self._log("Refreshing table list + row counts…")
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        try:
            tables = list_tables(self.conn)
            counts = {t: count_rows(self.conn, t) for t in tables}
            self._ui_queue.put(("loaded", tables, counts))
        except Exception as exc:
            self._ui_queue.put(("error", f"{type(exc).__name__}: {exc}"))

    def _pump_queue(self):
        try:
            while True:
                msg = self._ui_queue.get_nowait()
                kind = msg[0]
                if kind == "loaded":
                    _, tables, counts = msg
                    self.tables, self.counts = tables, counts
                    self._rebuild_rows()
                    total = sum(c for c in counts.values() if isinstance(c, int))
                    self.stats_label.config(text=f"{len(tables)} tables • {total:,} rows")
                    self._log(f"Loaded {len(tables)} tables, {total:,} total rows.")
                    self._busy = False
                elif kind == "error":
                    self._log("[ERROR] " + msg[1])
                    messagebox.showerror("DB error", msg[1])
                    self._busy = False
                elif kind == "truncated":
                    _, results = msg
                    ok = sum(1 for v in results.values() if v == "ok")
                    for tbl, res in results.items():
                        self._log(f"{'OK  ' if res == 'ok' else 'FAIL'}  {tbl}"
                                  + ("" if res == "ok" else f" — {res}"))
                    self._log(f"Done: {ok}/{len(results)} truncated.")
                    self._busy = False
                    self.truncate_btn.config(state="normal")
                    self.refresh_async()
        except queue.Empty:
            pass
        self.after(120, self._pump_queue)

    # -- rows -------------------------------------------------------
    def _select_preset(self, preset: str):
        """Tick the checkboxes for an automated preset.

        'all' = every table except officer_user (+ protected infra).
        'transactional' = sessions/devices/members/transacts/aid/fund flow.
        'sessions' = sessions/devices/login traces only.
        """
        if not self.tables:
            messagebox.showinfo("Not ready", "Table list hasn't loaded yet.")
            return
        wanted = set(resolve_preset_tables(self.tables, preset))
        for tbl, var in self.vars.items():
            if tbl in NEVER_TRUNCATE_TABLES:
                var.set(False)
            elif tbl in wanted and self.row_widgets[tbl].winfo_ismapped():
                var.set(True)
            else:
                var.set(False)
        missing = [t for t in
                   (TRANSACTIONAL_WIPE_TABLES if preset == "transactional"
                    else SESSION_WIPE_TABLES if preset == "sessions" else [])
                   if t not in set(self.tables)]
        self._log(f"Preset '{preset}': selected {len(wanted)} table(s), "
                  f"officer_user always excluded."
                  + (f" Not in DB: {', '.join(missing)}" if missing and preset != "all" else ""))
        self._update_sel_label()

    def _rebuild_rows(self):
        for w in self.rows_frame.winfo_children():
            w.destroy()
        self.vars.clear()
        self.row_widgets.clear()
        for tbl in self.tables:
            var = tk.BooleanVar(value=False)
            var.trace_add("write", lambda *_a: self._update_sel_label())
            self.vars[tbl] = var
            row = tk.Frame(self.rows_frame, bg="white", padx=8, pady=4,
                           highlightbackground=CAUFA_LINE, highlightthickness=0)
            row.pack(fill="x")
            cb = ttk.Checkbutton(row, text=f"  {tbl}", variable=var, style="Row.TCheckbutton")
            cb.pack(side="left", fill="x", expand=True)
            cnt = self.counts.get(tbl)
            badge = ttk.Label(row, text="—" if cnt is None else f"{cnt:,} rows",
                              style="Count.TLabel")
            badge.pack(side="right", padx=(6, 0))
            if tbl in NEVER_TRUNCATE_TABLES:
                cb.config(state="disabled")
                ttk.Label(row, text="KEEP — officer accounts", style="Keep.TLabel").pack(side="right")
            elif tbl in PROTECTED_TABLES:
                ttk.Label(row, text="PROTECTED", style="Prot.TLabel").pack(side="right")
            self.row_widgets[tbl] = row
        self._apply_filter()
        self._update_sel_label()

    def _apply_filter(self):
        q = self._filter.get().strip().lower()
        for tbl, row in self.row_widgets.items():
            row.pack_forget() if (q and q not in tbl.lower()) else row.pack(fill="x")

    def _set_all(self, val: bool):
        for tbl, var in self.vars.items():
            if tbl in NEVER_TRUNCATE_TABLES:
                var.set(False)
                continue
            if self.row_widgets[tbl].winfo_ismapped():
                var.set(val)

    def _selected(self) -> list[str]:
        return sorted(t for t, v in self.vars.items()
                      if v.get() and t not in NEVER_TRUNCATE_TABLES)

    def _update_sel_label(self):
        n = len(self._selected())
        self.sel_label.config(text=f"{n} selected")

    # -- truncate ---------------------------------------------------
    def _on_truncate(self):
        sel = self._selected()
        if not sel:
            messagebox.showinfo("Nothing selected", "Tick at least one table first.")
            return
        # Hard guard: officer accounts can never be wiped from here.
        if any(t in NEVER_TRUNCATE_TABLES for t in sel):
            messagebox.showerror("Blocked", "officer_user is preserved and cannot be truncated.")
            return
        prot = [t for t in sel if t in PROTECTED_TABLES]
        preview = "\n".join(f"  • {t} ({self.counts.get(t, '?')} rows)" for t in sel[:20])
        if len(sel) > 20:
            preview += f"\n  … +{len(sel) - 20} more"
        if not messagebox.askyesno(
            "Confirm TRUNCATE",
            f"Permanently wipe {len(sel)} table(s) on '{DB_NAME}'?\n\n{preview}\n\n"
            "This cannot be undone. FK checks are disabled during the run.",
            icon="warning",
        ):
            return
        if prot and not self._typed_confirm(prot):
            self._log("Truncate cancelled (protected-table confirmation failed).")
            return
        self._busy = True
        self.truncate_btn.config(state="disabled")
        self._log(f"Truncating {len(sel)} table(s)…")
        threading.Thread(target=self._truncate_worker, args=(sel,), daemon=True).start()

    def _typed_confirm(self, prot: list[str]) -> bool:
        dlg = tk.Toplevel(self)
        dlg.title("Protected tables!")
        dlg.transient(self)
        dlg.grab_set()
        tk.Label(dlg, text="These tables are protected:\n" + "\n".join(f"  • {t}" for t in prot) +
                 '\n\nType YES (all caps) to include them, or Cancel.',
                 justify="left", font=("Segoe UI", 10)).pack(padx=18, pady=14)
        entry = ttk.Entry(dlg, width=20)
        entry.pack(padx=18, pady=(0, 12))
        entry.focus_set()
        result = {"ok": False}

        def _ok():
            result["ok"] = entry.get().strip() == "YES"
            dlg.destroy()

        ttk.Button(dlg, text="Confirm", command=_ok).pack(side="left", padx=18, pady=10)
        ttk.Button(dlg, text="Cancel", command=dlg.destroy).pack(side="right", padx=18, pady=10)
        self.wait_window(dlg)
        return result["ok"]

    def _truncate_worker(self, tables: list[str]):
        try:
            from django.db import connection, transaction
            with transaction.atomic():
                results = truncate_tables(connection, tables, self._log)
        except Exception as exc:
            results = {t: f"{type(exc).__name__}: {exc}" for t in tables}
        self._ui_queue.put(("truncated", results))


def parse_args():
    p = argparse.ArgumentParser(description="CAUFA themed DB table browser + truncate tool")
    p.add_argument("--list", action="store_true", help="print tables + counts to console, no GUI")
    p.add_argument("--filter", default="", help="only include tables matching this substring (with --list)")
    p.add_argument("--wipe-all-keep-officers", action="store_true",
                   help="truncate EVERYTHING except officer_user (+ protected infra unless --include-protected)")
    p.add_argument("--wipe-transactional", action="store_true",
                   help="truncate sessions/devices/members/transacts/aid/fund flow, keep officer_user")
    p.add_argument("--wipe-sessions", action="store_true",
                   help="truncate sessions/devices/login traces only, keep officer_user")
    p.add_argument("--include-protected", action="store_true",
                   help="with a --wipe-* preset, also include PROTECTED infra tables")
    p.add_argument("--yes", action="store_true",
                   help="skip interactive confirmation (required for --wipe-* without a TTY)")
    return p.parse_args()


def run_cli_wipe(conn, tables: list[str], assume_yes: bool):
    assert_not_protected_never(tables)
    print(f"About to TRUNCATE {len(tables)} table(s) on '{DB_NAME}' (officer_user preserved):")
    for t in tables:
        print(f"  • {t} ({count_rows(conn, t)} rows)")
    if not assume_yes:
        ans = input("Type YES to proceed: ").strip()
        if ans != "YES":
            print("Cancelled.")
            sys.exit(1)
    logs = []
    results = truncate_tables(conn, tables, logs.append)
    for line in logs:
        print(line)
    ok = sum(1 for v in results.values() if v == "ok")
    for tbl, res in results.items():
        print(f"{'OK  ' if res == 'ok' else 'FAIL'}  {tbl}" + ("" if res == "ok" else f" — {res}"))
    print(f"Done: {ok}/{len(results)} truncated. officer_user untouched.")


def main():
    args = parse_args()
    try:
        conn = boot_django()
    except Exception as exc:
        print(f"Could not boot Django / connect to DB: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Tip: check .env DB_HOST/DB_NAME/DB_USER/DB_PASSWORD and that MySQL is running.",
              file=sys.stderr)
        sys.exit(1)

    wipe_flags = [args.wipe_all_keep_officers, args.wipe_transactional, args.wipe_sessions]
    if sum(bool(f) for f in wipe_flags) > 1:
        print("Pick only one of --wipe-all-keep-officers / --wipe-transactional / --wipe-sessions",
              file=sys.stderr)
        sys.exit(2)
    if any(wipe_flags):
        all_tables = list_tables(conn)
        preset = ("all" if args.wipe_all_keep_officers
                  else "transactional" if args.wipe_transactional else "sessions")
        tables = resolve_preset_tables(all_tables, preset,
                                       include_protected=args.include_protected)
        if not tables:
            print("Nothing to truncate for that preset.", file=sys.stderr)
            sys.exit(0)
        run_cli_wipe(conn, tables, assume_yes=args.yes)
        return

    if args.list:
        tables = list_tables(conn)
        if args.filter:
            tables = [t for t in tables if args.filter.lower() in t.lower()]
        for t in tables:
            if t in NEVER_TRUNCATE_TABLES:
                flag = " [KEEP — officer accounts, never truncated]"
            elif t in PROTECTED_TABLES:
                flag = " [PROTECTED]"
            else:
                flag = ""
            print(f"{t}{flag}: {count_rows(conn, t)} rows")
        return

    if not re.match(r"^[a-zA-Z0-9_.\-]+$", DB_NAME or ""):
        print(f"Refusing to open GUI against odd DB name {DB_NAME!r}", file=sys.stderr)
        sys.exit(1)
    app = DBBrowser(conn)
    app.mainloop()


if __name__ == "__main__":
    main()
