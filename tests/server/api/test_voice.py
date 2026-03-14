import io
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from server.services.llm import IntentResult


@pytest.fixture
def mock_services():
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
        device_id="D001",
    )

    switchbot = AsyncMock()
    switchbot.send_command.return_value = {"statusCode": 100, "message": "success"}

    return {"stt": stt, "tts": tts, "llm": llm, "switchbot": switchbot}


@pytest.fixture
def test_client(mock_services):
    from unittest.mock import MagicMock
    from server.main import create_app_with_services

    oauth = MagicMock()
    oauth.is_authenticated = True

    switchbot = mock_services["switchbot"]
    switchbot.get_devices = AsyncMock(return_value=[])

    llm = mock_services["llm"]
    llm.update_devices = MagicMock()

    app = create_app_with_services(**mock_services)
    app.state.oauth = oauth
    app.state.switchbot = switchbot
    app.state.llm = llm

    with TestClient(app) as client:
        return client


def test_voice_endpoint_device_control(test_client, sample_audio_bytes):
    response = test_client.post(
        "/api/v1/voice",
        files={"audio": ("test.wav", io.BytesIO(sample_audio_bytes), "audio/wav")},
    )
    assert response.status_code == 200
    content_type = response.headers["content-type"]
    assert "multipart/mixed" in content_type


def test_voice_endpoint_low_confidence_stt(test_client, mock_services, sample_audio_bytes):
    mock_services["stt"].transcribe.return_value = MagicMock(
        text="", is_low_confidence=True
    )
    response = test_client.post(
        "/api/v1/voice",
        files={"audio": ("test.wav", io.BytesIO(sample_audio_bytes), "audio/wav")},
    )
    assert response.status_code == 200
