from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def chf(value):
    """Betrag im Schweizer Format: 18582.5 → 18'582.50"""
    if value is None or value == "":
        return ""
    return f"{Decimal(value):,.2f}".replace(",", "'")


@register.filter
def iso_date(value):
    """2026-10-21 → 21.10.2026 (für Daten aus der Import-Vorschau)"""
    if not value:
        return ""
    year, month, day = str(value).split("-")
    return f"{int(day)}.{int(month)}.{year}"
