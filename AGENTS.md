# 開発ワークフロー

## 全体の流れ

```
[先輩（あなた）] プランを立てる・設計を決める
    ↓ ゴール・完了条件・参照ファイルを渡す
[後輩ちゃん] 実装・テスト作成をこなす
    ↓ 変更ファイル・判断理由・懸念点を報告
[先輩（あなた）] 報告をレビュー・設計意図とのズレを確認
    ↓
[CLI] lint / check / test（トークン消費ゼロ）
```

## 1. 計画フェーズ（プランモード）

**以下のどちらかに当てはまったら必ずプランモードに入る：**

- ステップが 3 つ以上ある
- 設計判断が必要（どの構造にするか、どのファイルを変えるか）

**プランを立てるときにやること：**

- 変更するファイル・方針・完了条件を明文化して曖昧さをゼロにする
- 実装ステップだけでなく、**検証ステップ**（lint / check / test の何を走らせるか）も一緒に計画する
- 途中で想定外の問題が出たら **即作業を止めて再計画**。無理に進めない。

## 2. 後輩ちゃん（サブエージェント）戦略

**積極的に後輩ちゃんを使う理由：**
先輩（あなた）のコンテキストウィンドウをきれいに保つため。
長い処理・大きなログ・並列作業は後輩ちゃんの中に閉じ込める。

**後輩ちゃんに任せること：**

- ファイルの新規作成・編集・リファクタリング
- テストの作成・実行
- リサーチ・コード探索・ドキュメント調査
- 並列で進められる独立したタスク（複数の後輩ちゃんを同時投入してOK）

**後輩ちゃんの使い方のコツ：**

- **1 後輩ちゃん = 1 タスク** で集中させる。複数タスクを混ぜない。
- 複雑な問題には複数の後輩ちゃんを投入して、より多くの計算リソースをかける。
- 後輩ちゃんに返してもらうのは「変更ファイル・判断理由・懸念点」の 3 点セット。

## 3. チェックリスト（毎タスク確認）

1. [ ] プランを先に立てた？（ファイル・方針・完了条件・検証方法）
2. [ ] 後輩ちゃんに委譲した？（1 後輩ちゃん = 1 タスク）
3. [ ] 後輩ちゃんの報告をレビューした？
4. [ ] `npm run lint` を実行した？
5. [ ] `npm run check` を実行した？

## 4. CLI で直接やること（後輩ちゃん不要）

```bash
npm run lint      # Lint（Biome）
npm run lint:fix  # Lint 自動修正（Biome）
npm run format    # フォーマット（Biome）
npm run check     # 型チェック
npm run test      # テスト
```

---

# モデル設定

| 用途                           | モデル                       |
| ------------------------------ | ---------------------------- |
| プラン作成・レビュー・設計判断 | Fable 5（あなた）            |
| 実装タスク（後輩ちゃん）       | `model: sonnet`（Sonnet 5）  |
| 単純作業（後輩ちゃん）         | `model: haiku`（Haiku 4.5）  |
| 巨大コンテキストが必要なとき   | Sonnet 5（1M コンテキスト）  |

---

# プロジェクト設定

## 概要

投資ポートフォリオ管理＋月次ブログ自動化アプリケーション。**現行システムは `portfolio-dashboard/`**（Hono + React SPA + SQLite）。GCE e2-micro で本番稼働中（月次 cron・WordPress 自動投稿）。

**⚠️ `web-app/` と `data-collector/` は旧構成（Next.js + FastAPI + Google Sheets）。メンテ停止中で、変更しないこと。**

## 技術スタック（portfolio-dashboard）

- **client**: Vite 6, React 19, react-router-dom 7, TanStack Query 5, Recharts 3, Tailwind CSS v4
- **server**: Hono 4, Drizzle ORM, better-sqlite3（ポート3000、SPA 静的配信兼用）
- **collector**: Python 3.12（uv / ruff / ty）。yfinance→SQLite、ブログ生成・AI コメント・WordPress 投稿・ブログ埋め込み HTML 生成
- **DB**: `portfolio-dashboard/data/portfolio.db`（SQLite。ローカルに無ければ GCS `portfolio-backup-pokebros` から復元）

## 開発コマンド

