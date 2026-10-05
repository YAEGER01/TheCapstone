function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(";").shift();
  return "";
}

(function () {
  function byId(id) {
    return document.getElementById(id);
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatCurrencyPHP(num) {
    const n = typeof num === "number" ? num : parseFloat(num || 0);
    return new Intl.NumberFormat("en-PH", {
      style: "currency",
      currency: "PHP",
    }).format(n);
  }

  function formatMemberDisplayName(value) {
    const parts = String(value || "").trim().split(/\s+/).filter(Boolean);
    if (parts.length < 2) return parts.join(" ");
    const last = parts.pop();
    const first = parts.shift();
    const middle = parts.map((part) => {
      const clean = part.replace(/[^A-Za-z.]/g, "");
      return clean.length === 1 ? clean.toUpperCase() + "." : clean;
    }).filter(Boolean).join(" ");
    return `${last}, ${first}${middle ? ` ${middle}` : ""}`;
  }

  let historyViewMode = "batch";
  let salaryHistoryPage = 1;
  const salaryHistoryPageSize = 10;

  async function apiGetOtcDues() {
    const res = await fetch("/api/treasurer/monthly-dues/otc/list/", {
      method: "GET",
      credentials: "same-origin",
    });
    return res.json();
  }

  async function apiAddOtcDues(formData) {
    const res = await fetch("/api/treasurer/monthly-dues/otc/add/", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: formData,
    });
    return res.json();
  }

  function renderOtcTable(rows) {
    const table = byId("otcTable");
    if (!table) return;
    const actualTbody = table.querySelector("tbody");
    if (!actualTbody) return;

    actualTbody.innerHTML = "";

    if (!rows || rows.length === 0) {
      actualTbody.innerHTML =
        '<tr><td colspan="5" style="text-align:center;color:#757575;">No OTC dues payments recorded</td></tr>';
      return;
    }

    rows.forEach((o) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td style="font-weight:600;color:#1b5e20;">${escapeHtml(o.ref || "")}</td>
        <td>${escapeHtml(formatMemberDisplayName(o.member_name || ""))} <br><span style="font-size:0.75rem;color:#757575;">Code: ${escapeHtml(o.member_id || "")}</span></td>
        <td><span class="badge-zero badge-green" style="font-size:0.75rem;">${escapeHtml(o.month || "")}</span></td>
        <td style="font-weight:600;">${escapeHtml(formatCurrencyPHP(o.amount))}</td>
        <td>${escapeHtml(o.method || "")} <br><span style="font-size:0.75rem;color:#757575;">Date: ${escapeHtml(o.date || "")}</span></td>
      `;
      actualTbody.appendChild(tr);
    });
  }

  async function apiGetSalaryDues() {
    const res = await fetch("/api/treasurer/monthly-dues/salary/list/", {
      method: "GET",
      credentials: "same-origin",
    });
    return res.json();
  }

  async function apiAddSalaryDues(formData) {
    const res = await fetch("/api/treasurer/monthly-dues/salary/add/", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: formData,
    });
    return res.json();
  }

  function renderSalaryTable(data) {
    const table = byId("salaryTable");
    if (!table) return;
    const thead = byId("salaryTableHead");
    const tbody = table.querySelector("tbody");
    if (!thead || !tbody) return;

    if (historyViewMode === "batch") {
      const batches = data.batches || [];
      renderSalaryBatchView(thead, tbody, batches.slice((salaryHistoryPage - 1) * salaryHistoryPageSize, salaryHistoryPage * salaryHistoryPageSize));
      renderSalaryHistoryPagination(batches.length);
    } else {
      const rows = data.salary_dues || [];
      renderSalaryListView(thead, tbody, rows.slice((salaryHistoryPage - 1) * salaryHistoryPageSize, salaryHistoryPage * salaryHistoryPageSize));
      renderSalaryHistoryPagination(rows.length);
    }
  }

  function renderSalaryHistoryPagination(total) {
    const container = byId("salary-history-pagination");
    if (!container) return;
    const pages = Math.max(1, Math.ceil(total / salaryHistoryPageSize));
    salaryHistoryPage = Math.min(salaryHistoryPage, pages);
    container.innerHTML = pages > 1
      ? `<button type="button" class="btn-brand" ${salaryHistoryPage === 1 ? "disabled" : ""} data-salary-page="prev">Previous</button><span>Page ${salaryHistoryPage} of ${pages}</span><button type="button" class="btn-brand" ${salaryHistoryPage === pages ? "disabled" : ""} data-salary-page="next">Next</button>`
      : "";
    const previous = container.querySelector('[data-salary-page="prev"]');
    const next = container.querySelector('[data-salary-page="next"]');
    if (previous) previous.addEventListener("click", () => {
      salaryHistoryPage -= 1;
      fetchSalaryHistory();
    });
    if (next) next.addEventListener("click", () => {
      salaryHistoryPage += 1;
      fetchSalaryHistory();
    });
  }

  function renderSalaryBatchView(thead, tbody, batches) {
    const table = thead.closest("table");
    if (table) table.classList.add("salary-table-batch");
    if (table) table.classList.remove("salary-table-list");
    thead.innerHTML = `
      <tr>
        <th>Month</th>
        <th>Members</th>
        <th>Total Amount</th>
        <th>Action</th>
      </tr>
    `;
    tbody.innerHTML = "";

    if (!batches || batches.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="4" style="text-align:center;color:#757575;">No batches recorded</td></tr>';
      return;
    }

    batches.forEach((b) => {
      const tr = document.createElement("tr");
      tr.className = "salary-batch-row";
      tr.style.cursor = "pointer";
      tr.innerHTML = `
        <td><span class="badge-zero badge-green" style="font-size:0.75rem;">${escapeHtml(b.month || "")}</span></td>
        <td>${b.member_count} member${b.member_count !== 1 ? "s" : ""}</td>
        <td style="font-weight:600;">${escapeHtml(formatCurrencyPHP(b.total_amount))}</td>
        <td><button type="button" class="btn-brand btn-brand-secondary batch-view-details">View Details</button></td>
      `;
      tr.querySelector(".batch-view-details").addEventListener(
        "click",
        function (e) {
          e.stopPropagation();
          showBatchDetailModal(b);
        },
      );
      tr.addEventListener("click", function () {
        showBatchDetailModal(b);
      });
      tbody.appendChild(tr);
    });
  }

  function renderSalaryListView(thead, tbody, rows) {
    const table = thead.closest("table");
    if (table) table.classList.add("salary-table-list");
    if (table) table.classList.remove("salary-table-batch");
    thead.innerHTML = `
      <tr>
        <th>Reference #</th>
        <th>Member</th>
        <th>Month</th>
        <th>Expected Dues</th>
        <th>Accounting Remarks</th>
        <th>Audit</th>
      </tr>
    `;
    tbody.innerHTML = "";

    if (!rows || rows.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="6" style="text-align:center;color:#757575;">No salary deduction remittances recorded</td></tr>';
      return;
    }

    rows.forEach((s) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td style="font-weight:600;color:#1b5e20;">${escapeHtml(s.ref || "")}</td>
        <td>${escapeHtml(formatMemberDisplayName(s.member_name || ""))} <br><span style="font-size:0.75rem;color:#757575;">Code: ${escapeHtml(s.member_id || "")}</span></td>
        <td><span class="badge-zero badge-green" style="font-size:0.75rem;">${escapeHtml(s.month || "")}</span></td>
        <td style="font-weight:600;">${escapeHtml(formatCurrencyPHP(s.amount))}</td>
        <td style="font-weight:600;">${escapeHtml(s.remarks || "")}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  function showBatchDetailModal(batch) {
    const modal = byId("batchDetailModal");
    const title = byId("batchDetailTitle");
    const content = byId("batchDetailContent");
    if (!modal || !title || !content) return;

    title.textContent = "Batch Details";

    let html = `
      <div class="batch-detail-meta">
        <div><strong>Batch Reference:</strong> ${escapeHtml(batch.batch_reference || "N/A")}</div>
        <div><strong>Processed By:</strong> ${escapeHtml(batch.recorded_by || "Unknown")}</div>
      </div>
      <div class="batch-detail-summary">
        <div class="batch-detail-summary-card">
          <span>Month</span>
          <strong>${escapeHtml(batch.month || "")}</strong>
        </div>
        <div class="batch-detail-summary-card">
          <span>Members</span>
          <strong>${batch.member_count}</strong>
        </div>
        <div class="batch-detail-summary-card">
          <span>Total Amount</span>
          <strong>${escapeHtml(formatCurrencyPHP(batch.total_amount))}</strong>
        </div>
      </div>
    `;

    const members = batch.members || [];
    if (members.length === 0) {
      html += '<p style="color:#757575;">No members in this batch.</p>';
    } else {
      html += `
        <div class="batch-detail-table-wrap">
          <table class="custom-table batch-detail-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Member Name</th>
                <th>Amount</th>
              </tr>
            </thead>
            <tbody>
      `;
      members.forEach((m, idx) => {
        html += `
          <tr>
            <td>${idx + 1}</td>
            <td>${escapeHtml(formatMemberDisplayName(m.member_name || ""))}</td>
            <td>${escapeHtml(formatCurrencyPHP(m.amount))}</td>
          </tr>
        `;
      });
      html += `
            </tbody>
          </table>
        </div>
      `;
    }

    content.innerHTML = html;
    modal.style.display = "flex";
  }

  function closeBatchDetailModal() {
    const modal = byId("batchDetailModal");
    if (modal) modal.style.display = "none";
  }
  window.closeBatchDetailModal = closeBatchDetailModal;

  async function fetchSalaryHistory() {
    const list = await apiGetSalaryDues();
    if (!list || !list.ok) {
      showToast(
        list && list.error
          ? list.error
          : "Failed to refresh salary deduction history.",
        true,
      );
      return;
    }
    renderSalaryTable(list);
    window.db = window.db || {};
    window.db.salary_deductions = list.salary_dues || [];
    window.db.salary_batches = list.batches || [];
    if (typeof window.saveSystemDatabase === "function")
      window.saveSystemDatabase();
    if (typeof window.updateKPICards === "function") window.updateKPICards();
  }

  async function fetchAndRenderOtc() {
    const list = await apiGetOtcDues();
    if (!list || !list.ok) {
      showToast(
        list && list.error ? list.error : "Failed to refresh OTC dues.",
        true,
      );
      return;
    }
    renderOtcTable(list.otc_dues || []);
    window.db = window.db || {};
    window.db.otc_dues = list.otc_dues || [];
    if (typeof window.saveSystemDatabase === "function")
      window.saveSystemDatabase();
    if (typeof window.updateKPICards === "function") window.updateKPICards();
  }

  async function fetchMembers() {
    const resp = await fetch("/api/treasurer/members/list/", {
      method: "GET",
      credentials: "same-origin",
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      throw new Error((data && data.error) || "Failed to load members.");
    }
    return data.members || [];
  }

  function populateDuesDropdowns(members) {
    ["otc_member", "sal_member"].forEach((id) => {
      const sel = byId(id);
      if (!sel) return;
      sel.innerHTML = '<option value="">Select Associated Member</option>';
      [...members].sort((a, b) =>
        formatMemberDisplayName(a.full_name).localeCompare(
          formatMemberDisplayName(b.full_name), undefined, { sensitivity: "base" }
        )
      ).forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m.member_id;
        opt.textContent = formatMemberDisplayName(m.full_name);
        sel.appendChild(opt);
      });
    });
  }

  // ---------------------------------------------------------------------------
  // Month dropdown (otc_month / sal_month)
  //
  // The member selects are populated by TWO sources whose option values differ:
  // this script writes raw member PKs ("123") while the inline dashboard
  // populateDropdowns() writes display codes ("M-123") — whichever finishes
  // last wins. The unpaid-months API requires a numeric id, so normalize
  // before every call, and never leave the dropdown stuck disabled: on load
  // failure it stays enabled with a "click to retry" option.
  // ---------------------------------------------------------------------------

  const MONTHS_PER_PAGE = 12;
  const monthSelectState = new WeakMap();

  function monthState(select) {
    let st = monthSelectState.get(select);
    if (!st) {
      st = { seq: 0, requestedMember: "", loadedMember: "", months: [], page: 0, totalPages: 0 };
      monthSelectState.set(select, st);
    }
    return st;
  }

  function normalizeMemberId(value) {
    const digits = String(value || "").replace(/^M-/i, "").replace(/[^0-9]/g, "");
    return digits || "";
  }

  function resetMonthSelect(select, optionText, disabled, title) {
    select.innerHTML = `<option value="">${optionText}</option>`;
    select.disabled = disabled;
    select.value = "";
    select.title = title || "";
  }

  // Fetch unpaid months for a member and populate month dropdown
  async function loadUnpaidMonthsForMember(memberId, monthInputId) {
    const monthSelect = byId(monthInputId);
    if (!monthSelect || monthSelect.tagName !== "SELECT") return;

    const state = monthState(monthSelect);
    const normalizedId = normalizeMemberId(memberId);

    // No member selected -> lock the month dropdown
    if (!normalizedId) {
      state.seq += 1;
      state.requestedMember = "";
      state.loadedMember = "";
      state.months = [];
      state.totalPages = 0;
      resetMonthSelect(monthSelect, "-- Select a member first --", true, "Select a member to load their unpaid months");
      return;
    }

    state.seq += 1;
    const seq = state.seq;
    state.requestedMember = normalizedId;

    resetMonthSelect(monthSelect, "Loading months...", true, "Loading available months");

    let data = null;
    try {
      const resp = await fetch(`/api/treasurer/member/${normalizedId}/unpaid-months/`, {
        method: "GET",
        credentials: "same-origin",
      });
      data = await resp.json();
    } catch (err) {
      console.error("Error loading unpaid months:", err);
      data = null;
    }

    // A newer request superseded this one — drop the stale response.
    if (seq !== state.seq) return;

    const months = data && data.ok && Array.isArray(data.unpaid_months) ? data.unpaid_months : null;

    if (!months) {
      // Failure: keep the dropdown ENABLED with a retry option so the user is
      // never stuck with a dead control. Focusing/clicking it retries.
      state.loadedMember = "";
      state.months = [];
      state.totalPages = 0;
      monthSelect.innerHTML = '<option value="">Couldn\u2019t load months \u2014 click to retry</option>';
      monthSelect.disabled = false;
      monthSelect.value = "";
      monthSelect.title = "Click to retry loading available months";
      return;
    }

    if (months.length === 0) {
      state.loadedMember = normalizedId;
      state.months = [];
      state.totalPages = 0;
      resetMonthSelect(monthSelect, "All months have been paid", true, "All months have been paid for this member");
      return;
    }

    state.months = months;
    state.page = 0;
    state.totalPages = Math.ceil(months.length / MONTHS_PER_PAGE);
    state.loadedMember = normalizedId;
    monthSelect.disabled = false;
    monthSelect.title = `${months.length} unpaid month(s) available`;
    renderMonthPage(monthSelect, state);
  }

  function renderMonthPage(select, state) {
    const startIndex = state.page * MONTHS_PER_PAGE;
    const pageMonths = state.months.slice(startIndex, startIndex + MONTHS_PER_PAGE);

    select.innerHTML = '<option value="">-- Select a month --</option>';

    pageMonths.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m.value;
      opt.textContent = m.label + (m.is_overdue ? " (Overdue)" : m.is_advance ? " (Advance)" : "");
      select.appendChild(opt);
    });

    if (state.totalPages > 1) {
      const separator = document.createElement("option");
      separator.disabled = true;
      separator.textContent = `Page ${state.page + 1} of ${state.totalPages}`;
      select.appendChild(separator);

      if (state.page > 0) {
        const prevOpt = document.createElement("option");
        prevOpt.value = "__PREV_PAGE__";
        prevOpt.textContent = "\u2190 Previous";
        select.appendChild(prevOpt);
      }

      if (state.page < state.totalPages - 1) {
        const nextOpt = document.createElement("option");
        nextOpt.value = "__NEXT_PAGE__";
        nextOpt.textContent = "Next \u2192";
        select.appendChild(nextOpt);
      }
    }

    select.value = "";
  }

  function attachMonthHandlers(monthSelect, monthSelId) {
    // Property assignment (not addEventListener) is idempotent: re-running on
    // every Turbo navigation never stacks duplicate handlers.
    monthSelect.onchange = function () {
      const state = monthSelectState.get(this);
      if (!state) return;
      if (this.value === "__PREV_PAGE__" || this.value === "__NEXT_PAGE__") {
        state.page += this.value === "__NEXT_PAGE__" ? 1 : -1;
        renderMonthPage(this, state);
      }
    };

    // Auto-retry a failed load as soon as the user interacts with the dropdown.
    monthSelect.onfocus = function () {
      const state = monthSelectState.get(this);
      if (state && state.requestedMember && !state.loadedMember && !this.disabled) {
        loadUnpaidMonthsForMember(state.requestedMember, monthSelId);
      }
    };
  }

  // Attach member -> month loader listeners. Safe to call on every init.
  function attachMonthValidationListeners() {
    [["otc_member", "otc_month"], ["sal_member", "sal_month"]].forEach(
      ([memberSelId, monthSelId]) => {
        const memberSelect = byId(memberSelId);
        const monthSelect = byId(monthSelId);
        if (!memberSelect || !monthSelect) return;

        memberSelect.onchange = function () {
          loadUnpaidMonthsForMember(this.value, monthSelId);
        };

        monthState(monthSelect);
        attachMonthHandlers(monthSelect, monthSelId);
      },
    );
  }

  function init() {
    FileQueue.init("otc", { inputId: "otc_file_input", containerId: "otc_file_queue", maxFiles: 1 });
    FileQueue.init("sal", { inputId: "sal_file_input", containerId: "sal_file_queue", maxFiles: 1 });
    FileQueue.init("bulk", { inputId: "bulk_file_input", containerId: "bulk_file_queue", maxFiles: 1 });

    window.fetchSalaryHistory = fetchSalaryHistory;

    // --- Event listener setup (runs only once to avoid duplicate listeners) ---
    if (!window._monthlyDuesListenersAttached) {
      window._monthlyDuesListenersAttached = true;

      // OTC
      const otcForm = byId("otcDuesForm");
      if (otcForm) {
        otcForm.removeAttribute("onsubmit");

        otcForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          try {
            const formData = new FormData(otcForm);
            var otcFiles = FileQueue.getFiles("otc");
            if (otcFiles.length > 0) formData.append("otc_photo_file", otcFiles[0]);

            const out = await apiAddOtcDues(formData);
            if (!out || !out.ok) {
              showToast(
                out && out.error ? out.error : "Failed to record OTC dues.",
                true,
              );
              return;
            }

            showToast("Over-the-Counter Monthly Dues recorded.", false);
            await fetchAndRenderOtc();
            otcForm.reset();
            FileQueue.clear("otc");
            loadUnpaidMonthsForMember("", "otc_month");
          } catch (err) {
            showToast("Network/server error while recording OTC dues.", true);
          }
        });
      }

      // Salary global handler
      window.handleSalarySubmit = async function handleSalarySubmit(event) {
        event.preventDefault();
        const salaryForm = byId("salaryForm");
        if (!salaryForm) return;

        const salRefInput = byId("sal_ref");
        const salRefValue = salRefInput ? (salRefInput.value || "").trim() : "";

        try {
          const formData = new FormData(salaryForm);
          if (salRefValue) {
            formData.set("sal_ref", salRefValue);
          }
          var salFiles = FileQueue.getFiles("sal");
          if (salFiles.length > 0) formData.append("sal_photo_file", salFiles[0]);

          const out = await apiAddSalaryDues(formData);
          if (!out || !out.ok) {
            showToast(
              out && out.error ? out.error : "Failed to record salary deduction.",
              true,
            );
            return;
          }

          showToast("Salary deduction remittance recorded.", false);
          await fetchSalaryHistory();
          salaryForm.reset();
          FileQueue.clear("sal");
          loadUnpaidMonthsForMember("", "sal_month");

          const preview = byId("sal_preview");
          if (preview) preview.style.display = "none";
        } catch (err) {
          showToast(
            "Network/server error while recording salary deduction.",
            true,
          );
        }
      };

      // History view toggle
      document.querySelectorAll(".history-view-toggle").forEach((btn) => {
        btn.addEventListener("click", function () {
          historyViewMode = this.dataset.view;
          salaryHistoryPage = 1;
          document.querySelectorAll(".history-view-toggle").forEach((b) => {
            b.classList.remove("btn-brand-primary");
            b.style.opacity = "0.7";
          });
          this.classList.add("btn-brand-primary");
          this.style.opacity = "1";
          const db = window.db || {};
          renderSalaryTable({
            salary_dues: db.salary_deductions || [],
            batches: db.salary_batches || [],
          });
        });
      });

      // --- Bulk Salary Deduction ---
      initBulkSalary();
    }

    // --- Data fetching (runs on every turbo:load) ---
    const otcForm = byId("otcDuesForm");
    if (otcForm) fetchAndRenderOtc().catch(() => {});

    const salaryTable = byId("salaryTable");
    if (salaryTable) fetchSalaryHistory().catch(() => {});

    // Re-attached on every load: Turbo body swaps replace the select elements,
    // so handlers must be (idempotently) bound against the current DOM.
    attachMonthValidationListeners();

    fetchMembers().then(populateDuesDropdowns).catch(() => {});
  }

  function initBulkSalary() {
    const bulkPanel = byId("salary-bulk-panel");
    if (!bulkPanel) return;

    // Tab switching
    document.querySelectorAll(".salary-tab-btn").forEach((btn) => {
      btn.addEventListener("click", function () {
        const tab = this.dataset.tab;
        document.querySelectorAll(".salary-tab-btn").forEach((b) => {
          b.classList.remove("btn-brand-primary");
          b.style.opacity = "0.7";
        });
        this.classList.add("btn-brand-primary");
        this.style.opacity = "1";

        const individualPanel = byId("salary-individual-panel");
        const bulkPanelEl = byId("salary-bulk-panel");
        if (individualPanel)
          individualPanel.style.display = tab === "individual" ? "" : "none";
        if (bulkPanelEl)
          bulkPanelEl.style.display = tab === "bulk" ? "" : "none";
        triggerPremiumGlow();
      });
    });

    // Auto-fetch batch ref on month selection
    const monthInput = byId("bulk_sal_month");
    if (monthInput) {
      monthInput.addEventListener("change", async function () {
        const display = byId("bulk_batch_ref_display");
        if (!this.value) {
          if (display) display.textContent = "\u2014";
          return;
        }
        try {
          const resp = await fetch(
            "/api/treasurer/monthly-dues/salary/next-batch-ref/?month=" +
              encodeURIComponent(this.value),
            { credentials: "same-origin" },
          );
          const data = await resp.json();
          if (data.ok && display) {
            display.textContent = data.next_batch_ref;
          }
        } catch {
          // silent fail
        }
      });
    }

    // Preview button
    const previewBtn = byId("bulk_preview_btn");
    const memberSection = byId("bulk-member-section");
    const memberTbody = byId("bulk-member-tbody");
    const memberCount = byId("bulk-member-count");
    const statusMsg = byId("bulk-status-msg");
    const processBtn = byId("bulk_process_btn");

    let previewData = { members: [], expected_amount: 0 };

    if (previewBtn) {
      previewBtn.addEventListener("click", async function () {
        const month = byId("bulk_sal_month");
        if (!month || !month.value) {
          showToast("Please select a deduction month.", true);
          return;
        }

        previewBtn.disabled = true;
        previewBtn.textContent = "Loading...";

        try {
          const fd = new FormData();
          fd.set("sal_month", month.value);
          const resp = await fetch(
            "/api/treasurer/monthly-dues/salary/bulk-preview/",
            {
              method: "POST",
              credentials: "same-origin",
              headers: { "X-CSRFToken": getCookie("csrftoken") },
              body: fd,
            },
          );
          const data = await resp.json();
          if (!data.ok) {
            showToast(data.error || "Preview failed.", true);
            previewBtn.disabled = false;
            previewBtn.textContent = "Preview Members";
            return;
          }

          previewData = data;
          renderBulkMemberTable(data);
          if (memberSection) memberSection.style.display = "block";
          const batchRefDisplay = byId("bulk_batch_ref_display");
          if (batchRefDisplay && data.next_batch_ref) {
            batchRefDisplay.textContent = data.next_batch_ref;
          }
          if (statusMsg) {
            const paid = data.already_processed || 0;
            const exempted = data.already_exempted || 0;
            const total = data.total_active || 0;
            let msg = `${total} active members`;
            if (paid > 0) msg += `, ${paid} already paid`;
            if (exempted > 0) msg += `, ${exempted} exempted`;
            statusMsg.textContent = msg;
          }
          updateProcessBtn();
        } catch (err) {
          showToast("Network error loading preview.", true);
        }

        previewBtn.disabled = false;
        previewBtn.textContent = "Preview Members";
      });
    }

    function updateBulkAmountBadge() {
      const perMemberEl = byId("bulk-per-member");
      const totalEl = byId("bulk-total-display");
      const totalAmountEl = byId("bulk-total-amount");
      if (!perMemberEl || !totalEl || !totalAmountEl) return;
      const amount = previewData.expected_amount || 0;
      perMemberEl.textContent = formatCurrencyPHP(amount).replace("₱", "");
      const checked = document.querySelectorAll("#bulk-member-tbody .bulk-member-cb:checked").length;
      if (checked > 0 && amount > 0) {
        totalEl.style.display = "inline";
        totalAmountEl.textContent = formatCurrencyPHP(amount * checked).replace("₱", "");
      } else {
        totalEl.style.display = "none";
      }
    }

    function renderBulkMemberTable(data) {
      if (!memberTbody) return;
      memberTbody.innerHTML = "";
      const members = data.members || [];
      if (memberCount) {
        memberCount.textContent = `${members.length} members`;
      }
      updateBulkAmountBadge();
      members.forEach((m) => {
        const tr = document.createElement("tr");
        let statusLabel = "";
        if (m.already_exists) {
          statusLabel = ' <span style="color:#d89600;font-size:0.75rem;font-weight:600;">[Already Paid]</span>';
        } else if (m.is_exempted) {
          statusLabel = ' <span style="color:#6200ea;font-size:0.75rem;font-weight:600;">[Exempted]</span>';
        }
        
        const isDisabled = m.already_exists || m.is_exempted;
        tr.innerHTML = `
          <td><input type="checkbox" class="bulk-member-cb" value="${m.member_id}" ${m.default_checked ? "checked" : ""} ${isDisabled ? "disabled" : ""}></td>
          <td>${escapeHtml(m.member_name)}${statusLabel}</td>
          <td>${escapeHtml(m.department || "—")}</td>
          <td>${escapeHtml(m.status || "—")}</td>
        `;
        memberTbody.appendChild(tr);
      });
    }

    // Select All / None / Invert
    const selectAllBtn = byId("bulk_select_all");
    const selectNoneBtn = byId("bulk_select_none");
    const selectInvertBtn = byId("bulk_select_invert");

    function getMemberCheckboxes() {
      return document.querySelectorAll("#bulk-member-tbody .bulk-member-cb");
    }

    function updateProcessBtn() {
      if (!processBtn) return;
      const checked = document.querySelectorAll(
        "#bulk-member-tbody .bulk-member-cb:checked",
      ).length;
      if (checked > 0) {
        processBtn.disabled = false;
        processBtn.textContent = `Process ${checked} Member${checked !== 1 ? "s" : ""}`;
      } else {
        processBtn.disabled = true;
        processBtn.textContent = "Process Members";
      }
      updateBulkAmountBadge();
    }

    if (selectAllBtn) {
      selectAllBtn.addEventListener("click", function () {
        getMemberCheckboxes().forEach((cb) => {
          if (!cb.disabled) cb.checked = true;
        });
        updateProcessBtn();
      });
    }
    if (selectNoneBtn) {
      selectNoneBtn.addEventListener("click", function () {
        getMemberCheckboxes().forEach((cb) => {
          if (!cb.disabled) cb.checked = false;
        });
        updateProcessBtn();
      });
    }
    if (selectInvertBtn) {
      selectInvertBtn.addEventListener("click", function () {
        getMemberCheckboxes().forEach((cb) => {
          if (!cb.disabled) cb.checked = !cb.checked;
        });
        updateProcessBtn();
      });
    }
    if (memberTbody) {
      memberTbody.addEventListener("change", function (e) {
        if (e.target.classList.contains("bulk-member-cb")) {
          updateProcessBtn();
        }
      });
    }

    // Process button
    if (processBtn) {
      processBtn.addEventListener("click", async function () {
        const month = byId("bulk_sal_month");
        const summary = byId("bulk_summary");

        if (!month || !month.value) {
          showToast("Please select a deduction month.", true);
          return;
        }

        const checkedIds = [];
        getMemberCheckboxes().forEach((cb) => {
          if (cb.checked && !cb.disabled) checkedIds.push(parseInt(cb.value));
        });

        if (checkedIds.length === 0) {
          showToast("No unpaid members selected. Already paid or exempted members are excluded.", true);
          return;
        }

        processBtn.disabled = true;
        processBtn.textContent = "Processing...";

        try {
          const fd = new FormData();
          fd.set("sal_month", month.value);
          fd.set("summary", summary ? summary.value.trim() : "");
          fd.set("member_ids", JSON.stringify(checkedIds));
          var bulkFiles = FileQueue.getFiles("bulk");
          if (bulkFiles.length > 0) fd.set("sal_photo_file", bulkFiles[0]);

          const resp = await fetch(
            "/api/treasurer/monthly-dues/salary/bulk-process/",
            {
              method: "POST",
              credentials: "same-origin",
              headers: { "X-CSRFToken": getCookie("csrftoken") },
              body: fd,
            },
          );
          const data = await resp.json();
          if (!data.ok) {
            showToast(data.error || "Bulk processing failed.", true);
            processBtn.disabled = false;
            processBtn.textContent = "Process Members";
            return;
          }

          showToast(
            `Created ${data.processed} salary deductions for ${data.month} — Batch Ref: ${data.batch_ref}`,
            false,
          );

          // Reset UI
          if (memberSection) memberSection.style.display = "none";
          if (memberTbody) memberTbody.innerHTML = "";
          if (statusMsg) statusMsg.textContent = "";
          if (month) month.value = "";
          const batchRefDisplay = byId("bulk_batch_ref_display");
          if (batchRefDisplay) batchRefDisplay.textContent = "";
          if (summary) summary.value = "";
          FileQueue.clear("bulk");
          const bulkPreview = byId("bulk_preview");
          if (bulkPreview) bulkPreview.style.display = "none";
          updateProcessBtn();
          previewData = { members: [], expected_amount: 0 };

          // Refresh history
          fetchSalaryHistory();
        } catch (err) {
          showToast(
            "Network error during bulk processing. Use Individual Entry tab as fallback.",
            true,
          );
          processBtn.disabled = false;
          processBtn.textContent = "Process Members";
        }
      });
    }

    // Month validation listeners are attached in init() on every load.

    triggerPremiumGlow();
  }

  function triggerPremiumGlow() {
    const btns = document.querySelectorAll(".salary-tab-btn");
    btns.forEach((b) => b.classList.add("premium-active"));
    setTimeout(() => {
      btns.forEach((b) => b.classList.remove("premium-active"));
    }, 2000);
  }

  window.addEventListener("turbo:load", init);
  document.addEventListener("turbo:before-cache", () => {
    window._monthlyDuesListenersAttached = false;
  });
})();
