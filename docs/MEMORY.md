## 2026-02-18 - Pack CM - Consumer browse card enhancements ✅

**Why**
- Improve buyer decision-making at browse-time with clearer location and fulfillment signals.

**What changed**
- Updated `products/templates/products/_product_card.html`:
  - Show seller public location (city/state) when provided.
  - Show product fulfillment badges (Pickup / Delivery / Shipping).
  - Show service radius badge for service listings when seller has a radius set.

**Acceptance checks**
- Browse Products: cards show Pickup/Delivery/Shipping badges when enabled.
- Browse Services: cards show “Service radius: X mi” when seller profile has a radius set.
- Cards show seller city/state when provided in seller profile.


## 2026-02-18 - Pack CL - RC checklist runner (rc_report)

**Why**
- Provide a single command to summarize RC readiness and prevent last-minute surprises.

**What changed**
- Added `core/management/commands/rc_report.py` which runs:
  - `rc_check --checks --db --quiet`
  - `url_reverse_audit --json`
  - `template_deadend_audit --json`
  - `money_loop_check --json`
- Supports `--json` and `--strict` for CI/automation.

**Acceptance checks**
- `python manage.py rc_report`
- `python manage.py rc_report --json`
- `python manage.py rc_report --strict` exits non-zero if any component fails.


## 2026-02-18 - Pack CI: RC Hardening (Dead-end audit resilience)

## 2026-02-18 - Pack CK - RC UI pass (tooltips + mobile navbar spacing) ✅

- Initialized Bootstrap tooltips globally (safe, optional) via `static/js/ui.js`.
- Added lightweight first-run tip tooltips on Consumer Dashboard and Seller Dashboard headers.
- Refactored navbar to use `.lm-navbar` / `.lm-logo` classes and added responsive spacing rules in `static/css/site.css`.

**Acceptance checks**
- Mobile (<576px): navbar height reduced, logo scales down, nav link spacing feels tighter without crowding.
- Hover/tap the info icon on dashboards shows the tooltip (no JS errors if Bootstrap Tooltip unavailable).


**Fix/Upgrade:** Prevented template-level hard crashes and reduced false positives in strict dead-end audits.

### What changed
- Updated `templates/partials/empty_state.html` to use safe URL reversing (`{% url name as var %}`) so missing/renamed routes no longer crash pages.
- Replaced a disabled `<a href="#">` CTA on the seller listings page with a non-link `<span>` (avoids dead-end and audit noise).
- Added `data-lm-ignore-deadend` to navbar dropdown toggles for strict dead-end audit compatibility.

### Acceptance checks
- Visit `/products/seller/` with listings disabled - page renders, no dead-end audit noise.
- Any empty state using `action_route` or `secondary_route` will not raise `NoReverseMatch` if the route is missing.

---

## 2026-02-17 - Pack CC: Seller Listing Form Kind Sections + Error Summary

**Fix/Upgrade:** Seller listing create/edit form is now *kind-aware* (Product vs Service) and no longer shows irrelevant sections.

### What changed
- Added `lm-kind-section` wrappers in seller listing form and a new JS controller to toggle visibility and disable irrelevant inputs.
- Category label updates dynamically:
  - Product → “Product category”
  - Service → “Service category”
- Added an error summary block that lists field errors and auto-scrolls into view.

### Files touched
- `products/templates/products/seller/product_form.html`
- `products/static/products/seller/kind_sections.js` (new)
- `static/css/site.css`

### Acceptance checks
- Selecting “Product” hides Service settings; selecting “Service” hides Product/Fulfillment settings.
- Category label updates based on kind.
- If validation fails, user is scrolled to error summary and field errors are listed.


## 2026-02-17 - Pack CD: Category Sidebar Filter/Search

**Fix/Upgrade:** Added a quick category filter/search UI on browse pages (desktop sidebar + mobile offcanvas).

### What changed
- Added a small search button next to the “Categories” title that toggles a filter input.
- Implemented lightweight client-side filtering of category and subcategory links.

### Files touched
- `products/templates/products/_category_sidebar.html`
- `static/js/category_filter.js` (new)
- `templates/base.html`

### Acceptance checks
- Products + Services browse pages: open Filters and type in the category filter.
- Category/subcategory links filter in-place while typing; clearing restores all.


## 2026-02-17 - Pack CA Hotfix: Dashboard Settings Reliability Sweep

**Problem:** Dashboard Admin Settings changes (marketplace fee, promo/home banners, etc.) were not reliably persisting/reflecting, forcing edits in Django admin.

**Root cause:** `dashboards/forms.py` had critical indentation/structure issues: `__init__`, CSV parsing, affiliate row handling, and `save()` override were defined at module level (not on `SiteConfigForm`), so the settings UI did not consistently map UI fields → model fields.

**Fixes:**
- Rebuilt `SiteConfigForm` as a correct, fully functional `ModelForm` with:
  - proper `__init__` wiring
  - CSV → `allowed_shipping_countries` persistence
  - affiliate link row persistence
  - deterministic housekeeping for banner fields
- Added `post_save` signal on `SiteConfig` to **always** invalidate the SiteConfig cache.

**Acceptance checks:**
- Change `marketplace_sales_percent` in Dashboard Settings → Save → reload page → value persists.
- Toggle promo/home banner → Save → reload page → enabled state + text persists (text clears when disabled by design).
- Update shipping countries CSV → Save → reload page → persists.

---

# Local Market NE - MEMORY

## 2026-02-17 - Hotfix - Seller/Orders admin queue crashes (reverse + requires_shipping filters) ✅

- Fixed seller listings empty-state CTA:
  - Corrected route from `products:seller_product_create` → `products:seller_create`.
- Fixed seller fulfillment queue crash:
  - Removed DB filtering on `requires_shipping` (property) and replaced with DB-safe filters:
    - `is_service=False`, `is_tip=False`, and `fulfillment_mode_snapshot != digital`.
- Fixed Orders admin fulfillment mix filter:
  - Replaced `items__requires_shipping=True` with `items__fulfillment_mode_snapshot="shipping"`.
  - Corrected “Digital-only” label and filter to match `fulfillment_mode_snapshot="digital"`.

Acceptance checks:
- Seller listings page loads at `/products/seller/` with the “Create a listing” CTA.
- Seller orders page loads at `/orders/seller/orders/` and shows physical items (pickup/delivery/shipping) excluding services/tips.
- Admin orders list filter “Has shippable items” works without FieldError.

## 2026-02-16 - Pack BL - V1 UX/CSS polish sweep + sidebar cleanup ✅

- Browse UX polish:
  - Added sticky search/filter bar on Products + Services browse pages.
  - Added one-click **Clear** action when any filters are active.
- Product card polish:
  - Standardized card media sizing via CSS helpers (removed inline styles).
  - Fixed badge layout + tightened title/description behavior (clamped descriptions).
- Sidebar cleanup:
  - Removed legacy HC3 sidebar JS includes from `base.html` (scripts were duplicating behavior).
  - De-duplicated sidebar store scripts and ensured “More/Less” label persists correctly.

Acceptance checks:
- Products browse: searching shows **Clear**; clicking Clear resets back to unfiltered browse.
- Services browse: state/radius filters show **Clear**; clicking Clear resets back to defaults.
- Sidebar: category filter inputs still work; “More” toggles show correct label and persist open/closed across reloads.


## 2026-02-16 - Pack BM - V1 micro-interactions + table/dash polish baseline ✅

- Added global UI helper JS:
  - Prevents accidental double-submits (disables submit buttons on form submit).
  - Optional `data-disable-once` click guard for one-time actions.
  - Adds a lightweight loading state on primary submit buttons (spinner + “Working…”).
- Added baseline "product-grade" table/card styling helpers:
  - `.lm-table` wrapper for rounded, sticky-header tables.
  - `.lm-card` helper for consistent card border/shadow.

Acceptance checks:
- Any form submit disables submit buttons (no double-charge / double-post UX).
- Tables wrapped in `.lm-table` have sticky headers and rounded container.


## 2026-02-16 - Pack BF - Crawl protection (robots + noindex middleware) ✅

- Hardened crawl/index protections for private areas:
  - `robots.txt` now disallows `/admin/`, `/ops/`, `/staff/`, `/dashboard/`, and `/accounts/`.
  - Added `RobotsNoIndexMiddleware` to emit `X-Robots-Tag: noindex, nofollow` on HTML responses under those paths.

Acceptance checks:
- Visiting `/robots.txt` shows Disallow lines for admin/ops/staff/dashboard/accounts.
- Any HTML page under `/dashboard/` or `/ops/` includes response header `X-Robots-Tag: noindex, nofollow`.


## 2026-02-16 - Pack BG - End-to-end smoke test command ✅

- Added management command: `python manage.py smoke_check`
- Validates:
  - Critical named routes reverse successfully (route wiring)
  - Key templates compile (catches TemplateSyntaxError / missing templates)

Acceptance checks:
- Run: `python manage.py smoke_check` → prints `Smoke check OK` and exits 0.
- Introduce a deliberate broken named route or template syntax error → prints failures and exits 2.


## 2026-02-16 - Pack BH - RC smoke check improvements (system checks + DB ping) ✅

- Enhanced `python manage.py smoke_check` with optional flags:
  - `--checks` runs Django system checks.
  - `--db` runs a tiny ORM “DB ping” (core/products/orders) to confirm migrations/tables exist.

Acceptance checks:
- `python manage.py smoke_check --checks` → exits 0 on a healthy codebase.
- `python manage.py smoke_check --db` → exits 0 after migrations; fails with a clear message if tables/migrations are missing.


## 2026-02-16 - Pack BI - Public health endpoint + smoke check wiring ✅

- Added a **public** health endpoint for hosting providers and uptime checks:
  - `GET /healthz/` returns JSON `{status: "ok", ...}` and is intentionally lightweight.
- Wired `healthz` into `python manage.py smoke_check` critical route reversals so broken URL wiring fails early.

Acceptance checks:
- Visiting `/healthz/` returns HTTP 200 JSON with `status=ok`.
- `python manage.py smoke_check` still passes (and would fail if `/healthz/` wiring is removed).

## 2026-02-16 - Pack BE - Settings sanity checks + launch check copy polish ✅

- Launch Check now includes production-grade **security posture** checks:
  - `SECURE_SSL_REDIRECT`, secure cookies, proxy SSL header, and a prod email-backend sanity check.
- In DEBUG/local dev, Launch Check warns if `SESSION_COOKIE_DOMAIN` / `CSRF_COOKIE_DOMAIN` are set (common localhost-breaker).
- Ops Launch Check page copy now clarifies dev vs prod expectations.

Acceptance checks:
- `/ops/launch-check/` renders and includes the new security/cookie-domain checks.
- In production settings (DEBUG=False) Launch Check fails if SSL redirect / secure cookies are not enabled.

## 2026-02-16 - Pack BD - Reconciliation CSV export polish ✅

- Ops Reconciliation pages now support CSV export via `?format=csv` (capped).
- Added Export CSV buttons to reconciliation list + mismatches pages.


## 2026-02-16 - Pack BB - Admin Ops: webhook drill-down + reprocess from error table ✅

- Admin Ops (`/dashboard/admin/ops/`) Stripe webhook error table now includes:
  - **Drill-down links** to the Ops Webhook Event detail page.
  - A one-click **Reprocess** button (idempotent) that triggers Ops webhook reprocessing.
- Admin Ops webhook queryset now uses `select_related("webhook_event", "order")` to avoid N+1 queries when rendering event type + links.

Acceptance checks:
- `/dashboard/admin/ops/` loads and webhook error rows link to the corresponding Ops webhook detail page.
- Clicking **Reprocess** shows a success/error toast and returns to the webhook detail page.


## 2026-02-16 - Pack AZ - Order detail cleanup + template integrity pass ✅

- Added a template compilation test (`core/tests.py`) that compiles key templates to catch `TemplateSyntaxError` regressions quickly.
- Included core flows in the compilation list (base, dashboards, products, orders, ops).
- Hotfix: Seller dashboard no longer annotates `line_total_cents` (annotation name conflicted with the `OrderItem.line_total_cents` field). It now relies on the stored field.

Acceptance checks:
- `python manage.py test core` passes and catches syntax errors if any key template is broken.
- `/dashboard/seller/` loads without a `ValueError` (annotation conflict).


