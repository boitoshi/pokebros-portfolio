# プロジェクト進行状況と今後の計画

---

## 今後の実装ロードマップ

実装優先順位（ユーザー決定 2026-03-01）:

### ✅ 完了（2026-03-01）
- [x] バグ修正: /api/portfolio の totalCost=0 / isForeign=false を修正
- [x] 為替損益分離チャート（`ProfitAreaChart` を積み上げ棒グラフ化）
- [x] アセットアロケーション推移チャート（`AllocationTrendChart` 新規作成）
- [x] 銘柄別パフォーマンス比較（`StockCompareChart` 新規作成）
- [x] 配当・分配金記録（`/api/dividend` + `/dividend` ページ新規作成）
  - ⚠️ スプレッドシートに「配当・分配金」シートの手動作成が必要
- [x] 月次レポート Web プレビュー（`/api/reports` + `/reports` ページ新規作成）
- [x] コードリファクタリング: `_to_float` を `utils.py` に集約、`buildPivotData` を `chartUtils.ts` に集約
- [x] ベンチマーク比較（`/api/benchmark` + `BenchmarkChart` — history ページに追加）
  - yfinance で日経225 / S&P500 を月次取得し、ポートフォリオ累積リターンと比較
- [x] 通貨エクスポージャーサマリー（`/api/exposure` + `CurrencyExposureTable` — ダッシュボードに追加）
  - 最新月の JPY/USD 別 評価額・損益率・構成比をテーブル表示

### 📋 中優先度
2. **CAGR（年率換算リターン）** — 取得日からの保有期間を考慮した年率リターン表示

---

## 2026-08-05: pokebros-blog-manager から移送したタスク

`pokebros-blog-manager/tasks/global.md` に「ポートフォリオアプリの修正」として
2026-08-03 に起票されていたもの。タスク本文自身が「content-hub 経由でなく、
そのリポジトリを直接開いて作業してもよい」と言っており、記事制作のタスクキューに
置く必然性が無いので**このファイルへ移した**（移送元は同日クローズ）。

### 起票時の2項目は、その前日 2026-08-02 の作業で決着していた

| 起票時の論点 | 現状 |
|---|---|
| 月次記事の生成機能に専用タブがある → **仕様を検討** | **決着済み**。下の「2026-08-02」節のとおり、月次レポートタブは存続（アプリ内レポート＋WP記事リンクのハイブリッド）。一覧を DB 駆動に変更し、`wp_posts` テーブルで WP 投稿 URL を永続化する形で実装済み |
| 配当金ページ（Dividend）を**実装するか廃止するか決める** | **決着済み**。実装（廃止しない）。`--add-dividend` CLI（`collector/main.py` の `PortfolioDataCollector.add_dividend`）・`dividends` の UNIQUE(date, code)・配当ページの新デザインまで完了 |

### 残っているもの → **無し**（2026-08-05 時点）

- ~~配当データがまだ入っていない~~ … **2026-08-05 ユーザー確認により入力完了**。
  `--add-dividend` での随時入力運用に乗った。空ページ状態は解消
- したがって移送時に想定した残作業は消化済み。ユーザーが「修正」と言っていた
  具体的な不具合が上記3項目以外にあるなら、ここに追記する

---

## 2026-08-02: 月次レポートタブ・配当タブの検討と本実装

### 検討結果（意思決定）

**月次レポートタブ → 存続（アプリ内レポート＋WP記事リンクのハイブリッド）**
- 詳細ページ（`/api/reports/:y/:m/data` の新デザイン）は DB 駆動で機能しており、WP 記事（文章中心）とは役割が異なるため廃止しない
- 死んでいたのは一覧のみ（旧構成 `data-collector/output` のファイル名走査）→ DB（monthly_pnl の月）駆動に変更
- WP 投稿 URL はこれまで print で捨てられていた → 新テーブル `wp_posts` に永続化し、一覧に「ブログ記事」外部リンクを表示

**配当金タブ → 実装（廃止しない）**
- dividends テーブル・API・ページの骨格が既にあり追加コストが小さい。インカム情報は視聴者にも価値がある
- 記録方法: `--add-purchase` と同じ流儀の CLI `--add-dividend`（シート非依存・SQLite 直書き）。証券会社の通知を見て月次バッチとは独立に随時入力する運用
- 表示範囲: **全期間**（個人規模のデータ量なら全件表示で問題なし）。年別集計チャート＋累計/今年サマリー＋全明細テーブル

### 実装内容

- **server**: `dividends` に UNIQUE(date, code) 追加（重複二重計上防止）、新テーブル `wp_posts`、`/api/dividend` に色付与・ソート、`/api/reports` 一覧を DB＋ファイル和集合＋wpUrl 付きに変更
- **collector**: `db_writer.save_dividend()` / `save_wp_post()` 追加、`--add-dividend` CLI 新設、`create_draft` 成功時に wp_posts へ URL 保存
- **client**: 配当ページを新デザインで刷新（サマリーカード・年別積み上げバーチャート・null 安全な明細テーブル）、レポート一覧に WP 記事リンク、シート時代の文言を削除

