# Local Market NE - Post-Deploy Verification Checklist

Last updated: 2026-03-08 (America/New_York)

## Go/No-Go policy
- `critical` from `launch_gate` is a hard NO-GO.
- `warning` from `launch_gate` is GO only with explicit operator sign-off.
- For strict deploys/CI, treat `warning` as NO-GO by using `--fail-on-warning`.

## Gate commands (copy/paste)
- Linux/macOS: `bash scripts/launch_gate.sh`
- Linux/macOS strict: `FAIL_ON_WARNING=1 bash scripts/launch_gate.sh`
- Windows: `scripts\launch_gate.bat`
- Windows strict: `set FAIL_ON_WARNING=1 && scripts\launch_gate.bat`

## 1) Site health
- [ ] Run launch gate: `python manage.py launch_gate --json`
- [ ] Run strict launch gate (optional): `python manage.py launch_gate --json --fail-on-warning`
- [ ] Run server-side validation: `python manage.py post_deploy_check`
- [ ] Optional env var audit: `python manage.py env_audit`
- [ ] Optional HTTP validation: `python manage.py post_deploy_check --base-url https://localmarketne.com`
- [ ] First-live helper (combines server + public checks): `python manage.py first_live_validate --base-url https://localmarketne.com`
- [ ] Home page loads (logged out)
- [ ] Browse loads (New / Trending / Top Rated)
- [ ] Product detail loads (images + Q&A/Reviews tabs)
- [ ] Static assets load (CSS/JS/icons)
- [ ] Admin loads

## 2) Auth + verification
- [ ] Register/login works
- [ ] Email verification status page loads
- [ ] Unverified account is correctly gated from verified-only features

## 3) Seller flows
- [ ] Seller dashboard loads
- [ ] Seller Listings page loads and shows publish checklist warnings
- [ ] Activate blocked unless checklist complete
- [ ] Stripe onboarding start + status pages load

## 4) Checkout flows
- [ ] Add to cart works for ready sellers
- [ ] Checkout blocked for unready sellers (unless owner bypass)
- [ ] Stripe Checkout session creation works
- [ ] `checkout.session.completed` webhook marks Order PAID
- [ ] Connect transfer creation succeeds for paid order (idempotent)

## 5) Orders
- [ ] Paid service order unlocks orders button
- [ ] Orders increments bundle-level `Product.order_count`
- [ ] Unique orderer event created (user or guest session)

## 6) Refunds
- [ ] Buyer can request refund for physical items
- [ ] Seller can approve/decline
- [ ] Seller-triggered Stripe refund works
- [ ] RefundAttempt audit rows created

## 7) Observability
- [ ] Webhook deliveries visible in admin
- [ ] Errors show in Render logs
- [ ] Database is backed up (snapshot created)

## Signoff record
- [ ] Complete and archive `docs/PRODUCTION_SIGNOFF.md` for this release.
- [ ] For staging dry-runs, use `docs/PRODUCTION_SIGNOFF_STAGING.md`.
