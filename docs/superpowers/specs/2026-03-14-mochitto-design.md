# Mochitto - ずんだもんホームアシスタント 設計書

## 概要

「モチット！」というWake Wordで起動する、ずんだもんの声で応答するホームアシスタント。
Raspberry Pi + 開発マシンのクライアント・サーバー構成で、スマートホームデバイス操作、Web検索、YouTube Music再生に対応する。

## 要件

### 機能要件

| # | 機能 | 詳細 |
|---|------|------|
| F1 | Wake Word検出 | 「モチット」というWake Wordでアシスタントを起動 |
| F2 | 日本語STT | ユーザーの日本語発話をテキストに変換 |
| F3 | 日本語TTS | VoiceVoxのずんだもんの声で応答 |
| F4 | 意図理解 | GPT-5.4で自然言語からユーザーの意図を構造化データに変換 |
| F5 | SwitchBot操作 | 照明（オン/オフ・明るさ）、エアコン（温度・モード）、カーテン（開閉）、温湿度計（読み取り） |
| F6 | TV操作 | SwitchBot Hub Mini IR経由のテレビ操作（電源、音量、チャンネル等）。通常IR/DIY学習リモコン対応 |
| F7 | Web検索 | 「〜を調べて」でWeb検索し、結果をずんだもんの声で要約読み上げ |
| F8 | 音楽再生 | 「〜の音楽を流して」でYouTube Musicから楽曲検索・ストリーミング再生 |

### 非機能要件

- ハードウェア: Raspberry Pi（クライアント）+ USBスピーカーフォン（エコーキャンセリング推奨）、開発マシン（サーバー、GPU推奨）
- LAN内通信で低レイテンシを確保
- ChatGPT Plus サブスクリプションの範囲内で動作（Codex CLI と同じ OAuth PKCE フローを実装し、サブスクリプション枠でGPT-5.4を利用。5時間あたり30〜150メッセージのレート制限あり）
- サーバーGPU要件: Faster-Whisper large-v3（約6GB VRAM）+ VoiceVox Engine。VRAM 8GB以上推奨。VoiceVoxをCPUモードで動作させる場合はVRAM 6GBで可

## アーキテクチャ

### 全体構成

```
┌─────────────────────────────────────────────┐
│           Raspberry Pi（クライアント）          │
│                                             │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
│  │ Porcupine│  │ 音声録音  │  │   mpv     │ │
│  │(Wake Word)│→│ (PyAudio) │  │(音楽再生)  │ │
│  └──────────┘  └────┬─────┘  └───────────┘ │
│                     │ WAV                    │
│                     ▼                        │
│              ┌─────────────┐                 │
│              │ HTTP Client │                 │
│              └──────┬──────┘                 │
│                     │                        │
└─────────────────────┼────────────────────────┘
                      │ HTTP (LAN)
┌─────────────────────┼────────────────────────┐
│         開発マシン（サーバー）                   │
│                     ▼                        │
│  ┌──────────────────────────────────┐        │
│  │    FastAPI Gateway (メインAPI)    │        │
│  └──┬───────┬───────┬───────┬──────┘        │
│     │       │       │       │                │
│     ▼       ▼       ▼       ▼                │
│  ┌─────┐┌──────┐┌──────┐┌──────────┐        │
│  │ STT ││ TTS  ││ LLM  ││ Device   │        │
│  │Fast-││Voice-││GPT5.4││ Control  │        │
│  │Whis-││ Vox  ││Codex ││(SwitchBot│        │
│  │per  ││Docker││OAuth ││ TV)      │        │
│  └─────┘└──────┘└──────┘└──────────┘        │
└──────────────────────────────────────────────┘
```

### 処理フロー

```
1. RPi: Porcupineが「モチット」を検出
2. RPi: PyAudioでユーザー発話を録音（無音検出で終了）
3. RPi → サーバー: POST /api/v1/voice に WAV送信
4. サーバー: STT (Faster-Whisper) で音声→テキスト変換
5. サーバー: LLM (GPT-5.4) でテキスト→意図+応答を生成
6. サーバー: 意図に応じた処理実行
   - device_control → DeviceController（SwitchBot / TV）
   - web_search → GPT-5.4のweb_searchツール
   - play_music → music_queryをレスポンスに含める
   - chat → 応答テキストのみ
7. サーバー: TTS (VoiceVox) で応答テキスト→ずんだもん音声変換
8. サーバー → RPi: multipartレスポンス（JSON意図情報 + WAVバイナリ）を返却
9. RPi: ずんだもん音声を再生
10. RPi: music_queryがあればmpvで音楽再生
```

