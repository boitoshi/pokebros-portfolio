/** 配当・分配金 年別受取額チャート（銘柄別積み上げ棒グラフ）*/
import type React from "react";
import {
  Bar,
  BarChart,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DividendItem } from "@/types";

interface Props {
  data: DividendItem[];
}

/** 円表示（例: ¥1,234）*/
function fmtJpy(v: number): string {
  return `¥${Math.round(v).toLocaleString("ja-JP")}`;
}

/** DividendItem[] を「年 × 銘柄コード」の積み上げ棒グラフ用データに変換する */
function buildYearlyStack(data: DividendItem[]): {
  chartData: Record<string, number | string>[];
  codes: { code: string; name: string; color: string }[];
} {
  const yearMap = new Map<number, Record<string, number>>();
  const codeMap = new Map<string, { name: string; color: string }>();

  for (const item of data) {
    const year = Number(item.date.slice(0, 4));
    let yearEntry = yearMap.get(year);
    if (!yearEntry) {
      yearEntry = {};
      yearMap.set(year, yearEntry);
    }
    yearEntry[item.code] = (yearEntry[item.code] ?? 0) + item.totalJpy;
    if (!codeMap.has(item.code)) {
      codeMap.set(item.code, { name: item.name, color: item.color });
    }
  }

  const years = Array.from(yearMap.keys()).sort((a, b) => a - b);
  const chartData = years.map((year) => ({
    year: `${year}年`,
    ...yearMap.get(year),
  }));
  const codes = Array.from(codeMap.entries()).map(([code, v]) => ({
    code,
    name: v.name,
    color: v.color,
  }));

  return { chartData, codes };
}

export function DividendYearChart({ data }: Props): React.ReactElement {
  const { chartData, codes } = buildYearlyStack(data);
  const nameByCode = new Map(codes.map((c) => [c.code, c.name]));

  return (
    <div
      style={{
        background: "white",
        borderRadius: "14px",
        padding: "18px",
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
      }}
    >
      <p
        style={{
          fontSize: "10px",
          color: "#8c90a0",
          margin: "0 0 12px",
          fontWeight: 500,
        }}
      >
        年別受取額
      </p>
      {chartData.length === 0 ? (
        <p
          style={{
            fontSize: "12px",
            color: "#8c90a0",
            textAlign: "center",
            padding: "40px 0",
          }}
        >
          データがありません
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart
            data={chartData}
            margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
          >
            <XAxis
              dataKey="year"
              tick={{ fontSize: 9, fill: "#b0b4c3" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 9, fill: "#b0b4c3" }}
              axisLine={false}
              tickLine={false}
              tickFormatter={fmtJpy}
              width={64}
            />
            <Tooltip
              formatter={(value, name) => [
                typeof value === "number" ? fmtJpy(value) : String(value),
                nameByCode.get(String(name)) ?? String(name),
              ]}
              contentStyle={{ fontSize: "11px" }}
            />
            <Legend
              verticalAlign="bottom"
              height={28}
              formatter={(value: string) => nameByCode.get(value) ?? value}
              wrapperStyle={{ fontSize: "10px" }}
            />
            {codes.map((c) => (
              <Bar
                key={c.code}
                dataKey={c.code}
                stackId="year"
                fill={c.color}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
