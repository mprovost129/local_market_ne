# LocalMarketNE — Go-Live Kit (Pack CE)

This document is the operational runbook for deploying and validating a release candidate.

## Pre-deploy checklist (local)

1) Update dependencies (if needed)
- `pip install -r requirements.txt`

2) Run the RC gate
- `python manage.py rc_check --checks --db`

3) Money loop invariant check (optional but recommended)
- `python manage.py money_loop_check --limit 200`

## Render production deploy checklist

> If you’re using the **Render Blueprint** included in this repo (`render.yaml`), Render will create the web service + Postgres for you.
> You still must add your secrets in the Render dashboard (the blueprint intentionally leaves them unsynced).

### Environment variables

Core:
- `DJANGO_SETTINGS_MODULE=config.settings.prod`
- `DJANGO_SECRET_KEY=<strong random>`
- `DEBUG=0`
- `PRIMARY_DOMAIN=localmarketne.com`
- `RENDER_EXTERNAL_HOSTNAME=<your-service>.onrender.com` (recommended)
- `ALLOWED_HOSTS_EXTRA=` (optional)
- `CSRF_TRUSTED_ORIGINS_EXTRA=` (optional)
- `COOKIE_DOMAIN=` (optional; defaults to `.<PRIMARY_DOMAIN>`)

Database:
- `DATABASE_URL=<Render Postgres URL>`

Stripe:
- `STRIPE_SECRET_KEY=sk_live_...`
- `STRIPE_PUBLIC_KEY=pk_live_...` (or `STRIPE_PUBLISHABLE_KEY`)
- `STRIPE_WEBHOOK_SECRET=whsec_...`

Email:
- `EMAIL_BACKEND=...`
- `DEFAULT_FROM_EMAIL=...`

Optional:
- `RECAPTCHA_V3_SITE_KEY=...`
- `RECAPTCHA_V3_SECRET_KEY=...`
- `USE_S3=1` (if using S3 media)

Recommended quick check after setting env vars:
- `python manage.py env_audit`

Full variable reference: `docs/ENV_VARS.md`

### Build / Start

Typical commands:
- Build: `python manage.py collectstatic --noinput`
- Start: `bash scripts/render_start.sh`

Notes:
- For first deploy safety, keep `RUN_MIGRATIONS_ON_START=0` and run migrations manually from Render Shell.
- After first successful deploy, you may set `RUN_MIGRATIONS_ON_START=1` to auto-run migrations at boot.
- Deploy gate on startup (recommended default):
  - `RUN_LAUNCH_GATE_ON_START=1`
  - `LAUNCH_GATE_FAIL_ON_WARNING=1` (strict mode: warning also blocks start)

### CI/Deploy gate commands

Use one of these before promoting a release:
- `python manage.py launch_gate --json`
- strict: `python manage.py launch_gate --json --fail-on-warning`
- shell helpers:
  - `bash scripts/launch_gate.sh`
  - `FAIL_ON_WARNING=1 bash scripts/launch_gate.sh`
  - `scripts\launch_gate.bat`
  - `set FAIL_ON_WARNING=1 && scripts\launch_gate.bat`

### After deploy (must-pass checks)

1) Public health
- `GET /healthz/` returns JSON indicating OK (e.g. `{status: "ok", ...}`)
- `GET /version/` returns JSON `{version: "..."}`

2) Ops health
- `GET /ops/health/` (ops-only) is green.

3) Launch check
- `GET /ops/launch-check/` review warnings.

4) Launch gate + smoke checks (server)
- `python manage.py launch_gate --json`
- strict (optional): `python manage.py launch_gate --json --fail-on-warning`
- `python manage.py rc_check --checks --db --quiet`

5) Post-deploy validation (server)
- `python manage.py post_deploy_check`
- Optional public HTTP check (from anywhere):
  - `python manage.py post_deploy_check --base-url https://localmarketne.com`

6) First-live validation helper (server + public HTTP)
- `python manage.py first_live_validate --base-url https://localmarketne.com`

## First-live validation (Stripe)

Run in Stripe **test mode** first, then **live** when you are ready.

Use `docs/PRODUCTION_SIGNOFF.md` to capture pass/fail evidence and final go/no-go approval.
For a prefilled staging execution worksheet, use `docs/PRODUCTION_SIGNOFF_STAGING.md`.

1) Create a seller
- Email verify
- Confirm seller 18+ and prohibited-items acknowledgement
- Connect Stripe Express

2) Create a product listing
- Ensure category/subcategory filtering works for Product vs Service.

3) Place an order
- Checkout success
- Webhook marks order PAID
- Transfers created (idempotent) and ledger invariants hold

4) Seller flow
- Seller sees order in seller orders list
- Fulfillment transitions work

5) Refund flow (physical items only)
- Create refund request
- Approve + trigger Stripe refund
- Order/refund status updates correctly

## Rollback plan

Preferred rollback:
1) Re-deploy the previous known-good commit/build.
2) If migrations were applied:
   - Prefer forward-fix migrations.
   - Only consider DB rollback when you have a clean provider snapshot and you understand data loss.

Emergency actions:
- Disable checkout in **Admin Settings → Checkout enabled** (SiteConfig) to keep browsing up while you resolve payment/webhook issues.
- Keep site up for browsing while you resolve payment/webhook issues.

## Ops snapshot command

For a quick environment/config snapshot:
- `python manage.py ops_backup_report` (JSON)
- `python manage.py ops_backup_report --text` (human)
