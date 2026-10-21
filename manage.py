#!/usr/bin/env python
"""Werkzeug für die Entwicklung (runserver, test, makemigrations).

Beim Entwickeln liegen die Daten im Ordner data/ des Projekts, nicht im Datenordner der fertigen App.
"""

import os
import sys
from pathlib import Path


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "boerse.settings")
    os.environ.setdefault("BOERSE_DATA_DIR", str(Path(__file__).resolve().parent / "data"))
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
