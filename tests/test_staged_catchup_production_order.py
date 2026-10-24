import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

from armored_core.coordinator import Coordinator
from armored_core.database import Database
from armored_core.models import PublicationCheck, State
from armored_core.services import (
    PublicationResult,
    StudioResult,
    VisionResult,
    VisionUnresolvedError,
)
from armored_core.storage import Storage
from coordinator_test_support import install_synthetic_speech_studio


SOURCE_IDS = ("source-1", "source-2", "source-3")


class HistorySource:
    def __init__(self, root, events, candidates, db):
        self.root = Path(root)
        self.events = events
        self.candidates = candidates
        self.db = db
        self.sources = tuple(SimpleNamespace(source_id=value) for value in SOURCE_IDS)
        self.historical_scan_exhausted = False
        self.historical_materialization_failed = False
        self.completed = False

    async def iter_historical_candidates_async(self):
        for candidate in self.candidates:
            self.events.append(("discover", candidate.source_id, candidate.message_id))
            yield SimpleNamespace(
                telegram_message_id=candidate.message_id,
                source_id=candidate.source_id,
                topic_id=100 + int(candidate.message_id),
                topic_name="fixture",
                original_url=getattr(
                    candidate,
                    "original_url",
                    f"https://shopee.example/{candidate.message_id}",
                ),
                source_path=None,
                materialize=lambda _target: (_ for _ in ()).throw(
                    AssertionError("history scan must not download")
                ),
            )
        self.historical_scan_exhausted = True

    def mark_ingested(self, _message_id):
        pass

    def mark_materialization_failed(self):
        self.historical_materialization_failed = True

    async def materialize_candidate_async(self, source_id, message_id, target):
        vision_events = [event for event in self.events if event[0] == "vision"]
        assert len(vision_events) >= len(self.candidates)
        self.events.append(("download", str(source_id), str(message_id)))
        Path(target).write_bytes(f"original-{message_id}".encode())

    def complete_historical_sync(self):
        self.completed = True
        self.db.complete_historical_sync()
        self.events.append(("historical-complete",))

    def is_historical_complete(self):
        return self.completed


class Vision:
    def __init__(self, events, fail_on=None):
        self.events = events
        self.fail_on = fail_on

    def identify(self, item):
        self.events.append(("vision", item.source_id, item.telegram_message_id))
        if item.telegram_message_id == self.fail_on:
            raise RuntimeError("temporary affiliate API outage")
        if not item.original_url:
            raise VisionUnresolvedError("no exact product offer")
        return VisionResult(
            "radio automotivo",
            f"https://affiliate.example/offer-{item.telegram_message_id}",
            ia_context={"productName": "radio automotivo"},
        )


class ValidIA:
    def generate_caption(self, _context):
        return "🧡 Radio bonita\n#radio"

    def generate_caption_with_evidence(self, context):
        from ArmoredIA.caption.generator import CaptionGenerationResult
        from ArmoredIA.caption.selector import CaptionCandidateEvaluation, CaptionSelection

        caption = self.generate_caption(context)
        evaluation = CaptionCandidateEvaluation(
            index=0, caption=caption, policy_valid=True, rejection_reason=None,
            score=1.0, selected=True,
        )
        return CaptionGenerationResult(
            caption=caption,
            selection=CaptionSelection(caption=caption, index=0, score=1.0),
            evaluations=(evaluation,),
            batch_id="staged-catch-up-caption",
        )


class Studio:
    def __init__(self, storage, events):
        self.storage = storage
        self.events = events

    def process(self, item):
        self.events.append(("studio", item.telegram_message_id))
        working = self.storage.working(item.content_id, item.source_id)
        result = self.storage.result(item.content_id, source_id=item.source_id)
        working.write_bytes(item.original_path.read_bytes())
        result.write_bytes(b"processed-" + item.original_path.read_bytes())
        return StudioResult(working, result)


class Publisher:
    def __init__(self, events):
        self.events = events
        self.calls = []

    def check_publication(self, _item):
        return PublicationCheck.ABSENT

    def publish(self, item):
        self.events.append(("published", item.telegram_message_id))
        self.calls.append(item.telegram_message_id)
        return PublicationResult(True, f"telegram-{item.telegram_message_id}")


class LiveDuringCatchUpSource(HistorySource):
    def __init__(self, root, events, candidates, db, studio_started):
        super().__init__(root, events, candidates, db)
        self.studio_started = studio_started
        self.live_vision_finished = threading.Event()
        self.live_message = SimpleNamespace(
            telegram_message_id="999",
            source_id=SOURCE_IDS[0],
            topic_id=999,
            topic_name="live-fixture",
            original_url="https://shopee.example/live",
            materialize=lambda target: Path(target).write_bytes(b"live-fixture-original"),
        )
        self.live_pending = False
        self.live_polled = False
        self.live_checkpoint_committed = False
        self.discovery_checkpoint_committed = False

    def commit_historical_discovery_checkpoints(self):
        self.discovery_checkpoint_committed = True
        self.events.append(("discovery-checkpoints-committed",))

    async def fetch_live_candidate_async(self):
        if self.live_pending:
            self.live_polled = True
            return self.live_message, {999: 999}
        if self.live_polled:
            return None, {}
        await asyncio.to_thread(self.studio_started.wait, 2)
        if not self.studio_started.is_set():
            return None, {}
        self.live_pending = True
        self.live_polled = True
        self.events.append(("live-discovered",))
        return self.live_message, {999: 999}

    def commit_live_checkpoints(self, _checkpoints):
        self.live_checkpoint_committed = True
        self.live_pending = False
        self.events.append(("live-checkpoint-committed",))


