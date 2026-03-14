# Mochitto Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wake Word「モチット」で起動し、ずんだもんの声で応答するホームアシスタントを構築する。

**Architecture:** Raspberry Pi（クライアント）がWake Word検出・音声I/O・音楽再生を担当し、開発マシン（サーバー）がSTT・TTS・LLM・デバイス制御を担当するクライアント・サーバー構成。LAN内HTTPで通信する。

**Tech Stack:** Python 3.12+, FastAPI, Faster-Whisper, VoiceVox Engine (Docker), GPT-5.4 (Codex OAuth), Porcupine, python-mpv, yt-dlp, httpx, vidaa-control, SwitchBot Cloud API

**Spec:** `docs/superpowers/specs/2026-03-14-mochitto-design.md`

---

## File Structure

```
mochitto/
├── pyproject.toml
├── docker-compose.yml
├── .gitignore
├── .env.example
├── server/
│   ├── __init__.py
│   ├── main.py                    # FastAPIアプリ起動・ライフサイクル管理
│   ├── config.py                  # サーバー設定（pydantic-settings）
│   ├── api/
│   │   ├── __init__.py
│   │   └── voice.py               # POST /api/v1/voice エンドポイント
│   ├── services/
│   │   ├── __init__.py
│   │   ├── oauth.py               # Codex OAuth PKCE管理
│   │   ├── stt.py                 # Faster-Whisper STT
│   │   ├── tts.py                 # VoiceVox TTS
│   │   └── llm.py                 # GPT-5.4 意図理解・Web検索
│   └── devices/
│       ├── __init__.py
│       ├── switchbot.py           # SwitchBot Cloud API
│       └── tv.py                  # Hisense TV (vidaa-control)
├── client/
│   ├── __init__.py
│   ├── main.py                    # クライアントメインループ
│   ├── config.py                  # クライアント設定
│   ├── wake_word.py               # Porcupine Wake Word検出
│   ├── audio_recorder.py          # 発話録音（無音検出）
│   ├── audio_player.py            # WAV音声再生
│   ├── music_player.py            # mpv + yt-dlp 音楽再生
│   └── server_client.py           # サーバーAPI通信（multipartパース）
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # 共通fixture
│   ├── server/
│   │   ├── __init__.py
│   │   ├── test_config.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── test_oauth.py
│   │   │   ├── test_stt.py
│   │   │   ├── test_tts.py
│   │   │   └── test_llm.py
│   │   ├── devices/
│   │   │   ├── __init__.py
│   │   │   ├── test_switchbot.py
│   │   │   └── test_tv.py
│   │   └── api/
│   │       ├── __init__.py
│   │       └── test_voice.py
│   └── client/
│       ├── __init__.py
│       ├── test_audio_recorder.py
│       ├── test_music_player.py
│       └── test_server_client.py
└── assets/
    └── error_audio/               # エラー時の事前キャッシュ済みWAV
        └── .gitkeep
```

---

## Chunk 1: プロジェクトセットアップ + サーバー基盤

### Task 1: プロジェクトスキャフォールド

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `docker-compose.yml`
- Create: `server/__init__.py`, `server/api/__init__.py`, `server/services/__init__.py`, `server/devices/__init__.py`
- Create: `client/__init__.py`
- Create: `tests/__init__.py`, `tests/server/__init__.py`, `tests/server/services/__init__.py`, `tests/server/devices/__init__.py`, `tests/server/api/__init__.py`, `tests/client/__init__.py`
- Create: `tests/conftest.py`
- Create: `assets/error_audio/.gitkeep`

- [ ] **Step 1: pyproject.toml を作成**

```toml
[project]
name = "mochitto"
version = "0.1.0"
description = "ずんだもんホームアシスタント"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "httpx>=0.28",
    "faster-whisper>=1.1",
    "pydantic-settings>=2.7",
    "python-multipart>=0.0.17",
    "vidaa-control>=0.10",
    "tenacity>=9.0",
]

[project.optional-dependencies]
client = [
    "pvporcupine>=3.0",
    "pyaudio>=0.2",
    "python-mpv>=1.0",
    "yt-dlp>=2025.1",
    "ytmusicapi>=1.9",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.25",
    "pytest-httpx>=0.35",
    "ruff>=0.9",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100
```

- [ ] **Step 2: .gitignore を作成**

```
__pycache__/
*.pyc
.env
auth.json
*.ppn
.venv/
dist/
*.egg-info/
.ruff_cache/
.pytest_cache/
```

- [ ] **Step 3: .env.example を作成**

```
SWITCHBOT_TOKEN=your_switchbot_token
SWITCHBOT_SECRET=your_switchbot_secret
PORCUPINE_ACCESS_KEY=your_porcupine_access_key
SERVER_URL=http://192.168.1.100:8000
VOICEVOX_URL=http://localhost:50021
WHISPER_MODEL=large-v3
TV_HOST=192.168.1.xxx
TV_MAC=AA:BB:CC:DD:EE:FF
```

- [ ] **Step 4: docker-compose.yml を作成**

```yaml
services:
  voicevox:
    image: voicevox/voicevox_engine:cpu-latest
    ports:
      - "50021:50021"
    restart: unless-stopped
```

- [ ] **Step 5: 全ディレクトリの __init__.py と conftest.py を作成**

`tests/conftest.py`:
```python
import pytest


@pytest.fixture
def sample_audio_bytes() -> bytes:
    """テスト用の最小WAVデータ（44バイトヘッダ + 無音）"""
    import struct
    import wave
    import io

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(struct.pack("<h", 0) * 16000)  # 1秒の無音
    return buf.getvalue()
```

- [ ] **Step 6: assets/error_audio/.gitkeep を作成**

空ファイル。

- [ ] **Step 7: uv で依存インストール、テストが実行できることを確認**

Run: `uv sync --all-extras && uv run pytest --co -q`
Expected: `no tests ran` （テストファイルがまだ無いため）

- [ ] **Step 8: コミット**

```bash
git add -A
git commit -m "chore: プロジェクトスキャフォールド"
```

---

### Task 2: サーバー設定 (config)

**Files:**
- Create: `server/config.py`
- Create: `tests/server/test_config.py`

- [ ] **Step 1: テストを書く**

```python
# tests/server/test_config.py
import os

import pytest


def test_config_loads_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SWITCHBOT_TOKEN", "test_token")
    monkeypatch.setenv("SWITCHBOT_SECRET", "test_secret")
    monkeypatch.setenv("VOICEVOX_URL", "http://localhost:50021")
    monkeypatch.setenv("WHISPER_MODEL", "tiny")
    monkeypatch.setenv("TV_HOST", "192.168.1.10")
    monkeypatch.setenv("TV_MAC", "AA:BB:CC:DD:EE:FF")

    from server.config import ServerConfig

    config = ServerConfig()
    assert config.switchbot_token == "test_token"
    assert config.switchbot_secret == "test_secret"
    assert config.voicevox_url == "http://localhost:50021"
    assert config.whisper_model == "tiny"
    assert config.tv_host == "192.168.1.10"
    assert config.tv_mac == "AA:BB:CC:DD:EE:FF"


def test_config_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SWITCHBOT_TOKEN", "t")
    monkeypatch.setenv("SWITCHBOT_SECRET", "s")
    monkeypatch.setenv("TV_HOST", "192.168.1.10")
    monkeypatch.setenv("TV_MAC", "AA:BB:CC:DD:EE:FF")

    from server.config import ServerConfig

    config = ServerConfig()
    assert config.voicevox_url == "http://localhost:50021"
    assert config.whisper_model == "large-v3"
    assert config.host == "0.0.0.0"
    assert config.port == 8000
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/server/test_config.py -v`
Expected: FAIL（`server.config` が存在しない）

- [ ] **Step 3: 実装**

