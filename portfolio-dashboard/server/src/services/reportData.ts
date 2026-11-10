/**
 * レポートデータ構築サービス
 *
 * buildReportData() はチャート・コレクター・クライアントが共有する
 * 正規のデータ形状を返す。月次レポート API と dashboard 拡張から呼ばれる。
 */

import { and, asc, desc, eq, like, lte } from "drizzle-orm";
import type { BetterSQLite3Database } from "drizzle-orm/better-sqlite3";
import type * as schema from "../db/schema.js";
import {
  aiComments,
  exchangeRates,
  monthlyPnl,
  monthlyPrices,
  purchaseHistory,
  stockMeta,
} from "../db/schema.js";

// DB 型エイリアス
type DB = BetterSQLite3Database<typeof schema>;

// ────────────────────────────────────────────────────────────
// 日付ユーティリティ
// ────────────────────────────────────────────────────────────

/** "YYYY-MM-末" → { year, month } */
function parsePnlDate(date: string): { year: number; month: number } {
  const [y, m] = date.split("-");
  return { year: parseInt(y, 10), month: parseInt(m, 10) };
}

/** "YYYY-MM-DD" → { year, month } */
function parseIsoDate(date: string): { year: number; month: number } {
  const [y, m] = date.split("-");
  return { year: parseInt(y, 10), month: parseInt(m, 10) };
}

/** { year, month } → "YYYY/M" 形式のラベル */
function toMonthLabel(ym: { year: number; month: number }): string {
  return `${ym.year}/${ym.month}`;
}

/** { year, month } → "YYYY-MM-末" 形式 */
function toPnlDate(ym: { year: number; month: number }): string {
  return `${ym.year}-${String(ym.month).padStart(2, "0")}-末`;
}

/** { year, month } の大小比較（負: a < b, 0: 同等, 正: a > b） */
function cmpYearMonth(
  a: { year: number; month: number },
  b: { year: number; month: number },
): number {
  if (a.year !== b.year) return a.year - b.year;
  return a.month - b.month;
}

/** 前月を返す */
function prevMonth(ym: { year: number; month: number }): {
  year: number;
  month: number;
} {
  if (ym.month === 1) return { year: ym.year - 1, month: 12 };
  return { year: ym.year, month: ym.month - 1 };
}

// ────────────────────────────────────────────────────────────
// 返り値の型定義
// ────────────────────────────────────────────────────────────

export interface Transaction {
  /** monthLabels のインデックス */
  month: number;
  action: "buy" | "sell";
  quantity: number;
  /** ネイティブ通貨単価 */
  price: number;
}

export interface StockReportData {
  code: string;
  name: string;
  /** コードと同値（このシステムでは code=ticker） */
  ticker: string;
  market: string;
  currency: "JPY" | "USD";
  /** 対象月末時点の保有株数（purchase_history 集計） */
  quantity: number;
  /** ネイティブ通貨の月末価格 */
  currentPrice: number;
  /** 前月のネイティブ価格（前月データがなければ null） */
  previousMonthPrice: number | null;
  /** monthly_prices.change_rate（対象月）。データなければ null */
  monthlyChangeRate: number | null;
  color: string;
  /** 対象月末時点の移動平均取得単価（ネイティブ） */
  acquiredPrice: number;
  /** 保有開始月〜対象月のネイティブ月末価格 */
  priceHistory: number[];
  /**
   * priceHistory と同長の stepped line 用移動平均取得単価配列。
   * 買付があった月にのみ値が変わり、それ以降は同じ値が続く。
   *
   * 計算式（buy のみ対応）:
   *   cumCost = Σ(nativePrice × shares)  for purchases ≤ current month
   *   cumShares = Σ(shares)              for purchases ≤ current month
   *   avg = cumCost / cumShares
   *
   * sell が追加された場合:
   *   cumCost -= sellPrice × sellShares
   *   cumShares -= sellShares
   */
  acquiredAvgHistory: number[];
  /** "YYYY/M" 形式。priceHistory と同長 */
  monthLabels: string[];
  transactions: Transaction[];
  /** ai_comments (kind='stock') の content。未設定は null */
  comment: string | null;
  /** 円建て評価額（monthly_pnl から） */
  value: number;
  /** 円建て損益（monthly_pnl から） */
  profit: number;
  /** 損益率（monthly_pnl から） */
  profitRate: number;
}

