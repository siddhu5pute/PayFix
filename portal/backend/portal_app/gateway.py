"""Minimal Razorpay Orders client used by the portal (works against Razorpay or MockPay)."""
from __future__ import annotations

import httpx

from .config import settings


class GatewayError(Exception):
    pass


def create_order(amount_paise: int, receipt: str, notes: dict) -> dict:
    try:
        r = httpx.post(
            f"{settings.razorpay_api_base}/orders",
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
            json={"amount": amount_paise, "currency": "INR", "receipt": receipt, "notes": notes},
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise GatewayError(f"gateway unreachable: {exc.__class__.__name__}") from exc
    if r.status_code >= 400:
        try:
            desc = r.json().get("error", {}).get("description") or r.text
        except Exception:
            desc = r.text
        raise GatewayError(f"order creation failed ({r.status_code}): {desc}")
    return r.json()
