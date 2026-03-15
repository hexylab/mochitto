#!/usr/bin/env bash
set -euo pipefail

# Mochitto クライアントの systemd ユーザーサービスをインストールするスクリプト
# 使い方: bash scripts/install-service.sh （sudo 不要）

SERVICE_NAME="mochitto-client"

# root で実行されたらエラー
if [ "$(id -u)" = "0" ]; then
    echo "エラー: sudo なしで一般ユーザーとして実行してください"
    echo "  bash $0"
    exit 1
fi

RUN_USER="$USER"

# プロジェクトディレクトリ（このスクリプトの親ディレクトリ）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# uv のパス検出
UV_PATH=""
for candidate in \
    "$HOME/.local/bin/uv" \
    "$HOME/.cargo/bin/uv" \
    "$(which uv 2>/dev/null || true)"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
        UV_PATH="$candidate"
        break
    fi
done

if [ -z "$UV_PATH" ]; then
    echo "エラー: uv が見つかりません。先に uv をインストールしてください"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# .env ファイルの確認
ENV_FILE="$PROJECT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "警告: $ENV_FILE が見つかりません。サービス起動前に作成してください"
fi

echo "=== Mochitto クライアント サービスインストール ==="
echo "  ユーザー:     $RUN_USER"
echo "  プロジェクト: $PROJECT_DIR"
echo "  uv:           $UV_PATH"
echo "  .env:         $ENV_FILE"
echo ""

# ユーザーサービスディレクトリの作成
SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"

SERVICE_FILE="$SERVICE_DIR/${SERVICE_NAME}.service"

cat > "$SERVICE_FILE" <<UNIT
[Unit]
Description=Mochitto Voice Assistant Client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
ExecStart=$UV_PATH run mochitto-client
Restart=on-failure
RestartSec=5

EnvironmentFile=$ENV_FILE

StandardOutput=journal
StandardError=journal
SyslogIdentifier=mochitto-client

[Install]
WantedBy=default.target
UNIT

echo "サービスファイルを作成しました: $SERVICE_FILE"

# systemd ユーザーデーモンのリロード & 有効化
systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE_NAME"

# ログインなしでも自動起動するよう linger を有効化
# （sudo が必要なため、失敗しても続行）
echo ""
echo "ログインなしでの自動起動を有効化します（sudo パスワードが求められます）..."
if sudo loginctl enable-linger "$RUN_USER" 2>/dev/null; then
    echo "linger を有効化しました"
else
    echo "警告: linger の有効化に失敗しました。手動で実行してください:"
    echo "  sudo loginctl enable-linger $RUN_USER"
fi

echo ""
echo "=== インストール完了 ==="
echo ""
echo "  状態確認:   systemctl --user status $SERVICE_NAME"
echo "  ログ確認:   journalctl --user -u $SERVICE_NAME -f"
echo "  停止:       systemctl --user stop $SERVICE_NAME"
echo "  再起動:     systemctl --user restart $SERVICE_NAME"
echo "  無効化:     systemctl --user disable --now $SERVICE_NAME"
