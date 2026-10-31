from __future__ import annotations

"""Release quarantined publications only after a recorded live topic-history absence scan."""

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from armored_core.database import Database
from armored_core.integrity import sha256_file
from armored_core.models import State
from armored_core.publication_quarantine import PublicationQuarantine
from armored_core.routing import CONTRACT_HUB_DESTINATIONS
from armored_core.storage import Storage


def _sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(source), timeout=30) as src, sqlite3.connect(str(destination)) as dst:
        src.backup(dst)
        result = dst.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"backup-quick-check-failed:{destination.name}:{result}")


def _validate_evidence(evidence: dict, item_id: str, expected_destination: tuple[str, int]) -> None:
    if evidence.get("method") != "telegram_topic_history_scan":
        raise ValueError("evidence-method-must-be-telegram-topic-history-scan")
    if evidence.get("checked_content_id") != item_id:
        raise ValueError(f"evidence-content-id-mismatch:{item_id}")
    if evidence.get("scan_complete") is not True:
        raise ValueError(f"evidence-topic-scan-incomplete:{item_id}")
    if evidence.get("matched_message_ids") != []:
        raise ValueError(f"evidence-found-a-publication-candidate:{item_id}")
    if evidence.get("operator_authorized") is not True:
        raise ValueError("evidence-requires-user-authorization")
    if (str(evidence.get("chat_id")), int(evidence.get("topic_id") or 0)) != expected_destination:
        raise ValueError(f"evidence-destination-mismatch:{item_id}")
    message_ids = evidence.get("scanned_message_ids")
    link_codes = evidence.get("checked_link_codes")
    if not isinstance(message_ids, list) or not message_ids:
        raise ValueError(f"evidence-missing-scanned-message-ids:{item_id}")
    if not isinstance(link_codes, list) or not link_codes or any(not str(code).strip() for code in link_codes):
        raise ValueError(f"evidence-missing-link-codes:{item_id}")
    if evidence.get("scanned_message_count") != len(message_ids):
        raise ValueError(f"evidence-scan-count-mismatch:{item_id}")
    receipt_status = evidence.get("exact_receipt_status")
    receipt_id = str(evidence.get("exact_receipt_id") or "").strip()
    if receipt_status not in {"NO_PRIOR_ID", "ABSENT"}:
        raise ValueError(f"evidence-exact-receipt-status-invalid:{item_id}")
    if receipt_status == "ABSENT" and not receipt_id:
        raise ValueError(f"evidence-exact-receipt-id-required:{item_id}")
    if receipt_status == "NO_PRIOR_ID" and receipt_id:
        raise ValueError(f"evidence-exact-receipt-id-conflicts-with-status:{item_id}")


def _backup_pair(root: Path, database: Path, quarantine: Path) -> tuple[Path, Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backups = root / "storage" / "backups"
    db_backup = backups / f"armoredcreator-before-absence-reconciliation-{stamp}.sqlite3"
    quarantine_backup = backups / f"publication-quarantine-before-absence-reconciliation-{stamp}.sqlite3"
    _sqlite_backup(database, db_backup)
    _sqlite_backup(quarantine, quarantine_backup)
    return db_backup, quarantine_backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="apply the audited absence decisions and return eligible items to RECEIVED")
    args = parser.parse_args()
    root = args.root.expanduser().resolve(strict=True)
    evidence_path = args.evidence.expanduser().resolve(strict=True)
    evidence_doc = json.loads(evidence_path.read_text(encoding="utf-8"))
    if evidence_doc.get("method") != "telegram_topic_history_scan" or evidence_doc.get("scan_complete") is not True:
        parser.error("evidence file must contain a complete telegram_topic_history_scan")
    rows = evidence_doc.get("items")
    if not isinstance(rows, list) or not rows:
        parser.error("evidence file must contain a non-empty items list")

    load_dotenv(root / "credentials" / "project.env", override=True)
    database_path = root / "storage" / "database" / "armoredcreator.db"
    quarantine_path = root / "storage" / "database" / "publication-quarantine.sqlite3"
    if not database_path.is_file() or not quarantine_path.is_file():
        parser.error("operational database or publication quarantine is missing")

    db = Database(database_path)
    quarantine = PublicationQuarantine(quarantine_path)
    lock_acquired = False
    try:
        db.acquire_runtime_lock("coordinator")
        lock_acquired = True
        prepared = []
        for record in rows:
            item_id = str(record.get("checked_content_id") or "")
            if not item_id:
                raise ValueError("evidence-item-missing-content-id")
            item = db.get(item_id)
            if item.state != State.RECOVERY:
                raise RuntimeError(f"item-not-in-recovery:{item_id}:{item.state.value}")
            if not item.affiliate_url or not item.affiliate_name:
                raise RuntimeError(f"item-lacks-persisted-vision-approval:{item_id}")
            if not item.original_path.is_file() or not item.original_sha256:
                raise RuntimeError(f"item-original-missing-or-unverified:{item_id}")
            if sha256_file(item.original_path).lower() != item.original_sha256.lower():
                raise RuntimeError(f"item-original-hash-mismatch:{item_id}")
            expected_destination = CONTRACT_HUB_DESTINATIONS.get(str(item.source_id))
            if expected_destination is None:
                raise RuntimeError(f"item-source-not-in-route-contract:{item_id}")
            _validate_evidence(record, item_id, expected_destination)
            if not quarantine.contains(item_id):
                raise RuntimeError(f"item-not-currently-quarantined:{item_id}")
            prepared.append((item_id, record, item))

        if not args.apply:
            print(json.dumps({
                "mode": "DRY_RUN",
                "items": [
                    {"content_id": item_id, "state": item.state.value, "topic_id": record["topic_id"], "original_sha256": item.original_sha256}
                    for item_id, record, item in prepared
                ],
                "no_state_changed": True,
            }, ensure_ascii=False, indent=2))
            return 0

        db_backup, quarantine_backup = _backup_pair(root, database_path, quarantine_path)
        outcomes = []
        for item_id, record, _item in prepared:
            resolution_id = quarantine.resolve_absent(item_id, evidence=record)
            generation_key = db.archive_publication_after_absence_reconciliation(
                item_id,
                resolution_id=resolution_id,
                evidence=record,
            )
            current = db.get(item_id)
            if current.state == State.RECOVERY:
                durable_result = (
                    current.result_path is not None
                    and current.result_path.is_file()
                    and db.has_speech_studio_v5_completion(item_id)
                )
                target = State.RECOVERY if durable_result else State.RECEIVED
                reason = (
                    f"telegram-topic-absence-reconciled:{resolution_id}:resume-durable-v5-result"
                    if durable_result
                    else f"telegram-topic-absence-reconciled:{resolution_id}:return-to-stock"
                )
                db.transition(item_id, target, reason)
            outcomes.append({
                "content_id": item_id,
                "resolution_id": resolution_id,
                "new_idempotency_key": generation_key,
                "state": db.get(item_id).state.value,
                "quarantined": quarantine.contains(item_id),
            })

        report = {
            "applied_at_utc": datetime.now(timezone.utc).isoformat(),
            "evidence_file": str(evidence_path),
            "scan_message_ids": evidence_doc.get("scanned_message_ids") or [
                message_id
                for record in rows
                for message_id in (record.get("scanned_message_ids") or [])
            ],
            "backup_database": str(db_backup),
            "backup_quarantine": str(quarantine_backup),
            "outcomes": outcomes,
        }
        report_path = root / "storage" / "validation" / "publication-absence-reconciliation.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        if lock_acquired:
            db.release_runtime_lock("coordinator")
        quarantine.close()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
