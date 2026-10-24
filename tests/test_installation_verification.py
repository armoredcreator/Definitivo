from pathlib import Path

from scripts.verify_installation import is_private_path, sha256_file


def test_integrity_manifest_refuses_private_runtime_paths():
    for path in (
        "credentials/project.env",
        "credentials/telegram/session/account.session",
        "storage/database/armoredcreator.db",
        "runtime/models/audio/model.bin",
        "runtime/telegram-bot-api/telegram-bot-api.exe",
        "ArmoredSpeech/runtime/rvc/models/melody.pth",
        "ArmoredSpeech/assets/efeitosonoro.wav",
        ".env",
    ):
        assert is_private_path(path)


def test_integrity_manifest_allows_versioned_project_templates():
    assert not is_private_path(".env.example")
    assert not is_private_path("requirements-runtime311.lock.txt")
    assert not is_private_path("ArmoredSpeech/audio_intelligence.py")


def test_sha256_file_hashes_content(tmp_path: Path):
    asset = tmp_path / "asset.txt"
    asset.write_bytes(b"armoredcreator")

    assert sha256_file(asset) == "f8ef2e30d1cefd1b04d38c945b5c67115a10e320c2462f9e1008cbe583222081"
