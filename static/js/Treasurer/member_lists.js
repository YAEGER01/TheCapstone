// member_lists.js — Member Directory: view + edit member PROFILE information
// (not finance — ledger history lives in its own module).
(function () {
  "use strict";

  const state = { members: [], detail: null, page: 1, pageSize: 10, total: 0, totalPages: 1, searchTimer: null, order: "asc" };

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
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

  async function getJSON(url) {
    try {
      const res = await fetch(url, { credentials: "same-origin" });
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  // Keep a stored value selectable even when it is not in the dropdown
  // (e.g. legacy free-text entries) so editing never loses data.
  function ensureSelectValue(sel, value) {
    if (!sel) return;
    if (value && ![...sel.options].some((o) => o.value === value)) {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = value;
      sel.appendChild(opt);
    }
    sel.value = value || "";
  }

  // Position ranks come from the same source as the create-member forms.
  let editRankCache = null;
  async function loadEditPositionRanks(current) {
    const sel = document.getElementById("nml-edit-position");
    if (!sel) return;
    try {
      if (!editRankCache) {
        const res = await fetch("/api/treasurer/members/position-ranks/options/", { credentials: "same-origin" });
        const data = await res.json().catch(() => ({}));
        editRankCache = (data && data.ok && data.ranks) ? data.ranks.map((r) => r.name).filter(Boolean) : [];
      }
      sel.innerHTML = '<option value="">-- Select Position / Rank --</option>' +
        editRankCache.map((n) => '<option value="' + esc(n) + '">' + esc(n) + "</option>").join("");
    } catch (e) {
      console.error("Failed to load position ranks", e);
    }
    ensureSelectValue(sel, current || "");
  }

  function photoOrPlaceholder(url) {
    return url
      ? `<img src="${esc(url)}" style="width:40px;height:40px;border-radius:50%;object-fit:cover;border:1px solid #dfe9df;" />`
      : '<span style="width:40px;height:40px;border-radius:50%;background:#e8f5e9;color:#1b5e20;display:inline-flex;align-items:center;justify-content:center;font-size:0.7rem;font-weight:700;">—</span>';
  }

  // Directory display is "LASTNAME, Firstname M.I." (server-provided
  // display_name, raw full_name as fallback). Initials are First + Last
  // so "JUAN A DELA CRUZ" monograms as "JC", skipping suffixes.
  function displayName(m) {
    return (m && (m.display_name || m.full_name)) || "—";
  }

  function nameInitials(fullName) {
    let parts = String(fullName || "").trim().split(/\s+/).filter(Boolean);
    while (parts.length > 1 && /^(jr\.?|sr\.?|ii|iii|iv|v)$/i.test(parts[parts.length - 1])) parts.pop();
    if (!parts.length) return "?";
    if (parts.length === 1) return parts[0][0].toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  window.nxMemberLists = {
    // Server-side filtering + pagination: the API does the search so the
    // dashboard never has to download the whole roster.
    async load(resetPage, silent) {
      const tbody = document.getElementById("nmlBody");
      if (!tbody) return;
      if (resetPage) state.page = 1;
      if (!silent) tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#757575;">Loading...</td></tr>';
      const search = ((document.getElementById("nml-search") || {}).value || "").trim();
      const classification = ((document.getElementById("nml-classification") || {}).value || "").trim();
      const params = new URLSearchParams();
      if (search) params.set("q", search);
      if (classification) params.set("classification", classification);
      params.set("page", String(state.page));
      params.set("per_page", String(state.pageSize));
      params.set("order", state.order === "desc" ? "desc" : "asc");
      const data = await getJSON("/api/treasurer/member-profiles/list/?" + params.toString());
      state.members = (data && data.members) || [];
      state.total = (data && data.total) || 0;
      state.totalPages = (data && data.total_pages) || 1;
      this.renderList();
    },

    searchDebounced() {
      const self = window.nxMemberLists;
      if (state.searchTimer) clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(() => self.load(true), 250);
    },

    // Caret up/down on the Member Name header: toggles surname A–Z / Z–A.
    // Sorting is server-side (the list is paginated) so every page stays ordered.
    toggleNameSort() {
      state.order = state.order === "asc" ? "desc" : "asc";
      state.page = 1;
      this.load(false, true);
    },

    updateNameSortIcon() {
      const icon = document.getElementById("nml-sort-name-icon");
      if (icon) {
        icon.className = "fa-solid " + (state.order === "asc" ? "fa-caret-up" : "fa-caret-down");
      }
      const th = icon && icon.closest ? icon.closest("th") : null;
      if (th) th.setAttribute("aria-sort", state.order === "asc" ? "ascending" : "descending");
    },

    renderList() {
      const tbody = document.getElementById("nmlBody");
      if (!tbody) return;
      this.updateNameSortIcon();
      const rows = state.members;
      const pagination = document.getElementById("nml-pagination");
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#757575;">No members found.</td></tr>';
        if (pagination) pagination.innerHTML = "";
        return;
      }
      const pageCount = Math.max(1, state.totalPages);
      const pageRows = rows;
      tbody.innerHTML = pageRows
        .map(
          (m, i) => `<tr>
              <td>${photoOrPlaceholder(m.photo_url)}</td>
              <td><b>${esc(displayName(m))}</b></td>
              <td><span style="display:inline-block;padding:2px 8px;border-radius:8px;font-size:0.68rem;font-weight:700;background:${m.classification === "Retired" ? "#f1f3f1" : "#e8f5e9"};color:${m.classification === "Retired" ? "#6b7280" : "#1b5e20"};">${esc(m.classification || "Teaching")}</span> <span style="font-size:0.72rem;color:#8a949e;">${esc(m.membership_status || "")}</span></td>
              <td>${esc(m.department || "—")}</td>
              <td>${esc(m.position || "—")}</td>
              <td>${esc(m.contact_number || "—")}</td>
              <td style="white-space:nowrap;">
                <button type="button" class="btn sm" style="background:#1d63d8;color:#fff;border:none;padding:4px 10px;font-size:11px;font-weight:600;cursor:pointer;border-radius:6px;" onclick="window.nxMemberLists.view('${esc(m.member_id)}')">Profile</button>
                <button type="button" class="btn sm" style="background:#f0b323;color:#1f1f1f;border:none;padding:4px 10px;font-size:11px;font-weight:600;cursor:pointer;border-radius:6px;" onclick="window.nxMemberLists.edit('${esc(m.member_id)}')">Edit</button>
              </td>
            </tr>`
        )
        .join("");
      if (pagination && typeof UniPager !== "undefined") {
        pagination.innerHTML = UniPager.html(state.page, pageCount, "window.nxMemberLists.goPage(PAGE)", UniPager.count(state.page, state.pageSize, state.total));
      }
    },

    goPage(p) {
      state.page = p;
      this.load();
    },

    view(memberId) {
      try {
      const m = state.members.find((x) => String(x.member_id) === String(memberId));
      if (!m) { toast("Member not found — refreshing the list."); this.load(); return; }
      const shownName = displayName(m);
      const fields = [
        ["Full Name", shownName],
        ["Membership Type", m.membership_status || "—"],
        ["Department", m.department || "—"],
        ["Position / Rank", m.position || "—"],
        ["Contact Number", m.contact_number || "—"],
        ["Email", m.email || "—"],
        ["Date Joined", m.date_joined || "—"],
      ];
      // Personal information is self-service: members edit it from their own
      // dashboard; the directory shows it READ-ONLY (no edit fields below).
      const fmtDOB = (iso) => {
        if (!iso) return "—";
        const d = new Date(iso + "T00:00:00");
        return isNaN(d) ? iso : d.toLocaleDateString("en-PH", { month: "short", day: "numeric", year: "numeric" });
      };
      const personal = [
        ["Address", m.address || "—"],
        ["Civil Status", m.civil_status || "—"],
        ["Sex", m.sex || "—"],
        ["Date of Birth", fmtDOB(m.date_of_birth)],
        ["Age", (m.age === null || m.age === undefined) ? "—" : String(m.age)],
      ];
      const photo = m.photo_url
        ? `<img src="${esc(m.photo_url)}" style="width:96px;height:96px;border-radius:50%;object-fit:cover;border:2px solid #dfe9df;" />`
        : '<span style="width:96px;height:96px;border-radius:50%;background:#e8f5e9;color:#1b5e20;display:inline-flex;align-items:center;justify-content:center;font-weight:800;font-size:1.4rem;">' + esc(nameInitials(m.full_name)) + '</span>';
      const grid = fields
        .map(
          ([k, v]) =>
            `<div><div style="font-size:0.62rem;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;color:#8a949e;">${esc(k)}</div><div style="font-size:0.85rem;font-weight:600;color:#101828;">${esc(v)}</div></div>`
        )
        .join("");
      const personalGrid = personal
        .map(
          ([k, v]) =>
            `<div><div style="font-size:0.62rem;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;color:#8a949e;">${esc(k)}</div><div style="font-size:0.85rem;font-weight:600;color:#101828;white-space:pre-wrap;word-break:break-word;">${esc(v)}</div></div>`
        )
        .join("");
      const overlay = document.createElement("div");
      overlay.id = "nmlViewModal";
      overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,0.45);z-index:9998;display:flex;align-items:flex-start;justify-content:center;padding:24px 16px;overflow-y:auto;";
      overlay.innerHTML = `
        <div style="background:#fff;border-radius:14px;width:min(560px,94vw);max-height:90vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,0.3);">
          <div style="padding:18px 22px;border-bottom:1px solid #eef1ee;display:flex;align-items:center;gap:14px;">
            ${photo}
            <div style="flex:1;">
              <div style="font-weight:800;color:#101828;font-size:1.05rem;">${esc(shownName)}</div>
              <div style="font-size:0.78rem;color:#757575;">${esc(m.position || "—")} · ${esc(m.department || "—")}</div>
            </div>
            <span class="badge approved">${esc(m.membership_status || "Member")}</span>
          </div>
          <div style="padding:18px 22px;display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px 18px;">
            ${grid}
          </div>
          <div style="padding:0 22px 20px;">
            <div style="font-size:0.66rem;font-weight:800;letter-spacing:0.6px;text-transform:uppercase;color:#1b5e20;border-bottom:1px solid #eef1ee;padding-bottom:6px;margin-bottom:12px;">Personal Information <span style="font-weight:600;text-transform:none;letter-spacing:0;color:#8a949e;">· maintained by the member</span></div>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px 18px;">
              ${personalGrid}
            </div>
          </div>
          <div style="padding:0 22px 18px;text-align:right;">
            <button type="button" class="btn-brand btn-brand-secondary" onclick="document.getElementById('nmlViewModal').remove()">Close</button>
          </div>
        </div>`;
      document.body.appendChild(overlay);
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) overlay.remove();
      });
      } catch (err) {
        console.error(err);
        toast("Could not open the member profile: " + err.message, true);
      }
    },

    edit(memberId) {
      try {
      const m = state.members.find((x) => String(x.member_id) === String(memberId));
      if (!m) { toast("Member not found — refreshing the list."); this.load(); return; }
      state.detail = m;
      const panel = document.getElementById("nmlEditPanel");
      if (!panel) return;
      const wrap = document.getElementById("nml-edit-photo-wrap");
      if (wrap) {
        wrap.innerHTML = m.photo_url
          ? '<img src="' + esc(m.photo_url) + '" style="width:100%;height:100%;object-fit:cover;" />'
          : esc(nameInitials(m.full_name));
      }
      document.getElementById("nml-edit-photo-input").value = "";
      document.getElementById("nml-edit-full-name").value = m.full_name || "";
      ensureSelectValue(document.getElementById("nml-edit-department"), m.department || "");
      loadEditPositionRanks(m.position || "");
      const statusSel = document.getElementById("nml-edit-membership-status");
      if (statusSel) statusSel.value = m.membership_status || "Permanent";
      document.getElementById("nml-edit-contact").value = m.contact_number || "";
      document.getElementById("nml-edit-email").value = m.email || "";
      panel.style.display = "block";
      panel.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (err) {
        console.error(err);
        toast("Could not open the editor: " + err.message, true);
        this.closeEdit();
      }
    },

    closeEdit() {
      const panel = document.getElementById("nmlEditPanel");
      if (panel) panel.style.display = "none";
      state.detail = null;
    },

    async save() {
      const m = state.detail;
      if (!m) return;
      const fd = new FormData();
      fd.append("member_id", String(m.member_id));
      fd.append("full_name", (document.getElementById("nml-edit-full-name") || {}).value || "");

      fd.append("department", (document.getElementById("nml-edit-department") || {}).value || "");
      fd.append("position", (document.getElementById("nml-edit-position") || {}).value || "");
      fd.append("membership_status", (document.getElementById("nml-edit-membership-status") || {}).value || "");
      fd.append("contact_number", (document.getElementById("nml-edit-contact") || {}).value || "");
      fd.append("email", (document.getElementById("nml-edit-email") || {}).value || "");
      const photoInput = document.getElementById("nml-edit-photo-input");
      if (photoInput && photoInput.files && photoInput.files[0]) fd.append("photo", photoInput.files[0]);

      const btn = document.getElementById("nml-save-btn");
      if (btn) { btn.disabled = true; btn.textContent = "Saving..."; }
      try {
        const res = await fetch("/api/treasurer/member-profiles/update/", {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": getCookie("csrftoken") },
          body: fd,
        });
        const data = await res.json().catch(() => ({}));
        if (data && data.ok) {
          toast(data.message || "Member profile updated.", false);
          this.closeEdit();
          this.load();
        } else {
          toast((data && data.error) || "Failed to update the member profile.", true);
        }
      } catch (e) {
        toast("Network error while saving.", true);
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = "Save Changes"; }
      }
    },
  };

  // Refresh on load + whenever the module is opened from the sidebar.
  document.addEventListener("turbo:load", () => window.nxMemberLists.load());
  if (document.readyState !== "loading") window.nxMemberLists.load();
  else document.addEventListener("DOMContentLoaded", () => window.nxMemberLists.load());
  if (!window.__nxMemberListsClickBound) {
    window.__nxMemberListsClickBound = true;
    document.addEventListener("click", function (e) {
      const el = e.target.closest && e.target.closest('[data-target="view-member-lists"]');
      if (el) setTimeout(() => window.nxMemberLists.load(), 200);
    });
  }

  // Live photo preview when a new image is chosen in the edit panel
  const photoInput = document.getElementById("nml-edit-photo-input");
  if (photoInput) {
    photoInput.addEventListener("change", function () {
      const wrap = document.getElementById("nml-edit-photo-wrap");
      if (!wrap) return;
      if (this.files && this.files[0]) {
        wrap.innerHTML = '<img src="' + URL.createObjectURL(this.files[0]) + '" style="width:100%;height:100%;object-fit:cover;" />';
      } else {
        wrap.innerHTML = "?";
      }
    });
  }
})();
