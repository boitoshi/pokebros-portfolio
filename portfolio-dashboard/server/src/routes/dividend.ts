import { Hono } from "hono";
import { db } from "../db/index.js";
import { dividends, stockMeta } from "../db/schema.js";
import { FALLBACK_COLORS, resolveStockColors } from "../services/reportData.js";

const app = new Hono();

app.get("/", (c) => {
  const rows = db.select().from(dividends).all();

  // date 降順 → code 昇順でソート
  const sorted = [...rows].sort((a, b) => {
    if (a.date !== b.date) return a.date < b.date ? 1 : -1;
    return a.code < b.code ? -1 : a.code > b.code ? 1 : 0;
  });

  // stock_meta を取得し、reportData.ts（buildReportData）と同一ロジックで色を解決
  const metaRows = db.select().from(stockMeta).all();
  const metaMap = new Map(metaRows.map((r) => [r.code, r]));
  const colorMap = resolveStockColors(
    sorted.map((r) => r.code),
    metaMap,
  );

  const data = sorted.map((r) => ({
    date: r.date,
    code: r.code,
    name: r.name,
    dividendForeign: r.dividendForeign ?? null,
    shares: r.shares,
    totalForeign: r.totalForeign ?? null,
    currency: r.currency,
    exchangeRate: r.exchangeRate ?? null,
    totalJpy: r.totalJpy,
    color: colorMap.get(r.code) ?? FALLBACK_COLORS[0],
  }));

  const totalJpy = rows.reduce((sum, r) => sum + r.totalJpy, 0);

  return c.json({ data, totalJpy });
});

export { app as dividendRoute };
