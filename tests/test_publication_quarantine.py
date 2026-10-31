from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ArmoredHub.service import ArmoredHub
from ArmoredStock.service import ArmoredStock
from armored_core.catch_up_budget import DurableCatchUpBudget
from armored_core.coordinator import Coordinator
from armored_core.database import Database
from armored_core.models import State
from armored_core.publication_quarantine import PublicationQuarantine
from armored_core.services import PublicationDeferredError, SyncService
from armored_core.storage import Storage
from armored_core.startup_audit import StartupReconciler


def _approved(
    db: Database, storage: Storage, message_id: str, *, state=State.RECEIVED, ambiguous=True
):
    source = storage.root / "fixtures" / f"{message_id}.mp4"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(f"immutable-original-{message_id}".encode())
    item_id = SyncService(db, storage).ingest(
        source,
        message_id,
        source_id="-1003788989075",
        topic_id=287,
        original_url=f"https://s.shopee.com.br/source-{message_id}",
    )
    db.set_vision(
        item_id,
        "radio automotivo com Bluetooth",
        f"https://s.shopee.com.br/affiliate-{message_id}",
        publication_caption="🧡 Conexão Bluetooth\n#radio",
        ia_context={"shopId": "10", "itemId": message_id, "productName": "radio automotivo com Bluetooth"},
    )
    if state != State.RECEIVED:
        db.transition(item_id, state, "fixture-prior-interruption")
    if ambiguous:
        db.publication_started(item_id, "-1004341972306", 228)
    return item_id


def test_legacy_publishing_without_receipt_gets_a_local_quarantine_fence(tmp_path):
    quarantine = PublicationQuarantine(tmp_path / "publication-quarantine.sqlite3")
    quarantine.quarantine_legacy_missing_receipt(
        "legacy-item-1", evidence={"item_state": "RECOVERY"},
    )

    assert quarantine.contains("legacy-item-1")
    assert quarantine.observed_outcomes() == {"UNKNOWN"}
    import sqlite3
    connection = sqlite3.connect(tmp_path / "publication-quarantine.sqlite3")
    key, status = connection.execute(
        "SELECT idempotency_key,original_status FROM quarantined_publications "
        "WHERE content_id='legacy-item-1'"
    ).fetchone()
    connection.close()
    assert key.startswith("legacy-missing-receipt:")
    assert status == "LEGACY_RECEIPT_MISSING"


def test_topic_scoped_absence_resolution_is_audited_and_later_unknown_reactivates_fence(tmp_path):
    import sqlite3

    quarantine = PublicationQuarantine(tmp_path / "publication-quarantine.sqlite3")
    item_id = "-1003788989075_1040"
    receipt = {
        "idempotency_key": f"armoredcreator:content:{item_id}",
        "verification_status": "SENT_UNVERIFIED",
        "published_message_id": "1339",
        "confirmed": 1,
        "destination_chat_id": "-1004341972306",
        "destination_topic_id": 228,
    }
    quarantine.quarantine_unknown(item_id, receipt, evidence={"item_state": "RECOVERY"})
    proof = {
        "method": "telegram_topic_history_scan",
        "checked_content_id": item_id,
        "chat_id": "-1004341972306",
        "topic_id": 228,
        "scan_complete": True,
        "scanned_message_ids": ["1363", "1360", "228"],
        "checked_link_codes": ["4fvURQ6ctv", "5fpQxUgaIQ"],
        "matched_message_ids": [],
        "exact_receipt_id": "1339",
        "exact_receipt_status": "ABSENT",
        "operator_authorized": True,
    }

    resolution_id = quarantine.resolve_absent(item_id, evidence=proof)

    assert resolution_id > 0
    assert not quarantine.contains(item_id)
    assert quarantine.unresolved_count() == 0
    connection = sqlite3.connect(tmp_path / "publication-quarantine.sqlite3")
    try:
        assert connection.execute(
            "SELECT original_message_id,original_confirmed FROM quarantined_publications "
            "WHERE content_id=?", (item_id,),
        ).fetchone() == ("1339", 1)
        assert connection.execute(
            "SELECT COUNT(*) FROM quarantine_evidence WHERE content_id=?", (item_id,),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT decision FROM quarantine_resolutions WHERE resolution_id=?",
            (resolution_id,),
        ).fetchone() == ("ABSENT",)
    finally:
        connection.close()


