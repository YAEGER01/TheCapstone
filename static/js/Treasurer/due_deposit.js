// due_deposit.js — ISUCauFA, Inc. Treasurer "Due Deposit" module.
// Three-card workspace:
//   left  (40%) — Pending Deposit (recorded batches awaiting bank deposit)
//                 Due Deposit History (past monthly dues deposits)
//   right (60%) — deposit form for the selected batch (bank ref + slip).
// Reuses the Record Transaction "Monthly Dues Deposit" endpoints:
//   GET  /api/treasurer/deductions/pending-deposit/
//   POST /api/treasurer/deductions/deposit/
//   GET  /api/treasurer/other-transactions/list/  (entries with source "monthly_dues")
// Host section: #view-due-deposit (Treasurer dashboard only).
(function () {
  "use strict";

  const PENDING_DEPOSIT_URL = "/api/treasurer/deductions/pending-deposit/";
  const DEPOSIT_URL = "/api/treasurer/deductions/deposit/";
  const LIST_URL = "/api/treasurer/other-transactions/list/";
  const HISTORY_LIMIT = 25;

  let pending = [];
  let historyRows = [];
  let selectedId = null;
  let renderedFormId = null;
  let autoSelectNext = true;
  let busy = false;

  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function getCSRFToken() {
    if (typeof window.getCSRFToken === "function") {
      const t = window.getCSRFToken();
      if (t) return t;
    }
    const el = document.querySelector("input[name='csrfmiddlewaretoken']");
    if (el && el.value) return el.value;
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function toast(msg, isError) {
    if (typeof showToast === "function") {
      showToast(msg, !!isError);
      return;
    }
    if (typeof window.showToast === "function") {
      window.showToast(msg, !!isError);
      return;
    }
    window.alert(msg);
  }

  function peso(v) {
    const n = Number(v || 0);
    const s = n.toFixed(2);
    const parts = s.split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return "₱" + parts.join(".");
  }

  function collectionById(id) {
    const key = String(id);
    return pending.find((c) => String(c.assessment_id) === key) || null;
  }

  function refreshSiblings() {
    try {
      if (window.nxOtherTransactions) {
        if (typeof window.nxOtherTransactions.load === "function") window.nxOtherTransactions.load();
      }
    } catch (e) {}
    try {
      if (typeof window.loadMdOverviews === "function") window.loadMdOverviews();
    } catch (e) {}
    try {
      if (window.nxFundOverview && typeof window.nxFundOverview.load === "function") window.nxFundOverview.load();
      if (window.nxFundLedger && typeof window.nxFundLedger.load === "function") window.nxFundLedger.load();
      if (window.overviewDashboard && typeof window.overviewDashboard.refresh === "function") window.overviewDashboard.refresh();
      else if (typeof window.nxRefreshFundSummary === "function") window.nxRefreshFundSummary();
    } catch (e) {}
  }

  /* ------------------------- pending deposit card ------------------------- */

  function renderPending() {
    const list = document.getElementById("dd-pending-list");
    const count = document.getElementById("dd-pending-count");
    if (count) count.textContent = String(pending.length);

    if (selectedId && !collectionById(selectedId)) selectedId = null;
    if (!selectedId && autoSelectNext && pending.length) {
      selectedId = String(pending[0].assessment_id);
    }
    if (!list) return;
    if (!pending.length) {
      list.innerHTML = '<div class="dd-empty">No recorded batches awaiting deposit.</div>';
      return;
    }
    list.innerHTML = pending
      .map((c) => {
        const id = String(c.assessment_id);
        const ref = c.collection_reference || "COL-" + id.padStart(5, "0");
        const members = Number(c.recorded_count || 0);
        const sel = id === selectedId ? " is-selected" : "";
        return (
          '<button type="button" class="dd-pending-row' + sel + '" data-dd-id="' + esc(id) + '">' +
            '<span class="dd-pending-main">' +
              '<span class="dd-pending-month">' + esc(c.month_label || "") + "</span>" +
              '<span class="dd-pending-meta">' + esc(ref) + " · " + members +
                (members === 1 ? " member" : " members") + "</span>" +
            "</span>" +
            '<span class="dd-pending-amount">' + esc(peso(c.total_recorded)) + "</span>" +
          "</button>"
        );
      })
      .join("");
  }

  function selectBatch(id) {
    const key = String(id);
    if (!collectionById(key)) return;
    selectedId = key;
    renderPending();
    renderForm();
  }

  /* ---------------------------- deposit form ---------------------------- */

  function setFormError(message) {
    const box = document.querySelector("#dd-form [data-role='form-error']");
    if (!box) return;
    box.textContent = message || "";
    box.classList.toggle("is-visible", !!message);
  }

  function bindFormCard(host) {
    const zone = host.querySelector("[data-role='dep-zone']");
    const input = host.querySelector("[data-role='dep-proof']");
    const nameEl = host.querySelector("[data-role='dep-file-name']");
    const refInput = host.querySelector("[data-role='dep-ref']");
    const submit = host.querySelector("[data-role='dd-submit']");
    const clear = host.querySelector("[data-role='dd-clear']");

    if (zone && input) {
      const onProofPicked = function () {
        setFormError("");
        const f = input.files && input.files[0];
        if (nameEl) {
          nameEl.textContent = f ? f.name : "";
          nameEl.style.display = f ? "block" : "none";
        }
      };
      zone.addEventListener("click", function (e) {
        if (e.target !== input) input.click();
      });
      zone.addEventListener("dragover", function (e) {
        e.preventDefault();
        zone.classList.add("dd-dragover");
      });
      zone.addEventListener("dragleave", function () {
        zone.classList.remove("dd-dragover");
      });
      zone.addEventListener("drop", function (e) {
        e.preventDefault();
        zone.classList.remove("dd-dragover");
        if (e.dataTransfer.files && e.dataTransfer.files.length) {
          input.files = e.dataTransfer.files;
          onProofPicked();
        }
      });
      input.addEventListener("change", onProofPicked);
    }

    if (refInput) {
      refInput.addEventListener("input", function () { setFormError(""); });
      refInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          submitDeposit();
        }
      });
    }
    if (submit) submit.addEventListener("click", submitDeposit);
    if (clear) {
      clear.addEventListener("click", function () {
        selectedId = null;
        autoSelectNext = false;
        renderPending();
        renderForm();
      });
    }
  }

  function renderForm() {
    const host = document.getElementById("dd-form");
    if (!host) return;
    const id = selectedId || "";
    if (id === renderedFormId) return;
    renderedFormId = id;

    const c = id ? collectionById(id) : null;
    if (!c) {
      host.innerHTML =
        '<div class="dd-form-empty">' +
          '<i class="fa-solid fa-building-columns"></i>' +
          "<div><b>Select a batch to deposit</b>" +
          "<span>Pick a recorded month under <b>Pending Deposit</b> on the left, then enter its bank deposit reference and slip here.</span></div>" +
        "</div>";
      return;
    }

    const key = String(c.assessment_id);
    const ref = c.collection_reference || "COL-" + key.padStart(5, "0");
    const remaining = (c.remaining_to_deposit != null ? Number(c.remaining_to_deposit) : Number(c.total_recorded || 0)).toFixed(2);
    const members = Number(c.recorded_count || 0);
    host.innerHTML =
      '<div class="dd-form-card">' +
        '<div class="dd-form-head">' +
          '<div class="dd-form-title">' +
            "<span>" + esc(c.month_label || "") + "</span>" +
            '<span class="dd-col-badge"><i class="fa-solid fa-link" style="font-size:0.65rem;"></i> ' + esc(ref) + "</span>" +
          "</div>" +
          '<span class="dd-chip">' + members + (members === 1 ? " member" : " members") + " recorded</span>" +
        "</div>" +
        '<div class="dd-form-grid">' +
          '<div class="dd-field">' +
            '<label class="dd-label">Amount to Deposit <span class="dd-optional">partial allowed — defaults to remaining</span></label>' +
            '<div class="dd-amount-wrap">' +
              '<span class="dd-currency">₱</span>' +
              '<input type="text" class="form-control dd-amount-input" data-role="dep-amount" value="' + esc(remaining) + '" />' +
            "</div>" +
          "</div>" +
          '<div class="dd-field">' +
            '<label class="dd-label">Bank Deposit Reference <span class="dd-optional">required — ORS/OR number</span></label>' +
            '<input type="text" class="form-control" data-role="dep-ref" maxlength="100" placeholder="e.g. ORS-2026-00123" />' +
          "</div>" +
          '<div class="dd-field full">' +
            '<label class="dd-label">Deposit Slip <span class="dd-optional">required — bank/ORS slip (image or PDF)</span></label>' +
            '<div class="dd-dropzone" data-role="dep-zone">' +
              '<div data-role="dep-zone-text"><i class="fa-solid fa-cloud-arrow-up"></i><br />Upload Deposit Slip (PDF/Image)</div>' +
              '<div class="dd-dropzone-file" data-role="dep-file-name" style="display:none;"></div>' +
              '<input type="file" accept="image/*,.pdf,.png,.jpg,.jpeg" class="dd-proof-input" data-role="dep-proof" />' +
            "</div>" +
          "</div>" +
        "</div>" +
        '<div class="dd-form-error" data-role="form-error"></div>' +
        '<div class="dd-form-actions">' +
          '<button type="button" class="dd-btn-primary" data-role="dd-submit">Deposit Batch</button>' +
          '<button type="button" class="dd-btn-secondary" data-role="dd-clear">Clear Selection</button>' +
        "</div>" +
      "</div>";
    bindFormCard(host);
  }

  async function submitDeposit() {
    if (busy) return;
    const host = document.getElementById("dd-form");
    const c = selectedId ? collectionById(selectedId) : null;
    if (!c || !host) {
      toast("Select a batch under Pending Deposit first.", true);
      return;
    }
    const refInput = host.querySelector("[data-role='dep-ref']");
    const amountInput = host.querySelector("[data-role='dep-amount']");
    const fileInput = host.querySelector("[data-role='dep-proof']");
    const submit = host.querySelector("[data-role='dd-submit']");
    const ref = refInput && refInput.value.trim();
    const amountVal = amountInput ? Number(String(amountInput.value).replace(/,/g, "")) : Number(c.remaining_to_deposit != null ? c.remaining_to_deposit : c.total_recorded || 0);
    const file = fileInput && fileInput.files && fileInput.files[0];
    setFormError("");
    if (!ref) {
      setFormError("Bank deposit reference is required.");
      if (refInput) refInput.focus();
      return;
    }
    if (!amountVal || isNaN(amountVal) || amountVal <= 0) {
      setFormError("Enter the amount actually deposited (partial deposits are allowed).");
      if (amountInput) amountInput.focus();
      return;
    }
    if (!file) {
      setFormError("Deposit slip is required.");
      return;
    }

    busy = true;
    if (submit) {
      submit.disabled = true;
      submit.textContent = "Depositing…";
    }
    try {
      const fd = new FormData();
      fd.append("assessment_id", String(c.assessment_id));
      fd.append("deposit_reference", ref);
      fd.append("deposited_amount", amountVal.toFixed(2));
      fd.append("proof", file);
      const res = await fetch(DEPOSIT_URL, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": getCSRFToken() },
        body: fd,
      });
      const d = await res.json().catch(function () { return {}; });
      if (!res.ok || !d.ok) {
        const err = new Error(d.error || "Deposit failed for " + (c.month_label || c.assessment_id) + ".");
        err.status = res.status;
        throw err;
      }
      selectedId = null;
      autoSelectNext = true;
      toast(d.message || (c.month_label + " deposited."));
      await load();
      refreshSiblings();
    } catch (e) {
      setFormError(e.message || "Deposit failed.");
      toast(e.message || "Deposit failed.", true);
      if (e.status === 409) await loadPending();
    } finally {
      busy = false;
    }
  }

  /* -------------------------- deposit history card -------------------------- */

  function renderHistory() {
    const list = document.getElementById("dd-history-list");
    if (!list) return;
    const rows = historyRows.slice(0, HISTORY_LIMIT);
    if (!rows.length) {
      list.innerHTML = '<div class="dd-empty">No monthly dues deposits recorded yet.</div>';
      return;
    }
    let html = rows
      .map((r) => {
        const ref = String(r.reference_number || "");
        return (
          '<div class="dd-hist-row">' +
            '<div class="dd-hist-main">' +
              '<span class="dd-hist-amount">' + esc(peso(r.amount)) + "</span>" +
              '<span class="dd-hist-meta">' + esc(r.date || "") + (ref ? " · " + esc(ref) : "") + "</span>" +
            "</div>" +
            '<button type="button" class="dd-hist-btn" data-dd-detail="' + esc(String(r.id)) + '">Details</button>' +
          "</div>"
        );
      })
      .join("");
    if (historyRows.length > HISTORY_LIMIT) {
      html += '<div class="dd-hist-more">Showing ' + HISTORY_LIMIT + " of " + historyRows.length + " deposits.</div>";
    }
    list.innerHTML = html;
  }

  async function loadHistory() {
    const list = document.getElementById("dd-history-list");
    try {
      const res = await fetch(LIST_URL, { credentials: "same-origin", cache: "no-store" });
      const d = await res.json();
      if (!d.ok) throw new Error(d.error || "Failed to load deposit history.");
      historyRows = (d.entries || []).filter((r) => r.source === "monthly_dues");
    } catch (e) {
      historyRows = [];
      if (list) list.innerHTML = '<div class="dd-empty dd-empty-error">' + esc(e.message || "Could not load history.") + "</div>";
      return;
    }
    renderHistory();
  }

  /* --------------------------------- load --------------------------------- */

  async function loadPending() {
    const list = document.getElementById("dd-pending-list");
    try {
      const res = await fetch(PENDING_DEPOSIT_URL, { credentials: "same-origin", cache: "no-store" });
      const d = await res.json();
      if (!d.ok) throw new Error(d.error || "Failed to load recorded batches.");
      pending = d.collections || [];
    } catch (e) {
      pending = [];
      if (list) list.innerHTML = '<div class="dd-empty dd-empty-error">' + esc(e.message || "Could not load batches.") + "</div>";
      selectedId = null;
      renderedFormId = null;
      renderForm();
      return;
    }
    renderPending();
    renderForm();
  }

  async function load() {
    await Promise.all([loadPending(), loadHistory()]);
  }

  function bindStatic() {
    const list = document.getElementById("dd-pending-list");
    if (list && list.dataset.ddBound !== "1") {
      list.dataset.ddBound = "1";
      list.addEventListener("click", function (e) {
        const row = e.target.closest("[data-dd-id]");
        if (row) selectBatch(row.getAttribute("data-dd-id"));
      });
    }
    const hist = document.getElementById("dd-history-list");
    if (hist && hist.dataset.ddBound !== "1") {
      hist.dataset.ddBound = "1";
      hist.addEventListener("click", function (e) {
        const btn = e.target.closest("[data-dd-detail]");
        if (!btn) return;
        const id = Number(btn.getAttribute("data-dd-detail"));
        if (typeof window.nxShowTxDetail === "function") window.nxShowTxDetail("monthly_dues", id);
        else toast("Details view is unavailable.", true);
      });
    }
  }

  function init() {
    if (window.nxDueDeposit) return;
    bindStatic();
    window.nxDueDeposit = { load: load };
    load();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