```python
# server/config.py
from pydantic_settings import BaseSettings


class ServerConfig(BaseSettings):
    model_config = {"env_file": ".env", "extra": "ignore"}

    # SwitchBot
    switchbot_token: str
    switchbot_secret: str

    # VoiceVox
    voicevox_url: str = "http://localhost:50021"

    # Whisper
    whisper_model: str = "large-v3"

    # Hisense TV
    tv_host: str
    tv_mac: str

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
```

- [ ] **Step 4: テストがパスすることを確認**

Run: `uv run pytest tests/server/test_config.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add server/config.py tests/server/test_config.py
git commit -m "feat: サーバー設定モジュールを追加"
```

---

### Task 3: OAuth Manager (Codex PKCE)

**Files:**
- Create: `server/services/oauth.py`
- Create: `tests/server/services/test_oauth.py`

- [ ] **Step 1: テストを書く**

```python
# tests/server/services/test_oauth.py
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from server.services.oauth import OAuthManager

AUTH_ENDPOINT = "https://auth.openai.com/oauth/authorize"
TOKEN_ENDPOINT = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


@pytest.fixture
def auth_file(tmp_path: Path) -> Path:
    return tmp_path / "auth.json"


@pytest.fixture
def valid_token_data() -> dict:
    return {
        "access_token": "test_access_token",
        "refresh_token": "rt_test_refresh",
        "expires_at": time.time() + 3600,
        "client_id": CLIENT_ID,
    }


@pytest.fixture
def expired_token_data() -> dict:
    return {
        "access_token": "expired_token",
        "refresh_token": "rt_test_refresh",
        "expires_at": time.time() - 100,
        "client_id": CLIENT_ID,
    }


def test_pkce_code_verifier_length():
    manager = OAuthManager(auth_path=Path("/tmp/test_auth.json"))
    verifier = manager._generate_code_verifier()
    assert 43 <= len(verifier) <= 128


def test_pkce_challenge_is_s256():
    manager = OAuthManager(auth_path=Path("/tmp/test_auth.json"))
    verifier = manager._generate_code_verifier()
    challenge = manager._generate_code_challenge(verifier)
    assert len(challenge) > 0
    assert "+" not in challenge  # URL-safe base64


def test_load_valid_token(auth_file: Path, valid_token_data: dict):
    auth_file.write_text(json.dumps(valid_token_data))
    manager = OAuthManager(auth_path=auth_file)
    manager._load_token()
    assert manager._access_token == "test_access_token"
    assert manager.is_authenticated


def test_load_no_file(auth_file: Path):
    manager = OAuthManager(auth_path=auth_file)
    manager._load_token()
    assert not manager.is_authenticated


async def test_get_token_returns_valid(auth_file: Path, valid_token_data: dict):
    auth_file.write_text(json.dumps(valid_token_data))
    manager = OAuthManager(auth_path=auth_file)
    manager._load_token()
    token = await manager.get_token()
    assert token == "test_access_token"


async def test_get_token_refreshes_expired(auth_file: Path, expired_token_data: dict):
    auth_file.write_text(json.dumps(expired_token_data))
    manager = OAuthManager(auth_path=auth_file)
    manager._load_token()

    new_token_data = {
        "access_token": "new_access_token",
        "refresh_token": "rt_new_refresh",
        "expires_in": 3600,
    }

    with patch.object(manager, "_refresh_token", new_callable=AsyncMock, return_value=new_token_data):
        token = await manager.get_token()
        assert token == "new_access_token"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/server/services/test_oauth.py -v`
Expected: FAIL

- [ ] **Step 3: 実装**

```python
# server/services/oauth.py
import asyncio
import base64
import hashlib
import json
import logging
import secrets
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

AUTH_ENDPOINT = "https://auth.openai.com/oauth/authorize"
TOKEN_ENDPOINT = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
REFRESH_MARGIN_SECONDS = 300  # 5分前にリフレッシュ


class OAuthManager:
    def __init__(self, auth_path: Path = Path("auth.json")):
        self._auth_path = auth_path
        self._access_token: str | None = None
        self._refresh_token_value: str | None = None
        self._expires_at: float = 0
        self._lock = asyncio.Lock()
        self._load_token()

    @property
    def is_authenticated(self) -> bool:
        return self._access_token is not None

    def _load_token(self) -> None:
        if not self._auth_path.exists():
            return
        data = json.loads(self._auth_path.read_text())
        self._access_token = data.get("access_token")
        self._refresh_token_value = data.get("refresh_token")
        self._expires_at = data.get("expires_at", 0)

    def _save_token(self) -> None:
        data = {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token_value,
            "expires_at": self._expires_at,
            "client_id": CLIENT_ID,
        }
        self._auth_path.write_text(json.dumps(data, indent=2))

    def _generate_code_verifier(self) -> str:
        return secrets.token_urlsafe(64)

    def _generate_code_challenge(self, verifier: str) -> str:
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    def _is_token_expired(self) -> bool:
        return time.time() >= (self._expires_at - REFRESH_MARGIN_SECONDS)

    async def _refresh_token(self) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                TOKEN_ENDPOINT,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token_value,
                    "client_id": CLIENT_ID,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def get_token(self) -> str:
        async with self._lock:
            if self._access_token and not self._is_token_expired():
                return self._access_token

            if not self._refresh_token_value:
                raise RuntimeError(
                    "認証されていません。サーバーを再起動して認証を行ってください。"
                )

            logger.info("OAuthトークンをリフレッシュ中...")
            token_data = await self._refresh_token()
            self._access_token = token_data["access_token"]
            if "refresh_token" in token_data:
                self._refresh_token_value = token_data["refresh_token"]
            self._expires_at = time.time() + token_data.get("expires_in", 3600)
            self._save_token()
            logger.info("OAuthトークンのリフレッシュ完了")
            return self._access_token

    def get_authorize_url(self, redirect_uri: str, code_verifier: str) -> str:
        from urllib.parse import urlencode

        code_challenge = self._generate_code_challenge(code_verifier)
        params = {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "scope": "user:inference",
        }
        return f"{AUTH_ENDPOINT}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str, code_verifier: str) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                TOKEN_ENDPOINT,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": CLIENT_ID,
                    "code_verifier": code_verifier,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        self._access_token = token_data["access_token"]
        self._refresh_token_value = token_data.get("refresh_token")
        self._expires_at = time.time() + token_data.get("expires_in", 3600)
        self._save_token()
        logger.info("OAuth認証完了。トークンを保存しました。")
```

- [ ] **Step 4: テストがパスすることを確認**

Run: `uv run pytest tests/server/services/test_oauth.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add server/services/oauth.py tests/server/services/test_oauth.py
git commit -m "feat: Codex OAuth PKCE マネージャーを追加"
```

---

## Chunk 2: サーバーサービス（STT・TTS・LLM）

### Task 4: STT Service (Faster-Whisper)

**Files:**
- Create: `server/services/stt.py`
- Create: `tests/server/services/test_stt.py`

- [ ] **Step 1: テストを書く**

```python
# tests/server/services/test_stt.py
from unittest.mock import MagicMock, patch

import pytest

from server.services.stt import STTService, STTResult


def test_stt_result_is_low_confidence():
    result = STTResult(text="", no_speech_prob=0.8, avg_logprob=-1.5)
    assert result.is_low_confidence


def test_stt_result_is_valid():
    result = STTResult(text="こんにちは", no_speech_prob=0.1, avg_logprob=-0.3)
    assert not result.is_low_confidence


def test_stt_result_empty_text_is_low_confidence():
    result = STTResult(text="", no_speech_prob=0.1, avg_logprob=-0.3)
    assert result.is_low_confidence


@patch("server.services.stt.WhisperModel")
def test_stt_service_init(mock_whisper_cls: MagicMock):
    service = STTService(model_name="tiny")
    mock_whisper_cls.assert_called_once_with("tiny", device="auto", compute_type="auto")


@patch("server.services.stt.WhisperModel")
def test_stt_service_transcribe(mock_whisper_cls: MagicMock, sample_audio_bytes: bytes):
    mock_segment = MagicMock()
    mock_segment.text = "テスト発話"
    mock_segment.no_speech_prob = 0.05
    mock_segment.avg_logprob = -0.2

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], MagicMock())
    mock_whisper_cls.return_value = mock_model

    service = STTService(model_name="tiny")
    result = service.transcribe(sample_audio_bytes)

    assert result.text == "テスト発話"
    assert not result.is_low_confidence
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/server/services/test_stt.py -v`
Expected: FAIL

