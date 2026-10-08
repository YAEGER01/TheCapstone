/* Monthly Deductions workspace (Treasurer)
 * --------------------------------------------------------------------------
 * Fully rendered into #mdp-root with mdp-* classes scoped under it, so host
 * page styles cannot interfere. Layout:
 *
 *   Toolbar   — month picker, workflow status chip, single refresh
 *   Tabs      — Active Entry | View Months (approved, read-only)
 *   Recording — compact status card (donut + 3 statuses + money line),
 *               sticky summary bar, search + filter chips, member table with
 *               status badges and expandable allocation breakdowns
 *
 * Member payment status has exactly three buckets: Paid / Partial / Not Paid.
 * Mid-year joiners also show a join-status pill (New member /
 * joined mid-year) under the member name on the recording roster.
 * Prior outstanding and catch-up are one list: the Unpaid Balance column
 * shows the total outstanding; its popup breaks the total down per month
 * with checkboxes (oldest pre-ticked), and months carrying aid split into
 * Due / Aid sub-rows so the treasurer can chase dues only. "Total Collected" IS the member's real
 * payroll deduction — the ticked months are settled from it FIRST (oldest
 * first), so a dues-only collection clears the oldest unsettled month and
 * this month carries over; the remainder funds this month's dues. Of that
 * remainder, the Monthly Due item is funded LAST — a shortfall shrinks the
 * due (auto carry-over) instead of reducing the medical aid or other items.
 *
 * APIs:
 *   GET  /api/treasurer/deductions/overview/
 *   GET  /api/treasurer/deductions/members/<assessmentId>/
 *   GET  /api/auditor/deductions/heatmap/?assessment_id=<id>   (status card)
 *   POST /api/treasurer/deductions/record/
 *   POST /api/treasurer/deductions/catch-up/
 */
