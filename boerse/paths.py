"""Wo die App ihre Daten ablegt: getrennt vom Programm, damit ein Update nie Daten überschreibt."""

import os
import secrets
import sys
from pathlib import Path

APP_NAME = "BoerseECThun"


def data_dir() -> Path:
    """Datenordner: BOERSE_DATA_DIR, sonst der übliche Ort des Betriebssystems."""
    env = os.environ.get("BOERSE_DATA_DIR")
    if env:
        path = Path(env)
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    elif os.name == "nt":
        path = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    else:
        path = Path.home() / ".local" / "share" / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def secret_key(directory: Path) -> str:
    """Geheimer Schlüssel für Django; beim ersten Start erzeugt und im Datenordner gespeichert."""
    file = directory / "secret_key.txt"
    if not file.exists():
        file.write_text(secrets.token_urlsafe(50), encoding="utf-8")
    return file.read_text(encoding="utf-8").strip()