## コンポーネント詳細

### RPi側コンポーネント

| コンポーネント | 技術 | 役割 |
|---|---|---|
| WakeWordListener | pvporcupine | 常時マイク監視。「モチット」検出で録音開始 |
| AudioRecorder | PyAudio | Wake Word検出後、ユーザー発話を録音。無音検出で録音終了（無音閾値: 500 RMS、無音継続: 1.5秒、最大録音: 15秒） |
| AudioPlayer | PyAudio or sounddevice | サーバーから返されたVoiceVox音声を再生 |
| MusicPlayer | python-mpv + yt-dlp | YouTube Music楽曲のストリーミング再生・停止・音量制御 |
| ServerClient | httpx (async) | サーバーのFastAPI Gatewayとの通信 |

### サーバー側コンポーネント

| コンポーネント | 技術 | 役割 |
|---|---|---|
| FastAPI Gateway | FastAPI | 全リクエストの受付・オーケストレーション |
| STTService | Faster-Whisper (large-v3) | 音声→テキスト変換。モデルはサーバー起動時にロードし常駐 |
| LLMService | OpenAI Responses API (Codex OAuth) | 意図理解・応答生成・Web検索要約 |
| TTSService | VoiceVox Engine (Docker) | テキスト→ずんだもん音声変換（speaker=3） |
| OAuthManager | 自前実装 (PKCE) | Codex OAuthトークンの取得・リフレッシュ管理 |
| SwitchBotClient | httpx (REST API) | SwitchBot Cloud API v1.1経由でデバイス操作。remoteType判定で通常IR/DIYを自動ルーティング |

### LLM意図解釈

GPT-5.4にシステムプロンプトでJSON形式の出力を指示し、以下のスキーマに従った出力を得る。Codex APIの制約により Structured Outputs は使用せず、フリーフォームのJSON出力をパースする。

#### Intent一覧

| intent | 用途 | 例 |
|---|---|---|
| `device_control` | SwitchBot / TV デバイス操作 | 「電気を消して」「テレビつけて」 |
| `play_music` | YouTube Music楽曲の再生開始 | 「米津玄師の曲を流して」 |
| `music_control` | 再生中の音楽の制御 | 「音楽止めて」「次の曲」 |
| `web_search` | Web検索と結果要約 | 「明日の天気を調べて」 |
| `chat` | 雑談・質問応答 | 「おはよう」「今何時？」 |

#### Intentごとのフィールド定義

全intentを1つの union schema で定義する。`intent` フィールドで分岐し、各intentに固有のフィールドを持つ。

| intent | 必須フィールド | オプションフィールド |
|---|---|---|
| `device_control` | `intent`, `device_type`, `device_category`, `action`, `device_id`, `response` | `params`（デフォルト: `{}`） |
| `play_music` | `intent`, `query`, `response` | なし |
| `music_control` | `intent`, `action`, `response` | なし |
| `web_search` | `intent`, `query` | なし（`response`は後述の2段階処理で生成） |
| `chat` | `intent`, `response` | なし |

#### 出力スキーマ例

