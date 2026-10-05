/* ==========================================================================
   OVERVIEW DASHBOARD — the standard overview for all three officer pages.
   --------------------------------------------------------------------------
   One shared design system (ovd-* classes, styles scoped under #ovd-root so
   host-page CSS cannot interfere). The overview is a VISUAL SUMMARY ONLY:

     1. Toolbar      — month picker + workflow status chip
     2. KPI row      — exactly four stat cards, scannable in seconds
     3. Chart row    — gauge / donut / visual bar lists, zero data tables
     4. Summary strip— the money figures on a single line
     5. Action row   — one-click jump into the working module

   Working lists (member recording, bulk verification, notification history,
   month-by-month tables) live in their own modules — the overview never
   duplicates them.

   Roles (auto-detected from the host page):
     President — monitor: gauge, assessment breakdown, department compliance
     Treasurer — record:  deduction status, department status, money strip
     Auditor   — verify:  verification activity, deduction status, variance

   Data comes only from the monthly deduction workflow APIs:
     GET  /api/auditor/deductions/heatmap/
     GET  /api/treasurer/deductions/members/<id>/          (submit-state only)
     POST /api/treasurer/deductions/record/                (submit:true)
   ========================================================================== */
(function () {
  "use strict";

  /* ================= injected styles (host-page-proof) ================== */
  const CSS = `
  #ovd-root { display:block; font-family:inherit; color:#1f2937; }
  #ovd-root *, #ovd-root *::before, #ovd-root *::after { box-sizing:border-box; }

  /* ---------- cards & panels ---------- */
  #ovd-root .ovd-card {
    background:#ffffff; border:1px solid #e8eaed; border-radius:16px;
    box-shadow:0 2px 8px rgba(0,0,0,0.04);
  }
  #ovd-root .ovd-panel { padding:24px; }
  #ovd-root .ovd-stack > * + * { margin-top:20px; }

  #ovd-root .ovd-panel-head {
    display:flex; align-items:flex-start; justify-content:space-between;
    gap:12px; margin-bottom:16px; flex-wrap:wrap;
  }
  #ovd-root .ovd-panel-title {
    display:flex; align-items:center; gap:10px; margin:0;
    font-size:1.1rem; font-weight:700; color:#1a1a1a; line-height:1.3;
  }
  #ovd-root .ovd-panel-ico {
    width:36px; height:36px; border-radius:10px; flex:0 0 36px;
    display:inline-flex; align-items:center; justify-content:center;
    font-size:0.9rem; background:#e8f5e9; color:#2e7d32;
  }
  #ovd-root .ovd-panel-sub { margin:4px 0 0; font-size:0.85rem; color:#6b7280; }

  /* ---------- toolbar ---------- */
  #ovd-root .ovd-toolbar {
    display:flex; align-items:center; gap:16px; flex-wrap:wrap;
    padding:20px 24px; margin-bottom:20px;
  }
  #ovd-root .ovd-toolbar-title {
    display:flex; align-items:center; gap:10px; margin:0;
    font-size:1.2rem; font-weight:800; color:#1a1a1a;
  }
  #ovd-root .ovd-toolbar-title .ovd-panel-ico { width:40px; height:40px; flex-basis:40px; font-size:1rem; }
  #ovd-root .ovd-toolbar-sub { font-size:0.8rem; color:#6b7280; margin:2px 0 0; }
  #ovd-root .ovd-toolbar-spacer { flex:1 1 auto; }
  #ovd-root .ovd-toolbar-label { font-size:0.75rem; font-weight:600; color:#6b7280; white-space:nowrap; }

  /* ---------- KPI row ---------- */
  #ovd-root .ovd-kpis {
    display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));
    gap:16px; margin-bottom:20px;
  }
  #ovd-root .ovd-kpi { padding:20px; display:flex; flex-direction:column; gap:8px; }
  #ovd-root .ovd-kpi-label {
    display:flex; align-items:center; gap:8px;
    font-size:0.7rem; font-weight:700; letter-spacing:0.8px;
    text-transform:uppercase; color:#6b7280; line-height:1.4;
  }
  #ovd-root .ovd-kpi-dot { width:10px; height:10px; border-radius:50%; flex:0 0 10px; }
  #ovd-root .ovd-kpi-value { font-size:1.8rem; font-weight:800; color:#1a1a1a; line-height:1.1; }
  #ovd-root .ovd-kpi-value.ovd-pos  { color:#1e8f4e; }
  #ovd-root .ovd-kpi-value.ovd-neg  { color:#b93a3a; }
  #ovd-root .ovd-kpi-value.ovd-warn { color:#9a6a12; }
  #ovd-root .ovd-kpi-sub { font-size:0.8rem; color:#8a949e; margin-top:-4px; }

  /* ---------- toolbar period group ---------- */
  #ovd-root .ovd-period-group {
    display:flex; align-items:center; gap:10px; flex-wrap:wrap;
    padding:8px 14px; background:#f8faf8; border:1px solid #e6ebe7; border-radius:12px;
  }

  /* ---------- layout grids ---------- */
  #ovd-root .ovd-row { display:grid; gap:20px; margin-bottom:20px; }
  #ovd-root .ovd-row.ovd-11 { grid-template-columns:repeat(2, minmax(0,1fr)); }
  #ovd-root .ovd-row.ovd-3 { grid-template-columns:repeat(3, minmax(0,1fr)); }
  @media (max-width: 1020px) {
    #ovd-root .ovd-row.ovd-11,
    #ovd-root .ovd-row.ovd-3 { grid-template-columns:minmax(0,1fr); }
  }

  /* ---------- buttons / chips ---------- */
  #ovd-root .ovd-btn {
    display:inline-flex; align-items:center; gap:10px;
    border:1px solid #d6ddd7; background:#ffffff; color:#374151;
    border-radius:12px; padding:12px 20px; font-size:0.9rem; font-weight:600;
    cursor:pointer; white-space:nowrap; font-family:inherit; line-height:1.2;
    transition:all 0.2s ease;
  }
  #ovd-root .ovd-btn:hover { background:#f3f6f3; border-color:#c6ccc8; }
  #ovd-root .ovd-btn:disabled { opacity:0.5; cursor:not-allowed; }
  #ovd-root .ovd-btn-primary { background:#1b5e20; border-color:#1b5e20; color:#ffffff; }
  #ovd-root .ovd-btn-primary:hover { background:#256b29; }
  #ovd-root .ovd-btn-lg { padding:14px 28px; font-size:0.95rem; border-radius:12px; font-weight:700; }
  #ovd-root .ovd-treasurer-toolbar { gap:14px; flex-wrap:nowrap; align-items:center; }
  @media (max-width: 1100px) { #ovd-root .ovd-treasurer-toolbar { flex-wrap:wrap; } }
  #ovd-root .ovd-treasurer-toolbar .ovd-period-group { gap:8px; padding:5px 8px; }
  #ovd-root .ovd-treasurer-toolbar .ovd-toolbar-label { font-size:0.7rem; }
  #ovd-root .ovd-treasurer-toolbar .ovd-select { padding:8px 10px; font-size:0.8rem; }
  #ovd-root .ovd-btn-compact { padding:8px 11px; font-size:0.78rem; border-radius:8px; }

  #ovd-root .ovd-select {
    border:1px solid #d6ddd7; border-radius:10px; background:#ffffff;
    padding:10px 14px; font-size:0.85rem; color:#1f2937; font-family:inherit; cursor:pointer;
  }
  #ovd-root .ovd-select:focus {
    outline:none; border-color:#2e7d32; box-shadow:0 0 0 3px rgba(46,125,50,0.12);
  }

  #ovd-root .ovd-chip {
    display:inline-flex; align-items:center; gap:6px;
    padding:4px 12px; border-radius:999px;
    font-size:0.75rem; font-weight:700; letter-spacing:0.3px; white-space:nowrap;
  }

  /* ---------- rate bars & stacked bars ---------- */
  #ovd-root .ovd-bar { display:flex; align-items.center; gap:10px; min-width:120px; }
  #ovd-root .ovd-bar-track { flex:1; height:10px; border-radius:99px; background:#eef1ee; overflow:hidden; }
  #ovd-root .ovd-bar-fill { height:100%; border-radius:99px; }
  #ovd-root .ovd-bar-pct { font-size:0.8rem; font-weight:700; color:#475569; min-width:45px; text-align:right; }

  #ovd-root .ovd-stackbar { display:flex; height:12px; border-radius:99px; overflow:hidden; background:#eef1ee; min-width:120px; }
  #ovd-root .ovd-stackbar span { height:100%; }

  /* ---------- visual department lists ---------- */
  #ovd-root .ovd-dept-list { display:flex; flex-direction:column; }
  /* In two-column rows the compliance card stretches to its sibling's
     height — spread the department rows evenly so they occupy it fully. */
  #ovd-root .ovd-row.ovd-11 > .ovd-card, #ovd-root .ovd-row.ovd-3 > .ovd-card { display:flex; flex-direction:column; }
  #ovd-root .ovd-row.ovd-11 > .ovd-card > .ovd-dept-list, #ovd-root .ovd-row.ovd-3 > .ovd-card > .ovd-dept-list { flex:1 1 auto; justify-content:space-evenly; }
  #ovd-root .ovd-dept-row {
    display:grid; grid-template-columns:minmax(110px, 190px) 1fr auto;
    gap:14px; align-items:center; padding:12px 4px;
    border-bottom:1px solid #f1f4f1; font-size:0.85rem;
  }
  #ovd-root .ovd-dept-row:last-child { border-bottom:none; }
  #ovd-root .ovd-dept-name { font-weight:600; color:#1a1a1a; line-height:1.4; overflow:hidden; text-overflow:ellipsis; }
  #ovd-root .ovd-dept-side { text-align:right; white-space:nowrap; font-size:0.8rem; font-weight:700; }

  /* ---------- gauge ---------- */
  #ovd-root .ovd-gauge-wrap { display:flex; align-items:center; justify-content:center; padding:8px 0 4px; }
  #ovd-root .ovd-gauge-badge { text-align:center; margin-top:4px; }

  /* ---------- donut ---------- */
  #ovd-root .ovd-donut-wrap {
    display:flex; align-items:center; justify-content:center; gap:30px; flex-wrap:wrap; padding:10px 4px;
  }
  #ovd-root .ovd-donut {
    width:170px; height:170px; border-radius:50%; flex:0 0 auto;
    display:flex; align-items:center; justify-content:center;
  }
  #ovd-root .ovd-donut-hole {
    width:110px; height:110px; border-radius:50%; background:#ffffff;
    display:flex; flex-direction:column; align-items:center; justify-content:center;
    box-shadow:0 0 0 1px rgba(16,24,40,0.03) inset;
  }
  #ovd-root .ovd-donut-hole strong { font-size:1.4rem; color:#1a1a1a; line-height:1.1; }
  #ovd-root .ovd-donut-hole small { font-size:0.72rem; color:#8a949e; margin-top:4px; }
  #ovd-root .ovd-legend { display:flex; flex-direction:column; gap:10px; min-width:160px; }
  #ovd-root .ovd-legend-row { display:flex; align-items:center; gap:10px; font-size:0.85rem; color:#374151; }
  #ovd-root .ovd-legend-row .ovd-dot { width:10px; height:10px; border-radius:50%; flex:0 0 10px; }
  #ovd-root .ovd-legend-row strong { margin-left:auto; font-variant-numeric:tabular-nums; }
  #ovd-root .ovd-legend-row small { color:#8a949e; min-width:45px; text-align:right; }

  /* ---------- summary strip (one line of money figures) ---------- */
  #ovd-root .ovd-strip {
    display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));
    padding:18px 12px;
  }
  #ovd-root .ovd-strip-seg { position:relative; padding:6px 20px; text-align:center; }
  #ovd-root .ovd-strip-seg + .ovd-strip-seg::before {
    content:""; position:absolute; left:0; top:20%; bottom:20%;
    width:1px; background:#e6ebe7;
  }
  #ovd-root .ovd-strip-label {
    font-size:0.7rem; font-weight:700; letter-spacing:0.8px;
    text-transform:uppercase; color:#6b7280;
  }
  #ovd-root .ovd-strip-value { font-size:1.4rem; font-weight:800; color:#1a1a1a; margin-top:4px; font-variant-numeric:tabular-nums; }
  #ovd-root .ovd-strip-value.ovd-pos { color:#1e8f4e; }
  #ovd-root .ovd-strip-value.ovd-neg { color:#b93a3a; }
  #ovd-root .ovd-strip-sub { font-size:0.75rem; color:#8a949e; margin-top:4px; }

  /* ---------- action row ---------- */
  #ovd-root .ovd-cta-row { display:flex; gap:14px; align-items:center; justify-content:center; flex-wrap:wrap; padding:8px 0 4px; }

  /* ---------- misc ---------- */
  #ovd-root .ovd-loading { padding:40px; text-align:center; color:#8a949e; font-size:0.9rem; }
  #ovd-root .ovd-error { padding:24px; color:#c62828; font-size:0.9rem; }
  #ovd-root .ovd-info {
    background:#eff6ff; border:1px solid #cfe0f5; border-left:4px solid #3b82f6;
    border-radius:12px; padding:14px 16px; margin-bottom:16px;
    font-size:0.85rem; color:#1e40af; line-height:1.5;
  }
  #ovd-root .ovd-readonly-note {
    display:flex; align-items:center; justify-content:space-between; gap:12px;
    padding:9px 12px; margin-bottom:12px; border:1px solid #d9e1da;
    border-left:3px solid #718096; border-radius:8px; background:#f7f9f7;
    color:#667085; font-size:0.78rem; line-height:1.35;
  }
  #ovd-root .ovd-readonly-label { display:inline-flex; align-items:center; gap:7px; color:#475467; }
  #ovd-root .ovd-readonly-label i { color:#667085; }
  @media (max-width: 760px) {
    #ovd-root .ovd-readonly-note { align-items:flex-start; flex-direction:column; gap:3px; }
  }
  #ovd-root .ovd-muted { color:#8a949e; }
  #ovd-root .ovd-tiny { font-size:0.75rem; }

  /* ---------- treasurer visualization panels (donuts + strips) ---------- */
  #ovd-root .ovd-viz { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:20px; }
  @media (max-width: 1020px) { #ovd-root .ovd-viz { grid-template-columns:minmax(0,1fr); } }
  #ovd-root .ovd-viz-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:6px; flex-wrap:wrap; }
  #ovd-root .ovd-viz-title { margin:0; font-size:1.0rem; font-weight:700; color:#1a1a1a; line-height:1.3; }
  #ovd-root .ovd-viz-sub { margin:4px 0 0; font-size:0.82rem; color:#6b7280; }
  #ovd-root .ovd-viz-badges { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
  #ovd-root .ovd-pill {
    display:inline-flex; align-items:center; padding:4px 12px; border-radius:8px;
    background:#eef2f7; border:1px solid #e2e8f0; color:#64748b;
    font-size:0.75rem; font-weight:600; white-space:nowrap;
  }
  #ovd-root .ovd-donutrow { display:flex; align-items:center; gap:26px; flex-wrap:wrap; padding:14px 4px 6px; }
  #ovd-root .ovd-donutstack { flex-direction:column; align-items:stretch; }
  #ovd-root .ovd-donutstack .ovd-ring { margin:2px auto 4px; width:210px; height:210px; }
  #ovd-root .ovd-donutstack .ovd-ring-hole { width:140px; height:140px; }
  #ovd-root .ovd-donutstack .ovd-ring-hole strong { font-size:1.6rem; }
  #ovd-root .ovd-ring {
    width:150px; height:150px; border-radius:50%; flex:0 0 auto;
    display:flex; align-items:center; justify-content:center;
  }
  #ovd-root .ovd-ring-hole {
    width:100px; height:100px; border-radius:50%; background:#ffffff;
    display:flex; flex-direction:column; align-items:center; justify-content:center;
  }
  #ovd-root .ovd-ring-hole strong { font-size:1.4rem; color:#1a1a1a; line-height:1.1; font-variant-numeric:tabular-nums; }
  #ovd-root .ovd-ring-hole small { font-size:0.68rem; font-weight:700; letter-spacing:0.6px; color:#8a949e; margin-top:4px; }
  #ovd-root .ovd-ring-hole .ovd-perm { font-size:0.95rem; color:#8a949e; }
  #ovd-root .ovd-leglist { display:flex; flex-direction:column; gap:10px; flex:1 1 200px; min-width:200px; }
  #ovd-root .ovd-legrow {
    display:flex; align-items:center; gap:10px; font-size:0.87rem; font-weight:600; color:#1f2937;
    background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:10px 14px;
  }
  #ovd-root .ovd-legrow .ovd-dot { width:10px; height:10px; border-radius:50%; flex:0 0 10px; }
  #ovd-root .ovd-legrow strong { margin-left:auto; font-weight:800; color:#111827; font-variant-numeric:tabular-nums; white-space:nowrap; }
  #ovd-root .ovd-strip3 {
    display:grid; grid-template-columns:repeat(3, minmax(0,1fr));
    background:#f8fafc; border:1px solid #eef2f7; border-radius:12px;
    padding:14px 8px; margin-top:14px;
  }
  #ovd-root .ovd-strip3-seg { position:relative; padding:2px 12px; text-align:center; min-width:0; }
  #ovd-root .ovd-strip3-seg + .ovd-strip3-seg::before {
    content:""; position:absolute; left:0; top:15%; bottom:15%;
    width:1px; background:#e2e8f0;
  }
  #ovd-root .ovd-strip3-label { font-size:0.68rem; font-weight:700; letter-spacing:0.6px; text-transform:uppercase; color:#8a9490; }
  #ovd-root .ovd-strip3-value { font-size:1.1rem; font-weight:800; margin-top:4px; font-variant-numeric:tabular-nums; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  #ovd-root .ovd-bdtable-wrap { margin-top:12px; border:1px solid #eef2f7; border-radius:10px; overflow:hidden; }
  #ovd-root .ovd-bdtable { width:100%; border-collapse:collapse; font-size:0.8rem; }
  #ovd-root .ovd-bdtable th { background:#f8fafc; color:#8a9490; font-size:0.66rem; text-transform:uppercase; letter-spacing:0.5px; padding:8px 12px; text-align:left; font-weight:700; }
  #ovd-root .ovd-bdtable td { padding:8px 12px; border-top:1px solid #eef2f7; color:#1f2937; font-weight:600; }
  #ovd-root .ovd-bdtable .num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
  #ovd-root .ovd-pos { color:#1e8f4e; }
  #ovd-root .ovd-neg { color:#b93a3a; }

  /* ---------- single month-year popup picker (treasurer) ---------- */
  #ovd-root .ovd-picker-wrap { position:relative; }
  #ovd-root .ovd-picker-btn { display:inline-flex; align-items:center; gap:10px; min-width:190px; justify-content:space-between; }
  #ovd-root .ovd-picker-pop {
    position:absolute; top:calc(100% + 8px); right:0; width:302px; z-index:60;
    background:#fff; border:1px solid #d6ddd7; border-radius:12px;
    box-shadow:0 12px 32px rgba(0,0,0,0.12); padding:14px;
  }
  #ovd-root .ovd-picker-year { display:flex; align-items:center; justify-content:space-between; padding:2px 4px 10px; margin-bottom:10px; border-bottom:1px solid #eef2f7; }
  #ovd-root .ovd-picker-year strong { font-size:0.9rem; color:#1f2937; }
  #ovd-root .ovd-picker-nav { border:none; background:#f1f5f9; width:28px; height:28px; border-radius:8px; cursor:pointer; color:#475569; font-size:1.1rem; line-height:1; }
  #ovd-root .ovd-picker-nav:hover:not(:disabled) { background:#e2e8f0; }
  #ovd-root .ovd-picker-nav:disabled { opacity:0.35; cursor:default; }
  #ovd-root .ovd-picker-grid { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px; }
  #ovd-root .ovd-mbtn {
    border:1px solid #e2e8f0; background:#f8fafc; border-radius:8px; padding:9px 4px;
    font-size:0.8rem; font-weight:600; color:#334155; cursor:pointer; font-family:inherit;
    display:flex; align-items:center; justify-content:center; gap:4px;
  }
  #ovd-root .ovd-mbtn:hover:not(:disabled) { border-color:#1e8f4e; background:#e7f6ec; }
  #ovd-root .ovd-mbtn.current { background:#1e8f4e; border-color:#1e8f4e; color:#fff; }
  #ovd-root .ovd-mbtn:disabled { background:transparent; border-color:transparent; color:#cbd5e1; cursor:default; }
  #ovd-root .ovd-mbtn .ovd-mini { font-size:0.62rem; opacity:0.75; }
  `;

  let cssInjected = false;
  function ensureStyles() {
    if (cssInjected) return;
    const style = document.createElement("style");
    style.id = "ovd-overview-styles";
    style.textContent = CSS;
    document.head.appendChild(style);
    cssInjected = true;
  }

  /* ============================== helpers ============================== */
  const PESO = (v) => "₱" + Number(v || 0).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const PESO0 = (v) => "₱" + Number(v || 0).toLocaleString("en-PH", { maximumFractionDigits: 0 });
  const esc = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const pct = (n, d) => (d ? Math.round((n / d) * 100) : 0);

  function getCookie(name) {
    const parts = document.cookie.split(`; ${name}=`);
    return parts.length === 2 ? parts.pop().split(";").shift() : "";
  }
  function csrfToken() {
    const input = document.querySelector("input[name='csrfmiddlewaretoken']");
    return (input && input.value) || getCookie("csrftoken");
  }
  function toast(message, isError) {
    if (typeof window.showToast === "function") window.showToast(message, isError);
    else if (isError) console.error(message);
  }

  /* Status chips stay inside the green/white/gray palette — green for
     healthy states, amber for in-review, red only for returned records. */
  const STATUS_META = {
    draft:            { label: "Draft",                  bg: "#eef1ee", fg: "#5f6b64" },
    pending_treasurer: { label: "For Auditing",        bg: "#eef7f0", fg: "#1e8f4e" },
    pending_audit:    { label: "For Auditing",          bg: "#faf3e2", fg: "#9a6a12" },
    pending_final:    { label: "For Approval",         bg: "#eef1ee", fg: "#4a5a50" },
    final_approved:   { label: "Approved",               bg: "#dcefe2", fg: "#14532d" },
    rejected:         { label: "Returned for Fixes",    bg: "#fbeeee", fg: "#b93a3a" },
    returned:         { label: "Returned for Fixes",  bg: "#faf3e2", fg: "#9a6a12" },
  };
  function statusChip(status) {
    const m = STATUS_META[status] || { label: status || "—", bg: "#f1f5f9", fg: "#475569" };
    return chip(m.bg, m.fg, m.label);
  }
  function chip(bg, fg, label) {
    return `<span class="ovd-chip" style="background:${bg}; color:${fg};">${label}</span>`;
  }

  function rateColor(rate) {
    const r = Math.min(100, Math.max(0, Number(rate) || 0));
    if (r >= 85) return "#1e8f4e";
    if (r >= 70) return "#6aa97c";
    if (r >= 50) return "#c99a2e";
    return "#b93a3a";
  }
  function rateName(rate) {
    const r = Math.min(100, Math.max(0, Number(rate) || 0));
    if (r >= 85) return "Excellent";
    if (r >= 70) return "Needs Attention";
    if (r >= 50) return "Concerning";
    return "Critical";
  }
  function statusChipFromRate(rate) {
    const r = Math.min(100, Math.max(0, Number(rate) || 0));
    if (r >= 85) return chip("#e9f4ec", "#1e8f4e", "VERY GOOD");
    if (r >= 70) return chip("#f1f8f3", "#4e7d61", "GOOD");
    if (r >= 50) return chip("#faf3e2", "#9a6a12", "BAD");
    return chip("#fbeeee", "#b93a3a", "VERY BAD");
  }

  function panel(icon, title, subtitle, body) {
    return `<div class="ovd-card ovd-panel">
      <div class="ovd-panel-head">
        <div>
          <h3 class="ovd-panel-title">${icon ? `<span class="ovd-panel-ico"><i class="fas ${icon}"></i></span>` : ""}${title}</h3>
          ${subtitle ? `<p class="ovd-panel-sub">${subtitle}</p>` : ""}
        </div>
      </div>
      ${body}
    </div>`;
  }

  function memberCount(t) {
    return (t.full || 0) + (t.partial || 0) + (t.zero || 0) + (t.pending || 0);
  }

  function rateBar(rate) {
    const r = Math.min(100, Math.max(0, Number(rate) || 0));
    const c = rateColor(r);
    return `<div class="ovd-bar">
      <div class="ovd-bar-track"><div class="ovd-bar-fill" style="width:${r}%; background:${c};"></div></div>
      <span class="ovd-bar-pct" style="color:${c};">${r.toFixed(0)}%</span>
    </div>`;
  }

  function collapseEmptyGroups() {
    document.querySelectorAll(".sidebar .nav-group-title").forEach((title) => {
      if (title.classList.contains("nav-system-group")) {
        title.style.display = "";
        return;
      }
      let el = title.nextElementSibling;
      let visible = 0;
      while (el && !el.classList.contains("nav-group-title")) {
        if (el.classList.contains("menu-item") && el.offsetParent !== null) visible += 1;
        el = el.nextElementSibling;
      }
      if (visible === 0) title.style.display = "none";
    });
  }

  /* ============================== state ============================== */
  const state = { role: "", assessmentId: null, view: null, viewOnly: false, roster: null, recordable: false, loading: false };

  function detectRole() {
    if (window.OFFICER_ROLE) return String(window.OFFICER_ROLE).toLowerCase();
    if (document.getElementById("president-monthly-assessment") || document.getElementById("ma-items-body")) return "president";
    if (document.getElementById("compliance-heatmap") || document.getElementById("mdhm-members-body")) return "auditor";
    if (document.getElementById("view-monthly-deduction") || document.getElementById("md-month-select")) return "treasurer";
    return "";
  }

  const ROLE_SUBTITLE = {
    president: "Monitor collection performance and department compliance.",
    treasurer: "Record monthly member deductions and submit them for audit.",
    auditor:   "Review, verify, and endorse monthly deduction records.",
  };
  /* ============================== data ============================== */
  async function fetchJson(url, options) {
    const resp = await fetch(url, options);
    return resp.json();
  }

  async function load(assessmentId) {
    const root = document.getElementById("ovd-root");
    if (!root || state.loading) return;
    state.loading = true;
    root.innerHTML = `<div class="ovd-card ovd-panel"><div class="ovd-loading"><i class="fas fa-circle-notch fa-spin" style="margin-right:8px;"></i>Loading overview…</div></div>`;
    try {
      const q = assessmentId ? `?assessment_id=${assessmentId}` : "";
      const data = await fetchJson(`/api/auditor/deductions/heatmap/${q}`);
      if (!data.ok) {
        root.innerHTML = `<div class="ovd-card ovd-panel"><div class="ovd-error"><i class="fas fa-triangle-exclamation" style="margin-right:8px;"></i>${esc(data.error || "The overview could not be loaded.")}</div></div>`;
        return;
      }
      state.view = data;
      const outstandingKpi = document.getElementById("kpi-outstanding");
      const outstandingSub = document.getElementById("kpi-outstanding-sub");
      if (outstandingKpi) outstandingKpi.textContent = PESO(data.totals && data.totals.outstanding || 0);
      if (outstandingSub) {
        const membersBehind = (data.members || []).filter((m) => Number(m.outstanding || 0) > 0).length;
        outstandingSub.textContent = `${membersBehind} member${membersBehind === 1 ? "" : "s"} behind`;
      }

      /* Tell the host page which deduction month is selected (e.g. the
         Auditor's Department Compliance card follows it). The month value is
         either "YYYY-MM" or the covered month date "YYYY-MM-01". */
      document.dispatchEvent(new CustomEvent("ovd:assessment", {
        detail: {
          assessment_id: data.assessment ? data.assessment.assessment_id : null,
          month: data.assessment ? data.assessment.month : null,
          month_label: data.assessment ? data.assessment.month_label : "",
          status: data.assessment ? data.assessment.status : null,
        },
      }));

      if (!data.assessment) {
        root.innerHTML = `
          <div class="ovd-card ovd-panel">
            <div class="ovd-panel-head">
              <div>
                <h3 class="ovd-panel-title"><span class="ovd-panel-ico"><i class="fas fa-chart-line"></i></span>Overview</h3>
                <p class="ovd-panel-sub">${ROLE_SUBTITLE[state.role] || ""}</p>
              </div>
            </div>
            <div class="ovd-empty" style="padding:44px 20px; text-align:center; color:#8a949e;">
              <i class="fas fa-inbox" style="font-size:1.6rem; display:block; margin-bottom:10px; color:#c3ccc4;"></i>
              No monthly assessment yet.<br>
              <span class="ovd-tiny">The President creates it in the Monthly Deduction module — the overview appears here as soon as one exists.</span>
            </div>
          </div>`;
        return;
      }

      state.assessmentId = data.assessment.assessment_id;
      state.viewOnly = data.assessment.status === "final_approved";
      state.roster = null;
      if (state.role === "treasurer") {
        try {
          const roster = await fetchJson(`/api/treasurer/deductions/members/${data.assessment.assessment_id}`);
          if (roster.ok) { state.roster = roster; state.recordable = !!roster.recordable; }
        } catch (e) { console.error(e); }
      }

      render();
    } catch (e) {
      console.error("Overview load failed:", e);
      root.innerHTML = `<div class="ovd-card ovd-panel"><div class="ovd-error"><i class="fas fa-triangle-exclamation" style="margin-right:8px;"></i>Overview error: ${esc(String((e && e.message) || e))}</div></div>`;
    } finally {
      state.loading = false;
    }
  }

  /* ============================== render ============================== */
  function render() {
    const root = document.getElementById("ovd-root");
    if (!root || !state.view) return;
    const data = state.view;

    root.innerHTML = toolbarHtml(data) + bodyHtml(data);
    if (window.nxFundFlow && document.getElementById("fundFlow")) {
      window.nxFundFlow.load();
    }
    bindPeriodPicker(data);
    collapseEmptyGroups();
  }

  /* Single month-year popup picker (all roles): one button showing the
     current period; the popup lists every assessment month in a year grid. */
  function bindPeriodPicker(data) {
    const btn = document.getElementById("ovd-period-btn");
    const pop = document.getElementById("ovd-period-pop");
    const grid = document.getElementById("ovd-month-grid");
    const yearLabel = document.getElementById("ovd-year-label");
    const prev = document.getElementById("ovd-year-prev");
    const next = document.getElementById("ovd-year-next");
    if (!btn || !pop || !grid || !yearLabel || !prev || !next) return;
    const list = data.assessments || [];
    const cur = data.assessment || {};
    const keyOf = (x) => String(x.month || "").slice(0, 7);
    const yearOf = (x) => String(x.month || "").slice(0, 4);
    const years = [...new Set(list.map(yearOf).filter((y) => /^\d{4}$/.test(y)))].sort();
    let year = (/^\d{4}$/.test(yearOf(cur)) && years.includes(yearOf(cur)))
      ? yearOf(cur)
      : (years[years.length - 1] || String(new Date().getFullYear()));
    const ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const isApproved = (x) => x.status === "final_approved";
    const close = () => { pop.style.display = "none"; document.removeEventListener("click", outside); };
    const outside = (e) => { if (!pop.contains(e.target) && !btn.contains(e.target)) close(); };
    const paint = () => {
      yearLabel.textContent = year;
      prev.disabled = !years.length || year <= years[0];
      next.disabled = !years.length || year >= years[years.length - 1];
      grid.innerHTML = ABBR.map((m, i) => {
        const hit = list.find((x) => keyOf(x) === `${year}-${String(i + 1).padStart(2, "0")}`);
        if (!hit) return `<button type="button" class="ovd-mbtn" disabled>${m}</button>`;
        const cls = hit.assessment_id === cur.assessment_id ? " current" : "";
        return `<button type="button" class="ovd-mbtn${cls}" data-aid="${hit.assessment_id}">${m}</button>`;
      }).join("");
      grid.querySelectorAll("[data-aid]").forEach((b) =>
        b.addEventListener("click", () => { close(); load(Number(b.dataset.aid)); })
      );
    };
    btn.onclick = (e) => {
      e.stopPropagation();
      if (pop.style.display === "none") { paint(); pop.style.display = "block"; document.addEventListener("click", outside); }
      else close();
    };
    prev.onclick = (e) => { e.stopPropagation(); const i = years.indexOf(year); if (i > 0) { year = years[i - 1]; paint(); } };
    next.onclick = (e) => { e.stopPropagation(); const i = years.indexOf(year); if (i >= 0 && i < years.length - 1) { year = years[i + 1]; paint(); } };
    if (!window.__ovdPickerEsc) {
      window.__ovdPickerEsc = true;
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") { const p = document.getElementById("ovd-period-pop"); if (p) p.style.display = "none"; }
      });
    }
  }

  function toolbarHtml(data) {
    const a = data.assessment;

    // Record Monthly Deductions lives in its own module — the toolbar keeps
    // only the title and the single Month picker.
    const treasurerCta = "";

    return `
    <div class="ovd-card ovd-toolbar ovd-treasurer-toolbar">
      <div>
        <h2 class="ovd-toolbar-title">
          Monthly Deduction Overview
        </h2>
      </div>
      <div class="ovd-toolbar-spacer"></div>
      <div class="ovd-period-group">
        <span class="ovd-toolbar-label">Month</span>
        <div class="ovd-picker-wrap">
          <button type="button" id="ovd-period-btn" class="ovd-select ovd-picker-btn"><span>${esc(a.month_label || "Select period")}</span><i class="fas fa-chevron-down" style="font-size:0.7rem;"></i></button>
          <div id="ovd-period-pop" class="ovd-picker-pop" style="display:none;">
            <div class="ovd-picker-year">
              <button type="button" class="ovd-picker-nav" id="ovd-year-prev">&lsaquo;</button>
              <strong id="ovd-year-label"></strong>
              <button type="button" class="ovd-picker-nav" id="ovd-year-next">&rsaquo;</button>
            </div>
            <div class="ovd-picker-grid" id="ovd-month-grid"></div>
          </div>
        </div>
      </div>
      ${treasurerCta}
    </div>`;
  }

  function bodyHtml(data) {
    if (state.role === "treasurer") return treasurerBody(data);
    if (state.role === "auditor") return auditorBody(data);
    return presidentBody(data);
  }

  /* ---------- shared visual fragments ---------- */
  function deptCompliancePanel(data, title, subtitle, icon, navTarget) {
    const rows = (data.departments || []).map((d) => `
      <div class="ovd-dept-row">
        <span class="ovd-dept-name" title="${esc(d.department)}">${esc(d.department)}</span>
        ${rateBar(d.rate)}
        <span class="ovd-dept-side">${statusChipFromRate(d.rate)}</span>
      </div>`).join("");
    return panel(icon, title,
      subtitle,
      `<div class="ovd-dept-list">${rows || `<div class="ovd-info" style="margin:4px 0 0;">No department records for this month yet.</div>`}</div>` +
      (navTarget ? `<button type="button" class="ovd-btn ovd-btn-lg ovd-btn-primary" style="width:100%;margin-top:16px;" onclick="setActiveModule('${navTarget}')">Open Dues Compliance &rarr;</button>` : ""));
  }

  /* ---------- role summary cards (tinted icon + value + sub) ---------- */
  function roleCard(icon, tint, label, value, sub) {
    return `<div class="ovd-card" style="display:flex;gap:14px;align-items:center;padding:16px 18px;margin-bottom:0;">
      <span style="width:42px;height:42px;border-radius:50%;background:${tint};display:flex;align-items:center;justify-content:center;font-size:0.95rem;flex:none;">
        <i class="fas ${icon}" style="color:#fff;"></i></span>
      <div style="min-width:0;">
        <div style="font-size:0.66rem;font-weight:800;letter-spacing:0.5px;text-transform:uppercase;color:#6b7280;">${label}</div>
        <div style="font-size:1.3rem;font-weight:800;color:#1f2a24;line-height:1.2;">${value}</div>
        <div style="font-size:0.76rem;color:#8a949e;">${sub}</div>
      </div>
    </div>`;
  }
  function roleCardsRow(cards) {
    return `<div class="ovd-kpis" style="margin-bottom:14px;">${cards.join("")}</div>`;
  }

  /* ---------- Monthly Deduction card (status chip + dues stats + rate + CTA) ---------- */
  function monthlyDeductionCard(data, opts) {
    const t = data.totals || {};
    const a = data.assessment || {};
    const rate = Math.min(100, t.rate || 0);
    const stat = (l, v, tone) => `<div>
        <div style="font-size:0.66rem;font-weight:800;letter-spacing:0.5px;text-transform:uppercase;color:#8a949e;">${l}</div>
        <div style="font-size:1.15rem;font-weight:800;color:${tone === "neg" ? "#b93a3a" : tone === "pos" ? "#1e8f4e" : "#1f2a24"};">${v}</div>
      </div>`;
    let stats;
    if (opts.stats === "payments") {
      stats =
        stat("Records Submitted", memberCount(t)) +
        stat("Fully Paid", t.full || 0, "pos") +
        stat("Partial", t.partial || 0) +
        stat("Not Paid", (t.zero || 0) + (t.pending || 0), (t.zero || 0) + (t.pending || 0) ? "neg" : "");
    } else {
      stats =
        stat("Expected", PESO(t.expected || 0)) +
        stat("Collected", PESO(t.collected || 0), "pos") +
        stat("Outstanding", PESO(t.outstanding || 0), (t.outstanding || 0) > 0 ? "neg" : "");
    }
    const rateBar = opts.rateBar === false ? "" : `
      <div style="margin:16px 0 0;">
        <div style="display:flex;justify-content:space-between;font-size:0.72rem;font-weight:700;color:#6b7280;margin-bottom:5px;">
          <span>Collection Rate</span><span>${rate.toFixed(1)}% · ${rateName(rate)}</span>
        </div>
        <div style="height:9px;background:#eef1ee;border-radius:999px;overflow:hidden;">
          <div style="width:${rate}%;height:100%;background:${rateColor(rate)};border-radius:999px;"></div>
        </div>
      </div>`;
    const cta = opts.cta
      ? `<button type="button" class="ovd-btn ovd-btn-lg ovd-btn-primary" style="width:100%;margin-top:14px;" onclick="setActiveModule('${opts.cta.target}')">${opts.cta.label} &rarr;</button>`
      : "";
    return `<div class="ovd-card" style="margin-bottom:0;padding:22px 24px;">
      <div class="ovd-panel-head">
        <div>
          <h3 class="ovd-panel-title"><span class="ovd-panel-ico"><i class="fas fa-calendar-check"></i></span>Monthly Deduction</h3>
          <p class="ovd-panel-sub">${esc(a.month_label || "")}</p>
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:9px;background:#f2f7f2;border-radius:9px;padding:10px 14px;margin:6px 0 18px;">
        <span style="font-size:0.78rem;font-weight:600;color:#5f6b64;">Status:</span> ${statusChip(a.status)}
      </div>
      <div style="display:grid;grid-template-columns:repeat(${opts.stats === "payments" ? 4 : 3},1fr);gap:16px;">${stats}</div>
      ${rateBar}
      ${opts.extraHtml || ""}
      ${cta}
    </div>`;
  }

  /* ---------- PRESIDENT — monitor (treasurer + auditor views, view-only) ----- */
  function presidentBody(data) {
    return `<div class="ovd-row ovd-3">`
      + deductionVizPanel(data) +
      allocationPanel(data) +
      deptCompliancePanel(data, "Department Compliance", "Collection rate per department.", null, null) +
      `</div>`;
  }

  /* ---------- shared deduction viz panel (treasurer + auditor) ----------
     Member collection donut, Expected/Collected/Unpaid strip, and the
     per-allocation breakdown table — identical figures on both dashboards. */
  function deductionVizPanel(data) {
    const t = data.totals || {};
    const a = data.assessment || {};

    /* --- member collection donut --- */
    const full = t.full || 0, partial = t.partial || 0;
    const notpaid = (t.zero || 0) + (t.pending || 0);
    const totalM = full + partial + notpaid;
    const share = (n) => (totalM ? Math.round((n / totalM) * 100) : 0);
    const C_PAID = "#1e8f4e", C_PART = "#d99a26", C_UNPAID = "#b93a3a";
    let ringBg = "#EDF1EE", acc = 0;
    if (totalM > 0) {
      const segs = [
        [C_PAID, (full / totalM) * 100],
        [C_PART, (partial / totalM) * 100],
        [C_UNPAID, (notpaid / totalM) * 100],
      ];
      ringBg = "conic-gradient(" + segs.map((s) => {
        const stop = `${s[0]} ${acc.toFixed(2)}% ${(acc + s[1]).toFixed(2)}%`;
        acc += s[1];
        return stop;
      }).join(", ") + ")";
    }
    const legRow = (color, label, n) =>
      `<div class="ovd-legrow"><span class="ovd-dot" style="background:${color};"></span>${label}<strong>${n} (${share(n)}%)</strong></div>`;

    /* --- strip breakdown: per-allocation expected / collected / unpaid ---
       Rows reconcile with the strip: prior-balance collections get their
       own row, and pre-existing arrears (inside the outstanding total but
       outside this month's assessment) land on an arrears row. */
    const bdSource = (data.breakdown || []).filter((b) => b && (b.expected > 0 || b.collected > 0 || b.per_member > 0));
    const bdRows = [];
    bdSource.forEach((b) => {
      if (b.label === "Prior Balance Collected") {
        bdRows.push({ label: "Prior Balance Collected", expected: null, collected: Number(b.collected) || 0, unpaid: 0 });
        return;
      }
      if (b.label === "Other" && Array.isArray(b.sub_items) && b.sub_items.length) {
        b.sub_items.forEach((s) => bdRows.push({ label: s.label || "Other", expected: Number(s.expected) || 0, collected: Number(s.collected) || 0, unpaid: null }));
      } else if (b.label === "Other") {
        bdRows.push({ label: "Other Dues / Fund Share", expected: Number(b.expected) || 0, collected: Number(b.collected) || 0, unpaid: null });
      } else {
        bdRows.push({ label: b.label, expected: Number(b.expected) || 0, collected: Number(b.collected) || 0, unpaid: null });
      }
    });
    bdRows.forEach((r) => { if (r.unpaid == null) r.unpaid = Math.max(0, (r.expected || 0) - (r.collected || 0)); });
    const arrears = Math.max(0, (Number(t.outstanding) || 0) - bdRows.reduce((s, r) => s + (r.unpaid || 0), 0));
    if (arrears > 0.005) bdRows.push({ label: "Previous Balance", expected: null, collected: null, unpaid: arrears });
    const bdCell = (v, cls) => v == null
      ? `<td class="num">—</td>`
      : `<td class="num${cls ? " " + cls : ""}">${PESO(v)}</td>`;
    const bdTable = bdRows.length ? `
      <div class="ovd-bdtable-wrap">
        <table class="ovd-bdtable">
          <thead><tr><th>Allocation</th><th class="num">Expected</th><th class="num">Collected</th><th class="num">Unpaid</th></tr></thead>
          <tbody>
            ${bdRows.map((r) =>
              `<tr><td>${esc(r.label)}</td>${bdCell(r.expected, "")}${bdCell(r.collected, "ovd-pos")}${bdCell(r.unpaid, "ovd-neg")}</tr>`
            ).join("")}
          </tbody>
        </table>
      </div>` : "";

    const monthBadge = `<span class="ovd-pill">${esc(a.month_label || "No Period")}</span>`;
    return `
      <div class="ovd-card ovd-panel">
        <div class="ovd-viz-head">
          <div>
            <h3 class="ovd-viz-title">Monthly Deduction Overview</h3>
            <p class="ovd-viz-sub">Record monthly member deductions &amp; collection progress</p>
          </div>
          <div class="ovd-viz-badges">${monthBadge}</div>
        </div>
        <div class="ovd-donutrow">
          <div class="ovd-ring" style="background:${ringBg};">
            <div class="ovd-ring-hole"><strong>${totalM}</strong><small>MEMBERS</small></div>
          </div>
          <div class="ovd-leglist">
            ${legRow(C_PAID, "Paid", full)}
            ${legRow(C_PART, "Partial", partial)}
            ${legRow(C_UNPAID, "UNPAID", notpaid)}
          </div>
        </div>
        <div class="ovd-strip3">
          <div class="ovd-strip3-seg"><div class="ovd-strip3-label">Expected Collections</div><div class="ovd-strip3-value">${PESO(t.expected || 0)}</div></div>
          <div class="ovd-strip3-seg"><div class="ovd-strip3-label">Collected Dues</div><div class="ovd-strip3-value ovd-pos">${PESO(t.collected || 0)}</div></div>
          <div class="ovd-strip3-seg"><div class="ovd-strip3-label">Unpaid Dues</div><div class="ovd-strip3-value ovd-neg">${PESO(t.outstanding || 0)}</div></div>
        </div>
        ${bdTable}
      </div>`;
  }

  /* ---------- shared per-member allocation panel (treasurer + president) --
     Every allocation row carries its real name; rows add up to the badge. */
  function allocationPanel(data) {
    const items = (data.breakdown || []).filter((b) => b && (b.expected > 0 || b.collected > 0 || b.per_member > 0));
    // Expand the aggregated "Other" row into its real sub-items so every
    // legend row carries its actual name (e.g. Token Incentive).
    const rows = [];
    items.forEach((b) => {
      if (b.label === "Prior Balance Collected") return; // fund-level, not a per-member allocation
      if (b.label === "Other" && Array.isArray(b.sub_items) && b.sub_items.length) {
        b.sub_items.forEach((s) => rows.push({ label: s.label || "Other", per_member: Number(s.per_member) || 0, other: true }));
      } else if (b.label === "Other") {
        rows.push({ label: "Other Dues / Fund Share", per_member: Number(b.per_member) || 0, other: true });
      } else {
        rows.push({ label: b.label, per_member: Number(b.per_member) || 0, other: false });
      }
    });
    const perMemberTotal = rows.reduce((s, r) => s + (Number(r.per_member) || 0), 0);
    const ALLOC_COLORS = ["#1e8f4e", "#2f9e5f", "#5aad77", "#8cc7a0", "#166a3b", "#6aa97c"];
    const OTHER_COLORS = ["#94a3b8", "#aebbca", "#c6d2de"];
    let otherIdx = 0;
    rows.forEach((r, i) => {
      r.color = r.other ? OTHER_COLORS[(otherIdx++) % OTHER_COLORS.length] : ALLOC_COLORS[i % ALLOC_COLORS.length];
    });
    let allocBg = "#EDF1EE";
    if (perMemberTotal > 0.005 && rows.length) {
      let aAcc = 0;
      allocBg = "conic-gradient(" + rows.map((r) => {
        const pctShare = Math.min(100, Math.max(0, ((Number(r.per_member) || 0) / perMemberTotal) * 100));
        const stop = `${r.color} ${aAcc.toFixed(2)}% ${(aAcc + pctShare).toFixed(2)}%`;
        aAcc += pctShare;
        return stop;
      }).join(", ") + ")";
    }
    const allocRows = rows.length
      ? rows.map((r) =>
          `<div class="ovd-legrow"><span class="ovd-dot" style="background:${r.color};"></span>${esc(r.label)}<strong>${PESO(r.per_member || 0)}</strong></div>`
        ).join("")
      : `<div class="ovd-legrow"><span class="ovd-dot" style="background:#94a3b8;"></span>Other Dues / Fund Share<strong>${PESO(0)}</strong></div>`;
    return `
      <div class="ovd-card ovd-panel">
        <div class="ovd-viz-head">
          <div>
            <h3 class="ovd-viz-title">Deduction Allocation Breakdown</h3>
            <p class="ovd-viz-sub">Allocation breakdown per active member</p>
          </div>
          <div class="ovd-viz-badges"><span class="ovd-pill">${PESO(perMemberTotal)} / Member</span></div>
        </div>
        <div class="ovd-donutrow ovd-donutstack">
          <div class="ovd-ring" style="background:${allocBg};">
            <div class="ovd-ring-hole"><strong class="ovd-perm">${PESO(perMemberTotal)}</strong><small>PER MEMBER</small></div>
          </div>
          <div class="ovd-leglist">
            ${allocRows}
          </div>
        </div>
      </div>`;
  }

  /* ---------- TREASURER — record (donut visualizations + money strip) ---------- */
  function treasurerBody(data) {
    const roster = state.roster;
    const allRecorded = !!(roster && roster.members.length && roster.members.every((m) => m.recorded_actual != null));
    const submitReady = state.recordable && allRecorded
      ? '<button type="button" class="ovd-btn ovd-btn-lg ovd-btn-primary" style="width:100%;margin-top:20px;" onclick="ovdSubmitAudit()">Submit for Audit</button>'
      : "";

    return `
    <div class="ovd-viz">`
      + deductionVizPanel(data) +
      allocationPanel(data) +
      `</div>${submitReady}`;
  }

  /* One-click submit: every roster member's recorded deduction, sent for audit. */
  window.ovdSubmitAudit = async function () {
    const roster = state.roster;
    if (!roster || !roster.members.length) return;
    const members = roster.members.map((m) => ({
      member_id: m.member_id,
      actual_deduction: m.recorded_actual == null ? 0 : Math.max(0, Number(m.recorded_actual) || 0),
    }));
    if (window.SimpleModal && SimpleModal.confirm) {
      const ok = await SimpleModal.confirm("Submit all recorded deductions for this month to the Auditor for verification?", { title: "Submit for Audit", okText: "Submit" });
      if (!ok) return;
    }
    try {
      const data = await fetchJson("/api/treasurer/deductions/record/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrfToken() },
        body: JSON.stringify({ assessment_id: state.assessmentId, members, submit: true }),
      });
      if (!data.ok) { toast(data.error || "Failed to submit.", true); return; }
      toast(data.message || "Submitted for audit.", false);
      load(state.assessmentId);
    } catch (e) {
      console.error(e);
      toast("Failed to submit deductions.", true);
    }
  };

  /* ---------- AUDITOR — verify (two-column: deduction viz + compliance) ---------- */
  function auditorBody(data) {
    return `<div class="ovd-row ovd-11">` +
      deductionVizPanel(data) +
      deptCompliancePanel(data, "Department Compliance", "Collection rate per department.", null, "compliance-heatmap") +
      `</div>`;
  }

  /* Leave the read-only approved month and return to the default view. */
  window.ovdBackToCurrent = function () { load(null); };

  /* ============================== boot ============================== */
  document.addEventListener("DOMContentLoaded", () => {
    ensureStyles();
    state.role = detectRole();
    load();
  });
  window.ovdRefresh = load;
})();
