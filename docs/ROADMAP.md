## 2026-02-20 — Pack CZ — Prod host/origin env config ✅

**Completed**
- Made production host/origin configuration environment-driven via `PRIMARY_DOMAIN` (+ optional `RENDER_EXTERNAL_HOSTNAME`).
- Updated Render Blueprint + `.env.example` + docs to match the new domain-driven approach.
- Updated `env_audit` to treat `PRIMARY_DOMAIN` as the prod-required host variable.

**Next**
- Production deploy on Render + first-live validation (docs/GO_LIVE_KIT.md).


## 2026-02-20 — Pack CY — Env var audit + docs alignment ✅

**Completed**
- Added `python manage.py env_audit` to print required/recommended environment variables (with `--strict` mode).
- Updated `.env.example` to include email + S3 keys and align naming.
- Added `docs/ENV_VARS.md` as a single reference page.
- Fixed deploy/go-live docs to use the correct env variable names (`DJANGO_SECRET_KEY`, `STRIPE_PUBLIC_KEY`, etc.).

**Next**
- Production deploy on Render + first-live validation (docs/GO_LIVE_KIT.md).


## 2026-02-18 — Pack CL — RC checklist runner (rc_report) ✅

**Completed**
- Added `python manage.py rc_report` to run RC-oriented checks and emit a consolidated report (human + JSON).
- Wrapper executes: `rc_check`, `url_reverse_audit`, `template_deadend_audit`, and `money_loop_check`.

**Next**
- Pack CN — Run `docs/RC_CHECKLIST.md` manually end-to-end (Stripe test mode) and fix any remaining flow blockers found.


## 2026-02-18 — Pack CM — Consumer browse card enhancements ✅

**Completed**
- Improved listing cards to include seller public location (city/state) when available.
- Added quick-scan fulfillment badges for products (Pickup / Delivery / Shipping).
- Added service-radius badge for services when the seller has a radius set.

**Next**
- Pack CN — Manual run of `docs/RC_CHECKLIST.md` end-to-end (Stripe test mode) + fix blockers.


## 2026-02-18 — Pack CN — RC checklist support tooling ✅

**Completed**
- Added `python manage.py flow_check` to create a tiny fixture set and request key pages (seller + consumer) plus a cart add.
- Updated `python manage.py rc_report` to include `flow_check` in the consolidated RC report.

**Next**
- Pack CO — Run `docs/RC_CHECKLIST.md` manually end-to-end (Stripe test mode) and fix any remaining blockers discovered.


## 2026-02-18 — Pack CO — RC Stripe config check + tooling fixups ✅

**Completed**
- Added `python manage.py stripe_config_check` (keys + webhook route reversal) to reduce Stripe go-live surprises.
- Fixed `rc_check` to run cleanly (previously had a broken try/except block around audits).
- Extended `url_reverse_audit` to support `--json`, `--limit`, and `--quiet` so `rc_report` can reliably aggregate results.
- Updated `rc_report` to emit structured JSON for `rc_check` and to include `stripe_config_check`.
- Added a manual RC results template for recording end-to-end checklist outcomes.

**Next**
- Pack CP — Manual run of `docs/RC_CHECKLIST.md` end-to-end (Stripe test mode) + fix any remaining flow blockers found.


## 2026-02-19 — Pack CP — RC checklist manual run support ✅

**Completed**
- Added `python manage.py rc_results_init` to generate a timestamped manual RC run log under `docs/rc_runs/` from `docs/RC_RESULTS_TEMPLATE.md`.
- Updated `docs/RC_CHECKLIST.md` to reference the initializer as an optional first step.

**Next**
- Production deploy on Render + first-live validation (docs/GO_LIVE_KIT.md).


## 2026-02-19 — Pack CQ — Render Blueprint + deploy doc alignment ✅

**Completed**
- Added `render.yaml` (Render Blueprint) to create the web service + database with sensible defaults.
- Aligned `docs/DEPLOY_RENDER.md` environment variable guidance with actual settings module (`config.settings.prod`) and current host/origin lists.

**Next**
- Production deploy on Render + first-live validation (docs/GO_LIVE_KIT.md).


## 2026-02-19 — Pack CR — Post-deploy validation command ✅

**Completed**
- Added `python manage.py post_deploy_check` (settings/env sanity, DB ping, staticfiles signal, optional public `/healthz/` HTTP check).
- Updated go-live and post-deploy docs to include the new command.

**Next**
- Production deploy on Render + first-live validation (docs/GO_LIVE_KIT.md).


## 2026-02-19 — Pack CS — Config key alignment (S3 + reCAPTCHA) ✅

**Completed**
- Standardized S3 config across code/docs to use `AWS_S3_MEDIA_BUCKET` (kept `AWS_STORAGE_BUCKET_NAME` as legacy env alias).
- Fixed launch checks and post-deploy checks to look for the correct S3 + reCAPTCHA v3 settings keys.

**Next**
- Production deploy on Render + first-live validation (docs/GO_LIVE_KIT.md).

## 2026-02-19 — Pack CT — First-live validation helper ✅

**Completed**
- Added `python manage.py first_live_validate` to run `post_deploy_check` and (optionally) perform public HTTP checks against `/healthz/`, `/catalog/`, and `/accounts/login/`.
- Updated go-live and post-deploy docs to include the new helper.

**Next**
- Production deploy on Render + first-live validation (docs/GO_LIVE_KIT.md).


## 2026-02-19 — Pack CU — Render start script + runtime pin ✅

**Completed**
- Added `scripts/render_start.sh` used by Render to start Gunicorn and optionally run migrations.
- Added `RUN_MIGRATIONS_ON_START` env toggle (blueprint defaults to `0` for first-deploy safety).
- Added `runtime.txt` to pin the Render Python runtime.
- Updated deploy/go-live docs to match the Render start script and the migration toggle.

**Next**
- Production deploy on Render + first-live validation (docs/GO_LIVE_KIT.md).


## 2026-02-19 — Pack CV — Checkout kill switch (SiteConfig) ✅

**Completed**
- Added `SiteConfig.checkout_enabled` + `SiteConfig.checkout_disabled_message` for an emergency “checkout off” switch.
- Enforced the switch in `orders:checkout_start` (owner bypass still allowed).
- Updated cart + order detail pages to disable checkout UI and show the configured message.
- Exposed the switch in Dashboard → Admin Settings (no Django-admin required).
- Updated go-live kit rollback guidance to reference the new switch.

**Next**
- Production deploy on Render + first-live validation (docs/GO_LIVE_KIT.md).


## 2026-02-19 — Pack CW — First-live check fixes + version endpoint checks ✅

**Completed**
- Fixed `first_live_validate` and `post_deploy_check` to accept the actual `/healthz/` payload shape (`status:"ok"`), avoiding false failures.
- Added `/version/` public checks to `first_live_validate` and `post_deploy_check`.
- Added `core:version` to `smoke_check` critical routes.
- Removed duplicate `/healthz/` route from `core.urls` (canonical route remains at project root).
- Updated go-live docs to reflect `/healthz/` and `/version/` expectations.

