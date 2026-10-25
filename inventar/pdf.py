"""PDF-Dokumente: Kaufquittung, Clubabrechnung, Abrechnung für Besitzerinnen, Etiketten."""

from decimal import Decimal
from pathlib import Path

from fpdf import FPDF

from .models import AppSettings, Article, ClubStatement, Payout, Sale

LOGO = Path(__file__).resolve().parent / "assets" / "logo-ec-thun.png"
INK = (30, 41, 59)
MUTED = (100, 116, 139)
NAVY = (12, 35, 92)

# Die eingebauten PDF-Schriften kennen nur Latin-1 (ä, ö, ü, é gehen; Gedankenstrich & Co. nicht)
_REPLACE = str.maketrans({"–": "-", "—": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "„": '"', "…": "...",
                          "×": "x", "€": "EUR"})


def latin1(value) -> str:
    return str(value or "").translate(_REPLACE).encode("latin-1", "replace").decode("latin-1")


def chf(amount: Decimal) -> str:
    return f"{amount:,.2f}".replace(",", "'")


def receipt_pdf(sale: Sale, settings: AppSettings | None = None) -> bytes:
    """Kaufquittung (A5): Logo, «Börse EC Thun», Posten ohne Artikelnummer, Total, Dankestext, Name, Datum."""
    settings = settings or AppSettings.load()
    pdf = FPDF(format=(148, 210))  # A5 hoch
    pdf.set_title(latin1(f"Quittung {sale.date:%d.%m.%Y} - Börse EC Thun"))
    pdf.set_author(latin1(settings.owner_name))
    pdf.set_margins(14, 12, 14)
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    if LOGO.exists():
        pdf.image(str(LOGO), x=(pdf.w - 30) / 2, y=10, w=30)
    pdf.set_y(44)
    pdf.set_text_color(*NAVY)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, latin1("Börse EC Thun"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, "Quittung", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*MUTED)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, latin1(f"{sale.date:%d.%m.%Y}"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    pdf.set_text_color(*INK)
    pdf.set_font("Helvetica", "", 10)
    items = list(sale.items.all())
    with pdf.table(
        col_widths=(width * 0.62, width * 0.18, width * 0.20),
        text_align=("LEFT", "LEFT", "RIGHT"),
        borders_layout="HORIZONTAL_LINES",
        line_height=6.5,
        first_row_as_headings=True,
    ) as table:
        head = table.row()
        for title in ("Artikel", "Grösse", "CHF"):
            head.cell(latin1(title))
        for item in items:
            row = table.row()
            row.cell(latin1(item.description))
            row.cell(latin1(item.size))
            row.cell(chf(item.price))

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(width * 0.80, 7, "Total", new_x="RIGHT", new_y="TOP")
    pdf.cell(width * 0.20, 7, latin1(f"CHF {chf(sale.total)}"), align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 10)
    pdf.multi_cell(0, 5.5, latin1(settings.receipt_thanks), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, latin1(settings.owner_name), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, latin1(f"{settings.place}, {sale.date:%d.%m.%Y}"), align="C", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _date(value) -> str:
    """21.10.2026 → «21.10.2026» ohne führende Nullen beim Tag, wie in Stephanies Quittung."""
    return f"{value.day}.{value.month}.{value.year}"


def club_statement_pdf(statement: ClubStatement, settings: AppSettings | None = None) -> bytes:
    """Beglichene Clubquittung."""
    items = statement.items.select_related("sale", "sale__buyer").order_by("sale__date", "pk")
    return club_receipt_pdf(list(items), statement.end_date, statement.total, settings, settled=True)


def club_receipt_pdf(items, date, total, settings: AppSettings | None = None, settled: bool = False) -> bytes:
    """Clubquittung (A4) im Aufbau der bisherigen Pages-Quittung – laufend oder beglichen."""
    settings = settings or AppSettings.load()
    pdf = FPDF(format="A4")
    pdf.set_title(latin1(f"Clubquittung {date:%d.%m.%Y}"))
    pdf.set_author(latin1(settings.owner_name))
    pdf.set_margins(20, 15, 20)
    pdf.set_auto_page_break(True, margin=20)
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    if LOGO.exists():
        pdf.image(str(LOGO), x=(pdf.w - 50) / 2, y=15, w=50)
    pdf.set_y(72)
    pdf.set_text_color(*NAVY)
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 12, "Quittung", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, latin1(f"Für EC Thun von {settings.owner_name} Börse EC Thun"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*NAVY)
    pdf.line(pdf.l_margin, pdf.get_y() + 1, pdf.l_margin + width, pdf.get_y() + 1)
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    status = f"Beglichen am {_date(date)}" if settled else f"Laufende Quittung, Stand {_date(date)}"
    pdf.cell(0, 5, latin1(status), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.set_text_color(*NAVY)
    pdf.set_font("Helvetica", "", 10)
    payee = [line.strip() for line in settings.club_payee.splitlines() if line.strip()]
    with pdf.table(
        col_widths=(width * 0.22, width * 0.58, width * 0.20),
        text_align=("CENTER", "LEFT", "RIGHT"),
        line_height=7,
        first_row_as_headings=True,
    ) as table:
        head = table.row()
        for title in ("Datum", "Was", "CHF"):
            head.cell(title)
        for item in items:
            what = f"{item.description} {item.size}".strip()
            if item.sale.buyer:
                what += f" ({item.sale.buyer.name})"
            row = table.row()
            row.cell(_date(item.sale.date))
            row.cell(latin1(what))
            row.cell(chf(item.club_amount))
        last = table.row()
        last.cell("")
        last.cell(latin1("\n".join(["Total Überweisung auf Konto", *payee])))
        last.cell(chf(total))

    pdf.ln(8)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, latin1(f"{settings.place}, {_date(date)}"), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def payout_pdf(payout: Payout, settings: AppSettings | None = None) -> bytes:
    """Abrechnung für eine Besitzerin: welche Artikel, wann verkauft, Preis, ihr Anteil."""
    settings = settings or AppSettings.load()
    pdf = FPDF(format=(148, 210))  # A5 hoch
    pdf.set_title(latin1(f"Abrechnung {payout.person.name}"))
    pdf.set_margins(12, 12, 12)
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_text_color(*NAVY)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, latin1("Börse EC Thun"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, latin1(f"Abrechnung für {payout.person.name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*MUTED)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, latin1(f"Ausbezahlt am {payout.date:%d.%m.%Y} per {payout.get_method_display()}"),
             new_x="LMARGIN", new_y="NEXT")
    if payout.note:
        pdf.cell(0, 5, latin1(payout.note), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    rows = []
    for item in payout.sale_items.select_related("sale", "article").order_by("sale__date", "pk"):
        rows.append((item.article.label if item.article else "", item.description, item.size, item.sale.date,
                     item.price, item.owner_amount))
    for article in payout.articles.filter(sale_items__isnull=True).order_by("sold_date", "number"):
        rows.append((article.label, article.description, article.size, article.sold_date,
                     article.sale_price or Decimal("0"), article.owner_amount or Decimal("0")))

    pdf.set_text_color(*INK)
    pdf.set_font("Helvetica", "", 8.5)
    with pdf.table(
        col_widths=(width * 0.12, width * 0.38, width * 0.12, width * 0.16, width * 0.11, width * 0.11),
        text_align=("LEFT", "LEFT", "LEFT", "LEFT", "RIGHT", "RIGHT"),
        borders_layout="HORIZONTAL_LINES",
        line_height=5.5,
        first_row_as_headings=True,
    ) as table:
        head = table.row()
        for title in ("Nr.", "Artikel", "Grösse", "verkauft", "Preis", "Anteil"):
            head.cell(latin1(title))
        for label, description, size, date, price, share in rows:
            row = table.row()
            row.cell(latin1(label))
            row.cell(latin1(description))
            row.cell(latin1(size))
            row.cell(f"{date:%d.%m.%Y}" if date else "")
            row.cell(chf(price))
            row.cell(chf(share))

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(width * 0.75, 7, "Total ausbezahlt", new_x="RIGHT", new_y="TOP")
    pdf.cell(width * 0.25, 7, latin1(f"CHF {chf(payout.amount)}"), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, latin1(settings.owner_name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, latin1(f"{settings.place}, {payout.date:%d.%m.%Y}"), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def price_text(article: Article) -> tuple[str, str]:
    """(Preis, Vermerk) für die Etikette. Den unteren Preis bei «verhandelbar bis …» sieht die Kundschaft nicht."""
    if article.price_note == "gratis":
        return "gratis", ""
    price = f"CHF {chf(article.price)}" if article.price is not None else ""
    note = "verhandelbar" if article.price_note.casefold().startswith("verhandelbar") else article.price_note
    return price, note


LABEL_W, LABEL_H, LABEL_MARGIN = 57, 32, 3


def labels_pdf(articles: list[Article]) -> bytes:
    """Etiketten 57 × 32 mm (DYMO S0722540 / 11354), eine pro Seite – direkt auf dem LabelWriter drucken."""
    pdf = FPDF(orientation="L", unit="mm", format=(LABEL_H, LABEL_W))
    pdf.set_margins(LABEL_MARGIN, 2.5, LABEL_MARGIN)
    pdf.set_auto_page_break(False)
    pdf.set_title(latin1("Etiketten Börse EC Thun"))
    width = LABEL_W - 2 * LABEL_MARGIN
    bottom = LABEL_H - 2.5
    for article in articles:
        pdf.add_page()
        pdf.set_xy(LABEL_MARGIN, 2.5)
        pdf.set_text_color(*MUTED)
        pdf.set_font("Helvetica", "", 6)
        pdf.cell(width, 2.6, latin1("Börse EC Thun"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(width, 7, latin1(article.label), new_x="LMARGIN", new_y="NEXT")
        # Bezeichnung: höchstens drei Zeilen
        pdf.set_font("Helvetica", "", 7)
        lines = pdf.multi_cell(width, 3, latin1(article.description), dry_run=True, output="LINES")
        if len(lines) > 3:
            lines = lines[:3]
            lines[-1] = lines[-1][:-3].rstrip() + "..."
        pdf.multi_cell(width, 3, "\n".join(lines), new_x="LMARGIN", new_y="NEXT")
        price, note = price_text(article)
        if note:
            pdf.set_xy(LABEL_MARGIN, bottom - 7.4)
            pdf.set_font("Helvetica", "", 5.5)
            pdf.cell(width, 2.4, latin1(note), align="R")
        pdf.set_xy(LABEL_MARGIN, bottom - 5)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(width * 0.45, 5, latin1(f"Gr. {article.size}" if article.size else ""), new_x="RIGHT", new_y="TOP")
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(width * 0.55, 5, latin1(price), align="R")
    return bytes(pdf.output())
