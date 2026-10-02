/** グラデーションヘッダー — ポートフォリオタイトルと基準日を表示 */
import type React from "react";

interface Props {
  year: number;
  month: number;
  usdJpy: number;
  /** 最新スナップショットの最終取引日（YYYY-MM-DD）。月次表示なら null */
  asOf?: string | null;
}

/** 基準日表記: 最新スナップショットなら「YYYY年M月D日時点」、月次なら「YYYY年M月末」 */
function formatBaseLabel(
  year: number,
  month: number,
  asOf: string | null,
): string {
  const match = asOf?.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (match) {
    return `${Number(match[1])}年${Number(match[2])}月${Number(match[3])}日時点`;
  }
  return `${year}年${month}月末`;
}

export function GradientHeader({
  year,
  month,
  usdJpy,
  asOf = null,
}: Props): React.ReactElement {
  return (
    <div
      style={{
        background: "linear-gradient(135deg,#0d47a1,#1565c0 40%,#1976d2)",
        padding: "16px 28px",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "8px",
        }}
      >
        {/* 左: ラベル＋タイトル */}
        <div>
          <p
            style={{
              fontSize: "10px",
              color: "rgba(255,255,255,0.4)",
              fontWeight: 600,
              letterSpacing: "0.1em",
              margin: 0,
            }}
          >
            POKÉMON STOCK PORTFOLIO
          </p>
          <p
            style={{
              fontSize: "18px",
              fontWeight: 800,
              color: "white",
              margin: "2px 0 0",
            }}
          >
            {`【ポケモン投資】${year}年${month}月の状況`}
          </p>
        </div>
        {/* 右: 基準日＋為替レート */}
        <p
          style={{
            fontSize: "11px",
            color: "rgba(255,255,255,0.5)",
            margin: 0,
          }}
        >
          {`${formatBaseLabel(year, month, asOf)} ・ USD/JPY ¥${usdJpy.toFixed(2)}`}
        </p>
      </div>
    </div>
  );
}
