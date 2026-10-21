"""Verkaufsübersicht nach Woche, Monat oder Jahr – aus Kassen-Posten und Verkäufen der alten Liste."""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from .models import Article, SaleItem

ZERO = Decimal("0")
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember"]
PERIODS = {"woche": "Woche", "monat": "Monat", "jahr": "Jahr"}


@dataclass
class Position:
    date: dt.date
    kind: str
    label: str
    description: str
    size: str
    owner: str
    price: Decimal
    owner_amount: Decimal
    shop_amount: Decimal
    club_amount: Decimal
    sale_id: int | None = None
    sale_number: int | None = None


@dataclass
class PeriodSummary:
    key: str
    title: str
    start: dt.date
    count: int = 0
    revenue: Decimal = ZERO
    owners: Decimal = ZERO
    shop: Decimal = ZERO
    own: Decimal = ZERO
    club: Decimal = ZERO
    positions: list = field(default_factory=list)

    def add(self, p: Position):
        self.count += 1
        self.revenue += p.price
        self.owners += p.owner_amount
        self.shop += p.shop_amount
        self.club += p.club_amount
        if p.kind == SaleItem.Kind.OWN:
            self.own += p.price
        self.positions.append(p)


def positions() -> list[Position]:
    """Alle verkauften Posten: Kasse (ohne stornierte) und alte Liste (verkauft ohne Kassen-Posten)."""
    result = []
    items = SaleItem.objects.filter(sale__cancelled_at__isnull=True).select_related("sale", "article", "owner")
    for i in items:
        result.append(Position(
            date=i.sale.date, kind=i.kind, label=i.article.label if i.article else "",
            description=i.description, size=i.size, owner=i.owner.name if i.owner else "",
            price=i.price, owner_amount=i.owner_amount, shop_amount=i.shop_amount, club_amount=i.club_amount,
            sale_id=i.sale_id, sale_number=i.sale.number,
        ))
    imported = Article.objects.filter(sold_date__isnull=False, sale_items__isnull=True).select_related("owner")
    for a in imported:
        result.append(Position(
            date=a.sold_date, kind=SaleItem.Kind.ARTICLE, label=a.label, description=a.description, size=a.size,
            owner=a.owner.name, price=a.sale_price or ZERO, owner_amount=a.owner_amount or ZERO,
            shop_amount=a.shop_amount or ZERO, club_amount=ZERO,
        ))
    return result


def period_of(date: dt.date, period: str) -> tuple[str, str, dt.date]:
    """(Schlüssel, Titel, erster Tag) der Woche, des Monats oder des Jahres."""
    if period == "woche":
        year, week, _ = date.isocalendar()
        start = date - dt.timedelta(days=date.weekday())
        end = start + dt.timedelta(days=6)
        return f"{year}-W{week:02d}", f"KW {week} · {start:%d.%m.} – {end:%d.%m.%Y}", start
    if period == "jahr":
        return str(date.year), str(date.year), dt.date(date.year, 1, 1)
    return f"{date:%Y-%m}", f"{MONTHS[date.month - 1]} {date.year}", date.replace(day=1)


def summarize(period: str) -> list[PeriodSummary]:
    """Summen pro Zeitraum, neuester zuerst."""
    groups: dict[str, PeriodSummary] = {}
    for p in positions():
        key, title, start = period_of(p.date, period)
        groups.setdefault(key, PeriodSummary(key=key, title=title, start=start)).add(p)
    for g in groups.values():
        g.positions.sort(key=lambda p: (p.date, p.sale_number or 0), reverse=True)
    return sorted(groups.values(), key=lambda g: g.start, reverse=True)


def totals(groups: list[PeriodSummary]) -> PeriodSummary:
    total = PeriodSummary(key="total", title="Total", start=dt.date.min)
    for g in groups:
        total.count += g.count
        total.revenue += g.revenue
        total.owners += g.owners
        total.shop += g.shop
        total.own += g.own
        total.club += g.club
    return total


def by_kind_owner(positions_list) -> dict[str, Decimal]:
    """Umsatz pro Besitzerin innerhalb eines Zeitraums (für die Detailansicht)."""
    sums: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for p in positions_list:
        sums[p.owner or "eigene / Club"] += p.price
    return dict(sorted(sums.items()))
