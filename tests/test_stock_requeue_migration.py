import sqlite3
from pathlib import Path

from armored_core.migrations import (
    fence_missing_legacy_receipts,
    requeue_vision_approved_to_stock,
    restore_publication_fences,
)


def _database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE items (
            content_id TEXT PRIMARY KEY, source_id TEXT, telegram_message_id TEXT,
            state TEXT NOT NULL, affiliate_url TEXT, original_path TEXT,
            original_sha256 TEXT, working_path TEXT, result_path TEXT,
            publication_caption TEXT, attempts INTEGER DEFAULT 0,
            recovery_count INTEGER DEFAULT 0, cleanup_completed INTEGER DEFAULT 0,
            last_error TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            duplicate_of_content_id TEXT
        );
        CREATE TABLE publications (
            content_id TEXT PRIMARY KEY, idempotency_key TEXT,
            published_message_id TEXT, confirmed INTEGER DEFAULT 0,
            verification_status TEXT, destination_chat_id TEXT,
            destination_topic_id INTEGER, verified_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE state_events (
            event_id INTEGER PRIMARY KEY, content_id TEXT,
            old_state TEXT, new_state TEXT, reason TEXT
        );
        INSERT INTO items VALUES
          ('s1_1','s1','1','PUBLISHED','https://aff/1','old/1.mp4','sha1','work','render','caption',3,2,1,'',CURRENT_TIMESTAMP,NULL),
          ('s2_2','s2','2','RECOVERY','https://aff/2','old/2.mp4','sha2','work2','render2','caption2',1,1,0,'unknown',CURRENT_TIMESTAMP,NULL),
          ('s3_3','s3','3','WAITING_VISION',NULL,'old/3.mp4',NULL,NULL,NULL,NULL,0,0,0,NULL,CURRENT_TIMESTAMP,NULL),
          ('s4_4','s4','4','DUPLICATE','https://aff/4','old/4.mp4',NULL,NULL,NULL,NULL,0,0,0,NULL,CURRENT_TIMESTAMP,'s1_1');
        INSERT INTO publications VALUES ('s1_1','key-1','publication-1',1,'CONFIRMED','chat',1,NULL,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
    """)
    connection.commit()
    connection.close()


def test_requeue_post_stock_approved_only_and_preserve_publication_history(tmp_path):
    root = tmp_path / "Definitivo"
    root.mkdir()
    database = root / "storage" / "database" / "armoredcreator.db"
    database.parent.mkdir(parents=True)
    _database(database)
    result = requeue_vision_approved_to_stock(
        database, project_root=root,
        backup_path=root / "storage" / "backups" / "before-requeue.db",
    )
    assert result["applied"] is True
    assert result["affected_items"] == 1
    connection = sqlite3.connect(database)
    assert connection.execute("SELECT state FROM items WHERE content_id='s1_1'").fetchone()[0] == "PUBLISHED"
    assert connection.execute("SELECT state FROM items WHERE content_id='s2_2'").fetchone()[0] == "RECEIVED"
    assert connection.execute("SELECT state FROM items WHERE content_id='s3_3'").fetchone()[0] == "WAITING_VISION"
    assert connection.execute("SELECT state FROM items WHERE content_id='s4_4'").fetchone()[0] == "DUPLICATE"
    assert connection.execute("SELECT original_path,original_sha256,affiliate_url FROM items WHERE content_id='s1_1'").fetchone() == ("old/1.mp4", "sha1", "https://aff/1")
    assert connection.execute("SELECT count(*) FROM publications").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM state_events WHERE new_state='RECEIVED'").fetchone()[0] == 1
    assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    connection.close()

    rerun = requeue_vision_approved_to_stock(
        database, project_root=root, backup_path=root / "storage" / "backups" / "unused.db"
    )
    assert rerun["applied"] is False
    assert not (root / "storage" / "backups" / "unused.db").exists()


def test_repair_restores_confirmed_publication_and_fences_unknown_receipts(tmp_path):
    root = tmp_path / "Definitivo"
    root.mkdir()
    database = root / "storage" / "database" / "armoredcreator.db"
    database.parent.mkdir(parents=True)
    _database(database)
    connection = sqlite3.connect(database)
    connection.executescript("""
      CREATE TABLE migration_audit (
        migration_id TEXT PRIMARY KEY, applied_at_utc TEXT NOT NULL,
        affected_items INTEGER NOT NULL, prior_states_json TEXT NOT NULL,
        backup_file TEXT NOT NULL
      );
      INSERT INTO migration_audit VALUES
        ('20261024_001_requeue_approved_to_stock','now',2,'{}','before.db');
      UPDATE items SET state='RECEIVED',working_path=NULL,result_path=NULL,
        publication_caption=NULL,attempts=0,recovery_count=0,cleanup_completed=0,
        last_error=NULL WHERE content_id IN ('s1_1','s2_2');
      INSERT INTO state_events VALUES
        (1,'s1_1','PUBLISHED','RECEIVED','20261024_001_requeue_approved_to_stock:return-to-stock-preserve-vision'),
        (2,'s2_2','RECOVERY','RECEIVED','20261024_001_requeue_approved_to_stock:return-to-stock-preserve-vision');
      UPDATE publications SET verification_status='CONFIRMED' WHERE content_id='s1_1';
      INSERT INTO publications VALUES ('uncertain','unknown-key',NULL,0,'PENDING','chat',12,NULL,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
      INSERT INTO items VALUES
        ('uncertain','s3','3','RECEIVED','https://aff/3',NULL,NULL,NULL,NULL,NULL,0,0,0,NULL,CURRENT_TIMESTAMP,NULL);
      INSERT INTO items VALUES
        ('legacy_no_receipt','s3','4','RECEIVED','https://aff/4',NULL,NULL,NULL,NULL,NULL,0,0,0,NULL,CURRENT_TIMESTAMP,NULL);
      INSERT INTO state_events VALUES
        (3,'uncertain','PUBLISHING','RECEIVED','20261024_001_requeue_approved_to_stock:return-to-stock-preserve-vision'),
        (4,'legacy_no_receipt','PUBLISHING','RECEIVED','20261024_001_requeue_approved_to_stock:return-to-stock-preserve-vision');
    """)
    connection.commit()
    connection.close()

    result = restore_publication_fences(
        database, project_root=root,
        backup_path=root / "storage" / "backups" / "before-repair.db",
    )
    assert result["applied"] is True
    connection = sqlite3.connect(database)
    states = dict(connection.execute(
        "SELECT content_id,state FROM items WHERE content_id IN ('s1_1','s2_2','uncertain','legacy_no_receipt')"
    ))
    assert states == {"s1_1": "PUBLISHED", "s2_2": "RECEIVED", "uncertain": "RECOVERY", "legacy_no_receipt": "RECOVERY"}
    assert connection.execute(
        "SELECT last_error FROM items WHERE content_id='uncertain'"
    ).fetchone()[0] is None
    assert connection.execute(
        "SELECT last_error FROM items WHERE content_id='legacy_no_receipt'"
    ).fetchone()[0].startswith("legacy-publication-receipt-missing:")
    assert connection.execute("SELECT count(*) FROM publications").fetchone()[0] == 2
    assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    connection.close()

    legacy_result = fence_missing_legacy_receipts(
        database, project_root=root,
        backup_path=root / "storage" / "backups" / "before-missing-receipt-fence.db",
    )
    assert legacy_result["applied"] is True
    assert legacy_result["affected_items"] == 1
    rerun_legacy = fence_missing_legacy_receipts(
        database, project_root=root,
        backup_path=root / "storage" / "backups" / "unused-missing-receipt-fence.db",
    )
    assert rerun_legacy["applied"] is False
    assert not (root / "storage" / "backups" / "unused-missing-receipt-fence.db").exists()