---

## 2026-03-01: ベンチマーク比較・通貨エクスポージャーサマリー実装

### Feature 1: ベンチマーク比較（history ページ）

- `GET /api/benchmark`: ポートフォリオ累積リターン vs 日経225 / S&P500 を返す
  - yfinance（`^N225` `^GSPC`）で月次終値を取得し、初月基準の累積リターン率（%）に変換
  - performance シートを月ごとに集計してポートフォリオ率を算出
  - yfinance 疎通失敗時は `except Exception` でフォールバックし nikkei225/sp500 を `null` に
- `BenchmarkChart.tsx`: Recharts `LineChart` で 3 本折れ線（青/赤/緑）・ゼロライン・Legend 付き
- history ページ下部に追加（Promise.all で並列フェッチ）

### Feature 2: 通貨エクスポージャーサマリー（ダッシュボード）

- `GET /api/exposure`: 最新月の JPY/USD 別に 評価額・取得額・損益・損益率・構成比 を集計（HKD 除外）
- `CurrencyExposureTable.tsx`: テーブル表示、損益は正負で色分け
- ダッシュボード（AllocationTrendChart の下）に追加

### 変更ファイル（13 ファイル）

**バックエンド:**
- `web-app/backend/pyproject.toml` — `yfinance>=0.2`, `httpx>=0.27.0` 追加
- `web-app/backend/app/schemas/benchmark.py` — 新規
- `web-app/backend/app/schemas/exposure.py` — 新規
- `web-app/backend/app/routers/benchmark.py` — 新規
- `web-app/backend/app/routers/exposure.py` — 新規
- `web-app/backend/main.py` — 2 ルーター登録
- `web-app/backend/tests/test_benchmark.py` — 新規（9 ケース、全 33 テスト パス）

**フロントエンド:**
- `web-app/frontend/src/types/index.ts` — 4 型追加
- `web-app/frontend/src/components/history/BenchmarkChart.tsx` — 新規
- `web-app/frontend/src/components/dashboard/CurrencyExposureTable.tsx` — 新規
- `web-app/frontend/src/app/history/page.tsx` — BenchmarkChart セクション追加
- `web-app/frontend/src/app/page.tsx` — CurrencyExposureTable セクション追加

### 検証済み
- `uv run ruff check .` — All checks passed
- `npm run check` — TypeScript エラーなし
- `uv run pytest tests/ -v` — 33 passed

---

## 2026-02-28 web-app 全面再構築完了

### 変更内容
- Django + Vue.js → FastAPI + Next.js 16 に全面移行
- `web-app/backend/`: FastAPI + gspread（4エンドポイント実装済み）
- `web-app/frontend/`: Next.js 16 + Tailwind v4 + Recharts（4ページ実装済み）
- Tremor は React 19 + Tailwind v4 に非対応のため Recharts に変更

---

## 2026-02-28: ドキュメント整備・静的解析修正

### 実施内容

- **CLAUDE.md 分割**: 268行の単一ファイルを `@import` 形式で4ファイルに分割（138行に削減）
  - `docs/project-structure.md` — ディレクトリ構成・データフロー
  - `docs/sheets-schema.md` — スプレッドシートカラム定義・損益計算式
  - `docs/api-reference.md` — 実装済み/未実装エンドポイント一覧
- **`data-collector/pyproject.toml` 修正**: `[tool.ty]` の `python-version` を `[tool.ty.environment]` 以下に移動。`extra-paths` で `collectors/`・`config/`・`../shared/` を追加
- **`data-collector/main.py` インポート修正**: `sys.path.append` + フラットインポートを、パッケージ形式（`from collectors.xxx import yyy`、`from config.settings import yyy`）に変更。ruff・ty・IDE 警告がすべてゼロに
- **ルート `pyproject.toml` 修正**: VS Code が参照するルートの `[tool.ty.environment]` に `python-version` と `extra-paths = ["shared"]` を追加
- **`web-app/backend/README.md`**: ほぼ空だったファイルに起動手順・エンドポイント一覧・ディレクトリ構成を記述

---

## 2026-02-06: Docker/devcontainerからローカル開発環境への移行

### 実施内容
- devcontainer環境を削除し、ローカル開発環境に完全移行
- **uv一本でPythonバージョン管理** - pyenv不要
- **型チェッカーをtyに変更** - Astral社製の超高速型チェッカー（ruff + ty）
- uvワークスペース + npm によるハイブリッド構成
- VS Code設定（settings/tasks/launch.json）の移行
- README.md, CLAUDE.md の更新

### 削除したファイル
- `.devcontainer/` ディレクトリ全体

