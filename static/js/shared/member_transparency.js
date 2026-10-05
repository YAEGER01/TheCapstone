/* Member Dashboard — Financial Transparency tab.
 *
 * Backs the Transparency view: the organisation-wide financial overview cards
 * and charts, the member's own cash flow with filters and a movement detail
 * dialog, and the member's own dues, contributions and payments.
 *
 * Three behaviours worth knowing before editing:
 *
 *  1. Every figure is shown as recorded. There is no masking and no reveal
 *     step, so a value that is genuinely zero reads as ₱0.00 and means it.
 *  2. Only the Financial Overview panels are organisation-wide. Everything
 *     else is scoped to the signed-in member by the server; the client never
 *     sends a member id and must never add one.
 *  3. `load()` is idempotent and lazy. The view only fetches when the member
 *     actually opens the tab, and re-opening reuses the same code path as the
 *     Refresh buttons, so there is exactly one loader to keep correct.
 */
(function () {
  "use strict";

  var state = {
    loaded: false,
    flow: { page: 1, direction: "", kind: "", year: "", date_from: "", date_to: "" },
    flowPage: 1,
    flowPages: 1,
    recordPanel: "dues",
  };

  // ---------------------------------------------------------------- helpers

  function $(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function num(v) {
    var n = parseFloat(v);
    return isNaN(n) ? 0 : n;
  }

  function peso(n) {
    return "₱" + num(n).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function pct(v) {
    return num(v) + "%";
  }

  function signed(v, direction) {
    return (direction === "in" ? "+" : "− ") + peso(Math.abs(num(v)));
  }

  function shortDate(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso).slice(0, 10);
    return d.toLocaleDateString("en-PH", { year: "numeric", month: "short", day: "2-digit" });
  }

  function stamp(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    return d.toLocaleString("en-PH", {
      year: "numeric", month: "short", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  }

  function emptyRow(colspan, message) {
    return '<tr><td colspan="' + colspan + '" style="text-align:center;color:#757575;">' + esc(message) + "</td></tr>";
  }

  function errorRow(colspan) {
    return emptyRow(colspan, "Could not load this information. Please try again.");
  }

  function getJSON(url) {
    return fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (res) { return res.ok ? res.json() : null; })
      .catch(function () { return null; });
  }

  // ------------------------------------------------------------------ charts
  /* Dependency-free inline SVG. Charting here is a two-series bar chart and
   * one line; pulling in a library for that would outweigh the cost. */

  function barChart(el, series) {
    if (!el) return;
    if (!series || !series.length) {
      el.innerHTML = '<span style="color:#757575;font-size:12.5px;">No movement recorded yet.</span>';
      return;
    }

    var W = 520, H = 200, padL = 8, padB = 26, padT = 10;
    var plotH = H - padB - padT;
    var maxV = 0;
    series.forEach(function (s) {
      maxV = Math.max(maxV, num(s.total_in), num(s.total_out));
    });
    if (maxV <= 0) {
      el.innerHTML = '<span style="color:#757575;font-size:12.5px;">No movement recorded yet.</span>';
      return;
    }

    var groupW = (W - padL * 2) / series.length;
    var barW = Math.max(3, Math.min(13, groupW / 2.6));
    var parts = [];

    series.forEach(function (s, i) {
      var cx = padL + groupW * i + groupW / 2;
      [["total_in", "#1b5e20"], ["total_out", "#dc2626"]].forEach(function (spec) {
        var v = num(s[spec[0]]);
        if (v <= 0) return;
        var h = (v / maxV) * plotH;
        var x = cx + (spec[0] === "total_in" ? -barW - 1.5 : 1.5);
        parts.push('<rect x="' + x.toFixed(1) + '" y="' + (padT + plotH - h).toFixed(1) +
          '" width="' + barW.toFixed(1) + '" height="' + Math.max(1, h).toFixed(1) +
          '" rx="2" fill="' + spec[1] + '"></rect>');
      });
      if (series.length <= 13 || i % 2 === 0) {
        parts.push('<text class="mt-axis" x="' + cx.toFixed(1) + '" y="' + (H - 8) +
          '" text-anchor="middle">' + esc(String(s.label).slice(0, 7)) + "</text>");
      }
    });

    el.innerHTML = '<svg viewBox="0 0 ' + W + " " + H +
      '" preserveAspectRatio="none" role="img" aria-label="Monthly money in and out">' +
      parts.join("") + "</svg>";
  }

  function lineChart(el, series) {
    if (!el) return;
    if (!series || !series.length) {
      el.innerHTML = '<span style="color:#757575;font-size:12.5px;">No history yet.</span>';
      return;
    }

    var W = 520, H = 200, padL = 8, padR = 8, padT = 10, padB = 26;
    var plotW = W - padL - padR, plotH = H - padB - padT;

    var values = series.map(function (s) { return num(s.balance); });
    var min = Math.min.apply(null, values);
    var max = Math.max.apply(null, values);
    if (max === min) { max = min + 1; }
    var span = max - min;

    function y(v) { return padT + plotH - ((v - min) / span) * plotH; }
    function x(i) { return padL + (series.length === 1 ? plotW / 2 : (plotW * i) / (series.length - 1)); }

    var points = values.map(function (v, i) { return x(i).toFixed(1) + "," + y(v).toFixed(1); });

    var parts = [];
    // Zero line when the range straddles it, so a downward trend is readable.
    if (min < 0 && max > 0) {
      parts.push('<line x1="' + padL + '" y1="' + y(0).toFixed(1) + '" x2="' + (W - padR) +
        '" y2="' + y(0).toFixed(1) + '" stroke="#e2e8e4" stroke-width="1" stroke-dasharray="3 3"></line>');
    }
    parts.push('<polyline fill="none" stroke="#2e7d32" stroke-width="2" stroke-linejoin="round" points="' +
      points.join(" ") + '"></polyline>');
    values.forEach(function (v, i) {
      parts.push('<circle cx="' + x(i).toFixed(1) + '" cy="' + y(v).toFixed(1) +
        '" r="2.5" fill="#2e7d32"></circle>');
      if (series.length <= 13 || i % 2 === 0) {
        parts.push('<text class="mt-axis" x="' + x(i).toFixed(1) + '" y="' + (H - 8) +
          '" text-anchor="middle">' + esc(String(series[i].label).slice(0, 7)) + "</text>");
      }
    });

    el.innerHTML = '<svg viewBox="0 0 ' + W + " " + H +
      '" preserveAspectRatio="none" role="img" aria-label="Closing fund balance over time">' +
      parts.join("") + "</svg>";
  }

  // ------------------------------------------------------- 1. financial overview

  function loadSummary() {
    return getJSON("/api/member/fund/summary/").then(function (data) {
      if (!data || !data.ok) {
        ["mtBalance", "mtCollections", "mtInflow", "mtOutflow"].forEach(function (id) {
          var el = $(id); if (el) el.textContent = "—";
        });
        return null;
      }

      var balance = $("mtBalance");
      if (balance) {
        balance.textContent = peso(data.balance);
        balance.className = "stat-value " + (num(data.balance) < 0 ? "danger" : "ok");
      }
      var coll = $("mtCollections"); if (coll) coll.textContent = peso(data.total_collections);
      var inflow = $("mtInflow"); if (inflow) inflow.textContent = peso(data.total_in);
      var outflow = $("mtOutflow"); if (outflow) outflow.textContent = peso(data.total_out);

      var collSub = $("mtCollectionsSub");
      if (collSub) collSub.textContent = pct(data.collection_share) + " of all money received";
      var inSub = $("mtInflowSub");
      if (inSub) inSub.textContent = peso(data.month_in) + " this month";
      var outSub = $("mtOutflowSub");
      if (outSub) outSub.textContent = peso(data.month_out) + " this month";

      var foot = $("mtSummaryFoot");
      if (foot) foot.textContent = "As of " + stamp(data.generated_at);
    });
  }

  function loadTrend() {
    return getJSON("/api/member/fund/trend/?months=12").then(function (data) {
      if (!data || !data.ok) {
        barChart($("mtFlowChart"), []);
        lineChart($("mtBalanceChart"), []);
        return;
      }
      barChart($("mtFlowChart"), data.series);
      lineChart($("mtBalanceChart"), data.series);
    });
  }

  // ------------------------------------------------------------ 2. cash flow

  function flowQuery(page) {
    var p = new URLSearchParams();
    p.set("page", String(page || 1));
    p.set("per_page", "25");
    if (state.flow.direction) p.set("direction", state.flow.direction);
    if (state.flow.kind) p.set("kind", state.flow.kind);
    if (state.flow.year) p.set("year", state.flow.year);
    if (state.flow.date_from) p.set("date_from", state.flow.date_from);
    if (state.flow.date_to) p.set("date_to", state.flow.date_to);
    return p.toString();
  }

  function loadFlow(page) {
    var body = $("mtFlowBody");
    if (!body) return Promise.resolve();
    body.innerHTML = '<tr><td colspan="5"><span class="skeleton"></span></td></tr>';

    return getJSON("/api/member/fund/ledger/?" + flowQuery(page)).then(function (data) {
      if (!data || !data.ok) { body.innerHTML = errorRow(5); return; }

      var s = data.summary || {};
      var i = $("mtFlowIn"); if (i) i.textContent = peso(s.total_in);
      var o = $("mtFlowOut"); if (o) o.textContent = peso(s.total_out);
      var b = $("mtFlowBal"); if (b) b.textContent = peso(s.net);
      var outstanding = $("mtFlowOutstanding"); if (outstanding) outstanding.textContent = peso(s.outstanding);

      var sel = $("mtFlowKind");
      if (sel && sel.options.length <= 1 && (data.kinds || []).length) {
        data.kinds.forEach(function (k) {
          var opt = document.createElement("option");
          opt.value = k.value;
          opt.textContent = k.label;
          sel.appendChild(opt);
        });
      }
      syncYearSelect($("mtFlowYear"), data.years || [], state.flow.year, null);

      var items = data.items || [];
      if (!items.length) {
        body.innerHTML = emptyRow(5, "No movements match these filters.");
      } else {
        body.innerHTML = items.map(function (t) {
          var inflow = t.direction === "in";
          return "<tr style='cursor:pointer;' data-tx='" + esc(t.id) + "'>" +
            "<td>" + esc(shortDate(t.date)) + "</td>" +
            "<td>" + esc(t.description || t.kind_label || "—") + "</td>" +
            "<td><span class='st-tag'>" + esc(t.kind_label || "—") + "</span></td>" +
            "<td style='text-align:right;'>" + peso(t.running_net) + "</td>" +
            "<td style='text-align:right;font-weight:700;color:" + (inflow ? "#1b5e20" : "#c62828") + ";'>" +
              signed(t.amount, t.direction) +
            "</td>" +
            "</tr>";
        }).join("");
      }

      state.flowPage = data.page;
      state.flowPages = data.total_pages;

      var pager = $("mtFlowPager");
      if (pager) {
        if (data.total_pages > 1) {
          pager.style.display = "flex";
          $("mtFlowPageInfo").textContent = "Page " + data.page + " of " + data.total_pages +
            " · " + data.total + " movements";
          $("mtFlowPrev").disabled = data.page <= 1;
          $("mtFlowNext").disabled = data.page >= data.total_pages;
        } else {
          pager.style.display = "none";
        }
      }
    });
  }

  /* A <select> is only rebuilt when its value would actually change, otherwise
   * re-populating it on every refresh would fight the user's selection. */
  function syncYearSelect(sel, years, current, onChange) {
    if (!sel || !years || !years.length) return;
    var wanted = years.map(String);
    var have = Array.prototype.map.call(sel.options, function (o) { return o.value; });
    if (have.join(",") !== wanted.join(",")) {
      sel.innerHTML = "";
      years.forEach(function (y) {
        var opt = document.createElement("option");
        opt.value = String(y);
        opt.textContent = String(y);
        sel.appendChild(opt);
      });
      if (onChange && !sel.dataset.bound) {
        sel.dataset.bound = "1";
        sel.addEventListener("change", function () { onChange(sel.value); });
      }
    }
    if (current) sel.value = String(current);
  }

  function alertBox(message, title) {
    if (window.SimpleModal && typeof window.SimpleModal.alert === "function") {
      window.SimpleModal.alert(message, title);
    } else {
      window.alert(message);
    }
  }

  function openMovement(id) {
    getJSON("/api/member/fund/movement/" + encodeURIComponent(id) + "/").then(function (d) {
      if (!d || !d.ok) { alertBox("Could not load that movement.", "Movement details"); return; }

      var rows = [
        ["Date", stamp(d.date)],
        ["Type", d.kind_label || "—"],
        ["Amount", signed(d.amount, d.direction)],
        ["Description", d.description || "—"],
        ["Reference", d.reference || "—"],
        ["Running total", peso(d.running_net)],
      ];
      if (d.recorded_by) rows.push(["Recorded by", d.recorded_by]);
      if (d.outstanding) rows.push(["Outstanding on this item", peso(d.outstanding)]);
      if (d.remarks) rows.push(["Remarks", d.remarks]);

      var html = "<table style='width:100%;border-collapse:collapse;font-size:13px;'>" +
        rows.map(function (r) {
          return "<tr>" +
            "<td style='padding:7px 10px 7px 0;color:#64748b;white-space:nowrap;vertical-align:top;width:42%;'>" +
              esc(r[0]) + "</td>" +
            "<td style='padding:7px 0;font-weight:600;'>" + esc(r[1]) + "</td>" +
            "</tr>";
        }).join("") + "</table>";

      if (window.SimpleModal && typeof window.SimpleModal.open === "function") {
        window.SimpleModal.open({ title: "Movement details", html: html, width: "560px", radius: "14px" });
      } else {
        alertBox(html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim(), "Movement details");
      }
    });
  }

  // -------------------------------------------------------- 3. my records

  function loadDues() {
    return getJSON("/api/member/records/dues-matrix/?months=24").then(function (data) {
      var body = $("mtDuesBody");
      var strip = $("mtDuesStrip");
      if (!body) return;
      if (!data || !data.ok) { body.innerHTML = errorRow(4); return; }

      var grid = data.grid || [];
      if (strip) {
        strip.innerHTML = grid.map(function (g) {
          var cls = "mt-cell";
          var s = (g.status || "").toLowerCase();
          if (s === "paid" || s === "full payment") cls += " is-paid";
          else if (s === "partial") cls += " is-partial";
          else if (s === "unpaid") cls += " is-unpaid";
          else if (s.indexOf("pending") >= 0) cls += " is-pending";
          else if (s === "exempt") cls += " is-exempt";
          else if (s === "retired") cls += " is-retired";
          else cls += " is-notdue";
          return '<span class="' + cls + '" title="' + esc(g.status) + '">' + esc(g.label) + "</span>";
        }).join("");
      }

      if (!grid.length) {
        body.innerHTML = emptyRow(4, "No dues history yet.");
        return;
      }
      body.innerHTML = grid.map(function (g) {
        return "<tr>" +
          "<td>" + esc(g.label) + "</td>" +
          "<td><span class='st-tag'>" + esc(g.status) + "</span></td>" +
          "<td style='text-align:right;'>" + peso(g.amount) + "</td>" +
          "<td>" + esc(g.detail || "") + "</td>" +
          "</tr>";
      }).join("");
    });
  }

  function loadContributions() {
    return getJSON("/api/member/records/contributions/").then(function (data) {
      var body = $("mtContribBody");
      if (!body) return;
      if (!data || !data.ok) { body.innerHTML = errorRow(6); return; }
      var items = data.items || [];
      if (!items.length) { body.innerHTML = emptyRow(6, "No contributions recorded."); return; }
      body.innerHTML = items.map(function (c) {
        return "<tr>" +
          "<td>" + esc(shortDate(c.payment_date)) + "</td>" +
          "<td>" + esc(c.aid_type || "—") + "</td>" +
          "<td>" + esc(c.target_month || "—") + "</td>" +
          "<td style='text-align:right;'>" + peso(c.expected) + "</td>" +
          "<td style='text-align:right;font-weight:600;'>" + peso(c.paid) + "</td>" +
          "<td><span class='st-tag'>" + esc(c.status) + "</span></td>" +
          "</tr>";
      }).join("");
    });
  }

  function loadPayments() {
    return getJSON("/api/member/records/payments/?page=1&per_page=50").then(function (data) {
      var body = $("mtPayBody");
      if (!body) return;
      if (!data || !data.ok) { body.innerHTML = errorRow(8); return; }
      var items = data.items || [];
      if (!items.length) { body.innerHTML = emptyRow(8, "No payment records yet."); return; }
      body.innerHTML = items.map(function (p) {
        return "<tr>" +
          "<td>" + esc(shortDate(p.date)) + "</td>" +
          "<td>" + esc(p.kind) + "</td>" +
          "<td>" + esc(p.period || "—") + "</td>" +
          "<td>" + esc(p.method || "—") + "</td>" +
          "<td style='text-align:right;font-weight:600;'>" + peso(p.amount) + "</td>" +
          "<td><span class='st-tag'>" + esc(p.treasurer_status || "—") + "</span></td>" +
          "<td><span class='st-tag'>" + esc(p.auditor_status || "—") + "</span></td>" +
          "<td><span class='st-tag'>" + esc(p.president_status || "—") + "</span></td>" +
          "</tr>";
      }).join("");
    });
  }

  function loadRecordPanel() {
    if (state.recordPanel === "contributions") return loadContributions();
    if (state.recordPanel === "payments") return loadPayments();
    return loadDues();
  }

  function showRecordPanel(name) {
    state.recordPanel = name;
    ["dues", "contributions", "payments"].forEach(function (key) {
      var el = $("mtPanel" + key.charAt(0).toUpperCase() + key.slice(1));
      if (el) el.style.display = key === name ? "" : "none";
    });
    var tabs = document.querySelectorAll("#mtRecTabs .filter-tab");
    Array.prototype.forEach.call(tabs, function (t) {
      t.classList.toggle("active", t.getAttribute("data-panel") === name);
    });
    loadRecordPanel();
  }

  // -------------------------------------------------------------- entry point

  /* `force` distinguishes "the member opened the tab" from "the member asked
   * for fresh data". Opening an already-loaded tab must not re-fire every
   * request on every tab switch, so the default is a no-op once loaded. */
  function load(force) {
    if (!$("view-transparency")) return Promise.resolve();
    if (state.loaded && !force) return Promise.resolve();
    state.loaded = true;
    return Promise.all([
      loadSummary(),
      loadTrend(),
      loadFlow(1),
      loadRecordPanel(),
    ]);
  }

  function bind() {
    }

    var flowTabs = document.querySelectorAll("#mtFlowTabs .filter-tab");
    Array.prototype.forEach.call(flowTabs, function (btn) {
      if (btn.dataset.bound) return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", function () {
        Array.prototype.forEach.call(flowTabs, function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        state.flow.direction = btn.getAttribute("data-direction") || "";
        loadFlow(1);
      });
    });

    var apply = $("mtFlowApply");
    if (apply && !apply.dataset.bound) {
      apply.dataset.bound = "1";
      apply.addEventListener("click", function () {
        state.flow.kind = ($("mtFlowKind") || {}).value || "";
        state.flow.year = ($("mtFlowYear") || {}).value || "";
        state.flow.date_from = ($("mtFlowFrom") || {}).value || "";
        state.flow.date_to = ($("mtFlowTo") || {}).value || "";
        loadFlow(1);
      });
    }

    var clear = $("mtFlowClear");
    if (clear && !clear.dataset.bound) {
      clear.dataset.bound = "1";
      clear.addEventListener("click", function () {
        state.flow = { page: 1, direction: "", kind: "", year: "", date_from: "", date_to: "" };
        ["mtFlowKind", "mtFlowYear", "mtFlowFrom", "mtFlowTo"].forEach(function (id) {
          var el = $(id); if (el) el.value = "";
        });
        Array.prototype.forEach.call(flowTabs, function (b) {
          b.classList.toggle("active", !b.getAttribute("data-direction"));
        });
        loadFlow(1);
      });
    }

    var prev = $("mtFlowPrev");
    if (prev && !prev.dataset.bound) {
      prev.dataset.bound = "1";
      prev.addEventListener("click", function () {
        if (state.flowPage > 1) loadFlow(state.flowPage - 1);
      });
    }
    var next = $("mtFlowNext");
    if (next && !next.dataset.bound) {
      next.dataset.bound = "1";
      next.addEventListener("click", function () {
        if (state.flowPage < state.flowPages) loadFlow(state.flowPage + 1);
      });
    }

    var body = $("mtFlowBody");
    if (body && !body.dataset.bound) {
      body.dataset.bound = "1";
      body.addEventListener("click", function (ev) {
        var tr = ev.target.closest ? ev.target.closest("tr[data-tx]") : null;
        if (tr) openMovement(tr.getAttribute("data-tx"));
      });
    }

    var recTabs = document.querySelectorAll("#mtRecTabs .filter-tab");
    Array.prototype.forEach.call(recTabs, function (btn) {
      if (btn.dataset.bound) return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", function () {
        showRecordPanel(btn.getAttribute("data-panel"));
      });
    });
  }

  /* The Transparency tab costs several requests, so it is loaded lazily: only
   * when the member actually opens the view. The active-view check covers the
   * case where it was the member's last-used tab and is therefore already
   * showing before this deferred script runs. */
  function boot() {
    bind();
    var view = $("view-transparency");
    if (view && view.classList.contains("active")) load();
  }

  document.addEventListener("DOMContentLoaded", boot);
  document.addEventListener("turbo:load", boot);

  window.MemberTransparency = { load: load, reload: function () { load(true); } };
})();