## 2026-02-16 - Pack AY - Buyer delivery confirmation + timeline polish ✅

- Added buyer confirmation endpoint for physical items:
  - Shipping: buyer can confirm after seller marks **SHIPPED**.
  - Pickup/Delivery: buyer can confirm after seller marks **READY**.
- Guest orders are supported: token accepted on POST (`t` hidden input) and via `?t=`.
- Order detail now shows a second timeline card for **pickup/delivery** items.
- Added throttling rules:
  - `orders:buyer_confirm` (buyer confirm received)
  - `orders:offplatform_sent` (buyer marks off-platform payment sent)
- Fixed `buyer_mark_offplatform_sent` access by removing incorrect seller-only decorators; access is now enforced inside the view (buyer or guest token).

Acceptance checks:
- On a paid order with pickup/delivery items: seller marks READY → buyer can confirm completed.
- On a paid order with shipping items: seller marks SHIPPED → buyer can confirm delivered.
- Guest order confirm works using the same order link token.


## 2026-02-16 - Pack AX - Seller fulfillment queue polish + task lifecycle sync ✅

- Fulfillment queue (`/orders/seller/orders/`) now supports inline **quick actions** by fulfillment method:
  - Pickup: Pending → Ready → Picked up
  - Delivery: Pending → Out for delivery → Delivered
  - Shipping: Pending → Shipped (optional tracking) → Delivered
- Shipping quick-action includes optional carrier + tracking number. Buyer is emailed when an item is marked shipped (existing behavior).
- Fixed Seller dashboard fulfillment preview to follow the actual data model (tasks are per `OrderItem`).
- Removed stale/irrelevant “Grant free orders” block + JS from the Seller dashboard template.
- Ensured fulfillment tasks are created and completed correctly:
  - `Order.mark_paid()` now creates `SellerFulfillmentTask` rows (idempotent).
  - Seller status updates refresh tasks to mark them done when delivered/canceled.

Acceptance checks:
- Place an order → pay it → seller sees open fulfillment tasks.
- Seller uses quick actions → statuses advance correctly for pickup/delivery/shipping.
- Shipping “Save + ship” stores tracking (when provided) and triggers shipped email.
- After an item is delivered, the corresponding fulfillment task disappears from open tasks.


## 2026-02-16 - Pack AW - Ops Dashboard “Money Loop” KPI tiles ✅

- Ops Dashboard now includes a dedicated **Money Loop** KPI card (last 7 days):
  - GMV (7d)
  - Marketplace fees (7d) from `OrderItem.marketplace_fee_cents`
  - Seller net (7d) from `OrderItem.seller_net_cents`
  - Refunds (7d) from `RefundRequest.total_refund_cents_snapshot` where status=REFUNDED
- These KPIs are intended for quick ops verification of the purchase → fee → payout → refund loop.

Acceptance checks:
- `/ops/` loads and shows Money Loop KPIs.
- Fees + seller net are non-zero after at least one paid order with ledger values.
- Refund totals increment after a successful refund.


## 2026-02-16 - Hotfix: Seller dashboard fulfillment task field mismatch ✅

- Fixed `dashboards.views.seller_dashboard` crash caused by filtering `SellerFulfillmentTask` using a non-existent field `is_completed`.
- Correct field is `is_done`; seller dashboard now filters open tasks using `is_done=False`.


## 2026-02-16 - Pack AU - Seller storefront profile + public location ✅

- Added Profile fields for approximate public location: `public_city`, `public_state`.
- Added optional `service_radius_miles` for service providers (informational in v1).
- Expanded Profile edit UI to cover storefront fields (shop name, bio, socials, quick-pay handles) plus public location/radius.
- Seller storefront + Top Sellers now display shop name (fallback username) and public location/radius when set.

Acceptance checks:
- Profile page saves without errors for sellers and consumers.
- Seller storefront displays location/radius only when provided.
- Top Sellers list displays location when provided.



## 2026-02-16 - Pack AT - Browse filters UX (collapsible subcategories + More + mobile filter drawer) ✅

- Replaced category dropdowns on Products and Services browse pages with a sidebar filter UX.
- Categories now render as an accordion: parent categories with expandable subcategories.
- Added a **More** button after the first 8 categories (desktop + mobile).
- Added a mobile **Filters** offcanvas drawer (Bootstrap) for category browsing.
- Removed all `request.GET.<key>` lookups in these templates to prevent `VariableDoesNotExist` when query params are missing.

Acceptance checks:
- `/products/` loads with no querystring.
- `/products/services/` loads with no querystring.
- Category and subcategory clicks preserve `q` when present.
- Pagination preserves `q` and `category`.


## 2026-02-16 - Pack AS (SEO polish)
- Added SiteConfig SEO defaults: meta description, default OG image URL, twitter handle.
- base.html: canonical URLs exclude querystrings; description/OG/Twitter tags use SiteConfig defaults with safe fallbacks.
- Footer copy tightened and de-duplicated policy links.

Last updated: 2026-02-16 (America/New_York)

## 2026-02-16 - Hotfix: ops ErrorEvent model/migration mismatch
What changed:
- Fixed startup and `makemigrations` crash caused by `ops/admin.py` importing `ErrorEvent` while `ops.models` did not define it.
- Added `ops.ErrorEvent` model and additive migration `ops.0002_errorevent`.


## 2026-02-16 - Pack AK (Funnel Metrics: Native Analytics)
What changed:
- Added native funnel event types to `analytics.AnalyticsEvent`: `ADD_TO_CART`, `CHECKOUT_STARTED`, `ORDER_PAID`.
- Funnel events are logged at real conversion points:
  - cart add → `ADD_TO_CART`
  - checkout start → `CHECKOUT_STARTED`
  - order paid transition (Stripe webhook + off-platform flows) → `ORDER_PAID`
- Ops Console: added `/ops/funnel/` dashboard showing counts and conversion rates over last N days (`?days=30`).

## 2026-02-16 - Pack AL (Ops Console hardening: Webhooks + Transfer Retry)
What changed:
- Ops Console: Webhooks list `/ops/webhooks/` with investigation filters (status/type/session_id/order_id/days).
- Webhook detail page includes deliveries and raw event JSON (`/ops/webhooks/<id>/`).
- Staff-only “Reprocess webhook” action (idempotent) using shared processing function.
- Ops Order detail: staff-only “Retry transfers” action (idempotent via Stripe Transfer idempotency keys).

## 2026-02-16 - Pack AM (Funnel enhancements: Unique sessions + % formatting + Host/Env breakouts)
What changed:
- Enhanced `/ops/funnel/` to include a **unique-session funnel** based on first-party `hc_sid` (AnalyticsEvent.session_id).
- Added human-friendly **percent formatting** for event-based and session-based funnel conversion rates.
- Added a **host + environment breakout** table (unique sessions) to quickly spot environment drift and data gaps.

## 2026-02-16 - Pack AN (Seller payout reconciliation UI)
What changed:
- Added structured metadata to `orders.OrderEvent` (`meta` JSON) to support seller-scoped payout reconciliation.
- Stripe Connect transfers now record `TRANSFER_CREATED` events with `meta` including: `seller_id`, `transfer_id`, `amount_cents`, `stripe_account_id`.
- Seller dashboard: enhanced `/dashboard/seller/payouts/` with:
  - Recent transfer history
  - Payout mismatch flags (delayed / mismatch / legacy-unknown)
- Ops Console: enhanced Seller detail view to include:
  - Ledger balance + pending pipeline
  - Pending payout items
  - Recent transfer events
  - Mismatch flags + recent seller ledger entries

## 2026-02-16 - Pack AO (Ops “Failed Emails” panel + resend tooling)
What changed:
- Added `notifications.EmailDeliveryAttempt` to track outbound email send attempts linked to `Notification`.
- Notifications send path now records an attempt for every email send (sent/failed) and captures failure errors.
- Ops Console: new Failed Emails queue `/ops/emails/failed/` with filters (days/kind/search) and pagination.
- Ops Console: Failed Email detail `/ops/emails/failed/<id>/` showing notification context, error, and recent attempts.
- Ops action: **Resend email** (POST) which uses stored rendered email bodies and records a new attempt.

## 2026-02-16 - Pack AP (Refund accounting hardening + transfer reversal controls)
What changed:
- Fixed refunds service/view contract mismatches to prevent runtime errors:
  - `create_refund_request()` now accepts optional `token`.
  - `seller_decide()` now matches views (`actor_user` param).
- Added transfer reversal tracking fields on `refunds.RefundRequest`:
  - `transfer_reversal_id`, `transfer_reversal_amount_cents`, `transfer_reversed_at`.
- Implemented best-effort Stripe **Transfer Reversal** after a successful Stripe refund:
  - Reverses ONLY the seller net portion for the refunded line item (`OrderItem.seller_net_cents`).
  - Platform fee remains non-refundable.
  - Records `orders.OrderEvent` type `TRANSFER_REVERSED` with structured metadata.
  - If no transfer is found or reversal fails, refund still completes and an ops-visible WARNING / RefundAttempt error is recorded.
- Added migration `refunds.0002_refundrequest_transfer_reversal`.

## 2026-02-16 - Pack AQ (Throttle/rate-limit tuning for cart/checkout/refunds)
What changed:
- Tightened throttle limits for high-abuse surfaces:
  - Cart mutations: 20/min per fingerprint.
  - Checkout start: 6/min per fingerprint.
  - Refund request/trigger: 4/min per fingerprint.
  - Refund decide: 10/min per fingerprint.
- Fixed misapplied checkout throttling:
  - `checkout_start` is now POST-only and is the endpoint protected by throttle + reCAPTCHA.
  - `order_set_fulfillment` is POST-only and uses its own throttle bucket (`orders:set_fulfillment`).

## 2026-02-15 - Pack AJ (Observability: error event capture + ops triage)
What changed:
- Added `ops.ErrorEvent` model to persist unhandled exceptions with request metadata and compact traceback.
- Added `core.middleware.ExceptionCaptureMiddleware` to record server exceptions without external services.
- Ops Console: new Error Events queue (list + detail) with “mark resolved” action requiring notes.
- Resolution actions are recorded in Ops Audit Log for traceability.

## 2026-02-14 - Pack X (Launch hardening: reCAPTCHA v3 on public write actions)
What changed:
- Added global reCAPTCHA v3 form helper (base template + `static/js/recaptcha_v3.js`).
- Wired server-side reCAPTCHA enforcement to:
  - Account registration
  - Product reviews + seller reviews + review replies
  - Product Q&A thread create / reply / report
- Updated templates to include `recaptcha_token` hidden inputs and `data-recaptcha-action` attributes.

## 2026-02-13 - Pack V (Legal acceptance wiring)
What changed:
- Added explicit **Seller Agreement acceptance** requirement before starting Stripe Connect onboarding.
- Checkout now records acceptance of base legal documents (Terms, Privacy, Refund, Content) for both users and guests.
- Service checkouts additionally record acceptance of the **Services & Appointments Policy** when relevant.

Notes:
- Acceptance records are tied to the exact published document content hash (auditability).
- If legal docs are unpublished, checkout/onboarding blocks with a user-facing error.


## 2026-02-13 - Pack T: Appointment rescheduling + lifecycle notifications
- Added seller **Reschedule** UI for service appointments (reschedules set/adjust `scheduled_start`/`scheduled_end`, preserve notes history).
- Added appointment lifecycle **email + in-app notifications** (requested, accepted, declined, deposit pending/paid, scheduled/rescheduled, canceled, completed).
- Wired deposit-paid webhook hook to notify both buyer and seller when deposit is confirmed and auto-scheduling occurs.


## 2026-02-13 - Pack L: Delivery/shipping UX hardening + tracking + off-platform signals
- Order fulfillment validation now enforces **ZIP presence** for delivery/shipping, with a **ZIP-prefix radius approximation** for local delivery.
- Buyers can mark off-platform payments as **“sent”** with an optional note (`offplatform_sent_at`, `offplatform_note`).
- Sellers can store a private **internal note** on an order (`seller_internal_note`) from the seller order detail page.
- Shipping tracking is supported per goods line item: seller can enter **carrier + tracking #** when marking an item shipped; buyer sees tracking on the order page.


