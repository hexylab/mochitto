import json
import logging
import uuid

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from server.services.stt import STTService
from server.services.tts import TTSService
from server.services.llm import LLMService, IntentResult
from server.services.oauth import OAuthError
from server.devices.switchbot import SwitchBotClient

logger = logging.getLogger(__name__)
client_error_logger = logging.getLogger("mochitto.client_error")


class ErrorReport(BaseModel):
    error: str
    hostname: str = ""


LOW_CONFIDENCE_RESPONSE = "うまく聞き取れなかったのだ、もう一度言ってほしいのだ"

DEVICE_CATEGORY_NAMES = {
    "light": "照明",
    "aircon": "エアコン",
    "curtain": "カーテン",
    "tv": "テレビ",
    "meter": "温湿度計",
}


def create_voice_router(
    stt: STTService,
    tts: TTSService,
    llm: LLMService,
    switchbot: SwitchBotClient,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/error-report")
    async def error_report(report: ErrorReport):
        client_error_logger.error(
            "クライアントエラー [%s]\n%s", report.hostname, report.error
        )
        return {"status": "received"}

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

        # 2. LLM intent classification
        try:
            intent_result = await llm.classify_intent(stt_result.text)
        except OAuthError:
            logger.exception("OAuth認証エラー")
            return await _build_response(
                IntentResult(
                    intent="chat",
                    response="認証が切れてしまったのだ。サーバーを確認してほしいのだ",
                ),
                tts,
            )
        except Exception:
            logger.exception("LLM呼び出し失敗")
            return await _build_response(
                IntentResult(
                    intent="chat",
                    response="ちょっと考えがまとまらなかったのだ、もう一度試してほしいのだ",
                ),
                tts,
            )

        # 3. Execute intent
        device_result = None

        if intent_result.intent == "device_control":
            device_result = await _handle_device(intent_result, switchbot)
            if device_result and not device_result.get("success"):
                device_name = DEVICE_CATEGORY_NAMES.get(
                    intent_result.device_category or "", intent_result.device_category or "デバイス"
                )
                intent_result.response = f"{device_name}の操作に失敗したのだ"

        elif intent_result.intent == "web_search" and intent_result.query:
            search_response = await llm.web_search(intent_result.query)
            intent_result.response = search_response

        # 4. Build response
        return await _build_response(intent_result, tts, device_result)

    return router


async def _handle_device(intent: IntentResult, switchbot: SwitchBotClient) -> dict:
    try:
        device_id = intent.device_id or ""

        # 温湿度計: ステータス読み取り
        if intent.device_category == "meter":
            return await _handle_meter(intent, switchbot, device_id)

        if switchbot.is_diy_device(device_id):
            await _handle_diy_device(intent, switchbot, device_id)
        elif intent.device_category == "tv":
            await _handle_regular_tv(intent, switchbot, device_id)
        elif switchbot.is_ir_device(device_id):
            await _handle_regular_ir(intent, switchbot, device_id)
        else:
            await _handle_physical_device(intent, switchbot, device_id)

        return {"success": True, "device": intent.device_category}

    except Exception as e:
        logger.exception("デバイス操作失敗")
        return {"success": False, "device": intent.device_category, "error": str(e)}


# ── 通常TV（remoteType: "TV"）──────────────────────
# SwitchBot API 標準コマンド: commandType "command"
_REGULAR_TV_ACTIONS = {
    "power_on": "turnOn",
    "power_off": "turnOff",
    "volume_up": "volumeAdd",
    "volume_down": "volumeSub",
    "channel_up": "channelAdd",
    "channel_down": "channelSub",
    "mute": "setMute",
}


async def _handle_regular_tv(
    intent: IntentResult, switchbot: SwitchBotClient, device_id: str
) -> None:
    """通常TV: 全コマンドを commandType "command" で送信"""
    action = intent.action or ""
    command = _REGULAR_TV_ACTIONS.get(action, action)
    parameter = "default"
    if action == "set_channel":
        parameter = str(intent.params.get("channel", ""))
        command = "SetChannel"
    await switchbot.send_command(device_id, command, parameter)


# ── DIY IR 共通処理 ──────────────────────────────
# SwitchBot API仕様: DIYデバイスの標準コマンドは turnOn/turnOff のみ
# それ以外はアプリ登録ボタン名を commandType "customize" で送信
_DIY_POWER_ON = {"on", "open", "power_on"}
_DIY_POWER_OFF = {"off", "close", "power_off"}


async def _handle_diy_device(
    intent: IntentResult, switchbot: SwitchBotClient, device_id: str
) -> None:
    """DIY IR機器: turnOn/turnOff は標準コマンド、他はボタン名で customize"""
    action = intent.action or ""

    if action in _DIY_POWER_ON:
        await switchbot.send_command(device_id, "turnOn")
    elif action in _DIY_POWER_OFF:
        await switchbot.send_command(device_id, "turnOff")
    else:
        button_name = intent.params.get("button_name", "")
        if not button_name:
            raise ValueError(
                f"DIYデバイスのアクション '{action}' にはbutton_nameパラメータが必要です。"
                "SwitchBotアプリに登録されたボタン名を指定してください。"
            )
        await switchbot.send_ir_command(device_id, button_name)


# ── 通常IR（TV以外、remoteType: "Light", "Air Conditioner" 等）──
# IR ライト: brightnessUp/brightnessDown のみ（絶対値指定不可）
_IR_LIGHT_ACTIONS = {
    "on": "turnOn",
    "off": "turnOff",
    "brightness_up": "brightnessUp",
    "brightness_down": "brightnessDown",
}

# IR エアコン: setAll で温度・モード一括設定
_IR_AIRCON_ACTIONS = {"on": "turnOn", "off": "turnOff"}


async def _handle_regular_ir(
    intent: IntentResult, switchbot: SwitchBotClient, device_id: str
) -> None:
    """通常IR機器（TV以外）: 標準コマンドを commandType "command" で送信"""
    action = intent.action or ""
    category = intent.device_category

    if category == "light":
        command = _IR_LIGHT_ACTIONS.get(action, action)
        await switchbot.send_command(device_id, command)

    elif category == "aircon":
        cmd = _IR_AIRCON_ACTIONS.get(action)
        if cmd:
            await switchbot.send_command(device_id, cmd)
        elif action == "set":
            temp = intent.params.get("temperature", 25)
            mode_map = {"cool": "2", "heat": "5", "auto": "1"}
            mode = mode_map.get(intent.params.get("mode", "auto"), "1")
            await switchbot.send_command(device_id, "setAll", f"{temp},{mode},1,on")
        else:
            await switchbot.send_command(device_id, action)
    else:
        await switchbot.send_command(device_id, action)


# ── 物理SwitchBotデバイス（Curtain, Color Bulb 等）──
async def _handle_physical_device(
    intent: IntentResult, switchbot: SwitchBotClient, device_id: str
) -> None:
    """物理SwitchBotデバイス: カテゴリ別のコマンドを送信"""
    action = intent.action or ""
    category = intent.device_category

    if category == "light":
        if action == "on":
            await switchbot.send_command(device_id, "turnOn")
        elif action == "off":
            await switchbot.send_command(device_id, "turnOff")
        elif action == "brightness":
            brightness = str(intent.params.get("brightness", 50))
            await switchbot.send_command(device_id, "setBrightness", brightness)
        else:
            await switchbot.send_command(device_id, action)

    elif category == "curtain":
        if action == "open":
            await switchbot.send_command(device_id, "turnOn")
        elif action == "close":
            await switchbot.send_command(device_id, "turnOff")
        else:
            await switchbot.send_command(device_id, action)
    else:
        await switchbot.send_command(device_id, action)


async def _handle_meter(
    intent: IntentResult, switchbot: SwitchBotClient, device_id: str
) -> dict:
    """温湿度計のステータスを読み取り、responseに結果を設定"""
    status = await switchbot.get_device_status(device_id)
    temperature = status.get("temperature")
    humidity = status.get("humidity")

    device_name = intent.params.get("device_name", "")
    parts = []
    if temperature is not None:
        parts.append(f"気温は{temperature}度")
    if humidity is not None:
        parts.append(f"湿度は{humidity}パーセント")

    if parts:
        location = f"{device_name}の" if device_name else ""
        intent.response = f"{location}{'、'.join(parts)}なのだ"
    else:
        intent.response = "センサーの値が取得できなかったのだ"

    return {"success": True, "device": "meter", "temperature": temperature, "humidity": humidity}


async def _build_response(
    intent: IntentResult,
    tts: TTSService,
    device_result: dict | None = None,
) -> StreamingResponse | JSONResponse:
    response_text = intent.response or ""

    try:
        audio_data = await tts.synthesize(response_text) if response_text else b""
    except Exception:
        logger.exception("TTS合成失敗")
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