```json
// SwitchBot操作: 「リビングの電気を消して」
{
  "intent": "device_control",
  "device_type": "switchbot",
  "device_category": "light",
  "action": "off",
  "params": {},
  "response": "リビングの電気を消したのだ"
}

// SwitchBot操作: 「エアコンを25度の冷房にして」
{
  "intent": "device_control",
  "device_type": "switchbot",
  "device_category": "aircon",
  "action": "set",
  "params": { "temperature": 25, "mode": "cool" },
  "response": "エアコンを冷房25度に設定したのだ"
}

// SwitchBot操作: 「カーテンを閉めて」
{
  "intent": "device_control",
  "device_type": "switchbot",
  "device_category": "curtain",
  "action": "close",
  "params": {},
  "response": "カーテンを閉めたのだ"
}

// TV操作（通常IR）: 「テレビをつけて」
{
  "intent": "device_control",
  "device_type": "switchbot",
  "device_category": "tv",
  "action": "power_on",
  "device_id": "IR001",
  "params": {},
  "response": "テレビをつけたのだ"
}

// TV操作（通常IR）: 「テレビの音量を上げて」
{
  "intent": "device_control",
  "device_type": "switchbot",
  "device_category": "tv",
  "action": "volume_up",
  "device_id": "IR001",
  "params": {},
  "response": "テレビの音量を上げたのだ"
}

// TV操作（DIY）: 「テレビのチャンネルを変えて」（ボタン名指定が必要）
{
  "intent": "device_control",
  "device_type": "switchbot",
  "device_category": "tv",
  "action": "channel_up",
  "device_id": "IR002",
  "params": { "button_name": "15" },
  "response": "チャンネルを変えたのだ"
}

// 音楽再生: 「米津玄師のLemonを流して」
{
  "intent": "play_music",
  "query": "米津玄師 Lemon",
  "response": "米津玄師のLemonを再生するのだ"
}

// 音楽制御: 「音楽を止めて」
{
  "intent": "music_control",
  "action": "stop",
  "response": "音楽を止めたのだ"
}

// Web検索: 「明日の天気を調べて」（1回目のLLM呼び出し、意図判定のみ）
{
  "intent": "web_search",
  "query": "明日の天気"
}

// 雑談: 「おはよう」
{
  "intent": "chat",
  "response": "おはようなのだ！今日も元気にがんばるのだ！"
}
```

#### device_control のアクション一覧

| device_category | 有効なaction | params | 備考 |
|---|---|---|---|
| light | `on`, `off`, `brightness` | `{ "brightness": 0-100 }` | 物理デバイス（Color Bulb等）の場合。brightness は絶対値指定 |
| light (IR) | `on`, `off`, `brightness_up`, `brightness_down` | なし | 通常IRリモコンの場合。相対的な明るさ調整のみ |
| light (DIY) | `on`, `off` | その他: `{ "button_name": "ボタン名" }` | DIY学習リモコン。電源以外はアプリ登録ボタン名が必要 |
| aircon | `on`, `off`, `set` | `{ "temperature": int, "mode": "cool"\|"heat"\|"auto" }` | IR経由。setAll コマンドで温度・モード一括設定 |
| curtain | `open`, `close` | なし | SwitchBot Curtain 3 等の物理デバイス |
| tv (通常IR) | `power_on`, `power_off`, `volume_up`, `volume_down`, `channel_up`, `channel_down`, `mute`, `set_channel` | `{ "channel": int }` | SwitchBotリモコンDB照合済みTV |
| tv (DIY) | `power_on`, `power_off` | その他: `{ "button_name": "ボタン名" }` | DIY学習リモコン。電源以外はアプリ登録ボタン名が必要 |
| meter | `status` | なし | 温湿度計。読み取り専用（温度・湿度を応答） |

#### SwitchBot API の commandType ルーティング

SwitchBot Cloud API v1.1 では、デバイスの種別に応じて `commandType` を使い分ける必要がある:

| デバイス種別 | 判定方法 | commandType | 説明 |
|---|---|---|---|
| 物理デバイス | `remoteType` なし | `command` | Curtain, Color Bulb 等。直接制御 |
| 通常 IR | `remoteType` が "TV", "Light" 等 | `command` | SwitchBotリモコンDB照合済み。標準コマンド使用可 |
| DIY IR | `remoteType` が "DIY TV", "DIY Light" 等 | `command` (turnOn/turnOff のみ) / `customize` (その他) | 手動学習リモコン。ボタン名を指定して操作 |

起動時に `GET /v1.1/devices` でデバイス一覧を取得し、各デバイスの `remoteType` / `deviceType` からルーティングを自動判定する。

#### music_control のアクション一覧

| action | 説明 |
|---|---|
| `stop` | 再生停止 |
| `pause` | 一時停止 |
| `resume` | 再生再開 |
| `volume_up` | 音量を上げる |
| `volume_down` | 音量を下げる |

#### web_search の処理フロー（2段階LLM呼び出し）

`web_search` intentは他のintentと異なり、2回のLLM呼び出しを行う：

```
1回目: Structured Outputs で意図判定
  入力: ユーザー発話テキスト
  出力: { "intent": "web_search", "query": "明日の天気" }

2回目: web_search ツール付きで検索+要約（Structured Outputsは使わない）
  入力: query + システムプロンプト（ずんだもん口調で要約するよう指示）
  ツール: [{"type": "web_search"}]
  出力: 自然文の要約テキスト（例: 「明日の東京の天気は晴れで最高気温は22度なのだ」）
```

