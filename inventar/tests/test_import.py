"""Import mit einer erfundenen Liste im Aufbau von Stephanies Numbers-Datei (keine echten Personendaten)."""

import datetime as dt
import tempfile
from decimal import Decimal
from pathlib import Path

from django.test import TestCase
from openpyxl import Workbook

from inventar import importer
from inventar.models import Article, Category, Person

HEADER = [
    None, "Datum", "Kleidungsstück", "Grösse", "Besitzer", "Kontakt", "Verkaufspreis ", "Code", "Inventar-Nr",
    "verkauft", "Nettoerlös Börsenbesitzerin", "Nettoerlös Besitzer", "Käufer", "Status", None,
]
D = dt.datetime


def sample_rows():
    return [
        [None] * 15,
        [None, None, None, None, None, None, 999.0, None, None, None, 10.5, 19.5, None, None, None],
        [None] * 15,
        HEADER,
        [None, D(2024, 1, 5), "schwarze Trainingsleggins", 134.0, "Muster Anna", "079 111 22 33 hat Twint", 5.0, 1.0, 1006.0, None, " ", " ", None, "offen", None],
        [None, D(2024, 2, 1), "Kürkleid blau", "8 bis 10", "Muster Anna", "079 444 55 66", 45.0, 10.0, 10001.0, D(2024, 3, 1), 15.75, 29.25, "Käuferin Berta", "zur Abrechung", "Abgerechnet"],
        [None, D(2024, 2, 2), "Jüpli rosa", "XS", "Beispiel Clara", None, 10.0, 11.0, 11001.0, D(2024, 3, 2), 3.5, 6.5, None, "zur Abrechung", None],
        [None, D(2024, 2, 3), "Body hautfarben", "S", "Beispiel Clara", None, "40-50", 12.0, 12001.0, None, None, None, None, "offen", None],
        [None, D(2024, 2, 4), "zweiter Artikel 1006", "M", "Beispiel Clara", None, 8.0, 1.0, 1006.0, None, None, None, None, "offen", None],
        [None, D(2024, 10, 16), "Handschuhe", "-", "Spenderin Doris", "möchte nichts dafür", 10.0, 3.0, 3001.0, D(2016, 1, 2), 10.0, 0.0, None, "zur Abrechung", "Abgerechnet"],
        [None, None, None, None, None, None, None, None, None, None, None, None, None, "offen", None],
        [None, None, None, None, None, None, None, None, None, None, None, None, None, "offen", None],
    ]


def write_xlsx(rows) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    path = Path(tempfile.mkdtemp()) / "liste.xlsx"
    workbook.save(path)
    return path


class ImportTests(TestCase):
    def analyze(self):
        rows = importer.read_rows(write_xlsx(sample_rows()))
        return importer.analyze(rows, {c.code: c.start_number for c in Category.objects.all()})

    def test_vorschau_erkennt_bestand_und_unstimmigkeiten(self):
        result = self.analyze()
        summary = result["summary"]
        self.assertEqual(summary["articles"], 6)
        self.assertEqual(summary["empty_rows"], 2)
        self.assertEqual((summary["stock"], summary["sold"], summary["paid"]), (3, 1, 2))
        self.assertEqual(summary["donated"], 1)
        self.assertEqual(summary["owners"], 3)
        self.assertEqual(summary["buyers_only"], 1)
        types = sorted(i["type"] for i in result["issues"])
        self.assertEqual(types, ["contact", "duplicate", "price", "sold_before_intake"])
        self.assertEqual(Article.objects.count(), 0, "Die Vorschau speichert nichts")

    def test_import_mit_entscheidungen(self):
        result = self.analyze()
        issues = {i["type"]: i for i in result["issues"]}
        dup = issues["duplicate"]
        decisions = {
            dup["id"]: str(dup["rows"][1]),  # der zweite Artikel behält 1006
            issues["price"]["id"]: "45",
            issues["sold_before_intake"]["id"]: "2025-01-02",
            issues["contact"]["id"]: "1",  # älterer Kontakt
        }
        stats = importer.apply(result, decisions)

        self.assertEqual(stats["articles"], 6)
        self.assertEqual(Person.objects.count(), 4)
        self.assertEqual(Article.objects.get(number=1006).description, "zweiter Artikel 1006")
        renumbered = Article.objects.get(description="schwarze Trainingsleggins")
        self.assertEqual(renumbered.number, 1007)
        self.assertEqual(stats["renumbered"], [(1006, 1007, "schwarze Trainingsleggins")])

        kleid = Article.objects.get(number=10001)
        self.assertEqual(kleid.status, Article.Status.PAID)
        self.assertEqual(kleid.size, "8–10")
        self.assertEqual((kleid.owner_amount, kleid.shop_amount), (Decimal("29.25"), Decimal("15.75")))
        self.assertEqual(kleid.buyer.name, "Käuferin Berta")

        self.assertEqual(Article.objects.get(number=11001).status, Article.Status.SOLD)
        body = Article.objects.get(number=12001)
        self.assertEqual((body.price, body.price_note), (Decimal("45.00"), "40-50"))

        handschuhe = Article.objects.get(number=3001)
        self.assertTrue(handschuhe.is_donated)
        self.assertEqual(handschuhe.sold_date, dt.date(2025, 1, 2))
        self.assertEqual(handschuhe.size, "")

        anna = Person.objects.get(name="Muster Anna")
        self.assertEqual(anna.phone, "079 111 22 33")
        self.assertTrue(anna.twint)

    def test_import_ersetzt_bisherigen_bestand(self):
        result = self.analyze()
        importer.apply(result, {})
        importer.apply(result, {})
        self.assertEqual(Article.objects.count(), 6)
        self.assertEqual(Person.objects.count(), 4)

    def test_datei_ohne_inventarspalte(self):
        with self.assertRaises(importer.ImportFehler):
            importer.read_rows(write_xlsx([["Name", "Preis"], ["x", 1]]))
