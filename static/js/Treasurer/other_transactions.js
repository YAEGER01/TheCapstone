// other_transactions.js — ISUCauFA, Inc. Treasurer "Record Transaction" module.
// One-off fund receipts/disbursements booked straight into FundTransaction
// with source_type = "other_transaction".
// (Monthly dues batch deposits live exclusively in the Due Deposit tab —
// logic in due_deposit.js — reusing the same deposit endpoints.)
// Host section: #treasurer-other-transactions (Treasurer dashboard only).
(function () {
  "use strict";

  const LIST_URL = "/api/treasurer/other-transactions/list/";
  const RECORD_URL = "/api/treasurer/other-transactions/record/";

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

  function refreshFundWidgets() {
    try {
      if (window.nxFundOverview && typeof window.nxFundOverview.load === "function") window.nxFundOverview.load();
    } catch (e) {}
    try {
      if (window.nxFundLedger && typeof window.nxFundLedger.load === "function") window.nxFundLedger.load();
    } catch (e) {}
    try {
      if (window.overviewDashboard && typeof window.overviewDashboard.refresh === "function") window.overviewDashboard.refresh();
      else if (window.nxRefreshFundSummary && typeof window.nxRefreshFundSummary === "function") window.nxRefreshFundSummary();
    } catch (e) {}
  }

  function refreshDeductionWorkspace() {
    try {
      if (typeof window.loadMdOverviews === "function") window.loadMdOverviews();
    } catch (e) {}
  }

  function currentAction() {
    const sel = document.querySelector("#treasurer-other-transactions .ot-type-btn[data-action].is-selected");
    return sel ? sel.dataset.action : "deposit";
  }

  function selectAction(action) {
    document.querySelectorAll("#treasurer-other-transactions .ot-type-btn[data-action]").forEach(function (btn) {
      btn.classList.toggle("is-selected", btn.dataset.action === action);
    });
    updateHint();
  }

  function updateHint() {
    const hint = document.getElementById("ot-live-hint");
    const action = currentAction();
    const donorWrap = document.getElementById("ot-donor-wrap");
    const recipWrap = document.getElementById("ot-recipient-wrap");
    if (donorWrap) donorWrap.style.display = action === "withdraw" ? "none" : "";
    if (recipWrap) recipWrap.style.display = action === "withdraw" ? "" : "none";
    if (!hint) return;
    hint.classList.remove("withdraw", "dues");
    hint.classList.toggle("withdraw", currentAction() === "withdraw");
    hint.innerHTML =
      currentAction() === "withdraw"
        ? '<i class="fas fa-circle-up" style="color:#a52c2c;"></i> A <b>Disbursement (Fund Withdrawal)</b> Debits general fund and shows under <b>Where Money Goes Out</b> in the Fund Overview.'
        : '<i class="fas fa-circle-up" style="color:#166a3b;"></i> Deposits will automatically reconcile with the General Fund receipt summary. A <b>Receipt (Fund Deposit)</b> credits the fund and shows under <b>Where Money Came From</b> in the Fund Overview.';
  }

  /* --------------------------- one-off mode --------------------------- */

  async function recordOneOff(submit) {
    const amountInput = document.getElementById("ot-amount");
    const descInput = document.getElementById("ot-description");
    const donorInput = document.getElementById("ot-donor");
    const recipInput = document.getElementById("ot-recipient");
    const proofInput = document.getElementById("ot-proof");

    const amountRaw = (amountInput && amountInput.value || "").trim();
    const amount = Number(amountRaw);
    if (!amountRaw || !isFinite(amount) || amount <= 0) {
      toast("Enter a valid Transaction Amount greater than zero.", true);
      if (amountInput) amountInput.focus();
      return;
    }
    const action = currentAction();
    const fd = new FormData();
    fd.append("amount", amountRaw);
    fd.append("action", action);
    if (descInput && descInput.value.trim()) fd.append("description", descInput.value.trim());
    if (action === "deposit") {
      if (donorInput && donorInput.value.trim()) fd.append("donor", donorInput.value.trim().slice(0, 120));
    } else {
      if (recipInput && recipInput.value.trim()) fd.append("recipient", recipInput.value.trim().slice(0, 120));
    }
    if (proofInput && proofInput.files && proofInput.files[0]) fd.append("proof_receipt", proofInput.files[0]);

    if (submit) submit.disabled = true;
    const label = action === "deposit" ? "Deposit" : "Withdraw";
    try {
      const res = await fetch(RECORD_URL, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": getCSRFToken() },
        body: fd,
      });
      const d = await res.json();
      if (!res.ok || !d.ok) throw new Error(d.error || "Could not record the transaction.");
      toast(label + " of " + peso(d.transaction.amount) + " recorded. Reference " + (d.transaction.reference_number || "") + ".");
      resetForm();
      await load();
      refreshFundWidgets();
    } catch (e) {
      toast(e.message || "Record failed.", true);
    } finally {
      if (submit) submit.disabled = false;
    }
  }

  function bindDropzone() {
    const zone = document.getElementById("ot-dropzone");
    const input = document.getElementById("ot-proof");
    const nameEl = document.getElementById("ot-proof-name");
    if (!zone || !input) return;
    zone.addEventListener("click", function (e) {
      if (e.target !== input) input.click();
    });
    zone.addEventListener("dragover", function (e) {
      e.preventDefault();
      zone.classList.add("ot-dragover");
    });
    zone.addEventListener("dragleave", function () {
      zone.classList.remove("ot-dragover");
    });
    zone.addEventListener("drop", function (e) {
      e.preventDefault();
      zone.classList.remove("ot-dragover");
      if (e.dataTransfer.files && e.dataTransfer.files.length) {
        input.files = e.dataTransfer.files;
        onProofPicked();
      }
    });
    input.addEventListener("change", onProofPicked);
    function onProofPicked() {
      const f = input.files && input.files[0];
      if (!f) {
        nameEl.style.display = "none";
        nameEl.textContent = "";
        return;
      }
      nameEl.textContent = f.name;
      nameEl.style.display = "block";
    }
  }

  function bindForm() {
    document.querySelectorAll("#treasurer-other-transactions .ot-type-btn[data-action]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        selectAction(btn.dataset.action);
      });
    });

    const clear = document.getElementById("ot-clear");
    if (clear) {
      clear.addEventListener("click", function () {
        resetForm();
      });
    }
    const submit = document.getElementById("ot-submit");
    if (submit) {
      submit.addEventListener("click", function () {
        record();
      });
      const amountInput = document.getElementById("ot-amount");
      if (amountInput) {
        amountInput.addEventListener("keydown", function (e) {
          if (e.key === "Enter" && !amountInput.readOnly) {
            e.preventDefault();
            record();
          }
        });
      }
    }
    bindDropzone();
  }

  /* --------------------- history: sort / filter / paging --------------------- */
  const TX_PAGE_SIZE = 10;
  let txRows = [];
  let txSort = { key: "date", dir: "desc" }; // newest first by default
  let txType = "";
  let txPage = 1;

  function txFilteredSorted() {
    let rows = txRows.slice();
    if (txType === "deposit") {
      rows = rows.filter((r) => r.source !== "monthly_dues" && r.action === "deposit");
    } else if (txType === "monthly_dues") {
      rows = rows.filter((r) => r.source === "monthly_dues");
    } else if (txType === "withdraw") {
      rows = rows.filter((r) => r.action === "withdraw");
    }
    const dir = txSort.dir === "asc" ? 1 : -1;
    const key = txSort.key;
    rows.sort((a, b) => {
      let cmp = 0;
      if (key === "amount") {
        cmp = Number(a.amount || 0) - Number(b.amount || 0);
      } else if (key === "reference") {
        cmp = String(a.reference_number || "").localeCompare(String(b.reference_number || ""), "en", { sensitivity: "base" });
      } else {
        cmp = String(a.sort_at || a.date || "").localeCompare(String(b.sort_at || b.date || ""));
      }
      if (cmp === 0) {
        cmp = String(a.sort_at || "").localeCompare(String(b.sort_at || "")) || Number(b.id || 0) - Number(a.id || 0);
      }
      return cmp * dir;
    });
    return rows;
  }

  function updateSortIcons() {
    ["date", "amount", "reference"].forEach((k) => {
      const el = document.getElementById("ot-sort-" + k + "-icon");
      if (!el) return;
      if (txSort.key !== k) {
        el.className = "fa-solid fa-sort";
        el.style.color = "";
      } else {
        el.className = "fa-solid " + (txSort.dir === "asc" ? "fa-caret-up" : "fa-caret-down");
        el.style.color = "#1b5e20";
      }
    });
  }

  function renderHistory() {
    const rows = txFilteredSorted();
    const totalPages = Math.max(1, Math.ceil(rows.length / TX_PAGE_SIZE));
    txPage = Math.min(Math.max(txPage, 1), totalPages);
    renderTable(rows.slice((txPage - 1) * TX_PAGE_SIZE, txPage * TX_PAGE_SIZE));
    updateSortIcons();
    const pag = document.getElementById("ot-history-pagination");
    if (pag) {
      pag.innerHTML = typeof UniPager !== "undefined"
        ? UniPager.html(txPage, totalPages, "window.__otTxGoPage(PAGE)", UniPager.count(txPage, TX_PAGE_SIZE, rows.length))
        : '<span style="color:#5f6b5f;font-size:0.78rem;">' + rows.length + " entries</span>";
    }
  }

  window.nxTxSort = function nxTxSort(key) {
    if (txSort.key === key) {
      txSort.dir = txSort.dir === "asc" ? "desc" : "asc";
    } else {
      txSort = { key: key, dir: key === "date" ? "desc" : "asc" };
    }
    txPage = 1;
    renderHistory();
  };

  window.nxTxFilter = function nxTxFilter(value) {
    txType = value || "";
    txPage = 1;
    renderHistory();
  };

  window.__otTxGoPage = function __otTxGoPage(page) {
    txPage = page;
    renderHistory();
  };

  function fmtDateStack(iso, fallback) {
    const d = iso ? new Date(iso) : null;
    if (!d || isNaN(d.getTime())) {
      return "<div>" + esc(fallback || "—") + "</div>";
    }
    const pad = (n) => String(n).padStart(2, "0");
    const mm = pad(d.getMonth() + 1);
    const dd = pad(d.getDate());
    const yy = pad(d.getFullYear() % 100);
    let hours = d.getHours();
    const ampm = hours >= 12 ? "PM" : "AM";
    hours = hours % 12 || 12;
    const time = pad(hours) + ":" + pad(d.getMinutes()) + " " + ampm;
    return (
      "<div style=\"white-space:nowrap;font-variant-numeric:tabular-nums;\">" + mm + "/" + dd + "/" + yy + "</div>" +
      '<div style="white-space:nowrap;font-size:0.72rem;color:#8a949e;font-variant-numeric:tabular-nums;">' + time + "</div>"
    );
  }

  function renderTable(rows) {
    const body = document.getElementById("ot-history-body");
    if (!body) return;
    if (!rows || !rows.length) {
      const msg = txRows.length
        ? "No transactions match the current filter."
        : "No transactions recorded yet. Use the form on the left to add a deposit or withdrawal.";
      body.innerHTML = '<tr><td colspan="5"><div class="empty-state">' + msg + "</div></td></tr>";
      return;
    }
    body.innerHTML = rows
      .map(function (r) {
        const badgeCls = r.source === "monthly_dues" ? "dues" : (r.action === "deposit" ? "deposit" : "withdraw");
        const source = esc(r.source || "other_transaction");
        const bankRef = String(r.reference_number || "");
        const colRef = String(r.collection_reference || "");
        const ref = colRef && bankRef ? colRef + " / " + bankRef : (colRef || bankRef);
        const refShort = ref ? (ref.length > 16 ? ref.slice(0, 16) + "…" : ref) : "—";
        return (
          "<tr>" +
          "<td>" + fmtDateStack(r.sort_at, r.date) + "</td>" +
          '<td><span class="ot-type-badge ' + badgeCls + '">' + esc(r.action_label) + "</span></td>" +
          '<td style="font-weight:700;font-variant-numeric:tabular-nums;" class="' + (r.action === "deposit" ? "text-success" : "text-danger") + '">' + (r.action === "deposit" ? "+" : "−") + peso(r.amount) + "</td>" +
          '<td style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:120px;" title="' + esc(ref) + '">' + esc(refShort) + "</td>" +
          '<td><button type="button" class="ot-proof-btn" onclick="window.nxShowTxDetail(\'' + source + '\',' + Number(r.id) + ')">View Details</button></td>' +
          "</tr>"
        );
      })
      .join("");
  }

  function fmtWhen(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return esc(String(iso));
    return d.toLocaleString(undefined, {
      year: "numeric", month: "short", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  }

  function detailField(label, value) {
    return (
      '<div style="display:flex;flex-direction:column;gap:2px;min-width:0;">' +
        '<span style="font-size:0.66rem;text-transform:uppercase;letter-spacing:0.03em;color:#8a949e;">' + esc(label) + "</span>" +
        '<b style="font-size:0.82rem;color:#1f2937;overflow-wrap:anywhere;">' + value + "</b>" +
      "</div>"
    );
  }

  function milestoneCell(label, iso, pendingText) {
    const done = !!iso;
    return (
      '<div style="display:flex;flex-direction:column;gap:3px;padding:8px 10px;border-radius:8px;border:1px solid ' +
        (done ? "#c8e6c9;background:#f3faf4;" : "#e5e7eb;background:#f9fafb;") + '">' +
        '<span style="font-size:0.66rem;text-transform:uppercase;letter-spacing:0.03em;color:' + (done ? "#1b5e20" : "#9ca3af") + ';">' +
          '<i class="fa-solid ' + (done ? "fa-circle-check" : "fa-clock") + '" style="margin-right:4px;"></i>' + esc(label) +
        "</span>" +
        '<b style="font-size:0.76rem;color:' + (done ? "#1f2937" : "#9ca3af") + ';">' + (done ? fmtWhen(iso) : esc(pendingText)) + "</b>" +
      "</div>"
    );
  }

  async function showTxDetail(source, id) {
    if (!window.SimpleModal) { toast("Details view is unavailable.", true); return; }
    SimpleModal.open({
      title: "Transaction Details",
      html: '<div class="empty-state">Loading transaction details…</div>',
      width: "700px",
    });
    try {
      const res = await fetch(
        "/api/treasurer/other-transactions/detail/" + encodeURIComponent(source) + "/" + Number(id) + "/",
        { credentials: "same-origin" }
      );
      const d = await res.json();
      if (!res.ok || !d.ok) throw new Error(d.error || "Failed to load details.");
      const det = d.detail || {};
      const isDues = det.source === "monthly_dues";

      const proofHtml = det.has_proof
        ? '<a href="' + esc(det.proof_url) + '" target="_blank" rel="noopener" style="color:#1565c0;text-decoration:underline;font-weight:600;">View attachment</a>'
        : '<span style="color:#8a949e;">—</span>';

      const summary =
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px 14px;">' +
          detailField("Transaction Type", esc(det.type_label || "—")) +
          (det.status_label ? detailField("Status", esc(det.status_label)) : "") +
          detailField("Amount", "<span style=\"color:" + (isDues ? "#1b5e20" : "#1f2937") + ";\">" + peso(det.amount) + "</span>") +
          detailField("Reference / Trace ID", esc(det.reference_number || "—")) +
          (det.collection_reference ? detailField("Collection Ref", esc(det.collection_reference)) : "") +
          (det.donor ? detailField("Donor / Source", esc(det.donor)) : "") +
          (det.recipient ? detailField("Recipient / Donee", esc(det.recipient)) : "") +
          detailField("Encoded By", esc(det.encoded_by || "Treasurer")) +
          detailField("Recorded", fmtWhen(det.recorded_at)) +
          detailField("Attachment", proofHtml) +
        "</div>";

      const what =
        '<div style="margin-top:12px;padding:10px 12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;font-size:0.83rem;color:#334155;line-height:1.5;">' +
          '<strong style="display:block;margin-bottom:3px;color:#0f172a;">What this transaction is about</strong>' +
          esc(det.description || "—") +
        "</div>";

      let html = summary + what;

      if (isDues) {
        const ms = det.milestones || {};
        html +=
          '<div style="margin-top:14px;">' +
            '<div style="font-weight:800;font-size:0.85rem;color:#1b5e20;margin-bottom:7px;">' +
              '<i class="fa-solid fa-flag-checkered" style="margin-right:6px;color:#2e7d32;"></i>Trace Milestones' +
            "</div>" +
            '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;">' +
              milestoneCell("Recorded", ms.recorded_at, "not recorded") +
              milestoneCell("Deposited", ms.deposited_at, "not deposited") +
              milestoneCell("Verified", ms.verified_at, "pending audit") +
              milestoneCell("Approved", ms.approved_at, "pending approval") +
            "</div>" +
          "</div>";

        const dep = det.deposit || {};
        const slipLinks = (dep.slips || []).length
          ? dep.slips.map((s, i) =>
              '<a href="' + esc(s.url) + '" target="_blank" rel="noopener" style="color:#1565c0;text-decoration:underline;font-weight:600;">Slip ' + (i + 1) + "</a>"
            ).join(" · ")
          : '<span style="color:#c62828;font-weight:700;">missing</span>';
        html +=
          '<div style="margin-top:12px;padding:11px 13px;border:1px solid #c5cae9;border-left:5px solid #283593;border-radius:8px;background:#f3f5ff;font-size:0.82rem;display:flex;gap:16px;flex-wrap:wrap;">' +
            "<div><strong>Deposit Ref:</strong> " + esc(dep.reference || "—") + "</div>" +
            "<div><strong>Amount:</strong> " + (dep.amount != null ? peso(dep.amount) : "—") + "</div>" +
            "<div><strong>Deposited:</strong> " + fmtWhen(dep.deposited_at) + (dep.deposited_by ? " by " + esc(dep.deposited_by) : "") + "</div>" +
            "<div><strong>Slip:</strong> " + slipLinks + "</div>" +
          "</div>";

        const logs = det.workflow_logs || [];
        html +=
          '<div style="margin-top:14px;">' +
            (window.mdWorkflowTimelineHtml
              ? window.mdWorkflowTimelineHtml(logs)
              : '<div style="font-weight:800;font-size:0.85rem;color:#1b5e20;margin-bottom:7px;">Workflow History</div>' +
                (logs.length
                  ? logs.map((l) =>
                      '<div style="font-size:0.78rem;padding:5px 0;border-bottom:1px dashed #e5e7eb;">' +
                        "<b>" + esc(l.action.replace(/_/g, " ")) + "</b> — " + esc(l.notes || "") +
                        '<span style="color:#8a949e;"> · ' + (l.performed_by ? esc(l.performed_by) + " · " : "") + fmtWhen(l.created_at) + "</span>" +
                      "</div>"
                    ).join("")
                  : '<div style="color:#8a949e;font-size:0.8rem;">No workflow activity recorded yet.</div>')) +
          "</div>";
      }

      // Replace the loading layer's content in place (stacked modals: close the
      // loading one first, then show the populated modal).
      SimpleModal.close();
      SimpleModal.open({ title: det.title || "Transaction Details", html: html, width: "700px" });
    } catch (e) {
      SimpleModal.close();
      toast(e.message || "Could not load transaction details.", true);
    }
  }

  window.nxShowTxDetail = showTxDetail;

  async function load(silent) {
    const body = document.getElementById("ot-history-body");
    if (body && !silent) body.innerHTML = '<tr><td colspan="5"><div class="empty-state">Loading transaction history…</div></td></tr>';
    try {
      const res = await fetch(LIST_URL, { credentials: "same-origin" });
      const d = await res.json();
      if (!d.ok) throw new Error(d.error || "Failed to load history.");
      txRows = d.entries || [];
      renderHistory();
      const tc = document.getElementById("ot-total-collected");
      const td = document.getElementById("ot-total-deposit");
      const tw = document.getElementById("ot-total-withdraw");
      const net = document.getElementById("ot-net");
      if (tc) tc.textContent = peso(d.total_collected || 0);
      if (td) td.textContent = peso(d.total_deposited);
      if (tw) tw.textContent = peso(d.total_withdrawn);
      if (net) net.textContent = peso(d.net);
    } catch (e) {
      if (body) body.innerHTML = '<tr><td colspan="5"><div class="empty-state">' + esc(e.message || "Could not load history.") + "</div></td></tr>";
    }
  }

  function resetForm() {
    const amount = document.getElementById("ot-amount");
    const desc = document.getElementById("ot-description");
    const donor = document.getElementById("ot-donor");
    const recip = document.getElementById("ot-recipient");
    const input = document.getElementById("ot-proof");
    const nameEl = document.getElementById("ot-proof-name");
    if (amount) { amount.value = ""; amount.readOnly = false; }
    if (desc) desc.value = "";
    if (donor) donor.value = "";
    if (recip) recip.value = "";
    if (input) input.value = "";
    if (nameEl) {
      nameEl.style.display = "none";
      nameEl.textContent = "";
    }
    selectAction("deposit");
  }

  async function record() {
    await recordOneOff(document.getElementById("ot-submit"));
  }

  function init() {
    if (window.nxOtherTransactions) return;
    bindForm();
    if (document.getElementById("treasurer-other-transactions")) {
      load();
    }
    window.nxOtherTransactions = {
      load: load,
      record: record,
      resetForm: resetForm,
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
