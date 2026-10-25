"""Kundendatei: Sortierung und Übersicht pro Person."""

import unicodedata
from collections import defaultdict
from dataclasses import dataclass
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


@dataclass
class Row:
    """Eine Zeile in der Übersicht der Person (Artikel mit Nummer oder Posten ohne Nummer)."""

    label: str
    description: str
    size: str
    date: object
    price: Decimal
    share: Decimal | None = None
    status: str = ""
    article_pk: int | None = None
    sale_pk: int | None = None


def overview(person: Person) -> dict:
    """Eingebracht (an Lager), verkauft (offen / ausbezahlt) und gekauft – je mit Totalen."""
    articles = list(person.articles.select_related("category"))
    in_stock = [Row(a.label, a.description, a.size, a.intake_date, a.price or ZERO, article_pk=a.pk)
                for a in articles if a.status == Article.Status.STOCK]
    sold_open, sold_paid = [], []
    for a in articles:
        if a.status in (Article.Status.SOLD, Article.Status.PAID):
            row = Row(a.label, a.description, a.size, a.sold_date, a.sale_price or a.price or ZERO,
                      a.owner_amount or ZERO, a.get_status_display(), article_pk=a.pk)
            (sold_paid if a.status == Article.Status.PAID else sold_open).append(row)
    # Posten ohne Nummer, die ihr gehören (z. B. Evas Artikel)
    for item in (person.sale_items.filter(kind=SaleItem.Kind.OTHER, sale__cancelled_at__isnull=True)
                 .select_related("sale")):
        row = Row("–", item.description, item.size, item.sale.date, item.price, item.owner_amount,
                  "ausbezahlt" if item.payout_id else "verkauft", sale_pk=item.sale_id)
        (sold_paid if item.payout_id else sold_open).append(row)
    bought = [Row(i.article.label if i.article else "–", i.description, i.size, i.sale.date, i.price,
                  sale_pk=i.sale_id)
              for i in SaleItem.objects.filter(sale__buyer=person, sale__cancelled_at__isnull=True)
              .select_related("sale", "article")]
    bought += [Row(a.label, a.description, a.size, a.sold_date, a.sale_price or ZERO, article_pk=a.pk)
               for a in person.purchases.filter(sale_items__isnull=True)]
    for rows in (sold_open, sold_paid, bought):
        rows.sort(key=lambda r: (r.date is None, r.date), reverse=True)
    total = lambda rows, attr="price": sum((getattr(r, attr) or ZERO for r in rows), ZERO)  # noqa: E731
    return {
        "in_stock": in_stock, "in_stock_total": total(in_stock),
        "sold_open": sold_open, "sold_open_total": total(sold_open), "sold_open_share": total(sold_open, "share"),
        "sold_paid": sold_paid, "sold_paid_total": total(sold_paid), "sold_paid_share": total(sold_paid, "share"),
        "bought": bought, "bought_total": total(bought),
    }
