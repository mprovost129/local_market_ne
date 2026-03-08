## 2026-02-18 — RC reporting

- Decision: Add `rc_report` as a convenience wrapper to summarize RC readiness across multiple checks.
- Rationale: reduces “works on my machine” drift by standardizing the same preflight checks before deploy.
- Note: Stripe checkout/webhook flows remain a manual RC checklist item (cannot be fully automated without Stripe events).


## 2026-02-18 — Templates must not hard-crash on missing route names

- For optional CTA routes in shared partials, use `{% url name as var %}` and render only when `var` is non-empty.
- This prevents `NoReverseMatch` runtime crashes when route names evolve during late-stage refactors.

---

## 2026-02-17 — Listing Form UX: Kind-aware sections

Seller listing create/edit UI must only display fields relevant to the selected listing kind (Product vs Service).
Implementation uses template `data-kind` wrappers + JS toggling (hide + disable inputs). This prevents confusion and reduces invalid submissions.


## 2026-02-17 — Browse UX: Category sidebar filter/search

Decision:
- Provide a lightweight, client-side category filter/search on browse pages (desktop sidebar + mobile offcanvas) to reduce friction when category lists are long.

Implementation:
- Adds a collapsible search input in `products/_category_sidebar.html` and a tiny JS helper `static/js/category_filter.js`.
- Filter is purely UI (no new server endpoints) and never changes URLs; it only hides/shows category links.


## Dashboard Settings are Source of Truth (No Django Admin Required)

- The Dashboard Admin Settings page must be able to edit every `SiteConfig` setting reliably.
- `SiteConfig` cache must be invalidated on every save (via model save + post_save signal).
- UI-only helper fields (CSV, repeated rows) must be translated in the form `save()` method.

# Local Market NE — DECISIONS

## 2026-02-16 — Pack BL — Avoid duplicated sidebar JS

Decision:
- Do not load legacy HC3 sidebar scripts globally in `base.html`.
- Storefront sidebar filtering + “More/Less” behavior is handled in one place (`partials/sidebar_store.html`) to avoid dueling listeners and hard-to-debug UI state.

Rationale:
- Previous iterations had overlapping sidebar scripts (`sidebar.js` + `sidebar_filter.js` + inline scripts) that could conflict.
- Centralizing the behavior reduces regressions and keeps the sidebar deterministic.


## 2026-02-16 — Pack BH — Smoke check extras are opt-in

- `smoke_check` remains lightweight by default (route reverse + template compile only).
- Optional flags enable deeper validation when needed:
  - `--checks` runs Django system checks.
  - `--db` performs a tiny ORM ping to confirm migrations/tables exist.
- Smoke-check route names must match the **current** URL namespaces (e.g., legal pages live under the `legal:` namespace).
- Rationale: keep the default command fast for frequent use, while providing stronger signals during RC hardening and deploy verification.

## 2026-02-16 — Pack BI — Public health endpoint is lightweight

Decision:
- Provide a public `/healthz/` endpoint that is safe for Render/uplink checks and uptime monitors.
- The endpoint is intentionally lightweight: no external calls and no DB dependency by default.
- `healthz` is included in `smoke_check` critical routes to catch broken URL wiring.

Rationale:
- Hosting providers often need a stable health endpoint; keeping it lightweight avoids false negatives during DB maintenance.
- Smoke-check coverage prevents regressions where the endpoint is accidentally removed.

## 2026-02-16 — Crawl protection for private areas (Pack BF)

Decision:
- Private areas must be protected from indexing using both layers:
  - `robots.txt` disallows `/admin/`, `/ops/`, `/staff/`, `/dashboard/`, and `/accounts/`.
  - Responses under those paths emit `X-Robots-Tag: noindex, nofollow` for HTML pages.
Rationale:
- Robots.txt is advisory and can be ignored; the response header provides an additional safety net.
- Prevents accidental indexing of operational pages and authenticated dashboards.

## 2026-02-16 — Required RC smoke check command (Pack BG)

Decision:
- A fast, local smoke test command (`python manage.py smoke_check`) is the required first step of RC validation.
- The smoke check must validate (a) critical named routes reverse, and (b) key templates compile.
Rationale:
- Recent RC issues were caused by template/runtime dead-ends (missing keys, invalid template expressions, schema drift).
- A lightweight command catches these regressions immediately without needing external services.

## 2026-02-16 — Launch Check: security posture checks (Pack BE)

Decision:
- Launch Check is the authoritative go-live gate and now includes explicit **security posture** validation when `DEBUG=False`:
  - `SECURE_SSL_REDIRECT`
  - `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE`
  - `SECURE_PROXY_SSL_HEADER` (proxy/load balancer environments)
  - Email backend must not be a dev backend (console/locmem/filebased)
- In `DEBUG=True`, Launch Check warns when cookie domains are set (common localhost session breaker).
Rationale:
- These settings are easy to overlook and materially affect authentication, session integrity, and HTTPS correctness in production.
- Explicit checks prevent “looks fine locally” misconfigurations from reaching production.

## 2026-02-16 — Reconciliation CSV exports

- Ops reconciliation exports are provided as CSV via `?format=csv`.
- Exports are **capped at 5,000 rows** to avoid large downloads impacting production.
- CSV includes snapshot + ledger totals and mismatch flags for quick ops triage.


Last updated: 2026-02-16 (America/New_York)


## 2026-02-16 — Buyer delivery confirmation rules (Pack AY)
Decision:
- Buyers can confirm fulfillment for physical items:
  - **Shipping** items: confirm after seller marks **SHIPPED**.
  - **Pickup/Delivery** items: confirm after seller marks **READY**.
- Guest access is supported via the existing `order_token` (`t` accepted on POST and GET).
- Buyer confirmation is throttled (server-side) to protect from abuse.
Rationale:
- Keeps fulfillment closure aligned with real-world receipt while preserving low-friction guest access.
- Throttling provides abuse resistance without introducing CAPTCHA friction.


## 2026-02-16 — Ops “Money Loop” KPIs use ledger + refund snapshots (Pack AW)
Decision:
- Ops dashboard “Money Loop” tiles are computed from:
  - `OrderItem.marketplace_fee_cents` and `OrderItem.seller_net_cents` for **PAID** orders (ledger truth), and
  - `RefundRequest.total_refund_cents_snapshot` for status **REFUNDED** (refund truth).
