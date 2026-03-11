# orders/templatetags/money.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django import template

register = template.Library()


@register.filter(name="cents_to_dollars")
def cents_to_dollars(value) -> str:
    """
    12345 -> "123.45"
    Safely formats cents as dollars for display.
    """
    try:
        cents = int(value or 0)
    except (TypeError, ValueError):
        cents = 0

    dollars = (Decimal(cents) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{dollars}"


@register.filter(name="money")
def money(value) -> str:
    """
    Formats a dollar amount as currency.
    Examples:
      12 -> "$12.00"
      Decimal("12.5") -> "$12.50"
      None -> "$0.00"
    """
    try:
        dollars = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        dollars = Decimal("0.00")
    return f"${dollars}"

@register.filter(name="dict_get")
def dict_get(d, key):
    """Safely get a dict value in templates: {{ mydict|dict_get:somekey }}"""
    try:
        return (d or {}).get(key)
    except Exception:
        return None
