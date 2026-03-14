from unittest.mock import MagicMock, patch


from server.services.stt import STTService, STTResult


def test_stt_result_is_low_confidence():
    result = STTResult(text="", no_speech_prob=0.8, avg_logprob=-1.5)
    assert result.is_low_confidence


def test_stt_result_is_valid():
    result = STTResult(text="こんにちは", no_speech_prob=0.1, avg_logprob=-0.3)
    assert not result.is_low_confidence


def test_stt_result_empty_text_is_low_confidence():
    result = STTResult(text="", no_speech_prob=0.1, avg_logprob=-0.3)
    assert result.is_low_confidence


def test_stt_result_high_no_speech_only():
    """no_speech_probだけが閾値を超えてもlow confidence"""
    result = STTResult(text="テスト", no_speech_prob=0.8, avg_logprob=-0.3)
    assert result.is_low_confidence


def test_stt_result_low_logprob_only():
    """avg_logprobだけが閾値を下回ってもlow confidence"""
    result = STTResult(text="テスト", no_speech_prob=0.1, avg_logprob=-1.5)
    assert result.is_low_confidence


@patch("server.services.stt.WhisperModel")
def test_stt_service_init(mock_whisper_cls: MagicMock):
    STTService(model_name="tiny")
    mock_whisper_cls.assert_called_once_with("tiny", device="auto", compute_type="auto")


@patch("server.services.stt.WhisperModel")
def test_stt_service_transcribe(mock_whisper_cls: MagicMock, sample_audio_bytes: bytes):
    mock_segment = MagicMock()
    mock_segment.text = "テスト発話"
    mock_segment.no_speech_prob = 0.05
    mock_segment.avg_logprob = -0.2

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], MagicMock())
    mock_whisper_cls.return_value = mock_model

    service = STTService(model_name="tiny")
    result = service.transcribe(sample_audio_bytes)

    assert result.text == "テスト発話"
    assert not result.is_low_confidence