**Next**
- Production deploy on Render + first-live validation (docs/GO_LIVE_KIT.md).



## 2026-02-18 — Pack CK — RC UI pass (tooltips + mobile navbar spacing) ✅

**Completed**
- Added optional Bootstrap tooltip initialization (`static/js/ui.js`).
- Added first-run tip tooltips on Consumer and Seller dashboards.
- Improved mobile navbar spacing and logo scaling with `.lm-navbar` and `.lm-logo`.

**Next**
- Pack CL — Run `docs/RC_CHECKLIST.md` end-to-end (Test Mode) and fix any RC blockers found.

## 2026-02-18 — Pack CI — RC Hardening (Dead-end audit resilience) ✅

**Completed**
- `empty_state` partial now uses safe `{% url ... as var %}` resolving to prevent template `NoReverseMatch` crashes.
- Removed a disabled dead-end anchor on seller listings (use `<span>`).
- Added `data-lm-ignore-deadend` markers on navbar dropdown toggles for strict audit compatibility.

**Next**
- Pack CJ — RC UI pass: seller/consumer “first run” guidance (tooltips + empty-state CTAs) + finalize mobile nav spacing.

## 2026-02-17 — Pack CC — Seller Listing Form Kind Sections + Error Summary ✅

**Completed**
- Seller listing create/edit now hides irrelevant sections based on kind (Product vs Service) and disables hidden inputs.
- Category label updates dynamically (Product category / Service category).
- Added error summary with auto-scroll for faster correction.

**Completed**
- Pack CD — Category sidebar filter/search (desktop sidebar + mobile offcanvas).
- Pack CE — Release Runbook + Go-Live Kit (Render deploy checklist, first-live validation, rollback steps) + `rc_check` usage docs.

**Completed**
- Pack CG — RC sweep: seller + buyer end-to-end QA checklist, dead-end link audit, and polish pass.
- Pack CH — Visual polish sweep (forms, steppers, surfaces) + sticky action row on seller listing form.

**Next**
- Pack CI — Run `docs/RC_CHECKLIST.md` end-to-end (Test Mode) and fix any RC blockers (routes, permissions, webhooks, refunds).

---

## 2026-02-17 — Pack CF — Seller listing mini-wizard + draft-save ✅

**Completed**
- Seller listing form now uses a lightweight stepper UX:
  - Type → Category → Details → Fulfillment → Media & Publish
- Added **Save draft** mode (forces unpublished) for both create and edit.
- Create flow: draft-save redirects to edit (so seller can add images later); normal save redirects to images.

---

## Pack CA — Dashboard Settings Reliability Sweep ✅
- Rebuilt SiteConfigForm to correctly save all settings from dashboard.
- Added SiteConfig post_save cache invalidation.

## 2026-02-17 — Pack BZ — RC gate command (rc_check) ✅

**Completed**
- Added `python manage.py rc_check` to bundle:
  - `smoke_check` (optionally with `--checks` and `--db`)
  - `launch_check` (settings posture + invariants)
- Intended as the single pre-deploy gate for local/dev/CI.

**Next**
- Pack CA — Release runbook + RC checklist (deploy, smoke, launch checks, rollback).

---

## 2026-02-17 — Pack CA (hotfix) — Listing upload category filtering ✅

**Completed**
- Fixed catalog category APIs to support `GOOD|SERVICE` and return `results` for seller form dropdowns.
- Seller listing form now filters categories by listing kind and correctly loads subcategories.

**Next (still Pack CA)**
- Release runbook + RC checklist (deploy, smoke, launch checks, rollback).
- “Go-live kit” docs polish: Render env var checklist + first-live validation steps.

## 2026-02-16 — Pack BT — Empty-state standardization sweep ✅

**Completed**
- Standardized empty states to use `templates/partials/empty_state.html` across:
  - Admin/consumer dashboards
  - Favorites / Wishlist
  - Notifications inbox
  - Seller order list
  - Payouts dashboard
  - Seller listings + public shop pages
  - Top sellers
  - Q&A and Reviews tabs
  - Category list

**Next**
- Pack BU — RC end-to-end Money Loop verification (checkout → webhook → ledger → payouts) + fixes.


## 2026-02-16 — Pack BF — Crawl protection (robots + noindex middleware) ✅

**Completed**
- `robots.txt` now disallows `/admin/`, `/ops/`, `/staff/`, `/dashboard/`, and `/accounts/`.
- Added `RobotsNoIndexMiddleware` to emit `X-Robots-Tag: noindex, nofollow` on HTML responses under those private paths.

**Next**
- Pack BG — End-to-end smoke test command (URLs + templates) + final RC bugfixes.


## 2026-02-16 — Pack BG — End-to-end smoke test command (URLs + templates) ✅

**Completed**
- Added `python manage.py smoke_check` to validate critical named routes reverse correctly and key templates compile.
- Command is lightweight and intended to catch dead-end regressions quickly during RC hardening.

**Next**
- Pack BH — RC smoke check improvements (system checks + DB ping).


## 2026-02-16 — Pack BH — RC smoke check improvements (system checks + DB ping) ✅

**Completed**
- Enhanced `python manage.py smoke_check` with optional flags:
  - `--checks` runs Django system checks.
  - `--db` runs a tiny ORM “DB ping” (verifies migrations/tables are present for core/products/orders).
- Output now reports enabled extras when not in `--quiet` mode.

**Next**
- Pack BI — Public health endpoint + smoke check wiring.


## 2026-02-16 — Pack BI — Public health endpoint + smoke check wiring ✅

**Completed**
- Added `GET /healthz/` public endpoint returning lightweight JSON for hosting providers/uplink checks.
- Added `healthz` route reversal to `python manage.py smoke_check` critical routes.

**Next**

- Pack BJ — Ops Health page (HTML + JSON) ✅


## 2026-02-16 — Pack BJ — Ops Health page (HTML + JSON) ✅

**Completed**
- Ops Health (`/ops/health/`) now renders a human-friendly Ops Console page by default.
- Ops Health supports `?format=json` for automation/quick copy.
- Ops Health links to the public `/healthz/` endpoint and Launch Check.

**Next**
- Pack BK — Seller onboarding policy + managed GA/AdSense + remove buyer age gate.




## 2026-02-16 — Pack BK — Seller onboarding policy + managed GA/AdSense + remove buyer age gate ✅

**Completed**
- Enforced seller-only 18+ confirmation at Stripe onboarding start (buyers are not gated).
- Added seller prohibited items acknowledgement (no tobacco, alcohol, firearms) at onboarding start.
- Added SiteConfig-managed GA4 and AdSense fields; removed hardcoded IDs from templates and injected scripts only when configured.
- Exposed GA/AdSense + seller onboarding policy fields in the Admin Settings dashboard form.

