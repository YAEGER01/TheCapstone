let _popStateHandler = null;
let currentModule = null;
let _navInitDone = false;
let _navFullReady = false;

// Immediate minimal navigation — active class only; full loadModule replaces this on init.
function __caufaMinimalSetActive(target) {
  if (!target) return;
  currentModule = target;
  document.querySelectorAll(".dashboard-module").forEach((mod) => {
    mod.classList.toggle("active", mod.id === target);
  });
  const targetModule = document.getElementById(target);
  if (!targetModule) {
    const fallback = document.getElementById("dashboard-overview");
    if (fallback) fallback.classList.add("active");
    currentModule = "dashboard-overview";
  }
  document.querySelectorAll(".menu-item[data-target]").forEach((item) => {
    item.classList.toggle("active", item.getAttribute("data-target") === target);
  });
  const viewTitle = document.getElementById("currentModuleTitle");
  const menuItem = document.querySelector(`.menu-item[data-target="${target}"]`);
  if (viewTitle && menuItem) {
    const text = menuItem.querySelector(".menu-text");
    if (text) viewTitle.textContent = text.textContent.trim();
  }
  try {
    sessionStorage.setItem("caufa_treasurer_module", target);
  } catch (e) {}
}

window.__caufaNavMinimal = true;
window.setActiveModule = __caufaMinimalSetActive;

// Initialize dashboard navigation
function initDashboardNavigation() {
  if (_navInitDone) return;
  _navInitDone = true;

  const sidebar = document.getElementById("appSidebar");
  const toggleBtn = document.getElementById("headerSidebarToggle");
  const mobileToggleBtn = document.getElementById("mobileSidebarToggle");
  const viewTitle = document.getElementById("currentModuleTitle");

  const currentPath = window.location.pathname.toLowerCase();
  let rolePrefix = "/get-treasurer-module";

  if (currentPath.includes("/auditor")) {
    rolePrefix = "/get-auditor-module";
  } else if (currentPath.includes("/president")) {
    rolePrefix = "/get-president-module";
  }

  const isDesktopViewport = () => !window.matchMedia("(max-width: 1200px)").matches;

  if (sidebar) {
    // Start collapsed (icon rail) on desktop; never collapsed on mobile —
    // the mobile drawer is toggled with open-mobile instead.
    const collapsed = isDesktopViewport();
    sidebar.classList.toggle("collapsed", collapsed);
    const appContainer = document.querySelector(".app-container");
    if (appContainer) {
      appContainer.classList.toggle("sidebar-collapsed", collapsed);
    }
  }

  // Collapse/expand of the .collapsed class is owned by the per-dashboard
  // setupCollapsibleSidebar() (inline in treasurer_dashboard.html) — binding it
  // here as well would give the button an even number of toggles and cancel out.
  if (toggleBtn && sidebar && !toggleBtn.dataset.navToggleBound) {
    toggleBtn.dataset.navToggleBound = "1";
    toggleBtn.addEventListener("click", () => {
      const appContainer = document.querySelector(".app-container");
      if (appContainer) {
        appContainer.classList.toggle("sidebar-collapsed", sidebar.classList.contains("collapsed"));
      }
    });
  }

  if (mobileToggleBtn && sidebar && !mobileToggleBtn.dataset.navToggleBound) {
    mobileToggleBtn.dataset.navToggleBound = "1";
    mobileToggleBtn.addEventListener("click", () => {
      const opening = !sidebar.classList.contains("open-mobile");
      sidebar.classList.toggle("open-mobile", opening);
      if (opening) sidebar.classList.remove("collapsed");
    });
  }

  const STORAGE_KEY = "caufa_treasurer_module";
  const allMenuItems = document.querySelectorAll(".menu-item[data-target]");
  const allDashboardModules = document.querySelectorAll(".dashboard-module");

  function persistModule(moduleName) {
    sessionStorage.setItem(STORAGE_KEY, moduleName);
    if (history.replaceState) {
      history.replaceState({ module: moduleName }, "", `#${moduleName}`);
    }
  }

  function getPersistedModule() {
    const hash = window.location.hash.replace("#", "");
    const stored = sessionStorage.getItem(STORAGE_KEY);
    return hash || stored || "dashboard-overview";
  }

  function setActiveMenuItem(targetModule) {
    allMenuItems.forEach((item) => {
      item.classList.toggle(
        "active",
        item.getAttribute("data-target") === targetModule,
      );
    });
  }

  function updateViewTitle(moduleName) {
    if (!viewTitle) return;
    const menuItem = document.querySelector(
      `.menu-item[data-target="${moduleName}"]`,
    );
    if (menuItem) {
      const text = menuItem.querySelector(".menu-text");
      if (text) viewTitle.textContent = text.textContent.trim();
    }
  }

  function showModule(moduleName) {
    // Hide all modules
    allDashboardModules.forEach((module) => {
      module.classList.remove("active");
    });

    // Show the target module
    const targetModule = document.getElementById(moduleName);
    if (targetModule) {
      targetModule.classList.add("active");
    } else {
      console.warn(`Module ${moduleName} not found, defaulting to dashboard-overview`);
      const defaultModule = document.getElementById("dashboard-overview");
      if (defaultModule) {
        defaultModule.classList.add("active");
      }
    }
  }

  function loadModule(moduleName, pushState = true) {
    if (!moduleName || moduleName === currentModule) {
      return;
    }

    // Validate that the module exists in the DOM
    const moduleExists = document.getElementById(moduleName);
    if (!moduleExists) {
      console.warn(`Module ${moduleName} not found, defaulting to dashboard-overview`);
      moduleName = "dashboard-overview";
    }

    currentModule = moduleName;

    if (pushState) {
      persistModule(moduleName);
    }

    setActiveMenuItem(moduleName);
    showModule(moduleName);
    updateViewTitle(moduleName);

    // Re-bind module-specific behaviors
    try {
      if (moduleName === "view-dues-tracking" && typeof dtInit === 'function') {
        setTimeout(() => dtInit(), 100);
      }

      // Call module initialization functions for specific modules
      if (typeof window.nxModuleInit === 'function') {
        window.nxModuleInit(moduleName);
      }

      // Direct calls for specific modules that need data loading (backup/fallback)
      if (moduleName === "treasurer-activity-log" && typeof window.nxLoadActivityLogs === 'function') {
        setTimeout(() => window.nxLoadActivityLogs(), 200);
      }
      if (moduleName === "treasurer-notifications" && typeof window.nxRefreshNotifications === 'function') {
        setTimeout(() => window.nxRefreshNotifications(), 200);
      }
      if (moduleName === "treasurer-transaction-history" && typeof window.nxLoadTransactionHistory === 'function') {
        setTimeout(() => window.nxLoadTransactionHistory(), 200);
      }
      if (moduleName === "treasurer-aid-release" && typeof window.nxLoadReleases === 'function') {
        setTimeout(() => window.nxLoadReleases(), 200);
      }
      if (moduleName === "treasurer-repayment" && typeof window.nxLoadRepayment === 'function') {
        setTimeout(() => window.nxLoadRepayment(), 200);
      }
    } catch (e) {
      console.error("Module init hook failed:", e);
    }
  }

  // Override the global setActiveModule function
  window.setActiveModule = function(target) {
    if (target) {
      // Always refresh financial notification counts
      if (typeof fetchFinancialPendingCounts === "function") {
        try { fetchFinancialPendingCounts(); } catch (e) {}
      }

      // Auto-load registration requests when that module is activated
      if (target === "view-registration-requests") {
        if (typeof fetchRegistrationRequests === "function") {
          fetchRegistrationRequests();
        }
        if (typeof fetchFinancialPendingCounts === "function") {
          fetchFinancialPendingCounts();
        }
      }
      if (target === "view-claims-queue") {
        if (typeof loadClaimsQueue === "function") {
          loadClaimsQueue();
        }
      }
      if (target === "view-monthly-dues-approval") {
        if (typeof loadMonthlyDuesApprovalQueue === "function") {
          loadMonthlyDuesApprovalQueue();
        }
      }
      if (target === "view-returned-entries") {
        if (window.__refreshReturnedEntries) {
          window.__refreshReturnedEntries();
        }
      }
      if (target === "view-monthly-dues-returned") {
        if (window.__refreshMonthlyDuesReturned || window.__refreshReturnedMonthlyDues) {
          (window.__refreshMonthlyDuesReturned || window.__refreshReturnedMonthlyDues)();
        }
      }

      loadModule(target, true);
    }
  };
  _navFullReady = true;

  // ==========================================================================
  // INIT: RESTORE PERSISTED MODULE OR DEFAULT TO HOME
  // ==========================================================================
  const initialModule = getPersistedModule();
  currentModule = null;
  loadModule(initialModule, false);

  // ==========================================================================
  // SINGLE PAGE CONTENT SWITCHING ENGINE
  // ==========================================================================
  allMenuItems.forEach((item) => {
    if (item.dataset.navBound === "1") return;
    item.dataset.navBound = "1";
    item.dataset.treasurerNavigationBound = "1";

    // Inline onclick already calls setActiveModule — avoid double navigation.
    if (item.hasAttribute("onclick")) return;

    item._clickHandler = function (e) {
      const targetModule = this.getAttribute("data-target");
      if (!targetModule) return;

      e.preventDefault();
      e.stopPropagation();
      loadModule(targetModule, true);

      const appSidebar = document.getElementById("appSidebar");
      if (appSidebar) appSidebar.classList.remove("open-mobile");
    };

    item.addEventListener("click", item._clickHandler);
    item.style.cursor = 'pointer';
    item.style.pointerEvents = 'auto';
  });

  // Handle browser back/forward buttons
  if (_popStateHandler) window.removeEventListener("popstate", _popStateHandler);
  _popStateHandler = function (e) {
    const module = e.state && e.state.module ? e.state.module : getPersistedModule();
    currentModule = null;
    loadModule(module, false);
  };
  window.addEventListener("popstate", _popStateHandler);
}

