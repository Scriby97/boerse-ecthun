from decimal import Decimal

from django.db import models
from django.db.models import Max
from django.utils import timezone

from .money import split

# Stephanies Wortlaut (21.10.2026)
RECEIPT_THANKS = "Herzlichen Dank für den Einkauf und weiterhin viel Freude auf dem Eis"


class AppSettings(models.Model):
    """Einstellungen, die Stephanie selbst ändern kann (es gibt genau einen Datensatz)."""

    owner_share_default = models.DecimalField(
        "Anteil Besitzerin (%)", max_digits=5, decimal_places=2, default=Decimal("65")
    )
    receipt_thanks = models.TextField("Dankestext auf der Quittung", default=RECEIPT_THANKS)
    owner_name = models.CharField("Name auf Quittungen", max_length=120, default="Stephanie Luginbühl")
    place = models.CharField("Ort", max_length=80, default="Höfen")
    club_payee = models.TextField(
        "Überweisung an den Club",
        default="CH23 0079 0042 4054 2570 8\nEislauf-Club Thun, 3600 Thun",
        help_text="Steht unten auf der Clubabrechnung.",
    )

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

    number = models.PositiveIntegerField("Nummer")
    # Doppelt beschriftete Nummern aus der alten Liste: der zweite Artikel heisst 1096+
    number_suffix = models.CharField(
        "Zusatz", max_length=3, blank=True, help_text="z. B. + bei einer doppelt vergebenen Nummer"
    )
    category = models.ForeignKey(Category, models.PROTECT, related_name="articles", verbose_name="Kategorie")
    description = models.CharField("Bezeichnung", max_length=300)
    extra_info = models.TextField(
        "Zusatzinformation", blank=True, help_text="Z. B. Zustand, Marke, Hinweise. Erscheint nicht auf der Quittung."
    )
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
    payout = models.ForeignKey(
        "Payout", models.SET_NULL, null=True, blank=True, related_name="articles", verbose_name="Auszahlung"
    )
    notes = models.TextField("Notizen", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["number", "number_suffix"]
        verbose_name = "Artikel"
        verbose_name_plural = "Artikel"
        constraints = [
            models.UniqueConstraint(
                fields=["number", "number_suffix"],
                name="unique_article_label",
                violation_error_message="Diese Nummer ist schon vergeben.",
            )
        ]

    def __str__(self):
        return f"{self.label} {self.description}"

    @property
    def label(self) -> str:
        """Nummer wie auf der Etikette, z. B. 1096 oder 1096+"""
        return f"{self.number}{self.number_suffix}"

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


class ClubItem(models.Model):
    """Clubbekleidung EC Thun mit Bestand; der Club erhält pro Stück seinen Preis."""

    name = models.CharField("Bezeichnung", max_length=120)
    size = models.CharField("Grösse", max_length=30, blank=True)
    customer_price = models.DecimalField("Preis Kunde (CHF)", max_digits=8, decimal_places=2)
    club_price = models.DecimalField("an den Club (CHF)", max_digits=8, decimal_places=2)
    stock = models.IntegerField("Bestand", default=0)

    class Meta:
        ordering = ["name", "size"]
        verbose_name = "Clubartikel"
        verbose_name_plural = "Clubartikel"

    def __str__(self):
        return f"{self.name} {self.size}".strip()


class Payout(models.Model):
    """Auszahlung an eine Besitzerin für einen oder mehrere verkaufte Artikel."""

    class Method(models.TextChoices):
        TWINT = "twint", "TWINT"
        CASH = "bar", "bar"
        BANK = "bank", "Banküberweisung"

    person = models.ForeignKey(Person, models.PROTECT, related_name="payouts", verbose_name="Besitzerin")
    date = models.DateField("Datum", default=timezone.localdate)
    amount = models.DecimalField("Betrag (CHF)", max_digits=9, decimal_places=2)
    method = models.CharField("Art", max_length=10, choices=Method.choices)
    note = models.CharField("Notiz", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Auszahlung"
        verbose_name_plural = "Auszahlungen"

    def __str__(self):
        return f"{self.person} {self.amount} ({self.get_method_display()})"


class Sale(models.Model):
    """Ein Einkauf an der Kasse = eine Quittung."""

    class Payment(models.TextChoices):
        CASH = "bar", "bar"
        TWINT = "twint", "TWINT"

    number = models.PositiveIntegerField("Quittung Nr.", unique=True)
    date = models.DateField("Datum", default=timezone.localdate)
    buyer = models.ForeignKey(
        Person, models.SET_NULL, null=True, blank=True, related_name="sales", verbose_name="Käuferin"
    )
    payment = models.CharField("Bezahlt mit", max_length=10, choices=Payment.choices, default=Payment.CASH)
    # «import»: aus der Import-Datei übernommen (frühere Clubverkäufe); ein neuer Import ersetzt sie
    source = models.CharField("Herkunft", max_length=10, default="kasse",
                              choices=[("kasse", "Kasse"), ("import", "Import")])
    cancelled_at = models.DateTimeField("Storniert am", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-number"]
        verbose_name = "Verkauf"
        verbose_name_plural = "Verkäufe"

    def __str__(self):
        return f"Quittung {self.number}"

    @classmethod
    def next_number(cls) -> int:
        return (cls.objects.aggregate(m=Max("number"))["m"] or 0) + 1

    @property
    def total(self) -> Decimal:
        return sum((item.price for item in self.items.all()), Decimal("0"))


class SaleItem(models.Model):
    """Ein Posten auf der Quittung mit der Aufteilung des Betrags."""

    class Kind(models.TextChoices):
        ARTICLE = "artikel", "Kommission"
        OTHER = "ohne_nummer", "ohne Nummer"
        OWN = "eigen", "eigener Artikel"
        CLUB = "club", "Clubartikel"

    sale = models.ForeignKey(Sale, models.CASCADE, related_name="items")
    kind = models.CharField("Art", max_length=12, choices=Kind.choices)
    article = models.ForeignKey(Article, models.PROTECT, null=True, blank=True, related_name="sale_items")
    club_item = models.ForeignKey(ClubItem, models.PROTECT, null=True, blank=True, related_name="sale_items")
    owner = models.ForeignKey(Person, models.PROTECT, null=True, blank=True, related_name="sale_items")
    description = models.CharField("Bezeichnung", max_length=300)
    size = models.CharField("Grösse", max_length=60, blank=True)
    price = models.DecimalField("Preis", max_digits=8, decimal_places=2)
    owner_amount = models.DecimalField("Anteil Besitzerin", max_digits=8, decimal_places=2, default=Decimal("0"))
    shop_amount = models.DecimalField("Anteil Börse", max_digits=8, decimal_places=2, default=Decimal("0"))
    club_amount = models.DecimalField("an den Club", max_digits=8, decimal_places=2, default=Decimal("0"))
    payout = models.ForeignKey(Payout, models.SET_NULL, null=True, blank=True, related_name="sale_items")
    club_statement = models.ForeignKey(
        "ClubStatement", models.SET_NULL, null=True, blank=True, related_name="items"
    )

    class Meta:
        ordering = ["pk"]
        verbose_name = "Posten"
        verbose_name_plural = "Posten"

    def __str__(self):
        return f"{self.description} {self.price}"


class ClubStatement(models.Model):
    """Abrechnung der Clubbekleidung an den EC Thun (per 30.6. und 31.12.)."""

    end_date = models.DateField("Abrechnung per")
    total = models.DecimalField("Total an den Club", max_digits=9, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-end_date", "-created_at"]
        verbose_name = "Clubabrechnung"
        verbose_name_plural = "Clubabrechnungen"

    def __str__(self):
        return f"Clubabrechnung per {self.end_date:%d.%m.%Y}"