**Next**
- Pack BL — V1 UX/CSS polish sweep + final seller onboarding copy + dead-end audit (TBD).
## 2026-02-16 — Pack BE — Final pre-deploy sweep: settings sanity + small UI copy fixes ✅

**Completed**
- Launch Check now validates production security posture (SSL redirect, secure cookies, proxy SSL header) and warns on dev cookie-domain misconfigurations.
- Ops Launch Check copy updated to clarify dev vs prod expectations.

**Next**
- Pack BF — TBD (final UX polish + any remaining bugfixes).


## 2026-02-16 — Pack BD — Reconciliation export polish + final ops wording pass ✅

**Completed**
- Added CSV export support for Ops Reconciliation:
  - `/ops/reconciliation/?format=csv`
  - `/ops/reconciliation/mismatches/?format=csv`
- Added **Export CSV** buttons to both reconciliation pages.
- Export is capped to 5,000 rows defensively to avoid pathological downloads.

# 2026-02-16 — Pack AZ — Order detail cleanup + template integrity pass ✅

**Completed**
- Added a **template compilation test** (`core/tests.py`) that compiles key templates to catch `TemplateSyntaxError` early.
- Tightened order/detail-related template integrity by including the order detail templates in the integrity list.
- Hotfix: fixed seller dashboard crash caused by annotating `line_total_cents` (annotation name conflicted with model field). Seller dashboard now uses the stored `OrderItem.line_total_cents` field directly.

**Next**
- Pack BA — Release candidate stabilization: smoke test checklist + runbook tighten-up + fix any remaining template/view dead-ends.


## 2026-02-16 — Pack AY — Buyer delivery confirmation + timeline polish ✅

**Completed**
- Buyer can confirm **pickup/delivery** items after seller marks them **READY**.
- Buyer can confirm **shipping** items after seller marks them **SHIPPED**.
- Guest orders are supported via `?t=<order_token>` (token accepted on POST).
- Order detail page now shows a second timeline card for **pickup/delivery** items.
- Added safe throttling for buyer confirmation + off-platform “sent” marking.

**Next**
- Pack AZ — Order detail cleanup + template integrity pass (remove stray tags, tighten sections, add tests).


## 2026-02-16 — Pack AX — Seller fulfillment queue polish (open tasks panel + quick actions + consistency audit) ✅

**Completed**
- Fulfillment queue supports quick-action state transitions (pickup/delivery/shipping).
- Seller fulfillment tasks are created at payment time and auto-completed when delivered.
- Seller dashboard “open tasks” preview fixed to follow task-per-order-item model.

**Next**
- Pack AY — Buyer delivery confirmation + timeline polish (shipping/delivery UX consistency).


## 2026-02-16 — Pack AW — Ops dashboards: quick “Money Loop” KPI tiles (paid orders, fees, net, refunds) ✅

**Completed**
- Ops Dashboard now includes Money Loop KPI tiles for the last 7 days:
  - GMV
  - Marketplace fees (OrderItem ledger)
  - Seller net (OrderItem ledger)
  - Refund totals + count (RefundRequest snapshots)
- Added a small explanation note in the UI to clarify data sources.

**Next**
- Pack AX — Seller fulfillment queue polish (open tasks panel + quick actions + consistency audit).



## 2026-02-16 — Pack AV — Service search improvements (state/radius filters + query persistence) ✅

**Completed**
- Added State + Radius filters to Services browse (`/products/services/`).
- State filter matches seller `Profile.public_state` (approximate).
- Radius filter matches sellers whose `service_radius_miles >= radius` (seller travels at least X miles).
- Filter parameters persist across category sidebar clicks and pagination.
- Fixed canonical/og:url template crash by avoiding arg method calls in templates.

**Next**
- Pack AX — Seller fulfillment queue polish (open tasks panel + quick actions + consistency audit).



## 2026-02-16 — Pack AU — Seller storefront profile + public location ✅

**Completed**
- Added approximate public seller location fields on Profile: `public_city`, `public_state`.
- Added optional `service_radius_miles` (for service providers; informational in v1).
- Profile edit UI now includes storefront fields (shop name, bio, socials, quick-pay handles) + public location + service radius.
- Seller storefront and Top Sellers now display shop name (fallback username) and public location/radius when set.

**Next**
- Pack AW — Ops dashboards: quick “Money Loop” KPI tiles (paid orders, fees, net, refunds).



## 2026-02-16 — Pack AS — SEO polish (meta/OG/canonical) + footer copy ✅

**Completed**
- Canonical URLs now exclude querystrings (uses `request.path`).
- Meta description + OG/Twitter description now default from `SiteConfig` (editable).
- Default OG/Twitter image now supports an admin-configurable absolute URL via `SiteConfig` (fallback to bundled image).
- Added optional `twitter:site` tag from `SiteConfig` twitter handle.
- Tightened footer marketing copy and removed duplicate policy links from Support column.

**Next**
- Pack AT — Browse filters UX (collapsible subcategories + More + mobile filter drawer).


## 2026-02-16 — Pack AR — References pages polish + sitemap/nav consistency ✅

**Completed**
- Polished reference pages (About / Help / FAQs / Tips) with consistent headers, CTAs, and cross-links.
- Nav consistency:
  - Added **Tips** to the top-nav References dropdown.
  - Renamed “Licenses & Policies” → “Policies” for clarity.
  - Added About/Help/FAQs/Tips links to the footer (Company/Support columns).
- Confirmed sitemap already includes all reference page URLs.

**Next**
- Pack AS — SEO polish (meta descriptions/OG tags + canonical URLs) and tighten footer copy.
# Local Market NE — ROADMAP

Last updated: 2026-02-16 (America/New_York)

## Hotfixes (2026-02-16)
- ✅ Fixed ops ErrorEvent import crash by adding `ops.ErrorEvent` model + migration `ops.0002_errorevent` (admin/model/migration shipped together).

NOTE: This roadmap originated from the Home Craft 3D engine and is being adapted for LocalMarketNE.

This roadmap is a living doc: completed items stay visible, and the next
phase is always explicit.

---

## 2026-02-16 — Pack BL — V1 UX/CSS polish sweep + seller onboarding copy + sidebar JS cleanup ✅

**Completed**
- Browse pages: added sticky search/filter bar with a one-click **Clear** action (Products + Services).
- Product cards: removed inline styles, fixed badge layout, and standardized media sizing via CSS helpers.
- Sidebar scripts: removed legacy HC3 sidebar JS includes and de-duplicated category filtering + “More/Less” persistence (now handled in `partials/sidebar_store.html`).

**Next**
- Pack BM — V1 visual polish pass (dashboards + tables) + micro-interactions (loading states / toasts).


