"""DECIDE: the rule table. Pure function, no I/O. Never guesses: anything unclear goes to a human.

| portal          | gateway            | action                                  |
|-----------------|--------------------|-----------------------------------------|
| pending/unknown | captured           | mark PAID (+ refund extra captures)     |
| pending/unknown | failed / none      | mark FAILED                             |
| pending/unknown | unclear            | manual review                           |
| paid            | captured (1)       | nothing (in sync)                       |
| paid            | captured (>1)      | refund the extra captures, keep first   |
| paid            | not captured       | manual review                           |
| failed          | captured           | manual review (money taken, portal says failed) |
| failed          | failed / none      | nothing (in sync)                       |
| anything        | unclear            | manual review                           |
"""
from __future__ import annotations

from dataclasses import dataclass, field

from contract import FAILED, G_CAPTURED, G_FAILED, G_NONE, G_UNCLEAR, PAID, PENDING, UNKNOWN

NONE = "none"
MARK_PAID = "mark_paid"
MARK_FAILED = "mark_failed"
MANUAL_REVIEW = "manual_review"
REFUND_DUPLICATES = "refund_duplicates"


@dataclass
class Decision:
    action: str
    mismatch_type: str | None = None
    reason: str = ""
    refund_payment_ids: list[str] = field(default_factory=list)
    keep_payment_id: str | None = None

    @property
    def is_mismatch(self) -> bool:
        return self.action != NONE

    def key(self) -> tuple:
        return (self.action, tuple(self.refund_payment_ids))


def decide(portal_status: str, gateway_status: str, captured_payment_ids: list[str] | None = None,
           auto_refund_duplicates: bool = True) -> Decision:
    captured = list(captured_payment_ids or [])
    keep = captured[0] if captured else None
    extras = captured[1:] if auto_refund_duplicates else []

    if portal_status in (PENDING, UNKNOWN):
        if gateway_status == G_CAPTURED:
            return Decision(MARK_PAID, f"PORTAL_{portal_status.upper()}_GATEWAY_CAPTURED",
                            f"gateway captured {keep} but portal says {portal_status}",
                            refund_payment_ids=extras, keep_payment_id=keep)
        if gateway_status == G_FAILED:
            return Decision(MARK_FAILED, f"PORTAL_{portal_status.upper()}_GATEWAY_FAILED",
                            f"all gateway attempts failed but portal says {portal_status}")
        if gateway_status == G_NONE:
            return Decision(MARK_FAILED, f"PORTAL_{portal_status.upper()}_NO_PAYMENT",
                            f"no payment ever reached the gateway but portal says {portal_status}")
        return Decision(MANUAL_REVIEW, "GATEWAY_UNCLEAR", "gateway state is not final; refusing to guess")

    if portal_status == PAID:
        if gateway_status == G_CAPTURED:
            if len(captured) > 1:
                if not auto_refund_duplicates:
                    return Decision(MANUAL_REVIEW, "DUPLICATE_CAPTURE",
                                    f"{len(captured)} captures on one order; auto refund disabled")
                return Decision(REFUND_DUPLICATES, "DUPLICATE_CAPTURE",
                                f"{len(captured)} captures on one order: keep {keep}, refund the rest",
                                refund_payment_ids=extras, keep_payment_id=keep)
            return Decision(NONE)
        return Decision(MANUAL_REVIEW, "PAID_NOT_CAPTURED",
                        f"portal says paid but gateway says {gateway_status}")

    if portal_status == FAILED:
        if gateway_status == G_CAPTURED:
            return Decision(MANUAL_REVIEW, "FAILED_BUT_CAPTURED",
                            "portal says failed but the gateway captured money: needs a human (refund or credit)")
        if gateway_status in (G_FAILED, G_NONE):
            return Decision(NONE)
        return Decision(MANUAL_REVIEW, "GATEWAY_UNCLEAR", "gateway state is not final; refusing to guess")

    return Decision(NONE)
