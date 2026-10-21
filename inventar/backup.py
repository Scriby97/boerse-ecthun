"""Sicherungen der Datenbank: lokal im Datenordner und zusätzlich in iCloud Drive.

- automatisch einmal täglich (beim Start der App und beim Öffnen der Startseite) und beim Schliessen
- vor jedem Import und vor dem Wiederherstellen
- pro Ordner bleiben die letzten 30 Sicherungen
"""

import datetime as dt
import os
import shutil
import sqlite3
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone

KEEP = 30
ICLOUD_FOLDER = "Börse EC Thun – Sicherungen"


def icloud_dir() -> Path | None:
    """Sicherungsordner in iCloud Drive, falls iCloud Drive auf diesem Rechner eingeschaltet ist."""
    env = os.environ.get("BOERSE_ICLOUD_DIR")
    if env is not None:
        return Path(env) if env else None
    drive = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    return drive / ICLOUD_FOLDER if drive.is_dir() else None


def backup_database(reason: str) -> Path:
    """Vollständige Kopie der Datenbank, auch während die App läuft; zusätzlich nach iCloud kopiert."""
    settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = settings.BACKUP_DIR / f"{timezone.localtime():%Y-%m-%d_%H%M%S}_{reason}.sqlite3"
    connection.ensure_connection()
    destination = sqlite3.connect(target)
    try:
        connection.connection.backup(destination)
    finally:
        destination.close()
    _prune(settings.BACKUP_DIR)
    cloud = icloud_dir()
    if cloud is not None:
        try:
            cloud.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, cloud / target.name)
            _prune(cloud)
        except OSError:
            pass  # iCloud nicht erreichbar: die lokale Sicherung gibt es trotzdem
    return target


def _prune(folder: Path) -> None:
    for old in list_backups(folder)[KEEP:]:
        old.unlink(missing_ok=True)


def list_backups(folder: Path | None = None) -> list[Path]:
    """Sicherungen, neueste zuerst."""
    folder = folder or settings.BACKUP_DIR
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.sqlite3"), key=lambda p: p.name, reverse=True)


def last_backup_time() -> dt.datetime | None:
    backups = list_backups()
    if not backups:
        return None
    return dt.datetime.fromtimestamp(backups[0].stat().st_mtime, tz=dt.timezone.utc)


def ensure_daily_backup() -> Path | None:
    """Sichert, wenn die letzte Sicherung älter als 24 Stunden ist."""
    if not getattr(settings, "AUTO_BACKUP", True):
        return None
    last = last_backup_time()
    if last and timezone.now() - last < dt.timedelta(hours=24):
        return None
    return backup_database("automatisch")


def backup_is_stale(days: int = 3) -> bool:
    last = last_backup_time()
    return last is None or timezone.now() - last > dt.timedelta(days=days)


def restore_backup(name: str) -> Path:
    """Holt eine Sicherung zurück. Vorher wird der aktuelle Stand selbst gesichert."""
    source = settings.BACKUP_DIR / Path(name).name
    if not source.is_file() or source.suffix != ".sqlite3":
        raise FileNotFoundError(name)
    # Erst in den Speicher laden: die Sicherung vorher könnte die älteste Datei wegräumen
    memory = sqlite3.connect(":memory:")
    try:
        src = sqlite3.connect(source)
        try:
            src.backup(memory)
        finally:
            src.close()
        safety = backup_database("vor-wiederherstellen")
        connection.ensure_connection()
        memory.backup(connection.connection)
    finally:
        memory.close()
    return safety
