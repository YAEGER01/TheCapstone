// aid_verify_new.js — NEW "Verify Aid Requests" module for the Auditor.
// Clean queue + claim detail with the "Documents to Verify" section.
// Forward = Verified (goes to President), Return = Returned (back to Treasurer).
(function () {
  "use strict";

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

  const REQUIRED_DOCS = {
    medical_aid: ["request_letter", "hospital_bill"],
    death_aid: [],
  };

  const LABELS = {
    request_letter: "Request Letter",
    hospital_bill: "Hospital Bill",
    other: "Other Supporting Document",
    uncategorized: "Uncategorized Upload",
  };

  const state = { items: [], selected: null };

  async function getJSON(url) {
    try {
      const res = await fetch(url, { credentials: "same-origin" });
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  function toast(msg, isErr) {
    if (typeof window.showToast === "function") window.showToast(msg, !!isErr);
    else if (isErr) alert(msg);
  }

  function isMedical(item) {
    return item.aid_type === "medical_aid" || item.type === "Medical Aid Request";
  }

  function docsBadge(item) {
    const docs = Array.isArray(item.documents) ? item.documents : [];
    const req = REQUIRED_DOCS[item.aid_type] || [];
    const missing = req.filter((t) => !docs.some((d) => d.document_type === t));
    if (item.aid_type === "death_aid") return '<span style="color:#0d47a1;font-size:0.75rem;">No docs needed</span>';
    if (!docs.length) return '<span style="color:#c62828;font-size:0.75rem;">No docs</span>';
    return missing.length
      ? `<span style="color:#c62828;font-size:0.75rem;">Missing ${missing.length}</span>`
      : '<span style="color:#2e7d32;font-size:0.75rem;">✓ Complete</span>';
  }

  // Silent mode (background realtime refresh) skips the Loading flash so
  // the queue updates in place without flicker every few seconds.
  async function load(silent) {
    const tbody = document.querySelector("#avr_queue tbody");
    if (!tbody) return;
    if (!silent) tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#757575;">Loading...</td></tr>';
    const data = await getJSON("/api/auditor/pending-aids/list/");
    state.items = (data && data.aids) || [];
    if (!state.items.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#757575;">No pending aid claims for audit review.</td></tr>';
      clearDetail();
      return;
    }
    tbody.innerHTML = state.items
      .map(
        (it, i) => `
        <tr style="cursor:pointer;" onclick="window.nxVerifyAid.select(${i})">
          <td>${esc(it.type)}</td>
          <td>${esc((it.member && it.member.member_name) || "")}</td>
          <td>${esc(it.request_date || it.claim_date || it.date || "—")}</td>
          <td>${peso(isMedical(it) ? it.total_hospital_bill || it.bill : it.bill_amount)}</td>
          <td>${docsBadge(it)}</td>
        </tr>`
      )
      .join("");
  }

  function clearDetail() {
    state.selected = null;
    const box = document.getElementById("avr_detail");
    if (box) box.style.display = "none";
  }

  function docsSection(item) {
    const docs = Array.isArray(item.documents) ? item.documents : [];
    const req = REQUIRED_DOCS[item.aid_type] || [];
    let html = '<div style="margin-top:12px;" class="inspection-data-block"><div class="inspection-data-title">Documents to Verify</div>';

    if (item.aid_type === "death_aid") {
      html +=
        '<div style="margin-top:8px;padding:10px 12px;border-radius:8px;background:rgba(33,150,243,0.08);border:1px solid rgba(33,150,243,0.25);font-size:0.8rem;color:#0d47a1;">' +
        "<strong>No documents required.</strong> Death Aid is a known event to the association &mdash; verify the relationship and the amount against the By-Laws instead.</div>";
    } else if (!docs.length) {
      html +=
        '<div style="margin-top:8px;padding:10px 12px;border-radius:8px;background:rgba(229,57,53,0.08);border:1px solid rgba(229,57,53,0.25);font-size:0.8rem;color:#b71c1c;">&#9888; No documents were uploaded with this claim.</div>';
    } else {
      html +=
        '<div style="display:flex;flex-direction:column;gap:6px;margin-top:8px;">' +
        docs
          .map((d) => {
            const isReq = req.indexOf(d.document_type) !== -1;
            return (
              '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 12px;border:1px solid #e0e0e0;border-radius:8px;font-size:0.8rem;">' +
              "<span><strong>" +
              esc(d.label || LABELS[d.document_type] || d.document_type) +
              (isReq ? " <span style='color:#c62828;'>*</span>" : "") +
              "</strong> <span style='color:#757575;'>" +
              esc(d.file_name || "") +
              "</span></span>" +
              "<a href='" +
              esc(d.url || "#") +
              "' target='_blank' rel='noopener' class='file-queue-btn' style='padding:4px 12px;font-size:0.75rem;text-decoration:none;white-space:nowrap;'>View</a>" +
              "</div>"
            );
          })
          .join("") +
        "</div>";
      const missing = req.filter((t) => !docs.some((d) => d.document_type === t));
      html += missing.length
        ? '<div style="margin-top:8px;padding:8px 12px;border-radius:8px;font-size:0.78rem;background:rgba(229,57,53,0.08);border:1px solid rgba(229,57,53,0.25);color:#b71c1c;">&#9888; Missing required document(s): ' +
          missing.map((t) => LABELS[t] || t).join(", ") +
          "</div>"
        : '<div style="margin-top:8px;padding:8px 12px;border-radius:8px;font-size:0.78rem;background:rgba(46,125,50,0.08);border:1px solid rgba(46,125,50,0.25);color:#1b5e20;">&#10003; All required documents present (Request Letter + Hospital Bill).</div>';
    }
    return html + "</div>";
  }

  function select(index) {
    const item = state.items[index];
    if (!item) return;
    state.selected = item;
    const med = isMedical(item);
    const m = item.member || {};

    // Two-column detail layout: short fields pair up, the long reason text
    // gets the full row so it never squashes its neighbours.
    const fields = med
      ? [
          ["Claim Type", "Medical Aid"],
          ["Request Date", item.request_date || item.date || "—"],
          ["Member", `${m.member_name || ""} (${m.employee_id || "—"})`],
          ["Department", m.department || "—"],
          ["Hospital", item.hospital || "—"],
          ["Confinement", (item.admission_date || "?") + " → " + (item.discharge_date || "?")],
          ["Total Hospital Bill", peso(item.total_hospital_bill || item.bill)],
          ["Aid Benefit (per member)", peso(item.assigned_amount || item.validated_aid_amount)],
          ["Reason / Medical Case", item.medical_case || item.reason || "—", true],
        ]
      : [
          ["Claim Type", "Death Aid"],
          ["Date of Death", item.date_of_death || item.dateOfDeath || "—"],
          ["Member", `${m.member_name || ""} (${m.employee_id || "—"})`],
          ["Department", m.department || "—"],
          ["Deceased", item.deceased_name || item.deceased || "—"],
          ["Relationship to Member", item.relationship || "—"],
          ["Claimant", item.claimant_name || item.claimantName || "—"],
          ["Total Bill", peso(item.bill_amount || 0)],
          ["Benefit Amount", peso(item.benefit_amount || item.benefit || item.assigned_amount)],
        ];

    const grid = document.getElementById("avr_detail_grid");
    grid.innerHTML = fields
      .map(
        ([k, v, wide]) =>
          `<div class="readonly-field"${wide ? ' style="grid-column: 1 / -1;"' : ""}><label>${esc(k)}</label><div>${esc(v)}</div></div>`
      )
      .join("");

    document.getElementById("avr_detail_docs").innerHTML = docsSection(item);

    document.getElementById("avr_remarks").value = "";
    document.getElementById("avr_detail").style.display = "block";
    document.getElementById("avr_detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function submitDecision(result) {
    const item = state.selected;
    if (!item) return;
    const remarks = (document.getElementById("avr_remarks") || {}).value || "";
    if (result === "Returned" && !remarks.trim()) {
      return toast("Remarks are required when returning a claim for correction.", true);
    }
    const fd = new FormData();
    fd.append("aAuditID", item.id);
    fd.append("aAuditResult", result === "Verified" ? "Verified" : "Returned");
    fd.append("aAuditRemarks", remarks);
    fd.append("table_name", item.aid_type === "medical_aid" ? "medical_aid" : "death_aid");

    const btns = document.querySelectorAll("#avr_detail button[data-avr-btn]");
    btns.forEach((b) => (b.disabled = true));
    try {
      const res = await fetch("/api/auditor/verify-aid/", {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": getCookie("csrftoken") },
        body: fd,
      });
      const data = await res.json().catch(() => ({}));
      if (data && data.ok) {
        toast(
          result === "Verified"
            ? "Claim verified and forwarded to the President. The member has been notified by email."
            : "Claim returned to the Treasurer for correction. The member has been notified by email.",
          false
        );
        clearDetail();
        await load();
      } else {
        toast((data && data.error) || "Failed to submit verification.", true);
      }
    } catch (e) {
      toast("Network error while submitting.", true);
    } finally {
      btns.forEach((b) => (b.disabled = false));
    }
  }

  function boot() {
    // Bind once — boot runs on DOMContentLoaded AND turbo:load.
    const ret = document.getElementById("avr_return");
    if (ret && !ret.dataset.bound) {
      ret.dataset.bound = "1";
      ret.addEventListener("click", () => submitDecision("Returned"));
    }
    const fwd = document.getElementById("avr_forward");
    if (fwd && !fwd.dataset.bound) {
      fwd.dataset.bound = "1";
      fwd.addEventListener("click", () => submitDecision("Verified"));
    }

    // Load the queue whenever the module is opened from the sidebar
    if (!window.__nxVerifyAidClickBound) {
      window.__nxVerifyAidClickBound = true;
      document.addEventListener("click", function (e) {
        const el = e.target.closest && e.target.closest('[data-target="aid-verify-requests"]');
        if (el) setTimeout(load, 200);
      });
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
  document.addEventListener("turbo:load", boot);

  window.nxVerifyAid = { load, select, submitDecision };
})();
