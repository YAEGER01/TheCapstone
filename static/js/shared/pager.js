/*
 * UniPager - consistent pagination across all dashboards.
 * Replicates the Audited Logs pager design: numbered pages with ellipsis,
 * green active state, Prev/Next. Used by Treasurer, Auditor, President.
 *
 * API:
 *   UniPager.html(page, totalPages, goExpr, countText)
 *     -> HTML string. goExpr is an onclick expression containing the token
 *        PAGE which is replaced with the target page number, e.g.
 *        "nxPagerGo('txHistory', PAGE, 'nxLoadTransactionHistory')".
 *        When totalPages <= 1 the pager renders only the count (if given).
 *   UniPager.count(page, pageSize, total)
 *     -> "Showing X-Y of Z" / "No entries" text for the optional counter.
 */
(function () {
  "use strict";

  function btn(label, pageExpr, active, disabled) {
    // Dedicated classes (NOT per-dashboard btn-brand) so the pager looks
    // identical everywhere: Auditor green theme.
    var cls = "uni-pg-btn" + (active ? " uni-pg-active" : "");
    return '<button type="button" class="' + cls + '"' + (disabled ? " disabled" : "") + ' onclick="' + pageExpr + '">' + label + "</button>";
  }

  function html(page, totalPages, goExpr, countText) {
    page = Math.max(1, parseInt(page, 10) || 1);
    totalPages = Math.max(1, parseInt(totalPages, 10) || 1);
    var out = "";
    if (countText) out += '<span class="uni-count" style="color:#5f6b5f;font-size:0.78rem;padding-right:10px;">' + countText + "</span>";
    if (totalPages <= 1) return out;
    out += btn("\u2039 Prev", goExpr.replace(/PAGE/g, String(page - 1)), false, page <= 1);
    var maxBtns = 7;
    var from = Math.max(1, page - Math.floor(maxBtns / 2));
    var to = Math.min(totalPages, from + maxBtns - 1);
    from = Math.max(1, to - maxBtns + 1);
    if (from > 1) {
      out += btn("1", goExpr.replace(/PAGE/g, "1"), page === 1, false);
      if (from > 2) out += '<span class="uni-ell" style="color:#5f6b5f;padding:0 2px;font-size:0.8rem;">\u2026</span>';
    }
    for (var p = from; p <= to; p++) {
      out += btn(String(p), goExpr.replace(/PAGE/g, String(p)), p === page, false);
    }
    if (to < totalPages) {
      if (to < totalPages - 1) out += '<span class="uni-ell" style="color:#5f6b5f;padding:0 2px;font-size:0.8rem;">\u2026</span>';
      out += btn(String(totalPages), goExpr.replace(/PAGE/g, String(totalPages)), false, false);
    }
    out += btn("Next \u203a", goExpr.replace(/PAGE/g, String(page + 1)), false, page >= totalPages);
    return out;
  }

  function count(page, pageSize, total) {
    total = total || 0;
    if (!total) return "No entries";
    return "Showing " + ((page - 1) * pageSize + 1) + "\u2013" + Math.min(page * pageSize, total) + " of " + total;
  }

  window.UniPager = { html: html, count: count };
})();
