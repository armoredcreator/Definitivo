from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ArmoredHub.service import ArmoredHub  # noqa: E402
from ArmoredIA.service import ArmoredIA  # noqa: E402
from armored_core.database import Database  # noqa: E402
from armored_core.models import State  # noqa: E402
from armored_core.storage import Storage  # noqa: E402


EXPECTED_ROUTES = {
    "-1003788989075": ("-1004341972306", 228),
    "-1002698134896": ("-1004341972306", 1160),
    "-1002039708059": ("-1004341972306", 1327),
}
CAPTION_ENGINE = "vision-title-rules-local"
URL_RE = re.compile(r"https?://[^\s<>\[\](){}]+", re.IGNORECASE)


def _configure_local_caption_run() -> None:
    load_dotenv(ROOT / "credentials" / "project.env", override=True)
    # Published-message refresh uses the same deterministic, Vision-grounded
    # title rules as the reviewed full-catalog replay. Never start Ollama here.
    os.environ["ARMORED_IA_CAPTION_ENABLED"] = "1"
    os.environ["ARMORED_IA_CAPTION_TITLE_RULES"] = "1"


def _backup_database(db: Database) -> Path:
    backup_dir = ROOT / "storage" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = backup_dir / f"armoredcreator-before-caption-refresh-{stamp}.sqlite3"
    target = sqlite3.connect(destination)
    try:
        db.conn.backup(target)
        check = target.execute("PRAGMA quick_check").fetchone()[0]
        fk = target.execute("PRAGMA foreign_key_check").fetchall()
        if check != "ok" or fk:
            raise RuntimeError("pre-caption-refresh SQLite backup failed integrity checks")
    finally:
        target.close()
    return destination


def _load_targets(db: Database) -> list[dict[str, Any]]:
    rows = db.conn.execute(
        "SELECT i.content_id,i.source_id,i.state,p.published_message_id,"
        "p.destination_chat_id,p.destination_topic_id,p.confirmed,p.verification_status "
        "FROM items i JOIN publications p USING(content_id) "
        "WHERE i.state='PUBLISHED' ORDER BY i.source_id,CAST(i.telegram_message_id AS INTEGER)"
    ).fetchall()
    targets: list[dict[str, Any]] = []
    for row in rows:
        content_id = str(row["content_id"])
        item = db.get(content_id)
        if (
            item.state is not State.PUBLISHED
            or not bool(row["confirmed"])
            or str(row["verification_status"] or "").upper() != "CONFIRMED"
            or not str(row["published_message_id"] or "").strip()
        ):
            raise RuntimeError(f"published item lacks a confirmed receipt: {content_id}")
        route = EXPECTED_ROUTES.get(str(item.source_id))
        actual = (
            str(row["destination_chat_id"] or ""),
            int(row["destination_topic_id"] or 0),
        )
        if route is None or actual != route:
            raise RuntimeError(f"published receipt has an unexpected route: {content_id}")
        if not item.affiliate_name or not item.affiliate_url or not item.ia_context:
            raise RuntimeError(f"Vision evidence or affiliate link is missing: {content_id}")
        targets.append({
            "content_id": content_id,
            "item": item,
            "message_id": str(row["published_message_id"]),
            "chat_id": actual[0],
            "topic_id": actual[1],
        })
    if not targets:
        raise RuntimeError("no confirmed published caption targets found")
    return targets


def _message_links(message) -> tuple[str, ...]:
    text = str(getattr(message, "message", "") or "")
    values = [match.group(0).rstrip(".,;!?") for match in URL_RE.finditer(text)]
    for entity in getattr(message, "entities", None) or ():
        linked = str(getattr(entity, "url", "") or "").strip()
        if linked:
            values.append(linked)
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return tuple(result)


def _caption_without_links(caption: str) -> str:
    value = URL_RE.sub(" ", str(caption or ""))
    return " ".join(value.split()).strip()


