# RC Results Log (Template)

Use this to record each manual RC run. Keep one copy per environment (local, staging, prod).

## Run metadata
- Date/time:
- Environment: (local / staging / prod)
- Commit / ZIP:
- Stripe mode: (test / live)
- Tester:

## Automated gates
- `python manage.py stripe_config_check`:
  - Result: (OK / WARN / FAIL)
  - Notes:
- `python manage.py rc_check --checks --db`:
  - Result: (OK / FAIL)
  - Notes:
- `python manage.py rc_report`:
  - Result: (OK / FAIL)
  - Notes:

## Manual checklist results

### Seller flow
- Register + verify email: (PASS/FAIL)
- 18+ + prohibited items acknowledgement: (PASS/FAIL)
- Stripe Connect onboarding to “ready”: (PASS/FAIL)
- Storefront settings (shop name + city/state): (PASS/FAIL)
- Product listing create + publish + image upload: (PASS/FAIL)
- Service listing create + publish: (PASS/FAIL)
- Seller orders list + fulfillment state updates: (PASS/FAIL)

### Buyer flow
- Browse + filters + product card badges: (PASS/FAIL)
- Add to cart: (PASS/FAIL)
- Checkout (pickup/delivery/shipping as applicable): (PASS/FAIL)
- Tips: (PASS/FAIL / N/A)
- Stripe Checkout completed: (PASS/FAIL)
- Post-payment order detail + confirm fulfillment: (PASS/FAIL)

### Money loop
- `python manage.py money_loop_check --limit 200`: (PASS/FAIL)
- Ledger invariant spot-checks: (PASS/FAIL)

### Ops/support
- Contact form → staff inbox: (PASS/FAIL)
- Staff reply email recorded: (PASS/FAIL)

## Issues found
List each issue with: page URL, steps to reproduce, expected vs actual, suspected module/file.

1) 
2) 
3) 

## Fixes applied
If fixes were made, record the pack name and ZIP/commit.

## Sign-off
- RC approved for deploy: (YES/NO)
- Notes:
