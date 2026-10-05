(function () {
  "use strict";

  const POSITION_PAGE_SIZE = 10;
  let positionRanks = [];
  let positionPage = 1;
  let positionCategoryCache = [];
  let categoryMatchOverride = false;
  let positionRankSuggestion = null;
  let ghostDismissedFor = null;
  let ghostEl = null;

  function getCSRFToken() {
    const el = document.querySelector("input[name='csrfmiddlewaretoken']");
    if (el && el.value) return el.value;
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }

  function showToast(message, isError = false) {
    const container = document.getElementById("toastContainer");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = "notification-toast";
    toast.style.cssText = `
      background: ${isError ? "#e53935" : "#1b5e20"};
      color: white;
      padding: 16px 20px;
      border-radius: 8px;
      margin-bottom: 12px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      animation: slideIn 0.3s ease-out;
      display: flex;
      align-items: center;
      gap: 12px;
    `;
    toast.innerHTML = `
      <i class="fa-solid ${isError ? "fa-circle-exclamation" : "fa-circle-check"}"></i>
      <span>${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = "slideOut 0.3s ease-out forwards";
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  async function loadPositionRanks() {
    try {
      // Add cache-busting timestamp to ensure fresh data
      const timestamp = new Date().getTime();
      const response = await fetch(`/api/treasurer/members/position-ranks/list/?t=${timestamp}`);
      const data = await response.json();

      if (data.ok) {
        positionRanks = Array.isArray(data.ranks) ? data.ranks : [];
        positionPage = 1;
        renderPositionRanksTable();
        loadCategoryOptions();
      } else {
        console.error("Failed to load position ranks:", data.error);
        showToast("Failed to load position ranks", true);
      }
    } catch (error) {
      console.error("Error loading position ranks:", error);
      showToast("Error loading position ranks", true);
    }
  }

  function renderPositionRanksTable() {
    const tbody = document.querySelector("#positionRanksTable tbody");
    if (!tbody) return;

    const ranks = positionRanks;
    const pagination = document.getElementById("positionRanksPagination");

    if (!ranks.length) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align:center; color:#757575; padding: 20px;">
            No position ranks found. Click "Add Faculty Rank" to create one.
          </td>
        </tr>
      `;
      if (pagination) pagination.innerHTML = "";
      return;
    }

    const pageCount = Math.ceil(ranks.length / POSITION_PAGE_SIZE);
    positionPage = Math.min(Math.max(positionPage, 1), pageCount);
    const start = (positionPage - 1) * POSITION_PAGE_SIZE;
    const pageRanks = ranks.slice(start, start + POSITION_PAGE_SIZE);

    tbody.innerHTML = pageRanks.map((rank) => {
      const statusText = rank.is_active ? "Active" : "Inactive";
      const actionClass = rank.is_active
        ? "position-rank-action position-rank-delete"
        : "position-rank-action position-rank-activate";
      const actionLabel = rank.is_active ? "Deactivate" : "Activate";
      const statusStyle = rank.is_active
        ? "color:#1b5e20;font-weight:600;"
        : "color:#c62828;font-weight:600;";
      return `
      <tr>
        <td><strong>${escapeHtml(rank.name)}</strong></td>
        <td>${escapeHtml(rank.category)}</td>
        <td style="${statusStyle}">${statusText}</td>
        <td>${escapeHtml(rank.created_by)}</td>
        <td>${escapeHtml(rank.created_at ? new Date(rank.created_at).toLocaleDateString() : "N/A")}</td>
        <td>
          <button class="position-rank-action position-rank-edit" onclick="editPositionRank(${rank.id})">Edit</button>
          <button class="${actionClass}" onclick="togglePositionRank(this, ${rank.id})">${actionLabel}</button>
        </td>
      </tr>
    `;
    }).join("");

    if (pagination) {
      pagination.innerHTML = UniPager.html(positionPage, pageCount, "window.__positionRankGoPage(PAGE)", UniPager.count(positionPage, POSITION_PAGE_SIZE, ranks.length));
    }
  }

  window.__positionRankGoPage = function (p) {
    positionPage = p;
    renderPositionRanksTable();
  };

  function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function escapeAttr(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  async function loadCategoryOptions(selectedValue) {
    const select = document.getElementById("position_category");
    positionCategoryCache = [];
    if (!select) return;
    try {
      const response = await fetch(
        `/api/treasurer/members/position-categories/list/?t=${new Date().getTime()}`,
        { credentials: "same-origin" }
      );
      const data = await response.json();
      const categories =
        data && data.ok && Array.isArray(data.categories) ? data.categories : [];

      const options = ['<option value="">Select Category</option>'];
      categories
        .filter((cat) => cat.is_active)
        .forEach((cat) => {
          positionCategoryCache.push(cat.name);
          options.push(
            `<option value="${escapeAttr(cat.name)}">${escapeHtml(cat.name)}</option>`
          );
        });

      // Keep an existing rank's category selectable even if it was deactivated.
      if (selectedValue && !categories.some((cat) => cat.name === selectedValue)) {
        options.push(
          `<option value="${escapeAttr(selectedValue)}">${escapeHtml(selectedValue)}</option>`
        );
        positionCategoryCache.push(selectedValue);
      }

      select.innerHTML = options.join("");
      if (selectedValue) select.value = selectedValue;
    } catch (error) {
      console.error("Error loading position categories:", error);
    }
  }

  function findBestCategoryMatch(input) {
    if (!input || !positionCategoryCache.length) return null;
    const a = input.toLowerCase();
    if (a.length < 2) return null;
    let best = null;
    let bestScore = 0;
    for (let i = 0; i < positionCategoryCache.length; i++) {
      const name = positionCategoryCache[i];
      const b = name.toLowerCase();
      let score = 0;
      if (a === b) score = 100;
      else if (b.startsWith(a)) score = 80;
      else if (a.startsWith(b)) score = 70;
      else if (b.includes(a)) score = 50;
      else if (a.includes(b)) score = 40;
      if (score > bestScore) {
        bestScore = score;
        best = name;
      } else if (score === bestScore && score > 0 && best && name.length > best.length) {
        best = name;
      }
    }
    return bestScore >= 50 ? best : null;
  }

  function onPositionNameInput() {
    const nameInput = document.getElementById("position_name");
    if (!nameInput) return;
    const select = document.getElementById("position_category");
    // Remove legacy outside-the-box suggestion element if it still exists.
    const legacyBox = document.getElementById("position_name_suggestion");
    if (legacyBox) legacyBox.remove();
    const current = (nameInput.value || "").trim();

    if (current) {
      if (select && !categoryMatchOverride) {
        const match = findBestCategoryMatch(current);
        select.value = match || "";
      }
    } else {
      categoryMatchOverride = false;
      if (select) select.value = "";
    }

    positionRankSuggestion = null;
    if (current && current !== ghostDismissedFor) {
      const suggestion = suggestNextRank(current);
      if (suggestion && suggestion.full && suggestion.full.toLowerCase() !== current.toLowerCase()) {
        // Only keep the suggestion when it actually extends what was typed
        // (prefix match). Otherwise the ghost text would be unrelated.
        if (suggestion.full.toLowerCase().startsWith(current.toLowerCase())) {
          positionRankSuggestion = suggestion.full;
        }
      }
    }
    updateInlineGhost();
  }

  function romanToInt(s) {
    const map = { I: 1, V: 5, X: 10, L: 50, C: 100, D: 500, M: 1000 };
    s = (s || "").toUpperCase();
    if (!s || !/^[IVXLCDM]+$/.test(s)) return NaN;
    let total = 0;
    let prev = 0;
    for (let i = s.length - 1; i >= 0; i--) {
      const cur = map[s[i]];
      if (!cur) return NaN;
      if (cur < prev) total -= cur;
      else {
        total += cur;
        prev = cur;
      }
    }
    if (intToRoman(total) !== s) return NaN;
    return total;
  }

  function intToRoman(num) {
    const map = [
      ["M", 1000],
      ["CM", 900],
      ["D", 500],
      ["CD", 400],
      ["C", 100],
      ["XC", 90],
      ["L", 50],
      ["XL", 40],
      ["X", 10],
      ["IX", 9],
      ["V", 5],
      ["IV", 4],
      ["I", 1],
    ];
    let res = "";
    for (let i = 0; i < map.length; i++) {
      while (num >= map[i][1]) {
        res += map[i][0];
        num -= map[i][1];
      }
    }
    return res;
  }

  function getRankStem(name) {
    const parts = (name || "").trim().split(/\s+/);
    if (parts.length >= 2 && romanToInt(parts[parts.length - 1]) > 0) {
      return parts.slice(0, -1).join(" ");
    }
    return (name || "").trim();
  }

  function isRomanToken(token) {
    return !!token && romanToInt(token) > 0;
  }

  function suggestNextRank(typed) {
    const trimmed = (typed || "").trim();
    if (!trimmed) return null;
    const parts = trimmed.split(/\s+/);
    // User already typed an explicit tier (e.g. "Professor I") — don't guess.
    if (parts.length >= 2 && isRomanToken(parts[parts.length - 1])) {
      return null;
    }
    const typedLower = trimmed.toLowerCase();

    // Group existing ranks by stem (case-insensitive), keeping canonical casing.
    const groups = Object.create(null);
    for (let i = 0; i < positionRanks.length; i++) {
      const r = positionRanks[i];
      if (!r || !r.name) continue;
      const rStem = getRankStem(r.name);
      const key = rStem.toLowerCase();
      if (!groups[key]) groups[key] = { canonical: rStem, tiers: [] };
      const tokens = r.name.trim().split(/\s+/);
      const tier = romanToInt(tokens[tokens.length - 1]);
      if (rStem !== r.name.trim() && tier > 0) groups[key].tiers.push(tier);
    }
    const keys = Object.keys(groups);
    if (!keys.length) return null;

    function fullFor(group) {
      if (group.tiers.length) {
        const next = Math.max.apply(null, group.tiers) + 1;
        const tierRoman = intToRoman(next);
        return { stem: group.canonical, tier: tierRoman, full: group.canonical + " " + tierRoman };
      }
      return { stem: group.canonical, tier: "", full: group.canonical };
    }

    // 1) Exact stem match (case-insensitive): "Professor" -> "Professor III".
    if (groups[typedLower]) {
      const g = groups[typedLower];
      if (!g.tiers.length) return null; // already a complete non-tiered rank
      return fullFor(g);
    }

    // 2) Prefix match: "Profe"/"prof" -> closest "Professor III".
    //    The ghost suffix is full.slice(typed.length), e.g. "essor III".
    let best = null;
    for (let i = 0; i < keys.length; i++) {
      const key = keys[i];
      if (key.indexOf(typedLower) !== 0) continue;
      const candidate = fullFor(groups[key]);
      if (candidate.full.toLowerCase() === typedLower) continue;
      if (!best || candidate.full.length < best.full.length ||
        (candidate.full.length === best.full.length && candidate.full < best.full)) {
        best = candidate;
      }
    }
    return best;
  }

  // ---- Inline ghost-text (IDE-style) suggestion inside #position_name ----

  function syncGhostStyle() {
    const nameInput = document.getElementById("position_name");
    if (!nameInput || !ghostEl) return;
    const cs = window.getComputedStyle(nameInput);
    ghostEl.style.fontFamily = cs.fontFamily;
    ghostEl.style.fontSize = cs.fontSize;
    ghostEl.style.fontWeight = cs.fontWeight;
    ghostEl.style.fontStyle = cs.fontStyle;
    ghostEl.style.letterSpacing = cs.letterSpacing;
    ghostEl.style.textTransform = cs.textTransform;
    ghostEl.style.padding = cs.paddingTop + " " + cs.paddingRight + " " + cs.paddingBottom + " " + cs.paddingLeft;
    ghostEl.style.borderTopWidth = cs.borderTopWidth;
    ghostEl.style.borderRightWidth = cs.borderRightWidth;
    ghostEl.style.borderBottomWidth = cs.borderBottomWidth;
    ghostEl.style.borderLeftWidth = cs.borderLeftWidth;
    ghostEl.style.borderStyle = "solid";
    ghostEl.style.borderColor = "transparent";
    ghostEl.style.lineHeight = cs.lineHeight;
  }

  function setupInlineGhost() {
    const nameInput = document.getElementById("position_name");
    if (!nameInput || document.getElementById("position_name_ghost")) {
      ghostEl = document.getElementById("position_name_ghost");
      if (nameInput && ghostEl) {
        syncGhostStyle();
        ghostEl.scrollLeft = nameInput.scrollLeft;
      }
      return;
    }
    // Wrap the input so the ghost can sit exactly behind its text.
    const wrap = document.createElement("div");
    wrap.className = "pos-inline-wrap";
    wrap.style.cssText = "position:relative;width:100%;";
    nameInput.parentNode.insertBefore(wrap, nameInput);
    wrap.appendChild(nameInput);

    ghostEl = document.createElement("div");
    ghostEl.id = "position_name_ghost";
    ghostEl.setAttribute("aria-hidden", "true");
    ghostEl.style.cssText =
      "position:absolute;top:0;left:0;right:0;bottom:0;" +
      "overflow:hidden;white-space:pre;pointer-events:none;" +
      "box-sizing:border-box;background:transparent;color:#9ca3af;" +
      "z-index:1;";
    wrap.insertBefore(ghostEl, nameInput);

    // Input must stay on top with a see-through background so the gray
    // continuation shows in the empty area after the caret.
    nameInput.style.position = "relative";
    nameInput.style.zIndex = "2";
    nameInput.style.background = "transparent";
    // Keep the caret visible above the ghost layer.
    try { nameInput.style.caretColor = "#333"; } catch (e) {}

    syncGhostStyle();
    nameInput.addEventListener("scroll", function () {
      if (ghostEl) ghostEl.scrollLeft = nameInput.scrollLeft;
    });
    window.addEventListener("resize", syncGhostStyle);
  }

  function caretAtEnd(nameInput) {
    try {
      const len = (nameInput.value || "").length;
      return nameInput.selectionStart === len && nameInput.selectionEnd === len;
    } catch (e) {
      return true;
    }
  }

  function updateInlineGhost() {
    const nameInput = document.getElementById("position_name");
    if (!nameInput) return;
    if (!ghostEl) setupInlineGhost();
    if (!ghostEl) return;
    syncGhostStyle();
    const typed = nameInput.value || "";
    if (!typed || !positionRankSuggestion || !caretAtEnd(nameInput) ||
        document.activeElement !== nameInput) {
      ghostEl.innerHTML = "";
      ghostEl.scrollLeft = nameInput.scrollLeft;
      return;
    }
    // Ghost continuation = remainder of the full suggestion after typed text.
    // e.g. typed "Profe", full "Professor III" -> gray "ssor III".
    // The suggestion is never part of the real value until accepted.
    const leadingSpaces = typed.length - typed.trimStart().length;
    const trimmedLen = typed.trim().length;
    const suffixText = positionRankSuggestion.slice(leadingSpaces + trimmedLen);
    if (!suffixText) {
      ghostEl.innerHTML = "";
      return;
    }
    // Invisible mirror of typed text keeps the gray suffix aligned after caret.
    ghostEl.innerHTML =
      '<span style="visibility:hidden;">' + escapeHtml(typed) + "</span>" +
      '<span style="color:#9ca3af;">' + escapeHtml(suffixText) + "</span>";
    ghostEl.scrollLeft = nameInput.scrollLeft;
  }

  function acceptRankSuggestion() {
    const nameInput = document.getElementById("position_name");
    if (!nameInput || !positionRankSuggestion) return;
    ghostDismissedFor = null;
    nameInput.value = positionRankSuggestion;
    positionRankSuggestion = null;
    // Re-run so category auto-match + next ghost state refresh, caret to end.
    onPositionNameInput();
    try {
      const len = nameInput.value.length;
      nameInput.setSelectionRange(len, len);
    } catch (e) {}
    updateInlineGhost();
  }

  function dismissRankSuggestion() {
    const nameInput = document.getElementById("position_name");
    ghostDismissedFor = nameInput ? (nameInput.value || "").trim() : null;
    positionRankSuggestion = null;
    updateInlineGhost();
  }

  async function openAddPositionModal() {
    const modal = document.getElementById("positionRankModal");
    const form = document.getElementById("positionRankForm");
    const title = document.getElementById("positionRankModalTitle");
    const activeWrapper = document.getElementById("position_active_wrapper");

    if (modal && form && title) {
      form.reset();
      document.getElementById("position_rank_id").value = "";
      await loadCategoryOptions();
      categoryMatchOverride = false;
      ghostDismissedFor = null;
      positionRankSuggestion = null;
      const nameInput = document.getElementById("position_name");
      if (nameInput) {
        nameInput.setAttribute("autocomplete", "off");
        nameInput.setAttribute("autocapitalize", "off");
        nameInput.setAttribute("spellcheck", "false");
      }
      updateInlineGhost();
      title.textContent = "Add Faculty Rank / Rank";
      activeWrapper.style.display = "none";
      modal.style.display = "flex";
    }
  }

  async function editPositionRank(rankId) {
    const modal = document.getElementById("positionRankModal");
    const form = document.getElementById("positionRankForm");
    const title = document.getElementById("positionRankModalTitle");
    const activeWrapper = document.getElementById("position_active_wrapper");

    if (!modal || !form || !title) return;

    const rank = positionRanks.find((item) => item.id === rankId);
    if (!rank) return;

    document.getElementById("position_rank_id").value = rankId;
    document.getElementById("position_name").value = rank.name;
    await loadCategoryOptions(rank.category);
    document.getElementById("position_category").value = rank.category;
    categoryMatchOverride = false;
    document.getElementById("position_active").checked = !!rank.is_active;
    title.textContent = "Edit Position / Rank";
    activeWrapper.style.display = "block";
    modal.style.display = "flex";
  }

  function closePositionRankModal() {
    const modal = document.getElementById("positionRankModal");
    if (modal) modal.style.display = "none";
  }

  async function handlePositionRankSubmit(e) {
    e.preventDefault();
    const form = e.currentTarget;
    const rankId = document.getElementById("position_rank_id").value;
    const isEdit = !!rankId;

    const data = {
      name: document.getElementById("position_name").value.trim(),
      category: document.getElementById("position_category").value,
    };

    if (isEdit) {
      data.is_active = document.getElementById("position_active").checked;
    }

    const csrf = getCSRFToken();
    const url = isEdit
      ? `/api/treasurer/members/position-ranks/${rankId}/update/`
      : "/api/treasurer/members/position-ranks/add/";

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf,
        },
        body: JSON.stringify(data),
        credentials: "same-origin",
      });

      const result = await response.json();

      if (result.ok) {
        showToast(isEdit ? "Position rank updated successfully" : "Position rank added successfully");
        closePositionRankModal();
        loadPositionRanks();
        if (window.loadPositionCategories) window.loadPositionCategories();
      } else {
        showToast(result.error || "Failed to save position rank", true);
      }
    } catch (error) {
      console.error("Error saving position rank:", error);
      showToast("Error saving position rank", true);
    }
  }

  async function togglePositionRank(button, rankId) {
    const rank = positionRanks.find((item) => item.id === rankId);
    if (!rank) return;
    const name = rank.name;
    const category = rank.category;
    const isCurrentlyActive = !!rank.is_active;
    const csrf = getCSRFToken();

    const url = isCurrentlyActive
      ? `/api/treasurer/members/position-ranks/${rankId}/delete/`
      : `/api/treasurer/members/position-ranks/${rankId}/update/`;
    const options = {
      method: "POST",
      headers: { "X-CSRFToken": csrf },
      credentials: "same-origin",
    };
    if (!isCurrentlyActive) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify({ name: name, category: category, is_active: true });
    }

    try {
      const response = await fetch(url, options);
      const result = await response.json();
      if (result.ok) {
        showToast(isCurrentlyActive ? "Faculty rank deactivated" : "Faculty rank activated");
        loadPositionRanks();
        if (window.loadPositionCategories) window.loadPositionCategories();
      } else {
        showToast(result.error || "Failed to update faculty rank", true);
      }
    } catch (error) {
      console.error("Error updating position rank:", error);
      showToast("Error updating faculty rank", true);
    }
  }

  function init() {
    const nameInputEarly = document.getElementById("position_name");
    if (nameInputEarly && nameInputEarly.dataset.inlineGhostBound === "1") {
      updateInlineGhost();
      return;
    }
    const form = document.getElementById("positionRankForm");
    if (form) {
      form.addEventListener("submit", handlePositionRankSubmit);
    }

    const nameInput = document.getElementById("position_name");
    const catSelect = document.getElementById("position_category");
    if (nameInput) {
      // Drop any legacy outside-the-box suggestion node from older markup.
      const legacy = document.getElementById("position_name_suggestion");
      if (legacy) legacy.remove();
      nameInput.dataset.inlineGhostBound = "1";
      setupInlineGhost();
      nameInput.addEventListener("input", function () {
        ghostDismissedFor = null;
        onPositionNameInput();
      });
      ["click", "keyup", "select", "focus"].forEach(function (evt) {
        nameInput.addEventListener(evt, updateInlineGhost);
      });
      nameInput.addEventListener("blur", function () {
        if (ghostEl) ghostEl.innerHTML = "";
      });
      nameInput.addEventListener("focus", function () {
        ghostDismissedFor = null;
        onPositionNameInput();
      });
      nameInput.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && positionRankSuggestion) {
          e.preventDefault();
          dismissRankSuggestion();
          return;
        }
        if (!positionRankSuggestion) return;
        // Accept ghost continuation inline: Tab / Enter / ArrowRight.
        // The gray text never becomes the value unless accepted here.
        if (e.key === "Tab" || e.key === "Enter" || e.key === "ArrowRight") {
          if (e.key === "ArrowRight" && !caretAtEnd(nameInput)) return;
          e.preventDefault();
          e.stopPropagation();
          acceptRankSuggestion();
        }
      }, true);
    }
    if (catSelect) {
      catSelect.addEventListener("change", function () {
        categoryMatchOverride = !!(catSelect.value || "").trim();
      });
    }

    // Expose functions globally for onclick handlers
    window.openAddPositionModal = openAddPositionModal;
    window.closePositionRankModal = closePositionRankModal;
    window.editPositionRank = editPositionRank;
    window.togglePositionRank = togglePositionRank;
    window.loadPositionRanks = loadPositionRanks;
    window.loadCategoryOptions = loadCategoryOptions;
    window.findBestCategoryMatch = findBestCategoryMatch;
    window.onPositionNameInput = onPositionNameInput;
    window.suggestNextRank = suggestNextRank;
    window.acceptRankSuggestion = acceptRankSuggestion;
    window.dismissRankSuggestion = dismissRankSuggestion;

    // Load positions immediately if section is visible
    const section = document.getElementById("view-position-ranks");
    if (section) {
      const isVisible = section.style.display !== "none" && section.style.visibility !== "hidden" && !section.classList.contains("hidden");
      if (isVisible) {
        loadPositionRanks();
      }

      // Also load when navigation menu items are clicked
      const menuItems = document.querySelectorAll('.menu-item[data-target="view-position-ranks"]');
      menuItems.forEach(item => {
        item.addEventListener('click', () => {
          setTimeout(loadPositionRanks, 100);
        });
      });

      // Fallback: observe style changes
      const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
          if (mutation.target.id === "view-position-ranks" && mutation.target.style.display !== "none") {
            loadPositionRanks();
          }
        });
      });

      observer.observe(section, { attributes: true, attributeFilter: ["style", "class"] });
    }
  }

  document.addEventListener("turbo:load", init);
  if (document.readyState !== "loading") init();
  else document.addEventListener("DOMContentLoaded", init);
})();
