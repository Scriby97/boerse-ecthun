# Börse EC Thun

Lokale App für Stephanie Luginbühls Second-Hand-Börse (Eiskunstlaufkleider): Inventar, Kundendatei,
Import der bisherigen Numbers-Liste; später Kasse, Quittungen, Auszahlungen und Clubabrechnung.
Läuft nur auf Stephanies Mac, ohne Internet. Beschrieb: https://claude.ai/artifact/YRt3EmiuAD4g41gdTuSeHf

**Personendaten:** `material/` (Stephanies Originaldateien) und `data/` (lokale Datenbank) sind in `.gitignore`
und dürfen nie ins Repo.

## Technik

Python 3.13, Django 5.2, SQLite. Oberfläche mit Django-Templates und eigenem CSS (kein Build-Schritt).
Import mit `numbers-parser` (Numbers) und `openpyxl` (Excel). Fertige App: `app.py` startet einen lokalen Server
(waitress) und ein Fenster (pywebview).

## Entwickeln (Windows oder Mac)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Mac: .venv/bin/python
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py runserver                  # http://127.0.0.1:8000
.venv/Scripts/python manage.py test
```

Beim Entwickeln liegen Datenbank und Sicherungen in `data/`. Die fertige App nutzt den Datenordner des Systems
(Mac: `~/Library/Application Support/BoerseECThun`, Windows: `%APPDATA%\BoerseECThun`), änderbar mit `BOERSE_DATA_DIR`.

Wie die fertige App starten: `pip install -r requirements-desktop.txt`, dann `python app.py`.
`python app.py --selftest` prüft die App ohne Fenster in einem Wegwerf-Datenordner.

## Anleitung

Die Anleitung für Stephanie (und eine Nachfolgerin) steht in der App unter «Anleitung» und als PDF in
`docs/Anleitung_BoerseApp.pdf`. Beides kommt aus `inventar/templates/inventar/_guide_content.html`; nach Änderungen
das PDF mit `python manage.py anleitung_pdf` neu schreiben.

## Mac-App bauen und ausliefern

GitHub Actions (`.github/workflows/build.yml`) testet bei jedem Push und baut die Mac-App für Apple-Chip und Intel
(PyInstaller, Rezept `boerse.spec`), inklusive Selbsttest der fertigen App, versiegelt sie (Ad-hoc-Signatur, ohne
Apple-Entwicklerkonto) und prüft die Signatur. Pro Chip entstehen ein DMG (Installation: App auf «Programme» ziehen)
und ein ZIP (für den Update-Knopf); beim Lauf unter «Artifacts».

Neue Version ausliefern:
1. `__version__` in `boerse/__init__.py` erhöhen, committen
2. `git tag v1.0.1 && git push origin master v1.0.1`
3. GitHub legt ein Release mit DMG und ZIP für beide Chips an. Die App zeigt beim nächsten Start (mit Internet)
   «Jetzt aktualisieren»: sie lädt das ZIP selbst (ohne Quarantäne, also ohne Meldung von macOS), schliesst sich,
   ersetzt sich im Ordner Programme und startet neu (`inventar/updates.py`).

Erste Installation aus dem Internet: macOS meldet «nicht überprüft», Freigabe einmalig unter Systemeinstellungen >
Datenschutz & Sicherheit > «Dennoch öffnen» (steht in der Anleitung). Erscheint stattdessen «beschädigt», ist die
Signatur ungültig – der Bau prüft das und bricht dann ab.

Lokal (Windows) lässt sich das Verpacken mit `pyinstaller --noconfirm boerse.spec` testen,
dann `dist/BoerseECThun/BoerseECThun.exe --selftest`.

## Aufbau

- `boerse/` – Django-Projekt (Einstellungen, Datenordner)
- `inventar/models.py` – Kategorien (Nummernkreise), Personen, Artikel, Einstellungen
- `inventar/normalize.py` – bereinigt Werte aus der alten Liste (Grössen, Preise, Kontakte, Daten)
- `inventar/importer.py` – Import: lesen → prüfen (Vorschau, nichts gespeichert) → übernehmen
- `inventar/money.py` – Aufteilung Besitzerin/Börse (Standard 65/35, auf 5 Rappen)
- `inventar/backup.py` – Sicherung der Datenbank (vor jedem Import)
- `inventar/sales.py` – Kasse: Verkauf anlegen/stornieren, offene Beträge, Auszahlungen
- `inventar/reports.py` – Verkauft-Übersicht pro Woche, Monat, Jahr
- `inventar/pdf.py` – PDFs: Kaufquittung, Clubabrechnung, Abrechnung Besitzerin, Etiketten 57 × 32 mm (fpdf2)
- `inventar/exports.py` – Excel: Gesamtexport und Etiketten-Tabelle für DYMO Connect
- `app.py` – Start der fertigen App

## Stand

Phase 1 (Import und Inventar): Kategorien, Erfassen mit Nummernvorschlag und Serienerfassung, Inventar mit Suche,
Kundendatei, Import mit Vorschau und Prüfliste, Sicherung vor dem Import.

Phase 2 (Kasse und Verkauf): Kasse mit Nummerneingabe (fragt bei 1096/1096+ nach), Artikel ohne Nummer
(eigene oder einer Besitzerin wie Eva), Clubartikel mit Bestand, Preis an der Kasse änderbar, Quittung als PDF,
Storno, Auszahlung direkt nach dem Verkauf oder gesammelt unter «Abrechnen», Verkauft-Übersicht.
Der Import ist gesperrt, sobald es Verkäufe oder Auszahlungen gibt.

Phase 3 (Abrechnungen und Export): Clubabrechnung per Stichtag (Vorschau, PDF im Layout der Pages-Quittung,
nicht doppelt), frühere Clubverkäufe nachtragen (ohne Bestandsänderung), Abrechnung pro Auszahlung als PDF,
Etiketten als PDF (direkt auf dem LabelWriter) oder Excel (DYMO Connect), Gesamtexport Excel, Einstellungen,
Sicherungen: täglich, beim Schliessen, vor Import/Wiederherstellen; lokal und in iCloud Drive, je 30 Stück.

Phase 4 (Mac-App): eigenes Fenster (pywebview, Downloads erlaubt), Selbsttest, PyInstaller-Rezept,
Bau und Release über GitHub Actions, Hinweis auf neue Versionen auf der Startseite.