- Do **not** derive fees/net from order totals or current SiteConfig settings.
Rationale:
- Ledger fields are snapshotted at order creation and remain historically correct when fees/settings change.
- RefundRequest snapshot totals are the authoritative “what was refunded” numbers.


## 2026-02-16 — Seller fulfillment tasks use `is_done` (hotfix)
Decision:
- The canonical completion flag on `SellerFulfillmentTask` is `is_done`.
- Views/templates must not reference legacy names like `is_completed`.
Rationale:
- Prevents FieldError crashes and keeps task completion semantics consistent across the app.


## 2026-02-16 — Fulfillment task lifecycle is tied to payment + delivery (Pack AX)
Decision:
- `SellerFulfillmentTask` rows are created when an order is marked **PAID** (idempotent).
- A task represents a single seller-owned `OrderItem` that requires fulfillment.
- Tasks are marked done when the item reaches a terminal state: **DELIVERED** (or **CANCELED**).
Rationale:
- Prevents “missing tasks” after payment and keeps seller dashboards aligned with real work.
- The per-item model avoids ambiguity when a single order contains items from multiple sellers.


## 2026-02-16 — Public seller location is approximate (Pack AU)
Decision:
- Seller storefronts may show an **approximate** public location (city/state) via `Profile.public_city` / `Profile.public_state`.
- Exact seller address remains private and is never required for storefront browsing.
- Service providers may optionally set `service_radius_miles` as **informational** buyer guidance in v1 (not hard-enforced).
Rationale:
- Buyers need a sense of “where” without exposing sensitive data.
- Keeps v1 free of geo/dependency complexity while supporting a future true-radius filter.



## 2026-02-16 — Funnel reporting basis (Pack AM)
- Funnel reporting supports both:
  - **Event-based** counts (can double-count within a session), and
  - **Unique-session** funnel (preferred for conversions) based on first-party `hc_sid` → `AnalyticsEvent.session_id`.
- Host/environment breakouts are included to detect environment drift (e.g., paid events appearing only in prod).

## 2026-02-15 — Observability: DB-backed error capture (v1)
Decision:
- LocalMarketNE captures unhandled server exceptions into a DB model (`ops.ErrorEvent`) instead of requiring an external service.
- Capture includes: request id, path, method, user (if authenticated), exception type, short message, and a compact traceback.
- Ops Console provides a triage queue: list, detail, and “mark resolved” with required notes.
- Resolution actions are audited via Ops Audit Log.
Rationale:
- Provides a production-grade “control tower” for incidents with minimal dependencies.
- Keeps troubleshooting grounded to concrete request ids and stack traces.
Guardrails:
- Traceback/message are truncated to prevent unbounded storage.
- Admin registrations must not reference models that are not defined in `models.py` and migrated; model/admin/migration changes ship together in the same pack.


## 2026-02-14 — reCAPTCHA v3 enforcement for public write actions (v1)
Decision:
- reCAPTCHA v3 is enforced server-side on **POST** for the highest-risk public write actions:
  - account registration
  - reviews (create / seller review / reply)
  - product Q&A (thread create / reply / report)
- UX wiring is standardized via a base template helper: forms opt-in via `data-recaptcha-action` and include a `recaptcha_token` hidden input.
- UX safety guardrails: a small global UI helper (`static/js/ui.js`) disables submit buttons on form submit to prevent accidental double-submits (double posts / double charges). Rare multi-submit forms may opt out via `data-no-disable-submit="1"`.
- If keys are not configured, the verification layer **fails open** (logs a warning) to avoid blocking checkout/dev environments.
Rationale:
- Cuts automated spam/abuse without adding visible friction (v3 score-based). Standard wiring prevents “one-off” template drift.


## 2026-02-13 — Legal acceptance recording (v1)
Decision:
- On checkout, LocalMarketNE records acceptance of the latest published: Terms, Privacy, Refund Policy, and Content & Safety Policy.
- If a cart includes service items, checkout also records acceptance of the Services & Appointments Policy.
- Seller Stripe Connect onboarding requires explicit Seller Agreement acceptance before the onboarding link is generated.
Rationale:
- Keeps a durable audit trail tied to exact document versions (hash-based), while minimizing UX friction.


## 2026-02-13 — Appointment rescheduling + notifications (v1)
Decision:
- Appointment rescheduling is **seller-driven** in v1 (seller can set new scheduled start; end derived from duration snapshot).
- All appointment lifecycle transitions emit **in-app notifications + email** via the central `notifications.services.notify_email_and_in_app` helper.
Rationale:
- Keeps a single audit trail (Notification records) even if email fails; reduces duplicated email logic.


## 2026-02-16 — Email delivery attempts + Ops resend tooling
Decision:
- Track outbound email send attempts in the database (`notifications.EmailDeliveryAttempt`) linked to the originating `Notification`.
- Ops may resend an email using the stored rendered bodies on the `Notification` (subject/text/html), which records a new attempt.
Rationale:
- Provides auditability and a concrete failure queue without relying on external provider dashboards.
- Resend is deterministic (uses stored rendered content) and safe (records attempts; does not mutate historical notification content).


## 2026-02-13 — Fulfillment and off-platform payment decisions (LocalMarketNE)
### ZIP-only delivery radius enforcement (v1)
Decision:
- For v1, delivery radius enforcement is **ZIP-only** with a conservative approximation:
  - Delivery requires buyer ZIP present.
  - If seller ZIP and buyer ZIP share the same first **3 digits**, delivery is allowed.
  - Otherwise, delivery is blocked when a seller radius is set (>0), pushing buyers to pickup or shipping.
Rationale:
- Avoids external geocoding dependencies while preventing obviously out-of-area delivery selections.
Follow-up:
- Replace with true distance calculation (geocoding/ZIP centroid) if traction warrants.

### Shipping tracking data
Decision:
- Shipping tracking is stored per **OrderItem** (`tracking_carrier`, `tracking_number`, `shipped_at`, `delivered_at`) and entered by the seller.
- Buyer sees tracking when the item is marked shipped.