def test_exact_message_confirmation_clears_unknown_fence_without_authorizing_resend(tmp_path):
    quarantine = PublicationQuarantine(tmp_path / "publication-quarantine.sqlite3")
    item_id = "-1003788989075_1041"
    receipt = {
        "idempotency_key": f"armoredcreator:content:{item_id}",
        "verification_status": "SENT_UNVERIFIED",
        "published_message_id": None,
        "confirmed": 0,
        "destination_chat_id": "-1004341972306",
        "destination_topic_id": 228,
    }
    quarantine.quarantine_unknown(item_id, receipt, evidence={"item_state": "RECOVERY"})
    assert quarantine.contains(item_id)

    confirmation_id = quarantine.resolve_confirmed(
        item_id,
        message_id="1450",
        evidence={
            "method": "telegram_exact_message_verification",
            "checked_content_id": item_id,
            "checked_message_id": "1450",
            "confirmed": True,
            "destination_chat_id": "-1004341972306",
            "destination_topic_id": 228,
        },
    )

    assert confirmation_id > 0
    assert not quarantine.contains(item_id)
    import sqlite3
    connection = sqlite3.connect(tmp_path / "publication-quarantine.sqlite3")
    try:
        assert connection.execute(
            "SELECT confirmed_message_id FROM quarantine_confirmations "
            "WHERE confirmation_id=?", (confirmation_id,),
        ).fetchone() == ("1450",)
    finally:
        connection.close()

    quarantine.quarantine_unknown(
        item_id,
        {**receipt, "idempotency_key": f"armoredcreator:content:{item_id}:next", "published_message_id": None},
        evidence={"item_state": "RECOVERY", "reason": "later-unknown-cycle"},
    )
    assert quarantine.contains(item_id)

    # A subsequent ambiguous send appends new evidence after the resolution;
    # the durable fence becomes active again without replacing the first receipt.
    next_receipt = {**receipt, "verification_status": "SENT_UNVERIFIED", "published_message_id": "1400", "confirmed": 0}
    quarantine.quarantine_unknown(item_id, next_receipt, evidence={"item_state": "RECOVERY"})
    assert quarantine.contains(item_id)
    assert quarantine.unresolved_count() == 1
    assert quarantine.quarantined_ids() == {item_id}


def test_confirmed_but_missing_video_receipt_is_preserved_until_complete_scan(tmp_path):
    quarantine = PublicationQuarantine(tmp_path / "publication-quarantine.sqlite3")
    item_id = "-1003788989075_1040"
    receipt = {
        "idempotency_key": f"armoredcreator:content:{item_id}",
        "verification_status": "CONFIRMED",
        "published_message_id": "1339",
        "confirmed": 1,
        "destination_chat_id": "-1004341972306",
        "destination_topic_id": 228,
    }
    quarantine.quarantine_confirmed_message_missing(
        item_id,
        receipt,
        evidence={"item_state": "PUBLISHED", "exact_message_fetch": "NOT_FOUND"},
    )
    assert quarantine.contains(item_id)

    evidence = {
        "method": "telegram_topic_history_scan",
        "checked_content_id": item_id,
        "chat_id": "-1004341972306",
        "topic_id": 228,
        "scan_complete": True,
        "scanned_message_ids": ["1363", "1360", "228"],
        "scanned_message_count": 3,
        "checked_link_codes": ["source-code", "affiliate-code"],
        "matched_message_ids": [],
        "exact_receipt_id": "1339",
        "exact_receipt_status": "ABSENT",
        "operator_authorized": True,
    }
    resolution_id = quarantine.resolve_absent(item_id, evidence=evidence)
    assert resolution_id > 0
    assert not quarantine.contains(item_id)

    import sqlite3
    connection = sqlite3.connect(tmp_path / "publication-quarantine.sqlite3")
    try:
        row = connection.execute(
            "SELECT original_status,original_message_id,original_confirmed "
            "FROM quarantined_publications WHERE content_id=?", (item_id,),
        ).fetchone()
        assert row == ("CONFIRMED", "1339", 1)
    finally:
        connection.close()