- [ ] **Step 3: 実装**

```python
# server/services/stt.py
import io
import logging
from dataclasses import dataclass

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

NO_SPEECH_PROB_THRESHOLD = 0.6
AVG_LOGPROB_THRESHOLD = -1.0


@dataclass
class STTResult:
    text: str
    no_speech_prob: float
    avg_logprob: float

    @property
    def is_low_confidence(self) -> bool:
        if not self.text.strip():
            return True
        return (
            self.no_speech_prob > NO_SPEECH_PROB_THRESHOLD
            or self.avg_logprob < AVG_LOGPROB_THRESHOLD
        )


class STTService:
    def __init__(self, model_name: str = "large-v3"):
        logger.info("Whisperモデル '%s' をロード中...", model_name)
        self._model = WhisperModel(model_name, device="auto", compute_type="auto")
        logger.info("Whisperモデルのロード完了")

    def transcribe(self, audio_bytes: bytes) -> STTResult:
        audio_file = io.BytesIO(audio_bytes)
        segments, _ = self._model.transcribe(audio_file, language="ja")
        segments_list = list(segments)

        if not segments_list:
            return STTResult(text="", no_speech_prob=1.0, avg_logprob=-2.0)

        text = "".join(seg.text for seg in segments_list)
        avg_no_speech = sum(s.no_speech_prob for s in segments_list) / len(segments_list)
        avg_logprob = sum(s.avg_logprob for s in segments_list) / len(segments_list)

        return STTResult(text=text.strip(), no_speech_prob=avg_no_speech, avg_logprob=avg_logprob)
```

- [ ] **Step 4: テストがパスすることを確認**

Run: `uv run pytest tests/server/services/test_stt.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add server/services/stt.py tests/server/services/test_stt.py
git commit -m "feat: Faster-Whisper STTサービスを追加"
```

---

### Task 5: TTS Service (VoiceVox)

**Files:**
- Create: `server/services/tts.py`
- Create: `tests/server/services/test_tts.py`

- [ ] **Step 1: テストを書く**

```python
# tests/server/services/test_tts.py
import httpx
import pytest

from server.services.tts import TTSService

ZUNDAMON_SPEAKER_ID = 3


async def test_tts_synthesize(httpx_mock):
    audio_query_response = {"accent_phrases": [], "speedScale": 1.0}
    httpx_mock.add_response(
        url="http://localhost:50021/audio_query?text=%E3%81%93%E3%82%93%E3%81%AB%E3%81%A1%E3%81%AF&speaker=3",
        method="POST",
        json=audio_query_response,
    )
    httpx_mock.add_response(
        url=f"http://localhost:50021/synthesis?speaker={ZUNDAMON_SPEAKER_ID}",
        method="POST",
        content=b"RIFF_FAKE_WAV_DATA",
    )

    service = TTSService(voicevox_url="http://localhost:50021")
    audio = await service.synthesize("こんにちは")
    assert audio == b"RIFF_FAKE_WAV_DATA"


async def test_tts_synthesize_empty_text():
    service = TTSService(voicevox_url="http://localhost:50021")
    with pytest.raises(ValueError, match="空のテキスト"):
        await service.synthesize("")
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/server/services/test_tts.py -v`
Expected: FAIL

- [ ] **Step 3: 実装**

```python
# server/services/tts.py
import logging
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

ZUNDAMON_SPEAKER_ID = 3


class TTSService:
    def __init__(self, voicevox_url: str = "http://localhost:50021"):
        self._base_url = voicevox_url

    async def synthesize(self, text: str, speaker_id: int = ZUNDAMON_SPEAKER_ID) -> bytes:
        if not text.strip():
            raise ValueError("空のテキストは合成できません")

        encoded_text = quote(text)

        async with httpx.AsyncClient(timeout=30.0) as client:
            query_resp = await client.post(
                f"{self._base_url}/audio_query?text={encoded_text}&speaker={speaker_id}"
            )
            query_resp.raise_for_status()
            audio_query = query_resp.json()

            synth_resp = await client.post(
                f"{self._base_url}/synthesis?speaker={speaker_id}",
                json=audio_query,
            )
            synth_resp.raise_for_status()
            return synth_resp.content
```

- [ ] **Step 4: テストがパスすることを確認**

Run: `uv run pytest tests/server/services/test_tts.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add server/services/tts.py tests/server/services/test_tts.py
git commit -m "feat: VoiceVox TTSサービスを追加"
```

---

### Task 6: LLM Service (GPT-5.4 意図理解 + Web検索)

**Files:**
- Create: `server/services/llm.py`
- Create: `tests/server/services/test_llm.py`

- [ ] **Step 1: テストを書く**

```python
# tests/server/services/test_llm.py
import json
from unittest.mock import AsyncMock, patch

import pytest

from server.services.llm import LLMService, IntentResult


def test_parse_device_control_intent():
    raw = {
        "intent": "device_control",
        "device_type": "switchbot",
        "device_category": "light",
        "action": "off",
        "params": {},
        "response": "電気を消したのだ",
    }
    result = IntentResult.from_dict(raw)
    assert result.intent == "device_control"
    assert result.device_type == "switchbot"
    assert result.action == "off"
    assert result.response == "電気を消したのだ"


def test_parse_play_music_intent():
    raw = {
        "intent": "play_music",
        "query": "米津玄師 Lemon",
        "response": "再生するのだ",
    }
    result = IntentResult.from_dict(raw)
    assert result.intent == "play_music"
    assert result.query == "米津玄師 Lemon"


def test_parse_music_control_intent():
    raw = {
        "intent": "music_control",
        "action": "stop",
        "response": "止めたのだ",
    }
    result = IntentResult.from_dict(raw)
    assert result.intent == "music_control"
    assert result.action == "stop"


def test_parse_web_search_intent():
    raw = {
        "intent": "web_search",
        "query": "明日の天気",
    }
    result = IntentResult.from_dict(raw)
    assert result.intent == "web_search"
    assert result.query == "明日の天気"
    assert result.response is None


def test_parse_chat_intent():
    raw = {
        "intent": "chat",
        "response": "おはようなのだ！",
    }
    result = IntentResult.from_dict(raw)
    assert result.intent == "chat"
    assert result.response == "おはようなのだ！"


async def test_llm_classify_intent():
    mock_oauth = AsyncMock()
    mock_oauth.get_token.return_value = "test_token"

    service = LLMService(oauth_manager=mock_oauth, devices_info=[])

    mock_response_json = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            {
                                "intent": "chat",
                                "response": "こんにちはなのだ！",
                            }
                        ),
                    }
                ],
            }
        ]
    }

    with patch("server.services.llm.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response_json
        mock_resp.raise_for_status = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await service.classify_intent("こんにちは")
        assert result.intent == "chat"
        assert result.response == "こんにちはなのだ！"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/server/services/test_llm.py -v`
Expected: FAIL

- [ ] **Step 3: 実装**

