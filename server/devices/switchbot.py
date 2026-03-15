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
        self._device_meta: dict[str, dict] = {}  # deviceId -> device metadata

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
            devices = body.get("deviceList", []) + body.get("infraredRemoteList", [])
            self._device_meta = {d["deviceId"]: d for d in devices}
            return devices

    def get_remote_type(self, device_id: str) -> str:
        """デバイスのremoteType（IR機器）またはdeviceType（物理デバイス）を取得"""
        meta = self._device_meta.get(device_id, {})
        return meta.get("remoteType", meta.get("deviceType", ""))

    def is_diy_device(self, device_id: str) -> bool:
        """DIY（手動学習）IR機器かどうかを判定"""
        return self.get_remote_type(device_id).startswith("DIY ")

    def is_ir_device(self, device_id: str) -> bool:
        """IR機器（赤外線リモコン）かどうかを判定"""
        meta = self._device_meta.get(device_id, {})
        return "remoteType" in meta

    async def get_device_status(self, device_id: str) -> dict:
        """デバイスのステータスを取得（温湿度計等）"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{SWITCHBOT_API_BASE}/devices/{device_id}/status",
                headers=self._build_headers(),
            )
            resp.raise_for_status()
            return resp.json().get("body", {})

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
