"""Razorpay signature checks (constant-time comparisons)."""
from __future__ import annotations

import hashlib
import hmac


def hmac_sha256_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_checkout_signature(order_id: str, payment_id: str, signature: str, key_secret: str) -> bool:
    """Checkout handler signature: HMAC-SHA256("order_id|payment_id", key_secret)."""
    if not (order_id and payment_id and signature and key_secret):
        return False
    expected = hmac_sha256_hex(key_secret, f"{order_id}|{payment_id}".encode())
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(raw_body: bytes, signature: str | None, webhook_secret: str) -> bool:
    """Webhook signature: HMAC-SHA256(raw request body, webhook secret) in X-Razorpay-Signature."""
    if not (signature and webhook_secret):
        return False
    expected = hmac_sha256_hex(webhook_secret, raw_body)
    return hmac.compare_digest(expected, signature)
