from armored_core.cli import _load_project_configuration


def test_private_project_configuration_has_single_file_source(tmp_path, monkeypatch):
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    (credentials / "project.env").write_text("ARMORED_CONFIG_SOURCE=credentials\n", encoding="utf-8")
    (tmp_path / ".env").write_text("ARMORED_ROOT_ENV_SHOULD_NOT_LOAD=1\n", encoding="utf-8")
    monkeypatch.delenv("ARMORED_CONFIG_SOURCE", raising=False)
    monkeypatch.delenv("ARMORED_ROOT_ENV_SHOULD_NOT_LOAD", raising=False)

    _load_project_configuration(tmp_path)

    assert __import__("os").environ["ARMORED_CONFIG_SOURCE"] == "credentials"
    assert "ARMORED_ROOT_ENV_SHOULD_NOT_LOAD" not in __import__("os").environ
