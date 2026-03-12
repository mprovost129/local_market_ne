# Environment Variables

This project is primarily configured via environment variables.

Use `.env.example` for local development and the Render dashboard (or Blueprint `render.yaml`) for production.

## Core

| Variable | Required | Notes |
|---|---:|---|
| `DJANGO_SECRET_KEY` | ✅ | Required everywhere. Use a long random value in production. |
| `DEBUG` | ✅ | `True` for local dev, `False` in production. |
| `PRIMARY_DOMAIN` | ✅ (prod) | Canonical domain (e.g. `localmarketne.com`). Used to build `ALLOWED_HOSTS` and CSRF trusted origins in production settings. |
| `RENDER_EXTERNAL_HOSTNAME` | recommended | The Render hostname (e.g. `yourapp.onrender.com`). Defaults to `localmarketne.onrender.com` if omitted. |
| `ALLOWED_HOSTS_EXTRA` | optional | Comma-separated additional hostnames (advanced). |
| `CSRF_TRUSTED_ORIGINS_EXTRA` | optional | Comma-separated additional trusted origins (`https://...`) (advanced). |
| `COOKIE_DOMAIN` | optional | Defaults to `.<PRIMARY_DOMAIN>`; override only if needed. |
| `SITE_BASE_URL` | ✅ (prod) | Used in emails and absolute URL generation. |
| `PYTHON_VERSION` | ✅ (Render) | Set to `3.12.7` (or another `3.12.x`). Do not use `3.14` with current pinned Django version. |

## Database

| Variable | Required | Notes |
|---|---:|---|
| `DATABASE_URL` | ✅ (prod recommended) | Render provides this automatically for the attached Postgres. |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_HOST` / `POSTGRES_PORT` | optional | Local dev fallback when `DATABASE_URL` is not provided. |

## Stripe

| Variable | Required | Notes |
|---|---:|---|
| `STRIPE_SECRET_KEY` | ✅ | `sk_test_...` in test, `sk_live_...` in production. |
| `STRIPE_PUBLISHABLE_KEY` or `STRIPE_PUBLIC_KEY` | ✅ | Publishable key (`pk_test_...` / `pk_live_...`). App accepts either name. |
| `STRIPE_WEBHOOK_SECRET` | recommended | Checkout webhooks. |
| `STRIPE_CONNECT_WEBHOOK_SECRET` | recommended | Connect-related webhooks. |

## Venmo / PayPal

Current behavior:
- Seller checkout support for Venmo/PayPal is driven by seller profile fields:
  - `venmo_handle`
  - `paypal_me_url`
- PayPal can run as native in-app checkout when PayPal API env vars are configured.
- Venmo remains seller-handle based in v1.

| Variable | Required | Notes |
|---|---:|---|
| `PAYPAL_CLIENT_ID` | required for native PayPal | PayPal REST app client id. |
| `PAYPAL_CLIENT_SECRET` | required for native PayPal | PayPal REST app client secret. |
| `PAYPAL_WEBHOOK_ID` | recommended | Used to verify PayPal webhook signatures. Configure for app webhook URL: `/orders/webhooks/paypal/`. |
| `PAYPAL_ENV` | optional | `sandbox` (default) or `live`. |
| `VENMO_CLIENT_ID` | optional (future) | Needed only if Venmo direct API integration is added. |
| `VENMO_CLIENT_SECRET` | optional (future) | Needed only if Venmo direct API integration is added. |

## Email

| Variable | Required | Notes |
|---|---:|---|
| `DEFAULT_FROM_EMAIL` | recommended | e.g. `no-reply@localmarketne.com`. |
| `EMAIL_HOST` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | recommended | Your SMTP provider credentials. |
| `EMAIL_PORT` | optional | Defaults to `587` if set in `.env.example`. |
| `EMAIL_USE_TLS` | optional | Use `1` for TLS. |

## reCAPTCHA v3

| Variable | Required | Notes |
|---|---:|---|
| `RECAPTCHA_ENABLED` | optional | Set to `1` to enforce. |
| `RECAPTCHA_V3_SITE_KEY` | ✅ if enabled | v3 site key. |
| `RECAPTCHA_V3_SECRET_KEY` | ✅ if enabled | v3 secret key. |

## S3 / Object Storage

| Variable | Required | Notes |
|---|---:|---|
| `USE_S3` | optional | Set to `1` in production when you want media stored on S3. |
| `AWS_ACCESS_KEY_ID` | ✅ if `USE_S3=1` | IAM access key. |
| `AWS_SECRET_ACCESS_KEY` | ✅ if `USE_S3=1` | IAM secret. |
| `AWS_S3_MEDIA_BUCKET` | ✅ if `USE_S3=1` | Bucket name for media. |
| `AWS_S3_REGION_NAME` | ✅ if `USE_S3=1` | Region, e.g. `us-east-2`. |

## Saved Search Alerts

| Variable | Required | Notes |
|---|---:|---|
| `SAVED_SEARCH_ALERTS_ENABLED` | optional | Set to `1` to allow scheduled saved-search dispatch. |
| `SAVED_SEARCH_ALERTS_LIMIT` | optional | Per-run cap for evaluated searches (default `500`). |
| `SAVED_SEARCH_ALERTS_MONITOR_ENABLED` | optional | Set to `1` to include scheduler heartbeat checks in ops alert summary. |
| `SAVED_SEARCH_ALERTS_EXPECTED_INTERVAL_MINUTES` | optional | Expected cron interval minutes (default `15`) for stale heartbeat detection. |

## Helpful Commands

- `python manage.py env_audit` - prints what’s present/missing (recommended/required).
- `python manage.py env_audit --strict` - exits non-zero if required vars are missing.
