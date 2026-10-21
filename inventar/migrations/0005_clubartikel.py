"""Clubartikel mit Stephanies Preisen (21.10.2026). Den Bestand erfasst Stephanie selbst."""

from decimal import Decimal

from django.db import migrations

ITEMS = [
    ("Clubjacke neu", Decimal("95.00"), Decimal("92.70")),
    ("Hose EC Thun", Decimal("79.00"), Decimal("79.00")),
]


def create(apps, schema_editor):
    ClubItem = apps.get_model("inventar", "ClubItem")
    for name, customer, club in ITEMS:
        ClubItem.objects.get_or_create(name=name, size="", defaults={"customer_price": customer, "club_price": club})


class Migration(migrations.Migration):
    dependencies = [("inventar", "0004_kasse")]

    operations = [migrations.RunPython(create, migrations.RunPython.noop)]
