"""
Django settings for agrosmart project.
Uses django-environ for environment variables with sane defaults.
"""
import os
from pathlib import Path
from datetime import timedelta

import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Initialize environ
env = environ.Env(
    DEBUG=(bool, False),
)

# Read .env file
environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY", default="django-insecure-CHANGE-ME-IN-PRODUCTION")
DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "testserver"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["http://localhost:8000", "http://127.0.0.1:8000"])

SYSTEM_NAME = env("SYSTEM_NAME", default="Lunyili AgroSmart Connect")
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", default="http://localhost:8000")


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    # "rest_framework",
    # "rest_framework_simplejwt",
    # "django_filters",
    # "drf_yasg",
    # "django_celery_beat",
    # "django_celery_results",
    # "cloudinary_storage",
    # "cloudinary",
]

LOCAL_APPS = [
    "core",
    # "accounts",  # We're using core as the main app
    # "dashboard",
    # "farmers",
    # "suppliers",
    # "buyers",
    # "products",
    # "orders",
    # "payments",
    # "weather",
    # "market",
    # "advice",
    # "finance",
    # "notifications",
    # "reports",
    # "ussd",
    # "sms",
    # "api",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "core.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # "whitenoise.middleware.WhiteNoiseMiddleware",  # Optional
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "agrosmart.urls"

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
            ],
        },
    },
]

WSGI_APPLICATION = "agrosmart.wsgi.application"
# ASGI_APPLICATION = "agrosmart.asgi.application"  # Optional

# ---------------------------------------------------------------------------
# Database (SQLite for Development, PostgreSQL for Production)
# ---------------------------------------------------------------------------
USE_SQLITE = env.bool("USE_SQLITE", default=True)

if USE_SQLITE:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": env.db(
            "DATABASE_URL",
            default="postgres://postgres:12345678@localhost:5432/lunyili_agrosmart",
        )
    }
    DATABASES["default"]["CONN_MAX_AGE"] = 60

# ---------------------------------------------------------------------------
# Cache / Redis / Celery (Optional for development)
# ---------------------------------------------------------------------------
USE_REDIS = env.bool("USE_REDIS", default=False)
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

if USE_REDIS:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = "django-db"
    CELERY_CACHE_BACKEND = "django-cache"
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "agrosmart-local-cache",
        }
    }
    # Disable Celery for development
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache"
    CELERY_CACHE_BACKEND = "default"
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Africa/Dar_es_Salaam"
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 240

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    # {
    #     "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    # },
    # {
    #     "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    #     "OPTIONS": {"min_length": 8},
    # },
    # {
    #     "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    # },
    # {
    #     "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    # },
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="Africa/Dar_es_Salaam")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & Media
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework (Optional)
# ---------------------------------------------------------------------------
# REST_FRAMEWORK = {
#     "DEFAULT_AUTHENTICATION_CLASSES": [
#         "rest_framework_simplejwt.authentication.JWTAuthentication",
#         "rest_framework.authentication.SessionAuthentication",
#     ],
#     "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
#     "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
#     "PAGE_SIZE": 20,
# }

# SIMPLE_JWT = {
#     "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
#     "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
#     "ROTATE_REFRESH_TOKENS": True,
#     "BLACKLIST_AFTER_ROTATION": True,
#     "AUTH_HEADER_TYPES": ("Bearer",),
# }

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=f"{SYSTEM_NAME} <no-reply@lunyili.co.tz>")

# ---------------------------------------------------------------------------
# External integrations (Africa's Talking, ClickPesa, OpenWeather)
# ---------------------------------------------------------------------------
AT_USERNAME = env("AT_USERNAME", default="sandbox")
AT_API_KEY = env("AT_API_KEY", default="")
AT_SENDER_ID = env("AT_SENDER_ID", default="agrosmart")
AT_SMS_CALLBACK_URL = env("AT_SMS_CALLBACK_URL", default="")
AT_SMS_DRY_RUN = env.bool("AT_SMS_DRY_RUN", default=not bool(AT_API_KEY))
AT_SHORT_CODE = env("AT_SHORT_CODE", default="*384*20997#")

CLICKPESA_CLIENT_ID = env("CLICKPESA_CLIENT_ID", default="")
CLICKPESA_API_KEY = env("CLICKPESA_API_KEY", default="")
CLICKPESA_BASE_URL = env("CLICKPESA_BASE_URL", default="https://api.clickpesa.com")
CLICKPESA_WEBHOOK_SECRET = env("CLICKPESA_WEBHOOK_SECRET", default="")
CLICKPESA_DRY_RUN = env.bool("CLICKPESA_DRY_RUN", default=not bool(CLICKPESA_API_KEY))

OPENWEATHER_API_KEY = env("OPENWEATHER_API_KEY", default="")
OPENWEATHER_BASE_URL = env("OPENWEATHER_BASE_URL", default="https://api.openweathermap.org/data/2.5")

# USSD Settings
USSD_DEFAULT_LANGUAGE = env("USSD_DEFAULT_LANGUAGE", default="sw")
DEFAULT_FARMER_COUNTRY = env("DEFAULT_FARMER_COUNTRY", default="TZ")

# ---------------------------------------------------------------------------
# Security hardening (production)
# ---------------------------------------------------------------------------
# Disabled for development
SECURE_BROWSER_XSS_FILTER = False
SECURE_CONTENT_TYPE_NOSNIFF = False
X_FRAME_OPTIONS = "SAMEORIGIN"
SESSION_COOKIE_HTTPONLY = False
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 hours

if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} - {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "application.log",
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "core": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
    },
}

# ---------------------------------------------------------------------------
# Login/Logout URLs
# ---------------------------------------------------------------------------
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"