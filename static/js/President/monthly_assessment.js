/* Monthly Deduction Assessment (President)
 * Set the monthly assessment breakdown, track the workflow, and give final
 * approval which triggers member email notices. Calls:
 *   GET  /api/president/monthly-assessment/list/
 *   POST /api/president/monthly-assessment/save/
 *   GET  /api/president/monthly-assessment/<id>/
 *   POST /api/president/deductions/approve/
 */
(function () {
  "use strict";

  const PESO = (v) => "₱" + Number(v || 0).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const esc = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
  }

  // CSRF token with two sources: the rendered {% csrf_token %} hidden input
  // first (always fresh), then the csrftoken cookie. Empty string means the
  // cookie is gone (cleared cookies, localhost<->127.0.0.1 host switch, or a
  // stale tab) — callers must abort with a reload hint INSTEAD of posting,
  // because an empty X-CSRFToken header always 403s ("incorrect length").
  function csrfToken() {
    const el = document.querySelector("[name=csrfmiddlewaretoken]");
    const fromInput = (el && el.value) || "";
    if (fromInput) return fromInput;
    return getCookie("csrftoken") || "";
  }

  // Returns the token or toasts why the action cannot proceed. Usage:
  //   const csrf = needCsrfToken(); if (!csrf) return;
  function needCsrfToken() {
    const token = csrfToken();
    if (!token) {
      toast("Security token missing (reload the page and try again).", true);
    }
    return token;
  }

  function toast(message, isError) {
    if (typeof window.showToast === "function") window.showToast(message, isError);
    else if (isError) console.error(message);
  }

  const PURPOSES = [
    { value: "monthly_due", label: "Monthly Due" },
    { value: "medical_aid_fund", label: "Medical Aid Fund" },
    { value: "death_aid_fund", label: "Death Aid Fund" },
    { value: "other", label: "Other" },
  ];

  // Purposes retired from the picker. Rows saved under them still render on
  // older assessments, but locked — they can no longer be added or changed.
  const LEGACY_PURPOSES = { token_incentive: "Token Incentive" };

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
    return `<span style="display:inline-block;max-width:100%;box-sizing:border-box;background:${bg};color:${fg};padding:2px 10px;border-radius:12px;font-size:0.75rem;font-weight:600;line-height:1.25;text-align:center;white-space:normal;overflow-wrap:anywhere;">${label || status}</span>`;
  }

  let defaultMonthlyDue = 200;
  let memberNames = [];
  let externalCampuses = [
    "ISU Echague Campus",
    "ISU Ilagan Campus",
    "ISU Jones Campus",
    "ISU San Mariano Campus",
    "ISU Cauayan Campus",
    "ISUFFAI Federation",
  ];
  let latestAssessments = [];
  let maHistoryPage = 1;
  let maPickerRange = null;
  window.__maHistoryGoPage = function (p) { maHistoryPage = p; loadMonthlyAssessments(); };

  function fileNameFromUrl(url) {
    const clean = String(url || "").split("?")[0];
    return clean.split("/").filter(Boolean).pop() || "file";
  }

  const MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"];

  function maMonthValue(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
  }

  function maShiftMonth(value, delta) {
    const [y, m] = value.split("-").map(Number);
    return maMonthValue(new Date(y, m - 1 + delta, 1));
  }

  function maMonthLabel(value) {
    const [y, m] = value.split("-").map(Number);
    return `${MONTH_NAMES[m - 1]} ${y}`;
  }

  /* Build the Month dropdown: every month in range stays selectable.
     Picking a declared month loads its saved breakdown and attachments —
     locked when already submitted, editable when still a draft. */
  function maPopulateMonthOptions() {
    const select = document.getElementById("ma-month");
    if (!select) return;
    const previous = select.value;
    const now = maMonthValue(new Date());
    const taken = new Set(latestAssessments.map((a) => String(a.month || "").slice(0, 7)));

    const existing = [...taken].sort();
    let start = maShiftMonth(now, -12);
    if (existing.length && existing[0] < start) start = existing[0];
    let end = maShiftMonth(now, 12);
    if (existing.length) {
      const afterLatest = maShiftMonth(existing[existing.length - 1], 1);
      if (afterLatest > end) end = afterLatest;
    }

    const options = ['<option value="" disabled ' + (previous ? "" : "selected") + '>Select month…</option>'];
    for (let v = start; v <= end; v = maShiftMonth(v, 1)) {
      const isTaken = taken.has(v);
      options.push(`<option value="${v}" ${v === previous ? "selected" : ""}${isTaken ? ' data-taken="1"' : ""}>${maMonthLabel(v)}</option>`);
    }
    select.innerHTML = options.join("");
    // Month range for the popup picker (same bounds as the dropdown had).
    maPickerRange = { start, end, taken };
    maRefreshPickerLabel();
    maBindPicker();
    // No month is picked on load — the President chooses one explicitly.
  }

  function maRefreshPickerLabel() {
    const label = document.getElementById("ma-month-label");
    const select = document.getElementById("ma-month");
    if (!label || !select) return;
    label.textContent = select.value ? maMonthLabel(select.value) : "Select month…";
  }

  /* Year-grid popup picker (replaces the long month dropdown). Every month
     in range stays selectable; months with a saved assessment get a dot. */
  function maBindPicker() {
    const btn = document.getElementById("ma-month-btn");
    const pop = document.getElementById("ma-month-pop");
    const grid = document.getElementById("ma-month-grid");
    const yearLabel = document.getElementById("ma-year-label");
    const prev = document.getElementById("ma-year-prev");
    const next = document.getElementById("ma-year-next");
    const select = document.getElementById("ma-month");
    if (!btn || !pop || !grid || !yearLabel || !prev || !next || !select) return;
    const ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const range = maPickerRange || { start: maShiftMonth(maMonthValue(new Date()), -12), end: maShiftMonth(maMonthValue(new Date()), 12), taken: new Set() };
    const startYear = Number(String(range.start).slice(0, 4));
    const endYear = Number(String(range.end).slice(0, 4));
    const curVal = () => String(select.value || "");
    let year = /^\d{4}$/.test(curVal().slice(0, 4)) ? curVal().slice(0, 4) : String(new Date().getFullYear());
    year = Math.min(endYear, Math.max(startYear, Number(year)));
    year = String(year);
    const close = () => { pop.style.display = "none"; document.removeEventListener("click", outside); };
    const outside = (e) => { if (!pop.contains(e.target) && !btn.contains(e.target)) close(); };
    const paint = () => {
      yearLabel.textContent = year;
      prev.disabled = Number(year) <= startYear;
      next.disabled = Number(year) >= endYear;
      grid.innerHTML = ABBR.map((m, i) => {
        const v = `${year}-${String(i + 1).padStart(2, "0")}`;
        if (v < range.start || v > range.end) return `<button type="button" class="ma-mbtn" disabled>${m}</button>`;
        const cls = v === curVal() ? " current" : "";
        const dot = range.taken.has(v) ? `<span class="ma-dot"></span>` : "";
        return `<button type="button" class="ma-mbtn${cls}" data-mv="${v}">${m}${dot}</button>`;
      }).join("");
      grid.querySelectorAll("[data-mv]").forEach((b) =>
        b.addEventListener("click", () => {
          select.value = b.dataset.mv;
          maRefreshPickerLabel();
          close();
          maMonthChanged();
        })
      );
    };
    btn.onclick = (e) => {
      e.stopPropagation();
      if (pop.style.display === "none") { paint(); pop.style.display = "block"; document.addEventListener("click", outside); }
      else close();
    };
    prev.onclick = (e) => { e.stopPropagation(); const y = Number(year) - 1; if (y >= startYear) { year = String(y); paint(); } };
    next.onclick = (e) => { e.stopPropagation(); const y = Number(year) + 1; if (y <= endYear) { year = String(y); paint(); } };
    if (!window.__maPickerEsc) {
      window.__maPickerEsc = true;
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") { const p = document.getElementById("ma-month-pop"); if (p) p.style.display = "none"; }
      });
    }
  }

  function maSetMonthValue(value) {
    const select = document.getElementById("ma-month");
    if (!select) return;
    if (![...select.options].some((o) => o.value === value)) {
      select.insertAdjacentHTML("beforeend", `<option value="${value}" data-taken="1">${maMonthLabel(value)}</option>`);
    }
    select.value = value;
    maRefreshPickerLabel();
  }

  function maFillItemsForm(a) {
    const itemsBody = document.getElementById("ma-items-body");
    if (!itemsBody) return;
    itemsBody.innerHTML = "";
    (a.items || []).forEach((i) =>
      maAddItemRow(i.purpose, i.amount, i.priority_order, i.recipient, i.custom_label,
        { recipientType: i.recipient_type || (i.is_external ? "external" : "member"),
          externalCampus: i.external_campus || "", externalBeneficiary: i.external_beneficiary || "" })
    );
    if (!itemsBody.children.length) maAddItemRow("monthly_due", defaultMonthlyDue, 1);
  }

  /* Header shows the picked month in words ("November 2026"). Switching the
     month also swaps the form content: a declared month loads its saved
     breakdown (locked if submitted), an open month starts blank. */
  window.maMonthChanged = function maMonthChanged() {
    const raw = (document.getElementById("ma-month") || {}).value || "";
    const title = document.getElementById("ma-form-title");
    if (title) {
      const match = raw.match(/^(\d{4})-(\d{2})$/);
      if (match) {
        title.textContent = `${MONTH_NAMES[Number(match[2]) - 1]} ${match[1]}`;
      } else {
        title.textContent = "Monthly Deduction";
      }
    }

    const existing = raw
      ? latestAssessments.find((a) => String(a.month || "").slice(0, 7) === raw)
      : null;
    if (existing) {
      maFillItemsForm(existing);
    } else {
      const itemsBody = document.getElementById("ma-items-body");
      if (itemsBody) {
        itemsBody.innerHTML = "";
        maAddItemRow("monthly_due", defaultMonthlyDue, 1);
      }
    }

    // Submitted months are view-only for the breakdown: the save buttons
    // stand down and the item rows lock. Attachments stay manageable so a
    // wrong scan can still be fixed. A month still awaiting the Treasurer
    // can be recalled to draft for correction.
    const locked = Boolean(existing && existing.status !== "draft");
    const recallable = Boolean(existing && existing.status === "pending_treasurer");
    document.querySelectorAll(
      "#president-monthly-assessment .ma-btn-primary, #president-monthly-assessment .ma-btn-secondary"
    ).forEach((btn) => {
      if (btn.id === "maRecallBtn") return;
      btn.disabled = locked;
      btn.title = locked ? "This month was already submitted and can no longer be edited." : "";
    });
    document.querySelectorAll(
      "#ma-items-body select, #ma-items-body input, #ma-items-body button, .ma-additem-btn"
    ).forEach((el) => {
      el.disabled = locked;
    });
    const recallBtn = document.getElementById("maRecallBtn");
    if (recallBtn) {
      recallBtn.style.display = recallable ? "" : "none";
      recallBtn.title = recallable ? "Pull this month back to draft so you can edit and resubmit it." : "";
    }
    maUpdateSubmitState();

    maRefreshDocBlock();
  };

  /* ---------- attachments: stage now, upload when the month is saved ------
     Picked or dropped images are held in the browser (dashed thumbnails) so
     they can be attached BEFORE the deduction is saved. Saving — draft or
     submit — flushes them to the server automatically. */
  const maStagedDocs = {}; // month -> { request_letter: [{file, url}], deduction_sheet: [...] }
  const DROP_PROMPT = "Drop image or click to choose · JPG, PNG, WEBP up to 10 MB · attaches when you save";

  function maStagedFor(month) {
    if (!maStagedDocs[month]) maStagedDocs[month] = { request_letter: [], deduction_sheet: [] };
    return maStagedDocs[month];
  }

  window.maRefreshDocBlock = function maRefreshDocBlock() {
    const month = (document.getElementById("ma-month") || {}).value || "";
    const match = month
      ? latestAssessments.find((a) => String(a.month || "").slice(0, 7) === month)
      : null;
    const staged = maStagedFor(month);
    const slots = [
      ["ma-current-request_letter", "request_letter_images", "request_letter", "Request letter"],
      ["ma-current-deduction_sheet", "deduction_sheet_images", "deduction_sheet", "Deduction sheet"],
    ];
    slots.forEach(([elId, listKey, kind, label]) => {
      const el = document.getElementById(elId);
      if (!el) return;
      if (!month) { el.innerHTML = ""; return; }
      const server = (match && match[listKey]) || [];
      const pending = staged[kind] || [];
      if (!server.length && !pending.length) { el.innerHTML = ""; return; }
      const fileRow = (name, url, removeAction, pendingFile) => `
        <div style="display:flex; align-items:center; gap:9px; width:100%; margin-top:6px; padding:7px 9px; border:1px solid #dbe3db; border-radius:7px; background:#fff; box-sizing:border-box;">
          <span style="color:#1b5e20; font-size:0.95rem; flex:0 0 auto;"><i class="fa-regular fa-file-image"></i></span>
          <span title="${esc(name)}" style="min-width:0; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:0.78rem; color:#374151;">${esc(name)}${pendingFile ? ' <small style="color:#8a949e;">(ready to attach)</small>' : ""}</span>
          <a href="${url}" target="_blank" rel="noopener" style="border:1px solid #cfe0cf; border-radius:5px; padding:4px 9px; color:#1b5e20; background:#fff; font-size:0.72rem; font-weight:700; text-decoration:none;">View</a>
          <button type="button" style="border:0; border-radius:5px; padding:4px 9px; color:#c62828; background:#ffebee; font-size:0.72rem; font-weight:700; cursor:pointer;" title="Remove file" onclick="${removeAction}">Remove</button>
        </div>`;
      const serverHtml = server.map((img) => fileRow(img.name || "Uploaded image", img.url, `maDeleteDocument(${img.id})`, false)).join("");
      const stagedHtml = pending.map((item, idx) => fileRow(item.file?.name || "Selected image", item.url, `maRemoveStaged('${kind}', ${idx})`, true)).join("");
      const parts = [];
      if (server.length) parts.push(`${server.length} attached`);
      if (pending.length) parts.push(`${pending.length} ready to attach on save`);
      el.innerHTML = serverHtml + stagedHtml +
        `<span style="font-size:0.74rem; color:#8a949e;">${label}: ${parts.join(" · ")}</span>`;
    });
  };

  window.maRemoveStaged = function maRemoveStaged(kind, idx) {
    const month = (document.getElementById("ma-month") || {}).value || "";
    const staged = maStagedFor(month);
    const removed = staged[kind].splice(idx, 1);
    removed.forEach((item) => { if (item.url) URL.revokeObjectURL(item.url); });
    maRefreshDocBlock();
    maUpdateSubmitState();
  };

  window.maDeleteDocument = async function maDeleteDocument(documentId) {
    const csrf = needCsrfToken(); if (!csrf) return;
    try {
      const resp = await fetch(`/api/president/monthly-assessment/documents/${documentId}/delete/`, {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf },
      });
      const data = await resp.json();
      if (!data.ok) { toast(data.error || "Failed to remove the image.", true); return; }
      toast(data.message || "Image removed.", false);
      await loadMonthlyAssessments();
      maRefreshDocBlock();
      maUpdateSubmitState();
    } catch (e) {
      console.error("Failed to remove attachment", e);
      toast("Failed to remove the image.", true);
    }
  };

  function setDropzoneText(kind, text) {
    const el = document.getElementById(`ma-dz-text-${kind}`);
    if (el) el.textContent = text;
  }

  const DOC_IMAGE_PATTERN = /\.(jpe?g|png|webp)$/i;

  /* ---------- duplicate-document guard (live, client-side) ----------
     The Request letter and the Deduction Sheet must be two DIFFERENT
     documents. Every staged file gets a quick meta fingerprint (name,
     size, type, timestamp — "same file name, same source, same meta")
     plus a SHA-256 of its content, so a renamed copy of the same scan is
     still caught before it ever reaches the server. */
  const MA_KIND_LABELS = { request_letter: "Request letter", deduction_sheet: "Deduction Sheet" };

  function maFileFingerprint(file) {
    return [String(file.name || "").toLowerCase(), file.size, file.type, file.lastModified].join("|");
  }

  async function maFileSha256(file) {
    try {
      if (file.__maSha256) return file.__maSha256;
      if (!window.crypto || !window.crypto.subtle) return "";
      const buf = await file.arrayBuffer();
      const digest = await window.crypto.subtle.digest("SHA-256", buf);
      const hex = Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
      file.__maSha256 = hex;
      return hex;
    } catch (e) {
      return ""; // hashing unavailable — the meta fingerprint still applies
    }
  }

  /* Both documents present (staged now or already attached to the month)? */
  function maDocsState(month) {
    const match = month
      ? latestAssessments.find((a) => String(a.month || "").slice(0, 7) === month)
      : null;
    const staged = maStagedFor(month);
    const hasLetter = staged.request_letter.length > 0 || Boolean(match && match.has_request_letter);
    const hasSheet = staged.deduction_sheet.length > 0 || Boolean(match && match.has_deduction_sheet);
    return { hasLetter, hasSheet, complete: hasLetter && hasSheet };
  }

  let maDocsValidNotified = false;

  /* Submit stays disabled until a month is picked AND both documents are
     in place. Composes with the month lock in maMonthChanged (a submitted
     month is view-only no matter what). */
  window.maUpdateSubmitState = function maUpdateSubmitState(opts) {
    const btn = document.getElementById("ma-submit-btn");
    if (!btn) return;
    const month = (document.getElementById("ma-month") || {}).value || "";
    const existing = month
      ? latestAssessments.find((a) => String(a.month || "").slice(0, 7) === month)
      : null;
    const locked = Boolean(existing && existing.status !== "draft");
    const complete = maDocsState(month).complete;
    const ok = Boolean(month) && complete && !locked;
    btn.disabled = !ok;
    btn.title = locked
      ? "This month was already submitted and can no longer be edited."
      : !month
        ? "Pick the month first."
        : !complete
          ? "Attach both the Request letter and the Deduction Sheet to enable Submit."
          : "";
    if (!ok) {
      maDocsValidNotified = false;
    } else if (!maDocsValidNotified && opts && opts.notify) {
      maDocsValidNotified = true;
      toast("Both files uploaded are valid — Submit is enabled.", false);
    }
  };

  window.maFilePicked = function maFilePicked(kind, input) {
    const files = Array.from((input && input.files) || []);
    input.value = "";
    if (!files.length) return;
    maStageImages(kind, files);
  };

  window.maStageImages = async function maStageImages(kind, files) {
    const month = (document.getElementById("ma-month") || {}).value || "";
    if (!month) { toast("Pick the month first.", true); return; }
    const staged = maStagedFor(month);
    const match = latestAssessments.find((a) => String(a.month || "").slice(0, 7) === month);
    const known = [];
    for (const k of ["request_letter", "deduction_sheet"]) {
      for (const item of staged[k]) known.push({ kind: k, print: item.print || "", sha: item.sha || "" });
    }
    // Images already attached to this month (letter, sheet, deposit slips):
    // the server list carries each one's content hash, so a re-upload of a
    // previously attached scan is refused here instead of colliding later.
    const attached = match
      ? [...(match.request_letter_images || []), ...(match.deduction_sheet_images || []), ...(match.deposit_slips || [])]
      : [];
    for (const img of attached) {
      known.push({ kind: "attached", print: "", sha: String(img.sha256 || "").toLowerCase() });
    }
    let accepted = 0;
    for (const file of Array.from(files || [])) {
      const print = maFileFingerprint(file);
      const sha = (await maFileSha256(file)) || "";
      const clash = known.find(
        (k) => (sha && k.sha && k.sha === sha) || (print && k.print === print)
      );
      if (clash) {
        if (clash.kind === "attached") {
          toast(`${file.name} is already attached to ${maMonthLabel(month)} — remove the existing copy first or choose a different image.`, true);
        } else if (clash.kind === kind) {
          toast(`${file.name} is already staged for the ${MA_KIND_LABELS[kind]} — the same scan cannot be attached twice.`, true);
        } else {
          toast(`${file.name} is the same file as the one staged for the ${MA_KIND_LABELS[clash.kind]} — the Request letter and the Deduction Sheet must be two different documents.`, true);
        }
        continue;
      }
      const item = { file, url: URL.createObjectURL(file), print, sha };
      staged[kind].push(item);
      known.push({ kind, print, sha });
      accepted += 1;
    }
    maRefreshDocBlock();
    maUpdateSubmitState({ notify: true });
    if (accepted > 0) {
      toast(`${accepted} image(s) ready — they attach when you save.`, accepted !== (files || []).length);
    }
  };

  async function maUploadFileToAssessment(assessmentId, kind, file) {
    const fd = new FormData();
    fd.append(kind, file);
    const csrf = needCsrfToken();
    if (!csrf) return false;
    try {
      const resp = await fetch(`/api/president/monthly-assessment/${assessmentId}/upload-documents/`, {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf },
        body: fd,
      });
      let data = null;
      try { data = await resp.json(); }
      catch (e) {
        toast(`Failed to upload ${file.name} (server error ${resp.status}).`, true);
        return false;
      }
      // 409 = duplicate image (same content already attached to this month).
      if (!data.ok) { toast(data.error || `Failed to upload ${file.name}.`, true); return false; }
      return true;
    } catch (e) {
      console.error("Failed to upload attachment", e);
      toast(`Failed to upload ${file.name}.`, true);
      return false;
    }
  }

  /* Called right after a successful save: the month now exists on the
     server, so every staged image for it can be uploaded. */
  window.maFlushStagedDocs = async function maFlushStagedDocs(month) {
    const staged = maStagedFor(month);
    const total = staged.request_letter.length + staged.deduction_sheet.length;
    if (!total) return;
    let assessmentId = null;
    try {
      const resp = await fetch("/api/president/monthly-assessment/list/", { cache: "no-store" });
      const data = await resp.json();
      if (data.ok) {
        const match = (data.assessments || []).find((a) => String(a.month || "").slice(0, 7) === month);
        assessmentId = match ? match.assessment_id : null;
      }
    } catch (e) { console.error(e); }
    if (!assessmentId) { toast("Could not find the saved month for the attachments.", true); return; }

    setDropzoneText("request_letter", `Attaching ${total} image(s)…`);
    setDropzoneText("deduction_sheet", `Attaching ${total} image(s)…`);
    let ok = 0;
    for (const kind of ["request_letter", "deduction_sheet"]) {
      for (const item of staged[kind]) {
        const done = await maUploadFileToAssessment(assessmentId, kind, item.file);
        if (done) ok += 1;
      }
    }
    delete maStagedDocs[month];
    toast(`Attached ${ok} of ${total} image(s) for ${maMonthLabel(month)}.`, ok !== total);
    setDropzoneText("request_letter", DROP_PROMPT);
    setDropzoneText("deduction_sheet", DROP_PROMPT);
  };

  function setupDropzones() {
    document.querySelectorAll("#president-monthly-assessment .ma-dropzone").forEach((zone) => {
      const kind = zone.dataset.kind;
      if (!kind) return;
      zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("ma-dragover"); });
      zone.addEventListener("dragleave", () => zone.classList.remove("ma-dragover"));
      zone.addEventListener("drop", (e) => {
        e.preventDefault();
        zone.classList.remove("ma-dragover");
        const files = Array.from((e.dataTransfer && e.dataTransfer.files) || []);
        const images = files.filter((f) => DOC_IMAGE_PATTERN.test(f.name));
        const rejected = files.length - images.length;
        if (rejected > 0) toast(`${rejected} file(s) skipped — only JPG, PNG and WEBP images are accepted.`, true);
        if (images.length) maStageImages(kind, images);
      });
    });
  }

  /* ---------- member picker (searchable modal, replaces the datalist) ------
     With 150+ members a native dropdown is unusable; the Browse button opens
     a searchable, scrollable list instead. The input stays editable so a
     mistake can be cleared and re-picked at any time. */
  window.__maPickerItems = [];
  window.__maPickerRow = null;

  window.maOpenMemberPicker = function maOpenMemberPicker(btn) {
    const row = btn.closest(".ma-item-row");
    if (!row) return;
    const purpose = row.querySelector(".ma-item-purpose")?.value || "";
    if ((RECIPIENT_RULES[purpose] || {}).fixed) return; // ISUCauFA, Inc. is fixed
    if (!window.SimpleModal || !SimpleModal.open) { toast("Modal unavailable.", true); return; }
    window.__maPickerRow = row;
    window.__maPickerPurpose = purpose;
    const purposeLabel = (PURPOSES.find((p) => p.value === purpose) || {}).label || "";
    SimpleModal.open({
      title: purposeLabel ? `Choose Recipient — ${purposeLabel}` : "Choose Recipient",
      width: "440px",
      html: `
        <input type="text" id="ma-picker-search" class="form-control" placeholder="Search member…"
               style="width:100%; margin-bottom:8px;" oninput="maRenderRecipientList(this.value, true)" />
        <div id="ma-picker-alpha" style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:8px;"></div>
        <div id="ma-picker-list" style="max-height:340px; overflow-y:auto; border:1px solid #e6ebe7; border-radius:8px;"></div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:12px;">
          <span id="ma-picker-count" style="font-size:0.76rem; color:#8a949e;"></span>
          <button type="button" class="btn-outline" style="padding:6px 16px;" onclick="SimpleModal.close()">Cancel</button>
        </div>`,
    });
    maPickerLetter = "";
    maPickerPage = 1;
    maRenderRecipientList("");
    const search = document.getElementById("ma-picker-search");
    if (search) search.focus();
  };

  /* Recipient picker list — searchable + alphabet-paginated. The list arrives
     sorted by surname ("SURNAME, Given"), so the A–Z strip jumps to a single
     initial and the search box narrows within it. The search input and the
     option clicks use inline handlers, so the functions must be on window. */
  const MA_PICKER_PAGE_SIZE = 8;
  const MA_PICKER_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
  let maPickerPage = 1;
  let maPickerLetter = "";

  function maPickerAlphaButton(label, letter, active) {
    return `<button type="button" onclick="window.__maPickerLetterGo('${letter}')"
      style="min-width:21px; height:21px; padding:0 5px; border-radius:5px; font-size:0.69rem; line-height:1;
      border:1px solid ${active ? "#1b5e20" : "#dfe6e0"}; background:${active ? "#1b5e20" : "#fff"};
      color:${active ? "#fff" : "#2f3d49"}; font-weight:700; cursor:pointer;">${label}</button>`;
  }

  // External (other-campus) beneficiaries are only allowed for Death Aid
  // and Other purposes — never Medical Aid, never Monthly Due.
  function maExternalAllowed(purpose) {
    return purpose === "death_aid_fund" || purpose === "other";
  }

  window.maRenderRecipientList = function maRenderRecipientList(term, resetPage) {
    const listEl = document.getElementById("ma-picker-list");
    if (!listEl) return;
    if (resetPage) maPickerPage = 1;
    const t = String(term || "").trim().toLowerCase();
    const purpose = window.__maPickerPurpose || "";
    const rule = RECIPIENT_RULES[purpose] || {};
    // Aid funds go to a named member only — the association is not an option.
    // Death Aid and Other additionally offer Other Campus at the top:
    // cross-campus aid declared from the very start (campus + beneficiary
    // required). Medical Aid never offers it.
    let options = rule.membersOnly
      ? memberNames.map((name) => ({ name, sub: "" }))
      : [{ name: "ISUCauFA, Inc.", sub: "The association" }, ...memberNames.map((name) => ({ name, sub: "" }))];
    if (maExternalAllowed(purpose)) {
      options = [{ name: "🌐 Other Campus (external beneficiary)…", sub: "Cross-campus aid — pick campus + beneficiary", external: true },
        ...options];
    }
    const base = options.filter((o) => !t || `${o.name} ${o.sub}`.toLowerCase().includes(t));

    // Alphabet strip: driven by what the search left, so it only offers
    // initials that still have a member behind them.
    const initialOf = (name) => {
      const ch = String(name || "").trim().charAt(0).toUpperCase();
      return MA_PICKER_ALPHABET.indexOf(ch) !== -1 ? ch : "";
    };
    const available = {};
    base.forEach((o) => {
      const initial = initialOf(o.name);
      if (initial) available[initial] = true;
    });
    if (maPickerLetter && !available[maPickerLetter]) maPickerLetter = "";
    const alphaEl = document.getElementById("ma-picker-alpha");
    if (alphaEl) {
      // Only initials that actually exist are shown — a strip full of dead
      // letters is just noise ("All, M, R, V" when those are the surnames).
      const present = MA_PICKER_ALPHABET.filter((ch) => available[ch]);
      alphaEl.innerHTML =
        maPickerAlphaButton("All", "", !maPickerLetter) +
        present.map((ch) => maPickerAlphaButton(ch, ch, maPickerLetter === ch)).join("");
    }

    const filtered = maPickerLetter
      ? base.filter((o) => initialOf(o.name) === maPickerLetter)
      : base;
    window.__maPickerItems = filtered;
    const pageCount = Math.max(1, Math.ceil(filtered.length / MA_PICKER_PAGE_SIZE));
    maPickerPage = Math.min(Math.max(maPickerPage, 1), pageCount);
    const pageItems = filtered.slice((maPickerPage - 1) * MA_PICKER_PAGE_SIZE, maPickerPage * MA_PICKER_PAGE_SIZE);
    const emptyNote = maPickerLetter
      ? `No member starts with "${esc(maPickerLetter)}"${t ? ` for “${esc(term)}”` : ""}.`
      : `No member matches "${esc(term)}".`;
    listEl.innerHTML = pageItems.map((o, i) => `
      <div role="button" tabindex="0" onclick="maPickRecipientAt(${(maPickerPage - 1) * MA_PICKER_PAGE_SIZE + i})"
           onmouseover="this.style.background='#f3f6f3'" onmouseout="this.style.background=''"
           style="padding:9px 14px; border-bottom:1px solid #f1f4f1; cursor:pointer; font-size:0.86rem; color:#1f2937;">
        <div style="font-weight:600;">${esc(o.name)}</div>
        ${o.sub ? `<div style="font-size:0.74rem; color:#8a949e;">${esc(o.sub)}</div>` : ""}
      </div>`).join("")
      || `<div style="padding:18px; text-align:center; color:#8a949e; font-size:0.84rem;">${emptyNote}</div>`
      + (typeof UniPager !== "undefined" && pageCount > 1
        ? `<div style="padding:8px 10px 4px;">${UniPager.html(maPickerPage, pageCount, "window.__maPickerGoPage(PAGE)", "")}</div>`
        : "");
    const count = document.getElementById("ma-picker-count");
    if (count) {
      count.textContent = (maPickerLetter ? `${filtered.length} starting with ${maPickerLetter}` : `${filtered.length} option(s)`);
    }
  };
  window.__maPickerGoPage = function (p) {
    maPickerPage = p;
    const search = document.getElementById("ma-picker-search");
    maRenderRecipientList(search ? search.value : "", false);
  };
  window.__maPickerLetterGo = function (letter) {
    maPickerLetter = letter || "";
    maPickerPage = 1;
    const search = document.getElementById("ma-picker-search");
    maRenderRecipientList(search ? search.value : "", false);
  };

  window.maPickRecipientAt = function maPickRecipientAt(idx) {
    const item = (window.__maPickerItems || [])[idx];
    const row = window.__maPickerRow;
    if (!item || !row) return;
    if (item.external) {
      // Other-campus choice: auto-check the row's checkbox, flip the row
      // into external mode and focus campus.
      const cb = row.querySelector(".ma-ext-toggle");
      if (cb) cb.checked = true;
      maSetRowExternal(row, true);
      if (window.SimpleModal) SimpleModal.close();
      const campus = row.querySelector(".ma-item-ext-campus");
      if (campus) campus.focus();
      return;
    }
    const input = row.querySelector(".ma-item-recipient");
    if (input) {
      input.value = item.name;
      maSetRowExternal(row, false);
      maApplyRecipientRules(row, row.querySelector(".ma-item-purpose")?.value);
    }
    if (window.SimpleModal) SimpleModal.close();
  };

  // External (other-campus) mode per row: hides the member input, shows the
  // campus datalist + beneficiary input. The canonical "CAMPUS — Beneficiary"
  // display is composed at save time so every module reads it identically.
  window.maSetRowExternal = function maSetRowExternal(row, isExternal) {
    if (!row) return;
    row.dataset.external = isExternal ? "1" : "";
    const memberInput = row.querySelector(".ma-item-recipient");
    const extWrap = row.querySelector(".ma-ext-wrap");
    const badge = row.querySelector(".ma-ext-badge");
    if (memberInput) memberInput.style.display = isExternal ? "none" : "";
    if (extWrap) extWrap.style.display = isExternal ? "" : "none";
    if (badge) badge.style.display = isExternal ? "" : "none";
    const browseBtn = row.querySelector(".ma-pick-btn");
    if (browseBtn) browseBtn.style.display = isExternal ? "none" : "";
    maApplyRecipientRules(row, row.querySelector(".ma-item-purpose")?.value);
    maComputeTotal();
  };

  window.maToggleExternal = function maToggleExternal(checkbox) {
    const row = checkbox.closest(".ma-item-row");
    if (!row) return;
    const purpose = row.querySelector(".ma-item-purpose")?.value || "";
    if (!maExternalAllowed(purpose)) {
      checkbox.checked = false;
      toast("Only Death Aid and Other purposes can be other-campus aid. Medical Aid always goes to a member.", true);
      return;
    }
    maSetRowExternal(row, checkbox.checked);
  };

  // Recipient behavior per purpose: every item goes to someone. Monthly dues
  // go to the association (fixed), everything else names a recipient — for
  // aid funds only an actual member qualifies, so the picker hides the
  // association option there.
  const RECIPIENT_RULES = {
    monthly_due: { fixed: "ISUCauFA, Inc." },
    medical_aid_fund: { required: true, membersOnly: true },
    death_aid_fund: { required: true, membersOnly: true },
    other: { required: true },
  };

  // The Specify control only exists for "Other". Monthly Due gets a month
  // picker instead (to distinguish e.g. a July line from an August line),
  // and the aid purposes need nothing extra.
  const SPECIFY_RULES = {
    monthly_due: { type: "month" },
    medical_aid_fund: { type: "none" },
    death_aid_fund: { type: "none" },
    other: { type: "text", required: true },
  };

  function maApplySpecifyControl(row, purpose, value) {
    const labelInput = row.querySelector(".ma-item-label");
    if (!labelInput) return;
    const rule = SPECIFY_RULES[purpose] || { type: "none" };
    if (rule.type === "none") {
      labelInput.style.display = "none";
      labelInput.value = "";
      return;
    }
    labelInput.style.display = "block";
    if (rule.type === "month") {
      labelInput.type = "month";
      labelInput.placeholder = "";
      labelInput.title = "The month this due covers";
    } else {
      labelInput.type = "text";
      labelInput.placeholder = "Specify what this is (required)";
      labelInput.title = "";
    }
    if (value != null && value !== "") labelInput.value = value;
  }

  function maApplyRecipientRules(row, purpose) {
    const recipientInput = row.querySelector(".ma-item-recipient");
    if (!recipientInput) return;
    const browseBtn = row.querySelector(".ma-pick-btn");
    const rule = RECIPIENT_RULES[purpose] || { required: false };
    // External rows are governed by campus + beneficiary, not the member input.
    if (row.dataset.external === "1") {
      recipientInput.style.border = "";
      const campus = row.querySelector(".ma-item-ext-campus");
      const bene = row.querySelector(".ma-item-ext-bene");
      if (campus) campus.style.border = !campus.value.trim() ? "1px solid #e57373" : "";
      if (bene) bene.style.border = !bene.value.trim() ? "1px solid #e57373" : "";
      if (browseBtn) browseBtn.style.display = "none";
      return;
    }
    if (LEGACY_PURPOSES[purpose]) {
      // Retired purpose — the stored recipient is shown, never edited.
      recipientInput.readOnly = true;
      recipientInput.style.background = "#f5f5f5";
      recipientInput.style.color = "#546e7a";
      recipientInput.style.border = "1px solid #e0e0e0";
      recipientInput.placeholder = "";
      if (browseBtn) browseBtn.style.display = "none";
      return;
    }
    if (rule.fixed) {
      // Monthly dues go to the association — shown, not edited.
      recipientInput.value = rule.fixed;
      recipientInput.readOnly = true;
      recipientInput.style.background = "#e8f5e9";
      recipientInput.style.color = "#1b5e20";
      recipientInput.style.border = "1px solid #cde3cd";
      recipientInput.placeholder = "";
      if (browseBtn) browseBtn.style.display = "none";
    } else {
      // "ISUCauFA, Inc." only has to be cleared when switching to a purpose that
      // needs a specific member (Medical/Death Aid) — for "Other" it is a
      // perfectly valid recipient, so an explicit pick must survive.
      if (recipientInput.value === "ISUCauFA, Inc." && rule.membersOnly) recipientInput.value = "";
      recipientInput.readOnly = false;
      recipientInput.style.background = "";
      recipientInput.style.color = "";
      // Flag required recipients red only while they are still empty.
      recipientInput.style.border =
        rule.required && !recipientInput.value.trim() ? "1px solid #e57373" : "";
      recipientInput.placeholder = "Who receives this?";
      if (browseBtn) browseBtn.style.display = "";
    }
  }

  /* Typing or picking a recipient clears the required-empty highlight. */
  window.maRecipientEdited = function maRecipientEdited(input) {
    const row = input.closest(".ma-item-row");
    if (!row) return;
    const purpose = row.querySelector(".ma-item-purpose")?.value || "";
    const rule = RECIPIENT_RULES[purpose] || {};
    input.style.border = rule.required && !input.value.trim() ? "1px solid #e57373" : "";
  };

  window.maToggleCustomLabel = function maToggleCustomLabel(select) {
    const row = select.closest(".ma-item-row");
    if (!row) return;
    maApplySpecifyControl(row, select.value);
    // Switching purposes clears external mode except death<->other.
    const purpose = select.value || "";
    if (!maExternalAllowed(purpose) && row.dataset.external === "1") {
      const cb = row.querySelector(".ma-ext-toggle");
      if (cb) cb.checked = false;
      maSetRowExternal(row, false);
    }
    maApplyRecipientRules(row, select.value);
  };

  function maMonthLabelToValue(label) {
    // "July 2026" (stored display form) -> "2026-07" for the month picker.
    const MONTHS = ["january", "february", "march", "april", "may", "june",
      "july", "august", "september", "october", "november", "december"];
    const match = (label || "").trim().match(/^([A-Za-z]+)\s+(\d{4})$/);
    if (!match) return label || "";
    const idx = MONTHS.indexOf(match[1].toLowerCase());
    return idx >= 0 ? `${match[2]}-${String(idx + 1).padStart(2, "0")}` : (label || "");
  }

  window.maAddItemRow = function maAddItemRow(purpose, amount, priority, recipient, customLabel, extra) {
    const body = document.getElementById("ma-items-body");
    if (!body) return;
    const ext = extra || {};
    const startExternal = (ext.recipientType === "external") || false;
    const extCampus = ext.externalCampus || "";
    const extBene = ext.externalBeneficiary || "";
    const legacyLabel = (purpose && LEGACY_PURPOSES[purpose]) || "";
    const options = PURPOSES.map(
      (p) => `<option value="${p.value}" ${p.value === (purpose || "monthly_due") ? "selected" : ""}>${p.label}</option>`
    ).join("") + (legacyLabel ? `<option value="${purpose}" selected>${legacyLabel} (locked)</option>` : "");
    const row = document.createElement("div");
    row.className = "ma-item-row";
    row.innerHTML = `
      <div class="ma-purpose-cell">
        <select class="ma-item-purpose form-control" style="min-width:150px;" ${legacyLabel ? "disabled" : ""} onchange="maToggleCustomLabel(this)">${options}</select>
        <input type="text" class="ma-item-label form-control" value="${customLabel || ""}" placeholder="Specify (optional)" style="min-width:150px; display:none;" />
      </div>

      <input type="number" class="ma-item-amount form-control" step="0.01" min="0.01" value="${amount != null ? amount : ""}" placeholder="0.00" ${legacyLabel ? "disabled" : ""} oninput="maComputeTotal()" />
      <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
        <input type="text" class="ma-item-recipient form-control" value="${recipient || ""}" placeholder="Who receives this?" style="flex:1; min-width:0;" ${legacyLabel ? "readonly" : ""} oninput="maRecipientEdited(this)" />
        ${legacyLabel ? "" : `<button type="button" class="ma-pick-btn" title="Browse members / Other Campus" onclick="maOpenMemberPicker(this)">Browse</button>`}
        <span class="ma-ext-badge" style="display:none; font-size:0.66rem; font-weight:800; letter-spacing:0.04em; background:#e3f2fd; color:#0d47a1; border:1px solid #90caf9; padding:2px 8px; border-radius:10px; white-space:nowrap;">EXTERNAL</span>
      </div>
      <div class="ma-ext-wrap" style="display:none; grid-column:1 / -1; background:#f5f9ff; border:1px dashed #90caf9; border-radius:8px; padding:8px 10px; margin-top:6px;">
        <label style="display:flex; align-items:center; gap:6px; font-size:0.74rem; font-weight:700; color:#0d47a1; cursor:pointer;">
          <input type="checkbox" class="ma-ext-toggle" onchange="maToggleExternal(this)" /> Other-campus aid (different campus beneficiary)
        </label>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:6px;">
          <input type="text" class="ma-item-ext-campus form-control" list="ma-campus-list" value="${extCampus || ""}" placeholder="Campus - e.g. ISU Echague Campus" oninput="maRecipientEdited(this)" />
          <input type="text" class="ma-item-ext-bene form-control" value="${extBene || ""}" placeholder="Beneficiary - e.g. Juan Dela Cruz" oninput="maRecipientEdited(this)" />
        </div>
        <div style="font-size:0.7rem; color:#546e7a; margin-top:4px;">Declared from the start - collected here, turned over via Other Transactions with acknowledgement receipt.</div>
      </div>
      ${legacyLabel
        ? `<span class="ma-legacy-badge" title="This purpose was retired. The line stays on the record as history and cannot be changed." style="font-size:0.7rem;font-weight:600;letter-spacing:0.03em;text-transform:uppercase;color:#78909c;text-align:center;white-space:nowrap;align-self:center;">locked</span>`
        : `<button type="button" class="ma-remove-btn" title="Remove this item" onclick="this.closest('.ma-item-row').remove(); maComputeTotal();">&times;</button>`}`;
    body.appendChild(row);
    if (!document.getElementById("ma-campus-list")) {
      const dl = document.createElement("datalist");
      dl.id = "ma-campus-list";
      dl.innerHTML = (externalCampuses || []).map((c) => `<option value="${c}">`).join("");
      document.body.appendChild(dl);
    } else {
      document.getElementById("ma-campus-list").innerHTML = (externalCampuses || []).map((c) => `<option value="${c}">`).join("");
    }
    const wrap = row.querySelector(".ma-ext-wrap");
    const extEligible = maExternalAllowed(purpose);
    if (wrap && extEligible && !legacyLabel) wrap.style.display = "";
    if (startExternal) {
      const cb = row.querySelector(".ma-ext-toggle");
      if (cb) cb.checked = true;
      maSetRowExternal(row, true);
      const campus = row.querySelector(".ma-item-ext-campus");
      const bene = row.querySelector(".ma-item-ext-bene");
      if (campus) campus.value = extCampus;
      if (bene) bene.value = extBene;
    } else if (wrap && !extEligible) {
      wrap.style.display = "none";
    }
    maToggleCustomLabel(row.querySelector(".ma-item-purpose"));
    if (startExternal) maSetRowExternal(row, true);
    if (purpose === "monthly_due") {
      const labelInput = row.querySelector(".ma-item-label");
      if (labelInput) labelInput.value = maMonthLabelToValue(customLabel);
    }
    maComputeTotal();
  };

  window.maComputeTotal = function maComputeTotal() {
    let total = 0;
    document.querySelectorAll("#ma-items-body .ma-item-amount").forEach((input) => {
      total += parseFloat(input.value) || 0;
    });
    const el = document.getElementById("ma-total");
    if (el) el.textContent = PESO(total);
  };

  window.loadMonthlyAssessments = async function loadMonthlyAssessments() {
    try {
      const resp = await fetch("/api/president/monthly-assessment/list/", { cache: "no-store" });
      const data = await resp.json();
      if (!data.ok) { toast(data.error || "Failed to load deduction records.", true); return; }
      defaultMonthlyDue = data.default_monthly_due || 200;
      memberNames = data.member_names || [];
      if (data.external_campuses && data.external_campuses.length) externalCampuses = data.external_campuses;
      latestAssessments = data.assessments || [];
      maPopulateMonthOptions();
      setBadge("ma-pending-dot", data.assessments.filter((a) => a.status === "pending_final").length);
      const tbody = document.getElementById("ma-history-body");
      if (tbody) {
        const all = data.assessments || [];
        const PAGE_SIZE = 8;
        const pageCount = Math.max(1, Math.ceil(all.length / PAGE_SIZE));
        maHistoryPage = Math.min(Math.max(maHistoryPage, 1), pageCount);
        const pageItems = all.slice((maHistoryPage - 1) * PAGE_SIZE, maHistoryPage * PAGE_SIZE);
        const pager = document.getElementById("ma-history-pagination");
        tbody.innerHTML = "";
        if (!all.length) {
          tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:#757575;padding:18px;">No deduction records yet. Create one above.</td></tr>`;
          if (pager) pager.innerHTML = "";
        }
        pageItems.forEach((a) => {
          const editable = ["draft", "rejected", "returned"].includes(a.status);
          const editBtn = editable
            ? ` <button type="button" class="btn-outline" style="padding:3px 10px;font-size:0.8rem;margin:2px 4px 2px 0;" onclick="maEditAssessment(${a.assessment_id})">Edit</button>`
            : "";
          tbody.innerHTML += `<tr>
            <td style="padding:6px 8px;">${a.month_label}</td>
            <td style="padding:6px 8px;">${PESO(a.total_amount)}</td>
            <td style="padding:6px 8px;">${a.recorded_count}</td>
            <td style="padding:6px 8px;">${PESO(a.total_recorded)}</td>
            <td style="padding:6px 8px;">${PESO(a.total_outstanding)}</td>
            <td style="padding:6px 8px;">${statusBadge(a.status, a.status_label)}</td>
            <td style="padding:6px 8px; width:15%; max-width:15%; white-space:normal; overflow-wrap:anywhere; word-break:break-word;">${a.auditor_remarks || a.president_remarks || "—"}</td>
            <td style="padding:6px 8px;">
              <button type="button" class="btn-outline" style="padding:3px 10px;font-size:0.8rem;margin:2px 4px 2px 0;" onclick="maReviewAssessment(${a.assessment_id})">${a.status === "final_approved" ? "View" : "Review"}</button>${editBtn}
            </td>
          </tr>`;
        });
        if (pager && typeof UniPager !== "undefined" && all.length) {
          pager.innerHTML = UniPager.html(maHistoryPage, pageCount, "window.__maHistoryGoPage(PAGE)", UniPager.count(maHistoryPage, PAGE_SIZE, all.length));
        }
      }
    } catch (e) {
      console.error("Failed to load monthly assessments", e);
      toast("Failed to load deduction records.", true);
    }
    maRefreshDocBlock();
    maUpdateSubmitState();
  };

  window.maSaveAssessment = async function maSaveAssessment(draft = false) {
    const month = (document.getElementById("ma-month") || {}).value || "";
    const rows = [...document.querySelectorAll("#ma-items-body .ma-item-row")];
    if (!month) { toast("Please pick a month.", true); return; }
    const items = rows.map((row) => {
      const isExternal = row.dataset.external === "1"
        || row.querySelector(".ma-ext-toggle")?.checked;
      return {
        purpose: row.querySelector(".ma-item-purpose")?.value,
        custom_label: row.querySelector(".ma-item-label")?.value || "",
        amount: row.querySelector(".ma-item-amount")?.value,
        recipient: row.querySelector(".ma-item-recipient")?.value,
        recipient_type: isExternal ? "external" : "member",
        external_campus: row.querySelector(".ma-item-ext-campus")?.value || "",
        external_beneficiary: row.querySelector(".ma-item-ext-bene")?.value || "",
      };
    }).filter((i) => i.amount && parseFloat(i.amount) > 0);

    if (!items.length) { toast("Add at least one breakdown item with an amount.", true); return; }
    if (!draft) {
      const unnamedOther = items.find((i) => i.purpose === "other" && !i.custom_label.trim());
      if (unnamedOther) { toast("An item set to 'Other' needs its specific name (e.g. 'ISUFFAI Federation Fee').", true); return; }
      const missingRecipient = items.find((i) => {
        if (!RECIPIENT_RULES[i.purpose]?.required) return false;
        if (i.recipient_type === "external") {
          return !(i.external_campus || "").trim() || !(i.external_beneficiary || "").trim();
        }
        return !(i.recipient || "").trim();
      });
      if (missingRecipient) {
        const label = PURPOSES.find((p) => p.value === missingRecipient.purpose)?.label || missingRecipient.purpose;
        if (missingRecipient.recipient_type === "external") {
          toast(`${label} (other-campus) needs both the campus and the beneficiary name.`, true);
        } else {
          toast(`${label} needs a recipient — aid funds go to a specific member, or tick Other-campus aid.`, true);
        }
        return;
      }
    }
    // Normalize: monthly dues always go to the membership, even if a row was
    // switched after typing something else.
    items.forEach((i) => {
      if (RECIPIENT_RULES[i.purpose]?.fixed) i.recipient = RECIPIENT_RULES[i.purpose].fixed;
    });

    // A submission carries the scanned letter + sheet; drafts may attach later.
    const monthMatch = latestAssessments.find((a) => String(a.month || "").slice(0, 7) === month);
    const staged = maStagedFor(month);
    if (!draft) {
      const missing = [];
      if (!staged.request_letter.length && !(monthMatch && monthMatch.has_request_letter)) missing.push("request letter");
      if (!staged.deduction_sheet.length && !(monthMatch && monthMatch.has_deduction_sheet)) missing.push("deducted amount sheet");
      if (missing.length) {
        toast(`Attach the ${missing.join(" and ")} image(s) before submitting.`, true);
        return;
      }
      const totalAmount = items.reduce((s, i) => s + (parseFloat(i.amount) || 0), 0);
      const imageCount = staged.request_letter.length + staged.deduction_sheet.length;
      const proceed = await SimpleModal.confirm(
        `Submit the deduction for ${maMonthLabel(month)}? ` +
          `${items.length} item(s) totalling ${PESO(totalAmount)} per member` +
          (imageCount ? `, plus ${imageCount} image(s) to attach` : "") +
          ". The Treasurer will be notified.",
        { title: "Submit Deduction", okText: "Yes, submit", cancelText: "Cancel" }
      );
      if (!proceed) return;
    }

    const csrf = needCsrfToken(); if (!csrf) return;
    try {
      const resp = await fetch("/api/president/monthly-assessment/save/", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf },
        body: JSON.stringify({ month, items, draft }),
      });
      let data = null;
      try { data = await resp.json(); }
      catch (e) {
        toast(`Failed to save (server error ${resp.status}). Reload the page and try again.`, true);
        return;
      }
      if (!data.ok) { toast(data.error || "Failed to save.", true); return; }
      toast(data.message || "Deduction saved.", false);
      await maFlushStagedDocs(month);
      await loadMonthlyAssessments();
      // Move the form to the next open (not yet declared) month so the saved
      // one is not accidentally re-submitted.
      const monthSelect = document.getElementById("ma-month");
      const nextOpen = [...(monthSelect?.options || [])].find(
        (o) => o.value && !o.dataset.taken
      );
      if (nextOpen && monthSelect.value !== nextOpen.value) {
        monthSelect.value = nextOpen.value;
        maMonthChanged();
      } else if (monthSelect.value) {
        maMonthChanged();
      }
    } catch (e) {
      console.error("Failed to save assessment", e);
      toast("Failed to save.", true);
    }
  };

  // Pull a submitted month back to draft so a mistake can be fixed and the
  // month resubmitted. Only possible while the Treasurer has not recorded
  // anything against it — the server enforces that guard.
  window.maRecallAssessment = async function maRecallAssessment() {
    const month = (document.getElementById("ma-month") || {}).value || "";
    const match = month
      ? latestAssessments.find((a) => String(a.month || "").slice(0, 7) === month)
      : null;
    if (!match || match.status !== "pending_treasurer") {
      toast("Only a submitted month still awaiting the Treasurer can be recalled.", true);
      return;
    }
    const proceed = await SimpleModal.confirm(
      `Pull back the ${maMonthLabel(month)} deduction to draft? The Treasurer will be notified, and you can edit the breakdown and resubmit.`,
      { title: "Recall Deduction", okText: "Yes, recall to draft", cancelText: "Cancel" }
    );
    if (!proceed) return;
    const csrf = needCsrfToken(); if (!csrf) return;
    try {
      const resp = await fetch("/api/president/monthly-assessment/recall/", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf },
        body: JSON.stringify({ assessment_id: match.assessment_id }),
      });
      const data = await resp.json();
      if (!data.ok) { toast(data.error || "Failed to recall.", true); return; }
      toast(data.message || "Recalled to draft.", false);
      await loadMonthlyAssessments();
      maMonthChanged();
    } catch (e) {
      console.error("Failed to recall assessment", e);
      toast("Failed to recall.", true);
    }
  };

  window.maEditAssessment = async function maEditAssessment(assessmentId) {
    try {
      const resp = await fetch(`/api/president/monthly-assessment/${assessmentId}/`, { cache: "no-store" });
      const data = await resp.json();
      if (!data.ok) { toast(data.error || "Failed to load the deduction.", true); return; }
      const a = data.assessment;
      const monthInput = document.getElementById("ma-month");
      const itemsBody = document.getElementById("ma-items-body");
      if (!monthInput || !itemsBody) return;

      maSetMonthValue((a.month || "").slice(0, 7));
      // Run the full month-switch so the lock state, totals and the
      // already-attached images all refresh — not just the item rows.
      maMonthChanged();

      const detailPanel = document.getElementById("ma-detail-panel");
      if (detailPanel) detailPanel.style.display = "none";
      window.scrollTo({ top: 0, behavior: "smooth" });
      toast(`Loaded ${a.month_label} into the form. Adjust the amounts and save.`, false);
    } catch (e) {
      console.error("Failed to load assessment for editing", e);
      toast("Failed to load the deduction for editing.", true);
    }
  };

  /* Sketch-style per-member collection line: "Due 100 · Token 50 = ₱150 Paid". */
  function maMiniCollectionLine(ma) {
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

  window.maReviewAssessment = async function maReviewAssessment(assessmentId) {
    const panel = document.getElementById("ma-detail-panel");
    if (!panel) return;
    panel.style.display = "block";
    try {
      const resp = await fetch(`/api/president/monthly-assessment/${assessmentId}/`, { cache: "no-store" });
      const data = await resp.json();
      if (!data.ok) { toast(data.error || "Failed to load details.", true); return; }
      const a = data.assessment;
      const actionable = a.status === "pending_final";

      document.getElementById("ma-detail-title").innerHTML =
        `${a.month_label} — ${PESO(a.total_amount)} per member ${statusBadge(a.status, a.status_label)}`;

      const itemsHtml = (a.items || []).map((i) =>
        `<tr><td style="padding:5px 8px;">${i.purpose_label}</td><td style="padding:5px 8px;">${PESO(i.amount)}</td><td style="padding:5px 8px;">${(i.is_external || i.recipient_type === "external") ? `<span style="display:inline-block;font-size:0.66rem;font-weight:800;background:#e3f2fd;color:#0d47a1;border:1px solid #90caf9;padding:1px 8px;border-radius:10px;margin-right:6px;">EXTERNAL</span>For: ${i.external_display || i.recipient || ((i.external_campus || "") + ((i.external_campus && i.external_beneficiary) ? " — " : "") + (i.external_beneficiary || ""))}` : (i.recipient ? "For: " + i.recipient : "—")}</td></tr>`
      ).join("");

      const allocData = {};
      const memberSortKey = (value) => {
        const name = String(value || "").trim();
        if (name.includes(",")) return name.split(",", 1)[0].trim().toLocaleLowerCase();
        const parts = name.split(/\s+/);
        return parts.length ? parts[parts.length - 1].toLocaleLowerCase() : "";
      };
      const memberRows = (data.member_assessments || []).slice().sort((a, b) =>
        memberSortKey(a.member_name).localeCompare(memberSortKey(b.member_name), "en", { sensitivity: "base" }) ||
        String(a.member_name || "").localeCompare(String(b.member_name || ""), "en", { sensitivity: "base" })
      );
      const membersHtml = memberRows.map((ma) => {
        allocData[ma.member_assessment_id] = ma;
        const priorNote = ma.prior_outstanding > 0
          ? `<div style="font-size:0.75rem; font-weight:400; color:#8a6d3b;">prior ${PESO(ma.prior_outstanding)} from ${ma.prior_month_label || "previous month"} — collected ${PESO(ma.prior_outstanding_collected)}</div>`
          : "";
        const changeNote = ma.change_amount > 0
          ? `<div style="font-size:0.75rem; font-weight:400; color:#2e7d32;">excess to ISUCauFA funds: ${PESO(ma.change_amount)}</div>`
          : "";
        return `<tr>
            <td style="padding:6px 8px;">${ma.member_name}${ma.is_excluded ? ` <span style="display:inline-block;padding:1px 8px;border-radius:8px;font-size:0.66rem;font-weight:700;background:#fff3e0;color:#e65100;">Excluded</span>` : ""}</td>
            <td style="padding:6px 8px;">${PESO(ma.standard_assessment)}</td>
            <td style="padding:6px 8px;">${PESO(ma.actual_deduction)}</td>
            <td style="padding:6px 8px; ${ma.outstanding_balance > 0 ? "color:#c62828;font-weight:600;" : ""}">${PESO(ma.outstanding_balance)}</td>
            <td style="padding:6px 8px;">${ma.employee_id || "—"}</td>
            <td style="padding:6px 8px;">${ma.department || "—"}</td>
            <td style="padding:6px 8px; text-align:center;">
              <button type="button" class="btn-outline" style="padding:2px 10px; font-size:0.75rem;" onclick="maViewAllocations(${ma.member_assessment_id})">Allocations</button>
            </td>
          </tr>`;
      }).join("");
      window.__maAllocData = allocData;

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
          <td style="padding:6px 8px;">TOTAL (${totals.count} member${totals.count === 1 ? "" : "s"})</td>
          <td style="padding:6px 8px;">${PESO(totals.standard)}</td>
          <td style="padding:6px 8px;">${PESO(totals.deducted)}</td>
          <td style="padding:6px 8px; ${totals.outstanding > 0 ? "color:#c62828;" : "color:#1b5e20;"}">${PESO(totals.outstanding)}</td>
          <td colspan="3"></td>
        </tr>` : "";
      document.getElementById("ma-detail-body").innerHTML = `
        <div style="display:flex; flex-direction:column; gap:20px;">
          <div>
            <h4 style="margin:0 0 8px;">Member Deductions (${(data.member_assessments || []).length})</h4>
            <div style="max-height:420px; overflow:auto;">
            <table class="custom-table">
              <thead><tr><th>Member</th><th>Expected Collection / Per Member</th><th>Amount Deduction</th><th>Balance</th><th>Employee ID</th><th>Department</th><th style="text-align:center;">Details</th></tr></thead>
              <tbody>${membersHtml || '<tr><td colspan="7" style="text-align:center;color:#757575;padding:16px;">The Treasurer has not recorded deductions yet.</td></tr>'}</tbody><tfoot>${totalsRow}</tfoot>
            </table>
            </div>
          </div>
          <div>
            <h4 style="margin:0 0 8px;">Breakdown</h4>
            <table class="custom-table" style="table-layout:fixed;"><colgroup><col style="width:32%;"><col style="width:18%;"><col style="width:50%;"></colgroup><thead><tr><th>Purpose</th><th>Amount</th><th>Recipient</th></tr></thead><tbody>${itemsHtml || '<tr><td colspan="3">None</td></tr>'}</tbody></table>
          </div>
          <div style="padding:12px 14px; border:1px solid #a5d6a7; border-left:5px solid #2e7d32; border-radius:10px; background:#f3faf4; box-shadow:0 2px 6px rgba(46,125,50,0.10);">
            <h4 style="margin:0 0 10px; color:#1b5e20; font-size:0.9rem; letter-spacing:0.02em;"><i class="fa-solid fa-paperclip" style="color:#2e7d32; margin-right:6px;"></i>ATTACHMENTS TO REVIEW</h4>
            <div style="display:flex; gap:12px; flex-wrap:wrap; font-size:0.84rem;">
              <div>
                <strong style="display:inline-block; margin-right:4px;">Request Letter (ISUCauFA):</strong>
                ${(a.request_letter_images || []).length
                  ? a.request_letter_images.map((img, i) => `<a href="${img.url}" target="_blank" rel="noopener" style="color:#1565c0; text-decoration:underline; font-weight:600;">Image ${i + 1}</a>`).join(" · ")
                  : '<span style="color:#757575;">not attached</span>'}
              </div>
              <div>
                <strong style="display:inline-block; margin-right:4px;">Deducted Amount Sheet:</strong>
                ${(a.deduction_sheet_images || []).length
                  ? a.deduction_sheet_images.map((img, i) => `<a href="${img.url}" target="_blank" rel="noopener" style="color:#1565c0; text-decoration:underline; font-weight:600;">Image ${i + 1}</a>`).join(" · ")
                  : '<span style="color:#757575;">not attached</span>'}
              </div>
            </div>
          </div>
          ${typeof window.mdDepositEvidenceHtml === "function" ? window.mdDepositEvidenceHtml(a) : ""}
          ${typeof window.mdWorkflowTimelineHtml === "function" ? window.mdWorkflowTimelineHtml(data.workflow_logs || []) : ""}
        </div>`;

      const actions = document.getElementById("ma-detail-actions");
      if (actions) {
        actions.style.display = actionable ? "grid" : "none";
        actions.dataset.assessmentId = a.assessment_id;
        document.getElementById("ma-decision-remarks").value = "";
      }
    } catch (e) {
      console.error("Failed to load assessment details", e);
      toast("Failed to load assessment details.", true);
    }
  };


  // Allocation details open in a modal so the members table stays aligned.
  window.maViewAllocations = function maViewAllocations(memberAssessmentId) {
    const ma = (window.__maAllocData || {})[memberAssessmentId];
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


  window.maDecide = async function maDecide(action) {
    const actions = document.getElementById("ma-detail-actions");
    if (!actions) return;
    const assessmentId = actions.dataset.assessmentId;
    const notes = (document.getElementById("ma-decision-remarks") || {}).value || "";
    if (action === "return" && !notes.trim()) {
      toast("Remarks are required when returning an entry.", true);
      return;
    }
    if (action === "approve") {
      const proceed = await SimpleModal.confirm(
        "Final approve this monthly deduction? Member email notices will be sent.",
        { title: "Final Approval", okText: "Approve & Email", cancelText: "Cancel" }
      );
      if (!proceed) return;
    }

    const csrf = needCsrfToken(); if (!csrf) return;
    try {
      const resp = await fetch("/api/president/deductions/approve/", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf },
        body: JSON.stringify({ assessment_id: Number(assessmentId), action, notes }),
      });
      const data = await resp.json();
      if (!data.ok) { toast(data.error || "Action failed.", true); return; }
      toast(data.message || "Done.", false);
      loadMonthlyAssessments();
      maReviewAssessment(assessmentId);
    } catch (e) {
      console.error("Failed to submit decision", e);
      toast("Failed to submit decision.", true);
    }
  };


  document.addEventListener("DOMContentLoaded", () => {
    setupDropzones();
    loadMonthlyAssessments().then(() => {
      const itemsBody = document.getElementById("ma-items-body");
      if (itemsBody && !itemsBody.children.length) {
        maAddItemRow("monthly_due", defaultMonthlyDue, 1);
      }
      maMonthChanged();
    });
  });

  /* Turbo navigations never re-fire DOMContentLoaded — without this the
     Monthly Deduction sidebar dot (pending president approval) would stay
     unset until a hard refresh. */
  document.addEventListener("turbo:load", () => {
    loadMonthlyAssessments();
  });
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
    const ws = new WebSocket(`${proto}${window.location.host}/ws/president-dashboard/?token=${encodeURIComponent(window.WS_AUTH_TOKEN || "")}`);
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "deduction_counts") setBadge("ma-pending-dot", msg["pending_final"] || 0);
      } catch (e) {}
    };
  } catch (e) {}

