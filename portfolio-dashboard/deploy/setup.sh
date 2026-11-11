#!/bin/bash
# GCP e2-micro 初期セットアップスクリプト
set -euo pipefail

echo "=== Portfolio Dashboard セットアップ開始 ==="

# === Node.js (fnm) ===
echo "[1/6] Node.js (fnm) インストール中..."
curl -fsSL https://fnm.vercel.app/install | bash
export PATH="$HOME/.local/share/fnm:$PATH"
eval "$(fnm env)"
fnm install 22
fnm default 22
echo "  Node.js $(node -v) インストール完了"

# === Python (uv) ===
echo "[2/6] Python (uv) インストール中..."
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
echo "  uv $(uv --version) インストール完了"

# === Caddy ===
echo "[3/6] Caddy インストール中..."
sudo apt-get update -qq
sudo apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update -qq && sudo apt-get install -y -qq caddy
echo "  Caddy インストール完了"

# === SQLite3 ===
echo "[4/6] SQLite3 インストール中..."
sudo apt-get install -y -qq sqlite3
echo "  SQLite3 インストール完了"

# === アプリケーション ===
echo "[5/6] アプリケーションセットアップ中..."
if [ ! -d /app ]; then
    echo "  /app ディレクトリが見つかりません。git clone を実行してください:"
    echo "  sudo mkdir -p /app && sudo chown deploy:deploy /app"
    echo "  git clone <your-repo-url> /app"
    exit 1
fi

cd /app
npm ci
npm run build
cd /app/collector && uv sync --extra ai --extra charts  # deploy.sh と同じ（素の uv sync は extras を入れない）

# === データディレクトリ ===
mkdir -p /app/data /app/logs

# === systemd + Caddy + crontab ===
echo "[6/6] サービス設定中..."
sudo cp /app/deploy/portfolio.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable portfolio
sudo systemctl start portfolio

sudo cp /app/deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy

# crontab: 毎月1日 9:00 に前月分の月次バッチ + 毎日 3:00 にバックアップ
# 1日時点の「前日」は前月末日なので、date -d yesterday で前月の年月が得られる
# （date +%Y %m をそのまま渡すと始まったばかりの当月レポートを月初データで作ってしまう）
(crontab -l 2>/dev/null || true; echo "0 9 1 * * cd /app/collector && uv run python main.py \$(date -d yesterday +\\%Y) \$(date -d yesterday +\\%m) >> /app/logs/collector.log 2>&1") | crontab -
(crontab -l 2>/dev/null || true; echo "0 3 * * * /app/deploy/backup.sh >> /app/logs/backup.log 2>&1") | crontab -

echo ""
echo "=== セットアップ完了 ==="
echo "確認コマンド:"
echo "  sudo systemctl status portfolio"
echo "  curl http://localhost:3000/health"
