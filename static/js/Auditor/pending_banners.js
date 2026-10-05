/*
 * Auditor pending-action banners (top-center).
 *
 * On dashboard refresh, checks the three auditor queues and pops a
 * top-center action banner (with a button link) for each non-empty one:
 *   - Pending Dues Verification      → Verify Monthly Dues
 *   - Pending Aid Claims Verification → Verify Benefit Claims
 *   - Pending Reports Verification    → Verify Financial Reports
 * On later live updates only newly-increased counts re-trigger a banner.
 */
(function () {
  "use strict";

  var ran = false;
  window.__audBannerSeen = window.__audBannerSeen || { dues: 0, aids: 0, reports: 0 };

  function goTo(target) {
    if (typeof window.setActiveModule === "function") {
      try { window.setActiveModule(target); } catch (e) {}
    }
  }

  function safeCount(resp) {
    if (!resp || !resp.ok) return Promise.resolve(null);
    return resp.json().then(
      function (d) { return d && d.ok ? d : null; },
      function () { return null; }
    );
  }

  function maybeBanner(key, count, title, message, actionLabel, target) {
    if (!(count > 0)) return;
    var seen = window.__audBannerSeen;
    if (seen._init && count <= (seen[key] || 0)) return;
    seen[key] = count;
    if (typeof window.showTopActionBanner !== "function") return;
    window.showTopActionBanner({
      key: "auditor-" + key,
      title: title,
      message: message,
      actionLabel: actionLabel,
      onAction: function () { goTo(target); },
    });
  }

  window.audCheckPendingBanners = function audCheckPendingBanners() {
    if (!document.getElementById("toastContainer")) return;
    var duesP = fetch("/api/auditor/deductions/queue/", { cache: "no-store", credentials: "same-origin" }).then(safeCount, function () { return null; });
    var aidsP = fetch("/api/auditor/pending-counts/", { cache: "no-store", credentials: "same-origin" }).then(safeCount, function () { return null; });
    var repsP = fetch("/api/fund-reports/workflow-counts/", { cache: "no-store", credentials: "same-origin" }).then(safeCount, function () { return null; });
    Promise.all([duesP, aidsP, repsP]).then(function (results) {
      var dues = results[0], aids = results[1], reps = results[2];
      if (dues) {
        var n = (dues.pending || []).length;
        maybeBanner("dues", n, "Dues Verification pending",
          n + " monthly dues record(s) awaiting auditor verification.",
          "Go to Verify Monthly Dues", "audit-verify-deduction");
      }
      if (aids) {
        var m = Number(aids.aids || 0);
        maybeBanner("aids", m, "Aid Claims Verification pending",
          m + " benefit claim(s) awaiting auditor verification.",
          "Go to Verify Benefit Claims", "aid-verify-requests");
      }
      if (reps) {
        var r = Number(reps.submitted || 0);
        maybeBanner("reports", r, "Reports Verification pending",
          r + " financial report(s) awaiting auditor verification.",
          "Go to Verify Financial Reports", "treasurer-reports-management");
      }
      window.__audBannerSeen._init = true;
    }).catch(function () {});
  };

  function initOnce() {
    if (ran) return;
    ran = true;
    try { window.audCheckPendingBanners(); } catch (e) {}
  }

  if (document.readyState === "complete" || document.readyState === "interactive") {
    setTimeout(initOnce, 0);
  } else {
    document.addEventListener("DOMContentLoaded", initOnce);
  }
  document.addEventListener("turbo:load", initOnce);
})();
