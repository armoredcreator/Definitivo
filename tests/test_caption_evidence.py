from __future__ import annotations

import tempfile
from pathlib import Path

from armored_core.database import Database
from armored_core.models import PublicationCheck, State
from armored_core.pipeline import Pipeline
from armored_core.services import PublicationResult, StudioResult, SyncService, VisionResult
from armored_core.storage import Storage
from ArmoredIA.service import ArmoredIA
from ArmoredIA.caption.generator import CaptionGenerator


class _Vision:
    def identify(self, item):
        return VisionResult(
            "produto-teste",
            "https://example.invalid/affiliate",
            ia_context={
                "productName": "Bancada Suspensa",
                "description": "solução prática para cozinha organizada",
            },
        )


def test_caption_recovery_block_requires_audited_explicit_retry(tmp_path):
    storage = Storage(tmp_path)
    db = Database(storage.database / "retry.sqlite3")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"original")
    item_id = SyncService(db, storage).ingest(source, "retry", source_id="test")
    db.finish_caption_recovery(item_id, status="BLOCKED", reason="provider-output-truncated")

    assert db.caption_recovery_blocked(item_id)
    db.authorize_caption_recovery_retry(item_id, reason="Ollama output cap corrected")
    assert not db.caption_recovery_blocked(item_id)
    assert db.claim_caption_recovery(item_id, previous_caption=None) == "STARTED"

    recovery = db.caption_recovery(item_id)
    event = db.conn.execute(
        "SELECT * FROM caption_recovery_retry_authorizations WHERE content_id=?", (item_id,)
    ).fetchone()
    assert recovery["attempts"] == 1
    assert recovery["status"] == "STARTED"
    assert event["previous_reason"] == "provider-output-truncated"
    assert event["authorization_reason"] == "Ollama output cap corrected"
    assert event["consumed_at"] is not None
    db.finish_caption_recovery(item_id, status="BLOCKED", reason="still-invalid")
    assert db.caption_recovery_blocked(item_id)
    db.close()


class _Studio:
    def __init__(self, storage):
        self.storage = storage

    def process(self, item):
        result = self.storage.result(
            item.content_id,
            affiliate_url=item.affiliate_url,
            affiliate_name=item.affiliate_name,
        )
        result.write_bytes(item.original_path.read_bytes() + b"-final")
        return StudioResult(None, result)


class _Publisher:
    def __init__(self):
        self.published = []

    def check_publication(self, item):
        return PublicationCheck.ABSENT

    def publish(self, item):
        self.published.append(item.content_id)
        return PublicationResult(True, "telegram-" + item.content_id)


def _make_item(root: Path, db: Database, storage: Storage) -> str:
    source = root / "source.mp4"
    source.write_bytes(b"VIDEO")
    return SyncService(db, storage).ingest(source, "caption-evidence")


def test_pipeline_persists_every_caption_candidate_and_selected_score(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")

    class Provider:
        def __init__(self):
            self.calls = 0

        def generate_candidates(self, task, context, limit):
            self.calls += 1
            return [
                "Compre agora 🔥\n#oferta",
                "Tudo bonito ✨\n#legal",
                "Cantinho prático ✨\n#cozinha",
            ]

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        storage = Storage(root)
        db = Database(storage.database / "armoredcreator.db")
        provider = Provider()
        ia = ArmoredIA(caption_generator=CaptionGenerator(provider=provider))
        item_id = _make_item(root, db, storage)

        Pipeline(db, storage, _Vision(), _Studio(storage), _Publisher(), ia=ia).run(item_id)

        rows = db.caption_candidates(item_id)
        assert provider.calls == 1
        assert len(rows) == 3
        assert rows[0]["policy_valid"] == 0
        assert rows[0]["rejection_reason"]
        # #legal has no product/category evidence and must never be publishable.
        assert rows[1]["policy_valid"] == 0
        assert rows[1]["rejection_reason"]
        assert rows[1]["selected"] == 0
        assert rows[2]["policy_valid"] == 1
        assert rows[2]["selected"] == 1
        assert rows[2]["score"] > rows[1]["score"]
        assert db.get(item_id).publication_caption == "🧡 Cantinho prático\n#cozinha"
        assert db.get(item_id).state == State.PUBLISHED
        db.close()


def test_pipeline_persists_all_rejections_before_entering_recovery(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")

    class Provider:
        def __init__(self):
            self.calls = 0

        def generate_candidates(self, task, context, limit):
            self.calls += 1
            return [
                "Compre agora 🔥\n#oferta",
                "Bancada suspensa ✨\n#beleza",
                "Medida 10ml ✨\n#beleza",
            ]

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        storage = Storage(root)
        db = Database(storage.database / "armoredcreator.db")
        provider = Provider()
        ia = ArmoredIA(caption_generator=CaptionGenerator(provider=provider))
        item_id = _make_item(root, db, storage)

        try:
            try:
                Pipeline(db, storage, _Vision(), _Studio(storage), _Publisher(), ia=ia).run(item_id)
            except RuntimeError:
                pass
            else:
                raise AssertionError("pipeline should fail when all caption candidates are rejected")

            rows = db.caption_candidates(item_id)
            # One bounded initial generation plus one bounded caption recovery
            # attempt; every candidate and rejection remains auditable.
            assert provider.calls == 2
            assert len(rows) == 6
            assert all(row["policy_valid"] == 0 for row in rows)
            assert all(row["rejection_reason"] for row in rows)
            assert all(row["selected"] == 0 for row in rows)
            assert db.get(item_id).state == State.RECOVERY
        finally:
            db.close()
