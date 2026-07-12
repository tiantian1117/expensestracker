from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).resolve().parent / "data" / "expense_tracker.db"

DEFAULT_ACCOUNTS = [
    ("Paper Bills", "Paper Bills", 0.0),
    ("Coins", "Coins", 0.0),
    ("GCash", "E-Money", 0.0),
    ("Maya", "E-Money", 0.0),
    ("Bank Account", "Bank Deposit", 0.0),
]


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                account_type TEXT NOT NULL,
                opening_balance REAL NOT NULL DEFAULT 0 CHECK (opening_balance >= 0),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_date TEXT NOT NULL,
                transaction_type TEXT NOT NULL
                    CHECK (transaction_type IN ('Income', 'Expense', 'Transfer')),
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK (amount > 0),
                account_id INTEGER NOT NULL,
                destination_account_id INTEGER,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id),
                FOREIGN KEY (destination_account_id) REFERENCES accounts(id),
                CHECK (
                    (transaction_type = 'Transfer'
                     AND destination_account_id IS NOT NULL
                     AND destination_account_id <> account_id)
                    OR
                    (transaction_type <> 'Transfer'
                     AND destination_account_id IS NULL)
                )
            );

            CREATE INDEX IF NOT EXISTS idx_transactions_date
                ON transactions(transaction_date);
            CREATE INDEX IF NOT EXISTS idx_transactions_account
                ON transactions(account_id);
            CREATE INDEX IF NOT EXISTS idx_transactions_destination
                ON transactions(destination_account_id);
            """
        )

        existing = connection.execute(
            "SELECT COUNT(*) AS count FROM accounts"
        ).fetchone()["count"]

        if existing == 0:
            connection.executemany(
                """
                INSERT INTO accounts (name, account_type, opening_balance)
                VALUES (?, ?, ?)
                """,
                DEFAULT_ACCOUNTS,
            )


def fetch_accounts(active_only: bool = False) -> list[dict[str, Any]]:
    where_clause = "WHERE a.is_active = 1" if active_only else ""
    query = f"""
        SELECT
            a.id,
            a.name,
            a.account_type,
            a.opening_balance,
            a.is_active,
            a.created_at,
            ROUND(
                a.opening_balance
                + COALESCE(SUM(
                    CASE
                        WHEN t.transaction_type = 'Income'
                             AND t.account_id = a.id THEN t.amount
                        WHEN t.transaction_type = 'Expense'
                             AND t.account_id = a.id THEN -t.amount
                        WHEN t.transaction_type = 'Transfer'
                             AND t.account_id = a.id THEN -t.amount
                        WHEN t.transaction_type = 'Transfer'
                             AND t.destination_account_id = a.id THEN t.amount
                        ELSE 0
                    END
                ), 0),
                2
            ) AS balance
        FROM accounts a
        LEFT JOIN transactions t
            ON t.account_id = a.id
            OR t.destination_account_id = a.id
        {where_clause}
        GROUP BY a.id
        ORDER BY
            CASE a.account_type
                WHEN 'Paper Bills' THEN 1
                WHEN 'Coins' THEN 2
                WHEN 'E-Money' THEN 3
                WHEN 'Bank Deposit' THEN 4
                ELSE 5
            END,
            a.name
    """
    with get_connection() as connection:
        rows = connection.execute(query).fetchall()
    return [dict(row) for row in rows]


def fetch_account_type_balances() -> list[dict[str, Any]]:
    accounts = fetch_accounts(active_only=False)
    totals: dict[str, float] = {}
    for account in accounts:
        totals[account["account_type"]] = (
            totals.get(account["account_type"], 0.0) + float(account["balance"])
        )
    return [
        {"account_type": account_type, "balance": round(balance, 2)}
        for account_type, balance in totals.items()
    ]


def add_account(name: str, account_type: str, opening_balance: float) -> None:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Account name is required.")
    if opening_balance < 0:
        raise ValueError("Opening balance cannot be negative.")

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO accounts (name, account_type, opening_balance)
            VALUES (?, ?, ?)
            """,
            (clean_name, account_type, round(opening_balance, 2)),
        )


