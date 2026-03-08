# LocalMarketNE - User and Ops Manual (Pack AG)

Generated: 2026-02-15

This manual documents how LocalMarketNE operates end-to-end: buyer and seller flows, staff administration,
ops controls, and the operational posture needed to run the marketplace reliably.

## Quick role map

- Guest: browse listings and storefronts.
- Consumer (verified): purchase items/services; message sellers; write purchase-gated reviews; report content.
- Seller (Stripe ready): create/publish listings; manage inventory; fulfill orders; handle appointments; respond to Q&A and reviews.
- Staff Admin (daily): run day-to-day queues (orders, refund requests, reports, listing moderation).
- Ops (support): health/runbook, reconciliation/mismatch tools, audit logs, elevated controls.

---

## 1. Accounts and onboarding

### 1.1 Registration and email verification
- Register: `/accounts/register/`
- Login: `/accounts/login/`
- Verify: `/accounts/verify-email/<token>/`
- Resend (POST): `/accounts/verify-email/resend/`

Until email verification is complete, users are limited to profile and verification-required pages.

### Recommendation: seller intent at registration
Do not ask “Are you a seller?” at registration. Every verified user is a consumer by default. Provide a clear
“Start selling” CTA after verification. Seller status becomes real only after Stripe onboarding.

### 1.2 Seller onboarding and Stripe readiness
A verified user remains a consumer until Stripe Connect onboarding is completed. Listings can be created
as drafts, but publishing is gated behind seller readiness checks.

Seller profile data (minimum):
- Store name (display name)
- About store text
- Approximate location: city/town, state, ZIP (no exact address required)
- Service radius for service providers
- Policies: refund/cancellation text blocks (seller-defined, within platform rules)

---

## 2. Buyer (consumer) workflows

### 2.1 Browse, search, and storefronts
Buyers browse by category and can provide location (ZIP/device location) to bias results toward nearby sellers.
Each seller has a storefront page showing only that seller’s listings, with filters scoped to that store.

### 2.2 Product detail page
Product pages include image gallery, price, seller link, and purchase controls. Fulfillment options and lead time
must be visible before add-to-cart.

### 2.3 Cart and checkout
- Cart is grouped by seller.
- Buyer can edit quantity, remove items, and optionally add a tip.
- Checkout uses Stripe. Marketplace fee is snapshotted and non-refundable per policy.
- After payment: stock decrements, units sold increments, and seller net/fees are locked via snapshots.

### 2.4 Reviews, Q&A, messaging, and refunds
- Reviews are purchase-gated.
- Public Q&A exists with reporting flows.
- Refunds: buyer submits request; seller approves/declines; seller triggers Stripe refund if approved.

---

## 3. Seller workflows

### 3.1 Listing creation (products)
Type-first flow: Product (default) or Service. Category is filtered by type; subcategory filtered by category.

Product required fields:
- Title, short description, full description
- Price in dollars
- At least one image before publish
- Inventory: stock qty OR made-to-order + lead time days
- Fulfillment: pickup and/or delivery and/or shipping; delivery radius required when delivery enabled

### 3.2 Listing creation (services)
- Service title, short description, full description
- Time increments / scheduling settings
- Optional deposit settings; cancellation policy
- Service radius

### 3.3 Managing listings
Seller listings page should show: thumbnail, title, category/subcategory, units sold, status, and Manage menu
(edit, images, specs, duplicate, activate/deactivate, preview).

### 3.4 Order fulfillment
- OrderItem snapshots fulfillment choice/instructions at purchase time; no retroactive edits.
- Shipping: seller provides carrier + tracking number; status visible to buyer and staff.
- Pickup: seller follows pickup instructions captured at purchase.

### 3.5 Appointments (services)
Appointments support request + confirmation. Deposits (if configured) link to orders. Rescheduling can require buyer
confirmation. Reminders can be sent via management command.

---

## 4. Staff Admin Console - daily operations

Primary pages:
- `/staff/` dashboard
- `/staff/orders/` order list/detail
- `/staff/refunds/` refund request queue
- `/staff/qa-reports/` Q&A reports queue
- `/staff/listings/` listing moderation (reason required, audited)

Expectations:
- Require a reason for policy-relevant listing edits.
- Escalate financial anomalies to Ops.

---

## 5. Ops Console - owner and support operations

Primary pages:
- `/ops/` ops dashboard
- `/ops/health/` system health checks
- `/ops/runbook/` backups and incident playbooks
- `/ops/audit/` audit log + CSV export
- `/ops/reconciliation/` reconciliation overview
- `/ops/reconciliation/mismatches/` mismatch detector

---

## 6. Settings, policies, and compliance

SiteConfig (DB-backed) includes:
- Marketplace fee percent (snapshotted on orders)
- Tips enabled/behavior
- Age gate (18+)
- Prohibited categories (weapons, alcohol, etc.)
- Announcement bar + maintenance mode
- reCAPTCHA v3 keys and enforcement
- Appointment reminders enable/hours-before

Maintenance mode serves a 503 page for public traffic while allowing Ops/Staff bypass.

---

## Appendix A - Environment checklist (production)

- DEBUG=False
- PRIMARY_DOMAIN set (prod derives ALLOWED_HOSTS/CSRF trusted origins)
- Stripe keys + webhook secret configured
- Email backend configured (SMTP) and FROM_EMAIL set
- Database configured (managed Postgres) and backups enabled
- Media storage configured (S3 optional) and lifecycle policy considered
- reCAPTCHA v3 keys configured if enabled
- Run migrations and collectstatic on deploy

## Appendix B - Launch gate

Before launch, complete at least one full end-to-end test per flow: buyer purchase, seller fulfillment, refund request,
Q&A moderation, and service appointment with deposit. Review Ops reconciliation for mismatches and confirm backups are enabled.
