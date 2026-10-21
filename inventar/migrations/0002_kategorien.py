"""Stephanies Kategorien mit Nummernkreisen (Stand 21.10.2026)."""

from django.db import migrations

CATEGORIES = [
    (1, "Trainingshosen", 1000, "#2563eb"),
    (2, "Reissverschlusshosen", 2000, "#0891b2"),
    (3, "Diverse Eiskunstlaufartikel", 3000, "#65a30d"),
    (4, "Trainings-T-Shirts", 4000, "#ca8a04"),
    (5, "Trainingspullover", 5000, "#ea580c"),
    (6, "Strümpfe und hautfarbene Leggins", 6000, "#b45309"),
    (7, "Gilets", 7000, "#7c3aed"),
    (8, "Einteiler und Dress Knaben", 8000, "#0f766e"),
    (10, "Kürkleider, Eiskunstlaufröckli", 10000, "#db2777"),
    (11, "Pantys und Jüpli", 11000, "#c026d3"),
    (12, "Bodys", 12000, "#e11d48"),
    (13, "Trainingsjacken", 13000, "#4f46e5"),
    (14, "Schlittschuhe und Eisen", 14000, "#475569"),
]


def create(apps, schema_editor):
    Category = apps.get_model("inventar", "Category")
    for code, name, start, color in CATEGORIES:
        Category.objects.get_or_create(code=code, defaults={"name": name, "start_number": start, "color": color})


class Migration(migrations.Migration):
    dependencies = [("inventar", "0001_initial")]

    operations = [migrations.RunPython(create, migrations.RunPython.noop)]
