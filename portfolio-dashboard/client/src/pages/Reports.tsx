import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchApi } from "@/lib/api";
import type { ReportListResponse } from "@/types";

export default function Reports() {
  const { data, isLoading } = useQuery({
    queryKey: ["reports"],
    queryFn: () => fetchApi<ReportListResponse>("/api/reports"),
  });
  if (isLoading || !data) return <p className="text-gray-500">読み込み中...</p>;
  const hasBlogLinks = data.reports.some((r) => r.wpUrl !== null);
  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">月次レポート</h1>
      {hasBlogLinks && (
        // 過去記事は執筆時点の手計算・為替で書いているため、アプリの数値と一致しない月がある
        <p className="text-xs text-gray-500 mb-4">
          「ブログ記事」は各月に公開した記事です。記事の数値は執筆時点のもので、
          このページの数値（月末の終値・ECB
          参照レートで再計算）と異なる場合があります。
        </p>
      )}
      {data.reports.length === 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 p-8 text-center text-gray-500">
          レポートがありません。月次バッチ（collect_and_publish）実行後に表示されます。
        </div>
      ) : (
        <ul className="space-y-2">
          {/* Link（<a>）の中に <a> を入れ子にできないため、リンク2つを兄弟要素として並べる */}
          {data.reports.map((r) => (
            <li
              key={`${r.year}-${r.month}`}
              className="flex items-center gap-3 bg-white rounded-lg border border-gray-200 px-5 py-4 hover:border-blue-400 hover:bg-blue-50 transition-colors"
            >
              <Link
                to={`/reports/${r.year}/${r.month}`}
                className="text-blue-600 font-medium flex-1"
              >
                {r.label}
              </Link>
              {r.wpUrl !== null && (
                <a
                  href={r.wpUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="記事の数値は執筆時点のもので、このページと異なる場合があります"
                  className="text-gray-400 text-sm hover:text-blue-500 hover:underline shrink-0"
                >
                  ブログ記事 ↗
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
