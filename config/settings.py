"""Instellingen voor het OPS/VET portaal.

Alle gevoelige of omgevingsafhankelijke waarden komen uit omgevingsvariabelen,
zodat dezelfde code lokaal, in Docker en in productie draait.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "ja"}


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]
# Render (en vergelijkbare hosts) geven de publieke hostnaam door; die wordt automatisch toegestaan.
if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])
    CSRF_TRUSTED_ORIGINS.append(f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "core",
    "planning",
    "meetings",
    "actions",
    "shipments",
    "documents",
    "customer_portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.LoginRequiredMiddleware",
    "customer_portal.middleware.CustomerPortalMiddleware",
    "core.audit.CurrentUserMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if os.environ.get("DATABASE_URL", "").startswith("postgres"):
    from urllib.parse import urlparse

    _db = urlparse(os.environ["DATABASE_URL"])
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _db.path.lstrip("/"),
            "USER": _db.username,
            "PASSWORD": _db.password,
            "HOST": _db.hostname,
            "PORT": _db.port or 5432,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("SQLITE_PATH", BASE_DIR / "db.sqlite3"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "nl"
TIME_ZONE = "Europe/Amsterdam"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# Ontbreekt er toch een bestand in het manifest, val dan terug op de gewone URL in plaats van een 500-fout.
WHITENOISE_MANIFEST_STRICT = False
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage" if not DEBUG else "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))

if not DEBUG:
    SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    if SECRET_KEY.startswith("dev-only"):
        raise RuntimeError("Zet DJANGO_SECRET_KEY voor productie.")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# --- Tracking (ETA / vessel) -------------------------------------------------
# Standaard provider voor rederijen zonder eigen configuratie: "mock" of "dcsa".
TRACKING_DEFAULT_PROVIDER = os.environ.get("TRACKING_DEFAULT_PROVIDER", "mock")
TRACKING_HTTP_TIMEOUT = int(os.environ.get("TRACKING_HTTP_TIMEOUT", "20"))
TERMINAL49_API_KEY = os.environ.get("TERMINAL49_API_KEY", "")
SAFECUBE_API_KEY = os.environ.get("SAFECUBE_API_KEY", "")
SAFECUBE_BASE_URL = os.environ.get("SAFECUBE_BASE_URL", "https://api.sinay.ai/container-tracking/api/v2")
SAFECUBE_API_KEY_HEADER = os.environ.get("SAFECUBE_API_KEY_HEADER", "API_KEY")

# --- Documentherkenning ------------------------------------------------------
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "")
TESSERACT_LANG = os.environ.get("TESSERACT_LANG", "nld+eng")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}

# --- E-mail ----------------------------------------------------------------
# Zonder EMAIL_HOST worden mails naar de console geschreven (handig bij testen).
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST else "django.core.mail.backends.console.EmailBackend",
)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "OPS/VET Portaal <noreply@example.com>")
# Basis-URL voor links in e-mails, bijv. https://portaal.example.nl
PORTAL_BASE_URL = os.environ.get("PORTAL_BASE_URL", os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8000")).rstrip("/")
# Geheim token voor /cron/<token>/ (gratis hosting zonder achtergrondproces).
CRON_TOKEN = os.environ.get("CRON_TOKEN", "")
# Tijdstip (HH:MM) waarop het dagoverzicht en de dienstherinneringen worden verstuurd.
DAILY_DIGEST_TIME = os.environ.get("DAILY_DIGEST_TIME", "07:30")