export interface ReportData {
  meta: {
    year: number;
    month: number;
    /** USD/JPY レート（対象月。なければ最新） */
    exchangeRate: number;
    /** "YYYY年M月末" 形式 */
    reportDate: string;
  };
  stocks: StockReportData[];
  totalHistory: {
    /** "YYYY/M" 形式 */
    months: string[];
    /** 全銘柄合計の月次評価額 */
    assetValues: number[];
    /** 全銘柄合計の月次損益 */
    plValues: number[];
  };
  /** ai_comments (kind='intro') の content。未設定は null */
  intro: string | null;
  /** ai_comments (kind='summary') の content。未設定は null */
  summary: string | null;
}

// ────────────────────────────────────────────────────────────
// 色解決ユーティリティ（stock_meta 未登録銘柄へのフォールバック割当）
// ────────────────────────────────────────────────────────────

/** stock_meta 未登録銘柄に割り当てるフォールバックカラー */
export const FALLBACK_COLORS = ["#FF6F00", "#7B1FA2"];

/**
 * 銘柄コードの表示色を解決する。
 * stock_meta に登録があればその色、なければ未登録銘柄の出現順に
 * FALLBACK_COLORS を割り当てる（buildReportData と同一の割当ロジック）。
 *
 * @param codes - 色を解決したい銘柄コードの並び（出現順。重複可、重複分は初出時の色を使い回す）
 * @param metaMap - stock_meta の code → { color } マップ
 * @returns code → color のマップ
 */
export function resolveStockColors(
  codes: string[],
  metaMap: Map<string, { color: string }>,
): Map<string, string> {
  let fallbackIdx = 0;
  const colorMap = new Map<string, string>();
  for (const code of codes) {
    if (colorMap.has(code)) continue;
    const meta = metaMap.get(code);
    colorMap.set(
      code,
      meta?.color ?? FALLBACK_COLORS[fallbackIdx++ % FALLBACK_COLORS.length],
    );
  }
  return colorMap;
}

// ────────────────────────────────────────────────────────────
// メイン関数
// ────────────────────────────────────────────────────────────

/**
 * 月次レポートデータを構築する。
 *
 * @param db - Drizzle DB インスタンス（テスト時はメモリ DB を渡す）
 * @param targetDate - "YYYY-MM-末" 形式。省略時は monthly_pnl の最新 date を使用
 * @returns ReportData | null  対象月のデータが存在しない場合は null
 */