## Data and performance
### 1) Card ratings via annotations
Decision:
- Use queryset annotations (`avg_rating`, `review_count`) for lists.
Reason:
- Avoid N+1 queries and keep pages fast.

### 2) Trending badge normalization rule
Decision:
- Templates ONLY check `p.trending_badge`.
Reason:
- Prevent drift across home/browse/detail templates.

Implementation:
- Home: `p.trending_badge = is_trending OR (id in computed_home_trending_ids)`
- Browse: `p.trending_badge` should be driven by a consistent subset rule (top N and/or score threshold), not “everything in trending sort”.

### 3) Trending computation uses engagement events
Decision:
Trending signals include:
- Paid purchases (highest weight)
- Add-to-cart (strong intent)
- Reviews (velocity)
- Views (weak, day-1 realism)
- Avg rating (quality, low weight)

Reason:
- Day-1 trending needs signals even without sales volume.

### 4) Trending tie-breakers prioritize quality
Decision:
When trending_score ties:
- sort by `avg_rating` then `created_at`
Reason:
- Trending should not promote junk when the score is tied.

### 5) Top Rated has a minimum review threshold + fallback
Decision:
- Require `MIN_REVIEWS_TOP_RATED` (currently 3).
- If none meet threshold, fall back to best early ratings and show a warning banner.
Reason:
- Prevent a single review from dominating early and keep browse pages populated.

### 6) Engagement logging is “best effort”
Decision:
- Engagement logging must never block core flows.
Reason:
- Analytics is optional; purchase flow is not.

Implementation:
- cart_add logs ADD_TO_CART inside try/except
- product_detail logs VIEW inside try/except with session throttling

# docs/DECISIONS.md

# Local Market NE — Decisions (Locked + Current)

Last updated: 2026-02-13 (America/New_York)

## Email verification gating (LOCKED)
- Users must verify email before: posting Q&A, starting seller Stripe onboarding, or leaving reviews.
- Unverified users can still browse the marketplace and manage their profile.

## Notifications rendering (LOCKED)
- All emails also create in-app notifications.
- Notifications are categorized by type (verification, refund, password, etc.).
- In-app notification detail should resemble the email that was sent.
- Implementation: store rendered email bodies (`Notification.email_text`, `Notification.email_html`) at send time and render an "Email view" tab when available.


## Free service giveaways cap (LOCKED)
- Non-Stripe-ready sellers may have at most **SiteConfig.free_digital_listing_cap** active FREE service FILE listings (default **5**).
- Enforcement occurs at **activation** time (draft-first remains soft until activation).

## orders counting (LOCKED)
- orders are counted at the **product/bundle** level via `Product.order_count`.
- Per-asset orders counts may exist, but Seller Listings displays bundle-level orders.

## Tips & Tricks content (LOCKED)
- Tips & Tricks lives under Navbar → References.
- Tips & Tricks is a static page for now; it will be migrated into the Blog later.

## Seller Listings units sold (CURRENT)
- Units sold displayed to sellers is **net**: paid quantity minus refunded physical line items (RefundRequest status=refunded).


This file records decisions that govern implementation and must not be silently changed.

---

## Payments / Money Handling

### Snapshot-based accounting (LOCKED)
- **Fees/settings are snapshotted at order creation** to preserve historical correctness.
- `Order.marketplace_sales_percent_snapshot` is the source of truth for marketplace fee rate at the time of purchase.
- `OrderItem` stores per-line ledger:
  - `marketplace_fee_cents`
  - `seller_net_cents`
- Legacy flat platform fee snapshot field remains present but is **not used** and must remain **0**.

### Stripe Connect readiness gates (LOCKED)
- A seller is “ready” only if:
  - `stripe_account_id` exists AND
  - `details_submitted`, `charges_enabled`, `payouts_enabled` are all true.
- Owner/admin bypass is treated as ready.
- Listings creation/modification is gated behind Connect readiness.

### Webhooks separation (LOCKED)
- Checkout/order webhooks (orders side) are separate from Stripe Connect account update webhooks (payments side).
- Connect webhook endpoint must use a **separate** signing secret: `STRIPE_CONNECT_WEBHOOK_SECRET`.

---

## Orders / Access Control

### Guest checkout access (LOCKED)
- Guest orders are accessed by token query string `?t=<order_token>`.
- Guest orders links and guest refund detail access must validate token against `order.order_token`.

### Guest paid email with orders (CURRENT)
- On `Order.mark_paid()`, if order is guest and has service items, send a best-effort email that includes:
  - tokenized order detail link
  - tokenized orders links per service asset
- Email send failures are non-fatal (best-effort).

---

## Refunds (LOCKED)

### Refund scope
- Refund requests are **physical-only**.
- Refunds are **full refunds per physical line item** only.
- service products are **not refundable** in v1.

### Allocation rules (CURRENT)
- Tax is allocated proportionally across all order items by `line_total_cents`.
- Shipping is allocated proportionally across shippable items (where `fulfillment_mode_snapshot == "shipping"` — exposed as `requires_shipping` property) by `line_total_cents`.
- `OrderItem.line_total_cents` is a stored ledger field; dashboards and reports should **not** annotate using the same name (Django raises an annotation conflict). If a computed expression is ever needed, use a different alias (e.g., `line_total_calc_cents`).
- Refund amount is stored as snapshots on `RefundRequest` at creation and becomes the source of truth.

### Transfer reversal controls (Pack AP)
Decision:
- LocalMarketNE uses **platform → seller transfers** (Connect) created after payment.
- When a physical line item is refunded, the system attempts a best-effort **Stripe Transfer Reversal** for the seller’s payout amount for that line item.
- The reversal amount is **`OrderItem.seller_net_cents`** (per-line ledger), so the **platform fee remains non-refundable**.
Guardrails:
- Reversal is best-effort: a successful buyer refund must not be blocked by a reversal failure.
- All reversal outcomes are recorded for ops via `OrderEvent.TRANSFER_REVERSED` (success) or `OrderEvent.WARNING` / `RefundAttempt.error_message` (failure).

### Refund authority
- Buyer/guest may create a request (subject to permissions).
- Seller decides approve/decline.
- Seller triggers Stripe refund after approval.
- Staff has a safety-valve endpoint and admin action to trigger refunds (dangerous).

