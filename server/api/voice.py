import json
import logging
import uuid

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse

from server.services.stt import STTService
from server.services.tts import TTSService
from server.services.llm import LLMService, IntentResult
from server.devices.switchbot import SwitchBotClient

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_RESPONSE = "うまく聞き取れなかったのだ、もう一度言ってほしいのだ"


def create_voice_router(
    stt: STTService,
    tts: TTSService,
    llm: LLMService,
    switchbot: SwitchBotClient,
) -> APIRouter:
    router = APIRouter()

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

        elif intent_result.intent == "web_search" and intent_result.query:
            search_response = await llm.web_search(intent_result.query)
            intent_result.response = search_response

        # 4. Build response
        return await _build_response(intent_result, tts, device_result)

    return router


async def _handle_device(intent: IntentResult, switchbot: SwitchBotClient) -> dict:
    try:
        device_id = intent.device_id or ""

        if intent.device_category == "tv":
            # TV is controlled via SwitchBot Hub Mini IR
            command = _tv_ir_command(intent)
            await switchbot.send_ir_command(device_id, command)
            return {"success": True, "device": "tv"}
        else:
            # Regular SwitchBot devices (light, aircon, curtain)
            command = _switchbot_command(intent)
            await switchbot.send_command(
                device_id, command["command"], command.get("parameter", "default")
            )
            return {"success": True, "device": intent.device_category}

    except Exception as e:
        logger.exception("デバイス操作失敗")
        return {"success": False, "device": intent.device_category, "error": str(e)}


def _tv_ir_command(intent: IntentResult) -> str:
    """TV IR action to SwitchBot IR command mapping"""
    action = intent.action or ""
    action_map = {
        "power_on": "turnOn",
        "power_off": "turnOff",
        "volume_up": "volumeAdd",
        "volume_down": "volumeSub",
        "channel_up": "channelAdd",
        "channel_down": "channelSub",
        "mute": "mute",
    }
    return action_map.get(action, action)


def _switchbot_command(intent: IntentResult) -> dict:
    action = intent.action
    category = intent.device_category

    if category == "light":
        if action == "on":
            return {"command": "turnOn"}
        elif action == "off":
            return {"command": "turnOff"}
        elif action == "brightness":
            return {"command": "setBrightness", "parameter": str(intent.params.get("brightness", 50))}

    elif category == "aircon":
        if action == "on":
            return {"command": "turnOn"}
        elif action == "off":
            return {"command": "turnOff"}
        elif action == "set":
            temp = intent.params.get("temperature", 25)
            mode_map = {"cool": "2", "heat": "5", "auto": "1"}
            mode = mode_map.get(intent.params.get("mode", "auto"), "1")
            return {"command": "setAll", "parameter": f"{temp},{mode},1,on"}

    elif category == "curtain":
        if action == "open":
            return {"command": "turnOn"}
        elif action == "close":
            return {"command": "turnOff"}

    return {"command": action or ""}


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