def update_account(
    account_id: int,
    name: str,
    account_type: str,
    opening_balance: float,
    is_active: bool,
) -> None:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Account name is required.")
    if opening_balance < 0:
        raise ValueError("Opening balance cannot be negative.")

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE accounts
            SET name = ?, account_type = ?, opening_balance = ?, is_active = ?
            WHERE id = ?
            """,
            (
                clean_name,
                account_type,
                round(opening_balance, 2),
                int(is_active),
                account_id,
            ),
        )


def add_transaction(
    transaction_date: date | str,
    transaction_type: str,
    category: str,
    amount: float,
    account_id: int,
    destination_account_id: int | None = None,
    note: str = "",
) -> None:
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    if transaction_type not in {"Income", "Expense", "Transfer"}:
        raise ValueError("Invalid transaction type.")

    if transaction_type == "Transfer":
        if destination_account_id is None:
            raise ValueError("A destination account is required for a transfer.")
        if destination_account_id == account_id:
            raise ValueError("Source and destination accounts must be different.")
        category = "Account Transfer"
    else:
        destination_account_id = None

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO transactions (
                transaction_date,
                transaction_type,
                category,
                amount,
                account_id,
                destination_account_id,
                note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(transaction_date),
                transaction_type,
                category.strip() or "Other",
                round(amount, 2),
                account_id,
                destination_account_id,
                note.strip(),
            ),
        )


def delete_transaction(transaction_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM transactions WHERE id = ?",
            (transaction_id,),
        )


def fetch_transactions(
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    transaction_type: str | None = None,
    account_id: int | None = None,
    category: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    parameters: list[Any] = []

    if start_date:
        conditions.append("t.transaction_date >= ?")
        parameters.append(str(start_date))
    if end_date:
        conditions.append("t.transaction_date <= ?")
        parameters.append(str(end_date))
    if transaction_type and transaction_type != "All":
        conditions.append("t.transaction_type = ?")
        parameters.append(transaction_type)
    if account_id:
        conditions.append(
            "(t.account_id = ? OR t.destination_account_id = ?)"
        )
        parameters.extend([account_id, account_id])
    if category and category != "All":
        conditions.append("t.category = ?")
        parameters.append(category)

    where_clause = (
        "WHERE " + " AND ".join(conditions)
        if conditions
        else ""
    )
    limit_clause = "LIMIT ?" if limit else ""
    if limit:
        parameters.append(limit)

    query = f"""
        SELECT
            t.id,
            t.transaction_date,
            t.transaction_type,
            t.category,
            t.amount,
            t.note,
            source.name AS account,
            source.account_type AS account_type,
            destination.name AS destination_account,
            t.created_at
        FROM transactions t
        JOIN accounts source ON source.id = t.account_id
        LEFT JOIN accounts destination
            ON destination.id = t.destination_account_id
        {where_clause}
        ORDER BY t.transaction_date DESC, t.id DESC
        {limit_clause}
    """

    with get_connection() as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


def fetch_categories() -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT category
            FROM transactions
            WHERE transaction_type <> 'Transfer'
            ORDER BY category
            """
        ).fetchall()
    return [row["category"] for row in rows]


def fetch_summary(start_date: date | str, end_date: date | str) -> dict[str, float]:
    query = """
        SELECT
            COALESCE(SUM(
                CASE WHEN transaction_type = 'Income' THEN amount ELSE 0 END
            ), 0) AS income,
            COALESCE(SUM(
                CASE WHEN transaction_type = 'Expense' THEN amount ELSE 0 END
            ), 0) AS expense
        FROM transactions
        WHERE transaction_date BETWEEN ? AND ?
    """
    with get_connection() as connection:
        row = connection.execute(
            query,
            (str(start_date), str(end_date)),
        ).fetchone()

    income = round(float(row["income"]), 2)
    expense = round(float(row["expense"]), 2)
    return {
        "income": income,
        "expense": expense,
        "net": round(income - expense, 2),
    }


def fetch_monthly_summary(months: int = 12) -> list[dict[str, Any]]:
    query = """
        SELECT
            strftime('%Y-%m', transaction_date) AS month,
            ROUND(SUM(
                CASE WHEN transaction_type = 'Income' THEN amount ELSE 0 END
            ), 2) AS income,
            ROUND(SUM(
                CASE WHEN transaction_type = 'Expense' THEN amount ELSE 0 END
            ), 2) AS expense
        FROM transactions
        WHERE transaction_type IN ('Income', 'Expense')
          AND transaction_date >= date('now', 'start of month', ?)
        GROUP BY strftime('%Y-%m', transaction_date)
        ORDER BY month
    """
    offset = f"-{max(months - 1, 0)} months"
    with get_connection() as connection:
        rows = connection.execute(query, (offset,)).fetchall()
    return [dict(row) for row in rows]


def fetch_expense_by_category(
    start_date: date | str,
    end_date: date | str,
) -> list[dict[str, Any]]:
    query = """
        SELECT
            category,
            ROUND(SUM(amount), 2) AS amount
        FROM transactions
        WHERE transaction_type = 'Expense'
          AND transaction_date BETWEEN ? AND ?
        GROUP BY category
        ORDER BY amount DESC
    """
    with get_connection() as connection:
        rows = connection.execute(
            query,
            (str(start_date), str(end_date)),
        ).fetchall()
    return [dict(row) for row in rows]
