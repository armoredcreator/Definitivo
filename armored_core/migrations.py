"""Versioned, copy-first migrations for the operational SQLite store."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import sqlite3
from pathlib import Path


STOCK_REQUEUE_MIGRATION = "20261024_001_requeue_approved_to_stock"
PUBLICATION_STATE_REPAIR_MIGRATION = "20261024_002_restore_publication_fences"
MISSING_RECEIPT_FENCE_MIGRATION = "20261024_003_fence_missing_legacy_receipts"
POST_STOCK_STATES = (
    "IA", "SPEECH", "STUDIO_BATCH", "STUDIO", "STUDIO_COMPLETE",
    "RECOVERY", "FAILED",
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
            "AND affiliate_url IS NOT NULL AND TRIM(affiliate_url)<>'' "
            "AND NOT EXISTS (SELECT 1 FROM publications p WHERE p.content_id=items.content_id)" + duplicate_filter +
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


def restore_publication_fences(
    database: Path, *, project_root: Path, backup_path: Path
) -> dict:
    """Restore terminal receipts and fence ambiguous items changed by migration 001.

    Confirmed receipts return to PUBLISHED. Any persisted but non-confirmed
    receipt returns to RECOVERY so startup reconciliation can place it in the
    durable publication quarantine before production begins. Unpublished
    recovery items return to RECEIVED; interrupted PUBLISHING items without a
    receipt remain in RECOVERY for manual evidence review.
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
            (PUBLICATION_STATE_REPAIR_MIGRATION,),
        ).fetchone()
        if prior:
            return {"migration_id": PUBLICATION_STATE_REPAIR_MIGRATION,
                    "applied": False, "affected_items": int(prior["affected_items"]),
                    "reason": "already-applied"}

        tables = {str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "state_events" not in tables or "publications" not in tables:
            raise sqlite3.DatabaseError("repair requires state_events and publications")
        backup = sqlite_backup(database, backup_path)
        connection.execute("BEGIN IMMEDIATE")
        event_columns = {str(row[1]) for row in connection.execute('PRAGMA table_info("state_events")')}
        item_columns = {str(row[1]) for row in connection.execute('PRAGMA table_info("items")')}
        publication_columns = {str(row[1]) for row in connection.execute('PRAGMA table_info("publications")')}
        if not {"content_id", "state"}.issubset(item_columns):
            raise sqlite3.DatabaseError("items schema is missing required repair columns")
        required_events = {"content_id", "old_state", "new_state", "reason"}
        if not required_events.issubset(event_columns):
            raise sqlite3.DatabaseError("state_events schema cannot prove the prior state")

        rows = connection.execute(
            "SELECT i.content_id,i.state,e.old_state FROM items i "
            "JOIN state_events e ON e.content_id=i.content_id "
            "WHERE i.state='RECEIVED' AND e.new_state='RECEIVED' AND e.reason=? "
            "AND e.old_state IN ('PUBLISHED','PUBLISHING','RECOVERY','FAILED') "
            "ORDER BY i.content_id",
            (f"{STOCK_REQUEUE_MIGRATION}:return-to-stock-preserve-vision",),
        ).fetchall()
        decisions: Counter[str] = Counter()
        table_columns = {str(row[1]) for row in connection.execute('PRAGMA table_info("publications")')}
        pub_fields = [name for name in ("published_message_id", "confirmed", "verification_status") if name in table_columns]
        state_event_columns = {str(row[1]) for row in connection.execute('PRAGMA table_info("state_events")')}
        for row in rows:
            item_id = str(row["content_id"])
            old_state = str(row["old_state"])
            publication = connection.execute(
                "SELECT " + ",".join(pub_fields) + " FROM publications WHERE content_id=?",
                (item_id,),
            ).fetchone()
            if publication is not None:
                message_id = str(publication["published_message_id"] or "").strip() if "published_message_id" in pub_fields else ""
                confirmed = bool(publication["confirmed"]) if "confirmed" in pub_fields else False
                status = str(publication["verification_status"] or "").upper() if "verification_status" in pub_fields else ""
                new_state = "PUBLISHED" if confirmed and message_id and status == "CONFIRMED" else "RECOVERY"
            elif old_state in {"PUBLISHING", "PUBLISHED"}:
                new_state = "RECOVERY"
            else:
                new_state = "RECEIVED"

            if new_state == "RECEIVED":
                continue
            missing_receipt_hold = publication is None and old_state in {"PUBLISHING", "PUBLISHED"}
            if missing_receipt_hold and "last_error" in item_columns:
                connection.execute(
                    "UPDATE items SET state=?,last_error=? WHERE content_id=?",
                    (new_state, "legacy-publication-receipt-missing:manual-reconciliation-required", item_id),
                )
            else:
                connection.execute("UPDATE items SET state=? WHERE content_id=?", (new_state, item_id))
            decisions[new_state] += 1
            values = {"content_id": item_id, "old_state": "RECEIVED", "new_state": new_state,
                      "reason": f"{PUBLICATION_STATE_REPAIR_MIGRATION}:restore-terminal-or-fence-uncertain"}
            fields = [name for name in values if name in state_event_columns]
            connection.execute(
                f"INSERT INTO state_events ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
                tuple(values[name] for name in fields),
            )

        connection.execute(
            "INSERT INTO migration_audit(migration_id,applied_at_utc,affected_items,prior_states_json,backup_file) "
            "VALUES(?,?,?,?,?)",
            (PUBLICATION_STATE_REPAIR_MIGRATION, datetime.now(timezone.utc).isoformat(),
             sum(decisions.values()), __import__("json").dumps(dict(decisions), sort_keys=True), str(backup_path)),
        )
        connection.commit()
        quick = [row[0] for row in connection.execute("PRAGMA quick_check")]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if quick != ["ok"] or foreign_keys:
            raise sqlite3.DatabaseError("publication-state repair failed integrity validation")
        return {"migration_id": PUBLICATION_STATE_REPAIR_MIGRATION, "applied": True,
                "affected_items": sum(decisions.values()), "resulting_states": dict(decisions),
                "backup": backup, "quick_check": quick[0], "foreign_key_violations": 0}
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def fence_missing_legacy_receipts(
    database: Path, *, project_root: Path, backup_path: Path
) -> dict:
    """Quarantine legacy PUBLISHING/PUBLISHED rows that have no receipt record."""
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
            (MISSING_RECEIPT_FENCE_MIGRATION,),
        ).fetchone()
        if prior:
            return {"migration_id": MISSING_RECEIPT_FENCE_MIGRATION,
                    "applied": False, "affected_items": int(prior["affected_items"]),
                    "reason": "already-applied"}
        backup = sqlite_backup(database, backup_path)
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            "SELECT DISTINCT i.content_id,i.state,e.old_state FROM items i "
            "JOIN state_events e ON e.content_id=i.content_id "
            "LEFT JOIN publications p ON p.content_id=i.content_id "
            "WHERE i.state IN ('RECEIVED','RECOVERY') AND e.new_state='RECEIVED' "
            "AND e.reason=? AND e.old_state IN ('PUBLISHING','PUBLISHED') "
            "AND p.content_id IS NULL ORDER BY i.content_id",
            (f"{STOCK_REQUEUE_MIGRATION}:return-to-stock-preserve-vision",),
        ).fetchall()
        state_columns = {str(row[1]) for row in connection.execute('PRAGMA table_info("items")')}
        event_columns = {str(row[1]) for row in connection.execute('PRAGMA table_info("state_events")')}
        for row in rows:
            item_id = str(row["content_id"])
            state = str(row["state"])
            assignments = ["state='RECOVERY'"]
            if "last_error" in state_columns:
                assignments.append("last_error='legacy-publication-receipt-missing:manual-reconciliation-required'")
            if "updated_at" in state_columns:
                assignments.append("updated_at=CURRENT_TIMESTAMP")
            connection.execute(
                f"UPDATE items SET {','.join(assignments)} WHERE content_id=?", (item_id,)
            )
            if state != "RECOVERY":
                values = {"content_id": item_id, "old_state": state, "new_state": "RECOVERY",
                          "reason": f"{MISSING_RECEIPT_FENCE_MIGRATION}:legacy-publication-without-receipt"}
                fields = [name for name in values if name in event_columns]
                connection.execute(
                    f"INSERT INTO state_events ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
                    tuple(values[name] for name in fields),
                )
        connection.execute(
            "INSERT INTO migration_audit(migration_id,applied_at_utc,affected_items,prior_states_json,backup_file) "
            "VALUES(?,?,?,?,?)",
            (MISSING_RECEIPT_FENCE_MIGRATION, datetime.now(timezone.utc).isoformat(), len(rows),
             __import__("json").dumps(dict(Counter(str(row["old_state"]) for row in rows)), sort_keys=True),
             str(backup_path)),
        )
        connection.commit()
        quick = [row[0] for row in connection.execute("PRAGMA quick_check")]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if quick != ["ok"] or foreign_keys:
            raise sqlite3.DatabaseError("missing-receipt fence migration failed integrity validation")
        return {"migration_id": MISSING_RECEIPT_FENCE_MIGRATION, "applied": True,
                "affected_items": len(rows), "backup": backup,
                "quick_check": quick[0], "foreign_key_violations": 0}
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()
