/*
 * Shared Monthly Deduction workflow timeline.
 *
 * Renders an assessment's AssessmentWorkflowLog entries (the audit-visible
 * trace of every workflow step: president set → treasurer record → treasurer
 * deposit → auditor verify → president approve, plus any invalidations) as a
 * vertical timeline. Used by the Treasurer, Auditor and President detail
 * panels — one renderer so all three tell the same story.
 *
 * Exposes: window.renderWorkflowTimeline(logs) -> HTML string
 *          window.mdDepositEvidenceHtml(assessment) -> HTML string
 *          window.mdWorkflowTimelineHtml(logs) -> titled card HTML
 */
(function () {
  "use strict";

  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  var PESO = function (v) {
    return "₱" + Number(v || 0).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  var ACTION_META = {
    president_set_assessment:   { label: "Assessment created",      icon: "fa-file-circle-plus", tone: "#1565c0" },
    president_revise_assessment:{ label: "Assessment revised",      icon: "fa-pen-to-square",    tone: "#1565c0" },
    president_recall:           { label: "Assessment recalled",     icon: "fa-rotate-left",      tone: "#e65100" },
    president_upload_documents: { label: "Documents uploaded",      icon: "fa-paperclip",        tone: "#1565c0" },
    president_delete_document:  { label: "Document removed",        icon: "fa-trash-can",        tone: "#8a949e" },
    treasurer_submit:           { label: "Submitted for deposit",   icon: "fa-arrow-right",      tone: "#00695c" },
    treasurer_save_draft:       { label: "Draft saved",             icon: "fa-floppy-disk",      tone: "#455a64" },
    treasurer_deposit:          { label: "Deposit recorded",        icon: "fa-building-columns", tone: "#283593" },
    deposit_invalidated:        { label: "Deposit invalidated",     icon: "fa-ban",              tone: "#c62828" },
    auditor_verify:             { label: "Verified by Auditor",     icon: "fa-circle-check",     tone: "#2e7d32" },
    auditor_reject:             { label: "Rejected by Auditor",     icon: "fa-circle-xmark",     tone: "#c62828" },
    auditor_notify_members:     { label: "Members notified",        icon: "fa-envelope",         tone: "#8a6d3b" },
    president_return:           { label: "Returned by President",   icon: "fa-rotate-left",      tone: "#e65100" },
    catchup_backfill:           { label: "Catchup backfill",        icon: "fa-user-clock",        tone: "#ef6c00" },
    auto_catchup_on_handoff:    { label: "Auto catch-up on handoff", icon: "fa-wand-magic-sparkles", tone: "#ef6c00" },
    president_approve:          { label: "Final approval",          icon: "fa-crown",            tone: "#6a1b9a" },
  };

  function fmtDateTime(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    return d.toLocaleString(undefined, {
      year: "numeric", month: "short", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  }

  function humanAction(action) {
    var meta = ACTION_META[action];
    if (meta) return meta;
    var words = String(action || "").replace(/_/g, " ").trim();
    return { label: words.charAt(0).toUpperCase() + words.slice(1), icon: "fa-list-check", tone: "#5f7a5f" };
  }

  function singleRowHtml(log) {
    var meta = humanAction(log.action);
    return (
      '<div class="mdtl-item" style="display:flex;gap:10px;padding:7px 0;position:relative;">' +
        '<div style="flex:0 0 26px;height:26px;border-radius:50%;background:' + meta.tone + '14;color:' + meta.tone + ';display:flex;align-items:center;justify-content:center;font-size:0.72rem;">' +
          '<i class="fa-solid ' + meta.icon + '"></i>' +
        "</div>" +
        "<div style=\"flex:1;min-width:0;\">" +
          '<div style="font-size:0.82rem;font-weight:700;color:' + meta.tone + ';">' + esc(meta.label) + "</div>" +
          '<div style="font-size:0.76rem;color:#4b5a50;">' + esc(log.notes || "") + "</div>" +
          '<div style="font-size:0.7rem;color:#8a949e;margin-top:1px;">' +
            (log.performed_by ? esc(log.performed_by) + " · " : "") + esc(fmtDateTime(log.created_at)) +
          "</div>" +
        "</div>" +
      "</div>"
    );
  }

  function subRowHtml(log) {
    return (
      '<div style="display:flex;gap:8px;padding:4px 0 4px 0;font-size:0.76rem;color:#4b5a50;">' +
        '<span style="flex:1;min-width:0;">' + esc(log.notes || "") + "</span>" +
        '<span style="flex:0 0 auto;color:#8a949e;font-size:0.7rem;white-space:nowrap;">' +
          esc(fmtDateTime(log.created_at)) +
        "</span>" +
      "</div>"
    );
  }

  function groupHtml(items) {
    if (items.length === 1) return singleRowHtml(items[0]);
    var meta = humanAction(items[0].action);
    var first = items[0];
    var last = items[items.length - 1];
    var sub = items.map(subRowHtml).join("");
    return (
      '<div class="mdtl-group">' +
        '<div class="mdtl-item" style="display:flex;gap:10px;padding:7px 0;cursor:pointer;" onclick="mdToggleWorkflowGroup(this)" role="button" tabindex="0" title="Click to expand grouped entries">' +
          '<div style="flex:0 0 26px;height:26px;border-radius:50%;background:' + meta.tone + '14;color:' + meta.tone + ';display:flex;align-items:center;justify-content:center;font-size:0.72rem;">' +
            '<i class="fa-solid ' + meta.icon + '"></i>' +
          "</div>" +
          '<div style="flex:1;min-width:0;">' +
            '<div style="font-size:0.82rem;font-weight:700;color:' + meta.tone + ';">' + esc(meta.label) +
              ' <span style="display:inline-block;min-width:20px;text-align:center;padding:0 6px;border-radius:999px;background:' + meta.tone + '14;font-size:0.72rem;">× ' + items.length + "</span></div>" +
            '<div style="font-size:0.7rem;color:#8a949e;margin-top:1px;">' +
              (first.performed_by ? esc(first.performed_by) + " · " : "") + esc(fmtDateTime(last.created_at)) + " — click to expand" +
            "</div>" +
          "</div>" +
          '<div class="mdtl-gchev" style="flex:0 0 auto;align-self:center;color:#8a949e;font-size:0.72rem;transition:transform 0.15s;"><i class="fa-solid fa-chevron-down"></i></div>' +
        "</div>" +
        '<div class="mdtl-sub" style="display:none;border-left:2px solid ' + meta.tone + '33;margin:0 0 4px 13px;padding-left:12px;">' + sub + "</div>" +
      "</div>"
    );
  }

  window.renderWorkflowTimeline = function renderWorkflowTimeline(logs) {
    var rows = logs || [];
    if (!rows.length) {
      return '<div style="padding:10px 12px;color:#8a949e;font-size:0.8rem;">No workflow activity recorded yet.</div>';
    }
    // Collapse consecutive same-action entries (e.g. eleven per-member
    // catch-up backfills) into one expandable group row.
    var groups = [];
    rows.forEach(function (log) {
      var last = groups[groups.length - 1];
      if (last && last[0].action === log.action) last.push(log);
      else groups.push([log]);
    });
    return groups.map(groupHtml).join("");
  };

  window.mdToggleWorkflowGroup = function mdToggleWorkflowGroup(head) {
    var group = head.closest ? head.closest(".mdtl-group") : null;
    var sub = group ? group.querySelector(".mdtl-sub") : null;
    var chev = head.querySelector ? head.querySelector(".mdtl-gchev") : null;
    if (!sub) return;
    var open = sub.style.display !== "none";
    sub.style.display = open ? "none" : "";
    if (chev) chev.style.transform = open ? "" : "rotate(180deg)";
  };

  window.mdToggleWorkflowDrawer = function mdToggleWorkflowDrawer(head) {
    var card = head.closest ? head.closest(".mdtl-card") : null;
    var body = card ? card.querySelector(".mdtl-body") : null;
    var chev = head.querySelector ? head.querySelector(".mdtl-chev") : null;
    if (!body) return;
    var open = body.style.display !== "none";
    body.style.display = open ? "none" : "";
    if (chev) chev.style.transform = open ? "" : "rotate(180deg)";
  };

  window.mdWorkflowTimelineHtml = function mdWorkflowTimelineHtml(logs) {
    var count = (logs || []).length;
    return (
      '<div class="mdtl-card" style="border:1px solid #e4ece4;border-radius:12px;background:#fff;padding:14px 16px;">' +
        '<div class="mdtl-head" style="display:flex;align-items:center;gap:8px;cursor:pointer;" onclick="mdToggleWorkflowDrawer(this)" role="button" tabindex="0" title="Show/hide workflow history">' +
          '<i class="fa-solid fa-timeline" style="color:#2e7d32;"></i>' +
          '<span style="font-weight:800;font-size:0.9rem;color:#1b5e20;">Workflow History</span>' +
          '<span style="display:inline-block;min-width:22px;text-align:center;padding:1px 7px;border-radius:999px;background:#e8f5e9;color:#1b5e20;font-size:0.72rem;font-weight:800;">' + count + "</span>" +
          '<span class="mdtl-chev" style="margin-left:auto;color:#8a949e;font-size:0.75rem;transition:transform 0.15s;"><i class="fa-solid fa-chevron-down"></i></span>' +
        "</div>" +
        '<div class="mdtl-body" style="display:none;margin-top:6px;">' +
          window.renderWorkflowTimeline(logs) +
        "</div>" +
      "</div>"
    );
  };

  window.mdDepositEvidenceHtml = function mdDepositEvidenceHtml(a) {
    var slips = a.deposit_slips || [];
    var hasDeposit = !!a.deposit_reference || !!a.deposited_at;
    var slipLinks = slips.length
      ? slips.map(function (img, i) {
          return '<a href="' + esc(img.url) + '" target="_blank" rel="noopener" style="color:#1565c0;text-decoration:underline;font-weight:600;">Slip ' + (i + 1) + "</a>";
        }).join(" · ")
      : '<span style="color:#c62828;font-weight:700;">missing</span>';
    var rows = [];
    rows.push("<div><strong style=\"display:inline-block;margin-right:4px;\">Collection:</strong>" + esc(a.collection_reference || "—") + "</div>");
    rows.push("<div><strong style=\"display:inline-block;margin-right:4px;\">Deposit Ref:</strong>" + esc(a.deposit_reference || (hasDeposit ? "—" : "not deposited yet")) + "</div>");
    rows.push("<div><strong style=\"display:inline-block;margin-right:4px;\">Amount:</strong>" + (a.deposited_amount != null ? PESO(a.deposited_amount) : "—") + "</div>");
    rows.push("<div><strong style=\"display:inline-block;margin-right:4px;\">Deposited:</strong>" + esc(fmtDateTime(a.deposited_at) || "—") + (a.deposited_by ? " by " + esc(a.deposited_by) : "") + "</div>");
    rows.push('<div><strong style="display:inline-block;margin-right:4px;">Deposit Slip:</strong>' + slipLinks + "</div>");
    return (
      '<div style="flex:1 1 auto; width:100%; height:100%; box-sizing:border-box; padding:12px 14px;border:1px solid #c5cae9;border-left:5px solid #283593;border-radius:10px;background:#f3f5ff;box-shadow:0 2px 6px rgba(40,53,147,0.08);">' +
        '<h4 style="margin:0 0 10px;color:#283593;font-size:0.9rem;letter-spacing:0.02em;">' +
          '<i class="fa-solid fa-building-columns" style="color:#283593;margin-right:6px;"></i>DEPOSIT EVIDENCE' +
        "</h4>" +
        '<div style="display:flex;gap:18px;flex-wrap:wrap;font-size:0.84rem;">' + rows.join("") + "</div>" +
      "</div>"
    );
  };
})();
