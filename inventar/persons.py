"""Kundendatei: Sortierung und Übersicht pro Person."""

import unicodedata
from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Q

from .models import Article, Person, SaleItem

ZERO = Decimal("0")
SORTS = {
    "name": "Name A–Z",
    "-name": "Name Z–A",
    "bestand": "Meiste Artikel in der Börse",
    "gekauft": "Meiste gekaufte Artikel",
}


def sort_key(name: str) -> str:
    """Alphabetisch wie im Telefonbuch: ohne Unterschied Gross/Klein, Ä wie A."""
    plain = unicodedata.normalize("NFKD", name)
    return "".join(c for c in plain if not unicodedata.combining(c)).casefold().strip()


def purchase_counts() -> dict[int, int]:
    """Anzahl gekaufter Artikel pro Person (Kasse und alte Liste)."""
    counts: dict[int, int] = defaultdict(int)
    rows = (SaleItem.objects.filter(sale__cancelled_at__isnull=True, sale__buyer__isnull=False)
            .values("sale__buyer").annotate(n=Count("pk")))
    for row in rows:
        counts[row["sale__buyer"]] += row["n"]
    for row in (Article.objects.filter(buyer__isnull=False, sale_items__isnull=True)
                .values("buyer").annotate(n=Count("pk"))):
        counts[row["buyer"]] += row["n"]
    return dict(counts)


def listing(q: str = "", sort: str = "name") -> list[Person]:
    persons = Person.objects.annotate(
        in_stock=Count("articles", filter=Q(articles__status=Article.Status.STOCK), distinct=True),
        sold=Count("articles", filter=Q(articles__status__in=[Article.Status.SOLD, Article.Status.PAID]),
                   distinct=True),
    )
    if q:
        persons = persons.filter(
            Q(name__icontains=q) | Q(phone__icontains=q) | Q(email__icontains=q) | Q(notes__icontains=q)
        )
    bought = purchase_counts()
    result = list(persons)
    for p in result:
        p.bought = bought.get(p.pk, 0)
    by_name = lambda p: sort_key(p.name)  # noqa: E731
    if sort == "-name":
        result.sort(key=by_name, reverse=True)
    elif sort == "bestand":
        result.sort(key=lambda p: (-p.in_stock, by_name(p)))
    elif sort == "gekauft":
        result.sort(key=lambda p: (-p.bought, by_name(p)))
    else:
        result.sort(key=by_name)
    return result
