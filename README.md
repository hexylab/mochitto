# Mochitto 🟢

> 「モチット！」と呼べば、ずんだもんが動かしてくれるのだ。

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen?style=flat-square)]()

---

## 概要

**Mochitto** は、ずんだもんの声で応答する日本語ボイスアシスタントです。
「モチット！」と話しかけるだけで、照明・エアコン・カーテン・テレビの操作から、Web検索、YouTube Musicの再生まで自然な会話で操作できます。

Raspberry Pi（クライアント）と開発マシン（サーバー）のクライアント・サーバー構成で動作します。
LAN内通信で低レイテンシを実現しつつ、サーバー側のGPUで高精度な音声認識と自然言語理解を行います。

---

## 機能

- **ウェイクワード検出** — 「モチット」で起動。Porcupineによるオンデバイス検出
- **日本語音声認識** — Faster-Whisper (large-v3) による高精度な日本語 STT
- **ずんだもん音声合成** — VoiceVox Engine でずんだもん（speaker=3）の声で応答
- **自然言語理解** — GPT-5.4 (Codex OAuth) による意図分類と応答生成
- **スマートホーム操作** — SwitchBot Cloud API 経由で照明・エアコン・カーテンを制御
- **テレビ操作** — SwitchBot Hub Mini の赤外線リモコンで Hisense TV を操作
- **Web検索** — 「〜を調べて」でリアルタイム検索し、結果を要約して読み上げ
- **YouTube Music 再生** — 「〜の音楽を流して」で楽曲を検索・ストリーミング再生
- **音楽との共存** — 音声コマンド中は BGM を自動ダッキング（音量を一時的に下げる）

---

## アーキテクチャ

```
┌─────────────────────────────────────────────┐
│           Raspberry Pi（クライアント）          │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │Porcupine │  │ 音声録音  │  │    mpv    │  │
│  │(Wake Word)│→│(PyAudio)  │  │(音楽再生)  │  │
│  └──────────┘  └────┬─────┘  └───────────┘  │
│                     │ WAV                    │
│                     ▼                        │
│              ┌─────────────┐                 │
│              │ HTTP Client │                 │
│              └──────┬──────┘                 │
│                     │                        │
└─────────────────────┼────────────────────────┘
                      │ HTTP/LAN
                      │  POST /api/v1/voice
                      │  ← multipart/mixed (JSON + WAV)
┌─────────────────────┼────────────────────────┐
│          開発マシン（サーバー）                  │
│                     ▼                        │
│  ┌──────────────────────────────────┐         │
│  │    FastAPI Gateway               │         │
│  └──┬──────┬──────┬────────┬────────┘         │
│     │      │      │        │                  │
│     ▼      ▼      ▼        ▼                  │
│  ┌──────┐┌──────┐┌──────┐┌──────────────┐     │
│  │ STT  ││ TTS  ││ LLM  ││   Device     │     │
│  │Faster││Voice-││GPT-  ││  Control     │     │
│  │Whisp-││ Vox  ││5.4   ││ (SwitchBot   │     │
│  │er    ││Docker││Codex ││  + TV IR)    │     │
│  └──────┘└──────┘└──────┘└──────────────┘     │
└────────────────────────────────────────────────┘
```

### 処理フロー

```
1. RPi: Porcupine が「モチット」を検出
2. RPi: PyAudio でユーザー発話を録音（無音検出で終了）
3. RPi → サーバー: POST /api/v1/voice に WAV 送信
4. サーバー: Faster-Whisper で音声 → テキスト変換
5. サーバー: GPT-5.4 でテキスト → 意図 + 応答を生成
6. サーバー: 意図に応じた処理を実行
   - device_control → SwitchBot / TV 操作
   - web_search     → GPT-5.4 の web_search ツールで検索・要約
   - play_music     → music_query をレスポンスに含める
   - chat           → 応答テキストのみ
7. サーバー: VoiceVox でずんだもん音声を合成
8. サーバー → RPi: multipart レスポンス（JSON + WAV）を返却
9. RPi: ずんだもん音声を再生
10. RPi: music_query があれば mpv で音楽を再生開始
```

