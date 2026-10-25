"""Hinweis auf neue Versionen und Aktualisieren per Knopf."""

import io
import json
import sys
from pathlib import Path
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from inventar import updates

RELEASE = {
    "tag_name": "v9.0.0",
    "html_url": "https://github.com/Scriby97/boerse-ecthun/releases/tag/v9.0.0",
    "assets": [
        {"name": "Boerse-EC-Thun-apple-chip.zip", "browser_download_url": "https://example.org/apple.zip"},
        {"name": "Boerse-EC-Thun-intel.zip", "browser_download_url": "https://example.org/intel.zip"},
        {"name": "Boerse-EC-Thun-apple-chip.dmg", "browser_download_url": "https://example.org/apple.dmg"},
    ],
}


class UpdateTests(TestCase):
    def setUp(self):
        updates._available = None
        updates.state.update(status="bereit", message="", percent=0)
        self.addCleanup(setattr, updates, "_available", None)

    def check(self, machine="arm64", release=RELEASE):
        response = io.BytesIO(json.dumps(release).encode())
        with mock.patch.object(updates, "_open", return_value=response), \
                mock.patch("platform.machine", return_value=machine):
            updates.check()

    def test_passende_datei_je_chip(self):
        self.check("arm64")
        self.assertEqual(updates.available()["download"], "https://example.org/apple.zip")
        self.check("x86_64")
        self.assertEqual(updates.available()["download"], "https://example.org/intel.zip")

    def test_keine_meldung_ohne_neuere_version(self):
        self.check(release=dict(RELEASE, tag_name="v0.9.0"))
        self.assertIsNone(updates.available())

    def test_ohne_mac_app_nur_link(self):
        self.check()
        self.assertFalse(updates.can_install())
        response = self.client.get(reverse("start"))
        self.assertContains(response, "Herunterladen")
        self.assertNotContains(response, "Jetzt aktualisieren")
        response = self.client.post(reverse("update"))
        self.assertRedirects(response, reverse("start"))

    def test_knopf_in_der_mac_app(self):
        self.check()
        bundle = Path("/Applications/Börse EC Thun.app")
        with mock.patch.object(updates, "app_bundle", return_value=bundle), mock.patch("os.access", return_value=True):
            self.assertContains(self.client.get(reverse("start")), "Jetzt aktualisieren")
            with mock.patch.object(updates, "_install") as install, \
                    mock.patch("threading.Thread.start", lambda thread: thread._target()):
                response = self.client.post(reverse("update"))
            self.assertRedirects(response, reverse("update"))
            install.assert_called_once()
        self.assertContains(self.client.get(reverse("update")), "wird geladen")

    def test_app_paket_nur_in_der_verpackten_mac_app(self):
        self.assertIsNone(updates.app_bundle())
        exe = "/Applications/Börse EC Thun.app/Contents/MacOS/Börse EC Thun"
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "platform", "darwin"), \
                mock.patch.object(sys, "executable", exe), mock.patch.object(Path, "resolve", lambda p: p):
            self.assertEqual(updates.app_bundle(), Path("/Applications/Börse EC Thun.app"))

    def test_fehler_wird_angezeigt(self):
        self.check()
        with mock.patch.object(updates, "_download", side_effect=OSError("kein Internet")):
            updates._install()
        self.assertEqual(updates.state["status"], "fehler")
        self.assertContains(self.client.get(reverse("update")), "kein Internet")
