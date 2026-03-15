#!/usr/bin/env bash
set -euo pipefail

# Mochitto クライアントの systemd サービスをインストールするスクリプト
# 使い方: sudo bash scripts/install-service.sh

SERVICE_NAME="mochitto-client"

# プロジェクトディレクトリ（このスクリプトの親ディレクトリ）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 実行ユーザーの検出（sudo 経由の場合は SUDO_USER を使用）
RUN_USER="${SUDO_USER:-$USER}"
if [ "$RUN_USER" = "root" ]; then
    echo "エラー: root ではなく一般ユーザーで sudo 実行してください"
    echo "  sudo bash $0"
    exit 1
fi

# uv のパス検出
UV_PATH=""
for candidate in \
    "/home/$RUN_USER/.local/bin/uv" \
    "/home/$RUN_USER/.cargo/bin/uv" \
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

# サービスファイル生成
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

cat > "$SERVICE_FILE" <<UNIT
[Unit]
Description=Mochitto Voice Assistant Client
After=network-online.target sound.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$UV_PATH run mochitto-client
Restart=on-failure
RestartSec=5

EnvironmentFile=$ENV_FILE

SupplementaryGroups=audio

StandardOutput=journal
StandardError=journal
SyslogIdentifier=mochitto-client

[Install]
WantedBy=multi-user.target
UNIT

echo "サービスファイルを作成しました: $SERVICE_FILE"

# systemd リロード & 有効化
systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"

echo ""
echo "=== インストール完了 ==="
echo ""
echo "  状態確認:   systemctl status $SERVICE_NAME"
echo "  ログ確認:   journalctl -u $SERVICE_NAME -f"
echo "  停止:       sudo systemctl stop $SERVICE_NAME"
echo "  再起動:     sudo systemctl restart $SERVICE_NAME"
echo "  無効化:     sudo systemctl disable --now $SERVICE_NAME"
