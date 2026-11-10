/** 銘柄ミニチャート — 株価ラインと移動平均取得単価（ステップ表示）*/
import type React from "react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { shouldShowDots } from "@/lib/chartUtils";
import { formatMonthFull, formatMonthTick } from "@/lib/formatters";

interface Props {
  prices: number[];
  avgCosts: number[];
  labels: string[];
  color: string;
  currency: "JPY" | "USD";
  height?: number;
}

/** ネイティブ価格を通貨に応じてフォーマット */
function fmtPrice(v: number, currency: "JPY" | "USD"): string {
  if (currency === "USD") {
    return `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  return `¥${Math.round(v).toLocaleString("ja-JP")}`;
}

/** カスタムツールチップ生成（closure で currency を取り込む）*/
function makeTooltipContent(currency: "JPY" | "USD") {
  return function TooltipContent({
    active,
    payload,
    label,
  }: {
    active?: boolean;
    payload?: ReadonlyArray<{
      dataKey?: unknown;
      value?: unknown;
    }>;
    label?: string | number;
  }): React.ReactElement | null {
    if (!active || !payload || payload.length === 0) return null;

    const priceEntry = payload.find((p) => p.dataKey === "price");
    const avgEntry = payload.find((p) => p.dataKey === "avg");
    const price = typeof priceEntry?.value === "number" ? priceEntry.value : 0;
    const avg = typeof avgEntry?.value === "number" ? avgEntry.value : 0;

    // 取得単価比の損益率
    const diffRate = avg > 0 ? ((price - avg) / avg) * 100 : null;
    const diffStr =
      diffRate !== null
        ? ` (${diffRate >= 0 ? "+" : ""}${diffRate.toFixed(2)}%)`
        : "";

    return (
      <div
        style={{
          background: "rgba(30,33,48,0.93)",
          borderRadius: "6px",
          padding: "6px 10px",
          fontSize: "11px",
          color: "white",
          lineHeight: 1.6,
        }}
      >
        <p style={{ margin: 0, color: "#b0b4c3", fontSize: "9px" }}>
          {formatMonthFull(String(label ?? ""))}
        </p>
        <p style={{ margin: 0 }}>
          株価: {fmtPrice(price, currency)}
          {diffStr}
        </p>
        {avg > 0 && (
          <p style={{ margin: 0, color: "#adb1be" }}>
            取得均: {fmtPrice(avg, currency)}
          </p>
        )}
      </div>
    );
  };
}

export function StockPriceChart({
  prices,
  avgCosts,
  labels,
  color,
  currency,
  height = 130,
}: Props): React.ReactElement {
  // Recharts 用データ配列
  const chartData = prices.map((price, i) => ({
    label: labels[i] ?? "",
    price,
    avg: avgCosts[i] ?? 0,
  }));

  // 点が密集すると丸が線を潰すため、期間が長いときはドットを出さない（ALL 表示など）
  const showDots = shouldShowDots(chartData.length);

  const TooltipContent = makeTooltipContent(currency);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart
        data={chartData}
        margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
      >
        <XAxis
          dataKey="label"
          tick={{ fontSize: 9, fill: "#b0b4c3" }}
          axisLine={false}
          tickLine={false}
          tickFormatter={formatMonthTick}
        />
        <YAxis
          tick={{ fontSize: 9, fill: "#b0b4c3" }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => fmtPrice(v, currency)}
          width={currency === "USD" ? 58 : 52}
        />
        <Tooltip content={TooltipContent} />
        {/* 移動平均取得単価（ステップ表示） */}
        <Line
          type="stepAfter"
          dataKey="avg"
          stroke="#adb1be"
          strokeDasharray="4 3"
          strokeWidth={1.5}
          dot={false}
          name="取得単価"
        />
        {/* 株価 */}
        <Line
          type="linear"
          dataKey="price"
          stroke={color}
          strokeWidth={2}
          dot={
            showDots
              ? { r: 3, fill: "white", stroke: color, strokeWidth: 1.5 }
              : false
          }
          activeDot={{ r: 4, fill: color }}
          name="株価"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
