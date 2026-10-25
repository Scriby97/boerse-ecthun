"""Numbers-Export im Aufbau der ursprünglichen Liste; die Datei muss sich wieder importieren lassen."""

import datetime as dt
import tempfile
from decimal import Decimal
from pathlib import Path

from django.test import TestCase
from django.urls import reverse
from numbers_parser import Document

from inventar import importer, numbers_export, sales
from inventar.models import Article, Category, ClubItem, Payout, Person, SaleItem


class NumbersExportTests(TestCase):
    def setUp(self):
        self.anna = Person.objects.create(name="Muster Anna", phone="079 000 00 00", twint=True)
        self.bea = Person.objects.create(name="Beispiel Bea")
        kleider = Category.objects.get(code=10)
        self.offen = Article.objects.create(number=10001, category=kleider, description="Kleid", size="134",
                                            owner=self.anna, price=Decimal("45"), extra_info="mit Gurt",
                                            intake_date=dt.date(2026, 9, 1))
        self.verkauft = Article.objects.create(number=10002, category=kleider, description="Body", owner=self.anna,
                                               price=Decimal("50"), price_note="verhandelbar bis 40.00",
                                               intake_date=dt.date(2026, 9, 1))
        self.doppelt = Article.objects.create(number=10002, number_suffix="+", category=kleider,
                                              description="Rock", owner=self.anna, price=Decimal("0"),
                                              price_note="gratis")
        self.ausbezahlt = Article.objects.create(number=10003, category=kleider, description="Jacke",
                                                 owner=self.bea, price=Decimal("30.50"),
                                                 intake_date=dt.date(2026, 9, 1))
        jacke = ClubItem.objects.get(name="Clubjacke neu", size="XS")
        day = dt.date(2026, 10, 24)
        sales.create_sale([{"kind": "artikel", "article_id": self.ausbezahlt.pk, "description": "Jacke",
                            "price": "30.50"}], buyer=self.anna, date=day)
        sales.record_payout(self.bea, Payout.Method.CASH, day=day)
        sales.create_sale([
            {"kind": "artikel", "article_id": self.verkauft.pk, "description": "Body", "price": "50.00"},
            {"kind": SaleItem.Kind.OWN, "description": "Mütze", "price": "5.00"},
            {"kind": SaleItem.Kind.CLUB, "club_item_id": jacke.pk, "description": jacke.name, "size": "XS",
             "price": str(jacke.customer_price)},
        ], buyer=self.bea, date=day)

    def export(self) -> Path:
        folder = Path(tempfile.mkdtemp())
        path = folder / "export.numbers"
        path.write_bytes(numbers_export.build())
        return path

    def test_aufbau_wie_die_urspruengliche_liste(self):
        doc = Document(str(self.export()))
        self.assertEqual([s.name for s in doc.sheets], ["Komplette Liste", "Ohne Nummer", "Clubbestand", "Clubverkäufe"])
        rows = doc.sheets[0].tables[0].rows(values_only=True)
        self.assertEqual(rows[3][1:14], numbers_export.HEADER[1:14])
        body = {(r[8], r[2]): r for r in rows[4:]}
        kleid = body[(10001, "Kleid (mit Gurt)")]
        self.assertEqual((kleid[3], kleid[4], kleid[6], kleid[7], kleid[13]), ("134", "Muster Anna", 45, 10, "offen"))
        self.assertEqual(kleid[5], "079 000 00 00, hat Twint")
        self.assertEqual(body[(10002, "Body")][6], "40-50")
        self.assertEqual(body[(10002, "Rock")][6], "gratis")
        jacke = body[(10003, "Jacke")]
        self.assertEqual((jacke[12], jacke[13], jacke[14]), ("Muster Anna", "zur Abrechung", "Abgerechnet"))
        self.assertEqual(rows[1][6], 125.5)

    def test_laesst_sich_wieder_importieren(self):
        path = self.export()
        categories = {c.code: c.start_number for c in Category.objects.all()}
        result = importer.analyze(importer.read_rows(path), categories)
        summary = result["summary"]
        self.assertEqual((summary["articles"], summary["stock"], summary["sold"], summary["paid"]), (4, 2, 1, 1))
        self.assertEqual([i["type"] for i in result["issues"]], ["duplicate"])
        body = next(a for a in result["articles"] if a["description"] == "Body")
        self.assertEqual((body["price"], body["price_note"]), ("50.00", "verhandelbar bis 40.00"))
        club = importer.read_club(path)
        self.assertEqual(len(club["stock"]), ClubItem.objects.count())
        self.assertEqual([(s["name"], s["size"], s["buyer"], s["settled"]) for s in club["sales"]],
                         [("Clubjacke neu", "XS", "Beispiel Bea", False)])

    def test_ohne_nummer(self):
        rows = Document(str(self.export())).sheets["Ohne Nummer"].tables[0].rows(values_only=True)
        self.assertEqual(rows[1][1:5], ["Mütze", None, "eigener Artikel", 5])

    def test_download(self):
        response = self.client.get(reverse("export_numbers"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(".numbers", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"PK"))