@pytest.mark.parametrize(
    "change, message",
    [
        ({"scan_complete": False}, "complete-topic-scan"),
        ({"matched_message_ids": ["1401"]}, "live-candidate"),
        ({"exact_receipt_status": "UNKNOWN"}, "receipt-not-absent"),
        ({"topic_id": 1160}, "topic-mismatch"),
    ],
)
def test_topic_absence_resolution_rejects_incomplete_or_mismatched_evidence(
    tmp_path, change, message
):
    item_id = "-1003788989075_1040"
    quarantine = PublicationQuarantine(tmp_path / "publication-quarantine.sqlite3")
    quarantine.quarantine_unknown(
        item_id,
        {
            "idempotency_key": f"armoredcreator:content:{item_id}",
            "verification_status": "SENT_UNVERIFIED",
            "published_message_id": "1339",
            "confirmed": 1,
            "destination_chat_id": "-1004341972306",
            "destination_topic_id": 228,
        },
    )
    evidence = {
        "method": "telegram_topic_history_scan",
        "checked_content_id": item_id,
        "chat_id": "-1004341972306",
        "topic_id": 228,
        "scan_complete": True,
        "scanned_message_ids": ["1363", "1360", "228"],
        "checked_link_codes": ["5fpQxUgaIQ"],
        "matched_message_ids": [],
        "exact_receipt_id": "1339",
        "exact_receipt_status": "ABSENT",
        "operator_authorized": True,
    }
    evidence.update(change)
    with pytest.raises((ValueError, RuntimeError), match=message):
        quarantine.resolve_absent(item_id, evidence=evidence)
    assert quarantine.contains(item_id)


def test_reconciled_publication_receipt_is_archived_before_new_generation(tmp_path):
    storage = Storage(tmp_path / "receipt-history")
    db = Database(storage.database / "armoredcreator.db")
    item_id = _approved(db, storage, "receipt-history", ambiguous=False)
    db.publication_started(item_id, "-1004341972306", 228)
    db.publication_message_sent(item_id, "1339")
    db.conn.execute(
        "UPDATE publications SET confirmed=1,verification_status='SENT_UNVERIFIED' "
        "WHERE content_id=?", (item_id,),
    )
    db.conn.commit()
    evidence = {
        "method": "telegram_topic_history_scan",
        "checked_content_id": item_id,
        "chat_id": "-1004341972306",
        "topic_id": 228,
        "scan_complete": True,
        "scanned_message_ids": ["1363", "1360", "228"],
        "checked_link_codes": ["original-code", "affiliate-code"],
        "matched_message_ids": [],
        "operator_authorized": True,
    }

    key = db.archive_publication_after_absence_reconciliation(
        item_id, resolution_id=17, evidence=evidence,
    )

    current = db.publication(item_id)
    assert key == f"armoredcreator:content:{item_id}:reconciled:17"
    assert current["idempotency_key"] == key
    assert current["published_message_id"] is None
    assert current["confirmed"] == 0
    assert current["verification_status"] == "PENDING"
    old = db.conn.execute(
        "SELECT published_message_id,confirmed,verification_status,resolution_id "
        "FROM publication_receipt_history WHERE content_id=?", (item_id,),
    ).fetchone()
    assert tuple(old) == ("1339", 1, "SENT_UNVERIFIED", 17)
    assert db.archive_publication_after_absence_reconciliation(
        item_id, resolution_id=17, evidence=evidence,
    ) == key
    assert db.conn.execute(
        "SELECT COUNT(*) FROM publication_receipt_history WHERE content_id=?", (item_id,),
    ).fetchone()[0] == 1
    db.close()


def test_startup_audit_fences_legacy_recovery_before_any_publication_check(tmp_path):
    storage = Storage(tmp_path / "legacy-project")
    db = Database(storage.database / "armoredcreator.db")
    item_id = _approved(db, storage, "legacy-no-receipt", state=State.RECOVERY, ambiguous=False)
    db.record_retryable_error(item_id, "legacy-publication-receipt-missing:manual-reconciliation-required")
    quarantine = PublicationQuarantine(storage.database / "publication-quarantine.sqlite3")

    StartupReconciler(db, storage, publisher=None, publication_quarantine=quarantine).run()

    assert quarantine.contains(item_id)
    assert quarantine.unresolved_count() == 1


class _ThreeSourceEmpty:
    sources = tuple(SimpleNamespace(source_id=f"source-{number}") for number in range(1, 4))
    historical_materialization_failed = False
    historical_scan_exhausted = False

    def set_run_candidate_limit(self, limit):
        self.limit = limit

    async def iter_historical_candidates_async(self):
        if False:
            yield None


class _CompleteSource(_ThreeSourceEmpty):
    def is_historical_complete(self):
        return True


