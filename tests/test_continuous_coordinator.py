import tempfile
import unittest
from pathlib import Path

from armored_core.coordinator import Coordinator
from armored_core.database import Database
from armored_core.models import PublicationCheck, State
from armored_core.services import PublicationResult, StudioResult, VisionResult
from armored_core.storage import Storage
from coordinator_test_support import install_synthetic_speech_studio


class _Vision:
    def identify(self, item):
        return VisionResult(
            "radio automotivo",
            "https://shopee.example/affiliate",
            ia_context={"productName": "radio automotivo"},
        )


class _IA:
    def generate_caption(self, _context):
        return "🧡 Radio bonito\n#radio"


class _Studio:
    def __init__(self, storage):
        self.storage = storage

    def process(self, item):
        working = self.storage.working(item.content_id)
        result = self.storage.result(item.content_id, affiliate_url=item.affiliate_url, affiliate_name=item.affiliate_name)
        payload = item.original_path.read_bytes()
        working.write_bytes(payload)
        result.write_bytes(payload + b"-final")
        return StudioResult(working, result)


class _Publisher:
    def __init__(self):
        self.published = []

    def check_publication(self, item):
        return PublicationCheck.ABSENT

    def publish(self, item):
        self.published.append(item.content_id)
        return PublicationResult(True, "telegram-" + item.content_id)


class _LiveSource:
    def __init__(self, db):
        self.db = db
        self.connected = False
        self.messages = ["live-1"]
        self.done = False
        self.checkpoints_committed = None

    async def fetch_live_batch_async(self):
        self.connected = True
        if self.done:
            return [], {}
        self.done = True

        async def materialize(target):
            target.write_bytes(b"LIVE")

        from types import SimpleNamespace
        return [SimpleNamespace(
            telegram_message_id="live-1",
            source_id="telegram",
            topic_id=901,
            topic_name="topic",
            original_url="https://shopee.example/source",
            materialize=materialize,
        )], {901: 100}

    async def disconnect(self):
        self.connected = False

    def mark_ingested(self, message_id):
        pass

    def commit_live_checkpoints(self, checkpoints):
        self.checkpoints_committed = dict(checkpoints)
        for topic_id, message_id in checkpoints.items():
            self.db.set_sync_topic_checkpoint(topic_id, "topic", message_id)


class _LiveSourceWithTransientMaterializationFailure(_LiveSource):
    def __init__(self, db):
        super().__init__(db)
        self.attempts = 0

    async def fetch_live_batch_async(self):
        self.connected = True
        self.attempts += 1

        async def materialize(target):
            if self.attempts == 1:
                raise TimeoutError("download Telegram excedeu o timeout")
            target.write_bytes(b"LIVE-RETRY")

        from types import SimpleNamespace
        return [SimpleNamespace(
            telegram_message_id="live-fail-then-retry",
            source_id="telegram",
            topic_id=901,
            topic_name="topic",
            original_url="https://shopee.example/source",
            materialize=materialize,
        )], {901: 101 if self.attempts == 1 else 102}





class _LiveSourceSerialized(_LiveSource):
    def __init__(self, db, events):
        super().__init__(db)
        self.events = events
        self.index = 0

    async def fetch_live_candidate_async(self):
        self.connected = True
        self.events.append("discover")
        from types import SimpleNamespace
        remaining = ["live-1", "live-2"][self.index:]
        if not remaining:
            return None, {}
        message_id = remaining[0]

        async def materialize(target, message_id=message_id):
            self.events.append("materialize:" + message_id)
            target.write_bytes(message_id.encode())

        self.index += 1
        return SimpleNamespace(
            telegram_message_id=message_id,
            source_id="telegram",
            topic_id=901,
            topic_name="topic",
            original_url="https://shopee.example/source",
            materialize=materialize,
        ), {901: 99 + self.index}





class _RecordingCoordinator(Coordinator):
    def __init__(self, *args, events, **kwargs):
        super().__init__(*args, **kwargs)
        self._events = events

    def run(self, item_id: str) -> None:
        self._events.append("pipeline:" + str(item_id))
        super().run(item_id)