### Stripe refunds mechanism (CURRENT)
- Refunds are created via Stripe Refund API referencing `order.stripe_payment_intent_id`.
- Idempotency key: `refundreq-<refund_request_uuid>`.
- Free checkouts (`payment_intent_id == "FREE"`) cannot be refunded via Stripe.

---

## Site settings rule (LOCKED)
- Any “setting” that affects behavior must be DB-backed via SiteConfig and snapshotted on Orders at creation (as applicable).
  - (This slice uses order snapshots; Connect uses env secrets; future fee/tax settings must follow this rule.)

---

# Local Market NE – Decisions (Locked + Active)

## Accounting & Historical Correctness
- Fee and payout logic must be historically correct:
  - Fee percent is snapshotted on the `Order` at creation time.
  - Seller identity is snapshotted on each `OrderItem`.
  - Do not recompute old orders using live settings.

## Stripe Connect Readiness
- Seller readiness is determined by `SellerStripeAccount.is_ready` property.
- Owner/admin bypass is treated as ready for gating and UX flows.
- Do not filter in the DB on `is_ready` because it is not a field.

## Refunds (Locked Requirements)
- Refunds are allowed only for PHYSICAL products in v1.
- Refund requests are FULL refunds per physical line item only.
- service products are never refundable in v1.
- Guest refund requests require:
  - tokenized order access (`?t=<order_token>`)
  - email confirmation equals `order.guest_email`

## Idempotency & Safety
- Refunds:
  - Stripe refund call uses idempotency key `refundreq-<refund_request_id>`.
  - Refund amount is strictly `RefundRequest.total_refund_cents_snapshot`.

## Code Organization
- Canonical seller gating decorator lives in `payments.decorators`.
- `payments.permissions` exists only as a backwards-compatible re-export to prevent import breakage.

## Favorites & Wishlist
- Favorites and Wishlist are separate models/entities.
- Both are shown on a single combined page for UX simplicity.
- Favorites/Wishlist require login AND verified email (unverified users have limited access).

## Notifications parity with email (locked)
- All user-facing emails that are sent to a **registered user** MUST also create an in-app `Notification`.
- `notifications.services.notify_email_and_in_app(...)` is the single choke point for creating the notification and sending the email.
- If an email has no explicit plaintext template, plaintext is derived from the HTML template via `strip_tags(...)`.

## Reviews (locked)
- Reviews are only by verified purchasers.
- Sellers may post a public reply to a product review (one reply per review in v1).

## orders metrics (locked)
- orders metrics are tracked and displayed at the **product (bundle)** level.
- Seller Listings for FILE products show:
  - **Unique orderers** = distinct registered users + distinct guest sessions.
  - **Total orders clicks** = `Product.order_count`.
- Guest uniqueness excludes blank session keys so missing sessions cannot inflate unique counts.
- Both free and paid orders endpoints increment these metrics (best-effort; never block orders).

## Trending badge membership (computed)
- Decision: Trending badge is limited to manual `Product.is_trending` plus computed Top N by `trending_score` where `trending_score > 0`.
- Computed membership is cached (15 min) and reused across Home and Browse for consistency.


## Seller analytics windows (7/30/90)
- Seller analytics are presented as rolling windows (last 7, 30, or 90 days).
- Refund impact for net units sold is computed using refund_request.refunded_at within the window (and paid units use order.paid_at within the window).
- orders analytics are counted at the product (bundle) level; unique orderers include distinct logged-in users plus distinct guest sessions.

- Moderation actions (Q&A): reports do not auto-hide; staff resolves reports manually. Staff may remove messages (soft delete) and suspend users via moderation queue; all actions are recorded in StaffActionLog.

- Moderation UX: staff can filter Q&A reports by status (open/resolved/all). Product Q&A tab shows staff-only open reports count badge. Suspended users review list is available to staff; suspensions remain recorded in StaffActionLog.

- Moderation UX: staff can unsuspend users from the suspensions review page; unsuspension is recorded in StaffActionLog. Product Q&A threads show staff-only per-message open-report count badges.

## Launch hardening (observability + abuse controls)
- All high-value/abuse-prone GET endpoints (orders) are throttled via core.throttle(throttle_rule, methods=("GET",)).
- Every request gets a request id (X-Request-ID) and logs include rid/user_id/path for traceability.

## Webhook reliability + ops visibility (2026-02-09)
- Stripe webhooks must be **idempotent** (StripeWebhookEvent) and **observable** (StripeWebhookDelivery).
- After signature verification, **internal processing exceptions return HTTP 500** so Stripe will retry. Failures are logged in StripeWebhookDelivery with request_id.
- Refund triggers must be logged with `refunds.RefundAttempt` so staff can diagnose misconfig/Stripe errors without digging through logs.

## Migration hygiene (2026-02-10)
- Do not change primary key types for already-shipped tables via migrations (UUID↔bigint casts are brittle and commonly fail).
- `orders.StripeWebhookDelivery` is treated as append-only ops logging; schema uses `delivered_at` (and references `StripeWebhookEvent.created_at`).
- If local dev migration history becomes inconsistent (e.g., a downstream app migration is marked applied before its dependency), the supported recovery is: **drop/recreate the local DB and rerun migrations**.

## 2026-02-10 — Analytics provider
- Google Analytics 4 is the active analytics provider (Plausible deprecated).
- Client-side tracking uses GA4 Measurement ID from environment variable `GOOGLE_MEASUREMENT_ID` mapped to `settings.GA_MEASUREMENT_ID`.
- Server-side dashboard reporting (optional) uses GA4 Data API with service-account credentials provided via env (`GOOGLE_ANALYTICS_*`). If not configured, admin dashboard links out to GA.


## Native analytics (v1)
- Local Market NE uses first-party server-side pageview analytics for in-app dashboard metrics (no external analytics required).
- Analytics stores hashed IPs (salted) and session keys; no raw IPs are persisted.
- Collection is throttled and bot-filtered; retention is configurable via SiteConfig.
- External analytics (GA) may be used optionally via outbound link, but is not required for dashboard metrics.