class BoundedLiveSource(LiveDuringCatchUpSource):
    async def iter_historical_candidates_async(self):
        candidate = self.candidates[0]
        self.events.append(("discover", candidate.source_id, candidate.message_id))
        yield SimpleNamespace(
            telegram_message_id=candidate.message_id,
            source_id=candidate.source_id,
            topic_id=100 + int(candidate.message_id),
            topic_name="fixture",
            original_url=f"https://shopee.example/{candidate.message_id}",
            source_path=None,
            materialize=lambda _target: None,
        )
        self.historical_scan_exhausted = False


class ConcurrentVision(Vision):
    def identify(self, item):
        result = super().identify(item)
        if item.telegram_message_id == "999":
            self.live_finished.set()
        return result

    def __init__(self, events, live_finished):
        super().__init__(events)
        self.live_finished = live_finished


class ConcurrentStudio(Studio):
    def __init__(self, storage, events, studio_started, live_vision_finished):
        super().__init__(storage, events)
        self.studio_started = studio_started
        self.live_vision_finished = live_vision_finished
        self.waited_for_live_vision = False

    def process(self, item):
        if item.telegram_message_id == "101" and not self.waited_for_live_vision:
            self.waited_for_live_vision = True
            self.studio_started.set()
            assert self.live_vision_finished.wait(3)
        return super().process(item)


class FailingLiveVision(Vision):
    def __init__(self, events, live_attempted):
        super().__init__(events)
        self.live_attempted = live_attempted

    def identify(self, item):
        if item.telegram_message_id == "999":
            self.events.append(("live-vision-failed",))
            self.live_attempted.set()
            raise RuntimeError("temporary live Vision outage")
        return super().identify(item)


def _coordinator(tmp_path, events, candidates, fail_on=None):
    storage = Storage(tmp_path)
    db = Database(storage.database / "armoredcreator.db")
    source = HistorySource(tmp_path, events, candidates, db)
    publisher = Publisher(events)
    coordinator = Coordinator(
        db,
        storage,
        Vision(events, fail_on=fail_on),
        Studio(storage, events),
        publisher,
        source=source,
        ia=ValidIA(),
    )
    install_synthetic_speech_studio(coordinator)
    return coordinator, source, publisher


def test_integrated_catchup_processes_each_approved_video_sequentially(tmp_path):
    candidates = [
        SimpleNamespace(source_id=SOURCE_IDS[0], message_id="101"),
        SimpleNamespace(source_id=SOURCE_IDS[1], message_id="202"),
        SimpleNamespace(source_id=SOURCE_IDS[2], message_id="303"),
    ]
    events = []
    coordinator, source, publisher = _coordinator(tmp_path, events, candidates)
    try:
        processed = __import__("asyncio").run(
            coordinator._run_staged_catch_up_async()
        )

        assert publisher.calls == ["101", "202", "303"]
        assert source.completed
        assert coordinator.db.historical_complete()
        assert all(
            coordinator.db.get(f"{candidate.source_id}_{candidate.message_id}").state
            == State.PUBLISHED
            for candidate in candidates
        )
        assert all(
            coordinator.db.get(f"{candidate.source_id}_{candidate.message_id}")
            .result_path.is_file()
            for candidate in candidates
        )

        first_download = next(i for i, event in enumerate(events) if event[0] == "download")
        last_vision = max(i for i, event in enumerate(events) if event[0] == "vision")
        downloads = [i for i, event in enumerate(events) if event[0] == "download"]
        assert last_vision < downloads[0]
        for index, message_id in enumerate(("101", "202", "303")):
            source_id = next(
                candidate.source_id for candidate in candidates
                if candidate.message_id == message_id
            )
            download_index = events.index(("download", source_id, message_id))
            studio_index = events.index(("studio", message_id))
            published_index = events.index(("published", message_id))
            assert download_index < studio_index < published_index
            if index + 1 < len(downloads):
                assert published_index < downloads[index + 1]
        assert processed
    finally:
        coordinator.close()