async def _read_remote_messages(targets: list[dict[str, Any]], hub: ArmoredHub) -> dict[str, dict[str, Any]]:
    api_id = (os.getenv("TELEGRAM_API_ID") or "").strip()
    api_hash = (os.getenv("TELEGRAM_API_HASH") or "").strip()
    if not api_id or not api_hash:
        raise RuntimeError("Telegram user session configuration is missing")
    try:
        from telethon import TelegramClient
    except ImportError as exc:
        raise RuntimeError("Telethon is required to verify existing Telegram posts") from exc

    session = ROOT / "credentials" / "telegram" / "session"
    session.mkdir(parents=True, exist_ok=True)
    session_name = (os.getenv("ARMORED_TELEGRAM_SESSION_NAME") or "armoredsync").strip()
    if not session_name or Path(session_name).name != session_name:
        raise RuntimeError("Configured Telegram session name is invalid")
    session_path = session / session_name
    client = TelegramClient(
        str(session_path), int(api_id), api_hash,
        request_retries=0, connection_retries=0,
    )
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError("Telegram verification session is not authorized")
        entity = await client.get_entity(int(targets[0]["chat_id"]))
        ids = [int(target["message_id"]) for target in targets]
        messages = await client.get_messages(entity, ids=ids)
        by_id = {
            str(getattr(message, "id", "")): message
            for message in (messages if isinstance(messages, (list, tuple)) else [messages])
            if message is not None
        }
        snapshots: dict[str, dict[str, Any]] = {}
        for target in targets:
            message = by_id.get(target["message_id"])
            if message is None:
                snapshots[target["content_id"]] = {
                    "available": False,
                    "message_id": target["message_id"],
                    "chat_id": target["chat_id"],
                    "topic_id": target["topic_id"],
                    "has_video": False,
                    "caption": "",
                    "links": [],
                }
                continue
            if str(getattr(message, "chat_id", "")) != target["chat_id"]:
                raise RuntimeError(f"Telegram chat mismatch: {target['content_id']}")
            topic_id = hub._topic_id(message)
            if topic_id != target["topic_id"]:
                raise RuntimeError(f"Telegram topic mismatch: {target['content_id']}")
            document = getattr(message, "document", None)
            is_video = bool(getattr(message, "video", None)) or str(
                getattr(document, "mime_type", "") or ""
            ).casefold().startswith("video/")
            if not is_video:
                raise RuntimeError(f"Telegram message is not a video: {target['content_id']}")
            links = _message_links(message)
            item = target["item"]
            expected_links = tuple(item.affiliate_urls or (item.affiliate_url,))
            if not set(expected_links).issubset(set(links)):
                raise RuntimeError(f"Telegram affiliate link mismatch: {target['content_id']}")
            snapshots[target["content_id"]] = {
                "available": True,
                "caption": str(getattr(message, "message", "") or ""),
                "links": list(links),
                "message_id": str(getattr(message, "id", "")),
                "chat_id": str(getattr(message, "chat_id", "")),
                "topic_id": topic_id,
                "has_video": is_video,
            }
        return snapshots
    finally:
        if client.is_connected():
            await client.disconnect()


def _remote_snapshots(targets: list[dict[str, Any]], hub: ArmoredHub) -> dict[str, dict[str, Any]]:
    return asyncio.run(_read_remote_messages(targets, hub))


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _candidate_rows(generated) -> list[dict[str, Any]]:
    remaining = Counter(
        str(caption)
        for batch in getattr(generated, "provider_candidate_batches", ())
        for caption in batch
    )
    result = []
    for evaluation in generated.evaluations:
        corrections = tuple(evaluation.normalization_corrections)
        raw_caption = str(evaluation.raw_caption or "")
        if "unsupported_model_tail_trimmed_to_vision_fact" in corrections:
            origin = "vision_fact_salvage"
        elif raw_caption and remaining[raw_caption] > 0:
            origin = "provider_candidate"
            remaining[raw_caption] -= 1
        else:
            origin = "local_grounded"
        result.append({
            "rank": int(evaluation.index),
            "caption": str(evaluation.caption),
            "raw_model_caption": raw_caption or None,
            "origin": origin,
            "policy_valid": bool(evaluation.policy_valid),
            "rejection_reason": evaluation.rejection_reason,
            "score": float(evaluation.score),
            "selected": bool(evaluation.selected),
            "normalization_corrections": list(corrections),
        })
    return result


