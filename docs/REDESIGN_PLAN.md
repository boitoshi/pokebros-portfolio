# ゼロから再設計プラン（⚠️ 移行前の計画書）

> **このドキュメントは 2026-04 の移行前に立てた設計計画で、移行は完了済みです。計画時点の記述のため実装と食い違う箇所があります。現行の仕様は docs/portfolio-dashboard.md 参照。**

## 目的

現在の Next.js + FastAPI + Google Sheets 構成を、**Hono + React SPA + SQLite** に全面移行する。
個人用ダッシュボードとして長期安定運用でき、月次ブログ投稿まで自動化する構成を目指す。

---

## 現状の課題

| 問題 | 根本原因 |
|------|----------|
| Google Sheets がボトルネック（レート制限、クエリ不可、スキーマ脆弱） | RDBMS の仕事を Sheets にやらせている |
| FastAPI + Next.js = 2サーバー運用 | 読み取り専用APIのためだけにバックエンドが存在 |
| data-collector と backend で gspread ロジックが重複 | Sheets が唯一の共有レイヤーになっている |
| Next.js の破壊的変更リスク | SSR/SSG 不要な個人ダッシュボードに過剰なフレームワーク |
| ブログ投稿が手動（コピペ + 画像アップ） | 自動化の仕組みがない |

---

## 決定済みの方針

1. **技術スタック**: Hono + React SPA (Vite) + Drizzle ORM + SQLite (better-sqlite3)
2. **デプロイ先**: GCP Compute Engine e2-micro（無料枠、常時起動）
3. **月次バッチ**: e2-micro 内の crontab で Python collector を自動実行
4. **ブログ自動化**: Claude Haiku で銘柄コメント生成 → WordPress REST API で下書き投稿
5. **Google Sheets**: 銘柄マスタの入力UIとしてだけ残す（Sheets → SQLite の一方向同期）
6. **WordPress**: CONOHA 共有サーバーで運用中の月次投資ブログ。ダッシュボードアプリへリンク

---

## 1. プロジェクト構造

```
portfolio-dashboard/
├── server/                     # Hono（API + 静的ファイル配信）
│   ├── src/
│   │   ├── index.ts            # エントリポイント
│   │   ├── routes/
│   │   │   ├── dashboard.ts
│   │   │   ├── portfolio.ts
│   │   │   ├── history.ts
│   │   │   ├── currency.ts
│   │   │   ├── dividend.ts
│   │   │   ├── reports.ts
│   │   │   ├── benchmark.ts
│   │   │   └── exposure.ts
│   │   └── db/
│   │       ├── index.ts        # better-sqlite3 接続
│   │       ├── schema.ts       # Drizzle スキーマ定義
│   │       └── queries.ts      # 共通クエリ関数
│   ├── drizzle/
│   │   └── migrations/         # マイグレーションファイル
│   ├── drizzle.config.ts
│   ├── tsconfig.json
│   └── package.json
├── client/                     # React SPA（Vite）
│   ├── src/
│   │   ├── main.tsx            # エントリポイント
│   │   ├── App.tsx             # React Router 設定
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Portfolio.tsx
│   │   │   ├── History.tsx
│   │   │   ├── Currency.tsx
│   │   │   ├── Dividend.tsx
│   │   │   └── Reports.tsx
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── AppLayout.tsx    # ナビゲーション共通レイアウト
│   │   │   │   └── Nav.tsx
│   │   │   ├── dashboard/
│   │   │   │   ├── KpiCards.tsx
│   │   │   │   ├── AllocationChart.tsx
│   │   │   │   ├── LatestBarChart.tsx
│   │   │   │   ├── AllocationTrendChart.tsx
│   │   │   │   └── CurrencyExposureTable.tsx
│   │   │   ├── history/
│   │   │   │   ├── ProfitBarChart.tsx
│   │   │   │   ├── StockCompareChart.tsx
│   │   │   │   ├── BenchmarkChart.tsx
│   │   │   │   └── StockFilter.tsx
│   │   │   ├── portfolio/
│   │   │   │   └── HoldingsTable.tsx
│   │   │   ├── currency/
│   │   │   │   └── CurrencyLineChart.tsx
│   │   │   └── dividend/
│   │   │       └── DividendTable.tsx
│   │   ├── lib/
│   │   │   ├── api.ts          # fetch ラッパー
│   │   │   ├── formatters.ts   # 通貨・パーセント表示（既存移植）
│   │   │   └── chartUtils.ts   # buildPivotData 等（既存移植）
│   │   └── types/
│   │       └── index.ts        # API レスポンス型（既存移植）
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── package.json
├── collector/                  # Python バッチ（yfinance → SQLite）
│   ├── main.py                 # エントリポイント
│   ├── collectors/
│   │   ├── stock_collector.py  # yfinance 株価取得（既存維持）
│   │   ├── currency_converter.py # 為替レート取得（既存維持）
│   │   ├── db_writer.py        # SQLite 書き込み（新規：sheets_writer.py の置き換え）
│   │   ├── sheets_sync.py      # Sheets → SQLite 一方向同期（新規）
│   │   ├── report_generator.py # ブログ用データ収集（SQLite から読み取りに変更）
│   │   ├── template_engine.py  # Jinja2 テンプレート（既存維持）
│   │   ├── ai_comment.py       # Claude Haiku コメント生成（新規）
│   │   ├── wp_publisher.py     # WordPress REST API 投稿（新規）
│   │   ├── chart_image_generator.py  # matplotlib PNG（既存維持）
│   │   └── interactive_chart_generator.py # Chart.js HTML（既存維持）
│   ├── templates/
│   │   └── blog_template.md    # Jinja2 テンプレート（既存維持）
│   ├── config/
│   │   └── settings.py
│   ├── output/                 # 生成物
│   ├── pyproject.toml
│   └── .env
├── data/
│   └── portfolio.db            # SQLite ファイル
├── deploy/
│   ├── Caddyfile               # HTTPS リバースプロキシ
│   ├── portfolio.service       # systemd ユニット
│   ├── backup.sh               # SQLite → GCS バックアップ
│   └── setup.sh                # e2-micro 初期セットアップ
├── .github/
│   └── workflows/
│       └── ci.yml
├── package.json                # ルート（npm workspaces）
├── tsconfig.base.json          # 共有 TypeScript 設定
└── CLAUDE.md
```