1回目でintentとクエリを特定し、2回目でweb_searchツールを使った検索・要約を実行する。2回目の出力テキストがそのままTTSに渡される。

#### デバイスマッピング

SwitchBotデバイスは起動時に SwitchBot Cloud API (`GET /v1.1/devices`) からデバイス一覧を取得する。レスポンスには物理デバイス (`deviceList`) と IR リモコン (`infraredRemoteList`) が含まれ、それぞれ `deviceType` / `remoteType` でデバイス種別を判別できる。

LLMには `id`, `name`, `type` を含むデバイス一覧をシステムプロンプトに注入し、ユーザーの発話から適切なデバイスを選択させる。`type` にはデバイス種別（"Light", "DIY TV", "Air Conditioner", "Curtain3", "Meter" 等）が含まれるため、LLMはDIYデバイスの制限を考慮したアクションを出力できる。

```json
// LLMシステムプロンプトに注入されるデバイス一覧の例
[
  {"id": "D001", "name": "リビング照明", "type": "Light"},
  {"id": "D002", "name": "ダイニング照明", "type": "DIY Light"},
  {"id": "D003", "name": "エアコン", "type": "Air Conditioner"},
  {"id": "D004", "name": "カーテン", "type": "Curtain3"},
  {"id": "D005", "name": "テレビ", "type": "DIY TV"},
  {"id": "D006", "name": "温湿度計", "type": "Meter"}
]
```

#### 正式対応デバイスカテゴリ

以下の5カテゴリを正式対応とする。それ以外のデバイス（Smart Lock, Hub Mini 等）はデバイス一覧には含まれるが、操作対象外とする。

| カテゴリ | 対応 deviceType / remoteType | 制御方法 |
|---|---|---|
| 照明 (light) | Color Bulb, Light, DIY Light | 物理 / IR / DIY IR |
| エアコン (aircon) | Air Conditioner, DIY Air Conditioner | IR / DIY IR |
| カーテン (curtain) | Curtain3 等 | 物理デバイス |
| テレビ (tv) | TV, DIY TV | IR / DIY IR |
| 温湿度計 (meter) | Meter, MeterPlus | センサー読み取り |

## 音楽再生中の音声コマンド

音楽再生中にユーザーが「モチット」と発話した場合：

1. Wake Word検出時にmpvの音量を自動で一時的に下げる（duck処理）
2. ユーザー発話を録音・送信
3. LLMが `music_control` intent（停止・音量変更等）または他のintentを返す
4. 応答音声を再生した後、mpvの音量を元に戻す（`music_control`で停止した場合を除く）

エコーキャンセリング対応のスピーカーフォンであれば、スピーカー出力とマイク入力を分離できるため、音楽再生中でもWake Word検出は動作する想定。ただし、大音量時は検出精度が低下する可能性がある。

## エラーハンドリング

### 方針

すべてのエラーはずんだもんの声でユーザーに通知する。致命的でないエラーではシステムを停止せず、次のWake Wordを待つ状態に戻る。

### エラー種別と対応

| エラー | 対応 | ユーザーへの応答例 |
|---|---|---|
| RPi→サーバー通信失敗 | RPi側でローカルに音声応答（事前キャッシュ済みWAV） | 「サーバーに接続できなかったのだ」 |
| STT認識結果が空/信頼度低（`no_speech_prob > 0.6` または `avg_logprob < -1.0`） | LLMには送らず即座にTTSで応答 | 「うまく聞き取れなかったのだ、もう一度言ってほしいのだ」 |
| LLM API通信失敗/タイムアウト | 3回リトライ後にエラー応答 | 「ちょっと考えがまとまらなかったのだ、もう一度試してほしいのだ」 |
| LLM出力のJSONパース失敗 | chat intentとして扱い、LLMの生テキストを応答に使用 | （LLMの生テキストを読み上げ） |
| SwitchBot API失敗 | カテゴリ名を含むテンプレートエラーメッセージをTTSで応答 | 「照明の操作に失敗したのだ」「テレビの操作に失敗したのだ」 |
| VoiceVox Engine停止 | RPi側でローカルにエラー音を再生 | （ビープ音のみ） |
| OAuthトークン期限切れ+リフレッシュ失敗 | サーバーログに再認証を促すメッセージ出力。ユーザーには音声で通知 | 「認証が切れてしまったのだ。サーバーを確認してほしいのだ」 |
| YouTube Music再生失敗 | エラーをLLMに渡して応答生成 | 「その曲が見つからなかったのだ」 |

