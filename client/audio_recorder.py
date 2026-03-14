import io
import logging
import math
import struct
import wave

logger = logging.getLogger(__name__)


def compute_rms(data: bytes) -> int:
    count = len(data) // 2
    if count == 0:
        return 0
    shorts = struct.unpack(f"<{count}h", data)
    sum_squares = sum(s * s for s in shorts)
    return int(math.sqrt(sum_squares / count))


class AudioRecorder:
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024,
        silence_threshold: int = 500,
        silence_duration: float = 1.5,
        max_record_seconds: float = 15.0,
    ):
        self._sample_rate = sample_rate
        self._channels = channels
        self._chunk_size = chunk_size
        self._silence_threshold = silence_threshold
        self._silence_duration = silence_duration
        self._max_record_seconds = max_record_seconds

    def record(self, stream) -> bytes:
        frames: list[bytes] = []
        silent_chunks = 0
        max_chunks = int(self._max_record_seconds * self._sample_rate / self._chunk_size)
        silence_chunks_limit = int(self._silence_duration * self._sample_rate / self._chunk_size)

        logger.info("録音開始...")

        for _ in range(max_chunks):
            data = stream.read(self._chunk_size, exception_on_overflow=False)
            frames.append(data)

            rms = compute_rms(data)
            if rms < self._silence_threshold:
                silent_chunks += 1
            else:
                silent_chunks = 0

            if silent_chunks >= silence_chunks_limit:
                logger.info("無音検出で録音終了")
                break

        logger.info("録音完了: %d フレーム", len(frames))

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self._channels)
            wf.setsampwidth(2)
            wf.setframerate(self._sample_rate)
            wf.writeframes(b"".join(frames))
        return buf.getvalue()