- Seller payout UI: "Pending pipeline" is defined as PAID order items for the seller where the order has no seller-scoped TRANSFER_CREATED event yet (webhook/transfer lag visibility only; ledger remains source of truth).
- `orders.OrderEvent.meta` is used (additively) to record structured payout transfer metadata for `TRANSFER_CREATED` events: `seller_id`, `transfer_id`, `amount_cents`, and `stripe_account_id`. Legacy transfer events may lack metadata and are treated as “unknown attribution” in reconciliation surfaces.


## 2026-02-10 — Analytics dashboard linking

- GA4 Data API service-account keys may be blocked by org policy; the app must not require GA credentials to function.
- `SiteConfig.google_analytics_dashboard_url` provides an optional **Open Google Analytics** link in the admin dashboard.


## Throttling & Abuse Visibility (v1)

- Rate limiting uses cache-based throttles with a centralized rule set (`core/throttle_rules.py`).
- Throttle hits are recorded in native analytics as `THROTTLE` events for admin visibility.
- Abuse signals are informational in v1 (no auto-blocking beyond throttle).

### 2026-02-16 — Checkout / refunds throttle placement
- The checkout initiation endpoint (`orders:checkout_start`) is POST-only and is the **only** place where the checkout-start throttle + reCAPTCHA applies.
- Fulfillment-choice persistence (`orders:set_fulfillment`) is POST-only and uses a separate throttle bucket (`orders:set_fulfillment`) to avoid blocking checkout start.


## Legal docs: versioned + seeded (2026-02-10)

- Legal policies are stored as versioned `LegalDocument` rows and displayed from the latest published version.
- Seeded v1 legal docs via migration to avoid blank public pages on fresh DBs.
- Only Terms/Privacy/Refund/Content are required for “accept and continue” flows; licensing pages are informational unless later required by a specific workflow (e.g., seller onboarding).



## 2026-02-10 — Seller order ops
- Sellers must be notified for ALL paid sales (service + physical) via email + in-app notification; tips excluded.
- Physical orders create persistent SellerFulfillmentTask per seller+order; tasks close automatically when no pending shippable items remain.
- Licenses & Policies must be discoverable from global navigation (References + Footer).


## 2026-02-10 — Free service listings cap enforcement
- Sellers may publish up to `SiteConfig.free_digital_listing_cap` active FREE FILE listings without Stripe onboarding.
- Publishing beyond the cap requires **verified email** first, and **Stripe Connect onboarding** (seller readiness).
- Enforcement points: listing activation and listing duplication guard.

## 2026-02-10 — Fulfillment UX
- Seller fulfillment queue is driven by **OrderItem fulfillment_status** for physical items only; service items are excluded from shipping queue.
- Fulfillment tasks remain open until all seller shippable items in the order are no longer pending.
- Seller net units sold is computed as **paid qty − refunded qty** (refunds are full-line-item for physical items in v1).

## 2026-02-10 — SiteConfig management parity
- All `SiteConfig` fields that are editable via the custom **Dashboard Admin Settings** page must also be editable via the Django admin `core.SiteConfig` singleton admin, and vice versa.
- The dashboard settings UI is treated as a first-class admin surface; it must not lag behind Django admin field availability.

## Native analytics definitions (2026-02-11)
- Unique visitors are counted by first-party visitor cookie (hc_vid), not IP.
- Sessions are counted by first-party session cookie (hc_sid) and rotate after 30 minutes of inactivity.
- Native analytics reports can be restricted to a primary host/environment via SiteConfig to avoid mixing dev/prod traffic.

## Native analytics metric (2026-02-11)
- Active users (last 30m) is reported as distinct visitor_id values in PAGEVIEW events within the last 30 minutes (after SiteConfig filters).

## Affiliate links storage (2026-02-11)
- SiteConfig.affiliate_links remains a JSONField for flexibility, but the dashboard UI edits it via simple repeated inputs (no raw JSON entry).

## 2026-02-13 — Store sidebar category navigation
- For Walmart-style category trees, the store sidebar uses a progressive disclosure UX:
  - Root category lists show the first 8 items by default, with a **More** expander for additional roots.
  - Subcategories are hidden by default and expanded per root category using collapse toggles.
  - A hidden (collapsed) **Filter** input is available above each category section (Products/Services) to allow quick client-side searching.


## Sidebar Categories UX (Pack K)
- Root categories show first 8 by default; “More” expands the rest and toggles to “Less”.
- Sidebar remembers expansion state using `localStorage` keys:
  - `lmne.goodsCats.more`, `lmne.serviceCats.more`
- Category filter UI is hidden by default and shown via a Filter toggle; filtering is client‑side.

## 2026-02-13 — Service cancellation window enforcement
- Services may define a cancellation cutoff window in hours (`service_cancellation_window_hours`).
- If set (>0), buyers cannot cancel within that window before the appointment start time.
- Enforcement is server-side; UI may still show Cancel but will reject within window.



## Pack O (2026-02-13)
- Sidebar category UX remains: expandable subcategories + More/Less + Filter search.
- Off-platform payments: buyer can mark 'sent'; seller confirms payment received via dedicated Payments queue.
- Service deposits are always collected via Stripe when required.

### 2026-02-13 — Shipping tracking fields (Pack P re-apply)
- Canonical per-line tracking fields are `OrderItem.tracking_carrier` and `OrderItem.tracking_number`.
- Legacy `OrderItem.carrier` is removed (migration 0005) and should not be used in new code/templates.

## 2026-02-13 — Inventory reservation + made-to-order lead times (Pack Q)
- **Non-made-to-order goods** reserve inventory at order creation (PENDING) by decrementing `Product.stock_qty` under row locks.
- Reserved inventory is released back to stock on order cancellation or Stripe session expiration (`Order.inventory_reserved`/`inventory_released` make this idempotent).
- **Made-to-order goods** are allowed to be purchased even when `stock_qty=0`, but must specify `lead_time_days`.
- Each `OrderItem` snapshots the product’s lead time into `lead_time_days_snapshot` for buyer/seller visibility and historical accuracy.


