#!/usr/bin/env bash
# GCE 本番（portfolio-dashboard）を読み取り専用で確認するラッパー。
# Claude Code の auto mode からはこのスクリプト経由でのみ本番を覗く。
# 書き込み系の操作（バッチ再実行・再起動・デプロイ）はここに足さないこと。
#
# 使い方:
#   gce-ro.sh status          # cron・サービス状態・DB の最新月・WP 投稿
#   gce-ro.sh log [行数]       # collector.log の末尾（既定 80 行、最大 500 行）
#   gce-ro.sh sql "SELECT ..." # 本番 DB に読み取り専用で SELECT
set -euo pipefail

INSTANCE=portfolio-dashboard
ZONE=us-west1-a
DB=/app/portfolio-dashboard/data/portfolio.db
LOG=/app/portfolio-dashboard/logs/collector.log
APP_USER=toshivx

remote() {
  gcloud compute ssh "$INSTANCE" --zone "$ZONE" --command "$1"
}

cmd="${1:-}"
case "$cmd" in
  status)
    remote "echo '--- crontab'; sudo crontab -l -u $APP_USER; \
echo '--- service'; systemctl is-active portfolio; \
echo '--- monthly_pnl 最新月'; sudo -u $APP_USER sqlite3 -readonly $DB 'SELECT MAX(date) FROM monthly_pnl'; \
echo '--- wp_posts 直近'; sudo -u $APP_USER sqlite3 -readonly $DB 'SELECT month, url FROM wp_posts ORDER BY month DESC LIMIT 3'; \
echo '--- log 更新日時'; sudo ls -l $LOG"
    ;;
  log)
    lines="${2:-80}"
    if ! [[ "$lines" =~ ^[0-9]+$ ]] || ((lines < 1 || lines > 500)); then
      echo "行数は 1〜500 の整数で指定してね" >&2
      exit 2
    fi
    remote "sudo tail -n $lines $LOG"
    ;;
  sql)
    query="${2:-}"
    # SELECT / WITH で始まる単文のみ。ドットコマンド（.shell 等）と複文は拒否する
    if ! [[ "$query" =~ ^[[:space:]]*([Ss][Ee][Ll][Ee][Cc][Tt]|[Ww][Ii][Tt][Hh])[[:space:]] ]] || [[ "$query" == *";"* ]]; then
      echo "SELECT / WITH で始まる単文だけ受け付ける（; は不可）" >&2
      exit 2
    fi
    # クエリはリモートのシェルを通さないよう base64 で渡す
    b64=$(printf '%s' "$query" | base64 | tr -d '\n')
    remote "sudo -u $APP_USER sqlite3 -readonly -header $DB \"\$(echo $b64 | base64 -d)\""
    ;;
  *)
    sed -n '2,10p' "$0" >&2
    exit 2
    ;;
esac
