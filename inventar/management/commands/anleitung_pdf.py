"""Schreibt die Anleitung als PDF nach docs/Anleitung_BoerseApp.pdf (nach Änderungen an der Anleitung ausführen)."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string

from inventar.pdf import guide_pdf

TARGET = Path(settings.BASE_DIR) / "docs" / "Anleitung_BoerseApp.pdf"


class Command(BaseCommand):
    help = "Anleitung als PDF in docs/ schreiben"

    def handle(self, *args, **options):
        TARGET.parent.mkdir(exist_ok=True)
        TARGET.write_bytes(guide_pdf(render_to_string("inventar/_guide_content.html")))
        self.stdout.write(f"Geschrieben: {TARGET}")
