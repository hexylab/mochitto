"""エラー用音声ファイルをVoiceVox APIおよびプログラム生成で作成するスクリプト

使い方:
    uv run python scripts/generate_error_audio.py
"""

import io
import math
import struct
import wave
from pathlib import Path

import httpx

VOICEVOX_URL = "http://localhost:50021"
SPEAKER_ID = 3  # ずんだもん
OUTPUT_DIR = Path(__file__).parent.parent / "assets" / "error_audio"

MESSAGES = {
    "server_error.wav": "サーバーに接続できなかったのだ",
    "auth_error.wav": "認証が切れてしまったのだ。サーバーを確認してほしいのだ",
}


def generate_voicevox_audio(text: str) -> bytes:
    with httpx.Client(timeout=30.0) as client:
        query_resp = client.post(
            f"{VOICEVOX_URL}/audio_query",
            params={"text": text, "speaker": str(SPEAKER_ID)},
        )
        query_resp.raise_for_status()

        synth_resp = client.post(
            f"{VOICEVOX_URL}/synthesis",
            params={"speaker": str(SPEAKER_ID)},
            json=query_resp.json(),
        )
        synth_resp.raise_for_status()
        return synth_resp.content


def generate_beep_wav(
    frequency: int = 880,
    duration_ms: int = 200,
    pause_ms: int = 150,
    count: int = 2,
    sample_rate: int = 24000,
    volume: float = 0.4,
) -> bytes:
    """ビープ音(2連)のWAVデータを生成"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)

        for i in range(count):
            n_samples = int(sample_rate * duration_ms / 1000)
            fade_samples = int(sample_rate * 0.01)
            for s in range(n_samples):
                envelope = 1.0
                if s < fade_samples:
                    envelope = s / fade_samples
                elif s > n_samples - fade_samples:
                    envelope = (n_samples - s) / fade_samples
                t = s / sample_rate
                value = int(volume * envelope * 32767 * math.sin(2 * math.pi * frequency * t))
                wf.writeframes(struct.pack("<h", max(-32768, min(32767, value))))

            if i < count - 1:
                n_pause = int(sample_rate * pause_ms / 1000)
                wf.writeframes(b"\x00\x00" * n_pause)

    return buf.getvalue()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for filename, text in MESSAGES.items():
        print(f"生成中: {filename} ← 「{text}」")
        audio = generate_voicevox_audio(text)
        (OUTPUT_DIR / filename).write_bytes(audio)
        print(f"  完了: {len(audio):,} bytes")

    print("生成中: voicevox_error.wav ← ビープ音 (プログラム生成)")
    beep = generate_beep_wav()
    (OUTPUT_DIR / "voicevox_error.wav").write_bytes(beep)
    print(f"  完了: {len(beep):,} bytes")

    print("\n全ファイル生成完了:")
    for f in sorted(OUTPUT_DIR.glob("*.wav")):
        print(f"  {f.name} ({f.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
