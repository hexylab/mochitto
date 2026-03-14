import pytest


@pytest.fixture
def sample_audio_bytes() -> bytes:
    """テスト用の最小WAVデータ（44バイトヘッダ + 無音）"""
    import struct
    import wave
    import io

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(struct.pack("<h", 0) * 16000)  # 1秒の無音
    return buf.getvalue()
