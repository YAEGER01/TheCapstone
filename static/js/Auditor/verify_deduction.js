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
    const outstanding = Number(a.total_outstanding) || 0;
    return `<div class="avd-card" data-assessment-id="${a.assessment_id}" onclick="auditReviewDeduction(${a.assessment_id})" role="button" tabindex="0"
      onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();auditReviewDeduction(${a.assessment_id});}">
      <div class="avd-card-head">
        <span class="avd-card-month">${a.month_label}</span>
        ${statusBadge(a.status, a.status_label)}
      </div>
      <div class="avd-card-stats">
        <div><span>Members</span><b>${a.recorded_count}</b></div>
        <div><span>Expected Amount</span><b>${PESO(a.total_amount)}</b></div>
        <div><span>Collected Amount</span><b>${PESO(a.total_recorded)}</b></div>
        <div><span>Outstanding Balance</span><b class="${outstanding > 0 ? "avd-neg" : "avd-ok"}">${PESO(a.total_outstanding)}</b></div>
      </div>
      <button type="button" class="btn-outline avd-card-btn" onclick="event.stopPropagation();auditReviewDeduction(${a.assessment_id})">${buttonLabel}</button>
    </div>`;
  }

  function historyCard(a) {
    const outstanding = Number(a.total_outstanding) || 0;
    const [bg, fg] = STATUS_BADGE[a.status] || ["#eeeeee", "#555555"];
    return `<div class="avd-card avd-hist-card" data-assessment-id="${a.assessment_id}"
      style="--avd-status-bg:${bg};--avd-status-fg:${fg};" title="${esc(a.status_label || a.status)}">
      <div class="avd-hist-head" onclick="avdToggleHistCard(this)" role="button" tabindex="0" aria-expanded="false"
        onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();avdToggleHistCard(this);}">
        <span class="avd-hist-titles">
          <span class="avd-card-month">${a.month_label}</span>
          <span class="avd-hist-status" style="color:${fg};">${esc(a.status_label || a.status)}</span>
        </span>
        <i class="fa-solid fa-chevron-down avd-hist-chev"></i>
      </div>
      <div class="avd-hist-body">
        <div class="avd-card-stats">
          <div><span>Members</span><b>${a.recorded_count}</b></div>
          <div><span>Expected Amount</span><b>${PESO(a.total_amount)}</b></div>
          <div><span>Collected Amount</span><b>${PESO(a.total_recorded)}</b></div>
          <div><span>Outstanding Balance</span><b class="${outstanding > 0 ? "avd-neg" : "avd-ok"}">${PESO(a.total_outstanding)}</b></div>
        </div>
        <button type="button" class="btn-outline avd-card-btn" onclick="event.stopPropagation();auditReviewDeduction(${a.assessment_id})">Review</button>
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
    document.querySelectorAll("#audit-verify-deduction .avd-card").forEach((el) => {
      el.classList.toggle("active", Number(el.dataset.assessmentId) === Number(assessmentId));
    });
  }

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
  const AVD_RECENT_PAGE_SIZE = 8;
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
        const openIds = Array.from(recentList.querySelectorAll(".avd-hist-card.open"))
          .map((c) => Number(c.dataset.assessmentId));
        if (!all.length) {
          recentList.innerHTML = `<div class="avd-empty"><i class="fa-solid fa-clock-rotate-left"></i>Nothing actioned yet.</div>`;
          if (pager) pager.innerHTML = "";
        } else {
          const pageCount = Math.max(1, Math.ceil(all.length / AVD_RECENT_PAGE_SIZE));
          avdRecentPage = Math.min(Math.max(avdRecentPage, 1), pageCount);
          const rows = all.slice((avdRecentPage - 1) * AVD_RECENT_PAGE_SIZE, avdRecentPage * AVD_RECENT_PAGE_SIZE);
          recentList.innerHTML = rows.map(historyCard).join("");
          openIds.forEach((id) => {
            const card = recentList.querySelector(`.avd-hist-card[data-assessment-id="${id}"]`);
            if (card) {
              card.classList.add("open");
              const head = card.querySelector(".avd-hist-head");
              if (head) head.setAttribute("aria-expanded", "true");
            }
          });
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
        // Single-write render: rebuild the whole members table inside its
        // wrapper. Headers are static (no sort toggles); rows always list
        // members A→Z. One innerHTML assignment, same mechanism as the
        // initial detail paint.
        const wrap = document.getElementById("avd-members-table-wrap");
        const rowsHtml = window.__avdApplySort().map(window.__avdMemberRowHtml).join("")
          || '<tr><td colspan="6" style="text-align:center;color:#757575;padding:16px;">No deductions recorded.</td></tr>';
        if (wrap) {
          wrap.innerHTML = `<table class="custom-table"><thead><tr>`
            + `<th style="white-space:nowrap;">Member</th>`
            + `<th style="white-space:nowrap;">Department</th>`
            + `<th>Expected per Member</th><th>Deducted</th>`
            + `<th>Unpaid</th>`
            + `<th style="text-align:center;">Details</th></tr></thead><tbody>${rowsHtml}</tbody><tfoot>${window.__avdTotalsRow || ""}</tfoot></table>`;
          void wrap.offsetHeight;
        }
        const titleEl = document.getElementById("avd-members-title");
        if (titleEl) {
          titleEl.textContent = "Recorded Deductions (" + (window.__avdRows || []).length + ")";
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
      document.getElementById("avd-detail-body").innerHTML = `
        <div style="display:flex; flex-direction:column; gap:20px;">
          <div>
            <h4 style="margin:0 0 8px;"><span id="avd-members-title">Recorded Deductions (${(data.member_assessments || []).length})</span></h4>
            <div id="avd-members-table-wrap" style="max-height:420px; overflow:auto;"></div>
          </div>
          <div>
            <h4 style="margin:0 0 8px;">Breakdown</h4>
            <table class="custom-table" style="table-layout:fixed;"><colgroup><col style="width:32%;"><col style="width:18%;"><col style="width:50%;"></colgroup><thead><tr><th>Purpose</th><th>Amount</th><th>Recipient</th></tr></thead><tbody>${itemsHtml || '<tr><td colspan="3">None</td></tr>'}</tbody></table>
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

    try {
      const resp = await fetch("/api/auditor/deductions/verify/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": getCookie("csrftoken") },
        body: JSON.stringify({ assessment_id: Number(assessmentId), action, notes }),
      });
      const data = await resp.json();
      if (!data.ok) { toast(data.error || "Action failed.", true); return; }
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
