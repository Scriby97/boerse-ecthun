import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from inventar import sales


class DesktopDeliveryTests(TestCase):
    """In der Desktop-App speichert die App Dateien selbst, statt das Fenster herunterladen zu lassen."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp()) / "Börse EC Thun"
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.sale = sales.create_sale([{"kind": "eigen", "description": "Leggins", "size": "S", "price": "12.00"}])

    def test_browser_bekommt_download(self):
        response = self.client.get(reverse("sale_receipt", args=[self.sale.pk]))
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_desktop_speichert_und_oeffnet(self):
        with override_settings(DESKTOP=True, EXPORT_DIR=self.folder), mock.patch("inventar.delivery.open_file") as opened:
            response = self.client.get(reverse("sale_receipt", args=[self.sale.pk]),
                                       HTTP_REFERER="http://testserver/verkauf/%d/" % self.sale.pk)
            self.assertRedirects(response, reverse("sale_detail", args=[self.sale.pk]), fetch_redirect_response=False)
            saved = self.folder / f"Quittung-{self.sale.number}.pdf"
            self.assertTrue(saved.read_bytes().startswith(b"%PDF"))
            opened.assert_called_once_with(saved)
            page = self.client.get(response.url)
            self.assertContains(page, "gespeichert in «Dokumente › Börse EC Thun» und geöffnet")

    def test_desktop_excel_und_fremder_referer(self):
        with override_settings(DESKTOP=True, EXPORT_DIR=self.folder), mock.patch("inventar.delivery.open_file"):
            response = self.client.get(reverse("export_xlsx"), HTTP_REFERER="https://boese.example/")
            self.assertRedirects(response, "/", fetch_redirect_response=False)
            self.assertEqual(len(list(self.folder.glob("*.xlsx"))), 1)
        self.assertEqual(Decimal("12.00"), self.sale.total)
