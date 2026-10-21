"""Hinweis auf neue Versionen: fragt beim Start einmal GitHub nach dem neusten Release (nur mit Internet)."""

import json
import urllib.request

from boerse import __version__

RELEASES_URL = "https://api.github.com/repos/Scriby97/boerse-ecthun/releases/latest"
_available: dict | None = None


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.lstrip("v").split(".") if part.isdigit())


def check() -> None:
    """Im Hintergrund beim Start aufgerufen; Fehler (kein Internet) werden ignoriert."""
    global _available
    try:
        request = urllib.request.Request(
            RELEASES_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "BoerseECThun"}
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.load(response)
    except Exception:
        return
    tag = data.get("tag_name", "")
    if version_tuple(tag) > version_tuple(__version__):
        _available = {"version": tag.lstrip("v"), "url": data.get("html_url", "")}


def available() -> dict | None:
    """Neuere Version, falls die Prüfung beim Start eine gefunden hat."""
    return _available
