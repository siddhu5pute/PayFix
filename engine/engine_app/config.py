from __future__ import annotations

import os


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.database_url = os.environ.get(
            "ENGINE_DATABASE_URL", "postgresql://engine:engine@localhost:5433/engine")
        self.portal_internal_url = os.environ.get("PORTAL_INTERNAL_URL", "http://localhost:8000").rstrip("/")
        self.internal_api_key = os.environ.get("INTERNAL_API_KEY", "")
        self.razorpay_key_id = os.environ.get("RAZORPAY_KEY_ID", "")
        self.razorpay_key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
        self.razorpay_api_base = os.environ.get("RAZORPAY_API_BASE", "https://api.razorpay.com/v1").rstrip("/")
        self.recon_interval_seconds = int(os.environ.get("RECON_INTERVAL_SECONDS", "15"))
        self.min_age_seconds = int(os.environ.get("MIN_AGE_SECONDS", "30"))
        self.lookback_hours = int(os.environ.get("RECON_LOOKBACK_HOURS", "24"))
        self.abandon_after_seconds = int(os.environ.get("ABANDON_AFTER_SECONDS", "300"))
        self.dry_run = _bool("DRY_RUN", False)
        self.auto_refund_duplicates = _bool("AUTO_REFUND_DUPLICATES", True)
        self.run_worker = _bool("ENGINE_RUN_WORKER", True)
        self.demo_mode = _bool("DEMO_MODE", True)
        self.max_retries = int(os.environ.get("GATEWAY_MAX_RETRIES", "4"))
        self.retry_base_seconds = float(os.environ.get("GATEWAY_RETRY_BASE_SECONDS", "0.5"))
        self.cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]


settings = Settings()
