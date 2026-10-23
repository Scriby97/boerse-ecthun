"""Bereinigt Werte aus Stephanies Liste: Texte, Zahlen, Daten, Preise, Grössen und Kontakte."""

import datetime as dt
import re
import unicodedata
from decimal import Decimal


def text(value) -> str:
    """Zellwert als sauberer Text (140.0 → «140»; Umlaute vom Mac vereinheitlicht)."""
    if value is None:
        return ""
    if isinstance(value, float) and abs(value - round(value)) < 1e-6:
        value = int(round(value))
    return unicodedata.normalize("NFC", str(value)).strip()


def header_key(value) -> str:
    """Spaltentitel zum Vergleichen: klein, einfache Leerzeichen."""
    return " ".join(text(value).casefold().split())


def person_key(name: str) -> str:
    """Gleiche Person trotz Gross-/Kleinschreibung und doppelter Leerzeichen erkennen."""
    return " ".join(text(name).casefold().split())


def to_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        # Tabellen speichern ganze Zahlen manchmal minimal ungenau (12.000000000000002)
        nearest = round(value)
        return int(nearest) if abs(value - nearest) < 1e-6 else None
    t = text(value)
    return int(t) if t.isdigit() else None


def to_date(value) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})", text(value))
    if not m:
        return None
    day, month, year = map(int, m.groups())
    if year < 100:
        year += 2000
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


_MONEY = re.compile(r"(?:CHF|Fr\.?)?\s*(\d+(?:[.,]\d{1,2})?)\s*(?:CHF|Fr\.?|\.-|-)?", re.IGNORECASE)


def to_money(value) -> Decimal | None:
    """Zahl oder Text wie «12.50», «CHF 12», «12.-» als Betrag; sonst None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(round(value, 2))).quantize(Decimal("0.01"))
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    m = _MONEY.fullmatch(text(value))
    if not m:
        return None
    return Decimal(m.group(1).replace(",", ".")).quantize(Decimal("0.01"))


_PRICE_RANGE = re.compile(r"(?:verhandelbar\s*)?(\d+(?:[.,]\d{1,2})?)\s*(?:-|–|bis)\s*(\d+(?:[.,]\d{1,2})?)", re.IGNORECASE)


def parse_price(value) -> tuple[Decimal | None, str, bool]:
    """(Preis, Vermerk, eindeutig). Nicht eindeutige Preise soll Stephanie vor dem Import bestätigen.

    Stephanies Regeln (21.10.2026): «-» und «gratis» → 0.– mit Vermerk «gratis»;
    eine Spanne wie «40-50» → der höhere Preis mit Vermerk «verhandelbar bis 40.00».
    """
    money = to_money(value)
    if money is not None:
        return money, "", True
    raw = text(value)
    if not raw:
        return None, "", True
    if raw in {"-", "–", "—"} or raw.casefold() == "gratis":
        return Decimal("0.00"), "gratis", True
    m = _PRICE_RANGE.fullmatch(raw)
    if m:
        low, high = sorted(Decimal(g.replace(",", ".")).quantize(Decimal("0.01")) for g in m.groups())
        return high, f"verhandelbar bis {low}", True
    return None, raw, False


_RANGE = re.compile(r"(\d+)\s*(?:bis|-|–)\s*(\d+)", re.IGNORECASE)


def normalize_size(value) -> str:
    """Einheitliche Grössen: «8 bis 10», «8-10», «8bis 10» → «8–10»; «-» → leer."""
    t = text(value)
    if t in {"-", "–", "—"}:
        return ""
    m = _RANGE.fullmatch(t)
    if m:
        return f"{m.group(1)}–{m.group(2)}"
    return t


_PHONE = re.compile(r"(?:\+41|0041|0)\s?\d{2}(?:[\s/.-]?\d){7}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def format_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0041"):
        digits = "0" + digits[4:]
    elif digits.startswith("41") and len(digits) == 11:
        digits = "0" + digits[2:]
    if len(digits) == 10:
        return f"{digits[:3]} {digits[3:6]} {digits[6:8]} {digits[8:]}"
    return raw.strip()


def parse_contact(value) -> dict:
    """Telefon, Mail und TWINT aus dem freien Kontakttext herauslösen. Der ganze Text bleibt erhalten."""
    raw = text(value)
    phone = _PHONE.search(raw)
    email = _EMAIL.search(raw)
    return {
        "raw": raw,
        "phone": format_phone(phone.group(0)) if phone else "",
        "email": email.group(0) if email else "",
        "twint": "twint" in raw.casefold(),
    }