### OAuthトークンの排他制御

OAuthManagerはasyncio.Lockを使い、トークンリフレッシュの同時実行を防止する。リフレッシュ中の他リクエストはロック解放まで待機し、リフレッシュ済みトークンを共有する。

## 通信プロトコル

### APIエンドポイント

```
POST /api/v1/voice
  Content-Type: multipart/form-data
  Body: audio=<WAVファイル>

  Response 200:
  Content-Type: multipart/mixed
  Part 1 (application/json):
  {
    "intent": "device_control" | "play_music" | "music_control" | "web_search" | "chat",
    "response_text": "エアコンを25度に設定したのだ",
    "music_query": null | "米津玄師 Lemon",
    "music_action": null | "stop" | "pause" | "resume" | "volume_up" | "volume_down",
    "device_result": null | { "success": true, "device": "aircon" }
  }
  Part 2 (audio/wav):
  <VoiceVox生成のWAVバイナリ>
```

音声データはbase64ではなくmultipartレスポンスでバイナリとして返す（サイズ効率のため）。

httpxはmultipart/mixedレスポンスのパースをネイティブにサポートしないため、クライアント側ではレスポンスのContent-Typeからboundaryを取得し、手動でパートを分割する。FastAPI側では `StreamingResponse` でmultipartレスポンスを構築する。

VoiceVox Engine停止時はサーバーがHTTP 503を返し、JSONボディにエラー情報を含める。RPi側は503を受けた場合、事前キャッシュ済みのエラー通知WAVを再生する。

## OAuth認証フロー

### 初回認証（セットアップ時に1回）

1. サーバー起動時にOAuthManagerが認証状態を確認
2. 未認証の場合、ターミナルにURLを表示
3. ローカルHTTPサーバー(localhost:1455)でコールバック待受
4. ユーザーがブラウザでChatGPTアカウントにログイン
5. OAuth 2.0 PKCE フローで認可コード取得
6. 認可コード → アクセストークン + リフレッシュトークン交換
7. トークンを auth.json に永続化

### トークン管理

```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "rt_...",
  "expires_at": 1741964800,
  "client_id": "app_EMoamEEZ73f0CkXaXp7hrann"
}
```

- アクセストークン期限切れ5分前に自動リフレッシュ
- リフレッシュ失敗時はターミナルに再ログインを促す
- auth.jsonは.gitignore対象

### LLMServiceからの利用

Codex OAuthトークンはChatGPTバックエンドAPIで使用する（OpenAI開発者APIではない）。
SSEストリーミングが必須で、`response.completed` イベントからレスポンスを取得する。

```
POST https://chatgpt.com/backend-api/codex/responses
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "model": "gpt-5.4",
  "store": false,
  "stream": true,
  "instructions": "<system_prompt>",
  "input": [{"role": "user", "content": "<user_input>"}],
  "tools": [{"type": "web_search"}]  // Web検索時のみ
}
```

注意: `instructions` フィールドにシステムプロンプトを渡す（`input` 配列内の `system` ロールではない）。

## プロジェクト構成

