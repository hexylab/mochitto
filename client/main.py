import asyncio
import logging
from pathlib import Path

import pyaudio

from client.config import ClientConfig
from client.wake_word import WakeWordListener
from client.audio_recorder import AudioRecorder
from client.audio_player import AudioPlayer
from client.server_client import ServerClient
from client.music_player import MusicPlayer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ERROR_AUDIO_DIR = Path(__file__).parent.parent / "assets" / "error_audio"


class MochittoClient:
    def __init__(self, config: ClientConfig):
        self._config = config
        self._pa = pyaudio.PyAudio()
        self._wake_word = WakeWordListener(
            access_key=config.porcupine_access_key,
            keyword_path=config.wake_word_path,
            model_path=config.porcupine_model_path,
        )
        self._recorder = AudioRecorder(
            sample_rate=config.sample_rate,
            channels=config.channels,
            chunk_size=config.chunk_size,
            silence_threshold=config.silence_threshold,
            silence_duration=config.silence_duration,
            max_record_seconds=config.max_record_seconds,
        )
        self._player = AudioPlayer(self._pa)
        self._server = ServerClient(config.server_url)
        self._music = MusicPlayer()

    async def run(self) -> None:
        stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self._config.channels,
            rate=self._wake_word.sample_rate,
            input=True,
            frames_per_buffer=self._wake_word.frame_length,
        )

        logger.info("Mochitto起動完了。「モチット」と呼びかけてください。")

        try:
            while True:
                pcm = stream.read(self._wake_word.frame_length, exception_on_overflow=False)

                if self._wake_word.process(pcm):
                    await self._handle_command(stream)

        except KeyboardInterrupt:
            logger.info("終了します...")
        finally:
            stream.stop_stream()
            stream.close()
            self._wake_word.cleanup()
            self._pa.terminate()

    async def _handle_command(self, stream) -> None:
        if self._music.is_playing:
            self._music.duck()

        audio_bytes = self._recorder.record(stream)

        try:
            json_data, audio_data = await self._server.send_voice(audio_bytes)
        except Exception:
            logger.exception("サーバー通信失敗")
            self._play_error_audio("server_error.wav")
            if self._music.is_playing:
                self._music.unduck()
            return

        intent = json_data.get("intent")

        # VoiceVox 503 エラー: ローカルのエラー音を再生
        if intent == "error":
            self._play_error_audio("voicevox_error.wav")
            if self._music.is_playing:
                self._music.unduck()
            return

        if audio_data:
            self._player.play(audio_data)

        if intent == "play_music":
            query = json_data.get("music_query")
            if query:
                self._music.play(query)

        elif intent == "music_control":
            action = json_data.get("music_action")
            if action:
                self._music.handle_action(action)

        if self._music.is_playing:
            self._music.unduck()

    def _play_error_audio(self, filename: str) -> None:
        path = ERROR_AUDIO_DIR / filename
        if path.exists():
            self._player.play(path.read_bytes())
        else:
            logger.warning("エラー音声ファイルが見つかりません: %s", path)


def main():
    config = ClientConfig()
    client = MochittoClient(config)
    asyncio.run(client.run())


if __name__ == "__main__":
    main()
