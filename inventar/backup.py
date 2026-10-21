"""Sicherungen der Datenbank (vorerst vor jedem Import; später auch täglich und in iCloud)."""

import sqlite3
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone


def backup_database(reason: str) -> Path:
    """Vollständige Kopie der Datenbank in den Sicherungsordner, auch während die App läuft."""
    settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = settings.BACKUP_DIR / f"{timezone.localtime():%Y-%m-%d_%H%M%S}_{reason}.sqlite3"
    connection.ensure_connection()
    destination = sqlite3.connect(target)
    try:
        connection.connection.backup(destination)
    finally:
        destination.close()
    return target