### 技術スタック（移行後）
- **Python管理**: uv（バージョン管理含む）
- **Python型チェック**: ty（Astral社製、mypyの代替）
- **Python リンター/フォーマッター**: ruff
- **Node.js**: npm（バージョン管理はnvm推奨だが任意）
- **開発環境**: VS Code（ローカルネイティブ）
- **デプロイ**: Docker（本番用Dockerfileは維持）

### 重要な変更点
- `pyproject.toml` - mypyからtyに変更、ルートプロジェクトからbuild-systemを削除
- `data-collector/.env` - GOOGLE_APPLICATION_CREDENTIALSのパスをdevcontainer用からローカル絶対パスに変更
- `.vscode/` - settings.json, tasks.json, launch.jsonを新規作成・更新

### 今後の課題
- [ ] CI/CDパイプラインでのuvとPython 3.12バージョン統一
- [ ] 本番Dockerfileの定期的なメンテナンス
- [ ] チーム開発時の.vscode設定共有方法検討
- [ ] tyの言語サーバー統合（VS Code拡張機能が利用可能になった場合）

---

## 2026-02-07: 外国株の外貨建て取得単価・取得時為替レート記録機能

### 実施内容
- ポートフォリオシートに「取得単価（外貨）」「取得時為替レート」カラムを追加（10→12カラム）
- 損益レポートシートに「通貨」「取得単価（外貨）」「月末価格（外貨）」「取得時為替レート」「現在為替レート」カラムを追加（11→16カラム）
- `shared/sheets_config.py` のヘッダー定義を統一（sheets_writer.pyとの矛盾を解消）
- 為替損益と株価損益の分離計算ロジックを実装
- `pyproject.toml` に ty（Astral社製型チェッカー）を依存関係として追加

### 変更ファイル
- `shared/sheets_config.py` - HEADERS/COLUMN_RANGES/SHEET_NAMES統一
- `data-collector/config/settings.py` - DEFAULT_STOCKSに外貨情報追加
- `data-collector/collectors/stock_collector.py` - 損益分離計算（株価損益/為替損益）
- `data-collector/collectors/sheets_writer.py` - sheets_configからヘッダー参照、12/16カラム対応
- `data-collector/main.py` - 外貨カラム読み取り・書き込み拡張
- `data-collector/collectors/report_generator.py` - ブログレポートに外貨・為替損益情報追加
- `web-app/backend/sheets/currency_views.py` - A1:L範囲拡張、外貨情報レスポンス追加
- `web-app/backend/portfolio/services.py` - 外貨建て加重平均計算、Vue.js形式に通貨情報追加
- `data-collector/pyproject.toml` - ty依存追加
- `web-app/backend/pyproject.toml` - ty依存追加

### 損益分離計算式
- 株価損益 = (月末外貨価格 - 取得外貨価格) × 取得時為替レート × 株数
- 為替損益 = (現在為替レート - 取得時為替レート) × 月末外貨価格 × 株数
- 総損益 = 株価損益 + 為替損益（= 評価額 - 取得額）

### ポートフォリオシート設計変更
- D列（取得単価（円））を数式 `=K*L` に変更（外貨単価×為替レートから自動算出）
- K列（取得単価（外貨））とL列（取得時為替レート）が入力元
- 日本株: K=円建て価格, L=1.0 → D=K*L
- 外国株: K=外貨価格, L=取得時レート → D=K*L（円換算）
- 通貨コードはISO形式（JPY, USD, HKD）

### スプレッドシートマイグレーション（完了）
- [x] K-L列のヘッダー追加（取得単価（外貨）、取得時為替レート）
- [x] 外国株のK/L列にデータ入力（楽天証券の保有数量明細から取得）
- [x] D列を `=K*L` 数式に変更
- [x] 通貨コード入力（JPY/USD/HKD）
- [x] 外国株フラグ（○）設定
- [x] `uv sync --dev` で ty インストール確認
- [x] `uv run python main.py 2025 1` で動作確認（NVDA為替損益分離が正常動作）

### 後方互換性
- D列が空の場合、K*Lから自動算出（main.pyのフォールバック）
- K/L列が空の場合、D列の値をそのまま使用（為替レート=1.0）
- 必須フィールド（銘柄コード、銘柄名、保有株数）が空の行は自動スキップ

### main.py バグ修正
- `except ValueError` が引数パースだけでなく `collect_monthly_data` 内部エラーも隠蔽していた問題を修正
- 必須フィールド（銘柄コード、銘柄名、保有株数）が空の行をスキップするバリデーション追加

### 損益レポートの保有期間フィルタリング（2026-02-07追加）
- ポートフォリオの「取得日」を参照し、取得月以降のみ損益レポートに記録
- 取得前の期間はデータ記録（市場データ）のみ記録し、損益計算は行わない
- `--range`で過去データを一括取得した際、保有していない期間の不正な損益レコードが作成されなくなった
- 取得日が空の場合はデフォルトで保有扱い（後方互換性）