### npm workspaces 構成

```jsonc
// ルート package.json
{
  "private": true,
  "workspaces": ["server", "client"],
  "scripts": {
    "dev": "concurrently \"npm run dev -w server\" \"npm run dev -w client\"",
    "build": "npm run build -w client && npm run build -w server",
    "start": "npm run start -w server",
    "lint": "npm run lint -w server && npm run lint -w client",
    "check": "npm run check -w server && npm run check -w client",
    "test": "npm run test -w server && npm run test -w client",
    "db:migrate": "npm run db:migrate -w server",
    "db:studio": "npm run db:studio -w server"
  }
}
```

---

## 2. SQLite スキーマ設計

### Drizzle スキーマ定義

```typescript
// server/src/db/schema.ts
import { sqliteTable, text, real, integer } from "drizzle-orm/sqlite-core";

// ━━━ 保有銘柄マスタ（旧ポートフォリオシート）━━━
export const holdings = sqliteTable("holdings", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  code: text("code").notNull(),              // 7974.T, NVDA
  name: text("name").notNull(),              // 任天堂
  acquiredDate: text("acquired_date"),       // 2023-06-28
  acquiredPriceJpy: real("acquired_price_jpy").notNull(), // 取得単価（円）
  acquiredPriceForeign: real("acquired_price_foreign"),   // 取得単価（外貨）
  acquiredExchangeRate: real("acquired_exchange_rate"),    // 取得時為替レート
  shares: real("shares").notNull(),          // 保有株数
  currency: text("currency").notNull().default("JPY"),    // JPY / USD / HKD
  isForeign: integer("is_foreign", { mode: "boolean" }).notNull().default(false),
  memo: text("memo"),                        // 備考
  updatedAt: text("updated_at"),             // 最終更新
});

// ━━━ 月次市場データ（旧データ記録シート）━━━
export const monthlyPrices = sqliteTable("monthly_prices", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  date: text("date").notNull(),              // 2024-12-31
  code: text("code").notNull(),              // 銘柄コード
  priceJpy: real("price_jpy").notNull(),     // 月末価格（円）
  high: real("high"),                        // 最高値
  low: real("low"),                          // 最安値
  average: real("average"),                  // 平均価格
  changeRate: real("change_rate"),           // 月間変動率(%)
  avgVolume: real("avg_volume"),             // 平均出来高
  createdAt: text("created_at"),             // 取得日時
});
// UNIQUE(date, code) で重複防止

// ━━━ 月次損益（旧損益レポートシート）━━━
export const monthlyPnl = sqliteTable("monthly_pnl", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  date: text("date").notNull(),              // 2024-12-末
  code: text("code").notNull(),
  name: text("name").notNull(),
  acquiredPrice: real("acquired_price").notNull(),   // 取得単価（円）
  currentPrice: real("current_price").notNull(),     // 月末価格（円）
  shares: real("shares").notNull(),
  cost: real("cost").notNull(),              // 取得額
  value: real("value").notNull(),            // 評価額
  profit: real("profit").notNull(),          // 損益
  profitRate: real("profit_rate").notNull(), // 損益率(%)
  currency: text("currency").notNull().default("JPY"),
  acquiredPriceForeign: real("acquired_price_foreign"),
  currentPriceForeign: real("current_price_foreign"),
  acquiredExchangeRate: real("acquired_exchange_rate"),
  currentExchangeRate: real("current_exchange_rate"),
  updatedAt: text("updated_at"),
});
// UNIQUE(date, code) で重複防止

// ━━━ 為替レート（旧為替レートシート）━━━
export const exchangeRates = sqliteTable("exchange_rates", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  date: text("date").notNull(),              // 2024-12-31
  pair: text("pair").notNull(),              // USD/JPY
  rate: real("rate").notNull(),
  prevRate: real("prev_rate"),               // 前回レート
  changeRate: real("change_rate"),           // 変動率(%)
  high: real("high"),
  low: real("low"),
  updatedAt: text("updated_at"),
});
// UNIQUE(date, pair) で重複防止

// ━━━ 配当・分配金（旧配当シート）━━━
export const dividends = sqliteTable("dividends", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  date: text("date").notNull(),              // 受取日
  code: text("code").notNull(),
  name: text("name").notNull(),
  dividendForeign: real("dividend_foreign"), // 1株配当（外貨）
  shares: real("shares").notNull(),
  totalForeign: real("total_foreign"),       // 配当合計（外貨）
  currency: text("currency").notNull().default("JPY"),
  exchangeRate: real("exchange_rate"),       // 為替レート
  totalJpy: real("total_jpy").notNull(),     // 配当合計（円）
});
```

