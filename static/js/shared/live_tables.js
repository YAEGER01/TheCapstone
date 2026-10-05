// live_tables.js — shared helper that keeps every REFRESH-backed table
// updating live with no page reload, on top of the central realtime
// service (window.CaufaRealtime, see shared/realtime.js).
//
// Each table refreshes instantly on its websocket events and otherwise
// re-polls every 5 seconds — but only while its module section is
// actually open, so background tabs and other modules cost no requests.
// Refreshes run silent (no "Loading…" flash, no toast spam).
//
// Usage (per-dashboard registry, e.g. Treasurer/realtime_tables.js):
//   window.CaufaLiveTables.subscribeTable({
//     channel: "treasurer",
//     path: "/ws/treasurer-dashboard/",
//     section: "view-member-lists",   // visible-gate: module must be .active
//     sections: ["members"],          // data_changed sections that refresh it
//     events: ["fund_updated"],       // extra WS types that refresh it
//     refresh: function () { window.nxMemberLists.load(false, true); },
//   });
(function () {
  "use strict";

  var POLL_MS = 5000;

  function sectionVisible(id) {
    var el = document.getElementById(id);
    if (!el || !el.classList.contains("active")) return false;
    return el.offsetParent !== null;
  }

  // data_changed carries a section (aids, financial, all, ...). Refresh the
  // table only for relevant sections so unrelated broadcasts stay cheap.
  // A missing/unknown section ("all") always refreshes.
  function sectionAllowed(msg, allowed) {
    var section = (msg && msg.section) || "all";
    if (section === "all") return true;
    return (allowed || []).indexOf(section) !== -1;
  }

  function subscribeTable(opts) {
    opts = opts || {};
    if (!window.CaufaRealtime) return function () {};
    if (!opts.channel || !opts.path || !opts.section || typeof opts.refresh !== "function") {
      return function () {};
    }
    var sectionId = opts.section;
    var allowed = opts.sections || [];
    var extraEvents = opts.events || [];
    var events = ["data_changed", "dashboard_refresh"];
    extraEvents.forEach(function (t) {
      if (events.indexOf(t) === -1) events.push(t);
    });

    function refreshIfVisible() {
      if (!sectionVisible(sectionId)) return;
      try { opts.refresh(); } catch (e) {}
    }

    return window.CaufaRealtime.subscribe({
      channel: opts.channel,
      path: opts.path,
      events: events,
      onEvent: function (msg) {
        if (msg && msg.type === "data_changed" && !sectionAllowed(msg, allowed)) return;
        refreshIfVisible();
      },
      poll: refreshIfVisible,
      pollIntervalMs: opts.pollIntervalMs || POLL_MS,
    });
  }

  window.CaufaLiveTables = {
    POLL_MS: POLL_MS,
    sectionVisible: sectionVisible,
    sectionAllowed: sectionAllowed,
    subscribeTable: subscribeTable,
  };
})();
