from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from armored_core.migrations import fence_missing_legacy_receipts, restore_publication_fences
from armored_core.publication_quarantine import PublicationQuarantine


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    database = root / "storage" / "database" / "armoredcreator.db"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = root / "storage" / "backups" / f"armoredcreator-before-publication-repair-{stamp}.sqlite3"
    result = restore_publication_fences(database, project_root=root, backup_path=backup)
    missing_receipt_backup = root / "storage" / "backups" / f"armoredcreator-before-missing-receipt-fence-{stamp}.sqlite3"
    missing_receipt_result = fence_missing_legacy_receipts(
        database, project_root=root, backup_path=missing_receipt_backup,
    )
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    quarantine = PublicationQuarantine(root / "storage" / "database" / "publication-quarantine.sqlite3")
    quarantined_receipts = 0
    quarantined_missing = 0
    try:
        for row in connection.execute(
            "SELECT p.* FROM publications p WHERE upper(coalesce(p.verification_status,'')) "
            "IN ('PENDING','SENT_UNVERIFIED','UNKNOWN','SENDING') ORDER BY p.content_id"
        ):
            item_id = str(row["content_id"])
            if not quarantine.contains(item_id):
                quarantine.quarantine_unknown(item_id, row, evidence={"reason": "versioned-publication-state-repair"})
                quarantined_receipts += 1
        for row in connection.execute(
            "SELECT content_id,last_error,state FROM items WHERE state='RECOVERY' "
            "AND last_error LIKE 'legacy-publication-receipt-missing:%' ORDER BY content_id"
        ):
            item_id = str(row["content_id"])
            if not quarantine.contains(item_id):
                quarantine.quarantine_legacy_missing_receipt(
                    item_id, evidence={"item_state": str(row["state"]), "reason": str(row["last_error"])}
                )
                quarantined_missing += 1
    finally:
        connection.close()
    quarantine.close()
    result["quarantine_seed"] = {
        "receipt_uncertain_items": quarantined_receipts,
        "missing_receipt_items": quarantined_missing,
        "total_fenced_items": quarantine.unresolved_count(),
    }
    result["missing_receipt_migration"] = missing_receipt_result
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        audit_rows = connection.execute(
            "SELECT migration_id,applied_at_utc,affected_items,prior_states_json,backup_file "
            "FROM migration_audit WHERE migration_id IN (?,?) ORDER BY migration_id",
            ("20261024_002_restore_publication_fences", "20261024_003_fence_missing_legacy_receipts"),
        ).fetchall()
    finally:
        connection.close()
    result["migration_history"] = [
        {
            **dict(row),
            "state_counts": json.loads(row["prior_states_json"] or "{}"),
            "backup_exists": Path(row["backup_file"]).is_file(),
        }
        for row in audit_rows
    ]
    result["effective_applied"] = {
        row["migration_id"]: bool(row["backup_exists"])
        for row in result["migration_history"]
    }
    validation = root / "storage" / "validation"
    validation.mkdir(parents=True, exist_ok=True)
    report = validation / "publication-state-repair.json"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