## 2026-02-10 - Native analytics dashboard filters
- Admin Dashboard native analytics panel now supports range filters: **Today**, **Last 7 days**, **Last 30 days**, and **Custom date range**.
- Server-side aggregation functions accept explicit start/end datetimes (end is exclusive) for consistent reporting.


## 2026-02-10 - Local DB + migration recovery (launch hardening)
- Fixed schema drift for `orders.StripeWebhookDelivery` by aligning ops views/templates to the current model/table shape:
  - BigAuto primary key
  - `delivered_at` timestamp for delivery ordering and filtering
  - `StripeWebhookEvent` is the source of truth for `event_type` and `created_at`
- Cleaned up `refunds` migration history to eliminate UUID↔bigint cast failures during local resets:
  - Removed the churny RefundAttempt create/delete/recreate chain
  - Replaced with a single `refunds.0002_refundattempt` creating `RefundAttempt` with BigAuto PK
- If local `django_migrations` becomes inconsistent (e.g., `payments.0002` applied before `orders.0002`), the supported recovery path is: **drop/recreate local DB** and re-run `migrate`.

## Goal
A working marketplace for:
- Physical  printed models (shipped by sellers)
- service  print files (orderable assets)

References / support content:
- Navbar includes a "References" dropdown with Help, FAQs, and Tips & Tricks.
- Tips & Tricks is a static page for now (it will become the Blog later).

Logged-out users can browse. Users have public usernames.


## 2026-02-16 - Pack BA - Admin Ops webhook schema alignment ✅
- Fixed admin ops view/template crash by aligning to current `orders.StripeWebhookDelivery` fields:
  - use `delivered_at` (not `received_at`)
  - use `webhook_event.event_type` (not `event_type` on delivery)
  - show `stripe_session_id` in place of the removed `request_id`

---

## Storefront buckets (Home page)
Home page shows 4 buckets, each capped at HOME_BUCKET_SIZE (currently 8):
- Featured: manual flag `Product.is_featured`
- New: most recent active listings
- Trending: manual override `Product.is_trending` + computed fill
- Misc: active products not already shown above

Home uses:
- `_annotate_rating()` so rating + review count display on every home card without per-card DB queries.
- `p.can_buy` flag to enable/disable Add to cart on home cards depending on seller Stripe readiness (or owner override).
- `p.trending_badge` as the single template rule for showing 🔥 Trending.

---

## Browse pages (Products list)
Browse supports:
- Search (`q`)
- Kind filtering (MODEL / FILE) via route lock or query param on the “all products” page
- Sort control:
  - new (default)
  - trending
  - top (Top Rated)

Browse cards display:
- 🔥 Trending badge when `p.trending_badge` is true
- rating summary (`avg_rating`, `review_count`) without extra queries

Browse behavior includes early-stage warnings:
- Top Rated fallback banner if no products meet `MIN_REVIEWS_TOP_RATED` yet
- Trending fallback banner when there’s no meaningful trending signal yet

---

## Ratings (no N+1)
We annotate list querysets once per request:
- `avg_rating` = AVG(reviews.rating) default 0.0
- `review_count` = COUNT(reviews) default 0

Templates should never aggregate reviews per product card.

---

## Trending (computed + day-1 realism)
Trending uses a rolling window (TRENDING_WINDOW_DAYS, currently 30 days) and mixes:
- recent paid purchases (strongest)
- recent add-to-cart events (strong intent)
- recent reviews (velocity)
- recent views (weak, but helps day-1)
- avg_rating (quality, lower weight)

Trending sort tie-breakers:
- trending_score DESC
- avg_rating DESC
- created_at DESC

Home Trending:
- manual trending products first (`is_trending=True`)
- remaining slots filled by highest computed trending_score

Badge normalization:
- templates check only `p.trending_badge`
- views set `p.trending_badge = is_trending OR computed-trending-membership`

---

## Engagement events (v1)
Added model:
- `ProductEngagementEvent` with event_type:
  - VIEW
  - ADD_TO_CART

Logging implemented:
- Product detail logs VIEW (throttled per session per product)
- Cart add logs ADD_TO_CART (best-effort, never breaks checkout)

Purpose:
- Provide “real” trending signals on day 1, even before sales volume exists.

---

## Files touched recently (high-level)
- core.views:
  - rating annotations on base queryset
  - trending computation includes purchases + reviews + engagement events
  - home buckets computed and flags applied to card objects
- products.views:
  - browse sorting modes (new / trending / top)
  - rating/trending annotations for lists
  - throttled VIEW logging in product_detail
  - “more like this” annotated for ratings
- templates:
  - home cards: add-to-cart button + rating + 🔥 badge
  - product list cards: sort controls + rating + 🔥 badge
  - product detail “more like this”: rating + 🔥 badge

---

## Current known risk / reminder
Trending badge membership on browse needs a strict rule:
- avoid marking *every* item as “Trending” when sort=trending
- badge should represent a subset (top N or score threshold), not “everything in the list”

---

## orders metrics (bundle-level)

LOCKED (Updated Platform Outline, Feb 2026):
- Seller Listings for service products display **unique orderers** and **total orders clicks**.
- Counts are tracked at the **product/bundle level** (not per-asset) for seller-facing metrics.

Implementation (current):
- `Product.order_count` stores total orders clicks (bundle-level).
- `products.ProductorderEvent` records each orders action with:
  - optional `user` (logged-in)
  - `session_key` for guest uniqueness approximation
- Free orders (`products:free_asset_order`) and paid orders (`orders:order_asset`, `orders:order_all_assets`) both:
  - increment `DigitalAsset.order_count` (per-asset display)
  - increment `Product.order_count` (bundle-level)
  - create `ProductorderEvent` (best-effort; never blocks orders)

Seller Listings metrics:
- Physical products show **net units sold** (PAID minus refunded).
- service products show **unique_orderers / total_orders**.


## 2026-02-09 - Change Pack: Email Verification Gating
- Added Profile email verification fields (email_verified, email_verification_token, email_verification_sent_at).
- Added /accounts/verify/ status page + resend flow; verification link sets email_verified true.
- Gated actions behind verified email: Stripe Connect onboarding, Q&A posting/report/delete, and review creation.


## 2026-02-09 - Change Pack: Free service Cap + orders + Seller Listings
- Added **SiteConfig.free_digital_listing_cap** (default 5) and wired it into the dashboard settings form.
- Enforced **free service activation cap** for non-Stripe-ready sellers (cap blocks activation beyond limit; redirects to Stripe status).
- Added **Product.order_count** for bundle-level orders tracking; Seller Listings uses this as `total_orders`.
- Seller Listings now computes **net units sold** as paid quantity minus refunded physical line items (RefundRequest status=refunded).


This file is the “what exists right now” ledger. It should match the codebase.

---

## Current State Summary (Orders + Payments + Refunds)

### Orders (app: `orders`)
- Orders are **financially snapshotted** at creation time to preserve historical correctness.
- Supports **registered buyers** and **guest checkout**.
- Guest access is **tokenized** via `order.order_token` and `?t=<token>` query string for order/detail/orders access and guest refund access.
- orders for guests are emailed on payment (best-effort) and include tokenized links.

**Key models**
- `Order`
  - Identity: UUID primary key.
  - Parties:
    - `buyer` nullable (registered user).
    - `guest_email` used when buyer is null.
    - Validation: order must have **buyer OR guest_email**; if buyer present, guest_email is cleared.
  - Access:
    - `order_token` UUID (db indexed), used for guest order access and guest orders/refund access.
  - Totals: `subtotal_cents`, `tax_cents`, `shipping_cents`, `total_cents`.
  - Snapshots:
    - `marketplace_sales_percent_snapshot` (Decimal % captured at creation).
    - `platform_fee_cents_snapshot` retained for legacy compatibility but must remain **0** (not used).
  - Stripe tracking:
    - `stripe_session_id` (indexed)
    - `stripe_payment_intent_id`
    - `paid_at`
  - Shipping snapshot fields stored on `Order` for physical shipping labels / fulfillment:
    - name/phone/address fields.
  - Helpers:
    - `requires_shipping` uses `Order.items.requires_shipping`.
    - `recompute_totals()` derives subtotal/total and sets `kind` (service/physical/mixed).
    - `mark_paid()` sets status/paid_at, captures stripe ids, records event, and emails guest orders.

- `OrderItem` (alias `LineItem`)
  - Seller is **snapshotted** on the line: `seller` FK to user (PROTECT).
  - Line flags:
    - `is_digital`
    - `requires_shipping`
  - Ledger snapshot on each line:
    - `marketplace_fee_cents`
    - `seller_net_cents`

- `OrderEvent`
  - Order audit trail: created/session created/paid/canceled/refunded/transfer created/warning.

- `StripeWebhookEvent`
  - Stores processed `stripe_event_id` for strict webhook idempotency.

---

### Payments (app: `payments`)
Payments owns Stripe Connect onboarding state + seller ledger models + seller payout/ledger UI + connect webhook syncing.

**Key models**
- `SellerStripeAccount`
  - OneToOne: `user` with related name `stripe_connect`.
  - Fields:
    - `stripe_account_id` (indexed)
    - `details_submitted`, `charges_enabled`, `payouts_enabled`
    - `onboarding_started_at`, `onboarding_completed_at`
  - `is_ready` property: account id present AND all three booleans true.
  - Methods: mark onboarding started / mark completed if ready.

- `SellerBalanceEntry`
  - Append-only ledger of seller balance deltas.
  - `amount_cents` signed:
    - positive => platform owes seller
    - negative => seller owes platform
  - Links:
    - optional `order` and `order_item` references.
  - Reasons: payout/refund/chargeback/adjustment.

**Views / flows**
- Connect onboarding:
  - `connect_status` shows current connect status and optionally refreshes status.
  - `connect_start` creates Express account if needed then redirects to Stripe-hosted onboarding link.
  - `connect_sync` is a manual refresh button for status.
  - `connect_refresh` and `connect_return` handle Stripe redirect UX.
- Payouts / ledger:
  - `payouts_dashboard` shows signed balance + paginated ledger with filters.
- Connect webhook:
  - `stripe_connect_webhook` handles `account.updated` and updates local booleans.
  - Uses **dedicated secret** `STRIPE_CONNECT_WEBHOOK_SECRET`.

**Global template context**
- `payments.context_processors.seller_stripe_status`
  - `seller_stripe_ready`: True/False/None (None means not a seller)
  - `has_connect_sync`: whether route exists
  - `user_is_owner`, `user_is_seller`
  - Avoids templates touching profile relations directly.

**Decorator**
- `payments.decorators.stripe_ready_required` gates seller publishing/modifying listings until Connect is ready (owner bypass).

---

### Refunds (app: `refunds`)
Refunds is implemented and wired as a full feature.

**Locked policy implemented**
- Refund requests are **physical-only** and **full refund per physical line item**.
- service products are **non-refundable** (v1).

**Model**
- `RefundRequest`
  - One refund request per order line item:
    - `order_item` is OneToOne with related name `refund_request`.
  - Denormalized parties:
    - `seller` snapshot (from order item)
    - `buyer` nullable
    - `requester_email` for guest
  - Status flow:
    - requested → approved/declined → refunded
    - canceled exists for future UI, but not central in current flows.
  - Snapshot amounts at creation (source of truth):
    - line subtotal
    - allocated tax
    - allocated shipping (allocated across shippable lines)
    - total refund
  - Stripe tracking:
    - `stripe_refund_id`, `refunded_at`
  - Seller decision tracking:
    - `seller_decided_at`, `seller_decision_note`

**Services**
- Allocation:
  - Tax allocated across all lines proportionally by `line_total_cents`.
  - Shipping allocated across **requires_shipping=True** lines proportionally by `line_total_cents`.
- Creation:
  - Only allowed on PAID orders and physical line items.
  - Enforces one request per item.
  - Writes `OrderEvent` WARNING for audit.
- Decision:
  - Seller/owner/staff can approve/decline.
  - Writes `OrderEvent` WARNING for audit.
- Trigger refund:
  - Allowed only after approval and if not already refunded.
  - Uses Stripe Refund API against `order.stripe_payment_intent_id`.
  - Uses `rr.total_refund_cents_snapshot` as the source of truth.
  - Writes `OrderEvent` REFUNDED for audit.

