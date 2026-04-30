"""Persistent per-session verification flag (set true by guardrail agent after PIN success)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class VerificationStore:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def _init_db(self) -> None:
        with self._connect() as cx:
            cx.execute(
                """
                CREATE TABLE IF NOT EXISTS session_verification (
                    session_id TEXT PRIMARY KEY,
                    verified INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def is_verified(self, session_id: str) -> bool:
        with self._connect() as cx:
            row = cx.execute(
                "SELECT verified FROM session_verification WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return bool(row and row[0])

    def set_verified(self, session_id: str, *, verified: bool = True) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as cx:
            cx.execute(
                """
                INSERT INTO session_verification (session_id, verified, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    verified = excluded.verified,
                    updated_at = excluded.updated_at
                """,
                (session_id, 1 if verified else 0, now),
            )

    def clear(self, session_id: str) -> None:
        with self._connect() as cx:
            cx.execute("DELETE FROM session_verification WHERE session_id = ?", (session_id,))
