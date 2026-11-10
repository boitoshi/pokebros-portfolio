/**
 * reportData サービスのユニットテスト
 *
 * `:memory:` + migration 方式で routes.test.ts と同じパターンを使用。
 * 買付 2 回シナリオで移動平均・acquiredAvgHistory・totalHistory を検証する。
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { BetterSQLite3Database } from "drizzle-orm/better-sqlite3";
import { beforeAll, describe, expect, it } from "vitest";
import type * as schemaTypes from "../db/schema.js";

// テスト前に DB_PATH を :memory: へ変更（db/index.ts より先に設定）
// ※ routes.test.ts が同じ process.env.DB_PATH を使うため、
//    このファイルを独立したテストファイルとして実行する
process.env.DB_PATH_REPORT_TEST = ":memory:";

const __dirname = dirname(fileURLToPath(import.meta.url));

let testDb: BetterSQLite3Database<typeof schemaTypes>;

beforeAll(async () => {
  // better-sqlite3 でインメモリ DB を独立生成
  const Database = (await import("better-sqlite3")).default;
  const { drizzle } = await import("drizzle-orm/better-sqlite3");
  const schema = await import("../db/schema.js");

  const sqlite = new Database(":memory:");
  sqlite.pragma("journal_mode = WAL");
  testDb = drizzle(sqlite, { schema });

  // マイグレーション SQL を順に適用
  const migrationFiles = [
    "0000_wise_morgan_stark.sql",
    "0001_add_purchase_history.sql",
    "0002_petite_vampiro.sql",
    "0003_overjoyed_santa_claus.sql",
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

  // ── テストデータ: 7974.T（任天堂）2回買付シナリオ ──────────────
  // 買付1: 100株 @ 6500円（JPY）2023-06-01
  // 買付2:  50株 @ 9200円（JPY）2024-07-01
  // 期待移動平均取得単価（最終）:
  //   累計コスト = 100*6500 + 50*9200 = 650000 + 460000 = 1110000
  //   累計株数   = 150
  //   平均       = 1110000 / 150 = 7400

  sqlite.exec(`
    INSERT INTO purchase_history (code, seq, shares, price, price_foreign, exchange_rate, purchased_at)
    VALUES
      ('7974.T', 1, 100, 6500, NULL, NULL, '2023-06-01'),
      ('7974.T', 2,  50, 9200, NULL, NULL, '2024-07-01');
  `);

  // monthly_pnl: 2023-06-末〜2024-07-末（途中1月分欠落なし・シンプルケース）
  sqlite.exec(`
    INSERT INTO monthly_pnl (date, code, name, acquired_price, current_price, shares,
      cost, value, profit, profit_rate, currency)
    VALUES
      ('2023-06-末', '7974.T', '任天堂', 6500,  6200, 100,  650000,  620000,  -30000, -4.62, 'JPY'),
      ('2023-07-末', '7974.T', '任天堂', 6500,  6800, 100,  650000,  680000,   30000,  4.62, 'JPY'),
      ('2024-07-末', '7974.T', '任天堂', 7400, 10000, 150, 1110000, 1500000,  390000, 35.14, 'JPY');
  `);

  // exchange_rates（USD/JPY）: 対象月用
  sqlite.exec(`
    INSERT INTO exchange_rates (date, pair, rate)
    VALUES ('2024-07-31', 'USD/JPY', 155.0);
  `);

  // stock_meta（0003 マイグレーションで INSERT されているが、テスト DB は独立なのでここでも挿入）
  sqlite.exec(`
    INSERT OR IGNORE INTO stock_meta (code, color, market, sort_order)
    VALUES ('7974.T', '#E53935', '東証プライム', 0);
  `);
});

/** レポートを構築し、null ならテストを失敗させる（以降のアサーションで `!` を使わずに済む） */
async function buildOrFail(targetDate: string) {
  const { buildReportData } = await import("../services/reportData.js");
  const result = buildReportData(testDb, targetDate);
  if (!result) throw new Error(`${targetDate} のレポートが null だった`);
  return result;
}

