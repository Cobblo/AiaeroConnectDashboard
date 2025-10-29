# core/settings.py
from pathlib import Path
import os
from dotenv import load_dotenv

# ---------------------------------------------------------------------
# Load .env (put API URL/secret, device ids, SMTP creds, etc. here)
# ---------------------------------------------------------------------
load_dotenv()

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Security ---
SECRET_KEY = "django-insecure-lu5^6t280no0k#bi8+k@bci!2p2p$1z-qawpzvx4def1+@a7pl"
DEBUG = True
ALLOWED_HOSTS = ["*"]  # fine for local/dev

# --- Installed apps ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Optional; remove if you don't use Channels/WebSockets
    "channels",

    "telemetry",
]

# --- Middleware ---
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# --- URLs / Templates ---
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

# --- WSGI / ASGI ---
WSGI_APPLICATION = "core.wsgi.application"
ASGI_APPLICATION = "core.asgi.application"

CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}

# --- Database ---
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# --- Auth redirects ---
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# --- I18N / TZ ---
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# --- Static / Media ---
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Excel exports (local folder for generated workbooks) ---
EXCEL_DIR = BASE_DIR / "excel_exports"
EXCEL_DIR.mkdir(exist_ok=True)

# =====================================================================
# LIVE DEVICE DATA (AWS API Gateway / your backend)
# Define these in .env:
#   VITALS_API_URL=...            (or legacy: VITALS_GET_URL=...)
#   VITALS_API_SECRET=...         (or legacy: VITALS_SECRET=...)
#   VITALS_DEVICE_IDS=ID1,ID2
#   VITALS_DEFAULT_DEVICE_ID=ID1
#   VITALS_API_TIMEOUT=10
# =====================================================================
def _parse_ids(s: str):
    return [x.strip() for x in (s or "").split(",") if x.strip()]

# Accept either new or legacy env names
VITALS_API_URL = (
    os.getenv("VITALS_API_URL")
    or os.getenv("VITALS_GET_URL")
    or ""
).strip()

VITALS_API_SECRET = (
    os.getenv("VITALS_API_SECRET")
    or os.getenv("VITALS_SECRET")
    or ""
).strip()

VITALS_API_TIMEOUT = int(os.getenv("VITALS_API_TIMEOUT", "10"))
VITALS_DEFAULT_DEVICE_ID = (os.getenv("VITALS_DEFAULT_DEVICE_ID") or "").strip()
VITALS_DEVICE_IDS = _parse_ids(os.getenv("VITALS_DEVICE_IDS", ""))

# --- Logging ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "verbose"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

# =====================================================================
# EMAIL (password reset, etc.)
# Defaults to console (prints emails in runserver). To use SMTP, set:
#   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
#   EMAIL_HOST=smtp.gmail.com
#   EMAIL_PORT=587
#   EMAIL_HOST_USER=you@example.com
#   EMAIL_HOST_PASSWORD=app_password
#   EMAIL_USE_TLS=true
# =====================================================================
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend"
)

EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587" if EMAIL_BACKEND.endswith("smtp.EmailBackend") else "25"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").lower() == "true"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "webmaster@localhost")

# Password reset link validity (seconds)
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24

DEVICES_MAX_AGE_MIN = int(os.getenv("DEVICES_MAX_AGE_MIN", "10"))