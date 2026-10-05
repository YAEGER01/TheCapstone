// realtime_tables.js — every Auditor table/page behind a REFRESH button
// updates live with no page reload, via the central realtime service
// (window.CaufaRealtime + shared/live_tables.js).
//
// Each surface refreshes instantly on its websocket events and otherwise
// re-polls every 5 seconds — but only while its module is actually open,
// so background tabs and other modules cost no requests. Refreshes run
// silent (no "Loading…" flash, no toast spam).
//
// NOTE: aid claims / dues / reports verification queues are not listed
// here — Auditor/realtime_queues.js already covers them on the same
// central service.
(function () {
  "use strict";

  var CHANNEL = "auditor";
  var PATH = "/ws/auditor-dashboard/";
  var bound = false;

  function bind() {
    if (bound || !window.CaufaRealtime || !window.CaufaLiveTables) return;
    bound = true;
    var sub = window.CaufaLiveTables.subscribeTable;

    // 1. ISUCauFA General Fund overview.
    sub({
      channel: CHANNEL, path: PATH,
      section: "fund-overview",
      sections: ["financial"],
      events: ["fund_updated"],
      refresh: function () {
        if (window.nxFundOverview && typeof window.nxFundOverview.load === "function") {
          try { window.nxFundOverview.load(true); } catch (e) {}
        }
      },
    });

    // 2. General Fund Ledger.
    sub({
      channel: CHANNEL, path: PATH,
      section: "fund-ledger",
      sections: ["financial"],
      events: ["fund_updated"],
      refresh: function () {
        if (window.nxFundLedger && typeof window.nxFundLedger.load === "function") {
          try { window.nxFundLedger.load(true); } catch (e) {}
        }
      },
    });

    // 3. Full transaction history.
    sub({
      channel: CHANNEL, path: PATH,
      section: "treasurer-transaction-history",
      sections: ["financial"],
      events: ["fund_updated"],
      refresh: function () {
        try {
          if (typeof window.nxLoadTransactionHistory === "function") window.nxLoadTransactionHistory(true);
        } catch (e) {}
      },
    });

    // 4. Activity logs.
    sub({
      channel: CHANNEL, path: PATH,
      section: "treasurer-activity-log",
      sections: ["financial", "aids"],
      refresh: function () {
        try {
          if (typeof window.nxLoadActivityLogs === "function") window.nxLoadActivityLogs(true);
        } catch (e) {}
      },
    });

    // 5. Aid releases awaiting action.
    sub({
      channel: CHANNEL, path: PATH,
      section: "treasurer-aid-release",
      sections: ["aids", "financial"],
      events: ["aid_post_finished", "aid_post_release_pending", "contribution_updated"],
      refresh: function () {
        try {
          if (typeof window.nxLoadReleases === "function") window.nxLoadReleases(true);
        } catch (e) {}
      },
    });

    // 6. Fund repayment tracking.
    sub({
      channel: CHANNEL, path: PATH,
      section: "treasurer-repayment",
      sections: ["aids", "financial"],
      events: ["aid_post_finished", "contribution_updated"],
      refresh: function () {
        try {
          if (typeof window.nxLoadRepayment === "function") window.nxLoadRepayment(true);
        } catch (e) {}
      },
    });
  }

  if (document.readyState !== "loading") bind();
  else document.addEventListener("DOMContentLoaded", bind);
  document.addEventListener("turbo:load", bind);
})();
