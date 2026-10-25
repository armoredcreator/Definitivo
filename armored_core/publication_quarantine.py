from __future__ import annotations

import json
import hashlib
import sqlite3
from pathlib import Path
from typing import Any


class PublicationQuarantine:
    """Durable, additive fence for publication outcomes that remain UNKNOWN.

    This ledger never edits the operational publications table and has no
    operation that turns an unknown outcome into absence or confirmation.
    Reconciliation is an explicit, separate workflow.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            conn.executescript(
                "CREATE TABLE IF NOT EXISTS quarantined_publications ("
                " content_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL,"
                " original_status TEXT NOT NULL, original_message_id TEXT,"
                " original_confirmed INTEGER NOT NULL, destination_chat_id TEXT,"
                " destination_topic_id INTEGER, first_observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);"
                "CREATE TABLE IF NOT EXISTS quarantine_evidence ("
                " evidence_id INTEGER PRIMARY KEY AUTOINCREMENT, content_id TEXT NOT NULL,"
                " observed_outcome TEXT NOT NULL CHECK(observed_outcome='UNKNOWN'),"
                " evidence_json TEXT NOT NULL, observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
                " FOREIGN KEY(content_id) REFERENCES quarantined_publications(content_id));"
                "CREATE INDEX IF NOT EXISTS idx_quarantine_evidence_content"
                " ON quarantine_evidence(content_id,evidence_id);"
                "CREATE TABLE IF NOT EXISTS quarantine_resolutions ("
                " resolution_id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " content_id TEXT NOT NULL, resolved_through_evidence_id INTEGER NOT NULL,"
                " decision TEXT NOT NULL CHECK(decision='ABSENT'),"
                " evidence_json TEXT NOT NULL, resolved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
                " FOREIGN KEY(content_id) REFERENCES quarantined_publications(content_id));"
                "CREATE INDEX IF NOT EXISTS idx_quarantine_resolutions_content"
                " ON quarantine_resolutions(content_id,resolved_through_evidence_id);"
            )
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=15, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def contains(self, content_id: str) -> bool:
        conn = self._connect()
        try:
            return conn.execute(
                "SELECT 1 FROM quarantined_publications q "
                "WHERE q.content_id=? AND COALESCE(("
                " SELECT MAX(e.evidence_id) FROM quarantine_evidence e "
                " WHERE e.content_id=q.content_id),0) > COALESCE(("
                " SELECT MAX(r.resolved_through_evidence_id) FROM quarantine_resolutions r "
                " WHERE r.content_id=q.content_id),0)",
                (str(content_id),),
            ).fetchone() is not None
        finally:
            conn.close()

    def quarantined_ids(self) -> set[str]:
        conn = self._connect()
        try:
            return {
                str(row[0])
                for row in conn.execute(
                    "SELECT q.content_id FROM quarantined_publications q "
                    "WHERE COALESCE((SELECT MAX(e.evidence_id) FROM quarantine_evidence e "
                    "WHERE e.content_id=q.content_id),0) > COALESCE(("
                    "SELECT MAX(r.resolved_through_evidence_id) FROM quarantine_resolutions r "
                    "WHERE r.content_id=q.content_id),0)"
                )
            }
        finally:
            conn.close()

    def unresolved_count(self) -> int:
        return len(self.quarantined_ids())

    def observed_outcomes(self) -> set[str]:
        conn = self._connect()
        try:
            return {
                str(row[0])
                for row in conn.execute("SELECT DISTINCT observed_outcome FROM quarantine_evidence")
            }
        finally:
            conn.close()

    def quarantine_unknown(
        self,
        item_id: str,
        publication: Any,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        """Append an UNKNOWN observation while preserving the first receipt snapshot."""
        content_id = str(item_id)
        row = dict(publication)
        status = str(row.get("verification_status") or "UNKNOWN")
        if status == "CONFIRMED":
            raise ValueError("confirmed-publication-cannot-enter-unknown-quarantine")
        key = str(row.get("idempotency_key") or "").strip()
        if not key:
            raise ValueError("quarantine-requires-existing-publication-idempotency-key")
        snapshot = {
            "reason": "telegram-publication-outcome-unknown",
            "item_state": (evidence or {}).get("item_state"),
            "last_state_event": (evidence or {}).get("last_state_event"),
            "publication_check": "UNKNOWN",
            "original_receipt": {
                "idempotency_key": key,
                "verification_status": status,
                "published_message_id": row.get("published_message_id"),
                "confirmed": int(bool(row.get("confirmed"))),
                "destination_chat_id": row.get("destination_chat_id"),
                "destination_topic_id": row.get("destination_topic_id"),
            },
        }
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT OR IGNORE INTO quarantined_publications "
                "(content_id,idempotency_key,original_status,original_message_id,"
                "original_confirmed,destination_chat_id,destination_topic_id) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    content_id, key, status, row.get("published_message_id"),
                    int(bool(row.get("confirmed"))), row.get("destination_chat_id"),
                    row.get("destination_topic_id"),
                ),
            )
            existing = conn.execute(
                "SELECT idempotency_key,original_status,original_message_id,original_confirmed,"
                "destination_chat_id,destination_topic_id FROM quarantined_publications "
                "WHERE content_id=?", (content_id,),
            ).fetchone()
            expected = (
                key, status, row.get("published_message_id"), int(bool(row.get("confirmed"))),
                row.get("destination_chat_id"), row.get("destination_topic_id"),
            )
            active = conn.execute(
                "SELECT COALESCE((SELECT MAX(evidence_id) FROM quarantine_evidence "
                "WHERE content_id=?),0) > COALESCE((SELECT MAX(resolved_through_evidence_id) "
                "FROM quarantine_resolutions WHERE content_id=?),0)",
                (content_id, content_id),
            ).fetchone()[0]
            if active and tuple(existing) != expected:
                raise RuntimeError("quarantined-publication-receipt-snapshot-changed")
            if not active:
                snapshot["new_quarantine_cycle"] = True
            conn.execute(
                "INSERT INTO quarantine_evidence(content_id,observed_outcome,evidence_json) "
                "VALUES(?, 'UNKNOWN', ?)",
                (content_id, json.dumps(snapshot, ensure_ascii=False, sort_keys=True)),
            )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def quarantine_legacy_missing_receipt(
        self, item_id: str, *, evidence: dict[str, Any] | None = None,
    ) -> None:
        """Fence legacy PUBLISHING states that have no durable receipt.

        The generated key is a local quarantine identity only; it is never
        passed to Telegram or represented as an outbound idempotency key.
        """
        content_id = str(item_id)
        key = "legacy-missing-receipt:" + hashlib.sha256(content_id.encode("utf-8")).hexdigest()
        snapshot = {
            "reason": "legacy-publishing-state-without-publication-receipt",
            "item_state": (evidence or {}).get("item_state"),
            "last_state_event": (evidence or {}).get("last_state_event"),
            "publication_check": "UNKNOWN",
            "quarantine_key_kind": "internal-only-not-an-outbound-idempotency-key",
        }
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT OR IGNORE INTO quarantined_publications "
                "(content_id,idempotency_key,original_status,original_message_id,original_confirmed) "
                "VALUES(?,?,?,NULL,0)",
                (content_id, key, "LEGACY_RECEIPT_MISSING"),
            )
            existing = conn.execute(
                "SELECT idempotency_key,original_status,original_message_id,original_confirmed "
                "FROM quarantined_publications WHERE content_id=?", (content_id,),
            ).fetchone()
            active = conn.execute(
                "SELECT COALESCE((SELECT MAX(evidence_id) FROM quarantine_evidence "
                "WHERE content_id=?),0) > COALESCE((SELECT MAX(resolved_through_evidence_id) "
                "FROM quarantine_resolutions WHERE content_id=?),0)",
                (content_id, content_id),
            ).fetchone()[0]
            if active and tuple(existing) != (key, "LEGACY_RECEIPT_MISSING", None, 0):
                raise RuntimeError("legacy-quarantine-snapshot-changed")
            if not active:
                snapshot["new_quarantine_cycle"] = True
            conn.execute(
                "INSERT INTO quarantine_evidence(content_id,observed_outcome,evidence_json) "
                "VALUES(?, 'UNKNOWN', ?)",
                (content_id, json.dumps(snapshot, ensure_ascii=False, sort_keys=True)),
            )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def resolve_absent(self, item_id: str, *, evidence: dict[str, Any]) -> int:
        """Resolve a quarantine only with a complete, topic-scoped live absence record.

        The original quarantine row and all UNKNOWN observations remain immutable.
        A later UNKNOWN observation receives a larger evidence ID and reactivates
        the fence automatically.
        """
        content_id = str(item_id)
        if not isinstance(evidence, dict):
            raise ValueError("absence-reconciliation-requires-structured-evidence")
        if evidence.get("method") != "telegram_topic_history_scan":
            raise ValueError("absence-reconciliation-requires-topic-history-scan")
        if evidence.get("checked_content_id") != content_id:
            raise ValueError("absence-reconciliation-content-id-mismatch")
        if evidence.get("scan_complete") is not True:
            raise ValueError("absence-reconciliation-requires-complete-topic-scan")
        message_ids = evidence.get("scanned_message_ids")
        codes = evidence.get("checked_link_codes")
        matches = evidence.get("matched_message_ids")
        if not isinstance(message_ids, list) or not message_ids:
            raise ValueError("absence-reconciliation-requires-scanned-message-ids")
        if not isinstance(codes, list) or not codes or any(not str(code).strip() for code in codes):
            raise ValueError("absence-reconciliation-requires-all-link-codes")
        if matches != []:
            raise ValueError("absence-reconciliation-found-live-candidate")
        if evidence.get("operator_authorized") is not True:
            raise ValueError("absence-reconciliation-requires-explicit-operator-authorization")
        try:
            chat_id = str(int(evidence.get("chat_id")))
            topic_id = int(evidence.get("topic_id"))
        except (TypeError, ValueError) as exc:
            raise ValueError("absence-reconciliation-invalid-destination") from exc
        if not chat_id.startswith("-100") or topic_id <= 0:
            raise ValueError("absence-reconciliation-invalid-destination")

        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        try:
            quarantine = conn.execute(
                "SELECT original_message_id,destination_chat_id,destination_topic_id "
                "FROM quarantined_publications WHERE content_id=?",
                (content_id,),
            ).fetchone()
            if quarantine is None:
                raise KeyError(content_id)
            if quarantine[1] is not None and str(quarantine[1]) != chat_id:
                raise ValueError("absence-reconciliation-chat-mismatch")
            if quarantine[2] is not None and int(quarantine[2]) != topic_id:
                raise ValueError("absence-reconciliation-topic-mismatch")
            if quarantine[0] is not None:
                if str(evidence.get("exact_receipt_id") or "") != str(quarantine[0]):
                    raise ValueError("absence-reconciliation-receipt-id-mismatch")
                if evidence.get("exact_receipt_status") != "ABSENT":
                    raise ValueError("absence-reconciliation-receipt-not-absent")
            elif evidence.get("exact_receipt_status") not in {"NO_PRIOR_ID", "ABSENT"}:
                raise ValueError("absence-reconciliation-receipt-status-invalid")

            evidence_id = conn.execute(
                "SELECT COALESCE(MAX(evidence_id),0) FROM quarantine_evidence WHERE content_id=?",
                (content_id,),
            ).fetchone()[0]
            if int(evidence_id) <= 0:
                raise RuntimeError("absence-reconciliation-missing-unknown-history")
            previous = conn.execute(
                "SELECT resolution_id,resolved_through_evidence_id FROM quarantine_resolutions "
                "WHERE content_id=? ORDER BY resolution_id DESC LIMIT 1",
                (content_id,),
            ).fetchone()
            if previous is not None and int(previous[1]) >= int(evidence_id):
                conn.commit()
                return int(previous[0])
            conn.execute(
                "INSERT INTO quarantine_resolutions "
                "(content_id,resolved_through_evidence_id,decision,evidence_json) "
                "VALUES(?,?, 'ABSENT', ?)",
                (content_id, int(evidence_id), json.dumps(evidence, ensure_ascii=False, sort_keys=True)),
            )
            resolution_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.commit()
            return resolution_id
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def close(self) -> None:
        # Connections are deliberately short-lived to avoid Windows file locks.
        return None
