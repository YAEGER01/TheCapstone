(function () {
  "use strict";

  const CATEGORY_PAGE_SIZE = 10;
  let positionCategories = [];
  let categoryPage = 1;
  let editingCategoryId = null;

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
      <span>${escapeHtml(message)}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = "slideOut 0.3s ease-out forwards";
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  async function loadPositionCategories() {
    const list = document.getElementById("positionCategoryList");
    try {
      const response = await fetch(
        `/api/treasurer/members/position-categories/list/?t=${new Date().getTime()}`,
        { credentials: "same-origin" }
      );
      const data = await response.json();

      if (data.ok) {
        positionCategories = Array.isArray(data.categories) ? data.categories : [];
        categoryPage = 1;
        renderCategoryList();
      } else if (list) {
        list.innerHTML =
          '<li class="position-category-empty">Failed to load categories.</li>';
      }
    } catch (error) {
      console.error("Error loading position categories:", error);
      if (list) {
        list.innerHTML =
          '<li class="position-category-empty">Error loading categories.</li>';
      }
    }
  }

  function renderCategoryList() {
    const list = document.getElementById("positionCategoryList");
    if (!list) return;
    const pagination = document.getElementById("positionCategoriesPagination");

    const categories = positionCategories;

    if (!categories.length) {
      list.innerHTML =
        '<li class="position-category-empty">No categories yet. Add one above.</li>';
      if (pagination) pagination.innerHTML = "";
      return;
    }

    const pageCount = Math.ceil(categories.length / CATEGORY_PAGE_SIZE);
    categoryPage = Math.min(Math.max(categoryPage, 1), pageCount);
    const start = (categoryPage - 1) * CATEGORY_PAGE_SIZE;
    const pageCategories = categories.slice(start, start + CATEGORY_PAGE_SIZE);

    list.innerHTML = pageCategories
      .map((category) => {
        const count = category.rank_count || 0;
        const meta = count === 1 ? "1 rank" : `${count} ranks`;
        const inactiveTag = category.is_active ? "" : " &bull; inactive";
        const inactiveClass = category.is_active ? "" : " is-inactive";
        return `
        <li class="position-category-item${inactiveClass}">
          <div class="position-category-info">
            <span class="position-category-name">${escapeHtml(category.name)}</span>
            <span class="position-category-meta">${meta}${inactiveTag}</span>
          </div>
          <div class="position-category-actions">
            <button type="button" class="position-category-rename" onclick="editPositionCategory(${category.id})">Rename</button>
            <button type="button" class="position-category-delete" onclick="deletePositionCategory(${category.id})">Delete</button>
          </div>
        </li>`;
      })
      .join("");

    if (pagination && typeof UniPager !== "undefined" && UniPager) {
      pagination.innerHTML = UniPager.html(
        categoryPage,
        pageCount,
        "window.__positionCategoryGoPage(PAGE)",
        UniPager.count(categoryPage, CATEGORY_PAGE_SIZE, categories.length)
      );
    }
  }

  window.__positionCategoryGoPage = function (page) {
    categoryPage = page;
    renderCategoryList();
  };

  function editPositionCategory(categoryId) {
    const category = positionCategories.find((item) => item.id === categoryId);
    if (!category) return;

    editingCategoryId = categoryId;
    document.getElementById("position_category_id").value = categoryId;
    document.getElementById("position_category_name").value = category.name;
    document.getElementById("positionCategorySubmit").textContent = "Save";
    document.getElementById("positionCategoryEditNote").style.display = "block";
    document.getElementById("position_category_name").focus();
  }

  function cancelPositionCategoryEdit() {
    editingCategoryId = null;
    const form = document.getElementById("positionCategoryForm");
    if (form) form.reset();
    document.getElementById("position_category_id").value = "";
    document.getElementById("positionCategorySubmit").textContent = "Add";
    document.getElementById("positionCategoryEditNote").style.display = "none";
  }

  async function handlePositionCategorySubmit(e) {
    e.preventDefault();

    const name = document.getElementById("position_category_name").value.trim();
    if (!name) {
      showToast("Category name is required", true);
      return;
    }

    const categoryId = document.getElementById("position_category_id").value;
    const isEdit = !!categoryId;
    const url = isEdit
      ? `/api/treasurer/members/position-categories/${categoryId}/update/`
      : "/api/treasurer/members/position-categories/add/";

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRFToken(),
        },
        body: JSON.stringify({ name: name }),
        credentials: "same-origin",
      });

      const result = await response.json();

      if (result.ok) {
        const renamed = result.renamed_ranks || 0;
        if (isEdit) {
          showToast(
            renamed
              ? `Category renamed — ${renamed} rank(s) updated`
              : "Category renamed successfully"
          );
        } else {
          showToast("Category added successfully");
        }
        cancelPositionCategoryEdit();
        loadPositionCategories();
        if (window.loadPositionRanks) window.loadPositionRanks();
      } else {
        showToast(result.error || "Failed to save category", true);
      }
    } catch (error) {
      console.error("Error saving position category:", error);
      showToast("Error saving category", true);
    }
  }

  async function deletePositionCategory(categoryId) {
    const category = positionCategories.find((item) => item.id === categoryId);
    if (!category) return;

    let confirmed = false;
    try {
      confirmed = await SimpleModal.confirm(`Delete category "${category.name}"?`, {
        title: "Delete Category",
        okText: "Delete",
        cancelText: "Cancel",
        danger: true,
      });
    } catch (e) {
      return;
    }
    if (!confirmed) return;

    try {
      const response = await fetch(
        `/api/treasurer/members/position-categories/${categoryId}/delete/`,
        {
          method: "POST",
          headers: { "X-CSRFToken": getCSRFToken() },
          credentials: "same-origin",
        }
      );

      const result = await response.json();

      if (result.ok) {
        showToast("Category deleted successfully");
        if (editingCategoryId === categoryId) cancelPositionCategoryEdit();
        loadPositionCategories();
      } else {
        showToast(result.error || "Failed to delete category", true);
      }
    } catch (error) {
      console.error("Error deleting position category:", error);
      showToast("Error deleting category", true);
    }
  }

  function init() {
    const form = document.getElementById("positionCategoryForm");
    if (form) form.addEventListener("submit", handlePositionCategorySubmit);

    window.loadPositionCategories = loadPositionCategories;
    window.editPositionCategory = editPositionCategory;
    window.deletePositionCategory = deletePositionCategory;
    window.cancelPositionCategoryEdit = cancelPositionCategoryEdit;

    const section = document.getElementById("view-position-ranks");
    if (!section) return;

    const isVisible =
      section.style.display !== "none" &&
      section.style.visibility !== "hidden" &&
      !section.classList.contains("hidden");
    if (isVisible) loadPositionCategories();

    const menuItems = document.querySelectorAll(
      '.menu-item[data-target="view-position-ranks"]'
    );
    menuItems.forEach((item) => {
      item.addEventListener("click", () => {
        setTimeout(loadPositionCategories, 120);
      });
    });
  }

  document.addEventListener("turbo:load", init);
})();
