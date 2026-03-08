/* products/static/products/seller/listing_wizard.js */
(function () {
  function qs(root, sel) { return root.querySelector(sel); }
  function qsa(root, sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); }

  document.addEventListener('DOMContentLoaded', function () {
    var form = document.querySelector('[data-wizard-form]');
    var root = document.querySelector('[data-wizard-root]');
    var nav = document.querySelector('[data-wizard-nav]');
    var progress = document.querySelector('[data-step-progress]');
    var saveMode = document.getElementById('id_save_mode');
    if (!form || !root || !nav || !progress || !saveMode) return;

    var steps = [1, 2, 3, 4, 5];
    var current = 1;

    function setActive(step) {
      current = step;
      qsa(root, '[data-step]').forEach(function (el) {
        el.classList.toggle('is-active', String(el.getAttribute('data-step')) === String(step));
      });

      // Stepper buttons
      qsa(document, '.lm-step-btn').forEach(function (btn) {
        btn.classList.toggle('active', String(btn.getAttribute('data-step-target')) === String(step));
      });

      // Progress bar
      var pct = Math.round((step / steps.length) * 100);
      progress.style.width = pct + '%';
      progress.setAttribute('aria-valuenow', String(pct));

      // Prev/Next
      var prevBtn = qs(nav, '[data-wizard-prev]');
      var nextBtn = qs(nav, '[data-wizard-next]');
      if (prevBtn) prevBtn.disabled = (step === 1);
      if (nextBtn) nextBtn.disabled = (step === steps.length);

      // Scroll to top of card
      var cardBody = form.closest('.card-body');
      if (cardBody) cardBody.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function next() {
      if (current < steps.length) setActive(current + 1);
    }

    function prev() {
      if (current > 1) setActive(current - 1);
    }

    // Navigation handlers
    nav.addEventListener('click', function (e) {
      var t = e.target.closest('[data-wizard-next],[data-wizard-prev]');
      if (!t) return;
      e.preventDefault();
      if (t.hasAttribute('data-wizard-next')) next();
      if (t.hasAttribute('data-wizard-prev')) prev();
    });

    // Step buttons
    qsa(document, '.lm-step-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var step = parseInt(btn.getAttribute('data-step-target') || '1', 10);
        if (!isNaN(step)) setActive(step);
      });
    });

    // Save modes
    var btnDraft = form.querySelector('[data-save-draft]');
    var btnNormal = form.querySelector('[data-save-normal]');
    if (btnDraft) {
      btnDraft.addEventListener('click', function () {
        saveMode.value = 'draft';
      });
    }
    if (btnNormal) {
      btnNormal.addEventListener('click', function () {
        saveMode.value = '';
      });
    }

    // If errors exist, jump directly to the server-provided step.
    var firstError = form.querySelector('.is-invalid, .text-danger.small, .lm-error-summary');
    if (firstError) {
      var initialStep = parseInt(form.getAttribute('data-initial-step') || '1', 10);
      if (isNaN(initialStep) || initialStep < 1 || initialStep > steps.length) {
        initialStep = 1;
      }
      setActive(initialStep);
    } else {
      setActive(1);
    }
  });
})();