// Initialize on DOMContentLoaded
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initDashboardNavigation);
} else {
  initDashboardNavigation();
}

// Also initialize on turbo:load for SPA navigation (guarded by _navInitDone)
document.addEventListener("turbo:load", initDashboardNavigation);

// ==========================================================================
// SYSTEM-WIDE TOAST NOTIFICATION MATRIX
// ==========================================================================
function showNotification(message, type = "info") {
  const container = document.getElementById("alert-container");
  const box = document.getElementById("alert-box");
  const msgSpan = document.getElementById("alert-message");
  const iconSpan = document.getElementById("alert-icon");

  if (!container || !box || !msgSpan || !iconSpan) return;

  msgSpan.textContent = message;

  if (type === "success") {
    box.style.backgroundColor = "#16a34a"; // Emerald green
    iconSpan.innerHTML = '<i class="fa-solid fa-circle-check"></i>';
  } else if (type === "error") {
    box.style.backgroundColor = "#dc2626"; // Deep warning red
    iconSpan.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i>';
  } else {
    box.style.backgroundColor = "#2563eb"; // Corporate Info Blue
    iconSpan.innerHTML = '<i class="fa-solid fa-circle-info"></i>';
  }

  container.style.display = "block";

  // Auto clearance execution routine
  setTimeout(() => {
    container.style.display = "none";
  }, 4500);
}