**Views**
- Buyer list (logged-in buyers).
- Buyer detail supports:
  - buyer
  - staff
  - guest access via valid underlying order token.
- Buyer/guest create request:
  - Guest must confirm checkout email matches `order.guest_email`.
  - Token is preserved through redirects.
- Seller queue/detail/actions:
  - Seller sees their requests; owner/staff can see all.
  - Approve/decline, then trigger Stripe refund.
- Staff queue + refund trigger safety valve.

**Admin**
- `RefundRequestAdmin` provides:
  - quick links to Order and OrderItem
  - read-only snapshot display
  - **dangerous** “admin_trigger_refund” action for APPROVED + not-yet-refunded requests

---

## Known Duplications / Cleanups Needed
- `payments.permissions.py` duplicates the decorator already in `payments.decorators.py`.
- `payments/services.py` appears duplicated twice in the pasted text (same content). In repo there should be **only one** file.

(These aren’t “broken”, but they are maintenance hazards.)

---

## What’s “Done” for this slice
- Orders: buyer/guest, token access model, snapshot accounting model, paid flow hooks, events, webhook idempotency table.
- Payments: Connect onboarding + sync + webhook, seller ledger models + dashboard, global status context.
- Refunds: full request/decision/refund flow with allocation + Stripe refund call + admin controls.

---

# Local Market NE – Project Memory

## Snapshot (2026-02-03) - Orders + Payments + Refunds

### Orders (source of truth: snapshots + ledger fields)
- Orders are production-grade and designed for historical correctness.
- `Order` snapshots:
  - `marketplace_sales_percent_snapshot` captures percent-based marketplace fee at order creation.
  - `platform_fee_cents_snapshot` is legacy/unused and must remain `0`.
- `OrderItem` snapshots:
  - `seller` FK snapshot (do not rely on product->seller later).
  - Per-line ledger fields: `marketplace_fee_cents`, `seller_net_cents`.
- Guest access:
  - Guest orders have `guest_email` + `order_token` and can access order/orders links via `?t=<token>`.
  - Paid guest emails include tokenized order link and tokenized orders links.
- `Order.mark_paid()`:
  - Sets paid status and `paid_at`, stores Stripe IDs once, emits `OrderEvent`.
  - Sends guest paid email with orders when applicable.

### Payments (Stripe Connect + seller readiness + seller ledger)
- Stripe Connect Express onboarding implemented:
  - `SellerStripeAccount` (OneToOne to user) stores Connect account id and readiness flags:
    - `details_submitted`, `charges_enabled`, `payouts_enabled`, plus onboarding timestamps.
  - Ready state is `is_ready` property (do not query it as a DB field).
- Seller gating:
  - Canonical gate decorator: `payments.decorators.stripe_ready_required`
  - Back-compat shim: `payments.permissions.stripe_ready_required` re-exports decorator.
- Seller ledger:
  - `SellerBalanceEntry` is append-only signed cents ledger.
  - `payments.services.get_seller_balance_cents()` returns signed sum.
  - `payments.views.payouts_dashboard` shows balance + ledger entries with filters.
- Connect status UX:
  - `connect_status` page shows readiness + continue CTA.
  - `connect_start` creates Express account once and redirects to Stripe onboarding.
  - `connect_sync` refreshes from Stripe manually.
  - Connect webhook endpoint updates account readiness on `account.updated`.

### Refunds (locked rules: physical-only, full refund per line item)
- Refund requests are FULL refunds per PHYSICAL line item only.
- service products are non-refundable in v1.
- `RefundRequest` model:
  - One refund request per `OrderItem` (OneToOne).
  - Snapshots at creation:
    - `line_subtotal_cents_snapshot`
    - `tax_cents_allocated_snapshot`
    - `shipping_cents_allocated_snapshot`
    - `total_refund_cents_snapshot`
  - Tracks Stripe refund id + timestamps, seller decision fields.
- Allocation:
  - Tax allocated across ALL items by line-total proportion.
  - Shipping allocated across shippable items only by line-total proportion.
- Flow:
  - Buyer/guest creates request (guests confirm email matches checkout email).
  - Seller approves/declines; after approval seller triggers Stripe refund.
  - Staff safety-valve refund trigger exists (admin action + staff endpoint).

## Code hygiene fixes applied (2026-02-03)
- Removed duplicate `stripe_ready_required` logic by making `payments/permissions.py` a re-export.
- Removed duplicated block in `payments/services.py` (function was defined twice).

---

## Favorites & Wishlist
- Implemented as separate entities (Favorites vs WishlistItems) in new `favorites` app.
- Single combined page: `/favorites/` with tabs.
- Add/remove actions exposed on product detail pages (logged-in users).
- Linked from navbar user menu and Consumer Dashboard.

## Free service listing cap hardening
- Enforced **SiteConfig.free_digital_listing_cap** server-side in seller **create** and **duplicate** flows (not just UI), preventing cap bypass when Stripe is not ready.

## Notifications email-like rendering
- Notifications now store rendered email bodies (`email_text`, `email_html`) at send time.
- Notification detail page renders an **Email view** tab (HTML if available) plus a **Text** tab to mirror what was sent.

## Email → In‑app notification parity (2026-02-09)
- Locked rule implemented: **user-facing emails also create an in-app Notification** with the same subject/body and an action link.
- `notifications.services.notify_email_and_in_app(...)` now supports `email_template_txt=None` and falls back to `strip_tags(html)` for plaintext.
- Wired into:
  - Welcome email (`accounts/signals.py`)
  - Order lifecycle emails (`orders/models.py`)
  - Refund lifecycle emails (registered users) (`refunds/services.py`)
  - Seller dashboard “free unlock” email (`dashboards/views.py`) + new template `templates/emails/free_unlock.html`.

## Unverified account access limits expanded (2026-02-09)
- Locked rule enforced: unverified users can sign in and access profile/basic dashboard, but **cannot use registered-only features**.
- Added email verification gating to:
  - Favorites/Wishlist (`favorites/views.py`)
  - Notifications (`notifications/views.py`)
  - Seller-only views (via `products.permissions.seller_required`)

## Seller replies to reviews (2026-02-09)
- Locked rule implemented: sellers can reply publicly to product reviews.
- Added `reviews.ReviewReply` (one reply per review) + seller-only reply endpoint.
- Seller replies are displayed under reviews on:
  - product detail Reviews tab
  - full product reviews page

## Trending badge hardening (2026-02-09)
- Locked rule enforced consistently across Home + Browse: 🔥 Trending badge shows only for:
  - manual `Product.is_trending=True`, OR
  - computed Top N by `trending_score` with `trending_score > 0` (cached).
- Home and Products list now share one computed badge-membership function (`products.services.trending.get_trending_badge_ids`).


## Seller analytics summary (2026-02-09)
- Added Seller Analytics page with 7/30/90 day windows.
- Metrics include: views/clicks/add-to-cart (ProductEngagementEvent), orders + paid units, refunded units (RefundRequest REFUNDED), net units sold, gross/net revenue, and bundle-level orders metrics (unique/total via ProductorderEvent).
- Added dashboard sidebar link: Seller → Analytics.

## Seller listings metrics polish (2026-02-09)
- Seller Listings now strictly matches locked metric definitions:
  - Physical: **NET units sold** (paid − refunded).
  - service: **unique orderers + total orders clicks** at the product (bundle) level.
- Uniqueness logic excludes blank guest session keys so guest counts cannot be inflated by missing sessions.

- 2026-02-09: Added staff Q&A moderation queue actions (resolve report, remove message, suspend user) with audit trail via core.StaffActionLog. Fixed staff reports template URL name mismatch.

- 2026-02-09: Moderation UX polish: staff Q&A reports filter (open/resolved/all), product Q&A tab shows staff-only open-report count badge, added staff suspensions list page.

- 2026-02-09: Moderation UX polish: added staff unsuspend action (with StaffActionLog), and staff-only per-message open-report badges in product Q&A threads.

## 2026-02-09 - Launch hardening
- Added RequestIDMiddleware with X-Request-ID response header and request-context logging filter.
- Enhanced dev/prod LOGGING to include request_id/user_id/path and configurable LOG_LEVEL.
- Extended core throttle decorator to support GET endpoints (methods=...).
- Added throttles to orders endpoints (paid + free) to prevent abuse/inflated counts.

## 2026-02-09 - Ops observability hardening
- Reintroduced operational models:
  - `orders.StripeWebhookDelivery` to log webhook receipt/processing/duplicates/errors (request_id, timestamps).
  - `refunds.RefundAttempt` to log each attempt to trigger a Stripe refund (success/failure, request_id).
- Stripe webhook now returns **HTTP 500 on internal processing errors** (after signature verification) so Stripe retries; status is tracked in `StripeWebhookDelivery`.
- Added **Admin Ops** dashboard (`/dashboard/admin/ops/`) showing recent webhook errors, refund failures, and order warnings.

## 2026-02-10 - Seller Listings stabilization + deploy docs
- Fixed Seller Listings rendering:
  - Template now iterates `products` as Product instances (no `row.obj` wrapper).
  - Removed non-existent template attributes (`is_digital`, `order_total`).
  - service metrics display uses `unique_orderers_count` + bundle-level `Product.order_count`.
  - Physical listings display **Net units sold** label.
- Added production playbooks:
  - `docs/DEPLOY_RENDER.md` (Render-safe deployment plan)
  - `docs/POST_DEPLOY_CHECKLIST.md` (verification checklist)

## 2026-02-10 - Analytics: migrate Plausible → Google Analytics 4
- Replaced Plausible client script with GA4 `gtag.js` snippet (uses `GA_MEASUREMENT_ID` from settings/env via context processor).
- Added GA4 Data API reporting module (`dashboards/analytics_google.py`) and wrapper (`dashboards/analytics.py`) for Admin Dashboard summaries/top pages.
- Admin dashboard analytics panel updated to 'Google Analytics' (30-day summary + top pages) and optional outbound link via `SiteConfig.google_analytics_dashboard_url`.
- CSP updated to remove Plausible frame-src and allow Google Tag Manager host.


## 2026-02-10 Native analytics (server-side)


- Implemented first-party server-side pageview analytics via new `analytics` app (AnalyticsEvent + admin).
- Added `analytics.middleware.RequestAnalyticsMiddleware` to record HTML GET/HEAD pageviews (bot filtered, throttled).
- Replaced Admin Dashboard analytics panel to use native analytics (30-day summary + top pages); Google Analytics link remains optional.
- Added SiteConfig toggles: `analytics_enabled`, `analytics_retention_days` with Admin Settings form support.
- Added management command `prune_analytics_events` to enforce retention policy.

- (2026-02-10) Added seller payouts reconciliation page (available vs pending) + review throttling + sidebar link.


## 2026-02-10 - Admin dashboard polish + References/About

- Admin dashboard: fixed Analytics card layout and ensured the **Open Google Analytics** button appears when `SiteConfig.google_analytics_dashboard_url` is set.
- Added **About** page under References and included References pages in the sitemap.


## 2026-02-10 - Launch hardening: throttling policy + abuse signals

- Centralized throttle policy in `core/throttle_rules.py` and updated all endpoint throttles to use it.
- Throttle rejections are now logged into native analytics as `AnalyticsEvent(event_type=THROTTLE)` with `meta.rule`.
- Admin dashboard now shows "Abuse signals" (24h/7d throttled counts + top throttled rules) alongside native analytics.


## 2026-02-10 - Legal / Licensing documents (versioned, DB-backed)

- Extended `legal.LegalDocument` doc types to include:
  - `seller_agreement` (Seller Agreement)
- Added public routes and templates for the new legal pages.
- Implemented a data migration to seed/publish initial v1 documents for all legal doc types.
- Legal document bodies are rendered as trusted HTML (`|safe`) since editing is admin-only.



## 2026-02-10 - Licensing nav + seller fulfillment tasks
- Added 'Licenses & Policies' landing page under legal app and linked it from Navbar → References and Footer (Support + Legal columns).
- Extended seller new order notifications to cover both physical and service sales (email + in-app) via Order.mark_paid hook.
- Implemented persistent SellerFulfillmentTask records for paid orders with physical items; tasks remain open until seller marks items shipped/delivered.
- Seller dashboard now shows Fulfillment tasks count + preview and links to fulfillment queue.