## 2026-02-13 — Pack S re-apply (Appointments)
- Appointment lifecycle is stateful and explicit:
  - `REQUESTED → DEPOSIT_PENDING → DEPOSIT_PAID → SCHEDULED → COMPLETED`
  - `DECLINED` and `CANCELED` are terminal states.
- Deposits are collected via Stripe only. Deposit orders are normal Orders with `kind=services`.
- Appointment deposit payment is recorded by Stripe webhook:
  - On `checkout.session.completed`, any `AppointmentRequest` linked to that Order transitions from `DEPOSIT_PENDING` to `DEPOSIT_PAID` and is auto-scheduled (v1 default).
- Scheduling is snapshotted on the appointment record (`scheduled_start/end`) and is not derived from live service listing after the request is created.

## Appointments — Buyer confirmation, calendar exports, and reminders

- Seller reschedules require explicit buyer confirmation before the appointment is considered final:
  - `AWAITING_BUYER_CONFIRMATION` → buyer confirms → `SCHEDULED`.
- Calendar invites are provided as downloadable `.ics` for both buyer and seller.
- Reminder delivery is cron-driven (management command) and controlled by DB-backed SiteConfig:
  - `appointment_reminders_enabled`
  - `appointment_reminder_hours_before`

## Pack W (Ops Console)
- Ops Console is a separate internal back-office surface (`/ops/`) distinct from Django admin.
- Superusers are always OPS; non-superuser ops staff will be granted access via the `ops` Group.
- Every ops action must create an `ops.AuditLog` record (actor + verb + before/after JSON + optional target).


## Operations account model (Admin vs Ops)
- The platform uses **two operational roles**:
  - **Admin (day-to-day)**: `staff_admin` group → access `/staff/`.
  - **Ops (support / elevated)**: `ops` group → access `/ops/`.
- Superusers bypass and can access both, but day-to-day operation should be done with non-superuser accounts.
- All sensitive override capabilities remain restricted to Ops routes (and remain audited).


## 2026-02-14 — Email sending helpers live in orders/emails.py
- Email side-effects are implemented in explicit service modules (orders/emails.py) rather than inside models.
- Orders events may include STRIPE_SESSION_CREATED for observability; it is treated as informational and does not change accounting.


## 2026-02-14 — Admin Console Moderation Model Naming
- Canonical Q&A report model is `ProductQuestionReport` (do not introduce aliases like `QAReport` in code; import the canonical model or alias locally only).
- Resolution updates must write `resolved_at` + `resolved_by` and never depend on an `updated_at` field.


## Age gating (18+) (locked v1)
- (Legacy) Buyer age gate was controlled via `require_age_18`/`age_gate_text`. Pack BK removes buyer gating; seller onboarding uses `seller_requires_age_18` + Profile confirmations.
- Authenticated buyers must confirm 18+ in Profile before placing orders.
- Guest checkout requires an explicit 18+ checkbox at checkout.
- Categories can be marked `requires_age_18` for future per-category enforcement; v1 enforces sitewide 18+ at checkout.


## Prohibited items enforcement (Pack Z)
- Category policy flags are enforced at multiple layers: cart add/prune, order creation, and checkout start.
- Prohibited categories block checkout regardless of prior order creation (defense-in-depth).
- Staff may re-categorize or deactivate listings via Staff Console; all changes require a reason and are audit logged.

## Pack AA Decisions (2026-02-15)
- Keep email verification resend reachable via a stable POST-only alias URL (`/accounts/verify-email/resend/`) to avoid broken historical links.
- Ops health surfaces live under ops namespace and are **ops-only** (`/ops/health/`).
- Platform exposes minimal `/healthz/` and `/version/` endpoints for hosting health checks and deploy verification.


## Pack AB Decisions (2026-02-15)
- Ops Audit Log is the system of record for staff/ops actions; all non-read operations in staff/ops surfaces must write an AuditLog entry.
- Audit log must be exportable (CSV) with filters (date range, actor, action, verb, search) for operational reconciliation.


## Ops runbook and backup posture
- Ops Runbook lives at `/ops/runbook/` and is the canonical incident/backup checklist for v1.
- Backups are treated as an ops responsibility: DB backups (managed provider) + media strategy (S3 versioning/lifecycle recommended).
- Ops health check (`/ops/health/`) is used for post-deploy smoke validation.

## Pack AD Decisions (2026-02-15)
- Public browse endpoints must **paginate by default**; never render unbounded product/seller querysets.
- Untrusted GET inputs are clamped:
  - `q` max length 200
  - `per_page` max 60
  - `page` coerced to >= 1
- Anonymous browse pages may use **short HTML caching** (60 seconds) keyed by `path + querystring`.
  - Authenticated users bypass this cache.


## Maintenance mode + Announcement controls — 2026-02-15
- Maintenance Mode is a **SiteConfig toggle** (DB-backed, editable via admin).
- Maintenance Mode returns HTTP **503** for public visitors to discourage indexing and communicate downtime.
- OPS and Staff Admin bypass maintenance gating so they can verify the site during incidents.
- Site Announcement is a separate toggle + text (also SiteConfig) and renders below the promo banner.

## Pack AF — Financial reconciliation is snapshot-based (non-mutating)
- Ops reconciliation compares **Order.subtotal_cents** against **sum(OrderItem.quantity * unit_price_cents_snapshot)** and compares item-ledger fee/net sums against **expected fee/net computed from marketplace_sales_percent_snapshot**.
- Reconciliation pages are **read-only** in v1: they surface mismatches and missing Stripe markers but do not auto-rewrite financial fields.
- Transfer presence is inferred via OrderEvent.Type.TRANSFER_CREATED; if payouts were skipped for unready sellers, we do not flag as missing transfer.

## 2026-02-15 - Documentation as an operational artifact
- `docs/USER_MANUAL.pdf` is the authoritative, shippable user manual for LocalMarketNE.
- When workflows, roles, permissions, or operational procedures change, **update USER_MANUAL.md first**, then regenerate USER_MANUAL.pdf.
- Manual must describe:
  - Buyer, Seller, Staff Admin, and Ops capabilities
  - System settings (SiteConfig) and enforcement points
  - Operational runbooks for incidents and reconciliation

## 2026-02-15 Hotfix
- SiteConfigAdmin fieldsets must not repeat fields across sections to satisfy Django admin checks.


