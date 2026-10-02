/**
 * ダッシュボードページ
 * - data.stocks && data.totalHistory が存在: 新デザイン（B-4 Phase）
 * - 存在しない: 旧レイアウト（後方互換）
 */
import { useQuery } from "@tanstack/react-query";
import { AllocationChart } from "@/components/dashboard/AllocationChart";
import { AllocationTrendChart } from "@/components/dashboard/AllocationTrendChart";
import { AssetTrendChart } from "@/components/dashboard/AssetTrendChart";
import { CurrencyExposureTable } from "@/components/dashboard/CurrencyExposureTable";
import { GradientHeader } from "@/components/dashboard/GradientHeader";
import { KpiCards } from "@/components/dashboard/KpiCards";
import { LatestBarChart } from "@/components/dashboard/LatestBarChart";
import { StockCard } from "@/components/dashboard/StockCard";
import { SummaryCard } from "@/components/dashboard/SummaryCard";
import { fetchApi } from "@/lib/api";
import type {
  DashboardResponse,
  ExposureResponse,
  HistoryResponse,
} from "@/types";

/** kpi.baseDate ("2026-03-末") から { year, month } をパース */
function parseBaseDate(baseDate: string): { year: number; month: number } {
  const match = baseDate.match(/^(\d{4})-(\d{2})/);
  if (!match) return { year: 0, month: 0 };
  return { year: parseInt(match[1], 10), month: parseInt(match[2], 10) };
}

/** 旧レイアウト（後方互換）*/
function LegacyDashboard({
  data,
  history,
  exposure,
}: {
  data: DashboardResponse;
  history: HistoryResponse | undefined;
  exposure: ExposureResponse | undefined;
}) {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-2">
          ダッシュボード
        </h1>
        <p className="text-sm text-gray-500">基準日: {data.kpi.baseDate}</p>
      </div>
      <KpiCards kpi={data.kpi} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">構成比</h2>
          <AllocationChart data={data.allocation} />
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">
            最新月 損益
          </h2>
          <LatestBarChart data={data.latestProfits} />
        </div>
      </div>
      {history && (
        <div className="mt-6 bg-white rounded-lg border border-gray-200 p-6">
          <h2 className="text-sm font-medium text-gray-500 mb-4">
            評価額推移（銘柄別）
          </h2>
          <AllocationTrendChart data={history.data} />
        </div>
      )}
      {exposure && (
        <div className="mt-6 bg-white rounded-lg border border-gray-200 p-6">
          <h2 className="text-sm font-medium text-gray-500 mb-4">
            通貨別エクスポージャー（最新月）
          </h2>
          <CurrencyExposureTable items={exposure.items} />
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => fetchApi<DashboardResponse>("/api/dashboard"),
  });

  // 新データが存在するか（isLoading 中は false → 旧系クエリを一時的に抑制）
  const hasNewData = !isLoading && !!(data?.stocks && data?.totalHistory);

  // 旧レイアウト用クエリ（新データがある場合は発火しない）
  const { data: history } = useQuery({
    queryKey: ["history"],
    queryFn: () => fetchApi<HistoryResponse>("/api/history"),
    enabled: !hasNewData,
  });
  const { data: exposure } = useQuery({
    queryKey: ["exposure"],
    queryFn: () => fetchApi<ExposureResponse>("/api/exposure"),
    enabled: !hasNewData,
  });

  if (isLoading || !data) {
    return <p className="text-gray-500">読み込み中...</p>;
  }

  // 新デザイン
  if (hasNewData && data.stocks && data.totalHistory) {
    // 最新スナップショットがあればその年月を見出しに使う（月末固定にしない）
    const asOf = data.asOf ?? null;
    const { year, month } = parseBaseDate(asOf ?? data.kpi.baseDate);
    const usdJpy = data.usdJpy ?? 0;
    const stocks = data.stocks;
    const totalHistory = data.totalHistory;

    return (
      // AppLayout の main padding（px-4 sm:px-6 lg:px-8 py-8）を負マージンで打ち消し、
      // グラデーションヘッダーをコンテナ全幅まで広げる
      <div className="-mt-8 -mx-4 sm:-mx-6 lg:-mx-8">
        {/* グラデーションヘッダー（全幅） */}
        <GradientHeader year={year} month={month} usdJpy={usdJpy} asOf={asOf} />

        {/* メインコンテンツ */}
        <div
          style={{
            maxWidth: "1280px",
            margin: "0 auto",
            padding: "20px",
          }}
        >
          {/* 上段: サマリーカード＋資産推移チャート */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "340px 1fr",
              gap: "16px",
              marginBottom: "16px",
            }}
            className="max-[900px]:!grid-cols-1"
          >
            <SummaryCard
              stocks={stocks}
              totalValue={data.kpi.totalValue}
              totalProfit={data.kpi.totalProfit}
              totalProfitRate={data.kpi.profitRate}
            />
            <AssetTrendChart
              totalHistory={totalHistory}
              totalProfit={data.kpi.totalProfit}
            />
          </div>

          {/* 銘柄カードグリッド */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: "16px",
              marginBottom: "16px",
            }}
            className="max-[900px]:!grid-cols-1"
          >
            {stocks.map((stock) => (
              <StockCard
                key={stock.code}
                stock={stock}
                isLive={asOf !== null}
              />
            ))}
          </div>
        </div>
      </div>
    );
  }

  // 旧レイアウト（後方互換）
  return <LegacyDashboard data={data} history={history} exposure={exposure} />;
}