### インデックス

```typescript
// server/src/db/schema.ts（続き）
import { uniqueIndex, index } from "drizzle-orm/sqlite-core";

// 重複防止 + 検索高速化
// monthlyPrices: UNIQUE(date, code)
// monthlyPnl: UNIQUE(date, code)
// exchangeRates: UNIQUE(date, pair)
// monthlyPnl: INDEX(date) — ダッシュボードの最新月検索用
// holdings: INDEX(code) — 銘柄検索用
```

### マイグレーション戦略

```bash
# Drizzle Kit でマイグレーション管理
npx drizzle-kit generate    # スキーマ変更からマイグレーション生成
npx drizzle-kit migrate     # マイグレーション適用
npx drizzle-kit studio      # ブラウザで DB 確認（開発用）
```

---

## 3. Hono サーバー設計

### エントリポイント

```typescript
// server/src/index.ts
import { Hono } from "hono";
import { serveStatic } from "hono/node-server/serve-static";
import { logger } from "hono/logger";
import { cors } from "hono/cors";
import { dashboardRoute } from "./routes/dashboard";
import { portfolioRoute } from "./routes/portfolio";
import { historyRoute } from "./routes/history";
import { currencyRoute } from "./routes/currency";
import { dividendRoute } from "./routes/dividend";
import { reportsRoute } from "./routes/reports";
import { benchmarkRoute } from "./routes/benchmark";
import { exposureRoute } from "./routes/exposure";

const app = new Hono();

app.use("*", logger());

// API ルート
const api = app.basePath("/api");
api.route("/dashboard", dashboardRoute);
api.route("/portfolio", portfolioRoute);
api.route("/history", historyRoute);
api.route("/currency", currencyRoute);
api.route("/dividend", dividendRoute);
api.route("/reports", reportsRoute);
api.route("/benchmark", benchmarkRoute);
api.route("/exposure", exposureRoute);

// ヘルスチェック
app.get("/health", (c) => c.json({ status: "ok" }));

// Vite ビルド成果物を静的配信
app.use("/*", serveStatic({ root: "../client/dist" }));
// SPA フォールバック（React Router 用）
app.get("/*", serveStatic({ root: "../client/dist", path: "index.html" }));

export default app;
```

### ルート例（dashboard）