## 2026-02-10 - Change Pack: Free service cap verification gate
- Enforced locked policy: when a seller exceeds `SiteConfig.free_digital_listing_cap` for active FREE FILE listings, they must **verify email first** (redirect to email verification), then complete **Stripe Connect onboarding** to publish more.
- Applied to both activation toggle and listing duplication guard.

## 2026-02-10 - Fulfillment UX Pack
- Fixed seller fulfillment queue: `/orders/seller/orders/` now lists *physical* PAID line items and supports status tabs (pending/shipped/delivered/all).
- Seller dashboard now surfaces open `SellerFulfillmentTask` count + preview with per-order pending counts and links into the order detail.
- Seller dashboard net-units-sold aggregates now compute **paid qty − refunded qty** (refunds are full-line for physical items).

## 2026-02-10 - Admin Settings parity (Dashboard UI ↔ Django Admin)
- Synced `SiteConfig` fields so the **Dashboard Admin Settings** page and **Django admin SiteConfig** expose the same configuration surface.
- Added missing Django admin fieldsets for: free service listing cap, GA dashboard URL, native analytics toggles, and legacy Plausible URL.
- Ensured affiliate links are editable consistently from the Dashboard Admin Settings page.

## Native analytics hardening (2026-02-11)
- Implemented first-party visitor + session cookies (hc_vid, hc_sid) with 30m inactivity rotation.
- AnalyticsEvent now stores visitor_id, session_id, host, environment, is_staff/is_bot for cleaner reporting and stream separation.
- Admin Settings and Django admin SiteConfig now include native analytics controls: exclude staff, exclude admin/dashboard paths, primary host, primary environment.

## Native analytics UI + settings polish (2026-02-11)
- Added Active users (last 30m) metric to Admin Dashboard native analytics card.
- Admin Settings page styling improved: section cards, aligned inputs, white inputs on light/gray backgrounds.
- Fixed affiliate_links JSON textarea to always render valid JSON (pretty-printed) so saving matches Django admin behavior.

## Admin settings affiliate links UX (2026-02-11)
- Replaced Affiliate Links JSON textarea with simple title/URL/details input rows (10).
- Affiliate links are stored as JSON behind the scenes, built from the form inputs on save.

---

## 2026-02-13 - LocalMarketNE: Store sidebar category UX
- Updated `templates/partials/sidebar_store.html` to better handle large category trees:
  - Subcategories are hidden by default and shown via per-category expand/collapse.
  - Root category lists are truncated to the first 8 items with a **More** expander.
  - Added a collapsed **Filter** control above each list to search categories client-side.

## Pack K - Fulfillment Status + Off‑Platform Payment Confirm + Sidebar UX Polish (2026-02-13)
**Done**
- Orders: removed remaining HC3 `is_digital` checks in seller/buyer fulfillment views (LMNE uses goods vs services).
- Orders: added seller action to **Confirm payment received** for Venmo/PayPal/Zelle orders (marks paid + logs event).
- Orders: added per‑line **fulfillment status** update for goods items (pickup/delivery/shipping aware).
- Fulfillment statuses expanded: pending, ready, out_for_delivery, picked_up, shipped, delivered.
- Seller fulfillment queue tabs expanded to match new statuses.
- Sidebar: “More” button now toggles to “Less” and persists expansion state; filter UI wired to restore clean behavior.

**In progress / Next**
- Fulfillment: mileage check (buyer zip vs delivery radius) and clearer delivery messaging.
- Fulfillment: add tracking fields entry UI for shipped items (carrier + tracking).
- Off‑platform: add optional buyer “I sent payment” marker and seller notes.

## 2026-02-13 - Pack M (Shipping notifications + service cancellation window)
- Added service cancellation window hours (optional) and enforced it on buyer appointment cancellations.
- Added buyer cancel action for appointment requests (requested/accepted) with server-side enforcement.
- Added buyer shipped email + in-app notification when seller marks a shipping item as SHIPPED (tracking included if provided).
- Cleaned Purchases template to remove old digital/download remnants.
- Docs updated (MEMORY/DECISIONS/ROADMAP).



## Pack O (2026-02-13)
- Added seller Payments (Awaiting) queue page for off-platform payment confirmations.
- Added seller sidebar link to Payments (Awaiting).
- Polished deposit UX on buyer appointment requests (shows deposit amount and deposit order status).
- Removed remaining HC3 download/free-unlock artifacts (templates/command).

## 2026-02-13 - Pack P re-apply: fulfillment tasks + shipping tracking cleanup
- Fixed a broken `OrderItem` model section (shipping tracking fields were accidentally unindented), causing import/runtime issues.
- Removed legacy `OrderItem.carrier` field usage in code/templates (LMNE now uses `tracking_carrier` + `tracking_number`).
- Seller fulfillment “mark shipped” view now accepts both `tracking_carrier` and legacy template `carrier`/`carrier_other` inputs.
- Added `orders` migration `0005_seller_fulfillment_tasks_and_tracking_cleanup` to:
  - Create `SellerFulfillmentTask` model
  - Remove legacy `OrderItem.carrier`
  - Add DB index on `OrderItem.tracking_number`

## 2026-02-13 - Pack Q: Inventory reservation + made-to-order lead times + delivery radius validation
**Done**
- Inventory enforcement end-to-end:
  - Cart add/update now clamps quantity to available stock for **non-made-to-order goods** and blocks out-of-stock adds.
  - Order creation reserves inventory (stock decrement) for **non-made-to-order goods** to prevent oversell.
  - Order cancel/Stripe session expire releases reserved inventory back to stock (idempotent).
- Lead time enforcement:
  - Products marked **made-to-order** now require `lead_time_days` (model validation).
  - Order items snapshot `lead_time_days_snapshot` at purchase time.
- Orders model adds reservation flags:
  - `Order.inventory_reserved`, `Order.inventory_released`.
  - New migration `orders/0006_inventory_reservation_and_lead_time_snapshot`.
- Fulfillment delivery validation hardened (ZIP normalization + stricter checks when local delivery is selected).


## 2026-02-13 - Pack S re-apply: Service appointment workflow completion (rule-compliant)
**What we did (code first)**
- Fixed `appointments.models.AppointmentRequest` (was broken: `requires_deposit`/decorator indentation).
- Implemented appointment lifecycle statuses: `REQUESTED → DEPOSIT_PENDING → DEPOSIT_PAID → SCHEDULED → COMPLETED` (+ `CANCELED/DECLINED`).
- Added scheduling fields and timestamps (`scheduled_start/end`, `accepted_at`, `deposit_paid_at`, `scheduled_at`, etc.).
- Wired Stripe webhook: when a **deposit order** is paid, any linked appointment is marked `DEPOSIT_PAID` and auto-scheduled to the requested slot.
- Added seller actions:
  - Cancel appointment
  - Mark appointment completed
- Added appointments **migrations** (`appointments/migrations/0001_initial.py`) so the app is migratable on clean DBs.
- Updated buyer/seller appointment templates to match the new status model and deposit flow.

**What we are doing**
- Stabilizing v1 service booking UX so sellers can accept requests, buyers can pay deposits, and the system deterministically schedules.

**What’s left**
- Add seller “reschedule” UI (override `scheduled_*` rather than defaulting to requested slot).
- Add email notifications for: accepted, deposit paid, scheduled, canceled, completed.
- Admin views/filters for appointment moderation/reconciliation.

## Pack U (2026-02-13) - Buyer confirmation + Calendar export (ICS) + Reminder notifications

**Code changes**
- Added appointment buyer-confirmation flow for seller reschedules (AWAITING_BUYER_CONFIRMATION → SCHEDULED).
- Added ICS calendar export endpoint for buyers/sellers (download .ics invite).
- Added reminder system via management command `send_appointment_reminders` (cron-friendly).
- Added SiteConfig settings for appointment reminders (enabled flag + hours-before).

## Pack W (Ops Console) - 2026-02-13
- Added a dedicated `ops` app providing an owner-grade Ops Console at `/ops/`.
- Ops access model: superusers are treated as OPS; an `ops` Group is auto-created on migrate for future ops staff.
- Ops Dashboard includes KPI tiles (GMV, queues) plus recent orders + recent ops activity.
- Ops tooling added: Orders list/detail, Sellers list/detail, Refund Requests queue, Q&A Reports queue (resolve action), and Audit Log viewer.
- Added `ops.AuditLog` (GenericFK target) and wrote audit entries for moderation actions.


## Pack W.1 - Store roles: Admin Console + Ops Console
- Added **Admin Console** at `/staff/` for day-to-day site work (orders, refund requests, Q&A reports).
- Kept **Ops Console** at `/ops/` for high-privilege operational support (reconciliation, audit log, deeper tools).
- Added `staff_admin` group with default permissions and access gate.
- Navbar now shows **Admin Console** for staff admins and **Ops Console** for ops users/superusers.
- Added management command `python manage.py bootstrap_admin_ops` (env-driven) to create/update the two accounts.


## 2026-02-14 - Orders email helpers + event enum fix
- Replaced missing orders model helpers (_send_payout_email, _send_order_failed_email) with orders/emails.py (send_payout_email, send_order_failed_email).
- Updated orders/stripe_service.py and orders/webhooks.py to import the new email helpers.
- Added OrderEvent.Type.STRIPE_SESSION_CREATED to align with existing usage.
- Added orders.models _site_base_url / _absolute_static_url so other apps (e.g., refunds) can safely import them.


## 2026-02-14 - Pack Fix: Staff Console Q&A Reports Model Alignment
- Fixed Admin Console (`/staff/`) Q&A reports queue to use `qa.ProductQuestionReport` (actual model) instead of non-existent `QAReport`.
- Fixed resolve flow to set `resolved_at` and save correct fields (removed invalid `updated_at`).
- Fixed staff console Q&A reports template to post to `staff_console:resolve_qa_report`.


## Pack Y - Policy & Safety (Age 18+ + Prohibited Categories) (2026-02-14)
- Added Category policy flags: `is_prohibited`, `requires_age_18` (admin-manageable).
- Added Profile age confirmation: `is_age_18_confirmed`, `age_18_confirmed_at`.
- Registration now requires a 18+ confirmation checkbox.
- Checkout is blocked unless age is confirmed (authenticated users) or guest checks the 18+ checkbox.
- Product listing validation blocks prohibited categories.


## Pack Z (2026-02-14) - Prohibited items enforcement + staff listing moderation
- Implemented purchase-time enforcement for category policy flags (is_prohibited / requires_age_18).
- Cart pruning and checkout/order creation now block prohibited categories.
- Added catalog migration seeding prohibited categories: Weapons and Alcohol.
- Added Prohibited / 18+ badges to product detail and product cards.
- Added Staff Console Listings tool for re-categorization/deactivation with audited reason.

## Pack AA - Smoke Test Hardening (2026-02-15)
**Goal:** eliminate dead ends and add lightweight health surfaces for deploy validation.

### Code changes
- Added `/accounts/verify-email/resend/` POST alias endpoint to resend verification emails (prevents dead links).
- Added Ops health endpoint: `/ops/health/` (ops-only JSON subsystem config checks).
- Added public health endpoints for uptime checks:
  - `/healthz/` → `ok`
  - `/version/` → JSON `{version: ...}`

### QA intent
Pack AA is a continuous “smoke test + patch” layer; future dead-end fixes should be recorded here before launch.


## Pack AB - Monitoring + Audit Completeness (2026-02-15)

- 2026-02-15 - Pack AC (Backups & Recovery): added ops runbook at /ops/runbook/ and management command `python manage.py ops_backup_report` for config/status snapshot and checklist. Ops nav includes Runbook + Ops Health.
- Fixed Admin Console listing edit audit call (was passing `actor=` instead of `request=`) and now requires a reason.
- Ops Audit Log now supports filters and CSV export for reconciliation and incident response.

## Pack AD (redo) - Browse Performance Hardening (2026-02-15)
**Goal:** reduce browse/storefront load, clamp untrusted inputs, and avoid runaway queries.

### Code changes
- Added **pagination** + **input clamping** to public browse surfaces:
  - Products list (`/products/`)
  - Services list (`/services/`)
  - Seller storefront (`/shop/<seller>/`)
  - Top sellers (`/top-sellers/`)
  - Default page size: 24 (max 60); query length clamped to 200 chars.
