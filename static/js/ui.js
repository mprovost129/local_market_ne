/* static/js/ui.js

LocalMarketNE - Pack BM

Small, global UI helpers:
- Prevent accidental double submits (disable submit buttons on form submit)
- Provide consistent loading micro-interactions (spinner + "Working…")
- Prevent double-click on any element explicitly marked data-disable-once

Designed to be safe and framework-agnostic (Bootstrap-friendly).
*/

(function () {
  "use strict";

  function hasClass(el, cls) {
    return el && el.classList && el.classList.contains(cls);
  }

  function makeSpinner() {
    var span = document.createElement("span");
    span.className = "spinner-border spinner-border-sm align-text-bottom me-2";
    span.setAttribute("role", "status");
    span.setAttribute("aria-hidden", "true");
    return span;
  }

  function markLoading(btn, label) {
    if (!btn || btn.dataset.lmLoading === "1") return;

    btn.dataset.lmLoading = "1";
    btn.dataset.lmOriginalHtml = btn.innerHTML;

    btn.innerHTML = "";
    btn.appendChild(makeSpinner());
    btn.appendChild(document.createTextNode(label || "Working…"));
  }

  function disableOnce(el) {
    if (!el || el.dataset.lmDisabledOnce === "1") return;
    el.dataset.lmDisabledOnce = "1";
    el.setAttribute("aria-disabled", "true");
    el.classList.add("disabled");

    if (typeof el.disabled !== "undefined") {
      el.disabled = true;
    }
  }

  function findPrimarySubmitButton(form) {
    if (!form) return null;

    var primary = form.querySelector('button[type="submit"].btn-primary');
    if (primary) return primary;

    return form.querySelector('button[type="submit"], input[type="submit"]');
  }

  function bindFormDoubleSubmitPrevention() {
    document.addEventListener("submit", function (evt) {
      var form = evt.target;
      if (!form || form.tagName !== "FORM") return;

      if (form.dataset.noDisableSubmit === "1") return;

      var submitButtons = form.querySelectorAll('button[type="submit"], input[type="submit"]');
      submitButtons.forEach(function (btn) {
        disableOnce(btn);
      });

      var primary = findPrimarySubmitButton(form);
      if (primary && primary.tagName === "BUTTON" && !hasClass(primary, "lm-no-loading")) {
        markLoading(primary, primary.getAttribute("data-loading-label") || "Working…");
      }
    });
  }

  function bindDisableOnceClicks() {
    document.addEventListener("click", function (evt) {
      var el = evt.target;
      if (!el) return;

      var node = el.closest ? el.closest("[data-disable-once]") : null;
      if (!node) return;

      if (node.dataset.lmDisabledOnce === "1") {
        evt.preventDefault();
        evt.stopPropagation();
        return;
      }

      disableOnce(node);

      if (node.tagName === "BUTTON" && !hasClass(node, "lm-no-loading")) {
        markLoading(node, node.getAttribute("data-loading-label") || "Working…");
      }
    });
  }

  function init() {
    bindFormDoubleSubmitPrevention();
    bindDisableOnceClicks();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();


// Bootstrap tooltips (optional)
(function () {
  try {
    if (window.bootstrap && typeof window.bootstrap.Tooltip === 'function') {
      var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
      tooltipTriggerList.forEach(function (el) {
        // Only init once
        if (!el._lmTooltip) {
          el._lmTooltip = new window.bootstrap.Tooltip(el);
        }
      });
    }
  } catch (e) {
    // No-op
  }
})();
