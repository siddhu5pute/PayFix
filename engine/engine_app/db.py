from __future__ import annotations

import logging
import time
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

log = logging.getLogger("engine.db")


class Database:
    def __init__(self, url: str, max_size: int = 20):
        self.pool = ConnectionPool(url, min_size=1, max_size=max_size,
                                   kwargs={"row_factory": dict_row}, open=False)
        self.pool.open()

    def connection(self):
        return self.pool.connection()

    def close(self) -> None:
        self.pool.close()

    def apply_schema(self, retries: int = 30) -> None:
        sql = (Path(__file__).parent / "schema.sql").read_text()
        last = None
        for attempt in range(retries):
            try:
                with self.connection() as conn:
                    conn.execute("SELECT pg_advisory_xact_lock(424202)")
                    conn.execute(sql)
                log.info("engine schema applied")
                return
            except Exception as exc:
                last = exc
                log.warning("schema attempt %d failed: %s", attempt + 1, exc)
                time.sleep(1)
        raise RuntimeError(f"could not apply schema: {last}")
