/* Member Ledger (shared: Treasurer / Auditor / President dashboards)
 * --------------------------------------------------------------------------
 * Month-by-month ledger for one ISUCauFA member so officers can see, for
 * every recorded month, what was deducted from the member,
 * ("change"), and their remaining balance — together with the member's full
 * profile. Rendered into #mlh-root with mlh-* classes scoped under it so
 * host-page styles cannot interfere.
 *
 * APIs:
 *   GET /api/officers/deductions/member-ledger/               (picker list)
 *   GET /api/officers/deductions/member-ledger/?member_id=<id> (one member)
 */
(function () {
  "use strict";

  /* ================= injected styles (host-page-proof) ================== */
  const CSS = `
  #mlh-root { display:block; font-family:inherit; color:#1f2937; }
  #mlh-root *, #mlh-root *::before, #mlh-root *::after { box-sizing:border-box; }
  #mlh-root .mlh-card {
    background:#fff; border:1px solid #e6ebe7; border-radius:14px;
    box-shadow:0 1px 2px rgba(16,24,40,0.04);
  }
  #mlh-root .mlh-toolbar {
    display:flex; align-items:flex-start; justify-content:space-between;
    gap:14px; flex-wrap:wrap; padding:16px 20px; margin-bottom:14px;
  }
  #mlh-root .mlh-title {
    display:flex; align-items:center; gap:10px; margin:0;
    font-size:1.02rem; font-weight:800; color:#111827;
  }
  #mlh-root .mlh-sub { margin:3px 0 0; font-size:0.78rem; color:#6b7280; }
  #mlh-root .mlh-select {
    border:1px solid #d6ddd7; border-radius:9px; background:#fff;
    padding:8px 11px; font-size:0.82rem; color:#1f2937; font-family:inherit; cursor:pointer; max-width:420px; width:100%;
  }
  #mlh-root .mlh-select:focus { outline:none; border-color:#2e7d32; box-shadow:0 0 0 3px rgba(46,125,50,0.12); }

  #mlh-root .mlh-profile { padding:18px 20px; margin-bottom:14px; }
  #mlh-root .mlh-profile-head { display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin-bottom:14px; }
  #mlh-root .mlh-avatar {
    width:52px; height:52px; border-radius:50%; background:#e8f5e9; color:#1b5e20;
    display:inline-flex; align-items:center; justify-content:center; font-weight:800; font-size:1.05rem; flex:0 0 52px;
  }
  #mlh-root .mlh-profile-name { font-size:1.05rem; font-weight:800; color:#101828; }
  #mlh-root .mlh-profile-sub { font-size:0.78rem; color:#6b7280; margin-top:2px; }
  #mlh-root .mlh-chip {
    display:inline-flex; align-items:center; gap:5px; padding:3px 11px;
    border-radius:999px; font-size:0.72rem; font-weight:700; white-space:nowrap;
  }
  #mlh-root .mlh-profile-grid {
    display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:10px 18px;
    border-top:1px solid #eef1ee; padding-top:14px;
  }
  #mlh-root .mlh-field-label {
    font-size:0.62rem; font-weight:700; letter-spacing:0.6px; text-transform:uppercase; color:#8a949e;
  }
  #mlh-root .mlh-field-value { font-size:0.84rem; color:#101828; font-weight:600; margin-top:2px; word-break:break-word; }

  #mlh-root .mlh-topgrid {
    display:grid; grid-template-columns:minmax(0,3fr) minmax(0,2fr); gap:14px; align-items:stretch; margin-bottom:14px;
  }
  #mlh-root .mlh-topgrid > .mlh-card { margin-bottom:0; height:100%; }
  @media(max-width:1000px){ #mlh-root .mlh-topgrid { grid-template-columns:1fr; } }
  #mlh-root .mlh-statscol { padding:4px 18px; display:flex; flex-direction:column; justify-content:center; }
  #mlh-root .mlh-stat-row {
    display:flex; align-items:center; justify-content:space-between; gap:12px;
    padding:12px 0; border-bottom:1px solid #eef1ee;
  }
  #mlh-root .mlh-stat-row:last-child { border-bottom:0; }
  #mlh-root .mlh-strip {
    display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); margin-bottom:14px;
  }
  #mlh-root .mlh-strip-seg { position:relative; text-align:center; padding:14px 10px; }
  #mlh-root .mlh-strip-seg + .mlh-strip-seg::before {
    content:""; position:absolute; left:0; top:18%; bottom:18%; width:1px; background:#e6ebe7;
  }
  #mlh-root .mlh-strip-label { font-size:0.64rem; font-weight:700; letter-spacing:0.7px; text-transform:uppercase; color:#6b7280; }
  #mlh-root .mlh-strip-value { font-size:1.25rem; font-weight:800; color:#101828; margin-top:3px; font-variant-numeric:tabular-nums; }
  #mlh-root .mlh-strip-value.mlh-neg { color:#c62828; }
  #mlh-root .mlh-strip-value.mlh-pos { color:#2e7d32; }
  #mlh-root .mlh-strip-sub { font-size:0.72rem; color:#8a949e; margin-top:2px; }

  #mlh-root .mlh-tablecard { overflow:hidden; }
  #mlh-root .mlh-tablehead {
    display:flex; align-items:center; justify-content:space-between; gap:12px;
    padding:14px 20px 10px; flex-wrap:wrap;
  }
  #mlh-root .mlh-tablehead h3 { margin:0; font-size:0.92rem; font-weight:800; color:#111827; }
  #mlh-root .mlh-tablewrap { max-height:52vh; overflow:auto; }
  #mlh-root table.mlh-table { width:100%; border-collapse:separate; border-spacing:0; font-size:0.83rem; }
  #mlh-root .mlh-table thead th {
    position:sticky; top:0; z-index:3; background:#f6faf7; color:#1b5e20;
    font-weight:700; font-size:0.7rem; letter-spacing:0.4px; text-transform:uppercase;
    padding:9px 12px; border-bottom:1.5px solid #dfe9df; text-align:left; white-space:nowrap;
  }
  #mlh-root .mlh-table thead th.mlh-num { text-align:right; }
  #mlh-root .mlh-table td { padding:10px 12px; border-bottom:1px solid #f1f4f1; vertical-align:middle; background:#fff; }
  #mlh-root .mlh-table tbody tr:hover td { background:#fafcf9; }
  #mlh-root .mlh-num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
  #mlh-root .mlh-col-month { width:30%; }
  #mlh-root .mlh-col-num { width:17.5%; }
  #mlh-root .mlh-empty { text-align:center; color:#8a949e; padding:34px 18px; font-size:0.85rem; }

  /* ---------- searchable member picker (handles long member lists) ---------- */
  #mlh-root .mlh-picker-wrap { position:relative; min-width:250px; max-width:420px; width:100%; }
  #mlh-root .mlh-picker-list {
    position:absolute; top:calc(100% + 6px); left:0; right:0; z-index:60;
    background:#fff; border:1px solid #d6ddd7; border-radius:10px;
    box-shadow:0 12px 30px rgba(16,24,40,0.14); max-height:260px; overflow:auto; padding:6px;
  }
  #mlh-root .mlh-picker-item {
    display:flex; flex-direction:column; gap:1px; width:100%; text-align:left;
    border:none; background:none; cursor:pointer; font-family:inherit;
    padding:8px 10px; border-radius:7px; font-size:0.82rem; color:#1f2937;
  }
  #mlh-root .mlh-picker-item small { font-size:0.7rem; color:#8a949e; }
  #mlh-root .mlh-picker-item:hover { background:#e8f5e9; }
  #mlh-root .mlh-picker-item.selected { background:#e8f5e9; }
  #mlh-root .mlh-picker-empty { padding:12px; text-align:center; color:#8a949e; font-size:0.8rem; }
  #mlh-root .mlh-az { display:flex; flex-wrap:wrap; gap:4px; padding:8px 6px; border-bottom:1px solid #eef1ee; margin-bottom:4px; position:sticky; top:0; background:#fff; }
  #mlh-root .mlh-az-chip { border:1px solid #cfdccc; background:#fff; border-radius:20px; min-width:28px; height:24px; padding:0 8px; font-size:0.7rem; font-weight:700; color:#546e7a; cursor:pointer; line-height:22px; text-align:center; font-family:inherit; }
  #mlh-root .mlh-az-chip:hover { border-color:#1b5e20; color:#1b5e20; }
  #mlh-root .mlh-az-chip.active { background:#1b5e20; border-color:#1b5e20; color:#fff; }

  /* ---------- expandable balance breakdown ---------- */
  #mlh-root .mlh-exp {
    display:inline-flex; align-items:center; justify-content:center;
    width:20px; height:20px; border-radius:6px; border:1px solid #dfe9df;
    background:#fff; color:#5f6b5f; font-size:0.7rem; cursor:pointer; margin-right:8px; vertical-align:middle;
  }
  #mlh-root .mlh-exp:hover { background:#e8f5e9; border-color:#1e8f4e; }
  #mlh-root .mlh-exp.open i { transform:rotate(90deg); }
  #mlh-root .mlh-exp i { transition:transform 0.15s ease; }
  #mlh-root tr.mlh-detail td { background:#f6faf7; border-bottom:1px solid #dfe9df; padding:4px 12px 12px 42px; }
  #mlh-root .mlh-math { max-width:420px; font-size:0.8rem; }
  #mlh-root .mlh-math-row { display:flex; justify-content:space-between; gap:12px; padding:4px 0; color:#374151; }
  #mlh-root .mlh-math-row span:last-child { font-variant-numeric:tabular-nums; font-weight:600; }
  #mlh-root .mlh-math-total { display:flex; justify-content:space-between; gap:12px; padding:7px 0 2px; margin-top:4px; border-top:1px solid #dfe9df; font-weight:800; color:#111827; }
  #mlh-root .mlh-math-total span:last-child { font-variant-numeric:tabular-nums; }
  #mlh-root table.mlh-bd { width:100%; max-width:560px; border-collapse:collapse; font-size:0.78rem; margin-top:2px; }
  #mlh-root .mlh-bd th { text-align:left; font-size:0.64rem; text-transform:uppercase; letter-spacing:0.5px; color:#8a949e; padding:4px 8px 4px 0; border-bottom:1px solid #dfe9df; white-space:nowrap; }
  #mlh-root .mlh-bd th.mlh-num, #mlh-root .mlh-bd td.mlh-num { text-align:right; }
  #mlh-root .mlh-bd td { padding:5px 8px 5px 0; border-bottom:1px solid #f1f4f1; color:#374151; vertical-align:top; }
  #mlh-root .mlh-bd tr:last-child td { border-bottom:none; }
  `;

  let cssInjected = false;
  function ensureStyles() {
    if (cssInjected) return;
    const style = document.createElement("style");
    style.id = "mlh-styles";
    style.textContent = CSS;
    document.head.appendChild(style);
    cssInjected = true;
  }

  /* ============================== helpers ============================== */
  const PESO = (v) => "₱" + Number(v || 0).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const esc = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  function toast(message, isError) {
    if (typeof window.showToast === "function") window.showToast(message, isError);
    else if (isError) console.error(message);
  }

  const state = { members: [], memberId: null, loaded: false, letter: "ALL" };

  /* Last-name initial for the A–Z strip. Picker names arrive as
   * "SURNAME, Given Names" (surname = text before the comma); raw
   * "FIRST M LAST [suffix]" names fall back to the last meaningful token
   * (suffixes/credentials stripped). Only initials that actually exist in
   * the loaded members become filter chips. */
  const NAME_SUFFIXES = { JR: 1, SR: 1, II: 1, III: 1, IV: 1, V: 1, VI: 1 };
  function lastNameInitial(name) {
    const raw = String(name || "").trim();
    if (!raw) return "#";
    let surname = raw;
    const comma = raw.indexOf(",");
    if (comma > 0) {
      surname = raw.slice(0, comma);
    } else {
      const parts = raw.split(/\s+/).filter(Boolean);
      while (parts.length > 1) {
        const tok = parts[parts.length - 1].toUpperCase().replace(/[.,]/g, "");
        if (NAME_SUFFIXES[tok]) { parts.pop(); continue; }
        break;
      }
      surname = parts.length ? parts[parts.length - 1] : "";
    }
    const m = surname.toUpperCase().match(/[A-Z]/);
    return m ? m[0] : "#";
  }

  function availableInitials() {
    const set = {};
    state.members.forEach((m) => { set[lastNameInitial(m.member_name)] = 1; });
    delete set["#"];
    return Object.keys(set).sort();
  }

  function shellReady() {
    const root = document.getElementById("mlh-root");
    if (!root) return false;
    ensureStyles();
    if (root.dataset.shell === "1") return true;
    root.dataset.shell = "1";
    root.innerHTML = `
      <div class="mlh-card mlh-toolbar">
        <div>
          <h2 class="mlh-title">Member Ledger</h2>
          <p class="mlh-sub">Historical breakdown of individual dues collections and outstanding balances.</p>
        </div>
        <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
          <div class="mlh-picker-wrap">
            <input id="mlh-member-search" class="mlh-select" style="cursor:text;" placeholder="Search member by name, ID, or department…" autocomplete="off" />
            <div id="mlh-member-list" class="mlh-picker-list" style="display:none;"></div>
          </div>
        </div>
      </div>
      <div id="mlh-content"><div class="mlh-card mlh-empty" style="padding:44px 20px;"><i class="fa-solid fa-user" style="font-size:1.5rem; display:block; margin-bottom:10px; color:#c3ccc4;"></i>Select a member to view their ledger history.</div></div>`;
    return true;
  }

  function pickerMatches(q) {
    const needle = (q || "").trim().toLowerCase();
    return state.members.filter((m) => {
      if (state.letter !== "ALL" && lastNameInitial(m.member_name) !== state.letter) return false;
      if (needle && !((m.member_name || "") + " " + (m.employee_id || "") + " " + (m.department || "")).toLowerCase().includes(needle)) return false;
      return true;
    });
  }

  function renderPickerList() {
    const list = document.getElementById("mlh-member-list");
    const input = document.getElementById("mlh-member-search");
    if (!list || !input) return;
    const letters = availableInitials();
    if (state.letter !== "ALL" && letters.indexOf(state.letter) === -1) state.letter = "ALL";
    const items = pickerMatches(input.value);
    const az = `<div class="mlh-az"><button type="button" class="mlh-az-chip${state.letter === "ALL" ? " active" : ""}" data-az="ALL">ALL</button>` +
      letters.map((L) => `<button type="button" class="mlh-az-chip${state.letter === L ? " active" : ""}" data-az="${L}">${L}</button>`).join("") +
      `</div>`;
    list.innerHTML = az + (items.length ? items.map((m) =>
      `<button type="button" class="mlh-picker-item${String(m.member_id) === String(state.memberId) ? " selected" : ""}" data-mid="${m.member_id}">
        <span>${esc(m.member_name)}${m.membership_status ? " · " + esc(m.membership_status) : ""}</span>
        <small>${esc([m.employee_id, m.department].filter(Boolean).join(" · ") || "—")}</small>
      </button>`
    ).join("") : `<div class="mlh-picker-empty">No members found — try another search or letter.</div>`);
    list.querySelectorAll("[data-az]").forEach((b) =>
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        state.letter = b.dataset.az || "ALL";
        renderPickerList();
        input.focus();
      })
    );
    list.querySelectorAll("[data-mid]").forEach((b) =>
      b.addEventListener("click", () => {
        const m = state.members.find((x) => String(x.member_id) === String(b.dataset.mid));
        input.value = m ? m.member_name : "";
        list.style.display = "none";
        mlhLoadMember(b.dataset.mid);
      })
    );
  }

  function bindPicker() {
    const input = document.getElementById("mlh-member-search");
    const list = document.getElementById("mlh-member-list");
    if (!input || !list || input.dataset.bound === "1") return;
    input.dataset.bound = "1";
    input.addEventListener("input", () => { list.style.display = "block"; renderPickerList(); });
    input.addEventListener("focus", () => { input.select(); list.style.display = "block"; renderPickerList(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        list.style.display = "none";
        const cur = state.members.find((x) => String(x.member_id) === String(state.memberId));
        input.value = cur ? cur.member_name : "";
        input.blur();
      } else if (e.key === "Enter") {
        const first = list.querySelector("[data-mid]");
        if (list.style.display !== "none" && first) first.click();
      }
    });
    document.addEventListener("click", (e) => {
      if (!list || list.style.display === "none") return;
      if (e.target.closest && e.target.closest(".mlh-picker-wrap")) return;
      list.style.display = "none";
      const cur = state.members.find((x) => String(x.member_id) === String(state.memberId));
      if (document.activeElement !== input) input.value = cur ? cur.member_name : (state.memberId ? input.value : "");
    });
  }

  function fillMemberSelect() {
    const input = document.getElementById("mlh-member-search");
    if (!input) return;
    bindPicker();
    const cur = state.members.find((x) => String(x.member_id) === String(state.memberId));
    if (cur && document.activeElement !== input) input.value = cur.member_name;
    renderPickerList();
  }

  async function loadMembers() {
    try {
      const resp = await fetch("/api/officers/deductions/member-ledger/");
      const data = await resp.json();
      if (!data.ok) { toast(data.error || "Failed to load members.", true); return; }
      state.members = data.members || [];
      fillMemberSelect();
    } catch (e) {
      console.error("Failed to load member ledger members", e);
      toast("Failed to load members.", true);
    }
  }

  window.mlhLoadMember = async function mlhLoadMember(memberId) {
    const content = document.getElementById("mlh-content");
    if (!content) return;
    state.memberId = memberId || null;
    if (!memberId) {
      content.innerHTML = `<div class="mlh-card mlh-empty" style="padding:44px 20px;"><i class="fa-solid fa-user" style="font-size:1.5rem; display:block; margin-bottom:10px; color:#c3ccc4;"></i>Select a member to view their ledger history.</div>`;
      return;
    }
    content.innerHTML = `<div class="mlh-card mlh-empty" style="padding:34px 20px;"><i class="fa-solid fa-circle-notch fa-spin" style="margin-right:8px;"></i>Loading ledger…</div>`;
    try {
      const resp = await fetch(`/api/officers/deductions/member-ledger/?member_id=${memberId}`);
      const data = await resp.json();
      if (!data.ok) { toast(data.error || "Failed to load the ledger.", true); content.innerHTML = `<div class="mlh-card mlh-empty">${esc(data.error || "Failed to load the ledger.")}</div>`; return; }
      renderLedger(data);
    } catch (e) {
      console.error("Failed to load member ledger", e);
      content.innerHTML = `<div class="mlh-card mlh-empty">Failed to load the ledger.</div>`;
    }
  };

  function profileField(label, value) {
    return `<div><div class="mlh-field-label">${esc(label)}</div><div class="mlh-field-value">${value ? esc(value) : "—"}</div></div>`;
  }

  function renderLedger(data) {
    const content = document.getElementById("mlh-content");
    if (!content) return;
    const m = data.member || {};
    const totals = data.totals || {};
    const months = (data.months || []).slice().reverse(); // most recent first
    const PAGE_SIZE = 8;
    const pageCount = Math.max(1, Math.ceil(months.length / PAGE_SIZE));
    mlhState.page = Math.min(Math.max(mlhState.page, 1), pageCount);
    const pageMonths = months.slice((mlhState.page - 1) * PAGE_SIZE, mlhState.page * PAGE_SIZE);
    const initials = String(m.full_name || "?").split(/\s+/).slice(0, 2).map((p) => p[0] || "").join("").toUpperCase();

    const profile = `
      <div class="mlh-card mlh-profile">
        <div class="mlh-profile-head">
          <span class="mlh-avatar">${esc(initials)}</span>
          <div style="flex:1; min-width:220px;">
            <div class="mlh-profile-name">${esc(m.full_name || "—")}</div>
            <div class="mlh-profile-sub">${esc(m.position || "Faculty Member")} · ${esc(m.department || "Unassigned")}</div>
          </div>
          <span class="mlh-chip" style="background:#e8f5e9; color:#1b5e20;">${esc(m.membership_status || "Member")}</span>
        </div>
        <div class="mlh-profile-grid">
          ${profileField("Email", m.email)}
          ${profileField("Contact Number", m.contact_number)}
        </div>
      </div>`;

    const statRow = (label, sub, valueHtml) => `
      <div class="mlh-stat-row">
        <div>
          <div class="mlh-strip-label">${label}</div>
          <div class="mlh-strip-sub">${sub}</div>
        </div>
        <div class="mlh-strip-value" style="margin:0;">${valueHtml}</div>
      </div>`;

    const strip = `
      <div class="mlh-card mlh-statscol">
        ${statRow("Months recorded", "monthly deduction history", String(totals.months_recorded || 0))}
        ${statRow("Total deducted", "across all recorded months", `<span class="mlh-pos">${PESO(totals.total_deducted)}</span>`)}
        ${statRow(
          "Outstanding Balance",
          Number(totals.remaining_balance) > 0 ? "outstanding, to be settled" : "fully settled",
          `<span class="${Number(totals.remaining_balance) > 0 ? "mlh-neg" : "mlh-pos"}">${PESO(totals.remaining_balance)}</span>`
        )}
      </div>`;

    // One-time membership fee row on top of the Monthly Payment Log.
    const fee = data.membership_fee || null;
    const feePaidAmt = fee && fee.paid ? Number(fee.amount) || 0 : 0;
    const feeRequired = fee ? Number(fee.required_amount) || 0 : 0;
    const feeBalance = fee ? Math.max(0, feeRequired - feePaidAmt) : 0;
    const feeRow = fee ? `<tr>
      <td>
        <span style="font-weight:700; color:#111827;">Membership Fee (One-time)</span>
        <small style="color:#8a949e; display:block; margin-left:28px;">${esc(fee.status || "")}${fee.payment_date ? " · " + esc(fee.payment_date) : ""}</small>
      </td>
      <td class="mlh-num">${PESO(feeRequired)}</td>
      <td class="mlh-num" style="font-weight:700;">${fee.paid ? PESO(feePaidAmt) : "—"}</td>
      <td class="mlh-num">—</td>
      <td class="mlh-num" style="${feeBalance > 0 ? "color:#c62828; font-weight:700;" : "color:#2e7d32;"}">${PESO(feeBalance)}</td>
    </tr>` : "";

    const table = `
      <div class="mlh-card mlh-tablecard">
        <div class="mlh-tablehead">
          <h3>Monthly Payment Log</h3>
          <span style="font-size:0.74rem; color:#8a949e;">Most recent month first · click a row for the balance breakdown</span>
        </div>
        <div class="mlh-tablewrap">
          <table class="mlh-table">
            <colgroup>
              <col class="mlh-col-month" />
              <col class="mlh-col-num" />
              <col class="mlh-col-num" />
              <col class="mlh-col-num" />
              <col class="mlh-col-num" />
            </colgroup>
            <thead><tr>
              <th>Billing Period</th>
              <th class="mlh-num">Expected Collection</th>
              <th class="mlh-num">Deducted</th>
              <th class="mlh-num">Paid Balance</th>
              <th class="mlh-num">Outstanding Balance</th>
            </tr></thead>
            <tbody>
              ${mlhState.page === 1 ? feeRow : ""}
              ${pageMonths.map((row) => `<tr data-mrow="${row.assessment_id}">
                <td>
                  <button type="button" class="mlh-exp" data-exp="${row.assessment_id}" onclick="mlhToggleDetail(${row.assessment_id})" title="Show balance breakdown"><i class="fas fa-chevron-right"></i></button>
                  <span style="font-weight:700; color:#111827;">${esc(row.month_label)}</span>
                  <small style="color:#8a949e; display:block; margin-left:28px;">${esc(row.assessment_status_label || row.assessment_status || "")}</small>
                </td>
                <td class="mlh-num">${PESO(row.standard)}</td>
                <td class="mlh-num" style="font-weight:700;">${PESO(row.deducted)}</td>
                <td class="mlh-num">${row.prior_collected > 0 ? PESO(row.prior_collected) : "—"}</td>
                <td class="mlh-num" style="${row.remaining_balance > 0 ? "color:#c62828; font-weight:700;" : "color:#2e7d32;"}">${PESO(row.remaining_balance)}</td>
              </tr>`).join("") || `<tr><td colspan="5" class="mlh-empty">No monthly deductions recorded yet for this member.</td></tr>`}
            </tbody>
          </table>
        </div>
        <div id="mlh-ledger-pagination" style="padding:12px 20px 14px;"></div>
      </div>`;

    content.innerHTML = `<div class="mlh-topgrid">${profile}${strip}</div>` + table;
    mlhState.cache = {};
    pageMonths.forEach((row) => { mlhState.cache[row.assessment_id] = row; });
    const pagerEl = document.getElementById("mlh-ledger-pagination");
    if (pagerEl && typeof UniPager !== "undefined" && months.length) {
      pagerEl.innerHTML = UniPager.html(mlhState.page, pageCount, "window.__mlhGoPage(PAGE)", UniPager.count(mlhState.page, PAGE_SIZE, months.length));
    }
  }
  const mlhState = { page: 1, cache: {} };
  window.mlhToggleDetail = function mlhToggleDetail(assessmentId) {
    const btn = document.querySelector(`[data-exp="${assessmentId}"]`);
    const mainRow = document.querySelector(`tr[data-mrow="${assessmentId}"]`);
    if (!btn || !mainRow) return;
    const openRow = mainRow.nextElementSibling;
    if (openRow && openRow.classList.contains("mlh-detail")) {
      openRow.remove();
      btn.classList.remove("open");
      return;
    }
    const row = (mlhState.cache || {})[assessmentId] || {};
    const standard = Number(row.standard) || 0;
    const deducted = Number(row.deducted) || 0;
    const priorOut = Number(row.prior_outstanding) || 0;
    const priorCol = Number(row.prior_collected) || 0;
    const current = standard - deducted;
    const remaining = Number(row.remaining_balance) || 0;
    const mathRow = (label, value, bold) => `
      <div class="mlh-math-row"><span>${label}</span><span${bold ? ' style="font-weight:800;color:#111827;"' : ""}>${value}</span></div>`;
    /* The pooled carry keeps its months context: show which months the
       prior outstanding is made of and what is still left on each. */
    const priorMonths = Array.isArray(row.prior_months) ? row.prior_months : [];
    const settledByKey = {};
    (Array.isArray(row.prior_collected_months) ? row.prior_collected_months : []).forEach((s) => {
      if (s && s.key) settledByKey[s.key] = (settledByKey[s.key] || 0) + (Number(s.amount) || 0);
    });
    const carriedMonthsLine = priorMonths.length
      ? mathRow(
          "Carried months",
          priorMonths.map((m) => {
            const paid = settledByKey[m.key] || 0;
            const left = Math.max(0, (Number(m.amount) || 0) - paid);
            return `${m.label || m.key}: ${PESO(left)} left`;
          }).join(" · "),
          false
        )
      : "";
    // Due vs aid split for this month: each assessed item (monthly due,
    // medical/death aid with recipient) with expected / deducted / balance.
    const bdRows = row.breakdown && Array.isArray(row.breakdown.rows)
      ? row.breakdown.rows.filter((r) => r && r.kind === "item" && ((Number(r.required) || 0) > 0 || (Number(r.applied) || 0) > 0))
      : [];
    const breakdownBlock = bdRows.length ? `
      <div style="margin-top:10px; padding-top:8px; border-top:1px solid #dfe9df;">
        <div class="mlh-field-label" style="margin-bottom:4px;">Due &amp; aid breakdown</div>
        <table class="mlh-bd">
          <thead><tr><th>Item</th><th class="mlh-num">Expected</th><th class="mlh-num">Deducted</th><th class="mlh-num">Outstanding</th></tr></thead>
          <tbody>
            ${bdRows.map((r) => {
              const rem = Number(r.remaining) || 0;
              return `<tr>
                <td>${esc(r.purpose)}${r.recipient ? `<br><span style="font-size:0.72rem; color:#8a949e;">${esc(r.recipient)}</span>` : ""}</td>
                <td class="mlh-num">${PESO(r.required)}</td>
                <td class="mlh-num">${PESO(r.applied)}</td>
                <td class="mlh-num" style="${rem > 0 ? "color:#c62828; font-weight:700;" : ""}">${PESO(rem)}</td>
              </tr>`;
            }).join("")}
          </tbody>
        </table>
      </div>` : "";
    const detail = document.createElement("tr");
    detail.className = "mlh-detail";
    detail.innerHTML = `<td colspan="5">
      <div class="mlh-math">
        ${mathRow("Expected collection", PESO(standard))}
        ${mathRow("Less: deducted", "− " + PESO(deducted))}
        ${mathRow("Current month balance", PESO(current), true)}
        ${mathRow("Add: prior outstanding carried in", PESO(priorOut))}
        ${carriedMonthsLine}
        ${mathRow("Less: prior balance settled", "− " + PESO(priorCol))}
        <div class="mlh-math-total"><span>Outstanding balance</span><span style="color:${remaining > 0 ? "#c62828" : "#2e7d32"};">${PESO(remaining)}</span></div>
        ${breakdownBlock}
      </div>
    </td>`;
    mainRow.after(detail);
    btn.classList.add("open");
  };
  window.__mlhGoPage = function (p) {
    mlhState.page = p;
    if (state.memberId) mlhLoadMember(state.memberId);
  };

  /* ============================== boot ============================== */
  document.addEventListener("DOMContentLoaded", () => {
    if (!shellReady()) return;
    loadMembers();
  });
  window.mlhRefresh = function () {
    loadMembers();
    if (state.memberId) mlhLoadMember(state.memberId);
  };
})();
