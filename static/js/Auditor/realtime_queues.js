// realtime_queues.js — Auditor verification queues on the central realtime
// runner (window.CaufaRealtime).
//
// Covered, all without a manual Refresh click:
//   * Pending Aid Claims Verification  (#aid-verify-requests, nxVerifyAid.load)
//   * Pending Dues Verification        (#audit-verify-deduction, loadAuditDeductionQueue)
//   * Pending Reports Verification     (#treasurer-reports-management, audLoadFundReports)
//
// Each queue refreshes instantly on its websocket events and otherwise
// re-polls every 5 seconds — but only while its module is actually open,
// so background tabs and other modules cost no requests.
(function () {
  "use strict";

  var POLL_MS = 5000;
  var bound = false;

  function sectionVisible(id) {
    var el = document.getElementById(id);
    if (!el || !el.classList.contains("active")) return false;
    return el.offsetParent !== null;
  }

  // data_changed carries a section (aids, financial, all, ...). Refresh the
  // queue only for relevant sections so unrelated broadcasts stay cheap.
  function sectionAllowed(msg, allowed) {
    var section = (msg && msg.section) || "all";
    if (section === "all") return true;
    return allowed.indexOf(section) !== -1;
  }

  function refreshAidClaims() {
    if (!sectionVisible("aid-verify-requests")) return;
    if (window.nxVerifyAid && typeof window.nxVerifyAid.load === "function") {
      window.nxVerifyAid.load(true); // silent: no flash, no toast spam
    }
  }

  function refreshDues() {
    if (!sectionVisible("audit-verify-deduction")) return;
    if (typeof window.loadAuditDeductionQueue === "function") {
      window.loadAuditDeductionQueue(true); // silent: no toast spam
    }
  }

  function refreshReports() {
    if (!sectionVisible("treasurer-reports-management")) return;
    if (typeof window.audLoadFundReports === "function") {
      window.audLoadFundReports(true); // silent: keep page + rows, no flash
    }
  }

  function bind() {
    if (bound || !window.CaufaRealtime) return;
    bound = true;

    // 1. Pending Aid Claims Verification — aid verifications, finish
    //    requests and releases all arrive as data_changed/aids or a full
    //    dashboard refresh.
    window.CaufaRealtime.subscribe({
      channel: "auditor",
      path: "/ws/auditor-dashboard/",
      events: ["data_changed", "dashboard_refresh"],
      onEvent: function (msg) {
        if (msg.type === "data_changed" && !sectionAllowed(msg, ["aids", "financial"])) return;
        refreshAidClaims();
      },
      poll: refreshAidClaims,
      pollIntervalMs: POLL_MS,
    });

    // 2. Pending Dues Verification — deduction queue counts are pushed on
    //    every deduction state change; dashboard refreshes cover the rest.
    window.CaufaRealtime.subscribe({
      channel: "auditor",
      path: "/ws/auditor-dashboard/",
      events: ["deduction_counts", "data_changed", "dashboard_refresh"],
      onEvent: function (msg) {
        if (msg.type === "data_changed" && !sectionAllowed(msg, ["monthly_dues", "membership_fee", "financial"])) return;
        refreshDues();
      },
      poll: refreshDues,
      pollIntervalMs: POLL_MS,
    });

    // 3. Pending Reports Verification — no backend event fires on report
    //    submit, so the 5s fallback is the primary updater here; any fund
    //    or dashboard event also refreshes while the module is open.
    window.CaufaRealtime.subscribe({
      channel: "auditor",
      path: "/ws/auditor-dashboard/",
      events: ["data_changed", "dashboard_refresh", "fund_updated"],
      onEvent: function (msg) {
        if (msg.type === "data_changed" && !sectionAllowed(msg, ["financial"])) return;
        refreshReports();
      },
      poll: refreshReports,
      pollIntervalMs: POLL_MS,
    });
  }

  if (document.readyState !== "loading") bind();
  else document.addEventListener("DOMContentLoaded", bind);
  document.addEventListener("turbo:load", bind);
})();
