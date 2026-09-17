"""Persistência SQLite, autenticação e controle de acesso às reuniões."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("TORUS_DB_PATH", str(BACKEND_ROOT / "runtime" / "torus.db")))
PBKDF2_ITERATIONS = 310_000
SESSION_HOURS = 8

DEMO_USERS = (
    ("Marina Costa", "manager@torus.ai", "Torus@2026", "manager"),
    ("Ana Souza", "ana@torus.ai", "Vendas@2026", "seller"),
    ("Carlos Lima", "carlos@torus.ai", "Vendas@2026", "seller"),
)


@contextmanager
def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
    finally:
        connection.close()


def _hash_password(password: str, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), actual_salt, PBKDF2_ITERATIONS
    )
    return "$".join(
        (
            "pbkdf2_sha256",
            str(PBKDF2_ITERATIONS),
            base64.urlsafe_b64encode(actual_salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_value, digest_value = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_value.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_value.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _ensure_column(
    connection: sqlite3.Connection, table: str, name: str, definition: str
) -> None:
    existing = {
        row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
    }
    if name not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('seller', 'manager')),
                active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id INTEGER NOT NULL,
                seller_id INTEGER NOT NULL REFERENCES users(id),
                created_by INTEGER NOT NULL REFERENCES users(id),
                title TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                transcript_json TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                intent TEXT NOT NULL,
                sentiment TEXT NOT NULL,
                churn_signal INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_meetings_seller ON meetings(seller_id);
            CREATE INDEX IF NOT EXISTS idx_meetings_created_at
            ON meetings(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            """
        )
        _ensure_column(
            connection,
            "analyses",
            "meeting_record_id",
            "INTEGER REFERENCES meetings(id)",
        )
        _ensure_column(
            connection, "analyses", "seller_id", "INTEGER REFERENCES users(id)"
        )
        from app.crm import migrate

        migrate(connection)
        for name, email, password, role in DEMO_USERS:
            connection.execute(
                """
                INSERT OR IGNORE INTO users (name, email, password_hash, role)
                VALUES (?, ?, ?, ?)
                """,
                (name, email, _hash_password(password), role),
            )
        from app.organizational_schema import migrate as migrate_organizational

        migrate_organizational(connection)
        connection.execute(
            "DELETE FROM sessions WHERE expires_at <= ?",
            (datetime.now(timezone.utc).isoformat(),),
        )
        connection.commit()


def public_user(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "email": str(row["email"]),
        "role": str(row["role"]),
    }


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE AND active = 1",
            (email.strip(),),
        ).fetchone()
    if row is None or not _verify_password(password, row["password_hash"]):
        return None
    return public_user(row)


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user_id, expires_at.isoformat()),
        )
        connection.commit()
    return token


def get_user_by_token(token: str) -> dict[str, Any] | None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT users.*, sessions.expires_at
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND users.active = 1
            """,
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        if datetime.fromisoformat(row["expires_at"]) <= now:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (token_hash,)
            )
            connection.commit()
            return None
    return public_user(row)


def delete_session(token: str) -> None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with get_connection() as connection:
        connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        connection.commit()


def list_sellers() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, name, email, role
            FROM users
            WHERE role = 'seller' AND active = 1
            ORDER BY name
            """
        ).fetchall()
    return [public_user(row) for row in rows]


def get_user(user_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, name, email, role FROM users WHERE id = ? AND active = 1",
            (user_id,),
        ).fetchone()
    return public_user(row) if row else None


def count_meetings() -> int:
    with get_connection() as connection:
        return int(connection.execute("SELECT COUNT(*) FROM meetings").fetchone()[0])


