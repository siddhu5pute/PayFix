from __future__ import annotations

import logging
import time
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from contract import transitions_sql_values

log = logging.getLogger("portal.db")

_pool: ConnectionPool | None = None


def init_pool(database_url: str) -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(database_url, min_size=1, max_size=20,
                               kwargs={"row_factory": dict_row}, open=False)
        _pool.open()
    return _pool


def pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("database pool not initialised")
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def apply_schema(retries: int = 30) -> None:
    sql = (Path(__file__).parent / "schema.sql").read_text()
    last = None
    for attempt in range(retries):
        try:
            with pool().connection() as conn:
                conn.execute("SELECT pg_advisory_xact_lock(424201)")  # released on commit
                conn.execute(sql)
                conn.execute(
                    f"INSERT INTO allowed_transitions (from_status, to_status) VALUES "
                    f"{transitions_sql_values()} ON CONFLICT DO NOTHING")
            log.info("portal schema applied")
            return
        except Exception as exc:  # DB may still be starting
            last = exc
            log.warning("schema attempt %d failed: %s", attempt + 1, exc)
            time.sleep(1)
    raise RuntimeError(f"could not apply schema: {last}")
