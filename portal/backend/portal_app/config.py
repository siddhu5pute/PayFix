"""Portal settings. Every secret comes from the environment; nothing is hardcoded or logged."""
from __future__ import annotations

import os


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.database_url = os.environ.get(
            "PORTAL_DATABASE_URL", "postgresql://portal:portal@localhost:5432/portal")
        self.razorpay_key_id = os.environ.get("RAZORPAY_KEY_ID", "")
        self.razorpay_key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
        self.razorpay_webhook_secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
        self.razorpay_api_base = os.environ.get("RAZORPAY_API_BASE", "https://api.razorpay.com/v1").rstrip("/")
        self.gateway_mode = os.environ.get("GATEWAY_MODE", "mock")  # mock | razorpay
        self.internal_api_key = os.environ.get("INTERNAL_API_KEY", "")
        self.admin_key = os.environ.get("ADMIN_KEY", "")
        self.demo_mode = _bool("DEMO_MODE", True)
        self.merchant_name = os.environ.get("MERCHANT_NAME", "CampusPay")
        # Failure-injection defaults (can be changed at runtime from the demo control room)
        self.drop_webhooks = _bool("DROP_WEBHOOKS", False)
        self.delay_webhook_seconds = int(os.environ.get("DELAY_WEBHOOK_SECONDS", "0") or 0)
        self.duplicate_webhooks = _bool("DUPLICATE_WEBHOOKS", False)
        self.cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]


settings = Settings()
