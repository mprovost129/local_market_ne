from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

from django.core.cache import cache

import requests


ZIP_LOOKUP_TIMEOUT_SECONDS = 2.5
ZIP_CACHE_SECONDS = 60 * 60 * 24 * 7


def _normalize_zip5(raw: str) -> str:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    return digits[:5]


def _to_decimal(raw) -> Optional[Decimal]:
    try:
        val = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return val.quantize(Decimal("0.000001"))


def lookup_zip_centroid(zip_code: str) -> Optional[Tuple[Decimal, Decimal]]:
    """
    Best-effort ZIP centroid lookup using zippopotam.us.
    Returns (lat, lng) as Decimal or None.
    """
    zip5 = _normalize_zip5(zip_code)
    if len(zip5) != 5:
        return None

    cache_key = f"geo:zip5:{zip5}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = f"https://api.zippopotam.us/us/{zip5}"
    try:
        resp = requests.get(url, timeout=ZIP_LOOKUP_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            cache.set(cache_key, None, timeout=60 * 30)
            return None
        payload = resp.json() or {}
        places = payload.get("places") or []
        if not places:
            cache.set(cache_key, None, timeout=60 * 30)
            return None
        first = places[0] or {}
        lat = _to_decimal(first.get("latitude"))
        lng = _to_decimal(first.get("longitude"))
        if lat is None or lng is None:
            cache.set(cache_key, None, timeout=60 * 30)
            return None
        out = (lat, lng)
        cache.set(cache_key, out, timeout=ZIP_CACHE_SECONDS)
        return out
    except Exception:
        cache.set(cache_key, None, timeout=60 * 10)
        return None
