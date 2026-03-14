import logging
import struct

logger = logging.getLogger(__name__)


class WakeWordListener:
    def __init__(self, access_key: str, keyword_path: str, sample_rate: int = 16000):
        import pvporcupine
        self._porcupine = pvporcupine.create(
            access_key=access_key,
            keyword_paths=[keyword_path],
        )
        self._sample_rate = sample_rate
        self._frame_length = self._porcupine.frame_length

    @property
    def frame_length(self) -> int:
        return self._frame_length

    @property
    def sample_rate(self) -> int:
        return self._porcupine.sample_rate

    def process(self, pcm_data: bytes) -> bool:
        num_samples = len(pcm_data) // 2
        pcm = struct.unpack_from(f"{num_samples}h", pcm_data)
        keyword_index = self._porcupine.process(pcm)
        if keyword_index >= 0:
            logger.info("Wake Word検出！")
            return True
        return False

    def cleanup(self) -> None:
        self._porcupine.delete()
