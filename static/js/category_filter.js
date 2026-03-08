// static/js/category_filter.js
// Lightweight client-side filter for category sidebars (desktop + mobile).

(function () {
  function normalize(s) {
    return (s || "").toString().trim().toLowerCase();
  }

  function applyFilter(scope, scopeId, query) {
    const list = document.querySelector(`[data-cat-list][data-cat-scope="${scope}"][data-cat-scope-id="${scopeId}"]`);
    if (!list) return;

    const q = normalize(query);
    const items = list.querySelectorAll("[data-cat-item]");
    items.forEach((el) => {
      const text = normalize(el.textContent);
      const match = !q || text.includes(q);
      // We hide the anchor. The surrounding accordion item can remain.
      el.style.display = match ? "" : "none";
    });
  }

  function bind() {
    document.querySelectorAll("[data-cat-filter]").forEach((input) => {
      const scope = input.getAttribute("data-cat-scope") || "desk";
      const scopeId = input.getAttribute("data-cat-scope-id") || "";
      input.addEventListener("input", () => applyFilter(scope, scopeId, input.value));
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
