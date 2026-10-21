"""Einstellungen der Börsen-App. Läuft nur lokal auf einem Laptop, ohne Login und ohne Internet."""

import os
import sys
import tempfile
from pathlib import Path

from .paths import data_dir, secret_key

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = data_dir()
BACKUP_DIR = DATA_DIR / "Sicherungen"
AUTO_BACKUP = True
if sys.argv[1:2] == ["test"]:
    # Tests laufen in einer offenen Transaktion; eine automatische Kopie würde darauf warten
    AUTO_BACKUP = False
    # Tests sichern in einen Wegwerf-Ordner, nie zu den echten Sicherungen oder nach iCloud
    BACKUP_DIR = Path(tempfile.mkdtemp(prefix="boerse-test-"))
    os.environ["BOERSE_ICLOUD_DIR"] = ""

SECRET_KEY = secret_key(DATA_DIR)
DEBUG = os.environ.get("BOERSE_DEBUG") == "1"
# Nur vom eigenen Rechner erreichbar
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "inventar",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "boerse.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "boerse.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "boerse.sqlite3",
    }
}

LANGUAGE_CODE = "de-ch"
TIME_ZONE = "Europe/Zurich"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# Statische Dateien direkt aus den App-Ordnern ausliefern, auch ohne DEBUG und ohne collectstatic
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Meldungen im Cookie: sie überstehen auch das Zurückholen einer Sicherung (Sitzungen liegen in der Datenbank)
MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"

# Grosse Numbers-Dateien beim Import zulassen
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
