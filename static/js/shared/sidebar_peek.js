/*
 * sidebar_peek.js — hover-to-peek for collapsed dashboard sidebars.
 *
 * When a dashboard's sidebar is collapsed down to its icon rail, hovering the
 * rail temporarily opens the full sidebar (labels, folders, badges); moving the
 * pointer away collapses it back to the rail. The peek never changes the
 * user's pinned state — if the sidebar was expanded by the header toggle, or
 * collapsed by it, that choice is restored when the pointer leaves.
 *
 * Works for both collapse conventions used in the dashboards:
 *   - `.sidebar.collapsed`          (Treasurer / Auditor / President / Superadmin / Secretary / SystemBackup)
 *   - `.app-container.sidebar-collapsed`  (PIO)
 *
 * Pointer-only: gated on (hover: hover) and (pointer: fine) so touch devices
 * (where there is no hover and the sidebar is a drawer) are left alone.
 */
(function () {
  "use strict";

  var canHover = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  function bind() {
    if (!canHover) return;

    var sidebar = document.querySelector("aside#appSidebar, aside.sidebar");
    if (!sidebar || sidebar.dataset.peekBound === "1") return;
    sidebar.dataset.peekBound = "1";

    var container =
      sidebar.closest && sidebar.closest(".app-container")
        ? sidebar.closest(".app-container")
        : null;

    // null when not peeking, otherwise the state to restore on mouseleave.
    var restore = null;

    function openPeek() {
      if (restore) return;
      var state = {
        rail: sidebar.classList.contains("collapsed"),
        shell: !!container && container.classList.contains("sidebar-collapsed"),
      };
      if (!state.rail && !state.shell) return; // already expanded — nothing to do
      restore = state;
      sidebar.classList.remove("collapsed");
      if (container) container.classList.remove("sidebar-collapsed");
    }

    function closePeek() {
      if (!restore) return;
      var state = restore;
      restore = null;
      if (state.rail) sidebar.classList.add("collapsed");
      if (state.shell && container) container.classList.add("sidebar-collapsed");
    }

    sidebar.addEventListener("mouseenter", openPeek);
    sidebar.addEventListener("mouseleave", closePeek);

    // Controls inside the rail that deliberately expand the sidebar (folder
    // headers, and the rail's own collapse button) win over a pending peek —
    // otherwise the folder the user just opened would snap shut on pointer-leave.
    sidebar.addEventListener("click", function (e) {
      if (!restore) return;
      var t = e.target;
      if (t && t.closest && t.closest(".folder-header, .collapse-toggle-btn")) {
        restore = null;
      }
    });

    // Keyboard parity: focusing anything inside the rail peeks it open, and
    // tabbing out (or losing focus entirely) closes it again.
    sidebar.addEventListener("focusin", openPeek);
    sidebar.addEventListener("focusout", function (e) {
      if (!sidebar.contains(e.relatedTarget)) closePeek();
    });
    window.addEventListener("blur", closePeek);
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) closePeek();
    });
    window.addEventListener("pagehide", closePeek);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
  document.addEventListener("turbo:load", bind);
})();
