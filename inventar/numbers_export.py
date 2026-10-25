"""Export als Numbers-Datei im Aufbau von Stephanies ursprünglicher Inventarliste.

Blätter: «Komplette Liste» (wie früher), «Ohne Nummer» (Kassenposten ohne Artikelnummer), «Clubbestand» und
«Clubverkäufe». Die Datei lässt sich mit dem Import der App wieder einlesen – eine Rückfallebene aufs alte System.
"""

import datetime as dt
import tempfile
from pathlib import Path

from numbers_parser import Document

from .models import Article, ClubItem, Person, SaleItem

HEADER = [None, "Datum", "Kleidungsstück", "Grösse", "Besitzer", "Kontakt", "Verkaufspreis ", "Code",
          "Inventar-Nr", "verkauft", "Nettoerlös Börsenbesitzerin", "Nettoerlös Besitzer", "Käufer", "Status", None]


def _num(value):
    """Beträge als Zahl; ganze Zahlen als int (Numbers speichert Kommazahlen sonst minimal ungenau)."""
    if value is None:
        return None
    number = float(value)
    return int(number) if number.is_integer() else round(number, 2)


def _datetime(value: dt.date | None):
    return dt.datetime(value.year, value.month, value.day) if value else None


def contact_text(person: Person) -> str:
    parts = [person.phone, person.email, "hat Twint" if person.twint else "", " ".join(person.address.split())]
    return ", ".join(p for p in parts if p)


def price_cell(article: Article):
    """Preis wie in der alten Liste: «gratis» oder eine Spanne «40-50» statt Zahl mit Vermerk."""
    if article.price_note == "gratis":
        return "gratis"
    if article.price_note.startswith("verhandelbar bis ") and article.price is not None:
        low = article.price_note.removeprefix("verhandelbar bis ")
        return f"{_num(low)}-{_num(article.price)}"
    return _num(article.price)


def _write(table, rows):
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            if value is not None and value != "":
                table.write(r, c, value)


def inventory_rows() -> list[list]:
    articles = list(Article.objects.select_related("category", "owner", "buyer").order_by("number", "number_suffix"))
    rows = [[None] * 15, [None] * 15, [None] * 15, HEADER]
    rows[1][6] = _num(sum((a.price or 0) for a in articles))
    rows[1][10] = _num(sum((a.shop_amount or 0) for a in articles))
    rows[1][11] = _num(sum((a.owner_amount or 0) for a in articles))
    for a in articles:
        description = a.description + (f" ({a.extra_info})" if a.extra_info else "")
        sold = a.status in (Article.Status.SOLD, Article.Status.PAID)
        status = {"lager": "offen", "zurueck": "zurückgegeben"}.get(a.status, "zur Abrechung")
        rows.append([
            None, _datetime(a.intake_date), description, a.size, a.owner.name, contact_text(a.owner),
            price_cell(a), a.category.code,
            # doppelte Nummern ohne «+»: der Import vergibt es wieder in dieser Reihenfolge
            a.number, _datetime(a.sold_date) if sold else None,
            _num(a.shop_amount) if sold else None, _num(a.owner_amount) if sold else None,
            a.buyer.name if a.buyer else None, status, "Abgerechnet" if a.status == Article.Status.PAID else None,
        ])
    return rows


def other_rows() -> list[list]:
    rows = [["Datum", "Bezeichnung", "Grösse", "Gehört", "Preis", "Anteil Besitzerin", "Anteil Börse", "ausbezahlt"]]
    items = (SaleItem.objects.filter(kind__in=[SaleItem.Kind.OTHER, SaleItem.Kind.OWN], sale__cancelled_at__isnull=True)
             .select_related("sale", "owner").order_by("sale__date", "pk"))
    for i in items:
        rows.append([_datetime(i.sale.date), i.description, i.size, i.owner.name if i.owner else "eigener Artikel",
                     _num(i.price), _num(i.owner_amount), _num(i.shop_amount), "ja" if i.payout_id else "nein"])
    return rows


def club_stock_rows() -> list[list]:
    rows = [["Artikel", "Grösse", "Preis Kunde", "an Club", "Bestand"]]
    for c in ClubItem.objects.all():
        rows.append([c.name, c.size, _num(c.customer_price), _num(c.club_price), c.stock])
    return rows


def club_sales_rows() -> list[list]:
    rows = [["Datum", "Artikel", "Grösse", "Käuferin", "Preis", "an Club", "abgerechnet"]]
    items = (SaleItem.objects.filter(kind=SaleItem.Kind.CLUB, sale__cancelled_at__isnull=True)
             .select_related("sale", "sale__buyer").order_by("sale__date", "pk"))
    for i in items:
        rows.append([_datetime(i.sale.date), i.description, i.size, i.sale.buyer.name if i.sale.buyer else "",
                     _num(i.price), _num(i.club_amount), "ja" if i.club_statement_id else "nein"])
    return rows


def build() -> bytes:
    doc = Document()
    first = doc.sheets[0]
    first.name = "Komplette Liste"
    first.tables[0].name = "Tabelle 1"
    _write(first.tables[0], inventory_rows())
    for name, rows in [("Ohne Nummer", other_rows()), ("Clubbestand", club_stock_rows()),
                       ("Clubverkäufe", club_sales_rows())]:
        doc.add_sheet(name, "Tabelle 1")
        _write(doc.sheets[name].tables[0], rows)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "export.numbers"
        doc.save(str(path))
        return path.read_bytes()
