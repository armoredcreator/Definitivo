"""Deterministic Speech/Studio seam for Coordinator orchestration tests."""
from __future__ import annotations

import json
from pathlib import Path

from ArmoredSpeech.contracts import AudioClass, SpeechDecision
from armored_core.storage import Storage


class SyntheticSpeechProcessor:
    def analyze(self, _video_path: Path) -> SpeechDecision:
        return SpeechDecision(
            audio_class=AudioClass.MUSIC_ONLY,
            language=None,
            speech_detected=False,
            music_detected=True,
            confidence=0.99,
            rationale="Synthetic Coordinator contract test; no RVC requested.",
        )

    def prepare_wav(self, _video_path: Path, wav_path: Path, _decision: SpeechDecision) -> None:
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path.write_bytes(b"synthetic-test-wav")


def install_synthetic_speech_studio(coordinator) -> None:
    """Keep Coordinator orchestration real while simulating expensive media engines."""
    coordinator._speech_processor_override = SyntheticSpeechProcessor()
    coordinator.recovery.speech_studio_runner = coordinator._run_recovery_speech_studio
    coordinator.recovery._has_speech_studio_v5_completion = lambda _item_id: True

    def run_studio(*, root, manifest_path, speech_database, report_path, copy_only, storage_root):
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        storage = Storage(Path(root))
        studio = getattr(coordinator.pipeline, "studio", None)
        processed = []
        for entry in manifest["items"]:
            message_id = str(entry["telegram_message_id"])
            events = getattr(studio, "events", None)
            if isinstance(events, list):
                events.append(("studio", message_id))
            started = getattr(studio, "studio_started", None)
            if started is not None and message_id != "999":
                started.set()
            source = getattr(coordinator, "source", None)
            if source is not None and hasattr(source, "studio_started") and message_id != "999":
                source.studio_started.set()
            output = storage.result(
                str(entry["content_id"]),
                affiliate_url=entry.get("affiliate_url"),
                affiliate_name=entry.get("affiliate_name"),
                source_id=entry.get("source_id"),
            )
            original = Path(entry["original_path"])
            output.write_bytes(original.read_bytes() + b"-synthetic-studio-output")
            processed.append({
                "source_id": str(entry["source_id"]),
                "item_id": str(entry["telegram_message_id"]),
                "original_sha256_before": str(entry["original_sha256"]),
                "output_path": str(output.resolve()),
            })
        report = {"status": "SUCCESS", "originals_intact": True, "processed": processed}
        Path(report_path).write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        return report

    coordinator._speech_studio_batch_runner_override = run_studio
    coordinator._speech_processor_override = SyntheticSpeechProcessor()
    # Coordinator lifecycle tests use isolated roots with no model/effect
    # assets. The preflight remains covered directly by its dedicated tests.
    coordinator._preflight_speech_studio_v5 = lambda: coordinator._speech_processor_override



def build_test_coordinator(root: Path, bindings):
    """Build through production composition, with only media engines injected."""
    from armored_core.coordinator import Coordinator

    coordinator = Coordinator.build(root, bindings)
    install_synthetic_speech_studio(coordinator)
    return coordinator
