/* Superadmin feedback form builder.
 *
 * Client-side question list editor. The server re-validates everything on
 * save (prompt text, option labels, scale bounds, choice counts), so this
 * file is a convenience layer only - never a trust boundary.
 */
(function () {
  "use strict";

  var E = window.FB_ENDPOINTS || {};
  var CSRF = (window.FB_TOKENS || {}).csrf || "";
  var CURRENT = window.FB_CURRENT || { formId: "", questions: [] };

  var listEl = document.getElementById("fb-questions");
  var editorForm = document.getElementById("fb-editor-form");
  var msgEl = document.getElementById("fb-editor-msg");
  var saveBtn = document.getElementById("fb-save");

  var TYPE_LABELS = { mc: "Multiple choice", likert: "Likert scale", text: "Freeform text" };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function say(message, level) {
    if (!msgEl) return;
    msgEl.textContent = message || "";
    msgEl.className = "fb-editor-msg" + (level ? " is-" + level : "");
  }

  function readQuestions() {
    return Array.prototype.map.call(
      listEl.querySelectorAll(".fb-q"),
      function (node) {
        return {
          qtype: node.getAttribute("data-qtype"),
          prompt: node.querySelector(".fb-q-prompt").value.trim(),
          help_text: (node.querySelector(".fb-q-help") || {}).value || "",
          options: (node.querySelector(".fb-q-options") || {}).value || "",
          scale_min: (node.querySelector(".fb-q-min") || {}).value || 1,
          scale_max: (node.querySelector(".fb-q-max") || {}).value || 5,
          min_choices: (node.querySelector(".fb-q-minc") || {}).value || 1,
          max_choices: (node.querySelector(".fb-q-maxc") || {}).value || 1,
          is_required: !!node.querySelector(".fb-q-required").checked
        };
      }
    );
  }

  function buildQuestion(spec, index) {
    var qtype = spec.qtype || "mc";
    var node = el("div", "fb-q");
    node.setAttribute("data-qtype", qtype);

    var head = el("div", "fb-q-head");
    head.appendChild(el("span", "fb-q-index", "Q" + (index + 1)));
    head.appendChild(el("span", "fb-q-type", TYPE_LABELS[qtype] || qtype));

    var up = el("button", "fb-q-move", "\u2191");
    up.type = "button";
    up.title = "Move up";
    up.addEventListener("click", function () {
      var prev = node.previousElementSibling;
      if (prev) listEl.insertBefore(node, prev);
      renumber();
    });
    var down = el("button", "fb-q-move", "\u2193");
    down.type = "button";
    down.title = "Move down";
    down.addEventListener("click", function () {
      var next = node.nextElementSibling;
      if (next) listEl.insertBefore(next, node);
      renumber();
    });
    var remove = el("button", "fb-q-remove", "\u2715");
    remove.type = "button";
    remove.title = "Remove question";
    remove.addEventListener("click", function () { node.remove(); renumber(); });

    head.appendChild(up);
    head.appendChild(down);
    head.appendChild(remove);
    node.appendChild(head);

    var prompt = el("textarea", "fb-q-field fb-q-prompt");
    prompt.rows = 2;
    prompt.maxLength = 400;
    prompt.placeholder = "Question shown to the officer";
    prompt.value = spec.prompt || "";
    node.appendChild(prompt);

    var help = el("input", "fb-q-field fb-q-help");
    help.type = "text";
    help.maxLength = 300;
    help.placeholder = "Helper text (optional)";
    help.value = spec.help_text || "";
    node.appendChild(help);

    if (qtype === "mc" || qtype === "likert") {
      var options = el("textarea", "fb-q-field fb-q-options");
      options.rows = qtype === "likert" ? 5 : 3;
      options.placeholder = qtype === "likert"
        ? "One label per line, low to high.\nExample:\nStrongly Disagree\nDisagree\nNeutral\nAgree\nStrongly Agree"
        : "One option per line.";
      options.value = Array.isArray(spec.options) ? spec.options.join("\n") : (spec.options || "");
      node.appendChild(options);
    }

    if (qtype === "likert") {
      var scale = el("div", "fb-q-grid");
      scale.appendChild(numberField("Scale from", "fb-q-min", spec.scale_min || 1));
      scale.appendChild(numberField("Scale to", "fb-q-max", spec.scale_max || 5));
      node.appendChild(scale);
    }

    if (qtype === "mc") {
      var counts = el("div", "fb-q-grid");
      counts.appendChild(numberField("Min choices", "fb-q-minc", spec.min_choices || 1));
      counts.appendChild(numberField("Max choices", "fb-q-maxc", spec.max_choices || 1));
      node.appendChild(counts);
    }

    var requiredWrap = el("label", "fb-q-required-wrap");
    var required = el("input", "fb-q-required");
    required.type = "checkbox";
    required.checked = spec.is_required !== false;
    requiredWrap.appendChild(required);
    requiredWrap.appendChild(el("span", null, "Required"));
    node.appendChild(requiredWrap);

    return node;
  }

  function numberField(labelText, className, value) {
    var wrap = el("label", "fb-q-number");
    wrap.appendChild(el("span", null, labelText));
    var input = el("input", className);
    input.type = "number";
    input.min = "1";
    input.value = String(value || 1);
    wrap.appendChild(input);
    return wrap;
  }

  function renumber() {
    Array.prototype.forEach.call(listEl.querySelectorAll(".fb-q"), function (node, i) {
      var label = node.querySelector(".fb-q-index");
      if (label) label.textContent = "Q" + (i + 1);
    });
  }

  function renderQuestions(specs) {
    listEl.innerHTML = "";
    (specs || []).forEach(function (spec) {
      listEl.appendChild(buildQuestion(spec, listEl.children.length));
    });
    renumber();
  }

  function postJSON(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": CSRF,
        "X-Requested-With": "XMLHttpRequest"
      },
      credentials: "same-origin",
      body: JSON.stringify(payload)
    }).then(function (resp) {
      return resp.json().catch(function () {
        return { ok: false, error: "Unexpected server response (" + resp.status + ")." };
      });
    });
  }

  // ---- adders -------------------------------------------------------------
  Array.prototype.forEach.call(document.querySelectorAll("[data-fb-add]"), function (btn) {
    btn.addEventListener("click", function () {
      listEl.appendChild(buildQuestion({ qtype: btn.getAttribute("data-fb-add") }, listEl.children.length));
      renumber();
      var last = listEl.lastElementChild;
      var field = last && last.querySelector(".fb-q-prompt");
      if (field) field.focus();
    });
  });

  // ---- save ---------------------------------------------------------------
  if (editorForm) {
    editorForm.addEventListener("submit", function (event) {
      event.preventDefault();
      say("");

      var titleField = editorForm.querySelector("[name=title]");
      if (!titleField.value.trim()) {
        say("A form title is required.", "error");
        titleField.focus();
        return;
      }

      var payload = {
        form_id: CURRENT.formId || "",
        title: titleField.value.trim(),
        section_title: editorForm.querySelector("[name=section_title]").value.trim(),
        description: editorForm.querySelector("[name=description]").value.trim(),
        is_active: editorForm.querySelector("[name=is_active]").checked ? "1" : "0",
        is_open: editorForm.querySelector("[name=is_open]").checked ? "1" : "0",
        show_on_roles: Array.prototype.slice
          .call(editorForm.querySelectorAll("[name=show_on_roles]:checked"))
          .map(function (box) { return box.value; }),
        questions: readQuestions()
      };

      if (saveBtn) saveBtn.disabled = true;
      say("Saving\u2026");

      postJSON(E.save, payload)
        .then(function (data) {
          if (data && data.ok) {
            say("Saved. Reloading\u2026", "ok");
            setTimeout(function () { window.location.href = E.list; }, 550);
          } else {
            say((data && data.error) || "Could not save the form.", "error");
            if (saveBtn) saveBtn.disabled = false;
          }
        })
        .catch(function () {
          say("Network error while saving.", "error");
          if (saveBtn) saveBtn.disabled = false;
        });
    });
  }

  // ---- list actions -------------------------------------------------------
  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-fb-toggle]");
    if (toggle) {
      var field = toggle.getAttribute("data-fb-toggle");
      var isOn = toggle.getAttribute("data-fb-state") === "1";
      postJSON(E.toggle, {
        form_id: toggle.getAttribute("data-fb-form"),
        [field]: isOn ? "0" : "1"
      })
        .then(function (data) {
          if (data && data.ok) window.location.reload();
          else say((data && data.error) || "Update failed.", "error");
        })
        .catch(function () { say("Network error.", "error"); });
      return;
    }

    var del = event.target.closest("[data-fb-delete]");
    if (del) {
      var responses = parseInt(del.getAttribute("data-fb-responses"), 10) || 0;
      var name = del.getAttribute("data-fb-title");
      var question = responses > 0
        ? "Archive \"" + name + "\"? It has " + responses + " response(s), which will be kept but the card will be hidden."
        : "Permanently delete \"" + name + "\"? This cannot be undone.";
      if (!window.confirm(question)) return;
      postJSON(E.delete, { form_id: del.getAttribute("data-fb-form") })
        .then(function (data) {
          if (data && data.ok) window.location.reload();
          else say((data && data.error) || "Delete failed.", "error");
        })
        .catch(function () { say("Network error.", "error"); });
    }
  });

  // ---- new form -----------------------------------------------------------
  var newBtn = document.getElementById("fb-new");
  if (newBtn) {
    newBtn.addEventListener("click", function () {
      window.location.href = E.list;
      setTimeout(function () {
        var title = document.querySelector("[name=title]");
        if (title) title.focus();
      }, 120);
    });
  }

  renderQuestions(CURRENT.questions);
})();
