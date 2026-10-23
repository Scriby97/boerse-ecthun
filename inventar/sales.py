"""Kasse und Auszahlungen: Verkauf anlegen, stornieren, offene Beträge, auszahlen.

Offen auszuzahlen sind Posten aus der Kasse (mit Besitzerin, noch ohne Auszahlung) und importierte Artikel,
die in der alten Liste verkauft, aber noch nicht abgerechnet waren.
"""

import datetime as dt
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import AppSettings, Article, ClubItem, ClubStatement, Payout, Person, Sale, SaleItem
from .money import split

ZERO = Decimal("0")


class SaleError(Exception):
    """Verständliche Meldung für Stephanie, nichts wurde gespeichert."""


# --- Verkauf ----------------------------------------------------------------------------------


@transaction.atomic
def create_sale(entries: list[dict], buyer: Person | None = None, payment: str = Sale.Payment.CASH,
                date: dt.date | None = None, adjust_stock: bool = True, source: str = "kasse") -> Sale:
    """Legt den Verkauf mit allen Posten an. entries = Warenkorb der Kasse (siehe views_kasse).

    adjust_stock=False: Clubverkauf nachtragen, der schon vor dem Zählen des Bestands war.
    """
    if not entries:
        raise SaleError("Der Warenkorb ist leer.")
    settings = AppSettings.load()
    sale = Sale.objects.create(number=Sale.next_number(), date=date or timezone.localdate(), buyer=buyer,
                               payment=payment, source=source)
    for entry in entries:
        price = Decimal(entry["price"])
        kind = entry["kind"]
        item = SaleItem(sale=sale, kind=kind, description=entry["description"], size=entry.get("size", ""),
                        price=price)
        if kind == SaleItem.Kind.ARTICLE:
            article = Article.objects.select_related("owner").get(pk=entry["article_id"])
            if article.status != Article.Status.STOCK:
                raise SaleError(f"Artikel {article.label} ist nicht mehr an Lager.")
            item.owner_amount, item.shop_amount = article.split_for(price, settings)
            article.status = Article.Status.SOLD
            article.sold_date = sale.date
            article.sale_price = price
            article.owner_amount, article.shop_amount = item.owner_amount, item.shop_amount
            article.buyer = buyer
            article.save()
            item.article, item.owner = article, article.owner
        elif kind == SaleItem.Kind.OTHER:
            owner = Person.objects.get(pk=entry["owner_id"])
            share = owner.owner_share if owner.owner_share is not None else settings.owner_share_default
            item.owner = owner
            item.owner_amount, item.shop_amount = split(price, share)
        elif kind == SaleItem.Kind.OWN:
            item.shop_amount = price
        elif kind == SaleItem.Kind.CLUB:
            club_item = ClubItem.objects.get(pk=entry["club_item_id"])
            # Der Club erhält immer seinen Preis; die Differenz gehört der Börse
            item.club_item = club_item
            item.club_amount = Decimal(entry["club_amount"]) if entry.get("club_amount") else club_item.club_price
            item.shop_amount = price - item.club_amount
            if adjust_stock:
                club_item.stock -= 1
                club_item.save(update_fields=["stock"])
        else:
            raise SaleError(f"Unbekannte Postenart: {kind}")
        item.save()
    return sale


@transaction.atomic
def cancel_sale(sale: Sale) -> None:
    """Storniert einen Verkauf: Artikel zurück an Lager, Clubbestand zurück. Nicht mehr nach einer Auszahlung."""
    if sale.cancelled_at:
        raise SaleError("Dieser Verkauf ist schon storniert.")
    if sale.items.filter(payout__isnull=False).exists():
        raise SaleError("Für diesen Verkauf wurde schon ausbezahlt. Bitte zuerst die Auszahlung klären.")
    if sale.items.filter(club_statement__isnull=False).exists():
        raise SaleError("Dieser Clubverkauf ist schon mit dem Club abgerechnet.")
    for item in sale.items.select_related("article", "club_item"):
        if item.article:
            article = item.article
            article.status = Article.Status.STOCK
            article.sold_date = article.sale_price = article.owner_amount = article.shop_amount = None
            article.buyer = None
            article.save()
        if item.club_item:
            item.club_item.stock += 1
            item.club_item.save(update_fields=["stock"])
    sale.cancelled_at = timezone.now()
    sale.save(update_fields=["cancelled_at"])