def save_meeting(
    payload: dict[str, Any],
    analysis: dict[str, Any],
    seller_id: int,
    created_by: int,
) -> int:
    title = str(payload.get("title") or f"Reunião {payload.get('meeting_id')}").strip()
    customer_name = str(payload.get("customer_name") or "Cliente não informado").strip()
    with get_connection() as connection:
        customer_id = payload.get("customer_id")
        if customer_id is None:
            connection.execute(
                "INSERT OR IGNORE INTO customers (name,seller_id) VALUES (?,?)",
                (customer_name, seller_id),
            )
            customer_id = connection.execute(
                "SELECT id FROM customers WHERE name=? COLLATE NOCASE AND seller_id=?",
                (customer_name, seller_id),
            ).fetchone()["id"]
        cursor = connection.execute(
            """
            INSERT INTO meetings (
                external_id, seller_id, created_by, title, customer_name,
                summary_json, transcript_json, analysis_json, customer_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(payload["meeting_id"]),
                seller_id,
                created_by,
                title,
                customer_name,
                json.dumps(analysis["summary"], ensure_ascii=False),
                json.dumps(payload["conversation"], ensure_ascii=False),
                json.dumps(analysis, ensure_ascii=False),
                customer_id,
            ),
        )
        record_id = int(cursor.lastrowid)
        for item in analysis["message_analysis"]:
            connection.execute(
                """
                INSERT INTO analyses (
                    text, intent, sentiment, churn_signal, meeting_record_id, seller_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item["original_text"],
                    item["intent"],
                    item["sentiment"]["label"],
                    int(item["features"]["churn_signal"]),
                    record_id,
                    seller_id,
                ),
            )
        connection.commit()
    return record_id


def _meeting_list_item(row: sqlite3.Row) -> dict[str, Any]:
    summary = json.loads(row["summary_json"])
    return {
        "id": int(row["id"]),
        "meeting_id": int(row["external_id"]),
        "customer_id": row["customer_id"],
        "title": row["title"],
        "customer_name": row["customer_name"],
        "created_at": row["created_at"],
        "seller": {"id": int(row["seller_id"]), "name": row["seller_name"]},
        "summary": summary,
    }


def list_meetings(user: dict[str, Any]) -> list[dict[str, Any]]:
    query = """
        SELECT meetings.*, users.name AS seller_name
        FROM meetings
        JOIN users ON users.id = meetings.seller_id
    """
    parameters: tuple[Any, ...] = ()
    if user["role"] == "seller":
        query += " WHERE meetings.seller_id = ?"
        parameters = (user["id"],)
    query += " ORDER BY meetings.created_at DESC, meetings.id DESC"
    with get_connection() as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [_meeting_list_item(row) for row in rows]


def get_meeting(record_id: int, user: dict[str, Any]) -> dict[str, Any] | None:
    query = """
        SELECT meetings.*, users.name AS seller_name
        FROM meetings
        JOIN users ON users.id = meetings.seller_id
        WHERE meetings.id = ?
    """
    parameters: list[Any] = [record_id]
    if user["role"] == "seller":
        query += " AND meetings.seller_id = ?"
        parameters.append(user["id"])
    with get_connection() as connection:
        row = connection.execute(query, tuple(parameters)).fetchone()
    if row is None:
        return None
    item = _meeting_list_item(row)
    item["conversation"] = json.loads(row["transcript_json"])
    item["analysis"] = json.loads(row["analysis_json"])
    return item


def save_message_analysis(
    text: str,
    intent: str,
    sentiment: str,
    churn_signal: bool,
) -> None:
    """Registra o resultado de uma análise feita fora de uma reunião completa."""
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO analyses (text, intent, sentiment, churn_signal)
            VALUES (?, ?, ?, ?)
            """,
            (text, intent, sentiment, int(churn_signal)),
        )
        connection.commit()


def list_users() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM users ORDER BY name").fetchall()
    return [{**public_user(row), "active": bool(row["active"])} for row in rows]


def create_user(name: str, email: str, password: str, role: str) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO users (name,email,password_hash,role) VALUES (?,?,?,?)",
            (name, email.lower(), _hash_password(password), role),
        )
        connection.commit()
        return int(cursor.lastrowid)


def set_user_active(user_id: int, active: bool) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE users SET active=? WHERE id=?", (int(active), user_id)
        )
        if not active:
            connection.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        connection.commit()
        return cursor.rowcount > 0


def change_password(user_id: int, current_password: str, new_password: str) -> bool:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE id=? AND active=1", (user_id,)
        ).fetchone()
        if row is None or not _verify_password(current_password, row["password_hash"]):
            return False
        connection.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (_hash_password(new_password), user_id),
        )
        connection.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        connection.commit()
    return True


def rename_meeting(record_id: int, title: str, user: dict[str, Any]) -> bool:
    query = "UPDATE meetings SET title=? WHERE id=?"
    parameters: list[Any] = [title, record_id]
    if user["role"] != "manager":
        query += " AND seller_id=?"
        parameters.append(user["id"])
    with get_connection() as connection:
        cursor = connection.execute(query, parameters)
        connection.commit()
        return cursor.rowcount > 0
