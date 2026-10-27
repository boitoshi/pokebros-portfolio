# pokebros-portfolio

個人投資ポートフォリオの記録・可視化と、pokebros.net の月次株記事（【ポケモン投資】シリーズ）の生成基盤。

- 保有銘柄・月次損益・為替・配当を SQLite に記録し、ダッシュボードで可視化する
- 毎月1日に前月分の株価を収集し、ブログ記事（グラフ埋め込み付き）を WordPress の下書きとして投稿する

> 2026-09-26 に `spreadsheet-chart-vue` から改名。旧名は Google Sheets ＋ Vue の初期構成に由来する。

## 構成

**現行システムは `portfolio-dashboard/`**。GCE e2-micro で本番稼働している。

```
pokebros-portfolio/
├── portfolio-dashboard/    # 現行システム
│   ├── client/             # Vite + React 19 SPA（Recharts / TanStack Query / Tailwind CSS v4）
│   ├── server/             # Hono 4 + Drizzle ORM + better-sqlite3（ポート3000、SPA 静的配信兼用）
│   ├── collector/          # Python バッチ（uv）: 株価収集・ブログ生成・AI コメント・WordPress 投稿
│   ├── data/portfolio.db   # SQLite（gitignore。ローカルは GCS バックアップから復元）
│   ├── deploy/             # GCE 用: deploy.sh / backup.sh / setup.sh / Caddyfile / systemd unit
│   └── scripts/            # 旧 Google Sheets からの移行スクリプト
├── docs/                   # ドキュメント（現行は portfolio-dashboard.md）
├── data-collector/         # 旧構成の収集バッチ。メンテ停止・変更禁止
└── shared/                 # 旧構成の共通定義。メンテ停止・変更禁止
```

データは SQLite が正。Google Sheets は保有銘柄・買付履歴の入力元として残っていて、collector の `--sync` で SQLite へ同期する。

## セットアップ

前提: Node.js、Python 3.12 以上、uv

```bash
cd portfolio-dashboard
npm ci

cd collector
uv sync --extra ai --extra charts   # 素の uv sync は extras を削除するので付ける
```

collector の設定は `portfolio-dashboard/collector/.env` に置く（`DB_PATH`, `SPREADSHEET_ID`, `GOOGLE_APPLICATION_CREDENTIALS` または `SHEETS_IMPERSONATE_SA`, `ANTHROPIC_API_KEY`, `AI_COMMENTS_ENABLED`, `WP_URL`, `WP_USER`, `WP_APP_PASSWORD`, `WP_PUBLISH_ENABLED`, `BLOG_EMBED_ENABLED` など）。Sheets の認証は `GOOGLE_APPLICATION_CREDENTIALS`（鍵ファイル）と `SHEETS_IMPERSONATE_SA`（鍵なし。実行環境の認証情報からそのサービスアカウントになりすます。GCE 向け）の**どちらか一方だけ**を置く（両方あるとエラーで止まる。`.env.example` 参照）。`.env` の `DB_PATH` は GCE のパスなので、ローカルでは環境変数で上書きする。

```bash
DB_PATH=<リポジトリ>/portfolio-dashboard/data/portfolio.db uv run python main.py --blog 2026 8
```

## よく使うコマンド

```bash
cd portfolio-dashboard

npm run dev                                   # server:3000 + client:5173 を並行起動
npm run lint && npm run check && npm run test # 品質チェック（Biome / 型 / テスト）
npm run build
npm run db:migrate -w server                  # DB マイグレーション（冪等）

cd collector
uv run python main.py 2026 8                  # 月次フル収集（収集 → ブログ生成 → WP 下書き）
uv run python main.py --blog 2026 8           # ブログ下書き＋埋め込みの生成のみ
uv run python main.py --sync                  # Google Sheets → SQLite 同期のみ
uv run python main.py --add-purchase 7974.T 2026-08-01 1 8500   # 買付の記録
uv run python main.py --add-dividend 7974.T 2026-06-27 2 118    # 配当の記録
uv run python main.py --benchmark 2026 8     # ベンチマーク（日経225 / S&P500）と TWR の再計算のみ（DB 内の全月が対象）
uv run python main.py --generate-chart 任天堂 7974.T 2023-06-28 2026-03-31 [JPY]  # 株価チャート PNG（DB 非依存。通貨は省略時 JPY）
uv run ruff check . && uv run ty check
```

## デプロイ

`main` への push（`portfolio-dashboard/` 配下の変更）で `.github/workflows/deploy.yml` が起動し、SSH で GCE 上の `deploy/deploy.sh` を実行する（DB バックアップ → git pull → build → migrate → 再起動）。月次バッチは GCE の cron が毎月1日 9:00 に前月分を実行する。

## ドキュメント

- [`AGENTS.md`](AGENTS.md) — 開発ルール・コマンド・環境設定（Claude Code / Codex 共通の正本）
- [`docs/portfolio-dashboard.md`](docs/portfolio-dashboard.md) — 現行システムの詳細（DB テーブル・API・ブログ埋め込み・GCE デプロイ）
- [`PROJECT_PROCEED.md`](PROJECT_PROCEED.md) — 2026-08 で更新停止した旧計画・記録（現在の構成と手順は README.md と docs/ を見る）
- `docs/` のその他のファイル — 旧構成（Google Sheets + Next.js + FastAPI）の記録

## 注意事項

- 個人的な投資記録であり、投資アドバイスを提供するものではない
- 認証情報（サービスアカウント JSON・`.env`）と `portfolio.db` はコミットしない