---

## 必要なもの

### ハードウェア

| 機器 | 役割 |
|------|------|
| Raspberry Pi (4 以上推奨) | クライアント。ウェイクワード検出・音声入出力 |
| スピーカーフォン (例: EMEET) | マイク入力 + スピーカー出力。エコーキャンセリング推奨 |
| 開発マシン (GPU 推奨) | サーバー。VRAM 8GB 以上推奨 (Faster-Whisper large-v3 で約 6GB 使用) |
| SwitchBot Hub Mini | 赤外線リモコン対応デバイス (テレビ等) の制御に必要 |

### アカウント・サブスクリプション

| サービス | 用途 | 料金 |
|----------|------|------|
| [Picovoice Console](https://console.picovoice.ai/) | カスタムウェイクワード (.ppn) の生成 | 無料（個人・非商用） |
| [SwitchBot](https://www.switch-bot.com/) | スマートホームデバイスの API アクセス | 無料（デバイス購入が別途必要） |
| [ChatGPT Plus](https://openai.com/chatgpt/pricing/) | GPT-5.4 の利用（Codex OAuth 経由） | 月額制 |

---

## クイックスタート

### 前提条件

- Docker / Docker Compose
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)（GPU 利用時）
- [uv](https://docs.astral.sh/uv/)（ローカル開発・クライアント用）

### 1. リポジトリのクローン

```bash
git clone https://github.com/hexylab/mochitto.git
cd mochitto
```

### 2. ウェイクワードファイルの準備

[Picovoice Console](https://console.picovoice.ai/) でアカウントを作成し、カスタムウェイクワードを生成します。

1. Porcupine → Custom Wake Word を選択
2. 言語: **Japanese**、テキスト: **「モチット」** を入力
3. ターゲットプラットフォーム: **Raspberry Pi (ARM)** を選択
4. 生成された `.ppn` ファイルをプロジェクトルートに配置

```
mochitto/
└── mochitto.ppn   ← ここに配置
```

### 3. サーバーのセットアップ

```bash
# .env ファイルの作成
cp .env.example .env  # なければ下記を参照して手動作成
```

`.env` を編集してサーバーの設定を行います（詳細は[設定](#設定)セクションを参照）。

```bash
# Docker Compose でサーバー + VoiceVox Engine を起動
docker compose up -d
```

Mochitto サーバー（GPU 対応）と VoiceVox Engine が一括で起動します。
初回起動時はブラウザが自動で開き、ChatGPT アカウントの OAuth 認証が求められます。
認証が完了すると `auth.json` にトークンが保存され、次回以降は自動でリフレッシュされます。

> **ローカル開発時**（Docker を使わない場合）:
> ```bash
> uv sync
> uv run uvicorn server.main:create_app --factory --host 0.0.0.0 --port 8000
> ```
> VoiceVox Engine は別途 `docker compose up -d voicevox` で起動してください。

### 4. クライアント（Raspberry Pi）のセットアップ

```bash
# クライアント用の依存関係をインストール
uv sync --extra client

# .env ファイルの作成（RPi 側にも配置）
```

`.env` に `SERVER_URL` と `PORCUPINE_ACCESS_KEY` を設定します。

```bash
# クライアントの起動
uv run mochitto-client
```

「Mochitto起動完了。『モチット』と呼びかけてください。」と表示されたら準備完了です。

---

## 設定

サーバーおよびクライアントの設定は `.env` ファイル（またはシェル環境変数）で管理します。

```dotenv
# ===== サーバー側 =====

# SwitchBot API 認証情報（SwitchBot アプリ → プロフィール → 開発者向けオプション で取得）
SWITCHBOT_TOKEN=your_switchbot_token
SWITCHBOT_SECRET=your_switchbot_secret

# VoiceVox Engine の URL
# Docker Compose 利用時: http://voicevox:50021（デフォルト）
# ローカル開発時: http://localhost:50021
VOICEVOX_URL=http://voicevox:50021

# Faster-Whisper のモデルサイズ（デフォルト: large-v3）
# 選択肢: tiny / base / small / medium / large-v2 / large-v3
WHISPER_MODEL=large-v3

# ===== クライアント側（Raspberry Pi）=====

# サーバーの URL
SERVER_URL=http://192.168.1.100:8000

# Picovoice のアクセスキー（Picovoice Console で取得）
PORCUPINE_ACCESS_KEY=your_picovoice_access_key
```

---

## テクノロジースタック

| カテゴリ | 技術 | 詳細 |
|----------|------|------|
| 言語 | Python 3.12+ | クライアント・サーバー共通 |
| パッケージ管理 | [uv](https://docs.astral.sh/uv/) | 高速な依存解決 |
| サーバー FW | FastAPI + uvicorn | 非同期対応 |
| HTTP クライアント | httpx | async 対応 |
| 音声認識 (STT) | Faster-Whisper (large-v3) | GPU 対応、高精度な日本語認識 |
| 音声合成 (TTS) | VoiceVox Engine (Docker) | ずんだもん (speaker=3) |
| 自然言語理解 | OpenAI Responses API (GPT-5.4) | Codex OAuth (PKCE) 経由 |
| ウェイクワード | pvporcupine | カスタム日本語ウェイクワード「モチット」 |
| 音声入力 | PyAudio | Raspberry Pi 側のマイク入力 |
| 音楽再生 | python-mpv + yt-dlp | YouTube Music ストリーミング |
| スマートホーム | SwitchBot Cloud API | 照明・エアコン・カーテン・TV (IR) |
| コンテナ | Docker / docker-compose | サーバー + VoiceVox Engine（NVIDIA GPU 対応） |

---

## プロジェクト構成

```
mochitto/
├── client/                     # Raspberry Pi 側
│   ├── main.py                 # エントリーポイント（メインループ）
│   ├── wake_word.py            # Porcupine ウェイクワード検出
│   ├── audio_recorder.py       # 発話録音（無音検出で自動停止）
│   ├── audio_player.py         # VoiceVox 音声の再生
│   ├── music_player.py         # mpv + yt-dlp 音楽再生
│   ├── server_client.py        # サーバー API 通信
│   └── config.py               # 設定
│
├── server/                     # 開発マシン側
│   ├── main.py                 # FastAPI アプリ起動
│   ├── api/
│   │   └── voice.py            # POST /api/v1/voice エンドポイント
│   ├── services/
│   │   ├── stt.py              # Faster-Whisper STT
│   │   ├── tts.py              # VoiceVox TTS
│   │   ├── llm.py              # GPT-5.4 Responses API
│   │   └── oauth.py            # Codex OAuth PKCE 管理
│   ├── devices/
│   │   └── switchbot.py        # SwitchBot Cloud API
│   └── config.py               # 設定
│
├── tests/                      # テスト
├── docs/                       # ドキュメント・設計書
├── assets/                     # エラー音声ファイル等
├── Dockerfile                 # サーバーコンテナ（NVIDIA CUDA ベース）
├── docker-compose.yml          # サーバー + VoiceVox Engine 起動用
├── .dockerignore              # Docker ビルド除外設定
└── pyproject.toml              # 依存管理
```

---

## テストの実行

```bash
uv run pytest
```

---

## ライセンス

[MIT License](LICENSE)

本プロジェクトは個人・非商用利用を前提としています。
使用している一部のサービス（Porcupine、yt-dlp 等）には商用利用に関する制約があります。ご注意ください。

---

## コントリビュート

Issue や Pull Request を歓迎します。
大きな変更を加える場合は、まず Issue で議論してから実装を始めてください。

---

*ずんだもんの声はずんだもんなのだ。*
