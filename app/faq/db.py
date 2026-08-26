import re
import psycopg2
import psycopg2.pool

from .config import (
    PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD,
    PG_FAQ_TABLE, PG_CHAT_TABLE,
)
from .logging import faq_log

# ──────────────────────────────────────────────
# Connection Pool
# ──────────────────────────────────────────────
_pg_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def get_pg_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pg_pool
    if _pg_pool is None:
        _pg_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=10,
            host=PG_HOST, port=PG_PORT,
            dbname=PG_DB, user=PG_USER, password=PG_PASSWORD,
        )
    return _pg_pool


# ══════════════════════════════════════════════
# SCRAPER — Table setup & chunk storage
# ══════════════════════════════════════════════

def ensure_faq_table() -> None:
    pool = get_pg_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {PG_FAQ_TABLE} (
                    id         SERIAL PRIMARY KEY,
                    url        TEXT,
                    chunk_text TEXT,
                    section    TEXT,
                    topic      TEXT,
                    link_text  TEXT,
                    embedding  vector(3072)
                );
            """)
            conn.commit()
        faq_log.info("[DB] faq table '%s' ready", PG_FAQ_TABLE)
    except Exception as e:
        faq_log.error("[DB] Failed to create faq table: %s", e)
    finally:
        pool.putconn(conn)


def store_chunks(all_chunks: list) -> None:
    pool = get_pg_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            urls_to_update = list({chunk["url"] for chunk in all_chunks})
            cur.execute(f"DELETE FROM {PG_FAQ_TABLE} WHERE url = ANY(%s)", (urls_to_update,))
            faq_log.info("[DB] Deleted old chunks for %d URL(s)", len(urls_to_update))
            conn.commit()

            for chunk in all_chunks:
                cur.execute(
                    f"INSERT INTO {PG_FAQ_TABLE} (url, chunk_text, section, topic, link_text, embedding) VALUES (%s, %s, %s, %s, %s, %s)",
                    (chunk["url"], chunk["text"], chunk.get("section", ""), chunk.get("topic", ""), chunk.get("link_text", ""), chunk["embedding"]),
                )
            conn.commit()
        faq_log.info("[DB] All chunks stored successfully | total=%d", len(all_chunks))
    except Exception as e:
        faq_log.error("[DB] Failed to store chunks: %s", e)
        raise
    finally:
        pool.putconn(conn)


# ══════════════════════════════════════════════
# RETRIEVAL — Chat table, history, vector dim
# ══════════════════════════════════════════════

def get_pg_table() -> str:
    table = (PG_FAQ_TABLE or "").strip()
    if not table:
        raise ValueError("PG_FAQ_TABLE is not configured.")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise ValueError(f"Invalid PG_FAQ_TABLE value: {table!r}")
    return table


def get_pg_vector_dim() -> int | None:
    pool = get_pg_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT vector_dims(embedding) FROM {get_pg_table()} WHERE embedding IS NOT NULL LIMIT 1;")
            row = cur.fetchone()
            return row[0] if row and row[0] else None
    finally:
        pool.putconn(conn)


def ensure_chat_table() -> None:
    pool = get_pg_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", (PG_CHAT_TABLE,))
            if cur.fetchone()[0] is not None:
                return
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {PG_CHAT_TABLE} (
                    id         SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role       TEXT NOT NULL,
                    message    TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            conn.commit()
        faq_log.info("[DB] chat table '%s' ready", PG_CHAT_TABLE)
    except Exception as e:
        faq_log.error("[DB] Failed to create chat table: %s", e)
    finally:
        pool.putconn(conn)


def save_message(session_id: str, role: str, message: str) -> None:
    pool = get_pg_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {PG_CHAT_TABLE} (session_id, role, message) VALUES (%s, %s, %s)",
                (session_id, role, message),
            )
            conn.commit()
    except Exception as e:
        faq_log.error("[DB] Error saving message: %s", e)
    finally:
        pool.putconn(conn)


def get_history(session_id: str) -> list:
    pool = get_pg_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT role, message FROM {PG_CHAT_TABLE} WHERE session_id = %s ORDER BY id DESC LIMIT 6",
                (session_id,)
            )
            rows = cur.fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
    except Exception:
        return []
    finally:
        pool.putconn(conn)
