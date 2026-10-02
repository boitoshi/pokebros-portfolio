import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";

// DB_PATH を :memory: に設定してからモジュールをインポート
process.env.DB_PATH = ":memory:";

const __dirname = dirname(fileURLToPath(import.meta.url));

let app: any;

beforeAll(async () => {
  // db/index.ts は process.env.DB_PATH を参照するので、インポート前に設定済み
  const { sqlite } = await import("../db/index.js");

  // 全マイグレーション SQL を順に読み込んで実行
  const migrationFiles = [
    "0000_wise_morgan_stark.sql",
    "0001_add_purchase_history.sql",
    "0002_petite_vampiro.sql",
    "0003_overjoyed_santa_claus.sql",
    "0004_adorable_tyger_tiger.sql",
    "0005_remarkable_kingpin.sql",
  ];

  for (const file of migrationFiles) {
    const sql = readFileSync(
      resolve(__dirname, "../../drizzle/migrations", file),
      "utf-8",
    );
    const statements = sql
      .split("--> statement-breakpoint")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    for (const stmt of statements) {
      sqlite.exec(stmt);
    }
  }

  // テストデータ INSERT
  sqlite.exec(`
    INSERT INTO holdings (code, name, acquired_date, acquired_price_jpy, acquired_price_foreign, acquired_exchange_rate, shares, currency, is_foreign)
    VALUES ('7974.T', '任天堂', '2023-06-28', 6433, NULL, NULL, 100, 'JPY', 0);
  `);
  sqlite.exec(`
    INSERT INTO holdings (code, name, acquired_date, acquired_price_jpy, acquired_price_foreign, acquired_exchange_rate, shares, currency, is_foreign)
    VALUES ('NVDA', 'エヌビディア', '2024-03-15', 16500, 110.0, 150.0, 10, 'USD', 1);
  `);

  sqlite.exec(`
    INSERT INTO monthly_pnl (date, code, name, acquired_price, current_price, shares, cost, value, profit, profit_rate, currency, acquired_price_foreign, current_price_foreign, acquired_exchange_rate, current_exchange_rate)
    VALUES ('2025-03-末', '7974.T', '任天堂', 6433, 10000, 100, 643300, 1000000, 356700, 55.45, 'JPY', NULL, NULL, NULL, NULL);
  `);
  sqlite.exec(`
    INSERT INTO monthly_pnl (date, code, name, acquired_price, current_price, shares, cost, value, profit, profit_rate, currency, acquired_price_foreign, current_price_foreign, acquired_exchange_rate, current_exchange_rate)
    VALUES ('2025-03-末', 'NVDA', 'エヌビディア', 16500, 18000, 10, 165000, 180000, 15000, 9.09, 'USD', 110.0, 120.0, 150.0, 150.0);
  `);

  sqlite.exec(`
    INSERT INTO exchange_rates (date, pair, rate, prev_rate, change_rate, high, low)
    VALUES ('2025-03-31', 'USD/JPY', 150.0, 149.0, 0.67, 151.0, 148.0);
  `);

  // 配当: 外国株1件＋日本株1件＋stock_meta 未登録銘柄1件（ソート・color・null 安全の検証用）
  sqlite.exec(`
    INSERT INTO dividends (date, code, name, dividend_foreign, shares, total_foreign, currency, exchange_rate, total_jpy)
    VALUES ('2025-03-15', 'NVDA', 'エヌビディア', 0.01, 10, 0.1, 'USD', 150.0, 15);
  `);
  sqlite.exec(`
    INSERT INTO dividends (date, code, name, dividend_foreign, shares, total_foreign, currency, exchange_rate, total_jpy)
    VALUES ('2025-06-27', '7974.T', '任天堂', NULL, 2, NULL, 'JPY', NULL, 236);
  `);
  sqlite.exec(`
    INSERT INTO dividends (date, code, name, dividend_foreign, shares, total_foreign, currency, exchange_rate, total_jpy)
    VALUES ('2025-06-27', 'TEST.X', 'テスト銘柄', NULL, 1, NULL, 'JPY', NULL, 100);
  `);

  sqlite.exec(`
    INSERT INTO benchmark_data (date, portfolio, nikkei225, sp500)
    VALUES ('2025-01-末', 5.0, 3.0, 2.0);
  `);
  sqlite.exec(`
    INSERT INTO benchmark_data (date, portfolio, nikkei225, sp500)
    VALUES ('2025-02-末', 10.0, 5.0, 4.0);
  `);
  sqlite.exec(`
    INSERT INTO benchmark_data (date, portfolio, nikkei225, sp500)
    VALUES ('2025-03-末', 15.0, 8.0, 6.0);
  `);

  // purchase_history（buildReportData / stocks 拡張が参照するため追加）
  // 7974.T: 日本株2件（seq 1, 2）、NVDA: 外国株1件（seq 1）
  sqlite.exec(`
    INSERT INTO purchase_history (code, seq, shares, price, price_foreign, exchange_rate, purchased_at)
    VALUES
      ('7974.T', 1, 100, 6433, NULL, NULL, '2023-06-28'),
      ('7974.T', 2,  50, 6500, NULL, NULL, '2023-09-01'),
      ('NVDA',   1,  10,    0, 110.0, 150.0, '2024-03-15');
  `);

  // app をインポート（DB 準備完了後）
  const mod = await import("../index.js");
  app = mod.default;
});

