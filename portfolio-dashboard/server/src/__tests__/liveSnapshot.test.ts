/**
 * 最新スナップショット（latest_pnl）重ね合わせの統合テスト。
 * routes.test.ts と同じく :memory: DB + マイグレーション SQL 方式。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";

process.env.DB_PATH = ":memory:";
// routes.test.ts と同時に index.ts を読み込んでもポートが衝突しないよう OS 任せにする
process.env.PORT = "0";

const __dirname = dirname(fileURLToPath(import.meta.url));

// biome-ignore lint/suspicious/noExplicitAny: テスト用
let app: any;
// biome-ignore lint/suspicious/noExplicitAny: テスト用
let sqlite: any;

const insertLatest = (
  code: string,
  name: string,
  currency: string,
  priceDate: string,
  v: {
    price: number;
    priceForeign: number | null;
    rate: number | null;
    monthStart: number | null;
    shares: number;
    cost: number;
    acq: number;
    acqForeign: number | null;
    value: number;
    profit: number;
    profitRate: number;
  },
) => {
  sqlite
    .prepare(
      `INSERT INTO latest_pnl (code, name, currency, price_date, current_price, current_price_foreign, exchange_rate, month_start_price_native, shares, cost, acquired_price, acquired_price_foreign, value, profit, profit_rate, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2025-04-10T00:00:00')`,
    )
    .run(
      code,
      name,
      currency,
      priceDate,
      v.price,
      v.priceForeign,
      v.rate,
      v.monthStart,
      v.shares,
      v.cost,
      v.acq,
      v.acqForeign,
      v.value,
      v.profit,
      v.profitRate,
    );
};

const seedLatest = (priceDate: string) => {
  sqlite.exec("DELETE FROM latest_pnl");
  // 任天堂: 4月に 10 株追加買付（150 株）
  insertLatest("7974.T", "任天堂", "JPY", priceDate, {
    price: 11000,
    priceForeign: null,
    rate: null,
    monthStart: 10500,
    shares: 150,
    cost: 1000000,
    acq: 6666.67,
    acqForeign: null,
    value: 1650000,
    profit: 650000,
    profitRate: 65,
  });
  insertLatest("NVDA", "エヌビディア", "USD", priceDate, {
    price: 21000,
    priceForeign: 140,
    rate: 150,
    monthStart: null,
    shares: 10,
    cost: 165000,
    acq: 16500,
    acqForeign: 110,
    value: 210000,
    profit: 45000,
    profitRate: 27.27,
  });
  // monthly_pnl に無い新規銘柄（合計にだけ含まれる）
  insertLatest("NEW.T", "新規", "JPY", priceDate, {
    price: 1000,
    priceForeign: null,
    rate: null,
    monthStart: 1000,
    shares: 1,
    cost: 900,
    acq: 900,
    acqForeign: null,
    value: 1000,
    profit: 100,
    profitRate: 11.11,
  });
};

beforeAll(async () => {
  ({ sqlite } = await import("../db/index.js"));

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
    for (const stmt of sql
      .split("--> statement-breakpoint")
      .map((s) => s.trim())
      .filter((s) => s.length > 0)) {
      sqlite.exec(stmt);
    }
  }

  sqlite.exec(`
    INSERT INTO monthly_pnl (date, code, name, acquired_price, current_price, shares, cost, value, profit, profit_rate, currency, acquired_price_foreign, current_price_foreign, acquired_exchange_rate, current_exchange_rate)
    VALUES
      ('2025-03-末', '7974.T', '任天堂', 6433, 10000, 100, 643300, 1000000, 356700, 55.45, 'JPY', NULL, NULL, NULL, NULL),
      ('2025-03-末', 'NVDA', 'エヌビディア', 16500, 18000, 10, 165000, 180000, 15000, 9.09, 'USD', 110.0, 120.0, 150.0, 150.0);
    INSERT INTO exchange_rates (date, pair, rate, prev_rate, change_rate, high, low)
    VALUES ('2025-03-31', 'USD/JPY', 150.0, 149.0, 0.67, 151.0, 148.0);
    INSERT INTO purchase_history (code, seq, shares, price, price_foreign, exchange_rate, purchased_at)
    VALUES
      ('7974.T', 1, 100, 6433, NULL, NULL, '2025-01-10'),
      ('7974.T', 2, 50, 6500, NULL, NULL, '2025-04-02'),
      ('NVDA', 1, 10, 0, 110.0, 150.0, '2025-01-15');
  `);

  app = (await import("../index.js")).default;
});

const getDashboard = async () => (await app.request("/api/dashboard")).json();
const getReport = async () =>
  (await app.request("/api/reports/2025/3/data")).json();

describe("dashboard 最新スナップショット重ね合わせ", () => {
  it("latest_pnl が空 → 従来値のまま asOf: null", async () => {
    const body = await getDashboard();
    expect(body.asOf).toBeNull();
    expect(body.kpi.totalValue).toBe(1180000);
    expect(body.kpi.baseDate).toBe("2025-03-末");
    expect(body.totalHistory.months).toEqual(["2025/3"]);
  });

  it("price_date が monthly 最新と同月 → 重ねない", async () => {
    const before = await getDashboard();
    seedLatest("2025-03-31");
    const body = await getDashboard();
    expect(body).toEqual(before);
    expect(body.asOf).toBeNull();
  });

  it("翌月 → 最新値を重ねる", async () => {
    seedLatest("2025-04-10");
    const body = await getDashboard();

    expect(body.asOf).toBe("2025-04-10");
    // 合計は latest_pnl の全行（新規銘柄含む）
    expect(body.kpi.totalValue).toBe(1650000 + 210000 + 1000);
    expect(body.kpi.totalProfit).toBe(650000 + 45000 + 100);
    expect(body.kpi.profitRate).toBeCloseTo(
      ((650000 + 45000 + 100) / (1000000 + 165000 + 900)) * 100,
    );
    expect(body.kpi.baseDate).toBe("2025-03-末");
    expect(body.allocation).toHaveLength(3);
    expect(body.allocation[0].name).toBe("任天堂");
    expect(body.latestProfits[0].name).toBe("任天堂");
    expect(body.usdJpy).toBe(150);

    // stocks（latest_pnl にある月次銘柄は置換）
    expect(body.stocks).toHaveLength(2);
    const nin = body.stocks.find((s: { code: string }) => s.code === "7974.T");
    expect(nin.currentPrice).toBe(11000);
    expect(nin.previousMonthPrice).toBe(10000);
    expect(nin.monthlyChangeRate).toBeCloseTo((11000 / 10500 - 1) * 100);
    expect(nin.quantity).toBe(150);
    expect(nin.value).toBe(1650000);
    expect(nin.acquiredPrice).toBeCloseTo(6666.67);
    expect(nin.priceHistory.at(-1)).toBe(11000);
    expect(nin.priceHistory).toHaveLength(nin.monthLabels.length);
    expect(nin.acquiredAvgHistory).toHaveLength(nin.monthLabels.length);
    expect(nin.monthLabels.at(-1)).toBe("2025/4");
    // 当月（4月）買付が末尾 index の buy として入る
    expect(nin.transactions.at(-1)).toEqual({
      month: nin.monthLabels.length - 1,
      action: "buy",
      quantity: 50,
      price: 6500,
    });

    const nvda = body.stocks.find((s: { code: string }) => s.code === "NVDA");
    expect(nvda.currentPrice).toBe(140);
    expect(nvda.previousMonthPrice).toBe(120);
    expect(nvda.acquiredPrice).toBe(110);
    expect(nvda.monthlyChangeRate).toBeNull();
    expect(nvda.monthLabels.at(-1)).toBe("2025/4");

    // totalHistory 末尾に 1 点
    expect(body.totalHistory.months).toEqual(["2025/3", "2025/4"]);
    expect(body.totalHistory.assetValues.at(-1)).toBe(1861000);
    expect(body.totalHistory.plValues.at(-1)).toBe(695100);
  });

  it("月次レポート /api/reports/:y/:m/data は latest_pnl の有無で変わらない", async () => {
    seedLatest("2025-04-10");
    const withLatest = await getReport();
    sqlite.exec("DELETE FROM latest_pnl");
    const without = await getReport();
    expect(withLatest).toEqual(without);
    expect(without.meta.year).toBe(2025);
  });
});
