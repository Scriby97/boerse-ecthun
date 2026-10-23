"""Clubbestand und frühere Clubverkäufe übernehmen – aus CSV oder aus Blättern der Import-Datei (Numbers/Excel).

Clubverkäufe – Spalten: Datum; Artikel; Grösse; Käuferin; Preis; an Club; abgerechnet
- Datum: 21.12.2025
- abgerechnet: «ja», wenn der Verkauf schon mit dem Club beglichen ist (vor der App)
Der Bestand ändert sich dabei nicht; schon übernommene Verkäufe werden übersprungen.

Clubbestand – Spalten: Artikel; Grösse; Preis Kunde; an Club; Bestand
"""

import csv
from decimal import Decimal

from django.db import transaction

from . import sales
from .models import ClubItem, ClubStatement, Person, SaleItem
from .normalize import header_key, text, to_date, to_money

COLUMNS = {
    "datum": "date",
    "artikel": "name",
    "grösse": "size",
    "käuferin": "buyer",
    "preis": "price",
    "an club": "club_amount",
    "abgerechnet": "settled",
}
STOCK_COLUMNS = {
    "artikel": "name",
    "grösse": "size",
    "preis kunde": "customer_price",
    "an club": "club_price",
    "bestand": "stock",
}


class ClubImportFehler(Exception):
    pass


def _clean(rows) -> list[list]:
    return [list(r) for r in rows if any(text(c) for c in r)]


def is_sales_header(row) -> bool:
    return {"datum", "artikel", "an club"} <= {header_key(c) for c in row}


def is_stock_header(row) -> bool:
    keys = {header_key(c) for c in row}
    return {"artikel", "bestand"} <= keys and "datum" not in keys


def parse(content: str) -> list[dict]:
    """Clubverkäufe aus CSV-Text."""
    try:
        dialect = csv.Sniffer().sniff(content[:2048], delimiters=";,\t")
    except csv.Error as error:
        raise ClubImportFehler("Die Datei ist keine CSV-Tabelle.") from error
    return parse_rows(list(csv.reader(content.splitlines(), dialect)))


def parse_rows(rows) -> list[dict]:
    """Clubverkäufe aus Tabellenzeilen (erste Zeile = Spaltentitel)."""
    rows = _clean(rows)
    if not rows:
        raise ClubImportFehler("Die Datei ist leer.")
    header = [COLUMNS.get(header_key(c)) for c in rows[0]]
    if {"date", "name", "club_amount"} - set(header):
        raise ClubImportFehler("Es fehlen Spalten: Datum, Artikel und an Club sind nötig.")
    result = []
    for line, row in enumerate(rows[1:], start=2):
        values = {field: row[i] if i < len(row) else "" for i, field in enumerate(header) if field}
        date = to_date(values.get("date"))
        club_amount = to_money(values.get("club_amount"))
        if not date or club_amount is None or not text(values.get("name")):
            raise ClubImportFehler(f"Zeile {line}: Datum, Artikel oder Betrag an den Club fehlt.")
        price = to_money(values.get("price")) or club_amount
        result.append({
            "date": date,
            "name": text(values["name"]),
            "size": text(values.get("size")),
            "buyer": " ".join(text(values.get("buyer")).split()),
            "price": price,
            "club_amount": club_amount,
            "settled": text(values.get("settled")).casefold() in {"ja", "j", "x", "1", "yes"},
        })
    return result


def parse_stock_rows(rows) -> list[dict]:
    """Clubbestand aus Tabellenzeilen (erste Zeile = Spaltentitel)."""
    rows = _clean(rows)
    header = [STOCK_COLUMNS.get(header_key(c)) for c in rows[0]] if rows else []
    if {"name", "customer_price", "club_price", "stock"} - set(header):
        raise ClubImportFehler("Clubbestand: Es fehlen Spalten (Artikel, Preis Kunde, an Club, Bestand).")
    result = []
    for line, row in enumerate(rows[1:], start=2):
        values = {field: row[i] if i < len(row) else None for i, field in enumerate(header) if field}
        customer, club = to_money(values.get("customer_price")), to_money(values.get("club_price"))
        stock = to_money(values.get("stock"))
        if not text(values.get("name")) or customer is None or club is None or stock is None:
            raise ClubImportFehler(f"Clubbestand Zeile {line}: Artikel, Preise oder Bestand fehlt.")
        result.append({"name": text(values["name"]), "size": text(values.get("size")),
                       "customer_price": customer, "club_price": club, "stock": int(stock)})
    return result


@transaction.atomic
def replace_stock(rows: list[dict]) -> int:
    """Setzt den Clubbestand; Artikel ohne Verkäufe, die nicht mehr vorkommen, werden entfernt."""
    keep = set()
    for row in rows:
        item, _ = ClubItem.objects.update_or_create(
            name=row["name"], size=row["size"],
            defaults={"customer_price": row["customer_price"], "club_price": row["club_price"], "stock": row["stock"]},
        )
        keep.add(item.pk)
    ClubItem.objects.exclude(pk__in=keep).filter(sale_items__isnull=True).delete()
    ClubItem.objects.exclude(pk__in=keep).update(stock=0)
    return len(rows)


def _exists(row: dict) -> bool:
    items = SaleItem.objects.filter(
        kind=SaleItem.Kind.CLUB, sale__cancelled_at__isnull=True, sale__date=row["date"],
        description=row["name"], size=row["size"], club_amount=row["club_amount"],
    )
    if row["buyer"]:
        items = items.filter(sale__buyer__name__iexact=row["buyer"])
    return items.exists()


@transaction.atomic
def import_rows(rows: list[dict]) -> dict:
    created, skipped, settled_items = 0, 0, []
    for row in rows:
        if _exists(row):
            skipped += 1
            continue
        item = ClubItem.objects.filter(name=row["name"], size=row["size"]).first()
        if item is None:
            # Ausverkaufte Grösse: als Clubartikel ohne Bestand anlegen
            item = ClubItem.objects.create(name=row["name"], size=row["size"], customer_price=row["price"],
                                           club_price=row["club_amount"], stock=0)
        buyer = None
        if row["buyer"]:
            buyer = Person.objects.filter(name__iexact=row["buyer"]).first() or Person.objects.create(name=row["buyer"])
        sale = sales.create_sale([{
            "kind": SaleItem.Kind.CLUB, "club_item_id": item.pk, "description": row["name"], "size": row["size"],
            "price": str(row["price"]), "club_amount": str(row["club_amount"]),
        }], buyer=buyer, date=row["date"], adjust_stock=False, source="import")
        created += 1
        if row["settled"]:
            settled_items.append(sale.items.get())
    if settled_items:
        # Schon vor der App mit dem Club beglichen: als beglichene Clubquittung festhalten
        statement = ClubStatement.objects.create(
            end_date=max(i.sale.date for i in settled_items),
            total=sum((i.club_amount for i in settled_items), Decimal("0")),
        )
        SaleItem.objects.filter(pk__in=[i.pk for i in settled_items]).update(club_statement=statement)
    return {"created": created, "skipped": skipped, "settled": len(settled_items)}