```python
# server/services/llm.py
import json
import logging
from dataclasses import dataclass, field

import httpx

from server.services.oauth import OAuthManager

logger = logging.getLogger(__name__)

RESPONSES_API_URL = "https://api.openai.com/v1/responses"
MODEL = "gpt-5.4"

SYSTEM_PROMPT_TEMPLATE = """\
あなたはスマートホームアシスタント「モチット」です。ずんだもんの口調（語尾に「のだ」「なのだ」）で応答してください。

ユーザーの発話を以下のintentに分類し、JSON形式で出力してください。

## Intent一覧
- device_control: デバイス操作（照明、エアコン、カーテン、テレビ）
- play_music: 音楽再生
- music_control: 再生中の音楽制御（停止、一時停止、再開、音量調整）
- web_search: Web検索
- chat: 雑談・質問

## 操作可能なデバイス
{devices_json}

## 出力形式
各intentに応じたJSONを出力してください。responseフィールドにはずんだもん口調の応答を含めてください。
device_controlの場合、device_idフィールドに操作対象のデバイスIDを必ず含めてください。
"""

WEB_SEARCH_SYSTEM_PROMPT = """\
あなたはスマートホームアシスタント「モチット」です。
ずんだもんの口調（語尾に「のだ」「なのだ」）で、検索結果を簡潔に要約して応答してください。
3文以内で要点をまとめてください。
"""


@dataclass
class IntentResult:
    intent: str
    response: str | None = None
    device_type: str | None = None
    device_category: str | None = None
    action: str | None = None
    params: dict = field(default_factory=dict)
    query: str | None = None

    device_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "IntentResult":
        return cls(
            intent=data["intent"],
            response=data.get("response"),
            device_type=data.get("device_type"),
            device_category=data.get("device_category"),
            action=data.get("action"),
            params=data.get("params", {}),
            query=data.get("query"),
            device_id=data.get("device_id"),
        )


class LLMService:
    def __init__(self, oauth_manager: OAuthManager, devices_info: list[dict]):
        self._oauth = oauth_manager
        self._devices_info = devices_info

    def _build_system_prompt(self) -> str:
        devices_json = json.dumps(self._devices_info, ensure_ascii=False, indent=2)
        return SYSTEM_PROMPT_TEMPLATE.format(devices_json=devices_json)

    async def _call_responses_api(
        self,
        user_input: str,
        system_prompt: str,
        tools: list[dict] | None = None,
        use_structured: bool = False,
    ) -> dict:
        from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_fixed(1),
            retry=retry_if_exception_type(httpx.HTTPError),
        )
        async def _do_request() -> dict:
            return await self.__call_api(user_input, system_prompt, tools, use_structured)

        return await _do_request()

    async def __call_api(
        self,
        user_input: str,
        system_prompt: str,
        tools: list[dict] | None = None,
        use_structured: bool = False,
    ) -> dict:
        token = await self._oauth.get_token()

        body: dict = {
            "model": MODEL,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
        }

        if tools:
            body["tools"] = tools
        if use_structured:
            body["text"] = {"format": {"type": "json_object"}}
            body["instructions"] = system_prompt

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                RESPONSES_API_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            return resp.json()

    def _extract_text(self, response_data: dict) -> str:
        for output in response_data.get("output", []):
            if output.get("type") == "message":
                for content in output.get("content", []):
                    if content.get("type") == "output_text":
                        return content["text"]
        return ""

    def update_devices(self, devices: list[dict]) -> None:
        """SwitchBotデバイス一覧を更新し、システムプロンプトに反映する"""
        self._devices_info = [
            {"id": d["deviceId"], "name": d["deviceName"], "type": d.get("deviceType", "")}
            for d in devices
        ]

    async def classify_intent(self, text: str) -> IntentResult:
        response_data = await self._call_responses_api(
            user_input=text,
            system_prompt=self._build_system_prompt(),
            use_structured=True,
        )
        raw_text = self._extract_text(response_data)

        try:
            parsed = json.loads(raw_text)
            return IntentResult.from_dict(parsed)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("LLM出力のパースに失敗: %s", e)
            return IntentResult(intent="chat", response=raw_text)

    async def web_search(self, query: str) -> str:
        response_data = await self._call_responses_api(
            user_input=query,
            system_prompt=WEB_SEARCH_SYSTEM_PROMPT,
            tools=[{"type": "web_search"}],
            use_structured=False,
        )
        return self._extract_text(response_data)
```

- [ ] **Step 4: テストがパスすることを確認**

Run: `uv run pytest tests/server/services/test_llm.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add server/services/llm.py tests/server/services/test_llm.py
git commit -m "feat: GPT-5.4 LLMサービス（意図理解+Web検索）を追加"
```

---

## Chunk 3: デバイス制御 + FastAPIゲートウェイ

### Task 7: SwitchBot Client

**Files:**
- Create: `server/devices/switchbot.py`
- Create: `tests/server/devices/test_switchbot.py`

- [ ] **Step 1: テストを書く**

```python
# tests/server/devices/test_switchbot.py
import hashlib
import hmac
from unittest.mock import AsyncMock

import pytest

from server.devices.switchbot import SwitchBotClient


@pytest.fixture
def switchbot_client():
    return SwitchBotClient(token="test_token", secret="test_secret")


async def test_get_devices(switchbot_client: SwitchBotClient, httpx_mock):
    httpx_mock.add_response(
        url="https://api.switch-bot.com/v1.1/devices",
        json={
            "statusCode": 100,
            "body": {
                "deviceList": [
                    {"deviceId": "D001", "deviceName": "リビング照明", "deviceType": "Color Bulb"},
                    {"deviceId": "D002", "deviceName": "寝室エアコン", "deviceType": "Air Conditioner"},
                ],
                "infraredRemoteList": [],
            },
        },
    )

    devices = await switchbot_client.get_devices()
    assert len(devices) == 2
    assert devices[0]["deviceId"] == "D001"


async def test_send_command(switchbot_client: SwitchBotClient, httpx_mock):
    httpx_mock.add_response(
        url="https://api.switch-bot.com/v1.1/devices/D001/commands",
        method="POST",
        json={"statusCode": 100, "body": {}, "message": "success"},
    )

    result = await switchbot_client.send_command("D001", "turnOff")
    assert result["statusCode"] == 100


def test_auth_headers(switchbot_client: SwitchBotClient):
    headers = switchbot_client._build_headers()
    assert "Authorization" in headers
    assert "sign" in headers
    assert "t" in headers
    assert "nonce" in headers
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/server/devices/test_switchbot.py -v`
Expected: FAIL

- [ ] **Step 3: 実装**

```python
# server/devices/switchbot.py
import base64
import hashlib
import hmac
import logging
import time
import uuid

import httpx

logger = logging.getLogger(__name__)

SWITCHBOT_API_BASE = "https://api.switch-bot.com/v1.1"


class SwitchBotClient:
    def __init__(self, token: str, secret: str):
        self._token = token
        self._secret = secret

    def _build_headers(self) -> dict[str, str]:
        t = str(int(time.time() * 1000))
        nonce = uuid.uuid4().hex
        string_to_sign = f"{self._token}{t}{nonce}"
        sign = base64.b64encode(
            hmac.HMAC(
                self._secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        return {
            "Authorization": self._token,
            "sign": sign,
            "t": t,
            "nonce": nonce,
            "Content-Type": "application/json",
        }

    async def get_devices(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{SWITCHBOT_API_BASE}/devices",
                headers=self._build_headers(),
            )
            resp.raise_for_status()
            body = resp.json()["body"]
            return body.get("deviceList", []) + body.get("infraredRemoteList", [])

    async def send_command(
        self, device_id: str, command: str, parameter: str = "default"
    ) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{SWITCHBOT_API_BASE}/devices/{device_id}/commands",
                headers=self._build_headers(),
                json={
                    "command": command,
                    "parameter": parameter,
                    "commandType": "command",
                },
            )
            resp.raise_for_status()
            return resp.json()
```

- [ ] **Step 4: テストがパスすることを確認**

Run: `uv run pytest tests/server/devices/test_switchbot.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add server/devices/switchbot.py tests/server/devices/test_switchbot.py
git commit -m "feat: SwitchBotクライアントを追加"
```

---

### Task 8: TV Client (Hisense vidaa-control)

**Files:**
- Create: `server/devices/tv.py`
- Create: `tests/server/devices/test_tv.py`

