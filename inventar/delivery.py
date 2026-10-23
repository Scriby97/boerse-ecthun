"""PDFs und Excel-Dateien ausliefern.

Im Browser: als normaler Download. In der Desktop-App (Fenster mit pywebview) hängt sich das Fenster auf dem Mac
bei Downloads auf. Dort speichert die App die Datei selbst in «Dokumente › Börse EC Thun» und öffnet sie
mit dem passenden Programm (PDF in Vorschau, Excel in Numbers).
"""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

PDF = "application/pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def deliver(request, content: bytes, filename: str, content_type: str) -> HttpResponse:
    if not settings.DESKTOP:
        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
    folder = Path(settings.EXPORT_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    path.write_bytes(content)
    open_file(path)
    messages.success(request, f"{filename} gespeichert in «Dokumente › {folder.name}» und geöffnet.")
    # Zurück auf die Seite, von der aus die Datei angefordert wurde (nur eigene Seiten)
    back = request.META.get("HTTP_REFERER", "")
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
        return redirect("/")
    parts = urlsplit(back)
    return redirect(parts.path + (f"?{parts.query}" if parts.query else ""))


def open_file(path: Path) -> None:
    """Datei mit dem Standardprogramm des Systems öffnen."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    elif os.name == "nt":
        os.startfile(path)  # noqa: S606 - lokale, selbst erzeugte Datei
    else:
        subprocess.Popen(["xdg-open", str(path)])