## 2026-02-16 — Pack BM — V1 micro-interactions + table/dash polish baseline ✅

**Completed**
- Added global UI helper JS (`static/js/ui.js`):
  - Disables submit buttons on submit to prevent double-submits.
  - Supports `data-disable-once` for one-time clicks.
  - Adds a lightweight primary button loading state.
- Added baseline UI polish helpers in `static/css/site.css`:
  - `.lm-table` wrapper (rounded container + sticky headers).
  - `.lm-card` helper for consistent card borders/shadows.

**Next**
- Pack BN — Apply `.lm-table`/`.lm-card` consistently across dashboards + ops tables (template sweep), plus any remaining dead-end audit fixes.




## Recently completed (2026-02-13)

## Recently completed (2026-02-14)

### Pack X — Launch hardening: reCAPTCHA v3 on public write actions
✅ Added global reCAPTCHA v3 helper (`static/js/recaptcha_v3.js`) wired from `templates/base.html`.
✅ Enforced server-side reCAPTCHA on POST for: register, reviews (create/seller/reply), product Q&A (thread/reply/report).
✅ Updated templates to include token fields and `data-recaptcha-action` attributes.

### Pack V — Legal acceptance wiring
✅ Seller onboarding now requires explicit **Seller Agreement** acceptance before starting Stripe Connect.
✅ Checkout now records acceptance of base legal docs (Terms/Privacy/Refund/Content) at purchase time.
✅ Service checkouts additionally record acceptance of the **Services & Appointments Policy** when a cart contains services.

### Store navigation UX
✅ Store sidebar category improvements for large category trees:
- Root category lists truncated (first 8 shown) with a **More** expander.
- Subcategories hidden by default and expanded per root.
- Collapsed **Filter** control above Products and Services category sections for quick client-side search.

## Recently completed (2026-02-15)

### Pack AJ — Observability: error event capture + ops triage
✅ Added DB-backed `ops.ErrorEvent` model to capture unhandled server exceptions (no external service required).
✅ Added `core.middleware.ExceptionCaptureMiddleware` to store request id, path, user, message, and compact traceback.
✅ Ops Console: **Error Events** list + detail + resolve with required notes and audit log entry.
✅ Ops Dashboard now surfaces **Open errors** count and links to triage.

## Recently completed (2026-02-09)