console.log("=== MONTHLY DEDUCTION JS LOADED - VERSION 20261004mdp97 ===");
(function () {
  "use strict";

  /* ================= injected styles (host-page-proof) ================== */
  const CSS = `
  #mdp-root { display:block; font-family:inherit; color:#1f2937; }
  #mdp-root *, #mdp-root *::before, #mdp-root *::after { box-sizing:border-box; }
  #mdp-root .mdp-card {
    background:#fff; border:1px solid #e6ebe7; border-radius:14px;
    box-shadow:0 1px 2px rgba(16,24,40,0.04);
  }
  #mdp-root #mdp-breakdown-summary { width:100%; margin:0 0 32px; }
  /* ---------- side-by-side top cards: Assessment Breakdown + Attachments.
     Each keeps its own show/hide; a hidden card leaves the flex row so the
     visible one fills the width. Wraps (stacks) on narrow screens. */
  #mdp-root .mdp-top-cards { display:flex; gap:14px; align-items:stretch; flex-wrap:wrap; }
  #mdp-root .mdp-top-cards:has(> :not(.mdp-hidden)) { margin-bottom:14px; }
  #mdp-root .mdp-top-cards > #mdp-breakdown-summary { flex:3 1 320px; min-width:0; width:auto; margin:0; }
  #mdp-root .mdp-top-cards > #mdp-breakdown-summary > div { height:100%; }
  #mdp-root .mdp-top-cards > #mdp-attachments { flex:2 1 260px; min-width:0; margin:0; }
  #mdp-root .mdp-top-cards > #mdp-attachments .mdp-attach-card { height:100%; margin-bottom:0; }

  /* ---------- toolbar ---------- */
  #mdp-root .mdp-toolbar {
    display:flex; align-items:flex-start; justify-content:space-between;
    gap:14px; flex-wrap:wrap; padding:16px 20px; margin-bottom:14px;
  }
  #mdp-root .mdp-title {
    display:flex; align-items:center; gap:10px; margin:0;
    font-size:1.02rem; font-weight:800; color:#111827;
  }
  #mdp-root .mdp-title-ico {
    width:34px; height:34px; border-radius:10px; flex:0 0 34px;
    display:inline-flex; align-items:center; justify-content:center;
    background:#e8f5e9; color:#2e7d32; font-size:0.9rem;
  }
  #mdp-root .mdp-sub { margin:3px 0 0; font-size:0.78rem; color:#6b7280; }
  #mdp-root .mdp-toolbar-right { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
  #mdp-root .mdp-select {
    border:1px solid #d6ddd7; border-radius:9px; background:#fff;
    padding:7px 11px; font-size:0.8rem; color:#1f2937; font-family:inherit; cursor:pointer; max-width:340px;
  }
  #mdp-root .mdp-select:focus { outline:none; border-color:#2e7d32; box-shadow:0 0 0 3px rgba(46,125,50,0.12); }
  #mdp-root .mdp-btn {
    display:inline-flex; align-items:center; gap:7px; border:1px solid #d6ddd7;
    background:#fff; color:#374151; border-radius:9px; padding:7px 14px;
    font-size:0.8rem; font-weight:600; cursor:pointer; font-family:inherit; white-space:nowrap;
  }
  #mdp-root .mdp-btn:hover { background:#f3f6f3; }
  #mdp-root .mdp-btn-primary { background:#1b5e20; border-color:#1b5e20; color:#fff; }
  #mdp-root .mdp-btn-primary:hover { background:#256b29; }

  /* ---------- months popup picker (view-only approved months) ---------- */
  #mdp-root .mdp-picker-wrap { position:relative; }
  #mdp-root .mdp-picker-btn { display:inline-flex; align-items:center; gap:10px; min-width:170px; justify-content:space-between; }
  #mdp-root .mdp-picker-btn:disabled { opacity:0.6; cursor:default; }
  #mdp-root .mdp-picker-pop {
    position:absolute; top:calc(100% + 8px); right:0; width:302px; z-index:60;
    background:#fff; border:1px solid #d6ddd7; border-radius:12px;
    box-shadow:0 12px 32px rgba(0,0,0,0.12); padding:14px;
  }
  #mdp-root .mdp-picker-year { display:flex; align-items:center; justify-content:space-between; padding:2px 4px 10px; margin-bottom:10px; border-bottom:1px solid #eef2f7; }
  #mdp-root .mdp-picker-year strong { font-size:0.9rem; color:#1f2937; }
  #mdp-root .mdp-picker-nav { border:none; background:#f1f5f9; width:28px; height:28px; border-radius:8px; cursor:pointer; color:#475569; font-size:1.1rem; line-height:1; }
  #mdp-root .mdp-picker-nav:hover:not(:disabled) { background:#e2e8f0; }
  #mdp-root .mdp-picker-nav:disabled { opacity:0.35; cursor:default; }
  #mdp-root .mdp-picker-grid { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px; }
  #mdp-root .mdp-mbtn {
    border:1px solid #e2e8f0; background:#f8fafc; border-radius:8px; padding:9px 4px;
    font-size:0.8rem; font-weight:600; color:#334155; cursor:pointer; font-family:inherit;
  }
  #mdp-root .mdp-mbtn:hover:not(:disabled) { border-color:#1e8f4e; background:#e7f6ec; }
  #mdp-root .mdp-mbtn.current { background:#1e8f4e; border-color:#1e8f4e; color:#fff; }
  #mdp-root .mdp-mbtn:disabled { background:transparent; border-color:transparent; color:#cbd5e1; cursor:default; }
  #mdp-root .mdp-chip {
    display:inline-flex; align-items:center; gap:5px; padding:3px 11px;
    border-radius:999px; font-size:0.73rem; font-weight:700; white-space:nowrap;
  }

  /* ---------- tabs ---------- */
  #mdp-root .mdp-tabs { display:flex; gap:6px; margin-bottom:14px; border-bottom:2px solid #e6ebe7; }
  #mdp-root .mdp-tab {
    display:inline-flex; align-items:center; gap:7px; background:none; border:none;
    border-bottom:2.5px solid transparent; margin-bottom:-2px; padding:9px 16px;
    font-size:0.84rem; font-weight:700; color:#6b7280; cursor:pointer; font-family:inherit;
  }
  #mdp-root .mdp-tab:hover { color:#1b5e20; }
  #mdp-root .mdp-tab.active { color:#1b5e20; border-bottom-color:#1b5e20; }

  /* ---------- compact status card ---------- */
  #mdp-root .mdp-statuscard { padding:18px 20px; margin-bottom:14px; }
  #mdp-root .mdp-overview-grid { display:grid; grid-template-columns:minmax(0, 7fr) minmax(320px, 3fr); gap:14px; align-items:stretch; margin-bottom:14px; }
  #mdp-root .mdp-overview-grid > .mdp-card { margin:0; height:100%; }
  #mdp-root .mdp-statuscard-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:18px; }
  #mdp-root .mdp-statuscard-kicker { color:#728078; font-size:0.66rem; font-weight:800; letter-spacing:0.08em; text-transform:uppercase; }
  #mdp-root .mdp-statuscard-month { margin-top:3px; color:#17231b; font-size:0.94rem; font-weight:800; }
  #mdp-root .mdp-statuscard-note { color:#8a949e; font-size:0.72rem; text-align:right; }
  #mdp-root .mdp-statuscard-grid {
    display:grid; grid-template-columns:1fr; gap:0; align-items:stretch;
  }
  #mdp-root .mdp-statuscard-main { display:flex; align-items:center; justify-content:center; gap:48px; min-height:190px; padding:8px 20px; }
  #mdp-root .mdp-statuscard-left { display:flex; align-items:center; justify-content:center; min-width:188px; min-height:168px; }
  #mdp-root .mdp-donut {
    width:166px; height:166px; border-radius:50%; position:relative; flex:0 0 auto;
    display:flex; align-items:center; justify-content:center;
  }
  #mdp-root .mdp-donut-hole {
    width:108px; height:108px; border-radius:50%; background:#fff;
    display:flex; flex-direction:column; align-items:center; justify-content:center;
  }
  #mdp-root .mdp-donut-hole strong { font-size:1.55rem; color:#101828; line-height:1.05; }
  #mdp-root .mdp-donut-hole small { font-size:0.74rem; color:#8a949e; }
  #mdp-root .mdp-legend { display:grid; grid-template-columns:repeat(3, minmax(130px, 1fr)); gap:12px; max-width:600px; width:100%; }
  #mdp-root .mdp-legend-row { display:grid; grid-template-columns:10px 1fr auto; grid-template-rows:auto auto; align-items:center; column-gap:9px; padding:15px 14px; border:1px solid #edf1ed; border-radius:10px; background:#fbfdfb; font-size:0.86rem; color:#374151; }
  #mdp-root .mdp-legend-dot { width:10px; height:10px; border-radius:50%; flex:0 0 10px; }
  #mdp-root .mdp-legend-row .mdp-legend-label { grid-column:2; grid-row:1; }
  #mdp-root .mdp-legend-row strong { grid-column:3; grid-row:1; font-variant-numeric:tabular-nums; }
  #mdp-root .mdp-legend-row small { grid-column:2 / 4; grid-row:2; color:#8a949e; font-size:0.74rem; margin-top:5px; }
  #mdp-root .mdp-moneyline {
    display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); align-content:center; gap:20px;
    border-top:1px solid #eef1ee; border-left:0; margin:16px 0 0; padding:16px 4px 0; grid-column:1;
  }
  #mdp-root .mdp-money-item { display:grid; grid-template-columns:auto 1fr; align-items:baseline; column-gap:8px; row-gap:2px; font-size:0.82rem; color:#475569; }
  #mdp-root .mdp-money-item strong { font-size:1.02rem; color:#101828; font-variant-numeric:tabular-nums; }
  #mdp-root .mdp-money-item .mdp-pos { color:#2e7d32; }
  #mdp-root .mdp-money-item .mdp-neg { color:#c62828; }
  #mdp-root .mdp-money-note { grid-column:1 / -1; font-size:0.72rem; color:#8a949e; }

  /* ---------- meta strip ---------- */
  #mdp-root .mdp-meta {
    display:flex; gap:16px; align-items:center; flex-wrap:wrap;
    padding:10px 20px; margin-bottom:14px; font-size:0.8rem; color:#475569;
  }
  #mdp-root .mdp-summary-card { display:flex; flex-direction:column; padding:0; margin-bottom:14px; overflow:hidden; }
  #mdp-root .mdp-summary-card .mdp-meta { margin:0; border-bottom:1px solid #eef1ee; }
  #mdp-root .mdp-summary-card .mdp-sticky { position:static; flex:1; align-content:start; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:0; margin:0; border:0; border-radius:0; box-shadow:none; padding:18px 14px; }
  #mdp-root .mdp-summary-card .mdp-sticky-seg { display:flex; flex-direction:column; justify-content:center; min-height:82px; text-align:center; }
  #mdp-root .mdp-summary-card .mdp-sticky-seg:nth-child(odd) { border-right:1px solid #e6ebe7; }
  #mdp-root .mdp-summary-card .mdp-sticky-seg:nth-child(-n+2) { border-bottom:1px solid #e6ebe7; }
  #mdp-root .mdp-summary-card .mdp-sticky-seg + .mdp-sticky-seg::before { display:none; }
  #mdp-root .mdp-meta strong { color:#101828; }
  #mdp-root .mdp-meta .mdp-remark { font-size:0.74rem; color:#b45309; }

  /* ---------- sticky summary ---------- */
  #mdp-root .mdp-sticky {
    position:sticky; top:0; z-index:8;
    display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr));
    background:#ffffff; border:1px solid #e6ebe7; border-radius:12px;
    box-shadow:0 4px 14px rgba(16,24,40,0.08); padding:10px 8px; margin-bottom:12px;
  }
  #mdp-root .mdp-sticky-seg { position:relative; text-align:center; padding:2px 10px; }
  #mdp-root .mdp-sticky-seg + .mdp-sticky-seg::before {
    content:""; position:absolute; left:0; top:15%; bottom:15%; width:1px; background:#e6ebe7;
  }
  #mdp-root .mdp-sticky-label {
    font-size:0.62rem; font-weight:700; letter-spacing:0.6px; text-transform:uppercase; color:#6b7280;
  }
  #mdp-root .mdp-sticky-value { font-size:1.05rem; font-weight:800; color:#101828; font-variant-numeric:tabular-nums; }
  #mdp-root .mdp-sticky-value.mdp-neg { color:#c62828; }
  #mdp-root .mdp-sticky-value.mdp-pos { color:#2e7d32; }

  /* ---------- controls ---------- */
  #mdp-root .mdp-controls {
    display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:12px;
  }
  #mdp-root .mdp-search { position:relative; flex:1; min-width:210px; max-width:340px; }
  #mdp-root .mdp-search i {
    position:absolute; left:11px; top:50%; transform:translateY(-50%);
    color:#9aa4ad; font-size:0.78rem; pointer-events:none;
  }
  #mdp-root .mdp-search input {
    width:100%; border:1px solid #d6ddd7; border-radius:9px; background:#fff;
    padding:8px 12px 8px 32px; font-size:0.8rem; color:#1f2937; font-family:inherit;
  }
  #mdp-root .mdp-search input:focus { outline:none; border-color:#2e7d32; box-shadow:0 0 0 3px rgba(46,125,50,0.12); }
  #mdp-root .mdp-filterchips { display:flex; gap:6px; flex-wrap:wrap; }
  #mdp-root .mdp-filterchip {
    display:inline-flex; align-items:center; gap:6px; border:1px solid #d6ddd7;
    background:#fff; color:#475569; border-radius:999px; padding:6px 13px;
    font-size:0.76rem; font-weight:600; cursor:pointer; font-family:inherit;
  }
  #mdp-root .mdp-filterchip:hover { background:#f3f6f3; }
  #mdp-root .mdp-filterchip.active { background:#1b5e20; border-color:#1b5e20; color:#fff; }

  /* ---------- allocation settings card (below the workflow history) ----------
     One amount box per assessment item + Apply pushes those amounts onto
     every SELECTED (ticked, non-excluded) member row's item inputs. */
  #mdp-root #mdp-alloc-settings { margin-bottom:14px; }
  #mdp-root .mdp-alloc-card { padding:16px 20px; }
  #mdp-root .mdp-alloc-head { display:flex; align-items:flex-start; justify-content:space-between; gap:14px; flex-wrap:wrap; }
  #mdp-root .mdp-alloc-title { display:flex; align-items:center; gap:9px; margin:0; font-size:0.95rem; font-weight:800; color:#111827; }
  #mdp-root .mdp-alloc-title-ico { width:30px; height:30px; border-radius:9px; flex:0 0 30px; display:inline-flex; align-items:center; justify-content:center; background:#e8f5e9; color:#2e7d32; font-size:0.82rem; }
  #mdp-root .mdp-alloc-sub { margin:4px 0 0; font-size:0.78rem; color:#6b7280; }
  #mdp-root .mdp-alloc-sub strong { color:#1b5e20; }
  #mdp-root .mdp-alloc-actions { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
  #mdp-root .mdp-alloc-grid { display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }
  #mdp-root .mdp-alloc-field { display:flex; flex-direction:column; gap:5px; min-width:150px; flex:1 1 150px; max-width:230px; }
  #mdp-root .mdp-alloc-field label { font-size:0.72rem; font-weight:700; color:#4b5a50; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  #mdp-root .mdp-alloc-field .mdp-alloc-max { font-weight:400; color:#8a949e; }
  #mdp-root .mdp-alloc-input { border:1px solid #d6ddd7; border-radius:9px; background:#fff; padding:8px 10px; font-size:0.86rem; font-weight:700; color:#1f2937; font-family:inherit; text-align:right; font-variant-numeric:tabular-nums; width:100%; }
  #mdp-root .mdp-alloc-input:focus { outline:none; border-color:#2e7d32; box-shadow:0 0 0 3px rgba(46,125,50,0.12); }
  #mdp-root .mdp-alloc-field-lead .mdp-alloc-input { border:2px solid #1b5e20; background:#f6fdf6; }
  #mdp-root .mdp-alloc-hint { margin-top:10px; font-size:0.76rem; color:#6b7280; }
  #mdp-root .mdp-alloc-hint strong { color:#1b5e20; }

  #mdp-root .mdp-selectall {
    display:inline-flex; align-items:center; gap:7px;
    font-size:0.78rem; font-weight:600; color:#475569; cursor:pointer; white-space:nowrap;
  }
  #mdp-root .mdp-check { width:15px; height:15px; accent-color:#1b5e20; cursor:pointer; }
  #mdp-root .mdp-exclude { display:inline-flex; align-items:center; gap:5px; color:#8a949e; font-size:0.7rem; white-space:nowrap; }
  #mdp-root .mdp-exclude .mdp-check { accent-color:#c62828; }
  #mdp-root .mdp-finance-options { display:flex; flex-direction:column; gap:5px; margin-top:7px; min-width:210px; }
  #mdp-root .mdp-finance-options .mdp-tag { display:flex; align-items:center; gap:6px; padding:6px 8px; font-size:0.68rem; line-height:1.2; }
  #mdp-root .mdp-finance-options .mdp-finance-input { width:72px; margin-left:auto; padding:3px 5px; border:1px solid currentColor; border-radius:5px; background:#fff; color:inherit; font:inherit; font-weight:700; text-align:right; }
  #mdp-root .md-prior-balance-cell { display:grid; grid-template-columns:minmax(48px,1fr) 64px; align-items:center; gap:4px; width:100%; }
  #mdp-root .md-prior-balance-value { min-width:0; color:#8a6d3b; font-size:0.72rem; font-weight:700; font-variant-numeric:tabular-nums; text-align:right; white-space:nowrap; }

  /* ---------- member table ---------- */
  /* Horizontal scroll is ENABLED (was overflow-x:hidden) so EVERY Itemized
     Assessment column is reachable. With hidden, a month with more itemized
     assessments than fit the width silently clipped the extras under the
     Total column and users could not see them at all — exactly the reported
     confusion. The left (Photo / # / Member) and right (Total / Payment
     Status / TOTAL Balance) columns stay pinned via sticky positioning so
     identity and totals never scroll out of view while the itemized middle
     scrolls. */
  #mdp-root .mdp-tablewrap { max-height:56vh; overflow-y:auto; overflow-x:auto; margin-top:0; }
  #mdp-root table.mdp-table { width:100%; min-width:100%; table-layout:fixed; border-collapse:separate; border-spacing:0; font-size:0.83rem; }
  /* The roster is ONE table acting as one (single scroll, aligned rows) but
     reads as [[card1][card2][card3]]: two 14px gutter columns show the tray
     color between the cards, the table shrink-wraps its content
     (Card 2 no longer stretches to fill slack) and centers as one unit. */
  #mdp-root table#md-roster-table { width:max-content; min-width:0; max-width:none; margin:0 auto; }
  #mdp-root #mdp-roster-wrap { background:#d3dbd4; padding:12px; }
  /* Card layout (12 columns — cols 5 and 9 are 14px gutters that visually
     split the table into cards):
       Card 1 (who — dynamic):     1 select 38 | 2 exclude 70 | 3 # 38 | 4 member var
       Card 2 (collect — dynamic): 6 Total Collected 128 | 7 Itemized var | 8 Unpaid 160
       Card 3 (result — fixed):    10 Total 84 | 11 Payment 96 | 12 TOTAL Balance 120
     Card 1 pins left, Card 3 pins right, gutters pin with their neighbor
     card; only Card 2 ever slides underneath on horizontal scroll. */
  #mdp-root #md-roster-table th:nth-child(1), #mdp-root #md-roster-table td:nth-child(1) { width:38px !important; }
  #mdp-root #md-roster-table th:nth-child(2), #mdp-root #md-roster-table td:nth-child(2) { width:70px !important; }
  #mdp-root #md-roster-table th:nth-child(3), #mdp-root #md-roster-table td:nth-child(3) { width:38px !important; }
  #mdp-root #md-roster-table th:nth-child(4), #mdp-root #md-roster-table td:nth-child(4) { width:var(--md-member-col-width, 280px) !important; }
  #mdp-root #md-roster-table th:nth-child(5), #mdp-root #md-roster-table td:nth-child(5) { width:14px !important; min-width:14px !important; }
  #mdp-root #md-roster-table th:nth-child(6), #mdp-root #md-roster-table td:nth-child(6) { width:128px !important; }
  #mdp-root #md-roster-table th:nth-child(7), #mdp-root #md-roster-table td:nth-child(7) { width:var(--md-item-column-width, auto) !important; }
  #mdp-root #md-roster-table th:nth-child(8), #mdp-root #md-roster-table td:nth-child(8) { width:160px !important; }
  #mdp-root #md-roster-table th:nth-child(9), #mdp-root #md-roster-table td:nth-child(9) { width:14px !important; min-width:14px !important; }
  #mdp-root #md-roster-table th:nth-child(10), #mdp-root #md-roster-table td:nth-child(10) { width:84px !important; }
  #mdp-root #md-roster-table th:nth-child(11), #mdp-root #md-roster-table td:nth-child(11) { width:96px !important; }
  #mdp-root #md-roster-table th:nth-child(12), #mdp-root #md-roster-table td:nth-child(12) { width:120px !important; }
  /* Card band tinting: Card 1 and Card 3 read as side cards, Card 2 stays
     white as the working area. Gutters wear the tray color (opaque, so the
     sliding middle passes under them invisibly). Sticky cells need opaque
     backgrounds, so tints are applied directly (not via colgroup). */
  #mdp-root #md-roster-table th:nth-child(-n+4) { background:#e9f1ea; }
  #mdp-root #md-roster-table td:nth-child(-n+4) { background:#fafcfb; }
  #mdp-root #md-roster-table th:nth-child(n+5):nth-child(-n+5),
  #mdp-root #md-roster-table td:nth-child(n+5):nth-child(-n+5),
  #mdp-root #md-roster-table th:nth-child(n+9):nth-child(-n+9),
  #mdp-root #md-roster-table td:nth-child(n+9):nth-child(-n+9) {
    background:#d3dbd4; border:none !important; padding:0 !important;
  }
  #mdp-root #md-roster-table th:nth-child(n+10) { background:#e9f1ea; }
  #mdp-root #md-roster-table td:nth-child(n+10) { background:#f6faf7; }
  /* Card corner rounding (top row = header, bottom row = last body row). */
  #mdp-root #md-roster-table thead th:nth-child(1) { border-top-left-radius:12px; }
  #mdp-root #md-roster-table thead th:nth-child(4) { border-top-right-radius:12px; }
  #mdp-root #md-roster-table thead th:nth-child(6) { border-top-left-radius:12px; }
  #mdp-root #md-roster-table thead th:nth-child(8) { border-top-right-radius:12px; }
  #mdp-root #md-roster-table thead th:nth-child(10) { border-top-left-radius:12px; }
  #mdp-root #md-roster-table thead th:nth-child(12) { border-top-right-radius:12px; }
  #mdp-root #md-roster-table tbody tr:last-child td:nth-child(1) { border-bottom-left-radius:12px; }
  #mdp-root #md-roster-table tbody tr:last-child td:nth-child(4) { border-bottom-right-radius:12px; }
  #mdp-root #md-roster-table tbody tr:last-child td:nth-child(6) { border-bottom-left-radius:12px; }
  #mdp-root #md-roster-table tbody tr:last-child td:nth-child(8) { border-bottom-right-radius:12px; }
  #mdp-root #md-roster-table tbody tr:last-child td:nth-child(10) { border-bottom-left-radius:12px; }
  #mdp-root #md-roster-table tbody tr:last-child td:nth-child(12) { border-bottom-right-radius:12px; }
/* ---------- frozen outer cards: whoever scrolls the itemized middle,
     Card 1 (cols 1-4 + gutter 5) and Card 3 (gutter 9 + cols 10-12) stay
     pinned so identity and totals never scroll out of view ---------- */
  #mdp-root #md-roster-table th:nth-child(1), #mdp-root #md-roster-table td:nth-child(1),
  #mdp-root #md-roster-table th:nth-child(2), #mdp-root #md-roster-table td:nth-child(2),
  #mdp-root #md-roster-table th:nth-child(3), #mdp-root #md-roster-table td:nth-child(3),
  #mdp-root #md-roster-table th:nth-child(4), #mdp-root #md-roster-table td:nth-child(4),
  #mdp-root #md-roster-table th:nth-child(5), #mdp-root #md-roster-table td:nth-child(5),
  #mdp-root #md-roster-table th:nth-child(9), #mdp-root #md-roster-table td:nth-child(9),
  #mdp-root #md-roster-table th:nth-child(10), #mdp-root #md-roster-table td:nth-child(10),
  #mdp-root #md-roster-table th:nth-child(11), #mdp-root #md-roster-table td:nth-child(11),
  #mdp-root #md-roster-table th:nth-child(12), #mdp-root #md-roster-table td:nth-child(12) {
    position:sticky;
  }
  /* Stacking: pinned HEADER cells sit above pinned BODY cells. Sharing one
     z-index let later-in-DOM body cells paint over the header on vertical
     scroll, so the Card 1 / Card 3 headers "disappeared" under the rows. */
  #mdp-root #md-roster-table th:nth-child(1), #mdp-root #md-roster-table th:nth-child(2),
  #mdp-root #md-roster-table th:nth-child(3), #mdp-root #md-roster-table th:nth-child(4),
  #mdp-root #md-roster-table th:nth-child(5),
  #mdp-root #md-roster-table th:nth-child(9),
  #mdp-root #md-roster-table th:nth-child(10), #mdp-root #md-roster-table th:nth-child(11),
  #mdp-root #md-roster-table th:nth-child(12) { z-index:6; }
  #mdp-root #md-roster-table td:nth-child(1), #mdp-root #md-roster-table td:nth-child(2),
  #mdp-root #md-roster-table td:nth-child(3), #mdp-root #md-roster-table td:nth-child(4),
  #mdp-root #md-roster-table td:nth-child(5),
  #mdp-root #md-roster-table td:nth-child(9),
  #mdp-root #md-roster-table td:nth-child(10), #mdp-root #md-roster-table td:nth-child(11),
  #mdp-root #md-roster-table td:nth-child(12) { z-index:4; }
  /* Pinned cells re-assert their card-band backgrounds (opaque, so the
     scrolling middle slides under them). Card 1 edge (col 4) and Card 3
     edge (col 8) carry the divider shadow. */
  #mdp-root #md-roster-table th:nth-child(1), #mdp-root #md-roster-table th:nth-child(2),
  #mdp-root #md-roster-table th:nth-child(3), #mdp-root #md-roster-table th:nth-child(4) { background:#e9f1ea; }
  #mdp-root #md-roster-table td:nth-child(1), #mdp-root #md-roster-table td:nth-child(2),
  #mdp-root #md-roster-table td:nth-child(3), #mdp-root #md-roster-table td:nth-child(4) { background:#fafcfb; }
  #mdp-root #md-roster-table th:nth-child(8), #mdp-root #md-roster-table th:nth-child(9),
  #mdp-root #md-roster-table th:nth-child(10) { background:#e9f1ea; }
  #mdp-root #md-roster-table td:nth-child(8), #mdp-root #md-roster-table td:nth-child(9),
  #mdp-root #md-roster-table td:nth-child(10) { background:#f6faf7; }
  #mdp-root #md-roster-table tbody tr.mdp-row:hover td:nth-child(-n+4) { background:#eef4ee; }
  #mdp-root #md-roster-table tbody tr.mdp-row:hover td:nth-child(n+6):nth-child(-n+8) { background:#f4f8f4; }
  #mdp-root #md-roster-table tbody tr.mdp-row:hover td:nth-child(n+10) { background:#e6f0e7; }
  #mdp-root #md-roster-table th:nth-child(1), #mdp-root #md-roster-table td:nth-child(1) { left:0; }
  #mdp-root #md-roster-table th:nth-child(2), #mdp-root #md-roster-table td:nth-child(2) { left:38px; }
  #mdp-root #md-roster-table th:nth-child(3), #mdp-root #md-roster-table td:nth-child(3) { left:108px; }
  #mdp-root #md-roster-table th:nth-child(4), #mdp-root #md-roster-table td:nth-child(4) { left:146px; }
  #mdp-root #md-roster-table th:nth-child(5), #mdp-root #md-roster-table td:nth-child(5) { left:calc(146px + var(--md-member-col-width, 280px)); }
  #mdp-root #md-roster-table th:nth-child(9), #mdp-root #md-roster-table td:nth-child(9) { right:300px; }
  #mdp-root #md-roster-table th:nth-child(10), #mdp-root #md-roster-table td:nth-child(10) { right:216px; }
  #mdp-root #md-roster-table th:nth-child(11), #mdp-root #md-roster-table td:nth-child(11) { right:120px; }
  #mdp-root #md-roster-table th:nth-child(12), #mdp-root #md-roster-table td:nth-child(12) { right:0; }
  /* The right columns DO pin horizontally now (wrap is overflow-x:auto so
     every itemized assessment is scrollable). Previously they were forced to
     position:static + right:auto, which let the itemized middle slide under
     Total / Payment Status / TOTAL Balance and hide the extras entirely. */
  #mdp-root .mdp-table thead th {
    position:sticky; top:0; z-index:3; background:#f6faf7; color:#1b5e20;
    font-weight:700; font-size:0.7rem; letter-spacing:0.4px; text-transform:uppercase;
    padding:9px 12px; border-bottom:1.5px solid #dfe9df; text-align:left; white-space:nowrap;
    vertical-align:middle;
  }
  /* Column headers wrap (Exclude / Total / Payment) so every word stays
     visible: centered text wider than its cell would spill both ways, hence
     the widened cols above plus breakable wrapping. */
  #mdp-root .mdp-table thead th.mdp-wraphead { white-space:normal; text-align:center; line-height:1.35; overflow-wrap:break-word; min-width:0; }
  /* Roster headers keep their compact 0.7rem uppercase design. The
     dashboard-wide "consistent table heads" override
     (.dashboard-module table thead th { font-size:0.8rem !important; ... })
     otherwise inflates "Exclude from Batch" past its cell so the centered
     text bleeds left over the Member-column divider. 2 IDs + !important
     outranks that override; injected styles also load after it. */
  #mdp-root #md-roster-table thead th {
    font-size:0.7rem !important; text-transform:uppercase !important;
    letter-spacing:0.4px !important; padding:6px 8px !important;
    z-index:5;
  }
  /* Rejection / return note banner: shows the Auditor's or President's remarks
     at the top of the Treasurer's Active Entry so they know what to fix. */
  #mdp-root .mdp-reject-note { display:flex; gap:12px; align-items:flex-start; padding:14px 18px; margin-bottom:14px; border-radius:12px; border:1.5px solid; font-size:0.82rem; line-height:1.5; }
  #mdp-root .mdp-reject-note.rejected { background:#fef2f2; border-color:#f5c2c2; }
  #mdp-root .mdp-reject-note.returned { background:#fff8ed; border-color:#f0d9b5; }
  #mdp-root .mdp-reject-note > i { font-size:1rem; margin-top:2px; }
  #mdp-root .mdp-reject-note.rejected > i, #mdp-root .mdp-reject-note.rejected .mdp-reject-title { color:#c62828; }
  #mdp-root .mdp-reject-note.returned > i, #mdp-root .mdp-reject-note.returned .mdp-reject-title { color:#e65100; }
  #mdp-root .mdp-reject-note .mdp-reject-title { font-weight:800; font-size:0.8rem; margin-bottom:2px; }
  #mdp-root .mdp-reject-note .mdp-reject-body { color:#374151; white-space:pre-wrap; overflow-wrap:anywhere; }
  /* President-uploaded attachments (request letter + deduction sheet), same
     "Attachments to Review" card the Auditor and President see. */
  #mdp-root .mdp-attach-card { background:#fff; border:1.5px solid #a5d6a7; border-radius:12px; padding:14px 18px; margin-bottom:14px; font-size:0.82rem; }
  #mdp-root .mdp-attach-title { color:#1b5e20; font-weight:800; font-size:0.78rem; letter-spacing:0.4px; text-transform:uppercase; margin-bottom:8px; }
  #mdp-root .mdp-attach-title i { margin-right:6px; }
  #mdp-root .mdp-attach-line { color:#374151; margin-top:4px; }
  #mdp-root .mdp-attach-line strong { color:#111827; }
  #mdp-root .mdp-attach-line a { color:#1565c0; text-decoration:underline; font-weight:600; }
  #mdp-root .mdp-table td { padding:3px 8px; border-bottom:1px solid #f1f4f1; vertical-align:middle; background:#fff; overflow:visible; }
  #mdp-root .mdp-table td.mdp-item-cell { overflow:visible; }
  #mdp-root .mdp-table th { padding:6px 8px; }
  #mdp-root .mdp-name { line-height:1.15; white-space:normal; overflow:visible; text-overflow:clip; overflow-wrap:anywhere; }
  #mdp-root .mdp-dept { line-height:1.05; }
  #mdp-root .mdp-exclude { line-height:1; }
  #mdp-root .mdp-table tbody tr.mdp-row:hover td { background:#fafcf9; }
  #mdp-root .mdp-table tbody tr.mdp-row:last-child td { border-bottom:none; }
  #mdp-root .mdp-name { font-weight:700; color:#111827; line-height:1.3; }
  #mdp-root .mdp-dept { font-size:0.72rem; color:#8a949e; margin-top:1px; }
  #mdp-root .mdp-actual {
    width:100%; min-width:0; max-width:100%; box-sizing:border-box;
    height:28px; text-align:right; font-weight:700; border:1px solid #d6ddd7;
    border-radius:6px; padding:4px 8px; font-size:0.78rem; font-family:inherit; color:#1f2937;
  }
  #mdp-root .mdp-actual:focus { outline:none; border-color:#2e7d32; box-shadow:0 0 0 3px rgba(46,125,50,0.12); }
  /* Browsers give number inputs a large intrinsic minimum width that ignores
     the width rule and blows the table off-screen. Kill it so every amount
     field truly fits its column — this is what caused the page scrollbar. */
  #mdp-root #md-roster-table input[type="number"] { min-width:0; max-width:100%; box-sizing:border-box; }
  #mdp-root .mdp-actual:read-only { background:#f4f6f4; color:#6b7280; }
  #mdp-root .mdp-fill100-btn {
    margin-top:3px; padding:2px 10px; border-radius:999px; cursor:pointer;
    border:1px solid #a5d6a7; background:#e8f5e9; color:#1b5e20;
    font-size:0.68rem; font-weight:800; font-family:inherit; line-height:1.4; white-space:nowrap;
  }
  #mdp-root .mdp-fill100-btn:hover { background:#c8e6c9; }
  #mdp-root .mdp-table td.mdp-status-cell { text-align:center; }
  #mdp-root .mdp-outstanding-cell { white-space:nowrap; text-align:right; font-weight:700; font-variant-numeric:tabular-nums; cursor:pointer; transition:all 0.2s ease; }
  #mdp-root .mdp-outstanding-cell small { display:block; font-weight:600; margin-top:2px; }
  #mdp-root .mdp-outstanding-cell:hover { color:#1b5e20; transform:scale(1.02); }
  #mdp-root .mdp-badge {
    display:inline-flex; align-items:center; gap:6px; padding:3px 11px;
    border-radius:999px; font-size:0.73rem; font-weight:700; white-space:nowrap;
  }
  #mdp-root .mdp-badge-paid    { background:#e8f5e9; color:#2e7d32; }
  #mdp-root .mdp-badge-partial { background:#fff8e1; color:#b45309; }
  #mdp-root .mdp-badge-unpaid  { background:#ffebee; color:#c62828; }
  #mdp-root .mdp-badges { display:flex; flex-wrap:wrap; gap:4px; margin-top:4px; align-items:center; max-width:100%; }
  /* Status pills may wrap to two lines inside narrow member columns instead
     of spilling over Card 1's edge into Card 2 (cells are overflow:visible
     so nothing clips — wrapping keeps every word inside the card). */
  #mdp-root .mdp-badges .mdp-class-chip,
  #mdp-root .mdp-badges .mdp-catchup-pill { white-space:normal; overflow-wrap:anywhere; max-width:100%; text-align:left; }
  #mdp-root .mdp-catchup-pill {
    display:inline-flex; align-items:center; gap:4px; padding:2px 8px;
    border-radius:999px; font-size:0.64rem; font-weight:800; letter-spacing:0.01em;
    border:1px solid transparent; line-height:1.3; white-space:nowrap;
  }
  #mdp-root .mdp-catchup-needed {
    background:#fff3e0; border-color:#e65100; color:#e65100; cursor:pointer;
  }
  #mdp-root .mdp-catchup-needed:hover { background:#ffe0b2; }
  #mdp-root .mdp-catchup-midyear {
    background:#fff8e1; border-color:#b45309; color:#b45309;
  }
  #mdp-root .mdp-catchup-after {
    background:#fce4ec; border-color:#ad1457; color:#ad1457;
  }
  #mdp-root .mdp-catchup-ok {
    background:#e8f5e9; border-color:#a5d6a7; color:#1b5e20;
  }
  /* Persistent importance signal: open back-dues never fade. The name cell
     gets an amber marker so a new member who still owes stands out. */
  #mdp-root .mdp-catchup-open {
    background:#fff3e0; border-color:#e65100; color:#b45309;
  }
  #mdp-root .mdp-name-new {
    background:#fff8e1; border-left:3px solid #e65100; border-radius:4px;
    padding:1px 6px; margin-left:-9px;
  }
  #mdp-root .mdp-catchup-soft.is-hidden { display:none; }
  #mdp-root .mdp-unpaid-wrap { position:relative; display:flex; flex-direction:column; gap:4px; align-items:stretch; }
  #mdp-root .mdp-unpaid-toggle {
    display:flex; align-items:center; justify-content:space-between; gap:6px;
    border:1px solid #d6ddd7; background:#fff; border-radius:8px; padding:3px 7px;
    font-size:0.68rem; font-weight:700; color:#374151; cursor:pointer; min-width:110px;
  }
  #mdp-root .mdp-unpaid-toggle:hover { border-color:#a5d6a7; background:#f6faf7; }
  #mdp-root .mdp-unpaid-toggle .mdp-unpaid-count { color:#e65100; }
  #mdp-root .mdp-unpaid-panel {
    position:fixed; z-index:9990; min-width:260px; max-width:320px;
    background:#fff; border:1px solid #d6ddd7; border-radius:10px; box-shadow:0 12px 32px rgba(15,23,42,0.18);
    padding:8px; display:none; max-height:min(42vh, 320px); overflow-y:auto;
  }
  #mdp-root .mdp-unpaid-panel.open { display:block; }
  #mdp-root .mdp-unpaid-panel-title {
    font-size:0.7rem; font-weight:800; color:#1b5e20; letter-spacing:0.02em;
    margin-bottom:6px; padding-bottom:6px; border-bottom:1px dashed #e5ebe6;
    display:flex; justify-content:space-between; align-items:center; gap:10px;
  }
  #mdp-root .mdp-unpaid-panel-title .mdp-unpaid-total {
    font-weight:800; color:#e65100; font-variant-numeric:tabular-nums;
  }
  #mdp-root .mdp-unpaid-panel-title .mdp-unpaid-selectall-label {
    display:inline-flex; align-items:center; gap:6px; cursor:pointer; user-select:none;
  }
  #mdp-root .mdp-unpaid-panel-title input.mdp-unpaid-selectall {
    width:14px; height:14px; margin:0; accent-color:#2e7d32; cursor:pointer;
  }
  #mdp-root .mdp-unpaid-panel-title input.mdp-unpaid-selectall:disabled { cursor:not-allowed; }
  /* Unpaid popup cards: [UNPAID MONTHS header] / [TOTAL UNPAID BALANCE] /
     [Amount to pay input] / [month selection list]. Amount and months are
     two linked ways to pay the same arrears — typing an amount auto-ticks
     the oldest months it covers; ticking months rewrites the amount. */
  #mdp-root .mdp-unpaid-card {
    display:flex; justify-content:space-between; align-items:center; gap:10px;
    background:#f6faf7; border:1px solid #dfe9df; border-radius:8px;
    padding:6px 9px; margin-bottom:6px; font-size:0.7rem;
  }
  #mdp-root .mdp-unpaid-card > span { color:#374151; font-weight:700; letter-spacing:0.02em; }
  #mdp-root .mdp-unpaid-card > strong { color:#e65100; font-weight:800; white-space:nowrap; font-variant-numeric:tabular-nums; }
  #mdp-root .mdp-unpaid-amount-input {
    width:110px; text-align:right; font-weight:800; color:#1b5e20;
    border:1px solid #d6ddd7; border-radius:6px; padding:4px 7px;
    font-size:0.74rem; font-family:inherit; font-variant-numeric:tabular-nums;
    box-sizing:border-box; min-width:0;
  }
  #mdp-root .mdp-unpaid-amount-input:focus { outline:none; border-color:#2e7d32; box-shadow:0 0 0 3px rgba(46,125,50,0.12); }
  #mdp-root .mdp-unpaid-amount-input:disabled { background:#f1f3f1; color:#8a949e; cursor:not-allowed; }
  #mdp-root .mdp-unpaid-hint { font-size:0.66rem; color:#8a949e; line-height:1.4; margin:-2px 1px 6px; min-height:0; }
  #mdp-root .mdp-unpaid-hint.has-warn { color:#b45309; font-weight:600; }
  #mdp-root .mdp-unpaid-listhead {
    display:flex; justify-content:space-between; align-items:center; gap:10px;
    font-size:0.68rem; font-weight:800; color:#1b5e20; letter-spacing:0.02em;
    margin:2px 1px 6px;
  }
  #mdp-root .mdp-unpaid-listhead label { display:inline-flex; align-items:center; gap:6px; cursor:pointer; user-select:none; font-weight:600; color:#6b7280; }
  #mdp-root .mdp-unpaid-row {
    display:grid; grid-template-columns:auto 1fr auto; gap:8px; align-items:center;
    padding:5px 7px; margin-bottom:4px; border:1px solid #e4ece6; border-radius:8px;
    font-size:0.7rem; cursor:pointer; user-select:none; background:#fff;
  }
  #mdp-root .mdp-unpaid-row:hover { background:#f6faf7; border-color:#a5d6a7; }
  #mdp-root .mdp-unpaid-row.is-selected { background:#e8f5e9; border-color:#a5d6a7; }
  #mdp-root .mdp-unpaid-row input.mdp-unpaid-check {
    width:14px; height:14px; margin:0; accent-color:#2e7d32; cursor:pointer;
  }
  #mdp-root .mdp-unpaid-row input.mdp-unpaid-check:disabled { cursor:not-allowed; }
  #mdp-root .mdp-unpaid-row .mdp-unpaid-label { color:#374151; font-weight:600; }
  #mdp-root .mdp-unpaid-row .mdp-unpaid-amt {
    color:#1b5e20; font-weight:800; white-space:nowrap; font-variant-numeric:tabular-nums;
  }
  #mdp-root .mdp-unpaid-empty { color:#8a949e; font-size:0.7rem; padding:6px 2px; }
  /* Superadmin "Unpaid Month List" switch OFF: the month checkbox cards hide
     and only the Amount to pay input stays. Hidden rows still auto-tick when
     an amount is typed (same DOM linkage), so recording is unaffected. */
  #mdp-root .mdp-unpaid-panel.mdp-months-hidden .mdp-unpaid-listhead,
  #mdp-root .mdp-unpaid-panel.mdp-months-hidden .mdp-unpaid-row,
  #mdp-root .mdp-unpaid-panel.mdp-months-hidden .mdp-unpaid-group,
  #mdp-root .mdp-unpaid-panel.mdp-months-hidden .mdp-unpaid-empty { display:none; }
  /* Month group: header checkbox ticks the whole month (Due + Aid);
     sub-rows tick one component. Same checkbox | label | amount grid. */
  #mdp-root .mdp-unpaid-group { display:flex; flex-direction:column; gap:3px; padding:4px; margin-bottom:4px; border:1px solid #e4ece6; border-radius:8px; background:#fcfdfc; }
  #mdp-root .mdp-unpaid-grouphead {
    display:grid; grid-template-columns:auto 1fr auto; gap:8px; align-items:center;
    padding:5px 7px; border-radius:6px; font-size:0.7rem; cursor:pointer; user-select:none;
    background:#f1f8f1; border:1px solid #dfe9df;
  }
  #mdp-root .mdp-unpaid-grouphead:hover { border-color:#a5d6a7; }
  #mdp-root .mdp-unpaid-grouphead input { width:14px; height:14px; margin:0; accent-color:#2e7d32; cursor:pointer; }
  #mdp-root .mdp-unpaid-grouphead input:disabled { cursor:not-allowed; }
  #mdp-root .mdp-unpaid-grouphead .mdp-unpaid-label { color:#1b5e20; font-weight:700; }
  #mdp-root .mdp-unpaid-grouphead .mdp-unpaid-amt {
    color:#1b5e20; font-weight:800; white-space:nowrap; font-variant-numeric:tabular-nums;
  }
  #mdp-root .mdp-unpaid-row.mdp-unpaid-sub { margin-bottom:0; margin-left:16px; }
  #mdp-root .mdp-expand-btn {
    width:32px; height:32px; border-radius:10px; border:2px solid #d6ddd7; background:#fff;
    color:#6b7280; cursor:pointer; display:inline-flex; align-items:center; justify-content:center; font-size:0.8rem;
    transition:all 0.2s ease;
  }
  #mdp-root .mdp-expand-btn:hover { background:#f3f6f3; color:#1b5e20; border-color:#a5d6a7; transform:scale(1.05); }
  #mdp-root .mdp-expand-btn.open { background:#e8f5e9; border-color:#a5d6a7; color:#1b5e20; box-shadow:0 2px 8px rgba(46,125,50,0.2); }

   /* ---------- expandable detail row ---------- */
   #mdp-root tr.mdp-detail td { background:#f8fbf8; border-bottom:1px solid #e6ebe7; padding:16px 20px 18px; }
   #mdp-root .mdp-detail-title { font-size:0.78rem; font-weight:700; letter-spacing:0.5px; text-transform:uppercase; color:#1b5e20; margin-bottom:12px; }
   #mdp-root .mdp-detail-title .mdp-hint { text-transform:none; letter-spacing:0; font-weight:600; color:#9aa4ad; margin-left:8px; }
  #mdp-root .mdp-chips { display:grid; grid-template-columns:repeat(var(--md-item-count, 1),max-content); gap:2px 8px; justify-content:start; align-content:start; width:max-content; max-width:100%; max-height:48px; overflow-x:auto; overflow-y:auto; padding:4px 3px 4px 0; }
  #mdp-root .mdp-item-header { display:grid; grid-template-columns:repeat(var(--md-item-count, 1),max-content); gap:2px 8px; justify-content:start; margin-top:2px; }
  #mdp-root .mdp-item-header span { min-width:0; overflow:visible; text-overflow:clip; white-space:nowrap; line-height:1.25; font-size:0.68rem; font-weight:700; color:#475569; text-transform:lowercase; }
  #mdp-root .mdp-item-input-row { display:grid; grid-template-columns:minmax(0,1fr) 64px; align-items:center; gap:6px; min-width:0; width:100%; }
  #mdp-root .mdp-chips input.md-item-amount-input { width:92px !important; min-width:0; padding:3px 5px !important; box-sizing:border-box; }
   #mdp-root .mdp-chips .md-item-chip, #mdp-root .mdp-chips .mdp-tag {
     display:inline-flex; align-items:center; gap:6px; border-radius:12px;
     padding:3px 8px; font-size:0.72rem; white-space:nowrap; font-family:inherit;
     transition:all 0.2s ease;
   }
   #mdp-root .mdp-chips .md-item-chip { cursor:pointer; }
   #mdp-root .mdp-chips .md-item-chip:hover { transform:translateY(-1px); box-shadow:0 2px 6px rgba(0,0,0,0.1); }
  /* Carry-over cue: outstanding unpaid dues were settled first, so this
     month's Monthly Due stays unpaid and moves to next month. A translucent
     overlay sits on ONLY the Monthly Due input (the aid items are not part
     of this cue) and the field is locked while it shows — pointer-events:none
     keeps the rest of the row usable; raising Total Collected (or unticking
     unpaid months) clears it. */
  #mdp-root .mdp-item-cell { position:relative; }
  #mdp-root .mdp-carry-overlay { position:absolute; box-sizing:border-box; z-index:2; display:flex; align-items:center; justify-content:center; padding:1px; pointer-events:none; background:rgba(255,183,77,0.32); border:1.5px dashed #ef6c00; border-radius:6px; }
  #mdp-root .mdp-carry-overlay span { max-width:100%; background:#fff3e0; border:1px solid #ef6c00; color:#8a4b00; font-size:0.62rem; font-weight:800; line-height:1.15; padding:2px 5px; border-radius:999px; box-shadow:0 1px 4px rgba(0,0,0,0.14); text-align:center; overflow:hidden; }
  #mdp-root #mdp-column-totals { padding:9px 14px !important; margin-top:9px !important; }
  #mdp-root #mdp-column-totals .mdp-sticky-label { font-size:0.58rem; }
   #mdp-root .mdp-note-line { margin-top:12px; font-size:0.76rem; color:#6b7280; background:#fff; padding:8px 12px; border-radius:8px; border-left:3px solid #1b5e20; }
   #mdp-root .md-vo-detail-grid { display:grid; grid-template-columns:minmax(220px,2fr) minmax(88px,1fr) minmax(88px,1fr) minmax(100px,1fr); align-items:center; gap:7px 14px; font-size:0.76rem; }
   #mdp-root .md-vo-detail-head { color:#8a949e; font-size:0.64rem; font-weight:700; letter-spacing:0.04em; text-transform:uppercase; }
   #mdp-root .md-vo-detail-cell { min-width:0; }
   #mdp-root .md-vo-detail-item { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
   #mdp-root .md-vo-detail-recipient { display:block; color:#8a949e; font-size:0.68rem; margin-top:1px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
   #mdp-root .md-vo-detail-money { font-variant-numeric:tabular-nums; white-space:nowrap; }
   #mdp-root .md-vo-detail-result { text-align:right; font-weight:700; white-space:nowrap; }
   #mdp-root .md-vo-detail-divider { grid-column:1 / -1; border-top:1px solid #e6ebe7; height:1px; }
   @media (max-width: 700px) {
     #mdp-root .md-vo-detail-grid { grid-template-columns:minmax(150px,2fr) repeat(2,minmax(72px,1fr)); }
     #mdp-root .md-vo-detail-head:nth-child(3), #mdp-root .md-vo-detail-cell:nth-child(3) { display:none; }
   }

  /* ---------- actions / states ---------- */
  #mdp-root .mdp-actions { display:flex; gap:12px; align-items:center; justify-content:flex-end; flex-wrap:wrap; margin-top:14px; }
  #mdp-root .mdp-empty { text-align:center; color:#8a949e; padding:34px 18px; font-size:0.85rem; }
  #mdp-root .mdp-loading { padding:30px; text-align:center; color:#8a949e; font-size:0.85rem; }
  #mdp-root .mdp-hidden { display:none !important; }
  @media (max-width: 860px) {
    #mdp-root .mdp-overview-grid { grid-template-columns:1fr; }
    #mdp-root .mdp-statuscard-grid { grid-template-columns:1fr; justify-items:stretch; }
    #mdp-root .mdp-statuscard-main { padding:0; gap:20px; }
    #mdp-root .mdp-statuscard-left { justify-content:center; }
    #mdp-root .mdp-legend { width:100%; }
    #mdp-root .mdp-moneyline { grid-column:1; grid-template-columns:repeat(2, minmax(0, 1fr)); }
  }
  @media (max-width: 560px) {
    #mdp-root .mdp-chips { grid-template-columns:max-content; max-height:96px; }
    #mdp-root .mdp-legend { grid-template-columns:1fr; }
    #mdp-root .mdp-statuscard-head { display:block; }
    #mdp-root .mdp-statuscard-note { margin-top:4px; text-align:left; }
  }
  /* ---------- roster pagination (50/page, client-side) ---------- */
  #mdp-root #mdp-pager {
    display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;
    padding:10px 14px; margin-top:10px; background:#fff; border:1px solid #e6ebe7; border-radius:12px;
    font-size:0.78rem; color:#475569;
  }
  #mdp-root #mdp-pager.mdp-hidden { display:none !important; }
  #mdp-root .mdp-pager-info { font-variant-numeric:tabular-nums; }
  #mdp-root .mdp-pager-btns { display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
  #mdp-root .mdp-pagebtn {
    border:1px solid #d6ddd7; background:#fff; border-radius:8px; padding:5px 11px;
    font-size:0.78rem; font-weight:700; color:#374151; cursor:pointer; font-family:inherit; min-width:34px;
    position:relative;
  }
  #mdp-root .mdp-pagebtn:hover:not(:disabled) { background:#f3f6f3; border-color:#a5d6a7; }
  #mdp-root .mdp-pagebtn.active { background:#1b5e20; border-color:#1b5e20; color:#fff; }
  #mdp-root .mdp-pagebtn:disabled { opacity:0.4; cursor:default; }
  /* Unpaid-dues dot: marks page buttons whose page contains a member with
     unpaid dues, so arrears are visible without opening each page. */
  #mdp-root .mdp-pagebtn .mdp-pagebtn-dot {
    position:absolute; top:3px; right:3px; width:7px; height:7px; border-radius:50%;
    background:#c62828; box-shadow:0 0 0 2px #fff; pointer-events:none;
  }
  #mdp-root .mdp-pagebtn.active .mdp-pagebtn-dot { box-shadow:0 0 0 2px #1b5e20; background:#ffcdd2; }
  `;

  /* ============================== helpers ============================== */
  let cssInjected = false;
  function ensureStyles() {
    if (cssInjected) return;
    const style = document.createElement("style");
    style.id = "mdp-styles";
    style.textContent = CSS;
    document.head.appendChild(style);
    cssInjected = true;
    console.log("=== MONTHLY DEDUCTION CSS INJECTED ===");
    console.log("=== CSS CONTAINS mdp-summary-item ===", CSS.includes("mdp-summary-item"));
    console.log("=== CSS CONTAINS flex-direction:column ===", CSS.includes("flex-direction:column"));
  }

  const PESO = (v) => "₱" + Number(v || 0).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const esc = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
  }
  function toast(message, isError) {
    if (typeof window.showToast === "function") window.showToast(message, isError);
    else if (isError) console.error(message);
  }

  const STATUS_BADGE = {
    draft: ["#eceff1", "#455a64"],
    pending_treasurer: ["#e0f2f1", "#00695c"],
    pending_deposit: ["#e8eaf6", "#283593"],
    pending_audit: ["#fff8e1", "#b45309"],
    pending_final: ["#f3e5f5", "#6a1b9a"],
    final_approved: ["#e8f5e9", "#1b5e20"],
    rejected: ["#ffebee", "#c62828"],
    returned: ["#fff3e0", "#e65100"],
  };
  function statusBadge(status, label) {
    const [bg, fg] = STATUS_BADGE[status] || ["#eeeeee", "#555555"];
    return `<span class="mdp-chip" style="background:${bg}; color:${fg};">${esc(label || status)}</span>`;
  }

  const PAY_STATUS = {
    paid:    { label: "Paid",     dot: "#2e7d32" },
    partial: { label: "Partial",  dot: "#f9a825" },
    unpaid:  { label: "Unpaid", dot: "#e53935" },
    exempt:  { label: "Exempt",  dot: "#607d8b" },
  };
  function payBadge(status) {
    const meta = PAY_STATUS[status] || PAY_STATUS.unpaid;
    return `<span class="mdp-badge mdp-badge-${status}">${meta.label}</span>`;
  }

  /* ============================== state ============================== */
  const state = { assessments: [], activeAssessments: [], approvedAssessments: [], assessmentId: null, voAssessmentId: null, roster: null, recordable: false, status: "", filter: "all", search: "", page: 1, perPage: 50, flags: { requireBackDues: false, showUnpaidMonths: true } };

  /* Informational join-status badges (green/amber/pink) show for 5 minutes
   * after first display in this tab; orange "New member" always stays. */
  const JOIN_BADGE_MS = 5 * 1000;
  let joinBadgeTimer = null;
  function joinBadgeRemainingMs() {
    try {
      const until = Number(sessionStorage.getItem("mdp-join-badges-until") || 0);
      if (until > Date.now()) return until - Date.now();
      const next = Date.now() + JOIN_BADGE_MS;
      sessionStorage.setItem("mdp-join-badges-until", String(next));
      return JOIN_BADGE_MS;
    } catch (e) {
      return JOIN_BADGE_MS;
    }
  }
  function hideSoftCatchupBadges() {
    document.querySelectorAll(".mdp-catchup-soft").forEach((el) => {
      el.classList.add("is-hidden");
      el.style.display = "none";
    });
  }
  function scheduleJoinBadgeExpiry() {
    if (joinBadgeTimer) clearTimeout(joinBadgeTimer);
    const remaining = joinBadgeRemainingMs();
    if (remaining <= 0) {
      hideSoftCatchupBadges();
      joinBadgeTimer = null;
      return;
    }
    joinBadgeTimer = setTimeout(hideSoftCatchupBadges, remaining);
  }
  function rosterDraftKey(assessmentId) {
    return `mdp-roster-draft-${assessmentId}`;
  }
  function loadRosterDraft(assessmentId) {
    try {
      const stored = JSON.parse(localStorage.getItem(rosterDraftKey(assessmentId)) || "{}");
      return stored && typeof stored === "object" ? stored : {};
    } catch (e) {
      return {};
    }
  }
  function saveRosterDraft() {
    if (!state.assessmentId) return;
    const draft = {};
    document.querySelectorAll("#md-roster-body tr.mdp-row").forEach((row) => {
      const items = {};
      row.querySelectorAll(".md-item-amount-input").forEach((input) => {
        items[input.dataset.itemId] = input.value;
      });
      const unpaidKeys = mdSelectedUnpaidKeys(row);
      draft[row.dataset.memberId] = {
        checked: !!row.querySelector(".md-member-check")?.checked,
        excluded: row.dataset.excluded === "1",
        actual: row.querySelector(".md-actual-input")?.value || "0.00",
        unpaid_keys: unpaidKeys,
        unpaid_amount: row.querySelector(".mdp-unpaid-amount-input")?.value || "0.00",
        items,
      };
    });
    try {
      localStorage.setItem(rosterDraftKey(state.assessmentId), JSON.stringify(draft));
    } catch (e) {
      // Storage can be unavailable in private browsing; server submission still works.
    }
  }
  function clearRosterDraft(assessmentId) {
    try { localStorage.removeItem(rosterDraftKey(assessmentId)); } catch (e) { /* unavailable */ }
  }

  function shellReady() {
    const root = document.getElementById("mdp-root");
    if (!root) return false;
    ensureStyles();
    if (root.dataset.shell === "1") return true;
    root.dataset.shell = "1";
    root.innerHTML = `
      <div class="mdp-card mdp-toolbar">
        <div>
          <h2 class="mdp-title">Monthly Deductions</h2>
          <p class="mdp-sub">Record each member's actual deduction from the accounting sheet, then submit for deposit.</p>
        </div>
        <div class="mdp-toolbar-right">
          <span class="mdp-toolbar-label" style="font-size:0.72rem; font-weight:600; color:#6b7280;">Month</span>
          <select id="md-month-select" class="mdp-select" onchange="mdLoadRoster()"></select>
          <span id="mdp-status-chip"></span>
          <button type="button" class="mdp-btn" id="md-catchup-btn" onclick="mdGenerateCatchupAll()" title="Some members have no dues rows for the months before they joined — create those missing rows so they can be collected">Create missing dues</button>
          <button type="button" class="mdp-btn" onclick="mdOpenYearTracker()" title="Per-member Jan–Dec collection grid for one year — late joiners owe from their join month">Year Tracker</button>
          <button type="button" class="mdp-btn btn-refresh" onclick="mdpRefresh()" title="Reload months, members and status">REFRESH</button>
        </div>
      </div>
      <div class="mdp-tabs">
        <button type="button" class="mdp-tab active" id="mdp-tabbtn-record" onclick="mdpSetTab('record')">Active Entry</button>
        <button type="button" class="mdp-tab" id="mdp-tabbtn-viewonly" onclick="mdpSetTab('viewonly')">View Months <span id="mdp-viewonly-count" style="font-weight:600; color:#8a949e;"></span></button>
      </div>

      <div id="mdp-tab-record">
        <div class="mdp-hidden" id="mdp-reject-note"></div>
        <div class="mdp-top-cards" id="mdp-top-cards">
          <div class="mdp-hidden" id="mdp-breakdown-summary"></div>
          <div class="mdp-hidden" id="mdp-attachments"></div>
        </div>
        <div class="mdp-hidden" id="mdp-timeline"></div>
        <div class="mdp-hidden" id="mdp-alloc-settings"></div>
        <div class="mdp-controls mdp-hidden" id="mdp-controls">
          <div class="mdp-search">
            <i class="fa-solid fa-magnifying-glass"></i>
            <input type="text" id="mdp-search-input" placeholder="Search Member or Department" oninput="mdpSetSearch(this.value)" />
          </div>
          <div class="mdp-filterchips" id="mdp-filterchips"></div>
        </div>
        <div class="mdp-card mdp-tablewrap mdp-hidden" id="mdp-roster-wrap">
          <table class="mdp-table" id="md-roster-table">
            <thead><tr>
              <th style="width:38px;text-align:center;" title="Select members to record"><input type="checkbox" class="mdp-check" onchange="mdToggleAll(this.checked)" title="Select All members" aria-label="Select All members" /></th><th style="width:70px;" class="mdp-wraphead" title="Exclude from Batch — record no contribution; balance carries next month">Exclude</th><th style="width:38px;">#</th><th>Member & Department</th><th style="width:14px;" aria-hidden="true"></th><th style="width:128px;" class="mdp-wraphead" title="Total Collected">Total Collected<br><button type="button" class="mdp-fill100-btn" onclick="mdFillAllCollected()" title="Fill each active Total Collected field with that member's supposed total (this month's assessment + ticked unpaid balance)">Total</button></th>
              <th><div>Itemized Assessment</div><div id="mdp-item-header" class="mdp-item-header"></div></th><th style="width:160px;" class="mdp-wraphead" title="Unpaid Balance">Unpaid<br>Balance</th><th style="width:14px;" aria-hidden="true"></th><th style="text-align:right;">Total</th><th class="mdp-wraphead">Payment Status</th><th class="mdp-wraphead" style="text-align:right;">TOTAL<br>Balance</th>
            </tr></thead>
            <tbody id="md-roster-body"></tbody>
          </table>
        </div>
        <div id="mdp-pager" class="mdp-hidden"></div>
        <div class="mdp-card mdp-hidden" id="mdp-column-totals"></div>
        <div id="mdp-actions"></div>
      </div>

      <div id="mdp-tab-viewonly" style="display:none;">
        <div class="mdp-card mdp-toolbar" style="margin-bottom:14px;">
          <div></div>
          <div class="mdp-toolbar-right">
            <span class="mdp-toolbar-label" style="font-size:0.72rem; font-weight:600; color:#6b7280;">Months</span>
            <div class="mdp-picker-wrap">
              <button type="button" id="mdp-vo-btn" class="mdp-select mdp-picker-btn"><span id="mdp-vo-label">Select month</span><i class="fas fa-chevron-down" style="font-size:0.7rem;"></i></button>
              <div id="mdp-vo-pop" class="mdp-picker-pop" style="display:none;">
                <div class="mdp-picker-year">
                  <button type="button" class="mdp-picker-nav" id="mdp-vo-prev">&lsaquo;</button>
                  <strong id="mdp-vo-year"></strong>
                  <button type="button" class="mdp-picker-nav" id="mdp-vo-next">&rsaquo;</button>
                </div>
                <div class="mdp-picker-grid" id="mdp-vo-grid"></div>
              </div>
            </div>
            <button type="button" class="mdp-btn mdp-btn-primary" onclick="mdpDownloadSheet('viewonly')" title="Transmittal letter + deduction sheet (PDF)">Letter + Sheet (PDF)</button>
          </div>
        </div>
        <div class="mdp-card" style="padding:16px 20px;">
          <div id="mdp-viewonly-info" style="display:flex; gap:16px; flex-wrap:wrap; align-items:center; font-size:0.8rem; color:#475569; margin-bottom:12px;"></div>
          <div class="mdp-tablewrap" style="max-height:56vh;">
            <table class="mdp-table" id="md-viewonly-table">
            <thead><tr>
                  <th style="width:42px;">#</th><th>Member Name</th><th>Department</th>
                  <th style="text-align:right;">Total Collected</th>
                  <th style="text-align:right;">Unpaid Balance</th>
                </tr></thead>
              <tbody id="md-viewonly-body"></tbody>
            </table>
          </div>
          <div id="mdp-viewonly-foot" class="mdp-note-line" style="display:none;"></div>
        </div>
      </div>

      </div>`;
    return true;
  }

  /* ============================== data loads ============================== */
  window.loadMdOverviews = async function loadMdOverviews(silent) {
    if (!shellReady()) return;
    try {
      const resp = await fetch("/api/treasurer/deductions/overview/", { cache: "no-store" });
      if (!resp.ok) {
        let detail = "";
        try { detail = (await resp.clone().json()).error || ""; } catch (e) { /* HTML redirect body */ }
        if (!silent) toast(detail || `Failed to load assessments (HTTP ${resp.status}).`, true);
        return;
      }
      const data = await resp.json();
      if (!data.ok) { if (!silent) toast(data.error || "Failed to load assessments.", true); return; }

      const visibleStatuses = new Set(["pending_treasurer", "pending_deposit", "rejected", "returned", "final_approved"]);
      state.assessments = (data.assessments || []).filter((a) => visibleStatuses.has(a.status));
      setBadge("md-attention-dot", state.assessments.filter((a) => ["pending_treasurer", "pending_deposit", "rejected", "returned"].includes(a.status)).length);
      // Months already handed off (deposited → audited) leave the Treasurer
      // list; a pending_deposit month stays visible read-only because the
      // Treasurer still has to deposit it in Record Transaction.
      state.activeAssessments = state.assessments.filter((a) => a.status !== "final_approved");
      state.approvedAssessments = state.assessments.filter((a) => a.status === "final_approved");

      const select = document.getElementById("md-month-select");
      if (select) {
        const previous = select.value;
        select.innerHTML = state.activeAssessments.length
          ? state.activeAssessments.map((a) =>
              `<option value="${a.assessment_id}">${esc(a.month_label)}</option>`
            ).join("")
          : `<option value="">No months open for recording</option>`;
        if (previous && state.activeAssessments.some((a) => String(a.assessment_id) === previous)) select.value = previous;
        select.disabled = !state.activeAssessments.length;
      }

      if (!state.voAssessmentId || !state.approvedAssessments.some((a) => String(a.assessment_id) === String(state.voAssessmentId))) {
        state.voAssessmentId = state.approvedAssessments.length ? String(state.approvedAssessments[0].assessment_id) : null;
      }
      mdpBindVoPicker();
      const voCount = document.getElementById("mdp-viewonly-count");
      if (voCount) voCount.textContent = state.approvedAssessments.length ? `(${state.approvedAssessments.length})` : "";

      if (!state.assessmentId && state.activeAssessments.length) {
        state.assessmentId = String(state.activeAssessments[0].assessment_id);
        if (select) select.value = state.assessmentId;
      }
      updateToolbarChip();
      if (data.flags && typeof data.flags.require_back_dues === "boolean") {
        state.flags.requireBackDues = data.flags.require_back_dues;
      }
      if (data.flags && typeof data.flags.show_unpaid_months === "boolean") {
        state.flags.showUnpaidMonths = data.flags.show_unpaid_months;
      }
      updateCatchupButton(data.catchup_pending_count || 0);
      // Pending-recording banner: once per page load, pop a top-center
      // action banner when months await treasurer recording, with a button
      // straight to Record Monthly Dues.
      try {
        var actionable = (state.assessments || []).filter(function (as) {
          return ["pending_treasurer", "rejected", "returned"].indexOf(String(as.status)) !== -1;
        });
        if (actionable.length && !state.pendingBannerShown && typeof window.showTopActionBanner === "function") {
          state.pendingBannerShown = true;
          var labels = actionable.map(function (as) { return as.month_label; }).join(", ");
          window.showTopActionBanner({
            key: "treasurer-pending-dues",
            title: "Record Monthly Dues pending",
            message: actionable.length + " month(s) awaiting recording: " + labels + ".",
            actionLabel: "Go to Record Monthly Dues",
            onAction: function () {
              if (typeof window.setActiveModule === "function") window.setActiveModule("view-monthly-deduction");
            },
          });
        }
      } catch (e) {}
      if (state.activeAssessments.length) mdLoadRoster({ auto: true });
      else mdpRenderEmpty();
      if (state.voAssessmentId) mdpLoadViewOnly();
    } catch (e) {
      console.error("Failed to load monthly deduction overview", e);
      toast("Failed to load assessments.", true);
    }
  };

  function updateCatchupButton(pendingCount) {
    const btn = document.getElementById("md-catchup-btn");
    if (!btn) return;
    // Back-dues chase switch (default OFF): hide the toolbar button entirely
    // when mid-year joiners pay current->future only.
    if (!state.flags.requireBackDues) { btn.style.display = "none"; return; }
    btn.style.display = "";
    const n = Number(pendingCount) || 0;
    btn.textContent = n > 0
      ? `Create missing dues (${n})`
      : "Create missing dues";
    btn.classList.toggle("mdp-btn-primary", n > 0);
    btn.title = n > 0
      ? `${n} member(s) have no dues rows for the months before they joined — click to create them`
      : "Some members have no dues rows for the months before they joined — create those missing rows so they can be collected";
  }

  /* ---------- months popup picker (view-only approved months) ---------- */
  function mdpBindVoPicker() {
    const btn = document.getElementById("mdp-vo-btn");
    const label = document.getElementById("mdp-vo-label");
    const pop = document.getElementById("mdp-vo-pop");
    const grid = document.getElementById("mdp-vo-grid");
    const yearLabel = document.getElementById("mdp-vo-year");
    const prev = document.getElementById("mdp-vo-prev");
    const next = document.getElementById("mdp-vo-next");
    if (!btn || !label || !pop || !grid || !yearLabel || !prev || !next) return;
    const list = state.approvedAssessments || [];
    const cur = list.find((a) => String(a.assessment_id) === String(state.voAssessmentId)) || null;
    label.textContent = cur ? cur.month_label : (list.length ? "Select month" : "No approved months yet");
    btn.disabled = !list.length;
    const keyOf = (x) => String(x.month || "").slice(0, 7);
    const yearOf = (x) => String(x.month || "").slice(0, 4);
    const years = [...new Set(list.map(yearOf).filter((y) => /^\d{4}$/.test(y)))].sort();
    let year = (cur && /^\d{4}$/.test(yearOf(cur)) && years.includes(yearOf(cur)))
      ? yearOf(cur)
      : (years[years.length - 1] || String(new Date().getFullYear()));
    const ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const close = () => { pop.style.display = "none"; document.removeEventListener("click", outside); };
    const outside = (e) => { if (!pop.contains(e.target) && !btn.contains(e.target)) close(); };
    const paint = () => {
      yearLabel.textContent = year;
      prev.disabled = !years.length || year <= years[0];
      next.disabled = !years.length || year >= years[years.length - 1];
      grid.innerHTML = ABBR.map((m, i) => {
        const hit = list.find((x) => keyOf(x) === `${year}-${String(i + 1).padStart(2, "0")}`);
        if (!hit) return `<button type="button" class="mdp-mbtn" disabled>${m}</button>`;
        const cls = String(hit.assessment_id) === String(state.voAssessmentId) ? " current" : "";
        return `<button type="button" class="mdp-mbtn${cls}" data-aid="${hit.assessment_id}">${m}</button>`;
      }).join("");
      grid.querySelectorAll("[data-aid]").forEach((b) =>
        b.addEventListener("click", () => {
          state.voAssessmentId = b.dataset.aid;
          close();
          mdpBindVoPicker();
          mdpLoadViewOnly();
        })
      );
    };
    btn.onclick = (e) => {
      e.stopPropagation();
      if (!list.length) return;
      if (pop.style.display === "none") { paint(); pop.style.display = "block"; document.addEventListener("click", outside); }
      else close();
    };
    prev.onclick = (e) => { e.stopPropagation(); const i = years.indexOf(year); if (i > 0) { year = years[i - 1]; paint(); } };
    next.onclick = (e) => { e.stopPropagation(); const i = years.indexOf(year); if (i >= 0 && i < years.length - 1) { year = years[i + 1]; paint(); } };
    if (!window.__mdpVoPickerEsc) {
      window.__mdpVoPickerEsc = true;
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") { const p = document.getElementById("mdp-vo-pop"); if (p) p.style.display = "none"; }
      });
    }
  }

  // Status suffix for dropdown options / chip. Months still inside the
  // Treasurer's hands show no status; a recorded month reads "Pending Deposit",
  // and once deposited it reads "Pending to Auditor".
  function monthStatusSuffix(a) {
    if (!a) return "";
    const sl = String(a.status_label || "").trim().toLowerCase();
    if (a.status === "pending_deposit" || sl === "pending deposit") return "Pending Deposit";
    if (a.status === "pending_audit" || sl === "pending auditor verification") return "Pending to Auditor";
    if (a.status === "pending_treasurer" || a.status === "draft" || sl === "with treasurer" || sl === "draft") return "";
    return a.status_label || "";
  }

  function updateToolbarChip() {
    const el = document.getElementById("mdp-status-chip");
    if (!el) return;
    const current = state.assessments.find((a) => String(a.assessment_id) === String(state.assessmentId));
    const suffix = monthStatusSuffix(current);
    el.innerHTML = current && suffix ? statusBadge(current.status, suffix) : "";
  }

  window.mdLoadRoster = async function mdLoadRoster(opts) {
    const optsAuto = !!(opts && opts.auto);
    const select = document.getElementById("md-month-select");
    const assessmentId = select ? select.value : "";
    state.assessmentId = assessmentId || null;
    updateToolbarChip();
    if (!assessmentId) { mdpRenderEmpty(); return; }
    try {
      const resp = await fetch(`/api/treasurer/deductions/members/${assessmentId}/`, { cache: "no-store" });
      if (!resp.ok) {
        // Non-200 (e.g. 302 redirect on expired session returns HTML, not
        // JSON): surface the real status instead of a generic message.
        let detail = "";
        try { detail = (await resp.clone().json()).error || ""; } catch (e) { /* HTML redirect body */ }
        if (!detail) {
          detail = (resp.status === 401 || resp.status === 403)
            ? "Session expired — please log out and log back in, then retry."
            : `Failed to load member roster (HTTP ${resp.status}).`;
        }
        toast(detail, true);
        return;
      }
      const data = await resp.json();
      if (!data.ok) { toast(data.error || "Failed to load member roster.", true); return; }
      state.roster = data;
      state.recordable = !!data.recordable;
      if (data.flags && typeof data.flags.require_back_dues === "boolean") {
        state.flags.requireBackDues = data.flags.require_back_dues;
      }
      if (data.flags && typeof data.flags.show_unpaid_months === "boolean") {
        state.flags.showUnpaidMonths = data.flags.show_unpaid_months;
      }
      state.status = String((data.assessment && data.assessment.status) || "");
      state.filter = "all";
      state.search = "";
      state.page = 1;
      renderRoster(data);
      scheduleJoinBadgeExpiry();
      // Aid linkage: a monthly due carrying an aid fund needs its claim
      // filed first — prompt before the treasurer records the collection.
      // Suppressed on automatic (boot) loads: the prompt belongs to opening
      // Record Monthly Dues or explicitly changing the month, never to
      // landing on the dashboard.
      try {
        const aidLinkCheck = mdCheckAidLinkage(data, { auto: !!optsAuto });
        if (aidLinkCheck && aidLinkCheck.catch) aidLinkCheck.catch(() => {});
      } catch (e) { /* never break roster load */ }
      /* Roster-load safety net fired: tell the treasurer exactly which
         missing rows were just created — this is the processing popup. */
      if (data.auto_created) {
        const label = data.assessment && data.assessment.month_label ? ` for ${data.assessment.month_label}` : "";
        toast(`Opening${label}: ${data.auto_created}`);
      }
    } catch (e) {
      console.error("Failed to load member roster", e);
      toast("Failed to load member roster.", true);
    }
  };

  /* ---------- aid linkage: monthly due carrying an aid fund ----------
   * When the treasurer opens a monthly due whose breakdown links an aid
   * fund to a member, pop a message BEFORE recording:
   *   "There is an AID linked on this monthly due, file a medical aid now
   *    before recording this monthly due collection [button to file]"
   * Shown only when that member has NO filed aid claim yet. The file
   * button jumps to the filing module and auto-selects the linked member.
   */
  const MD_AID_PURPOSES = { medical_aid_fund: "medical", death_aid_fund: "death" };
  const MD_AID_FILED_DEAD = new Set(["withdrawn", "rejected", "denied", "returned", "cancelled"]);

  function mdNormName(s) {
    return String(s == null ? "" : s).toLowerCase().replace(/,/g, " ").replace(/\s+/g, " ").trim();
  }

  // Assessment recipient text is free-form; roster rows carry the formatted
  // "SURNAME, Given" name — match case-insensitively on the normalized form.
  function mdResolveAidMember(recipient, members) {
    const want = mdNormName(recipient);
    if (!want || want === mdNormName("ISUCauFA, Inc.")) return null;
    const list = Array.isArray(members) ? members : [];
    return list.find((m) => mdNormName(m.member_name) === want)
      || list.find((m) => mdNormName(m.member_name).indexOf(want) !== -1 || want.indexOf(mdNormName(m.member_name)) !== -1)
      || null;
  }

  // A filed claim exists when the member has a claim row whose status is
  // still live (withdrawn / rejected / denied / returned rows never paid
  // out, so they do not count — the member must file anew).
  function mdFiledForMember(rows, memberId) {
    const list = Array.isArray(rows) ? rows : [];
    return list.some((r) => {
      const id = r.memberId != null ? r.memberId : r.member_id;
      if (id == null || String(id) !== String(memberId)) return false;
      return !MD_AID_FILED_DEAD.has(String(r.status || "").trim().toLowerCase());
    });
  }

  async function mdFetchAidRows(url) {
    try {
      const resp = await fetch(url, { cache: "no-store", credentials: "same-origin" });
      if (!resp.ok) return [];
      const data = await resp.json().catch(() => null);
      if (!data) return [];
      return data.medical_aids || data.death_aids || [];
    } catch (e) {
      return [];
    }
  }

  async function mdCheckAidLinkage(data, opts) {
    const items = (data && data.items) || ((data && data.assessment && data.assessment.items) || []);
    const members = (data && data.members) || [];
    const assessment = (data && data.assessment) || {};
    if (!items.length || !members.length) return;
    // Only prompt while the month is still recordable — a submitted month
    // no longer needs a pre-recording filing nudge.
    if (data.recordable === false) return;
    // Automatic loads (dashboard boot) never prompt — the treasurer hasn't
    // opened Record Monthly Dues. Explicit month changes and section opens
    // (via mdMaybePromptAidLink) do.
    if (opts && opts.auto) return;
    const aidItems = items.filter((i) => MD_AID_PURPOSES[i.purpose] && (i.recipient || "").trim());
    if (!aidItems.length) return;
    // One prompt per assessment per tab session — re-opening the same month
    // must not nag again, but a different month prompts afresh.
    const warnKey = `mdp-aid-link-warned-${assessment.assessment_id || state.assessmentId || "x"}`;
    try { if (sessionStorage.getItem(warnKey) === "1") return; } catch (e) {}
    const [medRows, deathRows] = await Promise.all([
      mdFetchAidRows("/api/treasurer/medical-aids/list/"),
      mdFetchAidRows("/api/treasurer/death-aids/list/"),
    ]);
    const unfiled = [];
    aidItems.forEach((item) => {
      const kind = MD_AID_PURPOSES[item.purpose];
      const member = mdResolveAidMember(item.recipient, members);
      if (!member) return;
      const rows = kind === "medical" ? medRows : deathRows;
      if (!mdFiledForMember(rows, member.member_id)) {
        unfiled.push({ item, kind, member });
      }
    });
    if (!unfiled.length) return;
    try { sessionStorage.setItem(warnKey, "1"); } catch (e) {}
    mdShowAidLinkPrompt(unfiled, assessment);
  }

  // Section-open entry point (nxModuleInit hook): re-evaluate the cached
  // roster and prompt only now that Record Monthly Dues is actually open.
  // No refetch — the roster payload already carries items + members.
  window.mdMaybePromptAidLink = function mdMaybePromptAidLink() {
    try {
      const data = state.roster;
      if (!data) return;
      const sec = document.getElementById("view-monthly-deduction");
      if (sec && !sec.classList.contains("active")) return;
      const p = mdCheckAidLinkage(data, { auto: false });
      if (p && p.catch) p.catch(() => {});
    } catch (e) { /* never break navigation */ }
  };

  function mdShowAidLinkPrompt(unfiled, assessment) {
    const monthLabel = (assessment && assessment.month_label) || "";
    const rowsHtml = unfiled.map((u, idx) => {
      const kindLabel = u.kind === "medical" ? "Medical Aid" : "Death Aid";
      const target = u.kind === "medical" ? "aid-file-medical" : "aid-file-death";
      return `<div style="display:flex; align-items:center; justify-content:space-between; gap:10px; padding:8px 10px; border:1px solid #e4ece6; border-radius:8px; margin-top:8px; background:#fffcf4;">
        <div style="min-width:0;"><div style="font-weight:700; color:#111827; font-size:0.82rem;">${esc(u.member.member_name)}</div>
        <div style="font-size:0.72rem; color:#8a949e;">${esc(kindLabel)} · ${esc(u.item.purpose_label || u.item.purpose)}${u.item.amount != null ? ` · ${PESO(u.item.amount)}` : ""}${u.item.recipient ? ` · For: ${esc(u.item.recipient)}` : ""}</div></div>
        <button type="button" class="mdp-btn mdp-btn-primary" data-aid-idx="${idx}" data-aid-target="${target}" data-aid-member="${u.member.member_id}" data-aid-kind="${u.kind}" onclick="mdGoFileAid(this)" style="flex:none;">File ${u.kind === "medical" ? "Medical" : "Death"} Aid</button>
      </div>`;
    }).join("");
    const html = `
      <p class="sm-message" style="margin-bottom:6px;">
        There is an <strong>AID linked on this monthly due${monthLabel ? ` (${esc(monthLabel)})` : ""}</strong> —
        file ${unfiled.length > 1 ? "the claims" : "a medical aid"} now <strong>before recording this monthly due collection</strong>.
      </p>
      <p style="margin:0; font-size:0.78rem; color:#6b7280;">No filed aid claim was found for the linked member${unfiled.length > 1 ? "s" : ""} below.</p>
      ${rowsHtml}`;
    if (typeof SimpleModal !== "undefined" && typeof SimpleModal.open === "function") {
      const modal = SimpleModal.open({
        title: "AID linked — file aid before recording",
        width: "520px",
        radius: "14px",
        dismissible: true,
        html: html + `<div class="sm-buttons" style="margin-top:14px;"><button type="button" id="mdp-aid-link-stay">Continue recording</button></div>`,
      });
      const stay = document.getElementById("mdp-aid-link-stay");
      if (stay) stay.addEventListener("click", () => { try { modal.close(); } catch (e) {} });
      return;
    }
    toast("There is an AID linked on this monthly due — file a medical aid now before recording this monthly due collection.", true);
  }

  // Filing-module jump: open File Medical/Death Aid and auto-select the
  // member linked to the monthly due aid item.
  window.mdGoFileAid = async function mdGoFileAid(btn) {
    const memberId = btn && btn.getAttribute ? btn.getAttribute("data-aid-member") : "";
    const kind = btn && btn.getAttribute ? (btn.getAttribute("data-aid-kind") || "medical") : "medical";
    const target = btn && btn.getAttribute ? (btn.getAttribute("data-aid-target") || "aid-file-medical") : "aid-file-medical";
    try {
      if (typeof window.setActiveModule === "function") window.setActiveModule(target);
    } catch (e) {}
    // Close the prompt modal if one is open.
    try {
      if (typeof SimpleModal !== "undefined" && typeof SimpleModal.close === "function" && SimpleModal.isOpen()) SimpleModal.close();
    } catch (e) {}
    if (!memberId) return;
    const isMedical = kind !== "death";
    // The filing member list loads async — load the module once, then pick
    // the linked member (retry the pick while the list is still loading).
    try {
      if (window.nxAidFiling) {
        if (isMedical && typeof window.nxAidFiling.loadMedical === "function") await window.nxAidFiling.loadMedical();
        else if (!isMedical && typeof window.nxAidFiling.loadDeath === "function") await window.nxAidFiling.loadDeath();
      }
    } catch (e) {}
    for (let attempt = 0; attempt < 10; attempt += 1) {
      try {
        if (window.nxAidFiling) {
          const pick = isMedical ? window.nxAidFiling.pickMedMember : window.nxAidFiling.pickDeathMember;
          if (typeof pick !== "function") return;
          pick(String(memberId));
          // Confirm the member card rendered; stop retrying once selected.
          await new Promise((r) => setTimeout(r, 300));
          const cardId = isMedical ? "afm_member_card" : "afd_member_card";
          const card = document.getElementById(cardId);
          if (card && card.textContent && card.textContent.indexOf("No member selected") === -1) return;
        }
      } catch (e) {}
      await new Promise((r) => setTimeout(r, 500));
    }
  };

  function mdpRenderEmpty() {
    ["mdp-overview-grid", "mdp-statuscard", "mdp-summary-card", "mdp-meta", "mdp-sticky", "mdp-controls", "mdp-reject-note", "mdp-attachments", "mdp-timeline", "mdp-roster-wrap", "mdp-pager"].forEach(hide);
    const body = document.getElementById("md-roster-body");
    if (body) body.innerHTML = "";
    const actions = document.getElementById("mdp-actions");
    if (actions) actions.innerHTML = "";
    show("mdp-statuscard");
    show("mdp-overview-grid");
    const card = document.getElementById("mdp-statuscard");
    const allApproved = state.assessments.length > 0 && state.activeAssessments.length === 0;
    if (card) card.innerHTML = allApproved
      ? `<div class="mdp-empty"><i class="fa-solid fa-circle-check" style="font-size:1.5rem; display:block; margin-bottom:10px; color:#2e7d32;"></i>Every recorded month is already final-approved.<br><span style="font-size:0.76rem;">Open the <strong>Pending Audit</strong> tab to review them, or wait for the President to create the next deduction.</span></div>`
      : `<div class="mdp-empty"><i class="fa-solid fa-inbox" style="font-size:1.5rem; display:block; margin-bottom:10px; color:#c3ccc4;"></i>No deduction records yet.<br><span style="font-size:0.76rem;">The President creates them in the Monthly Deduction module.</span></div>`;
  }

  function hide(id) { const el = document.getElementById(id); if (el) el.classList.add("mdp-hidden"); }
  function show(id) { const el = document.getElementById(id); if (el) el.classList.remove("mdp-hidden"); }

  /* ---------- roster rendering ---------- */
  const MONTH_ABBR = {
    January: "Jan", February: "Feb", March: "Mar", April: "Apr", May: "May",
    June: "Jun", July: "Jul", August: "Aug", September: "Sep", October: "Oct",
    November: "Nov", December: "Dec",
  };
  function mdChipLabel(item) {
    let label = String(item.purpose_label || "")
      .replace("Medical Aid Fund", "Medical Aid")
      .replace("Death Aid Fund", "Death Aid")
      .replace("Monthly Due", "Due");
    return label.replace(/(January|February|March|April|May|June|July|August|September|October|November|December)/g, (m) => MONTH_ABBR[m] || m);
  }

  function docImageLinks(images) {
    return (images || []).map((img, i) =>
      `<a href="${img.url}" target="_blank" rel="noopener" title="View ${esc(img.name)}">Image ${i + 1}</a>`
    ).join(" · ");
  }

  function sizeRosterItemColumns() {
    const table = document.getElementById("md-roster-table");
    if (!table) return;
    // Card 2 is content-sized: one 92px input per item plus the longest
    // header label in full — never stretched to fill slack (that stretch is
    // what left a large unoccupied space with a single assessment). With the
    // table shrink-wrapped (width:max-content, centered), leftover space
    // becomes even margins instead of dead Card 2 space.
    const itemCount = Number(table?.dataset.itemCount || 1);
    const labelLen = Number(table?.dataset.itemLabelLen || 0);
    const labelPx = labelLen * 6.4 + 6;
    const preferredWidth = Math.ceil(Math.max(itemCount * 100 + 16, labelPx + 20));
    table.style.setProperty("--md-item-column-width", `${preferredWidth}px`);
  }
  window.addEventListener("resize", sizeRosterItemColumns);

  function renderRoster(data) {
    const items = data.items || [];
    const assessment = data.assessment || {};
    if (assessment && ["rejected", "returned"].includes(String(assessment.status))) {
      clearRosterDraft(assessment.assessment_id);
    }
    const rosterDraft = assessment && assessment.assessment_id ? loadRosterDraft(assessment.assessment_id) : {};

    const itemHead = document.getElementById("mdp-item-header");
    if (itemHead) {
      const itemCount = Math.max(1, items.length);
      const table = document.getElementById("md-roster-table");
      if (table) {
        table.style.setProperty("--md-item-count", itemCount);
        table.dataset.itemCount = itemCount;
        table.dataset.itemLabelLen = items.reduce((n, it) => Math.max(n, mdChipLabel(it).length), 0);
        // Dynamic member column: hug the longest name, floor 180px, cap
        // 280px — beyond the cap long names wrap ("stack") via .mdp-name.
        // The floor covers the name + status pills so badge text never leaks
        // past Card 1 into Card 2 (cells are overflow:visible, so anything
        // wider than the column would clip over the next card).
        const longestName = (data.members || []).reduce(
          (n, mm) => Math.max(n, String(mm.member_name || "").length, String(mm.department || "").length), 0);
        const memberWidth = Math.min(280, Math.max(180, longestName * 7 + 20));
        table.style.setProperty("--md-member-col-width", memberWidth + "px");
        table.dataset.memberWidth = memberWidth;
      }
      itemHead.style.setProperty("--md-item-count", itemCount);
      itemHead.innerHTML = items.map((item) => {
        const label = mdChipLabel(item);
        return `<span title="${esc(label)}">${esc(label)}</span>`;
      }).join("");
      sizeRosterItemColumns();
    }

    const searchInput = document.getElementById("mdp-search-input");
    if (searchInput) searchInput.value = state.search;
    show("mdp-controls");
    show("mdp-roster-wrap");
    show("mdp-column-totals");
    // The wrap starts hidden, so the earlier sizeRosterItemColumns() call
    // measured clientWidth 0 on first paint. Re-run now that the wrap is
    // visible so the Itemized column gets its true share of the width.
    sizeRosterItemColumns();

    // Rejection / return note from the Auditor or President — the Treasurer
    // needs to see exactly what to fix before re-recording. The remarks are
    // cleared on resubmission, so the banner only shows while action is due.
    const noteEl = document.getElementById("mdp-reject-note");
    if (noteEl) {
      const st = String(assessment.status || "");
      let noteHtml = "";
      const auditorNote = String(assessment.auditor_remarks || "").trim();
      const presidentNote = String(assessment.president_remarks || "").trim();
      if (st === "rejected" && auditorNote) {
        noteHtml = `<div class="mdp-reject-note rejected"><i class="fa-solid fa-circle-exclamation"></i><div><div class="mdp-reject-title">Rejected by Auditor — please fix and resubmit</div><div class="mdp-reject-body">${esc(auditorNote)}</div></div></div>`;
      } else if (st === "returned" && presidentNote) {
        noteHtml = `<div class="mdp-reject-note returned"><i class="fa-solid fa-rotate-left"></i><div><div class="mdp-reject-title">Returned by President — please fix and resubmit</div><div class="mdp-reject-body">${esc(presidentNote)}</div></div></div>`;
      }
      noteEl.innerHTML = noteHtml;
      if (noteHtml) show("mdp-reject-note"); else hide("mdp-reject-note");
    }

    // President-uploaded attachments for this month (request letter +
    // deduction sheet) plus the Treasurer's deposit evidence — the same
    // files the Auditor and President review.
    const attachEl = document.getElementById("mdp-attachments");
    if (attachEl) {
      const letters = assessment.request_letter_images || [];
      const sheets = assessment.deduction_sheet_images || [];
      const slips = assessment.deposit_slips || [];
      let attachHtml = "";
      const lines = [];
      if (letters.length) lines.push(`<div class="mdp-attach-line"><strong>Request Letter (ISUCauFA):</strong> ${docImageLinks(letters)}</div>`);
      if (sheets.length) lines.push(`<div class="mdp-attach-line"><strong>Deduction Sheet:</strong> ${docImageLinks(sheets)}</div>`);
      if (assessment.deposit_reference || slips.length) {
        const depositBits = [
          `Collection ${esc(assessment.collection_reference || "")}`,
          assessment.deposit_reference ? `Ref ${esc(assessment.deposit_reference)}` : "",
          assessment.deposited_amount != null ? PESO(assessment.deposited_amount) : "",
          slips.length ? `Slip: ${docImageLinks(slips)}` : "Slip: missing",
        ].filter(Boolean);
        lines.push(`<div class="mdp-attach-line"><strong>Deposit:</strong> ${depositBits.join(" · ")}</div>`);
      }
      if (lines.length) {
        attachHtml = `<div class="mdp-attach-card"><div class="mdp-attach-title"><i class="fa-solid fa-paperclip"></i>Attachments to Review</div>${lines.join("")}</div>`;
      }
      attachEl.innerHTML = attachHtml;
      if (attachHtml) show("mdp-attachments"); else hide("mdp-attachments");
    }

    // Workflow trace (president set → record → deposit → verify → approve).
    const timelineEl = document.getElementById("mdp-timeline");
    if (timelineEl) {
      const logs = data.workflow_logs || [];
      if (logs.length && typeof window.mdWorkflowTimelineHtml === "function") {
        timelineEl.innerHTML = window.mdWorkflowTimelineHtml(logs);
        show("mdp-timeline");
      } else {
        timelineEl.innerHTML = "";
        hide("mdp-timeline");
      }
    }

    // Allocation settings card (below the workflow history): per-item
    // amounts the treasurer can push onto all selected member rows at once.
    renderAllocSettings(items);

    // Render assessment breakdown summary
    const summaryEl = document.getElementById("mdp-breakdown-summary");
    console.log("=== BREAKDOWN SUMMARY ELEMENT ===", summaryEl);
    if (summaryEl) {
      const compactCardSizing = items.length <= 4 ? "max-width:none;" : "";
      let itemsHtml = items.map((i) => {
        const covered = (data.members || []).some((m) => (m.recorded_item_ids || []).includes(i.item_id));
        return `<div style="display:flex; flex-direction:column; gap:10px; padding:18px; border:1px solid #e1e8e2; border-radius:12px; background:${covered ? '#f8fff8' : '#fbfdfb'}; transition:all 0.2s ease; flex:1; min-width:250px; max-width:320px; ${compactCardSizing}">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:12px;">
            <span style="font-weight:700; font-size:0.95rem; line-height:1.4; color:#1f2937; flex:1;">${esc(i.purpose_label)}</span>
            <span style="font-weight:800; color:#1b5e20; font-size:1.2rem; white-space:nowrap;">${PESO(i.amount)}</span>
          </div>
          <span style="font-size:0.78rem; color:#6b7280; line-height:1.5;">For: ${esc(i.recipient || '—')}</span>
        </div>`;
      }).join("");
      const html = `
          <div style="display:flex; flex-direction:column; gap:6px; width:100%; padding:20px; border:1px solid #dfe9df; border-radius:12px; background:#fff; box-shadow:0 1px 3px rgba(16,24,40,0.05);">
          <div style="margin-bottom:12px;">
            <span style="font-weight:800; font-size:1rem; color:#1b5e20;">Assessment Breakdown</span>
          </div>
          <div style="display:flex; flex-wrap:wrap; width:100%; gap:24px; margin-top:16px; justify-content:flex-start;">${itemsHtml || '<div style="padding:12px; color:#8a949e; font-size:0.85rem; text-align:center;">No assessment items yet</div>'}</div>
        </div>`;
      console.log("=== BREAKDOWN HTML GENERATED ===", html.substring(0, 200) + "...");
      summaryEl.innerHTML = html;
      show("mdp-breakdown-summary");
    }

    const tbody = document.getElementById("md-roster-body");
    if (!tbody) return;
    tbody.innerHTML = "";
    const readonlyAttr = state.recordable ? "0" : "1";
    const inputAttrs = state.recordable ? "" : "readonly";

    (data.members || []).forEach((m, index) => {
      const checkedIds = m.recorded_item_ids || [];
      const savedDraft = m.recorded_actual == null ? (rosterDraft[String(m.member_id)] || {}) : {};
      const recordedPrior = m.recorded_actual != null ? Number(m.recorded_prior_collected || 0) : 0;
      const base = m.recorded_actual != null
        ? Number(m.recorded_actual || 0)
        : (savedDraft.actual || 0);
      /* Payment obligation by classification (By-Laws): Retired members owe
         nothing: their row is locked with zeros but stays listed so the
         record is never removed. Teaching members owe every item. */
      const isRetired = m.classification === "Retired" || m.membership_status === "Retired";
      const isExcluded = Boolean(m.is_excluded) || Boolean(savedDraft.excluded);
      /* Unpaid-month checkboxes are interactive only on editable rows: a
         submitted/read-only month, a retired row, or an excluded row renders
         them disabled (toggle handlers guard on dataset.readonly too). */
      const unpaidRowLocked = !state.recordable || isRetired || isExcluded;
      const memberStandard = m.expected_total != null ? m.expected_total : m.standard_assessment;

      const itemChips = items.map((i) => {
        const covered = checkedIds.includes(i.item_id);
        const notRequired = isRetired;
        const exemptNote = "not required (Retired)";
        const amount = notRequired ? 0 : i.amount;
        const chipStyle = notRequired
          ? "background:#f1f3f1; border:2px dashed #c3cdc5; color:#8a949e; box-shadow:none;"
          : (covered ? "background:#e8f5e9; border:2px solid #a5d6a7; color:#1b5e20; box-shadow:0 2px 8px rgba(46,125,50,0.15);" : "background:#ffffff; border:2px solid #dde3dd; color:#374151; box-shadow:none;");
        return `<button type="button" class="md-item-chip" data-item-id="${i.item_id}" data-item-amount="${amount}" data-required="${notRequired ? "0" : "1"}" data-purpose="${esc(i.purpose || "")}" data-selected="${covered ? "1" : "0"}" ${i.recipient ? `title="For: ${esc(i.recipient)}"` : ""} ${notRequired ? "" : `onclick="mdToggleChip(this)"`} style="${chipStyle}">
          <i class="fa-solid ${notRequired ? "fa-ban" : covered ? "fa-circle-check" : "fa-circle"}" style="font-size:0.75rem;"></i>
          <span style="font-weight:600;">${esc(notRequired ? exemptNote : mdChipLabel(i))}</span> <span style="font-weight:700; color:${notRequired ? "#8a949e" : covered ? "#1b5e20" : "#2e7d32"};">${notRequired ? "exempt" : PESO(i.amount)}</span>
        </button>`;
      }).join("");

      // Back-dues chase switch (default OFF): exclude catch-up-source months
      // from the Unpaid column when mid-year joiners pay current->future only
      // (backend already excludes; this is defense-in-depth).
      const unpaidMonths = (Array.isArray(m.unpaid_months) ? m.unpaid_months : [])
        .filter((um) => state.flags.requireBackDues || !um || um.source !== "catchup");
      const unpaidTotal = unpaidMonths.reduce((sum, um) => sum + (Number(um.amount) || 0), 0);
      /* The popup shows the total outstanding balance with a tickable month
         breakdown — the OLDEST month starts ticked. The collection settles
         the ticked months FIRST (oldest ticked month first): a dues-only
         collection clears the oldest unsettled month and this month carries
         over. The treasurer ticks more months to apply more, or unticks to
         direct money at this month instead. Drafts restore the treasurer's
         picks; recorded rows re-select the months the recorded prior payment
         actually covered (its stored month attribution, falling back to the
         oldest-covered approximation for rows recorded before attribution
         existed). */
      const recordedCoveredKeys = (Array.isArray(m.recorded_prior_collected_months) ? m.recorded_prior_collected_months : [])
        .map((um) => um && um.key)
        .filter(Boolean);
      /* selectedKeys is built below (legacy keys expanded to Due/Aid leaves). */
      /* Expand legacy whole-month keys to their component leaves so drafts
         and snapshots recorded before the Due/Aid split restore correctly:
         a bare "2026-02" ticks Due + Aid, component keys pass through. */
      const expandUnpaidKeys = (keys) => {
        const out = [];
        (keys || []).forEach((k) => {
          const s = String(k);
          if (s.indexOf(":") !== -1) { if (out.indexOf(s) < 0) out.push(s); return; }
          const target = unpaidMonths.find((u) => u.key === s);
          if (!target) return;
          if ((Number(target.aid) || 0) > 0.004) {
            [`${s}:dues`, `${s}:aid`].forEach((ck) => { if (out.indexOf(ck) < 0) out.push(ck); });
          } else if (out.indexOf(s) < 0) {
            out.push(s);
          }
        });
        return out;
      };
      const rawSelectedKeys =
        (savedDraft.unpaid_keys && Array.isArray(savedDraft.unpaid_keys) && savedDraft.unpaid_keys.length)
          ? savedDraft.unpaid_keys
          : (m.recorded_actual != null
              ? (recordedCoveredKeys.length
                  ? recordedCoveredKeys
                  : (recordedPrior > 0.004 ? defaultSelectedKeysFor(unpaidMonths, recordedPrior) : []))
              : (unpaidMonths.length ? [unpaidMonths[0].key] : []));
      const selectedKeys = new Set(expandUnpaidKeys(rawSelectedKeys));
      let priorChip = "";
      if (m.prior_outstanding > 0 || unpaidMonths.length) {
        const outstandingTotal = unpaidTotal || m.prior_outstanding;
        const unpaidRows = unpaidMonths.length
          ? unpaidMonths.map((um) => {
              const dues = Number(um.dues != null ? um.dues : um.amount) || 0;
              const aid = Number(um.aid) || 0;
              const leaf = (key, label, amt) => {
                const sel = selectedKeys.has(key);
                return `
                <label class="mdp-unpaid-row${(Number(um.aid) || 0) > 0.004 ? " mdp-unpaid-sub" : ""}${sel ? " is-selected" : ""}" data-key="${esc(key)}" data-amount="${amt}">
                  <input type="checkbox" class="mdp-unpaid-check" ${sel ? "checked" : ""} ${unpaidRowLocked ? "disabled" : ""} onchange="mdUnpaidRowToggle(this)" />
                  <span class="mdp-unpaid-label">${esc(label)}</span>
                  <strong class="mdp-unpaid-amt">${PESO(amt)}</strong>
                </label>`;
              };
              /* Aid-free months stay a single row (whole-month key); months
                 with aid become a group: header ticks Due + Aid, sub-rows
                 tick one component. Label left, amount right, always. */
              if (aid <= 0.004) {
                return leaf(um.key, `${um.label} — Due`, dues);
              }
              const dKey = `${um.key}:dues`;
              const aKey = `${um.key}:aid`;
              const bothTicked = selectedKeys.has(dKey) && selectedKeys.has(aKey);
              const total = dues + aid;
              return `
              <div class="mdp-unpaid-group" data-key="${esc(um.key)}">
                <label class="mdp-unpaid-grouphead" data-key="${esc(um.key)}" data-amount="${total}">
                  <input type="checkbox" class="mdp-unpaid-groupcheck" ${bothTicked ? "checked" : ""} ${unpaidRowLocked ? "disabled" : ""} onchange="mdUnpaidGroupToggle(this)" />
                  <span class="mdp-unpaid-label">${esc(um.label)}</span>
                  <strong class="mdp-unpaid-amt">${PESO(total)}</strong>
                </label>
                ${leaf(dKey, "Due", dues)}
                ${leaf(aKey, "Aid", aid)}
              </div>`;
            }).join("")
          : `<div class="mdp-unpaid-empty">No unpaid months.</div>`;
        priorChip = `<div class="md-prior-balance-cell mdp-unpaid-wrap">
          <button type="button" class="mdp-unpaid-toggle" onclick="mdToggleUnpaidPanel(this)" title="Total outstanding unpaid balance — open for the month breakdown; tick the months this payment settles" aria-label="Outstanding unpaid balance for ${esc(m.member_name)}">
            <span>Unpaid <span class="mdp-unpaid-count">(${unpaidMonths.length})</span></span>
            <strong>${PESO(outstandingTotal)}</strong>
          </button>
          <div class="mdp-unpaid-panel${state.flags.showUnpaidMonths === false ? " mdp-months-hidden" : ""}" data-member-id="${m.member_id}" data-unpaid-total="${outstandingTotal}">
            <div class="mdp-unpaid-panel-title">Unpaid Months</div>
            <div class="mdp-unpaid-card"><span>Total Unpaid Balance</span><strong>${PESO(outstandingTotal)}</strong></div>
            <div class="mdp-unpaid-card"><span>Amount to pay</span><input type="number" class="mdp-unpaid-amount-input" data-member-id="${m.member_id}" step="0.01" min="0" max="${outstandingTotal}" value="0.00" placeholder="0.00" ${unpaidRowLocked ? "disabled" : ""} oninput="mdUnpaidAmountInput(this, false)" onchange="mdUnpaidAmountInput(this, true)" onkeydown="if(event.key==='Enter'){event.preventDefault();}" title="Type an amount to auto-pay the oldest unpaid months — linked with the month ticks below" /></div>
            <div class="mdp-unpaid-hint"></div>
            <div class="mdp-unpaid-listhead"><span>Selection of months</span><label class="mdp-unpaid-selectall-label" title="Select / deselect all unpaid dues in this popup" onclick="event.stopPropagation();"><input type="checkbox" class="mdp-unpaid-selectall" ${unpaidRowLocked ? "disabled" : ""} onchange="mdUnpaidSelectAllToggle(this)" />All</label></div>
            ${unpaidRows}
          </div>
        </div>`;
      }
      const excludeDisabled = state.recordable ? "" : "disabled";

      /* Join-status pills — shown under the name on the recording roster.
       * - New member      : flag still set (Jan→join-month rows not generated yet); click generates them
       * - Joined mid-year : joined after January of their join year (flag may already be cleared)
       * - joined after    : this assessed month is before the member's join month
       * - Jan joiner      : started with the calendar year — nothing to catch up */
      const classChip = `<span class="mdp-class-chip" style="display:inline-block;padding:1px 8px;border-radius:8px;font-size:0.66rem;font-weight:700;background:${m.classification === "Retired" ? "#f1f3f1" : "#e8f5e9"};color:${m.classification === "Retired" ? "#6b7280" : "#1b5e20"};">${esc(m.classification || "Teaching")}</span>`;
      const catchupPills = [];
      if (m.dues_backfill_pending && m.dues_required !== false && state.flags.requireBackDues) {
        catchupPills.push(
          `<button type="button" class="mdp-catchup-pill mdp-catchup-needed" onclick="mdGenerateCatchup(${m.member_id})" title="No dues rows exist yet for the months before this member joined — click to create them">Create missing dues</button>`
        );
      }

      tbody.insertAdjacentHTML("beforeend", `
        <tr class="mdp-row" data-member-id="${m.member_id}" data-standard="${memberStandard}" data-prior="${m.prior_outstanding}" data-unpaid-total="${unpaidTotal || m.prior_outstanding}" data-readonly="${readonlyAttr}" data-manual="0" data-excluded="${isExcluded ? "1" : "0"}" data-open="0" data-name="${esc(m.member_name)}" data-dept="${esc(m.department || "")}">
          <td style="text-align:center;"><input type="checkbox" class="md-member-check mdp-check" ${state.recordable ? (m.recorded_actual != null ? (!isExcluded ? "checked" : "") : (savedDraft.checked ? "checked" : "")) : "checked"} ${isExcluded ? "disabled" : ""} onchange="mdToggleMember(this)" title="Check the members you are recording this month — or use Select All" /></td>
          <td style="text-align:center;"><input type="checkbox" class="md-exclude-check mdp-check" ${isExcluded ? "checked" : ""} ${excludeDisabled} onchange="mdToggleExclude(this)" title="Record no contribution but will Still get a balance and will get carried next month." aria-label="Record no contribution for ${esc(m.member_name)}; balance carries next month" /></td>
          <td class="mdp-row-number" style="text-align:center; color:#8a949e; font-size:0.75rem; font-variant-numeric:tabular-nums;">${index + 1}</td>
          <td><div class="mdp-name">${esc(m.member_name)}</div><div class="mdp-dept">${esc(m.department || "—")}</div><div class="mdp-badges">${classChip}${catchupPills.join("")}</div></td>
          <td aria-hidden="true"></td>
          <td><input type="number" class="md-actual-input mdp-actual" step="0.01" min="0" value="${Number(base).toFixed(2)}" placeholder="0.00" ${inputAttrs} ${isExcluded ? "disabled" : ""} oninput="mdRefreshRow(this)" onkeydown="mdHandleAmountKeydown(event, this)" /></td>
          <td class="mdp-item-cell"><div class="mdp-chips">${itemChips || `<span class="mdp-note-line" style="margin:0;">No assessment items</span>`}</div></td>
          <td style="text-align:center;">${priorChip || '<span style="color:#9e9e9e;">—</span>'}</td>
          <td aria-hidden="true"></td>
          <td class="md-row-total-cell" style="text-align:right; font-weight:700; font-variant-numeric:tabular-nums; color:#1b5e20;">${PESO(0)}</td>
          <td class="mdp-status-cell"></td>
          <td class="mdp-outstanding-cell md-outstanding-cell">${PESO(0)}</td>
        </tr>`);
      if (isRetired) {
        // Retired members owe nothing but stay listed: lock the whole row
        // as excluded with zeros so nothing can be recorded for them.
        const newRow = tbody.lastElementChild;
        if (newRow) {
          newRow.dataset.excluded = "1";
          const memberCheck = newRow.querySelector(".md-member-check");
          if (memberCheck) { memberCheck.checked = false; memberCheck.disabled = true; }
          const actualInput = newRow.querySelector(".md-actual-input");
          if (actualInput) { actualInput.value = "0.00"; actualInput.disabled = true; }
          const excludeCheck = newRow.querySelector(".md-exclude-check");
          if (excludeCheck) { excludeCheck.checked = true; excludeCheck.disabled = true; }
          newRow.querySelectorAll(".mdp-unpaid-check, .mdp-unpaid-groupcheck, .mdp-unpaid-selectall, .mdp-unpaid-amount-input").forEach((x) => { x.disabled = true; });
        }
      }
    });

    const searchEmpty = !(data.members || []).length;
    if (searchEmpty) tbody.innerHTML = `<tr><td colspan="12" class="mdp-empty">No active members found.</td></tr>`;

    // Keep the deduction-items column in the plain amount-input layout for
    // every member, whether the row is fully paid or partially paid.
    const membersById = new Map((data.members || []).map((member) => [String(member.member_id), member]));
    tbody.querySelectorAll("tr.mdp-row").forEach((row) => {
      mdConvertRowToInputs(row);
      const member = membersById.get(String(row.dataset.memberId));
      const savedDraft = member && member.recorded_actual == null ? (rosterDraft[String(member.member_id)] || {}) : {};
      if (state.recordable && member && member.recorded_actual != null) {
        // Restore the Treasurer's exact manual split from recorded_allocations.
        // These are the values the Treasurer intentionally typed (item_amounts mode),
        // not the old auto-allocation. Preserve them so the Treasurer can adjust
        // and resubmit without re-entering everything.
        const appliedByItem = new Map((member.recorded_allocations || []).map((allocation) => [String(allocation.item_id), allocation.applied]));
        row.querySelectorAll(".md-item-amount-input").forEach((input) => {
          input.value = Number(appliedByItem.get(String(input.dataset.itemId)) || 0).toFixed(2);
        });
      } else if (savedDraft.items) {
          row.querySelectorAll(".md-item-amount-input").forEach((input) => {
            if (Object.prototype.hasOwnProperty.call(savedDraft.items, input.dataset.itemId)) {
              input.value = savedDraft.items[input.dataset.itemId];
            }
          });
        }
        // The ticked unpaid months receive the collection first — sync the
        // panel styling with the rendered selection, then link the Amount
        // to pay field: recorded rows show the recorded prior payment;
        // drafts replay the saved amount through the greedy ticker; fresh
        // rows show whatever the default (oldest-month) ticks sum to.
        mdUpdateUnpaidPanel(row);
        const amountInput = row.querySelector(".mdp-unpaid-amount-input");
        if (amountInput && !amountInput.disabled) {
          if (state.recordable && member && member.recorded_actual != null) {
            amountInput.value = Number(member.recorded_prior_collected || 0).toFixed(2);
            mdSyncUnpaidAmountField(row, false);
          } else if (savedDraft.unpaid_amount != null && !(savedDraft.unpaid_keys && savedDraft.unpaid_keys.length)) {
            amountInput.value = savedDraft.unpaid_amount;
            mdGreedyTickUnpaid(row, parseFloat(savedDraft.unpaid_amount) || 0);
            mdUpdateUnpaidPanel(row);
          }
          mdSyncUnpaidAmountField(row);
        }
    });

    // Restore exclusions the Treasurer set before submit/return: a recorded
    // excluded row re-checks its Exclude box (left enabled so it can still
    // be un-excluded), so the returned table matches what was submitted.
    // Retired rows are already locked as excluded above and are skipped.
    tbody.querySelectorAll("tr.mdp-row").forEach((row) => {
      if (row.dataset.excluded === "1") return;
      const member = membersById.get(String(row.dataset.memberId));
      if (state.recordable && member && member.is_excluded) {
        const excludeCheck = row.querySelector(".md-exclude-check");
        if (excludeCheck && !excludeCheck.disabled) {
          excludeCheck.checked = true;
          mdToggleExclude(excludeCheck);
        }
      }
    });

    // Strict snapshot note: members added after this collection was created
    // are excluded from the roster — their dues ride as catch-up next month.
    const rosterWrap = document.getElementById("mdp-roster-wrap");
    if (rosterWrap) {
      let exclNote = rosterWrap.querySelector(".mdp-excluded-note");
      const exclInfo = data.excluded_not_joined || { count: 0, names: [] };
      if (exclInfo.count > 0) {
        if (!exclNote) {
          exclNote = document.createElement("div");
          exclNote.className = "mdp-note-line mdp-excluded-note";
          rosterWrap.prepend(exclNote);
        }
        const shown = (exclInfo.names || []).slice(0, 8).join(", ");
        const extra = exclInfo.count > 8 ? ` and ${exclInfo.count - 8} more` : "";
        exclNote.textContent = `${exclInfo.count} new member(s) joined after this collection was created and are excluded here${shown ? `: ${shown}${extra}` : ""}. Their dues will be collected as catch-up with the next month.`;
        exclNote.style.display = "";
      } else if (exclNote) {
        exclNote.remove();
      }
    }

    state.page = 1;
    renderFilterChips();
    mdRefreshRow();
    renderActions();
    initializeOutstandingCells();
    applyFilters();
  }

  function renderActions() {
    const actions = document.getElementById("mdp-actions");
    if (!actions) return;
    if (!state.recordable) {
      actions.style.display = "";
      const depositing = state.status === "pending_deposit";
      actions.innerHTML = `<div style="text-align:center; color:#757575; font-size:0.8rem; margin-top:12px;">
        ${depositing
          ? 'This batch is recorded and awaiting its bank deposit — open <button type="button" class="mdp-btn" style="padding:4px 12px;font-size:0.78rem;" onclick="mdpGoDeposit()">Due Deposit</button> to record the deposit reference and slip.'
          : "This month has been submitted and the records are read-only until the Auditor returns them."}</div>`;
      return;
    }
    // The submit button lives inside the summary card (below Total Amount
    // Collected) — nothing to show down here while recording.
    actions.innerHTML = "";
    actions.style.display = "none";
  }

  // Jump from a recorded-but-undeposited month straight to the dedicated
  // Due Deposit tab.
  window.mdpGoDeposit = function mdpGoDeposit() {
    try {
      if (typeof window.setActiveModule === "function") {
        window.setActiveModule("view-due-deposit");
      }
    } catch (e) {}
    try {
      if (window.nxDueDeposit && typeof window.nxDueDeposit.load === "function") {
        window.nxDueDeposit.load();
      }
    } catch (e) {}
    const section = document.getElementById("view-due-deposit");
    if (section) section.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // After a successful record-keeping submit, prompt the Treasurer with a
  // 10s countdown to Due Deposit (Proceed now / Close = stay).
  // Simple modal only: rounded card, no backdrop dismiss (buttons only).
  function showDepositNowPrompt() {
    let remaining = 10;
    let timerId = null;
    let cancelled = false;
    let navigated = false;
    let modal = null;

    const clearTimer = () => {
      if (timerId !== null) {
        clearInterval(timerId);
        timerId = null;
      }
    };

    const goToNonDues = () => {
      if (navigated || cancelled) return;
      navigated = true;
      clearTimer();
      try {
        if (modal && typeof modal.close === "function") modal.close();
      } catch (e) {}
      if (typeof window.mdpGoDeposit === "function") window.mdpGoDeposit();
    };

    const closeOnly = () => {
      cancelled = true;
      clearTimer();
      try {
        if (modal && typeof modal.close === "function") modal.close();
      } catch (e) {}
    };

    if (typeof SimpleModal === "undefined" || typeof SimpleModal.open !== "function") {
      goToNonDues();
      return;
    }

    modal = SimpleModal.open({
      title: "Record Submitted — Complete Deposit",
      width: "440px",
      radius: "14px",
      dismissible: false,
      html: `
        <p class="sm-message" style="margin-bottom:10px;">
          This month’s deductions have been recorded for the books.
          Finish the bank deposit so the record is complete and ready for audit.
        </p>
        <p style="margin:0 0 14px;">
          Opening <strong>Due Deposit</strong> in
          <span id="mdp-deposit-countdown" style="font-weight:800;color:#1b5e20;font-variant-numeric:tabular-nums;">10</span>
          second(s)…
        </p>
        <div class="sm-buttons">
          <button type="button" id="mdp-deposit-close-btn">Close</button>
          <button type="button" class="sm-ok" id="mdp-deposit-proceed-btn">Proceed</button>
        </div>
      `,
    });

    const proceedBtn = document.getElementById("mdp-deposit-proceed-btn");
    const closeBtn = document.getElementById("mdp-deposit-close-btn");
    if (proceedBtn) proceedBtn.addEventListener("click", goToNonDues);
    if (closeBtn) closeBtn.addEventListener("click", closeOnly);

    clearTimer();
    timerId = setInterval(() => {
      if (cancelled || navigated) {
        clearTimer();
        return;
      }
      remaining -= 1;
      const el = document.getElementById("mdp-deposit-countdown");
      if (el) el.textContent = String(Math.max(remaining, 0));
      if (remaining <= 0) goToNonDues();
    }, 1000);
  }

  /* ---------- filter chips + search ---------- */
  function renderFilterChips() {
    const wrap = document.getElementById("mdp-filterchips");
    if (!wrap) return;
    const counts = { all: 0, paid: 0, partial: 0, unpaid: 0, exempt: 0 };
    document.querySelectorAll("#md-roster-body tr.mdp-row").forEach((row) => {
      counts.all += 1;
      counts[row.dataset.status] = (counts[row.dataset.status] || 0) + 1;
    });
    const defs = [
      ["all", "All Members"],
      ["paid", "Fully Paid"],
      ["partial", "Partial Paid"],
      ["unpaid", "Unpaid"],
      ["exempt", "Exempt"],
    ];
    wrap.innerHTML = defs.map(([key, label, dot, color]) => `
      <button type="button" class="mdp-filterchip ${state.filter === key ? "active" : ""}" onclick="mdpSetFilter('${key}')">
        ${label} (${counts[key] || 0})
      </button>`).join("");
  }

  window.mdpSetFilter = function (f) { state.filter = f; state.page = 1; renderFilterChips(); applyFilters(); };
  window.mdpSetSearch = function (v) { state.search = String(v == null ? "" : v).trim().toLowerCase(); state.page = 1; applyFilters(); };

  /* ---------- roster pagination: full roster stays in the DOM (so draft,
     totals, and whole-roster submit keep working); pages only control which
     filtered rows are visible. 50/page, global search + status filter. ----- */
  function mdRowMatches(row) {
    const matchStatus = state.filter === "all" || row.dataset.status === state.filter;
    const hay = ((row.dataset.name || "") + " " + (row.dataset.dept || "")).toLowerCase();
    const matchSearch = !state.search || hay.includes(state.search);
    return matchStatus && matchSearch;
  }
  function mdFilteredRows() {
    return [...document.querySelectorAll("#md-roster-body tr.mdp-row")].filter(mdRowMatches);
  }
  function mdPageCount(total) {
    const n = total != null ? total : mdFilteredRows().length;
    return Math.max(1, Math.ceil(n / state.perPage));
  }
  function ensurePagerEl() {
    let pager = document.getElementById("mdp-pager");
    if (pager) return pager;
    const wrap = document.getElementById("mdp-roster-wrap");
    pager = document.createElement("div");
    pager.id = "mdp-pager";
    if (wrap && wrap.parentElement) wrap.parentElement.insertBefore(pager, wrap.nextSibling);
    return pager;
  }
  function renderPager(total, pageCount) {
    const pager = ensurePagerEl();
    if (!pager) return;
    const rows = document.querySelectorAll("#md-roster-body tr.mdp-row").length;
    if (!rows) { pager.classList.add("mdp-hidden"); pager.innerHTML = ""; return; }
    pager.classList.remove("mdp-hidden");
    const start = total ? (state.page - 1) * state.perPage + 1 : 0;
    const end = Math.min(total, state.page * state.perPage);
    const maxBtns = 7;
    let first = Math.max(1, Math.min(state.page - Math.floor(maxBtns / 2), Math.max(1, pageCount - maxBtns + 1)));
    let last = Math.min(pageCount, first + maxBtns - 1);
    first = Math.max(1, Math.min(first, Math.max(1, last - maxBtns + 1)));
    // Unpaid-dues dots: a dot on a page number means that page holds at
    // least one member with unpaid dues (same page slices applyFilters shows).
    const filtered = mdFilteredRows();
    const pageHasUnpaid = (p) => filtered
      .slice((p - 1) * state.perPage, p * state.perPage)
      .some((row) => (Number(row.dataset.unpaidTotal) || 0) > 0.005);
    let btns = "";
    for (let p = first; p <= last; p++) {
      const hasUnpaid = pageHasUnpaid(p);
      const dot = hasUnpaid ? `<span class="mdp-pagebtn-dot" title="This page has member(s) with unpaid dues"></span>` : "";
      const label = `Page ${p}${hasUnpaid ? " — has member(s) with unpaid dues" : ""}`;
      btns += `<button type="button" class="mdp-pagebtn${p === state.page ? " active" : ""}" onclick="mdpSetPage(${p})" title="${label}">${p}${dot}</button>`;
    }
    pager.innerHTML = `
      <span class="mdp-pager-info">Showing ${start}–${end} of ${total} members · Page ${state.page} of ${pageCount}</span>
      <span class="mdp-pager-btns">
        <button type="button" class="mdp-pagebtn" onclick="mdpSetPage(1)" ${state.page <= 1 ? "disabled" : ""} title="First page">«</button>
        <button type="button" class="mdp-pagebtn" onclick="mdpPrevPage()" ${state.page <= 1 ? "disabled" : ""} title="Previous page">‹ Prev</button>
        ${btns}
        <button type="button" class="mdp-pagebtn" onclick="mdpNextPage()" ${state.page >= pageCount ? "disabled" : ""} title="Next page">Next ›</button>
        <button type="button" class="mdp-pagebtn" onclick="mdpSetPage(${pageCount})" ${state.page >= pageCount ? "disabled" : ""} title="Last page">»</button>
      </span>`;
  }
  window.mdpSetPage = function (p) {
    const count = mdPageCount();
    state.page = Math.min(Math.max(1, Number(p) || 1), count);
    applyFilters();
    const wrap = document.getElementById("mdp-roster-wrap");
    if (wrap) wrap.scrollTop = 0;
  };
  window.mdpNextPage = function () { window.mdpSetPage(state.page + 1); };
  window.mdpPrevPage = function () { window.mdpSetPage(state.page - 1); };
  function syncHeaderCheck(filtered) {
    const head = document.querySelector("#md-roster-table thead .mdp-check");
    if (!head) return;
    const active = (filtered || []).filter((r) => r.dataset.excluded !== "1");
    if (!active.length) { head.checked = false; head.indeterminate = false; return; }
    const checked = active.filter((r) => r.querySelector(".md-member-check")?.checked).length;
    head.checked = checked === active.length;
    head.indeterminate = checked > 0 && checked < active.length;
  }

  function applyFilters() {
    const allRows = [...document.querySelectorAll("#md-roster-body tr.mdp-row")];
    const filtered = allRows.filter(mdRowMatches);
    const pageCount = Math.max(1, Math.ceil(filtered.length / state.perPage));
    state.page = Math.min(Math.max(1, state.page || 1), pageCount);
    const inPage = new Set(filtered.slice((state.page - 1) * state.perPage, state.page * state.perPage));
    allRows.forEach((row) => {
      const showRow = inPage.has(row);
      row.style.display = showRow ? "" : "none";
      const detail = row.nextElementSibling;
      if (detail && detail.classList.contains("mdp-detail")) detail.style.display = showRow && row.dataset.open === "1" ? "" : "none";
    });
    let emptyEl = document.getElementById("mdp-filter-empty");
    if (filtered.length === 0 && allRows.length) {
      if (!emptyEl) {
        emptyEl = document.createElement("tr");
        emptyEl.id = "mdp-filter-empty";
        emptyEl.innerHTML = `<td colspan="12" class="mdp-empty">No members match the current search / filter.</td>`;
        document.getElementById("md-roster-body").appendChild(emptyEl);
      }
      emptyEl.style.display = "";
    } else if (emptyEl) {
      emptyEl.style.display = "none";
    }
    renderPager(filtered.length, pageCount);
    syncHeaderCheck(filtered);
  }

  window.mdpToggleDetail = function (btn) {
    const row = btn.closest(".mdp-row");
    if (!row) return;
    const open = row.dataset.open === "1";
    row.dataset.open = open ? "0" : "1";
    btn.classList.toggle("open", !open);
    const icon = btn.querySelector("i");
    if (icon) icon.className = `fa-solid fa-chevron-${open ? "down" : "up"}`;
    const detail = row.nextElementSibling;
    if (detail && detail.classList.contains("mdp-detail")) detail.style.display = open ? "none" : "";
    
    // Update the icon in the outstanding cell as well
    const outstandingCell = row.querySelector(".mdp-outstanding-cell");
    if (outstandingCell) {
      const outstandingIcon = outstandingCell.querySelector("i");
      if (outstandingIcon) {
        outstandingIcon.className = `fa-solid fa-chevron-${open ? "down" : "up"}`;
      }
    }
  };
  
  // Initialize outstanding cell click handlers and icons
  function initializeOutstandingCells() {
    document.querySelectorAll("#md-roster-body tr.mdp-row").forEach((row) => {
      const outstandingCell = row.querySelector(".mdp-outstanding-cell");
      if (outstandingCell) {
        outstandingCell.onclick = function() {
          const expandBtn = row.querySelector(".mdp-expand-btn");
          if (expandBtn) mdpToggleDetail(expandBtn);
        };
        
        // Set initial icon state based on whether row is open
        const open = row.dataset.open === "1";
        const outstandingIcon = outstandingCell.querySelector("i");
        if (outstandingIcon) {
          outstandingIcon.className = `fa-solid fa-chevron-${open ? "up" : "down"}`;
        }
      }
    });
  }

  window.mdpSetTab = function (tab) {
    const record = document.getElementById("mdp-tab-record");
    const viewonly = document.getElementById("mdp-tab-viewonly");
    const bR = document.getElementById("mdp-tabbtn-record");
    const bV = document.getElementById("mdp-tabbtn-viewonly");
    if (!record || !bR) return;
    record.style.display = tab === "record" ? "" : "none";
    if (viewonly) viewonly.style.display = tab === "viewonly" ? "" : "none";
    bR.classList.toggle("active", tab === "record");
    if (bV) bV.classList.toggle("active", tab === "viewonly");
    if (tab === "viewonly") mdpLoadViewOnly();
  };

  /* ---------- view-only tab (final-approved months) ---------- */
  window.mdpLoadViewOnly = async function mdpLoadViewOnly() {
    const assessmentId = state.voAssessmentId;
    const tbody = document.getElementById("md-viewonly-body");
    const info = document.getElementById("mdp-viewonly-info");
    const foot = document.getElementById("mdp-viewonly-foot");
    if (!tbody || !info) return;
    const voWrap = tbody.closest(".mdp-tablewrap");
    if (voWrap) voWrap.querySelectorAll(":scope > .md-vo-detail").forEach((p) => p.remove());
    if (!assessmentId) {
      tbody.innerHTML = `<tr><td colspan="7" class="mdp-empty">No final-approved months yet.</td></tr>`;
      info.innerHTML = "";
      if (foot) foot.style.display = "none";
      return;
    }
    try {
      const resp = await fetch(`/api/treasurer/deductions/members/${assessmentId}/`, { cache: "no-store" });
      const data = await resp.json();
      if (!data.ok) { toast(data.error || "Failed to load the approved month.", true); return; }
      const members = (data.members || []).filter((m) => m.recorded_actual != null);
      members.sort((a, b) => String(a.member_name).localeCompare(String(b.member_name), "en", { sensitivity: "base" }));

      let totalDeducted = 0, totalBalance = 0;
      state.voByMember = {};
      tbody.innerHTML = members.map((m, index) => {
        const actual = Number(m.recorded_actual) || 0;
        const balance = Number(m.recorded_outstanding) || 0;
        totalDeducted += actual; totalBalance += balance;
        const pay = actual <= 0 ? "unpaid" : (balance > 0 ? "partial" : "paid");
        // Kept for the on-demand breakdown: mdToggleVoDetail builds the
        // per-item panel right under the clicked row when it is opened.
        state.voByMember[m.member_id] = m;

        return `<tr class="md-vo-row" data-member-id="${m.member_id}" onclick="mdToggleVoDetail(${m.member_id}, this)" style="cursor:pointer;" title="Click to see the per-item payment breakdown">
          <td style="text-align:center; color:#8a949e; font-size:0.75rem; font-variant-numeric:tabular-nums;">${index + 1}</td>
          <td><div class="mdp-name">${esc(m.member_name)}</div><small style="color:#8a949e;">${esc(m.employee_id || "")}</small></td>
          <td style="color:#475569;">${esc(m.department || "—")}</td>
          <td style="text-align:right; font-weight:700; font-variant-numeric:tabular-nums;">${PESO(actual)}</td>
          <td style="text-align:right; font-variant-numeric:tabular-nums; ${balance > 0 ? "color:#c62828; font-weight:700;" : "color:#2e7d32;"}">${PESO(balance)}</td>
        </tr>`;
      }).join("") || `<tr><td colspan="5" class="mdp-empty">No deductions were recorded for this month.</td></tr>`;

      info.innerHTML = `
        <span>Month: <strong>${esc(data.assessment.month_label)}</strong></span>
        <span>Expected Collection per member: <strong>${PESO(data.assessment.total_amount)}</strong></span>
        <span>Members: <strong>${members.length}</strong></span>`;
      if (foot) {
        foot.style.display = "";
        foot.innerHTML = `Total collected: <strong>${PESO(totalDeducted)}</strong> · Total unpaid balance: <strong>${PESO(totalBalance)}</strong>`;
      }
    } catch (e) {
      console.error("Failed to load view-only month", e);
      toast("Failed to load the approved month.", true);
    }
  };

  /* Show/hide a member's per-item payment breakdown in Pending Audit. The panel
     is pinned — using the clicked row's live on-screen coordinates — directly
     beneath that member's row, and an invisible spacer pushes the rows below
     down so nothing gets covered. Clicking the same member again closes it;
     clicking another member moves it there. */
  window.mdToggleVoDetail = function mdToggleVoDetail(memberId, anchor) {
    const body = document.getElementById("md-viewonly-body");
    if (!body) return;
    const row = anchor && anchor.closest
      ? anchor.closest("tr")
      : body.querySelector(`tr.md-vo-row[data-member-id="${memberId}"]`);
    if (!row) return;
    const key = row.dataset.memberId;
    const wrap = body.closest(".mdp-tablewrap") || body.parentElement;
    const existing = wrap.querySelector(":scope > .md-vo-detail");
    if (existing && existing.dataset.for === key) {
      existing.remove();
      const oldSpacer = body.querySelector(`tr.md-vo-spacer[data-for="${key}"]`);
      if (oldSpacer) oldSpacer.remove();
      return;
    }
    if (existing) existing.remove();
    body.querySelectorAll("tr.md-vo-spacer").forEach((tr) => tr.remove());
    const m = (state.voByMember || {})[key] || {};
    const allocs = m.recorded_allocations || [];
    const allocLines = allocs.length ? allocs.map((a, index) => `${index ? '<div class="md-vo-detail-divider"></div>' : ""}
        <div class="md-vo-detail-cell md-vo-detail-item">${esc(a.purpose_label)}${a.recipient ? `<span class="md-vo-detail-recipient">For: ${esc(a.recipient)}</span>` : ""}</div>
        <div class="md-vo-detail-cell md-vo-detail-money"><span style="color:#8a949e;">Paid </span><strong style="color:#1b5e20;">${PESO(a.applied)}</strong></div>
        <div class="md-vo-detail-cell md-vo-detail-money"><span style="color:#8a949e;">Of </span>${PESO(a.required)}</div>
        <div class="md-vo-detail-cell md-vo-detail-result" style="${a.remaining > 0 ? "color:#c62828;" : "color:#2e7d32;"}">${a.remaining > 0 ? PESO(a.remaining) + " unpaid" : "Paid"}</div>`).join("")
      : `<div class="md-vo-detail-cell" style="grid-column:1 / -1; color:#8a949e;">No deduction was recorded for this member this month.</div>`;
    const priorReq = Number(m.recorded_prior_outstanding) || 0;
    const priorCol = Number(m.recorded_prior_collected) || 0;
    const priorLine = priorReq > 0 ? `
      <div class="md-vo-detail-divider"></div>
      <div class="md-vo-detail-cell md-vo-detail-item">Prior balance${m.recorded_prior_month ? ` (${esc(m.recorded_prior_month)})` : ""}</div>
      <div class="md-vo-detail-cell md-vo-detail-money"><span style="color:#8a949e;">Paid </span><strong style="color:#1b5e20;">${PESO(priorCol)}</strong></div>
      <div class="md-vo-detail-cell md-vo-detail-money"><span style="color:#8a949e;">Of </span>${PESO(priorReq)}</div>
      <div class="md-vo-detail-cell md-vo-detail-result" style="${priorReq - priorCol > 0 ? "color:#c62828;" : "color:#2e7d32;"}">${priorReq - priorCol > 0 ? PESO(priorReq - priorCol) + " still owed" : "Paid"}</div>` : "";
    const panel = document.createElement("div");
    panel.className = "md-vo-detail";
    panel.dataset.for = key;
    panel.style.cssText = "position:absolute; left:0; right:0; z-index:5; background:#fafcfa; border-top:1px solid #eef1ee; border-bottom:1px solid #eef1ee; padding:10px 16px;";
    panel.innerHTML = `
      <div style="font-size:0.76rem; font-weight:700; color:#1b5e20; margin-bottom:6px;">WHAT ${esc(String(m.member_name || "").toUpperCase())} PAID THIS MONTH</div>
      <div class="md-vo-detail-grid">
        <div class="md-vo-detail-head">Item</div><div class="md-vo-detail-head">Paid</div><div class="md-vo-detail-head">Required</div><div class="md-vo-detail-head" style="text-align:right;">Status</div>
        ${allocLines}${priorLine}
      </div>`;
    wrap.style.position = "relative";
    wrap.appendChild(panel);
    // Reserve the panel's height right after the clicked row so the members
    // below stay visible instead of being covered.
    const spacer = document.createElement("tr");
    spacer.className = "md-vo-spacer";
    spacer.dataset.for = key;
    spacer.innerHTML = `<td colspan="6" style="padding:0; border:none; height:${panel.offsetHeight}px; background:#fafcfa;"></td>`;
    // insertBefore (not .after()) — some browser extensions/older engines
    // replace .after() with a broken version that inserts at the top, which
    // is exactly what scattered these rows to the top of the table.
    row.parentNode.insertBefore(spacer, row.nextSibling);
    const wrapRect = wrap.getBoundingClientRect();
    const rowRect = row.getBoundingClientRect();
    const panelTop = rowRect.bottom - wrapRect.top + wrap.scrollTop;
    panel.style.top = panelTop + "px";
    const panelBottom = panelTop + panel.offsetHeight;
    if (panelBottom > wrap.scrollTop + wrap.clientHeight) {
      wrap.scrollTop = panelBottom - wrap.clientHeight + 6;
    }
  };

  /* ---------- transmittal letter + deducted amount sheet (PDF) ---------- */
  window.mdpDownloadSheet = function mdpDownloadSheet(source) {
    let assessmentId = null;
    if (source === "viewonly") {
      assessmentId = state.voAssessmentId || null;
    } else {
      const select = document.getElementById("md-month-select");
      assessmentId = select ? select.value : null;
    }
    if (!assessmentId) { toast("Select a month first.", true); return; }
    window.open(`/api/officers/deductions/sheet-pdf/${assessmentId}/`, "_blank");
  };

  window.mdpRefresh = function () {
    state.assessmentId = null;
    loadMdOverviews();
  };

  async function mdPostCatchup(body) {
    const resp = await fetch("/api/treasurer/deductions/catch-up/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      credentials: "same-origin",
      body: JSON.stringify(body),
    });
    let data = null;
    try { data = await resp.json(); } catch (e) { data = null; }
    if (!resp.ok || !data || !data.ok) {
      throw new Error((data && (data.error || data.message)) || `Could not create the missing dues rows (${resp.status})`);
    }
    return data;
  }

  window.mdGenerateCatchup = async function mdGenerateCatchup(memberId) {
    if (!state.flags.requireBackDues) { toast("Back-dues chase is disabled — members pay current dues forward."); return; }
    try {
      const data = await mdPostCatchup({ member_ids: [Number(memberId)] });
      toast(data.message || "Missing dues rows created.");
      if (typeof window.loadMdOverviews === "function") await window.loadMdOverviews();
      else if (typeof window.mdLoadRoster === "function") await window.mdLoadRoster();
    } catch (err) {
      toast(err.message || "Failed to create the missing dues rows.", true);
    }
  };

  window.mdGenerateCatchupAll = async function mdGenerateCatchupAll() {
    if (!state.flags.requireBackDues) { toast("Back-dues chase is disabled — members pay current dues forward."); return; }
    try {
      const data = await mdPostCatchup({ all_pending: true });
      toast(data.message || "Missing dues rows created.");
      if (typeof window.loadMdOverviews === "function") await window.loadMdOverviews();
      else if (typeof window.mdLoadRoster === "function") await window.mdLoadRoster();
    } catch (err) {
      toast(err.message || "Failed to create the missing dues rows.", true);
    }
  };

  /* ---------- year tracker: per-member Jan–Dec grid for one explicit year.
     The year defaults to the selected assessment month (never the machine
     clock); late joiners owe from their join month, earlier cells read n/a. */
  const YT_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const YT_DOT = {
    paid: "#2e7d32", partial: "#e65100", unpaid: "#c62828", missing: "#c62828",
    na: "#bdbdbd", no_assessment: "#e0e0e0",
  };
  const YT_LABEL = {
    paid: "Paid", partial: "Partial", unpaid: "Unpaid", missing: "No record",
    na: "n/a", no_assessment: "No collection",
  };

  function mdTrackerDefaultYear() {
    const current = (state.activeAssessments || []).find(
      (a) => String(a.assessment_id) === String(state.assessmentId)
    ) || (state.activeAssessments || [])[0];
    const iso = current && current.month ? String(current.month).slice(0, 4) : "";
    return /^\d{4}$/.test(iso) ? iso : "";
  }

  window.mdOpenYearTracker = async function mdOpenYearTracker() {
    const prev = document.getElementById("mdYearTrackerModal");
    if (prev) prev.remove();
    const overlay = document.createElement("div");
    overlay.id = "mdYearTrackerModal";
    overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,0.45);z-index:9999;display:flex;align-items:center;justify-content:center;";
    overlay.innerHTML = `
      <div style="background:#fff;border-radius:14px;width:min(1060px,96vw);max-height:92vh;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,0.3);">
        <div style="padding:14px 18px;border-bottom:1px solid #eef1ee;display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
          <div style="font-weight:800;color:#1b5e20;font-size:1rem;">Year Tracker</div>
          <div style="font-size:0.76rem;color:#757575;">Paid since January — new members owe from their join month</div>
          <select id="md-yt-year" onchange="mdLoadYearTracker(this.value)" style="margin-left:auto;padding:7px 10px;border:1px solid #cfdccc;border-radius:8px;font-size:0.82rem;"></select>
          <button type="button" class="mdp-btn" onclick="document.getElementById('mdYearTrackerModal').remove()">Close</button>
        </div>
        <div id="md-yt-body" style="padding:12px 18px;overflow:auto;"><div class="empty-state">Loading…</div></div>
        <div style="padding:8px 18px 12px;border-top:1px solid #eef1ee;font-size:0.72rem;color:#757575;display:flex;gap:14px;flex-wrap:wrap;">
          <span><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${YT_DOT.paid};margin-right:4px;"></i>Paid</span>
          <span><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${YT_DOT.partial};margin-right:4px;"></i>Partial</span>
          <span><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${YT_DOT.unpaid};margin-right:4px;"></i>Unpaid / missing</span>
          <span><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${YT_DOT.na};margin-right:4px;"></i>n/a (not yet joined / retired)</span>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
    window.mdLoadYearTracker(mdTrackerDefaultYear());
  };

  window.mdLoadYearTracker = async function mdLoadYearTracker(year) {
    const body = document.getElementById("md-yt-body");
    const sel = document.getElementById("md-yt-year");
    if (body) body.innerHTML = '<div class="empty-state">Loading…</div>';
    try {
      const res = await fetch(`/api/treasurer/deductions/year-tracker/${year ? `?year=${encodeURIComponent(year)}` : ""}`, { credentials: "same-origin" });
      const d = await res.json();
      if (!res.ok || !d.ok) throw new Error(d.error || "Could not load the tracker.");
      if (sel) {
        const years = d.available_years && d.available_years.length ? d.available_years : [d.year];
        sel.innerHTML = years.map((y) => `<option value="${y}"${String(y) === String(d.year) ? " selected" : ""}>${y}</option>`).join("");
      }
      const members = d.members || [];
      const head = `<tr><th style="position:sticky;left:0;background:#fff;text-align:left;min-width:170px;">Member</th>`
        + YT_MONTHS.map((m) => `<th style="min-width:44px;">${m}</th>`).join("")
        + `<th style="min-width:86px;">Paid / Open</th></tr>`;
      const rows = members.map((m) => {
        const cells = m.months.map((c) => {
          const tip = c.status === "paid" || c.status === "partial" || c.status === "unpaid"
            ? `${YT_LABEL[c.status]} — req ${PESO(c.required)} · paid ${PESO(c.paid_amount)} · bal ${PESO(c.balance)}`
            : c.status === "missing" ? `No record — collection ${PESO(c.required)}` : YT_LABEL[c.status];
          const glyph = (c.status === "na" || c.status === "no_assessment") ? "–" : "●";
          return `<td title="${esc(tip)}" style="color:${YT_DOT[c.status] || "#757575"};font-size:${glyph === "●" ? "0.85rem" : "0.8rem"};">${glyph}</td>`;
        }).join("");
        return `<tr><td style="position:sticky;left:0;background:#fff;text-align:left;"><b>${esc(m.member_name)}</b><div style="font-size:0.68rem;color:#8a949e;">${esc(m.department || "")}</div></td>${cells}<td style="font-variant-numeric:tabular-nums;"><b style="color:#2e7d32;">${m.paid_count}</b> / <b style="color:#c62828;">${m.open_count}</b></td></tr>`;
      }).join("");
      if (body) {
        body.innerHTML = members.length
          ? `<div style="overflow:auto;"><table class="data" style="border-collapse:collapse;width:100%;text-align:center;font-size:0.78rem;"><thead>${head}</thead><tbody>${rows}</tbody></table></div>`
          : '<div class="empty-state">No members to track.</div>';
      }
    } catch (e) {
      if (body) body.innerHTML = `<div class="empty-state">${esc(e.message || "Could not load the tracker.")}</div>`;
    }
  };

  /* ---------- selection + allocation engine ---------- */
  window.mdToggleAll = function mdToggleAll(masterChecked) {
    // Paginated: header Select-All applies to ALL filtered members across
    // every page (not just the visible page), keeping whole-roster submit.
    const rows = mdFilteredRows();
    rows.forEach((row) => {
      const memberCheck = row.querySelector(".md-member-check");
      const excluded = row.dataset.excluded === "1";
      if (memberCheck) {
        memberCheck.disabled = excluded;
        memberCheck.checked = excluded ? false : masterChecked;
      }
      if (masterChecked && !excluded) {
        const input = row.querySelector(".md-actual-input");
        if (input) input.value = (Number(row.dataset.standard) || 0).toFixed(2);
        row.dataset.manual = "0";
      } else if (!masterChecked) {
        const input = row.querySelector(".md-actual-input");
        if (input) input.value = "0.00";
        row.querySelectorAll(".md-item-amount-input").forEach((amountInput) => {
          amountInput.value = "0.00";
        });
        row.dataset.manual = "0";
        mdUpdateUnpaidPanel(row);
      }
    });
    // Refresh first so chip-based rows become item inputs before amounts are
    // distributed across them.
    mdRefreshRow();
    if (masterChecked) {
      rows.forEach((row) => {
        if (row.dataset.excluded !== "1") mdAutoDistributeItems(row);
      });
      mdRefreshRow();
    }
  };

  window.mdToggleMember = function mdToggleMember(checkbox) {
    const row = checkbox.closest(".mdp-row");
    if (!row || row.dataset.excluded === "1") return;
    const input = row.querySelector(".md-actual-input");
    if (checkbox.checked) {
      if (input) input.value = (Number(row.dataset.standard) || 0).toFixed(2);
      row.dataset.manual = "0";
      mdRefreshRow(row);
      mdAutoDistributeItems(row);
      mdRefreshRow(row);
      return;
    }
    if (input) input.value = "0.00";
    row.querySelectorAll(".md-item-amount-input").forEach((amountInput) => {
      amountInput.value = "0.00";
    });
    row.dataset.manual = "0";
    mdUpdateUnpaidPanel(row);
    mdRefreshRow(row);
  };

  /* Header quick-fill: "Total" button under the Total Collected thead.
     When called with no amount, each ACTIVE row gets its own supposed total
     (this month's standard assessment + ticked unpaid balance) so every
     member is filled Paid. When called with a fixed amount (legacy), every
     row gets that amount. Active = row not excluded and input enabled.
     Member checkboxes are ticked so the filled rows actually record
     (unchecked rows settle nothing). Mirrors mdToggleAll: refresh first,
     distribute across items, refresh again. */
  window.mdFillAllCollected = function mdFillAllCollected(amount) {
    const hasFixed = amount !== undefined && amount !== null && String(amount).trim() !== "";
    const fixedValue = hasFixed ? (Number(amount) || 0).toFixed(2) : null;
    // Paginated: Total fill applies to ALL filtered members across pages.
    const rows = mdFilteredRows();
    rows.forEach((row) => {
      if (row.dataset.excluded === "1") return;
      const input = row.querySelector(".md-actual-input");
      if (!input || input.disabled || input.readOnly) return;
      if (fixedValue !== null) {
        input.value = fixedValue;
      } else {
        const standard = Number(row.dataset.standard) || 0;
        const tickedUnpaid = (typeof mdSelectedUnpaidTotal === "function")
          ? mdSelectedUnpaidTotal(row)
          : (Number(row.dataset.unpaidTotal) || Number(row.dataset.prior) || 0);
        input.value = (standard + tickedUnpaid).toFixed(2);
      }
      row.dataset.manual = "0";
      const memberCheck = row.querySelector(".md-member-check");
      if (memberCheck && !memberCheck.disabled) memberCheck.checked = true;
    });
    mdRefreshRow();
    rows.forEach((row) => {
      if (row.dataset.excluded !== "1") mdAutoDistributeItems(row);
    });
    mdRefreshRow();
  };

  /* Allocation settings card (below the workflow history).
     A Total Collected box plus one amount box per assessment item,
     prefilled with the item's standard amount. Apply pushes those amounts
     onto every SELECTED member row (ticked, non-excluded, editable) — same
     row inputs the submit reads, so totals, statuses, the summary bar and
     the roster draft all follow through the normal mdRefreshRow() path.
     Total Collected is optional: blank keeps each row's own collection. */
  function renderAllocSettings(items) {
    const host = document.getElementById("mdp-alloc-settings");
    if (!host) return;
    state.allocItems = Array.isArray(items) ? items : [];
    if (!state.recordable || !state.allocItems.length) {
      host.innerHTML = "";
      hide("mdp-alloc-settings");
      return;
    }
    const fields = state.allocItems.map((item) => {
      const id = Number(item.item_id) || 0;
      const label = mdChipLabel(item);
      const standard = Number(item.amount) || 0;
      return `<div class="mdp-alloc-field">
        <label for="md-alloc-${id}" title="${esc(label)} — standard ${PESO(standard)}">${esc(label)} <span class="mdp-alloc-max">· max ${PESO(standard)}</span></label>
        <input type="number" id="md-alloc-${id}" class="mdp-alloc-input" data-alloc-item-id="${id}" min="0" max="${standard}" step="0.01" value="${standard.toFixed(2)}" oninput="mdAllocUpdateHint()" onkeydown="if(event.key==='Enter'){event.preventDefault();mdApplyAllocToSelected();}" />
      </div>`;
    }).join("");
    host.innerHTML = `
      <div class="mdp-card mdp-alloc-card">
        <div class="mdp-alloc-head">
          <div>
            <h3 class="mdp-alloc-title"><span class="mdp-alloc-title-ico"><i class="fa-solid fa-sliders"></i></span>Allocation Settings</h3>
            <p class="mdp-alloc-sub">Set the per-item amounts once, then apply them to <strong id="mdp-alloc-count">0 selected members</strong>. Only ticked, non-excluded rows are updated; rows whose collection cannot cover the split are clamped at submit.</p>
          </div>
          <div class="mdp-alloc-actions">
            <button type="button" class="mdp-btn" onclick="mdResetAllocSettings()" title="Restore each box to its standard item amount">Reset</button>
            <button type="button" class="mdp-btn mdp-btn-primary" onclick="mdApplyAllocToSelected()" title="Write these amounts onto every selected member's collection and item boxes">Apply to Selected</button>
          </div>
        </div>
        <div class="mdp-alloc-grid">
          <div class="mdp-alloc-field mdp-alloc-field-lead">
            <label for="md-alloc-total" title="Total Collected written onto every selected row — leave blank to keep each member's current collection">Total Collected <span class="mdp-alloc-max">· blank = keep</span></label>
            <input type="number" id="md-alloc-total" class="mdp-alloc-input" min="0" step="0.01" placeholder="Keep current" onkeydown="if(event.key==='Enter'){event.preventDefault();mdApplyAllocToSelected();}" />
          </div>
          ${fields}
        </div>
        <div class="mdp-alloc-hint">Items total: <strong id="mdp-alloc-sum">₱0.00</strong> — set Total Collected to at least this plus each member's unpaid balance.</div>
      </div>`;
    show("mdp-alloc-settings");
    mdUpdateAllocCount();
    mdAllocUpdateHint();
  }

  function mdUpdateAllocCount() {
    const el = document.getElementById("mdp-alloc-count");
    if (!el) return;
    let selected = 0;
    document.querySelectorAll("#md-roster-body tr.mdp-row").forEach((row) => {
      const check = row.querySelector(".md-member-check");
      if (check && check.checked && !check.disabled && row.dataset.excluded !== "1") selected += 1;
    });
    el.textContent = `${selected} selected member${selected === 1 ? "" : "s"}`;
  }

  window.mdAllocUpdateHint = function mdAllocUpdateHint() {
    const host = document.getElementById("mdp-alloc-settings");
    const el = document.getElementById("mdp-alloc-sum");
    if (!host || !el) return;
    let sum = 0;
    host.querySelectorAll(".mdp-alloc-input[data-alloc-item-id]").forEach((inp) => {
      sum += Math.max(0, parseFloat(inp.value) || 0);
    });
    el.textContent = PESO(sum);
  };

  window.mdResetAllocSettings = function mdResetAllocSettings() {
    const host = document.getElementById("mdp-alloc-settings");
    if (!host || !state.allocItems) return;
    const standardById = new Map(state.allocItems.map((item) => [String(Number(item.item_id) || 0), Number(item.amount) || 0]));
    host.querySelectorAll(".mdp-alloc-input[data-alloc-item-id]").forEach((inp) => {
      const standard = standardById.get(String(inp.dataset.allocItemId)) || 0;
      inp.max = standard;
      inp.value = standard.toFixed(2);
    });
    const totalInp = host.querySelector("#md-alloc-total");
    if (totalInp) totalInp.value = "";
    mdAllocUpdateHint();
  };

  window.mdApplyAllocToSelected = function mdApplyAllocToSelected() {
    const host = document.getElementById("mdp-alloc-settings");
    if (!host) return;
    const settings = {};
    host.querySelectorAll(".mdp-alloc-input[data-alloc-item-id]").forEach((inp) => {
      settings[String(inp.dataset.allocItemId)] = Math.max(0, parseFloat(inp.value) || 0);
    });
    // Total Collected is optional: filled → written onto every selected row
    // first (so the split below has funds); blank → each row keeps its own.
    const totalInp = host.querySelector("#md-alloc-total");
    const totalRaw = totalInp ? String(totalInp.value).trim() : "";
    const totalValue = totalRaw === "" ? null : Math.max(0, parseFloat(totalRaw) || 0);
    // Same selectable-row definition as the submit path: ticked,
    // non-excluded, editable rows (retired/locked rows are skipped).
    const rows = mdFilteredRows().filter((row) => {
      const check = row.querySelector(".md-member-check");
      return check && check.checked && !check.disabled &&
        row.dataset.excluded !== "1" && row.dataset.readonly !== "1";
    });
    if (!rows.length) {
      toast("Select at least one member first (tick their checkboxes).", true);
      return;
    }
    let touched = 0;
    rows.forEach((row) => {
      let changed = false;
      if (totalValue !== null) {
        const actual = row.querySelector(".md-actual-input");
        if (actual && !actual.disabled && !actual.readOnly) {
          actual.value = totalValue.toFixed(2);
          changed = true;
        }
      }
      row.querySelectorAll(".md-item-amount-input").forEach((inp) => {
        if (inp.disabled || inp.dataset.required === "0") return;
        const value = settings[String(inp.dataset.itemId)];
        if (value === undefined) return;
        const max = Number(inp.dataset.max) || 0;
        inp.value = Math.min(value, max).toFixed(2);
        changed = true;
      });
      if (changed) {
        // Manual split, like a chip toggle: kept verbatim by refresh and
        // submitted as this row's item_amounts.
        row.dataset.manual = "1";
        touched += 1;
      }
    });
    // One refresh recalculates every row (clamping to each row's available
    // funds), updates totals + statuses, and persists the roster draft.
    mdRefreshRow();
    mdUpdateAllocCount();
    if (touched) {
      let msg = `Allocation applied to ${touched} selected member${touched === 1 ? "" : "s"}`;
      if (totalValue !== null) msg += ` with Total Collected ${PESO(totalValue)}`;
      toast(msg + ".");
    } else toast("No editable boxes on the selected rows.", true);
  };

  /* Item funding order: every item keeps its column order, but the Monthly
     Due is funded LAST. When the collection cannot cover the whole month
     (the outstanding unpaid dues are settled first), the Monthly Due shrinks
     to whatever is left — or to zero and carry over — instead of squeezing
     the medical aid or other assessments. Array#sort is stable, so the other
     items keep their relative order. */
  function mdPriorityOrder(nodes) {
    return [...nodes].sort((a, b) =>
      ((a.dataset && a.dataset.purpose === "monthly_due") ? 1 : 0) -
      ((b.dataset && b.dataset.purpose === "monthly_due") ? 1 : 0)
    );
  }

  function mdAutoDistributeItems(row) {
    const input = row.querySelector(".md-actual-input");
    const itemInputs = mdPriorityOrder(row.querySelectorAll(".md-item-amount-input"));
    if (!input || !itemInputs.length) return;
    const collected = Math.max(0, parseFloat(input.value) || 0);
    // Items only receive what is left after the ticked unpaid months are
    // settled — a dues-only collection funds no items while arrears remain.
    let allowance = Math.max(0, collected - mdPriorFor(row, collected));
    itemInputs.forEach((itemInput) => {
      const maximum = Number(itemInput.dataset.max) || 0;
      const amount = Math.min(maximum, allowance);
      itemInput.value = amount.toFixed(2);
      allowance -= amount;
    });
  }

  window.mdHandleAmountKeydown = function mdHandleAmountKeydown(event, input) {
    if (!["Enter", "ArrowDown", "ArrowUp"].includes(event.key)) return;
    event.preventDefault();
    const inputs = [...document.querySelectorAll("#md-roster-body .md-actual-input:not([disabled]):not([readonly])")];
    const currentIndex = inputs.indexOf(input);
    if (currentIndex < 0) return;
    const direction = event.key === "ArrowUp" || (event.key === "Enter" && event.shiftKey) ? -1 : 1;
    const next = inputs[currentIndex + direction];
    if (next) {
      next.focus();
      next.select();
    }
  };

  window.mdToggleExclude = function mdToggleExclude(checkbox) {
    const row = checkbox.closest(".mdp-row");
    if (!row || row.dataset.readonly === "1") return;
    const memberCheck = row.querySelector(".md-member-check");
    const input = row.querySelector(".md-actual-input");
    const itemInputs = [...row.querySelectorAll(".md-item-amount-input")];
    const excluding = checkbox.checked;
    row.dataset.excluded = excluding ? "1" : "0";
      saveRosterDraft();
    row.dataset.manual = excluding ? "1" : "0";
    if (memberCheck) {
      memberCheck.checked = excluding ? false : memberCheck.checked;
      memberCheck.disabled = excluding;
    }
    if (input) {
      input.value = "0.00";
      input.disabled = excluding;
      row.dataset.base = (Number(row.dataset.standard) || 0).toFixed(2);
    }
    // Excluded members keep their calculated balance visible but settle no
    // unpaid months while they are outside this deduction batch.
    row.querySelectorAll(".mdp-unpaid-check, .mdp-unpaid-groupcheck, .mdp-unpaid-selectall, .mdp-unpaid-amount-input").forEach((cb) => { cb.disabled = excluding; });
    mdUpdateUnpaidPanel(row);
    itemInputs.forEach((itemInput) => {
      itemInput.disabled = excluding || itemInput.dataset.required === "0";
      itemInput.value = "0.00";
    });
    row.querySelectorAll(".md-item-chip").forEach((chip) => styleItemChip(chip, false));
    mdRefreshRow(row);
  };

  function styleItemChip(chip, covered) {
    chip.dataset.selected = covered ? "1" : "0";
    chip.style.background = covered ? "#e8f5e9" : "#ffffff";
    chip.style.border = `2px solid ${covered ? "#a5d6a7" : "#dde3dd"}`;
    chip.style.color = covered ? "#1b5e20" : "#374151";
    chip.style.boxShadow = covered ? "0 2px 8px rgba(46,125,50,0.15)" : "none";
    const icon = chip.querySelector("i");
    if (icon) icon.className = `fa-solid ${covered ? "fa-circle-check" : "fa-circle"}`;
    const amountSpan = chip.querySelector("span:last-child");
    if (amountSpan) amountSpan.style.color = covered ? "#1b5e20" : "#2e7d32";
  }

  // Clicking a chip manually overrides which items were funded for that
  // member — without touching the typed amount. If the selected items would
  // cost more than the money available, the click is refused with a warning.
  window.mdToggleChip = function mdToggleChip(chip) {
    const row = chip.closest(".mdp-row") || chip.closest("tr");
    if (!row || row.dataset.readonly === "1") return;
    const wasSelected = chip.dataset.selected === "1";
    const collected = parseFloat(row.querySelector(".md-actual-input")?.value) || 0;
    // Items can only claim what the collection has left after the ticked
    // unpaid months are settled.
    const funds = Math.max(0, collected - mdPriorFor(row, collected));

    let selectedTotal = 0;
    row.querySelectorAll(".md-item-chip").forEach((other) => {
      if (other === chip) return;
      if (other.dataset.selected === "1") selectedTotal += Number(other.dataset.itemAmount) || 0;
    });
    if (!wasSelected) selectedTotal += Number(chip.dataset.itemAmount) || 0;
    if (selectedTotal > funds + 0.005) {
      toast(`Can't select ${PESO(Number(chip.dataset.itemAmount))}: the selected items would cost more than the ${PESO(funds)} left for this month's items. Increase the deduction or untick unpaid months first.`, true);
      return;
    }

    row.dataset.manual = "1";
    styleItemChip(chip, !wasSelected);
    mdRefreshRow(row);
  };

  // Refresh one row (or all). Typing an amount returns the row to automatic
  // priority allocation; a manually-set row stays manual until then.
  /* ---------- partial rows: per-item manual distribution ----------
     When the amount deducted does not fully cover the month, the item
     checkboxes give way to a small amount input per item — the treasurer
     types exactly how much lands on each one. Paying the full month swaps
     back to the checked chips. */
  function mdConvertRowToInputs(row) {
    const container = row.querySelector(".mdp-chips");
    if (!container) return;
    if (!row.__chipsHtml) row.__chipsHtml = container.innerHTML;
    const chips = [...container.querySelectorAll(".md-item-chip")];
    const funds = parseFloat(row.querySelector(".md-actual-input")?.value) || 0;
    const manual = row.dataset.manual === "1";
    let remaining = Math.max(0, funds - mdPriorFor(row, funds));
    // Allocate in priority order — Monthly Due LAST — so a shortfall shrinks
    // the due (carry-over) instead of the other assessments. The HTML below
    // still maps chips in visual (column) order.
    const values = new Map();
    mdPriorityOrder(chips).forEach((chip) => {
      const max = Number(chip.dataset.itemAmount) || 0;
      let value = 0;
      if (manual) {
        value = chip.dataset.selected === "1" ? max : 0;
      } else if (max > 0 && remaining >= max - 0.005) {
        value = max;
      }
      if (value > 0) remaining -= value;
      values.set(chip, value);
    });
    container.innerHTML = chips.map((chip) => {
      const id = Number(chip.dataset.itemId) || 0;
      const max = Number(chip.dataset.itemAmount) || 0;
      const purpose = chip.dataset.purpose || "";
      const value = values.get(chip) || 0;
      const name = (chip.querySelector("span")?.textContent || "").trim();
      const locked = chip.dataset.required === "0";
      return `<input type="number" class="md-item-amount-input" data-item-id="${id}" data-required="${locked ? "0" : "1"}" data-purpose="${esc(purpose)}" data-max="${max}" min="0" max="${max}" step="0.01" value="${value.toFixed(2)}" ${locked ? "disabled" : ""} title="${esc(name)} · maximum ${PESO(max)}" style="width:92px; min-width:0; text-align:right; border:1px solid #d6ddd7; border-radius:6px; padding:3px 5px; font-family:inherit; font-size:0.76rem; box-sizing:border-box;${locked ? "background:#f1f3f1;color:#8a949e;" : ""}" oninput="mdClampItemAmount(this)" />`;
    }).join("");
    row.dataset.itemMode = "inputs";
  }

  function mdConvertRowToChips(row) {
    const container = row.querySelector(".mdp-chips");
    if (!container || !row.__chipsHtml) return;
    container.innerHTML = row.__chipsHtml;
    row.dataset.itemMode = "chips";
    row.dataset.manual = "0";
  }

  window.mdClampItemAmount = function mdClampItemAmount(input) {
    const row = input.closest(".mdp-row") || input.closest("tr");
    const collected = parseFloat(row?.querySelector(".md-actual-input")?.value) || 0;
    const funds = Math.max(0, collected - mdPriorFor(row, collected));
    const max = Number(input.dataset.max) || 0;
    let value = parseFloat(input.value) || 0;
    if (!Number.isFinite(value) || value < 0) value = 0;
    // The per-item split can never total more than the amount deducted:
    // cap this box at what the sibling item inputs have left unassigned.
    let others = 0;
    (row || document).querySelectorAll(".md-item-amount-input").forEach((inp) => {
      if (inp !== input) others += parseFloat(inp.value) || 0;
    });
    const cap = Math.max(0, Math.min(max, funds - others));
    // Rewrite the box only when clamping — touching the value on every
    // keystroke jumps the caret to the end mid-typing.
    if (value > cap) { value = cap; input.value = value.toFixed(2); }
    mdRefreshRow(input);
  };

  // Oldest-first default selection: with an amount, pick the prefix of
  // months that amount covers; with none, the single oldest month.
  function defaultSelectedKeysFor(unpaidMonths, amount) {
    if (!unpaidMonths || !unpaidMonths.length) return [];
    const amt = Number(amount) || 0;
    if (amt <= 0.004) return [unpaidMonths[0].key];
    const keys = [];
    let cum = 0;
    for (const um of unpaidMonths) {
      if (cum >= amt - 0.004) break;
      keys.push(um.key);
      cum += Number(um.amount) || 0;
    }
    return keys.length ? keys : [unpaidMonths[0].key];
  }

  // Months the treasurer ticked — these define what the payment settles.
  function mdSelectedUnpaidKeys(row) {
    const keys = [];
    if (!row) return keys;
    row.querySelectorAll(".mdp-unpaid-row.is-selected[data-key]").forEach((el) => keys.push(el.dataset.key));
    return keys;
  }

  // The prior-balance payment: the sum of every ticked unpaid month.
  function mdSelectedUnpaidTotal(row) {
    if (!row) return 0;
    let total = 0;
    row.querySelectorAll(".mdp-unpaid-row.is-selected[data-amount]").forEach((el) => {
      total += Number(el.dataset.amount) || 0;
    });
    return total;
  }

  /* Amount ⇄ months linkage (two linked ways to pay the same arrears).
     Leaves walk oldest-first (Due before Aid inside aid months) — the same
     order the server uses for a key-less prior payment. Programmatic .value
     writes never refire oninput, so the two controls cannot loop. */
  function mdUnpaidLeafRows(row) {
    if (!row) return [];
    return [...row.querySelectorAll(".mdp-unpaid-panel .mdp-unpaid-row[data-key][data-amount]")]
      .filter((el) => !el.querySelector(".mdp-unpaid-check")?.disabled);
  }

  // Amount → months: tick the oldest leaves until their sum covers the typed
  // amount (ceil semantics — months settle whole). Returns the ticked sum.
  function mdGreedyTickUnpaid(row, amount) {
    const leaves = mdUnpaidLeafRows(row);
    const target = Math.max(0, Number(amount) || 0);
    let cum = 0;
    leaves.forEach((el) => {
      const cb = el.querySelector(".mdp-unpaid-check");
      const take = target > 0.004 && cum < target - 0.004;
      if (cb) cb.checked = take;
      if (take) cum += Number(el.dataset.amount) || 0;
    });
    return cum;
  }

  // Months → amount: rewrite the Amount to pay field with the ticked sum plus
  // a coverage hint (oldest N months; warn when Total Collected is short).
  // Pass rewrite=false while the treasurer is mid-typing so keystrokes are
  // never yanked; the exact ceil snaps in on change/blur.
  function mdSyncUnpaidAmountField(row, rewrite) {
    if (!row) return;
    if (rewrite === undefined) rewrite = true;
    const panel = row.querySelector(".mdp-unpaid-panel");
    const input = panel ? panel.querySelector(".mdp-unpaid-amount-input") : null;
    if (!input) return;
    const ticked = mdSelectedUnpaidTotal(row);
    const coveredMonths = new Set(
      [...panel.querySelectorAll(".mdp-unpaid-row.is-selected[data-key]")]
        .map((el) => String(el.dataset.key || "").split(":")[0])
        .filter(Boolean)
    ).size;
    if (rewrite) input.value = ticked.toFixed(2);
    const hint = panel.querySelector(".mdp-unpaid-hint");
    if (hint) {
      const funds = parseFloat(row.querySelector(".md-actual-input")?.value) || 0;
      if (ticked <= 0.004) { hint.textContent = ""; hint.classList.remove("has-warn"); }
      else {
        let msg = `Covers the oldest ${coveredMonths} unpaid month${coveredMonths === 1 ? "" : "s"} (${PESO(ticked)}).`;
        if (ticked > funds + 0.004) { msg += ` Raise Total Collected to at least ${PESO(ticked)}.`; hint.classList.add("has-warn"); }
        else hint.classList.remove("has-warn");
        hint.textContent = msg;
      }
    }
  }

  // Amount input handler: clamp 0 … total unpaid, greedy-tick the months it
  // covers, then flow through the normal refresh/distribute pipeline (the
  // ticked months remain the single source of truth for submit).
  window.mdUnpaidAmountInput = function mdUnpaidAmountInput(input, commit) {
    const row = input && input.closest ? input.closest(".mdp-row") : null;
    if (!row || row.dataset.readonly === "1" || row.dataset.excluded === "1") return;
    const panel = input.closest(".mdp-unpaid-panel");
    const total = Number(panel && panel.dataset.unpaidTotal) || 0;
    let value = parseFloat(input.value);
    if (!Number.isFinite(value) || value < 0) value = 0;
    value = Math.min(value, total);
    mdGreedyTickUnpaid(row, value);
    mdUpdateUnpaidPanel(row);
    mdSyncUnpaidAmountField(row, commit !== false);
    mdRefreshRow(row);
    if (row.dataset.excluded !== "1") {
      mdAutoDistributeItems(row);
      mdRefreshRow(row);
    }
  };

  // How much of the collection goes to prior unpaid months: every ticked
  // month, capped at what was actually collected. Excluded / unchecked rows
  // settle nothing. The server applies it to the ticked months in tick
  // (oldest) order; the remainder of the collection funds this month.
  function mdPriorFor(row, funds) {
    if (!row || row.dataset.excluded === "1") return 0;
    if (!row.querySelector(".md-member-check")?.checked) return 0;
    return Math.min(mdSelectedUnpaidTotal(row), Math.max(0, funds));
  }

  // Keep each unpaid row's selected styling in sync with its checkbox,
  // plus each month-group header (ticked only when Due + Aid both are),
  // plus the "Outstanding balance" select-all box (ticked only when every
  // enabled unpaid due inside the popup is ticked).
  function mdUpdateUnpaidPanel(row) {
    if (!row) return;
    const panel = row.querySelector(".mdp-unpaid-panel");
    if (!panel) return;
    panel.querySelectorAll(".mdp-unpaid-row[data-key]").forEach((el) => {
      const cb = el.querySelector(".mdp-unpaid-check");
      el.classList.toggle("is-selected", !!(cb && cb.checked));
    });
    panel.querySelectorAll(".mdp-unpaid-group").forEach((g) => {
      const leaves = Array.from(g.querySelectorAll(".mdp-unpaid-check"));
      const head = g.querySelector(".mdp-unpaid-groupcheck");
      if (head && leaves.length) {
        head.checked = leaves.every((cb) => cb.checked);
      }
    });
    const selectAll = panel.querySelector(".mdp-unpaid-selectall");
    if (selectAll && !selectAll.disabled) {
      const leaves = Array.from(panel.querySelectorAll(".mdp-unpaid-check")).filter((cb) => !cb.disabled);
      selectAll.checked = leaves.length > 0 && leaves.every((cb) => cb.checked);
    }
  }

  // Select-all box in the month-selection list — ticks / unticks every
  // unpaid due inside the popup. Locked rows (read-only, retired, excluded)
  // only flip their enabled boxes; disabled boxes stay as-is. The collection
  // settles the ticked months oldest-first; the Amount to pay field re-syncs.
  window.mdUnpaidSelectAllToggle = function mdUnpaidSelectAllToggle(cb) {
    const row = cb && cb.closest ? cb.closest(".mdp-row") : null;
    const panel = cb && cb.closest ? cb.closest(".mdp-unpaid-panel") : null;
    if (!row || !panel || row.dataset.readonly === "1") {
      if (cb && panel) mdUpdateUnpaidPanel(row);
      return;
    }
    const checked = !!cb.checked;
    panel.querySelectorAll(".mdp-unpaid-check").forEach((leaf) => {
      if (!leaf.disabled) leaf.checked = checked;
    });
    mdUpdateUnpaidPanel(row);
    mdSyncUnpaidAmountField(row);
    mdRefreshRow(row);
    if (row.dataset.excluded !== "1") {
      mdAutoDistributeItems(row);
      mdRefreshRow(row);
    }
  };

  // Tick a whole month (Due + Aid) on/off from the group header — the
  // collection settles the ticked components oldest-first; untick Aid to
  // chase dues only.
  window.mdUnpaidGroupToggle = function mdUnpaidGroupToggle(cb) {
    const row = cb && cb.closest ? cb.closest(".mdp-row") : null;
    const group = cb && cb.closest ? cb.closest(".mdp-unpaid-group") : null;
    if (!row || !group || row.dataset.readonly === "1") return;
    group.querySelectorAll(".mdp-unpaid-check").forEach((leaf) => {
      if (!leaf.disabled) leaf.checked = cb.checked;
    });
    mdUpdateUnpaidPanel(row);
    mdSyncUnpaidAmountField(row);
    mdRefreshRow(row);
    if (row.dataset.excluded !== "1") {
      mdAutoDistributeItems(row);
      mdRefreshRow(row);
    }
  };

  // Tick a month to include / exclude it in this payment — the collection
  // settles the ticked months oldest-first; the remainder re-flows across
  // this month's items (Monthly Due last), so ticking never squeezes the
  // other assessments. The Amount to pay field re-syncs to the ticked sum.
  window.mdUnpaidRowToggle = function mdUnpaidRowToggle(cb) {
    const row = cb && cb.closest ? cb.closest(".mdp-row") : null;
    const rowEl = cb && cb.closest ? cb.closest(".mdp-unpaid-row") : null;
    if (!row || !rowEl || row.dataset.readonly === "1") return;
    rowEl.classList.toggle("is-selected", cb.checked);
    mdUpdateUnpaidPanel(row);
    mdSyncUnpaidAmountField(row);
    mdRefreshRow(row);
    // The post-prior remainder changed — re-flow the item amounts (Monthly
    // Due last) so freed money returns to the due and claimed money comes
    // out of the due first, never the other assessments.
    if (row.dataset.excluded !== "1") {
      mdAutoDistributeItems(row);
      mdRefreshRow(row);
    }
  };

  window.mdToggleUnpaidPanel = function mdToggleUnpaidPanel(btn) {
    const wrap = btn && btn.closest ? btn.closest(".mdp-unpaid-wrap") : null;
    if (!wrap) return;
    const panel = wrap.querySelector(".mdp-unpaid-panel");
    if (!panel) return;
    const wasOpen = panel.classList.contains("open");
    document.querySelectorAll("#mdp-root .mdp-unpaid-panel.open").forEach((p) => p.classList.remove("open"));
    if (wasOpen) return;
    // Keep the ticked-month styling in sync with the rendered checkboxes.
    mdUpdateUnpaidPanel(wrap.closest(".mdp-row"));
    // Fixed positioning escapes .mdp-tablewrap overflow clipping.
    const rect = btn.getBoundingClientRect();
    panel.classList.add("open");
    const panelWidth = panel.offsetWidth || 280;
    const panelHeight = panel.offsetHeight || 180;
    let left = rect.right - panelWidth;
    left = Math.max(8, Math.min(left, window.innerWidth - panelWidth - 8));
    let top = rect.bottom + 4;
    if (top + panelHeight > window.innerHeight - 8) {
      top = Math.max(8, rect.top - panelHeight - 4);
    }
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
  };

  document.addEventListener("click", (event) => {
    const t = event && event.target;
    if (!t || !t.closest) return;
    if (t.closest(".mdp-unpaid-toggle") || t.closest(".mdp-unpaid-panel")) return;
    document.querySelectorAll("#mdp-root .mdp-unpaid-panel.open").forEach((p) => p.classList.remove("open"));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      document.querySelectorAll("#mdp-root .mdp-unpaid-panel.open").forEach((p) => p.classList.remove("open"));
    }
  });
  window.addEventListener("scroll", () => {
    document.querySelectorAll("#mdp-root .mdp-unpaid-panel.open").forEach((p) => p.classList.remove("open"));
  }, true);

  /* Carry-over cue: the collection settled outstanding unpaid dues first, so
     this month's Monthly Due stays unpaid and carries to next month. The
     translucent overlay sits on ONLY the Monthly Due input — the aid items
     are not part of this cue — and that field is locked while it shows.
     Raising Total Collected (or unticking unpaid months) clears it and
     re-opens the field. */
  function mdUpdateCarryCue(row, uncovered) {
    const cell = row && row.querySelector(".mdp-item-cell");
    if (!cell) return;
    const dueInput = row.querySelector('.md-item-amount-input[data-purpose="monthly_due"]');
    const cue = cell.querySelector(".mdp-carry-overlay");
    if (!(uncovered > 0.005) || !dueInput) {
      if (cue) cue.remove();
      if (dueInput && row.dataset.excluded !== "1" && dueInput.dataset.required !== "0") dueInput.disabled = false;
      return;
    }
    let overlay = cue;
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "mdp-carry-overlay";
      overlay.innerHTML = "<span></span>";
      cell.appendChild(overlay);
    }
    const label = overlay.querySelector("span");
    label.textContent = `${PESO(uncovered)} → carry over`;
    label.title = `Outstanding unpaid dues were settled first — ${PESO(uncovered)} of this month's Monthly Due is unpaid and carries to next month. Raise Total Collected to cover it.`;
    // Cover only the Monthly Due field inside the itemized cell. Measured
    // with client rects (not offsetTop) so the cell's 3px padding and the
    // chips container padding cannot skew the placement.
    mdPositionCarryCue(cell, dueInput, overlay);
    if (dueInput.dataset.required !== "0") dueInput.disabled = true;
  }

  // Exact placement of the carry-over overlay over the Monthly Due input.
  function mdPositionCarryCue(cell, dueInput, overlay) {
    const cellRect = cell.getBoundingClientRect();
    const inpRect = dueInput.getBoundingClientRect();
    if (!inpRect.width && !inpRect.height) return;
    overlay.style.left = `${inpRect.left - cellRect.left}px`;
    overlay.style.top = `${inpRect.top - cellRect.top}px`;
    overlay.style.width = `${inpRect.width}px`;
    overlay.style.height = `${inpRect.height}px`;
  }

  // Column widths / viewport changes move the input — re-measure the cue.
  window.addEventListener("resize", () => {
    document.querySelectorAll("#mdp-root .mdp-item-cell .mdp-carry-overlay").forEach((overlay) => {
      const cell = overlay.closest(".mdp-item-cell");
      const dueInput = cell && cell.querySelector('.md-item-amount-input[data-purpose="monthly_due"]');
      if (dueInput) mdPositionCarryCue(cell, dueInput, overlay);
    });
  });

  window.mdRefreshRow = function mdRefreshRow() {
    const arg = arguments[0];
    const rows = arg && arg.closest ? [arg.closest(".mdp-row") || arg.closest("tr")] : [...document.querySelectorAll("#md-roster-body tr.mdp-row")];
    for (const row of rows) {
      if (!row) continue;
      const input = row.querySelector(".md-actual-input");
      if (input && arg === input) row.dataset.manual = "0";
      const standard = Number(row.dataset.standard) || 0;
      const memberChecked = !!row.querySelector(".md-member-check")?.checked;
      const funds = parseFloat(input?.value) || 0;
      /* "Total Collected" IS the member's real payroll deduction. The ticked
         unpaid months are settled from it FIRST (oldest ticked month first,
         up to what was collected); whatever remains funds this month's
         items — so a collection covering only one due clears the oldest
         unsettled month and this month carries over. Excluded / unchecked
         rows settle nothing. */
      const priorApplied = mdPriorFor(row, funds);
      const currentFunds = Math.max(0, funds - priorApplied);
      const manual = row.dataset.manual === "1";

      // Only what is left after the prior payment funds this month's items,
      // and each input remains capped at its item amount.
      if (row.dataset.excluded !== "1") {
        if (row.dataset.itemMode !== "inputs") mdConvertRowToInputs(row);
        // Typing the Total Collected box always re-flows the money across
        // the items in priority order — full or partial — so a partial
        // payment lands on the items instead of stranding as excess.
        // Typing an item box directly only clamps (manual tweaks are kept).
        if (arg === input) mdAutoDistributeItems(row);
      }
      const inputsMode = row.dataset.itemMode === "inputs";

      let fundedSum = 0;
      const chips = row.querySelectorAll(".md-item-chip");
      if (row.dataset.excluded === "1") {
        if (inputsMode) {
          row.querySelectorAll(".md-item-amount-input").forEach((inp) => { inp.disabled = true; inp.value = "0.00"; });
        } else {
          chips.forEach((chip) => styleItemChip(chip, false));
        }
      } else if (inputsMode) {
        row.querySelectorAll(".md-item-amount-input").forEach((inp) => { if (inp.dataset.required !== "0") inp.disabled = false; });
        // First come, first served (Monthly Due last): each item input is
        // capped at its own item amount and at whatever of the post-prior
        // remainder the earlier-priority inputs have left — the split can
        // never exceed the money left for this month, and a shortfall
        // clamps the due, never the items before it.
        let allowance = currentFunds;
        mdPriorityOrder(row.querySelectorAll(".md-item-amount-input")).forEach((inp) => {
          const max = Number(inp.dataset.max) || 0;
          let value = parseFloat(inp.value) || 0;
          // Only rewrite the box when the value must be clamped — reformatting
          // while typing yanks the caret to the end.
          if (!Number.isFinite(value) || value < 0) { value = 0; inp.value = "0.00"; }
          const cap = Math.min(max, Math.max(0, allowance));
          if (value > cap) { value = cap; inp.value = value.toFixed(2); }
          allowance -= value;
          fundedSum += value;
        });
      } else if (manual) {
        chips.forEach((chip) => {
          const covered = chip.dataset.selected === "1";
          styleItemChip(chip, covered);
          if (covered) fundedSum += Number(chip.dataset.itemAmount) || 0;
        });
      } else {
        let remaining = currentFunds;
        let stopped = false;
        mdPriorityOrder(chips).forEach((chip) => {
          const value = Number(chip.dataset.itemAmount) || 0;
          const covered = !stopped && value > 0 && remaining >= value - 0.005;
          if (covered) remaining -= value; else stopped = true;
          /* No live check styling — typing an amount must not mark items
             funded/paid before the batch is actually submitted. Chips light
             up only from recorded data or an explicit manual selection. */
          styleItemChip(chip, chip.dataset.selected === "1");
          if (covered) fundedSum += value;
        });
      }

      // Row total = this month's items funded + the prior balance payment.
      const rowTotal = fundedSum + priorApplied;
      const totalCell = row.querySelector(".md-row-total-cell");
      if (totalCell) totalCell.textContent = PESO(rowTotal);
      row.dataset.rowTotal = rowTotal.toFixed(2);
      row.dataset.priorApplied = priorApplied.toFixed(2);
      // Overlay on the Monthly Due input whenever outstanding dues took the
      // money and this month's dues are left uncovered (aid items excluded).
      let dueUncovered = 0;
      const dueInput = row.querySelector('.md-item-amount-input[data-purpose="monthly_due"]');
      if (dueInput && dueInput.dataset.required !== "0") {
        dueUncovered = Math.max(0, (Number(dueInput.dataset.max) || 0) - (parseFloat(dueInput.value) || 0));
      }
      mdUpdateCarryCue(row, priorApplied > 0.005 ? dueUncovered : 0);

      // Excess beyond the breakdown (after the prior payment) is forwarded
      // to the ISUCauFA funds — there is no member credit.
      const excessToFund = Math.max(0, currentFunds - fundedSum);
      /* The Outstanding column always counts the FULL unpaid pool — every
         past month still owed — minus whatever this payment settles.
         Deselecting a month only keeps it out of the payment; it stays in
         the balance and carries to next month with its months context. */
      const fullUnpaid = Number(row.dataset.unpaidTotal) || Number(row.dataset.prior) || 0;
      const rowOutstanding = inputsMode
        ? Math.max(0, standard - fundedSum) + fullUnpaid - priorApplied
        : Math.max(0, standard - currentFunds) + fullUnpaid - priorApplied;

      // Member payment status: exactly Paid / Partial / Not Paid.
      // "Paid" means the current month AND every unpaid month are settled.
      const priorSettled = fullUnpaid - priorApplied <= 0.005;
      const hasPayment = funds > 0;
      const status = standard <= 0.005 && priorSettled
        ? "exempt"
        : standard > 0 && currentFunds >= standard - 0.005 && priorSettled
          ? "paid"
          : hasPayment
            ? "partial"
            : "unpaid";
      row.dataset.status = status;
      const statusCell = row.querySelector(".mdp-status-cell");
      if (statusCell) statusCell.innerHTML = payBadge(status);

      const included = memberChecked;
      const cell = row.querySelector(".mdp-outstanding-cell");
      if (cell) {
        const excluded = row.dataset.excluded === "1";
        if (!included && !excluded) {
          cell.innerHTML = `<span style="color:#9e9e9e;">—</span>`;
          row.dataset.change = "0.00";
          row.dataset.outstanding = "0.00";
        } else {
          cell.innerHTML = PESO(rowOutstanding) +
            (manual && fundedSum > 0 ? `<small style="color:#8a6d3b; font-weight:600;">manual allocation</small>` : "") +
            ``;
          row.dataset.change = excluded ? "0.00" : excessToFund.toFixed(2);
          row.dataset.outstanding = rowOutstanding.toFixed(2);
        }
      }
    }
    mdUpdateSummary();
    renderFilterChips();
    saveRosterDraft();
  };

  window.mdUpdateSummary = function mdUpdateSummary() {
    let selected = 0, deducted = 0, outstanding = 0;
    document.querySelectorAll("#md-roster-body tr.mdp-row").forEach((row) => {
      if (!row.querySelector(".md-member-check")?.checked) return;
      selected += 1;
      deducted += parseFloat(row.querySelector(".md-actual-input")?.value) || 0;
      outstanding += Number(row.dataset.outstanding) || 0;
    });
    const set = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
    const outEl = document.getElementById("mdp-total-outstanding");
    set("mdp-total-selected", `${selected} member${selected === 1 ? "" : "s"}`);
    set("mdp-total-deducted", PESO(deducted));
    set("mdp-total-outstanding", PESO(outstanding));
    // Keep the allocation-settings card count in lockstep (it reuses the
    // same "ticked + enabled + non-excluded" selection definition).
    try { mdUpdateAllocCount(); } catch (e) {}

    if (outEl) outEl.classList.toggle("mdp-neg", outstanding > 0);

    // ---- Summary + "where the money goes" (plain-terms totals card) ----
    let totalRows = 0, sumDeducted = 0, sumExpected = 0, sumPriorApplied = 0, sumExcess = 0, sumOutstanding = 0;
    const itemApplied = {}; // item_id -> total applied across rows
    const outstandingRows = [];
    document.querySelectorAll("#md-roster-body tr.mdp-row").forEach((row) => {
      // Total expected covers EVERY member the President set the plan for —
      // excluded members still carry their share (it shows in their balance),
      // so counting them keeps Expected − Collected = Outstanding.
      sumExpected += Number(row.dataset.standard) || 0;
      const balance = Number(row.dataset.outstanding) || 0;
      // Excluded members owe their share too — their balance counts in the
      // Outstanding total, so it belongs in the breakdown list as well.
      sumOutstanding += balance;
      if (balance > 0.005) {
        // Months this balance is made of: the ticked months the collection
        // did not fully settle (walked oldest-first, exactly like the server
        // attribution) plus every unticked month — they carry to next month
        // with their months context (an excluded row settles nothing, so all
        // count).
        const carriesAll = row.dataset.excluded === "1";
        const carriedMonths = [];
        let settleLeft = carriesAll ? 0 : Number(row.dataset.priorApplied) || 0;
        row.querySelectorAll(".mdp-unpaid-row[data-key]").forEach((el) => {
          const amt = Number(el.dataset.amount) || 0;
          if (!amt) return;
          const settled = !carriesAll && el.classList.contains("is-selected");
          if (settled && settleLeft > 0) {
            if (amt <= settleLeft + 0.005) { settleLeft -= amt; return; }
            settleLeft = 0;
          }
          const label = (el.querySelector(".mdp-unpaid-label")?.textContent || el.dataset.key || "").trim();
          if (label) carriedMonths.push(label);
        });
        outstandingRows.push({
          name: row.dataset.name || "Member",
          amount: balance,
          months: carriedMonths,
        });
      }
      if (row.dataset.excluded === "1") return;
      totalRows += 1;
      const included = row.querySelector(".md-member-check")?.checked;
      if (!included) return;
      const funds = parseFloat(row.querySelector(".md-actual-input")?.value) || 0;
      sumDeducted += funds;
      sumPriorApplied += Number(row.dataset.priorApplied) || 0;
      sumExcess += Number(row.dataset.change) || 0;

      row.querySelectorAll(".md-item-chip").forEach((chip) => {
        if (chip.dataset.selected !== "1") return;
        const id = chip.dataset.itemId;
        itemApplied[id] = (itemApplied[id] || 0) + (Number(chip.dataset.itemAmount) || 0);
      });
      row.querySelectorAll(".md-item-amount-input").forEach((inp) => {
        const id = inp.dataset.itemId;
        itemApplied[id] = (itemApplied[id] || 0) + (parseFloat(inp.value) || 0);
      });
    });

    const items = (state.roster && state.roster.items) || [];
    const totalsCard = document.getElementById("mdp-column-totals");
    if (totalsCard) {
      const moneyLine = (lineLabel, recipient, amount) => `
        <div style="padding:3px 0;">
          <div style="display:flex; justify-content:space-between; gap:14px; font-size:0.8rem;">
            <span>${esc(lineLabel)}</span>
            <span style="font-weight:700; color:#1b5e20; font-variant-numeric:tabular-nums;">${PESO(amount)}</span>
          </div>
          ${recipient ? `<div style="font-size:0.68rem; color:#8a949e; margin-top:-2px;">For: ${esc(recipient)}</div>` : ""}
        </div>`;
      const itemLines = items
        .map((i) => moneyLine(i.purpose_label || i.purpose || "Item", i.recipient || "", itemApplied[i.item_id] || 0))
        .join("");
      const extraLines =
        (sumPriorApplied > 0.005 ? moneyLine("Prior balance collected", "", sumPriorApplied) : "")
        + (sumExcess > 0.005 ? moneyLine("Excess forwarded to ISUCauFA, Inc.", "", sumExcess) : "");

      totalsCard.innerHTML = `
        <div class="mdp-sticky-label" style="margin-bottom:8px;"><i class="fa-solid fa-chart-simple" style="margin-right:6px;"></i>Summary</div>
        <div style="display:flex; gap:34px; flex-wrap:wrap; align-items:center;">
          <div><div class="mdp-sticky-label">Recorded Members</div><div style="font-size:1rem; font-weight:800;">${totalRows}</div></div>
          <div><div class="mdp-sticky-label">Total Expected Dues</div><div style="font-size:1rem; font-weight:800;">${PESO(sumExpected)}</div></div>
          <div><div class="mdp-sticky-label">Total Amount Collected</div><div style="font-size:1rem; font-weight:800; color:#1b5e20;">${PESO(sumDeducted)}</div></div>
          <div><div class="mdp-sticky-label">Outstanding</div><div style="font-size:1rem; font-weight:800; ${sumOutstanding > 0.005 ? "color:#c62828;" : "color:#1b5e20;"}">${PESO(sumOutstanding)}</div></div>
          ${state.recordable ? `
          <button type="button" class="mdp-btn mdp-btn-primary" style="width:fit-content; margin-left:auto; padding:10px 22px; font-size:0.86rem; border-radius:8px;" onclick="mdSubmit()">Submit for Deposit</button>` : ""}
        </div>
        ${itemLines || extraLines ? `
        <div style="border-top:1px solid #eef1ee; margin-top:12px; padding-top:10px;">
          <div class="mdp-sticky-label" style="margin-bottom:4px;"><i class="fa-solid fa-coins" style="margin-right:6px;"></i>Fund Allocation Breakdown</div>
          ${itemLines}${extraLines}
          <div style="display:flex; justify-content:space-between; border-top:2px solid #e6ebe7; margin-top:8px; padding-top:6px; font-size:0.85rem; font-weight:800;">
            <span>Total Amount Collected</span>
            <span style="color:#1b5e20; font-variant-numeric:tabular-nums;">${PESO(sumDeducted)}</span>
          </div>
        </div>` : ""}
        ${outstandingRows.length ? `
        <div style="border-top:1px solid #eef1ee; margin-top:12px; padding-top:10px;">
          <div class="mdp-sticky-label" style="margin-bottom:4px; color:#c62828;">Outstanding balances — carried to next month</div>
          ${outstandingRows.map((r) => `
            <div style="display:flex; justify-content:space-between; gap:14px; font-size:0.8rem; padding:3px 0;">
              <span style="min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${esc(r.name)}${r.months && r.months.length ? ` <span style="color:#8a949e; white-space:normal;">— ${esc(r.months.join(", "))}</span>` : ""}</span>
              <span style="font-weight:700; color:#c62828; font-variant-numeric:tabular-nums;">${PESO(r.amount)}</span>
            </div>`).join("")}
        </div>` : ""}`;
    }
    // Paginated: keep the header Select-All checkbox in sync (all filtered
    // members across pages, not just the visible page).
    try { syncHeaderCheck(mdFilteredRows()); } catch (e) {}
  };

  /* ---------- submit ---------- */
  let mdSubmitInFlight = false;
  window.mdSubmit = async function mdSubmit() {
    if (mdSubmitInFlight) return;
    mdSubmitInFlight = true;
    try {
    const select = document.getElementById("md-month-select");
    const assessmentId = select ? select.value : "";
    if (!assessmentId) { toast("Select an assessment month first.", true); return; }

    const rows = [...document.querySelectorAll("#md-roster-body tr.mdp-row")];
    const incompleteSelection = rows.some((row) => {
      if (row.dataset.excluded === "1") return false;
      return !row.querySelector(".md-member-check")?.checked;
    });
    if (incompleteSelection) {
      toast("Select All non-excluded members before submitting.", true);
      return;
    }

    const members = [];
    rows.forEach((row) => {
      if (!row.querySelector(".md-member-check")?.checked) return;
      const amount = parseFloat(row.querySelector(".md-actual-input").value) || 0;
      // The collection is the member's real total. The ticked unpaid months
      // are settled from it first (oldest ticked month first, capped at what
      // was collected); the server sends the remainder to this month's items.
      const priorAmount = Number(mdPriorFor(row, amount).toFixed(2));
      const unpaidKeys = mdSelectedUnpaidKeys(row);
      const entry = {
        member_id: Number(row.dataset.memberId),
        actual_deduction: Number(amount.toFixed(2)),
        prior_balance_amount: priorAmount,
      };
      if (unpaidKeys.length && priorAmount > 0) entry.unpaid_month_keys = unpaidKeys;
      // Partial rows: submit the typed per-item distribution, re-clamped so
      // the split can never exceed what is left of the collection after the
      // prior payment (the prior payment belongs to the prior balance, not
      // to the items). Clamped in priority order — Monthly Due last — so a
      // shortfall never eats the other assessments.
      if (row.dataset.itemMode === "inputs") {
        let allowance = Math.max(0, Number((amount - priorAmount).toFixed(2)));
        entry.item_amounts = mdPriorityOrder(row.querySelectorAll(".md-item-amount-input")).map((inp) => {
          const max = Number(inp.dataset.max) || 0;
          let amount2 = parseFloat(inp.value) || 0;
          if (!Number.isFinite(amount2) || amount2 < 0) amount2 = 0;
          amount2 = Math.min(amount2, max, allowance);
          allowance -= amount2;
          return { item_id: Number(inp.dataset.itemId), amount: Number(amount2.toFixed(2)) };
        });
      } else if (row.dataset.manual === "1") {
        // Manual rows: submit exactly the chips the treasurer selected.
        entry.selected_item_ids = [...row.querySelectorAll(".md-item-chip")]
          .filter((chip) => chip.dataset.selected === "1")
          .map((chip) => Number(chip.dataset.itemId));
      }
      members.push(entry);
    });
    if (!members.length) { toast("Select at least one member.", true); return; }
    // Members left out of this collection batch still owe the month: their
    // ids travel with the submission so the server writes carry-forward
    // zero-rows that stay visible downstream as unpaid.
    const excludedMemberIds = rows
      .filter((row) => row.dataset.excluded === "1")
      .map((row) => Number(row.dataset.memberId))
      .filter((id) => Number.isFinite(id));
    const proceed = await SimpleModal.confirm(
      `Submit ${members.length} deduction(s)` +
      (excludedMemberIds.length ? ` (${excludedMemberIds.length} excluded, carried as unpaid)` : "") +
      ` for bank deposit?`,
      { title: "Submit for Deposit", okText: "Submit", cancelText: "Cancel" }
    );
    if (!proceed) return;

    try {
      const resp = await fetch("/api/treasurer/deductions/record/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": getCookie("csrftoken") },
        body: JSON.stringify({ assessment_id: Number(assessmentId), members, excluded_member_ids: excludedMemberIds }),
      });
      const data = await resp.json();
      if (!data.ok) { toast(data.error || "Failed to record deductions.", true); return; }
      clearRosterDraft(assessmentId);
      toast(data.message || "Deductions recorded.", false);
      mdpSetTab("record");
      loadMdOverviews();
      showDepositNowPrompt();
    } catch (e) {
      console.error("Failed to record deductions", e);
      toast("Failed to record deductions.", true);
    }
    } finally {
      mdSubmitInFlight = false;
    }
  };

  /* ============================== boot ============================== */
  document.addEventListener("DOMContentLoaded", () => {
    loadMdOverviews();
  });
  /* Turbo navigations never re-fire DOMContentLoaded — without this the
     sidebar dot would stay unset until a hard refresh. */
  document.addEventListener("turbo:load", () => {
    loadMdOverviews();
  });
})();


function setBadge(elId, count) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.textContent = count > 0 ? count : "";
  el.style.display = count > 0 ? "inline-flex" : "none";
}

// Live badge: updates instantly when any officer moves the workflow along.
try {
  const proto = window.location.protocol === "https:" ? "wss://" : "ws://";
  const ws = new WebSocket(`${proto}${window.location.host}/ws/treasurer-dashboard/?token=${encodeURIComponent(window.WS_AUTH_TOKEN || "")}`);
  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "deduction_counts") setBadge("md-attention-dot", msg["attention"] || 0);
    } catch (e) {}
  };
} catch (e) {}
