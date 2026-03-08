// products/static/products/seller/kind_sections.js
(function () {
  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  function setDisabled(container, disabled) {
    qsa('input, select, textarea', container).forEach(function (el) {
      // never disable CSRF or kind/category/subcategory
      if (el.name === 'csrfmiddlewaretoken') return;
      if (el.name === 'kind' || el.name === 'category' || el.name === 'subcategory') return;
      el.disabled = disabled;
    });
  }

  function updateCategoryLabel(kindVal) {
    var label = qs('label[for="id_category"]');
    if (!label) return;
    if (kindVal === 'SERVICE') label.textContent = 'Service category';
    else label.textContent = 'Product category';
  }

  function applyKind(kindVal) {
    qsa('.lm-kind-section').forEach(function (sec) {
      var k = sec.getAttribute('data-kind');
      var show = (k === kindVal);
      sec.style.display = show ? '' : 'none';
      setDisabled(sec, !show);
    });
    updateCategoryLabel(kindVal);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var kindEl = qs('select[name="kind"]') || qs('#id_kind');
    if (!kindEl) return;
    applyKind(kindEl.value || 'GOOD');
    kindEl.addEventListener('change', function () {
      applyKind(kindEl.value || 'GOOD');
    });

    // If there are errors, scroll to the summary for faster correction.
    var summary = qs('.lm-error-summary');
    if (summary) {
      summary.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
})();
