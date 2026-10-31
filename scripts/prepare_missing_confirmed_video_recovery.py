from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from ArmoredHub.service import ArmoredHub  # noqa: E402
from ArmoredStock.service import ArmoredStock  # noqa: E402
from armored_core.database import Database  # noqa: E402
from armored_core.integrity import sha256_file  # noqa: E402
from armored_core.models import State  # noqa: E402
from armored_core.publication_quarantine import PublicationQuarantine  # noqa: E402
from armored_core.routing import CONTRACT_HUB_DESTINATIONS  # noqa: E402
from armored_core.storage import Storage  # noqa: E402


URL_RE = re.compile(r"https?://[^\s<>\[\](){}]+", re.IGNORECASE)


def _codes_for(item) -> list[str]:
    codes: list[str] = []
    for raw in (*tuple(item.affiliate_urls or ()), item.affiliate_url, item.original_url):
        value = str(raw or "").strip()
        if not value:
            continue
        path = unquote(urlparse(value).path or "").rstrip("/")
        code = path.rsplit("/", 1)[-1].strip()
        if len(code) >= 4 and code not in codes:
            codes.append(code)
    return codes


def _message_links(message) -> tuple[str, ...]:
    text = str(getattr(message, "message", "") or "")
    links = [match.group(0).rstrip(".,;!?") for match in URL_RE.finditer(text)]
    for entity in getattr(message, "entities", None) or ():
        linked = str(getattr(entity, "url", "") or "").strip()
        if linked:
            links.append(linked)
    return tuple(dict.fromkeys(link for link in links if link))


async def _scan_topic_history(targets: list[dict[str, Any]], hub: ArmoredHub) -> dict[str, dict[str, Any]]:
    api_id = (os.getenv("TELEGRAM_API_ID") or "").strip()
    api_hash = (os.getenv("TELEGRAM_API_HASH") or "").strip()
    if not api_id or not api_hash:
        raise RuntimeError("Telegram user-session configuration is missing")
    from telethon import TelegramClient

    session_name = (os.getenv("ARMORED_TELEGRAM_SESSION_NAME") or "armoredsync").strip()
    if not session_name or Path(session_name).name != session_name:
        raise RuntimeError("Configured Telegram session name is invalid")
    client = TelegramClient(
        str(ROOT / "credentials" / "telegram" / "session" / session_name),
        int(api_id), api_hash, request_retries=0, connection_retries=0,
    )
    by_topic: dict[int, list[dict[str, Any]]] = {}
    for target in targets:
        by_topic.setdefault(int(target["topic_id"]), []).append(target)
    evidence: dict[str, dict[str, Any]] = {}
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError("Telegram verification session is not authorized")
        entity = await client.get_entity(int(targets[0]["chat_id"]))
        for topic_id, topic_targets in by_topic.items():
            scanned_ids: list[str] = []
            scanned_links: dict[str, set[str]] = {}
            scan_started = datetime.now(timezone.utc).isoformat()
            async for message in client.iter_messages(entity, reply_to=topic_id, limit=None):
                if str(getattr(message, "chat_id", "")) != str(topic_targets[0]["chat_id"]):
                    raise RuntimeError(f"Topic scan returned an unexpected chat: {topic_id}")
                current_topic = hub._topic_id(message)
                if current_topic is not None and int(current_topic) != topic_id:
                    raise RuntimeError(f"Topic scan crossed a thread boundary: {topic_id}")
                message_id = str(getattr(message, "id", ""))
                if not message_id:
                    raise RuntimeError(f"Topic scan returned a message without an id: {topic_id}")
                scanned_ids.append(message_id)
                for link in _message_links(message):
                    parsed = urlparse(link)
                    code = unquote(parsed.path or "").rstrip("/").rsplit("/", 1)[-1].strip()
                    if len(code) >= 4:
                        scanned_links.setdefault(code.casefold(), set()).add(message_id)
            scan_finished = datetime.now(timezone.utc).isoformat()
            if not scanned_ids:
                raise RuntimeError(f"Topic scan was empty; completeness cannot be proven: {topic_id}")
            for target in topic_targets:
                item = target["item"]
                checked_codes = _codes_for(item)
                if not checked_codes:
                    raise RuntimeError(f"No Shopee link codes available for absence check: {item.content_id}")
                matches = set()
                for code in checked_codes:
                    matches.update(scanned_links.get(code.casefold(), set()))
                if target["message_id"] in scanned_ids:
                    matches.add(target["message_id"])
                evidence[target["content_id"]] = {
                    "method": "telegram_topic_history_scan",
                    "checked_content_id": target["content_id"],
                    "source_id": str(item.source_id),
                    "chat_id": target["chat_id"],
                    "topic_id": topic_id,
                    "scan_complete": True,
                    "scan_started_at_utc": scan_started,
                    "scan_finished_at_utc": scan_finished,
                    "scanned_message_ids": scanned_ids,
                    "scanned_message_count": len(scanned_ids),
                    "checked_link_codes": checked_codes,
                    "matched_message_ids": sorted(matches, key=lambda value: int(value)),
                    "exact_receipt_id": target["message_id"],
                    "exact_receipt_status": "ABSENT" if not matches else "PRESENT",
                    "operator_authorized": True,
                }
    finally:
        if client.is_connected():
            await client.disconnect()
    return evidence


