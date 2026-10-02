import { desc, eq } from "drizzle-orm";
import { Hono } from "hono";
import { db } from "../db/index.js";
import { getLatestDate, getLatestPnlRecords } from "../db/queries.js";
import { exchangeRates, latestPnl, purchaseHistory } from "../db/schema.js";
import {
  applyLatestSnapshot,
  summarizeRecords,
} from "../services/liveSnapshot.js";
import { buildReportData } from "../services/reportData.js";

const app = new Hono();

app.get("/", (c) => {
  const latestDate = getLatestDate();

  if (!latestDate) {
    return c.json({
      kpi: { totalValue: 0, totalProfit: 0, profitRate: 0, baseDate: "" },
      allocation: [],
      latestProfits: [],
      stocks: [],
      totalHistory: { months: [], assetValues: [], plValues: [] },
      usdJpy: null,
      asOf: null,
    });
  }

  const records = getLatestPnlRecords(latestDate);
  const summary = summarizeRecords(records, latestDate);

  // ── 拡張データ：stocks / totalHistory / usdJpy ───────────────
  // buildReportData は latestDate をベースに詳細データを構築する
  const reportData = buildReportData(db, latestDate);

  // 最新 USD/JPY レート
  const latestUsdJpy = db
    .select({ rate: exchangeRates.rate })
    .from(exchangeRates)
    .where(eq(exchangeRates.pair, "USD/JPY"))
    .orderBy(desc(exchangeRates.date))
    .limit(1)
    .get();

  const base = {
    ...summary,
    // 以下は Phase A で追加した拡張フィールド
    stocks: reportData?.stocks ?? [],
    totalHistory: reportData?.totalHistory ?? {
      months: [],
      assetValues: [],
      plValues: [],
    },
    usdJpy: latestUsdJpy?.rate ?? null,
  };

  // latest_pnl（collector が毎日上書きする最新スナップショット）を月次の上に重ねる
  const latestRows = db.select().from(latestPnl).all();
  const purchases =
    latestRows.length > 0 ? db.select().from(purchaseHistory).all() : [];

  return c.json(applyLatestSnapshot(base, latestDate, latestRows, purchases));
});

export { app as dashboardRoute };