- [ ] **Step 1: テストを書く**

```python
# tests/server/devices/test_tv.py
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from server.devices.tv import TVClient


@pytest.fixture
def tv_client():
    return TVClient(host="192.168.1.10", mac="AA:BB:CC:DD:EE:FF")


async def test_send_key(tv_client: TVClient):
    with patch.object(tv_client, "_get_tv", new_callable=AsyncMock) as mock_get_tv:
        mock_tv = AsyncMock()
        mock_get_tv.return_value = mock_tv
        await tv_client.send_key("power")
        mock_tv.async_send_key.assert_called_once_with("power")


async def test_set_volume(tv_client: TVClient):
    with patch.object(tv_client, "_get_tv", new_callable=AsyncMock) as mock_get_tv:
        mock_tv = AsyncMock()
        mock_get_tv.return_value = mock_tv
        await tv_client.send_key("volume_up")
        mock_tv.async_send_key.assert_called_once_with("volume_up")


def test_action_to_key_mapping():
    client = TVClient(host="192.168.1.10", mac="AA:BB:CC:DD:EE:FF")
    assert client.resolve_action("power_on") == "power"
    assert client.resolve_action("power_off") == "power"
    assert client.resolve_action("mute") == "mute"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/server/devices/test_tv.py -v`
Expected: FAIL

- [ ] **Step 3: 実装**

```python
# server/devices/tv.py
import logging
from vidaa import AsyncVidaaTV

logger = logging.getLogger(__name__)

ACTION_KEY_MAP = {
    "power_on": "power",
    "power_off": "power",
    "mute": "mute",
}


class TVClient:
    def __init__(self, host: str, mac: str):
        self._host = host
        self._mac = mac
        self._tv: AsyncVidaaTV | None = None

    def resolve_action(self, action: str) -> str:
        return ACTION_KEY_MAP.get(action, action)

    async def _get_tv(self) -> AsyncVidaaTV:
        if self._tv is None:
            self._tv = AsyncVidaaTV(host=self._host, mac_address=self._mac)
            await self._tv.async_connect()
        return self._tv

    async def send_key(self, key_name: str) -> None:
        tv = await self._get_tv()
        await tv.async_send_key(key_name)
        logger.info("TVキー送信: %s", key_name)

    async def set_volume(self, volume: int) -> None:
        tv = await self._get_tv()
        await tv.async_change_volume(volume)

    async def change_source(self, source_id: str) -> None:
        tv = await self._get_tv()
        await tv.async_change_source(source_id)

    async def disconnect(self) -> None:
        if self._tv:
            await self._tv.async_disconnect()
            self._tv = None
```

- [ ] **Step 4: テストがパスすることを確認**

Run: `uv run pytest tests/server/devices/test_tv.py -v`
Expected: PASS

- [ ] **Step 5: pyproject.toml に vidaa-control を追加してコミット**

`pyproject.toml` の `dependencies` に `"vidaa-control>=0.10"` を追加。

```bash
uv sync --all-extras
git add server/devices/tv.py tests/server/devices/test_tv.py pyproject.toml
git commit -m "feat: Hisense TV (vidaa-control) クライアントを追加"
```

---

### Task 9: FastAPI Gateway (voice エンドポイント)

**Files:**
- Create: `server/api/voice.py`
- Create: `server/main.py`
- Create: `tests/server/api/test_voice.py`

- [ ] **Step 1: テストを書く**

```python
# tests/server/api/test_voice.py
import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from server.services.llm import IntentResult


@pytest.fixture
def mock_services():
    """全サービスをモックしたdictを返す"""
    stt = MagicMock()
    stt.transcribe.return_value = MagicMock(
        text="電気を消して", is_low_confidence=False
    )

    tts = AsyncMock()
    tts.synthesize.return_value = b"FAKE_WAV_DATA"

    llm = AsyncMock()
    llm.classify_intent.return_value = IntentResult(
        intent="device_control",
        device_type="switchbot",
        device_category="light",
        action="off",
        params={},
        response="電気を消したのだ",
    )

    switchbot = AsyncMock()
    switchbot.send_command.return_value = {"statusCode": 100, "message": "success"}

    tv = AsyncMock()

    return {"stt": stt, "tts": tts, "llm": llm, "switchbot": switchbot, "tv": tv}


@pytest.fixture
def test_client(mock_services):
    with patch("server.main.create_app") as mock_create:
        from server.main import create_app_with_services

        app = create_app_with_services(**mock_services)
        return TestClient(app)


def test_voice_endpoint_device_control(test_client, sample_audio_bytes):
    response = test_client.post(
        "/api/v1/voice",
        files={"audio": ("test.wav", io.BytesIO(sample_audio_bytes), "audio/wav")},
    )
    assert response.status_code == 200

    # multipart/mixed レスポンスのパース
    content_type = response.headers["content-type"]
    assert "multipart/mixed" in content_type or "application/json" in content_type


def test_voice_endpoint_low_confidence_stt(test_client, mock_services, sample_audio_bytes):
    mock_services["stt"].transcribe.return_value = MagicMock(
        text="", is_low_confidence=True
    )

    response = test_client.post(
        "/api/v1/voice",
        files={"audio": ("test.wav", io.BytesIO(sample_audio_bytes), "audio/wav")},
    )
    assert response.status_code == 200
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/server/api/test_voice.py -v`
Expected: FAIL

- [ ] **Step 3: voice.py を実装**

