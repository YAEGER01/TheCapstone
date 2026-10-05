// aid_approval_new.js — NEW "Final Approval" module for the President.
// Queue of Auditor-verified aid claims with the "Documents to Verify" section.
// Approve = forward to Treasurer for release; Return = back to Treasurer for revision.
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

  const REQUIRED_DOCS = { medical_aid: ["request_letter", "hospital_bill"], death_aid: [] };
  const LABELS = {
    request_letter: "Request Letter",
    hospital_bill: "Hospital Bill",
    other: "Other Supporting Document",
    uncategorized: "Uncategorized Upload",
  };

  const state = { items: [], selected: null };

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

  async function load(silent) {
    const tbody = document.querySelector("#afa_queue tbody");
    if (!tbody) return;
    if (!silent) tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#757575;">Loading...</td></tr>';
    const data = await getJSON("/api/president/auditor-approved-aids/list/");
    state.items = (data && data.aids) || [];
    if (!state.items.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#757575;">No claims awaiting final approval.</td></tr>';
      clearDetail();
      return;
    }
    tbody.innerHTML = state.items
      .map(
        (it, i) => `
        <tr style="cursor:pointer;" onclick="window.nxAidApproval.select(${i})">
          <td>${esc(it.type)}</td>
          <td>${esc(it.memberName || (it.member && it.member.member_name) || "")}</td>
          <td>${esc(it.request_date || it.claim_date || it.date || "—")}</td>
          <td>${peso(isMedical(it) ? it.reqAmount || it.total_hospital_bill : it.benefit)}</td>
          <td>${docsBadge(it)}</td>
        </tr>`
      )
      .join("");
  }

  function clearDetail() {
    state.selected = null;
    const box = document.getElementById("afa_detail");
    if (box) box.style.display = "none";
  }

  function docsSection(item) {
    const docs = Array.isArray(item.documents) ? item.documents : [];
    const req = REQUIRED_DOCS[item.aid_type] || [];
    let html = '<div class="inspection-data-block" style="margin-top:12px;"><div class="inspection-data-title">Documents to Verify</div>';

    if (item.aid_type === "death_aid") {
      html +=
        '<div style="margin-top:8px;padding:10px 12px;border-radius:8px;background:rgba(33,150,243,0.08);border:1px solid rgba(33,150,243,0.25);font-size:0.8rem;color:#0d47a1;">' +
        "<strong>No documents required.</strong> Death Aid is a known event to the association.</div>";
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

    const fields = med
      ? [
          ["Member", item.memberName || (item.member && item.member.member_name) || "—"],
          ["Request Date", item.request_date || item.date || "—"],
          ["Reason / Medical Case", item.medical_case || item.reason || "—"],
          ["Hospital", item.hospital || "—"],
          ["Hospital Bill", peso(item.total_hospital_bill || item.bill)],
        ]
      : [
          ["Member", item.memberName || (item.member && item.member.member_name) || "—"],
          ["Deceased", item.deceased || item.deceased_name || "—"],
          ["Relationship", item.relationship || "—"],
          ["Claimant", item.claimantName || "—"],
          ["Date of Death", item.deathDate || item.date_of_death || "—"],
          ["Benefit Amount", peso(item.benefit)],
        ];

    const grid = document.getElementById("afa_detail_grid");
    grid.innerHTML = fields
      .map(([k, v]) => `<div class="readonly-field"><label>${esc(k)}</label><div>${esc(v)}</div></div>`)
      .join("");

    document.getElementById("afa_detail_docs").innerHTML = docsSection(item);

    const remarks = document.getElementById("afa_remarks");
    if (remarks) remarks.value = "";

    document.getElementById("afa_detail").style.display = "block";
    document.getElementById("afa_detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function decide(decision) {
    const item = state.selected;
    if (!item) return;
    const remarksEl = document.getElementById("afa_remarks");
    const remarks = remarksEl ? remarksEl.value : "";
    // Nothing is "approved" in pesos here — the actual cash amount is entered
    // by the Treasurer at release time. The claim's validated figure is sent
    // internally to keep the aid-post records intact.
    const approvedAmount = parseFloat((item.reqAmount || item.validated_aid_amount || item.benefit) || 0) || 0;
    if (decision === "Rejected" && !remarks.trim()) {
      return toast("A clear reason is required when returning a claim to the Treasurer.", true);
    }

    const btns = document.querySelectorAll("#afa_detail button[data-afa-btn]");
    btns.forEach((b) => (b.disabled = true));
    try {
      const res = await fetch("/api/aids/presidential-decision/", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify({
          target_id: item.id,
          decision: decision,
          approved_amount: approvedAmount,
          remarks: remarks,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (data && data.success) {
        toast(
          decision === "Approved"
            ? "Claim approved. The member has been notified by email — the Treasurer can now release the funds."
            : "Claim returned to the Treasurer for revision. The member has been notified by email.",
          false
        );
        clearDetail();
        await load();
      } else {
        toast((data && (data.message || data.error)) || "Failed to save the decision.", true);
      }
    } catch (e) {
      toast("Network error while saving the decision.", true);
    } finally {
      btns.forEach((b) => (b.disabled = false));
    }
  }

  function boot() {
    // Bind once — boot runs on DOMContentLoaded AND turbo:load, and duplicate
    // anonymous handlers meant one click fired the decision twice (double
    // toasts, double notifications).
    const appr = document.getElementById("afa_approve");
    if (appr && !appr.dataset.bound) {
      appr.dataset.bound = "1";
      appr.addEventListener("click", () => decide("Approved"));
    }
    const ret = document.getElementById("afa_return");
    if (ret && !ret.dataset.bound) {
      ret.dataset.bound = "1";
      ret.addEventListener("click", () => decide("Rejected"));
    }

    // Load the queue whenever the module is opened from the sidebar
    if (!window.__nxAidApprovalClickBound) {
      window.__nxAidApprovalClickBound = true;
      document.addEventListener("click", function (e) {
        const el = e.target.closest && e.target.closest('[data-target="aid-final-approval"]');
        if (el) setTimeout(load, 200);
      });
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
  document.addEventListener("turbo:load", boot);

  window.nxAidApproval = { load, select, decide };
})();
