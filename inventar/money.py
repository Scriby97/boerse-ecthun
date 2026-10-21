"""Beträge und Aufteilung zwischen Besitzerin und Börse."""

from decimal import ROUND_HALF_UP, Decimal

FIVE_RAPPEN = Decimal("0.05")


def round_rappen(amount: Decimal) -> Decimal:
    """Auf 5 Rappen runden, wie beim Bargeld."""
    return (amount / FIVE_RAPPEN).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * FIVE_RAPPEN


def split(price: Decimal, owner_percent: Decimal) -> tuple[Decimal, Decimal]:
    """(Anteil Besitzerin, Anteil Börse). Der Anteil der Börse ist der Rest, damit die Summe immer stimmt."""
    owner = round_rappen(price * owner_percent / 100).quantize(Decimal("0.01"))
    return owner, (price - owner).quantize(Decimal("0.01"))