def _prepare_captions(
    db: Database,
    hub: ArmoredHub,
    ia: ArmoredIA,
    targets: list[dict[str, Any]],
    snapshots: dict[str, dict[str, Any]],
    *,
    batch_id: str,
    report_path: Path,
    report: dict[str, Any],
) -> None:
    config = ia.provider_configuration()
    if (
        str(config.get("provider")) != "local"
        or str(config.get("model")) != "deterministic-caption-rules"
        or os.getenv("ARMORED_IA_CAPTION_TITLE_RULES") != "1"
    ):
        raise RuntimeError("Caption refresh must use the reviewed local Vision title rules")

    by_id = {row["content_id"]: row for row in report["results"]}
    for index, target in enumerate(targets, start=1):
        content_id = target["content_id"]
        prior = db.published_caption_edit(batch_id, content_id)
        if prior is not None:
            retryable_rate_limit = (
                str(prior["status"]) == "FAILED"
                and str(prior["error_type"] or "") == "RetryAfter"
            )
            if (str(prior["status"]) == "FAILED" and not retryable_rate_limit) or (
                str(prior["status"]) == "BLOCKED"
                and str(prior["error_type"] or "") != "remote-message-unavailable"
            ):
                raise RuntimeError(f"caption edit is blocked and needs review: {content_id}")
            print(f"CAPTION_PREPARED={index}/{len(targets)} item={content_id} resume=1")
            continue

        item = db.get(content_id)
        context = dict(item.ia_context or {})
        context.setdefault("productName", item.affiliate_name)
        snapshot = snapshots.get(content_id) or {}
        print(f"CAPTION_GENERATING={index}/{len(targets)} item={content_id}", flush=True)
        attempt_provider = str(config["provider"])
        attempt_model = CAPTION_ENGINE
        attempt_id = None
        try:
            with db.ia_generation_attempt(
                content_id, provider=attempt_provider, model=attempt_model,
            ) as attempt_id:
                generated = ia.caption_generator.generate_with_evidence(
                    context,
                    # Regenerate from Vision context alone. Feeding the old
                    # caption back as a novelty constraint can reject the
                    # strongest grounded rule and select a vague fallback.
                    preserve_previous_caption=False,
                )
                request_count = int(generated.provider_requests)
                db.record_ia_provider_request_count(attempt_id, request_count)
        except Exception as exc:
            request_count = int(
                getattr(exc, "provider_requests", None)
                or 0
            )
            if attempt_id is not None:
                db.record_ia_provider_request_count(attempt_id, request_count)
            row = {
                "content_id": content_id,
                "status": "GENERATION_FAILED",
                "error_type": type(exc).__name__,
                "provider_requests": request_count,
                "model_candidate_batches": [
                    {"request": request_index, "captions": list(batch)}
                    for request_index, batch in enumerate(
                        getattr(exc, "provider_candidate_batches", ()), start=1
                    )
                ],
                "candidates": [
                    {
                        "rank": int(evaluation.index),
                        "caption": str(evaluation.caption),
                        "raw_model_caption": str(evaluation.raw_caption or ""),
                        "policy_valid": bool(evaluation.policy_valid),
                        "rejection_reason": evaluation.rejection_reason,
                        "selected": bool(evaluation.selected),
                    }
                    for evaluation in getattr(exc, "evaluations", ())
                ],
            }
            report["results"] = [
                previous for previous in report["results"]
                if previous.get("content_id") != content_id
            ] + [row]
            by_id[content_id] = row
            report["results"] = list(by_id.values())
            _write_report(report_path, report)
            print(f"CAPTION_GENERATION_FAILED item={content_id} error={type(exc).__name__}")
            continue

        logical_request_count = int(generated.provider_requests)
        if (
            logical_request_count not in {0, 1, 2}
            or len(generated.provider_attempts) != logical_request_count
            or len(generated.provider_candidate_batches) > logical_request_count
        ):
            raise RuntimeError(f"Caption generator exceeded one batch plus one Policy retry: {content_id}")
        candidates = tuple(generated.evaluations)
        if not candidates or not any(row.policy_valid and row.selected for row in candidates):
            raise RuntimeError(f"No Policy-approved caption selected: {content_id}")
        selected_caption = hub._validated_caption(item, str(generated.caption))
        if selected_caption != str(generated.caption):
            raise RuntimeError(f"Selected caption is not canonical: {content_id}")
        snapshot = snapshots[content_id]
        links = snapshot["links"] if snapshot["available"] else list(
            item.affiliate_urls or (item.affiliate_url,)
        )
        final_caption = hub._publication_text(
            item,
            caption_override=selected_caption,
            links_override=links,
        )
        evaluations = list(candidates)
        db.record_caption_candidates(content_id, str(generated.batch_id), evaluations)
        edit = db.prepare_published_caption_edit(
            batch_id=batch_id,
            item_id=content_id,
            published_message_id=target["message_id"],
            destination_chat_id=target["chat_id"],
            destination_topic_id=target["topic_id"],
            previous_caption=snapshot["caption"] if snapshot["available"] else "",
            selected_caption=selected_caption,
            final_caption=final_caption,
            provider=attempt_provider,
            model=attempt_model,
            generation_batch_id=str(generated.batch_id),
        )
        model_count = sum(
            len(batch) for batch in generated.provider_candidate_batches
        )
        selected = next(row for row in candidates if row.selected)
        evaluated_rows = _candidate_rows(generated)
        selected_source = next(
            row["origin"] for row in evaluated_rows
            if int(row["rank"]) == int(selected.index) and row["selected"]
        )
        report_row = {
            "content_id": content_id,
            "published_message_id": target["message_id"],
            "destination_chat_id": target["chat_id"],
            "destination_topic_id": target["topic_id"],
            "provider": attempt_provider,
            "model": attempt_model,
            "provider_requests": logical_request_count,
            "requested_model_candidates": 0,
            "received_model_candidates": model_count,
            "model_candidate_batches": [
                {"request": request_index, "captions": list(batch)}
                for request_index, batch in enumerate(generated.provider_candidate_batches, start=1)
            ],
            "policy_approved_candidates": sum(
                1 for row in evaluated_rows if row["policy_valid"]
            ),
            "selected_source": selected_source,
            "selected_caption": selected_caption,
            "final_caption": final_caption,
            "edit_status": str(edit["status"]),
            "telegram_message_available": bool(snapshot["available"]),
            "candidates": evaluated_rows,
        }
        by_id[content_id] = report_row
        report["results"] = list(by_id.values())
        _write_report(report_path, report)
        print(
            f"CAPTION_PREPARED={index}/{len(targets)} item={content_id} "
            f"candidates={len(evaluated_rows)} approved={report_row['policy_approved_candidates']} "
            f"selected={selected_source}"
        )

    errors = [row for row in report["results"] if row.get("status") == "GENERATION_FAILED"]
    prepared = db.conn.execute(
        "SELECT COUNT(*) FROM published_caption_edits WHERE batch_id=? "
        "AND (status IN ('READY','SENDING','UNKNOWN','CONFIRMED') "
        "OR (status='BLOCKED' AND error_type='remote-message-unavailable') "
        "OR (status='FAILED' AND error_type='RetryAfter'))", (batch_id,)
    ).fetchone()[0]
    if errors or int(prepared) != len(targets):
        raise RuntimeError(
            f"caption generation incomplete: prepared={prepared}/{len(targets)} failures={len(errors)}"
        )


