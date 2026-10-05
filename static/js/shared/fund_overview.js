// fund_overview.js — ISUCauFA, Inc. Fund overview + ledger, in simple everyday terms.
// Self-contained: injects its own styles, no chart library needed for the page
// itself (the dashboard flow chart uses the host page's Chart.js).
// Hosts: #fund-overview-root (Fund Overview page), #fund-ledger-root (Fund
//        Ledger page), #nxf-root (compact summary card on the dashboards),
//        #fundFlowChart (Money In vs Money Out graph on the dashboards).
// Design: white cards, thin #DDE5DE borders, small radii, green/white/gray.
(function () {
  "use strict";

  const SOURCE_LABELS = {
    monthly_dues: "Monthly Dues",
    monthly_deduction: "Monthly Dues",
    salary_deduction_remittance: "Salary Deductions",
    membership_fee: "Membership Fee",
    outstanding_payment: "Outstanding Payments",
    donation: "Donations",
    interest: "Bank Interest",
    fund_drive: "Fund Drive",
    other_income: "Other Income",
    medical_aid: "Medical Aid",
    death_aid: "Death Aid",
    token_incentive: "Retiree Tokens",
    aid_post_payment: "Aid Release",
    aid_contribution: "Aid Contribution",
    contribution: "Contribution",
    payroll_batch: "Payroll",
    manual_adjustment: "Manual Adjustment",
    operating_expense: "Operations",
    other_expense: "Other Expenses",
    other_transaction: "Non-Dues Transaction",
  };

  const CSS = `
    .fx-card{background:#fff;border:1px solid #DDE5DE;border-radius:8px;padding:20px;margin-bottom:16px;}
    .fx-title{font-size:1rem;font-weight:700;color:#1f2a24;margin:0 0 2px;}
    .fx-subtitle{font-size:0.8rem;color:#8a9490;margin:0 0 16px;}

    /* ---- balance hero ---- */
    .fx-hero-label{font-size:0.68rem;font-weight:700;letter-spacing:0.6px;text-transform:uppercase;color:#6b7280;}
    .fx-balance{font-size:2.2rem;font-weight:800;font-variant-numeric:tabular-nums;line-height:1.1;margin-top:4px;color:#166a3b;}
    .fx-balance.neg{color:#b93a3a;}
    .fx-balance-label{font-size:0.82rem;color:#8a9490;margin-top:4px;}
    .fx-strip{display:flex;flex-wrap:wrap;margin-top:16px;border-top:1px solid #EDF1EE;padding-top:14px;}
    .fx-strip-cell{flex:1;min-width:130px;padding:2px 18px;border-left:1px solid #EDF1EE;}
    .fx-strip-cell:first-child{border-left:none;padding-left:0;}
    .fx-strip-label{font-size:0.68rem;font-weight:700;letter-spacing:0.6px;text-transform:uppercase;color:#8a9490;}
    .fx-strip-value{font-size:1.05rem;font-weight:700;margin-top:4px;font-variant-numeric:tabular-nums;color:#1f2a24;}
    .fx-pos{color:#1e8f4e;}
    .fx-neg{color:#b93a3a;}

    /* ---- quick month stats ---- */
    .fx-quick{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:16px;}
    .fx-quick-cell{background:#fff;border:1px solid #DDE5DE;border-radius:8px;padding:14px 16px;}
    .fx-quick-label{font-size:0.68rem;font-weight:700;letter-spacing:0.6px;text-transform:uppercase;color:#8a9490;}
    .fx-quick-value{font-size:1.15rem;font-weight:700;margin-top:5px;font-variant-numeric:tabular-nums;color:#1f2a24;}
    .fx-status-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:1px;}

    /* ---- monthly cash flow bars ---- */
    .fx-bars .fx-bar-row{display:flex;align-items:center;gap:14px;padding:9px 0;border-bottom:1px solid #EDF1EE;}
    .fx-bars .fx-bar-row:last-child{border-bottom:none;}
    .fx-bars .fx-bar-month{width:88px;font-size:0.82rem;color:#1f2a24;font-weight:600;flex:none;}
    .fx-bar-track{flex:1;background:#f0f3f0;border-radius:4px;height:16px;overflow:hidden;display:flex;flex-direction:column;justify-content:center;gap:2px;}
    .fx-bar-in{height:6px;background:#1e8f4e;border-radius:3px;min-width:3px;}
    .fx-bar-out{height:6px;background:#b93a3a;border-radius:3px;min-width:3px;}
    .fx-bar-note{font-size:0.78rem;color:#5f6b64;margin:10px 0 0 102px;font-variant-numeric:tabular-nums;}
    .fx-legend{display:flex;gap:18px;font-size:0.78rem;color:#5f6b64;margin-top:12px;flex-wrap:wrap;}
    /* compact variant used inside overview cards */
    .fx-bars-compact .fx-bar-row{padding:7px 0;}
    .fx-bars-compact .fx-bar-month{width:74px;font-size:0.78rem;}
    .fx-bars-compact .fx-bar-track{height:14px;gap:2px;}
    .fx-bars-compact .fx-bar-in,.fx-bars-compact .fx-bar-out{height:5px;}
    .fx-bar-amt{width:172px;flex:none;font-size:0.74rem;color:#5f6b64;font-variant-numeric:tabular-nums;text-align:right;}
    .fx-bar-amt b{font-weight:700;}
    .fx-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;}

    /* ---- source donuts ---- */
    .fx-donuts{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-bottom:16px;}
    .fx-donuts .fx-card{margin-bottom:0;}
    .fx-donut-wrap{text-align:center;padding:16px 8px 4px;background:#fafcfa;border:1px solid #EDF1EE;border-radius:8px;}
    .fx-donut{width:150px;height:150px;border-radius:50%;margin:0 auto 14px;position:relative;}
    .fx-donut-hole{position:absolute;inset:28px;background:#fff;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;font-weight:800;color:#1f2a24;font-size:0.95rem;font-variant-numeric:tabular-nums;}
    .fx-donut-lines{text-align:left;font-size:0.82rem;color:#5f6b64;margin-top:6px;}
    .fx-donut-lines div{display:flex;justify-content:space-between;padding:6px 2px;border-bottom:1px solid #EDF1EE;}
    .fx-donut-lines div:last-child{border-bottom:none;}
    .fx-donut-lines b{font-variant-numeric:tabular-nums;}

    /* ---- tables ---- */
    .fx-table{width:100%;border-collapse:collapse;font-size:0.84rem;}
    .fx-table th{background:#f3f6f3;color:#5f6b64;font-size:0.68rem;text-transform:uppercase;letter-spacing:0.5px;padding:9px 12px;text-align:left;border:1px solid #E4EAE5;font-weight:700;white-space:nowrap;}
    .fx-table td{padding:9px 12px;border-bottom:1px solid #EDF1EE;color:#1f2a24;}
    .fx-table tr:hover td{background:#f7faf7;}
    .fx-table .fx-num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;font-weight:600;}
    .fx-table-wrap{overflow-x:auto;}
    .fx-empty{text-align:center;color:#8a9490;padding:32px 16px;font-size:0.85rem;background:#fafcfa;border:1px solid #EDF1EE;border-radius:8px;}
    .fx-actions{margin-top:14px;}

    /* ---- compact fund summary card (officer dashboards) ---- */
    .fx-fundcard{background:#fff;border:1px solid #DDE5DE;border-radius:8px;padding:14px 18px;margin:0 0 16px;display:flex;align-items:center;gap:22px;flex-wrap:wrap;}
    .fx-fundcard .fx-loading{color:#8a9490;font-size:0.85rem;}
    .fx-fundmain{min-width:200px;}
    .fx-fundcard .fx-kpi-label,.fx-fundstat .fx-kpi-label{font-size:0.68rem;font-weight:700;letter-spacing:0.6px;text-transform:uppercase;color:#6b7280;}
    .fx-fundbalance{font-size:1.7rem;font-weight:800;margin-top:3px;font-variant-numeric:tabular-nums;line-height:1.1;}
    .fx-fundstats{display:flex;gap:26px;flex-wrap:wrap;flex:1;min-width:260px;}
    .fx-fundstat{padding-left:18px;border-left:1px solid #E4EAE5;}
    .fx-fundval{font-size:1.05rem;font-weight:700;margin-top:3px;font-variant-numeric:tabular-nums;}
    .fx-fundval.pos,.fx-fundbalance.pos{color:#1e8f4e;}
    .fx-fundval.neg,.fx-fundbalance.neg{color:#b93a3a;}
    .fx-fundlinks{display:flex;gap:8px;flex-wrap:wrap;}
    .fx-fundlink{border:1px solid #DDE5DE;background:#fff;border-radius:6px;padding:8px 14px;font-size:0.82rem;font-weight:600;color:#166a3b;cursor:pointer;font-family:inherit;transition:background .12s,border-color .12s;}
    .fx-fundlink:hover{background:#e9f4ec;border-color:#1e8f4e;}

    /* ---- overview grid: each row's cards share one equal height ---- */
    .fx-grid2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;}
    .fx-grid2 .fx-card{margin-bottom:0;height:100%;box-sizing:border-box;}
    .fx-grid2 .fx-span2{grid-column:1 / -1;}
    @media(max-width:1100px){.fx-grid2{grid-template-columns:1fr;}.fx-grid2 .fx-card{height:auto;}}

    /* ---- overview stat strip (4 compact cards) ---- */
    .fx-cards4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:16px;}
    .fx-mcard{background:#fff;border:1px solid #DDE5DE;border-radius:10px;padding:14px 16px;min-width:0;}
    .fx-mcard-label{font-size:0.7rem;font-weight:700;color:#8a9490;text-transform:uppercase;letter-spacing:0.4px;}
    .fx-mcard-value{font-size:1.15rem;font-weight:800;color:#1f2a24;margin-top:2px;font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .fx-mcard-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;}
    .fx-cards3{grid-template-columns:repeat(3,minmax(0,1fr));}

    /* ---- money breakdown donut pair ---- */
    .fx-bd{display:grid;grid-template-columns:1fr 1fr;gap:18px;}
    @media(max-width:900px){.fx-bd{grid-template-columns:1fr;}}
    .fx-bd-side{text-align:center;background:#fafcfa;border:1px solid #EDF1EE;border-radius:10px;padding:18px 14px 12px;}
    .fx-bd-donut{width:150px;height:150px;border-radius:50%;margin:0 auto;position:relative;}
    .fx-bd-hole{position:absolute;inset:26px;background:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;color:#1f2a24;font-size:0.92rem;font-variant-numeric:tabular-nums;}
    .fx-bd-caption{font-size:0.8rem;font-weight:700;color:#5f6b64;margin-top:8px;}
    .fx-bd-legend{text-align:left;margin-top:14px;font-size:0.8rem;color:#1f2a24;}
    .fx-bd-legend div{display:flex;align-items:center;gap:8px;padding:5px 0;}
    .fx-bd-legend .amt{margin-left:auto;font-variant-numeric:tabular-nums;color:#5f6b64;white-space:nowrap;}

    /* ---- View All link ---- */
    .fx-viewall{border:none;background:none;color:#166a3b;font-weight:700;font-size:0.8rem;cursor:pointer;font-family:inherit;padding:0;flex:none;}
    .fx-viewall:hover{text-decoration:underline;}
    @media(max-width:1100px){.fx-cards4{grid-template-columns:repeat(2,minmax(0,1fr));}}
    @media(max-width:640px){.fx-cards4{grid-template-columns:1fr;}}

    /* ---- treasurer overview strip (4 KPI cards: label + icon chip + value + sub) ---- */
    .fx-ovw4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-bottom:20px;}
    .fx-ovw-card{background:#fff;border:1px solid #DDE5DE;border-radius:12px;padding:20px;min-width:0;}
    .fx-ovw-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;}
    .fx-ovw-label{font-size:0.7rem;font-weight:700;color:#8a9490;text-transform:uppercase;letter-spacing:0.6px;line-height:1.5;padding-top:4px;}
    .fx-ovw-chip{width:34px;height:34px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:0.85rem;flex:0 0 34px;}
    .fx-ovw-value{font-size:1.8rem;font-weight:800;color:#1a1a1a;margin-top:8px;font-variant-numeric:tabular-nums;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .fx-ovw-sub{font-size:0.78rem;color:#8a9490;margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .fx-ovw-sub .fx-dotsep{margin:0 8px;color:#c3cdc5;}
    @media(max-width:1100px){.fx-ovw4{grid-template-columns:repeat(2,minmax(0,1fr));}}
    @media(max-width:640px){.fx-ovw4{grid-template-columns:1fr;}}

    /* ---- transaction type chips ---- */
    .fx-chip{display:inline-block;padding:3px 10px;border-radius:999px;font-size:0.72rem;font-weight:700;white-space:nowrap;}
    .fx-chip-in{background:#e9f4ec;color:#166a3b;border:1px solid #bfe3cb;}
    .fx-chip-out{background:#fdeeee;color:#9a2f2f;border:1px solid #f0cccc;}
    .fx-chip + .fx-chip{margin-left:4px;}
    .fx-detail{font-size:0.78rem;color:#5f6b64;margin-top:2px;display:block;}
    .fx-detail b{font-variant-numeric:tabular-nums;}
    .fx-net-tag{font-size:0.62rem;font-weight:700;color:#8a9490;text-transform:uppercase;letter-spacing:0.5px;margin-left:4px;}
  `;

  let stylesInjected = false;
  function ensureStyles() {
    if (stylesInjected) return;
    const style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);
    stylesInjected = true;
  }

  const PESO = (v) => "₱" + Number(v || 0).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const PESO0 = (v) => "₱" + Number(v || 0).toLocaleString("en-PH", { maximumFractionDigits: 0 });
  const esc = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const label = (source) => SOURCE_LABELS[source] || source || "Other";
  const sign = (v) => (v >= 0 ? "+" : "−") + PESO(Math.abs(v));
  const chip = (t) => `<span class="fx-chip ${t.direction === "inflow" ? "fx-chip-in" : "fx-chip-out"}">${esc(label(t.source_type))}</span>`;

  async function getJSON(url) {
    try {
      const res = await fetch(url, { credentials: "same-origin" });
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  /* ================= Fund Overview page ================= */

  /* Balance line chart. `startBalance` anchors a filtered window (a
     mid-history range must not restart from ₱0). An area fill under the
     line plus dots colored per movement direction. */
  function trendSvg(trend, startBalance) {
    if (!trend || !trend.length) return '<div class="fx-empty">No fund movements recorded yet.</div>';
    const w = 560, h = 210, padX = 46, padY = 18;
    const base = typeof startBalance === "number" ? startBalance : 0;
    const pts = [{ balance: base }].concat(trend);
    const values = pts.map((p) => p.balance);
    const min = Math.min(...values, base);
    const max = Math.max(...values, base, 1);
    const span = max - min || 1;
    const step = (w - padX * 2) / Math.max(pts.length - 1, 1);
    const yOf = (balance) => padY + (1 - (balance - min) / span) * (h - padY * 2);
    const ptsAttr = pts.map((p, i) => `${(padX + i * step).toFixed(1)},${yOf(p.balance).toFixed(1)}`).join(" ");
    const y0 = (padY + (h - padY * 2)).toFixed(1);
    const areaAttr = `M ${ptsAttr.replace(/ /g, " L ")} L ${(padX + (pts.length - 1) * step).toFixed(1)},${y0} L ${padX},${y0} Z`;
    const gridLines = [0, 0.5, 1].map((t) => {
      const y = (padY + t * (h - padY * 2)).toFixed(1);
      const val = max - t * span;
      return `<line x1="${padX - 6}" y1="${y}" x2="${w - 4}" y2="${y}" stroke="#EDF1EE" stroke-width="1" />
        <text x="${padX - 10}" y="${Number(y) + 3}" font-size="9" fill="#8a9490" text-anchor="end">${PESO0(val)}</text>`;
    }).join("");
    // X labels: first movement, each time the month changes, and the last one.
    const labels = trend
      .map((t, i) => ({ t, i: i + 1 }))
      .filter(({ t, i }) => i === 1 || i === trend.length || t.label.split(" ")[0] !== trend[i - 2].label.split(" ")[0])
      .map(({ t, i }) => {
        const x = padX + i * step;
        return `<text x="${x.toFixed(1)}" y="${h - 2}" font-size="9.5" fill="#8a9490" text-anchor="middle">${esc(t.label)}</text>`;
      })
      .join("");
    const dots = trend
      .map((t, i) => {
        const x = padX + (i + 1) * step;
        const y = yOf(t.balance);
        const color = t.direction === "inflow" ? "#1e8f4e" : "#b93a3a";
        const tip = `${t.label} · ${t.direction === "inflow" ? "+" : "−"}${PESO(t.amount)} · fund at ${PESO(t.balance)}`;
        return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="${color}"><title>${esc(tip)}</title></circle>`;
      })
      .join("");
    return `<svg viewBox="0 0 ${w} ${h}" style="width:100%;height:auto;display:block;">
      ${gridLines}
      <path d="${areaAttr}" fill="rgba(30,143,78,0.08)" stroke="none" />
      <polyline points="${ptsAttr}" fill="none" stroke="#1e8f4e" stroke-width="2.5" stroke-linejoin="round" />
      ${dots}
      ${labels}
    </svg>`;
  }

  /* Trend always shows the FULL history — every movement from ₱0 to now. */
  function fxTrendBody(trend) {
    if (!trend || !trend.length) return '<div class="fx-empty">No fund movements recorded yet.</div>';
    return trendSvg(trend, 0) +
      `<div class="fx-legend">
        <span><span class="fx-dot" style="background:#1e8f4e;"></span>Collections (+)</span>
        <span><span class="fx-dot" style="background:#b93a3a;"></span>Expenses (&minus;)</span>
      </div>`;
  }

  /* One donut + its legend with peso amounts and share %. Two readability rules:
     1. Colors are per LEGEND GROUP and shared by the ring segments and the
        dots — a slice never wears a color the legend doesn't show.
     2. Slices are drawn in LEGEND ORDER starting at 12 o'clock, and each
        named group gets a small MINIMUM arc so tiny shares (0.2%) stay
        findable in the ring like the Expenses donut. The minimum is purely
        visual — Other's arc absorbs it and the printed % stays truthful.
     Shows up to 6 named sources individually before aggregating the rest
     into "Other" so Membership Fee, Monthly Dues, etc. stay visible. */
  function breakdownDonut(entries, caption, color) {
    const ramps = {
      green: ["#1e8f4e", "#5aad77", "#8cc7a0", "#b8dfc6", "#166a3b", "#8fd4ab", "#4a9c6e", "#a8dcc0"],
      red: ["#b93a3a", "#c96b62", "#d98f88", "#e8b5b0", "#9a2f2f", "#e2a49e"],
    };
    const ramp = ramps[color] || ramps.green;
    const MIN_VIS = 2; /* % of ring guaranteed to each named group */
    const items = entries || [];
    const total = items.reduce((s, e) => s + e.total, 0);
    const isOther = (e) => label(e.source !== undefined ? e.source : e.label) === "Other";
    const namedPool = items.filter((e) => !isOther(e));
    const named = namedPool.slice(0, 6);
    const restTotal = namedPool.slice(6).concat(items.filter(isOther)).reduce((s, e) => s + e.total, 0);
    const groups = named.map((e) => ({ item: e, total: e.total }));
    const hasOther = restTotal > 0.005;
    if (hasOther) groups.push({ item: null, total: restTotal });
    const shareOf = (g) => (total ? (g.total / total) * 100 : 0);
    /* Visual arcs: named groups get at least MIN_VIS; the last group
       (Other, or the only group when nothing is aggregated) absorbs the
       difference so the ring still totals 100%. */
    const vis = groups.map((g) => shareOf(g));
    if (groups.length > 1) {
      let deficit = 0;
      for (let i = 0; i < groups.length - 1; i++) {
        if (vis[i] < MIN_VIS) { deficit += MIN_VIS - vis[i]; vis[i] = MIN_VIS; }
      }
      vis[vis.length - 1] = Math.max(vis[vis.length - 1] - deficit, 1);
    }
    let acc = 0;
    const stops = vis
      .map((v, i) => {
        const stop = `${ramp[i % ramp.length]} ${acc.toFixed(2)}% ${(acc + v).toFixed(2)}%`;
        acc += v;
        return stop;
      })
      .join(", ");
    const legend = groups
      .map((g, i) => {
        const display = g.item ? g.item.source : "Other";
        return `<div>
            <span class="fx-dot" style="background:${ramp[i % ramp.length]};"></span>
            <span>${esc(display === "Other" ? "Other" : label(display))}</span>
            <span class="amt">${PESO(g.total)} (${shareOf(g).toFixed(1)}%)</span>
          </div>`;
      })
      .join("");
    const donut = total > 0
      ? `<div class="fx-bd-donut" style="background:conic-gradient(${stops});"><div class="fx-bd-hole">${PESO(total)}</div></div>`
      : `<div class="fx-bd-donut" style="background:#EDF1EE;"><div class="fx-bd-hole">₱0.00</div></div>`;
    return `<div class="fx-bd-side">
        ${donut}
        <div class="fx-bd-caption">${esc(caption)}</div>
        <div class="fx-bd-legend">${legend || '<div><span class="fx-dot" style="background:#c3cdc5;"></span><span>Nothing recorded yet</span></div>'}</div>
      </div>`;
  }

  window.nxFundOverview = {
    async load(silent) {
      const root = document.getElementById("fund-overview-root");
      if (!root) return;
      ensureStyles();
      if (!silent) root.innerHTML = '<div class="fx-card fx-empty">Loading the fund overview…</div>';
      const d = await getJSON("/api/fund/overview/");
      if (!d || !d.ok) {
        root.innerHTML = '<div class="fx-card fx-empty">Could not load the fund overview.</div>';
        return;
      }
      const go = (target) => `onclick="if(typeof setActiveModule==='function')setActiveModule('${target}')"`;

      /* Recent activity flattened to plain rows: one line per covered month
         of dues (with the aid-fund set-aside folded into the description),
         one per released payout, one per standalone movement. */
      const recent = (d.recent || [])
        .map((g) => {
          if (g.row_type === "month") {
            const desc = [];
            if (g.in_members > 0) desc.push(`Dues collection from ${g.in_members} member${g.in_members === 1 ? "" : "s"}`);
            if (g.out_total > 0.005) desc.push(`aid fund set-aside from ${g.out_members} member${g.out_members === 1 ? "" : "s"}' dues`);
            if (!desc.length) desc.push(esc(g.month) + " dues recording");
            const netShown = g.out_total > 0;
            return `<tr>
                <td>${esc(g.date)}</td>
                <td><span class="fx-chip fx-chip-in">Monthly Dues</span></td>
                <td>${desc.join(" · ")}</td>
                <td class="fx-num ${g.amount >= 0 ? "fx-pos" : "fx-neg"}">${sign(g.amount)}${netShown ? '<span class="fx-net-tag">net</span>' : ""}</td>
              </tr>`;
          }
          if (g.row_type === "release") {
            const desc = g.member && g.aid_type
              ? `${esc(g.aid_type)} released to ${esc(g.member)}`
              : esc(g.description);
            return `<tr>
                <td>${esc(g.date)}</td>
                <td>${chip({ direction: "outflow", source_type: "aid_post_payment" })}</td>
                <td>${desc}</td>
                <td class="fx-num fx-neg">−${PESO(g.amount)}</td>
              </tr>`;
          }
          return `<tr>
              <td>${esc(g.date)}</td>
              <td>${chip({ direction: g.direction, source_type: g.source_type })}</td>
              <td>${esc(g.description)}</td>
              <td class="fx-num ${g.direction === "inflow" ? "fx-pos" : "fx-neg"}">${g.direction === "inflow" ? "+" : "−"}${PESO(g.amount)}</td>
            </tr>`;
        })
        .join("");

      root.innerHTML = `
        <div class="fx-cards4 fx-cards3">
          <div class="fx-mcard">
            <div><div class="fx-mcard-label">Current Balance</div><div class="fx-mcard-value">${PESO(d.balance)}</div></div>
          </div>
          <div class="fx-mcard">
            <div><div class="fx-mcard-label">Total Money In</div><div class="fx-mcard-value fx-pos">${PESO(d.money_in)}</div></div>
          </div>
          <div class="fx-mcard">
            <div><div class="fx-mcard-label">Total Money Out</div><div class="fx-mcard-value fx-neg">${PESO(d.money_out)}</div></div>
          </div>
        </div>

        <div class="fx-grid2" style="margin-bottom:16px;">
          <div class="fx-card" style="margin-bottom:0;">
            <div class="fx-mcard-head">
              <div>
                <h3 class="fx-title">Fund Balance Trend</h3>
                <p class="fx-subtitle" style="margin-bottom:0;">Balance movement across monthly collections and expenses.</p>
              </div>
            </div>
            <div id="fx-trend-body" style="margin-top:12px;">${fxTrendBody(d.trend || [])}</div>
          </div>

          <div class="fx-card" style="margin-bottom:0;">
            <div class="fx-mcard-head">
              <div>
                <h3 class="fx-title">Money Breakdown</h3>
                <p class="fx-subtitle" style="margin-bottom:0;">Where the funds came from and where they were used</p>
              </div>
            </div>
            <div class="fx-bd" style="margin-top:12px;">
              ${breakdownDonut(d.inflow_breakdown || [], "Collections", "green")}
              ${breakdownDonut(d.outflow_breakdown || [], "Expenses", "red")}
            </div>
          </div>
        </div>

        <div class="fx-card">
          <div class="fx-mcard-head">
            <div>
              <h3 class="fx-title">Recent Fund Transactions</h3>
              <p class="fx-subtitle" style="margin-bottom:0;">Latest recorded transactions for this period</p>
            </div>
            <button type="button" class="fx-viewall" ${go("fund-ledger")}>View All &rarr;</button>
          </div>
          <div class="fx-table-wrap" style="margin-top:10px;">
          <table class="fx-table">
            <thead><tr><th>Transaction Date</th><th>Transaction Type</th><th>Details</th><th class="fx-num">Amount</th></tr></thead>
            <tbody>${recent || '<tr><td colspan="4" class="fx-empty">No fund movements recorded yet.</td></tr>'}</tbody>
          </table>
          </div>
        </div>`;
    },
  };

  /* ================= Dashboard fund section (top of Overview) ================= */

  /* Compact ISUCauFA, Inc. fund summary for the Overview page. Deliberately a
     SUMMARY only — the complete trend / cash-flow / source breakdowns stay
     on the dedicated Fund Overview module, and every movement stays in the
     Fund Ledger module (both linked from here). */
  window.nxFundDashboard = {
    async load() {
      const root = document.getElementById("nxf-root");
      if (!root) return;
      ensureStyles();
      root.innerHTML = '<div class="fx-fundcard fx-loading">Loading fund…</div>';
      const d = await getJSON("/api/fund/overview/");
      if (!d || !d.ok) {
        root.innerHTML = '<div class="fx-fundcard fx-loading">Fund overview unavailable right now.</div>';
        return;
      }

      const go = (target) => `onclick="if(typeof setActiveModule==='function')setActiveModule('${target}')"`;
      const OVW_MONTH = new Date().toLocaleString("en-PH", { month: "long", year: "numeric" });
      root.innerHTML = `
        <div class="fx-fundcard">
          <div class="fx-fundmain">
            <div class="fx-kpi-label">CASH ON-HAND AS OF ${OVW_MONTH}</div>
            <div class="fx-fundbalance ${d.balance >= 0 ? "pos" : "neg"}">${PESO(d.balance)}</div>
          </div>
          <div class="fx-fundstats">
            <div class="fx-fundstat">
              <div class="fx-kpi-label">COLLECTIONS OF ${OVW_MONTH}</div>
              <div class="fx-fundval pos">+${PESO(d.month_in)}</div>
            </div>
            <div class="fx-fundstat">
              <div class="fx-kpi-label">DISBURSEMENTS OF ${OVW_MONTH}</div>
              <div class="fx-fundval neg">&minus;${PESO(d.month_out)}</div>
            </div>
          </div>
          <div class="fx-fundlinks">
            <button type="button" class="fx-fundlink" ${go("fund-overview")}>Fund Overview</button>
            <button type="button" class="fx-fundlink" ${go("fund-ledger")}>General Fund Ledger</button>
          </div>
        </div>`;
    },
  };

  /* ================= Fund Ledger page ================= */

  const FX_LEDGER_PAGE_SIZE = 15;
  let fxLedgerPage = 1;
  window.__fxLedgerGoPage = function (p) {
    fxLedgerPage = p;
    window.nxFundLedger.load();
  };

  window.nxFundLedger = {
    async load() {
      const root = document.getElementById("fund-ledger-root");
      if (!root) return;
      ensureStyles();
      if (!root.dataset.loaded) root.innerHTML = '<div class="fx-card fx-empty">Loading the record of money…</div>';
      const d = await getJSON("/api/fund/ledger/");
      if (!d || !d.ok) {
        root.innerHTML = '<div class="fx-card fx-empty">Could not load the fund ledger.</div>';
        return;
      }
      root.dataset.loaded = "1";

      const entries = d.entries || [];
      const pageCount = Math.max(1, Math.ceil(entries.length / FX_LEDGER_PAGE_SIZE));
      fxLedgerPage = Math.min(Math.max(fxLedgerPage, 1), pageCount);
      const pageEntries = entries.slice((fxLedgerPage - 1) * FX_LEDGER_PAGE_SIZE, fxLedgerPage * FX_LEDGER_PAGE_SIZE);

      const rows = pageEntries
        .map(
          (t) => `<tr>
              <td>${esc(t.date)}</td>
              <td>${chip(t)}</td>
              <td>${esc(t.description || "—")}</td>
              <td class="fx-num ${t.direction === "inflow" ? "fx-pos" : "fx-neg"}">${t.direction === "inflow" ? "+" : "−"}${PESO(t.amount)}</td>
            </tr>`
        )
        .join("");

      root.innerHTML = `
        <div class="fx-card">
          <div class="fx-quick" style="margin-bottom:0;">
            <div class="fx-quick-cell"><div class="fx-quick-label">Total Money In</div><div class="fx-quick-value fx-pos">+${PESO(d.money_in)}</div></div>
            <div class="fx-quick-cell"><div class="fx-quick-label">Total Money Out</div><div class="fx-quick-value fx-neg">−${PESO(d.money_out)}</div></div>
            <div class="fx-quick-cell"><div class="fx-quick-label">Current Fund</div><div class="fx-quick-value" style="color:${d.balance >= 0 ? "#1e8f4e" : "#b93a3a"};">${PESO(d.balance)}</div></div>
          </div>
        </div>
        <div class="fx-card">
          <h3 class="fx-title">General Fund Log</h3>
          <p class="fx-subtitle">Complete log of all receipts and disbursements in reverse chronological order.</p>
          <div class="fx-table-wrap">
          <table class="fx-table">
            <thead><tr><th>Transaction Date</th><th>Transaction Type</th><th>Details</th><th class="fx-num">Amount</th></tr></thead>
            <tbody>${rows || '<tr><td colspan="4" class="fx-empty">No fund movements recorded yet.</td></tr>'}</tbody>
          </table>
          </div>
          <div id="fx-ledger-pagination" style="margin-top:10px;"></div>
        </div>`;
      const pager = document.getElementById("fx-ledger-pagination");
      if (pager && typeof UniPager !== "undefined" && entries.length) {
        pager.innerHTML = UniPager.html(fxLedgerPage, pageCount, "window.__fxLedgerGoPage(PAGE)", UniPager.count(fxLedgerPage, FX_LEDGER_PAGE_SIZE, entries.length));
      }
    },
  };

  /* ================= Unified overview cards (treasurer overview strip) ================= */

  /* Four KPI cards — Fund Balance, Collected This Month, Money Out, Active
     Members — same live figures as before (fund balance, current-month
     collections / disbursements, member headcount), presented with a label
     row + icon chip, a large value, and a context sub-line. */
  window.nxOverviewCards = {
    async load() {
      const root = document.getElementById("ovw-cards-root");
      if (!root) return;
      ensureStyles();
      root.innerHTML = '<div class="fx-card fx-empty">Loading overview…</div>';
      const d = await getJSON("/api/fund/overview/");
      if (!d || !d.ok) {
        root.innerHTML = '<div class="fx-card fx-empty">Fund summary unavailable right now.</div>';
        return;
      }
      const MON = new Date().toLocaleString("en-PH", { month: "long", year: "numeric" });
      const active = d.active_members != null ? d.active_members : 0;
      const perm = d.permanent_members != null ? d.permanent_members : 0;
      const temp = d.temporary_members != null ? d.temporary_members : 0;
      const retired = d.retired_members != null ? d.retired_members : 0;
      root.innerHTML = `
        <div class="fx-ovw4">
          <div class="fx-ovw-card">
            <div class="fx-ovw-top">
              <div class="fx-ovw-label">Fund Balance</div>
              <span class="fx-ovw-chip" style="background:#e7f6ec;color:#16703c;font-weight:800;">&#8369;</span>
            </div>
            <div class="fx-ovw-value">${PESO(d.balance)}</div>
            <div class="fx-ovw-sub">Available Liquid Funds</div>
          </div>
          <div class="fx-ovw-card">
            <div class="fx-ovw-top">
              <div class="fx-ovw-label">Collected This Month</div>
              <span class="fx-ovw-chip" style="background:#e8effd;color:#2f6fed;"><i class="fas fa-arrow-up"></i></span>
            </div>
            <div class="fx-ovw-value">${PESO(d.month_in)}</div>
            <div class="fx-ovw-sub">Collections of ${esc(MON)}</div>
          </div>
          <div class="fx-ovw-card">
            <div class="fx-ovw-top">
              <div class="fx-ovw-label">Money Out (Expenses)</div>
              <span class="fx-ovw-chip" style="background:#fdf0dd;color:#c77414;"><i class="fas fa-arrow-down"></i></span>
            </div>
            <div class="fx-ovw-value">${PESO(d.month_out)}</div>
            <div class="fx-ovw-sub">Disbursements of ${esc(MON)}</div>
          </div>
          <div class="fx-ovw-card">
            <div class="fx-ovw-top">
              <div class="fx-ovw-label">Members</div>
              <span class="fx-ovw-chip" style="background:#ece7fd;color:#6d4fc2;"><i class="fas fa-users"></i></span>
            </div>
            <div class="fx-ovw-value">${Number(active).toLocaleString("en-PH")}</div>
            <div class="fx-ovw-sub">Permanent: ${Number(perm).toLocaleString("en-PH")}<span class="fx-dotsep">\u2022</span>Temporary: ${Number(temp).toLocaleString("en-PH")}<span class="fx-dotsep">\u2022</span>Retired: ${Number(retired).toLocaleString("en-PH")}</div>
          </div>
        </div>`;
    },
  };
  document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("ovw-cards-root")) window.nxOverviewCards.load();
  });

  /* ================= dashboard flow graph (Money In vs Money Out) ================= */

  /* Compact Money In vs Money Out graph for the officer Overview pages —
     same data and same bar design as the Fund Overview page's Monthly Cash
     Flow section, rendered as plain HTML/CSS so it behaves identically on
     all three dashboards (no chart-library quirks). Re-drawn whenever the
     Overview module is opened. */
  window.nxFundFlow = {
    _cache: null,
    async load() {
      const box = document.getElementById("fundFlow");
      if (!box) return;
      const d = nxFundFlow._cache || (nxFundFlow._cache = await getJSON("/api/fund/overview/"));
      if (!d || !d.ok || !Array.isArray(d.series) || !d.series.length) {
        box.innerHTML = '<p class="pd-card-placeholder">No fund activity data yet.</p>';
        return;
      }
      ensureStyles();
      const series = d.series.slice(-6);
      const maxBar = Math.max(...series.map((x) => Math.max(x.money_in, x.money_out)), 1);
      box.innerHTML =
        '<div class="fx-bars fx-bars-compact">'
        + series.map((s) => `
          <div class="fx-bar-row">
            <div class="fx-bar-month">${esc(s.label)}</div>
            <div class="fx-bar-track" title="Money In ${PESO(s.money_in)} · Money Out ${PESO(s.money_out)}">
              <div class="fx-bar-in" style="width:${Math.max(1.5, (s.money_in / maxBar) * 100).toFixed(1)}%;"></div>
              <div class="fx-bar-out" style="width:${Math.max(1.5, (s.money_out / maxBar) * 100).toFixed(1)}%;"></div>
            </div>
            <div class="fx-bar-amt">In <b class="fx-pos">${PESO0(s.money_in)}</b> · Out <b class="fx-neg">${PESO0(s.money_out)}</b></div>
          </div>`).join("")
        + '</div>'
        + '<div class="fx-legend"><span><span class="fx-dot" style="background:#1e8f4e;"></span>Collections (+)</span><span><span class="fx-dot" style="background:#b93a3a;"></span>Expenses (&minus;)</span></div>';
    },
  };

  /* ================= dashboard "Financial Overview" card ================= */

  /* Renders the same totals and breakdowns the ISUCauFA, Inc. Fund Overview /
     Fund Ledger modules show (same endpoint, same labels) into a host
     dashboard card: Treasurer "Fund Summary", President "Financial
     Overview". Re-rendered on websocket fund_updated via nxFundRefreshAll
     so the card can never drift from the fund modules. */
  window.nxFundSummaryWidget = {
    load(rootId) {
      const root = document.getElementById(rootId || "nxFundSummary");
      if (!root) return;
      ensureStyles();
      const render = (d) => {
        if (!d || !d.ok) {
          root.innerHTML = '<p class="pd-card-placeholder">Fund data unavailable right now.</p>';
          return;
        }
        const inBk = (d.inflow_breakdown || []).map((e) => {
          const subs = (e.sub_items || []).map((s) =>
            `<div class="pd-bk-row" style="padding-left:14px;"><span class="l">${esc("· " + label(s.label))}</span><span class="v pos">+${PESO(s.total)}</span></div>`
          ).join("");
          return `<div class="pd-bk-row"><span class="l">${esc(label(e.source))}</span><span class="v pos">+${PESO(e.total)}</span></div>${subs}`;
        }).join("") || '<div class="pd-bk-row"><span class="l">None yet</span><span class="v">—</span></div>';
        const outBk = (d.outflow_breakdown || []).map((e) =>
          `<div class="pd-bk-row"><span class="l">${esc(label(e.source))}</span><span class="v neg">&minus;${PESO(e.total)}</span></div>`
        ).join("") || '<div class="pd-bk-row"><span class="l">None yet</span><span class="v">—</span></div>';
        root.innerHTML = `
          <div class="pd-bk-section" style="margin-bottom:12px;">
            <div class="pd-bk-title">Overview</div>
            <div class="pd-bk-row"><span class="l">Total Money In</span><span class="v pos">+${PESO(d.money_in)}</span></div>
            <div class="pd-bk-row"><span class="l">Total Money Out</span><span class="v neg">&minus;${PESO(d.money_out)}</span></div>
            <div class="pd-bk-row"><span class="l">Current Balance</span><span class="v total">${PESO(d.balance)}</span></div>
          </div>
          <div class="pd-fundsummary-grid">
            <div class="pd-bk-section">
              <div class="pd-bk-title">Inflow Breakdown</div>
              ${inBk}
            </div>
            <div class="pd-bk-section">
              <div class="pd-bk-title">Outflow Breakdown</div>
              ${outBk}
            </div>
          </div>`;
        /* Keep the president's "Total Fund Balance" KPI in lockstep too. */
        const kpi = document.getElementById("kpi-funds");
        if (kpi) kpi.textContent = PESO(d.balance);
      };
      const cached = nxFundFlow._cache;
      if (cached) { render(cached); return; }
      getJSON("/api/fund/overview/").then((data) => {
        nxFundFlow._cache = data;
        render(data);
      });
    },
  };

  /* Redraw the flow graph whenever the Overview module is opened. */
  if (!window.__nxFundFlowBound) {
    window.__nxFundFlowBound = true;
    document.addEventListener("click", function (e) {
      if (e.target.closest && e.target.closest('[data-target="dashboard-overview"]')) {
        setTimeout(() => window.nxFundFlow.load(), 250);
      }
    });
  }

  /* ================= dashboard strip (legacy — unused) ================= */

  window.nxFundStrip = {
    async load() {
      const strip = document.getElementById("nx-fund-strip");
      if (!strip) return;
      ensureStyles();
      strip.innerHTML = '<span class="fx-kpi-label" style="color:#6b7280;">Loading fund…</span>';
      const d = await getJSON("/api/fund/overview/");
      if (!d || !d.ok) {
        strip.innerHTML = '<span class="fx-kpi-label">Fund overview unavailable right now.</span>';
        return;
      }
      strip.innerHTML = `
        <span><span class="fx-kpi-label">Current Fund</span> <span class="fx-kpi-value" style="color:#1e8f4e;">${PESO(d.balance)}</span></span>
        <span><span class="fx-kpi-label">Money In</span> <span class="fx-kpi-value fx-pos">+${PESO(d.month_in)}</span> <span class="fx-kpi-label">this month</span></span>
        <span><span class="fx-kpi-label">Money Out</span> <span class="fx-kpi-value fx-neg">−${PESO(d.month_out)}</span> <span class="fx-kpi-label">this month</span></span>
        <span><span class="fx-kpi-label">Fund Status</span> <span class="fx-kpi-value">${d.balance > 0 ? "Good" : "Low"}</span></span>`;
    },
  };

  /* Reload every fund widget currently on screen — called when a websocket
     `fund_updated` event arrives so officers never need a manual refresh.
     Debounced: an approval books many movements at once, and each fires the
     signal; one reload covers them all. */
  let __fundRefreshTimer = null;
  window.nxFundRefreshAll = function nxFundRefreshAll() {
    if (__fundRefreshTimer) clearTimeout(__fundRefreshTimer);
    __fundRefreshTimer = setTimeout(() => {
      __fundRefreshTimer = null;
      nxFundFlow._cache = null;
      if (document.getElementById("fund-overview-root")) window.nxFundOverview.load();
      if (document.getElementById("fund-ledger-root")) window.nxFundLedger.load();
      if (document.getElementById("nxf-root")) window.nxFundDashboard.load();
      if (document.getElementById("fundFlow")) window.nxFundFlow.load();
      if (document.getElementById("nxFundSummary")) window.nxFundSummaryWidget.load("nxFundSummary");
    }, 600);
  };

  function loadAll() {
    window.nxFundOverview.load();
    window.nxFundDashboard.load();
    window.nxFundLedger.load();
    window.nxFundFlow.load();
    if (document.getElementById("nxFundSummary")) window.nxFundSummaryWidget.load("nxFundSummary");
  }

  document.addEventListener("turbo:load", loadAll);
  if (document.readyState !== "loading") loadAll();
  else document.addEventListener("DOMContentLoaded", loadAll);

  if (!window.__nxFundClickBound) {
    window.__nxFundClickBound = true;
    document.addEventListener("click", function (e) {
      if (e.target.closest && e.target.closest('[data-target="fund-overview"]')) {
        setTimeout(() => window.nxFundOverview.load(), 200);
      }
      if (e.target.closest && e.target.closest('[data-target="fund-ledger"]')) {
        setTimeout(() => window.nxFundLedger.load(), 200);
      }
    });
  }
})();
