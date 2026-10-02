/** 個別銘柄カード — 価格チャート・メトリクス・AI コメント */

import type React from "react";
import { useState } from "react";
import {
  formatNative,
  formatSignedPercent,
  formatSignedYen,
  plColor,
} from "@/lib/formatters";
import type { DashboardStock } from "@/types";
import type { Period } from "./PeriodToggle";
import { PeriodToggle } from "./PeriodToggle";
import { StockPriceChart } from "./StockPriceChart";

/** カード共通スタイル */
const cardStyle: React.CSSProperties = {
  background: "white",
  borderRadius: "14px",
  padding: "18px",
  boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
};

interface Props {
  stock: DashboardStock;
  /** 最新スナップショット表示中か（ラベルを「月初来」「前月末比」に切り替える） */
  isLive?: boolean;
}

/** 期間に応じてスライス件数を返す */
function sliceCount(period: Period, total: number): number {
  if (period === "3M") return Math.min(3, total);
  if (period === "6M") return Math.min(6, total);
  if (period === "1Y") return Math.min(12, total);
  return total; // ALL
}

export function StockCard({
  stock,
  isLive = false,
}: Props): React.ReactElement {
  const [period, setPeriod] = useState<Period>("6M");
  const [showComment, setShowComment] = useState(false);

  // 期間に応じてスライス
  const total = stock.priceHistory.length;
  const count = sliceCount(period, total);
  const prices = stock.priceHistory.slice(-count);
  const avgCosts = stock.acquiredAvgHistory.slice(-count);
  // dataKey には年付きの "YYYY/M" をそのまま使う（表示はチャート側でフォーマット）
  const labels = stock.monthLabels.slice(-count);

  // 前月比の計算
  const prevMonthRate: number | null =
    stock.previousMonthPrice !== null && stock.previousMonthPrice > 0
      ? ((stock.currentPrice - stock.previousMonthPrice) /
          stock.previousMonthPrice) *
        100
      : null;

  // 銘柄名の頭文字（イニシャルアイコン用）
  const initial = stock.name.charAt(0);

  // 損益背景色
  const profitBg = stock.profit >= 0 ? "#fef2f2" : "#eff6ff";

  return (
    <div style={cardStyle}>
      {/* ── ヘッダー ── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
          marginBottom: "12px",
        }}
      >
        {/* イニシャルアイコン */}
        <div
          style={{
            width: "34px",
            height: "34px",
            borderRadius: "10px",
            backgroundColor: stock.color,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <span style={{ fontSize: "14px", fontWeight: 800, color: "white" }}>
            {initial}
          </span>
        </div>

        {/* 銘柄名・ticker・market */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <p
            style={{
              fontSize: "14px",
              fontWeight: 700,
              color: "#1e2130",
              margin: 0,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {stock.name}
          </p>
          <p style={{ fontSize: "10px", color: "#8c90a0", margin: "1px 0 0" }}>
            {stock.ticker} ・ {stock.market}
          </p>
        </div>

        {/* 現在価格＆取得単価 */}
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <p
            style={{
              fontSize: "18px",
              fontWeight: 800,
              color: "#1e2130",
              margin: 0,
            }}
          >
            {formatNative(stock.currentPrice, stock.currency)}
          </p>
          <p style={{ fontSize: "10px", color: "#8c90a0", margin: "1px 0 0" }}>
            取得 {formatNative(stock.acquiredPrice, stock.currency)}
          </p>
        </div>
      </div>

      {/* ── メトリクス 3枠 ── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: "6px",
          marginBottom: "12px",
        }}
      >
        {/* 損益 */}
        <div
          style={{
            background: profitBg,
            borderRadius: "6px",
            padding: "6px 8px",
          }}
        >
          <p
            style={{
              fontSize: "9px",
              color: "#8c90a0",
              margin: "0 0 2px",
              fontWeight: 500,
            }}
          >
            損益
          </p>
          <p
            className={plColor(stock.profit)}
            style={{ fontSize: "12px", fontWeight: 700, margin: 0 }}
          >
            {formatSignedYen(stock.profit)}
          </p>
        </div>

        {/* 月間変動 */}
        <div
          style={{
            background: "#f6f7fa",
            borderRadius: "6px",
            padding: "6px 8px",
          }}
        >
          <p
            style={{
              fontSize: "9px",
              color: "#8c90a0",
              margin: "0 0 2px",
              fontWeight: 500,
            }}
          >
            {isLive ? "月初来" : "月間変動"}
          </p>
          <p
            className={
              stock.monthlyChangeRate !== null
                ? plColor(stock.monthlyChangeRate)
                : ""
            }
            style={{
              fontSize: "12px",
              fontWeight: 700,
              margin: 0,
              color: stock.monthlyChangeRate === null ? "#8c90a0" : undefined,
            }}
          >
            {stock.monthlyChangeRate !== null
              ? formatSignedPercent(stock.monthlyChangeRate)
              : "—"}
          </p>
        </div>

        {/* 前月比 */}
        <div
          style={{
            background: "#f6f7fa",
            borderRadius: "6px",
            padding: "6px 8px",
          }}
        >
          <p
            style={{
              fontSize: "9px",
              color: "#8c90a0",
              margin: "0 0 2px",
              fontWeight: 500,
            }}
          >
            {isLive ? "前月末比" : "前月比"}
          </p>
          <p
            className={prevMonthRate !== null ? plColor(prevMonthRate) : ""}
            style={{
              fontSize: "12px",
              fontWeight: 700,
              margin: 0,
              color: prevMonthRate === null ? "#8c90a0" : undefined,
            }}
          >
            {prevMonthRate !== null ? formatSignedPercent(prevMonthRate) : "—"}
          </p>
        </div>
      </div>

      {/* ── 期間切替＋チャート ── */}
      <div style={{ marginBottom: "10px" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            marginBottom: "6px",
          }}
        >
          <PeriodToggle
            period={period}
            onChange={setPeriod}
            color={stock.color}
          />
        </div>
        <StockPriceChart
          prices={prices}
          avgCosts={avgCosts}
          labels={labels}
          color={stock.color}
          currency={stock.currency}
          height={130}
        />
      </div>

      {/* ── AI コメントトグル ── */}
      {stock.comment !== null && (
        <div>
          <button
            type="button"
            onClick={() => setShowComment((prev) => !prev)}
            style={{
              background: "none",
              border: "none",
              padding: 0,
              cursor: "pointer",
              fontSize: "10px",
              color: "#8c90a0",
              display: "flex",
              alignItems: "center",
              gap: "4px",
            }}
          >
            <span
              style={{
                transform: showComment ? "rotate(90deg)" : "none",
                display: "inline-block",
                transition: "transform 0.15s",
              }}
            >
              ▸
            </span>
            {showComment ? "コメントを閉じる" : "コメントを見る"}
          </button>
          {showComment && (
            <p
              style={{
                fontSize: "12px",
                color: "#3a3f52",
                lineHeight: 1.7,
                margin: "8px 0 0",
              }}
            >
              {stock.comment}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
