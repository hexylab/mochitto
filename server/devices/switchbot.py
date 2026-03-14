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

    async def send_ir_command(
        self, device_id: str, command: str, parameter: str = "default"
    ) -> dict:
        """IR機器（テレビ等）へのコマンド送信。commandTypeが異なる。"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{SWITCHBOT_API_BASE}/devices/{device_id}/commands",
                headers=self._build_headers(),
                json={
                    "command": command,
                    "parameter": parameter,
                    "commandType": "customize",
                },
            )
            resp.raise_for_status()
            return resp.json()