def _apply_edits(
    db: Database,
    hub: ArmoredHub,
    targets: list[dict[str, Any]],
    *,
    batch_id: str,
    report_path: Path,
    report: dict[str, Any],
) -> None:
    snapshots = _remote_snapshots(targets, hub)
    last_edit_at: float | None = None
    total = len(targets)
    for index, target in enumerate(targets, start=1):
        content_id = target["content_id"]
        edit = db.published_caption_edit(batch_id, content_id)
        if edit is None:
            raise RuntimeError(f"prepared caption edit is missing: {content_id}")
        status = str(edit["status"])
        if status == "CONFIRMED":
            print(f"CAPTION_EDIT_CONFIRMED={index}/{total} item={content_id} resume=1")
            continue
        if status == "BLOCKED" and str(edit["error_type"] or "") == "remote-message-unavailable":
            print(f"CAPTION_EDIT_SKIPPED={index}/{total} item={content_id} reason=message-missing")
            continue
        retryable_rate_limit = status == "FAILED" and str(edit["error_type"] or "") == "RetryAfter"
        if status in {"FAILED", "BLOCKED"} and not retryable_rate_limit:
            raise RuntimeError(f"caption edit is blocked and needs review: {content_id}")

        current = snapshots[content_id]
        if not current["available"]:
            db.set_published_caption_edit_status(
                int(edit["edit_id"]), "BLOCKED", error_type="remote-message-unavailable",
            )
            report_row = next(row for row in report["results"] if row.get("content_id") == content_id)
            report_row["edit_status"] = "REMOTE_MISSING"
            report_row["telegram_message_available"] = False
            _write_report(report_path, report)
            print(f"CAPTION_EDIT_SKIPPED={index}/{total} item={content_id} reason=message-missing")
            continue
        if current["caption"] == str(edit["final_caption"]):
            db.set_published_caption_edit_status(int(edit["edit_id"]), "CONFIRMED")
            print(f"CAPTION_EDIT_CONFIRMED={index}/{total} item={content_id} reconciled=1")
            continue
        if current["caption"] != str(edit["previous_caption"]):
            db.set_published_caption_edit_status(
                int(edit["edit_id"]), "BLOCKED", error_type="remote-caption-changed",
            )
            raise RuntimeError(f"Telegram caption changed outside this batch: {content_id}")
        if (
            current["message_id"] != target["message_id"]
            or current["chat_id"] != target["chat_id"]
            or current["topic_id"] != target["topic_id"]
            or not current["has_video"]
        ):
            db.set_published_caption_edit_status(
                int(edit["edit_id"]), "BLOCKED", error_type="remote-message-identity-changed",
            )
            raise RuntimeError(f"Telegram message identity changed: {content_id}")

        # The Bot API limits edits. Keep a conservative five-second spacing
        # between successful edit requests; a RetryAfter row is reconciled
        # against Telegram above before it can be sent again.
        if last_edit_at is not None:
            remaining = 5.0 - (time.monotonic() - last_edit_at)
            if remaining > 0:
                time.sleep(remaining)
        db.set_published_caption_edit_status(int(edit["edit_id"]), "SENDING")
        try:
            result = hub.edit_confirmed_caption(
                content_id,
                str(edit["selected_caption"]),
                affiliate_links=tuple(current["links"]),
            )
        except Exception as exc:
            error_type = type(exc).__name__
            status = "UNKNOWN" if error_type in {"NetworkError", "TimedOut"} else "FAILED"
            db.set_published_caption_edit_status(
                int(edit["edit_id"]), status, error_type=error_type,
            )
            raise RuntimeError(f"Telegram caption edit did not confirm for {content_id} ({error_type})") from None
        if result["caption"] != str(edit["final_caption"]):
            db.set_published_caption_edit_status(
                int(edit["edit_id"]), "UNKNOWN", error_type="telegram-response-caption-mismatch",
            )
            raise RuntimeError(f"Telegram returned an unexpected caption for {content_id}")
        last_edit_at = time.monotonic()
        db.set_published_caption_edit_status(int(edit["edit_id"]), "CONFIRMED")
        report_row = next(row for row in report["results"] if row.get("content_id") == content_id)
        report_row["edit_status"] = "CONFIRMED"
        report_row["external_confirmation"] = {
            "message_id": result["message_id"],
            "chat_id": result["chat_id"],
            "topic_id": result["topic_id"],
            "media_preserved": True,
        }
        _write_report(report_path, report)
        print(f"CAPTION_EDIT_CONFIRMED={index}/{total} item={content_id} message={result['message_id']}")

    final_snapshots = _remote_snapshots(targets, hub)
    mismatches = []
    missing_messages = []
    for target in targets:
        content_id = target["content_id"]
        edit = db.published_caption_edit(batch_id, content_id)
        current = final_snapshots[content_id]
        if (
            not current["available"]
            and str(edit["status"]) == "BLOCKED"
            and str(edit["error_type"] or "") == "remote-message-unavailable"
        ):
            missing_messages.append(content_id)
            continue
        if (
            str(edit["status"]) != "CONFIRMED"
            or current["caption"] != str(edit["final_caption"])
            or current["message_id"] != target["message_id"]
            or current["chat_id"] != target["chat_id"]
            or current["topic_id"] != target["topic_id"]
            or not current["has_video"]
        ):
            mismatches.append(content_id)
    if mismatches:
        raise RuntimeError("final Telegram caption verification failed for: " + ",".join(mismatches))
    report["final_verification"] = {
        "sqlite_confirmed_posts": len(targets),
        "verified_posts": len(targets) - len(missing_messages),
        "confirmed_caption_edits": len(targets) - len(missing_messages),
        "remote_messages_missing": missing_messages,
        "media_preserved": True,
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    _write_report(report_path, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reprocess and edit only confirmed publication captions")
    parser.add_argument("--apply", action="store_true", help="authorize the caption-only Telegram edits")
    parser.add_argument("--prepare-only", action="store_true", help="generate and persist candidates without editing Telegram")
    parser.add_argument("--batch-id", default="published-caption-refresh-20261030-title-rules-v1")
    parser.add_argument(
        "--item-id", action="append", default=[],
        help="limit this caption-only refresh to the specified content ID; repeat for multiple IDs",
    )
    args = parser.parse_args(argv)
    if args.apply == args.prepare_only:
        parser.error("choose exactly one of --prepare-only or --apply")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", args.batch_id):
        parser.error("--batch-id may contain only letters, digits, dot, underscore and hyphen")
    if not (ROOT / "credentials" / "project.env").is_file():
        parser.error("credentials/project.env is required")

    _configure_local_caption_run()
    storage = Storage(ROOT)
    db = Database(storage.database / "armoredcreator.db", initialize=False)
    lock_held = False
    try:
        db.acquire_runtime_lock("coordinator")
        lock_held = True
        backup = _backup_database(db)
        db.initialize()
        targets = _load_targets(db)
        if args.item_id:
            requested = set(args.item_id)
            by_content_id = {target["content_id"]: target for target in targets}
            unknown = requested - set(by_content_id)
            if unknown:
                raise RuntimeError(
                    "caption refresh item IDs are not confirmed PUBLISHED rows: "
                    + ",".join(sorted(unknown))
                )
            targets = [target for target in targets if target["content_id"] in requested]
        hub = ArmoredHub(ROOT, db=db)
        baseline = _remote_snapshots(targets, hub)
        report_path = ROOT / "storage" / "validation" / f"{args.batch_id}.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if report.get("batch_id") != args.batch_id or report.get("model") != CAPTION_ENGINE:
                raise RuntimeError("existing caption report belongs to a different batch or caption engine")
            report["database_backups"] = list(dict.fromkeys([
                *(report.get("database_backups") or []),
                str(backup.relative_to(ROOT)),
            ]))
        else:
            report = {
                "batch_id": args.batch_id,
                "provider": "local",
                "model": CAPTION_ENGINE,
                "max_model_candidates_per_product": 0,
                "generation_order": "the reviewed deterministic title rules create a short caption from the Vision title/context; shared Policy validates each caption before any edit",
                "request_rule": "no model-provider requests; use the same approved local generator and Policy as the full-catalog replay",
                "products": len(targets),
                "database_backups": [str(backup.relative_to(ROOT))],
                "results": [],
            }
        _write_report(report_path, report)
        ia = ArmoredIA()
        _prepare_captions(
            db, hub, ia, targets, baseline,
            batch_id=args.batch_id, report_path=report_path, report=report,
        )
        if args.prepare_only:
            print("CAPTION_REFRESH_PREPARED=1")
            print("TELEGRAM_EDITS=0")
            print(f"REPORT={report_path}")
            print(f"SQLITE_BACKUP={backup}")
            return 0
        _apply_edits(
            db, hub, targets,
            batch_id=args.batch_id, report_path=report_path, report=report,
        )
        statuses = Counter(
            str(row[0]) for row in db.conn.execute(
                "SELECT status FROM published_caption_edits WHERE batch_id=?", (args.batch_id,)
            )
        )
        print("CAPTION_REFRESH_COMPLETE=1")
        print("EDIT_STATES=" + json.dumps(dict(statuses), sort_keys=True))
        print(f"VERIFIED_MESSAGES={len(targets) - statuses.get('BLOCKED', 0)}")
        print(f"REMOTE_MESSAGES_MISSING={statuses.get('BLOCKED', 0)}")
        print(f"REPORT={report_path}")
        print(f"SQLITE_BACKUP={backup}")
        return 0
    except Exception as exc:
        print(f"CAPTION_REFRESH_BLOCKED={type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        if lock_held:
            try:
                db.release_runtime_lock("coordinator")
            except Exception:
                pass
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
