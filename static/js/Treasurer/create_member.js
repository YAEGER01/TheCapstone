(function () {
  "use strict";

  const form = document.getElementById("createMemberForm");
  if (!form) return;

  function value(id) {
    const element = document.getElementById(id);
    return element ? element.value.trim() : "";
  }

  function csrfToken() {
    const input = document.querySelector("input[name='csrfmiddlewaretoken']");
    return input ? input.value : "";
  }

  async function emailIsAvailable(email) {
    const body = new FormData();
    body.append("check_email", email);
    const response = await fetch("/api/treasurer/members/add/", {
      method: "POST",
      body: body,
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": csrfToken(),
      },
      credentials: "same-origin",
    });
    const data = await response.json();
    return !(data.error && data.error.includes("already taken"));
  }

  // PH mobile numbers — always displayed as 09##-###-####. Type it as
  // 09171234567, +639171234567 or 639171234567; it collapses to one shape.
  function isValidPhContact(value) {
    if (window.PHONE_FORMAT) return window.PHONE_FORMAT.isValid(value);
    const digits = (value || "").replace(/\D/g, "");
    return /^09\d{9}$/.test(digits);
  }

  // Member accounts require a valid email (ISU when the guard is on).
  function isIsuEmailGuardEnabled() {
    return typeof window.ISU_EMAIL_GUARD_ENABLED === "undefined" || window.ISU_EMAIL_GUARD_ENABLED !== false;
  }
  function isValidIsuEmail(value) {
    const v = (value || "").trim();
    if (!v) return false;
    if (!isIsuEmailGuardEnabled()) return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
    return /^[A-Za-z0-9._%+-]+@isu\.edu\.ph$/.test(v);
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    const emailValue = value("create_email");
    if (!isValidIsuEmail(emailValue)) {
      if (typeof showToast === "function") showToast(
        isIsuEmailGuardEnabled()
          ? "Email must be a valid ISU email address in the format emailaddress@isu.edu.ph."
          : "Email must be a valid email address.",
        true
      );
      const emailField = document.getElementById("create_email");
      if (emailField) emailField.focus();
      return;
    }
    if (emailValue && !(await emailIsAvailable(emailValue))) {
      if (typeof showToast === "function") showToast("This email address already exists — it is already used by a member of the association.", true);
      const emailField = document.getElementById("create_email");
      if (emailField) emailField.focus();
      return;
    }
    const positionValue = value("create_position");
    if (!positionValue) {
      if (typeof showToast === "function") showToast("Academic Rank is required.", true);
      const positionField = document.getElementById("create_position");
      if (positionField) positionField.focus();
      return;
    }
    const contactValue = value("create_contact");
    if (contactValue && !isValidPhContact(contactValue)) {
      if (typeof showToast === "function") showToast("Contact number must be a valid PH mobile number: 11 digits starting with 09.", true);
      const contactField = document.getElementById("create_contact");
      if (contactField) contactField.focus();
      return;
    }
    const payload = new FormData();
    const fields = {
      first_name: "create_first_name",
      middle_initial: "create_middle_initial",
      last_name: "create_last_name",
      name_ext: "create_name_ext",
      email: "create_email",
      department: "create_department",
      position: "create_position",
      classification: "create_classification",
      membership_category: "create_membership_category",
      contact: "create_contact",
      amount: "create_amount",
    };
    Object.keys(fields).forEach(function (key) {
      payload.append(key, value(fields[key]));
    });
    const photoInput = document.getElementById("create_photo");
    if (photoInput && photoInput.files && photoInput.files[0]) {
      payload.append("photo", photoInput.files[0]);
    }

    const submit = form.querySelector("button[type='submit']");
    if (submit) submit.disabled = true;
    try {
      const response = await fetch("/api/treasurer/members/create/", {
        method: "POST",
        body: payload,
        headers: { "X-CSRFToken": csrfToken() },
        credentials: "same-origin",
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.error || "Unable to submit the Register New Member request.");
      }
      // Never show the password on the Treasurer's screen — it is delivered
      // to the member's email only. Just confirm the account was created.
      const credHtml =
        '<p style="font-size:0.95rem;color:#374151;margin:0;">' +
        'An Account for the new member has been created, notify the member to check the email inbox/spam to get the login credentials.' +
        '</p>';
      if (window.SimpleModal && SimpleModal.open) {
        SimpleModal.open({ title: "Member Registered", html: credHtml, width: "460px" });
      }
      if (typeof showToast === "function") showToast(data.message || "Register New Member request submitted.");
      form.reset();
      loadPositionRankDropdown();
    } catch (error) {
      if (typeof showToast === "function") showToast(error.message, true);
    } finally {
      if (submit) submit.disabled = false;
    }
  });

  // Live-format the contact field — 09##-###-#### regardless of whether the
  // member types a local (0917...), +63 or 63 prefix. Shared with File Death
  // Aid's Claimant Contact via static/js/shared/phone_format.js.
  (function initContactFormat() {
    const contactInput = document.getElementById("create_contact");
    if (!contactInput) return;
    if (window.PHONE_FORMAT) window.PHONE_FORMAT.attach(contactInput);
    else contactInput.addEventListener("input", function () {
      let digits = contactInput.value.replace(/\D/g, "").slice(0, 11);
      let formatted = digits;
      if (digits.length > 7) formatted = digits.slice(0, 4) + "-" + digits.slice(4, 7) + "-" + digits.slice(7);
      else if (digits.length > 4) formatted = digits.slice(0, 4) + "-" + digits.slice(4, 7);
      contactInput.value = formatted;
    });
  })();

  // Live PH phone number validation — shows validation status while typing
  (function initContactValidation() {
    const contactInput = document.getElementById("create_contact");
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
        setStatus(false, "Must be 11 digits starting with 09 (e.g., 0917-123-4567). +63 / 63 prefixes are converted automatically.");
      }
    });
  })();

  // Populate Academic Rank dropdown from the same source as Add Member Profile
  async function loadPositionRankDropdown() {
    const select = document.getElementById("create_position");
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

  loadPositionRankDropdown();
})();