```python
# server/api/voice.py
import json
import logging
import uuid

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse

from server.services.stt import STTService
from server.services.tts import TTSService
from server.services.llm import LLMService, IntentResult
from server.devices.switchbot import SwitchBotClient
from server.devices.tv import TVClient

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_RESPONSE = "うまく聞き取れなかったのだ、もう一度言ってほしいのだ"


def create_voice_router(
    stt: STTService,
    tts: TTSService,
    llm: LLMService,
    switchbot: SwitchBotClient,
    tv: TVClient,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/voice")
    async def handle_voice(audio: UploadFile = File(...)):
        audio_bytes = await audio.read()

        # 1. STT
        stt_result = stt.transcribe(audio_bytes)

        if stt_result.is_low_confidence:
            return await _build_response(
                IntentResult(intent="chat", response=LOW_CONFIDENCE_RESPONSE),
                tts,
            )

        logger.info("STT結果: %s", stt_result.text)

        # 2. LLM 意図理解
        try:
            intent_result = await llm.classify_intent(stt_result.text)
        except Exception:
            logger.exception("LLM呼び出し失敗")
            return await _build_response(
                IntentResult(
                    intent="chat",
                    response="ちょっと考えがまとまらなかったのだ、もう一度試してほしいのだ",
                ),
                tts,
            )

        # 3. Intent に応じた処理
        device_result = None

        if intent_result.intent == "device_control":
            device_result = await _handle_device(intent_result, switchbot, tv)

        elif intent_result.intent == "web_search" and intent_result.query:
            search_response = await llm.web_search(intent_result.query)
            intent_result.response = search_response

        # 4. レスポンス構築
        return await _build_response(intent_result, tts, device_result)

    return router


async def _handle_device(
    intent: IntentResult, switchbot: SwitchBotClient, tv: TVClient
) -> dict:
    try:
        if intent.device_type == "switchbot":
            command = _switchbot_command(intent)
            result = await switchbot.send_command(
                intent.device_id or "", command["command"], command.get("parameter", "default")
            )
            return {"success": True, "device": intent.device_category}

        elif intent.device_type == "tv":
            key = tv.resolve_action(intent.action or "")
            if intent.action == "volume":
                direction = intent.params.get("direction", "up")
                key = f"volume_{direction}"
            elif intent.action == "channel":
                # チャンネル番号を数字キーで入力
                for digit in str(intent.params.get("number", "")):
                    await tv.send_key(f"num_{digit}")
                return {"success": True, "device": "tv"}
            elif intent.action == "input_source":
                await tv.change_source(intent.params.get("source", ""))
                return {"success": True, "device": "tv"}

            await tv.send_key(key)
            return {"success": True, "device": "tv"}

    except Exception as e:
        logger.exception("デバイス操作失敗")
        return {"success": False, "device": intent.device_category, "error": str(e)}

    return {"success": False, "device": "unknown"}


def _switchbot_command(intent: IntentResult) -> dict:
    action = intent.action
    category = intent.device_category

    if category == "light":
        if action == "on":
            return {"command": "turnOn"}
        elif action == "off":
            return {"command": "turnOff"}
        elif action == "brightness":
            return {"command": "setBrightness", "parameter": str(intent.params.get("brightness", 50))}

    elif category == "aircon":
        if action == "on":
            return {"command": "turnOn"}
        elif action == "off":
            return {"command": "turnOff"}
        elif action == "set":
            temp = intent.params.get("temperature", 25)
            mode_map = {"cool": "2", "heat": "5", "auto": "1"}
            mode = mode_map.get(intent.params.get("mode", "auto"), "1")
            return {"command": "setAll", "parameter": f"{temp},{mode},1,on"}

    elif category == "curtain":
        if action == "open":
            return {"command": "turnOn"}
        elif action == "close":
            return {"command": "turnOff"}

    return {"command": action or ""}


async def _build_response(
    intent: IntentResult,
    tts: TTSService,
    device_result: dict | None = None,
) -> StreamingResponse:
    response_text = intent.response or ""

    try:
        audio_data = await tts.synthesize(response_text) if response_text else b""
    except Exception:
        logger.exception("TTS合成失敗")
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"error": "VoiceVox Engine is unavailable"},
        )

    json_part = {
        "intent": intent.intent,
        "response_text": response_text,
        "music_query": intent.query if intent.intent == "play_music" else None,
        "music_action": intent.action if intent.intent == "music_control" else None,
        "device_result": device_result,
    }

    boundary = uuid.uuid4().hex

    async def generate():
        yield f"--{boundary}\r\n".encode()
        yield b"Content-Type: application/json\r\n\r\n"
        yield json.dumps(json_part, ensure_ascii=False).encode()
        yield f"\r\n--{boundary}\r\n".encode()
        yield b"Content-Type: audio/wav\r\n\r\n"
        yield audio_data
        yield f"\r\n--{boundary}--\r\n".encode()

    return StreamingResponse(
        generate(),
        media_type=f"multipart/mixed; boundary={boundary}",
    )
```

- [ ] **Step 4: main.py を実装**

```python
# server/main.py
import logging

from fastapi import FastAPI

from server.config import ServerConfig
from server.services.oauth import OAuthManager
from server.services.stt import STTService
from server.services.tts import TTSService
from server.services.llm import LLMService
from server.devices.switchbot import SwitchBotClient
from server.devices.tv import TVClient
from server.api.voice import create_voice_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


def create_app_with_services(
    stt: STTService,
    tts: TTSService,
    llm: LLMService,
    switchbot: SwitchBotClient,
    tv: TVClient,
) -> FastAPI:
    app = FastAPI(title="Mochitto Server")
    router = create_voice_router(stt=stt, tts=tts, llm=llm, switchbot=switchbot, tv=tv)
    app.include_router(router)
    return app


def create_app() -> FastAPI:
    config = ServerConfig()

    oauth = OAuthManager()
    stt = STTService(model_name=config.whisper_model)
    tts = TTSService(voicevox_url=config.voicevox_url)
    switchbot = SwitchBotClient(token=config.switchbot_token, secret=config.switchbot_secret)
    llm = LLMService(oauth_manager=oauth, devices_info=[])
    tv = TVClient(host=config.tv_host, mac=config.tv_mac)

    app = create_app_with_services(stt=stt, tts=tts, llm=llm, switchbot=switchbot, tv=tv)

    # lifespan で使えるように state に保存
    app.state.oauth = oauth
    app.state.switchbot = switchbot
    app.state.llm = llm
    app.state.tv = tv

    return app
```

- [ ] **Step 5: テストがパスすることを確認**

Run: `uv run pytest tests/server/api/test_voice.py -v`
Expected: PASS

- [ ] **Step 6: コミット**

```bash
git add server/api/voice.py server/main.py tests/server/api/test_voice.py
git commit -m "feat: FastAPI voiceエンドポイント + サーバーメイン起動を追加"
```

---

## Chunk 4: クライアント側コンポーネント

### Task 10: クライアント設定

**Files:**
- Create: `client/config.py`

- [ ] **Step 1: 実装**

```python
# client/config.py
from pydantic_settings import BaseSettings


class ClientConfig(BaseSettings):
    model_config = {"env_file": ".env", "extra": "ignore"}

    server_url: str = "http://192.168.1.100:8000"
    porcupine_access_key: str
    wake_word_path: str = "mochitto.ppn"

    # 録音パラメータ
    silence_threshold: int = 500
    silence_duration: float = 1.5
    max_record_seconds: float = 15.0
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024
```

- [ ] **Step 2: コミット**

```bash
git add client/config.py
git commit -m "feat: クライアント設定モジュールを追加"
```

---

### Task 11: Audio Recorder（発話録音）

**Files:**
- Create: `client/audio_recorder.py`
- Create: `tests/client/test_audio_recorder.py`

- [ ] **Step 1: テストを書く**

```python
# tests/client/test_audio_recorder.py
import struct

from client.audio_recorder import compute_rms


def test_compute_rms_silence():
    """無音データのRMSは0"""
    silence = struct.pack("<" + "h" * 100, *([0] * 100))
    assert compute_rms(silence) == 0


def test_compute_rms_loud():
    """大きい音のRMSは閾値を超える"""
    loud = struct.pack("<" + "h" * 100, *([10000] * 100))
    rms = compute_rms(loud)
    assert rms > 500
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/client/test_audio_recorder.py -v`
Expected: FAIL

- [ ] **Step 3: 実装**

```python
# client/audio_recorder.py
import io
import logging
import math
import struct
import wave

logger = logging.getLogger(__name__)


def compute_rms(data: bytes) -> int:
    """16bit PCMデータのRMS値を計算"""
    count = len(data) // 2
    if count == 0:
        return 0
    shorts = struct.unpack(f"<{count}h", data)
    sum_squares = sum(s * s for s in shorts)
    return int(math.sqrt(sum_squares / count))


class AudioRecorder:
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024,
        silence_threshold: int = 500,
        silence_duration: float = 1.5,
        max_record_seconds: float = 15.0,
    ):
        self._sample_rate = sample_rate
        self._channels = channels
        self._chunk_size = chunk_size
        self._silence_threshold = silence_threshold
        self._silence_duration = silence_duration
        self._max_record_seconds = max_record_seconds

    def record(self, stream) -> bytes:
        """PyAudio streamからWAVデータを録音して返す。無音検出で自動停止。"""
        frames: list[bytes] = []
        silent_chunks = 0
        max_chunks = int(self._max_record_seconds * self._sample_rate / self._chunk_size)
        silence_chunks_limit = int(self._silence_duration * self._sample_rate / self._chunk_size)

        logger.info("録音開始...")

        for _ in range(max_chunks):
            data = stream.read(self._chunk_size, exception_on_overflow=False)
            frames.append(data)

            rms = compute_rms(data)
            if rms < self._silence_threshold:
                silent_chunks += 1
            else:
                silent_chunks = 0

            if silent_chunks >= silence_chunks_limit:
                logger.info("無音検出で録音終了")
                break

        logger.info("録音完了: %d フレーム", len(frames))

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self._channels)
            wf.setsampwidth(2)  # 16bit
            wf.setframerate(self._sample_rate)
            wf.writeframes(b"".join(frames))
        return buf.getvalue()
```

- [ ] **Step 4: テストがパスすることを確認**

