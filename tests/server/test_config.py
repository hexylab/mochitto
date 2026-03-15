import pytest

from server.config import ServerConfig


def test_config_loads_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ENV_FILE", raising=False)
    monkeypatch.setenv("SWITCHBOT_TOKEN", "test_token")
    monkeypatch.setenv("SWITCHBOT_SECRET", "test_secret")
    monkeypatch.setenv("VOICEVOX_URL", "http://localhost:50021")
    monkeypatch.setenv("WHISPER_MODEL", "tiny")

    config = ServerConfig(_env_file=None)
    assert config.switchbot_token == "test_token"
    assert config.switchbot_secret == "test_secret"
    assert config.voicevox_url == "http://localhost:50021"
    assert config.whisper_model == "tiny"


def test_config_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SWITCHBOT_TOKEN", "t")
    monkeypatch.setenv("SWITCHBOT_SECRET", "s")

    config = ServerConfig(_env_file=None)
    assert config.voicevox_url == "http://voicevox:50021"
    assert config.whisper_model == "large-v3"
