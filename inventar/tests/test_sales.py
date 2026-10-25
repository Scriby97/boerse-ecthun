import datetime as dt
from decimal import Decimal

from django.test import TestCase

from inventar import reports, sales
from inventar.models import Article, Category, ClubItem, Payout, Person, Sale, SaleItem
from inventar.pdf import payout_pdf, receipt_pdf


class SalesTests(TestCase):
    def setUp(self):
        self.anna = Person.objects.create(name="Muster Anna")
        self.eva = Person.objects.create(name="Eva", owner_share=Decimal("100"))
        cat = Category.objects.get(code=10)
        self.kleid = Article.objects.create(number=10001, category=cat, description="Kürkleid blau", size="8–10",
                                            owner=self.anna, price=Decimal("45"))
        self.spende = Article.objects.create(number=10002, category=cat, description="Röckli", owner=self.anna,
                                             price=Decimal("10"), owner_share=Decimal("0"))
        self.jacke = ClubItem.objects.get(name="Clubjacke neu", size="XS")
        self.jacke.stock = 3
        self.jacke.save()

    def entries(self):
        return [
            {"kind": "artikel", "article_id": self.kleid.pk, "description": "Kürkleid blau", "size": "8–10", "price": "45.00"},
            {"kind": "artikel", "article_id": self.spende.pk, "description": "Röckli", "size": "", "price": "10.00"},
            {"kind": "ohne_nummer", "owner_id": self.eva.pk, "description": "Haarschmuck", "size": "", "price": "8.00"},
            {"kind": "eigen", "description": "Leggins", "size": "S", "price": "12.00"},
            {"kind": "club", "club_item_id": self.jacke.pk, "description": "Clubjacke neu", "size": "XS", "price": "95.00"},
        ]

    def test_verkauf_teilt_jeden_posten_richtig_auf(self):
        sale = sales.create_sale(self.entries(), buyer=self.anna, date=dt.date(2026, 10, 21))
        self.assertEqual(sale.number, 1)
        self.assertEqual(sale.total, Decimal("170.00"))
        items = {i.description: i for i in sale.items.all()}
        self.assertEqual((items["Kürkleid blau"].owner_amount, items["Kürkleid blau"].shop_amount), (Decimal("29.25"), Decimal("15.75")))
        self.assertEqual((items["Röckli"].owner_amount, items["Röckli"].shop_amount), (Decimal("0.00"), Decimal("10.00")))
        self.assertEqual((items["Haarschmuck"].owner_amount, items["Haarschmuck"].shop_amount), (Decimal("8.00"), Decimal("0.00")))
        self.assertEqual(items["Leggins"].shop_amount, Decimal("12.00"))
        self.assertEqual((items["Clubjacke neu"].club_amount, items["Clubjacke neu"].shop_amount), (Decimal("92.70"), Decimal("2.30")))

        self.kleid.refresh_from_db()
        self.assertEqual((self.kleid.status, self.kleid.sold_date, self.kleid.buyer), (Article.Status.SOLD, dt.date(2026, 10, 21), self.anna))
        self.jacke.refresh_from_db()
        self.assertEqual(self.jacke.stock, 2)
        self.assertEqual(sales.open_amounts(), {self.anna.pk: Decimal("29.25"), self.eva.pk: Decimal("8.00")})

    def test_artikel_nicht_zweimal_verkaufen(self):
        sales.create_sale(self.entries()[:1])
        with self.assertRaises(sales.SaleError):
            sales.create_sale(self.entries()[:1])
        self.assertEqual(Sale.objects.count(), 1, "Der zweite Verkauf wird ganz zurückgenommen")

    def test_stornieren_bringt_alles_zurueck(self):
        sale = sales.create_sale(self.entries())
        sales.cancel_sale(sale)
        self.kleid.refresh_from_db()
        self.jacke.refresh_from_db()
        self.assertEqual((self.kleid.status, self.kleid.sold_date, self.kleid.owner_amount), (Article.Status.STOCK, None, None))
        self.assertEqual(self.jacke.stock, 3)
        self.assertEqual(sales.open_amounts(), {})

    def test_auszahlung_direkt_nach_verkauf_und_kein_storno_danach(self):
        sale = sales.create_sale(self.entries())
        payout = sales.record_payout(self.anna, Payout.Method.TWINT, day=sale.date)
        self.assertEqual(payout.amount, Decimal("29.25"))
        self.kleid.refresh_from_db()
        self.assertEqual((self.kleid.status, self.kleid.payout), (Article.Status.PAID, payout))
        self.assertEqual(sales.open_amounts(), {self.eva.pk: Decimal("8.00")})
        with self.assertRaises(sales.SaleError):
            sales.record_payout(self.anna, Payout.Method.CASH)
        with self.assertRaises(sales.SaleError):
            sales.cancel_sale(sale)

    def test_auszahlung_umfasst_verkaeufe_aus_der_alten_liste(self):
        cat = Category.objects.get(code=1)
        Article.objects.create(number=1001, category=cat, description="alt", owner=self.anna, price=Decimal("20"),
                               status=Article.Status.SOLD, sold_date=dt.date(2026, 9, 1), sale_price=Decimal("20"),
                               owner_amount=Decimal("13.00"), shop_amount=Decimal("7.00"))
        sales.create_sale(self.entries()[:1])
        self.assertEqual(sales.open_amounts()[self.anna.pk], Decimal("42.25"))
        payout = sales.record_payout(self.anna, Payout.Method.CASH)
        self.assertEqual(payout.amount, Decimal("42.25"))
        self.assertFalse(Article.objects.filter(status=Article.Status.SOLD, owner_amount__gt=0).exists())

    def test_uebersicht_pro_monat(self):
        sales.create_sale(self.entries(), date=dt.date(2026, 10, 21))
        cat = Category.objects.get(code=1)
        Article.objects.create(number=1001, category=cat, description="alt", owner=self.anna, price=Decimal("20"),
                               status=Article.Status.PAID, sold_date=dt.date(2026, 9, 1), sale_price=Decimal("20"),
                               owner_amount=Decimal("13.00"), shop_amount=Decimal("7.00"))
        groups = reports.summarize("monat")
        self.assertEqual([g.title for g in groups], ["Oktober 2026", "September 2026"])
        okt = groups[0]
        self.assertEqual((okt.count, okt.revenue, okt.owners, okt.shop, okt.own, okt.club),
                         (5, Decimal("170.00"), Decimal("37.25"), Decimal("40.05"), Decimal("12.00"), Decimal("92.70")))
        self.assertEqual(reports.totals(groups).revenue, Decimal("190.00"))
        self.assertEqual(reports.period_of(dt.date(2026, 10, 21), "woche")[0], "2026-W43")

    def test_quittung_als_pdf_ohne_artikelnummer(self):
        sale = sales.create_sale(self.entries())
        pdf = receipt_pdf(sale)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 5000, "mit Logo")
        self.assertEqual(SaleItem.objects.filter(sale=sale).count(), 5)