## Pack AH — Orders invariants & Stripe consistency (2026-02-15)
- Once an order leaves `DRAFT`, its key financial fields are **immutable** (subtotal, tax, shipping, total, currency, fee snapshots).
- Order status changes must follow explicit **transition guardrails** to prevent accidental jumps.
- Stripe-paid orders must have **both** `stripe_session_id` and `stripe_payment_intent_id` recorded before becoming `PAID`.
- Tips are stored as separate `OrderItem` rows (`is_tip=True`) and bypass marketplace fees.

## 2026-02-15 — Launch Readiness Checks

- We treat “launch readiness” as a **conservative checklist** (failures = do not go live).
- The same checks are available in two forms:
  - Human-facing Ops UI (`/ops/launch-check/`)
  - CLI command (`python manage.py launch_check`) for CI/deploy automation.
- Checks validate configuration and core invariants; they do not mutate data.

### Pack BY — Money loop is a release blocker
- `launch_check` includes a **money_loop** invariant check over a bounded sample of recent PAID orders.
- A dedicated CLI exists for deeper verification: `python manage.py money_loop_check`.
- If money-loop invariants fail, treat it as a **release blocker** until reconciled/fixed.

### Pack BZ — RC gate command
- We provide a single pre-deploy gate command: `python manage.py rc_check`.
- `rc_check` bundles:
  - `smoke_check` (optionally `--checks` and `--db`)
  - `launch_check`
- CI/deploy pipelines should prefer `rc_check` over running multiple commands manually.

## 2026-02-16 — Pack AK — Funnel Metrics are first-party + server-side

- Conversion funnel metrics are tracked via our own `analytics.AnalyticsEvent` table (not client JS), so they still work under ad blockers.
- Funnel event types (v1):
  - `ADD_TO_CART` (logged on cart add, throttled per session+product)
  - `CHECKOUT_STARTED` (logged on checkout start, throttled per session+order)
  - `ORDER_PAID` (logged when Stripe webhook marks an order paid; system event)
- Ops Console is the source of truth for quick visibility: `/ops/funnel/?days=7`.


## 2026-02-16 — Pack AL — Ops Reprocessing & Transfer Retry (Decisions)

- Webhook processing logic is centralized in `orders.webhooks.process_stripe_event_dict()` and used by both:
  - the inbound Stripe webhook endpoint, and
  - Ops staff reprocess actions.
- Reprocessing is treated as **idempotent**:
  - Order payment transition is guarded (`mark_paid()` no-ops if already PAID).
  - Connect Transfers use Stripe idempotency keys per order+seller.
  - Native analytics ORDER_PAID event only logs on actual order status transition (prevents double-counting).
- Every reprocess attempt creates a new `StripeWebhookDelivery` row for auditability.


## 2026-02-16 — Pack BB — Admin Ops webhook drill-down + reprocess

- Admin Ops surfaces *errors* but does not re-implement webhook debugging.
- The canonical investigation surface is **Ops → Webhooks**:
  - Admin Ops error rows link to the corresponding **Ops Webhook Event detail**.
  - Reprocessing is executed by calling the **Ops reprocess action** (same idempotent processor), not by duplicating webhook logic inside dashboards.


## 2026-02-16 — Reference pages navigation
- Reference pages are first-class v1 routes under canonical short paths (`/about/`, `/help/`, `/faqs/`, `/tips/`) and must be linked consistently in both top-nav and footer.
- Legacy `/references/*` routes remain as permanent redirects for backwards compatibility.
- Reference content remains static v1 (templates), but the URL structure is stable for future CMS/blog upgrades.

## 2026-02-16 — SEO canonical + defaults
- Canonical and share URLs must be stable and exclude querystrings (`request.build_absolute_uri(request.path)`).
- Sitewide default meta description / share image / twitter handle are DB-backed in `SiteConfig` so Ops can tune without deploys.



## 2026-02-16 — Pack AT — Browse filters UX
- **Never** use `request.GET.<key>` in templates; it raises `VariableDoesNotExist` when missing. Views must pass `q`/`category` explicitly and templates must rely on those.
- Category browsing UX standard: sidebar accordion (desktop) + offcanvas drawer (mobile), with a “More” collapse after 8 top-level categories.

## 2026-02-16 — Canonical URLs in templates
- We do **not** call request methods with arguments inside Django templates.
- Canonical + `og:url` are rendered as: `{{ request.scheme }}://{{ request.get_host }}{{ request.path }}`.

## 2026-02-16 — Service browse filters: state + radius semantics
- `state` filter matches seller `Profile.public_state` (approximate location, not an address).
- `radius` filter means: **seller will travel at least X miles** (`service_radius_miles >= X`).
- True buyer-zip distance filtering is deferred until we introduce geo lookup (ZIP→lat/lon) and compute distances.


## 2026-02-16 — Pack BC — Dead-end guardrails for launch
- Launch posture should catch broken operator routes *before* deploy.
- `launch_check` includes a conservative URL wiring check that verifies core named routes resolve (dashboards, ops surfaces, and storefront entry points).
- If `url_wiring` fails, treat it as a release-blocker until the route mismatch is corrected.

## 2026-02-16 — Pack BJ — Ops Health UX
- Ops Health (`/ops/health/`) is an **ops-only** surface.
- Default response is **HTML** for humans; `?format=json` is supported for automation.
- Public uptime/host checks must use the separate lightweight `/healthz/` endpoint.

## 2026-02-16 — Seller age policy (v1)
- **18+ enforcement applies to sellers only**.
- Buyers are not globally gated by age; sellers may mark listings as “18+” at their discretion.
- Seller must confirm **18+** and acknowledge **prohibited items (no tobacco, alcohol, firearms)** before initiating Stripe Connect onboarding.
- Enforcement point: `POST payments:connect_start` (cannot proceed without both attestations).

## 2026-02-16 — Managed tracking scripts
- GA4 and AdSense scripts must be **SiteConfig-managed**, not hardcoded in templates.
- `SiteConfig.ga_measurement_id` controls GA injection.
- `SiteConfig.adsense_enabled` + `SiteConfig.adsense_client_id` control AdSense injection.

