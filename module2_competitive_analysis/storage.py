"""SQLite storage for competitive analysis snapshots.

Schema:
  apps       — tracked apps (name, store, apple_id)
  snapshots  — one row per tracking event (version, rating, review_count, ...)
  features   — feature checklist per app (parsed from update notes)
"""

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Optional


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS apps (
    app_id      TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    store       TEXT NOT NULL DEFAULT '',
    apple_id    TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id          TEXT NOT NULL REFERENCES apps(app_id),
    snapshot_date   TEXT NOT NULL,
    version         TEXT NOT NULL DEFAULT '',
    rating          REAL NOT NULL DEFAULT 0,
    rating_count    INTEGER NOT NULL DEFAULT 0,
    review_count    INTEGER NOT NULL DEFAULT 0,
    description     TEXT NOT NULL DEFAULT '',
    price_text      TEXT NOT NULL DEFAULT '',
    app_size_mb     REAL NOT NULL DEFAULT 0,
    update_notes    TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(app_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS feature_checks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id      TEXT NOT NULL REFERENCES apps(app_id),
    check_date  TEXT NOT NULL DEFAULT (date('now')),
    feature_key TEXT NOT NULL,
    present     INTEGER NOT NULL DEFAULT 0,
    notes       TEXT NOT NULL DEFAULT '',
    UNIQUE(app_id, check_date, feature_key)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_app ON snapshots(app_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_features_app ON feature_checks(app_id, check_date);
"""


class Storage:
    """SQLite-backed storage for competitive analysis data."""

    def __init__(self, db_path: str = "data/module2/competitor_tracker.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA_SQL)

    # ------------------------------------------------------------------
    # Apps
    # ------------------------------------------------------------------

    def upsert_app(self, app_id: str, name: str, store: str = "", apple_id: str = ""):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO apps(app_id, name, store, apple_id)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(app_id) DO UPDATE SET
                       name=excluded.name,
                       store=excluded.store,
                       apple_id=excluded.apple_id""",
                (app_id, name, store, apple_id),
            )

    def get_apps(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM apps ORDER BY name").fetchall()
            return [dict(r) for r in rows]

    def get_app(self, app_id: str) -> Optional[dict]:
        with self._conn() as conn:
            r = conn.execute("SELECT * FROM apps WHERE app_id = ?", (app_id,)).fetchone()
            return dict(r) if r else None

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def insert_snapshot(self, app_id: str, snapshot: dict):
        """Insert or replace a snapshot for the given app and date."""
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO snapshots
                   (app_id, snapshot_date, version, rating, rating_count,
                    review_count, description, price_text, app_size_mb, update_notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    app_id,
                    snapshot.get("snapshot_date", date.today().isoformat()),
                    snapshot.get("version", ""),
                    snapshot.get("rating", 0),
                    snapshot.get("rating_count", 0),
                    snapshot.get("review_count", 0),
                    snapshot.get("description", ""),
                    snapshot.get("price_text", ""),
                    snapshot.get("app_size_mb", 0),
                    snapshot.get("update_notes", ""),
                ),
            )

    def get_snapshots(self, app_id: str, limit: int = 30) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM snapshots
                   WHERE app_id = ?
                   ORDER BY snapshot_date DESC
                   LIMIT ?""",
                (app_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_latest_snapshot(self, app_id: str) -> Optional[dict]:
        with self._conn() as conn:
            r = conn.execute(
                """SELECT * FROM snapshots
                   WHERE app_id = ?
                   ORDER BY snapshot_date DESC
                   LIMIT 1""",
                (app_id,),
            ).fetchone()
            return dict(r) if r else None

    def get_snapshot_count(self, app_id: str) -> int:
        with self._conn() as conn:
            r = conn.execute(
                "SELECT COUNT(*) as cnt FROM snapshots WHERE app_id = ?",
                (app_id,),
            ).fetchone()
            return r["cnt"] if r else 0

    # ------------------------------------------------------------------
    # Feature checks
    # ------------------------------------------------------------------

    def upsert_feature(self, app_id: str, feature_key: str, present: bool, notes: str = ""):
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO feature_checks
                   (app_id, check_date, feature_key, present, notes)
                   VALUES (?, date('now'), ?, ?, ?)""",
                (app_id, feature_key, 1 if present else 0, notes),
            )

    def get_features(self, app_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM feature_checks
                   WHERE app_id = ?
                   ORDER BY check_date DESC""",
                (app_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def get_all_latest_snapshots(self) -> list[dict]:
        """Get the most recent snapshot for each tracked app."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT a.app_id, a.name, a.store,
                          s.snapshot_date, s.version, s.rating,
                          s.rating_count, s.review_count, s.price_text
                   FROM apps a
                   LEFT JOIN snapshots s ON s.id = (
                       SELECT s2.id FROM snapshots s2
                       WHERE s2.app_id = a.app_id
                       ORDER BY s2.snapshot_date DESC
                       LIMIT 1
                   )
                   ORDER BY a.name"""
            ).fetchall()
            return [dict(r) for r in rows]
