"""Clientes e tarefas comerciais, sempre limitados ao responsável da carteira."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.storage import get_connection


def migrate(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE,
            seller_id INTEGER NOT NULL REFERENCES users(id),
            segment TEXT NOT NULL DEFAULT '',
            stage TEXT NOT NULL DEFAULT 'active'
                CHECK(stage IN ('prospect', 'active', 'renewal', 'inactive')),
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name, seller_id)
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            meeting_id INTEGER REFERENCES meetings(id),
            title TEXT NOT NULL,
            due_date TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'normal'
                CHECK(priority IN ('normal','high')),
            status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','done')),
            notes TEXT NOT NULL DEFAULT '',
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_customers_seller ON customers(seller_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_customer_due
            ON tasks(customer_id,due_date);
        """
    )
    if "customer_id" not in {
        row["name"] for row in connection.execute("PRAGMA table_info(meetings)")
    }:
        connection.execute(
            "ALTER TABLE meetings ADD COLUMN customer_id "
            "INTEGER REFERENCES customers(id)"
        )
    connection.execute(
        """INSERT OR IGNORE INTO customers (name,seller_id)
           SELECT customer_name,seller_id FROM meetings WHERE customer_id IS NULL"""
    )
    connection.execute(
        """UPDATE meetings SET customer_id = (
               SELECT id FROM customers
               WHERE customers.name=meetings.customer_name COLLATE NOCASE
                 AND customers.seller_id=meetings.seller_id
           ) WHERE customer_id IS NULL"""
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_meetings_customer ON meetings(customer_id)"
    )


def scope(user: dict[str, Any], alias: str = "c") -> tuple[str, tuple]:
    if user["role"] == "manager":
        return "1=1", ()
    return f"{alias}.seller_id = ?", (user["id"],)


def list_customers(user: dict[str, Any]) -> list[dict[str, Any]]:
    condition, parameters = scope(user)
    with get_connection() as connection:
        rows = connection.execute(
            f"""SELECT c.*, u.name AS seller_name,
                   (SELECT COUNT(*) FROM meetings m WHERE m.customer_id=c.id)
                       AS meeting_count,
                   (SELECT COUNT(*) FROM tasks t WHERE t.customer_id=c.id
                       AND t.status='open') AS open_tasks,
                   (SELECT MIN(due_date) FROM tasks t WHERE t.customer_id=c.id
                       AND t.status='open') AS next_due,
                   (SELECT summary_json FROM meetings m WHERE m.customer_id=c.id
                       ORDER BY m.created_at DESC,m.id DESC LIMIT 1) AS latest_summary
               FROM customers c JOIN users u ON c.seller_id=u.id
               WHERE {condition} ORDER BY c.name,c.id""",
            parameters,
        ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["latest_summary"] = (
            json.loads(item["latest_summary"]) if item["latest_summary"] else None
        )
        results.append(item)
    return results


def get_customer(customer_id: int, user: dict[str, Any]) -> dict[str, Any] | None:
    condition, parameters = scope(user)
    with get_connection() as connection:
        row = connection.execute(
            f"""SELECT c.*,u.name AS seller_name FROM customers c
                JOIN users u ON c.seller_id=u.id WHERE c.id=? AND {condition}""",
            (customer_id, *parameters),
        ).fetchone()
    return dict(row) if row else None


def create_customer(values: dict[str, Any], seller_id: int) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO customers (name,seller_id,segment,stage,notes)
               VALUES (?,?,?,?,?)""",
            (
                values["name"],
                seller_id,
                values["segment"],
                values["stage"],
                values["notes"],
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def update_customer(customer_id: int, values: dict[str, Any], user: dict) -> bool:
    condition, parameters = scope(user, "customers")
    with get_connection() as connection:
        cursor = connection.execute(
            f"""UPDATE customers SET name=?,segment=?,stage=?,notes=?,
                updated_at=CURRENT_TIMESTAMP WHERE id=? AND {condition}""",
            (
                values["name"],
                values["segment"],
                values["stage"],
                values["notes"],
                customer_id,
                *parameters,
            ),
        )
        if cursor.rowcount:
            connection.execute(
                "UPDATE meetings SET customer_name=? WHERE customer_id=?",
                (values["name"], customer_id),
            )
        connection.commit()
        return cursor.rowcount > 0


def list_tasks(user: dict[str, Any]) -> list[dict[str, Any]]:
    condition, parameters = scope(user)
    with get_connection() as connection:
        rows = connection.execute(
            f"""SELECT t.*,c.name AS customer_name,c.seller_id,u.name AS seller_name
               FROM tasks t JOIN customers c ON c.id=t.customer_id
               JOIN users u ON u.id=c.seller_id WHERE {condition}
               ORDER BY CASE t.status WHEN 'open' THEN 0 ELSE 1 END,
                        t.due_date, t.id""",
            parameters,
        ).fetchall()
    return [dict(row) for row in rows]


def create_task(values: dict[str, Any], user: dict[str, Any]) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO tasks
               (customer_id,meeting_id,title,due_date,priority,notes,created_by)
               VALUES (?,?,?,?,?,?,?)""",
            (
                values["customer_id"],
                values["meeting_id"],
                values["title"],
                values["due_date"].isoformat(),
                values["priority"],
                values["notes"],
                user["id"],
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def update_task(task_id: int, values: dict[str, Any], user: dict[str, Any]) -> bool:
    condition, parameters = scope(user)
    with get_connection() as connection:
        cursor = connection.execute(
            f"""UPDATE tasks SET title=?,due_date=?,priority=?,notes=?,status=?,
                   completed_at=CASE WHEN ?='done'
                       THEN COALESCE(completed_at,CURRENT_TIMESTAMP) ELSE NULL END
               WHERE id=? AND customer_id IN (SELECT c.id FROM customers c
                   WHERE {condition})""",
            (
                values["title"],
                values["due_date"].isoformat(),
                values["priority"],
                values["notes"],
                values["status"],
                values["status"],
                task_id,
                *parameters,
            ),
        )
        connection.commit()
        return cursor.rowcount > 0
