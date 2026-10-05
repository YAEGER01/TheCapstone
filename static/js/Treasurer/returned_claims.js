// returned_claims.js — Returned Claims for the Treasurer (v2).
// List + filters, and a Fix panel: request details, uploaded documents (View),
// return reason, returned by/on, treasurer response notes, re-upload,
// resubmit to Auditor, or withdraw the request.
(function () {
  "use strict";

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

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
  }

  function toast(msg, isErr) {
    if (typeof window.showToast === "function") window.showToast(msg, !!isErr);
    else if (isErr) alert(msg);
  }

  const state = { rows: [], detail: null };

  /* ============================ LIST ============================ */

  function rowAmount(r) {
    if (r.type === "Medical Aid") {
      return Number(r.validated_aid_amount || 0) || Number(r.hospital_bill_amount || 0);
    }
    return Number(r.benefit_amount || 0) || Number(r.bill_amount || 0);
  }

  function passesDateFilter(dateStr) {
    const filter = (document.getElementById("nrcDateFilter") || {}).value || "";
    if (!filter || !dateStr) return filter !== "older" && filter !== "7" && filter !== "30" ? true : filter === "older";
    const d = new Date(dateStr);
    if (isNaN(d)) return filter === "older";
    const days = Math.floor((Date.now() - d.getTime()) / 86400000);
    if (filter === "7") return days <= 7;
    if (filter === "30") return days <= 30;
    if (filter === "older") return days > 30;
    return true;
  }

  window.nxReturnedClaims = {
    async load(silent) {
      const tbody = document.querySelector("#nxReturnedBody");
      if (!tbody) return;
      if (!silent) tbody.innerHTML = '<tr><td colspan="6"><div class="empty-state">Loading...</div></td></tr>';

      const [med, dth] = await Promise.all([
        getJSON("/api/treasurer/medical-aid/returned/list/"),
        getJSON("/api/treasurer/death-aid/returned/list/"),
      ]);

      state.rows = [];
      ((med && med.records) || []).forEach((r) =>
        state.rows.push({
          ref: r.display_id || "MED-" + r.record_id,
          recordId: r.record_id,
          table: "medical_aid",
          type: "Medical Aid",
          member: r.member_name || "",
          date: r.request_date || "",
          amount: rowAmount({ type: "Medical Aid", validated_aid_amount: r.validated_aid_amount, hospital_bill_amount: r.hospital_bill_amount }),
          status: r.status || "Returned",
          reason: r.rejection_reason || "Returned for revision",
          details: r.rejection_details || [],
          returnedBy: r.returned_by || "Auditor",
          returnedAt: r.returned_at || "",
          documents: r.documents || [],
          // editable fields (UPDATABLE_FIELDS)
          hospital_name: r.hospital_name || "",
          hospital_bill_amount: r.hospital_bill_amount || "",
          request_date: r.request_date || "",
        })
      );
      ((dth && dth.records) || []).forEach((r) =>
        state.rows.push({
          ref: r.display_id || "DTH-" + r.record_id,
          recordId: r.record_id,
          table: "death_aid",
          type: "Death Aid",
          member: r.member_name || "",
          date: r.claim_date || "",
          amount: Number(r.benefit_amount || 0) || Number(r.bill_amount || 0),
          status: r.status || "Returned",
          reason: r.rejection_reason || "Returned for revision",
          details: r.rejection_details || [],
          returnedBy: r.returned_by || "Auditor / President",
          returnedAt: r.returned_at || "",
          documents: r.documents || [],
          deceased_name: r.deceased_name || "",
          bill_amount: r.bill_amount || "",
          claim_date: r.claim_date || "",
        })
      );

      const dot = document.getElementById("returned-claims-dot");
      if (dot) {
        dot.textContent = state.rows.length > 0 ? state.rows.length : "";
        dot.style.display = state.rows.length ? "inline-flex" : "none";
      }

      this.renderList();
    },

    renderList() {
      const tbody = document.querySelector("#nxReturnedBody");
      if (!tbody) return;
      const type = (document.getElementById("nrcTypeFilter") || {}).value || "";
      const search = ((document.getElementById("nrcSearch") || {}).value || "").trim().toLowerCase();

      const rows = state.rows.filter(
        (r) =>
          (!type || r.type === type) &&
          passesDateFilter(r.date) &&
          (!search || (r.member + " " + r.ref).toLowerCase().includes(search))
      );

      if (!rows.length) {
        tbody.innerHTML =
          '<tr><td colspan="4"><div class="empty-state">No returned or rejected claims match — everything is in progress.</div></td></tr>';
        return;
      }

      tbody.innerHTML = rows
        .map(
          (r) => `<tr>
              <td><b>${esc(r.member)}</b></td>
              <td>${esc(r.type)}</td>
              <td><span class="badge pending">${esc(r.status)}</span></td>
              <td><button class="btn primary sm" onclick="window.nxReturnedClaims.fix('${esc(r.ref)}')">Fix</button></td>
            </tr>`
        )
        .join("");
    },

    /* ============================ FIX PANEL ============================ */

    fix(ref) {
      const row = state.rows.find((r) => r.ref === ref);
      if (!row) return;
      state.detail = row;
      this.renderDetail();
    },

    renderDetail() {
      const row = state.detail;
      const box = document.getElementById("nrcDetail");
      if (!box || !row) return;
      const isMed = row.table === "medical_aid";

      const details = isMed
        ? [
            ["Member", row.member],
            ["Patient / Beneficiary", row.member + " (Self)"],
            ["Type", "Medical Aid"],
            ["Hospital", row.hospital_name || "—"],
          ]
        : [
            ["Member", row.member],
            ["Type", "Death Aid"],
            ["Deceased", row.deceased_name || "—"],
            ["Date of Claim", row.claim_date || row.date || "—"],
          ];

      const docs = Array.isArray(row.documents) ? row.documents : [];
      const docsHtml = docs.length
        ? docs
            .map(
              (d, i) =>
                '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 12px;border:1px solid #e3ece3;border-radius:8px;font-size:0.8rem;">' +
                "<span><strong>" +
                esc(d.label || "Document") +
                (docs.length > 1 ? " #" + (i + 1) : "") +
                "</strong> <span style='color:#757575;'>" +
                esc(d.file_name || "") +
                "</span></span>" +
                "<a href='" +
                esc(d.url || "#") +
                "' target='_blank' rel='noopener' class='fq-view-btn' style='text-decoration:none;display:inline-flex;align-items:center;justify-content:center;padding:5px 14px;border-radius:8px;font-size:0.75rem;font-weight:600;background:#fff;border:1px solid #cfdccc;color:#1b5e20;'>View</a>" +
                "</div>"
            )
            .join("")
        : '<div style="font-size:0.8rem;color:#757575;">No documents were recorded for this claim.</div>';

      const notesHtml = (row.details || []).length
        ? row.details
            .map(
              (d) =>
                '<div style="padding:8px 12px;border-left:3px solid #e53935;background:rgba(229,57,53,0.04);font-size:0.8rem;color:#7f5a5a;margin-bottom:6px;">' +
                esc(typeof d === "string" ? d : d.message || JSON.stringify(d)) +
                "</div>"
            )
            .join("")
        : "";

      box.innerHTML = `
        <div class="pd-card" style="border-left:4px solid #e53935;">
          <div class="pd-card-head">
            <div>
              <div class="pd-card-title">RETURNED CLAIM</div>
              <div class="pd-card-sub">Review what was flagged, fix it, and resubmit for verification.</div>
            </div>
            <button class="pd-link-btn" onclick="window.nxReturnedClaims.closeDetail()">Back to list</button>
          </div>

          <div style="padding:16px 20px;display:flex;flex-direction:column;gap:16px;">
            <div>
              <div style="font-size:0.68rem;font-weight:700;letter-spacing:0.5px;color:#8a958a;text-transform:uppercase;margin-bottom:8px;">Request Details</div>
              <div style="display:grid;grid-template-columns:repeat(2, minmax(0,1fr));gap:12px 20px;">
                ${details
                  .map(
                    ([k, v]) =>
                      `<div><div style="font-size:0.62rem;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;color:#8a949e;">${esc(k)}</div><div style="font-size:0.84rem;font-weight:600;color:#101828;">${esc(v)}</div></div>`
                  )
                  .join("")}
              </div>
            </div>

            <div>
              <div style="font-size:0.68rem;font-weight:700;letter-spacing:0.5px;color:#8a958a;text-transform:uppercase;margin-bottom:8px;">Uploaded Documents</div>
              <div style="display:flex;flex-direction:column;gap:8px;">${docsHtml}</div>
            </div>

            <div style="border-top:1px solid #eef1ee;padding-top:14px;">
              <div style="font-size:0.68rem;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;color:#c62828;margin-bottom:8px;">Returned for Correction</div>
              <div style="padding:12px 14px;border-radius:10px;background:rgba(229,57,53,0.07);border:1px solid rgba(229,57,53,0.3);">
                <div style="font-size:0.8rem;color:#374151;margin-bottom:8px;">Returned by <strong>${esc(row.returnedBy || "Auditor")}</strong> on ${esc(row.returnedAt || "—")}</div>
                <div style="font-size:0.68rem;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;color:#c62828;margin-bottom:6px;">Return Reason</div>
                <div style="font-size:0.85rem;color:#8f3e3e;white-space:pre-line;">${esc(row.reason || "No reason was provided.")}</div>
              </div>
              ${notesHtml}
            </div>

            <div style="border-top:1px solid #eef1ee;padding-top:14px;">
              <div style="font-size:0.68rem;font-weight:700;letter-spacing:0.5px;color:#8a958a;text-transform:uppercase;margin-bottom:8px;">Treasurer Actions</div>

              <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-bottom:12px;">
                ${
                  isMed
                    ? `<div><label style="font-size:0.72rem;font-weight:600;color:#5f6b5f;display:block;margin-bottom:4px;">Hospital / Clinic</label><input type="text" id="nrc-edit-hospital" value="${esc(row.hospital_name)}" style="width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #cfdccc;border-radius:8px;font-size:0.82rem;"></div>
                       <div><label style="font-size:0.72rem;font-weight:600;color:#5f6b5f;display:block;margin-bottom:4px;">Corrected Hospital Bill (₱)</label><input type="number" step="0.01" id="nrc-edit-bill" value="${esc(row.hospital_bill_amount)}" style="width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #cfdccc;border-radius:8px;font-size:0.82rem;"></div>`
                    : `<div><label style="font-size:0.72rem;font-weight:600;color:#5f6b5f;display:block;margin-bottom:4px;">Deceased Name</label><input type="text" id="nrc-edit-deceased" value="${esc(row.deceased_name)}" style="width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #cfdccc;border-radius:8px;font-size:0.82rem;"></div>
                       <div><label style="font-size:0.72rem;font-weight:600;color:#5f6b5f;display:block;margin-bottom:4px;">Corrected Bill Amount (₱)</label><input type="number" step="0.01" id="nrc-edit-bill" value="${esc(row.bill_amount)}" style="width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #cfdccc;border-radius:8px;font-size:0.82rem;"></div>`
                }
              </div>

              <div style="margin-bottom:12px;">
                <label style="font-size:0.72rem;font-weight:600;color:#5f6b5f;display:block;margin-bottom:4px;">Re-upload Documents <span style="font-weight:400;color:#9ca3af;">(optional — attaches on resubmit)</span></label>
                <div style="display:flex;align-items:center;">
                  <button type="button" class="file-queue-btn" onclick="document.getElementById('nrc_file_input').click()">+ Upload File</button>
                </div>
                <input type="file" id="nrc_file_input" multiple accept="image/*,.pdf,.docx" style="display:none" onchange="FileQueue.handleInput('nrc_files')" />
                <div id="nrc_file_queue" class="file-queue"></div>
              </div>

              <div style="margin-bottom:14px;">
                <label style="font-size:0.72rem;font-weight:600;color:#5f6b5f;display:block;margin-bottom:4px;">Treasurer's Response Notes (clarify what you fixed)</label>
                <textarea id="nrc-notes" rows="3" style="width:100%;box-sizing:border-box;padding:9px 11px;border:1px solid #cfdccc;border-radius:8px;font-size:0.85rem;" placeholder="e.g., Secured an updated bill totaling ₱22,000 — attached above."></textarea>
              </div>

              <div style="display:flex;gap:10px;flex-wrap:wrap;">
                <button type="button" class="btn-brand btn-brand-secondary" onclick="window.nxReturnedClaims.closeDetail()">Cancel</button>
                <button type="button" class="btn-brand btn-brand-secondary" style="background:rgba(229,57,53,0.08);color:#c62828;border:1px solid rgba(229,57,53,0.35);" onclick="window.nxReturnedClaims.withdraw()">Withdraw Request</button>
                <button type="button" class="btn-brand btn-brand-primary" style="margin-left:auto;" onclick="window.nxReturnedClaims.resubmit()">Resubmit</button>
              </div>
            </div>
          </div>
        </div>`;

      if (window.FileQueue) {
        window.FileQueue.init("nrc_files", {
          inputId: "nrc_file_input",
          containerId: "nrc_file_queue",
          maxFiles: 10,
          accept: "image/*,.pdf,.docx",
          mode: "rows",
        });
      }

      box.style.display = "block";
      box.scrollIntoView({ behavior: "smooth", block: "nearest" });
    },

    closeDetail() {
      state.detail = null;
      const box = document.getElementById("nrcDetail");
      if (box) {
        box.style.display = "none";
        box.innerHTML = "";
      }
      if (window.FileQueue) window.FileQueue.clear("nrc_files");
    },

    /* ============================ ACTIONS ============================ */

    async withdraw() {
      const row = state.detail;
      if (!row) return;
      try {
        const yes = await SimpleModal.confirm(
          "Withdraw this claim? It will be closed and will no longer proceed through the process.",
          { title: "Withdraw Request", okText: "Yes, withdraw", danger: true }
        );
        if (!yes) return;
      } catch (e) {
        return;
      }
      try {
        const res = await fetch("/api/treasurer/aid/withdraw/", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") },
          body: JSON.stringify({ target_id: row.ref }),
        });
        const data = await res.json().catch(() => ({}));
        if (data && data.ok) {
          toast("Request withdrawn. The member has been notified.", false);
          this.closeDetail();
          this.load();
        } else {
          toast((data && data.error) || "Failed to withdraw the request.", true);
        }
      } catch (e) {
        toast("Network error while withdrawing.", true);
      }
    },

    async resubmit() {
      const row = state.detail;
      if (!row) return;
      const isMed = row.table === "medical_aid";
      const notes = ((document.getElementById("nrc-notes") || {}).value || "").trim();
      const files = window.FileQueue ? window.FileQueue.getFiles("nrc_files") : [];

      const fd = new FormData();
      fd.append("treasurer_notes", notes);
      fd.append("same_auditor", "true");
      if (isMed) {
        fd.append("hospital_name", ((document.getElementById("nrc-edit-hospital") || {}).value || "").trim());
        fd.append("hospital_bill_amount", ((document.getElementById("nrc-edit-bill") || {}).value || "").trim());
      } else {
        fd.append("deceased_name", ((document.getElementById("nrc-edit-deceased") || {}).value || "").trim());
        fd.append("bill_amount", ((document.getElementById("nrc-edit-bill") || {}).value || "").trim());
      }
      files.forEach((f) => fd.append(isMed ? "ma_returned_photo_file" : "da_returned_photo_file", f));

      const btns = document.querySelectorAll("#nrcDetail button");
      btns.forEach((b) => (b.disabled = true));
      try {
        const res = await fetch(`/api/treasurer/resubmit/${row.table}/${row.recordId}/`, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": getCookie("csrftoken") },
          body: fd,
        });
        const data = await res.json().catch(() => ({}));
        if (data && data.ok) {
          toast("Claim resubmitted to the Auditor. You can track it in the verification queue.", false);
          this.closeDetail();
          this.load();
        } else {
          toast((data && data.error) || "Failed to resubmit the claim.", true);
        }
      } catch (e) {
        toast("Network error while resubmitting.", true);
      } finally {
        btns.forEach((b) => (b.disabled = false));
      }
    },
  };

  // Refresh on load + whenever the module is opened from the sidebar.
  document.addEventListener("turbo:load", () => window.nxReturnedClaims.load());
  if (document.readyState !== "loading") window.nxReturnedClaims.load();
  else document.addEventListener("DOMContentLoaded", () => window.nxReturnedClaims.load());
  if (!window.__nxReturnedClaimsClickBound) {
    window.__nxReturnedClaimsClickBound = true;
    document.addEventListener("click", function (e) {
      const el = e.target.closest && e.target.closest('[data-target="treasurer-returned-claims"]');
      if (el) setTimeout(() => window.nxReturnedClaims.load(), 200);
    });
  }
})();
