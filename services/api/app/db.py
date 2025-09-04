import os
from pathlib import Path
import psycopg
from psycopg_pool import ConnectionPool

POSTGRES_USER = os.getenv("POSTGRES_USER", "teuser")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "tepass")
POSTGRES_DB = os.getenv("POSTGRES_DB", "te_audit")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))

DSN = f"host={POSTGRES_HOST} port={POSTGRES_PORT} dbname={POSTGRES_DB} user={POSTGRES_USER} password={POSTGRES_PASSWORD}"
pool = ConnectionPool(DSN, min_size=1, max_size=4, timeout=10)

SCHEMA_SQL_PATH = Path(os.getenv("SCHEMA_SQL_PATH", str(Path(__file__).resolve().parents[3] / "sql" / "create_audit_schema.sql")))

def ensure_schema():
    if not SCHEMA_SQL_PATH.exists():
        print(f"[warn] schema file not found: {SCHEMA_SQL_PATH}")
        return
    ddl = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()

def write_decision(row: dict):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                '''
                INSERT INTO audit.decisions
                (corr_id, symbol, decision, confidence, latency_ms, reason, model_tag, feature_ms, inference_ms, policy_ms)
                VALUES (%(corr_id)s, %(symbol)s, %(decision)s, %(confidence)s, %(latency_ms)s, %(reason)s, %(model_tag)s, %(feature_ms)s, %(inference_ms)s, %(policy_ms)s)
                ''',
                row,
            )
        conn.commit()