Run: `uv run pytest tests/client/test_audio_recorder.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add client/audio_recorder.py tests/client/test_audio_recorder.py
git commit -m "feat: 音声録音モジュール（無音検出付き）を追加"
```

---

### Task 12: Audio Player + Server Client

**Files:**
- Create: `client/audio_player.py`
- Create: `client/server_client.py`
- Create: `tests/client/test_server_client.py`

- [ ] **Step 1: テストを書く**

```python
# tests/client/test_server_client.py
import json

from client.server_client import parse_multipart_response


def test_parse_multipart_response():
    boundary = "test_boundary"
    json_data = {"intent": "chat", "response_text": "テスト"}
    audio_data = b"FAKE_WAV"

    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json\r\n\r\n"
        f"{json.dumps(json_data)}"
        f"\r\n--{boundary}\r\n"
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + audio_data + f"\r\n--{boundary}--\r\n".encode()

    parsed_json, parsed_audio = parse_multipart_response(body, boundary)
    assert parsed_json["intent"] == "chat"
    assert parsed_audio == audio_data
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/client/test_server_client.py -v`
Expected: FAIL

- [ ] **Step 3: server_client.py を実装**

```python
# client/server_client.py
import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)


def parse_multipart_response(body: bytes, boundary: str) -> tuple[dict, bytes]:
    """multipart/mixed レスポンスをパースし、(json_dict, audio_bytes) を返す"""
    parts = body.split(f"--{boundary}".encode())
    json_data = {}
    audio_data = b""

    for part in parts:
        if b"application/json" in part:
            json_start = part.find(b"\r\n\r\n") + 4
            json_bytes = part[json_start:].strip()
            json_data = json.loads(json_bytes)
        elif b"audio/wav" in part:
            audio_start = part.find(b"\r\n\r\n") + 4
            audio_data = part[audio_start:]
            if audio_data.endswith(b"\r\n"):
                audio_data = audio_data[:-2]

    return json_data, audio_data


class ServerClient:
    def __init__(self, server_url: str):
        self._server_url = server_url

    async def send_voice(self, audio_bytes: bytes) -> tuple[dict, bytes]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._server_url}/api/v1/voice",
                files={"audio": ("recording.wav", audio_bytes, "audio/wav")},
            )

            if resp.status_code == 503:
                return {"intent": "error", "response_text": ""}, b""

            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            boundary_match = re.search(r"boundary=(\S+)", content_type)

            if boundary_match:
                boundary = boundary_match.group(1)
                return parse_multipart_response(resp.content, boundary)

            return resp.json(), b""
```

- [ ] **Step 4: audio_player.py を実装**

```python
# client/audio_player.py
import io
import logging
import wave

logger = logging.getLogger(__name__)


class AudioPlayer:
    def __init__(self, pyaudio_instance, output_device_index: int | None = None):
        self._pa = pyaudio_instance
        self._output_device_index = output_device_index

    def play(self, wav_bytes: bytes) -> None:
        if not wav_bytes:
            return

        buf = io.BytesIO(wav_bytes)
        try:
            with wave.open(buf, "rb") as wf:
                stream = self._pa.open(
                    format=self._pa.get_format_from_width(wf.getsampwidth()),
                    channels=wf.getnchannels(),
                    rate=wf.getframerate(),
                    output=True,
                    output_device_index=self._output_device_index,
                )
                chunk = 1024
                data = wf.readframes(chunk)
                while data:
                    stream.write(data)
                    data = wf.readframes(chunk)
                stream.stop_stream()
                stream.close()
        except Exception:
            logger.exception("音声再生エラー")
```

- [ ] **Step 5: テストがパスすることを確認**

Run: `uv run pytest tests/client/test_server_client.py -v`
Expected: PASS

- [ ] **Step 6: コミット**

```bash
git add client/audio_player.py client/server_client.py tests/client/test_server_client.py
git commit -m "feat: 音声再生+サーバー通信クライアントを追加"
```

---

### Task 13: Music Player (mpv + yt-dlp)

**Files:**
- Create: `client/music_player.py`
- Create: `tests/client/test_music_player.py`

- [ ] **Step 1: テストを書く**

```python
# tests/client/test_music_player.py
from unittest.mock import MagicMock, patch

import pytest

from client.music_player import MusicPlayer


def test_build_youtube_url():
    player = MusicPlayer()
    url = player._build_url("abc123")
    assert url == "https://www.youtube.com/watch?v=abc123"


@patch("ytmusicapi.YTMusic")
def test_search_returns_video_id(mock_ytmusic_cls):
    mock_yt = MagicMock()
    mock_yt.search.return_value = [
        {"videoId": "xyz789", "title": "Test Song", "artists": [{"name": "Artist"}]}
    ]
    mock_ytmusic_cls.return_value = mock_yt

    player = MusicPlayer()
    result = player.search("test query")
    assert result["videoId"] == "xyz789"


def test_handle_music_action_stop():
    player = MusicPlayer()
    player._player = MagicMock()
    player._is_playing = True
    player.handle_action("stop")
    player._player.stop.assert_called_once()
    assert not player._is_playing
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/client/test_music_player.py -v`
Expected: FAIL

- [ ] **Step 3: 実装**

```python
# client/music_player.py
import logging
from typing import Any

logger = logging.getLogger(__name__)


class MusicPlayer:
    def __init__(self):
        self._player = None
        self._is_playing = False
        self._original_volume: int = 100

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    def _ensure_player(self):
        if self._player is None:
            import mpv
            self._player = mpv.MPV(ytdl=True, video=False)

    def _build_url(self, video_id: str) -> str:
        return f"https://www.youtube.com/watch?v={video_id}"

    def search(self, query: str) -> dict[str, Any] | None:
        from ytmusicapi import YTMusic
        yt = YTMusic()
        results = yt.search(query, filter="songs")
        if results:
            return results[0]
        return None

    def play(self, query: str) -> str | None:
        result = self.search(query)
        if not result:
            return None

        video_id = result.get("videoId")
        if not video_id:
            return None

        title = result.get("title", "不明")
        url = self._build_url(video_id)

        self._ensure_player()
        self._player.play(url)
        self._is_playing = True
        logger.info("再生開始: %s (%s)", title, url)
        return title

    def handle_action(self, action: str) -> None:
        if not self._player:
            return

        if action == "stop":
            self._player.stop()
            self._is_playing = False
        elif action == "pause":
            self._player.pause = True
        elif action == "resume":
            self._player.pause = False
        elif action == "volume_up":
            self._player.volume = min(150, (self._player.volume or 100) + 10)
        elif action == "volume_down":
            self._player.volume = max(0, (self._player.volume or 100) - 10)

    def duck(self) -> None:
        """音量を一時的に下げる"""
        if self._player and self._is_playing:
            self._original_volume = self._player.volume or 100
            self._player.volume = max(0, int(self._original_volume * 0.2))

    def unduck(self) -> None:
        """音量を元に戻す"""
        if self._player and self._is_playing:
            self._player.volume = self._original_volume
```

- [ ] **Step 4: テストがパスすることを確認**

Run: `uv run pytest tests/client/test_music_player.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add client/music_player.py tests/client/test_music_player.py
git commit -m "feat: YouTube Music再生プレイヤーを追加"
```

---

### Task 14: Wake Word Listener

**Files:**
- Create: `client/wake_word.py`

- [ ] **Step 1: 実装**

```python
# client/wake_word.py
import logging
import struct

logger = logging.getLogger(__name__)


class WakeWordListener:
    def __init__(self, access_key: str, keyword_path: str, sample_rate: int = 16000):
        import pvporcupine
        self._porcupine = pvporcupine.create(
            access_key=access_key,
            keyword_paths=[keyword_path],
        )
        self._sample_rate = sample_rate
        self._frame_length = self._porcupine.frame_length

    @property
    def frame_length(self) -> int:
        return self._frame_length

    @property
    def sample_rate(self) -> int:
        return self._porcupine.sample_rate

    def process(self, pcm_data: bytes) -> bool:
        """PCMデータを処理し、Wake Wordが検出されたらTrueを返す"""
        num_samples = len(pcm_data) // 2
        pcm = struct.unpack_from(f"{num_samples}h", pcm_data)
        keyword_index = self._porcupine.process(pcm)
        if keyword_index >= 0:
            logger.info("Wake Word検出！")
            return True
        return False

    def cleanup(self) -> None:
        self._porcupine.delete()
```

