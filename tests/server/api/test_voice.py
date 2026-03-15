import io
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from server.services.llm import IntentResult
from server.services.oauth import OAuthError


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
    switchbot.send_ir_command.return_value = {"statusCode": 100, "message": "success"}
    switchbot.is_diy_device = MagicMock(return_value=False)
    switchbot.is_ir_device = MagicMock(return_value=False)
    switchbot.get_remote_type = MagicMock(return_value="")

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


def test_voice_endpoint_oauth_error(test_client, mock_services, sample_audio_bytes):
    """OAuth認証エラー時は固有のエラーメッセージを返す"""
    mock_services["llm"].classify_intent.side_effect = OAuthError("トークン期限切れ")
    response = test_client.post(
        "/api/v1/voice",
        files={"audio": ("test.wav", io.BytesIO(sample_audio_bytes), "audio/wav")},
    )
    assert response.status_code == 200
    assert "認証が切れてしまったのだ" in response.text


def test_voice_endpoint_device_failure(test_client, mock_services, sample_audio_bytes):
    """デバイス操作失敗時はテンプレートエラーメッセージを返す"""
    mock_services["switchbot"].send_command.side_effect = RuntimeError("接続エラー")
    response = test_client.post(
        "/api/v1/voice",
        files={"audio": ("test.wav", io.BytesIO(sample_audio_bytes), "audio/wav")},
    )
    assert response.status_code == 200
    assert "照明の操作に失敗したのだ" in response.text


def test_voice_endpoint_regular_tv(test_client, mock_services, sample_audio_bytes):
    """通常TV（remoteType: TV）は標準コマンドで操作"""
    mock_services["llm"].classify_intent.return_value = IntentResult(
        intent="device_control",
        device_type="switchbot",
        device_category="tv",
        action="volume_up",
        params={},
        response="音量を上げたのだ",
        device_id="IR001",
    )
    mock_services["switchbot"].is_diy_device.return_value = False
    response = test_client.post(
        "/api/v1/voice",
        files={"audio": ("test.wav", io.BytesIO(sample_audio_bytes), "audio/wav")},
    )
    assert response.status_code == 200
    mock_services["switchbot"].send_command.assert_called_with("IR001", "volumeAdd", "default")


def test_voice_endpoint_diy_tv_power(test_client, mock_services, sample_audio_bytes):
    """DIY TV（remoteType: DIY TV）の電源は標準コマンドで操作"""
    mock_services["llm"].classify_intent.return_value = IntentResult(
        intent="device_control",
        device_type="switchbot",
        device_category="tv",
        action="power_on",
        params={},
        response="テレビをつけたのだ",
        device_id="IR002",
    )
    mock_services["switchbot"].is_diy_device.return_value = True
    response = test_client.post(
        "/api/v1/voice",
        files={"audio": ("test.wav", io.BytesIO(sample_audio_bytes), "audio/wav")},
    )
    assert response.status_code == 200
    mock_services["switchbot"].send_command.assert_called_with("IR002", "turnOn")


def test_voice_endpoint_diy_tv_custom_button(test_client, mock_services, sample_audio_bytes):
    """DIY TVのカスタムボタンはbutton_nameでcustomize送信"""
    mock_services["llm"].classify_intent.return_value = IntentResult(
        intent="device_control",
        device_type="switchbot",
        device_category="tv",
        action="volume_up",
        params={"button_name": "9"},
        response="音量を上げたのだ",
        device_id="IR002",
    )
    mock_services["switchbot"].is_diy_device.return_value = True
    response = test_client.post(
        "/api/v1/voice",
        files={"audio": ("test.wav", io.BytesIO(sample_audio_bytes), "audio/wav")},
    )
    assert response.status_code == 200
    mock_services["switchbot"].send_ir_command.assert_called_with("IR002", "9")


def test_voice_endpoint_diy_light(test_client, mock_services, sample_audio_bytes):
    """DIY Lightの電源は標準コマンドで操作"""
    mock_services["llm"].classify_intent.return_value = IntentResult(
        intent="device_control",
        device_type="switchbot",
        device_category="light",
        action="on",
        params={},
        response="電気をつけたのだ",
        device_id="IR003",
    )
    mock_services["switchbot"].is_diy_device.return_value = True
    response = test_client.post(
        "/api/v1/voice",
        files={"audio": ("test.wav", io.BytesIO(sample_audio_bytes), "audio/wav")},
    )
    assert response.status_code == 200
    mock_services["switchbot"].send_command.assert_called_with("IR003", "turnOn")


def test_voice_endpoint_ir_light_brightness(test_client, mock_services, sample_audio_bytes):
    """通常IR Lightの明るさ調整はbrightnessUp/Downで操作"""
    mock_services["llm"].classify_intent.return_value = IntentResult(
        intent="device_control",
        device_type="switchbot",
        device_category="light",
        action="brightness_up",
        params={},
        response="明るくしたのだ",
        device_id="IR004",
    )
    mock_services["switchbot"].is_diy_device.return_value = False
    mock_services["switchbot"].is_ir_device.return_value = True
    response = test_client.post(
        "/api/v1/voice",
        files={"audio": ("test.wav", io.BytesIO(sample_audio_bytes), "audio/wav")},
    )
    assert response.status_code == 200
    mock_services["switchbot"].send_command.assert_called_with("IR004", "brightnessUp")
