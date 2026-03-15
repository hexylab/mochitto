import json
from unittest.mock import AsyncMock, MagicMock, patch

from server.services.llm import LLMService, IntentResult


def _make_sse_response(response_data: dict):
    """SSEストリーミングレスポンスのモックを作成するヘルパー"""
    completed_event = {
        "type": "response.completed",
        "response": response_data,
    }
    lines = [
        f"data: {json.dumps(completed_event)}",
        "data: [DONE]",
    ]

    async def aiter_lines():
        for line in lines:
            yield line

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = aiter_lines

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    return mock_stream_ctx


def _patch_llm_client(mock_stream_ctx):
    """httpx.AsyncClient をモックし stream() が mock_stream_ctx を返すようにする"""
    mock_client = AsyncMock()
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    patcher = patch("server.services.llm.httpx.AsyncClient", return_value=mock_client)
    return patcher


def test_parse_device_control_intent():
    raw = {
        "intent": "device_control",
        "device_type": "switchbot",
        "device_category": "light",
        "action": "off",
        "params": {},
        "response": "電気を消したのだ",
        "device_id": "D001",
    }
    result = IntentResult.from_dict(raw)
    assert result.intent == "device_control"
    assert result.device_type == "switchbot"
    assert result.action == "off"
    assert result.response == "電気を消したのだ"
    assert result.device_id == "D001"


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


def test_update_devices():
    mock_oauth = AsyncMock()
    service = LLMService(oauth_manager=mock_oauth, devices_info=[])
    service.update_devices([
        {"deviceId": "D001", "deviceName": "リビング照明", "deviceType": "Color Bulb"},
    ])
    assert len(service._devices_info) == 1
    assert service._devices_info[0]["id"] == "D001"


async def test_llm_classify_intent():
    mock_oauth = AsyncMock()
    mock_oauth.get_token.return_value = "test_token"

    service = LLMService(oauth_manager=mock_oauth, devices_info=[])

    response_data = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps({
                            "intent": "chat",
                            "response": "こんにちはなのだ！",
                        }),
                    }
                ],
            }
        ]
    }

    mock_stream_ctx = _make_sse_response(response_data)

    with _patch_llm_client(mock_stream_ctx):
        result = await service.classify_intent("こんにちは")
        assert result.intent == "chat"
        assert result.response == "こんにちはなのだ！"


async def test_llm_classify_intent_parse_failure():
    """LLM出力がJSONでない場合、chatとして扱う"""
    mock_oauth = AsyncMock()
    mock_oauth.get_token.return_value = "test_token"

    service = LLMService(oauth_manager=mock_oauth, devices_info=[])

    response_data = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "これはJSONではないのだ",
                    }
                ],
            }
        ]
    }

    mock_stream_ctx = _make_sse_response(response_data)

    with _patch_llm_client(mock_stream_ctx):
        result = await service.classify_intent("テスト")
        assert result.intent == "chat"
        assert result.response == "これはJSONではないのだ"
