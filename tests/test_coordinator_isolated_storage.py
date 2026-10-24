from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from armored_core.coordinator import Coordinator


def test_coordinator_build_keeps_database_and_media_in_explicit_clone_root(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    clone_storage = project / "work" / "integration-clone"
    coordinator = Coordinator.build(
        project,
        bindings=SimpleNamespace(
            vision=object(), studio=object(), publisher=object(), source=object(), ia=object(),
        ),
        storage_root=clone_storage,
    )
    try:
        assert coordinator.storage.root == project.resolve()
        assert coordinator.storage.storage_root == clone_storage.resolve()
        assert coordinator.db.path == clone_storage / "storage" / "database" / "armoredcreator.db"
        assert coordinator.pipeline.trace.path == clone_storage / "storage" / "logs" / "pipeline_trace.jsonl"
    finally:
        coordinator.close()