export function buildReportData(
  db: DB,
  targetDate?: string,
): ReportData | null {
  // ── 1. 対象月の決定 ──────────────────────────────────────────
  const resolvedDate =
    targetDate ??
    db
      .select({ date: monthlyPnl.date })
      .from(monthlyPnl)
      .orderBy(desc(monthlyPnl.date))
      .limit(1)
      .get()?.date;

  if (!resolvedDate) return null;

  // 対象月の monthly_pnl が存在しない場合は null
  const targetRecords = db
    .select()
    .from(monthlyPnl)
    .where(eq(monthlyPnl.date, resolvedDate))
    .all();
  if (targetRecords.length === 0) return null;

  const targetYM = parsePnlDate(resolvedDate);
  const targetMonthStr = String(targetYM.month).padStart(2, "0");
  const targetYearMonthPrefix = `${targetYM.year}-${targetMonthStr}`;

  // ── 2. stock_meta の取得 ──────────────────────────────────────
  const metaRows = db.select().from(stockMeta).all();
  const metaMap = new Map(metaRows.map((r) => [r.code, r]));

  // 色の解決（stock_meta 未登録銘柄は出現順にフォールバックカラーを割当）
  const colorMap = resolveStockColors(
    targetRecords.map((r) => r.code),
    metaMap,
  );

  // ── 3. USD/JPY レートの取得 ────────────────────────────────────
  // 対象月のレートを優先。なければ最新を使用
  const rateRow =
    db
      .select({ rate: exchangeRates.rate })
      .from(exchangeRates)
      .where(
        and(
          eq(exchangeRates.pair, "USD/JPY"),
          like(exchangeRates.date, `${targetYearMonthPrefix}%`),
        ),
      )
      .orderBy(desc(exchangeRates.date))
      .limit(1)
      .get() ??
    db
      .select({ rate: exchangeRates.rate })
      .from(exchangeRates)
      .where(eq(exchangeRates.pair, "USD/JPY"))
      .orderBy(desc(exchangeRates.date))
      .limit(1)
      .get();

  const usdJpy = rateRow?.rate ?? 0;

  // ── 4. 全 monthly_pnl の集計（totalHistory 用） ───────────────
  const allPnl = db
    .select()
    .from(monthlyPnl)
    .orderBy(asc(monthlyPnl.date))
    .all();

  // 日付ごとに value / profit を集計
  const totalByDate = new Map<string, { assetValue: number; pl: number }>();
  for (const r of allPnl) {
    const existing = totalByDate.get(r.date) ?? { assetValue: 0, pl: 0 };
    existing.assetValue += r.value;
    existing.pl += r.profit;
    totalByDate.set(r.date, existing);
  }

  // 日付キーで昇順に並べる（"YYYY-MM-末" なので文字列比較で月順になる）
  const sortedTotals = [...totalByDate.entries()].sort(([a], [b]) =>
    a < b ? -1 : a > b ? 1 : 0,
  );
  const totalHistory = {
    months: sortedTotals.map(([d]) => toMonthLabel(parsePnlDate(d))),
    assetValues: sortedTotals.map(([, t]) => t.assetValue),
    plValues: sortedTotals.map(([, t]) => t.pl),
  };

  // ── 5. 各銘柄の詳細データ構築 ────────────────────────────────
  const stocks: StockReportData[] = [];

  for (const pnlRow of targetRecords) {
    const code = pnlRow.code;
    const isForeign = pnlRow.currency !== "JPY";
    const meta = metaMap.get(code);

    // resolveStockColors に全銘柄を渡しているので必ず見つかる（型を満たすための既定値）
    const color = colorMap.get(code) ?? FALLBACK_COLORS[0];
    const market = meta?.market ?? "";

    // ── 5a. 全期間の monthly_pnl 履歴（保有開始月〜対象月） ────
    // purchase_history の最古レコードで保有開始月を特定
    const purchases = db
      .select()
      .from(purchaseHistory)
      .where(eq(purchaseHistory.code, code))
      .orderBy(asc(purchaseHistory.seq))
      .all();

    // 保有開始月を特定（最古の purchased_at から）
    const firstPurchase = purchases[0];
    const firstPurchaseYM = firstPurchase
      ? parseIsoDate(firstPurchase.purchasedAt)
      : targetYM;

    // monthly_pnl を保有開始月から対象月まで取得
    const pnlHistory = db
      .select()
      .from(monthlyPnl)
      .where(and(eq(monthlyPnl.code, code), lte(monthlyPnl.date, resolvedDate)))
      .orderBy(asc(monthlyPnl.date))
      .all()
      .filter((r) => {
        // 保有開始月より前のレコードは除外
        return cmpYearMonth(parsePnlDate(r.date), firstPurchaseYM) >= 0;
      });

    const monthLabels = pnlHistory.map((r) =>
      toMonthLabel(parsePnlDate(r.date)),
    );

    // ネイティブ通貨の月末価格配列
    const priceHistory = pnlHistory.map((r) =>
      isForeign ? (r.currentPriceForeign ?? r.currentPrice) : r.currentPrice,
    );

    // ── 5b. 移動平均取得単価の計算（stepped line） ──────────────
    // 買付のみ対応。sell が追加された場合は以下の式で計算する:
    //   累計コスト -= sellNativePrice × sellShares
    //   累計株数 -= sellShares
    let cumCost = 0;
    let cumShares = 0;
    let purchaseIdx = 0;

    // 購入履歴を時系列昇順にソート（seq は購入日順のはずだが念のため）
    const sortedPurchases = [...purchases].sort((a, b) => {
      const da = parseIsoDate(a.purchasedAt);
      const db_ = parseIsoDate(b.purchasedAt);
      const diff = cmpYearMonth(da, db_);
      return diff !== 0 ? diff : a.seq - b.seq;
    });

    const acquiredAvgHistory: number[] = [];

    for (const r of pnlHistory) {
      const monthYM = parsePnlDate(r.date);

      // この月までの購入を累積
      while (purchaseIdx < sortedPurchases.length) {
        const p = sortedPurchases[purchaseIdx];
        const pYM = parseIsoDate(p.purchasedAt);
        if (cmpYearMonth(pYM, monthYM) <= 0) {
          // USD 銘柄は price_foreign、JPY は price を使用
          const nativePrice = isForeign ? (p.priceForeign ?? 0) : p.price;
          cumCost += nativePrice * p.shares;
          cumShares += p.shares;
          purchaseIdx++;
        } else {
          break;
        }
      }

      acquiredAvgHistory.push(cumShares > 0 ? cumCost / cumShares : 0);
    }

    // 対象月末時点の移動平均取得単価（acquiredAvgHistory の最終値）
    const acquiredPrice =
      acquiredAvgHistory.length > 0
        ? acquiredAvgHistory[acquiredAvgHistory.length - 1]
        : 0;

    // ── 5c. 取引リスト（monthLabels のインデックス付き） ──────
    const transactions: Transaction[] = [];
    for (const p of sortedPurchases) {
      // 対象月より後の購入は除外
      const pYM = parseIsoDate(p.purchasedAt);
      if (cmpYearMonth(pYM, targetYM) > 0) continue;

      const purchaseLabel = toMonthLabel(pYM);
      const monthIdx = monthLabels.indexOf(purchaseLabel);
      if (monthIdx === -1) {
        // 該当月が monthLabels にない場合（データ欠落月）→ 翌月以降の最初の月を使用
        const fallback = monthLabels.findIndex((l) => {
          const [y, m] = l.split("/").map(Number);
          return cmpYearMonth({ year: y, month: m }, pYM) >= 0;
        });
        if (fallback === -1) continue;
        transactions.push({
          month: fallback,
          action: "buy",
          quantity: p.shares,
          price: isForeign ? (p.priceForeign ?? 0) : p.price,
        });
      } else {
        transactions.push({
          month: monthIdx,
          action: "buy",
          quantity: p.shares,
          price: isForeign ? (p.priceForeign ?? 0) : p.price,
        });
      }
    }

    // ── 5d. 前月のネイティブ価格 ────────────────────────────
    const prevMonthYM = prevMonth(targetYM);
    const prevPnlRow = db
      .select()
      .from(monthlyPnl)
      .where(
        and(
          eq(monthlyPnl.code, code),
          eq(monthlyPnl.date, toPnlDate(prevMonthYM)),
        ),
      )
      .limit(1)
      .get();

    const previousMonthPrice = prevPnlRow
      ? isForeign
        ? (prevPnlRow.currentPriceForeign ?? prevPnlRow.currentPrice)
        : prevPnlRow.currentPrice
      : null;

    // ── 5e. monthly_prices の月間変動率 ──────────────────────
    const priceRow = db
      .select({ changeRate: monthlyPrices.changeRate })
      .from(monthlyPrices)
      .where(
        and(
          eq(monthlyPrices.code, code),
          like(monthlyPrices.date, `${targetYearMonthPrefix}%`),
        ),
      )
      .limit(1)
      .get();

    const monthlyChangeRate = priceRow?.changeRate ?? null;

    // ── 5f. 保有株数（purchase_history から集計） ──────────────
    // 対象月末までの全購入を合計（売りは現状未対応）
    // 対象月末 = "YYYY-MM-末" → その月の翌月初日より前の日付
    const nextMonthFirstDay =
      targetYM.month < 12
        ? `${targetYM.year}-${String(targetYM.month + 1).padStart(2, "0")}-01`
        : `${targetYM.year + 1}-01-01`;

    const quantity = sortedPurchases
      .filter((p) => p.purchasedAt < nextMonthFirstDay)
      .reduce((sum, p) => sum + p.shares, 0);

    // ── 5g. AI コメント ───────────────────────────────────────
    const commentRow = db
      .select({ content: aiComments.content })
      .from(aiComments)
      .where(
        and(
          eq(aiComments.date, resolvedDate),
          eq(aiComments.code, code),
          eq(aiComments.kind, "stock"),
        ),
      )
      .limit(1)
      .get();

    stocks.push({
      code,
      name: pnlRow.name,
      ticker: code,
      market,
      currency: (isForeign ? "USD" : "JPY") as "JPY" | "USD",
      quantity,
      currentPrice: isForeign
        ? (pnlRow.currentPriceForeign ?? pnlRow.currentPrice)
        : pnlRow.currentPrice,
      previousMonthPrice,
      monthlyChangeRate,
      color,
      acquiredPrice,
      priceHistory,
      acquiredAvgHistory,
      monthLabels,
      transactions,
      comment: commentRow?.content ?? null,
      value: pnlRow.value,
      profit: pnlRow.profit,
      profitRate: pnlRow.profitRate,
    });
  }

  // ── 6. AI コメント（intro / summary） ────────────────────────
  const introRow = db
    .select({ content: aiComments.content })
    .from(aiComments)
    .where(
      and(
        eq(aiComments.date, resolvedDate),
        eq(aiComments.code, ""),
        eq(aiComments.kind, "intro"),
      ),
    )
    .limit(1)
    .get();

  const summaryRow = db
    .select({ content: aiComments.content })
    .from(aiComments)
    .where(
      and(
        eq(aiComments.date, resolvedDate),
        eq(aiComments.code, ""),
        eq(aiComments.kind, "summary"),
      ),
    )
    .limit(1)
    .get();

  return {
    meta: {
      year: targetYM.year,
      month: targetYM.month,
      exchangeRate: usdJpy,
      reportDate: `${targetYM.year}年${targetYM.month}月末`,
    },
    stocks,
    totalHistory,
    intro: introRow?.content ?? null,
    summary: summaryRow?.content ?? null,
  };
}
