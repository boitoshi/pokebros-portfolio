# フロントエンド（Next.js）（⚠️ 旧構成）

> **`web-app/` は旧システム（Next.js + FastAPI）で、メンテ停止中・変更禁止です。現行の画面は `portfolio-dashboard/client/`（docs/portfolio-dashboard.md 参照）。**

ポートフォリオダッシュボードの Next.js 16 アプリケーション。

## 技術スタック

- Next.js 16（App Router）
- Tailwind CSS v4
- Recharts（チャート描画）
- TypeScript strict

## 起動

```bash
npm run dev    # 開発サーバー（ポート3000）
npm run build  # 本番ビルド（型チェック含む）
```

## ページ構成

| URL | 内容 |
|-----|------|
| `/` | ダッシュボード（KPI・構成比・最新月損益）|
| `/portfolio` | 保有銘柄テーブル |
| `/history` | 月次損益推移チャート |
| `/currency` | 為替レート推移チャート |

## アーキテクチャ

- **Server Components**（`page.tsx`）でデータフェッチ → Client Components に props を渡す
- **Client Components**（`"use client"`）で Recharts チャートを描画
- `/api/*` は `next.config.ts` で FastAPI（ポート8000）にリライト

## 環境変数

`.env.local`:
```
NEXT_PUBLIC_API_BASE_URL=http://localhost:3000
```

## ファイル構成

```
src/
├── app/                    # App Router ページ
│   ├── layout.tsx          # ナビゲーション共通レイアウト
│   ├── page.tsx            # / ダッシュボード
│   ├── portfolio/page.tsx
│   ├── history/page.tsx
│   └── currency/page.tsx
├── components/             # UI コンポーネント
│   ├── dashboard/          # KpiCards, AllocationChart, LatestBarChart
│   ├── history/            # ProfitAreaChart, StockFilter
│   ├── portfolio/          # HoldingsTable
│   └── currency/           # CurrencyLineChart
├── lib/
│   ├── api.ts              # fetch ラッパー
│   └── formatters.ts       # 通貨・パーセント表示
└── types/
    └── index.ts            # TypeScript 型定義
```
