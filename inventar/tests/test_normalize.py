import datetime as dt
from decimal import Decimal

from django.test import SimpleTestCase

from inventar.money import split
from inventar.normalize import normalize_size, parse_contact, parse_price, text, to_date, to_int


class NormalizeTests(SimpleTestCase):
    def test_text_vereinheitlicht_zahlen_und_mac_umlaute(self):
        self.assertEqual(text(140.0), "140")
        self.assertEqual(text("Börse"), "Börse")
        self.assertEqual(text(None), "")

    def test_groessen(self):
        for raw in ["8 bis 10", "8-10", "8bis 10", "8 - 10", "8–10"]:
            self.assertEqual(normalize_size(raw), "8–10", raw)
        self.assertEqual(normalize_size(134.0), "134")
        self.assertEqual(normalize_size("-"), "")
        self.assertEqual(normalize_size("CL/152"), "CL/152")
        self.assertEqual(normalize_size("ca. 140"), "ca. 140")

    def test_preise(self):
        self.assertEqual(parse_price(45.0), (Decimal("45.00"), "", True))
        self.assertEqual(parse_price("12.50"), (Decimal("12.50"), "", True))
        self.assertEqual(parse_price("CHF 20.-"), (Decimal("20.00"), "", True))
        self.assertEqual(parse_price("gratis"), (Decimal("0.00"), "gratis", True))
        self.assertEqual(parse_price("-"), (Decimal("0.00"), "gratis", True))
        self.assertEqual(parse_price("40-50"), (Decimal("50.00"), "verhandelbar bis 40.00", True))
        self.assertEqual(
            parse_price("verhandelbar 30 - 40.00"), (Decimal("40.00"), "verhandelbar bis 30.00", True)
        )
        self.assertEqual(parse_price("nach Absprache"), (None, "nach Absprache", False))

    def test_kontakt(self):
        contact = parse_contact("Muster Anna, 079 123 45 67, hat Twint, anna@example.ch")
        self.assertEqual(contact["phone"], "079 123 45 67")
        self.assertEqual(contact["email"], "anna@example.ch")
        self.assertTrue(contact["twint"])
        self.assertEqual(parse_contact("+41791234567")["phone"], "079 123 45 67")
        self.assertEqual(parse_contact("")["phone"], "")

    def test_daten_und_zahlen(self):
        self.assertEqual(to_date(dt.datetime(2025, 4, 11)), dt.date(2025, 4, 11))
        self.assertEqual(to_date("11.4.25"), dt.date(2025, 4, 11))
        self.assertIsNone(to_date("irgendwann"))
        self.assertEqual(to_int(1096.0), 1096)
        self.assertIsNone(to_int(10.5))

    def test_aufteilung_65_35_auf_5_rappen(self):
        self.assertEqual(split(Decimal("45"), Decimal("65")), (Decimal("29.25"), Decimal("15.75")))
        self.assertEqual(split(Decimal("7"), Decimal("65")), (Decimal("4.55"), Decimal("2.45")))
        self.assertEqual(split(Decimal("13.90"), Decimal("65")), (Decimal("9.05"), Decimal("4.85")))
        self.assertEqual(split(Decimal("10"), Decimal("0")), (Decimal("0.00"), Decimal("10.00")))
