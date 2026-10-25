"""Neue Versionen: Hinweis beim Start und Aktualisieren per Knopf.

Beim Start fragt die App einmal GitHub nach dem neusten Release (nur mit Internet). Auf dem Mac lädt «Jetzt
aktualisieren» die passende ZIP-Datei selbst herunter. Was die App selbst lädt, markiert macOS nicht als Download
aus dem Internet – es gibt also keine Meldung «beschädigt». Nach dem Schliessen ersetzt ein kleines Skript die App
im Ordner Programme und startet die neue Version. Die Daten liegen ausserhalb der App und bleiben, wie sie sind.
"""

import json
import os
import platform
import ssl
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

from boerse import __version__

RELEASES_URL = "https://api.github.com/repos/Scriby97/boerse-ecthun/releases/latest"
ARCHITECTURES = {"arm64": "apple-chip", "x86_64": "intel"}
_available: dict | None = None
# Fortschritt des Aktualisierens: status = bereit | laden | neustart | fehler
state = {"status": "bereit", "message": "", "percent": 0}
# Schliesst das App-Fenster; setzt app.py, sobald es ein Fenster gibt
quit_app = None

# Ersetzt die App, sobald sie beendet ist (Argumente: Prozess-Nr., bisherige App, neue App)
SWAP_SCRIPT = """#!/bin/sh
pid="$1"; app="$2"; new="$3"
while kill -0 "$pid" 2>/dev/null; do sleep 0.5; done
rm -rf "$app.alt"
if mv "$app" "$app.alt"; then
  if mv "$new" "$app"; then rm -rf "$app.alt"; else mv "$app.alt" "$app"; fi
fi
xattr -dr com.apple.quarantine "$app" 2>/dev/null
open "$app"
"""


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.lstrip("v").split(".") if part.isdigit())


def _open(url: str, accept: str = "application/vnd.github+json"):
    # Eigene Zertifikatsliste: der verpackten App fehlen die des Systems
    try:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "BoerseECThun"})
    return urllib.request.urlopen(request, timeout=30, context=context)


def asset_name(machine: str | None = None) -> str:
    return f"Boerse-EC-Thun-{ARCHITECTURES.get(machine or platform.machine(), 'apple-chip')}.zip"


def check() -> bool | None:
    """Fragt GitHub nach dem neusten Release: True = neuere Version da, False = aktuell, None = keine Verbindung.

    Läuft beim Start im Hintergrund und auf Knopfdruck in den Einstellungen; Fehler (kein Internet) werden ignoriert.
    """
    global _available
    try:
        with _open(RELEASES_URL) as response:
            data = json.load(response)
    except Exception:
        return None
    tag = data.get("tag_name", "")
    if version_tuple(tag) <= version_tuple(__version__):
        return False
    download = next((a.get("browser_download_url") for a in data.get("assets", []) if a.get("name") == asset_name()),
                    None)
    _available = {"version": tag.lstrip("v"), "url": data.get("html_url", ""), "download": download}
    return True


def available() -> dict | None:
    """Neuere Version, falls die Prüfung beim Start eine gefunden hat."""
    return _available


def app_bundle() -> Path | None:
    """Die laufende Mac-App (…/Börse EC Thun.app), sonst None (Entwicklung, Windows)."""
    if not getattr(sys, "frozen", False) or sys.platform != "darwin":
        return None
    bundle = Path(sys.executable).resolve().parents[2]
    return bundle if bundle.suffix == ".app" else None


def can_install() -> bool:
    bundle = app_bundle()
    return bool(_available and _available.get("download") and bundle and os.access(bundle.parent, os.W_OK))


def start_install() -> bool:
    """Lädt die neue Version im Hintergrund; False, wenn das hier nicht geht oder schon läuft."""
    if not can_install() or state["status"] in ("laden", "neustart"):
        return False
    state.update(status="laden", message="", percent=0)
    threading.Thread(target=_install, daemon=True).start()
    return True


def _install() -> None:
    try:
        folder = Path(tempfile.mkdtemp(prefix="boerse-update-"))
        archive = folder / "update.zip"
        _download(_available["download"], archive)
        subprocess.run(["ditto", "-x", "-k", str(archive), str(folder / "neu")], check=True)
        new = next((folder / "neu").glob("*.app"))
        script = folder / "ersetzen.sh"
        script.write_text(SWAP_SCRIPT)
        subprocess.Popen(["/bin/sh", str(script), str(os.getpid()), str(app_bundle()), str(new)],
                         start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as error:  # noqa: BLE001 – jede Störung als Hinweis zeigen, die App läuft weiter
        state.update(status="fehler", message=str(error) or error.__class__.__name__)
        return
    state.update(status="neustart", percent=100)
    if quit_app is not None:
        # Kurz warten, damit die Seite «startet neu» noch erscheint
        threading.Timer(2.0, quit_app).start()


def _download(url: str, target: Path) -> None:
    with _open(url, accept="application/octet-stream") as response, target.open("wb") as file:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(1 << 16):
            file.write(chunk)
            done += len(chunk)
            if total:
                state["percent"] = int(done * 100 / total)
    if total and done != total:
        raise OSError("Der Download wurde unterbrochen.")
