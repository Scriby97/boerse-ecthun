"""Frühere Clubverkäufe aus einer CSV-Datei übernehmen (z. B. aus den Inventurlisten und der Pages-Quittung).

Spalten: Datum; Artikel; Grösse; Käuferin; Preis; an Club; abgerechnet
- Datum: 21.12.2025
- abgerechnet: «ja», wenn der Verkauf schon mit dem Club abgerechnet ist (vor der App)
Der Bestand ändert sich nicht; schon übernommene Verkäufe werden übersprungen.
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


class ClubImportFehler(Exception):
    pass


def parse(content: str) -> list[dict]:
    try:
        dialect = csv.Sniffer().sniff(content[:2048], delimiters=";,\t")
    except csv.Error as error:
        raise ClubImportFehler("Die Datei ist keine CSV-Tabelle.") from error
    rows = list(csv.reader(content.splitlines(), dialect))
    if not rows:
        raise ClubImportFehler("Die Datei ist leer.")
    header = [COLUMNS.get(header_key(c)) for c in rows[0]]
    missing = {"date", "name", "club_amount"} - set(header)
    if missing:
        raise ClubImportFehler("Es fehlen Spalten: Datum, Artikel und an Club sind nötig.")
    result = []
    for line, row in enumerate(rows[1:], start=2):
        values = {field: row[i] if i < len(row) else "" for i, field in enumerate(header) if field}
        if not any(text(v) for v in values.values()):
            continue
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
        }], buyer=buyer, date=row["date"], adjust_stock=False)
        created += 1
        if row["settled"]:
            settled_items.append(sale.items.get())
    if settled_items:
        # Schon vor der App mit dem Club abgerechnet: als frühere Abrechnung festhalten
        statement = ClubStatement.objects.create(
            end_date=max(i.sale.date for i in settled_items),
            total=sum((i.club_amount for i in settled_items), Decimal("0")),
        )
        SaleItem.objects.filter(pk__in=[i.pk for i in settled_items]).update(club_statement=statement)
    return {"created": created, "skipped": skipped, "settled": len(settled_items)}

