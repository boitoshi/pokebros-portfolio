import type { MonthlyProfitPoint } from "@/types";

export const COLORS = [
  "#3b82f6",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#06b6d4",
];

/**
 * 折れ線にドット（節の丸）を表示するデータ点数の上限。
 * これを超えると点の間隔より丸の方が目立ち、線が読みづらくなるため非表示にする。
 * ホバー時の activeDot は点数に関わらず出るので、値は読める。
 */
export const DOT_VISIBLE_MAX_POINTS = 12;

/** データ点数からドットを表示すべきか判定する */
export function shouldShowDots(pointCount: number): boolean {
  return pointCount <= DOT_VISIBLE_MAX_POINTS;
}

/**
 * MonthlyProfitPoint[] を「日付 × 銘柄名」のピボット形式に変換する。
 * getValue で取り出す値フィールドを選択する。
 */
export function buildPivotData(
  data: MonthlyProfitPoint[],
  getValue: (d: MonthlyProfitPoint) => number,
): { chartData: Record<string, unknown>[]; names: string[] } {
  const dateSet = new Set<string>();
  const nameMap = new Map<string, string>(); // code -> name
  for (const d of data) {
    dateSet.add(d.date);
    nameMap.set(d.code, d.name);
  }
  const dates = Array.from(dateSet).sort((a, b) => a.localeCompare(b));
  const names = Array.from(nameMap.values());

  const pivotMap = new Map<string, Record<string, number>>();
  for (const d of data) {
    let row = pivotMap.get(d.date);
    if (!row) {
      row = {};
      pivotMap.set(d.date, row);
    }
    row[d.name] = getValue(d);
  }

  return {
    chartData: dates.map((date) => ({ date, ...pivotMap.get(date) })),
    names,
  };
}

/** フォールバックカラー（stock_meta 未登録銘柄用） */
export const FALLBACK_STOCK_COLORS = [
  "#E53935",
  "#1565C0",
  "#76B900",
  "#FF6F00",
  "#7B1FA2",
];
