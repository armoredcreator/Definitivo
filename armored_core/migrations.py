"""Versioned, copy-first migrations for the operational SQLite store."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import sqlite3
from pathlib import Path


STOCK_REQUEUE_MIGRATION = "20261024_001_requeue_approved_to_stock"
POST_STOCK_STATES = (
    "IA", "SPEECH", "STUDIO_BATCH", "STUDIO", "STUDIO_COMPLETE",
    "PUBLISHING", "PUBLISHED", "RECOVERY", "FAILED",
)


def sqlite_backup(source: Path, destination: Path) -> dict:
    """Create a consistent SQLite backup without modifying the source."""
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve()
    if source == destination or destination.exists():
        raise FileExistsError("backup destination must be new and distinct")
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=30)
    dst = sqlite3.connect(destination, timeout=30)
    try:
        src.backup(dst, pages=512, sleep=0.05)
        dst.commit()
        quick = [row[0] for row in dst.execute("PRAGMA quick_check")]
        foreign_keys = dst.execute("PRAGMA foreign_key_check").fetchall()
        if quick != ["ok"] or foreign_keys:
            raise sqlite3.DatabaseError("SQLite backup failed integrity validation")
        tables = {
            str(row[0]): int(dst.execute(
                'SELECT count(*) FROM "' + str(row[0]).replace('"', '""') + '"'
            ).fetchone()[0])
            for row in dst.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        return {"path": str(destination), "bytes": destination.stat().st_size,
                "quick_check": quick[0], "foreign_key_violations": 0, "tables": tables}
    finally:
        src.close()
        dst.close()


def requeue_vision_approved_to_stock(
    database: Path, *, project_root: Path, backup_path: Path
) -> dict:
    """Reset downstream processing in a new install while preserving Vision and receipts.

    Only approved, non-duplicate items that advanced beyond Stock are reset.
    The original media path, Vision evidence, publication receipts, captions in
    candidate history, and all event history remain available. Derived output
    references are cleared so the next run starts at Stock and creates a
    workspace only when that approved item is selected.
    """
    database = Path(database).resolve(strict=True)
    root = Path(project_root).resolve(strict=True)
    try:
        database.relative_to(root)
    except ValueError as exc:
        raise ValueError("migration target must be inside the new project root") from exc
    if "armoredcreator-final" in str(database).casefold():
        raise ValueError("refusing to migrate the preserved historical installation")

    connection = sqlite3.connect(database, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("""CREATE TABLE IF NOT EXISTS migration_audit (
            migration_id TEXT PRIMARY KEY,
            applied_at_utc TEXT NOT NULL,
            affected_items INTEGER NOT NULL,
            prior_states_json TEXT NOT NULL,
            backup_file TEXT NOT NULL
        )""")
        prior = connection.execute(
            "SELECT * FROM migration_audit WHERE migration_id=?",
            (STOCK_REQUEUE_MIGRATION,),
        ).fetchone()
        if prior:
            return {"migration_id": STOCK_REQUEUE_MIGRATION, "applied": False,
                    "affected_items": int(prior["affected_items"]),
                    "prior_states": {}, "reason": "already-applied"}

        backup = sqlite_backup(database, backup_path)
        placeholders = ",".join("?" for _ in POST_STOCK_STATES)
        connection.execute("BEGIN IMMEDIATE")
        columns = {str(row[1]) for row in connection.execute('PRAGMA table_info("items")')}
        if not {"content_id", "state", "affiliate_url"}.issubset(columns):
            raise sqlite3.DatabaseError("items schema is missing required migration columns")
        duplicate_filter = " AND (duplicate_of_content_id IS NULL OR TRIM(duplicate_of_content_id)='')" if "duplicate_of_content_id" in columns else ""
        rows = connection.execute(
            f"SELECT content_id,state FROM items WHERE state IN ({placeholders}) "
            "AND affiliate_url IS NOT NULL AND TRIM(affiliate_url)<>''" + duplicate_filter +
            " ORDER BY source_id,CAST(telegram_message_id AS INTEGER),content_id",
            POST_STOCK_STATES,
        ).fetchall()
        prior_states = Counter(str(row["state"]) for row in rows)
        updates = [
            ("state", "RECEIVED"),
            ("working_path", None),
            ("result_path", None),
            ("publication_caption", None),
            ("attempts", 0),
            ("recovery_count", 0),
            ("cleanup_completed", 0),
            ("last_error", None),
        ]
        available_updates = [(name, value) for name, value in updates if name in columns]
        assignments = ",".join(f'"{name}"=?' for name, _ in available_updates)
        if "updated_at" in columns:
            assignments += ",updated_at=CURRENT_TIMESTAMP"
        for row in rows:
            item_id, old_state = str(row["content_id"]), str(row["state"])
            connection.execute(
                f"UPDATE items SET {assignments} WHERE content_id=?",
                tuple(value for _, value in available_updates) + (item_id,),
            )
            if "state_events" in {
                str(r[0]) for r in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }:
                event_columns = {str(r[1]) for r in connection.execute('PRAGMA table_info("state_events")')}
                fields = [name for name in ("content_id", "old_state", "new_state", "reason") if name in event_columns]
                values = {"content_id": item_id, "old_state": old_state, "new_state": "RECEIVED",
                          "reason": f"{STOCK_REQUEUE_MIGRATION}:return-to-stock-preserve-vision"}
                connection.execute(
                    f"INSERT INTO state_events ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
                    tuple(values[name] for name in fields),
                )
        connection.execute(
            "INSERT INTO migration_audit(migration_id,applied_at_utc,affected_items,prior_states_json,backup_file) "
            "VALUES(?,?,?,?,?)",
            (STOCK_REQUEUE_MIGRATION, datetime.now(timezone.utc).isoformat(), len(rows),
             __import__("json").dumps(dict(prior_states), sort_keys=True), str(backup_path)),
        )
        connection.commit()
        quick = [row[0] for row in connection.execute("PRAGMA quick_check")]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if quick != ["ok"] or foreign_keys:
            raise sqlite3.DatabaseError("SQLite migration failed integrity validation")
        return {"migration_id": STOCK_REQUEUE_MIGRATION, "applied": True,
                "affected_items": len(rows), "prior_states": dict(prior_states),
                "backup": backup, "quick_check": quick[0], "foreign_key_violations": 0}
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()
