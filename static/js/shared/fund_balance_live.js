// fund_balance_live.js — Fund Balance / Available Liquid Funds auto-update.
//
// Every dashboard renders its fund-balance numbers once on page load
// (President #fund-balance-summary, officer #kpi-funds, member
// #fundBalance/#fundInflow/#fundOutflow). This module re-fetches the
// existing /api/fund-balance/ endpoint and repaints whichever of those
// hooks exist on the current page, so the numbers stay correct with no
// page refresh.
//
// Transport reuses the existing realtime service (shared/realtime.js):
//   * instant refresh on the websocket `fund_updated` event (broadcast by
//     broadcast_fund_update() on every FundTransaction write), and
//   * the service's 5-second polling fallback + reconnect resync while the
//     socket is down (e.g. plain WSGI hosting with no ASGI server).
//
// Wiring (one script tag per dashboard, after shared/realtime.js):
//   <script src=".../shared/fund_balance_live.js"
//           data-fund-balance-live
//           data-channel="treasurer" data-path="/ws/treasurer-dashboard/"></script>
(function () {
  "use strict";

  var POLL_MS = 5000;
  var DEBOUNCE_MS = 500;
  var bound = false;
  var refreshTimer = null;

  function config() {
    var el = document.querySelector("script[data-fund-balance-live]");
    return {
      channel: (el && el.getAttribute("data-channel")) || "treasurer",
      path: (el && el.getAttribute("data-path")) || "/ws/treasurer-dashboard/",
    };
  }

  function peso(n) {
    var v = Number(n || 0);
    if (!isFinite(v)) v = 0;
    return "\u20B1" + v.toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  // Same masked-placeholder guard the member dashboard uses: a masked
  // value must never be coerced to a number (it would render ₱NaN).
  function pesoOrMasked(n) {
    return (n === null || n === undefined || n === "\u2022\u2022\u2022\u2022\u2022\u2022") ? "\u20B1\u2022\u2022\u2022\u2022\u2022\u2022" : peso(n);
  }

  function hasFundCard() {
    return !!(document.getElementById("fund-balance-summary") ||
              document.getElementById("kpi-funds") ||
              document.getElementById("fundBalance") ||
              document.getElementById("cohBalance"));
  }

  function paint(data) {
    if (!data || !data.ok) return;

    // President "Fund Balance" card (Current Balance / Safety Threshold /
    // Available / Month In-Out): reuse its own renderer so the markup has
    // a single source of truth.
    if (document.getElementById("fund-balance-summary") &&
        typeof window.loadFundBalance === "function") {
      try { window.loadFundBalance(); } catch (e) {}
    }

    // Officer KPI cards (Treasurer / Auditor / President). Both this
    // endpoint's `balance` and the inflow-outflow endpoint's
    // `fund_balance` are lifetime total_in - total_out, so they agree.
    var kpi = document.getElementById("kpi-funds");
    if (kpi) {
      kpi.textContent = peso(data.balance);
      kpi.dataset.liveLoaded = "true";
    }

    // Member "CauFA Funds" cards.
    var fb = document.getElementById("fundBalance");
    if (fb) fb.textContent = pesoOrMasked(data.balance);
    var fi = document.getElementById("fundInflow");
    if (fi) fi.textContent = pesoOrMasked(data.total_in);
    var fo = document.getElementById("fundOutflow");
    if (fo) fo.textContent = pesoOrMasked(data.total_out);

    // Member overview hero + movement tiles share the same figures.
    var coh = document.getElementById("cohBalance");
    if (coh) coh.textContent = pesoOrMasked(data.balance);
    var fmIn = document.getElementById("fmIn");
    if (fmIn) fmIn.textContent = pesoOrMasked(data.total_in);
    var fmOut = document.getElementById("fmOut");
    if (fmOut) fmOut.textContent = pesoOrMasked(data.total_out);

    // Keep the heavier fund modules (overview / ledger / flow / summary
    // widgets) in lockstep too — debounced inside, so sharing the event
    // with the per-role websocket.js handlers costs nothing extra.
    if (typeof window.nxFundRefreshAll === "function") {
      try { window.nxFundRefreshAll(); } catch (e) {}
    }
  }

  function refresh() {
    fetch("/api/fund-balance/", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(paint)
      .catch(function () {});
  }

  function refreshSoon() {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(function () { refreshTimer = null; refresh(); }, DEBOUNCE_MS);
  }

  function bind() {
    if (bound || !hasFundCard()) return;
    bound = true;
    var cfg = config();
    if (window.CaufaRealtime && typeof window.CaufaRealtime.subscribe === "function") {
      window.CaufaRealtime.subscribe({
        channel: cfg.channel,
        path: cfg.path,
        events: ["fund_updated"],
        onEvent: refreshSoon,
        poll: refresh,
        pollIntervalMs: POLL_MS,
      });
    } else if (!window.__fundBalanceLiveFallback) {
      // Realtime service not on this page — plain visible-tab polling.
      window.__fundBalanceLiveFallback = true;
      setInterval(function () {
        if (document.visibilityState !== "hidden") refresh();
      }, POLL_MS * 2);
      refresh();
    }
  }

  if (document.readyState !== "loading") bind();
  else document.addEventListener("DOMContentLoaded", bind);
  document.addEventListener("turbo:load", bind);
})();
