"""Small helpers shared by the test modules (kept out of conftest so it is imported once)."""
import uuid


def new_txn() -> str:
    return str(uuid.uuid4())


def audit_rows(engine_db, txn_id, step=None):
    sql = "SELECT * FROM audit_log WHERE txn_id=%s"
    params = [txn_id]
    if step:
        sql += " AND step=%s"
        params.append(step)
    with engine_db.connection() as conn:
        return conn.execute(sql + " ORDER BY id", params).fetchall()
