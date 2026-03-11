# Local Market NE - Render Deployment Plan (Render-safe)

Last updated: 2026-02-10 (America/New_York)

This document is the production deployment playbook for deploying the current Local Market NE codebase to Render.

The project’s migration policy is **locked**:

- **Do not rewrite migrations** (production safety).
- Use additive migrations only.
- Treat production DB as the source of truth; use dry-runs and backups.

---

## 0) Preconditions

You should have:

- A clean local checkout of the same git commit you intend to deploy.
- A Render Web Service already created for the repo (or ready to create).
- A Render PostgreSQL instance provisioned.

---

## 1) Render service settings

### Python runtime

Use **Python 3.12.x** (recommended: `3.12.7`).

- This repo pins `python-3.12.7` in `runtime.txt`.
- Blueprint env includes `PYTHON_VERSION=3.12.7`.
- Start script fails fast on Python `>=3.14` to prevent known admin/template runtime errors with current dependency set.

### Build command

Use:

```
pip install -r requirements.txt
python manage.py collectstatic --noinput
```

### Start command

This repo includes a Render start script that can optionally run migrations before starting Gunicorn.

Use:

```
bash scripts/render_start.sh
```

By default the blueprint sets `RUN_MIGRATIONS_ON_START=0` (manual migrations for first deploy safety).

---

## 2) Environment variables (required)

Set these in Render (Dashboard → Environment):

Core:

- `DJANGO_SETTINGS_MODULE=config.settings.prod`
- `DJANGO_SECRET_KEY=...`
- `DEBUG=0`
- `PRIMARY_DOMAIN=localmarketne.com`
- `RENDER_EXTERNAL_HOSTNAME=<your-service>.onrender.com` (recommended)
- `ALLOWED_HOSTS_EXTRA=` (optional)
- `CSRF_TRUSTED_ORIGINS_EXTRA=` (optional)
- `COOKIE_DOMAIN=` (optional; defaults to `.<PRIMARY_DOMAIN>`)

Database:

- `DATABASE_URL=...` (from Render Postgres)

### Stripe

- `STRIPE_SECRET_KEY=...`
- `STRIPE_PUBLIC_KEY=...` (or `STRIPE_PUBLISHABLE_KEY`)
- `STRIPE_WEBHOOK_SECRET=...`

### Email

- `DEFAULT_FROM_EMAIL=...`
- SMTP vars (whatever your stack uses in `config/settings/`)

### Saved search alerts

- `SAVED_SEARCH_ALERTS_ENABLED=1`
- `SAVED_SEARCH_ALERTS_LIMIT=500`
- `SAVED_SEARCH_ALERTS_MONITOR_ENABLED=1`
- `SAVED_SEARCH_ALERTS_EXPECTED_INTERVAL_MINUTES=15`
- Create a Render Cron Job to run every 10-15 minutes:
  - `python manage.py send_saved_search_alerts --enabled --limit 500`

### Storage

v1 uses local storage. Ensure `MEDIA_ROOT` and `STATIC_ROOT` are configured in production settings.

If you plan to use S3 for media:

- `USE_S3=1`
- `AWS_S3_MEDIA_BUCKET=...`
- `AWS_ACCESS_KEY_ID=...`
- `AWS_SECRET_ACCESS_KEY=...`

---

## Quick sanity check (recommended)

After setting env vars in Render, run:

```
python manage.py env_audit
python manage.py post_deploy_check
```

For a fuller variable reference, see `docs/ENV_VARS.md`.

---

## 3) Render-safe migration strategy

### Why this matters

Render deploys are automated. A migration that fails can block deploy and/or leave a partial state.
This plan prioritizes:

- **Idempotency**
- **Non-destructive DB changes**
- **Rollback capability**

### Recommended approach

1) **Deploy code first** with `RUN_MIGRATIONS_ON_START=0`.
2) Run migrations manually from Render Shell.
3) Verify.
4) Optionally set `RUN_MIGRATIONS_ON_START=1` after the first successful deploy.

#### Step A - First deploy without migrations

- Ensure `RUN_MIGRATIONS_ON_START=0` in Render env.
- Deploy the web service.

#### Step B - Manual migrate

Open Render Shell → run:

```
python manage.py migrate --noinput
python manage.py check
```

If you want future deploys to auto-run migrations at boot, set:

```
RUN_MIGRATIONS_ON_START=1
```

If migrations fail:

- Do **not** retry blindly.
- Read the migration error, fix in a new commit, redeploy, then re-run migrate.

#### Step C - Collect static (already in build)

Confirm `collectstatic` succeeded in build logs.

---

## 4) Production verification (required)

Follow `docs/POST_DEPLOY_CHECKLIST.md`.

---

## 5) Backups and rollback

### DB backup

Before any risky change:

- Create a Render Postgres snapshot/backup.

### Rollback strategy

Rollback means:

- Deploying the last known-good commit.
- Restoring DB only if you ran destructive migrations (which you should not for v1).

---

## 6) First-live checklist summary

- [ ] Deploy web service code
- [ ] Run `migrate` manually
- [ ] Confirm site loads and core flows work
- [ ] Confirm Stripe keys/webhooks
- [ ] Confirm uploads (media) and orders
- [ ] Confirm admin access
- [ ] Confirm seller onboarding and checkout gating

---

## Optional: Render Blueprint

This repo includes `render.yaml` (blueprint) you can import into Render to create the web service + database.

- Defaults to `DJANGO_SETTINGS_MODULE=config.settings.prod`
- Stripe/email keys are marked `sync: false` so you set them in Render.
- Includes a cron service for saved-search alerts (`localmarketne-saved-search-alerts`) scheduled every 15 minutes.
