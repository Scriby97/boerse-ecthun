from decimal import Decimal

from django.db import models
from django.db.models import Max
from django.utils import timezone

from .money import split


class AppSettings(models.Model):
    """Einstellungen, die Stephanie selbst ändern kann (es gibt genau einen Datensatz)."""

    owner_share_default = models.DecimalField(
        "Anteil Besitzerin (%)", max_digits=5, decimal_places=2, default=Decimal("65")
    )
    receipt_thanks = models.TextField("Dankestext auf der Quittung", default="Herzlichen Dank für deinen Einkauf!")

    class Meta:
        verbose_name = "Einstellungen"

    @classmethod
    def load(cls) -> "AppSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Category(models.Model):
    """Kategorie mit eigenem Nummernkreis, z. B. 10 Kürkleider ab 10000."""

    code = models.PositiveIntegerField("Code", unique=True)
    name = models.CharField("Bezeichnung", max_length=120)
    start_number = models.PositiveIntegerField("Nummern ab")
    color = models.CharField("Farbe", max_length=7, default="#64748b")

    class Meta:
        ordering = ["code"]
        verbose_name = "Kategorie"
        verbose_name_plural = "Kategorien"

    def __str__(self):
        return f"{self.code} {self.name}"

    def next_number(self) -> int:
        """Nächste freie Nummer: nach der höchsten vergebenen, frühestens ab dem Startwert."""
        last = self.articles.aggregate(m=Max("number"))["m"]
        number = max(last or 0, self.start_number - 1) + 1
        while Article.objects.filter(number=number).exists():
            number += 1
        return number


class Person(models.Model):
    """Besitzerin, Käuferin oder beides."""

    name = models.CharField("Name", max_length=200)
    phone = models.CharField("Telefon", max_length=50, blank=True)
    email = models.CharField("E-Mail", max_length=200, blank=True)
    twint = models.BooleanField("hat TWINT", default=False)
    address = models.TextField("Adresse", blank=True)
    iban = models.CharField("IBAN", max_length=40, blank=True)
    owner_share = models.DecimalField(
        "Anteil Besitzerin (%)",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Leer lassen für den Standard (65 %).",
    )
    notes = models.TextField("Notizen", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Person"
        verbose_name_plural = "Personen"

    def __str__(self):
        return self.name


class Article(models.Model):
    class Status(models.TextChoices):
        STOCK = "lager", "an Lager"
        SOLD = "verkauft", "verkauft"
        PAID = "ausbezahlt", "ausbezahlt"
        RETURNED = "zurueck", "zurückgegeben"

    number = models.PositiveIntegerField("Nummer", unique=True)
    category = models.ForeignKey(Category, models.PROTECT, related_name="articles", verbose_name="Kategorie")
    description = models.CharField("Bezeichnung", max_length=300)
    size = models.CharField("Grösse", max_length=60, blank=True)
    owner = models.ForeignKey(Person, models.PROTECT, related_name="articles", verbose_name="Besitzerin")
    price = models.DecimalField("Preis (CHF)", max_digits=8, decimal_places=2, null=True, blank=True)
    price_note = models.CharField("Preisvermerk", max_length=100, blank=True, help_text="z. B. verhandelbar")
    owner_share = models.DecimalField(
        "Anteil Besitzerin (%)",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Nur bei Abweichung ausfüllen. 0 = gespendet.",
    )
    intake_date = models.DateField("Eingang", default=timezone.localdate)
    status = models.CharField("Status", max_length=12, choices=Status.choices, default=Status.STOCK)
    sold_date = models.DateField("Verkauft am", null=True, blank=True)
    sale_price = models.DecimalField("Verkaufspreis", max_digits=8, decimal_places=2, null=True, blank=True)
    owner_amount = models.DecimalField("Anteil Besitzerin", max_digits=8, decimal_places=2, null=True, blank=True)
    shop_amount = models.DecimalField("Anteil Börse", max_digits=8, decimal_places=2, null=True, blank=True)
    buyer = models.ForeignKey(
        Person, models.SET_NULL, null=True, blank=True, related_name="purchases", verbose_name="Käuferin"
    )
    notes = models.TextField("Notizen", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["number"]
        verbose_name = "Artikel"
        verbose_name_plural = "Artikel"

    def __str__(self):
        return f"{self.number} {self.description}"

    @property
    def is_donated(self) -> bool:
        return self.owner_share == 0

    def effective_owner_share(self, settings: AppSettings | None = None) -> Decimal:
        """Anteil der Besitzerin: Artikel, sonst Person, sonst Standard."""
        if self.owner_share is not None:
            return self.owner_share
        if self.owner.owner_share is not None:
            return self.owner.owner_share
        return (settings or AppSettings.load()).owner_share_default

    def split_for(self, price: Decimal, settings: AppSettings | None = None) -> tuple[Decimal, Decimal]:
        return split(price, self.effective_owner_share(settings))
