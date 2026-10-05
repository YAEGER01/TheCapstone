// batch_upload_members.js — Excel-style batch member registration grid.
// Typing works like a spreadsheet: Enter moves DOWN to the next row (creating
// it automatically), Shift+Enter moves up, arrow keys navigate rows, Tab moves
// across cells, and pasting a range copied from Excel (Ctrl+C in Excel →
// Ctrl+V here) fills the whole grid starting at the focused cell.
(function () {
  "use strict";

  var tableBody = document.getElementById("batchMembersBody");
  var addRowBtn = document.getElementById("addBatchMemberRowBtn");
  var saveBtn = document.getElementById("batchMembersSaveBtn");
  if (!tableBody || !saveBtn) return;

  // Keyboard/paste column order. The photo cell is mouse-only and skipped.
  var FIELD_SELECTORS = [
    ".batch-first-name",     // col 0
    ".batch-middle-initial", // col 1
    ".batch-last-name",      // col 2
    ".batch-email",          // col 3
    ".batch-contact",        // col 4
    ".batch-department",     // col 5
    ".batch-position",       // col 6
  ];
  var MAX_ROWS = 500;

  var positionRanksCache = null;
  var positionFetchPromise = null;

  function csrfToken() {
    var input = document.querySelector("input[name='csrfmiddlewaretoken']");
    return input ? input.value : "";
  }

  function toast(msg, isError) {
    if (typeof showToast === "function") showToast(msg, !!isError);
    else console.log(isError ? "ERROR: " + msg : msg);
  }

  function formatContact(value) {
    var digits = (value || "").replace(/\D/g, "").slice(0, 11);
    if (digits.length > 7) return digits.slice(0, 4) + "-" + digits.slice(4, 7) + "-" + digits.slice(7);
    if (digits.length > 4) return digits.slice(0, 4) + "-" + digits.slice(4, 7);
    return digits;
  }

  function loadStyles() {
    if (document.getElementById("batchGridStyles")) return;
    var style = document.createElement("style");
    style.id = "batchGridStyles";
    style.textContent =
      "#batchMembersTable tbody tr.batch-row-active td { background:#f4faf5; }" +
      "#batchMembersTable input:focus, #batchMembersTable select:focus {" +
      "  outline:none; border-color:#1b5e20 !important; box-shadow:0 0 0 2px rgba(27,94,32,.15); }" +
      "#batchMembersTable input, #batchMembersTable select { transition: border-color .1s, box-shadow .1s; }" +
      ".batch-paste-hint { font-size:11px; color:#757575; margin-top:6px; }" +
      ".batch-paste-hint kbd { background:#f0f0f0; border:1px solid #ccc; border-radius:3px; padding:0 4px; font-size:10px; font-family:inherit; }";
    document.head.appendChild(style);
  }

  function rows() {
    // Data rows only — inline validation error rows are skipped so column
    // mapping and numbering always line up with what the user sees.
    return Array.prototype.slice.call(tableBody.querySelectorAll("tr")).filter(function (r) {
      return !r.classList.contains("row-error-message");
    });
  }

  function updateRowNumbers() {
    rows().forEach(function (row, index) {
      var numberCell = row.querySelector("td:first-child");
      if (numberCell) numberCell.textContent = index + 1;
      row.setAttribute("data-row-num", String(index + 1));
    });
  }

  function highlightActiveRow(row) {
    rows().forEach(function (r) { r.classList.remove("batch-row-active"); });
    if (row) row.classList.add("batch-row-active");
  }

  function populatePositionSelect(select) {
    select.innerHTML = '<option value="">Select position</option>';
    (positionRanksCache || []).forEach(function (r) {
      var opt = document.createElement("option");
      opt.value = r.name;
      opt.textContent = r.name;
      select.appendChild(opt);
    });
  }

  function loadPositionRanks() {
    if (positionRanksCache) return Promise.resolve(positionRanksCache);
    if (positionFetchPromise) return positionFetchPromise;
    positionFetchPromise = fetch("/api/treasurer/members/position-ranks/options/", { credentials: "same-origin" })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        positionRanksCache = (data && data.ok && data.ranks) ? data.ranks : [];
        tableBody.querySelectorAll(".batch-position").forEach(populatePositionSelect);
        return positionRanksCache;
      })
      .catch(function () { positionRanksCache = []; return positionRanksCache; });
    return positionFetchPromise;
  }

  function createMemberRow() {
    if (rows().length >= MAX_ROWS) { toast("The grid is limited to " + MAX_ROWS + " rows.", true); return null; }

    var row = document.createElement("tr");

    function cellHtml(className, col, extra) {
      return '<input type="text" class="' + className + '" data-col="' + col + '" ' + (extra || "") +
        ' style="width:100%;padding:6px 6px;border:1px solid #cfdccc;border-radius:6px;font-size:13px;" />';
    }

    row.innerHTML =
      '<td style="text-align:center;font-size:13px;color:#757575;"></td>' +
      "<td>" + cellHtml("batch-first-name", 0, 'placeholder="Juan"') + "</td>" +
      "<td>" + cellHtml("batch-middle-initial", 1, 'maxlength="1" placeholder="R"') + "</td>" +
      "<td>" + cellHtml("batch-last-name", 2, 'placeholder="Dela Cruz"') + "</td>" +
      '<td><select class="batch-kind" style="width:100%;padding:6px 6px;border:1px solid #cfdccc;border-radius:6px;font-size:13px;">' +
        '<option value="new" selected>New</option><option value="old">Old</option>' +
      "</select></td>" +
      '<td><select class="batch-classification" style="width:100%;padding:6px 6px;border:1px solid #cfdccc;border-radius:6px;font-size:13px;">' +
        '<option value="Teaching" selected>Teaching</option><option value="Retired">Retired</option>' +
      "</select></td>" +
      '<td><input type="email" class="batch-email" data-col="3" placeholder="emailaddress@isu.edu.ph" style="width:100%;padding:6px 6px;border:1px solid #cfdccc;border-radius:6px;font-size:13px;" /></td>' +
      '<td><input type="tel" class="batch-contact" data-col="4" maxlength="13" placeholder="0917-123-4567" style="width:100%;padding:6px 6px;border:1px solid #cfdccc;border-radius:6px;font-size:13px;" /></td>' +
      "<td>" +
        '<label class="file-upload-btn" style="display:inline-block;padding:4px 8px;background:#f0f0f0;border:1px solid #ccc;border-radius:4px;cursor:pointer;font-size:12px;">Upload Photo' +
          '<input type="file" class="batch-photo" accept="image/*" style="display:none;" />' +
        "</label>" +
        '<span class="file-name" style="font-size:10px;color:#666;margin-left:4px;"></span>' +
      "</td>" +
      '<td><select class="batch-department" data-col="5" style="width:100%;padding:6px 6px;border:1px solid #cfdccc;border-radius:6px;font-size:13px;">' +
        '<option value="">Select department</option><option>IAT</option><option>CCJE</option><option>CCSICT</option><option>PS</option><option>SAS</option><option>CBM</option><option>CED</option>' +
      "</select></td>" +
      '<td><select class="batch-position" data-col="6" style="width:100%;padding:6px 6px;border:1px solid #cfdccc;border-radius:6px;font-size:13px;"><option value="">Loading…</option></select></td>' +
      '<td style="text-align:center;">' +
        '<button type="button" class="remove-row-btn" title="Remove row" style="background:#d93636;color:white;border:none;border-radius:4px;padding:4px 8px;font-size:12px;font-weight:600;cursor:pointer;">Remove</button>' +
      "</td>";

    tableBody.appendChild(row);
    updateRowNumbers();

    // Remove button
    row.querySelector(".remove-row-btn").addEventListener("click", function () {
      var err = row.nextElementSibling;
      if (err && err.classList.contains("row-error-message")) err.remove();
      var wasLast = rows().length === 1;
      row.remove();
      updateRowNumbers();
      if (wasLast) createMemberRow(); // never leave an empty grid
    });

    // Photo filename display
    var photoInput = row.querySelector(".batch-photo");
    var fileNameSpan = row.querySelector(".file-name");
    photoInput.addEventListener("change", function () {
      var name = photoInput.files && photoInput.files[0] ? photoInput.files[0].name : "";
      if (name.length > 15) name = name.substring(0, 12) + "…";
      fileNameSpan.textContent = name;
    });

    // Middle initial auto-uppercase
    var mi = row.querySelector(".batch-middle-initial");
    mi.addEventListener("input", function () { mi.value = mi.value.toUpperCase(); });

    // Contact auto-format
    var contact = row.querySelector(".batch-contact");
    contact.addEventListener("input", function () { contact.value = formatContact(contact.value); });

    // Email auto-lowercase
    var email = row.querySelector(".batch-email");
    email.addEventListener("input", function () {
      var pos = email.selectionStart;
      email.value = email.value.toLowerCase();
      try { email.setSelectionRange(pos, pos); } catch (e) {}
    });

    // Clear error styling while typing
    row.querySelectorAll("input, select").forEach(function (field) {
      field.addEventListener("input", function () {
        field.style.borderColor = "#cfdccc";
        field.classList.remove("batch-error-field");
        var err = row.nextElementSibling;
        if (err && err.classList.contains("row-error-message")) err.remove();
      });
      field.addEventListener("focus", function () { highlightActiveRow(row); });
    });

    attachNav(row);
    populatePositionSelect(row.querySelector(".batch-position"));
    return row;
  }

  /* ---------------- Excel-style navigation ---------------- */

  function cellOf(el) {
    // Returns {row, rowIndex, col} for an input/select inside the grid.
    var row = el.closest("tr");
    if (!row || !tableBody.contains(row)) return null;
    var allRows = rows();
    return { row: row, rowIndex: allRows.indexOf(row), col: parseInt(el.getAttribute("data-col"), 10) };
  }

  function focusCell(rowIndex, col) {
    var allRows = rows();
    if (rowIndex < 0 || rowIndex >= allRows.length) return;
    var el = allRows[rowIndex].querySelector(FIELD_SELECTORS[col]);
    if (!el) return;
    el.focus();
    if (el.tagName === "INPUT" && el.type !== "tel") {
      try { el.select(); } catch (e) {}
    }
  }

  function moveVertical(el, delta) {
    var pos = cellOf(el);
    if (!pos) return;
    var target = pos.rowIndex + delta;
    if (target >= rows().length && delta > 0) {
      var newRow = createMemberRow(); // Enter at the last row adds a row — like Excel
      if (!newRow) return;
    }
    focusCell(target, pos.col);
  }

  function attachNav(row) {
    row.querySelectorAll("input[data-col], select[data-col]").forEach(function (el) {
      el.addEventListener("keydown", function (e) {
        var isInput = el.tagName === "INPUT";
        if (e.key === "Enter") {
          e.preventDefault();
          moveVertical(el, e.shiftKey ? -1 : 1);
        } else if (e.key === "ArrowDown" && isInput) {
          e.preventDefault();
          moveVertical(el, 1);
        } else if (e.key === "ArrowUp" && isInput) {
          e.preventDefault();
          moveVertical(el, -1);
        }
        // ArrowLeft/ArrowRight and Tab keep their native behavior inside the
        // text; Tab moves to the next cell in DOM order, like a spreadsheet.
      });
    });
  }

  /* ---------------- Paste from Excel ---------------- */

  function setCellValue(el, value) {
    var v = (value == null ? "" : String(value)).trim();
    if (el.classList.contains("batch-contact")) {
      el.value = formatContact(v);
    } else if (el.classList.contains("batch-email")) {
      el.value = v.toLowerCase();
    } else if (el.classList.contains("batch-middle-initial")) {
      el.value = v.toUpperCase().slice(0, 1);
    } else if (el.tagName === "SELECT") {
      var match = null;
      Array.prototype.slice.call(el.options).forEach(function (opt) {
        if (!match && opt.value && opt.value.toLowerCase() === v.toLowerCase()) match = opt.value;
      });
      el.value = match || "";
    } else {
      el.value = v;
    }
  }

  function fillFromPaste(startRowIndex, startCol, lines) {
    var created = 0;
    for (var i = 0; i < lines.length; i++) {
      var rowIndex = startRowIndex + i;
      while (rows().length <= rowIndex) { if (!createMemberRow()) return; created++; }
      var tokens = lines[i];
      for (var k = 0; k < tokens.length; k++) {
        var col = startCol + k;
        if (col >= FIELD_SELECTORS.length) break; // clip past the last column
        var el = rows()[rowIndex].querySelector(FIELD_SELECTORS[col]);
        if (el) setCellValue(el, tokens[k]);
      }
    }
    updateRowNumbers();
    if (created > 0) toast("Pasted " + lines.length + " row(s) from the clipboard.");
  }

  tableBody.addEventListener("paste", function (e) {
    var target = e.target;
    if (!target || !(target.matches && target.matches("input[data-col], select[data-col]"))) return;
    var text = (e.clipboardData || window.clipboardData).getData("text/plain") || "";
    if (!text) return;
    var lines = text.replace(/\r/g, "").split("\n").filter(function (l) { return l.trim() !== ""; })
      .map(function (l) { return l.split("\t"); });
    var isRange = lines.length > 1 || lines[0].length > 1;
    if (!isRange) return; // single value — paste normally into the cell
    e.preventDefault();
    var pos = cellOf(target);
    if (!pos) return;
    fillFromPaste(pos.rowIndex, pos.col, lines);
  });

  /* ---------------- Validation + save ---------------- */

  function validateIsuEmail(value) {
    const v = (value || "").trim();
    if (!v) return false;
    const guardOn = typeof window.ISU_EMAIL_GUARD_ENABLED === "undefined" || window.ISU_EMAIL_GUARD_ENABLED !== false;
    if (!guardOn) return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
    return /^[A-Za-z0-9._%+-]+@isu\.edu\.ph$/.test(v);
  }
  function validatePhContact(value) {
    return /^09\d{9}$/.test((value || "").replace(/\D/g, ""));
  }

  function markError(row, selector) {
    var el = row.querySelector(selector);
    if (el) {
      el.classList.add("batch-error-field");
      el.style.borderColor = "#c62828";
    }
  }

  function collectMemberData() {
    var allRows = rows();
    var members = [];
    var errors = [];

    document.querySelectorAll(".row-error-message").forEach(function (el) { el.remove(); });
    document.querySelectorAll(".batch-error-field").forEach(function (el) {
      el.style.borderColor = "#cfdccc";
      el.classList.remove("batch-error-field");
    });

    allRows.forEach(function (row, index) {
      var firstName = row.querySelector(".batch-first-name").value.trim();
      var middleInitial = row.querySelector(".batch-middle-initial").value.trim();
      var lastName = row.querySelector(".batch-last-name").value.trim();
      var email = row.querySelector(".batch-email").value.trim();
      var contact = row.querySelector(".batch-contact").value.trim();
      var department = row.querySelector(".batch-department").value;
      var position = row.querySelector(".batch-position").value;
      var memberKind = (row.querySelector(".batch-kind") || {}).value || "new";
      var classification = (row.querySelector(".batch-classification") || {}).value || "Teaching";
      var photoInput = row.querySelector(".batch-photo");

      // Skip fully empty rows — they are just leftover spreadsheet space.
      if (!firstName && !lastName && !email && !contact && !department && !position) return;

      var rowErrors = [];
      if (!firstName) { rowErrors.push("First Name is required"); markError(row, ".batch-first-name"); }
      if (!lastName) { rowErrors.push("Last Name is required"); markError(row, ".batch-last-name"); }
      if (!email) {
        rowErrors.push("Email is required — e.g. name@example.com");
        markError(row, ".batch-email");
      } else if (!validateIsuEmail(email)) {
        const guardOn = typeof window.ISU_EMAIL_GUARD_ENABLED === "undefined" || window.ISU_EMAIL_GUARD_ENABLED !== false;
        rowErrors.push(guardOn
          ? "Not an ISU email — use your @isu.edu.ph address (e.g. name@isu.edu.ph)"
          : "Not a valid email address");
        markError(row, ".batch-email");
      }
      if (contact && !validatePhContact(contact)) {
        rowErrors.push("Contact must be 11 digits starting with 09");
        markError(row, ".batch-contact");
      }
      if (!department) { rowErrors.push("Department is required"); markError(row, ".batch-department"); }
      if (!position) { rowErrors.push("Academic Rank is required"); markError(row, ".batch-position"); }

      if (rowErrors.length > 0) {
        errors.push("Row " + (index + 1) + ": " + rowErrors.join(", "));
        var errorRow = document.createElement("tr");
        errorRow.className = "row-error-message";
        errorRow.innerHTML =
          '<td colspan="12" style="background:#fee;border:1px solid #c62828;color:#c62828;padding:8px;font-size:11px;font-weight:600;text-align:center;"></td>';
        errorRow.firstChild.textContent = "⚠ " + rowErrors.join(" • ");
        row.parentNode.insertBefore(errorRow, row.nextSibling);
        return;
      }

      members.push({
        data: {
          first_name: firstName,
          middle_initial: middleInitial,
          last_name: lastName,
          email: email,
          contact: contact,
          department: department,
          position: position,
          classification: classification,
          member_kind: memberKind,
          membership_category: classification === "Retired" ? "Permanent" : "Permanent",
          username: email.split("@")[0],
          amount: memberKind === "new" ? "100" : "",
          payment_method: memberKind === "new" ? "Pending" : "",
        },
        photo: photoInput.files && photoInput.files[0] ? photoInput.files[0] : null,
      });
    });

    return { members: members, errors: errors };
  }

  addRowBtn.addEventListener("click", function () {
    var row = createMemberRow();
    if (row) focusCell(rows().length - 1, 0);
  });

  saveBtn.addEventListener("click", async function () {
    var collected = collectMemberData();

    if (collected.errors.length > 0) {
      toast("Some rows need a double check — see the highlighted rows below for the details.", true);
      return;
    }
    if (collected.members.length === 0) {
      toast("The grid is empty — type or paste member rows first.", true);
      return;
    }

    saveBtn.disabled = true;
    saveBtn.textContent = "Saving…";

    try {
      var succeeded = 0;
      var failed = 0;
      var failedNames = [];

      for (var i = 0; i < collected.members.length; i++) {
        var member = collected.members[i];
        var body = new FormData();
        Object.keys(member.data).forEach(function (key) {
          if (member.data[key] !== "" && member.data[key] != null) body.append(key, member.data[key]);
        });
        if (member.photo) body.append("photo", member.photo);

        try {
          var url = member.data.member_kind === "old"
            ? "/api/treasurer/members/create-old/"
            : "/api/treasurer/members/create/";
          var response = await fetch(url, {
            method: "POST",
            body: body,
            headers: { "X-CSRFToken": csrfToken() },
            credentials: "same-origin",
          });
          var data = await response.json().catch(function () { return {}; });
          if (response.ok && data.ok) {
            succeeded++;
          } else {
            failed++;
            failedNames.push((member.data.first_name + " " + member.data.last_name).trim() + " — " + (data.error || "Unknown error"));
          }
        } catch (error) {
          failed++;
          failedNames.push((member.data.first_name + " " + member.data.last_name).trim() + " — " + error.message);
        }
      }

      if (failed === 0) {
        toast("All " + succeeded + " member(s) registered — passwords emailed to their ISU addresses.");
        tableBody.innerHTML = "";
        createMemberRow();
      } else {
        toast("Saved " + succeeded + ", failed " + failed + ". First failure: " + failedNames[0], true);
      }
    } catch (error) {
      toast("An error occurred: " + error.message, true);
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = "Save All Members";
    }
  });

  // Init: one ready-to-type row (Excel always has an active cell)
  loadStyles();
  loadPositionRanks();
  createMemberRow();
})();
