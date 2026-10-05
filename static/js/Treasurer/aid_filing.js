// aid_filing.js — NEW step-based aid filing UI (File Medical Aid / File Death Aid).
// Replaces the old filing forms' workflow: member → details → required uploads
// (request letter + hospital bill(s) for medical; none for death) → validation →
// submit to Auditor. Uses the existing backend endpoints.
(function () {
  "use strict";

  /* Pagination state for the "recent" tables (UniPager). */
  let afmHistoryPage = 1;
  let afdHistoryPage = 1;
  window.__afmHistoryGoPage = function (p) { afmHistoryPage = p; loadMedical(); };
  window.__afdHistoryGoPage = function (p) { afdHistoryPage = p; loadDeath(); };

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function peso(n) {
    const num = Number(n || 0);
    return new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" }).format(num);
  }

  async function getJSON(url) {
    try {
      const res = await fetch(url, { credentials: "same-origin" });
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  const DEATH_BENEFITS = { member: 500, spouse: 300, parent: 250, child: 250, sibling: 100 };
  const DEATH_LABELS = {
    member: "Member (the CAUFA member themselves)",
    spouse: "Spouse of member",
    parent: "Parent of member",
    child: "Child of member",
    sibling: "Brother/Sister (Full Blood)",
  };

  function threshold() {
    const el = document.getElementById("afm_config");
    return el ? parseFloat(el.getAttribute("data-threshold") || "20000") : 20000;
  }
  function medBenefit() {
    const el = document.getElementById("afm_config");
    return el ? parseFloat(el.getAttribute("data-benefit") || "100") : 100;
  }

  let membersCache = null;
  let membersPromise = null;
  let membersError = "";
  async function loadMembers(force) {
    if (membersCache && !force) return membersCache;
    // Share one in-flight request so the medical + death pickers opening
    // together only hit the API once.
    if (membersPromise) return membersPromise;
    membersPromise = (async () => {
      const data = await getJSON("/api/treasurer/members/list/");
      if (!data || !Array.isArray(data.members)) {
        // Do NOT cache failures — a session hiccup used to poison the
        // picker ("No members found") until a full page reload.
        membersError = "Could not load members. Check your connection/session, then Retry.";
        return membersCache || [];
      }
      const all = data.members || [];
      // Management policy: retired members cannot file medical/death aid
      // claims, so they are excluded from the filing member picker.
      membersCache = all.filter(
        (m) =>
          String(m.membership_status || "").toLowerCase() !== "retired" &&
          String(m.classification || "").toLowerCase() !== "retired"
      );
      membersError = "";
      return membersCache;
    })();
    try {
      return await membersPromise;
    } finally {
      membersPromise = null;
    }
  }

  function allFilingMembers() {
    return membersCache || [];
  }

  function toast(msg, isErr) {
    if (typeof window.showToast === "function") window.showToast(msg, !!isErr);
    else if (isErr) alert(msg);
  }

  /* ================= MEDICAL AID ================= */

  const med = { member: null, patient: "", diagnosis: "", notes: "" };

  function initialsOf(name) {
    return String(name || "")
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0].toUpperCase())
      .join("") || "?";
  }

  function memberCardHTML(m, clearFn) {
    const name = m.full_name || m.name || "";
    const meta = [m.department || "", m.position || m.rank || ""].filter(Boolean).join(" · ");
    return `
      <div style="display:flex;align-items:center;gap:12px;padding:12px;border:1px solid #dfe9df;border-radius:12px;background:#f6faf6;">
        <div style="width:44px;height:44px;border-radius:50%;background:#1b5e20;color:#fff;font-weight:700;font-size:0.95rem;display:flex;align-items:center;justify-content:center;flex:none;">${esc(initialsOf(name))}</div>
        <div style="flex:1;min-width:0;">
          <div style="font-weight:700;color:#1b5e20;font-size:0.9rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(name)}</div>
          ${meta ? `<div style="font-size:0.72rem;color:#757575;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(meta)}</div>` : ""}
        </div>
        <button type="button" class="pd-link-btn" style="color:#c62828;flex:none;" onclick="${clearFn}">Change</button>
      </div>`;
  }

  function emptyMemberBox() {
    return '<div style="display:flex;align-items:center;justify-content:center;padding:18px 12px;border:1px dashed #cfdccc;border-radius:12px;color:#9aa59a;font-size:0.78rem;text-align:center;">No member selected yet — open the dropdown above to select.</div>';
  }

  /* ============ MEMBER PICKER (dropdown: search header + A–Z filter
     + scrollable paged list). Shared by Medical and Death Aid. ============ */

  function ensurePickerCSS() {
    if (document.getElementById("mpicker-style")) return;
    const st = document.createElement("style");
    st.id = "mpicker-style";
    st.textContent = [
      ".mpicker-trigger{width:100%;display:flex;align-items:center;justify-content:space-between;gap:8px;",
      "padding:9px 12px;border:1px solid #cfdccc;border-radius:8px;background:#fff;font-size:0.85rem;",
      "color:#212121;cursor:pointer;text-align:left;}",
      ".mpicker-trigger:hover{border-color:#1b5e20;}",
      ".mpicker-trigger-text{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}",
      ".mpicker-trigger-text.is-placeholder{color:#9aa59a;}",
      ".mpicker-caret{color:#1b5e20;font-size:0.8rem;flex:none;}",
      ".mpicker-panel{position:absolute;top:100%;left:0;right:0;z-index:999;background:#fff;",
      "border:1px solid #cfdccc;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,0.12);",
      "margin-top:4px;overflow:hidden;}",
      ".mpicker-head{padding:8px;border-bottom:1px solid #eef4ee;background:#f6faf6;}",
      ".mpicker-head input{width:100%;padding:8px 10px;border:1px solid #cfdccc;border-radius:8px;font-size:0.82rem;}",
      ".mpicker-head input:focus{outline:none;border-color:#1b5e20;}",
      ".mpicker-alpha{display:flex;flex-wrap:wrap;gap:4px;padding:8px;border-bottom:1px solid #eef4ee;",
      "max-height:76px;overflow-y:auto;background:#fff;}",
      ".mpicker-chip{border:1px solid #cfdccc;background:#fff;border-radius:20px;min-width:28px;height:24px;",
      "padding:0 8px;font-size:0.7rem;font-weight:700;color:#546e7a;cursor:pointer;line-height:22px;text-align:center;}",
      ".mpicker-chip:hover{border-color:#1b5e20;color:#1b5e20;}",
      ".mpicker-chip.active{background:#1b5e20;border-color:#1b5e20;color:#fff;}",
      ".mpicker-list{max-height:240px;overflow-y:auto;}",
      ".mpicker-row{padding:8px 12px;border-bottom:1px solid #f0f0f0;font-size:0.82rem;cursor:pointer;}",
      ".mpicker-row:hover{background:#f5f5f5;}",
      ".mpicker-empty{padding:14px 12px;color:#999;font-size:0.8rem;text-align:center;}",
      ".mpicker-retry{margin-top:8px;padding:6px 14px;border:1px solid #1b5e20;border-radius:8px;background:#fff;",
      "color:#1b5e20;font-size:0.78rem;font-weight:700;cursor:pointer;}",
      ".mpicker-foot{display:flex;align-items:center;justify-content:space-between;gap:8px;",
      "padding:7px 10px;border-top:1px solid #eef4ee;background:#f6faf6;font-size:0.72rem;color:#546e7a;}",
      ".mpicker-pagebtn{border:1px solid #cfdccc;background:#fff;border-radius:6px;padding:3px 10px;",
      "font-size:0.72rem;font-weight:700;color:#1b5e20;cursor:pointer;}",
      ".mpicker-pagebtn:disabled{opacity:0.4;cursor:default;}",
    ].join("\n");
    document.head.appendChild(st);
  }

  const NAME_SUFFIXES = { JR: 1, SR: 1, II: 1, III: 1, IV: 1, V: 1, VI: 1 };
  const NAME_CREDENTIALS = { MAED: 1, EDD: 1, PHD: 1, MBA: 1, CPA: 1, RN: 1, LPT: 1, DPA: 1, LLB: 1 };

  function credentialLike(raw) {
    const tok = String(raw || "").toUpperCase().replace(/[.,]/g, "");
    if (NAME_CREDENTIALS[tok]) return true;
    // Mixed-case leftovers such as "MAEd" (dataset names are ALL CAPS,
    // so mixed case almost always means a credential, not a surname).
    const t = String(raw || "").replace(/\./g, "");
    return /[a-z]/.test(t) && /[A-Z]/.test(t);
  }

  // Last-name initial of "FIRST M LAST [suffix][, credential]" names. Only
  // letters that actually exist in the dataset become filter chips
  // (e.g. ALL, M, R, V).
  function lastNameInitial(fullName) {
    const parts = String(fullName || "").trim().split(/\s+/).filter(Boolean);
    // 1) Drop trailing credentials: "MATEO JR., MAEd" / "CRUZ, PhD".
    while (parts.length > 1 && credentialLike(parts[parts.length - 1])) parts.pop();
    // 2) Drop suffixes; a trailing comma belongs to the separator
    // ("CRUZ," -> surname CRUZ), so de-comma it and stop.
    while (parts.length > 1) {
      const raw = parts[parts.length - 1];
      const tok = String(raw).toUpperCase().replace(/[.,]/g, "");
      if (NAME_SUFFIXES[tok]) { parts.pop(); continue; }
      if (/,/.test(raw)) {
        parts[parts.length - 1] = String(raw).replace(/,+$/g, "");
      }
      break;
    }
    const last = parts.length ? parts[parts.length - 1] : "";
    const ch = (last.charAt(0) || "").toUpperCase();
    return ch >= "A" && ch <= "Z" ? ch : "#";
  }

  function memberSearchText(m) {
    return (
      String(m.full_name || m.name || "") + " " + String(m.employee_id || "")
    ).toLowerCase();
  }

  function createMemberPicker(cfg) {
    const picker = {
      cfg: cfg,
      open: false,
      q: "",
      alpha: "ALL",
      page: 1,
      perPage: 12,
      loading: false,
    };

    function els() {
      return {
        trigger: document.getElementById(cfg.triggerId),
        panel: document.getElementById(cfg.panelId),
        search: document.getElementById(cfg.searchId),
        alpha: document.getElementById(cfg.alphaId),
        list: document.getElementById(cfg.listId),
        pager: document.getElementById(cfg.pagerId),
      };
    }

    function availableLetters() {
      const set = {};
      allFilingMembers().forEach((m) => { set[lastNameInitial(m.full_name || m.name || "")] = 1; });
      return Object.keys(set).sort();
    }

    function filtered() {
      const q = picker.q.trim().toLowerCase();
      return allFilingMembers().filter((m) => {
        if (picker.alpha !== "ALL" && lastNameInitial(m.full_name || m.name || "") !== picker.alpha) return false;
        if (q && memberSearchText(m).indexOf(q) === -1) return false;
        return true;
      });
    }

    function renderAlpha() {
      const box = els().alpha;
      if (!box) return;
      const letters = availableLetters();
      if (picker.alpha !== "ALL" && letters.indexOf(picker.alpha) === -1) picker.alpha = "ALL";
      let html = `<button type="button" class="mpicker-chip${picker.alpha === "ALL" ? " active" : ""}" data-alpha="ALL">ALL</button>`;
      html += letters.map((L) => `<button type="button" class="mpicker-chip${picker.alpha === L ? " active" : ""}" data-alpha="${L}">${L}</button>`).join("");
      box.innerHTML = html;
      box.querySelectorAll(".mpicker-chip").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          picker.alpha = btn.getAttribute("data-alpha") || "ALL";
          picker.page = 1;
          render();
        });
      });
    }

    function renderList(rows, pageCount) {
      const box = els().list;
      if (!box) return;
      if (picker.loading) {
        box.innerHTML = '<div class="mpicker-empty">Loading members…</div>';
        return;
      }
      if (membersError && !allFilingMembers().length) {
        box.innerHTML = `<div class="mpicker-empty">${esc(membersError)}<br><button type="button" class="mpicker-retry" data-retry="1">Retry</button></div>`;
        const rb = box.querySelector("[data-retry]");
        if (rb) rb.addEventListener("click", async (e) => {
          e.stopPropagation();
          picker.loading = true;
          render();
          await loadMembers(true);
          picker.loading = false;
          cfg.onData && cfg.onData();
          render();
        });
        return;
      }
      if (!rows.length) {
        box.innerHTML = '<div class="mpicker-empty">No members found — try another search or letter.</div>';
        return;
      }
      box.innerHTML = rows
        .map((m) => {
          const id = m.member_id_PK || m.member_id || m.id || 0;
          const nm = m.full_name || m.name || "";
          const meta = [m.employee_id || "", m.department || ""].filter(Boolean).join(" · ");
          return `<div class="mpicker-row" role="option" data-mid="${esc(id)}"><b>${esc(nm)}</b>${meta ? ` <span style="color:#757575;">· ${esc(meta)}</span>` : ""}</div>`;
        })
        .join("");
      box.querySelectorAll(".mpicker-row").forEach((row) => {
        row.addEventListener("click", (e) => {
          e.stopPropagation();
          cfg.onPick(row.getAttribute("data-mid"));
        });
      });
    }

    function renderPager(total, pageCount) {
      const box = els().pager;
      if (!box) return;
      if (!total) { box.innerHTML = ""; return; }
      const start = (picker.page - 1) * picker.perPage + 1;
      const end = Math.min(total, picker.page * picker.perPage);
      box.innerHTML = (
        `<button type="button" class="mpicker-pagebtn" data-pg="prev"${picker.page <= 1 ? " disabled" : ""}>‹ Prev</button>` +
        `<span>Showing ${start}–${end} of ${total}</span>` +
        `<button type="button" class="mpicker-pagebtn" data-pg="next"${picker.page >= pageCount ? " disabled" : ""}>Next ›</button>`
      );
      box.querySelectorAll(".mpicker-pagebtn").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          if (btn.getAttribute("data-pg") === "prev" && picker.page > 1) picker.page -= 1;
          if (btn.getAttribute("data-pg") === "next" && picker.page < pageCount) picker.page += 1;
          render();
        });
      });
    }

    function render() {
      const r = els();
      if (!r.panel) return;
      renderAlpha();
      const all = filtered();
      const pageCount = Math.max(1, Math.ceil(all.length / picker.perPage));
      picker.page = Math.min(Math.max(picker.page, 1), pageCount);
      const rows = all.slice((picker.page - 1) * picker.perPage, picker.page * picker.perPage);
      renderList(rows, pageCount);
      renderPager(all.length, pageCount);
    }

    async function open() {
      const r = els();
      if (!r.panel) return;
      ensurePickerCSS();
      picker.open = true;
      r.panel.style.display = "block";
      if (r.trigger) r.trigger.setAttribute("aria-expanded", "true");
      // (Re)load every time it opens so the list is never stale/empty.
      if (!allFilingMembers().length || membersError) {
        picker.loading = true;
        render();
        await loadMembers();
        picker.loading = false;
        cfg.onData && cfg.onData();
      }
      render();
      if (r.search) {
        // Keep the header search box in sync, then focus it for typing.
        if (r.search.value !== picker.q) r.search.value = picker.q;
        setTimeout(() => { try { r.search.focus(); } catch (e) {} }, 30);
      }
    }

    function close() {
      const r = els();
      if (!r.panel) return;
      picker.open = false;
      r.panel.style.display = "none";
      if (r.trigger) r.trigger.setAttribute("aria-expanded", "false");
    }

    picker.els = els;
    picker.render = render;
    picker.openPanel = open;
    picker.closePanel = close;
    picker.setQuery = function (q) {
      picker.q = q || "";
      picker.page = 1;
      if (!picker.open) open();
      else render();
    };
    picker.reset = function () {
      picker.q = "";
      picker.alpha = "ALL";
      picker.page = 1;
      const r = els();
      if (r.search) r.search.value = "";
      close();
      renderTrigger();
    };
    function renderTrigger() {
      const r = els();
      const sel = cfg.getSelected();
      if (!r.trigger) return;
      const label = r.trigger.querySelector(".mpicker-trigger-text");
      if (!label) return;
      if (sel) {
        label.textContent = sel.full_name || sel.name || "Selected member";
        label.classList.remove("is-placeholder");
      } else {
        label.textContent = "Select member…";
        label.classList.add("is-placeholder");
      }
    }
    picker.renderTrigger = renderTrigger;

    // Wire static controls once.
    if (!cfg._wired) {
      cfg._wired = true;
      document.addEventListener("click", (e) => {
        const t = document.getElementById(cfg.triggerId);
        const p = document.getElementById(cfg.panelId);
        if (t && (t === e.target || t.contains(e.target))) {
          e.stopPropagation();
          if (picker.open) close();
          else open();
          return;
        }
        if (p && picker.open && !p.contains(e.target)) close();
      });
      // Bind the header search box (delegated: panel HTML is static, survives re-renders).
      document.addEventListener("input", (e) => {
        if (e.target && e.target.id === cfg.searchId) {
          picker.q = e.target.value || "";
          picker.page = 1;
          render();
        }
      });
    }

    return picker;
  }

  function lockPatientField(value) {
    const el = document.getElementById("afm_patient");
    if (!el) return;
    el.value = value || "";
    el.readOnly = true;
    el.style.background = value ? "#e8f5e9" : "#f3f6f3";
    el.style.fontWeight = "600";
  }

  function renderMedMemberCard() {
    const box = document.getElementById("afm_member_card");
    if (!box) return;
    if (!med.member) {
      box.innerHTML = emptyMemberBox();
    } else {
      box.innerHTML = memberCardHTML(med.member, "window.nxAidFiling.clearMedMember()");
    }
    if (medPicker) medPicker.renderTrigger();
  }

  let medPicker = null;
  function getMedPicker() {
    if (medPicker) return medPicker;
    medPicker = createMemberPicker({
      triggerId: "afm_member_trigger",
      panelId: "afm_member_results",
      searchId: "afm_member_search",
      alphaId: "afm_member_alpha",
      listId: "afm_member_list",
      pagerId: "afm_member_pager",
      getSelected: function () { return med.member; },
      onPick: function (id) { if (window.nxAidFiling) window.nxAidFiling.pickMedMember(id); },
      onData: function () { med.members = allFilingMembers(); },
    });
    return medPicker;
  }

  // Legacy entry points (kept for compat): route into the dropdown picker.
  function renderMedResults(query) {
    getMedPicker().setQuery(query || "");
  }

  // Statuses that count against the once-a-year limit — matches
  // medical_aid_proceeded_statuses() in policy_constants.py: only claims
  // still in the pipeline or already paid. Withdrawn / rejected / denied /
  // returned claims never released a payout and allow a fresh filing.
  const MED_PROCEEDED = new Set([
    "Pending", "Pending Verification", "Pending Treasurer Check",
    "Pending Auditor Verification", "Pending Auditor Review",
    "Pending Treasurer Review", "Pending President Approval",
    "Treasurer Direct", "Auditor Verified", "Approved",
    "President Approved", "Released", "Completed",
  ]);

  function medClaimsThisYear() {
    if (!med.member) return 0;
    const id = med.member.member_id_PK || med.member.member_id || med.member.id;
    const year = new Date().getFullYear();
    const rows = (window.db && window.db.medical_aids) || [];
    return rows.filter(
      (r) =>
        String(r.memberId) === String(id) &&
        String(r.request_date || r.date || "").startsWith(String(year)) &&
        MED_PROCEEDED.has(String(r.status || "").trim())
    ).length;
  }

  function checkPill(ok, text) {
    return `
      <div style="display:flex;align-items:center;gap:9px;padding:5px 2px;">
        <input type="checkbox" ${ok ? "checked" : ""} disabled style="width:16px;height:16px;accent-color:#2e7d32;flex:none;cursor:default;">
        <span style="font-size:0.82rem;color:${ok ? "#1b5e20" : "#546e7a"};">${esc(text)}</span>
      </div>`;
  }

  function updateMedChecklist() {
    const list = document.getElementById("afm_checklist");
    if (!list) return;
    const letters = window.FileQueue ? window.FileQueue.getFiles("afm_letter") : [];
    const bills = window.FileQueue ? window.FileQueue.getFiles("afm_bills") : [];
    const billInput = document.getElementById("afm_bill");
    const billVal = parseFloat(billInput && billInput.value ? billInput.value : "0");
    const claims = med.member ? medClaimsThisYear() : null;

    const checks = [
      { ok: !!med.member, text: "Member selected" },
      {
        ok: !!med.member && claims === 0,
        text: med.member
          ? (claims === 0
              ? "No medical aid claim this year"
              : `Already claimed ${claims} time(s) this year — blocked per By-Laws`)
          : "No medical aid claim this year (select a member first)",
      },
      { ok: billVal >= threshold(), text: billVal >= threshold() ? `Hospital bill meets the ${peso(threshold())} requirement` : `Hospital bill must be at least ${peso(threshold())}` },
      { ok: letters.length > 0, text: "Request letter uploaded" },
      { ok: bills.length > 0, text: "Hospital bill(s) uploaded" },
    ];

    list.innerHTML = checks.map((c) => checkPill(c.ok, c.text)).join("");

    const eligible = checks[0].ok && checks[1].ok && checks[2].ok && checks[3].ok && checks[4].ok;
    const amountBox = document.getElementById("afm_amount");
    if (amountBox) {
      amountBox.textContent = eligible ? peso(medBenefit()) + " (per By-Laws Article XI)" : "";
    }
    // Hide the header "Amount to Request" block until everything qualifies.
    const amountWrap = document.getElementById("afm_amount_wrap");
    if (amountWrap) amountWrap.style.display = eligible ? "" : "none";
    const btn = document.getElementById("afm_submit");
    if (btn) btn.disabled = !eligible;
  }

  async function submitMedical(e) {
    e.preventDefault();
    if (!med.member) return toast("Select a member first.", true);

    const letters = window.FileQueue ? window.FileQueue.getFiles("afm_letter") : [];
    const bills = window.FileQueue ? window.FileQueue.getFiles("afm_bills") : [];
    const others = window.FileQueue ? window.FileQueue.getFiles("afm_other") : [];
    if (!letters.length) return toast("Missing required document: Request Letter (addressed to the CAUFA President).", true);
    if (!bills.length) return toast("Missing required document: Hospital Bill.", true);

    const diagnosis = (document.getElementById("afm_diagnosis") || {}).value || "";
    if (!diagnosis.trim()) return toast("Diagnosis is required.", true);

    const adm = (document.getElementById("afm_admission") || {}).value || "";
    const dis = (document.getElementById("afm_discharge") || {}).value || "";
    if (trapConfinementTo()) return;
    const hospitalDate = adm && dis ? `${adm} to ${dis}` : adm || dis || "";

    const patient = (document.getElementById("afm_patient") || {}).value || "";
    const notes = (document.getElementById("afm_notes") || {}).value || "";
    let reason = diagnosis.trim();
    if (patient.trim() && med.member && patient.trim() !== (med.member.full_name || med.member.name || "")) {
      reason += ` (Patient: ${patient.trim()})`;
    }
    if (notes.trim()) reason += ` — Notes: ${notes.trim()}`;

    const fd = new FormData();
    fd.append("med_member", String(med.member.member_id_PK || med.member.member_id || med.member.id || ""));
    fd.append("med_date", (document.getElementById("afm_date") || {}).value || new Date().toISOString().slice(0, 10));
    fd.append("med_req_amount", String(medBenefit()));
    fd.append("med_hospital", (document.getElementById("afm_hospital") || {}).value || "");
    fd.append("med_hospital_date", hospitalDate);
    fd.append("med_bill", (document.getElementById("afm_bill") || {}).value || "0");
    fd.append("med_reason", reason);
    letters.forEach((f) => fd.append("med_request_letter", f));
    bills.forEach((f) => fd.append("med_hospital_bill", f));
    others.forEach((f) => fd.append("med_photo_files", f));

    const btn = document.getElementById("afm_submit");
    if (btn) { btn.disabled = true; btn.textContent = "Submitting..."; }
    try {
      const res = await fetch("/api/treasurer/medical-aid/add/", {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": getCookie("csrftoken") },
        body: fd,
      });
      const data = await res.json().catch(() => ({}));
      if (data && data.ok) {
        toast("Medical aid request filed and submitted to the Auditor. The member has been notified by email.", false);
        resetMedical();
      } else {
        toast((data && data.error) || "Failed to submit medical aid request.", true);
      }
    } catch (err) {
      toast("Network error while submitting.", true);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "Submit to Auditor"; }
      updateMedChecklist();
    }
  }

  function resetMedical() {
    med.member = null;
    renderMedMemberCard();
    if (medPicker) medPicker.reset();
    else { const search = document.getElementById("afm_member_search"); if (search) search.value = ""; }
    ["afm_patient", "afm_diagnosis", "afm_notes", "afm_hospital", "afm_bill"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.value = "";
    });
    lockPatientField("");
    ["afm_admission", "afm_discharge"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.value = "";
    });
    if (window.FileQueue) {
      window.FileQueue.clear("afm_letter");
      window.FileQueue.clear("afm_bills");
      window.FileQueue.clear("afm_other");
    }
    initMedQueues();
    updateMedChecklist();
  }

  function initMedQueues() {
    if (!window.FileQueue) return;
    window.FileQueue.init("afm_letter", { inputId: "afm_letter_input", containerId: "afm_letter_queue", maxFiles: 5, accept: "image/*,.pdf,.docx", mode: "rows" });
    window.FileQueue.init("afm_bills", { inputId: "afm_bills_input", containerId: "afm_bills_queue", maxFiles: 10, accept: "image/*,.pdf,.docx", mode: "rows" });
    window.FileQueue.init("afm_other", { inputId: "afm_other_input", containerId: "afm_other_queue", maxFiles: 5, accept: "image/*,.pdf,.docx", mode: "rows" });
  }

  async function loadMedical() {
    initMedQueues();
    await loadMembers();
    med.members = allFilingMembers();
    if (medPicker) medPicker.render();
    const dateEl = document.getElementById("afm_date");
    if (dateEl && !dateEl.value) dateEl.value = new Date().toISOString().slice(0, 10);
    const data = await getJSON("/api/treasurer/medical-aids/list/");
    window.db = window.db || {};
    window.db.medical_aids = (data && data.medical_aids) || [];
    const tbody = document.querySelector("#afm_history tbody");
    if (tbody) {
      const all = window.db.medical_aids || [];
      const PAGE_SIZE = 8;
      const pageCount = Math.max(1, Math.ceil(all.length / PAGE_SIZE));
      afmHistoryPage = Math.min(Math.max(afmHistoryPage, 1), pageCount);
      const rows = all.slice((afmHistoryPage - 1) * PAGE_SIZE, afmHistoryPage * PAGE_SIZE);
      tbody.innerHTML = rows.length
        ? rows
            .map(
              (r) =>
                `<tr><td><b>${esc(r.name)}</b></td><td>${esc(r.reason || "")}</td><td>${peso(r.bill)}</td><td>${esc(r.status || "")}</td></tr>`
            )
            .join("")
        : '<tr><td colspan="4" style="text-align:center;color:#757575;">No medical aid requests yet.</td></tr>';
      const pager = document.getElementById("afm-history-pagination");
      if (pager && typeof UniPager !== "undefined") {
        pager.innerHTML = UniPager.html(afmHistoryPage, pageCount, "window.__afmHistoryGoPage(PAGE)", UniPager.count(afmHistoryPage, PAGE_SIZE, all.length));
      }
    }
    renderMedMemberCard();
    updateMedChecklist();
  }

  /* ================= DEATH AID ================= */

  const dth = { member: null, rel: "", claimsThisYearChecked: false, family: [], deceasedAuto: "" };

  function renderDeathMemberCard() {
    const box = document.getElementById("afd_member_card");
    if (!box) return;
    if (!dth.member) {
      box.innerHTML = emptyMemberBox();
    } else {
      box.innerHTML = memberCardHTML(dth.member, "window.nxAidFiling.clearDeathMember()");
    }
    if (dthPicker) dthPicker.renderTrigger();
  }

  let dthPicker = null;
  function getDeathPicker() {
    if (dthPicker) return dthPicker;
    dthPicker = createMemberPicker({
      triggerId: "afd_member_trigger",
      panelId: "afd_member_results",
      searchId: "afd_member_search",
      alphaId: "afd_member_alpha",
      listId: "afd_member_list",
      pagerId: "afd_member_pager",
      getSelected: function () { return dth.member; },
      onPick: function (id) { if (window.nxAidFiling) window.nxAidFiling.pickDeathMember(id); },
      onData: function () {},
    });
    return dthPicker;
  }

  // Legacy entry point (kept for compat): route into the dropdown picker.
  function renderDeathResults(query) {
    getDeathPicker().setQuery(query || "");
  }

  function deathMembers() {
    return allFilingMembers();
  }

  function memberContactOf(m) {
    if (!m) return "";
    return m.contact_number || m.contact || m.phone || m.mobile || "";
  }

  function memberNameOf(m) {
    if (!m) return "";
    return m.full_name || m.name || "";
  }

  // Claimant Contact is always displayed as 09##-###-#### — whether it was
  // auto-filled from the member record or typed by the treasurer (local,
  // +63 and 63 entries all collapse to the same shape).
  function formatClaimantContact(el) {
    if (!el) return el;
    if (window.PHONE_FORMAT) el.value = window.PHONE_FORMAT.format(el.value);
    return el;
  }

  // Phase 1 → Phase 2 link: claimant name/contact are taken straight from
  // the database record of the associated member selected in Step 1.
  function fillClaimantFromMember() {
    const nameEl = document.getElementById("afd_claimant");
    const contactEl = document.getElementById("afd_contact");
    if (!dth.member) return;
    const nm = memberNameOf(dth.member);
    const ct = memberContactOf(dth.member);
    // Only overwrite when the field is empty, so a treasurer edit done
    // before picking the member is not clobbered — but a fresh pick
    // always populates empty fields automatically.
    if (nameEl && !nameEl.value.trim() && nm) nameEl.value = nm;
    if (contactEl && !contactEl.value.trim() && ct) {
      contactEl.value = ct;
      formatClaimantContact(contactEl);
    }
  }

  function forceClaimantFromMember() {
    const nameEl = document.getElementById("afd_claimant");
    const contactEl = document.getElementById("afd_contact");
    if (nameEl) nameEl.value = dth.member ? memberNameOf(dth.member) : "";
    if (contactEl) {
      contactEl.value = dth.member ? memberContactOf(dth.member) : "";
      formatClaimantContact(contactEl);
    }
  }

  // Member family list (Claimants) for the selected member — used to
  // auto-fill the deceased name when a relationship category is picked.
  async function refreshDeathFamily() {
    dth.family = [];
    const id = dth.member ? dth.member.member_id_PK || dth.member.member_id || dth.member.id : null;
    if (!id) return;
    try {
      const data = await getJSON("/api/treasurer/member/" + encodeURIComponent(id) + "/family/");
      if (data && data.ok) dth.family = data.items || [];
    } catch (e) {}
  }

  function fillDeceasedFromFamily() {
    const deceased = document.getElementById("afd_deceased");
    const deceasedWrap = deceased ? deceased.closest(".form-group") : null;
    if (!deceased || !dth.rel || dth.rel === "member") return;
    const matches = (dth.family || []).filter((f) => f.category === dth.rel);
    if (!matches.length) return;

    // Remove any existing dropdown from previous selection
    const existingDropdown = deceasedWrap ? deceasedWrap.querySelector(".afd-family-dropdown") : null;
    if (existingDropdown) existingDropdown.remove();

    // Never clobber a name the treasurer already typed — only a previous
    // auto-fill may be replaced.
    if (deceased.value.trim() && deceased.value !== dth.deceasedAuto) return;

    if (matches.length === 1) {
      deceased.value = matches[0].full_name || "";
      dth.deceasedAuto = deceased.value;
      updateDeathChecklist();
    } else {
      // Multiple relatives in this tier (2 children, both parents…) — the
      // name cannot be guessed, so prompt the treasurer to pick which one
      // is the deceased.
      const relLabel = (DEATH_LABELS[dth.rel] || dth.rel).replace(" of member", "").toLowerCase();
      const dropdown = document.createElement("select");
      dropdown.className = "afd-family-dropdown";
      dropdown.setAttribute("aria-label", "Select which listed " + relLabel + " is the deceased");
      dropdown.style.cssText = "width:100%;margin-top:6px;padding:10px 14px;border-radius:8px;border:1.5px solid #2e7d32;font:inherit;background:#f6fbf6;color:#263238;font-weight:600;";
      dropdown.innerHTML =
        '<option value="">' + matches.length + " " + esc(relLabel) + " records listed — select which one is the deceased</option>" +
        matches.map((m) => '<option value="' + esc(m.full_name || "") + '">' + esc(m.full_name || "") + "</option>").join("");

      dropdown.addEventListener("change", function () {
        if (this.value) {
          deceased.value = this.value;
          dth.deceasedAuto = this.value;
          updateDeathChecklist();
        }
      });

      // Insert dropdown after the input
      deceased.parentNode.insertBefore(dropdown, deceased.nextSibling);
    }
  }

  // Drop a stale auto-filled name (e.g. switching from a category that has
  // a relative to one that has none). A manually typed name is preserved.
  function clearStaleDeceasedAuto() {
    const deceased = document.getElementById("afd_deceased");
    const deceasedWrap = deceased ? deceased.closest(".form-group") : null;
    if (deceased && dth.deceasedAuto && deceased.value === dth.deceasedAuto) {
      deceased.value = "";
    }
    // Remove any existing dropdown
    if (deceasedWrap) {
      const existingDropdown = deceasedWrap.querySelector(".afd-family-dropdown");
      if (existingDropdown) existingDropdown.remove();
    }
    dth.deceasedAuto = "";
  }

  function onDeathRelChange() {
    const sel = document.getElementById("afd_rel");
    dth.rel = sel ? sel.value : "";
    const deceased = document.getElementById("afd_deceased");
    const deceasedWrap = deceased ? deceased.closest(".form-group") : null;
    // Remove any existing dropdown when relationship changes
    if (deceasedWrap) {
      const existingDropdown = deceasedWrap.querySelector(".afd-family-dropdown");
      if (existingDropdown) existingDropdown.remove();
    }
    if (deceased) {
      if (dth.rel === "member") {
        dth.deceasedAuto = "";
        deceased.value = dth.member ? dth.member.full_name || dth.member.name || "" : "";
        deceased.readOnly = true;
        deceased.style.background = "#e8f5e9";
      } else {
        const wasLocked = deceased.readOnly;
        deceased.readOnly = false;
        deceased.style.background = "";
        if (wasLocked) { deceased.value = ""; dth.deceasedAuto = ""; }
        else clearStaleDeceasedAuto();
        fillDeceasedFromFamily();
      }
    }
    // Validate spouse - should only have one
    if (dth.rel === "spouse") {
      const spouseMatches = (dth.family || []).filter((f) => f.category === "spouse");
      if (spouseMatches.length > 1) {
        toast("Warning: Multiple spouses found in family list. Only one spouse is allowed.", true);
      }
    }
    const amt = document.getElementById("afd_amount");
    const knownBenefit = !!(dth.rel && DEATH_BENEFITS[dth.rel]);
    if (amt) {
      amt.textContent = knownBenefit ? peso(DEATH_BENEFITS[dth.rel]) + " (per By-Laws Article XI)" : "";
    }
    // Hide the header "Benefit Amount" block until a relationship is chosen.
    const amtWrap = document.getElementById("afd_amount_wrap");
    if (amtWrap) amtWrap.style.display = knownBenefit ? "" : "none";
    const rows = document.querySelectorAll("[data-afd-rel-row]");
    rows.forEach((r) => {
      r.style.background = r.getAttribute("data-afd-rel-row") === dth.rel ? "rgba(46,125,50,0.10)" : "transparent";
      r.style.fontWeight = r.getAttribute("data-afd-rel-row") === dth.rel ? "700" : "400";
    });
    updateDeathChecklist();
  }

  /* ---------- future-date traps (blocking top-center alert) ----------
   * Dates that cannot logically sit in the future — confinement end and
   * date of death — are rejected the moment they are picked and again at
   * submit time. The alert card has to be clicked away.               */
  function trapConfinementTo() {
    const el = document.getElementById("afm_discharge");
    if (!el || !el.value) return false;
    return window.guardFutureDate({
      input: el,
      key: "future-confinement-to",
      phrase:
        "Confinement — To is set to " + window.friendlyDateLabel(el.value) +
        ", which is in the future. A confinement end date cannot be later than today.",
    });
  }

  function deathDateSubject() {
    const typed = ((document.getElementById("afd_deceased") || {}).value || "").trim();
    if (typed) return typed;
    if (dth.member) return memberNameOf(dth.member);
    return "The deceased";
  }

  function trapDeathDate() {
    const el = document.getElementById("afd_dod");
    if (!el || !el.value) return false;
    const subject = deathDateSubject();
    return window.guardFutureDate({
      input: el,
      key: "future-death-date",
      phrase:
        subject + " is recorded as having passed away on " +
        window.friendlyDateLabel(el.value) +
        ", which is in the future — a date of death cannot be later than today.",
    });
  }

  function updateDeathChecklist() {
    const list = document.getElementById("afd_checklist");
    if (!list) return;
    const deceased = ((document.getElementById("afd_deceased") || {}).value || "").trim();
    const dod = (document.getElementById("afd_dod") || {}).value || "";
    const claimant = ((document.getElementById("afd_claimant") || {}).value || "").trim();
    const contact = ((document.getElementById("afd_contact") || {}).value || "").trim();
    const memberName = dth.member ? memberNameOf(dth.member) : "";
    const relLabel = dth.rel ? (DEATH_LABELS[dth.rel] || dth.rel) : "";
    const benefit = dth.rel && DEATH_BENEFITS[dth.rel] ? peso(DEATH_BENEFITS[dth.rel]) : "";
    const dropdownWaiting = !deceased && !!document.querySelector(".afd-family-dropdown");
    const checks = [
      { ok: !!dth.member, text: dth.member ? `Associated member: ${memberName}` : "Associated member: — select a member in Step 1" },
      { ok: !!dth.rel, text: dth.rel ? `Relationship: ${relLabel}${benefit ? ` (${benefit})` : ""}` : "Relationship: — select from Deceased Details (Step 2)" },
      { ok: !!deceased, text: deceased ? `Name of deceased: ${deceased}` : (dropdownWaiting ? "Name of deceased: — select which listed relative is the deceased from the dropdown in Step 2" : "Name of deceased: — enter in Deceased Details (Step 2)") },
      { ok: !!dod, text: dod ? `Date of death: ${dod}` : "Date of death: — enter in Deceased Details (Step 2)" },
      { ok: !!claimant && !!contact, text: (claimant && contact) ? `Claimant: ${claimant} · ${contact}` : "Claimant: — auto-filled from member (Step 1), name + contact required" },
    ];
    list.innerHTML = checks.map((c) => checkPill(c.ok, c.text)).join("");
    const btn = document.getElementById("afd_submit");
    if (btn) btn.disabled = !checks.every((c) => c.ok);
  }

  async function submitDeath(e) {
    e.preventDefault();
    if (!dth.member) return toast("Select a member first.", true);
    if (!dth.rel) return toast("Select who passed away.", true);
    if (trapDeathDate()) return;

    const fd = new FormData();
    fd.append("death_member", String(dth.member.member_id_PK || dth.member.member_id || dth.member.id || ""));
    fd.append("death_deceased", (document.getElementById("afd_deceased") || {}).value || "");
    fd.append("death_rel", dth.rel);
    fd.append("death_rel_group", dth.rel === "member" ? "member" : dth.rel === "sibling" ? "sibling" : "immediate");
    fd.append("death_scenario", dth.rel === "member" ? "member" : "dependent");
    fd.append("death_type", dth.rel === "member" ? "Member" : dth.rel === "spouse" ? "Spouse" : dth.rel === "sibling" ? "Full-Blood / Half Sibling" : "Parent/Child");
    fd.append("death_date", (document.getElementById("afd_dod") || {}).value || "");
    fd.append("death_interment_date", (document.getElementById("afd_interment") || {}).value || "");
    fd.append("death_funeral_location", (document.getElementById("afd_place") || {}).value || "");
    fd.append("death_bill", ((document.getElementById("afd_bill") || {}).value || ""));
    fd.append("death_claimant", (document.getElementById("afd_claimant") || {}).value || "");
    fd.append("death_contact", (document.getElementById("afd_contact") || {}).value || "");
    fd.append("death_source", "fund");
    const others = window.FileQueue ? window.FileQueue.getFiles("afd_other") : [];
    others.forEach((f) => fd.append("death_photo_files", f));

    const btn = document.getElementById("afd_submit");
    if (btn) { btn.disabled = true; btn.textContent = "Submitting..."; }
    try {
      const res = await fetch("/api/treasurer/death-aid/add/", {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": getCookie("csrftoken") },
        body: fd,
      });
      const data = await res.json().catch(() => ({}));
      if (data && data.ok) {
        toast("Death aid claim filed and submitted to the Auditor. The member has been notified by email.", false);
        resetDeath();
      } else {
        toast((data && data.error) || "Failed to submit death aid claim.", true);
      }
    } catch (err) {
      toast("Network error while submitting.", true);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "Submit to Auditor"; }
      updateDeathChecklist();
    }
  }

  function resetDeath() {
    dth.member = null;
    dth.family = [];
    dth.deceasedAuto = "";
    dth.rel = "";
    // Remove any existing dropdown
    const deceased = document.getElementById("afd_deceased");
    const deceasedWrap = deceased ? deceased.closest(".form-group") : null;
    if (deceasedWrap) {
      const existingDropdown = deceasedWrap.querySelector(".afd-family-dropdown");
      if (existingDropdown) existingDropdown.remove();
    }
    renderDeathMemberCard();
    if (dthPicker) dthPicker.reset();
    else { const search = document.getElementById("afd_member_search"); if (search) search.value = ""; }
    ["afd_deceased", "afd_dod", "afd_interment", "afd_place", "afd_claimant", "afd_contact"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.value = "";
    });
    const relSel = document.getElementById("afd_rel");
    if (relSel) relSel.value = "";
    if (window.FileQueue) window.FileQueue.clear("afd_other");
    initDeathQueue();
    onDeathRelChange();
  }

  function initDeathQueue() {
    if (!window.FileQueue) return;
    window.FileQueue.init("afd_other", { inputId: "afd_other_input", containerId: "afd_other_queue", maxFiles: 5, accept: "image/*,.pdf,.docx", mode: "rows" });
  }

  async function loadDeath() {
    initDeathQueue();
    await loadMembers();
    if (dthPicker) dthPicker.render();
    const data = await getJSON("/api/treasurer/death-aids/list/");
    const tbody = document.querySelector("#afd_history tbody");
    if (tbody) {
      const all = (data && data.death_aids) || [];
      const PAGE_SIZE = 8;
      const pageCount = Math.max(1, Math.ceil(all.length / PAGE_SIZE));
      afdHistoryPage = Math.min(Math.max(afdHistoryPage, 1), pageCount);
      const rows = all.slice((afdHistoryPage - 1) * PAGE_SIZE, afdHistoryPage * PAGE_SIZE);
      tbody.innerHTML = rows.length
        ? rows
            .map(
              (r) =>
                `<tr><td><b>${esc(r.name || r.claimant || "")}</b></td><td>${esc(r.deceased || "")}</td><td>${esc(r.relationship || "")}</td><td>${peso(r.benefit_amount || r.benefit || 0)}</td><td>${esc(r.status || "")}</td></tr>`
            )
            .join("")
        : '<tr><td colspan="5" style="text-align:center;color:#757575;">No death aid claims yet.</td></tr>';
      const pager = document.getElementById("afd-history-pagination");
      if (pager && typeof UniPager !== "undefined") {
        pager.innerHTML = UniPager.html(afdHistoryPage, pageCount, "window.__afdHistoryGoPage(PAGE)", UniPager.count(afdHistoryPage, PAGE_SIZE, all.length));
      }
    }
    renderDeathMemberCard();
    onDeathRelChange();
  }

  /* ================= BOOT / HOOKS ================= */

  function boot() {
    // Bind once: boot() re-runs on turbo:load, and rebinding form submits
    // used to stack duplicate handlers (double POSTs on submit).
    if (window.__nxAidFilingBooted) {
      // Still refresh trigger labels in case the DOM was re-rendered.
      try { getMedPicker().renderTrigger(); } catch (e) {}
      try { getDeathPicker().renderTrigger(); } catch (e) {}
      return;
    }
    window.__nxAidFilingBooted = true;
    ensurePickerCSS();
    getMedPicker();
    getDeathPicker();
    // live listeners for checklist updates
    ["afm_bill", "afm_diagnosis"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener("input", updateMedChecklist);
    });
    ["afd_deceased", "afd_dod", "afd_claimant", "afd_contact"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener("input", updateDeathChecklist);
    });
    // Trap impossible future dates the moment they are picked.
    const afmDischargeEl = document.getElementById("afm_discharge");
    if (afmDischargeEl) afmDischargeEl.addEventListener("change", trapConfinementTo);
    const afdDodEl = document.getElementById("afd_dod");
    if (afdDodEl) afdDodEl.addEventListener("change", trapDeathDate);
    // Claimant Contact → live 09##-###-#### formatting.
    const afdContactEl = document.getElementById("afd_contact");
    if (afdContactEl && window.PHONE_FORMAT) window.PHONE_FORMAT.attach(afdContactEl);
    const relSel = document.getElementById("afd_rel");
    if (relSel) relSel.addEventListener("change", onDeathRelChange);

    // Refresh the validation checklists the moment uploads change
    // (FileQueue re-renders its queue container when files are added/removed).
    if (window.MutationObserver && !window.__nxAidFilingObserved) {
      window.__nxAidFilingObserved = true;
      let medTimer = null;
      const medObserver = new MutationObserver(() => {
        clearTimeout(medTimer);
        medTimer = setTimeout(updateMedChecklist, 60);
      });
      ["afm_letter_queue", "afm_bills_queue", "afm_other_queue"].forEach((qid) => {
        const el = document.getElementById(qid);
        if (el) medObserver.observe(el, { childList: true, subtree: true });
      });

      let dthTimer = null;
      const dthObserver = new MutationObserver(() => {
        clearTimeout(dthTimer);
        dthTimer = setTimeout(updateDeathChecklist, 60);
      });
      ["afd_other_queue"].forEach((qid) => {
        const el = document.getElementById(qid);
        if (el) dthObserver.observe(el, { childList: true, subtree: true });
      });
    }


    const medForm = document.getElementById("afm_form");
    if (medForm) medForm.addEventListener("submit", submitMedical);
    const deathForm = document.getElementById("afd_form");
    if (deathForm) deathForm.addEventListener("submit", submitDeath);
    // NOTE: picker panels manage their own open/close (trigger toggle +
    // outside-click) inside createMemberPicker — no global closer needed.
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
  document.addEventListener("turbo:load", boot);

  // Load data whenever a new filing module is opened from the sidebar
  if (!window.__nxAidFilingClickBound) {
    window.__nxAidFilingClickBound = true;
    document.addEventListener("click", function (e) {
      if (e.target.closest && e.target.closest('[data-target="aid-file-medical"]')) {
        setTimeout(function () { if (window.nxAidFiling) window.nxAidFiling.loadMedical(); }, 200);
      }
      if (e.target.closest && e.target.closest('[data-target="aid-file-death"]')) {
        setTimeout(function () { if (window.nxAidFiling) window.nxAidFiling.loadDeath(); }, 200);
      }
    });
  }

  window.nxAidFilingRender = {
    medResults: renderMedResults,
    deathResults: renderDeathResults,
  };

  window.nxAidFiling = {
    resetMedical,
    resetDeath,
    loadMedical,
    loadDeath,
    reloadMembers: async function () {
      await loadMembers(true);
      med.members = allFilingMembers();
      if (medPicker) medPicker.render();
      if (dthPicker) dthPicker.render();
    },
    openMedPicker: function () { getMedPicker().openPanel(); },
    openDeathPicker: function () { getDeathPicker().openPanel(); },
    pickMedMember: function (id) {
      const m = (med.members || allFilingMembers()).find((x) => String(x.member_id_PK || x.member_id || x.id) === String(id));
      if (m) med.member = m;
      if (medPicker) { medPicker.closePanel(); medPicker.renderTrigger(); }
      // Patient / Beneficiary is locked to the selected member (read-only).
      if (m) lockPatientField(m.full_name || m.name || "");
      renderMedMemberCard();
      updateMedChecklist();
    },
    clearMedMember: function () {
      med.member = null;
      lockPatientField("");
      if (medPicker) medPicker.reset();
      renderMedMemberCard();
      updateMedChecklist();
    },
    pickDeathMember: function (id) {
      const m = allFilingMembers().find((x) => String(x.member_id_PK || x.member_id || x.id) === String(id));
      if (m) dth.member = m;
      if (dthPicker) { dthPicker.closePanel(); dthPicker.renderTrigger(); }
      // Phase 1 select → auto-populate Claimant Name + Contact from DB.
      forceClaimantFromMember();
      renderDeathMemberCard();
      // Drop the previous member's family + auto-fill so a stale name can
      // never leak into the new member's form.
      dth.family = [];
      clearStaleDeceasedAuto();
      onDeathRelChange();
      // Load the family list so the deceased name auto-fills when a
      // category is already selected (or gets selected next).
      refreshDeathFamily().then(function () { fillDeceasedFromFamily(); });
    },
    clearDeathMember: function () {
      dth.member = null;
      dth.family = [];
      dth.deceasedAuto = "";
      const nameEl = document.getElementById("afd_claimant");
      if (nameEl) nameEl.value = "";
      const contactEl = document.getElementById("afd_contact");
      if (contactEl) contactEl.value = "";
      if (dthPicker) dthPicker.reset();
      renderDeathMemberCard();
      onDeathRelChange();
      updateDeathChecklist();
    },
  };
})();
