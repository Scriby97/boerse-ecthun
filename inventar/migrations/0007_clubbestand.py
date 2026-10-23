"""Clubbekleidung EC Thun: Bestand laut Stephanies Inventurlisten (Stand 23.10.2026).

Ersetzt die zwei Platzhalter aus 0005 (ohne Grösse). Bestand = Übergabe 21.11.2025 minus die
eingetragenen Verkäufe. Mondor-Hosen fehlen bewusst: sie sind bei den Börsenartikeln eingeräumt.
Annahme (noch zu bestätigen): bei Jiv-alt und Mondor erhält der Club den ganzen Verkaufspreis.
"""

from decimal import Decimal

from django.db import migrations

D = Decimal
ITEMS = [
    # Bezeichnung, Grösse, Preis Kunde, an den Club, Bestand
    # Clubjacke 2026 mit Club-Logo (Jiv neu): Club erhält 92.70
    ("Clubjacke neu", "140", D("95"), D("92.70"), 5),
    ("Clubjacke neu", "150", D("95"), D("92.70"), 6),
    ("Clubjacke neu", "XS", D("95"), D("92.70"), 6),
    ("Clubjacke neu", "S", D("95"), D("92.70"), 7),
    ("Clubjacke neu", "M", D("95"), D("92.70"), 7),
    ("Clubjacke neu", "L", D("95"), D("92.70"), 2),
    # Jiv alt (ohne Logo)
    ("Jacke Frauen Jiv", "140", D("95"), D("95"), 5),
    ("Jacke Frauen Jiv", "M", D("95"), D("95"), 3),
    ("Jacke Männer Jiv", "140", D("95"), D("95"), 1),
    ("Jacke Männer Jiv", "150", D("95"), D("95"), 1),
    ("Jacke Männer Jiv", "XS", D("95"), D("95"), 1),
    ("Jacke Männer Jiv", "S", D("95"), D("95"), 2),
    ("Jacke Männer Jiv", "M", D("95"), D("95"), 1),
    ("Hose EC Thun", "140", D("79"), D("79"), 2),
    # Mondor (Ausverkaufspreise: Kinder 55, Erwachsene 65)
    ("Jacke Mondor", "L", D("65"), D("65"), 1),
    ("Jacke Mondor", "XL", D("65"), D("65"), 1),
    ("Jacke Mondor Herren", "10-12", D("55"), D("55"), 2),
    ("Jacke Mondor Herren", "12-14", D("55"), D("55"), 1),
    ("Jacke Mondor Herren", "S", D("65"), D("65"), 1),
]


def create(apps, schema_editor):
    ClubItem = apps.get_model("inventar", "ClubItem")
    # Platzhalter ohne Grösse entfernen, solange damit nichts verkauft wurde
    ClubItem.objects.filter(size="", sale_items__isnull=True).delete()
    for name, size, customer, club, stock in ITEMS:
        ClubItem.objects.update_or_create(
            name=name, size=size, defaults={"customer_price": customer, "club_price": club, "stock": stock}
        )


class Migration(migrations.Migration):
    dependencies = [("inventar", "0006_abrechnungen")]

    operations = [migrations.RunPython(create, migrations.RunPython.noop)]
