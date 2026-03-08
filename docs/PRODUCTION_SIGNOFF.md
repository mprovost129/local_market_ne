# Local Market NE - Production Signoff

Date (America/New_York): ____________________
Release / Commit: ____________________
Operator(s): ____________________
Environment: `staging` / `production` (circle one)

## 1) Gate Status

Run:

```bash
python manage.py launch_gate --json --fail-on-warning
```

Record:
- Result status: `ok` / `warning` / `critical`
- Critical count: __________
- Warning count: __________
- Notes:

____________________________________________________________

## 2) Seller + Buyer Setup

- [ ] Seller A created and email verified
- [ ] Seller B created and email verified
- [ ] Seller A Stripe onboarding completed
- [ ] Seller B Stripe onboarding completed
- [ ] Buyer account created and email verified

Evidence (usernames/emails):

____________________________________________________________

## 3) Multi-Seller Checkout Simulation

Scenario:
- Buyer adds Seller A product with quantity `2`
- Buyer adds Seller B product/service
- Buyer adds tip(s)
- Buyer checks out successfully

Checks:
- [ ] Checkout line items include correct quantity `2` for Seller A item
- [ ] Checkout groups by seller
- [ ] Tip updates total correctly
- [ ] Order marked `PAID`
- [ ] Transfer events created (or expected skipped state if seller unready)
- [ ] Audit/event logs present

Order ID(s): ____________________
Notes:

____________________________________________________________

## 4) Duplicate Webhook Replay (Idempotency)

Run replay for same Stripe event twice (or use ops webhook reprocess twice).

Checks:
- [ ] Order remains correctly `PAID`
- [ ] No duplicate transfer side effects
- [ ] No financial drift introduced

Stripe Event ID: ____________________
Notes:

____________________________________________________________

## 5) Refund + Transfer Reversal Simulation

Scenario:
- Create refund request for eligible physical line item
- Seller/authorized operator approves
- Trigger refund

Checks:
- [ ] Refund status reaches `REFUNDED`
- [ ] Stripe refund id recorded
- [ ] Transfer reversal recorded when transfer exists
- [ ] Refund attempts/audit logs created

Refund Request ID: ____________________
Notes:

____________________________________________________________

## 6) Reconciliation + Alerts Post-Flow

Run:

```bash
python manage.py reconciliation_check --days 30 --limit 500 --json
python manage.py alert_summary --hours 24 --reconciliation-days 7 --json
python manage.py money_loop_check --limit 200 --json
```

Checks:
- [ ] Reconciliation reports `ok=true`
- [ ] Alert summary status acceptable for go-live (`ok`; or warning with approved exception)
- [ ] Money loop invariants pass

Notes:

____________________________________________________________

## 7) Ops + Admin Access / RBAC

Checks:
- [ ] Non-privileged ops user cannot trigger high-risk actions
- [ ] Delegated user with explicit permission can run authorized action(s)
- [ ] Owner/staff can execute all required incident operations

Notes:

____________________________________________________________

## 8) Final Go/No-Go Decision

- Decision: `GO` / `NO-GO`
- Approved by: ____________________
- Timestamp: ____________________

Required NO-GO conditions:
- `launch_gate` returns `critical`
- unresolved money/reconciliation mismatch
- payment/refund core flow failure

Open risks accepted (if any):

____________________________________________________________
