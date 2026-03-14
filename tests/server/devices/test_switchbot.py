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
                ],
                "infraredRemoteList": [
                    {"deviceId": "IR001", "deviceName": "テレビ", "remoteType": "TV"},
                ],
            },
        },
    )

    devices = await switchbot_client.get_devices()
    assert len(devices) == 2
    assert devices[0]["deviceId"] == "D001"
    assert devices[1]["deviceId"] == "IR001"


async def test_send_command(switchbot_client: SwitchBotClient, httpx_mock):
    httpx_mock.add_response(
        url="https://api.switch-bot.com/v1.1/devices/D001/commands",
        method="POST",
        json={"statusCode": 100, "body": {}, "message": "success"},
    )

    result = await switchbot_client.send_command("D001", "turnOff")
    assert result["statusCode"] == 100


async def test_send_ir_command(switchbot_client: SwitchBotClient, httpx_mock):
    """IR機器（テレビ等）へのコマンド送信"""
    httpx_mock.add_response(
        url="https://api.switch-bot.com/v1.1/devices/IR001/commands",
        method="POST",
        json={"statusCode": 100, "body": {}, "message": "success"},
    )

    result = await switchbot_client.send_ir_command("IR001", "turnOn")
    assert result["statusCode"] == 100


def test_auth_headers(switchbot_client: SwitchBotClient):
    headers = switchbot_client._build_headers()
    assert "Authorization" in headers
    assert "sign" in headers
    assert "t" in headers
    assert "nonce" in headers
