from __future__ import annotations

from pathlib import Path

from ArmoredSpeech import rvc_engine


def test_rvc_engine_is_owned_by_armoredspeech():
    repo_root = Path(__file__).resolve().parents[2]
    speech_root = repo_root / "ArmoredSpeech"

    assert rvc_engine.REPO_ROOT == repo_root
    assert rvc_engine.SPEECH_ROOT == speech_root
    assert Path(rvc_engine.__file__).resolve().parent == speech_root
    assert rvc_engine.SHARED_ENV_DIR == repo_root / ".venv"
    assert rvc_engine.BASE_DIR == speech_root


def test_rvc_models_have_one_canonical_speech_runtime_root():
    repo_root = Path(__file__).resolve().parents[2]
    expected_root = (repo_root / "ArmoredSpeech" / "runtime" / "rvc").resolve()

    assert rvc_engine.RVC_ROOT == expected_root
    assert rvc_engine.MODELS_DIR == expected_root / "models"
    assert Path(rvc_engine.MODELS_DIR).parts[-3:] == ("runtime", "rvc", "models")


def test_legacy_rvc_root_environment_variable_cannot_redirect_runtime(monkeypatch):
    # The engine root is a code-level ownership boundary, not an env fallback
    # that could silently continue to use ArmoredStudio/runtime/rvc.
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("ARMORED_RVC_ROOT", str(repo_root / "ArmoredStudio" / "runtime" / "rvc"))
    assert rvc_engine.RVC_ROOT == (repo_root / "ArmoredSpeech" / "runtime" / "rvc").resolve()


def test_studio_has_no_importable_rvc_entry_point():
    from ArmoredStudio import unified

    assert not hasattr(unified, "converter_voz")
    assert not hasattr(unified, "rvc")


def test_shared_runtime_declares_exact_python_patch_before_installation():
    repo_root = Path(__file__).resolve().parents[2]
    assert (repo_root / ".python-version").read_text().strip() == "3.11.9"
    bootstrap = (repo_root / "scripts" / "bootstrap.ps1").read_text(encoding="utf-8")
    assert "$Version -ne 'Python 3.11.9'" in bootstrap
    assert "requirements-runtime311.lock.txt" in bootstrap
    assert bootstrap.index("$Version -ne 'Python 3.11.9'") < bootstrap.index("-m venv .venv")
    assert bootstrap.index("$Version -ne 'Python 3.11.9'") < bootstrap.index("-m pip install")
    assert not (repo_root / "ArmoredSpeech" / "setup_runtime.ps1").exists()
    assert not (repo_root / "ArmoredSpeech" / "requirements-analysis.txt").exists()
    assert not (repo_root / "ArmoredSpeech" / "requirements-separation.txt").exists()


def test_rvc_base_assets_are_linked_from_central_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("ARMORED_ROOT", str(tmp_path))
    central = tmp_path / "runtime" / "models" / "rvc" / "base_model"
    central.mkdir(parents=True)
    expected = {}
    for name in ("hubert_base.pt", "rmvpe.pt", "rmvpe.onnx"):
        payload = (name + "-fixture").encode()
        (central / name).write_bytes(payload)
        expected[name] = payload

    package = tmp_path / ".venv" / "Lib" / "site-packages" / "rvc_python"
    rvc_engine._ensure_rvc_base_assets(package)

    assert {
        name: (package / "base_model" / name).read_bytes()
        for name in expected
    } == expected