```typescript
// server/src/routes/dashboard.ts
import { Hono } from "hono";
import { db } from "../db";
import { monthlyPnl, holdings } from "../db/schema";
import { eq, desc, sql, sum } from "drizzle-orm";

const app = new Hono();

app.get("/", async (c) => {
  // 最新月を取得
  const latest = db
    .select({ date: monthlyPnl.date })
    .from(monthlyPnl)
    .orderBy(desc(monthlyPnl.date))
    .limit(1)
    .get();

  if (!latest) return c.json({ kpi: null, allocation: [], latestProfits: [] });

  const latestDate = latest.date;

  // KPI 集計
  const kpiRow = db
    .select({
      totalValue: sum(monthlyPnl.value),
      totalProfit: sum(monthlyPnl.profit),
      totalCost: sum(monthlyPnl.cost),
    })
    .from(monthlyPnl)
    .where(eq(monthlyPnl.date, latestDate))
    .get();

  const totalValue = kpiRow?.totalValue ?? 0;
  const totalCost = kpiRow?.totalCost ?? 0;
  const totalProfit = kpiRow?.totalProfit ?? 0;
  const profitRate = totalCost > 0 ? (totalProfit / totalCost) * 100 : 0;

  // 構成比
  const allocation = db
    .select({
      name: monthlyPnl.name,
      value: monthlyPnl.value,
    })
    .from(monthlyPnl)
    .where(eq(monthlyPnl.date, latestDate))
    .all()
    .map((row) => ({
      name: row.name,
      value: row.value,
      percentage: (row.value / Number(totalValue)) * 100,
    }));

  // 最新月損益
  const latestProfits = db
    .select({
      name: monthlyPnl.name,
      profit: monthlyPnl.profit,
      profitRate: monthlyPnl.profitRate,
    })
    .from(monthlyPnl)
    .where(eq(monthlyPnl.date, latestDate))
    .all();

  return c.json({
    kpi: {
      totalValue: Number(totalValue),
      totalProfit: Number(totalProfit),
      profitRate,
      baseDate: latestDate,
    },
    allocation,
    latestProfits,
  });
});

export { app as dashboardRoute };
```

### benchmark の yfinance 問題

現在の FastAPI benchmark ルーターは yfinance を直接呼んでいる。解決策：

**方針: collector で月次バッチ時にベンチマークデータも SQLite に保存する**

```typescript
// 新テーブル追加
export const benchmarkData = sqliteTable("benchmark_data", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  date: text("date").notNull(),           // 2024-12-末
  portfolio: real("portfolio").notNull(), // ポートフォリオ累積リターン(%)
  nikkei225: real("nikkei225"),           // 日経225 累積リターン(%)
  sp500: real("sp500"),                   // S&P500 累積リターン(%)
});
```

collector 側で yfinance から日経225/S&P500 を取得し、ポートフォリオの累積リターンと合わせて保存。
→ Hono サーバーから yfinance 依存を**完全排除**。Node.js サーバーが Python に依存しなくなる。

### 依存パッケージ（server）

```jsonc
{
  "dependencies": {
    "hono": "^4",
    "@hono/node-server": "^1",
    "better-sqlite3": "^11",
    "drizzle-orm": "^0.36"
  },
  "devDependencies": {
    "drizzle-kit": "^0.30",
    "@types/better-sqlite3": "^7",
    "tsx": "^4",
    "typescript": "^5.7",
    "vitest": "^3"
  }
}
```

---

## 4. React SPA (Vite) 設計

### ルーティング

```typescript
// client/src/App.tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import Dashboard from "./pages/Dashboard";
import Portfolio from "./pages/Portfolio";
import History from "./pages/History";
import Currency from "./pages/Currency";
import Dividend from "./pages/Dividend";
import Reports from "./pages/Reports";
import ReportDetail from "./pages/ReportDetail";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="portfolio" element={<Portfolio />} />
          <Route path="history" element={<History />} />
          <Route path="currency" element={<Currency />} />
          <Route path="dividend" element={<Dividend />} />
          <Route path="reports" element={<Reports />} />
          <Route path="reports/:year/:month" element={<ReportDetail />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

### データフェッチ: TanStack Query

```typescript
// client/src/lib/api.ts
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// client/src/pages/Dashboard.tsx
import { useQuery } from "@tanstack/react-query";

