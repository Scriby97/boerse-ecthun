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
        self.assertContains(detail, "Jetzt auszahlen")
        pdf = self.client.get(reverse("sale_receipt", args=[sale.pk]))
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

        self.client.post(reverse("sale_payout", args=[sale.pk]), {"person": self.anna.pk, "method": "twint"})
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
