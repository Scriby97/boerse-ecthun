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

## Aufbau

- `boerse/` – Django-Projekt (Einstellungen, Datenordner)
- `inventar/models.py` – Kategorien (Nummernkreise), Personen, Artikel, Einstellungen
- `inventar/normalize.py` – bereinigt Werte aus der alten Liste (Grössen, Preise, Kontakte, Daten)
- `inventar/importer.py` – Import: lesen → prüfen (Vorschau, nichts gespeichert) → übernehmen
- `inventar/money.py` – Aufteilung Besitzerin/Börse (Standard 65/35, auf 5 Rappen)
- `inventar/backup.py` – Sicherung der Datenbank (vor jedem Import)
- `app.py` – Start der fertigen App

## Stand

Phase 1 (Import und Inventar): Kategorien, Erfassen mit Nummernvorschlag und Serienerfassung, Inventar mit Suche,
Kundendatei, Import mit Vorschau und Prüfliste, Sicherung vor dem Import.

Als Nächstes (Phase 2): Kasse, Quittung als PDF, Verkauft-Liste, Auszahlungen.
