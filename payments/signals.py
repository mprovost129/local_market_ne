# payments/signals.py
from __future__ import annotations

"""
Payment signals module.

Fee-waiver start logic now lives in products.signals and begins when a listing first
goes live (is_active=True), not when Stripe account rows are created.
"""
