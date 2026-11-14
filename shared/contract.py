"""PayFix shared contract.

Single source of truth for payment statuses, allowed transitions and money rules.
Copied into the portal backend and engine images at build time (see Dockerfiles).
The same transition table is enforced in Postgres by a trigger in each schema.
"""
from __future__ import annotations

CURRENCY = "INR"

# Portal payment statuses
CREATED = "created"
PENDING = "pending"
PAID = "paid"
FAILED = "failed"
UNKNOWN = "unknown"
REFUNDED = "refunded"

PAYMENT_STATUSES = (CREATED, PENDING, PAID, FAILED, UNKNOWN, REFUNDED)

# Allowed transitions. Nothing leaves paid/failed except a documented refund (paid -> refunded).
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    CREATED: frozenset({PENDING}),
    PENDING: frozenset({PAID, FAILED, UNKNOWN}),
    UNKNOWN: frozenset({PAID, FAILED}),
    PAID: frozenset({REFUNDED}),
    FAILED: frozenset(),
    REFUNDED: frozenset(),
}

# Gateway view of an order, as reported by the gateway client interface
G_CAPTURED = "captured"
G_FAILED = "failed"
G_NONE = "none"
G_UNCLEAR = "unclear"
GATEWAY_STATUSES = (G_CAPTURED, G_FAILED, G_NONE, G_UNCLEAR)


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in ALLOWED_TRANSITIONS.get(from_status, frozenset())


class InvalidTransition(Exception):
    def __init__(self, from_status: str, to_status: str):
        super().__init__(f"invalid transition {from_status} -> {to_status}")
        self.from_status = from_status
        self.to_status = to_status


def validate_amount_paise(amount: object) -> int:
    """Money is always integer paise. Floats and non-positive values are rejected."""
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise ValueError("amount_paise must be an integer number of paise")
    if amount <= 0:
        raise ValueError("amount_paise must be positive")
    return amount


def transitions_sql_values() -> str:
    """VALUES list used to seed the DB transition table so code and DB agree."""
    rows = [f"('{f}','{t}')" for f, tos in ALLOWED_TRANSITIONS.items() for t in sorted(tos)]
    return ",".join(rows)
