"""PDF-Dokumente: Kaufquittung (später auch Abrechnungen)."""

from decimal import Decimal
from pathlib import Path

from fpdf import FPDF

from .models import AppSettings, Sale

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
    pdf.set_title(latin1(f"Quittung {sale.number} - Börse EC Thun"))
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
    pdf.cell(0, 5, latin1(f"Nr. {sale.number} · {sale.date:%d.%m.%Y}"), align="C", new_x="LMARGIN", new_y="NEXT")
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
