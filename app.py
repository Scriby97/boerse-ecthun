"""Startet die Börsen-App: Datenbank vorbereiten, lokalen Server starten, App-Fenster öffnen.

Das ist der Einstieg der fertigen Mac-App. Ohne pywebview öffnet sich stattdessen der Browser.
"""

import os
import threading
import webbrowser


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "boerse.settings")

    import django

    django.setup()

    from django.core.management import call_command
    from waitress import create_server

    from boerse.wsgi import application

    # Neue Versionen bringen ihre Datenbank-Änderungen selbst mit
    call_command("migrate", interactive=False, verbosity=0)

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
        return

    webview.create_window("Börse EC Thun", url, width=1320, height=880, min_size=(1000, 680))
    webview.start()


if __name__ == "__main__":
    main()
