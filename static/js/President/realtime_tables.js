// realtime_tables.js — every President table/page behind a REFRESH button
// updates live with no page reload, via the central realtime service
// (window.CaufaRealtime + shared/live_tables.js).
//
// Each surface refreshes instantly on its websocket events and otherwise
// re-polls every 5 seconds — but only while its module is actually open,
// so background tabs and other modules cost no requests. Refreshes run
// silent (no "Loading…" flash, no toast spam).
(function () {
  "use strict";

  var CHANNEL = "president";
  var PATH = "/ws/president-dashboard/";
  var bound = false;

  function bind() {
    if (bound || !window.CaufaRealtime || !window.CaufaLiveTables) return;
    bound = true;
    var sub = window.CaufaLiveTables.subscribeTable;

    // 1. Aid final approval queue.
    sub({
      channel: CHANNEL, path: PATH,
      section: "aid-final-approval",
      sections: ["aids"],
      events: ["aid_post_finish_requested", "aid_post_finished", "pending_queue_updated"],
      refresh: function () {
        if (window.nxAidApproval && typeof window.nxAidApproval.load === "function") {
          try { window.nxAidApproval.load(true); } catch (e) {}
        }
      },
    });

    // 2. ISUCauFA General Fund overview.
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

    // 3. General Fund Ledger.
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

    // 4. Fund reports awaiting presidential approval.
    sub({
      channel: CHANNEL, path: PATH,
      section: "fund-summary-view",
      sections: ["financial"],
      events: ["fund_updated"],
      refresh: function () {
        try {
          if (typeof window.presLoadFundReports === "function") window.presLoadFundReports(true);
        } catch (e) {}
      },
    });
  }

  if (document.readyState !== "loading") bind();
  else document.addEventListener("DOMContentLoaded", bind);
  document.addEventListener("turbo:load", bind);
})();
