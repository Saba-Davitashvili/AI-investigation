"""PostgreSQL connection and search metadata. Credentials are environment-only."""
import json
import os
from contextlib import contextmanager
from threading import RLock, local
from urllib.parse import urlparse, parse_qs


@contextmanager
def connection():
    import psycopg
    from psycopg.rows import dict_row
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("Cloud mode requires DATABASE_URL.")
    parsed = urlparse(url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} and parse_qs(parsed.query).get("sslmode", [""])[0] not in {"require", "verify-ca", "verify-full"}:
        raise RuntimeError("Cloud database connection must require TLS.")
    # Use sslmode=require in the provider's connection string. Never print it.
    with psycopg.connect(url, connect_timeout=15, row_factory=dict_row) as conn:
        conn.execute("SET statement_timeout = '60s'")
        yield conn


def initialize_search_store():
    with connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS search_collections (
            name TEXT PRIMARY KEY, metadata_json TEXT NOT NULL, complete BOOLEAN NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS search_terms (
            collection TEXT NOT NULL, term TEXT NOT NULL, term_id INTEGER NOT NULL,
            document_frequency INTEGER NOT NULL, PRIMARY KEY(collection, term)
        )""")


def metadata(name, require_complete=True):
    with connection() as conn:
        row = conn.execute("SELECT metadata_json, complete FROM search_collections WHERE name = %s", (name,)).fetchone()
    if row is None or (require_complete and not row["complete"]):
        raise RuntimeError("Cloud index is not ready. Run seed_cloud.py first.")
    return json.loads(row["metadata_json"])


def save_statistics(name, values, vocabulary, complete=False):
    with connection() as conn:
        conn.execute("""INSERT INTO search_collections(name, metadata_json, complete) VALUES(%s,%s,%s)
            ON CONFLICT(name) DO UPDATE SET metadata_json=excluded.metadata_json, complete=excluded.complete""",
                     (name, json.dumps(values), complete))
        conn.execute("DELETE FROM search_terms WHERE collection=%s", (name,))
        with conn.cursor() as cursor:
            cursor.executemany("INSERT INTO search_terms VALUES(%s,%s,%s,%s)",
                               ((name, word, index, frequency) for word, (index, frequency) in vocabulary.items()))


def mark_complete(name):
    with connection() as conn:
        conn.execute("UPDATE search_collections SET complete=TRUE WHERE name=%s", (name,))


def lookup_terms(name, words):
    if not words:
        return {}
    with connection() as conn:
        rows = conn.execute("SELECT term, term_id, document_frequency FROM search_terms WHERE collection=%s AND term = ANY(%s)",
                            (name, list(words))).fetchall()
    return {row["term"]: (row["term_id"], row["document_frequency"]) for row in rows}


class SharedUploadLock:
    """Reentrant local lock plus PostgreSQL advisory lock across deploy overlap.

    Search and upload refresh both use this lock. This deliberately serializes
    a small shared demo, preventing a second process from reading half an index.
    It is not intended as a scalable multi-user queue.
    """
    def __init__(self):
        self._lock = RLock()
        self._thread = local()

    def __enter__(self):
        self._lock.acquire()
        depth = getattr(self._thread, "depth", 0)
        try:
            if depth == 0:
                context = connection()
                conn = context.__enter__()
                try:
                    # Transaction-level lock releases automatically on connection failure.
                    conn.execute("SELECT pg_advisory_xact_lock(73917391)")
                except BaseException:
                    context.__exit__(*__import__('sys').exc_info())
                    raise
                self._thread.context = context
            self._thread.depth = depth + 1
            return self
        except BaseException:
            self._lock.release()
            raise

    def __exit__(self, kind, value, traceback):
        self._thread.depth -= 1
        try:
            if self._thread.depth == 0:
                self._thread.context.__exit__(kind, value, traceback)
                del self._thread.context
        finally:
            self._lock.release()
