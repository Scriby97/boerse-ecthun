import shutil
import tempfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from inventar.models import Article, Category, Person

from .test_import import sample_rows, write_xlsx


class PageTests(TestCase):
    def setUp(self):
        self.anna = Person.objects.create(name="Muster Anna", phone="079 111 22 33")
        self.cat = Category.objects.get(code=10)
        Article.objects.create(number=10005, category=self.cat, description="Kürkleid rot", owner=self.anna, price=Decimal("60"))

    def test_seiten_laden(self):
        for url in [
            reverse("start"),
            reverse("article_list"),
            reverse("article_create"),
            reverse("article_create") + "?kategorie=10",
            reverse("article_edit", args=[10005]),
            reverse("person_list"),
            reverse("person_detail", args=[self.anna.pk]),
            reverse("person_create"),
            reverse("import_upload"),
        ]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_kategorien_mit_nummernkreis(self):
        self.assertEqual(Category.objects.count(), 13)
        self.assertEqual(self.cat.next_number(), 10006)
        self.assertEqual(Category.objects.get(code=1).next_number(), 1000)

    def test_erfassen_schlaegt_naechste_nummer_vor(self):
        response = self.client.get(reverse("article_create") + "?kategorie=10")
        self.assertContains(response, 'value="10006"')

    def test_serienerfassung_mit_neuer_besitzerin(self):
        response = self.client.post(
            reverse("article_create"),
            {"category": self.cat.pk, "number": 10006, "new_owner": "Neu Nina", "description": "Kleid grün",
             "size": "134", "price": "50", "intake_date": "2026-10-21"},
        )
        nina = Person.objects.get(name="Neu Nina")
        self.assertRedirects(response, reverse("article_create") + f"?kategorie=10&besitzerin={nina.pk}")
        self.assertEqual(Article.objects.get(number=10006).owner, nina)

    def test_erfassen_ohne_besitzerin_wird_abgelehnt(self):
        response = self.client.post(
            reverse("article_create"),
            {"category": self.cat.pk, "number": 10006, "description": "Kleid", "intake_date": "2026-10-21"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Article.objects.filter(number=10006).exists())

    def test_suche_im_inventar(self):
        response = self.client.get(reverse("article_list"), {"q": "rot"})
        self.assertContains(response, "Kürkleid rot")
        response = self.client.get(reverse("article_list"), {"q": "10005"})
        self.assertContains(response, "Kürkleid rot")


class ImportPageTests(TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.data_dir, ignore_errors=True)

    def test_hochladen_vorschau_und_import(self):
        from pathlib import Path

        with override_settings(DATA_DIR=Path(self.data_dir), BACKUP_DIR=Path(self.data_dir) / "Sicherungen"):
            content = write_xlsx(sample_rows()).read_bytes()
            response = self.client.post(
                reverse("import_upload"), {"file": SimpleUploadedFile("Inventarliste.xlsx", content)}
            )
            self.assertEqual(response.status_code, 302)
            preview = self.client.get(response.url)
            self.assertContains(preview, "Doppelte Nummer")
            self.assertContains(preview, "Preis ohne Zahl")
            self.assertEqual(Article.objects.count(), 0)

            done = self.client.post(response.url, {})
            self.assertRedirects(done, reverse("article_list"))
            self.assertEqual(Article.objects.count(), 6)
            self.assertTrue(any((Path(self.data_dir) / "Sicherungen").iterdir()), "Sicherung vor dem Import")

    def test_falscher_dateityp(self):
        response = self.client.post(reverse("import_upload"), {"file": SimpleUploadedFile("liste.pdf", b"x")})
        self.assertContains(response, "Numbers-, Excel- oder CSV-Datei")