```bash
cd portfolio-dashboard

# 開発サーバー（server:3000 + client:5173 を並行起動）
npm run dev

# 品質チェック（server + client）
npm run lint && npm run check && npm run test
npm run build

# DB マイグレーション
npm run db:generate -w server   # スキーマ差分から SQL 生成
npm run db:migrate -w server    # 適用（冪等）

# collector（月次バッチ・ブログ生成）
cd collector
uv run python main.py --blog 2026 3                                    # ブログ下書き＋埋め込み生成
uv run python main.py --repair-pnl --dry-run                           # monthly_pnl 補正の差分確認
uv run python main.py --latest                                         # トップページ用の最新値を更新（日次 cron）
uv run python main.py --add-purchase 7974.T 2026-08-01 1 8500          # 買付追記（日本株）
uv run python main.py --add-purchase NVDA 2026-08-01 1 208.27 162.35   # 買付追記（外国株）
uv run python main.py --add-dividend 7974.T 2026-06-27 2 118           # 配当記録（日本株: 株数・1株配当円）
uv run python main.py --add-dividend NVDA 2026-06-27 2 0.01 155.30     # 配当記録（外国株: +為替レート）
uv run python main.py --import-dividends dividendlist.csv --dry-run    # 配当CSV一括取込（楽天証券・cp932）
uv run ruff check . && uv run ty check
```

## 環境設定

- `portfolio-dashboard/collector/.env`: `DB_PATH`, `ANTHROPIC_API_KEY`, `WP_URL`, `WP_USER`, `WP_APP_PASSWORD`, `WP_PUBLISH_ENABLED`, `BLOG_EMBED_ENABLED`, `AI_COMMENTS_FORCE`
- `.env` の `DB_PATH` は GCE パス（`/app/...`）。ローカル実行時は `DB_PATH=<リポジトリ>/portfolio-dashboard/data/portfolio.db` を環境変数で上書きする
- API キー等の秘密情報はユーザー本人が直接設定する（LLM に渡さない）

## 実装状況

| 層 | 状態 |
|---|---|
| server | 完成（dashboard/portfolio/history/currency/dividend/reports/benchmark/exposure API、reports/:y/:m/data 追加済み）|
| client | 完成（claude.ai/design 由来の新デザイン: Dashboard・ReportDetail。他ページは旧デザイン）|
| collector | 完成（--sync/--range/--blog、AI コメント永続化、ブログ埋め込みエクスポート）|
| デプロイ | GCE e2-micro 稼働中（systemd portfolio.service、Caddy、月次 cron、GCS 日次バックアップ）|

## 開発ガイドライン

- コードコメント・コミットメッセージ・会話はすべて日本語
- AGENTS.md・README.md は開発状況に合わせて随時更新する（CLAUDE.md は作らない）
- 開発の問題点・実装計画は `PROJECT_PROCEED.md` で管理する
- DB スキーマ変更は additive のみ（本番 SQLite が GCE にあるため）。`sheets_sync` が holdings を全入替するので銘柄メタは `stock_meta` テーブルに置く

---

# 詳細ドキュメント

@docs/portfolio-dashboard.md

---

## Codex

This file is the shared source of truth for Claude Code and Codex. Claude Code reads it directly;
do not add a `CLAUDE.md` (it would make Claude Code read that instead of this file).

### Before working

1. Read this file completely.
2. Treat every standalone `@path` line in this file as a required file reference and read that
   file completely before the related work. The `@` syntax is a Claude Code import and is not a
   Codex import.
3. If `../pokebros-content-hub/AGENTS.md` exists, read it before cross-repository work. Follow its
   shared rules for repository ownership, concurrent sessions, handoff, publication, and deploys.
4. Use the validation commands documented in this file for the files changed.

### Concurrent sessions and handoff

- One checkout has one writing session. Concurrent writers use separate checkouts or worktrees and
  separate branches.
- Split concurrent work by phase or repository. Read-only review may run in parallel.
- At a handoff, commit the exact paths, push, and have the receiving environment pull before it
  edits. Do not use chat history or ignored files as the handoff record.
- Stage explicit paths only. Never include changes from another active session in a commit.
- Keep edits and Git operations inside this repository unless the hub workflow explicitly assigns
  cross-repository work.