- Added **short-lived anonymous page caching** (60s) for:
  - Product list, services list, seller storefront, and product detail (GET only)
  - Cache key includes path + querystring for correctness.
- Updated templates to render pagination controls and added basic storefront filters (kind/category/search).

### QA checks
- Browse pages should remain functional with large catalogs.
- Pagination should preserve query/category filters.
- Anonymous caching should not affect authenticated sessions.


## Pack AE (Store Operations controls) - 2026-02-15
**Done**
- Added SiteConfig store-ops controls:
  - Site Announcement bar (enabled + text)
  - Maintenance Mode (enabled + message)
  - Featured sellers/categories lists (optional)
- Added `MaintenanceModeMiddleware` (public sees 503 maintenance page; staff/ops allowed).
- Added `includes/site_announcement.html` and `templates/maintenance.html`.
- Wired announcement include into `templates/base.html`.
- Added `core/migrations/0003_siteconfig_store_ops.py`.

**Notes**
- Maintenance mode allowlists /admin/, /ops/, /staff/, /accounts/, /healthz/, /health/, /version/, /static/, /media/.

## 2026-02-15 - Pack AF (Financial Reconciliation Console)
- Added snapshot-based reconciliation annotations for Orders (items gross, expected fee/net, ledger sums, mismatch flags).
- Ops Console: added /ops/reconciliation/ list and /ops/reconciliation/mismatches/ detector.
- Ops Order Detail now displays reconciliation breakdown + mismatch badges.

## 2026-02-15 - Pack AG (User Manual PDF)
**What’s been done**
- Created a full **User and Ops Manual** in both Markdown and PDF:
  - `docs/USER_MANUAL.md`
  - `docs/USER_MANUAL.pdf`
- Manual covers: role model, buyer/seller flows, Staff Admin Console, Ops Console, SiteConfig settings, policies, and launch gate checklist.

**What we are doing**
- Converting the real store operating model into a maintainable, versioned manual artifact that can be shipped with the repo and updated alongside features.

**What needs to be done**
- Add in-app **Help/Docs** link(s) that point to the manual (and/or render the markdown in-app).
- Run a full launch QA pass and update the manual with any workflow changes discovered during testing.

## 2026-02-15 Hotfix
- Fixed Django admin SiteConfigAdmin fieldsets: removed duplicate fields that caused admin.E012 SystemCheckError.


## Pack AH (2026-02-15)

**Goal:** production-hardening and consistency fixes for Orders/Stripe flows.

### What was done
- **Orders invariants**: added status-transition guardrails and financial field immutability once an order leaves `DRAFT`.
- **Stripe ID consistency**: `Order.mark_paid()` now enforces Stripe session + payment_intent IDs for Stripe-paid orders.
- **Shipping snapshot helper**: added `Order.set_shipping_from_stripe()` for webhook/checkout flows.
- **OrderItem tips**: added `OrderItem.is_tip` (migration `orders/0002_orderitem_is_tip`) and compatibility helpers (`fulfillment_method`, `requires_shipping`, `unit_price_cents`).
- **Checkout plumbing fixes**:
  - Rebuilt `orders/services.py` to correctly create `Order` + `OrderItem` rows from the cart, including optional tip lines.
  - Rebuilt `orders/stripe_service.py` to use snapshot fields consistently and create Checkout Sessions.
  - Rebuilt `orders/webhooks.py` with **idempotent** processing via `StripeWebhookEvent` and `StripeWebhookDelivery`.
- **Compatibility aliases**: added `Product.pickup_enabled / delivery_enabled / shipping_enabled` to match older view/template references.
- **Fulfillment selection fix**: updated `orders/views.py` to persist fulfillment choices to the actual stored fields (`fulfillment_mode_snapshot`, fee snapshots) and to avoid saving non-existent snapshot fields.

### What we are doing
- Converging legacy view/template expectations onto the authoritative snapshot-based models so checkout + fulfillment + payouts run end-to-end.

### What’s left
- Add an end-to-end smoke test checklist (local + Render) that covers: cart → order → checkout → webhook paid → seller fulfillment → reconciliation.
- Tighten Stripe Connect transfer linking (`source_transaction`) after confirming whether we’re using charges vs payment intents in the Stripe account.
- Add a simple admin/ops reconciliation UI entry point linking orders ↔ webhook events ↔ transfers.

## 2026-02-15 - Pack AI - Launch Check

- Added launch readiness checks surfaced in Ops Console:
  - New Ops page: `/ops/launch-check/`
  - New management command: `python manage.py launch_check` (supports `--json`)
- Checks cover: DEBUG/PRIMARY_DOMAIN, DB, cache, email, Stripe keys, reCAPTCHA config, storage posture, SiteConfig presence, HSTS posture.

## 2026-02-16 - Pack AJ (Error Events Hotfix Baseline)

**What’s been done**
- Baseline ZIP for this pack: `localmarketne_packAJ_error_events_hotfix.zip`.
- ErrorEvents are present in Ops Console with list/detail/resolve flows.

**What we are doing**
- Stabilizing Ops-facing operational telemetry to support a real launch.

**What’s left**
- Add conversion funnel metrics to measure browse → cart → checkout → paid.

## 2026-02-16 - Pack AK (Funnel Metrics - Native Analytics)

**What’s been done**
- Added native analytics funnel event types: `ADD_TO_CART`, `CHECKOUT_STARTED`, `ORDER_PAID`.
- Logged events at real conversion points:
  - Cart add → `ADD_TO_CART` (throttled per session+product).
  - Order checkout start (Stripe + non-Stripe) → `CHECKOUT_STARTED` (throttled per session+order).
  - Stripe webhook paid → `ORDER_PAID` as a system event.
- New Ops page: `/ops/funnel/` showing counts + conversion rates for last N days (`?days=30`).
- Added Ops nav link: **Funnel**.

**What we are doing**
- Establishing first-party conversion metrics so we can validate the marketplace loop without relying solely on third-party analytics.

**What’s left**
- Add % formatting + unique-session variants (unique sessions that added to cart, started checkout, paid).
- Break out funnel by host/environment once we’re running multiple domains.


## 2026-02-16 - Pack AL - Ops Console hardening (Webhooks + Transfer Retry)

**What changed**
- Added staff Ops tooling to investigate Stripe webhook events and safely reprocess them.
- Added staff Ops action to retry Stripe Connect transfers for paid orders (idempotent).

**Key paths**
- `/ops/webhooks/` (list + filters)
- `/ops/webhooks/<id>/` (detail + reprocess)
- `/ops/orders/<uuid>/` (order detail now includes "Retry transfers" when missing)

**Notes**
- Webhook reprocess uses stored `StripeWebhookEvent.raw_json` and re-runs the same core processing logic as the inbound webhook view.
- ORDER_PAID analytics event is only emitted on an actual order state transition to avoid double-counting during reprocess.


## 2026-02-16 - Pack AO - Ops “Failed Emails” panel + resend tooling

**What’s been done**
- Implemented `notifications.EmailDeliveryAttempt` to record every outbound email send attempt (sent/failed) tied to a `Notification`.
- Updated the unified notification/email send path to always create an `EmailDeliveryAttempt` and capture failure errors.
- Added Ops console visibility:
  - `/ops/emails/failed/` list with filters (days, kind, search) + pagination.
  - `/ops/emails/failed/<id>/` detail showing notification context, error, and recent attempts.
- Added Ops action to **resend** a notification email using stored rendered subject/body (creates a new attempt record).

**What we are doing**
- Hardening Ops tooling so email delivery issues are debuggable without guessing or digging through provider logs.

**What’s left**
- Add refund accounting hardening (physical-only refunds) and ensure transfer reversal safety controls.


## 2026-02-16 - Hotfix - Services browse template crash

**What was fixed**
- Fixed `VariableDoesNotExist` on `/products/services/` caused by template lookups like `request.GET.q` and `request.GET.category` when query params are missing.

**Changes**
- `products/services_list.html` now uses the view-provided context variables (`q`, `category`) consistently and no longer performs `request.GET.<key>` lookups.

**Why**
- Django template attribute-style lookups on `QueryDict` raise `VariableDoesNotExist` when the key is missing; using context variables avoids that failure mode.


### Pack AR - References pages polish ✅
- Updated About/Help/FAQs/Tips templates for a more professional, consistent layout.
- Added Tips to navbar References dropdown and added reference links in footer for consistency.
## 2026-02-16 - Hotfix - base.html canonical TemplateSyntaxError

**What was fixed**
- Fixed `TemplateSyntaxError` from using `request.build_absolute_uri(request.path)` in templates (Django templates cannot call methods with args).

**Change**
- Canonical + `og:url` now use: `{{ request.scheme }}://{{ request.get_host }}{{ request.path }}` (no arg method calls).


## 2026-02-16 - Pack AV - Service search improvements (state/radius filters + query persistence)

**What’s been done**
- Services browse (`/products/services/`) now supports additional filters:
  - `state` → filters by seller `Profile.public_state`.
  - `radius` → filters by seller `Profile.service_radius_miles >= radius` ("seller travels at least X miles").
- Filters persist through:
  - category clicks in the sidebar
  - pagination links
- Services page UI updated with State + Radius dropdowns.

**What we are doing**
- Improving service discovery UX without introducing geo/ZIP distance calculations yet.

**What’s left**
- Next pack: Pack AW (as defined in ROADMAP).


## 2026-02-16 - Pack BC - Release candidate sweep: dead-end audit + launch-check copy tighten-up ✅

**What’s been done**
- Added a Launch Check guardrail to catch "dead-end" risks: a URL wiring check that verifies key named routes resolve (dashboards + ops + storefront entry points).
- Tightened Ops Launch Check copy and added direct links to Ops Health + Ops Runbook.

**What we are doing**
- Stabilizing operator surfaces so broken links/routes are caught before production.

**What’s left**
- Next pack: Pack BD (as defined in ROADMAP).


## 2026-02-16 - Pack BJ - Ops Health page (HTML + JSON) ✅

**What’s been done**
- Converted Ops Health (`/ops/health/`) from JSON-only to a human-friendly Ops Console page.
- Ops Health still supports `?format=json` for quick copy/paste and automation.
- Added a clear link to the public `/healthz/` endpoint and Launch Check from Ops Health.

**What we are doing**
- Tightening release-candidate operator UX so smoke checks are fast and unambiguous.

**What’s left**
- Next pack: Pack BK (as defined in ROADMAP).


## 2026-02-16 - Pack BK - Seller onboarding policy + managed GA/AdSense + remove buyer age gate ✅

**What’s been done**
- **Seller 18+ confirmation** is now enforced at the correct point: **Stripe Connect onboarding start**.
  - Buyers are no longer blocked by the global “18+” gate.
  - Seller confirms 18+ once (stored on `Profile.is_age_18_confirmed`).
- Added seller onboarding **prohibited items acknowledgement**:
  - Sellers must acknowledge **no tobacco, alcohol, or firearms** before Stripe onboarding.
  - Stored on `Profile.seller_prohibited_items_ack` (+ timestamp).
- Moved external tracking scripts to **DB-managed SiteConfig**:
  - Added `SiteConfig.ga_measurement_id` and wired templates/context to use it.
  - Added `SiteConfig.adsense_enabled` + `SiteConfig.adsense_client_id` and inject AdSense only when enabled.
  - Removed hardcoded GA/AdSense IDs from `base.html`.
- Admin Settings (dashboard) now exposes GA/AdSense + seller onboarding policy fields.

**What we are doing**
- Converging v1 policy so seller onboarding is explicit and operator-managed via SiteConfig.

**What’s left**
- Next pack: Pack BL (as defined in ROADMAP).

## 2026-02-16 - Pack BN - Table/Card template sweep

**What changed**
- Standardized table rendering across Ops/Staff Console/Appointments by wrapping Bootstrap tables in `.lm-table` containers.
- Standardized card styling by adding `.lm-card` to Bootstrap cards.

**Acceptance checks**
- Ops pages with lists (orders, sellers, webhooks, failed emails, reconciliation, queues) render with rounded `.lm-table` containers and remain responsive.
- Staff Console dashboard cards render with consistent shadows.

---

## 2026-02-16 - Pack BO - Dead-end audit sweep ✅

