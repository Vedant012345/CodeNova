"""
CodeNova Django Settings — Production-ready with Cloudinary media storage.
"""
import os
import dj_database_url
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-scholarflow-change-in-production-abc123xyz789")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DEBUG = os.getenv("DEBUG", "True") == "True"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "cloudinary_storage",   # ← must be before staticfiles for media
    "cloudinary",           # ← Cloudinary SDK
    "portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Serve static files in production
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "scholarflow.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS":    [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "portal.context_processors.host_sidebar_counts",
            ],
        },
    },
]

WSGI_APPLICATION = "scholarflow.wsgi.application"

# ─── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "portal.CustomUser"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE     = "UTC"
USE_I18N      = True
USE_TZ        = True

STATIC_URL       = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT      = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL           = "/login/"
LOGIN_REDIRECT_URL  = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"

SESSION_COOKIE_AGE               = 86400
SESSION_EXPIRE_AT_BROWSER_CLOSE  = False

CACHES = {
    "default": {
        "BACKEND":  "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "scholarflow-cache",
        "TIMEOUT":  300,
        "OPTIONS":  {"MAX_ENTRIES": 1000},
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"

# ─── Media / File Storage ─────────────────────────────────────────────────────
# Cloudinary is used in production (when CLOUDINARY_URL env var is set).
# Falls back to local MEDIA_ROOT for local development.
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL", "")

if CLOUDINARY_URL:
    # Production: store all uploaded files on Cloudinary CDN
    import cloudinary
    cloudinary.config(cloudinary_url=CLOUDINARY_URL)

    DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"
    MEDIA_URL = "/media/"   # kept for template compatibility
    MEDIA_ROOT = BASE_DIR / "media"  # unused in production but required by Django
else:
    # Local development: serve from local filesystem
    MEDIA_URL  = "/media/"
    MEDIA_ROOT = BASE_DIR / "media"
