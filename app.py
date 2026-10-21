"""Startet die Börsen-App: Datenbank vorbereiten, lokalen Server starten, App-Fenster öffnen.

Das ist der Einstieg der fertigen Mac-App. Ohne pywebview öffnet sich stattdessen der Browser.
`--selftest` prüft die (verpackte) App ohne Fenster in einem Wegwerf-Datenordner.
"""

import os
import sys
import tempfile
import threading
import webbrowser


def setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "boerse.settings")

    import django

    django.setup()

    from django.core.management import call_command
    from django.core.management.commands.migrate import Command as Migrate

    # Neue Versionen bringen ihre Datenbank-Änderungen selbst mit.
    # Das Kommando direkt übergeben: in der verpackten App findet Django es nicht über den Namen.
    call_command(Migrate(), interactive=False, verbosity=0)


def selftest() -> int:
    """Lädt die wichtigsten Seiten und erzeugt je ein PDF; Ergebnis als Text, Rückgabewert 0 = alles gut."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.environ["BOERSE_DATA_DIR"] = tempfile.mkdtemp(prefix="boerse-selbsttest-")
    os.environ["BOERSE_ICLOUD_DIR"] = ""
    setup_django()

    from decimal import Decimal

    from django.test import Client

    from boerse import __version__
    from inventar import sales
    from inventar.models import Article, Category, Person

    anna = Person.objects.create(name="Selbsttest")
    article = Article.objects.create(number=10001, category=Category.objects.get(code=10), description="Testkleid",
                                     size="134", owner=anna, price=Decimal("45"))
    sale = sales.create_sale([{"kind": "artikel", "article_id": article.pk, "description": "Testkleid",
                               "size": "134", "price": "45.00"}])
    client = Client()
    checks = [
        ("Startseite", "/", b"Guten Tag"),
        ("Kasse", "/kasse/", b"Artikelnummer"),
        ("Inventar", "/artikel/?status=", b"Testkleid"),
        ("Gestaltung", "/static/inventar/app.css", b"--accent"),
        ("Quittung", f"/verkauf/{sale.pk}/quittung.pdf", b"%PDF"),
        ("Etiketten", "/etiketten.pdf?status=", b"%PDF"),
        ("Export", "/export/boerse.xlsx", b"PK"),
    ]
    failed = 0
    print(f"Börse EC Thun {__version__} – Selbsttest")
    for name, url, expected in checks:
        response = client.get(url)
        content = b"".join(response.streaming_content) if response.streaming else response.content
        ok = response.status_code == 200 and expected in content[:200000]
        failed += not ok
        print(f"  {'ok ' if ok else 'FEHLER'} {name} ({response.status_code})")
    print("Alles in Ordnung." if not failed else f"{failed} Prüfung(en) fehlgeschlagen.")
    return 1 if failed else 0


def main() -> None:
    if "--selftest" in sys.argv:
        sys.exit(selftest())

    setup_django()

    from waitress import create_server

    from boerse.wsgi import application
    from inventar import updates
    from inventar.backup import backup_database, ensure_daily_backup

    ensure_daily_backup()
    threading.Thread(target=updates.check, daemon=True).start()

    # Port 0: das Betriebssystem wählt einen freien Port, nur auf diesem Rechner erreichbar
    server = create_server(application, host="127.0.0.1", port=0, threads=4)
    url = f"http://127.0.0.1:{server.effective_port}/"
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    try:
        import webview
    except ImportError:
        webbrowser.open(url)
        print(f"Börse EC Thun läuft auf {url} – zum Beenden Ctrl+C drücken.")
        try:
            thread.join()
        except KeyboardInterrupt:
            pass
        backup_database("beim-schliessen")
        return

    # PDFs und Excel-Dateien speichern dürfen; Links nach aussen (z. B. neue Version) im Browser öffnen
    for key, value in {"ALLOW_DOWNLOADS": True, "OPEN_EXTERNAL_LINKS_IN_BROWSER": True}.items():
        if key in getattr(webview, "settings", {}):
            webview.settings[key] = value
    webview.create_window("Börse EC Thun", url, width=1320, height=880, min_size=(1000, 680))
    webview.start()
    # Fenster geschlossen: Stand sichern (lokal und in iCloud)
    backup_database("beim-schliessen")


if __name__ == "__main__":
    main()
