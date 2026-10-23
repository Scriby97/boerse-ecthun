"""Übernahme früherer Clubverkäufe aus CSV (erfundene Namen)."""

import datetime as dt
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from inventar import club_import, sales
from inventar.models import ClubItem, ClubStatement, SaleItem

CSV = """Datum;Artikel;Grösse;Käuferin;Preis;an Club;abgerechnet
21.12.2025;Jacke Frauen Jiv;150;;95.00;95.00;ja
28.02.2026;Jacke Mondor;10-12;;55.00;55.00;ja
26.06.2026;Hose EC Thun;L;Beispiel Julia;79.00;79.00;nein
13.07.2026;Clubjacke neu;150;Beispiel Diana;95.00;92.70;nein
"""


class ClubImportTests(TestCase):
    def test_uebernahme_mit_abgerechneten_und_offenen(self):
        stock_before = {(c.name, c.size): c.stock for c in ClubItem.objects.all()}
        stats = club_import.import_rows(club_import.parse(CSV))
        self.assertEqual(stats, {"created": 4, "skipped": 0, "settled": 2})

        old = ClubStatement.objects.get()
        self.assertEqual((old.end_date, old.total), (dt.date(2026, 2, 28), Decimal("150.00")))
        open_items = list(sales.open_club_items(dt.date(2026, 12, 31)))
        self.assertEqual([(i.description, i.size, i.club_amount, i.sale.buyer.name) for i in open_items], [
            ("Hose EC Thun", "L", Decimal("79.00"), "Beispiel Julia"),
            ("Clubjacke neu", "150", Decimal("92.70"), "Beispiel Diana"),
        ])
        # Bestand bleibt; ausverkaufte Grösse wird ohne Bestand angelegt
        for item in ClubItem.objects.all():
            self.assertEqual(item.stock, stock_before.get((item.name, item.size), 0))
        self.assertTrue(ClubItem.objects.filter(name="Jacke Mondor", size="10-12", stock=0).exists())

    def test_doppelt_hochladen_wird_uebersprungen(self):
        club_import.import_rows(club_import.parse(CSV))
        stats = club_import.import_rows(club_import.parse(CSV))
        self.assertEqual((stats["created"], stats["skipped"]), (0, 4))
        self.assertEqual(SaleItem.objects.filter(kind="club").count(), 4)

    def test_fehlerhafte_datei(self):
        with self.assertRaises(club_import.ClubImportFehler):
            club_import.parse("Name;Preis\nx;1\n")
        with self.assertRaises(club_import.ClubImportFehler):
            club_import.parse("Datum;Artikel;an Club\nirgendwann;Jacke;5\n")

    def test_ueber_die_seite(self):
        response = self.client.post(reverse("club_import_csv"),
                                    {"file": SimpleUploadedFile("club.csv", CSV.encode("utf-8"))}, follow=True)
        self.assertContains(response, "4 Clubverkäufe übernommen, davon 2 schon beglichen")
        self.assertContains(response, "Beispiel Diana")
        self.assertContains(response, "Verkaufte Clubartikel (4)")