describe("buildReportData", () => {
  it("対象月が存在しない場合は null を返す", async () => {
    const { buildReportData } = await import("../services/reportData.js");
    const result = buildReportData(testDb, "1999-01-末");
    expect(result).toBeNull();
  });

  it("最新月（2024-07-末）のデータを正常に構築する", async () => {
    const result = await buildOrFail("2024-07-末");
    expect(result.meta.year).toBe(2024);
    expect(result.meta.month).toBe(7);
    expect(result.meta.reportDate).toBe("2024年7月末");
    expect(result.meta.exchangeRate).toBe(155.0);
  });

  it("stocks は 1件（7974.T）で基本フィールドが正しい", async () => {
    const result = await buildOrFail("2024-07-末");
    const stock = result.stocks[0];

    expect(stock.code).toBe("7974.T");
    expect(stock.ticker).toBe("7974.T");
    expect(stock.currency).toBe("JPY");
    expect(stock.market).toBe("東証プライム");
    expect(stock.color).toBe("#E53935");
    expect(stock.currentPrice).toBe(10000);
    expect(stock.value).toBe(1500000);
    expect(stock.profit).toBe(390000);
  });

  it("quantity は 2回買付の合計株数（100+50=150）", async () => {
    const result = await buildOrFail("2024-07-末");
    expect(result.stocks[0].quantity).toBe(150);
  });

  it("acquiredPrice は移動平均（1110000/150=7400）", async () => {
    const result = await buildOrFail("2024-07-末");
    expect(result.stocks[0].acquiredPrice).toBeCloseTo(7400, 5);
  });

  it("acquiredAvgHistory は stepped line になっている", async () => {
    const result = await buildOrFail("2024-07-末");
    const stock = result.stocks[0];

    // monthLabels: ["2023/6", "2023/7", "2024/7"]
    expect(stock.monthLabels).toEqual(["2023/6", "2023/7", "2024/7"]);

    // 2023/6: 買付1のみ → 650000/100 = 6500
    expect(stock.acquiredAvgHistory[0]).toBeCloseTo(6500, 5);

    // 2023/7: 変化なし（買付2は2024/7）→ 6500
    expect(stock.acquiredAvgHistory[1]).toBeCloseTo(6500, 5);

    // 2024/7: 買付2が加算 → 1110000/150 = 7400
    expect(stock.acquiredAvgHistory[2]).toBeCloseTo(7400, 5);
  });

  it("priceHistory は monthly_pnl の currentPrice と一致する", async () => {
    const result = await buildOrFail("2024-07-末");
    expect(result.stocks[0].priceHistory).toEqual([6200, 6800, 10000]);
  });

  it("transactions は 2件（buy のみ）で month インデックスが正しい", async () => {
    const result = await buildOrFail("2024-07-末");
    const txs = result.stocks[0].transactions;

    expect(txs).toHaveLength(2);
    // 買付1: 2023/6 → monthLabels[0]
    const buy1 = txs.find((t) => t.price === 6500);
    expect(buy1).toMatchObject({ month: 0, action: "buy", quantity: 100 });

    // 買付2: 2024/7 → monthLabels[2]
    const buy2 = txs.find((t) => t.price === 9200);
    expect(buy2).toMatchObject({ month: 2, action: "buy", quantity: 50 });
  });

  it("previousMonthPrice は前月（2024-06-末）が存在しないので null", async () => {
    // テストデータには 2024-06-末 の monthly_pnl がないので null になる
    const result = await buildOrFail("2024-07-末");
    expect(result.stocks[0].previousMonthPrice).toBeNull();
  });

  it("previousMonthPrice は前月（2023-07-末）が存在する場合に取得できる", async () => {
    // 2023-06-末 の前月は 2023-05-末（データなし）→ null
    // 2023-07-末 の前月は 2023-06-末（データあり）→ 6200
    const result = await buildOrFail("2023-07-末");
    expect(result.stocks[0].previousMonthPrice).toBe(6200);
  });

  it("totalHistory は全月の合計値を集計している", async () => {
    const result = await buildOrFail("2024-07-末");
    const th = result.totalHistory;

    // 月数: 2023-06-末, 2023-07-末, 2024-07-末 の 3 月
    expect(th.months).toHaveLength(3);
    expect(th.months).toEqual(["2023/6", "2023/7", "2024/7"]);

    // 2024-07-末の assetValue = 1500000
    const idx = th.months.indexOf("2024/7");
    expect(th.assetValues[idx]).toBe(1500000);
    expect(th.plValues[idx]).toBe(390000);
  });

  it("intro と summary は null（AI コメント未設定）", async () => {
    const result = await buildOrFail("2024-07-末");
    expect(result.intro).toBeNull();
    expect(result.summary).toBeNull();
  });

  it("comment は null（AI コメント未設定）", async () => {
    const result = await buildOrFail("2024-07-末");
    expect(result.stocks[0].comment).toBeNull();
  });
});
