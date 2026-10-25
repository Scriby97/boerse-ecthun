from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from inventar.models import Article, Category, ClubItem, Payout, Person, Sale


class KasseViewTests(TestCase):
    def setUp(self):
        self.anna = Person.objects.create(name="Muster Anna", twint=True)
        cat = Category.objects.get(code=1)
        self.a = Article.objects.create(number=1096, category=cat, description="Leggins schwarz", owner=self.anna,
                                        price=Decimal("5"))
        self.b = Article.objects.create(number=1096, number_suffix="+", category=cat, description="Leggins grau",
                                        owner=self.anna, price=Decimal("6"))
        self.c = Article.objects.create(number=1097, category=cat, description="Leggins blau", owner=self.anna,
                                        price=Decimal("7"), price_note="verhandelbar bis 5.00")

    def add(self, nummer):
        return self.client.post(reverse("kasse_add_number"), {"nummer": nummer}, follow=True)

    def test_seiten_laden(self):
        for name in ["kasse", "sale_list", "payout_list", "club_items"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        for period in ["woche", "monat", "jahr"]:
            self.assertEqual(self.client.get(reverse("sale_list"), {"periode": period}).status_code, 200)

    def test_nummer_eingeben_und_verkaufen(self):
        response = self.add("1097")
        self.assertContains(response, "Leggins blau")
        self.assertContains(response, "verhandelbar bis 5.00")
        self.client.post(reverse("kasse_price", args=[0]), {"price": "6,50"})
        response = self.client.post(
            reverse("kasse_checkout"), {"payment": "twint", "date": "2026-10-21", "new_buyer": "Käuferin Berta"}
        )
        sale = Sale.objects.get()
        self.assertRedirects(response, reverse("sale_detail", args=[sale.pk]))
        self.assertEqual(sale.total, Decimal("6.50"))
        self.assertEqual(sale.buyer.name, "Käuferin Berta")
        self.c.refresh_from_db()
        self.assertEqual((self.c.status, self.c.sale_price), (Article.Status.SOLD, Decimal("6.50")))
        self.assertEqual(self.client.session["kasse"], [])

        detail = self.client.get(reverse("sale_detail", args=[sale.pk]))
        self.assertContains(detail, "kommen auf die Tagesabrechnung")
        pdf = self.client.get(reverse("sale_receipt", args=[sale.pk]))
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

        self.client.post(reverse("payout_person", args=[self.anna.pk]), {"method": "twint", "day": "2026-10-21"})
        self.assertEqual(Payout.objects.get().amount, Decimal("4.25"))

    def test_doppelte_nummer_fragt_nach(self):
        response = self.add("1096")
        self.assertContains(response, "Diese Nummer gibt es mehrfach")
        self.assertEqual(self.client.session.get("kasse", []), [])
        self.client.post(reverse("kasse_add_article", args=[self.b.pk]))
        self.assertEqual([e["label"] for e in self.client.session["kasse"]], ["1096+"])
        response = self.add("1096")
        self.assertEqual([e["label"] for e in self.client.session["kasse"]], ["1096+", "1096"])

    def test_nummer_mit_plus_direkt(self):
        self.add("1096+")
        self.assertEqual([e["label"] for e in self.client.session["kasse"]], ["1096+"])

    def test_unbekannte_und_verkaufte_nummer(self):
        self.assertContains(self.add("9999"), "gibt es nicht")
        self.c.status = Article.Status.SOLD
        self.c.save()
        self.assertContains(self.add("1097"), "nicht an Lager")

    def test_artikel_ohne_nummer_und_clubartikel(self):
        self.client.post(reverse("kasse_add_other"), {"description": "Haarschmuck", "price": "8"})
        jacke = ClubItem.objects.get(name="Clubjacke neu", size="XS")
        self.client.post(reverse("kasse_add_club"), {"club_item": jacke.pk, "size": "XS"})
        cart = self.client.session["kasse"]
        self.assertEqual([(e["kind"], e["price"]) for e in cart], [("eigen", "8.00"), ("club", "95.00")])
        self.client.post(reverse("kasse_remove", args=[0]))
        self.assertEqual(len(self.client.session["kasse"]), 1)

    def test_storno_ueber_die_seite(self):
        self.add("1097")
        self.client.post(reverse("kasse_checkout"), {"payment": "bar", "date": "2026-10-21"})
        sale = Sale.objects.get()
        self.client.post(reverse("sale_cancel", args=[sale.pk]))
        self.c.refresh_from_db()
        self.assertEqual(self.c.status, Article.Status.STOCK)

    def test_import_gesperrt_sobald_verkauft_wurde(self):
        self.add("1097")
        self.client.post(reverse("kasse_checkout"), {"payment": "bar", "date": "2026-10-21"})
        self.assertContains(self.client.get(reverse("import_upload")), "ist deshalb gesperrt")

    def test_abrechnen_zahlt_alles_offene_aus(self):
        self.add("1097")
        self.add("1096+")
        self.client.post(reverse("kasse_checkout"), {"payment": "bar", "date": "2026-10-21"})
        self.assertContains(self.client.get(reverse("payout_list")), "Muster Anna")
        self.client.post(reverse("payout_person", args=[self.anna.pk]), {"method": "bar"})
        self.assertEqual(Payout.objects.get().amount, Decimal("8.45"))
        self.assertContains(self.client.get(reverse("payout_list")), "Alles ausbezahlt")


class ReceiptDescriptionTests(TestCase):
    def setUp(self):
        anna = Person.objects.create(name="Muster Anna")
        cat = Category.objects.get(code=10)
        self.article = Article.objects.create(number=10001, category=cat, description="Kürkleid blau",
                                              extra_info="kleiner Fleck am Ärmel", owner=anna, price=Decimal("45"))

    def test_zusatzinformation_nicht_auf_der_quittung_und_bezeichnung_anpassen(self):
        self.client.post(reverse("kasse_add_number"), {"nummer": "10001"})
        self.assertContains(self.client.get(reverse("kasse")), "kleiner Fleck am Ärmel")
        self.client.post(reverse("kasse_checkout"), {"payment": "bar", "date": "2026-10-23"})
        sale = Sale.objects.get()
        item = sale.items.get()
        detail = self.client.get(reverse("sale_detail", args=[sale.pk]))
        self.assertContains(detail, 'value="Kürkleid blau"')

        response = self.client.post(reverse("sale_descriptions", args=[sale.pk]),
                                    {f"bezeichnung-{item.pk}": "Kürkleid hellblau mit Glitzer", "pdf": "1"})
        self.assertRedirects(response, reverse("sale_receipt", args=[sale.pk]), fetch_redirect_response=False)
        item.refresh_from_db()
        self.article.refresh_from_db()
        self.assertEqual(item.description, "Kürkleid hellblau mit Glitzer")
        self.assertEqual(self.article.description, "Kürkleid blau", "Inventar bleibt unverändert")

        from inventar.pdf import receipt_pdf
        import zlib, re
        pdf = receipt_pdf(sale)
        text = b"".join(zlib.decompress(m) for m in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S)
                        if m[:2] in (b"x\x9c", b"x\xda"))
        self.assertIn(b"hellblau", text)
        self.assertNotIn(b"Fleck", text)

    def test_zusatzinformation_beim_erfassen(self):
        response = self.client.post(reverse("article_create"), {
            "category": Category.objects.get(code=10).pk, "number": 10002, "new_owner": "Neu Nina",
            "description": "Röckli", "extra_info": "Marke Jiv, wie neu", "intake_date": "2026-10-23",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Article.objects.get(number=10002).extra_info, "Marke Jiv, wie neu")
        self.assertContains(self.client.get(reverse("article_list"), {"q": "Jiv"}), "Röckli")


class SaleBuyerTests(TestCase):
    def test_kaeuferin_nachtraeglich(self):
        anna = Person.objects.create(name="Muster Anna")
        cat = Category.objects.get(code=1)
        article = Article.objects.create(number=1001, category=cat, description="Leggins", owner=anna,
                                         price=Decimal("5"))
        from inventar import sales
        sale = sales.create_sale([{"kind": "artikel", "article_id": article.pk, "description": "Leggins",
                                   "price": "5.00"}])
        self.assertContains(self.client.get(reverse("sale_detail", args=[sale.pk])), "Käuferin speichern")
        self.client.post(reverse("sale_buyer", args=[sale.pk]), {"new_buyer": "Neu  Nina"})
        sale.refresh_from_db()
        article.refresh_from_db()
        self.assertEqual((sale.buyer.name, article.buyer.name), ("Neu Nina", "Neu Nina"))
        self.client.post(reverse("sale_buyer", args=[sale.pk]), {"buyer": anna.pk})
        sale.refresh_from_db()
        self.assertEqual(sale.buyer, anna)
        self.assertEqual(Person.objects.filter(name="Neu Nina").count(), 1)


class ReceiptWithoutNumberTests(TestCase):
    def test_keine_quittungsnummer_auf_der_quittung(self):
        import re
        import zlib

        from inventar import sales
        from inventar.pdf import receipt_pdf
        for _ in range(3):
            sale = sales.create_sale([{"kind": "eigen", "description": "Band", "price": "2.00"}])
        pdf = receipt_pdf(sale)
        text = b"".join(zlib.decompress(m) for m in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S)
                        if m[:2] in (b"x\x9c", b"x\xda"))
        self.assertNotIn(b"Nr. 3", text)
        self.assertIn(sale.date.strftime("%d.%m.%Y").encode(), text)
