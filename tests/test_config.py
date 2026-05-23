from __future__ import annotations

from pathlib import Path

import pytest

from agentheim_code.config import _config_dir, ensure_default_config, load_config, save_config


class TestConfigDir:
    def test_windows_config_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("platform.system", lambda: "Windows")
        monkeypatch.setenv("APPDATA", "C:/\\Users\\Test\\AppData\\Roaming")
        assert _config_dir() == Path("C:/Users/Test/AppData/Roaming/Agentheim Code")

    def test_darwin_config_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        assert _config_dir() == Path.home() / "Library/Application Support/Agentheim Code"

    def test_linux_config_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("platform.system", lambda: "Linux")
        assert _config_dir() == Path.home() / ".config/agentheim-code"


class TestLoadConfig:
    def test_returns_empty_when_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("agentheim_code.config._config_file", lambda: tmp_path / "missing.toml")
        assert load_config() == {}

    def test_loads_valid_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text('[core]\ndefault_workspace = "/tmp"\n')
        monkeypatch.setattr("agentheim_code.config._config_file", lambda: config_path)
        cfg = load_config()
        assert cfg.get("core", {}).get("default_workspace") == "/tmp"

    def test_returns_empty_on_invalid_toml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text("not valid toml!!!")
        monkeypatch.setattr("agentheim_code.config._config_file", lambda: config_path)
        assert load_config() == {}


class TestSaveConfig:
    def test_saves_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("agentheim_code.config._config_file", lambda: config_path)
        save_config({"core": {"default_port": 9999}})
        assert config_path.exists()
        assert "default_port = 9999" in config_path.read_text()


class TestEnsureDefaultConfig:
    def test_creates_default_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("agentheim_code.config._config_file", lambda: config_path)
        path = ensure_default_config()
        assert path == config_path
        assert config_path.exists()
        text = config_path.read_text()
        assert "[core]" in text
        assert "default_port = 8765" in text

    def test_does_not_overwrite_existing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text("[core]\ndefault_port = 1111\n")
        monkeypatch.setattr("agentheim_code.config._config_file", lambda: config_path)
        ensure_default_config()
        assert "default_port = 1111" in config_path.read_text()

    def test_default_config_structure_matches_documentation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("agentheim_code.config._config_file", lambda: config_path)
        ensure_default_config()
        cfg = load_config()
        assert "core" in cfg
        assert "ui" in cfg
        assert cfg["core"].get("default_workspace") == "."
        assert cfg["core"].get("default_port") == 8765
        assert cfg["ui"].get("theme") == "dark"