describe("API routes", () => {
  it("GET /health → { status: 'ok' }", async () => {
    const res = await app.request("/health");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toEqual({ status: "ok" });
  });

  it("GET /api/dashboard → kpi.totalValue === 1180000、allocation と latestProfits は 2件", async () => {
    const res = await app.request("/api/dashboard");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.kpi.totalValue).toBe(1180000);
    expect(body.allocation).toHaveLength(2);
    expect(body.latestProfits).toHaveLength(2);
  });

  it("GET /api/dashboard → 拡張フィールド stocks/totalHistory/usdJpy が存在する", async () => {
    const res = await app.request("/api/dashboard");
    expect(res.status).toBe(200);
    const body = await res.json();
    // stocks は 2件（7974.T, NVDA）
    expect(Array.isArray(body.stocks)).toBe(true);
    expect(body.stocks).toHaveLength(2);
    // 各 stock に必須フィールドが含まれる
    const stock = body.stocks[0];
    expect(stock).toHaveProperty("code");
    expect(stock).toHaveProperty("priceHistory");
    expect(stock).toHaveProperty("acquiredAvgHistory");
    expect(stock).toHaveProperty("monthLabels");
    expect(stock).toHaveProperty("transactions");
    expect(Array.isArray(stock.priceHistory)).toBe(true);
    // totalHistory
    expect(body.totalHistory).toHaveProperty("months");
    expect(body.totalHistory).toHaveProperty("assetValues");
    expect(body.totalHistory).toHaveProperty("plValues");
    // usdJpy は数値
    expect(typeof body.usdJpy).toBe("number");
    expect(body.usdJpy).toBe(150.0);
  });

  it("GET /api/portfolio → items は 2件、items[0].totalCost === 643300", async () => {
    const res = await app.request("/api/portfolio");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.items).toHaveLength(2);
    // code 順にソートされている場合でも totalCost で探す
    const nintendo = body.items.find(
      (item: { code: string }) => item.code === "7974.T",
    );
    expect(nintendo).toBeDefined();
    expect(nintendo.totalCost).toBe(643300);
  });

  it("GET /api/portfolio → items[].purchases が seq 昇順で返り、外国株は priceForeign/exchangeRate を含む", async () => {
    const res = await app.request("/api/portfolio");
    expect(res.status).toBe(200);
    const body = await res.json();

    const nintendo = body.items.find(
      (item: { code: string }) => item.code === "7974.T",
    );
    expect(nintendo.purchases).toHaveLength(2);
    expect(nintendo.purchases.map((p: { seq: number }) => p.seq)).toEqual([
      1, 2,
    ]);
    expect(nintendo.purchases[0].priceForeign).toBeNull();
    expect(nintendo.purchases[0].exchangeRate).toBeNull();

    const nvda = body.items.find(
      (item: { code: string }) => item.code === "NVDA",
    );
    expect(nvda.purchases).toHaveLength(1);
    expect(nvda.purchases[0].priceForeign).toBe(110.0);
    expect(nvda.purchases[0].exchangeRate).toBe(150.0);
  });

  it("GET /api/history → data は 2件、symbols は code 昇順で { code, name } の配列", async () => {
    const res = await app.request("/api/history");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data).toHaveLength(2);
    expect(body.symbols).toHaveLength(2);
    expect(body.symbols).toEqual([
      { code: "7974.T", name: "任天堂" },
      { code: "NVDA", name: "エヌビディア" },
    ]);
  });

  it("GET /api/history?stock=7974.T → data は 1件", async () => {
    const res = await app.request("/api/history?stock=7974.T");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data).toHaveLength(1);
    expect(body.data[0].code).toBe("7974.T");
  });

  it("GET /api/currency → data は 1件、latestRate === 150.0", async () => {
    const res = await app.request("/api/currency");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data).toHaveLength(1);
    expect(body.latestRate).toBe(150.0);
  });

  it("GET /api/dividend → date降順・code昇順、color 付与、totalJpy === 351", async () => {
    const res = await app.request("/api/dividend");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data).toHaveLength(3);
    expect(body.totalJpy).toBe(351);

    // ソート: date 降順 → 同一日は code 昇順
    expect(body.data.map((d: { code: string }) => d.code)).toEqual([
      "7974.T",
      "TEST.X",
      "NVDA",
    ]);

    // color: stock_meta 登録銘柄はその色、未登録はフォールバック先頭色
    expect(body.data[0].color).toBe("#E53935"); // 7974.T（stock_meta）
    expect(body.data[1].color).toBe("#FF6F00"); // TEST.X（フォールバック）
    expect(body.data[2].color).toBe("#76B900"); // NVDA（stock_meta）

    // 日本株行は外貨系フィールドが null（クライアントの null 安全表示の前提）
    expect(body.data[0].dividendForeign).toBeNull();
    expect(body.data[0].totalForeign).toBeNull();
    expect(body.data[0].exchangeRate).toBeNull();

    // 外国株行は外貨系フィールドが number
    expect(body.data[2].dividendForeign).toBe(0.01);
    expect(body.data[2].totalForeign).toBe(0.1);
    expect(body.data[2].exchangeRate).toBe(150.0);
  });

  it("GET /api/benchmark → data は 3件", async () => {
    const res = await app.request("/api/benchmark");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data).toHaveLength(3);
  });

  it("GET /api/exposure → items は 2件（JPY, USD）、JPY の value === 1000000", async () => {
    const res = await app.request("/api/exposure");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.items).toHaveLength(2);
    const jpyItem = body.items.find(
      (item: { currency: string }) => item.currency === "JPY",
    );
    expect(jpyItem).toBeDefined();
    expect(jpyItem.value).toBe(1000000);
  });

  it("GET /api/reports → reports は配列（空でも可）", async () => {
    const res = await app.request("/api/reports");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(Array.isArray(body.reports)).toBe(true);
  });

  it("GET /api/reports/2025/3/data → 正常系: meta.year=2025, stocks は 2件", async () => {
    const res = await app.request("/api/reports/2025/3/data");
    expect(res.status).toBe(200);
    const body = await res.json();
    // meta フィールドの確認
    expect(body.meta.year).toBe(2025);
    expect(body.meta.month).toBe(3);
    expect(body.meta.reportDate).toBe("2025年3月末");
    // stocks は 2件
    expect(Array.isArray(body.stocks)).toBe(true);
    expect(body.stocks).toHaveLength(2);
    // totalHistory の形状確認
    expect(Array.isArray(body.totalHistory.months)).toBe(true);
    expect(Array.isArray(body.totalHistory.assetValues)).toBe(true);
    // intro/summary は null（テストデータ未設定）
    expect(body.intro).toBeNull();
    expect(body.summary).toBeNull();
  });

  it("GET /api/reports/1999/1/data → 404 JSON", async () => {
    const res = await app.request("/api/reports/1999/1/data");
    expect(res.status).toBe(404);
    const body = await res.json();
    expect(body).toHaveProperty("error");
  });

  it("GET /api/reports/2025/3 → Markdown ルートは既存のまま動作（404 is ok, endpoint still exists）", async () => {
    // テスト環境では REPORTS_DIR が存在しないため 404 が期待値
    const res = await app.request("/api/reports/2025/3");
    // 200 または 404（ファイル存在有無による）— ステータスは問わず形状のみ確認
    const body = await res.json();
    expect(body).toBeDefined();
  });
});
