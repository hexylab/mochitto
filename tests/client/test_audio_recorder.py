import struct
from client.audio_recorder import compute_rms


def test_compute_rms_silence():
    silence = struct.pack("<" + "h" * 100, *([0] * 100))
    assert compute_rms(silence) == 0


def test_compute_rms_loud():
    loud = struct.pack("<" + "h" * 100, *([10000] * 100))
    rms = compute_rms(loud)
    assert rms > 500
