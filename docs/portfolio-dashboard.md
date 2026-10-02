# portfolio-dashboard 詳細（現行システム）

## ディレクトリ構成

```
portfolio-dashboard/
├── client/                 # Vite + React 19 SPA
│   └── src/
│       ├── pages/          # Dashboard, Portfolio, History, Currency, Dividend, Reports, ReportDetail
│       ├── components/
│       │   ├── dashboard/  # 新デザイン: GradientHeader, SummaryCard, AssetTrendChart,
│       │   │               #   StockCard, StockPriceChart, PeriodToggle
│       │   ├── layout/     # AppLayout, SiteFooter（全ページ共通: ブログ導線・データ出典・免責・©）
│       │   └── report/     # 新デザイン: ReportHeader, ReportSummaryCard, ReportStockCard,
│       │                   #   CtaBox, ReportFooter, ReportMarkdown（旧表示フォールバック）
│       ├── lib/            # api.ts, formatters.ts, chartUtils.ts
│       └── types/          # API レスポンス型
├── server/                 # Hono 4 + Drizzle + better-sqlite3（ポート3000）
│   ├── src/routes/         # dashboard, portfolio, history, currency, dividend, reports, benchmark, exposure
│   ├── src/services/       # reportData.ts（レポートデータビルダー・形状の正）
│   ├── src/db/schema.ts    # Drizzle スキーマ
│   └── drizzle/migrations/ # マイグレーション SQL（IF NOT EXISTS で冪等化済み）
├── collector/              # Python バッチ（uv）
│   ├── main.py             # --sync / --range / --blog / --repair-pnl / --add-purchase / collect_and_publish
│   ├── collectors/         # db_writer, report_generator, ai_comment, wp_publisher,
│   │                       #   block_converter, report_json_builder, embed_generator ほか
│   ├── templates/          # blog_template.md, blog_embed.html（Jinja2）
│   └── output/embeds/      # portfolio_YYYY_MM.json, blog_embed_YYYY_MM(.html/_fragment.html)
├── data/portfolio.db       # SQLite（ローカルは GCS portfolio-backup-pokebros から復元）
└── deploy/                 # Caddyfile, backup.sh 等（GCE）
```

## DB テーブル（server/src/db/schema.ts）

| テーブル | 用途 |
|---|---|
| holdings | 保有銘柄（sheets_sync が DELETE→INSERT 全入替。メタ情報を足さないこと） |
| monthly_prices | 月次価格（円換算）・月間変動率 change_rate |
| monthly_pnl | 銘柄×月の損益。date は `"YYYY-MM-末"` 形式。current_price（円）/ current_price_foreign（外貨）を保持し株価履歴の源泉 |
| exchange_rates | 為替レート（pair `USD/JPY`） |
| purchase_history | 買付履歴（code, seq, shares, price, price_foreign, purchased_at）。移動平均取得単価の源泉 |
| stock_meta | 銘柄カラー・市場表示（7974.T=#E53935/東証プライム、2432.T=#1565C0/東証プライム、NVDA=#76B900/NASDAQ）。未登録銘柄はフォールバック `#FF6F00`→`#7B1FA2` |
| ai_comments | AI コメント永続化（date, code, kind='stock'/'intro'/'summary'）。--blog 再実行時は再利用（AI_COMMENTS_FORCE=true で再生成） |
| dividends | 受取配当（date+code UNIQUE）。`--add-dividend` CLI で記録。日本株は total_jpy のみ、外国株は dividend_foreign/total_foreign/exchange_rate も保持 |
| wp_posts | WordPress 投稿 URL（month `"YYYY-MM"` UNIQUE, url, title）。--blog の create_draft 成功時に保存。レポート一覧の「ブログ記事」リンクの源泉 |
| benchmark_data | ベンチマーク |
| latest_pnl | トップページ用の最新スナップショット（code PK、1銘柄1行）。`--latest` が毎日上書きする。月次データ・レポート・ブログには使わない |

## API

