/* Monthly Deduction Verification (Auditor)
 * Review the Treasurer's recorded deductions against the president-set
 * breakdown, then verify (endorse to President) or reject. Calls:
 *   GET  /api/auditor/deductions/queue/
 *   GET  /api/auditor/deductions/detail/<assessmentId>/
 *   POST /api/auditor/deductions/verify/
 */
(function () {
  "use strict";
  console.log("=== VERIFY DEDUCTION JS LOADED - VERSION 20260927vd44 ===");

  const PESO = (v) => "₱" + Number(v || 0).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const esc = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
  }

  function toast(message, isError) {
    if (typeof window.showToast === "function") window.showToast(message, isError);
    else if (isError) console.error(message);
  }

  const STATUS_BADGE = {
    draft: ["#eceff1", "#455a64"],
    pending_treasurer: ["#e0f2f1", "#00695c"],
    pending_deposit: ["#e8eaf6", "#283593"],
    pending_audit: ["#fff8e1", "#8a6d3b"],
    pending_final: ["#f3e5f5", "#6a1b9a"],
    final_approved: ["#e8f5e9", "#1b5e20"],
    rejected: ["#ffebee", "#c62828"],
    returned: ["#fff3e0", "#e65100"],
  };

  function statusBadge(status, label) {
    const [bg, fg] = STATUS_BADGE[status] || ["#eeeeee", "#555555"];
    return `<span style="background:${bg};color:${fg};padding:2px 10px;border-radius:12px;font-size:0.75rem;font-weight:600;">${label || status}</span>`;
  }

  function assessmentCard(a, buttonLabel) {
    return `<div class="avd-card" data-assessment-id="${a.assessment_id}" onclick="auditReviewDeduction(${a.assessment_id})" role="button" tabindex="0"
      onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();auditReviewDeduction(${a.assessment_id});}">
      <div class="avd-card-head">
        <span class="avd-card-month">${a.month_label}</span>
        ${statusBadge(a.status, a.status_label)}
      </div>
      <button type="button" class="btn-outline avd-card-btn" onclick="event.stopPropagation();auditReviewDeduction(${a.assessment_id})">${buttonLabel}</button>
    </div>`;
  }

  /* History card: same header / grid / footer structure as the President
     history card — header (month + Review), 2x2 stat grid, footer (status
     badge + remarks). Always expanded; no accordion. */
  function historyCard(a) {
    const st = String(a.status || "draft");
    const remarks = esc(a.auditor_remarks || a.president_remarks || a.treasurer_remarks || "");
    return `<div class="avd-hist-card avd-st-${st}" data-assessment-id="${a.assessment_id}"
      title="${esc(a.status_label || a.status)}" role="button" tabindex="0"
      onclick="avdReviewFromHistory(${a.assessment_id})"
      onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();avdReviewFromHistory(${a.assessment_id});}">
      <div class="avd-h-head">
        <div>
          <div class="avd-h-title">${esc(a.month_label)}</div>
          <div class="avd-h-sub">${PESO(a.total_amount)} / member &middot; ${esc(String(a.recorded_count || 0))} active</div>
        </div>
        <div class="avd-h-actions">
          <button type="button" class="btn-outline" onclick="event.stopPropagation();avdReviewFromHistory(${a.assessment_id})">Review</button>
        </div>
      </div>
      <div class="avd-h-grid">
        <div class="avd-h-cell"><span>Per member</span><strong>${PESO(a.total_amount)}</strong></div>
        <div class="avd-h-cell"><span>Active</span><strong>${esc(String(a.recorded_count || 0))}</strong></div>
        <div class="avd-h-cell"><span>Collected</span><strong>${PESO(a.total_recorded)}</strong></div>
        <div class="avd-h-cell"><span>Unpaid</span><strong>${PESO(a.total_outstanding)}</strong></div>
      </div>
      <div class="avd-h-foot">
        <div class="avd-h-status">${statusBadge(a.status, a.status_label)}</div>
        <p class="avd-h-remarks">${remarks}</p>
      </div>
    </div>`;
  }

  window.avdToggleHistCard = function avdToggleHistCard(headEl) {
    const card = headEl.closest(".avd-hist-card");
    if (!card) return;
    const willOpen = !card.classList.contains("open");
    document.querySelectorAll("#avd-recent-list .avd-hist-card.open").forEach((c) => {
      c.classList.remove("open");
      const h = c.querySelector(".avd-hist-head");
      if (h) h.setAttribute("aria-expanded", "false");
    });
    if (willOpen) {
      card.classList.add("open");
      headEl.setAttribute("aria-expanded", "true");
    }
  };

  function markActiveCard(assessmentId) {
    document.querySelectorAll("#audit-verify-deduction .avd-card, #audit-verify-deduction .avd-hist-card").forEach((el) => {
      el.classList.toggle("active", Number(el.dataset.assessmentId) === Number(assessmentId));
    });
  }

  // Review launched from the history drawer: close the drawer first so the
  // detail panel is visible, then load the record (which scrolls to it).
  window.avdReviewFromHistory = function avdReviewFromHistory(assessmentId) {
    try { if (window.avdCloseHistory) window.avdCloseHistory(); } catch (e) {}
    window.auditReviewDeduction(assessmentId);
  };

  window.avdCloseDetail = function avdCloseDetail() {
    const body = document.getElementById("avd-detail-body");
    const title = document.getElementById("avd-detail-title");
    const actions = document.getElementById("avd-detail-actions");
    if (title) title.textContent = "Assessment Details";
    if (body) body.innerHTML = `<div class="avd-empty"><i class="fa-solid fa-file-circle-check"></i>Select a record from the list to review its details here.</div>`;
    if (actions) { actions.style.display = "none"; delete actions.dataset.assessmentId; }
    markActiveCard(null);
  };

  let avdRecentPage = 1;
  const AVD_RECENT_PAGE_SIZE = 10;
  window.__avdRecentGoPage = function (p) { avdRecentPage = p; window.loadAuditDeductionQueue(); };

  // Silent mode (background realtime refresh) never toasts — a failing
  // background poll must not spam the auditor every few seconds.
  window.loadAuditDeductionQueue = async function loadAuditDeductionQueue(silent) {
    try {
      const resp = await fetch("/api/auditor/deductions/queue/", { cache: "no-store" });
      const data = await resp.json();
      if (!data.ok) { if (!silent) toast(data.error || "Failed to load the verification queue.", true); return; }

      const pendingList = document.getElementById("avd-pending-list");
      if (pendingList) {
        pendingList.innerHTML = data.pending.length
          ? data.pending.map((a) => assessmentCard(a, "Review")).join("")
          : `<div class="avd-empty"><i class="fa-solid fa-circle-check"></i>No pending dues records for audit review.</div>`;
        const activeId = (document.getElementById("avd-detail-actions") || {}).dataset
          ? document.getElementById("avd-detail-actions").dataset.assessmentId
          : null;
        if (activeId) markActiveCard(activeId);
      }

      setBadge("avd-pending-dot", data.pending.length);

      const recentList = document.getElementById("avd-recent-list");
      if (recentList) {
        const pager = document.getElementById("avd-recent-pagination");
        const all = data.recent || [];
        if (!all.length) {
          recentList.innerHTML = `<div class="avd-empty"><i class="fa-solid fa-clock-rotate-left"></i>Nothing actioned yet.</div>`;
          if (pager) pager.innerHTML = "";
        } else {
          const pageCount = Math.max(1, Math.ceil(all.length / AVD_RECENT_PAGE_SIZE));
          avdRecentPage = Math.min(Math.max(avdRecentPage, 1), pageCount);
          const rows = all.slice((avdRecentPage - 1) * AVD_RECENT_PAGE_SIZE, avdRecentPage * AVD_RECENT_PAGE_SIZE);
          recentList.innerHTML = rows.map(historyCard).join("");
          if (pager && typeof UniPager !== "undefined") {
            pager.innerHTML = UniPager.html(avdRecentPage, pageCount, "window.__avdRecentGoPage(PAGE)", UniPager.count(avdRecentPage, AVD_RECENT_PAGE_SIZE, all.length));
          }
        }
      }
    } catch (e) {
      console.error("Failed to load deduction queue", e);
      if (!silent) toast("Failed to load the verification queue.", true);
    }
  };

  function docImageLinks(images) {
    return (images || []).map((img, i) =>
      `<a href="${img.url}" target="_blank" rel="noopener" title="View ${String(img.name || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")}" style="color:#1565c0; text-decoration:underline; font-weight:600;">Image ${i + 1}</a>`
    ).join(" · ");
  }

  /* Sketch-style per-member collection line: "Due 100 · Token 50 = ₱150 Paid". */
  function avdMiniCollectionLine(ma) {
    const allocs = ma.allocations || [];
    if (!allocs.length) return "";
    const short = (l) => String(l || "").replace(/\s*\([^)]*\)/g, "");
    const parts = allocs.map((a) => `${short(a.purpose_label)} ${PESO(a.applied)}`);
    const prior = Number(ma.prior_outstanding_collected) || 0;
    const total = allocs.reduce((s, a) => s + (Number(a.applied) || 0), 0) + prior;
    let line = parts.join(" · ") + (prior > 0 ? ` · Prior ${PESO(prior)}` : "") + ` = <b style="color:#1b5e20;">${PESO(total)}</b>`;
    if ((ma.actual_deduction || 0) <= 0) {
      line += ` <span style="color:#c62828;font-weight:700;">NOT PAID</span> out of ${PESO(Number(ma.standard_assessment) + Number(ma.prior_outstanding || 0))}`;
    } else if ((ma.outstanding_balance || 0) > 0.005) {
      line += ` <span style="color:#e65100;font-weight:700;">PARTIAL</span> out of ${PESO(Number(ma.standard_assessment) + Number(ma.prior_outstanding || 0))}`;
    } else {
      line += ` <span style="color:#2e7d32;font-weight:700;">PAID</span>`;
    }
    return `<div style="font-size:0.7rem; color:#8a949e; margin-top:2px;">${line}</div>`;
  }

  window.auditReviewDeduction = async function auditReviewDeduction(assessmentId) {
    const panel = document.getElementById("avd-detail-panel");
    if (!panel) return;
    panel.style.display = "block";
    markActiveCard(assessmentId);
    try { if (window.avdCloseHistory) window.avdCloseHistory(); } catch (e) {}
    try { panel.scrollIntoView({ behavior: "smooth", block: "start" }); } catch (e) { try { panel.scrollIntoView(); } catch (e2) {} }
    const body = document.getElementById("avd-detail-body");
    if (body) body.innerHTML = `<div class="avd-empty"><i class="fa-solid fa-spinner fa-spin"></i>Loading assessment details…</div>`;
    try {
      const resp = await fetch(`/api/auditor/deductions/detail/${assessmentId}/`, { cache: "no-store" });
      const data = await resp.json();
      if (!data.ok) { toast(data.error || "Failed to load details.", true); window.avdCloseDetail(); return; }
      const a = data.assessment;

      document.getElementById("avd-detail-title").innerHTML =
        `${a.month_label} — ${PESO(a.total_amount)} per member ${statusBadge(a.status, a.status_label)}`;

      const itemsHtml = (a.items || []).map((i) =>
        `<tr><td style="padding:5px 8px;">${i.purpose_label}</td><td style="padding:5px 8px;">${PESO(i.amount)}</td><td style="padding:5px 8px;">${i.recipient ? "For: " + i.recipient : "—"}</td></tr>`
      ).join("");

      const allocData = {};
    const memberSortKey = (value) => {
      const name = String(value || "").trim();
      if (name.includes(",")) return name.split(",", 1)[0].trim().toLocaleLowerCase();
      const parts = name.split(/\s+/);
      return parts.length ? parts[parts.length - 1].toLocaleLowerCase() : "";
    };
    const memberByName = (a, b) =>
      memberSortKey(a.member_name).localeCompare(memberSortKey(b.member_name), "en", { sensitivity: "base" }) ||
      String(a.member_name || "").localeCompare(String(b.member_name || ""), "en", { sensitivity: "base" });
    /* Interactive header sorts — one active at a time. Member: alphabetical
       toggle. Department: similar departments grouped, most members on top.
       Unpaid: largest unpaid on top. */
    window.__avdRows = (data.member_assessments || []).slice();
    window.__avdSort = { key: "member", dir: 1 };
    window.__avdFilter = "all";
    window.__avdPage = 1;
    window.__avdPageSize = 50;
    const deptCounts = {};
    window.__avdRows.forEach((ma) => {
      const d = String(ma.department || "—");
      deptCounts[d] = (deptCounts[d] || 0) + 1;
    });
    window.__avdDeptCounts = deptCounts;
    window.__avdRows.forEach((ma) => { allocData[ma.member_assessment_id] = ma; });
    window.__avdAllocData = allocData;
    window.__avdMemberRowHtml = function (ma) {
        const priorNote = ma.prior_outstanding > 0
          ? `<div style="font-size:0.75rem; font-weight:400; color:#8a6d3b;">prior ${PESO(ma.prior_outstanding)} from ${ma.prior_month_label || "previous month"} — collected ${PESO(ma.prior_outstanding_collected)}</div>`
          : "";
        const changeNote = ma.change_amount > 0
          ? `<div style="font-size:0.75rem; font-weight:400; color:#2e7d32;">excess to ISUCauFA funds: ${PESO(ma.change_amount)}</div>`
          : "";
        return `<tr>
            <td style="padding:6px 8px;">${ma.member_name}${ma.is_excluded ? ` <span style="display:inline-block;padding:1px 8px;border-radius:8px;font-size:0.66rem;font-weight:700;background:#fff3e0;color:#e65100;">Excluded</span>` : ""}${priorNote}${changeNote}</td>
            <td style="padding:6px 8px;">${ma.department || "—"}</td>
            <td style="padding:6px 8px;">${PESO(ma.standard_assessment)}</td>
            <td style="padding:6px 8px;">${PESO(ma.actual_deduction)}</td>
            <td style="padding:6px 8px; ${ma.outstanding_balance > 0 ? "color:#c62828;font-weight:600;" : ""}">${PESO(ma.outstanding_balance)}</td>
            <td style="padding:6px 8px; text-align:center;">
              <button type="button" class="btn-outline" style="padding:2px 10px; font-size:0.75rem;" onclick="avdViewAllocations(${ma.member_assessment_id})">Allocations</button>
            </td>
          </tr>`;
    };
    window.__avdStatusOf = function (ma) {
      const balance = Number(ma.outstanding_balance) || 0;
      if (balance > 0.005) return "unpaid";
      return "paid";
    };
    window.__avdSetFilter = function (f) {
      window.__avdFilter = f || "all";
      window.__avdPage = 1;
      window.__avdRenderMemberRows();
    };
    window.__avdGoPage = function (p) {
      const filtered = window.__avdFilteredRows ? window.__avdFilteredRows() : (window.__avdRows || []);
      const pageCount = Math.max(1, Math.ceil(filtered.length / (window.__avdPageSize || 50)));
      window.__avdPage = Math.min(Math.max(1, Number(p) || 1), pageCount);
      window.__avdRenderMemberRows();
    };
    window.__avdFilteredRows = function () {
      const sorted = window.__avdApplySort();
      const f = window.__avdFilter || "all";
      if (f === "all") return sorted;
      return sorted.filter((ma) => window.__avdStatusOf(ma) === f);
    };
    window.__avdApplySort = function () {
        const s = window.__avdSort || { key: "member", dir: 1 };
        const rows = (window.__avdRows || []).slice();
        if (s.key === "department") {
          const counts = window.__avdDeptCounts || {};
          rows.sort((a, b) =>
            ((counts[String(b.department || "—")] || 0) - (counts[String(a.department || "—")] || 0)) ||
            String(a.department || "").localeCompare(String(b.department || ""), "en", { sensitivity: "base" }) ||
            memberByName(a, b));
        } else if (s.key === "unpaid") {
          rows.sort((a, b) => ((Number(b.outstanding_balance) || 0) - (Number(a.outstanding_balance) || 0)) || memberByName(a, b));
        } else {
          rows.sort(memberByName);
          if (s.dir < 0) rows.reverse();
        }
        return rows;
    };
    window.__avdRenderMemberRows = function () {
        // Filter (all/paid/unpaid) + paginate at 50 rows per page.
        const wrap = document.getElementById("avd-members-table-wrap");
        const pager = document.getElementById("avd-members-pager");
        const pageSize = window.__avdPageSize || 50;
        const filtered = window.__avdFilteredRows();
        const total = (window.__avdRows || []).length;
        const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
        window.__avdPage = Math.min(Math.max(1, window.__avdPage || 1), pageCount);
        const start = (window.__avdPage - 1) * pageSize;
        const pageRows = filtered.slice(start, start + pageSize);
        const rowsHtml = pageRows.map(window.__avdMemberRowHtml).join("")
          || '<tr><td colspan="6" style="text-align:center;color:#757575;padding:16px;">No deductions recorded.</td></tr>';
        if (wrap) {
          const sticky = "position:sticky;top:0;z-index:3;background:#eef6ee;box-shadow:0 1px 0 #d3e2d3;";
          wrap.innerHTML = `<table class="custom-table" style="border-collapse:separate;border-spacing:0;"><thead style="position:sticky;top:0;z-index:3;"><tr>`
            + `<th style="white-space:nowrap;${sticky}">Member</th>`
            + `<th style="white-space:nowrap;${sticky}">Department</th>`
            + `<th style="${sticky}">Expected per Member</th><th style="${sticky}">Deducted</th>`
            + `<th style="${sticky}">Unpaid</th>`
            + `<th style="text-align:center;${sticky}">Details</th></tr></thead><tbody>${rowsHtml}</tbody><tfoot>${window.__avdTotalsRow || ""}</tfoot></table>`;
          void wrap.offsetHeight;
        }
        // Filter pill counts.
        const counts = { all: total, paid: 0, unpaid: 0 };
        (window.__avdRows || []).forEach((ma) => {
          const s = window.__avdStatusOf(ma);
          if (counts[s] != null) counts[s] += 1;
        });
        ["all", "paid", "unpaid"].forEach((k) => {
          const el = document.getElementById("avd-count-" + k);
          if (el) el.textContent = counts[k];
        });
        document.querySelectorAll("[data-avd-filter]").forEach((btn) => {
          const on = (btn.dataset.avdFilter === (window.__avdFilter || "all"));
          btn.style.background = on ? "#1b5e20" : "#fff";
          btn.style.color = on ? "#fff" : "#374151";
          btn.style.borderColor = on ? "#1b5e20" : "#d6ddd7";
          btn.setAttribute("aria-pressed", on ? "true" : "false");
        });
        if (pager) {
          const from = filtered.length ? start + 1 : 0;
          const to = Math.min(start + pageSize, filtered.length);
          let nums = "";
          const win = 2;
          const lo = Math.max(1, window.__avdPage - win);
          const hi = Math.min(pageCount, window.__avdPage + win);
          for (let p = lo; p <= hi; p++) {
            nums += `<button type="button" onclick="__avdGoPage(${p})" ${p === window.__avdPage ? 'disabled' : ""} style="min-width:30px;padding:4px 8px;border-radius:6px;border:1px solid ${p === window.__avdPage ? "#1b5e20" : "#d6ddd7"};background:${p === window.__avdPage ? "#1b5e20" : "#fff"};color:${p === window.__avdPage ? "#fff" : "#374151"};font-size:.78rem;font-weight:700;cursor:${p === window.__avdPage ? "default" : "pointer"};">${p}</button>`;
          }
          pager.innerHTML = `
            <div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px;margin-top:10px;">
              <div style="font-size:.78rem;color:#5b6675;">Showing ${from}–${to} of ${filtered.length} (total ${total})</div>
              <div style="display:flex;align-items:center;gap:6px;">
                <button type="button" onclick="__avdGoPage(${window.__avdPage - 1})" ${window.__avdPage <= 1 ? "disabled" : ""} style="padding:4px 12px;border-radius:6px;border:1px solid #d6ddd7;background:#fff;font-size:.78rem;font-weight:700;cursor:pointer;opacity:${window.__avdPage <= 1 ? ".45" : "1"};">Prev</button>
                ${pageCount > 7 && lo > 1 ? `<button type="button" onclick="__avdGoPage(1)" style="min-width:30px;padding:4px 8px;border-radius:6px;border:1px solid #d6ddd7;background:#fff;font-size:.78rem;font-weight:700;cursor:pointer;">1</button><span style="color:#8a949e;">…</span>` : ""}
                ${nums}
                ${pageCount > 7 && hi < pageCount ? `<span style="color:#8a949e;">…</span><button type="button" onclick="__avdGoPage(${pageCount})" style="min-width:30px;padding:4px 8px;border-radius:6px;border:1px solid #d6ddd7;background:#fff;font-size:.78rem;font-weight:700;cursor:pointer;">${pageCount}</button>` : ""}
                <button type="button" onclick="__avdGoPage(${window.__avdPage + 1})" ${window.__avdPage >= pageCount ? "disabled" : ""} style="padding:4px 12px;border-radius:6px;border:1px solid #d6ddd7;background:#fff;font-size:.78rem;font-weight:700;cursor:pointer;opacity:${window.__avdPage >= pageCount ? ".45" : "1"};">Next</button>
              </div>
            </div>`;
        }
        const titleEl = document.getElementById("avd-members-title");
        if (titleEl) {
          titleEl.textContent = "Recorded Deductions (" + total + ")";
        }
    };

      const totals = (data.member_assessments || []).reduce(
        (acc, m) => {
          acc.standard += m.standard_assessment;
          acc.deducted += m.actual_deduction;
          acc.outstanding += m.outstanding_balance;
          acc.count += 1;
          return acc;
        },
        { standard: 0, deducted: 0, outstanding: 0, count: 0 }
      );
      const totalsRow = totals.count ? `
        <tr style="background:#f5f5f5; font-weight:700; border-top:2px solid #1b5e20;">
          <td colspan="2" style="padding:6px 8px;">TOTAL (${totals.count} member${totals.count === 1 ? "" : "s"})</td>
          <td style="padding:6px 8px;">${PESO(totals.standard)}</td>
          <td style="padding:6px 8px;">${PESO(totals.deducted)}</td>
          <td style="padding:6px 8px; ${totals.outstanding > 0 ? "color:#c62828;" : "color:#1b5e20;"}">${PESO(totals.outstanding)}</td>
          <td></td>
        </tr>` : "";
      window.__avdTotalsRow = totalsRow;

      /* Collection summary card — mirrors the Treasurer's Submit-for-Deposit
         card (mdDepositSummary / mdDepositConfirmModal), computed from the
         recorded member assessments. Expected covers every member on the
         roster (excluded still owe); Collected counts non-excluded rows. */
      function avdDepositSummary(rows) {
        let expected = 0, collected = 0, after = 0, before = 0;
        let dueTotal = 0, priorTotal = 0, excess = 0;
        const itemApplied = {};
        const itemIsDue = {};
        const unpaidRows = [], priorRows = [], balanceRows = [];
        (rows || []).forEach((ma) => {
          const name = ma.member_name || "Member";
          expected += Number(ma.standard_assessment) || 0;
          const balance = Number(ma.outstanding_balance) || 0;
          after += balance;
          if (balance > 0.005) unpaidRows.push({ name, amount: balance });
          const actual = Number(ma.actual_deduction) || 0;
          const change = Number(ma.change_amount) || 0;
          const rowBefore = Math.max(0, balance + (ma.is_excluded ? 0 : actual - change));
          before += rowBefore;
          const priorOwed = Number(ma.prior_outstanding) || 0;
          if (priorOwed > 0.005) balanceRows.push({ name, before: rowBefore, after: balance });
          if (ma.is_excluded) return;
          collected += actual;
          const prior = Number(ma.prior_outstanding_collected) || 0;
          priorTotal += prior;
          if (prior > 0.005) priorRows.push({ name, amount: prior });
          excess += change;
          (ma.allocations || []).forEach((al) => {
            const id = String(al.item_id != null ? al.item_id : al.purpose_label);
            const label = al.purpose_label || al.purpose || "Item";
            const isDue = al.purpose === "monthly_due" || /monthly due/i.test(String(label));
            if (!(id in itemIsDue)) itemIsDue[id] = { isDue, label };
            itemApplied[id] = (itemApplied[id] || 0) + (Number(al.applied) || 0);
          });
        });
        const aidLines = Object.keys(itemApplied)
          .filter((id) => !((itemIsDue[id] || {}).isDue) && (itemApplied[id] || 0) > 0.005)
          .map((id) => ({ label: (itemIsDue[id] || {}).label || "Item", amount: itemApplied[id] }));
        Object.keys(itemApplied).forEach((id) => {
          if ((itemIsDue[id] || {}).isDue) dueTotal += itemApplied[id];
        });
        unpaidRows.sort((x, y) => y.amount - x.amount);
        priorRows.sort((x, y) => y.amount - x.amount);
        balanceRows.sort((x, y) => y.before - x.before);
        return { expected, collected, before, after, unpaidRows, balanceRows, dueTotal, aidLines, priorTotal, priorRows, excess };
      }

      window.__avdToggleSummary = function () {
        const body = document.getElementById("avd-summary-body");
        const chev = document.getElementById("avd-summary-chev");
        const head = document.getElementById("avd-summary-head");
        if (!body) return;
        const isHidden = body.style.display === "none";
        body.style.display = isHidden ? "" : "none";
        if (chev) chev.style.transform = isHidden ? "" : "rotate(-90deg)";
        if (head) head.setAttribute("aria-expanded", isHidden ? "true" : "false");
      };

      function avdSummaryCardHtml(summary, assessment) {
        summary = summary || {};
        const expected = summary.expected || 0;
        const collected = summary.collected || 0;
        const after = summary.after != null ? summary.after : 0;
        // Total including unpaid balances = what members owed BEFORE this
        // collection (current dues + prior unpaid). `before` already sums
        // per-row Before = outstanding + collected − excess, so it includes
        // prior dues that were just collected (e.g. 13100 current + 100
        // prior = 13200). Never use expected + after here: expected already
        // counts this month's dues, so adding the leftover `after`
        // double-counts the current portion and drops the prior paid.
        const beforeTotal = summary.before != null ? summary.before : (expected + after);
        const unpaidRows = summary.unpaidRows || [];
        const balanceRows = summary.balanceRows || [];
        const aidLines = summary.aidLines || [];
        const priorRows = summary.priorRows || [];
        const cap = (t) => `<div style="font-size:0.68rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#5b6675;">${t}</div>`;
        const big = (amt, color) => `<div style="font-size:1.3rem;font-weight:800;color:${color || "#1c2430"};font-variant-numeric:tabular-nums;margin:2px 0 10px;">${PESO(amt)}</div>`;
        const kv = (label, amt, color) => `
          <div style="display:flex;align-items:flex-end;gap:8px;font-size:0.8rem;padding:3px 0;">
            <span style="color:#5b6675;white-space:nowrap;">${esc(label)}</span>
            <span style="flex:1 1 auto;border-bottom:2px dotted #b9c6bb;transform:translateY(-4px);min-width:20px;" aria-hidden="true"></span>
            <span style="font-weight:700;color:${color || "#1c2430"};font-variant-numeric:tabular-nums;white-space:nowrap;">${PESO(amt)}</span>
          </div>`;
        const perMember = Number((assessment || {}).total_amount) || 0;
        const count = (window.__avdRows || []).length;
        return `
        <div id="avd-summary-card" style="background:#fff;border:1px solid #cfe0cf;border-radius:14px;box-sizing:border-box;box-shadow:0 4px 14px rgba(27,94,32,.08);font-family:inherit;color:#1c2430;overflow:hidden;">
          <button type="button" id="avd-summary-head" onclick="__avdToggleSummary()" aria-expanded="true" aria-controls="avd-summary-body" style="width:100%;background:none;border:none;cursor:pointer;display:flex;align-items:center;gap:10px;padding:16px 18px 12px;text-align:left;font-family:inherit;">
            <span style="flex:1;min-width:0;">
              <span style="display:block;font-weight:800;color:#1b5e20;font-size:.95rem;"><i class="fa-solid fa-file-invoice-dollar" style="margin-right:6px;"></i>Collection Summary</span>
              <span style="display:block;font-size:.75rem;color:#5b6675;margin-top:2px;">${count} member${count === 1 ? "" : "s"}${perMember ? ` &times; ${PESO(perMember)} per member` : ""} &nbsp;•&nbsp; Collected ${PESO(collected)} &nbsp;•&nbsp; Unpaid ${PESO(after)}</span>
            </span>
            <i id="avd-summary-chev" class="fa-solid fa-chevron-down" style="color:#8a949e;font-size:.8rem;transition:transform .18s ease;flex:0 0 auto;"></i>
          </button>
          <div id="avd-summary-body" style="padding:0 18px 18px;">
          <div style="margin-top:4px;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px;">
              <div style="min-width:0;border:1px solid #e6ebe7;border-radius:10px;background:#fbfdfb;padding:8px 12px;box-sizing:border-box;">
                ${cap("Total Amount Expected")}
                ${big(expected)}
                <div style="font-size:0.72rem;color:#8a949e;margin:-6px 0 0;">${PESO(beforeTotal)} if unpaid member balance is included</div>
              </div>
              <div style="min-width:0;border:1px solid #e6ebe7;border-radius:10px;background:#fbfdfb;padding:8px 12px;box-sizing:border-box;">
                ${cap("Collected Amount")}
                ${big(collected, "#1b5e20")}
              </div>
            </div>
            <div style="border:1px solid #e6ebe7;border-radius:10px;background:#fbfdfb;padding:6px 12px;margin:-4px 0 10px;box-sizing:border-box;">
              ${kv("Due", summary.dueTotal || 0, "#1b5e20")}
              ${aidLines.map((l) => kv(l.label, l.amount, "#1b5e20")).join("")}
              ${kv("Balance Paid", summary.priorTotal || 0, "#1b5e20")}
              ${priorRows.length ? `
              <div style="max-height:120px;overflow-y:auto;margin:2px 0 4px;padding-left:14px;box-sizing:border-box;">
                ${priorRows.map((r) => `<div style="font-size:0.78rem;color:#5b6675;padding:1px 0;font-variant-numeric:tabular-nums;">${PESO(r.amount)} - ${esc(r.name)}</div>`).join("")}
              </div>` : ""}
              ${(summary.excess || 0) > 0.005 ? kv("Excess to ISUCauFA funds", summary.excess, "#1b5e20") : ""}
            </div>
            ${cap("Unpaid Balances")}
            ${big(after, after > 0.005 ? "#c62828" : "#1b5e20")}
            ${balanceRows.length ? `
            <div style="max-height:180px;overflow-y:auto;border:1px solid #e6ebe7;border-radius:10px;background:#fbfdfb;padding:4px 12px;margin:6px 0 10px;box-sizing:border-box;">
              <div style="font-size:0.66rem;font-weight:800;letter-spacing:0.06em;text-transform:uppercase;color:#8a949e;padding:6px 0 2px;">Members with prior unpaid balances</div>
              ${balanceRows.map((r) => `
              <div style="padding:5px 0;border-bottom:1px dashed #e6ebe7;">
                <div style="font-size:0.8rem;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">- ${esc(r.name)}</div>
                <div style="font-size:0.78rem;font-variant-numeric:tabular-nums;margin-top:1px;">
                  <span style="color:#5b6675;">Before: ${PESO(r.before)}</span>
                  <span style="color:#8a949e;margin:0 6px;">|</span>
                  <span style="color:${r.after > 0.005 ? "#c62828" : "#1b5e20"};font-weight:700;">After: ${PESO(r.after)}</span>
                </div>
              </div>`).join("")}
            </div>` : `<div style="font-size:0.78rem;color:#8a949e;margin:6px 0 10px;">No prior unpaid balances.</div>`}
          </div>
          <div style="border-top:1px solid #e6ebe7;margin:12px 0 0;padding-top:10px;">
            <div style="font-size:0.72rem;font-weight:800;letter-spacing:0.06em;text-transform:uppercase;color:#5b6675;margin-bottom:6px;">Unpaid Members${unpaidRows.length ? ` (${unpaidRows.length})` : ""}</div>
            ${unpaidRows.length ? `
            <div style="max-height:220px;overflow-y:auto;border:1px solid #f0e0e0;border-radius:10px;background:#fffafa;padding:4px 10px;box-sizing:border-box;">
              ${unpaidRows.map((r) => `
              <div style="display:flex;justify-content:space-between;gap:14px;font-size:0.8rem;padding:5px 0;border-bottom:1px dashed #f3dcdc;">
                <span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">- ${esc(r.name)}</span>
                <span style="font-weight:700;color:#c62828;font-variant-numeric:tabular-nums;white-space:nowrap;">${PESO(r.amount)}</span>
              </div>`).join("")}
            </div>` : `<div style="font-size:0.82rem;color:#1b5e20;font-weight:700;">All members fully paid.</div>`}
          </div>
          </div>
        </div>`;
      }

      const avdSummary = avdDepositSummary(data.member_assessments || []);
      document.getElementById("avd-detail-body").innerHTML = `
        <div style="display:flex; flex-direction:column; gap:20px;">
          ${avdSummaryCardHtml(avdSummary, a)}
          <div>
            <h4 style="margin:0 0 8px;">Breakdown</h4>
            <table class="custom-table" style="table-layout:fixed;"><colgroup><col style="width:32%;"><col style="width:18%;"><col style="width:50%;"></colgroup><thead><tr><th>Purpose</th><th>Amount</th><th>Recipient</th></tr></thead><tbody>${itemsHtml || '<tr><td colspan="3">None</td></tr>'}</tbody></table>
          </div>
          <div>
            <h4 style="margin:0 0 8px;"><span id="avd-members-title">Recorded Deductions (${(data.member_assessments || []).length})</span></h4>
            <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;" role="group" aria-label="Filter by payment status">
              <button type="button" data-avd-filter="all" onclick="__avdSetFilter('all')" style="padding:5px 14px;border-radius:999px;border:1px solid #1b5e20;font-size:.78rem;font-weight:700;cursor:pointer;">All (<span id="avd-count-all">0</span>)</button>
              <button type="button" data-avd-filter="paid" onclick="__avdSetFilter('paid')" style="padding:5px 14px;border-radius:999px;border:1px solid #d6ddd7;font-size:.78rem;font-weight:700;cursor:pointer;">Paid (<span id="avd-count-paid">0</span>)</button>
              <button type="button" data-avd-filter="unpaid" onclick="__avdSetFilter('unpaid')" style="padding:5px 14px;border-radius:999px;border:1px solid #d6ddd7;font-size:.78rem;font-weight:700;cursor:pointer;">Unpaid (<span id="avd-count-unpaid">0</span>)</button>
            </div>
            <div id="avd-members-table-wrap" style="max-height:420px; overflow:auto;"></div>
            <div id="avd-members-pager"></div>
          </div>
          <div style="display:flex; gap:14px; align-items:stretch; flex-wrap:wrap;">
          <div style="flex:3 1 320px; min-width:0; padding:12px 14px; border:1px solid #a5d6a7; border-left:5px solid #2e7d32; border-radius:10px; background:#f3faf4; box-shadow:0 2px 6px rgba(46,125,50,0.10);">
            <h4 style="margin:0 0 10px; color:#1b5e20; font-size:0.9rem; letter-spacing:0.02em;"><i class="fa-solid fa-paperclip" style="color:#2e7d32; margin-right:6px;"></i>ATTACHMENTS TO REVIEW</h4>
            <div style="display:flex; gap:12px; flex-wrap:wrap; font-size:0.84rem;">
              <div>
                <strong style="display:inline-block; margin-right:4px;">Request Letter (ISUCauFA):</strong>
                ${(a.request_letter_images || []).length
                  ? docImageLinks(a.request_letter_images)
                  : '<span style="color:#757575;">not attached</span>'}
              </div>
              <div>
                <strong style="display:inline-block; margin-right:4px;">Deducted Amount Sheet:</strong>
                ${(a.deduction_sheet_images || []).length
                  ? docImageLinks(a.deduction_sheet_images)
                  : '<span style="color:#757575;">not attached</span>'}
              </div>
            </div>
          </div>
          <div style="flex:2 1 220px; min-width:0; display:flex;">
          ${typeof window.mdDepositEvidenceHtml === "function" ? window.mdDepositEvidenceHtml(a) : ""}
          </div>
          </div>
          ${typeof window.mdWorkflowTimelineHtml === "function" ? window.mdWorkflowTimelineHtml(data.workflow_logs || []) : ""}
        </div>`;

      window.__avdRenderMemberRows();

      const actions = document.getElementById("avd-detail-actions");
      if (actions) {
        actions.style.display = a.status === "pending_audit" ? "flex" : "none";
        actions.dataset.assessmentId = a.assessment_id;
        document.getElementById("avd-decision-remarks").value = "";
      }
      try { panel.scrollIntoView({ behavior: "smooth", block: "start" }); } catch (e) { try { panel.scrollIntoView(); } catch (e2) {} }
    } catch (e) {
      console.error("Failed to load assessment details", e);
      toast("Failed to load assessment details.", true);
      window.avdCloseDetail();
    }
  };


  // Allocation details open in a modal so the members table stays aligned.
  window.avdViewAllocations = function avdViewAllocations(memberAssessmentId) {
    const ma = (window.__avdAllocData || {})[memberAssessmentId];
    if (!ma) return;
    const rows = (ma.allocations || []).map((al) =>
      `<tr>
        <td style="padding:6px 10px; border:1px solid #ddd;">${al.purpose_label}</td>
        <td style="padding:6px 10px; border:1px solid #ddd; text-align:right;">${PESO(al.required)}</td>
        <td style="padding:6px 10px; border:1px solid #ddd; text-align:right;">${PESO(al.applied)}</td>
        <td style="padding:6px 10px; border:1px solid #ddd; text-align:right; ${al.remaining > 0 ? "color:#c62828; font-weight:600;" : "color:#1b5e20;"}">${PESO(al.remaining)}</td>
      </tr>`).join("");
    // The balance carried over from earlier months is not part of this
    // month's items — show it as its own row so the modal always explains
    // the member's full remaining balance.
    const priorReq = Number(ma.prior_outstanding) || 0;
    const priorCol = Number(ma.prior_outstanding_collected) || 0;
    const priorRow = priorReq > 0
      ? `<tr>
          <td style="padding:6px 10px; border:1px solid #ddd; background:#fffdf5;">Prior balance${ma.prior_month_label ? ` (${esc(ma.prior_month_label)})` : ""}</td>
          <td style="padding:6px 10px; border:1px solid #ddd; text-align:right; background:#fffdf5;">${PESO(priorReq)}</td>
          <td style="padding:6px 10px; border:1px solid #ddd; text-align:right; background:#fffdf5;">${PESO(priorCol)}</td>
          <td style="padding:6px 10px; border:1px solid #ddd; text-align:right; font-weight:600; ${priorReq - priorCol > 0 ? "color:#c62828;" : "color:#1b5e20;"} background:#fffdf5;">${PESO(priorReq - priorCol)}</td>
        </tr>`
      : "";
    const html = `
      <table style="width:100%; border-collapse:collapse; font-size:0.85rem;">
        <thead><tr>
          <th style="border:1px solid #ddd; background:#f5f5f5; padding:6px 10px; text-align:left;">Purpose</th>
          <th style="border:1px solid #ddd; background:#f5f5f5; padding:6px 10px; text-align:right;">Required</th>
          <th style="border:1px solid #ddd; background:#f5f5f5; padding:6px 10px; text-align:right;">Applied</th>
          <th style="border:1px solid #ddd; background:#f5f5f5; padding:6px 10px; text-align:right;">Outstanding</th>
        </tr></thead>
        <tbody>${rows}${priorRow}</tbody>
      </table>
      <div style="margin-top:10px; font-size:0.82rem; color:#475569;">
        Total remaining balance: <strong style="color:${Number(ma.outstanding_balance) > 0 ? "#c62828" : "#1b5e20"};">${PESO(ma.outstanding_balance)}</strong>
        
      </div>`;
    if (window.SimpleModal) SimpleModal.open({ title: `Allocations — ${ma.member_name}`, html, width: "560px" });
  };

  /* Action-PIN prompt as a standalone 3:4 vertical card (no outer chrome).
     The verify endpoint is PIN-gated server-side (@require_action_pin_view),
     so the PIN is collected AFTER the confirm above instead of failing with
     "Action PIN is required". */
  function avdPromptActionPin(heading, subtitle) {
    return new Promise(function (resolve) {
      let settled = false;
      const done = function (val) { if (!settled) { settled = true; cleanup(); resolve(val); } };
      const overlay = document.createElement("div");
      overlay.setAttribute("role", "dialog");
      overlay.setAttribute("aria-modal", "true");
      overlay.setAttribute("aria-label", heading || "Enter Action PIN");
      overlay.style.cssText = "position:fixed;inset:0;background:rgba(10,18,30,.55);z-index:6001;display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box;";
      overlay.innerHTML =
        "<style>#avd-pin-entry::-ms-reveal,#avd-pin-entry::-ms-clear{display:none;}#avd-pin-entry::-webkit-credentials-auto-fill-button{visibility:hidden;pointer-events:none;}</style>" +
        '<div style="aspect-ratio:3/4;width:min(300px,calc(100vw - 32px));display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:10px;padding:22px 18px;background:linear-gradient(180deg,#f3faf4 0%,#ffffff 60%);border:1px solid #cfe0cf;border-radius:18px;box-sizing:border-box;box-shadow:0 18px 60px rgba(0,0,0,.28);font-family:Inter,system-ui,sans-serif;color:#1c2430;">' +
          '<div style="width:52px;height:52px;border-radius:50%;background:#1b5e20;color:#fff;display:flex;align-items:center;justify-content:center;font-size:1.25rem;box-shadow:0 4px 12px rgba(27,94,32,.3);"><i class="fa-solid fa-lock"></i></div>' +
          '<div style="font-weight:800;color:#1b5e20;font-size:0.95rem;letter-spacing:0.02em;">' + esc(heading || "Verify Entries") + "</div>" +
          '<div style="font-size:0.78rem;color:#5b6675;line-height:1.5;max-width:220px;">' + esc(subtitle || "Enter your 4-digit action PIN to confirm this action.") + "</div>" +
          '<input id="avd-pin-entry" type="password" inputmode="numeric" pattern="[0-9]*" maxlength="4" autocomplete="current-password" placeholder="••••" ' +
            'style="width:170px;box-sizing:border-box;text-align:center;font-size:1.6rem;letter-spacing:0.45em;text-indent:0.45em;padding:10px 8px;border:1.5px solid #cfe0cf;border-radius:10px;outline:none;" />' +
          '<div id="avd-pin-err" style="min-height:18px;font-size:0.76rem;color:#c62828;"></div>' +
          '<div style="display:flex;gap:8px;width:100%;margin-top:2px;">' +
            '<button type="button" id="avd-pin-cancel" style="flex:1;border:none;border-radius:999px;padding:11px 14px;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:0.08em;cursor:pointer;background:#eef1f5;color:#1c2430;">Cancel</button>' +
            '<button type="button" id="avd-pin-ok" style="flex:1;border:none;border-radius:999px;padding:11px 14px;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:0.08em;cursor:pointer;background:#1e8f4e;color:#fff;box-shadow:0 4px 12px rgba(30,143,78,.35);">Confirm</button>' +
          "</div>" +
        "</div>";
      function cleanup() { if (overlay.parentNode) overlay.parentNode.removeChild(overlay); document.removeEventListener("keydown", onKey); }
      function onKey(e) { if (e.key === "Escape") done(null); }
      document.addEventListener("keydown", onKey);
      document.body.appendChild(overlay);
      const entry = overlay.querySelector("#avd-pin-entry");
      const errEl = overlay.querySelector("#avd-pin-err");
      const okBtn = overlay.querySelector("#avd-pin-ok");
      const cancelBtn = overlay.querySelector("#avd-pin-cancel");
      if (okBtn) {
        okBtn.addEventListener("mouseover", function () { okBtn.style.background = "#16703c"; });
        okBtn.addEventListener("mouseout", function () { okBtn.style.background = "#1e8f4e"; });
      }
      const fail = function (msg) { if (errEl) errEl.textContent = msg || ""; };
      if (entry) {
        entry.addEventListener("input", function () {
          entry.value = String(entry.value || "").replace(/\D/g, "").slice(0, 4);
          fail("");
        });
        entry.addEventListener("keydown", function (e) {
          if (e.key === "Enter") { e.preventDefault(); if (okBtn) okBtn.click(); }
        });
        setTimeout(function () { entry.focus(); }, 50);
      }
      if (cancelBtn) cancelBtn.addEventListener("click", function () { done(null); });
      if (okBtn) okBtn.addEventListener("click", function () {
        const pin = String((entry && entry.value) || "").replace(/\D/g, "").slice(0, 4);
        if (pin.length !== 4) { fail("PIN must be exactly 4 digits."); if (entry) entry.focus(); return; }
        done(pin);
      });
    });
  }

  window.auditDecideDeduction = async function auditDecideDeduction(action) {
    const actions = document.getElementById("avd-detail-actions");
    if (!actions) return;
    const assessmentId = actions.dataset.assessmentId;
    const notes = (document.getElementById("avd-decision-remarks") || {}).value || "";
    if (action === "reject" && !notes.trim()) {
      toast("Remarks are required when rejecting an entry.", true);
      return;
    }
    const verb = action === "approve" ? "verify" : "reject";
    const proceed = await SimpleModal.confirm(
      `Are you sure you want to ${verb} this monthly deduction?` + (action === "approve" ? " It will be endorsed to the President for final approval." : " It will be returned to the Treasurer for revision."),
      { title: action === "approve" ? "Verify Entries" : "Reject Entries", okText: verb === "verify" ? "Verify" : "Reject", danger: action !== "approve", cancelText: "Cancel" }
    );
    if (!proceed) return;

    // PIN-gated endpoint — prompt AFTER the confirm above so the input
    // always appears instead of failing with "Action PIN is required".
    const pinOpts = action === "approve"
      ? { heading: "Verify & Endorse", subtitle: "Enter your 4-digit action PIN to verify & endorse to the President." }
      : { heading: "Reject Entries", subtitle: "Enter your 4-digit action PIN to reject this entry." };
    const actionPin = await avdPromptActionPin(pinOpts.heading, pinOpts.subtitle);
    if (!actionPin) return;

    try {
      const resp = await fetch("/api/auditor/deductions/verify/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": getCookie("csrftoken"), "X-Action-PIN": actionPin },
        body: JSON.stringify({ assessment_id: Number(assessmentId), action, notes, action_pin: actionPin }),
      });
      const data = await resp.json();
      if (!data.ok) {
        if (data.code === "PIN_NOT_SET" && window.CaufaPin && window.CaufaPin.openSetup) {
          try { window.CaufaPin.openSetup("setup"); } catch (e2) {}
        }
        toast(data.error || "Action failed.", true); return;
      }
      toast(data.message || "Done.", false);
      loadAuditDeductionQueue();
      auditReviewDeduction(assessmentId);
    } catch (e) {
      console.error("Failed to submit decision", e);
      toast("Failed to submit decision.", true);
    }
  };

  document.addEventListener("DOMContentLoaded", loadAuditDeductionQueue);
  // Keep the badge current when the WebSocket is unavailable or reconnecting.
  setInterval(function () {
    fetch("/api/auditor/deductions/queue/", { cache: "no-store" })
      .then((resp) => resp.json())
      .then((data) => {
        if (data && data.ok) setBadge("avd-pending-dot", (data.pending || []).length);
      })
      .catch(() => {});
  }, 15000);
})();


  function setBadge(elId, count) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.textContent = count > 0 ? count : "";
    el.style.display = count > 0 ? "inline-flex" : "none";
  }

  // Live badge: updates instantly when any officer moves the workflow along.
  try {
    const proto = window.location.protocol === "https:" ? "wss://" : "ws://";
    const ws = new WebSocket(`${proto}${window.location.host}/ws/auditor-dashboard/?token=${encodeURIComponent(window.WS_AUTH_TOKEN || "")}`);
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "deduction_counts") setBadge("avd-pending-dot", msg["pending_audit"] || 0);
      } catch (e) {}
    };
  } catch (e) {}
