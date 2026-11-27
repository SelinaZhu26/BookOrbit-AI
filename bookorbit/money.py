"""Money helpers. All arithmetic is done with Decimal and rounded to the cent."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def D(value) -> Decimal:
    """Convert a stored number/str to a Decimal rounded to the cent."""
    if isinstance(value, Decimal):
        return value.quantize(CENT, rounding=ROUND_HALF_UP)
    if value is None or value == "":
        return Decimal("0.00")
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def to_store(value) -> float:
    """Value written to the JSON text files (2 decimals)."""
    return float(D(value))


def fmt(value) -> str:
    v = D(value)
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.2f}"


def parse_amount(text, max_amount: str = "10000.00") -> Decimal:
    """UC-07 deposit check. Raises ValueError("Enter a valid amount")."""
    raw = str(text).strip().replace("$", "").replace(",", "")
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid amount")
    if not amount.is_finite() or amount <= 0 or amount > Decimal(max_amount):
        raise ValueError("Enter a valid amount")
    if amount.as_tuple().exponent < -2:      # more than 2 decimals
        raise ValueError("Enter a valid amount")
    return D(amount)