```
mochitto/
├── client/                     # RPi側
│   ├── main.py                 # エントリーポイント（メインループ）
│   ├── wake_word.py            # Porcupine Wake Word検出
│   ├── audio_recorder.py       # 発話録音（無音検出で停止）
│   ├── audio_player.py         # VoiceVox音声の再生
│   ├── music_player.py         # mpv + yt-dlp 音楽再生
│   ├── server_client.py        # サーバーAPI通信
│   └── config.py               # 設定（サーバーURL、デバイス設定等）
│
├── server/                     # 開発マシン側
│   ├── main.py                 # FastAPIアプリ起動
│   ├── api/
│   │   └── voice.py            # POST /api/v1/voice エンドポイント
│   ├── services/
│   │   ├── stt.py              # Faster-Whisper STT
│   │   ├── tts.py              # VoiceVox TTS
│   │   ├── llm.py              # GPT-5.4 Responses API
│   │   └── oauth.py            # Codex OAuth PKCE管理
│   ├── devices/
│   │   └── switchbot.py        # SwitchBot Cloud API（TV IR制御含む）
│   └── config.py               # 設定
│
├── tests/                      # テスト
│   ├── conftest.py             # 共通フィクスチャ
│   └── server/                 # サーバー側テスト
│       ├── api/
│       │   └── test_voice.py
│       ├── devices/
│       │   └── test_switchbot.py
│       └── services/
│           ├── test_llm.py
│           ├── test_oauth.py
│           ├── test_stt.py
│           └── test_tts.py
│
├── assets/
│   └── error_audio/            # エラー時のローカル再生用WAV
│       ├── server_error.wav
│       ├── auth_error.wav
│       └── voicevox_error.wav
│
├── scripts/
│   └── generate_error_audio.py # エラー音声WAV生成スクリプト
│
├── Dockerfile                  # サーバーコンテナ（NVIDIA CUDA ベース）
├── docker-compose.yml          # サーバー + VoiceVox Engine 起動用
├── .dockerignore               # Docker ビルド除外設定
├── pyproject.toml              # 依存管理（uv）
└── .gitignore                  # auth.json, .env等を除外
```

## テクノロジースタック

| カテゴリ | 技術 | 備考 |
|---|---|---|
| 言語 | Python 3.12+ | client/server共通 |
| パッケージ管理 | uv | 高速な依存解決 |
| サーバーFW | FastAPI + uvicorn | 非同期対応 |
| HTTPクライアント | httpx | async対応 |
| STT | faster-whisper | large-v3モデル |
| TTS | VoiceVox Engine | Docker (CPU or GPU)、speaker=3（ずんだもん） |
| LLM | OpenAI Responses API | GPT-5.4, Codex OAuth |
| Wake Word | pvporcupine | カスタム日本語Wake Word「モチット」 |
| 音声入力 | PyAudio | RPi側 |
| 音楽再生 | python-mpv + yt-dlp | RPi側ストリーミング再生 |
| SwitchBot | SwitchBot Cloud API v1.1 | 照明・エアコン・カーテン・TV・温湿度計（通常IR / DIY学習リモコン対応） |
| コンテナ | Docker / docker-compose | サーバー + VoiceVox Engine（NVIDIA GPU 対応） |

## 設定管理

環境変数または`.env`ファイルで管理:

```
# サーバー側
SWITCHBOT_TOKEN=xxx
SWITCHBOT_SECRET=xxx
VOICEVOX_URL=http://voicevox:50021
WHISPER_MODEL=large-v3

# クライアント側
SERVER_URL=http://192.168.1.100:8000
PORCUPINE_ACCESS_KEY=xxx
PORCUPINE_MODEL_PATH=porcupine_params_ja.pv
```

## Wake Word「モチット」について

Porcupine（Picovoice）は日本語のカスタムWake Wordをサポートしている。Picovoice Consoleでテキスト入力（「モチット」）するだけで `.ppn` モデルファイルを生成できる。

セットアップ手順:
1. Picovoice Console（https://console.picovoice.ai/）でアカウント作成（無料）
2. Porcupine → Custom Wake Word → 言語: Japanese → テキスト: 「モチット」
3. Raspberry Pi (ARM) 向けの `.ppn` ファイルをダウンロード
4. プロジェクトの所定パスに配置

短い語（3モーラ）のため誤検出の可能性がある。実運用で精度が不十分な場合は「ねえモチット」等の長いフレーズに変更して対応する。

## 既知のリスク・制約

| リスク | 影響 | 対策 |
|---|---|---|
| yt-dlp はYouTube利用規約上グレーゾーン | 個人利用の範囲では実質的リスクは低い。商用利用は不可 | 個人利用に限定。代替手段が出た場合は移行を検討 |
| yt-dlp はYouTube側の仕様変更で頻繁に壊れる | 音楽再生機能が一時的に使えなくなる | yt-dlpを最新版に保つ。再生失敗時はエラーハンドリングで対応 |
| Codex OAuthのレート制限（Plus: 5時間30-150メッセージ） | 短時間に大量の音声コマンドを送ると制限に達する | ホーム用途では十分な量。制限到達時はエラー応答で通知 |
| Porcupine無料枠は個人非商用のみ | 商用利用時は有料ライセンスが必要 | 個人プロジェクトとして利用 |