| エンドポイント | 備考 |
|---|---|
| GET /api/dashboard | 既存 kpi/allocation/latestProfits ＋ **stocks[]・totalHistory・usdJpy**（新デザイン用。形状の正は `server/src/services/reportData.ts`）。latest_pnl の最終取引日が monthly_pnl 最新月より後なら `services/liveSnapshot.ts` が最新値を重ね、各配列の末尾に当月1点を足して `asOf`（YYYY-MM-DD）を返す。重ねないときは `asOf: null` |
| GET /api/reports/:year/:month/data | 月次レポートデータ（portfolio.json 形状）。該当月なしは 404 → client は Markdown 表示にフォールバック |
| GET /api/reports/:year/:month | 従来の Markdown レポート（維持） |
| GET /api/reports | 一覧は DB（monthly_pnl の月）＋ blog_draft ファイルの和集合。各項目に `wpUrl`（wp_posts 由来、無ければ null）。filename は廃止 |
| GET /api/dividend | date 降順ソート、各行に stock_meta 由来の `color` 付与（未登録はフォールバック色）。外貨系フィールドは日本株で null |
| その他 /api/portfolio, /history, /currency, /benchmark, /exposure | 変更なし |

stocks[] の主要フィールド: `currentPrice`/`acquiredPrice`/`priceHistory`/`acquiredAvgHistory` は **native 通貨**（USD 銘柄は外貨）、`value`/`profit` は円建て。`monthLabels` は `"YYYY/M"`。

## デザイン（claude.ai/design 由来）

デザインソース: claude.ai/design プロジェクト「保有株ポートフォリオ可視化アプリ」（ID: 11fbaa01-4d90-470d-91c1-32b30e2766cb）。DesignSync ツールで読み取り可能。

- トークン: 背景 `#f0f2f5`、本文 `#1e2130`、補助 `#8c90a0`、フォント Noto Sans JP。globals.css の `@theme` に定義
- 損益色は日本市場慣習（**プラス=赤 #E53935 / マイナス=青 #1565C0**）。新デザイン部分のみ。旧ページの `profitColor`（緑/赤）は温存
- client 内のチャートは Recharts 統一（Chart.js 禁止）。ブログ埋め込み HTML のみ Chart.js CDN 使用可

## ブログ埋め込みフロー

```
uv run python main.py --blog YYYY MM
  → AI コメント生成（ai_comments テーブルに永続化・既存あれば再利用）
  → report_json_builder が SQLite から portfolio.json を構築
  → templates/blog_embed.html で standalone / fragment の 2 モードをレンダリング
  → output/embeds/ に保存
  → WP_PUBLISH_ENABLED=true なら wp_publisher.create_draft(raw_html_prepend=fragment)
     で WordPress 下書きの先頭に wp:html ブロックとして自動挿入
```

- fragment は全 CSS を `.pf-report-embed` プレフィックスでスコープ済み（テーマ衝突防止）、Chart.js は二重読み込みガード付き動的ロード
- server 側 `reportData.ts` と collector 側 `report_json_builder.py` は同一形状・同一計算。片方を変えたら必ず両方直す

## 配当の記録

- 配当入力: `uv run python main.py --add-dividend 7974.T 2026-06-27 2 118`（日本株: 株数・1株配当円）/ `--add-dividend NVDA 2026-06-27 2 0.01 155.30`（外国株: 株数・1株配当外貨・為替レート）
- シート非依存で SQLite の dividends に直接 UPSERT（date+code キー）。銘柄名・通貨は holdings から取得するため、holdings に無い銘柄は登録不可
- 証券会社の受取通知を見て随時入力する運用（月次バッチとは独立）。`/dividend` ページに累計・今年サマリー、年別積み上げチャート、全期間の明細が表示される

## 買付の記録と monthly_pnl 補正