- [ ] **Step 2: コミット**

```bash
git add client/wake_word.py
git commit -m "feat: Porcupine Wake Wordリスナーを追加"
```

---

### Task 15: クライアントメインループ

**Files:**
- Create: `client/main.py`

- [ ] **Step 1: 実装**

```python
# client/main.py
import asyncio
import logging
import os
from pathlib import Path

import pyaudio

from client.config import ClientConfig
from client.wake_word import WakeWordListener
from client.audio_recorder import AudioRecorder
from client.audio_player import AudioPlayer
from client.server_client import ServerClient
from client.music_player import MusicPlayer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# エラー時のキャッシュ済みWAVパス
ERROR_AUDIO_DIR = Path(__file__).parent.parent / "assets" / "error_audio"


class MochittoClient:
    def __init__(self, config: ClientConfig):
        self._config = config
        self._pa = pyaudio.PyAudio()
        self._wake_word = WakeWordListener(
            access_key=config.porcupine_access_key,
            keyword_path=config.wake_word_path,
        )
        self._recorder = AudioRecorder(
            sample_rate=config.sample_rate,
            channels=config.channels,
            chunk_size=config.chunk_size,
            silence_threshold=config.silence_threshold,
            silence_duration=config.silence_duration,
            max_record_seconds=config.max_record_seconds,
        )
        self._player = AudioPlayer(self._pa)
        self._server = ServerClient(config.server_url)
        self._music = MusicPlayer()

    async def run(self) -> None:
        stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self._config.channels,
            rate=self._wake_word.sample_rate,
            input=True,
            frames_per_buffer=self._wake_word.frame_length,
        )

        logger.info("Mochitto起動完了。「モチット」と呼びかけてください。")

        try:
            while True:
                pcm = stream.read(self._wake_word.frame_length, exception_on_overflow=False)

                if self._wake_word.process(pcm):
                    await self._handle_command(stream)

        except KeyboardInterrupt:
            logger.info("終了します...")
        finally:
            stream.stop_stream()
            stream.close()
            self._wake_word.cleanup()
            self._pa.terminate()

    async def _handle_command(self, stream) -> None:
        # 音楽再生中ならduck
        if self._music.is_playing:
            self._music.duck()

        # 録音
        audio_bytes = self._recorder.record(stream)

        # サーバーに送信
        try:
            json_data, audio_data = await self._server.send_voice(audio_bytes)
        except Exception:
            logger.exception("サーバー通信失敗")
            self._play_error_audio("server_error.wav")
            if self._music.is_playing:
                self._music.unduck()
            return

        # 応答音声を再生
        if audio_data:
            self._player.play(audio_data)

        # Intentに応じた追加処理
        intent = json_data.get("intent")

        if intent == "play_music":
            query = json_data.get("music_query")
            if query:
                self._music.play(query)

        elif intent == "music_control":
            action = json_data.get("music_action")
            if action:
                self._music.handle_action(action)

        # unduck（停止した場合を除く）
        if self._music.is_playing:
            self._music.unduck()

    def _play_error_audio(self, filename: str) -> None:
        path = ERROR_AUDIO_DIR / filename
        if path.exists():
            self._player.play(path.read_bytes())
        else:
            logger.warning("エラー音声ファイルが見つかりません: %s", path)


def main():
    config = ClientConfig()
    client = MochittoClient(config)
    asyncio.run(client.run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: コミット**

```bash
git add client/main.py
git commit -m "feat: クライアントメインループを追加"
```

---

## Chunk 5: 統合 + ドキュメント

### Task 16: 起動スクリプトとエントリーポイント

**Files:**
- Modify: `pyproject.toml` （scriptsセクション追加）

- [ ] **Step 1: pyproject.toml にエントリーポイントを追加**

```toml
[project.scripts]
mochitto-client = "client.main:main"
```

サーバーの起動コマンド（uvicorn factory pattern）:
```bash
uv run uvicorn server.main:create_app --factory --host 0.0.0.0 --port 8000
```

クライアントの起動コマンド:
```bash
uv run mochitto-client
```

- [ ] **Step 2: コミット**

```bash
git add pyproject.toml
git commit -m "feat: CLI エントリーポイントを追加"
```

---

### Task 17: OAuth初回認証フロー

**Files:**
- Modify: `server/main.py`（lifespan追加）

- [ ] **Step 1: server/main.py に lifespan イベントを追加し、create_app に接続**

`create_app_with_services` の `FastAPI(title="Mochitto Server")` を `FastAPI(title="Mochitto Server", lifespan=lifespan)` に変更。

さらに以下の lifespan 関数と OAuth フローヘルパーを `server/main.py` に追加:

```python
import asyncio
import socket
import webbrowser
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # OAuth認証チェック
    oauth = app.state.oauth
    if not oauth.is_authenticated:
        await _run_oauth_flow(oauth)

    # SwitchBotデバイス一覧取得
    switchbot = app.state.switchbot
    try:
        devices = await switchbot.get_devices()
        app.state.llm.update_devices(devices)
        logger.info("SwitchBotデバイス %d 件を取得", len(devices))
    except Exception:
        logger.warning("SwitchBotデバイス一覧の取得に失敗")

    yield

    # クリーンアップ
    await app.state.tv.disconnect()


async def _run_oauth_flow(oauth: OAuthManager) -> None:
    """uvicorn起動前にOAuth認証フローを実行する。
    Starletteを使い一時的なHTTPサーバーでコールバックを受け付ける。"""
    import uvicorn
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import HTMLResponse
    from starlette.routing import Route

    code_verifier = oauth._generate_code_verifier()
    port = _find_free_port()
    redirect_uri = f"http://localhost:{port}/callback"
    auth_url = oauth.get_authorize_url(redirect_uri, code_verifier)

    received_code: asyncio.Future[str] = asyncio.get_event_loop().create_future()

    async def callback(request: Request):
        code = request.query_params.get("code")
        if code:
            received_code.set_result(code)
            return HTMLResponse("<h1>認証成功！このウィンドウを閉じてください。</h1>")
        return HTMLResponse("エラー", status_code=400)

    callback_app = Starlette(routes=[Route("/callback", callback)])
    config = uvicorn.Config(callback_app, host="localhost", port=port, log_level="warning")
    server = uvicorn.Server(config)

    # サーバーをバックグラウンドで起動
    serve_task = asyncio.create_task(server.serve())

    logger.info("ブラウザで以下のURLを開いて認証してください:\n%s", auth_url)
    webbrowser.open(auth_url)

    code = await received_code
    await oauth.exchange_code(code, redirect_uri, code_verifier)
    server.should_exit = True
    await serve_task


def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]
```

- [ ] **Step 2: コミット**

```bash
git add server/main.py
git commit -m "feat: OAuth初回認証フロー + SwitchBotデバイス取得をlifespanに追加"
```

---

### Task 18: 全体テスト実行 + Push

- [ ] **Step 1: 全テストを実行**

Run: `uv run pytest -v`
Expected: 全テスト PASS

- [ ] **Step 2: リントチェック**

Run: `uv run ruff check .`
Expected: エラーなし（あれば修正）

- [ ] **Step 3: リモートにPush**

```bash
git push -u origin main
```

- [ ] **Step 4: docker-compose でVoiceVoxが起動できることを確認**

Run: `docker compose up -d voicevox && curl -s http://localhost:50021/version`
Expected: VoiceVox のバージョン番号が返る