### Fulfillment + off-platform payment UX hardening
✅ Pack L delivered:
- ZIP-only validation for delivery/shipping selections (conservative approximation).
- Buyer can mark off-platform payment as **sent** with optional note.
- Seller can save an **internal order note** (seller-only).
- Shipping tracking (carrier + tracking #) recorded per line item when marked shipped.


### Trust & access
✅ Email verification gating across registered-only features
✅ Email → in-app notification parity (user-facing emails create Notifications)

### Marketplace mechanics
✅ Favorites & Wishlist split (single combined UX page)
✅ Free service listing cap (SiteConfig-managed) enforced server-side
✅ Seller replies to product reviews (one reply per review in v1)

### Seller listings stability
✅ Template crash fixed: no template access to private (_underscore) attributes
✅ Seller Listings publish checklist exposed as `p.publish_ok` / `p.publish_missing`

### orders metrics (bundle-level)
✅ Bundle-level orders counter: `Product.order_count`
✅ Paid + free orders increment:
  - `DigitalAsset.order_count`
  - `Product.order_count` (bundle-level)
✅ Unique orderers tracking:
  - New `ProductorderEvent` model (user + guest session)
  - Seller Listings shows **unique / total** for FILE products
✅ Seller Listings metrics polish: unique orderers excludes blank guest sessions; physical listings show NET units sold.

## Recently completed (2026-02-10)

### Seller Listings stability
✅ Fixed Seller Listings template/context mismatch (template iterates Product instances directly).
✅ service listings show bundle-level total orders via `Product.order_count`.

### Deployment readiness
✅ Added Render deployment playbook (`docs/DEPLOY_RENDER.md`).
✅ Added post-deploy verification checklist (`docs/POST_DEPLOY_CHECKLIST.md`).

---

## Phase 1 — Storefront credibility (DONE)
✅ Add-to-cart buttons on home cards with Stripe readiness gating (`p.can_buy`)
✅ Trending computation on home (manual override + computed fill)
✅ Trending score includes purchases + reviews + engagement events
✅ Rating on cards across home + browse + “more like this” using annotations
✅ Browse sort controls (New / Trending / Top Rated)
✅ Top Rated threshold with fallback + warning banner

## Phase 2 — Engagement signals v1 (DONE)
✅ `ProductEngagementEvent` (VIEW, ADD_TO_CART, CLICK)
✅ Throttled VIEW logging on product detail
✅ Best-effort ADD_TO_CART logging on cart add

## Phase 3 — Badge membership rules (DONE)
- [x] Ensure browse “🔥 Trending” badge applies only to a meaningful subset:
  - badge if in computed Top N AND `trending_score > 0` (with manual override)
- [x] Keep badge rule consistent between home + browse

## Phase 4 — Seller analytics (DONE)
- [x] Seller analytics summary page:
  - views / clicks / add-to-cart
  - net units sold
  - orders (unique / total)
- [x] Time-window filters (7/30/90 days)

## Phase 5 — Messaging & moderation polish (DONE)
- [x] Staff moderation queue for reported Q&A messages
  - reports filter (open/resolved/all)
  - actions: resolve / remove message / suspend user
- [x] Audit trail for staff actions (`core.StaffActionLog`)
- [x] Staff-only visibility aids
  - product Q&A tab open-report badge
  - per-message open-report count badges
- [x] Suspensions review + unsuspend action

## Phase 6 — Launch hardening
- [ ] Rate limiting / abuse controls review
- [ ] Observability and error reporting
- [ ] Backups and performance tuning

### Launch hardening (DONE)
- Request IDs + log context filter (rid/user/path)
- Throttle GET orders endpoints (paid + free)
- Add lightweight audit/operational log lines for moderation + orders

### Migration stability (DONE)
- Align ops/logging models to their migrations (no PK-type flips).
- If local DB migration history becomes inconsistent, recover by dropping/recreating the local DB and rerunning `migrate`.

### Next: Ops + launch readiness
- Add admin reconciliation page per-order (ledger totals vs transfers) + export.
- Expand Admin Ops with: failed emails panel, payout/backlog summary, webhook latency histogram.
- Add staff tooling for manual reprocessing of a Stripe event **only** via a guarded, audited workflow (v2).

## 2026-02-10 — Launch hardening: analytics migration
- Confirm Render environment variables: `GOOGLE_MEASUREMENT_ID` (required) and optional GA4 Data API vars (`GOOGLE_ANALYTICS_PROPERTY_ID`, `GOOGLE_ANALYTICS_CREDENTIALS_JSON` or `GOOGLE_ANALYTICS_CREDENTIALS_FILE`).
- Verify GA events are firing on production and real-time reports populate.
- Remove Plausible-specific UI remnants once GA is confirmed stable (optional cleanup).


## Completed
- Native analytics: server-side pageview capture + admin dashboard panel + retention pruning + range filters (today/7d/30d/custom).

## Next
- Add rate limiting for cart/checkout/Q&A/reviews.
- Seller payout reconciliation UI (pending vs available).
- References pages (Help/FAQ/Tips & Tricks).

- ✅ Seller payouts reconciliation page (available vs pending, pending items, ledger table)
- ✅ Abuse control: throttled review create/reply endpoints


### 2026-02-10
- [x] Admin dashboard: Google Analytics link visible (SiteConfig URL).
- [x] References: About page (static v1) + sitemap entries.
- [ ] References: polish Help/FAQ/Tips content.
- [ ] Launch hardening: reCAPTCHA v3 wiring on public write actions.


### Launch Hardening (current)

- [x] Native analytics dashboard filters (today/7d/30d/custom)
- [x] Centralized throttle policy + throttle logging to native analytics
- [x] Admin "Abuse signals" panel (24h/7d + top rules)
- [ ] Expand throttling to login/register (already present), and add per-endpoint tuning after observing real traffic
- [ ] Add reCAPTCHA v3 on public write actions (register, reviews, Q&A)


### Legal / Licensing (next)

- [x] Add versioned licensing documents (service License, Seller Agreement, Physical Policy)
- [ ] Wire Seller Agreement acceptance into seller onboarding (explicit checkbox + acceptance record)
- [ ] Wire service License acknowledgment into service checkout/orders flows where appropriate
- [ ] Add admin UI shortcut to publish/clone legal docs and preview rendering


## 2026-02-10 — Next steps
- Add seller fulfillment queue filters (Pending only toggle, search by order/product).
- Add notifications UI badge counts for open fulfillment tasks (optional).
- Add order fulfillment SLA reminders (optional scheduled email) and export packing slips (PDF).

- [x] Free service listings cap enforcement (email verification + Stripe onboarding beyond cap) (2026-02-10)
- [x] SiteConfig admin settings parity (Dashboard Admin Settings ↔ Django admin) (2026-02-10)

## Next — Seller Fulfillment UX polish
- Add bulk actions (mark all shipped / exported packing slip).
- Add buyer messaging from order detail.
- Add optional carrier presets and printable label links.

## Native analytics next steps (2026-02-11)
- Add optional bot/scanner rule tuning UI (advanced).
- Add daily rollups table for faster dashboard queries at scale (optional v2).
- Add export (CSV) for native analytics top pages + summary (optional).

## Admin settings UX (2026-02-11)
- Continue polishing Admin Settings layout (icons, spacing) as new SiteConfig fields are added.

## Settings UX (2026-02-11)
- Optional: add dynamic add/remove rows for affiliate links (JS) if 10 fixed rows becomes limiting.


## Pack K (Completed 2026-02-13)
**Focus:** Seller fulfillment statuses + off‑platform payment confirmation + sidebar polish.

**Completed**
- Seller confirms off‑platform payments (Venmo/PayPal/Zelle).
- Seller updates goods fulfillment status (pickup/delivery/shipping aware).
- Expanded fulfillment statuses and updated seller fulfillment queue tabs.
- Sidebar “More/Less” toggle + persisted state + filter wiring.

**Next**
- Pack L: delivery radius enforcement (ZIP‑only), shipped tracking UI, buyer “I sent payment” marker.

### Completed
- Pack M: Shipping notification + appointment cancellation window


## Pack O (2026-02-13)
- Completed: Seller Payments (Awaiting) queue + nav integration.
- Completed: Deposit UX polish and cleanup sweep of download remnants.
- Next: Buyer notifications for off-platform status changes; service completion lifecycle polish; delivery radius (ZIP-only) edge cases.

## Pack P (re-applied) — Fulfillment tasks + tracking cleanup (2026-02-13)
- ✅ Fulfillment tasks (`SellerFulfillmentTask`) created on PAID orders with goods.
- ✅ Seller dashboard surfaces open tasks + links to fulfillment queue.
- ✅ Shipping tracking uses `tracking_carrier` + `tracking_number`; legacy `carrier` removed via migration.
- Next: Pack Q — inventory/lead-time enforcement and improved delivery radius validation.


### Pack S (Re-applied 2026-02-13) — Service Appointments: lifecycle + deposit webhook hookup
**Completed**
- Fixed broken AppointmentRequest model property/indentation issues.
- Implemented appointment status lifecycle and timestamps.
- Added scheduling fields and auto-scheduling default behavior.
- Hooked Stripe webhook to mark deposit-paid appointments and schedule them.
- Added seller “cancel” and “mark completed” actions.
- Added appointments migrations for clean DB setup.
- Updated buyer/seller appointment templates.

**Next**
- Pack U: Service booking buyer confirmation + calendar export (ICS) + reminder notifications.

### Pack T (2026-02-13) — Rescheduling UI + appointment lifecycle notifications
**Completed**
- Added seller rescheduling UI for appointments.
- Added email + in-app notifications for appointment lifecycle events.
- Wired deposit-paid webhook to notify buyer and seller and confirm auto-scheduling.

## Pack W — Ops Console (Completed)
- [x] Add `ops` app + `/ops/` routes and ops_required gate
- [x] Ops dashboard KPI tiles + operational queues
- [x] Orders console (list/detail) and sellers console (list/detail)
- [x] Moderation queue for Q&A reports + resolve action (audited)
- [x] Refund requests queue
- [x] AuditLog model + Admin + viewer

## Next: Pack X — Financial Reconciliation + Overrides
- [ ] Stripe reconciliation drill-down per order (charge/session/transfer IDs)
- [ ] Ops override actions (force state transitions) with strict invariants + audit
- [ ] Seller risk controls (freeze seller, freeze payouts, internal notes)


### Pack W.1 — Real-store ops accounts (Admin + Ops)
✅ Added `/staff/` Admin Console and `staff_admin` group for day-to-day work.
✅ Kept `/ops/` Ops Console for elevated support.
✅ Added bootstrap command for creating/updating both accounts via env.

## Next up
- Define the exact day-to-day permissions and remove any admin-only actions from staff console where needed.
- Add staff-level order actions (resend emails, mark shipped, respond to support tickets) with audit entries.
- Expand Ops: financial reconciliation view per order (Stripe IDs, transfer states) and seller freeze/payout holds.


## 2026-02-14 — Stability Fix: orders imports/event enums
- Completed: repair missing email helper imports and event enum mismatch to prevent runtime errors.
- Next: continue roadmap from current pack sequence (Admin/Ops console hardening, moderation queues, analytics).


### 2026-02-14 — Hotfix
- Admin Console Q&A Reports queue fixed to reference `ProductQuestionReport` and correct resolve field updates.


## Pack Y — Policy & Safety (Complete) (2026-02-14)
- ✅ Category policy flags (prohibited, 18+)
- ✅ Registration age confirmation
- ✅ Checkout age enforcement (auth + guest)
- ✅ Product listing validation blocks prohibited categories

## Pack Z — Prohibited Items Enforcement + Staff Listing Moderation (Complete) (2026-02-14)
- ✅ Block prohibited categories at cart + order creation + checkout start
- ✅ Seed prohibited categories (Weapons, Alcohol)
- ✅ Product detail + listing cards show Prohibited/18+ badges
- ✅ Staff Console: Listings page + Edit Listing (re-categorize/deactivate) with audit log

## Launch Readiness Packs (Post-Z)

### Pack AA — Smoke Test Hardening (2026-02-15) ✅
- Email verification resend alias endpoint
- Ops health surface
- Public health/version endpoints

### Pack AB — Monitoring + Audit Completeness (2026-02-15) ✅
- Fixed Admin Console listing policy audit call + required reason
- Ops audit log: filtering (q/action/verb/actor/date range) and CSV export
- Improved audit log UI with filter bar and export link

### Next: Pack AC — Backups + Recovery Runbook ✅
- Document DB backup/restore steps (Render/managed PG)
- Document media storage backup strategy (S3 lifecycle/versioning)
- Add ops runbook page in Ops Console (links + checklists)

- Add audit export/filter improvements
- Add mismatch detectors (orders/snapshots) and ops runbook hooks


### Next packs (post-AC)
- Pack AD — Performance + Abuse Controls (rate limits, query optimizations, caching of heavy aggregates).
- Pack AF — Financial Reconciliation (mismatch detector, stripe IDs visibility, transfer status).
- Pack AG — Full User Manual PDF + Ops Runbook PDF (end-to-end instructions + role matrix).

### Pack AD — Performance + Abuse Controls (2026-02-15) ✅
- ✅ Added pagination + input clamping to public browse/storefront pages.
- ✅ Added short-lived anonymous page caching (60s) for heavy browse surfaces.
- ✅ Updated templates with pagination UI and storefront filters.

### Next: Pack AE — Search + Discovery Polish
- [ ] Add unified search bar behavior across home/products/services/storefront.
- [ ] Add sort controls (new/top/trending/nearest) with safe allowlist.
- [ ] Add distance/radius filtering for storefront discovery (zip-based) per LocalMarketNE spec.

### Next: Pack AF — Financial Reconciliation
- [ ] Ops reconciliation per order: charge/session/transfer IDs + mismatch detector.
- [ ] Ops risk controls: freeze seller / freeze payouts with audit.


## Pack AE — Store Ops Controls — 2026-02-15
**Completed**
- Ops-grade maintenance mode + announcement controls via SiteConfig.
- Public maintenance page + middleware gating.
- Admin UI updated to manage the new fields.

**Next**
- Pack AF: Financial reconciliation + mismatch detection (Stripe IDs, snapshot validation, investigation tooling).

## 2026-02-15 - Pack AG Complete
- Pack AG delivered the full User and Ops Manual (PDF + Markdown).
- Next recommended pack: **Pack AH - In-app Help Center + Docs Links**
  - Add /help/ area with links to Terms/Privacy/FAQ and the User Manual
  - Add navbar/footer links for logged-in users (Staff/Ops) and public users
- After Pack AH: **Pack AI - Full Launch QA Script Execution**
  - Execute the AA smoke-test script end-to-end and patch any dead ends; then update USER_MANUAL and ROADMAP accordingly.

### 2026-02-15 Hotfix
- Admin system check fix (core.admin.SiteConfigAdmin fieldsets duplicates)


## Next packs after AH

### Pack AI — End-to-end checkout + payout verification
- Add a documented smoke-test runbook (dev + prod): cart → checkout → webhook → transfers → seller fulfillment.
- Add a minimal management command to reconcile: order totals vs Stripe session vs transfers.
- Add admin links: Order admin → StripeWebhookEvent list filtered by `stripe_session_id`.

### Pack AJ — Seller storefront polish & discovery
- Storefront filtering refinements (in-store category filters, seller distance display, service radius UX).
- Public storefront about/info blocks + location display (non-exact).

### Pack AK — Ops console hardening
- Operational dashboards: failed webhooks, unpaid awaiting-payment orders, payout exceptions.
- Staff-only tools to reprocess webhook events and re-attempt transfers (idempotent).

## 2026-02-15 — Pack AI — Launch Check (Ops + CLI)

**Completed**
- Added `/ops/launch-check/` with a conservative “go-live” checklist.
- Added management command `python manage.py launch_check` (and `--json`) for automation/CI.
- Checks cover settings/integrations/invariants: DB, cache, email, Stripe keys, reCAPTCHA, storage posture, SiteConfig presence, HSTS posture.

**Next**
- Pack AJ: Seller storefront polish & discovery improvements (store about/location blocks, in-store filters, better seller cards).


## 2026-02-16 — Pack AK — Funnel Metrics (Native Analytics) ✅

**Completed**
- Native funnel event types added to `AnalyticsEvent`: `ADD_TO_CART`, `CHECKOUT_STARTED`, `ORDER_PAID`.
- Events are logged at real conversion points (cart add, checkout start, Stripe webhook paid).
- Ops Console page added: `/ops/funnel/` with counts + conversion rates over last N days (`?days=30`).
- Ops nav updated with **Funnel** link.

**Next**
- Pack AL — Ops Console hardening (webhook reprocess tools, transfer retry tooling) + investigation aids.
- Pack AM — Funnel enhancements: unique-session funnel, % formatting, environment/host breakouts.


## 2026-02-16 — Pack AL — Ops Console hardening (Webhooks + Transfer Retry) ✅

**Completed**
- Ops Console Webhooks page: `/ops/webhooks/` with investigation filters (status, type, session_id, order_id, days).
- Webhook detail page with deliveries + raw event JSON: `/ops/webhooks/<id>/`.
- Staff-only action: **Reprocess** a webhook event (idempotent), creating a new delivery attempt row and updating webhook status.
- Ops Order detail action: **Retry transfers** for PAID Stripe orders (idempotent via Stripe Transfer idempotency keys).
- Ops nav updated with **Webhooks** link; Order detail shows quick link to filtered webhooks by Stripe session id.

**Next**
- Pack AN — Seller payout reconciliation UI (per seller: pending payouts, transfer history, mismatch flags).


## 2026-02-16 — Pack AM — Funnel enhancements (Unique sessions + % formatting + Host/Env breakouts) ✅

**Completed**
- Enhanced `/ops/funnel/` to include a **unique-session** funnel based on `AnalyticsEvent.session_id` (first-party session cookie).
- Added human-friendly **percent formatting** for conversion rates (event-based + session-based).
- Added **host + environment breakouts** (unique sessions) to debug environment drift and gaps quickly.

**Next**
- Pack AN — Seller payout reconciliation UI (per seller: pending payouts, transfer history, mismatch flags).


## 2026-02-16 — Pack AN — Seller payout reconciliation UI ✅

**Completed**
- Added structured metadata to `orders.OrderEvent` (`meta` JSONField) to enable seller-scoped payout reconciliation.
- Stripe Connect transfer creation now records `TRANSFER_CREATED` events with metadata: `seller_id`, `transfer_id`, `amount_cents`, `stripe_account_id`.
- Seller dashboard payouts page now includes:
  - Recent transfer history
  - Payout mismatch/delay flags (mismatch, delayed, legacy-unknown)
- Ops seller detail page now includes:
  - Seller ledger balance + pending pipeline
  - Pending payout items
  - Recent transfer events
  - Mismatch flags + recent ledger entries

**Next**
- Pack AO — Ops “Failed Emails” panel + resend tooling (visibility into email delivery problems).


## 2026-02-16 — Pack AO — Ops “Failed Emails” panel + resend tooling ✅

**Completed**
- Added `notifications.EmailDeliveryAttempt` to track outbound email send attempts linked to `Notification`.
- Notifications send path now records an attempt for every email send (sent/failed) and captures failure errors without losing the in-app notification audit trail.
- New Ops page: `/ops/emails/failed/` with filters (days/kind/search) and pagination.
- New Ops detail page: `/ops/emails/failed/<id>/` showing notification context, error, and recent attempts.
- Added Ops action: **Resend email** (POST) which uses stored rendered email bodies and records a new attempt.

**Next**
- Pack AP — Refund accounting hardening + transfer reversal controls (fees are non-refundable; seller-triggered refunds).


## 2026-02-16 — Pack AP — Refund accounting hardening + transfer reversal controls ✅

**Completed**
- Fixed refunds service/view contract mismatches to prevent runtime errors:
  - `create_refund_request()` now accepts optional `token`.
  - `seller_decide()` now matches views (`actor_user` param).
- Added transfer reversal tracking fields on `refunds.RefundRequest`:
  - `transfer_reversal_id`, `transfer_reversal_amount_cents`, `transfer_reversed_at`.
- Implemented best-effort Stripe **Transfer Reversal** after successful Stripe refunds:
  - Reverses ONLY seller net for the refunded line item (`OrderItem.seller_net_cents`).
  - Platform fee remains non-refundable.
  - Records `orders.OrderEvent` type `TRANSFER_REVERSED` with structured metadata.
  - If no transfer is found or reversal fails, refund still completes and a WARNING/attempt record is created for ops.
- Added migration `refunds.0002_refundrequest_transfer_reversal`.

**Next**
- Pack AQ — Throttle/rate-limit tuning for cart/checkout/refunds after observing real traffic.


## 2026-02-16 — Hotfix — Services browse template crash ✅

**Completed**
- Fixed `/products/services/` crashing when `q`/`category` are absent by removing `request.GET.<key>` template lookups.
- Standardized the services browse template to rely on view-provided context vars (`q`, `category`) for form values and pagination URLs.

**Next**
- Pack AQ — Throttle/rate-limit tuning for cart/checkout/refunds after observing real traffic.


## 2026-02-16 — Pack AQ — Throttle/rate-limit tuning for cart/checkout/refunds ✅

**Completed**
- Tuned centralized throttle limits (cart/checkout/refunds) to be more conservative at launch.
- Fixed checkout throttle placement:
  - `checkout_start` is POST-only and protected by throttle + reCAPTCHA.
  - `order_set_fulfillment` is POST-only and uses its own throttle rule.

**Next**
- Pack AR — References pages polish (Help / FAQ / Tips) + sitemap/nav consistency.


## 2026-02-16 — Pack BA — Admin Ops webhook schema alignment + crash fix ✅

**Completed**
- Fixed `/dashboard/admin/ops/` crash caused by stale field names (`received_at` / `event_type` / `request_id`) that no longer exist on `orders.StripeWebhookDelivery`.
- Admin ops now uses:
  - `StripeWebhookDelivery.delivered_at` for time filtering/ordering
  - `StripeWebhookEvent.event_type` for type display
  - `StripeWebhookDelivery.stripe_session_id` for request/session context
- Updated supporting docs to reflect the current schema and avoid reintroducing the mismatch.

**Next**
- Pack BB — Ops: webhook delivery drill-down links + "reprocess" button on admin ops error table.


## 2026-02-16 — Pack BB — Admin Ops: webhook drill-down + reprocess from error table ✅

**Completed**
- Admin Ops webhook error rows now link directly to the Ops Webhook Event detail page.
- Added an idempotent **Reprocess** button in the Admin Ops webhook error table that triggers Ops webhook reprocessing.
- Admin Ops webhook queryset now uses `select_related("webhook_event", "order")` to keep rendering efficient.

**Next**
- Pack BC — Release candidate sweep: dead-end audit on dashboards/ops links + tighten launch-check copy.


## 2026-02-16 — Pack BC — Release candidate sweep: dead-end audit + launch-check copy tighten-up ✅

**Completed**
- Added a conservative "dead-end" guardrail to Launch Check: a URL wiring check that verifies core named routes resolve (dashboards + ops + storefront entry points).
- Tightened Ops Launch Check copy and added prominent links to Ops Health + Ops Runbook.

**Next**
- Pack BD — Release candidate sweep: reconciliation/export polish + final wording pass (TBD).

## 2026-02-16 — Pack BN — Apply `.lm-table`/`.lm-card` across ops + dashboards ✅

**Completed**
- Wrapped Bootstrap tables (`class="table"`) in Ops, Staff Console, and Appointments templates with `<div class="lm-table">`.
- Added `lm-card` helper class to Bootstrap cards for consistent borders/shadows.

**Next**
- Pack BO — Dead-end audit sweep (empty-states, missing links, permission/404 guardrails) + remaining UX paper-cuts.

## 2026-02-16 — Pack BO — Dead-end audit sweep ✅

### Done
- Removed the last obvious “dead end” link in `coming_soon.html` by adding a real waitlist flow.
- Added Waitlist capture (model, admin, view, route, template).
- Introduced a reusable empty-state partial and upgraded key user-facing empty states with CTAs.
- Fixed `core/views.py` duplicate `healthz()` override.

## 2026-02-16 — Pack BP — Waitlist hardening (throttle + email settings) ✅

### Done
- Added SiteConfig-managed waitlist toggles and email templates (confirmation + admin notify).
- Added `WAITLIST_SIGNUP` throttle rule and applied it to `/waitlist/`.
- Waitlist page now renders a disabled state cleanly when turned off.

## 2026-02-16 — Pack BQ — Smoke check fixes (legal namespace) ✅

### Done
- Updated the smoke-check critical routes to use the dedicated `legal:` namespace (`legal:privacy`, `legal:terms`) and added `legal:index`.

## 2026-02-16 — Pack BR — Canonical reference routes ✅

### Done
- Promoted reference pages to canonical short routes: `/about/`, `/help/`, `/faqs/`, `/tips/`.
- Kept legacy `/references/*` routes as permanent redirects (301) for backwards compatibility.
- Updated sitemap to list the canonical routes.

## 2026-02-16 — Pack BS — Empty states + Support pathway consistency ✅

### Done
- Updated `templates/partials/empty_state.html` to support primary/secondary CTAs and optional Support links.
- Added canonical `/contact/` page with a simple support form + mailto fallback.
- Added `SiteConfig.support_email` (admin + dashboard-managed) and used it on Contact.
- Swept seller dashboards, appointment lists, and ops queues to use the empty-state component with clear exits.
- Updated footer + navbar to include Contact and ensure Help/FAQs are easy to reach.

### Next (Pack BT)
- Permissions + 404/500 UX polish: ensure blocked pages explain why and provide next actions.
- Consistency sweep: ensure all “support links” point to canonical routes and no legacy `/references/*` appear in UI.

- ✅ Pack BU: Contact form inbox + SiteConfig controls
- ✅ Pack BV: Staff Console Support Inbox (list + detail + resolve/reopen)
- ✅ Pack BW: Support ops hardening (response templates + internal notes + SLA tags)
- ✅ Pack BX: Outbound support email logging
- ✅ Pack BY: RC Money Loop verification (launch check + `money_loop_check` command)
- ⏭️ Pack BZ: Email deliverability hardening (provider checklist + template audit + DNS guidance)


### Hotfixes
- 2026-02-17: Admin dashboard crash fix — `ProductEngagementEvent.Kind` + `kind` field.

- Pack CA (Sweep): Fixed Orders admin aggregation + appointment deposit order legacy field usage (snapshot-safe).

## 2026-02-17 — Pack CB — Seller onboarding checklist ✅

### Done
- Added seller onboarding checklist (until complete) to Seller Dashboard and Seller Listings.
- Steps cover: email verification, 18+ confirmation, prohibited-items policy, Stripe Connect payouts, shop name, public location, first listing.

### Next
- Pack CA (Release): Finish release runbook + RC checklist (deploy, rc_check, rollback).
- Pack CC: Listing creation UX (3-step wizard) + consumer browse polish (sticky filters, fulfillment badges).

### ✅ Pack CJ — RC URL reverse audit
- Add `url_reverse_audit` command and include it in `rc_check`.
- Goal: prevent runtime NoReverseMatch due to stale template route names.

## 2026-02-20 — Pack CX — Environment banner + Stripe test-mode safety ✅

**Completed**
- Added SiteConfig environment banner controls (enable + text) managed via Dashboard → Admin Settings.
- Added automatic production warning banner if Stripe is configured with test keys (`sk_test_`).

**Next**
- Production deploy on Render + first-live validation (docs/GO_LIVE_KIT.md).


## 2026-03-09 - Pack DA - UI Consistency + Upgrade Execution Plan

### Goal
Move from "working and branded" to "production-consistent UX" with a tracked, phased execution plan.

### Priority checklist
- [ ] Design system pass
  - [ ] Standardize spacing, heading scale, card spacing, and form rhythm.
  - [ ] Replace remaining inline template styling with reusable classes.
- [ ] Mobile UX pass
  - [ ] Checkout, listing create/edit, and dashboards reviewed at small breakpoints.
  - [ ] Reduce scroll depth and improve action placement for thumb reach.
- [ ] State consistency
  - [ ] Standardize empty/loading/error states across buyer, seller, and ops pages.
  - [ ] Ensure every state includes clear next actions.
- [ ] Seller conversion UX
  - [ ] Improve onboarding progress visibility.
  - [ ] Add "next best action" cards on seller surfaces.
- [ ] Trust and policy visibility
  - [ ] Strengthen checkout trust messaging and policy surfacing.
  - [ ] Keep support/refund paths obvious through checkout and post-purchase views.
- [ ] Performance pass
  - [ ] Image optimization and lazy loading audit.
  - [ ] Reduce duplicate CSS/JS/template patterns on high-traffic pages.
- [ ] Accessibility pass
  - [ ] Contrast + focus + keyboard navigation checks in light and dark themes.
  - [ ] Form validation cues and screen-reader label consistency.
- [ ] Release hardening
  - [ ] Add visual regression checklist for top user flows.
  - [ ] Keep runtime/dependency policy pinned and review quarterly.

### Execution order
1. Auth + onboarding pages (high-traffic entry flow)
2. Checkout + cart + listing detail
3. Seller dashboard + listing management
4. Admin/Ops surfaces

### Current status
- Completed: Theme alignment and button consistency sweep across major buyer/seller surfaces.
- Completed: Seller listing management consistency pass (dashboard + create/edit/images/assets/delete).
- Completed: Checkout/cart/product detail consistency pass (button variants, spacing, text rendering helpers).
- In progress: Pack DA execution order step 4 (Admin/Ops surface consistency + final cross-page QA sweep).

### Immediate next (Pack DA)
- Run focused QA on top user flows in both light/dark and mobile breakpoints:
  - Home -> Product detail -> Cart -> Checkout
  - Seller dashboard -> Listings CRUD -> Storefront preview
  - Admin dashboard -> Ops pages (tables/filters/buttons/states)
- Close remaining visual/copy regressions from prior encoding cleanup on high-traffic templates.
- Add a compact visual regression checklist to lock the current UI baseline before commit/deploy.


## 2026-03-09 - Pack DB - Native analytics inflation hardening

### Completed
- Hardened analytics collection to reduce inflated visitor counts:
  - Ignore `HEAD` requests for pageview tracking.
  - Treat empty user-agent requests as bot/automation traffic.
  - Expanded bot/monitor signatures (`uptimerobot`, `pingdom`, `python-requests`, `curl`, etc.).
- Fixed cookie-less visitor inflation:
  - If `hc_vid` is missing, visitor id now resolves to a stable value (authenticated user id or derived anonymous hash) instead of random UUID churn.
- Added safer admin analytics scoping:
  - `dashboards.analytics` now defaults to canonical host from `SITE_BASE_URL` when `analytics_primary_host` is not explicitly set.
- Added one-time analytics cleanup tooling:
  - New command: `python manage.py cleanup_analytics_noise`
  - Supports `--dry-run`, `--days N`, and `--all-time`.

### Next
- Run cleanup in production with preview first:
  - `python manage.py cleanup_analytics_noise --days 30 --dry-run`
  - `python manage.py cleanup_analytics_noise --days 30`
- Observe metrics for 24-48 hours and tune if needed:
  - `ANALYTICS_THROTTLE_SECONDS`
  - SiteConfig `analytics_primary_host` and `analytics_primary_environment`


