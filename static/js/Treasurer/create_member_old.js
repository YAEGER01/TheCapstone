// create_member_old.js — Register OLD / existing ISUCauFA, Inc. members.
// No membership fee / fund entry, but the member still receives a dashboard
// account: the password is auto-generated and emailed to their ISU address.
(function () {
  "use strict";

  const form = document.getElementById("createMemberOldForm");
  if (!form) return;

  function value(id) {
    const element = document.getElementById(id);
    return element ? element.value.trim() : "";
  }

  function csrfToken() {
    const input = document.querySelector("input[name='csrfmiddlewaretoken']");
    return input ? input.value : "";
  }

  // Member accounts require a valid email (ISU when the guard is on).
  function isIsuEmailGuardEnabled() {
    return typeof window.ISU_EMAIL_GUARD_ENABLED === "undefined" || window.ISU_EMAIL_GUARD_ENABLED !== false;
  }
  function isValidIsuEmail(v) {
    const value = (v || "").trim();
    if (!value) return false;
    if (!isIsuEmailGuardEnabled()) return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
    return /^[A-Za-z0-9._%+-]+@isu\.edu\.ph$/.test(value);
  }

  // PH mobile numbers: 11 digits starting with 09 (e.g. 09171234567)
  function isValidPhContact(value) {
    const digits = (value || "").replace(/\D/g, "");
    return /^09\d{9}$/.test(digits);
  }

  async function loadPositionRankDropdown() {
    const select = document.getElementById("old_position");
    if (!select) return;
    try {
      const resp = await fetch("/api/treasurer/members/position-ranks/options/", { credentials: "same-origin" });
      const data = await resp.json();
      if (!data || !data.ok || !data.ranks) return;
      select.innerHTML = '<option value="">Select Position</option>';
      data.ranks.forEach(function (r) {
        const opt = document.createElement("option");
        opt.value = r.name;
        opt.textContent = r.name;
        select.appendChild(opt);
      });
    } catch (e) {
      console.error("Failed to load position ranks", e);
    }
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();

    if (!value("old_first_name") || !value("old_last_name")) {
      if (typeof showToast === "function") showToast("First Name and Last Name are required.", true);
      return;
    }

    if (!isValidIsuEmail(value("old_email"))) {
      if (typeof showToast === "function") showToast(
        isIsuEmailGuardEnabled()
          ? "Email must be a valid ISU email address in the format emailaddress@isu.edu.ph."
          : "Email must be a valid email address.",
        true
      );
      const emailField = document.getElementById("old_email");
      if (emailField) emailField.focus();
      return;
    }

    if (!value("old_position")) {
      if (typeof showToast === "function") showToast("Academic Rank is required.", true);
      const positionField = document.getElementById("old_position");
      if (positionField) positionField.focus();
      return;
    }

    const contactValue = value("old_contact");
    if (contactValue && !isValidPhContact(contactValue)) {
      if (typeof showToast === "function") showToast("Contact number must be a valid PH mobile number: 11 digits starting with 09.", true);
      const contactField = document.getElementById("old_contact");
      if (contactField) contactField.focus();
      return;
    }

    const payload = new FormData();
    payload.append("first_name", value("old_first_name"));
    payload.append("middle_initial", value("old_middle_initial"));
    payload.append("last_name", value("old_last_name"));
    payload.append("email", value("old_email"));
    payload.append("department", value("old_department"));
    payload.append("position", value("old_position"));
    payload.append("classification", value("old_classification"));
    payload.append("membership_category", value("old_membership_category"));
    payload.append("contact", value("old_contact"));

    // Optional member photo
    const photoInput = document.getElementById("old_photo");
    if (photoInput && photoInput.files && photoInput.files[0]) {
      payload.append("photo", photoInput.files[0]);
    }

    const submit = form.querySelector("button[type='submit']");
    if (submit) submit.disabled = true;

    // Duplicate email check — an email can only belong to one member.
    const emailValue = value("old_email");
    if (emailValue) {
      try {
        const checkBody = new FormData();
        checkBody.append("check_email", emailValue);
        const checkResp = await fetch("/api/treasurer/members/add/", {
          method: "POST",
          body: checkBody,
          headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin",
        });
        const checkData = await checkResp.json();
        if (checkData.error && checkData.error.includes("already taken")) {
          if (submit) submit.disabled = false;
          if (typeof showToast === "function") showToast("This email address already exists — it is already used by a member of the association.", true);
          const emailField = document.getElementById("old_email");
          if (emailField) emailField.focus();
          return;
        }
      } catch (e) { /* fall through — the backend re-validates */ }
    }
    try {
      const response = await fetch("/api/treasurer/members/create-old/", {
        method: "POST",
        body: payload,
        headers: { "X-CSRFToken": csrfToken() },
        credentials: "same-origin",
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.error || "Unable to register the old member.");
      }
      const emailValue = value("old_email");
      const emailNote = data.credentials_sent
        ? "The credentials were emailed to " + emailValue + ". The member can log in with their email address OR their username."
        : "<b>⚠ The credentials email failed to send.</b> Share the login details below with the member manually.";
      const credHtml =
        '<p style="font-size:0.9rem;color:#374151;margin:0 0 10px;">' + emailNote + '</p>' +
        '<table style="width:100%;font-size:0.9rem;">' +
        '<tr><td style="padding:6px 0;color:#6b7280;">Login Username</td><td style="text-align:right;font-weight:800;font-family:monospace;">' + (data.username || "—") + '</td></tr>' +
        '<tr><td style="padding:6px 0;color:#6b7280;">Password</td><td style="text-align:right;font-weight:800;font-family:monospace;color:#b91c1c;">' + (data.password || "—") + '</td></tr>' +
        '<tr><td style="padding:6px 0;color:#6b7280;">Email</td><td style="text-align:right;font-weight:600;">' + emailValue + '</td></tr>' +
        '</table>';
      if (window.SimpleModal && SimpleModal.open) {
        SimpleModal.open({ title: "Old Member Registered — Login Credentials", html: credHtml, width: "460px" });
      }
      if (typeof showToast === "function") showToast(data.message || "Old member registered.");
      form.reset();
      loadPositionRankDropdown();
    } catch (error) {
      if (typeof showToast === "function") showToast(error.message, true);
    } finally {
      if (submit) submit.disabled = false;
    }
  });

  // Live-format the contact field (0917-123-4567)
  (function initContactFormat() {
    const contactInput = document.getElementById("old_contact");
    if (!contactInput) return;
    contactInput.addEventListener("input", function () {
      let digits = contactInput.value.replace(/\D/g, "").slice(0, 11);
      let formatted = digits;
      if (digits.length > 7) formatted = digits.slice(0, 4) + "-" + digits.slice(4, 7) + "-" + digits.slice(7);
      else if (digits.length > 4) formatted = digits.slice(0, 4) + "-" + digits.slice(4, 7);
      else if (digits.length === 4) formatted = digits;
      contactInput.value = formatted;
    });
  })();

  // Live PH phone number validation — shows validation status while typing
  (function initContactValidation() {
    const contactInput = document.getElementById("old_contact");
    if (!contactInput) return;
    const statusEl = document.createElement("p");
    statusEl.style.cssText = "font-size:11px;margin-top:4px;display:none;";
    contactInput.insertAdjacentElement("afterend", statusEl);

    function setStatus(ok, message) {
      statusEl.style.display = "block";
      statusEl.style.color = ok ? "#2e7d32" : "#c62828";
      statusEl.textContent = message;
    }

    contactInput.addEventListener("input", function () {
      const value = contactInput.value.trim();
      if (!value) {
        statusEl.style.display = "none";
        return;
      }
      if (isValidPhContact(value)) {
        setStatus(true, "Valid PH mobile number.");
      } else {
        setStatus(false, "Must be 11 digits starting with 09 (e.g., 0917-123-4567).");
      }
    });
  })();

  // Live email availability check — same behavior as Create Member (new).
  // Shows instantly while typing whether the email already exists.
  (function initEmailCheck() {
    const emailInput = document.getElementById("old_email");
    if (!emailInput) return;
    const statusEl = document.createElement("p");
    statusEl.style.cssText = "font-size:11px;margin-top:4px;display:none;";
    emailInput.insertAdjacentElement("afterend", statusEl);

    let timer = null;

    function setStatus(ok, message) {
      statusEl.style.display = "block";
      statusEl.style.color = ok ? "#2e7d32" : "#c62828";
      statusEl.textContent = message;
    }

    emailInput.addEventListener("input", function () {
      clearTimeout(timer);
      const value = emailInput.value.trim();
      if (!value) { statusEl.style.display = "none"; return; }
      if (!isValidIsuEmail(value)) {
        setStatus(false, isIsuEmailGuardEnabled()
          ? "Enter a valid ISU email address (emailaddress@isu.edu.ph)."
          : "Enter a valid email address.");
        return;
      }
      timer = setTimeout(async function () {
        try {
          const body = new FormData();
          body.append("check_email", value);
          const resp = await fetch("/api/treasurer/members/add/", {
            method: "POST",
            body: body,
            headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin",
          });
          const data = await resp.json();
          if (data.error && data.error.includes("already taken")) {
            setStatus(false, "This email address already exists — used by another member.");
          } else {
            setStatus(true, "Email is available.");
          }
        } catch (e) {
          /* keep the last state on network errors */
        }
      }, 350);
    });
  })();

  loadPositionRankDropdown();
})();
