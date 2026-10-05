// realtime_tables.js — every Treasurer table/page behind a REFRESH button
// updates live with no page reload, via the central realtime service
// (window.CaufaRealtime + shared/live_tables.js).
//
// Each surface refreshes instantly on its websocket events and otherwise
// re-polls every 5 seconds — but only while its module is actually open,
// so background tabs and other modules cost no requests. Refreshes run
// silent (no "Loading…" flash, no toast spam).
//
// NOTE: Fund Timeline is not listed here — fund_timeline.js already
// subscribes itself to fund_updated on the same central service.
(function () {
  "use strict";

  var CHANNEL = "treasurer";
  var PATH = "/ws/treasurer-dashboard/";
  var bound = false;

  var AID_EVENTS = [
    "aid_post_created",
    "aid_post_finish_requested",
    "aid_post_release_pending",
    "aid_post_repayment_pending",
    "aid_post_finished",
    "contribution_updated",
    "pending_queue_updated",
  ];

  function call(fn) {
    try {
      if (typeof fn === "function") fn();
    } catch (e) {}
  }

  function bind() {
    if (bound || !window.CaufaRealtime || !window.CaufaLiveTables) return;
    bound = true;
    var sub = window.CaufaLiveTables.subscribeTable;

    // 1. Claims queue (medical/death aid awaiting treasurer review).
    sub({
      channel: CHANNEL, path: PATH,
      section: "view-claims-queue",
      sections: ["aids"],
      events: AID_EVENTS,
      refresh: function () { call(window.loadClaimsQueue); },
    });

    // 2. Monthly dues approval queue.
    sub({
      channel: CHANNEL, path: PATH,
      section: "view-monthly-dues-approval",
      sections: ["monthly_dues", "membership_fee", "financial"],
      events: ["deduction_counts"],
      refresh: function () { call(window.loadMonthlyDuesApprovalQueue); },
    });

    // 3. Due deposit (pending batches + deposit history).
    sub({
      channel: CHANNEL, path: PATH,
      section: "view-due-deposit",
      sections: ["monthly_dues", "financial"],
      events: ["deduction_counts", "fund_updated"],
      refresh: function () {
        if (window.nxDueDeposit && typeof window.nxDueDeposit.load === "function") {
          try { window.nxDueDeposit.load(true); } catch (e) {}
        }
      },
    });

    // 4. Member directory.
    sub({
      channel: CHANNEL, path: PATH,
      section: "view-member-lists",
      sections: ["members", "registration"],
      refresh: function () {
        if (window.nxMemberLists && typeof window.nxMemberLists.load === "function") {
          try { window.nxMemberLists.load(false, true); } catch (e) {}
        }
      },
    });

    // 5. ISUCauFA General Fund overview.
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

    // 6. General Fund Ledger.
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

    // 7. Record Transaction history (one-off receipts/disbursements).
    sub({
      channel: CHANNEL, path: PATH,
      section: "treasurer-other-transactions",
      sections: ["financial"],
      events: ["fund_updated"],
      refresh: function () {
        if (window.nxOtherTransactions && typeof window.nxOtherTransactions.load === "function") {
          try { window.nxOtherTransactions.load(true); } catch (e) {}
        }
      },
    });

    // 8. Public registration requests.
    sub({
      channel: CHANNEL, path: PATH,
      section: "view-registration-requests",
      sections: ["registration", "members"],
      refresh: function () { call(window.fetchRegistrationRequests); },
    });

    // 9. Dues tracking (silent: keeps the user's search text).
    sub({
      channel: CHANNEL, path: PATH,
      section: "view-dues-tracking",
      sections: ["monthly_dues"],
      events: ["deduction_counts"],
      refresh: function () { call(window.dtSilentRefresh); },
    });

    // 10. Salary deduction exemption requests.
    sub({
      channel: CHANNEL, path: PATH,
      section: "view-exemption-requests",
      sections: ["monthly_dues"],
      refresh: function () { call(window.loadExemptionRequests); },
    });

    // 11. Monthly deduction recording (silent, keeps the selected month —
    //     never mdpRefresh(), which would reset the user's selection).
    sub({
      channel: CHANNEL, path: PATH,
      section: "view-monthly-deduction",
      sections: ["monthly_dues", "financial"],
      events: ["deduction_counts"],
      refresh: function () {
        try {
          if (typeof window.loadMdOverviews === "function") window.loadMdOverviews(true);
        } catch (e) {}
      },
    });

    // 12. Notifications / items requiring attention.
    sub({
      channel: CHANNEL, path: PATH,
      section: "treasurer-notifications",
      events: ["notification_created", "notification_summary"],
      refresh: function () { call(window.nxRefreshNotifications); },
    });

    // 13. Full transaction history (fund journal).
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

    // 14. Aid release queue.
    sub({
      channel: CHANNEL, path: PATH,
      section: "treasurer-aid-release",
      sections: ["aids", "financial"],
      events: AID_EVENTS.concat(["fund_updated"]),
      refresh: function () {
        try {
          if (typeof window.nxLoadReleases === "function") window.nxLoadReleases(true);
        } catch (e) {}
      },
    });

    // 15. Returned claims.
    sub({
      channel: CHANNEL, path: PATH,
      section: "treasurer-returned-claims",
      sections: ["returned_entries", "aids"],
      events: AID_EVENTS,
      refresh: function () {
        if (window.nxReturnedClaims && typeof window.nxReturnedClaims.load === "function") {
          try { window.nxReturnedClaims.load(true); } catch (e) {}
        }
      },
    });

    // 16. Fund repayment tracking.
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
