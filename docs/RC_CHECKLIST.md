# Release Candidate Checklist (RC)

This checklist is intended to be run **before any production deploy**.

## 0) One-command gate

Optional: initialize a timestamped manual RC results log:

- `python manage.py rc_results_init --env local`

Run:

- `python manage.py rc_check --checks --db`

Stripe posture sanity (keys + webhook routes):

- `python manage.py stripe_config_check`

RC gate bundle:

- `python manage.py rc_check --checks --db`

Optional consolidated report (includes audits + flow smoke check):

- `python manage.py rc_report`

Optional lightweight runtime flow smoke check (creates a tiny fixture set):

- `python manage.py flow_check`

Optional (fail build on dead ends):

- `python manage.py rc_check --checks --db --deadends-strict`

## 1) Seller end-to-end flow

### Account + onboarding
- [ ] Register seller account
- [ ] Verify email (no lockout; can still reach required admin/staff flows)
- [ ] Seller 18+ confirmation required at onboarding
- [ ] Seller prohibited-items acknowledgement required (no tobacco, alcohol, firearms)
- [ ] Stripe Connect onboarding completes; seller becomes “ready”

### Storefront basics
- [ ] Seller can set public shop name
- [ ] Seller can set public location (city/state) without exposing exact address
- [ ] Seller dashboard shows onboarding checklist until complete

### Listing creation
- [ ] Seller can create **Product** listing
  - [ ] Category list shows **Products only**
  - [ ] Subcategory list populates after category selection
  - [ ] Product-only sections show (stock/fulfillment); service-only sections hidden
- [ ] Seller can create **Service** listing
  - [ ] Category list shows **Services only**
  - [ ] Subcategory list populates
  - [ ] Service-only sections show; product-only sections hidden
- [ ] Save Draft works (listing is not public)
- [ ] Publish works (listing becomes public)
- [ ] Images upload works (at least 1 required)

### Seller fulfillment
- [ ] Seller can view orders list
- [ ] Seller can move physical goods through states:
  - READY (pickup/delivery) → buyer confirmation
  - SHIPPED (shipping) → buyer confirmation
- [ ] Tracking fields save and appear on order detail

## 2) Buyer end-to-end flow

### Browsing
- [ ] Home loads (no missing assets)
- [ ] Category sidebar filter works
- [ ] Product listing cards show price + fulfillment badge
- [ ] Seller shop pages filter within shop

### Cart + checkout
- [ ] Add product to cart
- [ ] Checkout supports pickup/delivery/shipping (as configured)
- [ ] Tips (if enabled) calculate correctly
- [ ] Stripe Checkout completes in test mode

### After payment
- [ ] Order detail loads
- [ ] Buyer can confirm pickup/delivery after READY
- [ ] Buyer can confirm shipping after SHIPPED

## 3) Money Loop invariants

Run:

- `python manage.py money_loop_check --limit 200`

Verify:
- [ ] Order totals recompute cleanly
- [ ] For every OrderItem: `marketplace_fee_cents + seller_net_cents == line_total_cents`

## 4) Support ops

- [ ] Contact form saves to inbox (and respects throttling)
- [ ] Staff Console Support Inbox lists messages
- [ ] Staff can reply from console
- [ ] Outbound email log records sent/failed attempts

## 5) Dead ends / broken links

Run:

- `python manage.py template_deadend_audit`

If you want to gate deploy on this:

- `python manage.py template_deadend_audit --strict`

## 6) Production config sanity

- [ ] `DEBUG=False`
- [ ] Correct `PRIMARY_DOMAIN` (and optionally `RENDER_EXTERNAL_HOSTNAME`) for prod host/origin generation
- [ ] Secure cookies + SSL redirect enabled in prod
- [ ] Stripe keys + webhook secrets present
- [ ] `python manage.py stripe_config_check` passes (or only warns in dev)
- [ ] Admin/staff accounts exist