### What changed
- **Coming Soon** page now links to a real **Waitlist** flow (no `href="#"` dead-end).
- Added **WaitlistEntry** model + admin (read-only list).
- Added `core:waitlist` route + `core/waitlist.html` template.
- Added `templates/partials/empty_state.html` and upgraded key empty states to include clear next actions:
  - Cart empty → Browse products
  - Product search/filters empty → Clear filters
  - Orders empty → Shop local
  - Category empty → Browse categories
- Fixed **core/views.py** accidental duplicate `healthz()` definition that previously overwrote the JSON health payload.

### Acceptance checks
- `GET /healthz/` returns JSON (status/environment/version keys).
- `GET /version/` returns JSON with `version`.
- `GET /coming-soon/?feature=blog` renders without dead links; “Sign up for updates” routes to `/waitlist/`.
- `POST /waitlist/` with valid email creates a `WaitlistEntry` (or reuses existing), shows a message, and redirects back.
- Empty-state pages render with a clear CTA button.

---

## 2026-02-16 - Pack BP - Waitlist hardening (throttle + email settings) ✅

### What changed
- Added **SiteConfig-managed waitlist controls** (so marketing/ops can toggle without code):
  - `waitlist_enabled`
  - `waitlist_send_confirmation`
  - `waitlist_admin_notify_enabled`
  - `waitlist_admin_email`
  - `waitlist_confirmation_subject` / `waitlist_confirmation_body`
- Added a central throttle rule: `WAITLIST_SIGNUP` (6/min per fingerprint) and applied it to `core.views.waitlist_signup`.
- Waitlist page now shows a friendly message if disabled (instead of silently failing).
- Optional emails:
  - Confirmation email to the signup address (if enabled)
  - Admin notification on new signup (if enabled + email provided)

### Acceptance checks
- Admin → **Site Config** shows the new Waitlist fields under Store Operations.
- `POST /waitlist/` is throttled (repeat submits can hit 429 + friendly UI message on browser flow).
- If `waitlist_enabled=False`, `/waitlist/` renders with the disabled message and no signup form.
- If `waitlist_send_confirmation=True`, new signups receive a confirmation email (best-effort / fail-silently).
- If `waitlist_admin_notify_enabled=True` and `waitlist_admin_email` set, admin receives a notification email for new signups.

---

## 2026-02-16 - Pack BQ - Smoke check fixes (legal namespace) ✅

### What changed
- Updated `core/management/commands/smoke_check.py` so the critical route list matches the current URL structure.
  - Replaced legacy `core:privacy` / `core:terms` references with `legal:privacy` / `legal:terms`.
  - Added `legal:index` as a critical route.

### Why
- The app already uses the dedicated `/legal/` app + namespace in templates/footers. The smoke check had drifted and could fail (or miss regressions) due to stale route names.

### Acceptance checks
- `python manage.py smoke_check --quiet` exits 0.
- `python manage.py smoke_check` prints all critical routes as OK (including legal pages).

---

## 2026-02-16 - Pack BR - Canonical reference routes ✅

### What changed
- Promoted the static reference pages to **canonical short paths**:
  - `/about/` (core:about)
  - `/help/` (core:help)
  - `/faqs/` (core:faqs)
  - `/tips/` (core:tips)
- Kept the legacy `/references/*` routes as **permanent redirects (301)** to preserve old links and any previously indexed URLs.
- Updated `sitemap.xml` output to list the canonical short routes.

### Why
- These pages are surfaced in the footer and are common “escape hatches” when users are stuck.
- Short, predictable URLs improve user trust and reduce friction (especially on mobile and shared links).

### Acceptance checks
- Visiting `/references/help/` redirects (301) to `/help/`.
- Footer links for About/Help/FAQs/Tips still work.
- `GET /sitemap.xml` includes `/help/`, `/faqs/`, `/tips/`, `/about/`.


## 2026-02-16 - Pack BS - Empty states + Support pathway consistency ✅

### Done
- Enhanced `templates/partials/empty_state.html`:
  - Supports `action_route` / `secondary_route` and optional `show_support_links`.
- Added Contact page:
  - `/contact/` (`core:contact`) with form (best-effort email) and mailto fallback.
  - Uses `SiteConfig.support_email` (fallback to `waitlist_admin_email` if blank).
- Added `SiteConfig.support_email` + migration `core/migrations/0027_siteconfig_support_email.py`.
- Updated UI to avoid dead-ends:
  - Seller dashboards, appointment lists, and ops queues now use the shared empty-state component.
  - Navbar + footer now include Contact and consistently point to canonical `/about/`, `/help/`, `/faqs/`, `/tips/`.

### Acceptance checks
- `python manage.py migrate` applies `0027_siteconfig_support_email` cleanly.
- Admin: SiteConfig shows Support Email field and saves.
- Dashboard: Admin Settings page shows Support Email and saves.
- `/contact/` loads, validates, and shows success/error messages as expected.
- Empty lists (seller payouts, ops queues, appointment lists) show a CTA + Help/FAQs/Contact where appropriate.

---

## 2026-02-16 - Pack BT - Empty-state standardization sweep ✅

### What changed
- Replaced remaining “plain text” empty states with the shared component: `templates/partials/empty_state.html`.
- Standardized CTAs so users always have a next step (Browse / Create / Help / Contact) instead of hitting dead ends.

### Updated areas
- Admin dashboard: Top sellers + analytics empty states.
- Consumer dashboard: orders empty state.
- Favorites: favorites + wishlist empty states.
- Notifications inbox: empty state.
- Seller orders list: empty state.
- Payouts dashboard: empty state.
- Seller listings + seller shop: empty states.
- Top sellers page: empty state.
- Q&A + Reviews tabs: empty states.
- Category list: empty states.

### Acceptance checks
- Visit each page with no data and confirm the UI shows a consistent empty-state card with a CTA and (where applicable) Help/FAQs/Contact links.
- Template compilation remains clean: `python manage.py smoke_check` exits 0.

## 2026-02-16 - Pack BU: Contact form inbox + SiteConfig controls

**Done**
- Added ContactMessage inbox model stored in DB (optional toggle).
- Added SiteConfig toggles for Contact form enablement, storage, email send, admin notify, and auto-reply.
- Added CONTACT_SUBMIT throttle rule (6/min).

**Acceptance checks**
- Contact page respects SiteConfig.support_form_enabled.
- Submitting contact form stores ContactMessage (when enabled) and shows success message.
- Admin can view ContactMessage list and mark resolved.

## 2026-02-16 - Pack BV: Staff Console Support Inbox

**Done**
- Added Staff Console Support Inbox list + detail pages for `core.ContactMessage`.
- Staff Console dashboard shows open support count and recent support messages.
- Staff can mark resolved/reopen from detail page with audit log entries.

**Acceptance checks**
- `/staff/` shows Open Support Messages count and Recent Support Messages table.
- `/staff/support/` supports filtering (open/resolved/all), searching, and pagination.
- Detail page supports mailto reply and mark resolved / reopen (audit log written).

---

## 2026-02-16 - Pack BW: Support ops hardening (templates + internal notes + SLA tags)

**Done**
- Added triage fields to `core.ContactMessage`: `sla_tag`, `internal_notes`, `last_responded_at/by`, `response_count`.
- Added staff-facing canned responses: `core.SupportResponseTemplate` (admin-managed).
- Staff Console Support Inbox now supports:
  - SLA filtering
  - Triage edit (SLA + internal notes) with audit log
  - Sending replies from the console (best-effort email) with optional auto-resolve
  - Reply metadata (last reply + count)
- Added audit verb(s):
  - `contact_message_triage_updated`
  - `contact_message_reply_sent`

**Acceptance checks**
- `python manage.py migrate` applies `0030_support_inbox_hardening` cleanly.
- Admin: Support Response Templates can be created/edited and marked active.
- Staff Console:
  - Inbox filters by SLA + status.
  - Detail page can save triage notes and SLA.
  - “Reply from console” sends an email (best-effort) and increments reply count.
  - Optional “mark resolved after sending” works and is audited.

---

## 2026-02-17 - Pack BX: Outbound support email logging

**Done**
- Added `core.SupportOutboundEmailLog` to record outbound emails sent from the Staff Console Support Inbox.
- Staff Console now logs each “Reply from console” attempt with status (`sent` / `failed`) and error text (if any).
- Support message detail page shows the most recent 10 outbound email log entries.
- Admin has a read-only `SupportOutboundEmailLog` list for reconciliation.

**Acceptance checks**
- `python manage.py migrate` applies `0031_support_outbound_email_log` cleanly.
- Staff Console: sending a reply creates an outbound log row (even if email backend fails).
- Detail page shows Sent/Failed badge and error text when failed.


## Pack BX Hotfix - Admin dashboard analytics enum mismatch (2026-02-17)
- Fixed ProductEngagementEvent enum references in `core/admin.py` and `dashboards/views.py` (use `Kind` + `kind` field; removed stale `EventType`/`event_type`).
- Symptom fixed: `/admin/` AttributeError: `ProductEngagementEvent` has no attribute `EventType`.

### Acceptance checks
- Visit `/admin/` loads without error.
- Seller analytics page loads and engagement counts render.


## Pack BX Hotfix - Admin dashboard top-products revenue query (2026-02-17)
- Fixed stale OrderItem field reference in `core/admin.py` top-products aggregation:
  - replaced `unit_price_cents` with snapshot-safe totals (`line_total_cents`) and quantity sum.
- Symptom fixed: `/admin/` FieldError: Cannot resolve keyword `unit_price_cents`.

### Acceptance checks
- Visit `/admin/` loads without error.
- Admin dashboard “Top products by revenue” renders values.


## Pack BX Hotfix - Restore SiteConfig.free_digital_listing_cap (2026-02-17)
- Restored missing `SiteConfig.free_digital_listing_cap` field (was referenced by admin/dashboard/docs but missing from the model), causing the SiteConfig admin page to crash.
- Added model field + migration `core/migrations/0032_siteconfig_free_digital_listing_cap.py`.
- Ensured `core/admin.py` SiteConfig fieldsets include `free_digital_listing_cap` under **Commerce**.

### Acceptance checks
- Visit `/admin/core/siteconfig/1/change/` loads without FieldError.
- Admin Settings page renders the “Free digital listing cap” input.
- Seller publish gating that references `SiteConfig.free_digital_listing_cap` works (create/duplicate/publish flows).

---

## 2026-02-17 - Pack BY: RC Money Loop verification (launch check + command)

### Done
- Added a **money-loop invariant check** to `core.launch_checks.run_launch_checks()`.
  - Samples up to 100 recent **PAID** orders.
  - Verifies totals: `subtotal_cents`, `shipping_cents`, `tax_cents`, `total_cents` match recompute logic.
  - Verifies per-line ledger invariant: `marketplace_fee_cents + seller_net_cents == line_total_cents`.
- Added management command: `python manage.py money_loop_check [--limit N] [--json]`.

### Acceptance checks
- `python manage.py launch_check` includes a `money_loop` row.
- `python manage.py money_loop_check --limit 50` exits 0 on a healthy dataset.
- If you intentionally corrupt an OrderItem ledger row in dev, the command fails (exit code 2) and reports bad counts.

---

## 2026-02-17 - Pack BZ: RC gate command (rc_check)

### Done
- Added a single RC gate management command: `python manage.py rc_check`.
- `rc_check` runs:
  - `smoke_check` (supports `--checks`, `--db`, `--quiet`)
  - `launch_check`
- Intended usage:
  - Local pre-commit sanity: `python manage.py rc_check --checks --db`
  - CI/deploy gating: `python manage.py rc_check --checks --db --quiet`

### Acceptance checks
- `python manage.py rc_check --checks --db` exits 0 on a healthy environment.
- If a critical route breaks, rc_check fails with exit code 2.

---

## 2026-02-17 - Pack CA (hotfix): Listing upload category filtering + subcategory AJAX

### Done
- Updated **Category type labels** for seller UX: `GOOD` now displays as **Products**.
- Fixed `/catalog/api/categories/` and `/catalog/api/subcategories/`:
  - Switched to `kind=GOOD|SERVICE`.
  - Standardized JSON payload to `{ ok: true, results: [{id, text}, ...] }`.
- Seller listing form now:
  - Filters **root categories** by listing kind (Product vs Service).
  - Loads **subcategories dynamically** when a category is chosen.
  - Properly wires the form widgets with `data-category-endpoint` and `data-subcategory-endpoint`.
