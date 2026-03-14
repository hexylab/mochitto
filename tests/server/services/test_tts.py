import httpx
import pytest

from server.services.tts import TTSService

ZUNDAMON_SPEAKER_ID = 3


async def test_tts_synthesize(httpx_mock):
    audio_query_response = {"accent_phrases": [], "speedScale": 1.0}
    httpx_mock.add_response(
        method="POST",
        url=httpx.URL("http://localhost:50021/audio_query", params={"text": "こんにちは", "speaker": "3"}),
        json=audio_query_response,
    )
    httpx_mock.add_response(
        url=httpx.URL("http://localhost:50021/synthesis", params={"speaker": "3"}),
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
