"""Django settings for the basketball statistics platform.

Configuration is environment-driven (12-factor style) via ``django-environ``
so the same image runs locally under Docker Compose and in production.

Notes
-----
This is a monolith-modular layout: a single Django project split into focused
apps (``connectors``, ``ingestion``, ``stats``, ``players``, ``teams``,
``games``, ``api``) as described in the technical specification, §2.2.
"""

from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:3000"]),
    SENTRY_DSN=(str, ""),
)

# Load backend/.env if present (Docker Compose also injects these via env_file).
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "django_filters",
    "django_celery_beat",
]

LOCAL_APPS = [
    "connectors",
    "ingestion",
    "stats",
    "players",
    "teams",
    "games",
    "api",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://basketball_stats:basketball_stats@db:5432/basketball_stats",
    ),
}

# Cache + Celery (Redis shared as broker and cache backend, §2.2)
REDIS_URL = env("REDIS_URL", default="redis://redis:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE = True
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Periodic ingestion of the current FEB season, post-matchday only (spec §3.3,
# §9). The DatabaseScheduler syncs this into django_celery_beat on startup.
# Runs nightly at 05:00 Europe/Madrid, well after games have finished.
CELERY_BEAT_SCHEDULE = {
    "ingest-current-feb-season-nightly": {
        "task": "ingestion.tasks.ingest_current_feb_season",
        "schedule": crontab(hour=5, minute=0),
    },
    # ACB (Liga Endesa) nightly ingest via the public JSON API. Offset from the
    # FEB run so the two don't contend for the worker at the same minute.
    "ingest-current-acb-season-nightly": {
        "task": "ingestion.tasks.ingest_current_acb_season",
        "schedule": crontab(hour=5, minute=30),
    },
    # Profile enrichment (bio/branding/trajectory/logos) changes far less often
    # than scores, so it runs weekly rather than nightly (plan §6.5). Monday
    # 06:00 Europe/Madrid — after that night's ingestion, so new players exist.
    "enrich-current-feb-profiles-weekly": {
        "task": "ingestion.tasks.enrich_current_feb_profiles",
        "schedule": crontab(hour=6, minute=0, day_of_week=1),
    },
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization (UI is Spanish; data stored timezone-aware in UTC)
LANGUAGE_CODE = "es-es"
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploaded / ingested media (team logos, player photos).
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Media ingestion kill-switch (docs/team-member-enrichment-plan.md §6.4). When
# True the enrichment pipeline downloads and stores logos/photos from their
# official free-distribution sources (ACB mediacenter, FEB/club assets) with
# per-asset attribution; flip to False to pause storage if a host's terms change.
INGEST_STORE_MEDIA = env.bool("INGEST_STORE_MEDIA", default=True)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django REST Framework
# camelCase render/parse to match the TypeScript frontend (spec §5.3).
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": (
        "djangorestframework_camel_case.render.CamelCaseJSONRenderer",
        "djangorestframework_camel_case.render.CamelCaseBrowsableAPIRenderer",
    ),
    "DEFAULT_PARSER_CLASSES": (
        "djangorestframework_camel_case.parser.CamelCaseJSONParser",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
}

# CORS: read-only public API restricted to the frontend origin (spec §6.4).
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")

# Structured logging to stdout (captured by the platform / Sentry).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

# Optional Sentry error tracking.
SENTRY_DSN = env("SENTRY_DSN")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.0)
