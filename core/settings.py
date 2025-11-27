from pathlib import Path
import os
from dotenv import load_dotenv

# ---------------------------------------------------------------------
# Load .env early (API/device ingest, SMTP creds, etc.)
# ---------------------------------------------------------------------
load_dotenv()

# === Paths ===
BASE_DIR = Path(__file__).resolve().parent.parent

# === Security / Debug ===
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-dev-only")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "*").split(",") if h.strip()] or ["*"]

# Optional if you reverse-proxy with HTTPS
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

# === Installed apps ===
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Channels (optional; useful if you add websockets later)
    "channels",
    # Local app
    "telemetry",
]

# === Middleware ===
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# === URLs / Templates ===
ROOT_URLCONF = "core.urls"

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
            ],
        },
    },
]

# === WSGI / ASGI ===
WSGI_APPLICATION = "core.wsgi.application"
ASGI_APPLICATION = "core.asgi.application"
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# === Database ===
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# === Auth redirects ===
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# === I18N / TZ ===
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# === Static / Media ===
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# === Excel exports (local folder for generated workbooks) ===
EXCEL_DIR = BASE_DIR / "excel_exports"
EXCEL_DIR.mkdir(exist_ok=True)

# =====================================================================
# LIVE DATA SOURCES
# =====================================================================

# (A) Ingest directly to Django (recommended for LoRa receiver)
#     Devices POST to /ingest/v1 with header: x-ingest-secret: <INGEST_SECRET>
INGEST_SECRET = os.getenv("INGEST_SECRET", "aiaero_4444_secure_key").strip()

# Consider a device "online" if last post < N minutes
DEVICES_MAX_AGE_MIN = int(os.getenv("DEVICES_MAX_AGE_MIN", "60"))

# (B) Pull from AWS API Gateway (for cloud vitals – LoRa + GSM aggregators)
# Default base (used only if ENV does not override)
DEFAULT_VITALS_BASE = "https://9bttash411.execute-api.ap-south-1.amazonaws.com/vitals"

# --- LoRa / main vitals API ---

# Main readings endpoint (query lambda)
# Can be overridden by ENV, but falls back to DEFAULT_VITALS_BASE
VITALS_API_URL = (
    os.getenv("VITALS_API_URL")
    or os.getenv("VITALS_GET_URL")
    or DEFAULT_VITALS_BASE
).strip()

# Devices registry endpoint (query lambda /devices)
VITALS_DEVICES_URL = (os.getenv("VITALS_DEVICES_URL") or "").strip()
if not VITALS_DEVICES_URL:
    # If API URL already ends with /devices, keep it
    if VITALS_API_URL.endswith("/devices"):
        VITALS_DEVICES_URL = VITALS_API_URL
    # If API URL ends with /vitals, append /devices
    elif VITALS_API_URL.endswith("/vitals"):
        VITALS_DEVICES_URL = VITALS_API_URL.rstrip("/") + "/devices"
    else:
        VITALS_DEVICES_URL = VITALS_API_URL.rstrip("/") + "/devices"

# --- GSM / EC200U vitals API (NEW) ---

# These are read from .env, e.g.:
# VITALS_GSM_API_URL=https://zaz41a0b60.execute-api.ap-south-1.amazonaws.com/gsm_ingest
# VITALS_GSM_DEVICES_URL=https://zaz41a0b60.execute-api.ap-south-1.amazonaws.com/gsm_ingest
VITALS_GSM_API_URL = os.getenv("VITALS_GSM_API_URL", "").strip()
VITALS_GSM_DEVICES_URL = (
    os.getenv("VITALS_GSM_DEVICES_URL", "") or VITALS_GSM_API_URL
).strip()

# Secret shared between firmware, ingest lambda and query lambda
VITALS_API_SECRET = (
    os.getenv("VITALS_API_SECRET")
    or os.getenv("VITALS_SECRET")
    or INGEST_SECRET
).strip()

# HTTP timeout for Django → AWS requests (seconds)
VITALS_API_TIMEOUT = int(os.getenv("VITALS_API_TIMEOUT", "6"))

# === Logging ===
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("LOG_LEVEL", "INFO"),
    },
}

# === EMAIL (password reset, etc.) ===
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(
    os.getenv(
        "EMAIL_PORT",
        "587" if EMAIL_BACKEND.endswith("smtp.EmailBackend") else "25",
    )
)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").lower() == "true"
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "webmaster@localhost"
)
PASSWORD_RESET_TIMEOUT = int(
    os.getenv("PASSWORD_RESET_TIMEOUT", str(60 * 60 * 24))
)

# === AWS / DynamoDB (if you later query it directly from Django) ===
AWS_REGION = "ap-south-1"
DYNAMODB_READINGS_TABLE = os.getenv(
    "DYNAMODB_READINGS_TABLE", "aiaero_4444_secure_key"
)

# Optional latest table name (matches your lambda_ingest TABLE_LATEST)
DYNAMODB_LATEST_TABLE = os.getenv(
    "DYNAMODB_LATEST_TABLE", "vitals_latest"
)