def _backup_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(source), timeout=30) as src, sqlite3.connect(str(destination)) as dst:
        src.backup(dst)
        if dst.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError(f"SQLite backup failed integrity check: {destination.name}")
        if dst.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError(f"SQLite backup failed foreign-key check: {destination.name}")


def _report_path(batch_id: str) -> Path:
    return ROOT / "storage" / "validation" / f"{batch_id}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit missing confirmed Telegram posts and stage their video recovery"
    )
    parser.add_argument("--batch-id", default="published-caption-refresh-20261027-qwen25-3b")
    parser.add_argument("--apply", action="store_true", help="archive only fully proven absent receipts and stage videos for START_ALL")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", args.batch_id):
        parser.error("invalid --batch-id")
    load_dotenv(ROOT / "credentials" / "project.env", override=True)
    report_path = _report_path(args.batch_id)
    if not report_path.is_file():
        parser.error("caption-generation report is missing")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (
        report.get("batch_id") != args.batch_id
        or report.get("products") != 45
        or len(report.get("results", [])) != 45
    ):
        parser.error("caption report does not match the expected 45-item batch")

    storage = Storage(ROOT)
    database_path = storage.database / "armoredcreator.db"
    quarantine_path = storage.database / "publication-quarantine.sqlite3"
    db = Database(database_path, initialize=False)
    quarantine = PublicationQuarantine(quarantine_path)
    lock_held = False
    try:
        db.acquire_runtime_lock("coordinator")
        lock_held = True
        results = {str(row["content_id"]): row for row in report.get("results", [])}
        targets: list[dict[str, Any]] = []
        for content_id, result in results.items():
            if bool(result.get("telegram_message_available")):
                continue
            if result.get("status") == "GENERATION_FAILED":
                raise RuntimeError(f"Caption generation is incomplete for {content_id}")
            item = db.get(content_id)
            receipt = db.publication(content_id)
            if receipt is None:
                raise RuntimeError(f"Publication receipt is missing: {content_id}")
            reconciled = db.is_reconciled_publication_generation(content_id)
            old_message_id = str(result["published_message_id"])
            if reconciled:
                old_receipt = db.conn.execute(
                    "SELECT * FROM publication_receipt_history WHERE content_id=? "
                    "AND published_message_id=? ORDER BY resolution_id DESC LIMIT 1",
                    (content_id, old_message_id),
                ).fetchone()
                if (
                    old_receipt is None
                    or not bool(old_receipt["confirmed"])
                    or str(old_receipt["verification_status"] or "").upper() != "CONFIRMED"
                    or item.state not in {State.PUBLISHED, State.RECOVERY, State.SPEECH}
                ):
                    raise RuntimeError(f"Reconciled receipt history is inconsistent: {content_id}")
                receipt_for_history = dict(old_receipt)
            else:
                if item.state is not State.PUBLISHED:
                    raise RuntimeError(f"Item is not an active PUBLISHED receipt: {content_id}")
                if (
                    not bool(receipt["confirmed"])
                    or str(receipt["verification_status"] or "").upper() != "CONFIRMED"
                    or str(receipt["published_message_id"] or "") != old_message_id
                ):
                    raise RuntimeError(f"Confirmed receipt changed after caption generation: {content_id}")
                receipt_for_history = dict(receipt)
            route = CONTRACT_HUB_DESTINATIONS.get(str(item.source_id))
            actual = (str(receipt["destination_chat_id"] or ""), int(receipt["destination_topic_id"] or 0))
            if route != actual or actual != (str(result["destination_chat_id"]), int(result["destination_topic_id"])):
                raise RuntimeError(f"Unexpected receipt route: {content_id}")
            caption = str(result.get("selected_caption") or "").strip()
            if not caption:
                raise RuntimeError(f"Selected caption is missing: {content_id}")
            hub = ArmoredHub(ROOT, db=db)
            hub._validated_caption(item, caption)
            if not item.original_path.is_file() or not item.original_sha256:
                raise RuntimeError(f"Verified ORIGINAL is unavailable: {content_id}")
            if sha256_file(item.original_path).lower() != item.original_sha256.lower():
                raise RuntimeError(f"Verified ORIGINAL hash mismatch: {content_id}")
            if not item.affiliate_url or not item.affiliate_name or not item.ia_context:
                raise RuntimeError(f"Persisted Vision approval is incomplete: {content_id}")
            targets.append({
                "content_id": content_id,
                "item": item,
                "message_id": str(receipt["published_message_id"]),
                "chat_id": actual[0],
                "topic_id": actual[1],
                "caption": caption,
                "receipt": receipt_for_history,
                "already_reconciled": reconciled,
            })
        if not targets:
            print("MISSING_CONFIRMED_POSTS=0")
            return 0

        evidence_by_id = asyncio.run(_scan_topic_history(targets, ArmoredHub(ROOT, db=db)))
        blocked = [
            content_id for content_id, evidence in evidence_by_id.items()
            if evidence["matched_message_ids"]
        ]
        plan = []
        for target in targets:
            evidence = evidence_by_id[target["content_id"]]
            plan.append({
                "content_id": target["content_id"],
                "old_message_id": target["message_id"],
                "route": {"chat_id": target["chat_id"], "topic_id": target["topic_id"]},
                "caption": target["caption"],
                "absence_proven": not evidence["matched_message_ids"],
                "matched_message_ids": evidence["matched_message_ids"],
                "original_sha256": target["item"].original_sha256,
            })
        if not args.apply:
            print(json.dumps({
                "mode": "DRY_RUN",
                "missing_confirmed_posts": len(targets),
                "absence_proven": len(targets) - len(blocked),
                "link_match_found": len(blocked),
                "plan": plan,
            }, ensure_ascii=True, indent=2))
            return 0
        if blocked:
            raise RuntimeError(
                "Topic scan found a matching affiliate link; refusing to create duplicate posts for: "
                + ",".join(blocked)
            )

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backups = ROOT / "storage" / "backups"
        database_backup = backups / f"armoredcreator-before-video-recovery-{stamp}.sqlite3"
        quarantine_backup = backups / f"publication-quarantine-before-video-recovery-{stamp}.sqlite3"
        _backup_sqlite(database_path, database_backup)
        _backup_sqlite(quarantine_path, quarantine_backup)
        stock = ArmoredStock(type("StockCoordinator", (), {"storage": storage, "db": db})())
        recovered = list(
            (report.get("missing_post_recovery") or {}).get("items") or []
        )
        recovered_ids = {str(row.get("content_id")) for row in recovered}
        report["missing_post_recovery"] = {
            "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
            "verified_topic_scans": len(evidence_by_id),
            "backups": [str(database_backup.relative_to(ROOT)), str(quarantine_backup.relative_to(ROOT))],
            "items": recovered,
            "topic_scan_evidence": evidence_by_id,
            "next_step": "START_ALL resumes each item at SPEECH, then Studio and Hub; original receipts remain in publication_receipt_history.",
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for target in targets:
            content_id = target["content_id"]
            item = db.get(content_id)
            evidence = evidence_by_id[content_id]
            if target["already_reconciled"]:
                archived = db.conn.execute(
                    "SELECT resolution_id FROM publication_receipt_history WHERE content_id=? "
                    "AND published_message_id=? ORDER BY resolution_id DESC LIMIT 1",
                    (content_id, target["message_id"]),
                ).fetchone()
                if archived is None:
                    raise RuntimeError(f"Archived receipt is unavailable: {content_id}")
                resolution_id = int(archived["resolution_id"])
                generation_key = str(db.publication(content_id)["idempotency_key"])
            else:
                quarantine.quarantine_confirmed_message_missing(
                    content_id,
                    target["receipt"],
                    evidence={
                        "item_state": item.state.value,
                        "exact_receipt_id": target["message_id"],
                        "exact_message_fetch": "NOT_FOUND",
                        "complete_topic_scan_required": True,
                    },
                )
                resolution_id = quarantine.resolve_absent(content_id, evidence=evidence)
                generation_key = db.archive_publication_after_absence_reconciliation(
                    content_id, resolution_id=resolution_id, evidence=evidence,
                )
            if not generation_key:
                raise RuntimeError(f"Could not open reconciled receipt generation: {content_id}")
            if item.state is State.PUBLISHED:
                db.transition(
                    content_id, State.RECOVERY,
                    f"confirmed-message-absent:{resolution_id}:operator-authorized-video-recovery",
                )
            item = db.get(content_id)
            relocated = stock.relocate_trusted_legacy_original(item)
            if relocated is None and not item.original_path.is_relative_to(storage.storage_root.resolve()):
                raise RuntimeError(f"Original could not be relocated into canonical storage: {content_id}")
            db.set_caption(content_id, target["caption"])
            current = db.get(content_id)
            if current.state is not State.SPEECH:
                db.transition(
                    content_id, State.SPEECH,
                    f"caption-approved-video-rebuild-ready:{resolution_id}:speech-studio-hub",
                )
            record = {
                "content_id": content_id,
                "old_message_id": target["message_id"],
                "new_generation_key": generation_key,
                "resolution_id": resolution_id,
                "state_ready_for_start": db.get(content_id).state.value,
                "canonical_original": str(db.get(content_id).original_path),
                "original_hash_verified": True,
                "new_caption": target["caption"],
            }
            if content_id in recovered_ids:
                recovered = [row for row in recovered if str(row.get("content_id")) != content_id]
            recovered.append(record)
            recovered_ids.add(content_id)
            report["missing_post_recovery"]["items"] = recovered
            report["missing_post_recovery"]["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"VIDEO_RECOVERY_STAGED={len(recovered)}")
        print("STATES=" + json.dumps(sorted({r["state_ready_for_start"] for r in recovered})))
        print(f"REPORT={report_path}")
        print(f"DATABASE_BACKUP={database_backup}")
        print(f"QUARANTINE_BACKUP={quarantine_backup}")
        return 0
    finally:
        if lock_held:
            try:
                db.release_runtime_lock("coordinator")
            except Exception:
                pass
        quarantine.close()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
