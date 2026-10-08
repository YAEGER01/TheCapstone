// fund_timeline.js — ISUCauFA, Inc. FUND › Fund Timeline
// Chronological record-by-record timeline in three aligned columns:
//   left (35%)  — the credit record      (empty on debit rows)
//   center(30%) — Fund Before → Fund After FOR THAT RECORD
//   right (35%) — the debit record       (empty on credit rows)
// Consecutive same-kind records (a whole dues batch recorded member by
// member) collapse into one accordion drawer spanning their NET effect;
// expanding it reveals each record with its own before/after step.
// Month headers group the rows; a global toolbar toggle sorts each month's
// rows oldest/newest; each month has its own pager; the month body has a
// fixed height and scrolls in place.
// Data: /api/treasurer/fund-timeline/.
(function () {
  "use strict";

  const PAGE_SIZE = 12;
  const state = {
    year: null,
    years: [],
    data: null,
    loading: false,
    sort: "newest",
    pages: {},   // monthIdx -> page number
    open: {},    // "monthIdx:groupKey" -> true (accordion open)
  };

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function peso(n) {
    const v = Number(n || 0);
    const sign = v < 0 ? "-" : "";
    return sign + "₱" + Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function getJSON(url) {
    return fetch(url, { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);
  }

  function itemMeta(t, withPos) {
    const parts = [t.source_type, t.reference ? "ref " + t.reference : "", t.date].filter(Boolean).map(esc);
    if (withPos) {
      parts.push('<span class="ft-pos-mini">' + peso(t.fund_before) + ' &#8594; ' + peso(t.fund_after) + '</span>');
    }
    return parts.join(" · ");
  }

  function itemRow(t, dir, withPos) {
    const desc = t.description || t.source_type;
    // Recipient line only when it ADDS info (release descriptions already
    // name the payee — no "for Juan" under "disbursement — Juan").
    const recip = (t.recipient && String(desc).indexOf(t.recipient) === -1)
      ? '<span class="ft-recip">for ' + esc(t.recipient) + '</span>'
      : "";
    return (
      '<div class="ft-item">' +
        '<span class="ft-item-desc">' +
          '<span class="ft-desc" title="' + esc(desc) + '">' + esc(desc) + '</span>' +
          recip +
          '<span class="ft-meta">' + itemMeta(t, withPos) + '</span>' +
        '</span>' +
        '<span class="ft-amt ' + dir + '">' + (dir === "in" ? "+" : "−") + peso(t.amount) + '</span>' +
      '</div>'
    );
  }

  function posCell(before, after) {
    const up = Number(after) >= Number(before);
    return (
      '<div class="ft-pos">' +
        '<span class="ft-pos-before">' + peso(before) + '</span>' +
        '<span class="ft-pos-sep">&#8594;</span>' +
        '<span class="ft-pos-after ' + (up ? "up" : "down") + '">' + peso(after) + '</span>' +
      '</div>'
    );
  }

  // A dues batch: one collapsed row showing the WHOLE money collected; the
  // drawer (only when the batch has aid assessments) breaks it down into
  // Monthly Dues / Medical Aid / Death Aid components.
  function batchBlock(u, mIdx) {
    const open = u.has_aid && state.open[mIdx + ":" + u.key];
    const caret = u.has_aid ? '<span class="ft-group-caret">&#9654;</span>' : "";
    const headAttrs = u.has_aid
      ? ' type="button" data-ft-group="' + esc(mIdx + ":" + u.key) + '"'
      : "";
    const breakdown = u.has_aid
      ? '<div class="ft-group-items">' +
          u.components.map(function (c) {
            const recip = c.recipient
              ? '<span class="ft-recip">for ' + esc(c.recipient) + '</span>'
              : "";
            return (
              '<div class="ft-item">' +
                '<span class="ft-item-desc">' +
                  '<span class="ft-desc">' + esc(c.label) + '</span>' +
                  recip +
                  '<span class="ft-meta">' + c.count + (c.count === 1 ? " record" : " records") +
                    ' · <span class="ft-pos-mini">' + peso(c.fund_before) + ' &#8594; ' + peso(c.fund_after) + '</span>' +
                  '</span>' +
                '</span>' +
                '<span class="ft-amt in">+' + peso(c.total) + '</span>' +
              '</div>'
            );
          }).join("") +
        '</div>'
      : "";
    return (
      '<div class="ft-group' + (open ? " open" : "") + '">' +
        '<' + (u.has_aid ? "button" : "div") + ' class="ft-group-head"' + headAttrs + '>' +
          caret +
          '<span class="ft-group-label" title="' + esc(u.label) + '">' + esc(u.label) + '</span>' +
          '<span class="ft-group-count">' + u.count + ' records</span>' +
          '<span class="ft-group-amt">+' + peso(u.total) + '</span>' +
        '</' + (u.has_aid ? "button" : "div") + '>' +
        breakdown +
      '</div>'
    );
  }

  function unitRow(u, mIdx) {
    const dir = u.direction === "inflow" ? "in" : "out";
    let center = posCell(u.fund_before, u.fund_after);
    if (u.kind === "batch") {
      center += '<span class="ft-net ' + (u.total > 0 ? "in" : "flat") + '">Net +' + peso(u.total) + '</span>';
    }
    let side;
    if (u.kind === "batch") side = batchBlock(u, mIdx);
    else side = itemRow(u, dir);
    const left = dir === "in" ? side : "";
    const right = dir === "out" ? side : "";
    return (
      '<div class="ft-row' + (u.kind === "batch" ? " ft-row-group" : "") + '">' +
        '<div class="ft-cell">' + left + '</div>' +
        '<div class="ft-cell ft-cell-pos">' + center + '</div>' +
        '<div class="ft-cell">' + right + '</div>' +
      '</div>'
    );
  }

  function unitTs(u) {
    if (!u) return "";
    if (u.kind === "group" && Array.isArray(u.items) && u.items.length) {
      return u.items.reduce((a, b) => (a.ts > b.ts ? a : b)).ts || "";
    }
    return u.ts || "";
  }

  function monthCard(m, idx) {
    const mode = state.sort;
    const rows = (m.rows || []).slice().sort((a, b) => {
      const cmp = unitTs(a).localeCompare(unitTs(b));
      return mode === "newest" ? -cmp : cmp;
    });

    const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    const page = Math.min(Math.max(state.pages[idx] || 1, 1), pageCount);
    state.pages[idx] = page;
    const start = (page - 1) * PAGE_SIZE;
    const pageRows = rows.slice(start, start + PAGE_SIZE);

    const headRow =
      '<div class="ft-head-row">' +
        '<div class="ft-cell">Credit · Money In</div>' +
        '<div class="ft-cell ft-cell-pos">Fund Position</div>' +
        '<div class="ft-cell">Debit · Money Out</div>' +
      '</div>';

    const body = pageRows.length
      ? pageRows.map((u) => unitRow(u, idx)).join("")
      : '<div class="ft-empty-year">No records.</div>';

    const foot =
      '<div class="ft-foot">' +
        '<span>' + rows.length + ' record' + (rows.length === 1 ? "" : "s") +
          (pageCount > 1 ? " · showing " + (start + 1) + "–" + (start + pageRows.length) : "") +
        '</span>' +
        (pageCount > 1
          ? '<span class="ft-pager">' +
              '<button type="button" class="ft-pg-btn" data-ft-pg="' + idx + ':-1"' + (page <= 1 ? " disabled" : "") + '>&lsaquo;</button>' +
              '<span>' + page + ' / ' + pageCount + '</span>' +
              '<button type="button" class="ft-pg-btn" data-ft-pg="' + idx + ':1"' + (page >= pageCount ? " disabled" : "") + '>&rsaquo;</button>' +
            '</span>'
          : "") +
      '</div>';

    return (
      '<div class="ft-month">' +
        '<div class="ft-month-head">' +
          '<span class="ft-month-name">' + esc(m.month_label) + '</span>' +
          '<span class="ft-month-chips">' +
            '<span class="ft-chip in">In +' + peso(m.total_in) + '</span>' +
            '<span class="ft-chip out">Out −' + peso(m.total_out) + '</span>' +
          '</span>' +
        '</div>' +
        headRow +
        '<div class="ft-body">' + body + '</div>' +
        foot +
      '</div>'
    );
  }

  function renderYearSelect() {
    const sel = document.getElementById("ft-year");
    if (!sel) return;
    sel.innerHTML = state.years
      .map((y) => '<option value="' + y + '"' + (y === state.year ? " selected" : "") + '>' + y + '</option>')
      .join("");
  }

  function renderMonths() {
    const root = document.getElementById("fund-timeline-root");
    if (!root || !state.data) return;
    const months = state.data.months || [];
    root.innerHTML = months.length
      ? months.map(monthCard).join("")
      : '<div class="ft-empty-year">No fund activity recorded in ' + esc(String(state.data.year)) + '.</div>';
    const sortBtn = document.getElementById("ft-sort");
    if (sortBtn) sortBtn.innerHTML = '&#8645; ' + (state.sort === "newest" ? "Newest first" : "Oldest first");
  }

  function rerenderMonth(idx) {
    const root = document.getElementById("fund-timeline-root");
    const m = state.data && (state.data.months || [])[idx];
    if (!root || !m) return;
    const fresh = document.createElement("div");
    fresh.innerHTML = monthCard(m, idx);
    const old = root.children[idx];
    if (old) root.replaceChild(fresh.firstElementChild, old);
  }

  function cycleYear(step) {
    if (!state.years.length) return;
    const idx = state.years.indexOf(state.year);
    const next = state.years[Math.min(state.years.length - 1, Math.max(0, (idx === -1 ? 0 : idx) + step))];
    if (next !== state.year) {
      state.year = next;
      renderYearSelect();
      load();
    }
  }

  async function fetchAndRender() {
    if (state.loading) return false;
    state.loading = true;
    try {
      const q = state.year ? "?year=" + state.year : "";
      const data = await getJSON("/api/treasurer/fund-timeline/" + q);
      if (!data || !data.ok) return false;
      state.year = data.year;
      state.years = data.years || [];
      state.data = data;
      renderYearSelect();

      const balanceChip = document.getElementById("ft-current-balance");
      if (balanceChip) balanceChip.textContent = "Current Fund Balance: " + peso(data.current_balance);

      renderMonths();
      return true;
    } finally {
      state.loading = false;
    }
  }

  async function load() {
    const root = document.getElementById("fund-timeline-root");
    if (root) root.innerHTML = '<div class="ft-empty-year">Loading…</div>';
    const ok = await fetchAndRender();
    if (!ok && root) root.innerHTML = '<div class="ft-empty-year">Could not load the fund timeline.</div>';
  }

  function isTimelineVisible() {
    const section = document.getElementById("fund-timeline");
    if (!section || !section.classList.contains("active")) return false;
    const root = document.getElementById("fund-timeline-root");
    return !!(root && root.offsetParent !== null);
  }

  // Realtime silent refresh: same data, no "Loading…" flash, accordion
  // pages/groups/sort/year untouched. Skipped while the module is hidden.
  async function refreshSilent() {
    if (!state.data) { load(); return; }
    if (!isTimelineVisible()) return;
    await fetchAndRender();
  }

  function bindRealtime() {
    if (state.rtBound || !window.CaufaRealtime) return;
    state.rtBound = true;
    window.CaufaRealtime.subscribe({
      channel: "treasurer",
      path: "/ws/treasurer-dashboard/",
      event: "fund_updated",
      onEvent: function () { refreshSilent(); },
      poll: function () { refreshSilent(); },
      pollIntervalMs: 5000,
    });
  }

  function onRootClick(e) {
    const pgBtn = e.target.closest && e.target.closest("[data-ft-pg]");
    if (pgBtn && !pgBtn.disabled) {
      const parts = pgBtn.getAttribute("data-ft-pg").split(":");
      const idx = Number(parts[0]);
      state.pages[idx] = (state.pages[idx] || 1) + Number(parts[1]);
      rerenderMonth(idx);
      return;
    }
    const groupHead = e.target.closest && e.target.closest("[data-ft-group]");
    if (groupHead) {
      const key = groupHead.getAttribute("data-ft-group");
      state.open[key] = !state.open[key];
      const groupEl = groupHead.closest(".ft-group");
      if (groupEl) groupEl.classList.toggle("open", !!state.open[key]);
    }
  }

  function init() {
    const root = document.getElementById("fund-timeline-root");
    if (root && !root.dataset.bound) {
      root.dataset.bound = "1";
      root.addEventListener("click", onRootClick);
    }
    const sel = document.getElementById("ft-year");
    const prev = document.getElementById("ft-prev-year");
    const next = document.getElementById("ft-next-year");
    const sortBtn = document.getElementById("ft-sort");
    if (sel && !sel.dataset.bound) {
      sel.dataset.bound = "1";
      sel.addEventListener("change", () => {
        state.year = Number(sel.value) || null;
        load();
      });
    }
    if (prev && !prev.dataset.bound) {
      prev.dataset.bound = "1";
      prev.addEventListener("click", () => cycleYear(1)); // years are newest-first
    }
    if (next && !next.dataset.bound) {
      next.dataset.bound = "1";
      next.addEventListener("click", () => cycleYear(-1));
    }
    if (sortBtn && !sortBtn.dataset.bound) {
      sortBtn.dataset.bound = "1";
      sortBtn.addEventListener("click", () => {
        state.sort = state.sort === "newest" ? "oldest" : "newest";
        renderMonths();
      });
    }
    bindRealtime();
    if (state.year === null && !state.loading) load();
  }

  window.nxFundTimeline = { load, init, refreshSilent, isTimelineVisible };

  if (document.readyState !== "loading") init();
  else document.addEventListener("DOMContentLoaded", init);
  document.addEventListener("turbo:load", init);
  // Reload when the module is opened from the sidebar.
  if (!window.__ftNavBound) {
    window.__ftNavBound = true;
    document.addEventListener("click", function (e) {
      const el = e.target.closest && e.target.closest('.menu-item[data-target="fund-timeline"]');
      if (el) setTimeout(() => refreshSilent(), 150);
    });
  }
})();
