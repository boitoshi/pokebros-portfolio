import { Fragment, useState } from "react";
import { formatJpy, formatNative } from "@/lib/formatters";
import type { PortfolioItem } from "@/types";

interface Props {
  items: PortfolioItem[];
}

const COLUMN_COUNT = 6;
// モバイルでは「通貨」「取得日」列を非表示にするため列数が変わる
const MOBILE_COLUMN_COUNT = 4;

export function HoldingsTable({ items }: Props) {
  // 単一展開方式: 展開中の銘柄コードのみ保持
  const [expandedCode, setExpandedCode] = useState<string | null>(null);

  const toggleRow = (code: string) => {
    setExpandedCode((prev) => (prev === code ? null : code));
  };

  return (
    <div className="overflow-x-auto bg-white rounded-lg border border-gray-200">
      <table className="min-w-full text-sm">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            {/* 通貨・取得日はモバイルでは列を出さず、銘柄名の下に併記する（横スクロール回避） */}
            {(
              [
                ["銘柄コード", ""],
                ["銘柄名", ""],
                ["通貨", "hidden sm:table-cell"],
                ["取得日", "hidden sm:table-cell"],
                ["取得単価（円）", ""],
                ["保有株数", ""],
              ] as [string, string][]
            ).map(([h, cls]) => (
              <th
                key={h}
                className={`px-2 sm:px-4 py-3 text-left font-medium text-gray-600 ${cls}`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {items.map((item, i) => {
            const isExpanded = expandedCode === item.code;
            return (
              <Fragment key={item.code || i}>
                <tr
                  className="hover:bg-gray-50 cursor-pointer"
                  onClick={() => toggleRow(item.code)}
                >
                  <td className="px-2 sm:px-4 py-3 font-mono text-gray-900 whitespace-nowrap">
                    <span
                      className="inline-block mr-1 text-gray-400 transition-transform"
                      style={{
                        transform: isExpanded ? "rotate(90deg)" : "none",
                      }}
                    >
                      ▸
                    </span>
                    {item.code}
                  </td>
                  <td className="px-2 sm:px-4 py-3 text-gray-900">
                    {item.name}
                    {/* モバイルのみ: 非表示にした通貨・取得日をここに併記 */}
                    <span className="block text-xs text-gray-500 sm:hidden">
                      {item.currency}・{item.acquiredDate}
                    </span>
                  </td>
                  <td className="hidden sm:table-cell px-4 py-3 text-gray-600">
                    {item.currency}
                  </td>
                  <td className="hidden sm:table-cell px-4 py-3 text-gray-600 whitespace-nowrap">
                    {item.acquiredDate}
                  </td>
                  <td className="px-2 sm:px-4 py-3 text-right text-gray-900 whitespace-nowrap">
                    {formatJpy(item.acquiredPriceJpy)}
                  </td>
                  <td className="px-2 sm:px-4 py-3 text-right text-gray-900 whitespace-nowrap">
                    {item.shares.toLocaleString()}
                  </td>
                </tr>
                {isExpanded && (
                  <tr className="bg-gray-50">
                    {/* colSpan は表示中の列数に合わせる（モバイル4列 / sm以上6列） */}
                    <td
                      colSpan={MOBILE_COLUMN_COUNT}
                      className="sm:hidden px-2 py-3"
                    >
                      {/* 収まらない環境向けの保険としてスクロール可能にしておく */}
                      <div className="overflow-x-auto">
                        <PurchaseHistoryTable purchases={item.purchases} />
                      </div>
                    </td>
                    <td
                      colSpan={COLUMN_COUNT}
                      className="hidden sm:table-cell px-4 py-3"
                    >
                      <div className="overflow-x-auto">
                        <PurchaseHistoryTable purchases={item.purchases} />
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** 買付履歴ミニテーブル */
function PurchaseHistoryTable({
  purchases,
}: {
  purchases: PortfolioItem["purchases"];
}) {
  if (purchases.length === 0) {
    return <p className="text-xs text-gray-500">買付履歴がありません</p>;
  }

  return (
    <table className="min-w-full text-xs">
      <thead>
        <tr className="text-gray-500">
          <th className="px-2 py-1 text-left font-medium">回</th>
          <th className="px-2 py-1 text-left font-medium">取得日</th>
          <th className="px-2 py-1 text-right font-medium">株数</th>
          <th className="px-2 py-1 text-right font-medium">取得単価</th>
          <th className="px-2 py-1 text-right font-medium">円換算額</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100">
        {purchases.map((p) => {
          const isForeign = p.priceForeign != null;
          const jpyAmount =
            p.priceForeign == null
              ? p.price * p.shares
              : p.exchangeRate != null
                ? p.priceForeign * p.exchangeRate * p.shares
                : null;

          return (
            <tr key={p.seq}>
              <td className="px-2 py-1 text-gray-700">{p.seq}</td>
              <td className="px-2 py-1 text-gray-700 whitespace-nowrap">
                {p.purchasedAt}
              </td>
              <td className="px-2 py-1 text-right text-gray-700">
                {p.shares.toLocaleString()}
              </td>
              <td className="px-2 py-1 text-right text-gray-900">
                {isForeign ? (
                  <>
                    {formatNative(p.priceForeign as number, "USD")}
                    {p.exchangeRate != null && (
                      <span className="block text-[10px] text-gray-400">
                        @為替 ¥{p.exchangeRate.toFixed(2)}
                      </span>
                    )}
                  </>
                ) : (
                  formatJpy(p.price)
                )}
              </td>
              <td className="px-2 py-1 text-right text-gray-900">
                {jpyAmount != null ? formatJpy(jpyAmount) : "—"}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