export default function Dashboard() {
  const { data: dashboard } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => fetchApi<DashboardResponse>("/api/dashboard"),
  });

  const { data: history } = useQuery({
    queryKey: ["history"],
    queryFn: () => fetchApi<HistoryResponse>("/api/history"),
  });

  const { data: exposure } = useQuery({
    queryKey: ["exposure"],
    queryFn: () => fetchApi<ExposureResponse>("/api/exposure"),
  });

  // ...
}
```

### 既存資産の移植方針

| 既存ファイル | 移植先 | 変更点 |
|-------------|--------|--------|
| `src/types/index.ts` | `client/src/types/index.ts` | そのまま移植（型定義は同一） |
| `src/lib/formatters.ts` | `client/src/lib/formatters.ts` | そのまま移植 |
| `src/lib/chartUtils.ts` | `client/src/lib/chartUtils.ts` | そのまま移植 |
| `src/lib/api.ts` | `client/src/lib/api.ts` | fetch ラッパーを簡略化（revalidate 不要） |
| `src/components/dashboard/*` | `client/src/components/dashboard/*` | `"use client"` 削除のみ |
| `src/components/history/*` | `client/src/components/history/*` | 同上 |
| `src/components/portfolio/*` | `client/src/components/portfolio/*` | 同上 |
| `src/components/currency/*` | `client/src/components/currency/*` | 同上 |
| 各 `page.tsx` | `client/src/pages/*.tsx` | Server Component → TanStack Query に書き換え |
| `app/layout.tsx` | `client/src/components/layout/AppLayout.tsx` | `<Outlet />` ベースに変更 |

**チャートコンポーネントは Recharts のまま変更なし**。`"use client"` ディレクティブを消すだけ。

### 依存パッケージ（client）

```jsonc
{
  "dependencies": {
    "react": "^19",
    "react-dom": "^19",
    "react-router-dom": "^7",
    "@tanstack/react-query": "^5",
    "recharts": "^3",
    "clsx": "^2"
  },
  "devDependencies": {
    "vite": "^6",
    "@vitejs/plugin-react": "^4",
    "tailwindcss": "^4",
    "typescript": "^5.7",
    "vitest": "^3",
    "@testing-library/react": "^16"
  }
}
```

---

## 5. Python collector の改修

### 変更概要

| モジュール | 変更内容 |
|-----------|---------|
| `sheets_writer.py` | → `db_writer.py` に置き換え（SQLite 書き込み） |
| `report_generator.py` | Sheets 読み取り → SQLite 読み取りに変更 |
| `chart_image_generator.py` | Sheets 読み取り → SQLite 読み取りに変更 |
| `interactive_chart_generator.py` | Sheets 読み取り → SQLite 読み取りに変更 |
| `stock_collector.py` | 変更なし（yfinance ロジック維持） |
| `currency_converter.py` | 変更なし |
| `template_engine.py` | 変更なし |
| `ai_comment.py` | **新規**: Claude Haiku でコメント生成 |
| `wp_publisher.py` | **新規**: WordPress REST API 下書き投稿 |
| `sheets_sync.py` | **新規**: Sheets → SQLite 一方向同期 |
| `benchmark_collector.py` | **新規**: yfinance で日経225/S&P500 取得 → SQLite 保存 |

### db_writer.py（新規）

```python
# collector/collectors/db_writer.py
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "portfolio.db"

class DbWriter:
    def __init__(self, db_path: str = str(DB_PATH)):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")  # 同時読み書き対応

    def save_monthly_price(self, data: dict) -> None:
        """月次市場データを保存（UPSERT）"""
        self.conn.execute("""
            INSERT INTO monthly_prices (date, code, price_jpy, high, low, average, change_rate, avg_volume, created_at)
            VALUES (:date, :code, :price_jpy, :high, :low, :average, :change_rate, :avg_volume, :created_at)
            ON CONFLICT(date, code) DO UPDATE SET
                price_jpy=excluded.price_jpy, high=excluded.high, low=excluded.low,
                average=excluded.average, change_rate=excluded.change_rate,
                avg_volume=excluded.avg_volume, created_at=excluded.created_at
        """, data)
        self.conn.commit()

    def save_monthly_pnl(self, data: dict) -> None:
        """月次損益を保存（UPSERT）"""
        self.conn.execute("""
            INSERT INTO monthly_pnl (date, code, name, acquired_price, current_price,
                shares, cost, value, profit, profit_rate, currency,
                acquired_price_foreign, current_price_foreign,
                acquired_exchange_rate, current_exchange_rate, updated_at)
            VALUES (:date, :code, :name, :acquired_price, :current_price,
                :shares, :cost, :value, :profit, :profit_rate, :currency,
                :acquired_price_foreign, :current_price_foreign,
                :acquired_exchange_rate, :current_exchange_rate, :updated_at)
            ON CONFLICT(date, code) DO UPDATE SET
                name=excluded.name, current_price=excluded.current_price,
                value=excluded.value, profit=excluded.profit, profit_rate=excluded.profit_rate,
                current_price_foreign=excluded.current_price_foreign,
                current_exchange_rate=excluded.current_exchange_rate, updated_at=excluded.updated_at
        """, data)
        self.conn.commit()

    # save_exchange_rate, save_dividend, save_benchmark も同様の UPSERT パターン
```

### sheets_sync.py（新規）

```python
# collector/collectors/sheets_sync.py
"""Google Sheets のポートフォリオシートを読み取り、SQLite の holdings テーブルに同期する"""
import gspread
from google.oauth2.service_account import Credentials

class SheetsSync:
    def sync_holdings(self) -> None:
        """Sheets → SQLite の一方向同期（holdings テーブル）"""
        # 1. Sheets から全行取得
        records = self.sheet.get_all_records()
        # 2. SQLite の holdings を全削除 → 全挿入（マスタデータなので REPLACE で十分）
        self.conn.execute("DELETE FROM holdings")
        for row in records:
            self.conn.execute("""
                INSERT INTO holdings (code, name, acquired_date, acquired_price_jpy,
                    acquired_price_foreign, acquired_exchange_rate, shares,
                    currency, is_foreign, memo, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (...))
        self.conn.commit()
```

### ai_comment.py（新規）

```python
# collector/collectors/ai_comment.py
from anthropic import Anthropic

class AiCommentGenerator:
    def __init__(self):
        self.client = Anthropic()  # ANTHROPIC_API_KEY 環境変数から自動読み取り

    def generate_stock_comment(self, stock_data: dict) -> str:
        """銘柄ごとの月次コメントを生成"""
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=(
                "あなたは個人投資家のブログ筆者です。"
                "月次の株価レポートのコメントを2-3文で簡潔に書いてください。"
                "データに基づいた分析を行い、自然な日本語で書いてください。"
            ),
            messages=[{
                "role": "user",
                "content": f"""
銘柄: {stock_data['name']} ({stock_data['code']})
月末価格: {stock_data['current_price']}円
損益: {stock_data['profit']}円（{stock_data['profit_rate']:.1f}%）
月間変動率: {stock_data['change_rate']:.1f}%
通貨: {stock_data['currency']}
"""
            }]
        )
        return response.content[0].text

    def generate_summary(self, portfolio_data: dict) -> str:
        """まとめコメントを生成"""
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=(
                "あなたは個人投資家のブログ筆者です。"
                "月次の投資成績のまとめを3-5文で書いてください。"
                "全体の傾向と特筆すべき銘柄に触れてください。"
            ),
            messages=[{
                "role": "user",
                "content": f"""
ポートフォリオ全体:
  合計評価額: {portfolio_data['total_value']}円
  合計損益: {portfolio_data['total_profit']}円（{portfolio_data['profit_rate']:.1f}%）
  銘柄数: {portfolio_data['stock_count']}

各銘柄の損益率:
{portfolio_data['stock_summary']}
"""
            }]
        )
        return response.content[0].text
```

### wp_publisher.py（新規）

```python
# collector/collectors/wp_publisher.py
import requests
import markdown
from pathlib import Path

class WpPublisher:
    def __init__(self, wp_url: str, wp_user: str, wp_app_password: str):
        self.wp_url = wp_url.rstrip("/")
        self.auth = (wp_user, wp_app_password)  # Application Password 認証

    def upload_image(self, image_path: str) -> int:
        """画像をアップロードしてメディアIDを返す"""
        path = Path(image_path)
        with open(path, "rb") as f:
            resp = requests.post(
                f"{self.wp_url}/wp-json/wp/v2/media",
                auth=self.auth,
                headers={"Content-Disposition": f"attachment; filename={path.name}"},
                files={"file": (path.name, f, "image/png")},
            )
            resp.raise_for_status()
            return resp.json()["id"]

    def create_draft(self, title: str, markdown_content: str, image_paths: list[str] = []) -> str:
        """WordPress に下書き投稿。投稿URLを返す"""
        # 画像アップロード
        for img_path in image_paths:
            media_id = self.upload_image(img_path)
            # Markdown 内の相対パスを WordPress URL に置換
            img_name = Path(img_path).name
            wp_url = requests.get(
                f"{self.wp_url}/wp-json/wp/v2/media/{media_id}",
                auth=self.auth,
            ).json()["source_url"]
            markdown_content = markdown_content.replace(img_name, wp_url)

        # Markdown → HTML 変換
        html_content = markdown.markdown(markdown_content, extensions=["tables", "fenced_code"])

        # 下書き投稿
        resp = requests.post(
            f"{self.wp_url}/wp-json/wp/v2/posts",
            auth=self.auth,
            json={
                "title": title,
                "content": html_content,
                "status": "draft",
            },
        )
        resp.raise_for_status()
        return resp.json()["link"]
```

### main.py の月次フロー（改修後）

```python
def collect_and_publish(self, year: int, month: int) -> None:
    """月次バッチ: データ収集 → ブログ生成 → WordPress 投稿"""
    # 1. Sheets からポートフォリオ同期
    self.sheets_sync.sync_holdings()

    # 2. yfinance で株価取得 → SQLite 保存
    self.collect_monthly_data(year, month)

    # 3. ベンチマーク（日経225/S&P500）取得 → SQLite 保存
    self.benchmark_collector.collect(year, month)

    # 4. チャート画像生成
    self.chart_generator.generate_all(year, month)

    # 5. ブログ下書き生成（Claude Haiku でコメント付き）
    report_data = self.report_generator.get_monthly_report_data(year, month)
    report_data["ai_comments"] = self.ai_comment.generate_all(report_data)
    draft_path = self.template_engine.render("blog_template.md", report_data)

    # 6. WordPress に下書き投稿
    self.wp_publisher.create_draft(
        title=f"{year}年{month}月の投資成績",
        markdown_content=draft_path.read_text(),
        image_paths=self.chart_generator.get_image_paths(year, month),
    )
```

### 依存パッケージの変更

```diff
# collector/pyproject.toml
  dependencies = [
    "yfinance>=0.2.18",
    "pandas>=2.0.0",
-   "google-api-python-client>=2.100.0",
-   "google-auth-httplib2>=0.1.0",
-   "google-auth-oauthlib>=1.1.0",
-   "google-auth>=2.40.3",
-   "gspread>=6.2.1",
+   "gspread>=6.2.1",              # Sheets 同期用（読み取りのみ）
+   "google-auth>=2.40.3",         # 認証
    "python-dotenv>=1.0.0",
    "jinja2>=3.1.0",
+   "anthropic>=0.49.0",           # Claude Haiku
+   "requests>=2.31.0",            # WordPress API
+   "markdown>=3.7",               # Markdown → HTML 変換
  ]
```

---

## 6. GCP デプロイ設計

### e2-micro セットアップスクリプト

```bash
#!/bin/bash
# deploy/setup.sh — e2-micro 初期セットアップ

set -euo pipefail

# === Node.js (fnm) ===
curl -fsSL https://fnm.vercel.app/install | bash
export PATH="$HOME/.local/share/fnm:$PATH"
eval "$(fnm env)"
fnm install 22
fnm default 22

# === Python (uv) ===
curl -LsSf https://astral.sh/uv/install.sh | sh

# === Caddy ===
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy

# === gsutil（GCS バックアップ用）===
# GCE インスタンスには gcloud CLI がプリインストール済み

# === アプリケーション ===
git clone https://github.com/<user>/portfolio-dashboard.git /app
cd /app
npm install
npm run build
cd /app/collector && uv sync

# === systemd ===
sudo cp deploy/portfolio.service /etc/systemd/system/
sudo systemctl enable portfolio
sudo systemctl start portfolio

# === Caddy ===
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy

# === crontab ===
(crontab -l 2>/dev/null; echo "0 9 1 * * cd /app/collector && uv run python main.py \$(date +\%Y) \$(date +\%m) >> /app/logs/collector.log 2>&1") | crontab -
(crontab -l 2>/dev/null; echo "0 3 * * * /app/deploy/backup.sh >> /app/logs/backup.log 2>&1") | crontab -
```

### Caddyfile

```
# deploy/Caddyfile
dashboard.example.com {
    reverse_proxy localhost:3000
    encode gzip
    log {
        output file /var/log/caddy/access.log
    }
}
```

### systemd ユニット

```ini
# deploy/portfolio.service
[Unit]
Description=Portfolio Dashboard (Hono)
After=network.target

[Service]
Type=simple
User=deploy
WorkingDirectory=/app
ExecStart=/home/deploy/.local/share/fnm/aliases/default/bin/node server/dist/index.js
Restart=always
RestartSec=5
Environment=NODE_ENV=production
Environment=PORT=3000
Environment=DB_PATH=/app/data/portfolio.db

[Install]
WantedBy=multi-user.target
```

### SQLite バックアップ

```bash
#!/bin/bash
# deploy/backup.sh — SQLite → GCS 日次バックアップ
set -euo pipefail

DB_PATH="/app/data/portfolio.db"
BUCKET="gs://portfolio-backup-<project-id>"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# SQLite の安全なバックアップ（.backup コマンドで一貫性保証）
sqlite3 "$DB_PATH" ".backup /tmp/portfolio_backup.db"

# GCS にアップロード
gsutil cp /tmp/portfolio_backup.db "$BUCKET/portfolio_${TIMESTAMP}.db"

# 30日以前のバックアップを削除
gsutil ls "$BUCKET/" | head -n -30 | xargs -r gsutil rm

rm /tmp/portfolio_backup.db
```

### ドメイン設定

```
CONOHA の DNS 管理画面:
  dashboard.yourdomain.com → A レコード → GCP e2-micro の外部IP

Caddy が自動で Let's Encrypt 証明書を取得・更新
```

---

## 7. CI/CD

### GitHub Actions

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - run: npm ci
      - run: npm run lint
      - run: npm run check
      - run: npm run test

  collector-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: cd collector && uv sync --dev
      - run: cd collector && uv run ruff check .
      - run: cd collector && uvx ty check

  deploy:
    needs: [lint-and-test, collector-lint]
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - run: npm ci && npm run build
      # SSH でデプロイ（rsync + systemctl restart）
      - name: Deploy to GCE
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.GCE_HOST }}
          username: deploy
          key: ${{ secrets.GCE_SSH_KEY }}
          script: |
            cd /app
            git pull origin main
            npm ci && npm run build
            cd collector && uv sync
            sudo systemctl restart portfolio
```

### テスト戦略

| 対象 | ツール | テスト内容 |
|------|--------|-----------|
| server/ | Vitest | API ルートのユニットテスト（SQLite in-memory） |
| client/ | Vitest + Testing Library | ユーティリティ関数 + コンポーネント |
| collector/ | pytest | データ収集・損益計算ロジック |

---

## 8. 移行手順

### フェーズ 1: 基盤構築（SQLite + Hono）

1. プロジェクト初期化（npm workspaces, Drizzle, Hono）
2. SQLite スキーマ作成 + マイグレーション
3. **既存データ移行スクリプト**: Google Sheets → SQLite
   ```python
   # scripts/migrate_from_sheets.py
   # 全4シートの全レコードを読み取り、SQLite に INSERT
   ```
4. Hono ルーター実装（8エンドポイント、SQLite クエリ）
5. テスト作成

### フェーズ 2: フロントエンド移植

6. Vite + React Router セットアップ
7. 既存コンポーネント移植（`"use client"` 削除、TanStack Query 導入）
8. 全ページの動作確認

### フェーズ 3: collector 改修

9. `db_writer.py` 作成（Sheets → SQLite 出力先変更）
10. `sheets_sync.py` 作成（Sheets 一方向同期）
11. `benchmark_collector.py` 作成
12. `ai_comment.py` 作成（Claude Haiku 統合）
13. `wp_publisher.py` 作成（WordPress REST API）
14. テンプレート更新（AI コメント挿入対応）

### フェーズ 4: デプロイ

15. GCP e2-micro インスタンス作成
16. Caddy + systemd + crontab 設定
17. ドメイン設定（サブドメイン → GCE）
18. GCS バックアップ設定
19. GitHub Actions CI/CD 設定

### フェーズ 5: 検証・切り替え

20. 月次バッチの手動実行テスト
21. WordPress 下書き投稿テスト
22. 本番切り替え（旧システム停止）

---

## 消えるもの

| 消えるもの | 理由 |
|-----------|------|
| `web-app/backend/` (FastAPI 全体) | Hono に統合 |
| `web-app/frontend/` (Next.js 全体) | Vite + React SPA に置換 |
| `shared/sheets_config.py` | Drizzle スキーマに統合 |
| `collectors/sheets_writer.py` | `db_writer.py` に置換 |
| gspread 読み取りロジック（backend） | SQLite クエリに置換 |
| `next.config.ts` の API リライト | サーバー1台なので不要 |
| CORS 設定 | 同上 |

## 残るもの

| 残るもの | 理由 |
|---------|------|
| `stock_collector.py` | yfinance ロジックはそのまま |
| `currency_converter.py` | 同上 |
| `chart_image_generator.py` | matplotlib チャート生成はそのまま |
| `interactive_chart_generator.py` | Chart.js HTML 生成はそのまま |
| `template_engine.py` | Jinja2 テンプレートはそのまま |
| `blog_template.md` | AI コメント挿入部分のみ修正 |
| 全 Recharts コンポーネント | `"use client"` 削除のみ |
| `formatters.ts`, `chartUtils.ts`, `types/index.ts` | そのまま移植 |
