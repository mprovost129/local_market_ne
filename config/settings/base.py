# config/settings/base.py

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
import os

# Load environment variables from .env file
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")


def _db_from_database_url(url: str) -> dict:
    parsed = urlparse(url)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or "5432"),
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
    }


DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()

if DATABASE_URL:
    DATABASES = {"default": _db_from_database_url(DATABASE_URL)}
else:
    # Local fallback
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "local_market_ne"),
            "USER": os.getenv("POSTGRES_USER", "lmuser"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "lmuser"),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "0")),
        }
    }

# ============================================================
# Helpers
# ============================================================
def _csv_env(name: str, default: str = "") -> list[str]:
    """
    Read a comma-separated env var into a clean list.

    - Strips whitespace
    - Drops empty entries
    - Safe if unset/blank
    """
    raw = (os.getenv(name, default) or "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _bool_env(name: str, default: str = "False") -> bool:
    raw = (os.getenv(name, default) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


# ============================================================
# Core
# ============================================================
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or os.getenv("SECRET_KEY") or "unsafe-dev-key-change-me"

# Allow either DEBUG or DJANGO_DEBUG in env
DEBUG = _bool_env("DEBUG", os.getenv("DJANGO_DEBUG", "False"))

# IMPORTANT: ALLOWED_HOSTS must NOT contain schemes.
# Example: "localmarketne.onrender.com,localmarketne.com,www.localmarketne.com"
ALLOWED_HOSTS = _csv_env("ALLOWED_HOSTS", default="localhost,127.0.0.1,localmarketne.onrender.com")

# IMPORTANT: CSRF_TRUSTED_ORIGINS MUST include scheme.
# Example: "https://localmarketne.onrender.com,https://localmarketne.com,https://www.localmarketne.com"
CSRF_TRUSTED_ORIGINS = _csv_env("CSRF_TRUSTED_ORIGINS", default="https://localmarketne.onrender.com")


DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS: list[str] = [
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "storages",
]

LOCAL_APPS = [
    "accounts.apps.AccountsConfig",
    "core.apps.CoreConfig",
    "catalog",
    "products",
    "cart",
    "orders",
    "payments.apps.PaymentsConfig",
    "reviews",
    "analytics.apps.AnalyticsConfig",
    "dashboards",
    "refunds.apps.RefundsConfig",
    "qa",
    "legal.apps.LegalConfig",
    "notifications.apps.NotificationsConfig",
    "favorites.apps.FavoritesConfig",
    "appointments.apps.AppointmentsConfig",
    "ops.apps.OpsConfig",
    "staff_console.apps.StaffConsoleConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "core.middleware.RequestIDMiddleware",
    "django.middleware.common.CommonMiddleware",
    "core.middleware.RobotsNoIndexMiddleware",
    "analytics.middleware.RequestAnalyticsMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.MaintenanceModeMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.ExceptionCaptureMiddleware",
    "core.security_headers.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "cart.context_processors.cart_summary",
                "catalog.context_processors.sidebar_categories",
                "payments.context_processors.seller_stripe_status",
                "core.context_processors.sidebar_flags",
                "core.context_processors.site_config",
				"core.context_processors.env_banner",
                "core.context_processors.analytics",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/New_York"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Media: local in dev, S3 in prod (via STORAGES backend)
# MEDIA_URL should match storage backend to avoid hardcoding URLs
if _bool_env("USE_S3", "False"):
    # In production with S3, MEDIA_URL isn't used (storage.url() handles it)
    # But set it for consistency and any manual URL building
    MEDIA_URL = f"https://{(os.getenv('AWS_S3_MEDIA_BUCKET') or '').strip()}.s3.{(os.getenv('AWS_S3_REGION_NAME') or 'us-east-2').strip()}.amazonaws.com/media/"
else:
    # Local development: serve from /media/
    MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/accounts/profile/"
LOGOUT_REDIRECT_URL = "/"

SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True

# Production security settings for Render
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# -------- Cache (used by throttling) --------
CACHES = {
    "default": {
        "BACKEND": os.getenv("DJANGO_CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache"),
        "LOCATION": os.getenv("DJANGO_CACHE_LOCATION", "lmn-default"),
        "TIMEOUT": int(os.getenv("DJANGO_CACHE_TIMEOUT", "300")),
    }
}

# -------- reCAPTCHA v3 --------
RECAPTCHA_ENABLED = (os.getenv("RECAPTCHA_ENABLED", "1").strip().lower() not in ("0", "false", "off", "no"))
RECAPTCHA_V3_SITE_KEY = os.getenv("RECAPTCHA_V3_SITE_KEY", "").strip()
RECAPTCHA_V3_SECRET_KEY = os.getenv("RECAPTCHA_V3_SECRET_KEY", "").strip()
RECAPTCHA_V3_MIN_SCORE = float(os.getenv("RECAPTCHA_V3_MIN_SCORE", "0.5"))

# -------- Site base URL --------
SITE_BASE_URL = os.getenv("SITE_BASE_URL", "").strip().rstrip("/")

# -------- Analytics --------
# Client-side GA tag (gtag.js) measurement ID (e.g. G-XXXXXXX)
# Supports both GA_MEASUREMENT_ID and GOOGLE_MEASUREMENT_ID env vars
GA_MEASUREMENT_ID = os.getenv("GA_MEASUREMENT_ID", os.getenv("GOOGLE_MEASUREMENT_ID", "")).strip()

# Stripe secrets remain env-based (NOT DB settings)
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY") or os.getenv("STRIPE_PUBLIC_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_CONNECT_WEBHOOK_SECRET = os.getenv("STRIPE_CONNECT_WEBHOOK_SECRET")

# ------------------------------------------------------------------------------
# AWS S3 (optional)
# ------------------------------------------------------------------------------
AWS_ACCESS_KEY_ID = (os.getenv("AWS_ACCESS_KEY_ID") or "").strip()
AWS_SECRET_ACCESS_KEY = (os.getenv("AWS_SECRET_ACCESS_KEY") or "").strip()
AWS_S3_REGION_NAME = (os.getenv("AWS_S3_REGION_NAME") or "us-east-2").strip()

AWS_S3_MEDIA_BUCKET = (os.getenv("AWS_S3_MEDIA_BUCKET") or os.getenv("AWS_STORAGE_BUCKET_NAME") or "").strip()
AWS_S3_BACKUPS_BUCKET = (os.getenv("AWS_S3_BACKUPS_BUCKET") or "").strip()

if not AWS_S3_MEDIA_BUCKET:
    raise RuntimeError("USE_S3=True but AWS_S3_MEDIA_BUCKET is not set.")

AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_FILE_OVERWRITE = False
AWS_DEFAULT_ACL = None

# Prefer modern Django storage config
STORAGES = {
    "default": {"BACKEND": "core.storage_backends.MediaStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }

# -------------------------
# Analytics (Google Analytics 4)
# -------------------------
# Optional: GA4 Data API (server-side reporting for admin dashboard)
# Provide either a service-account JSON string OR a file path.
GA4_PROPERTY_ID = os.getenv("GOOGLE_ANALYTICS_PROPERTY_ID", "").strip()
GA4_CREDENTIALS_JSON = os.getenv("GOOGLE_ANALYTICS_CREDENTIALS_JSON", "").strip()
GA4_CREDENTIALS_FILE = os.getenv("GOOGLE_ANALYTICS_CREDENTIALS_FILE", "").strip()

# (Optional) GA4 Measurement Protocol values (future server-side event ingestion)
GOOGLE_STREAM_NAME = os.getenv("GOOGLE_STREAM_NAME", "").strip()
GOOGLE_STREAM_ID = os.getenv("GOOGLE_STREAM_ID", "").strip()
GOOGLE_MEASUREMENT_API_SECRET_KEY = os.getenv("GOOGLE_MEASUREMENT_API_SECRET_KEY", "").strip()