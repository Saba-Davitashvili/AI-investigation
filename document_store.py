import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from config import BASE_DIRECTORY


DATABASE_PATH = (
    BASE_DIRECTORY / "data" / "uploads" / "documents.sqlite3"
)


@contextmanager
def database():
    if os.getenv("STORAGE_BACKEND") == "cloud":
        from cloud_storage import connection
        with connection() as conn:
            yield PostgresAdapter(conn)
        return
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=30
    )
    connection.row_factory = sqlite3.Row

    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_store():
    with database() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                format TEXT NOT NULL,
                content_hash TEXT NOT NULL UNIQUE,
                parsed_json TEXT NOT NULL,
                original_file BLOB NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            )
        """)


def get_document(document_id):
    with database() as connection:
        row = connection.execute(
            """
            SELECT id, filename, format, parsed_json,
                   created_at, updated_at, version
            FROM documents
            WHERE id = ?
            """,
            (document_id,)
        ).fetchone()

    if row is None:
        return None

    result = dict(row)
    parsed = json.loads(result.pop("parsed_json"))

    return {
        **parsed,
        **result
    }


def list_documents():
    with database() as connection:
        rows = connection.execute("""
            SELECT id, filename, format,
                   created_at, updated_at, version
            FROM documents
            ORDER BY created_at DESC, id
        """).fetchall()

    return [dict(row) for row in rows]


class DocumentCapacityError(Exception):
    pass


def enforce_storage_budget(connection):
    if os.getenv("STORAGE_BACKEND") != "cloud":
        return
    row = connection.execute("SELECT COUNT(*) AS count, COALESCE(SUM(length(parsed_json)),0) AS text_size, COALESCE(SUM(length(original_file)),0) AS file_size FROM documents").fetchone()
    if row["count"] > 20 or row["text_size"] > 300000 or row["file_size"] > 20 * 1024 * 1024:
        raise DocumentCapacityError("Shared free demo capacity reached: 20 uploads, 300,000 parsed JSON characters, or 20 MiB of original files. Delete an upload or use a smaller file.")


def save_document(parsed, original_file):
    content_hash = hashlib.sha256(
        original_file
    ).hexdigest()

    document_id = str(uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    duplicate = False

    with database() as connection:
        cursor = connection.execute(
            """
            INSERT INTO documents (
                id, filename, format, content_hash,
                parsed_json, original_file,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(content_hash) DO NOTHING
            """,
            (
                document_id,
                parsed["filename"],
                parsed["format"],
                content_hash,
                json.dumps(parsed, ensure_ascii=False),
                original_file,
                timestamp,
                timestamp
            )
        )

        if cursor.rowcount == 0:
            duplicate = True
            row = connection.execute(
                """
                SELECT id FROM documents
                WHERE content_hash = ?
                """,
                (content_hash,)
            ).fetchone()

            document_id = row["id"]

        enforce_storage_budget(connection)

    return {
        "document": get_document(document_id),
        "duplicate": duplicate
    }




class DuplicateDocumentError(Exception):
    pass


def replace_document(document_id, parsed, original_file):
    content_hash = hashlib.sha256(original_file).hexdigest()
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        with database() as connection:
            cursor = connection.execute(
                """
                UPDATE documents
                SET filename = ?,
                    format = ?,
                    content_hash = ?,
                    parsed_json = ?,
                    original_file = ?,
                    updated_at = ?,
                    version = version + 1
                WHERE id = ?
                """,
                (
                    parsed["filename"],
                    parsed["format"],
                    content_hash,
                    json.dumps(parsed, ensure_ascii=False),
                    original_file,
                    timestamp,
                    document_id
                )
            )

            if cursor.rowcount == 0:
                return None
            enforce_storage_budget(connection)

    except sqlite3.IntegrityError:
        raise DuplicateDocumentError(
            "This file already belongs to another document."
        ) from None

    return get_document(document_id)


def delete_document(document_id):
    with database() as connection:
        cursor = connection.execute(
            "DELETE FROM documents WHERE id = ?",
            (document_id,)
        )

    return cursor.rowcount > 0

class PostgresAdapter:
    """Small dialect boundary; all data values remain bound parameters."""
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, parameters=None):
        from psycopg.errors import UniqueViolation
        sql = sql.replace("?", "%s").replace("original_file BLOB", "original_file BYTEA")
        try:
            return self.connection.execute(sql, parameters)
        except UniqueViolation:
            raise sqlite3.IntegrityError("Duplicate document content") from None
