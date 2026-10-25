from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from inventar import persons, sales
from inventar.models import Article, Category, Person


class PersonListTests(TestCase):
    def setUp(self):
        cat = Category.objects.get(code=1)
        self.names = ["Zürcher Ida", "ärni Anna", "Bauer Bea", "Ödegaard Olga", "meier Max"]
        people = {n: Person.objects.create(name=n) for n in self.names}
        for i in range(3):
            Article.objects.create(number=1000 + i, category=cat, description="Leggins", owner=people["meier Max"],
                                   price=Decimal("5"))
        Article.objects.create(number=1010, category=cat, description="Hose", owner=people["Bauer Bea"],
                               price=Decimal("8"))
        sales.create_sale([{"kind": "eigen", "description": "Socken", "price": "3.00"},
                           {"kind": "eigen", "description": "Band", "price": "2.00"}], buyer=people["Zürcher Ida"])

    def test_alphabetisch_ohne_gross_klein_und_umlaute(self):
        self.assertEqual([p.name for p in persons.listing()],
                         ["ärni Anna", "Bauer Bea", "meier Max", "Ödegaard Olga", "Zürcher Ida"])
        self.assertEqual([p.name for p in persons.listing(sort="-name")][0], "Zürcher Ida")

    def test_sortieren_nach_bestand_und_gekauft(self):
        self.assertEqual([p.name for p in persons.listing(sort="bestand")][:2], ["meier Max", "Bauer Bea"])
        top = persons.listing(sort="gekauft")[0]
        self.assertEqual((top.name, top.bought), ("Zürcher Ida", 2))

    def test_seite_mit_sortierung(self):
        response = self.client.get(reverse("person_list"), {"sortierung": "bestand"})
        self.assertContains(response, 'value="bestand" selected')
        self.assertEqual(self.client.get(reverse("person_list"), {"sortierung": "quatsch"}).status_code, 200)


class PersonOverviewTests(TestCase):
    def test_eingebracht_verkauft_gekauft_mit_totalen(self):
        anna = Person.objects.create(name="Muster Anna")
        berta = Person.objects.create(name="Käuferin Berta")
        cat = Category.objects.get(code=10)
        Article.objects.create(number=10001, category=cat, description="Kleid rot", owner=anna, price=Decimal("60"))
        sold = Article.objects.create(number=10002, category=cat, description="Kleid blau", owner=anna,
                                      price=Decimal("40"))
        sale = sales.create_sale([{"kind": "artikel", "article_id": sold.pk, "description": "Kleid blau",
                                   "price": "40.00"}], buyer=berta)
        ov = persons.overview(anna)
        self.assertEqual((len(ov["in_stock"]), ov["in_stock_total"]), (1, Decimal("60")))
        self.assertEqual((len(ov["sold_open"]), ov["sold_open_total"], ov["sold_open_share"]),
                         (1, Decimal("40.00"), Decimal("26.00")))
        self.assertEqual(ov["sold_paid"], [])
        ov_b = persons.overview(berta)
        self.assertEqual((len(ov_b["bought"]), ov_b["bought_total"]), (1, Decimal("40.00")))

        page = self.client.get(reverse("person_detail", args=[anna.pk]))
        self.assertContains(page, "Eingebrachte Artikel – an Lager (1) · CHF 60.00")
        self.assertContains(page, "Verkaufte Artikel – offen (1)")
        self.assertContains(self.client.get(reverse("person_detail", args=[berta.pk])), "Gekaufte Artikel (1) · CHF 40.00")
        self.assertEqual(sale.total, Decimal("40.00"))