# --- Offene Beträge und Auszahlungen ------------------------------------------------------------


def open_sale_items():
    return SaleItem.objects.filter(
        sale__cancelled_at__isnull=True, payout__isnull=True, owner__isnull=False, owner_amount__gt=0
    )


def open_imported_articles():
    """Aus der alten Liste: verkauft, noch nicht abgerechnet (ohne Posten aus der Kasse)."""
    return Article.objects.filter(status=Article.Status.SOLD, sale_items__isnull=True, owner_amount__gt=0)


def open_amounts() -> dict[int, Decimal]:
    """Offener Betrag pro Person (nur Personen mit etwas Offenem)."""
    totals: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for row in open_sale_items().values("owner").annotate(s=Sum("owner_amount")):
        totals[row["owner"]] += row["s"]
    for row in open_imported_articles().values("owner").annotate(s=Sum("owner_amount")):
        totals[row["owner"]] += row["s"]
    return dict(totals)


@transaction.atomic
def record_payout(person: Person, method: str, date: dt.date | None = None, sale: Sale | None = None,
                  note: str = "") -> Payout:
    """Zahlt alles Offene einer Person aus – oder nur die Posten eines Verkaufs (direkt nach dem Verkauf)."""
    items = list(open_sale_items().filter(owner=person).select_related("article"))
    articles = list(open_imported_articles().filter(owner=person))
    if sale is not None:
        items = [i for i in items if i.sale_id == sale.pk]
        articles = []
    amount = sum((i.owner_amount for i in items), ZERO) + sum((a.owner_amount for a in articles), ZERO)
    if amount <= 0:
        raise SaleError(f"Für {person.name} ist nichts offen.")
    payout = Payout.objects.create(person=person, date=date or timezone.localdate(), amount=amount,
                                   method=method, note=note)
    for item in items:
        item.payout = payout
        item.save(update_fields=["payout"])
        if item.article:
            articles.append(item.article)
    for article in articles:
        article.status = Article.Status.PAID
        article.payout = payout
        article.save(update_fields=["status", "payout", "updated_at"])
    return payout


# --- Clubabrechnung -------------------------------------------------------------------------------


def open_club_items(until: dt.date | None = None):
    """Verkaufte Clubartikel, die noch nicht mit dem Club abgerechnet sind (optional bis zu einem Datum)."""
    items = SaleItem.objects.filter(
        kind=SaleItem.Kind.CLUB, sale__cancelled_at__isnull=True, club_statement__isnull=True
    ).select_related("sale", "sale__buyer").order_by("sale__date", "pk")
    return items.filter(sale__date__lte=until) if until else items


def default_statement_end(today: dt.date | None = None) -> dt.date:
    """Letzter Stichtag (30.6. oder 31.12.), der nicht in der Zukunft liegt."""
    today = today or timezone.localdate()
    candidates = [dt.date(today.year, 12, 31), dt.date(today.year, 6, 30), dt.date(today.year - 1, 12, 31)]
    return next(d for d in candidates if d <= today)


@transaction.atomic
def create_club_statement(end_date: dt.date) -> ClubStatement:
    items = list(open_club_items(end_date))
    if not items:
        raise SaleError(f"Bis {end_date:%d.%m.%Y} gibt es keine offenen Clubverkäufe.")
    statement = ClubStatement.objects.create(end_date=end_date, total=sum((i.club_amount for i in items), ZERO))
    SaleItem.objects.filter(pk__in=[i.pk for i in items]).update(club_statement=statement)
    return statement


@transaction.atomic
def delete_club_statement(statement: ClubStatement) -> None:
    """Abrechnung zurücknehmen (z. B. falsch erstellt): die Posten sind danach wieder offen."""
    statement.items.update(club_statement=None)
    statement.delete()
