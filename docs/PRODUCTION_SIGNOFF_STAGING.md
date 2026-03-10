# Local Market NE - Production Signoff (Staging Run Draft)

Date (America/New_York): ____________________
Release / Commit: ____________________
Operator(s): ____________________
Environment: `staging`

## Latest Automated Snapshot (2026-03-10, local env)

Executed commands:

```bash
python manage.py launch_gate --json
python manage.py launch_gate --json --fail-on-warning
python manage.py post_deploy_check
python manage.py first_live_validate
```

Observed results:
- `launch_gate --json`: `ok=true`, `critical_count=0`, `warning_count=0`
- `launch_gate --json --fail-on-warning`: `ok=true`
- `post_deploy_check`: `NOT OK` (fatal)
- `first_live_validate`: `NOT OK` (inherits post_deploy_check failure)

Current blockers from automated checks:
- `DEBUG is True in the current settings module`
- `STRIPE_CONNECT_WEBHOOK_SECRET` missing in the active environment

Notes:
- This snapshot is not a staging signoff; it is a local preflight reference.
- Complete this template in real staging after environment variables and settings are corrected.

## 0) Pre-checks

- Ensure test Stripe keys/webhook secret are configured for staging.
- Ensure at least one ops user can access `/ops/`.
- Ensure two seller accounts and one buyer account are available (or create them below).

Planned accounts:
- Seller A username/email: ____________________
- Seller B username/email: ____________________
- Buyer username/email: ____________________

## 1) Launch gate (must run first)

```bash
python manage.py launch_gate --json --fail-on-warning
```

Record:
- Status: ____________________
- Critical count: ____________________
- Warning count: ____________________

## 2) Seller onboarding checks

- [ ] Seller A email verified
- [ ] Seller B email verified
- [ ] Seller A Stripe onboarding complete
- [ ] Seller B Stripe onboarding complete
- [ ] Seller dashboards load

Notes:

____________________________________________________________

## 3) Listing + storefront checks

- [ ] Seller A listing created and visible on storefront/listings
- [ ] Seller B listing/service created and visible on storefront/listings
- [ ] Listing validation/focus behavior works when required fields missing

Product/Service IDs:
- Seller A listing ID: ____________________
- Seller B listing ID: ____________________

## 4) Multi-seller checkout scenario

Scenario:
- Buyer adds Seller A item with quantity `2`
- Buyer adds Seller B item/service
- Buyer adds per-seller tips
- Buyer completes checkout

Expected:
- [ ] Checkout reflects quantity `2` for Seller A line
- [ ] Seller-grouped sections shown in checkout
- [ ] Tips update totals correctly
- [ ] Order status reaches `PAID`

Artifacts:
- Order ID: ____________________
- Stripe Checkout Session ID: ____________________
- Stripe Event ID (`checkout.session.completed`): ____________________

## 5) Duplicate webhook replay (idempotency)

Run replay (or Ops UI reprocess) on the same Stripe event twice.

Expected:
- [ ] Order remains correctly paid
- [ ] No duplicate transfer side effects
- [ ] No reconciliation drift introduced

Notes:

____________________________________________________________

## 6) Refund + reversal scenario

Scenario:
- Create refund request on eligible physical item
- Approve request
- Trigger refund

Expected:
- [ ] Refund status becomes `REFUNDED`
- [ ] Stripe refund ID stored
- [ ] Transfer reversal created when matching transfer exists
- [ ] Refund attempts + audit logs present

Artifacts:
- Refund Request ID: ____________________
- Stripe Refund ID: ____________________
- Transfer Reversal ID (if present): ____________________

## 7) Financial integrity checks (post-flow)

```bash
python manage.py reconciliation_check --days 30 --limit 500 --json
python manage.py money_loop_check --limit 200 --json
python manage.py alert_summary --hours 24 --reconciliation-days 7 --json
```

Expected:
- [ ] `reconciliation_check.ok == true`
- [ ] `money_loop_check.ok == true`
- [ ] `alert_summary.status == ok` (or documented, accepted warning)

Notes:

____________________________________________________________

## 8) RBAC checks

- [ ] Non-privileged ops user blocked from high-risk actions
- [ ] Delegated user with explicit permission can run allowed action(s)
- [ ] Owner/staff can run high-risk actions

Notes:

____________________________________________________________

## 9) Final decision

- Decision: `GO` / `NO-GO`
- Approved by: ____________________
- Timestamp: ____________________

Blocking conditions:
- launch_gate critical
- unresolved reconciliation/money-loop mismatches
- failed core checkout/refund/idempotency scenario