def test_unknown_receipts_are_quarantined_and_assigned_safe_items_reach_dry_run_barrier(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ARMORED_HUB_DRY_RUN", "1")
    monkeypatch.setenv("ARMORED_CREATOR_BOT_TOKEN", "synthetic-test-token")
    monkeypatch.setenv("ARMORED_CREATOR_GROUP_ID", "-1004341972306")
    monkeypatch.setenv("ARMORED_HUB_TOPIC_ID", "228")
    root = tmp_path / "clone"
    storage = Storage(root)
    db = Database(storage.database / "armoredcreator.db")

    ids = {
        "291": _approved(db, storage, "291", state=State.RECOVERY),
        "292": _approved(db, storage, "292", ambiguous=False),
        "293": _approved(db, storage, "293", ambiguous=False),
        "294": _approved(db, storage, "294"),
    }
    legacy_1040 = _approved(db, storage, "1040", state=State.RECOVERY)
    db.publication_message_sent(legacy_1040, "1339")
    # Reproduce the legacy inconsistent flag exactly; the status remains the
    # authority and must not be rewritten to CONFIRMED by startup.
    db.conn.execute(
        "UPDATE publications SET confirmed=1,verification_status='SENT_UNVERIFIED' "
        "WHERE content_id=?", (legacy_1040,),
    )
    db.conn.commit()

    budget = DurableCatchUpBudget(
        storage.database / "catch-up-work-budget.sqlite3", "lote-001", 3
    )
    assert budget.claim([ids["291"], ids["292"], ids["293"]]) == {
        ids["291"], ids["292"], ids["293"]
    }
    before_291 = dict(db.get(ids["291"]).__dict__)
    before_291_events = [tuple(row) for row in db.conn.execute(
        "SELECT old_state,new_state,reason,created_at FROM state_events "
        "WHERE content_id=? ORDER BY id", (ids["291"],)
    )]
    before_receipts = {
        item_id: None if db.publication(item_id) is None else tuple(db.publication(item_id))
        for item_id in (*ids.values(), legacy_1040)
    }

    routes = (SimpleNamespace(
        source=SimpleNamespace(source_id="-1003788989075"),
        hub=SimpleNamespace(chat_id="-1004341972306", topic_id=228),
    ),)
    hub = ArmoredHub(root, db, routes=routes)
    monkeypatch.setattr(hub, "_video_metadata", lambda _path: (1080, 1920, 2))
    hub_attempts = []
    original_publish_once = hub.publish_once

    def tracked_publish_once(item):
        hub_attempts.append(item.content_id)
        return original_publish_once(item)

    hub.publish_once = tracked_publish_once
    coordinator = Coordinator(
        db, storage, SimpleNamespace(), SimpleNamespace(), hub,
        source=_ThreeSourceEmpty(), catch_up_budget=budget,
    )

    summary = coordinator.startup_reconciler.run()
    quarantine = coordinator.publication_quarantine
    assert summary["publication_ambiguous"] == 3
    assert {item_id for item_id in (*ids.values(), legacy_1040) if quarantine.contains(item_id)} == {
        ids["291"], ids["294"], legacy_1040,
    }
    assert all(db.publication(item_id)["verification_status"] != "CONFIRMED"
               for item_id in (ids["291"], ids["294"], legacy_1040))
    assert tuple(db.publication(legacy_1040)) == before_receipts[legacy_1040]
    assert quarantine.observed_outcomes() == {"UNKNOWN"}
    assert quarantine.quarantined_ids() == {ids["291"], ids["294"], legacy_1040}

    # Quarantine inspection itself leaves the historical case untouched; the
    # normal bounded pipeline below will admit only independent safe IDs.
    assert dict(db.get(ids["291"]).__dict__) == before_291
    assert [tuple(row) for row in db.conn.execute(
        "SELECT old_state,new_state,reason,created_at FROM state_events "
        "WHERE content_id=? ORDER BY id", (ids["291"],)
    )] == before_291_events
    assert budget.assigned_ids() == {ids["291"], ids["292"], ids["293"]}

    events = []
    original_pipeline_run = coordinator.pipeline.run

    def pipeline_run(item_id, *, stop_after_ia=False, **kwargs):
        current = db.get(item_id)
        if stop_after_ia and current.state == State.RECEIVED:
            events.append(f"ia:{current.telegram_message_id}")
            db.transition(item_id, State.SPEECH, "ia-complete")
            return None
        return original_pipeline_run(item_id, stop_after_ia=stop_after_ia, **kwargs)

    coordinator.pipeline.run = pipeline_run

    def speech_studio(item_ids):
        outputs = {}
        for item_id in item_ids:
            item = db.get(item_id)
            events.append(f"speech:{item.telegram_message_id}")
            events.append(f"studio:{item.telegram_message_id}")
            db.transition(item_id, State.STUDIO_BATCH, "fixture-v5-render-start")
            output = storage.result(
                item_id, item.affiliate_url, item.affiliate_name, source_id=item.source_id
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(item.original_path.read_bytes() + b"-clone-render")
            outputs[item_id] = output
        db.complete_speech_studio_batch(outputs)

    coordinator._run_speech_studio_batch = speech_studio

    async def no_download_stock(_self, *, content_ids=None):
        # Both safe items already have verified originals, so there is no
        # Stock download batch to run; Coordinator still resumes them below.
        assert set(content_ids or ()).issubset({ids["292"], ids["293"]})
        return {
            "errors": [], "processed": 0,
            "outcomes": {"approved_missing_original": 0, "skipped_existing_original": 2},
        }

    monkeypatch.setattr(ArmoredStock, "run", no_download_stock)

    # The exact assigned batch gets through IA and the Speech/Studio boundary;
    # real Hub dry-run defers both sends and leaves the prepared rows in PUBLISHING.
    import asyncio

    first = asyncio.run(coordinator._run_staged_catch_up_async())
    assert set(first) == {ids["292"], ids["293"]}
    assert hub_attempts == [ids["292"], ids["293"]]
    assert db.get(ids["291"]).state is State.RECOVERY
    assert db.get(ids["292"]).state is State.PUBLISHING
    assert db.get(ids["293"]).state is State.PUBLISHING
    assert all(db.publication(item_id) is None for item_id in (ids["292"], ids["293"]))
    assert budget.assigned_count == 3 and budget.remaining == 0
    assert db.historical_complete() is False
    assert db.conn.execute("SELECT COUNT(*) FROM sync_topics").fetchone()[0] == 0
    assert set(events) == {
        "ia:292", "ia:293", "speech:292", "speech:293", "studio:292", "studio:293",
    }

    for item_id in (ids["292"], ids["293"]):
        # Keep the actual Hub boundary closed in every validation branch.
        monkeypatch.setenv("ARMORED_HUB_DRY_RUN", "1")
        with pytest.raises(PublicationDeferredError, match="ARMORED_HUB_DRY_RUN=1"):
            hub.publish_once(db.get(item_id))
        with pytest.raises(PublicationDeferredError, match="ARMORED_HUB_DRY_RUN=1"):
            hub.publish(db.get(item_id))
    monkeypatch.setenv("ARMORED_HUB_DRY_RUN", "1")

    # Same run ID is idempotent: Hub alone is retried, no costly stage repeats,
    # no receipt/checkpoint/status is inferred, and its three IDs stay fixed.
    before_events = list(events)
    receipts_before_resume = {
        item_id: None if db.publication(item_id) is None else tuple(db.publication(item_id))
        for item_id in ids.values()
    }
    coordinator.startup_reconciler.run()
    coordinator.recover_pending()
    asyncio.run(coordinator._run_staged_catch_up_async())
    assert events == before_events
    assert budget.assigned_ids() == {ids["291"], ids["292"], ids["293"]}
    assert budget.assigned_count == 3
    assert {
        item_id: None if db.publication(item_id) is None else tuple(db.publication(item_id))
        for item_id in ids.values()
    } == receipts_before_resume
    assert tuple(db.publication(ids["294"])) == before_receipts[ids["294"]]
    assert db.get(ids["291"]).state is State.RECOVERY
    assert all(db.get(item_id).state is State.PUBLISHING for item_id in (ids["292"], ids["293"]))
    coordinator.close()


def test_quarantined_unknown_blocks_catchup_to_live_even_if_source_reports_complete(
    tmp_path, monkeypatch
):
    import asyncio

    root = tmp_path / "live-fence"
    storage = Storage(root)
    db = Database(storage.database / "armoredcreator.db")
    item_id = _approved(db, storage, "291", state=State.RECOVERY)
    quarantine = PublicationQuarantine(storage.database / "publication-quarantine.sqlite3")
    quarantine.quarantine_unknown(
        item_id,
        db.publication(item_id),
        evidence={"item_state": "RECOVERY"},
    )
    quarantine.close()
    coordinator = Coordinator(
        db, storage, SimpleNamespace(), SimpleNamespace(), SimpleNamespace(),
        source=_CompleteSource(),
    )
    entered_live = []
    async def live_once():
        entered_live.append(True)
        return []
    coordinator.run_live_once_async = live_once
    asyncio.run(coordinator._run_forever_async())
    assert entered_live == []
    assert coordinator.publication_quarantine.contains(item_id)
    assert db.get(item_id).state is State.RECOVERY
    coordinator.close()


def test_startup_preserves_explicitly_reconciled_fresh_generation(tmp_path):
    storage = Storage(tmp_path / "reconciled-startup")
    db = Database(storage.database / "armoredcreator.db")
    item_id = _approved(db, storage, "reconciled-startup", state=State.RECEIVED, ambiguous=True)
    quarantine = PublicationQuarantine(storage.database / "publication-quarantine.sqlite3")
    quarantine.quarantine_unknown(
        item_id,
        db.publication(item_id),
        evidence={"item_state": "RECOVERY"},
    )
    evidence = {
        "method": "telegram_topic_history_scan",
        "checked_content_id": item_id,
        "chat_id": "-1004341972306",
        "topic_id": 228,
        "scan_complete": True,
        "scanned_message_ids": ["1363", "1360", "228"],
        "scanned_message_count": 3,
        "checked_link_codes": ["source-reconciled-startup", "affiliate-reconciled-startup"],
        "matched_message_ids": [],
        "exact_receipt_status": "NO_PRIOR_ID",
        "operator_authorized": True,
    }
    resolution_id = quarantine.resolve_absent(item_id, evidence=evidence)
    db.archive_publication_after_absence_reconciliation(
        item_id, resolution_id=resolution_id, evidence=evidence,
    )
    db.transition(item_id, State.RECOVERY, "startup-publication-unknown-quarantined")

    StartupReconciler(
        db, storage, publisher=None, publication_quarantine=quarantine,
    ).run()

    assert db.is_reconciled_publication_generation(item_id)
    assert not quarantine.contains(item_id)
    assert db.get(item_id).state == State.RECEIVED
    assert db.last_state_event(item_id)["reason"] == "startup-resume-explicitly-reconciled-absence-to-stock"
    quarantine.close()
    db.close()


def test_recovery_reuses_completed_v5_result_after_explicit_absence(tmp_path):
    from armored_core.recovery import Recovery

    storage = Storage(tmp_path / "reconciled-v5-resume")
    db = Database(storage.database / "armoredcreator.db")
    item_id = _approved(db, storage, "reconciled-v5-resume", state=State.RECEIVED, ambiguous=True)
    item = db.get(item_id)
    result_path = storage.result(
        item_id, item.affiliate_url, item.affiliate_name, source_id=item.source_id,
    )
    result_path.write_bytes(b"verified-v5-render")
    db.set_result(item_id, result_path)
    db.transition(item_id, State.PUBLISHING, "speech-studio-v5-complete")

    quarantine = PublicationQuarantine(storage.database / "publication-quarantine.sqlite3")
    quarantine.quarantine_unknown(item_id, db.publication(item_id), evidence={"item_state": "RECOVERY"})
    evidence = {
        "method": "telegram_topic_history_scan",
        "checked_content_id": item_id,
        "chat_id": "-1004341972306",
        "topic_id": 228,
        "scan_complete": True,
        "scanned_message_ids": ["1363", "1360", "228"],
        "scanned_message_count": 3,
        "checked_link_codes": ["source-reconciled-v5", "affiliate-reconciled-v5"],
        "matched_message_ids": [],
        "exact_receipt_status": "NO_PRIOR_ID",
        "operator_authorized": True,
    }
    resolution_id = quarantine.resolve_absent(item_id, evidence=evidence)
    db.archive_publication_after_absence_reconciliation(
        item_id, resolution_id=resolution_id, evidence=evidence,
    )
    db.publication_absent_confirmed(item_id)
    db.transition(item_id, State.RECOVERY, "simulated-restart-after-explicit-absence")

    calls = []
    class Publisher:
        def check_publication(self, _item):
            calls.append("check")
            raise AssertionError("an explicit absence and complete v5 result do not need another send check")
    def speech_studio_runner(_item_id):
        calls.append("render")

    recovery = Recovery(
        db, storage, vision=None, studio=None, publisher=Publisher(), ia=None,
        speech_studio_runner=speech_studio_runner,
        publication_quarantine=quarantine,
    )
    recovery.reconcile(item_id)

    assert calls == []
    assert db.get(item_id).state == State.PUBLISHING
    assert db.get(item_id).result_path == result_path
    assert db.has_speech_studio_v5_completion(item_id)
    assert db.is_reconciled_publication_generation(item_id)
    quarantine.close()
    db.close()
