from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from armored_core.coordinator import Coordinator
from armored_core.database import Database
from armored_core.models import State
from armored_core.services import PublicationResult, StudioResult, VisionResult
from armored_core.storage import Storage
from ArmoredIA.caption.generator import CaptionGenerator, CaptionGenerationError
from ArmoredIA.providers.gemini import GeminiProvider
from ArmoredVision.service import ArmoredVision
from coordinator_test_support import install_synthetic_speech_studio


class _Vision:
    def identify(self, item):
        return VisionResult(
            "radio automotivo", "https://example.invalid/affiliate",
            ia_context={"productName": "radio automotivo"},
        )


class _IA:
    def generate_caption(self, _context):
        return "🧡 Radio bonito\n#radio"


class _Studio:
    def __init__(self, storage):
        self.storage = storage

    def process(self, item):
        result = self.storage.result(item.content_id, affiliate_name="affiliate")
        result.write_bytes(item.original_path.read_bytes())
        return StudioResult(None, result)


class _Publisher:
    def check_publication(self, item):
        from armored_core.models import PublicationCheck
        return PublicationCheck.ABSENT

    def publish(self, item):
        return PublicationResult(True, "pub-" + item.content_id)


class AuditRegressionTests(unittest.TestCase):
    def test_catch_up_does_not_recover_inline_when_pipeline_returns_recovery(self):
        class Source:
            def __init__(self):
                self.calls = 0

            async def fetch_next_async(self):
                self.calls += 1
                if self.calls == 1:
                    async def materialize(target):
                        target.write_bytes(b"first")
                    return SimpleNamespace(
                        telegram_message_id="501",
                        source_id="telegram",
                        topic_id=1,
                        topic_name="topic",
                        original_url="https://shopee.example/first",
                        materialize=materialize,
                    )
                if self.calls == 2:
                    async def materialize(target):
                        target.write_bytes(b"second")
                    return SimpleNamespace(
                        telegram_message_id="502",
                        source_id="telegram",
                        topic_id=1,
                        topic_name="topic",
                        original_url="https://shopee.example/second",
                        materialize=materialize,
                    )
                return None

            def mark_ingested(self, _message_id):
                pass

            def complete_historical_sync(self):
                self.db.complete_historical_sync()

        class CoordinatorUnderTest(Coordinator):
            def run(self, item_id):
                if item_id == "501":
                    self.db.transition(item_id, State.RECOVERY, "synthetic")
                    return
                self.db.transition(item_id, State.PUBLISHED, "synthetic")
                self.db.mark_cleanup_completed(item_id)

            def recover(self, item_id):
                raise AssertionError("RECOVERY não pode ser tentado inline durante o scan")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            storage = Storage(root)
            db = Database(storage.database / "db.sqlite")
            source = Source()
            source.db = db
            coordinator = CoordinatorUnderTest(
                db, storage, _Vision(), _Studio(storage), _Publisher(), source, ia=_IA()
            )
            try:
                processed = coordinator.run_catch_up()
                self.assertEqual(processed, ["501", "502"])
                self.assertEqual(source.calls, 3)
                self.assertEqual(db.get("501").state, State.RECOVERY)
                self.assertEqual(db.get("502").state, State.PUBLISHED)
                self.assertFalse(db.historical_complete())
            finally:
                coordinator.close()

    def test_recovery_progress_resets_historical_scan_before_rescan(self):
        class Source:
            def __init__(self, db):
                self.db = db
                self.scan = 0
                self.reset_calls = 0
                self.checkpoints = []

            async def fetch_next_async(self):
                self.scan += 1
                if self.scan == 1:
                    return self._message("501")
                if self.scan == 2:
                    return self._message("502")
                if self.scan == 3:
                    return None
                if self.scan == 4:
                    return self._message("503")
                if self.scan == 5:
                    return self._message("504")
                return None

            @staticmethod
            def _message(item_id):
                async def materialize(target):
                    target.write_bytes(item_id.encode())
                return SimpleNamespace(
                    telegram_message_id=item_id,
                    source_id="telegram",
                    topic_id=1,
                    topic_name="topic",
                    original_url="https://shopee.example/" + item_id,
                    materialize=materialize,
                )

            def reset_historical_scan(self):
                self.reset_calls += 1
                self.scan = 3

            def mark_ingested(self, _message_id):
                pass

            def commit_live_checkpoints(self, checkpoints):
                self.checkpoints.append(dict(checkpoints))

            def complete_historical_sync(self):
                self.db.complete_historical_sync()

        class CoordinatorUnderTest(Coordinator):
            def run(self, item_id):
                if item_id == "501" and self.db.get(item_id).state != State.PUBLISHED:
                    self.db.transition(item_id, State.RECOVERY, "synthetic")
                    raise RuntimeError("synthetic")
                self.db.transition(item_id, State.PUBLISHED, "synthetic")
                self.db.mark_cleanup_completed(item_id)

            def recover_pending(self):
                item = self.db.get("501")
                if item.state == State.RECOVERY:
                    self.db.transition(item.item_id, State.PUBLISHED, "recovered")
                    self.db.mark_cleanup_completed(item.item_id)
                    return ["503"]
                return []

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            effect = root / "ArmoredSpeech" / "assets" / "efeitosonoro.wav"
            effect.parent.mkdir(parents=True, exist_ok=True)
            effect.write_bytes(b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + (8000).to_bytes(4, "little") + (16000).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little") + b"data" + (0).to_bytes(4, "little"))
            studio_assets = root / "ArmoredStudio" / "assets"
            studio_assets.mkdir(parents=True, exist_ok=True)
            (studio_assets / "banner.png").write_bytes(b"fixture")
            storage = Storage(root)
            db = Database(storage.database / "db.sqlite")
            source = Source(db)
            coordinator = CoordinatorUnderTest(
                db, storage, _Vision(), _Studio(storage), _Publisher(), source
            )
            try:
                import asyncio
                asyncio.run(coordinator._run_catch_up_with_recovery_async())
                self.assertEqual(source.reset_calls, 1)
                self.assertTrue(db.historical_complete())
                self.assertEqual(db.get("501").state, State.PUBLISHED)
                self.assertEqual(db.get("502").state, State.PUBLISHED)
            finally:
                coordinator.close()

    def test_failed_materialization_gets_one_same_run_rediscovery(self):
        class Source:
            def __init__(self, db):
                self.db = db
                self.index = 0
                self.fail_once = True
                self.reset_calls = 0
                self.checkpoints = []
                self.rediscovering = False

            async def fetch_next_async(self):
                if self.rediscovering:
                    self.rediscovering = False
                    item_id = "503"
                elif self.index >= 3:
                    return None
                else:
                    item_id = ("503", "504")[self.index] if self.index < 2 else None
                    self.index += 1
                    if item_id is None:
                        return None

                async def materialize(target):
                    # Materialization failure is represented in the first pass
                    # before the candidate is committed to production state.
                    if item_id == "503" and self.fail_once:
                        self.fail_once = False
                        raise TimeoutError("synthetic-download-timeout")
                    target.write_bytes(item_id.encode())

                return SimpleNamespace(
                    telegram_message_id=item_id,
                    source_id="telegram",
                    topic_id=1,
                    topic_name="topic",
                    original_url="https://shopee.example/" + item_id,
                    materialize=materialize,
                )

            def reset_historical_scan(self):
                self.reset_calls += 1
                # A one-time rediscovery resumes the iterator after the failed
                # candidate; it must not replay the already successful 504.
                self.rediscovering = True

            def mark_ingested(self, _message_id):
                pass

            def mark_materialization_failed(self):
                pass

            historical_materialization_failed = False
            historical_scan_exhausted = True

            def commit_live_checkpoints(self, checkpoints):
                self.checkpoints.append(dict(checkpoints))

            def complete_historical_sync(self):
                self.db.complete_historical_sync()

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            effect = root / "ArmoredSpeech" / "assets" / "efeitosonoro.wav"
            effect.parent.mkdir(parents=True, exist_ok=True)
            effect.write_bytes(
                b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt "
                + (16).to_bytes(4, "little") + (1).to_bytes(2, "little")
                + (1).to_bytes(2, "little") + (8000).to_bytes(4, "little")
                + (16000).to_bytes(4, "little") + (2).to_bytes(2, "little")
                + (16).to_bytes(2, "little") + b"data" + (0).to_bytes(4, "little")
            )
            studio_assets = root / "ArmoredStudio" / "assets"
            studio_assets.mkdir(parents=True, exist_ok=True)
            (studio_assets / "banner.png").write_bytes(b"fixture")
            storage = Storage(root)
            db = Database(storage.database / "db.sqlite")
            source = Source(db)
            coordinator = Coordinator(
                db, storage, _Vision(), _Studio(storage), _Publisher(), source, ia=_IA()
            )
            install_synthetic_speech_studio(coordinator)
            try:
                import asyncio
                asyncio.run(coordinator._run_catch_up_with_recovery_async())
                self.assertEqual(source.reset_calls, 1)
                # Sync's failed materialization marker blocks cutover for that
                # pass, but the wrapper makes one bounded rediscovery; after
                # it succeeds, the historical batch may complete.
                self.assertTrue(db.historical_complete())
                self.assertEqual(db.get("503").state, State.PUBLISHED)
                self.assertEqual(db.get("504").state, State.PUBLISHED)
            finally:
                coordinator.close()

    def test_published_cleanup_pending_is_recovered_on_startup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            storage = Storage(root)
            db = Database(storage.database / "db.sqlite")
            item_id = db.create_item(
                "cleanup-pending",
                storage.original("cleanup-pending"),
                original_url="https://shopee.example/product",
            )
            original = db.get(item_id).original_path
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(b"original")
            db.transition(item_id, State.PUBLISHED, "synthetic-published")
            db.set_result(item_id, storage.result(item_id, "https://example.invalid/a", "affiliate"))
            calls = []

            coordinator = Coordinator(db, storage, None, None, None, None)
            coordinator.recover = lambda value: calls.append(value)
            try:
                recovered = coordinator.recover_pending()
                self.assertEqual(recovered, [item_id])
                self.assertEqual(calls, [item_id])
            finally:
                coordinator.close()

    def test_database_migration_does_not_drop_legacy_vision_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "db.sqlite"
            db = Database(path)
            db.conn.execute(
                "CREATE TABLE vision_candidates (id INTEGER PRIMARY KEY, evidence TEXT)"
            )
            db.conn.execute(
                "INSERT INTO vision_candidates(id,evidence) VALUES(1,'historical')"
            )
            db.conn.commit()
            db.close()

            reopened = Database(path)
            try:
                row = reopened.conn.execute(
                    "SELECT evidence FROM vision_candidates WHERE id=1"
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["evidence"], "historical")
            finally:
                reopened.close()

    def test_ia_unexpected_runtime_error_is_recovery(self):
        class FailingIA:
            def generate_caption(self, context):
                raise RuntimeError("unexpected-programming-error")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            storage = Storage(root)
            db = Database(storage.database / "db.sqlite")
            original = storage.original("ia-runtime", ".mp4", original_url="https://shopee.example/product")
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(b"original")
            item_id = db.create_item(
                "ia-runtime",
                original,
                original_url="https://shopee.example/product",
            )
            try:
                class VisionResolved:
                    def identify(self, item):
                        return VisionResult(
                            "Produto",
                            "https://example.invalid/a",
                            ia_context={"productName": "Produto"},
                        )

                with self.assertRaisesRegex(RuntimeError, "unexpected-programming-error"):
                    from armored_core.pipeline import Pipeline
                    Pipeline(
                        db,
                        storage,
                        VisionResolved(),
                        _Studio(storage),
                        _Publisher(),
                        FailingIA(),
                    ).run(item_id)

                self.assertEqual(db.get(item_id).state, State.RECOVERY)
            finally:
                db.close()

    def test_ia_missing_key_is_provider_error(self):
        old_key = os.environ.pop("GEMINI_API_KEY", None)
        old_enabled = os.environ.get("ARMORED_IA_CAPTION_ENABLED")
        os.environ["ARMORED_IA_CAPTION_ENABLED"] = "1"
        try:
            with self.assertRaisesRegex(Exception, "GEMINI_API_KEY ausente"):
                CaptionGenerator(provider=GeminiProvider()).generate({
                    "productName": "Produto"
                })
        finally:
            os.environ.pop("ARMORED_IA_CAPTION_ENABLED", None)
            if old_enabled is not None:
                os.environ["ARMORED_IA_CAPTION_ENABLED"] = old_enabled
            if old_key is not None:
                os.environ["GEMINI_API_KEY"] = old_key


if __name__ == "__main__":
    unittest.main()
