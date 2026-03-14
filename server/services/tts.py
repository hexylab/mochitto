import logging

import httpx

logger = logging.getLogger(__name__)

ZUNDAMON_SPEAKER_ID = 3


class TTSService:
    def __init__(self, voicevox_url: str = "http://localhost:50021"):
        self._base_url = voicevox_url

    async def synthesize(self, text: str, speaker_id: int = ZUNDAMON_SPEAKER_ID) -> bytes:
        if not text.strip():
            raise ValueError("空のテキストは合成できません")

        async with httpx.AsyncClient(timeout=30.0) as client:
            query_resp = await client.post(
                f"{self._base_url}/audio_query",
                params={"text": text, "speaker": str(speaker_id)},
            )
            query_resp.raise_for_status()
            audio_query = query_resp.json()

            synth_resp = await client.post(
                f"{self._base_url}/synthesis",
                params={"speaker": str(speaker_id)},
                json=audio_query,
            )
            synth_resp.raise_for_status()
            return synth_resp.content
