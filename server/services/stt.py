import io
import logging
from dataclasses import dataclass

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

NO_SPEECH_PROB_THRESHOLD = 0.6
AVG_LOGPROB_THRESHOLD = -1.0


@dataclass
class STTResult:
    text: str
    no_speech_prob: float
    avg_logprob: float

    @property
    def is_low_confidence(self) -> bool:
        if not self.text.strip():
            return True
        return (
            self.no_speech_prob > NO_SPEECH_PROB_THRESHOLD
            or self.avg_logprob < AVG_LOGPROB_THRESHOLD
        )


class STTService:
    def __init__(self, model_name: str = "large-v3"):
        logger.info("Whisperモデル '%s' をロード中...", model_name)
        self._model = WhisperModel(model_name, device="auto", compute_type="auto")
        logger.info("Whisperモデルのロード完了")

    def transcribe(self, audio_bytes: bytes) -> STTResult:
        audio_file = io.BytesIO(audio_bytes)
        segments, _ = self._model.transcribe(audio_file, language="ja")
        segments_list = list(segments)

        if not segments_list:
            return STTResult(text="", no_speech_prob=1.0, avg_logprob=-2.0)

        text = "".join(seg.text for seg in segments_list)
        avg_no_speech = sum(s.no_speech_prob for s in segments_list) / len(segments_list)
        avg_logprob = sum(s.avg_logprob for s in segments_list) / len(segments_list)

        return STTResult(text=text.strip(), no_speech_prob=avg_no_speech, avg_logprob=avg_logprob)
