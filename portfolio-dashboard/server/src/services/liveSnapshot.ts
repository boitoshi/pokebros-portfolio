/**
 * 最新スナップショット重ね合わせサービス
 *
 * トップページ（GET /api/dashboard）は monthly_pnl の最新月末を基準にするため
 * 月1回しか値が変わらない。collector が latest_pnl に毎日上書きする「今日時点の値」を
 * 月次データの上に 1 点追加して返す。
 *
 * 重ねるのは latest_pnl の最終取引日の年月が monthly_pnl 最新月より後のときだけ。
 * reportData.ts（月次レポートと同一形状・同一計算を保つ義務がある）は変更せず、
 * その結果を受け取って加工する純粋関数として実装している。
 */

import type { latestPnl, purchaseHistory } from "../db/schema.js";
import type { ReportData, StockReportData } from "./reportData.js";

export type LatestPnlRow = typeof latestPnl.$inferSelect;
export type PurchaseRow = typeof purchaseHistory.$inferSelect;

export interface DashboardPayload {
  kpi: {
    totalValue: number;
    totalProfit: number;
    profitRate: number;
    baseDate: string;
  };
  allocation: { name: string; value: number; percentage: number }[];
  latestProfits: { name: string; profit: number; profitRate: number }[];
  stocks: StockReportData[];
  totalHistory: ReportData["totalHistory"];
  usdJpy: number | null;
  /** 最新スナップショットを重ねたときの最終取引日（"YYYY-MM-DD"）。重ねていなければ null */
  asOf: string | null;
}

interface YearMonth {
  year: number;
  month: number;
}

/** "YYYY-MM-末" / "YYYY-MM-DD" → { year, month } */
function parseYearMonth(date: string): YearMonth {
  const [y, m] = date.split("-");
  return { year: parseInt(y, 10), month: parseInt(m, 10) };
}

/** { year, month } → "YYYY/M" 形式のラベル */
function toMonthLabel(ym: YearMonth): string {
  return `${ym.year}/${ym.month}`;
}

function cmpYearMonth(a: YearMonth, b: YearMonth): number {
  return a.year !== b.year ? a.year - b.year : a.month - b.month;
}

/** 合計値（kpi / allocation / latestProfits）を行配列から計算する（dashboard.ts と同じ形・並び順） */
export function summarizeRecords(
  records: {
    name: string;
    value: number;
    profit: number;
    profitRate: number;
    cost: number;
  }[],
  baseDate: string,
): Pick<DashboardPayload, "kpi" | "allocation" | "latestProfits"> {
  const totalValue = records.reduce((sum, r) => sum + r.value, 0);
  const totalProfit = records.reduce((sum, r) => sum + r.profit, 0);
  const totalCost = records.reduce((sum, r) => sum + r.cost, 0);
  const profitRate = totalCost > 0 ? (totalProfit / totalCost) * 100 : 0;

  const allocation = records
    .map((r) => ({
      name: r.name,
      value: r.value,
      percentage: totalValue > 0 ? (r.value / totalValue) * 100 : 0,
    }))
    .sort((a, b) => b.value - a.value);

  const latestProfits = records
    .map((r) => ({
      name: r.name,
      profit: r.profit,
      profitRate: r.profitRate,
    }))
    .sort((a, b) => b.profit - a.profit);

  return {
    kpi: { totalValue, totalProfit, profitRate, baseDate },
    allocation,
    latestProfits,
  };
}

/**
 * 月次ベースのレスポンスに latest_pnl を重ねる。
 *
 * @param base - 従来どおり組み立てたレスポンス（asOf 以外）
 * @param latestMonthlyDate - monthly_pnl の最新 date（"YYYY-MM-末"）
 * @param latestRows - latest_pnl の全行
 * @param purchases - purchase_history の全行（当月買付の transactions 用）
 */
export function applyLatestSnapshot(
  base: Omit<DashboardPayload, "asOf">,
  latestMonthlyDate: string,
  latestRows: LatestPnlRow[],
  purchases: PurchaseRow[],
): DashboardPayload {
  if (latestRows.length === 0) return { ...base, asOf: null };

  const asOf = latestRows.reduce(
    (max, r) => (r.priceDate > max ? r.priceDate : max),
    latestRows[0].priceDate,
  );
  const asOfYM = parseYearMonth(asOf);
  if (cmpYearMonth(asOfYM, parseYearMonth(latestMonthlyDate)) <= 0) {
    return { ...base, asOf: null };
  }

  const monthLabel = toMonthLabel(asOfYM);
  const latestByCode = new Map(latestRows.map((r) => [r.code, r]));
  const currentMonthPurchases = purchases
    .filter((p) => {
      const ym = parseYearMonth(p.purchasedAt);
      return cmpYearMonth(ym, asOfYM) === 0;
    })
    .sort((a, b) => a.seq - b.seq);

  const stocks = base.stocks.map((s) => {
    const row = latestByCode.get(s.code);
    if (!row) return s;

    const isForeign = row.currency !== "JPY";
    const currentPrice = isForeign
      ? (row.currentPriceForeign ?? row.currentPrice)
      : row.currentPrice;
    const acquiredPrice = isForeign
      ? (row.acquiredPriceForeign ?? row.acquiredPrice)
      : row.acquiredPrice;
    const newIdx = s.monthLabels.length;

    const newTransactions = currentMonthPurchases
      .filter((p) => p.code === s.code)
      .map((p) => ({
        month: newIdx,
        action: "buy" as const,
        quantity: p.shares,
        price: isForeign ? (p.priceForeign ?? 0) : p.price,
      }));

    return {
      ...s,
      quantity: row.shares,
      currentPrice,
      previousMonthPrice: s.currentPrice,
      monthlyChangeRate:
        row.monthStartPriceNative != null && row.monthStartPriceNative !== 0
          ? (currentPrice / row.monthStartPriceNative - 1) * 100
          : null,
      acquiredPrice,
      priceHistory: [...s.priceHistory, currentPrice],
      acquiredAvgHistory: [...s.acquiredAvgHistory, acquiredPrice],
      monthLabels: [...s.monthLabels, monthLabel],
      transactions: [...s.transactions, ...newTransactions],
      value: row.value,
      profit: row.profit,
      profitRate: row.profitRate,
    };
  });

  const totalValue = latestRows.reduce((sum, r) => sum + r.value, 0);
  const totalProfit = latestRows.reduce((sum, r) => sum + r.profit, 0);

  const usdRow = latestRows.find(
    (r) => r.currency === "USD" && r.exchangeRate != null,
  );

  return {
    ...summarizeRecords(latestRows, base.kpi.baseDate),
    stocks,
    totalHistory: {
      months: [...base.totalHistory.months, monthLabel],
      assetValues: [...base.totalHistory.assetValues, totalValue],
      plValues: [...base.totalHistory.plValues, totalProfit],
    },
    usdJpy: usdRow?.exchangeRate ?? base.usdJpy,
    asOf,
  };
}