def test_live_discovery_and_vision_continue_during_historical_studio(tmp_path):
    candidates = [
        SimpleNamespace(source_id=SOURCE_IDS[0], message_id="101"),
    ]
    events = []
    storage = Storage(tmp_path)
    db = Database(storage.database / "armoredcreator.db")
    studio_started = threading.Event()
    live_vision_finished = threading.Event()
    source = LiveDuringCatchUpSource(
        tmp_path,
        events,
        candidates,
        db,
        studio_started,
    )
    publisher = Publisher(events)
    coordinator = Coordinator(
        db,
        storage,
        ConcurrentVision(events, live_vision_finished),
        ConcurrentStudio(storage, events, studio_started, live_vision_finished),
        publisher,
        source=source,
            ia=ValidIA(),
    )
    install_synthetic_speech_studio(coordinator)
    try:
        asyncio.run(coordinator._run_staged_catch_up_async())

        assert source.discovery_checkpoint_committed
        assert source.live_checkpoint_committed
        assert publisher.calls == ["101", "999"]
        assert source.completed
        assert coordinator.db.historical_complete()
        assert coordinator.db.get("source-1_999").state == State.PUBLISHED
        assert events.index(("live-discovered",)) < events.index(("published", "101"))
        assert events.index(("vision", SOURCE_IDS[0], "999")) < events.index(
            ("published", "101")
        )
    finally:
        coordinator.close()


def test_bounded_history_does_not_start_live_discovery_or_cut_over(tmp_path):
    candidates = [
        SimpleNamespace(source_id=SOURCE_IDS[0], message_id="101"),
    ]
    events = []
    storage = Storage(tmp_path)
    db = Database(storage.database / "armoredcreator.db")
    studio_started = threading.Event()
    source = BoundedLiveSource(
        tmp_path,
        events,
        candidates,
        db,
        studio_started,
    )
    publisher = Publisher(events)
    coordinator = Coordinator(
        db,
        storage,
        Vision(events),
        Studio(storage, events),
        publisher,
        source=source,
            ia=ValidIA(),
    )
    install_synthetic_speech_studio(coordinator)
    try:
        asyncio.run(coordinator._run_staged_catch_up_async())

        assert publisher.calls == ["101"]
        assert not source.discovery_checkpoint_committed
        assert not source.live_checkpoint_committed
        assert not any(event[0] == "live-discovered" for event in events)
        assert not source.completed
        assert not coordinator.db.historical_complete()
    finally:
        coordinator.close()


def test_live_vision_failure_keeps_checkpoint_and_blocks_historical_cutover(tmp_path):
    candidates = [
        SimpleNamespace(source_id=SOURCE_IDS[0], message_id="101"),
    ]
    events = []
    storage = Storage(tmp_path)
    db = Database(storage.database / "armoredcreator.db")
    studio_started = threading.Event()
    live_attempted = threading.Event()
    source = LiveDuringCatchUpSource(
        tmp_path,
        events,
        candidates,
        db,
        studio_started,
    )
    studio = ConcurrentStudio(
        storage,
        events,
        studio_started,
        live_attempted,
    )
    publisher = Publisher(events)
    coordinator = Coordinator(
        db,
        storage,
        FailingLiveVision(events, live_attempted),
        studio,
        publisher,
        source=source,
            ia=ValidIA(),
    )
    install_synthetic_speech_studio(coordinator)
    try:
        asyncio.run(coordinator._run_staged_catch_up_async())

        pending = coordinator.db.get("source-1_999")
        assert pending.state == State.VISION
        assert not pending.original_path.exists()
        assert not source.live_checkpoint_committed
        assert publisher.calls == ["101"]
        assert not source.completed
        assert not coordinator.db.historical_complete()
    finally:
        coordinator.close()


def test_retryable_vision_failure_does_not_download_or_mark_history_complete(tmp_path):
    candidates = [
        SimpleNamespace(source_id=SOURCE_IDS[0], message_id="101"),
        SimpleNamespace(source_id=SOURCE_IDS[1], message_id="202"),
    ]
    events = []
    coordinator, source, publisher = _coordinator(
        tmp_path, events, candidates, fail_on="101"
    )
    try:
        __import__("asyncio").run(coordinator._run_staged_catch_up_async())

        item = coordinator.db.get("source-1_101")
        assert item.state == State.VISION
        assert coordinator.db.last_error(item.content_id)
        assert not item.original_path.exists()
        assert not any(event[0] == "download" for event in events)
        assert publisher.calls == []
        assert not source.completed
        assert not coordinator.db.historical_complete()
    finally:
        coordinator.close()


def test_waiting_vision_is_terminal_classification_not_technical_failure(tmp_path):
    candidates = [
        SimpleNamespace(source_id=SOURCE_IDS[0], message_id="101"),
        SimpleNamespace(source_id=SOURCE_IDS[1], message_id="202"),
    ]
    events = []
    coordinator, source, publisher = _coordinator(tmp_path, events, candidates)
    candidates[0].original_url = None
    try:
        __import__("asyncio").run(coordinator._run_staged_catch_up_async())

        waiting = coordinator.db.get("source-1_101")
        published = coordinator.db.get("source-2_202")
        assert waiting.state == State.WAITING_VISION
        assert not waiting.original_path.exists()
        assert published.state == State.PUBLISHED
        assert source.completed
        assert coordinator.db.historical_complete()
        assert publisher.calls == ["202"]
    finally:
        coordinator.close()
