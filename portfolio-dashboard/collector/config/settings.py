"""設定ファイル（SQLite 版）"""

import os
from pathlib import Path

from dotenv import load_dotenv

# .env ファイルの読み込み
load_dotenv(Path(__file__).parent.parent / ".env")

GOOGLE_APPLICATION_CREDENTIALS = os.getenv(
    "GOOGLE_APPLICATION_CREDENTIALS",
    str(
        Path(__file__).parent.parent.parent
        / "data-collector"
        / "config"
        / "my-service-account.json"
    ),
)
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
# Sheets を鍵ファイルなしで読むときの、なりすまし先のサービスアカウント。
# 指定すると実行環境の既定の認証情報（GCE なら VM の SA）からこの SA になりすます。
# このとき GOOGLE_APPLICATION_CREDENTIALS は .env に置かない
SHEETS_IMPERSONATE_SA = os.getenv("SHEETS_IMPERSONATE_SA", "")
DB_PATH = os.getenv(
    "DB_PATH",
    str(Path(__file__).parent.parent.parent / "data" / "portfolio.db"),
)

# WordPress 設定（ブログ自動投稿用）
WP_URL = os.getenv("WP_URL", "")
WP_USER = os.getenv("WP_USER", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")

# WordPress 投稿時に付けるカテゴリ ID（既定: 30 =「ポケモン投資」）
WP_CATEGORY_IDS = [
    int(x) for x in os.getenv("WP_CATEGORY_IDS", "30").split(",") if x.strip()
]

# AI コメント生成（ANTHROPIC_API_KEY は anthropic ライブラリが自動読み取り）
AI_COMMENTS_ENABLED = os.getenv("AI_COMMENTS_ENABLED", "false").lower() == "true"
WP_PUBLISH_ENABLED = os.getenv("WP_PUBLISH_ENABLED", "false").lower() == "true"

# ブログ埋め込みエクスポート（portfolio_{year}_{month}.json + blog_embed HTML 生成）
BLOG_EMBED_ENABLED = os.getenv("BLOG_EMBED_ENABLED", "true").lower() == "true"

# AI コメント強制再生成フラグ（true のとき既存 DB コメントを無視して再生成）
AI_COMMENTS_FORCE = os.getenv("AI_COMMENTS_FORCE", "false").lower() == "true"

# 対応通貨設定
CURRENCY_SETTINGS = {
    "supported_currencies": ["USD", "HKD", "EUR", "GBP"],
    "base_currency": "JPY",
    "foreign_stock_patterns": [".HK", ".L", ".PA", ".DE"],
}

# まとめて後から公開した月（この月の記事にだけ、その旨の注記を出す）
BACKFILLED_MONTHS = [
    x.strip() for x in os.getenv(
        "BACKFILLED_MONTHS", "2026-03,2026-04,2026-05,2026-06,2026-07"
    ).split(",") if x.strip()
]
