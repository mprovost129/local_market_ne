// static/js/recaptcha_v3.js
//
// Global reCAPTCHA v3 helper.
//
// Convention:
// - Any <form> with attribute data-recaptcha-action="..." will be intercepted on submit.
// - The form must contain a hidden input named "recaptcha_token".
// - We fetch a v3 token for the provided action and then submit.

(function () {
  function bindRecaptchaForms() {
    var forms = document.querySelectorAll('form[data-recaptcha-action]');
    if (!forms.length) return;

    forms.forEach(function (form) {
      if (form.__recaptchaBound) return;
      form.__recaptchaBound = true;

      form.addEventListener('submit', function (evt) {
        var action = form.getAttribute('data-recaptcha-action');
        var tokenField = form.querySelector('input[name="recaptcha_token"]');

        // If the form isn't wired correctly, do nothing.
        if (!action || !tokenField) return;

        // If token already present, allow submit (e.g., repeated submit after validation errors).
        if ((tokenField.value || '').trim().length > 0) return;

        // Block and fetch token.
        evt.preventDefault();

        if (!window.grecaptcha || !grecaptcha.ready || !grecaptcha.execute) {
          // Fail open: allow submit without token (server-side decorator will handle if configured).
          form.submit();
          return;
        }

        grecaptcha.ready(function () {
          try {
            var siteKey = (window.__RECAPTCHA_SITE_KEY || '').trim();
            // If not present, grecaptcha.execute will still work because script was loaded with render=SITE_KEY.
            grecaptcha.execute(siteKey || undefined, { action: action }).then(function (token) {
              tokenField.value = token;
              form.submit();
            }).catch(function () {
              // Fail open
              form.submit();
            });
          } catch (e) {
            form.submit();
          }
        });
      });
    });
  }

  document.addEventListener('DOMContentLoaded', bindRecaptchaForms);
})();
