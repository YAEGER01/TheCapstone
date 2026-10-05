/* Monthly Dues Compliance (Auditor)
 * Department collection bars + member status table with checkbox
 * notification for members with outstanding balances.
 *   GET  /api/auditor/deductions/heatmap/          (?assessment_id=)
 *   POST /api/auditor/deductions/notify/
 */
(function () {
  "use strict";

  const PESO = (v) => "₱" + Number(v || 0).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const getCookie = (name) => {
    const parts = document.cookie.split(`; ${name}=`);
    return parts.length === 2 ? parts.pop().split(";").shift() : "";
  };
  const csrfToken = () => {
    const input = document.querySelector("input[name='csrfmiddlewaretoken']");
    return (input && input.value) || getCookie("csrftoken");
  };
  const esc = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");

  function toast(message, isError) {
    if (typeof window.showToast === "function") window.showToast(message, isError);
    else if (isError) console.error(message);
  }

  // Four-color scale, nothing rainbow: green / light green / yellow / red.
  function rateColor(rate) {
    if (rate >= 85) return "#2e7d32";
    if (rate >= 70) return "#7cb342";
    if (rate >= 50) return "#f9a825";
    return "#e53935";
  }

  const STATUS_BADGE = {
    full: ["#e8f5e9", "#1b5e20", "Paid"],
    partial: ["#fff8e1", "#8a6d3b", "Partial"],
    unpaid: ["#ffebee", "#c62828", "Unpaid"],
    retired: ["#eceff1", "#455a64", "Retired"],
  };

  function statusBadge(status) {
    // Map backend statuses: "zero" and "pending" both display as "Unpaid"
    const displayStatus = (status === "zero" || status === "pending") ? "unpaid" : status;
    const [bg, fg, label] = STATUS_BADGE[displayStatus] || ["#f5f5f5", "#757575", displayStatus];
    return `<span style="background:${bg};color:${fg};padding:2px 10px;border-radius:12px;font-size:0.72rem;font-weight:600;">${label}</span>`;
  }

  const state = { assessmentId: null, members: [], departmentsCache: [], deptFilter: null };

  // Members of the active department filter who must be notified
  // (outstanding balance > 0).
  function membersNeedingNotify() {
    const members = state.deptFilter
      ? state.members.filter((m) => m.department === state.deptFilter)
      : state.members;
    return members.filter((m) => m.outstanding > 0);
  }

  window.loadDeductionCompliance = async function loadDeductionCompliance() {
    try {
      const q = state.assessmentId ? `?assessment_id=${state.assessmentId}` : "";
      const resp = await fetch("/api/auditor/deductions/heatmap/" + q);
      const data = await resp.json();
      if (!data.ok) { toast(data.error || "Failed to load compliance data.", true); return; }

      state.assessmentId = data.assessment ? data.assessment.assessment_id : null;
      state.members = data.members || [];
      state.departmentsCache = data.departments || [];
      state.notifyAllowed = data.notify_allowed !== false;
      state.notice = data.notice || "";
      const notifyBtn = document.getElementById("mdhm-notify-btn");
      if (notifyBtn) {
        notifyBtn.style.display = state.notifyAllowed ? "inline-flex" : "none";
      }
      const selectAllWrap = document.querySelector("#mdhm-members-table")
        ?.closest(".dashboard-panel")
        ?.querySelector("label input[onchange='mdhmToggleAll(this.checked)']");
      if (selectAllWrap) {
        selectAllWrap.parentElement.style.display = state.notifyAllowed ? "inline-flex" : "none";
      }

      state.assessmentsCache = data.assessments || [];
      mdhmBindPicker();

      const t = data.totals || {};
const summary = document.getElementById("mdhm-summary");
      if (summary) {
        const stat = (label, value, color) => `
          <div style="min-width:92px;">
            <div style="font-size:0.62rem; font-weight:700; letter-spacing:0.6px; text-transform:uppercase; color:#8a949e;">${label}</div>
            <div style="font-size:1.05rem; font-weight:800; color:${color || "#101828"}; font-variant-numeric:tabular-nums; margin-top:2px;">${value}</div>
          </div>`;
        const divider = `<div style="width:1px; align-self:stretch; background:#e6ebe7;"></div>`;
        summary.innerHTML = `
          <div class="dashboard-panel" style="margin-bottom:20px; padding:14px 18px; display:flex; gap:16px; align-items:center; flex-wrap:wrap;">
            ${stat("Expected", PESO(t.expected))}
            ${divider}
            ${stat("Collected", PESO(t.collected), "#2e7d32")}
            ${divider}
            ${stat("Outstanding", PESO(t.outstanding), t.outstanding > 0 ? "#c62828" : "#2e7d32")}
            ${divider}
            ${stat("Paid", t.full || 0, "#2e7d32")}
            ${stat("Partial", t.partial || 0, "#b45309")}
            ${stat("Unpaid", (t.zero || 0) + (t.pending || 0), "#c62828")}
          </div>`;
      }

      const bars = document.getElementById("mdhm-departments");
      if (bars) {
        bars.innerHTML = (data.departments || []).map((d, idx) => {
          const color = rateColor(d.rate);
          const toNotify = state.members.filter((m) => m.department === d.department && m.outstanding > 0).length;
          const active = state.deptFilter === d.department;
          const border = active ? "2px solid #2e7d32" : "1px solid #e6ebe7";
          return `<div role="button" tabindex="0" aria-pressed="${active}"
              onclick="mdhmFilterDept(${idx})"
              onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();mdhmFilterDept(${idx});}"
              onmouseover="this.style.boxShadow='0 2px 10px rgba(16,24,40,0.10)';"
              onmouseout="this.style.boxShadow='none';"
              title="${active ? "Click again to show all departments" : "Click to list the members who need to be notified"}"
              style="border:${border}; background:${active ? "#f1f8f1" : "#ffffff"}; border-radius:10px; padding:10px 12px; margin-bottom:8px; cursor:pointer; outline:none; transition:box-shadow .15s ease;">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:7px;">
              <span style="flex:1; min-width:0; font-weight:700; font-size:0.88rem; color:#111827; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${esc(d.department)}</span>
              ${toNotify > 0
                ? `<span style="background:#ffebee; color:#c62828; padding:2px 9px; border-radius:999px; font-size:0.68rem; font-weight:700; white-space:nowrap;">${toNotify} to notify</span>`
                : `<span style="background:#e8f5e9; color:#2e7d32; padding:2px 9px; border-radius:999px; font-size:0.68rem; font-weight:700; white-space:nowrap;">100% Collected</span>`}
              <span style="min-width:54px; text-align:right; color:${color}; font-weight:800; font-size:0.92rem; font-variant-numeric:tabular-nums;">${d.rate.toFixed(1)}%</span>
            </div>
            <div style="background:#eef1ee; border-radius:99px; height:8px; overflow:hidden;">
              <div style="width:${Math.min(100, d.rate)}%; height:100%; background:${color}; border-radius:99px;"></div>
            </div>
            <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:7px; font-size:0.72rem; color:#8a949e;">
              <span>${d.members} member(s)</span>
              <span>Paid <strong style="color:#2e7d32;">${d.full}</strong></span>
              <span>Partial <strong style="color:#b45309;">${d.partial}</strong></span>
              <span>Unpaid <strong style="color:#c62828;">${(d.zero || 0) + (d.pending || 0)}</strong></span>
              <span>Outstanding <strong style="color:${d.outstanding > 0 ? "#c62828" : "#2e7d32"};">${PESO(d.outstanding)}</strong></span>
            </div>
          </div>`;
        }).join("") || '<p style="color:#757575; padding:8px 0;">No deductions yet.</p>';
      }

      renderMembersTable();
      // Verification rollup: strip + per-department table
      const strip = document.getElementById("mdhm-verify-strip");
      if (strip) {
        strip.innerHTML = `
          <span><strong style="color:#f9a825;">${t.v_pending || 0}</strong> Pending Verification</span>
          <span><strong style="color:#1565c0;">${t.v_verified || 0}</strong> Verified (with President)</span>
          <span><strong style="color:#2e7d32;">${t.v_approved || 0}</strong> Approved</span>
          <span><strong style="color:#c62828;">${t.v_none || 0}</strong> Unpaid</span>`;
      }
      const vbody = document.getElementById("mdhm-verify-body");
      if (vbody) {
        vbody.innerHTML = (data.departments || []).map((d) => `
          <tr>
            <td style="padding:5px 8px; font-weight:600;">${esc(d.department)}</td>
            <td style="padding:5px 8px;">${d.members}</td>
            <td style="padding:5px 8px; color:#f9a825; font-weight:600;">${d.v_pending || 0}</td>
            <td style="padding:5px 8px; color:#1565c0; font-weight:600;">${d.v_verified || 0}</td>
            <td style="padding:5px 8px; color:#2e7d32; font-weight:600;">${d.v_approved || 0}</td>
            <td style="padding:5px 8px; color:#757575;">${d.v_none || 0}</td>
          </tr>`).join("") || '<tr><td colspan="6" style="text-align:center; color:#757575; padding:16px;">No departments yet.</td></tr>';
      }

      mdhmUpdateNotify();
    } catch (e) {
      console.error("Failed to load deduction compliance", e);
      toast("Failed to load compliance data.", true);
    }
  };

  /* ---------- member table (optionally filtered to one department) ---------- */
  let mdhmPage = 1;
  const MDHM_PAGE_SIZE = 10;
  window.__mdhmGoPage = function (p) { mdhmPage = p; renderMembersTable(); };
  function renderMembersTable() {
    const tbody = document.getElementById("mdhm-members-body");
    if (!tbody) return;
    if (!state.notifyAllowed) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:#757575; padding:16px;">' + esc(state.notice) + '</td></tr>';
      mdhmUpdateNotify();
      return;
    }
    let members = state.members;
    if (state.deptFilter) members = members.filter((m) => m.department === state.deptFilter);
    const emptyMessage = state.deptFilter
      ? `No members recorded for ${esc(state.deptFilter)} this month.`
      : "No members yet.";
    const pager = document.getElementById("mdhm-members-pagination");
    if (!members.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:#757575; padding:16px;">${emptyMessage}</td></tr>`;
      if (pager) pager.innerHTML = "";
      renderDeptFilterBanner();
      mdhmUpdateNotify();
      return;
    }
    const pageCount = Math.max(1, Math.ceil(members.length / MDHM_PAGE_SIZE));
    mdhmPage = Math.min(Math.max(mdhmPage, 1), pageCount);
    const pageMembers = members.slice((mdhmPage - 1) * MDHM_PAGE_SIZE, mdhmPage * MDHM_PAGE_SIZE);
    tbody.innerHTML = pageMembers.map((m) => `<tr data-member-id="${m.member_id}" data-outstanding="${m.outstanding}" ${m.outstanding > 0 ? 'style="background:#fff8f8;"' : ""}>
        <td style="padding:5px 8px; text-align:center;">${m.outstanding > 0 ? '<input type="checkbox" class="mdhm-check" onchange="mdhmUpdateNotify()" />' : "—"}</td>
        <td style="padding:5px 8px;">${esc(m.member_name)}</td>
        <td style="padding:5px 8px;">${esc(m.department)}</td>
        <td style="padding:5px 8px;">${statusBadge(m.status)}</td>
        <td style="padding:5px 8px; text-align:right;">${PESO(m.actual)}</td>
        <td style="padding:5px 8px; text-align:right; ${m.outstanding > 0 ? "color:#c62828; font-weight:600;" : ""}">${PESO(m.outstanding)}</td>
      </tr>`).join("");
    if (pager && typeof UniPager !== "undefined") {
      pager.innerHTML = UniPager.html(mdhmPage, pageCount, "window.__mdhmGoPage(PAGE)", UniPager.count(mdhmPage, MDHM_PAGE_SIZE, members.length));
    }
    // A department click pre-selects everyone who needs the notification —
    // the Auditor only has to press "Send Dues Reminder".
    if (state.deptFilter) {
      document.querySelectorAll("#mdhm-members-body .mdhm-check").forEach((cb) => { cb.checked = true; });
    }
    renderDeptFilterBanner();
    mdhmUpdateNotify();
    if (state.scrollPending) {
      state.scrollPending = false;
      const table = document.getElementById("mdhm-members-table");
      if (table) table.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  /* ---------- department click → list members who need to be notified ---------- */
  window.mdhmFilterDept = function mdhmFilterDept(idx) {
    const dept = (state.departmentsCache || [])[idx];
    const name = dept && dept.department;
    if (!name) return;
    state.deptFilter = state.deptFilter === name ? null : name;
    state.scrollPending = Boolean(state.deptFilter);
    mdhmPage = 1;
    loadDeductionCompliance();
  };

  window.mdhmClearDeptFilter = function mdhmClearDeptFilter() {
    state.deptFilter = null;
    state.scrollPending = false;
    mdhmPage = 1;
    loadDeductionCompliance();
  };

  function renderDeptFilterBanner() {
    const wrap = document.getElementById("mdhm-dept-filter");
    if (!wrap) return;
    if (!state.deptFilter || !state.notifyAllowed) { wrap.innerHTML = ""; return; }
    const need = membersNeedingNotify();
    const total = need.reduce((s, m) => s + (Number(m.outstanding) || 0), 0);
    if (!need.length) {
      wrap.innerHTML = `
        <div style="background:#e8f5e9; border:1px solid #a5d6a7; border-left:4px solid #2e7d32; border-radius:8px; padding:8px 12px; margin-bottom:10px; font-size:0.83rem; color:#1b5e20; display:flex; align-items:center; gap:10px;">
          <i class="fa-solid fa-circle-check"></i>
          <span><strong>${esc(state.deptFilter)}</strong> — every member is fully paid. No one needs to be notified.</span>
          <button type="button" class="btn-outline" style="margin-left:auto; padding:2px 12px; font-size:0.78rem;" onclick="mdhmClearDeptFilter()">Clear</button>
        </div>`;
      return;
    }
    wrap.innerHTML = `
      <div style="background:#fff8e1; border:1px solid #ffe082; border-left:4px solid #b45309; border-radius:8px; padding:8px 12px; margin-bottom:10px; font-size:0.83rem; color:#7a5b00; display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
        <i class="fa-solid fa-bullhorn"></i>
        <span><strong>${esc(state.deptFilter)}</strong> — <strong>${need.length}</strong> member(s) need to be notified · outstanding <strong>${PESO(total)}</strong>. They are pre-selected below — press <strong>Send Dues Reminder</strong> to send reminders.</span>
        <button type="button" class="btn-outline" style="margin-left:auto; padding:2px 12px; font-size:0.78rem;" onclick="mdhmClearDeptFilter()">Clear filter</button>
      </div>`;
  }

  /* ---------- month-year popup picker (replaces the long month dropdown) ---------- */
  function mdhmBindPicker() {
    const btn = document.getElementById("mdhm-assessment-btn");
    const label = document.getElementById("mdhm-assessment-label");
    const pop = document.getElementById("mdhm-assessment-pop");
    const grid = document.getElementById("mdhm-month-grid");
    const yearLabel = document.getElementById("mdhm-year-label");
    const prev = document.getElementById("mdhm-year-prev");
    const next = document.getElementById("mdhm-year-next");
    if (!btn || !label || !pop || !grid || !yearLabel || !prev || !next) return;
    const list = state.assessmentsCache || [];
    const cur = state.assessmentId != null ? list.find((a) => String(a.assessment_id) === String(state.assessmentId)) : null;
    label.textContent = cur ? cur.month_label : (list.length ? "Select month" : "No months yet");
    btn.disabled = !list.length;
    const keyOf = (x) => String(x.month || "").slice(0, 7);
    const yearOf = (x) => String(x.month || "").slice(0, 4);
    const years = [...new Set(list.map(yearOf).filter((y) => /^\d{4}$/.test(y)))].sort();
    let year = (cur && /^\d{4}$/.test(yearOf(cur)) && years.includes(yearOf(cur)))
      ? yearOf(cur)
      : (years[years.length - 1] || String(new Date().getFullYear()));
    const ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const close = () => { pop.style.display = "none"; document.removeEventListener("click", outside); };
    const outside = (e) => { if (!pop.contains(e.target) && !btn.contains(e.target)) close(); };
    const paint = () => {
      yearLabel.textContent = year;
      prev.disabled = !years.length || year <= years[0];
      next.disabled = !years.length || year >= years[years.length - 1];
      grid.innerHTML = ABBR.map((m, i) => {
        const hit = list.find((x) => keyOf(x) === `${year}-${String(i + 1).padStart(2, "0")}`);
        if (!hit) return `<button type="button" class="mdhm-mbtn" disabled>${m}</button>`;
        const cls = String(hit.assessment_id) === String(state.assessmentId) ? " current" : "";
        return `<button type="button" class="mdhm-mbtn${cls}" data-aid="${hit.assessment_id}">${m}</button>`;
      }).join("");
      grid.querySelectorAll("[data-aid]").forEach((b) =>
        b.addEventListener("click", () => { close(); mdhmSelectAssessment(b.dataset.aid); })
      );
    };
    btn.onclick = (e) => {
      e.stopPropagation();
      if (!list.length) return;
      if (pop.style.display === "none") { paint(); pop.style.display = "block"; document.addEventListener("click", outside); }
      else close();
    };
    prev.onclick = (e) => { e.stopPropagation(); const i = years.indexOf(year); if (i > 0) { year = years[i - 1]; paint(); } };
    next.onclick = (e) => { e.stopPropagation(); const i = years.indexOf(year); if (i >= 0 && i < years.length - 1) { year = years[i + 1]; paint(); } };
    if (!window.__mdhmPickerEsc) {
      window.__mdhmPickerEsc = true;
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") { const p = document.getElementById("mdhm-assessment-pop"); if (p) p.style.display = "none"; }
      });
    }
  }

  window.mdhmSelectAssessment = function mdhmSelectAssessment(id) {
    state.assessmentId = id || null;
    state.deptFilter = null;
    loadDeductionCompliance();
  };

  window.mdhmAssessmentChanged = function mdhmAssessmentChanged(select) {
    mdhmSelectAssessment(select ? select.value : null);
  };

  window.mdhmToggleAll = function mdhmToggleAll(master) {
    document.querySelectorAll("#mdhm-members-body .mdhm-check").forEach((cb) => { cb.checked = master; });
    mdhmUpdateNotify();
  };

  window.mdhmUpdateNotify = function mdhmUpdateNotify() {
    let count = 0, outstanding = 0;
    document.querySelectorAll("#mdhm-members-body tr").forEach((row) => {
      const cb = row.querySelector(".mdhm-check");
      if (!cb || !cb.checked) return;
      count += 1;
      outstanding += Number(row.dataset.outstanding) || 0;
    });
    if (document.getElementById("mdhm-selected-count")) document.getElementById("mdhm-selected-count").textContent = count;
    if (document.getElementById("mdhm-selected-outstanding")) document.getElementById("mdhm-selected-outstanding").textContent = PESO(outstanding);
    const btn = document.getElementById("mdhm-notify-btn");
    if (btn) btn.disabled = count === 0;
  };

  window.mdhmOpenNotify = function mdhmOpenNotify() {
    if (!window.SimpleModal) { toast("Modal unavailable.", true); return; }
    if (state.notifyAllowed === false) {
      toast(state.notice || "Not available yet.", true);
      return;
    }
    const selected = [];
    document.querySelectorAll("#mdhm-members-body tr").forEach((row) => {
      const cb = row.querySelector(".mdhm-check");
      if (cb && cb.checked && Number(row.dataset.outstanding) > 0) {
        selected.push({ id: Number(row.dataset.memberId), outstanding: Number(row.dataset.outstanding) });
      }
    });
    const zeroSelected = document.querySelectorAll("#mdhm-members-body .mdhm-check:checked").length - selected.length;

    const listHtml = selected.map((s) => {
      const m = state.members.find((x) => x.member_id === s.id);
      return `<li style="margin-bottom:2px;">${esc(m ? m.member_name : "#" + s.id)} — ${PESO(s.outstanding)} outstanding</li>`;
    }).join("");

    const layer = window.SimpleModal.open({
      title: "Send Dues Reminder Members",
      width: "560px",
      html: `
        <p style="font-size:0.85rem; color:#333; margin:0 0 8px;">Sending to <strong>${selected.length}</strong> member(s) with outstanding balances${zeroSelected ? ` — ${zeroSelected} selected member(s) with nothing outstanding will be skipped` : ""}:</p>
        <ul style="font-size:0.82rem; color:#555; margin:0 0 14px; padding-left:18px; max-height:140px; overflow-y:auto;">${listHtml}</ul>
        <div style="margin-bottom:8px; font-size:0.88rem;">
          <label style="display:block; margin-bottom:4px;"><input type="radio" name="mdhm-type" value="reminder" checked /> Reminder (standard)</label>
          <label style="display:block; margin-bottom:4px;"><input type="radio" name="mdhm-type" value="urgent" /> Urgent (escalation)</label>
          <label style="display:block;"><input type="radio" name="mdhm-type" value="custom" /> Custom message</label>
        </div>
        <textarea id="mdhm-custom-message" class="form-control" rows="3" placeholder="Custom message (used only when Custom is chosen)" style="width:100%; margin-bottom:14px;"></textarea>
        <div style="display:flex; gap:10px; justify-content:flex-end;">
          <button type="button" class="btn-outline" style="padding:6px 16px;" onclick="SimpleModal.close()">Cancel</button>
          <button type="button" class="btn-brand btn-brand-primary" style="padding:6px 16px;" onclick="mdhmSend(this)">Send to ${selected.length} Member(s)</button>
        </div>`,
    });

    window.mdhmSend = async function mdhmSend(btn) {
      const type = (layer.el.querySelector('input[name="mdhm-type"]:checked') || {}).value || "reminder";
      const customMessage = (layer.el.querySelector("#mdhm-custom-message") || {}).value || "";
      btn.disabled = true;
      btn.textContent = "Sending…";
      try {
        const resp = await fetch("/api/auditor/deductions/notify/", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrfToken() },
          body: JSON.stringify({
            assessment_id: state.assessmentId,
            member_ids: selected.map((s) => s.id),
            notify_type: type,
            custom_message: customMessage,
          }),
        });
        const data = await resp.json();
        if (!data.ok) { toast(data.error || "Failed to send notifications.", true); btn.disabled = false; btn.textContent = "Send"; return; }
        const rows = (data.results || []).map((r) =>
          `<tr>
            <td style="border:1px solid #ddd; padding:5px 10px;">${esc(r.member_name)}</td>
            <td style="border:1px solid #ddd; padding:5px 10px; text-align:right;">${PESO(r.outstanding)}</td>
            <td style="border:1px solid #ddd; padding:5px 10px; text-align:center;">${r.email_sent ? "✅ Sent" : "— no email"}</td>
          </tr>`).join("");
        layer.el.innerHTML = `
          <p style="font-size:0.9rem; margin:0 0 10px;">✅ <strong>${data.sent}</strong> notification(s) sent — total outstanding ${PESO(data.total_outstanding)}${data.skipped ? `, ${data.skipped} skipped (nothing outstanding)` : ""}.</p>
          <table style="width:100%; border-collapse:collapse; font-size:0.82rem; margin-bottom:12px;">
            <thead><tr><th style="border:1px solid #ddd; background:#f5f5f5; padding:5px 10px; text-align:left;">Member</th><th style="border:1px solid #ddd; background:#f5f5f5; padding:5px 10px; text-align:right;">Outstanding</th><th style="border:1px solid #ddd; background:#f5f5f5; padding:5px 10px;">Email</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
          <div style="text-align:right;"><button type="button" class="btn-brand btn-brand-primary" style="padding:6px 16px;" onclick="SimpleModal.close()">OK</button></div>`;
        loadDeductionCompliance();
      } catch (e) {
        console.error("Failed to send notifications", e);
        toast("Failed to send notifications.", true);
        btn.disabled = false;
        btn.textContent = "Send";
      }
    };
  };

  document.addEventListener("DOMContentLoaded", loadDeductionCompliance);
})();