class ContinuousCoordinatorTests(unittest.TestCase):
    def test_live_materializes_and_processes_strictly_one_at_a_time(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            storage = Storage(root)
            db = Database(storage.database / "db.sqlite")
            db.complete_historical_sync()
            db.set_sync_topic_checkpoint(901, "topic", 99)
            events = []
            source = _LiveSourceSerialized(db, events)
            publisher = _Publisher()

            coordinator = _RecordingCoordinator(
                db, storage, _Vision(), _Studio(storage), publisher, source, ia=_IA(), events=events
            )
            # The production preflight requires immutable runtime assets.
            # This test targets orchestration, so create its local fixture and
            # preserve the production gate unchanged.
            (root / "ArmoredSpeech" / "assets").mkdir(parents=True, exist_ok=True)
            (root / "ArmoredSpeech" / "assets" / "efeitosonoro.wav").write_bytes(b"fixture")
            install_synthetic_speech_studio(coordinator)

            try:
                coordinator.run_forever(max_cycles=1, poll_seconds=0)
                # LIVE is strictly serialized: discovery itself is limited
                # to one candidate, then that candidate is materialized and
                # completes the pipeline before the next discovery.
                self.assertEqual(events, [
                    "discover",
                    "materialize:live-1",
                    "pipeline:live-1",
                ])
                self.assertEqual(publisher.published, ["live-1"])
                self.assertEqual(db.get("live-1").state, State.PUBLISHED)
                self.assertIsNone(db.conn.execute("SELECT 1 FROM items WHERE content_id=?", ("live-2",)).fetchone())
                self.assertEqual(source.checkpoints_committed, {901: 100})
            finally:
                coordinator.close()




    def test_live_pipeline_failure_does_not_advance_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            storage = Storage(root)
            db = Database(storage.database / "db.sqlite")
            db.complete_historical_sync()
            db.set_sync_topic_checkpoint(901, "topic", 99)
            events = []
            source = _LiveSourceSerialized(db, events)

            class FailingCoordinator(Coordinator):
                def run(self, item_id: str) -> None:
                    events.append("pipeline:" + str(item_id))
                    raise RuntimeError("synthetic pipeline failure")

            coordinator = FailingCoordinator(
                db, storage, _Vision(), _Studio(storage), _Publisher(), source
            )
            try:
                coordinator.run_live_once()
                self.assertEqual(events, [
                    "discover",
                    "materialize:live-1",
                    "pipeline:live-1",
                ])
                self.assertIsNone(source.checkpoints_committed)
                self.assertEqual(db.sync_topic_checkpoint(901), 99)
                self.assertEqual(db.get("live-1").state, State.RECEIVED)
            finally:
                coordinator.close()

    def test_run_forever_processes_live_then_restarts_without_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            storage = Storage(root)
            db = Database(storage.database / "db.sqlite")
            db.complete_historical_sync()
            db.set_sync_topic_checkpoint(901, "topic", 99)
            source = _LiveSource(db)
            publisher = _Publisher()
            coordinator = Coordinator(db, storage, _Vision(), _Studio(storage), publisher, source, ia=_IA())
            install_synthetic_speech_studio(coordinator)

            restarted = None
            try:
                coordinator.run_forever(max_cycles=2, poll_seconds=0)
                self.assertEqual(publisher.published, ["live-1"])
                self.assertEqual(db.get("live-1").state, State.PUBLISHED)
                self.assertEqual(source.checkpoints_committed, {901: 100})

                restarted_db = Database(storage.database / "db.sqlite")
                restarted_source = _LiveSource(restarted_db)
                restarted_source.done = True
                restarted = Coordinator(
                    restarted_db, storage, _Vision(), _Studio(storage), publisher, restarted_source
                )
                install_synthetic_speech_studio(restarted)
                restarted.run_forever(max_cycles=1, poll_seconds=0)

                self.assertEqual(publisher.published, ["live-1"])
                self.assertEqual(restarted_db.get("live-1").state, State.PUBLISHED)
            finally:
                if restarted is not None:
                    restarted.close()
                coordinator.close()


    def test_live_materialization_failure_does_not_kill_coordinator(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            storage = Storage(root)
            db = Database(storage.database / "db.sqlite")
            db.complete_historical_sync()
            db.set_sync_topic_checkpoint(901, "topic", 100)
            source = _LiveSourceWithTransientMaterializationFailure(db)
            publisher = _Publisher()
            coordinator = Coordinator(db, storage, _Vision(), _Studio(storage), publisher, source, ia=_IA())
            install_synthetic_speech_studio(coordinator)

            try:
                coordinator.run_forever(max_cycles=2, poll_seconds=0)

                item = db.get("live-fail-then-retry")
                self.assertEqual(item.state, State.PUBLISHED)
                self.assertEqual(publisher.published, ["live-fail-then-retry"])
                self.assertEqual(source.checkpoints_committed, {901: 102})
            finally:
                coordinator.close()



if __name__ == "__main__":
    unittest.main()
