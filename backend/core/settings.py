from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent


def load_local_env(path):
    """Load simple KEY=VALUE development settings without overriding the shell."""
    if not path.exists():
        return False
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return True


def load_local_environments(paths):
    """Load paths in priority order and return the first file found."""
    loaded = None
    for env_path in paths:
        if load_local_env(env_path) and loaded is None:
            loaded = str(env_path)
    return loaded


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


LOADED_ENV_PATH = load_local_environments((BASE_DIR.parent / ".env", BASE_DIR / ".env"))

SECRET_KEY = "dev-secret-not-for-prod"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "corsheaders",
    "subscriptions",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"

CORS_ALLOW_ALL_ORIGINS = True

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
OPENAI_SUBSCRIPTION_REVIEW_ENABLED = env_bool("OPENAI_SUBSCRIPTION_REVIEW_ENABLED")
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "subscriptions.semantic_review": {
            "handlers": ["console"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        }
    },
}
