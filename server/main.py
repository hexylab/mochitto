import logging

from fastapi import FastAPI

from server.config import ServerConfig
from server.services.oauth import OAuthManager
from server.services.stt import STTService
from server.services.tts import TTSService
from server.services.llm import LLMService
from server.devices.switchbot import SwitchBotClient
from server.api.voice import create_voice_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


def create_app_with_services(
    stt: STTService,
    tts: TTSService,
    llm: LLMService,
    switchbot: SwitchBotClient,
) -> FastAPI:
    app = FastAPI(title="Mochitto Server")
    router = create_voice_router(stt=stt, tts=tts, llm=llm, switchbot=switchbot)
    app.include_router(router)
    return app


def create_app() -> FastAPI:
    config = ServerConfig()

    oauth = OAuthManager()
    stt = STTService(model_name=config.whisper_model)
    tts = TTSService(voicevox_url=config.voicevox_url)
    switchbot = SwitchBotClient(token=config.switchbot_token, secret=config.switchbot_secret)
    llm = LLMService(oauth_manager=oauth, devices_info=[])

    app = create_app_with_services(stt=stt, tts=tts, llm=llm, switchbot=switchbot)

    # lifespan で使えるように state に保存
    app.state.oauth = oauth
    app.state.switchbot = switchbot
    app.state.llm = llm

    return app