- Removed the stale inline JS in the listing form template and standardized on `products/static/products/seller/category_subcategory.js`.

### Acceptance checks
- Seller create/edit listing page:
  - Selecting **Product** shows only **Product** categories.
  - Selecting **Service** shows only **Service** categories.
  - After selecting a category, the **Subcategory** dropdown populates.
- API sanity:
  - `/catalog/api/categories/?kind=GOOD` returns `results`.
  - `/catalog/api/subcategories/?category_id=<root>` returns `results`.

---

## 2026-02-17 - Pack CA Sweep Fixes - Admin money totals + appointment deposit order ✅

### What was fixed
- **Orders admin aggregation**: replaced invalid DB annotation using `items__unit_price_cents` (property) with snapshot-safe `Sum(items__line_total_cents)`.
- **Appointment deposit order** (`appointments/services_booking.py`): updated `OrderItem.objects.create(...)` to use snapshot-safe fields:
  - `unit_price_cents_snapshot`, `line_total_cents`, `fulfillment_mode_snapshot`, `pickup_instructions_snapshot`
  - removed legacy args (`unit_price_cents`, `requires_shipping`, `buyer_notes`).
- **Fee rounding** for deposits now matches marketplace rounding (basis points + ROUND_HALF_UP).

### Acceptance checks
- `/admin/orders/order/` loads without FieldError and shows correct aggregated totals.
- Deposit-required appointment creates a valid `Order` + `OrderItem` and `order.recompute_totals()` succeeds.

---

## 2026-02-17 - Pack CB: Seller Onboarding Checklist ✅

### Goal
Reduce seller drop-off by making the next steps explicit and persistent.

### What changed
- Added an onboarding checklist (until complete) to:
  - Seller Dashboard (`dashboards/seller_dashboard.html`)
  - Seller Listings (`products/seller/product_list.html`)
- Checklist steps (with links): email verification, 18+ confirmation, prohibited-items acknowledgement, Stripe Connect payouts, shop name, public location, first listing.
- Added shared partial: `templates/partials/seller_onboarding_checklist.html`.
- Added supporting CSS in `static/css/site.css`.

### Acceptance checks
- Seller dashboard shows checklist until all steps are complete.
- "Fix" buttons route to Profile / Verify Email / Stripe Connect / New Listing.
- Once complete, checklist no longer appears.

---

## 2026-02-17 - Pack CE: Release Runbook + Go-Live Kit ✅

### What changed
- Added an ops snapshot command: `python manage.py ops_backup_report` (JSON or `--text`).
- Ops Runbook page now includes pre-deploy gate reminders (`rc_check`, `money_loop_check`).
- Added a complete go-live runbook: `docs/GO_LIVE_KIT.md` (Render env checklist, deploy validation, rollback plan).

### Acceptance checks
- `python manage.py ops_backup_report` runs and prints JSON.
- `python manage.py ops_backup_report --text` prints a readable report.
- `/ops/runbook/` renders and includes RC gate commands.

---

## 2026-02-17 - Pack CF: Seller Listing Mini‑Wizard + Draft Save ✅

### Goal
Reduce friction on the seller listing create/edit flow by breaking the form into steps and supporting drafts.

### What changed
- Listing form now includes a lightweight stepper:
  - Type → Category → Details → Fulfillment → Media & Publish
- Added **Save draft** mode (forces `is_active=False`) for both create and edit.
- Create flow: draft save redirects to Edit; normal save continues to Images.

### Acceptance checks
- Seller can click Next/Back to move between steps; only the active step is shown.
- Clicking **Save draft** persists the listing as unpublished.
- On create: draft save redirects to Edit; normal save redirects to Images.

---

## 2026-02-17 - Pack CG: RC Sweep Toolkit (Checklist + Dead-End Audit) ✅

### Goal
Make release-candidate validation repeatable and catch dead ends/broken links before users do.

### What changed
- Added management command: `python manage.py template_deadend_audit`
  - Scans templates for obvious dead ends: `href='#'`, `action='#'`, `javascript:void(0)`.
  - Ignores common Bootstrap toggle patterns and supports explicit opt-out via `data-lm-ignore-deadend`.
  - Supports `--strict` to fail the run when issues are found.
- Updated `python manage.py rc_check` to include `template_deadend_audit`.
  - Default behavior is **non-fatal**; pass `--deadends-strict` to gate deploy.
- Added `docs/RC_CHECKLIST.md` covering seller + buyer end-to-end QA and Money Loop verification.

### Acceptance checks
- `python manage.py template_deadend_audit` runs and reports findings without crashing.
- `python manage.py rc_check --checks --db` runs and includes the dead-end audit in its output.
- `docs/RC_CHECKLIST.md` is usable as the operational QA script for RC validation.

## Pack CH - Visual polish sweep (forms, steppers, surfaces)
- Improved global form control look (rounded corners, consistent focus ring) for `.form-control`, `.form-select`, `.form-check-input`.
- Added subtle button hover elevation and unified button radius.
- Polished cards/tables/empty states and seller listing stepper styling.
- Added optional `.lm-sticky-actions` sticky action bar for long forms and applied it to the seller listing form publish/save row.

### Acceptance checks
- Seller listing create/edit: stepper buttons show an obvious active state and the publish/save row stays accessible while scrolling.
- Form inputs (text/select/checkbox) share the same visual language and focus behavior across seller and consumer pages.

## Hotfix - Empty state template var naming
- Fixed `TemplateSyntaxError` caused by using underscore-prefixed template variables in `templates/partials/empty_state.html`.
- Replaced `{% url ... as _action_url %}` / `_secondary_url` with `action_url_resolved` / `secondary_url_resolved`.

### Acceptance checks
- `/dashboard/consumer/` renders without `TemplateSyntaxError`.
- Any empty state using `action_route` / `secondary_route` renders safely.

## 2026-02-18 - Pack CJ (RC URL reverse audit)
- Added management command `url_reverse_audit` to scan templates for literal `{% url 'route_name' %}` usage and detect stale route names early.
- Wired `url_reverse_audit` into `rc_check` after `template_deadend_audit`.
- Acceptance: `python manage.py url_reverse_audit` returns OK; `python manage.py rc_check --checks --db` includes reverse audit output.

## 2026-02-18 - Pack CN (RC checklist support tooling)

### Goal
Reduce “click → 500” regressions during RC by adding a minimal, automated flow smoke check.

### What changed
- Added `python manage.py flow_check`:
  - Creates a tiny fixture set (user/profile + categories + 1 active listing).
  - Requests key pages (products list/detail, cart, seller/consumer dashboards, seller listings, seller create).
  - Performs a basic `POST cart:add` and follows redirects.
- Updated `python manage.py rc_report` to include `flow_check` output as a component.

### Acceptance checks
- `python manage.py flow_check` runs locally and reports OK/FAIL without crashing.
- `python manage.py rc_report` includes a `flow_check` component.

## 2026-02-18 - Pack CO (RC Stripe config check + tooling fixups)

### Goal
Make RC checks trustworthy and reduce Stripe go-live surprises.

### What changed
- Added `python manage.py stripe_config_check` (Stripe keys + webhook route reversal for `orders:stripe_webhook` and `payments:stripe_connect_webhook`).
- Fixed `rc_check` implementation (was broken due to a malformed try/except block around audits).
- Extended `url_reverse_audit` to support `--json`, `--limit`, and `--quiet` so `rc_report` can aggregate results reliably.
- Updated `rc_report` to:
  - call `rc_check --json`
  - include `stripe_config_check` as a component
- Added `docs/RC_RESULTS_TEMPLATE.md` for recording manual RC outcomes.

### Acceptance checks
- `python manage.py stripe_config_check` prints key/webhook status and does not crash.
- `python manage.py rc_check --checks --db` runs cleanly and outputs a summary.
- `python manage.py rc_report --json` produces valid JSON (no missing command arguments).

## 2026-02-19 - Pack CP (RC checklist manual run support)

- Pack CS: Standardized S3 bucket key to `AWS_S3_MEDIA_BUCKET` across checks/docs (kept `AWS_STORAGE_BUCKET_NAME` as legacy alias). Fixed reCAPTCHA launch checks to use v3 key names.
- Pack CT: Added `first_live_validate` management command to combine server-side `post_deploy_check` with optional public HTTP checks, and updated go-live/post-deploy docs.
- Pack CU: Added `scripts/render_start.sh` and `RUN_MIGRATIONS_ON_START` toggle (blueprint defaults to manual migrations), plus `runtime.txt` pin and doc alignment.
- Pack CV: Added a SiteConfig-driven **checkout kill switch** (`checkout_enabled` + message), enforced at `orders:checkout_start`, surfaced in cart/order UI, and exposed in Dashboard Admin Settings for emergency rollback without disabling browsing.
- Pack CW: Fixed first-live/public health checks to match `/healthz/` payload (`status:"ok"`) and added `/version/` checks (also added `core:version` to `smoke_check` and removed duplicate healthz route from `core.urls`).


### Goal
Make it easy to record each manual RC run in a consistent, timestamped log.

### What changed
- Added `python manage.py rc_results_init` to generate a timestamped RC results log file from `docs/RC_RESULTS_TEMPLATE.md`.
  - Output default: `docs/rc_runs/rc_results_<env>_<YYYYMMDD_HHMMSS>.md`
  - Options: `--env local|staging|prod`, `--outdir`, `--name`
- Updated `docs/RC_CHECKLIST.md` to reference `rc_results_init` as an optional first step.

### Acceptance checks
- `python manage.py rc_results_init --env local` creates a new markdown file under `docs/rc_runs/`.
- Refuses to overwrite an existing file.


## 2026-02-19 - Pack CQ (Render Blueprint + deploy doc alignment)

### Goal
Make the Render production deploy path less error-prone by providing a blueprint and ensuring docs match the real settings module.

### What changed
- Added `render.yaml` (Render Blueprint) to scaffold a Render web service + database with sane defaults.
- Updated `docs/DEPLOY_RENDER.md` to reflect the real production settings module (`config.settings.prod`) and current host/origin lists.

### Acceptance checks
- `render.yaml` exists at repo root and can be imported into Render as a blueprint.
- `docs/DEPLOY_RENDER.md` references `DJANGO_SETTINGS_MODULE=config.settings.prod`.


## 2026-02-19 - Pack CR (Post-deploy validation command)

### Goal
Add a lightweight, repeatable post-deploy verification command to reduce “first-live” surprises.

### What changed
- Added `python manage.py post_deploy_check` (settings/env sanity, DB connectivity ping, staticfiles signal, optional public HTTP `/healthz/` check).
- Updated `docs/GO_LIVE_KIT.md` and `docs/POST_DEPLOY_CHECKLIST.md` to include the command.

### Acceptance checks
- `python manage.py post_deploy_check` runs locally without crashing.
- With `--base-url https://example.com`, it attempts `/healthz/` and fails clearly if unreachable.

## 2026-02-20 - Pack CX - Environment banner + Stripe test-mode safety

- Added SiteConfig environment banner fields: `environment_banner_enabled`, `environment_banner_text`.
- Added `core.context_processors.env_banner` and included banner partial sitewide.
- Added auto-warning banner when `DEBUG=False` and Stripe secret key starts with `sk_test_` to prevent accidental live launch misconfigurations.

## 2026-02-20 - Pack CY - Env var audit + docs alignment

- Added `python manage.py env_audit` (with optional `--strict`) to report missing required/recommended environment variables.
- Updated `.env.example` to include email + S3 keys and to align naming with settings/checks.
- Added `docs/ENV_VARS.md` as the canonical env variable reference.
- Fixed deploy/go-live docs to use correct variable names (e.g., `DJANGO_SECRET_KEY`, `STRIPE_PUBLIC_KEY`).

## 2026-02-20 - Pack CZ - Prod host/origin env config

- Updated `config/settings/prod.py` to derive `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and cookie domain from `PRIMARY_DOMAIN` (plus optional `RENDER_EXTERNAL_HOSTNAME`).
- Updated Render blueprint + `.env.example` + docs to match (removed direct `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` env requirements).
- Updated `python manage.py env_audit` to require `PRIMARY_DOMAIN` when `DEBUG=False`.

