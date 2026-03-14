import asyncio
import logging
import socket
import webbrowser
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route

from server.config import ServerConfig
from server.services.oauth import OAuthManager
from server.services.stt import STTService
from server.services.tts import TTSService
from server.services.llm import LLMService
from server.devices.switchbot import SwitchBotClient
from server.api.voice import create_voice_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # OAuth check
    oauth: OAuthManager = app.state.oauth
    if not oauth.is_authenticated:
        await _run_oauth_flow(oauth)

    # Fetch SwitchBot devices
    switchbot: SwitchBotClient = app.state.switchbot
    llm: LLMService = app.state.llm
    try:
        devices = await switchbot.get_devices()
        llm.update_devices(devices)
        logger.info("SwitchBotデバイス %d 件を取得", len(devices))
    except Exception:
        logger.warning("SwitchBotデバイス一覧の取得に失敗", exc_info=True)

    yield


async def _run_oauth_flow(oauth: OAuthManager) -> None:
    code_verifier = oauth._generate_code_verifier()
    port = _find_free_port()
    redirect_uri = f"http://localhost:{port}/callback"
    auth_url = oauth.get_authorize_url(redirect_uri, code_verifier)

    received_code: asyncio.Future[str] = asyncio.get_event_loop().create_future()

    async def callback(request: Request):
        code = request.query_params.get("code")
        if code:
            received_code.set_result(code)
            return HTMLResponse("<h1>認証成功！このウィンドウを閉じてください。</h1>")
        return HTMLResponse("エラー", status_code=400)

    callback_app = Starlette(routes=[Route("/callback", callback)])
    config = uvicorn.Config(callback_app, host="localhost", port=port, log_level="warning")
    server = uvicorn.Server(config)

    serve_task = asyncio.create_task(server.serve())

    logger.info("ブラウザで以下のURLを開いて認証してください:\n%s", auth_url)
    webbrowser.open(auth_url)

    code = await received_code
    await oauth.exchange_code(code, redirect_uri, code_verifier)
    server.should_exit = True
    await serve_task


def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def create_app_with_services(
    stt: STTService,
    tts: TTSService,
    llm: LLMService,
    switchbot: SwitchBotClient,
) -> FastAPI:
    app = FastAPI(title="Mochitto Server", lifespan=lifespan)
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

    app.state.oauth = oauth
    app.state.switchbot = switchbot
    app.state.llm = llm

    return app