## 2026-02-16 — Template styling standards (tables/cards)
- All Bootstrap tables used for lists/queues in ops/staff consoles should be wrapped in `<div class="lm-table">` for consistent rounding, header treatment, and overflow behavior.
- All Bootstrap cards used for KPI tiles/modules should include `.lm-card` to enforce consistent border/shadow style.

---

## 2026-02-16 — Dead-end audit standards
- Any “Coming Soon” or placeholder feature must route users to a **real next step** (e.g., Help/FAQs or Waitlist), not `href="#"`.
- Empty states should provide a clear CTA using the shared partial: `templates/partials/empty_state.html`.
- Health endpoints must remain stable and **must not be accidentally overridden** by duplicate view definitions.

## 2026-02-16 — Waitlist is SiteConfig-managed + throttled
- Waitlist availability and messaging are treated as **ops/marketing controls** and must be editable via **SiteConfig** (no settings.py constants).
- Waitlist POST is throttled with the central throttle system to prevent spam and reduce email abuse.
- Email sends (confirmation/admin notify) are best-effort and must never block signup UX.


## 2026-02-16 — Support pathway consistency (Contact + empty-state component)

- Added canonical `core:contact` (`/contact/`) so users always have a “Support” exit path.
- Support email is DB-managed (`SiteConfig.support_email`) so it can be changed without deploys.
- `partials/empty_state.html` is the standard for empty lists/queues and may include Help/FAQs/Contact links via `show_support_links=True`.

---

## Empty-state UX standard (Pack BT)
- All primary list/detail pages should use `templates/partials/empty_state.html` for “no data” states.
- Every empty state must provide at least one clear CTA (Browse / Create / Back) and optionally show Help/FAQs/Contact links on pages where users commonly get stuck.

## 2026-02-16 — Contact messages are stored + configurable
- Contact form submissions are stored in DB (ContactMessage) by default for staff review.
- Email delivery is best-effort and can be toggled via SiteConfig.
- Contact submission endpoints are throttled (CONTACT_SUBMIT) to reduce abuse.

## 2026-02-16 — Support Inbox lives in Staff Console (audited)
- Support triage for ContactMessage is handled in the **Staff Console** (`/staff/support/`) for fast ops access.
- Resolve/reopen actions are written to the **Audit log** (verbs: `contact_message_resolved`, `contact_message_reopened`).
- Staff may reply either via their email client (mailto shortcut) or directly from Staff Console.

## 2026-02-16 — Support Inbox triage fields + canned responses (Pack BW)
- ContactMessage includes internal triage fields: SLA tag + internal notes + last reply metadata (count + last replied by/at).
- Staff Console can send replies using admin-managed `SupportResponseTemplate` canned responses.
- Replies are best-effort sends and must not crash staff operations; reply sends + triage edits are audited (verbs: `contact_message_reply_sent`, `contact_message_triage_updated`).

## 2026-02-17 — Outbound support email logging (Pack BX)
- Every Staff Console “Reply from console” must write an immutable outbound log row (`SupportOutboundEmailLog`) with:
  - to/from/subject/body, status (sent/failed), and error text when failed.
- This provides reconciliation without relying on external email provider logs.
- SupportOutboundEmailLog is read-only in admin and displayed on the ContactMessage detail page.

---

## 2026-02-17 — Dependent category dropdowns (seller listing form)

- Catalog category APIs use `kind=GOOD|SERVICE` to match listing kinds (Product vs Service).
- API payload shape is standardized for dropdowns:
  - `{ ok: true, results: [{ id, text }, ...] }`
- Seller listing upload UX must:
  - Filter root categories by listing kind.
  - Load subcategories dynamically by selected category.


## Analytics event enums
- `products.ProductEngagementEvent` uses `Kind` (field: `kind`). Do not reference `EventType`/`event_type` anywhere.

---

## 2026-02-17 — Seller onboarding checklist (Pack CB)
- The seller dashboard and seller listings page must show an onboarding checklist until complete.
- Checklist steps are derived from persisted profile + Stripe readiness (no new DB tables required).
- Each incomplete step must include a direct link to the correct page to complete it (no dead-end CTAs).

---

## 2026-02-17 — Seller listing mini‑wizard + draft-save (Pack CF)
- The mini‑wizard is a **front-end only** stepper that hides/shows sections; it must not change the data model.
- Draft-save is implemented by sending `save_mode=draft` and forcing `is_active=False` server-side to prevent accidental publish.
- On create, draft-save redirects to Edit (so the seller can add images after the first save).

---

## 2026-02-17 — RC dead-end audit (Pack CG)
- We treat obvious dead-end patterns in templates (`href='#'`, `action='#'`, `javascript:void(0)`) as release risks.
- `template_deadend_audit` is included in `rc_check` output.
- Default behavior is **warn-only** to avoid blocking day-to-day dev; production gating can enforce strictness via:
  - `python manage.py rc_check --deadends-strict` or `python manage.py template_deadend_audit --strict`.

## 2026-02-18 — Template route-name drift prevention
- Decision: include a template URL reverse audit (`url_reverse_audit`) in RC checks to catch stale `{% url 'name' %}` references before runtime.
- Scope: audits only *literal/quoted* route names; variable-based url tags are not audited.


## Pack CK — Tooltips initialization
- We initialize Bootstrap tooltips opportunistically in `static/js/ui.js` for any element with `data-bs-toggle="tooltip"`.
- If Bootstrap tooltip JS is not present, initialization is a no-op (no hard dependency).

---

## 2026-02-18 — Minimal flow smoke check for RC
- Add `python manage.py flow_check` to create a tiny fixture set and request key seller/consumer pages plus a cart add.
- Include `flow_check` in `python manage.py rc_report` so RC results show both static audits and a lightweight runtime flow.
- This does **not** replace the manual `docs/RC_CHECKLIST.md` run; it exists to catch obvious 500s early.

---

## 2026-02-18 — RC tooling contract (JSON/quiet support)
- Any management command intended to be aggregated by `rc_report` must support `--json` output.
- Audits must support `--limit` and `--quiet` to keep RC output bounded and usable.
- `stripe_config_check` exists as a dedicated Stripe posture check (keys + webhook route reversal) so Stripe surprises are caught before manual testing.
