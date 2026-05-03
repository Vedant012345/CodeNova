"""
CodeNova — PRODUCTION settings
Inherits from base settings and overrides for production.

Usage:
    export DJANGO_SETTINGS_MODULE=scholarflow.settings_production
    export SECRET_KEY="your-very-long-random-secret-key"
    export DATABASE_URL="postgresql://user:pass@host:5432/dbname?sslmode=require"
"""
import os
from .settings import *  # noqa: F401, F403

# ── Security ──────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ["SECRET_KEY"]   # MUST be set in environment
DEBUG = False
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")

# ── HTTPS ─────────────────────────────────────────────────────────────────────
SECURE_HSTS_SECONDS             = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS  = True
SECURE_HSTS_PRELOAD             = True
SECURE_SSL_REDIRECT             = True
SESSION_COOKIE_SECURE           = True
CSRF_COOKIE_SECURE              = True
SECURE_BROWSER_XSS_FILTER       = True
SECURE_CONTENT_TYPE_NOSNIFF     = True
X_FRAME_OPTIONS                 = "DENY"

# ── Database ──────────────────────────────────────────────────────────────────
# DATABASE_URL is already handled in base settings.py with ssl_require=True.
# No override needed here — the base settings.py auto-detects DATABASE_URL
# and configures PostgreSQL (production) or SQLite (local) accordingly.

# ── Static & Media ────────────────────────────────────────────────────────────
# Whitenoise for static file serving on Vercel (no S3 needed):
# MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
# STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ── Logging ───────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "ERROR"),
            "propagate": False,
        },
    },
}