- 買付入力: `uv run python main.py --add-purchase 7974.T 2026-08-01 1 8500`（日本株）/ `--add-purchase NVDA 2026-08-01 1 208.27 162.35`（外国株: 外貨単価と為替）。シート追記 → holdings/purchase_history 同期 → monthly_pnl 補正まで自動実行。1 株未満の端株（ポケポケサブスク相当の積立分）はポートフォリオ対象外のため受け付けない
- `--repair-pnl [--dry-run]`: monthly_pnl の取得系カラム（shares/cost/acquired_price 系/value/profit）を purchase_history の累積で全月再計算。current_price 系は変更しない。月次収集後にも対象月分が自動補正される（collect_monthly_data 末尾フック）
- `uv run python repair_prices.py --db <DB> [--apply]`: 月末価格を yfinance の**未調整終値**に揃え直し、評価額・損益と monthly_prices を再計算する単発ツール（既定はドライラン）。2023-07〜2025-08 の日本株が配当調整後終値で保存されていたのを直すために作った（2026-10）。適用後は `main.py --benchmark YYYY M` で TWR を再計算する。為替の過去データ修正は `repair_fx.py`

## GCE デプロイ手順

### 自動デプロイ（GitHub Actions）

main への push（portfolio-dashboard/ 配下の変更）で `.github/workflows/deploy.yml` が起動し、SSH で GCE 上の `deploy/deploy.sh` を実行する（バックアップ → git pull → npm ci/build → db:migrate → systemctl restart → uv sync --extra）。手動実行（workflow_dispatch）も可。

必要な設定:

- リポジトリ Secrets: `GCE_HOST`（IP かホスト名）、`GCE_SSH_USER`（例: deploy）、`GCE_SSH_KEY`（秘密鍵。公開鍵を GCE 側 `~/.ssh/authorized_keys` に登録）
- GCE 側で deploy ユーザーがパスワードなしで再起動できるよう sudoers 設定:
  `echo 'deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart portfolio' | sudo tee /etc/sudoers.d/deploy-portfolio`
- Secrets 未設定の間はデプロイジョブはエラーにならずスキップされる

### 手動デプロイ

```bash
# GCE 上で（deploy.sh は同じ手順を自動化したもの）
bash /app/portfolio-dashboard/deploy/deploy.sh

# もしくは従来どおり:
# 事前に deploy/backup.sh 相当で DB バックアップを取ること
cd /app && git pull
cd portfolio-dashboard && npm ci && npm run build
npm run db:migrate -w server        # DB: /app/portfolio-dashboard/data/portfolio.db
sudo systemctl restart portfolio
cd collector && uv sync --extra ai --extra charts   # 素の uv sync は extras（anthropic/markdown/matplotlib）を削除してしまう
```

### 日次 cron（トップページの最新値）

毎日 21:30 UTC（JST 6:30。東証・米国の前日終値が確定した後）に `--latest` を実行し、latest_pnl を上書きする。AI・WP・monthly_* には触れないので費用は増えない。

```
30 21 * * * export PATH="$HOME/.local/share/fnm:$HOME/.local/bin:$PATH" && cd /app/portfolio-dashboard/collector && uv run python main.py --latest >> /app/portfolio-dashboard/logs/latest.log 2>&1
```

- yfinance は未確定の当日行を Close=NaN で返すことがあるため、確定済みの最終行を使う（東証は前営業日の値になることがある）
- 月初で最新値がまだ前月末のままの日は重ねず、月次表示になる

### 月次 cron（ブログ自動下書き）

毎月1日 9:00 に**前月分**の月次バッチ（`collect_and_publish`: 株価収集→ブログ生成→WP 下書き投稿）を実行する。crontab は deploy.sh では更新されないため、変更時は GCE 上で `crontab -e` を直接編集すること。

```
0 9 1 * * cd /app/portfolio-dashboard/collector && uv run python main.py $(date -d yesterday +\%Y) $(date -d yesterday +\%m) >> /app/logs/collector.log 2>&1
```

- 1日時点の「前日」は前月末日なので `date -d yesterday` で前月の年月になる（当月を渡すと月初データで当月レポートを作ってしまうので不可）
- `wp_publisher.create_draft` は毎回新規 POST（既存下書きの更新はしない）。手動 `--blog` と cron が重なると同月の下書きが複数できるので、不要な方は WP 側で削除する

## 旧構成（参考）

`web-app/`（Next.js + FastAPI）・`data-collector/`・`shared/` は 2026-04 の移行前の旧システム。ドキュメントは docs/project-structure.md・docs/sheets-schema.md・docs/api-reference.md（いずれも旧構成の記述）。変更禁止。