class DailyStatementTests(TestCase):
    def setUp(self):
        self.anna = Person.objects.create(name="Muster Anna")
        self.cat = Category.objects.get(code=1)

    def sell(self, number, day):
        a = Article.objects.create(number=number, category=self.cat, description=f"Artikel {number}",
                                   owner=self.anna, price=Decimal("10"))
        return sales.create_sale([{"kind": "artikel", "article_id": a.pk, "description": a.description,
                                   "price": "10.00"}], date=day)

    def test_mehrere_verkaeufe_eines_tages_eine_abrechnung(self):
        day1, day2 = dt.date(2026, 10, 24), dt.date(2026, 10, 25)
        self.sell(1001, day1)
        self.sell(1002, day1)
        self.sell(1003, day2)
        groups = sales.daily_groups()
        self.assertEqual([(g["day"], g["count"], g["amount"]) for g in groups],
                         [(day2, 1, Decimal("6.50")), (day1, 2, Decimal("13.00"))])

        payout = sales.record_payout(self.anna, Payout.Method.TWINT, day=day1, note="Tagesabrechnung 24.10.2026")
        self.assertEqual((payout.amount, payout.sale_items.count()), (Decimal("13.00"), 2))
        self.assertTrue(receipt_ok := payout_pdf(payout).startswith(b"%PDF"), receipt_ok)

        # Am Nachmittag abgeschlossen, danach noch ein Verkauf am selben Tag → neue Tagesabrechnung
        self.sell(1004, day1)
        self.assertEqual([(g["day"], g["count"]) for g in sales.daily_groups()], [(day2, 1), (day1, 1)])


class NavigationCountTests(TestCase):
    def test_zahl_offener_abrechnungen_in_der_navigation(self):
        from django.urls import reverse
        anna = Person.objects.create(name="Muster Anna")
        cat = Category.objects.get(code=1)
        page = self.client.get(reverse("start"))
        self.assertNotContains(page, 'class="nav-count"')
        for n, day in [(1001, dt.date(2026, 10, 24)), (1002, dt.date(2026, 10, 25))]:
            a = Article.objects.create(number=n, category=cat, description="x", owner=anna, price=Decimal("10"))
            sales.create_sale([{"kind": "artikel", "article_id": a.pk, "description": "x", "price": "10.00"}], date=day)
        self.assertContains(self.client.get(reverse("start")), 'aria-label="2 offene Abrechnungen">2</span>')
