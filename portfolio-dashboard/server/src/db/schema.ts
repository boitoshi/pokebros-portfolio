import {
  index,
  integer,
  real,
  sqliteTable,
  text,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";

// ━━━ 保有銘柄マスタ ━━━
export const holdings = sqliteTable(
  "holdings",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    code: text("code").notNull(),
    name: text("name").notNull(),
    acquiredDate: text("acquired_date"),
    acquiredPriceJpy: real("acquired_price_jpy").notNull(),
    acquiredPriceForeign: real("acquired_price_foreign"),
    acquiredExchangeRate: real("acquired_exchange_rate"),
    shares: real("shares").notNull(),
    currency: text("currency").notNull().default("JPY"),
    isForeign: integer("is_foreign", { mode: "boolean" })
      .notNull()
      .default(false),
    memo: text("memo"),
    updatedAt: text("updated_at"),
  },
  (table) => ({
    codeIdx: index("idx_holdings_code").on(table.code),
  }),
);

// ━━━ 月次市場データ ━━━
export const monthlyPrices = sqliteTable(
  "monthly_prices",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    date: text("date").notNull(),
    code: text("code").notNull(),
    priceJpy: real("price_jpy").notNull(),
    high: real("high"),
    low: real("low"),
    average: real("average"),
    changeRate: real("change_rate"),
    avgVolume: real("avg_volume"),
    createdAt: text("created_at"),
  },
  (table) => ({
    dateCodeUniq: uniqueIndex("uq_monthly_prices_date_code").on(
      table.date,
      table.code,
    ),
  }),
);

// ━━━ 月次損益 ━━━
export const monthlyPnl = sqliteTable(
  "monthly_pnl",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    date: text("date").notNull(),
    code: text("code").notNull(),
    name: text("name").notNull(),
    acquiredPrice: real("acquired_price").notNull(),
    currentPrice: real("current_price").notNull(),
    shares: real("shares").notNull(),
    cost: real("cost").notNull(),
    value: real("value").notNull(),
    profit: real("profit").notNull(),
    profitRate: real("profit_rate").notNull(),
    currency: text("currency").notNull().default("JPY"),
    acquiredPriceForeign: real("acquired_price_foreign"),
    currentPriceForeign: real("current_price_foreign"),
    acquiredExchangeRate: real("acquired_exchange_rate"),
    currentExchangeRate: real("current_exchange_rate"),
    updatedAt: text("updated_at"),
  },
  (table) => ({
    dateCodeUniq: uniqueIndex("uq_monthly_pnl_date_code").on(
      table.date,
      table.code,
    ),
    dateIdx: index("idx_monthly_pnl_date").on(table.date),
  }),
);

// ━━━ 為替レート ━━━
export const exchangeRates = sqliteTable(
  "exchange_rates",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    date: text("date").notNull(),
    pair: text("pair").notNull(),
    rate: real("rate").notNull(),
    prevRate: real("prev_rate"),
    changeRate: real("change_rate"),
    high: real("high"),
    low: real("low"),
    updatedAt: text("updated_at"),
  },
  (table) => ({
    datePairUniq: uniqueIndex("uq_exchange_rates_date_pair").on(
      table.date,
      table.pair,
    ),
  }),
);

// ━━━ 配当・分配金 ━━━
export const dividends = sqliteTable(
  "dividends",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    date: text("date").notNull(),
    code: text("code").notNull(),
    name: text("name").notNull(),
    dividendForeign: real("dividend_foreign"),
    shares: real("shares").notNull(),
    totalForeign: real("total_foreign"),
    currency: text("currency").notNull().default("JPY"),
    exchangeRate: real("exchange_rate"),
    totalJpy: real("total_jpy").notNull(),
  },
  (table) => ({
    dateCodeUniq: uniqueIndex("uq_dividends_date_code").on(
      table.date,
      table.code,
    ),
  }),
);

// ━━━ ベンチマークデータ ━━━
export const benchmarkData = sqliteTable(
  "benchmark_data",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    date: text("date").notNull(),
    portfolio: real("portfolio").notNull(),
    nikkei225: real("nikkei225"),
    sp500: real("sp500"),
  },
  (table) => ({
    dateUniq: uniqueIndex("uq_benchmark_data_date").on(table.date),
  }),
);

// ━━━ 購入履歴 ━━━
export const purchaseHistory = sqliteTable(
  "purchase_history",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    code: text("code").notNull(),
    seq: integer("seq").notNull(),
    shares: real("shares").notNull(),
    price: real("price").notNull(),
    priceForeign: real("price_foreign"),
    exchangeRate: real("exchange_rate"),
    purchasedAt: text("purchased_at").notNull(),
  },
  (table) => ({
    codeSeqUniq: uniqueIndex("uq_purchase_history_code_seq").on(
      table.code,
      table.seq,
    ),
  }),
);

// ━━━ 銘柄メタ情報（チャート色・市場区分・表示順） ━━━
export const stockMeta = sqliteTable("stock_meta", {
  code: text("code").primaryKey(),
  color: text("color").notNull(),
  market: text("market").notNull(),
  sortOrder: integer("sort_order").notNull().default(0),
});

// ━━━ AI コメント（銘柄別・月次レポート用） ━━━
export const aiComments = sqliteTable(
  "ai_comments",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    // "YYYY-MM-末" 形式。intro/summary は date のみで code=''
    date: text("date").notNull(),
    // 銘柄コード。intro/summary は空文字
    code: text("code").notNull().default(""),
    // 種別: 'stock'（銘柄コメント）| 'intro'（イントロ）| 'summary'（まとめ）
    kind: text("kind").notNull(),
    content: text("content").notNull(),
    createdAt: text("created_at"),
  },
  (table) => ({
    dateCodeKindUniq: uniqueIndex("uq_ai_comments_date_code_kind").on(
      table.date,
      table.code,
      table.kind,
    ),
  }),
);

// ━━━ WordPress 投稿リンク（月次レポート） ━━━
export const wpPosts = sqliteTable(
  "wp_posts",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    // "YYYY-MM" 形式
    month: text("month").notNull(),
    url: text("url").notNull(),
    title: text("title"),
    createdAt: text("created_at"),
  },
  (table) => ({
    monthUniq: uniqueIndex("uq_wp_posts_month").on(table.month),
  }),
);

// ━━━ 最新スナップショット（collector が毎日上書き。トップページ用） ━━━
export const latestPnl = sqliteTable("latest_pnl", {
  code: text("code").primaryKey(),
  name: text("name").notNull(),
  currency: text("currency").notNull(),
  // "YYYY-MM-DD"（yfinance の最終取引日）
  priceDate: text("price_date").notNull(),
  // 円建て現在価格
  currentPrice: real("current_price").notNull(),
  currentPriceForeign: real("current_price_foreign"),
  exchangeRate: real("exchange_rate"),
  // 当月最初の終値（native）。無ければ null
  monthStartPriceNative: real("month_start_price_native"),
  shares: real("shares").notNull(),
  cost: real("cost").notNull(),
  // 円建て平均取得単価
  acquiredPrice: real("acquired_price").notNull(),
  // native 平均取得単価（日本株は null）
  acquiredPriceForeign: real("acquired_price_foreign"),
  value: real("value").notNull(),
  profit: real("profit").notNull(),
  profitRate: real("profit_rate").notNull(),
  updatedAt: text("updated_at").notNull(),
});
