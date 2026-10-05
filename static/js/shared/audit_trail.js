/*
 * Shared Audit Trail UI.
 *
 * Drop a container marked with `data-audit-trail` on the page (see
 * templates/website/partials/_audit_trail_panel.html). This script renders the
 * simple summary table (Date & Time | User | Role | Action | Module | Status),
 * filters, pagination via UniPager, and an "Activity Details" modal on row click.
 *
 * The API (/api/audit/trail/) is role-scoped server-side, so the exact same
 * markup + script works for Treasurer, Auditor, President and Superadmin.
 */
(function () {
  "use strict";

  var PAGE_SIZE = 50;

  function esc(value) {
    if (value === null || value === undefined) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function fmtDateTime(iso) {
    if (!iso) return "-";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return esc(iso);
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  function statusClass(status) {
    var s = (status || "").toLowerCase();
    if (s === "failed") return "failed";
    if (s === "pending") return "pending";
    return "success";
  }

  function buildDiff(changes, oldValues, newValues) {
    if (Array.isArray(changes)) {
      if (!changes.length) return "";
      var resolvedRows = changes
        .map(function (c) {
          return (
            "<tr" + (c.changed ? ' class="at-changed"' : "") + ">" +
            "<td>" + esc(c.field) + "</td>" +
            "<td>" + esc(c.previous) + "</td>" +
            "<td>" + esc(c.new) + "</td>" +
            "</tr>"
          );
        })
        .join("");
      return (
        '<h4 class="at-detail-h">Changes</h4>' +
        '<table class="at-details"><thead><tr><th>Field</th><th>Previous</th><th>New</th></tr></thead>' +
        "<tbody>" + resolvedRows + "</tbody></table>"
      );
    }

    var keys = {};
    function collect(obj) {
      if (obj && typeof obj === "object") {
        Object.keys(obj).forEach(function (k) {
          keys[k] = true;
        });
      }
    }
    collect(oldValues);
    collect(newValues);
    var names = Object.keys(keys);
    if (!names.length) return "";

    var rows = names
      .map(function (k) {
        var before = oldValues && oldValues[k] !== undefined ? oldValues[k] : "";
        var after = newValues && newValues[k] !== undefined ? newValues[k] : "";
        var changed = JSON.stringify(before) !== JSON.stringify(after);
        return (
          '<tr' + (changed ? ' class="at-changed"' : "") + ">" +
          "<td>" + esc(k) + "</td>" +
          "<td>" + esc(typeof before === "object" ? JSON.stringify(before) : before) + "</td>" +
          "<td>" + esc(typeof after === "object" ? JSON.stringify(after) : after) + "</td>" +
          "</tr>"
        );
      })
      .join("");

    return (
      '<h4 class="at-detail-h">Changes</h4>' +
      '<table class="at-details"><thead><tr><th>Field</th><th>Previous</th><th>New</th></tr></thead>' +
      "<tbody>" + rows + "</tbody></table>"
    );
  }

  function showDetails(entry) {
    var html =
      '<table class="at-details"><tbody>' +
      "<tr><th>User</th><td>" + esc(entry.actor_name) + "</td></tr>" +
      "<tr><th>Role</th><td>" + esc(entry.actor_role || "-") + "</td></tr>" +
      "<tr><th>Date &amp; Time</th><td>" + esc(fmtDateTime(entry.timestamp)) + "</td></tr>" +
      "<tr><th>Action</th><td>" + esc(entry.action_label) + "</td></tr>" +
      "<tr><th>Module</th><td>" + esc(entry.module) + "</td></tr>" +
      "<tr><th>Record Affected</th><td>" + esc(entry.record_label) + "</td></tr>" +
      "<tr><th>Result</th><td><span class=\"at-badge " + statusClass(entry.status) + "\">" + esc(entry.status) + "</span></td></tr>" +
      "<tr><th>IP Address</th><td>" + esc(entry.ip_address || "-") + "</td></tr>" +
      "<tr><th>Device</th><td>" + esc(entry.device_info || "-") + "</td></tr>" +
      "<tr><th>Notes</th><td>" + esc(entry.notes || "-") + "</td></tr>" +
      "</tbody></table>" +
      buildDiff(entry.changes, entry.old_values, entry.new_values);

    if (window.SimpleModal && typeof window.SimpleModal.open === "function") {
      window.SimpleModal.open({ title: "Activity Details", html: html, width: "680px" });
    }
  }

  function AuditTrail(root) {
    this.root = root;
    this.endpoint = root.getAttribute("data-endpoint") || "/api/audit/trail/";
    this.offset = 0;
    this.total = 0;
    this.page = 1;
    this.self = this;

    this.body = root.querySelector(".at-body");
    this.pager = root.querySelector(".at-pager");
    this.search = root.querySelector(".at-search");
    this.module = root.querySelector(".at-module");
    this.action = root.querySelector(".at-action");
    this.role = root.querySelector(".at-role");
    this.status = root.querySelector(".at-status");
    this.dateFrom = root.querySelector(".at-date-from");
    this.dateTo = root.querySelector(".at-date-to");
    this.applyBtn = root.querySelector(".at-apply");

    var self = this;
    if (this.applyBtn) this.applyBtn.addEventListener("click", function () { self.reload(); });
    if (this.search) {
      this.search.addEventListener("keydown", function (e) {
        if (e.key === "Enter") self.reload();
      });
    }
    [this.module, this.action, this.role, this.status, this.dateFrom, this.dateTo].forEach(function (el) {
      if (el) el.addEventListener("change", function () { self.reload(); });
    });
    if (this.body) {
      this.body.addEventListener("click", function (e) {
        var row = e.target.closest ? e.target.closest("tr[data-trail-id]") : null;
        if (row) self.openDetail(row.getAttribute("data-trail-id"));
      });
    }
  }

  AuditTrail.prototype.qs = function () {
    var params = new URLSearchParams();
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String(this.offset));
    if (this.search && this.search.value.trim()) params.set("q", this.search.value.trim());
    if (this.module && this.module.value) params.set("module", this.module.value);
    if (this.action && this.action.value) params.set("action", this.action.value);
    if (this.role && this.role.value) params.set("role", this.role.value);
    if (this.status && this.status.value) params.set("status", this.status.value);
    if (this.dateFrom && this.dateFrom.value) params.set("date_from", this.dateFrom.value);
    if (this.dateTo && this.dateTo.value) params.set("date_to", this.dateTo.value);
    return params.toString();
  };

  AuditTrail.prototype.reload = function () {
    this.offset = 0;
    this.load();
  };

  AuditTrail.prototype.load = function () {
    var self = this;
    if (this.body) {
      this.body.innerHTML = '<tr><td colspan="6" class="at-empty">Loading...</td></tr>';
    }
    fetch(this.endpoint + "?" + this.qs(), {
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin",
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.ok) {
          self.renderError((data && data.error) || "Unable to load audit trail.");
          return;
        }
        self.total = data.total || 0;
        self.page = Math.floor(self.offset / PAGE_SIZE) + 1;
        self.fillOptions(self.module, data.modules || [], "All Modules");
        self.fillActionOptions(data.actions || []);
        self.renderRows(data.entries || []);
        self.renderPager();
      })
      .catch(function () {
        self.renderError("Network error while loading audit trail.");
      });
  };

  AuditTrail.prototype.fillOptions = function (select, values, placeholder) {
    if (!select) return;
    var current = select.value;
    select.innerHTML = '<option value="">' + esc(placeholder) + "</option>";
    values.forEach(function (v) {
      var opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      select.appendChild(opt);
    });
    select.value = current;
  };

  AuditTrail.prototype.fillActionOptions = function (actions) {
    if (!this.action) return;
    var current = this.action.value;
    var placeholder = this.action.querySelector('option[value=""]');
    this.action.innerHTML = "";
    this.action.appendChild(placeholder || new Option("All Actions", ""));
    actions.forEach(function (item) {
      var opt = document.createElement("option");
      opt.value = item.value;
      opt.textContent = item.label;
      this.action.appendChild(opt);
    }, this);
    this.action.value = current;
  };

  AuditTrail.prototype.renderRows = function (entries) {
    if (!this.body) return;
    if (!entries.length) {
      this.body.innerHTML = '<tr><td colspan="6" class="at-empty">No audit records found.</td></tr>';
      return;
    }
    this.body.innerHTML = entries
      .map(function (entry) {
        return (
          '<tr data-trail-id="' + esc(entry.trail_id) + '" class="at-row">' +
          "<td>" + esc(fmtDateTime(entry.timestamp)) + "</td>" +
          "<td>" + esc(entry.actor_name) + "</td>" +
          "<td>" + esc(entry.actor_role || "-") + "</td>" +
          "<td>" + esc(entry.action_label) + "</td>" +
          "<td>" + esc(entry.module) + "</td>" +
          '<td><span class="at-badge ' + statusClass(entry.status) + '">' + esc(entry.status) + "</span></td>" +
          "</tr>"
        );
      })
      .join("");
  };

  AuditTrail.prototype.renderError = function (message) {
    if (this.body) {
      this.body.innerHTML = '<tr><td colspan="6" class="at-empty">' + esc(message) + "</td></tr>";
    }
    if (this.pager) this.pager.innerHTML = "";
  };

  AuditTrail.prototype.renderPager = function () {
    if (!this.pager) return;
    var totalPages = Math.max(1, Math.ceil(this.total / PAGE_SIZE));
    var counter =
      window.UniPager && window.UniPager.count
        ? window.UniPager.count(this.page, PAGE_SIZE, this.total)
        : "";
    if (window.UniPager && window.UniPager.html) {
      window.__auditTrailPager = this;
      this.pager.innerHTML = window.UniPager.html(
        this.page,
        totalPages,
        "window.__auditTrailPager.go(PAGE)",
        counter
      );
    } else {
      this.pager.textContent = counter;
    }
  };

  AuditTrail.prototype.go = function (page) {
    page = Math.max(1, parseInt(page, 10) || 1);
    this.offset = (page - 1) * PAGE_SIZE;
    this.load();
  };

  AuditTrail.prototype.openDetail = function (trailId) {
    fetch(this.endpoint + encodeURIComponent(trailId) + "/", {
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin",
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.ok) {
          if (window.SimpleModal) window.SimpleModal.alert((data && data.error) || "Unable to load details.");
          return;
        }
        showDetails(data.entry);
      })
      .catch(function () {
        if (window.SimpleModal) window.SimpleModal.alert("Network error while loading details.");
      });
  };

  function init() {
    var nodes = document.querySelectorAll("[data-audit-trail]");
    Array.prototype.forEach.call(nodes, function (node) {
      if (node.__auditTrailInited) return;
      node.__auditTrailInited = true;
      var instance = new AuditTrail(node);
      instance.load();
    });
  }

  window.AuditTrail = { init: init };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
