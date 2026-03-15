import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)


def parse_multipart_response(body: bytes, boundary: str) -> tuple[dict, bytes]:
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

    async def report_error(self, error: str, hostname: str) -> None:
        """エラーレポートをサーバーに送信"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{self._server_url}/api/v1/error-report",
                json={"error": error, "hostname": hostname},
            )

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
