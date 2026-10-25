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
