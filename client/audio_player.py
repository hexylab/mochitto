import io
import logging
import wave

logger = logging.getLogger(__name__)


class AudioPlayer:
    def __init__(self, pyaudio_instance, output_device_index: int | None = None):
        self._pa = pyaudio_instance
        self._output_device_index = output_device_index

    def play(self, wav_bytes: bytes) -> None:
        if not wav_bytes:
            return

        buf = io.BytesIO(wav_bytes)
        try:
            with wave.open(buf, "rb") as wf:
                stream = self._pa.open(
                    format=self._pa.get_format_from_width(wf.getsampwidth()),
                    channels=wf.getnchannels(),
                    rate=wf.getframerate(),
                    output=True,
                    output_device_index=self._output_device_index,
                )
                chunk = 1024
                data = wf.readframes(chunk)
                while data:
                    stream.write(data)
                    data = wf.readframes(chunk)
                stream.stop_stream()
                stream.close()
        except Exception:
            logger.exception("音声再生エラー")
