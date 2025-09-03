import os
import psycopg
from psycopg_pool import ConnectionPool

POSTGRES_USER = os.getenv("POSTGRES_USER", "teuser")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "tepass")
POSTGRES_DB = os.getenv("POSTGRES_DB", "te_audit")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))

DSN = f"host={POSTGRES_HOST} port={POSTGRES_PORT} dbname={POSTGRES_DB} user={POSTGRES_USER} password={POSTGRES_PASSWORD}"

pool = ConnectionPool(DSN, min_size=1, max_size=4, timeout=10)

def ensure_schema():
    schema_sql_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "sql", "create_audit_schema.sql")
    with open(schema_sql_path, "r", encoding="utf-8") as f:
        ddl = f.read()
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
