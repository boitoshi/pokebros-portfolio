// KPI サマリー
export interface KpiSummary {
  totalValue: number; // 評価額合計（円）
  totalProfit: number; // 損益合計（円）
  profitRate: number; // 損益率（%）
  baseDate: string; // 基準日（YYYY-MM-DD）
}

// ダッシュボード: 構成比（DonutChart 用）
export interface AllocationItem {
  name: string; // 銘柄名
  value: number; // 評価額（円）
  percentage: number; // 構成比（%）
}

// ダッシュボード: 最新月損益（BarChart 用）
export interface LatestProfitItem {
  name: string; // 銘柄名
  profit: number; // 損益（円）
  profitRate: number; // 損益率（%）
}

// ダッシュボード レスポンス
export interface DashboardResponse {
  kpi: KpiSummary;
  allocation: AllocationItem[];
  latestProfits: LatestProfitItem[];
  stocks?: DashboardStock[];
  totalHistory?: TotalHistory;
  usdJpy?: number;
  asOf?: string | null; // 最新スナップショットの最終取引日（YYYY-MM-DD）。月次表示なら null
}

// 買付履歴 1 件（purchase_history テーブル由来）
export interface PurchaseRecord {
  seq: number; // 買付回次
  shares: number; // 買付株数
  price: number; // 取得単価（円。外国株は 0 の場合あり）
  priceForeign: number | null; // 取得単価（外貨）
  exchangeRate: number | null; // 取得時為替レート
  purchasedAt: string; // 買付日
}

// ポートフォリオ保有銘柄
export interface PortfolioItem {
  code: string; // 銘柄コード
  name: string; // 銘柄名
  acquiredDate: string; // 取得日
  acquiredPriceJpy: number; // 取得単価（円）
  acquiredPriceForeign: number | null; // 取得単価（外貨）
  acquiredExchangeRate: number | null; // 取得時為替レート
  shares: number; // 保有株数
  totalCost: number; // 取得額合計
  currency: string; // 通貨コード（JPY/USD/HKD）
  isForeign: boolean; // 外国株フラグ
  purchases: PurchaseRecord[]; // 買付履歴（回ごとの明細）
}

// ポートフォリオ レスポンス
export interface PortfolioResponse {
  items: PortfolioItem[];
}

// 月次損益データポイント
export interface MonthlyProfitPoint {
  date: string; // 日付
  code: string; // 銘柄コード
  name: string; // 銘柄名
  profit: number; // 損益（円）
  value: number; // 評価額（円）
  profitRate: number; // 損益率（%）
  currency: string; // 通貨コード（JPY/USD/HKD）
  stockProfit: number; // 株価損益（円）
  fxProfit: number; // 為替損益（円）
}

// 銘柄セレクタの選択肢（コード＋銘柄名）
export interface SymbolOption {
  code: string;
  name: string;
}

// 損益推移 レスポンス
export interface HistoryResponse {
  data: MonthlyProfitPoint[];
  symbols: SymbolOption[]; // フィルター選択肢（銘柄コード＋銘柄名）
}

// 為替レートデータポイント
export interface CurrencyRatePoint {
  date: string; // 取得日
  pair: string; // 通貨ペア（例: USD/JPY）
  rate: number; // レート
  changeRate: number | null; // 変動率（%）
  high: number | null; // 最高値
  low: number | null; // 最安値
}

// 為替レート レスポンス
export interface CurrencyResponse {
  data: CurrencyRatePoint[];
  latestRate: number; // 最新レート
}

// 配当・分配金データポイント
export interface DividendItem {
  date: string; // 受取日
  code: string; // 銘柄コード
  name: string; // 銘柄名
  dividendForeign: number | null; // 1株配当（外貨）。日本株は null
  shares: number; // 保有株数
  totalForeign: number | null; // 配当合計（外貨）。日本株は null
  currency: string; // 通貨コード（JPY/USD/HKD）
  exchangeRate: number | null; // 為替レート。日本株は null
  totalJpy: number; // 配当合計（円）
  color: string; // 銘柄カラー（stock_meta 由来）
}

// 配当・分配金 レスポンス
export interface DividendResponse {
  data: DividendItem[];
  totalJpy: number; // 受取配当合計（円）
}

// 月次レポート一覧アイテム
export interface ReportItem {
  year: number;
  month: number;
  label: string; // 例: "2026年1月"
  wpUrl: string | null; // WordPress 記事URL。未投稿は null
}

// 月次レポート一覧 レスポンス
export interface ReportListResponse {
  reports: ReportItem[];
}

// 月次レポート内容 レスポンス
export interface ReportContentResponse {
  year: number;
  month: number;
  content: string; // Markdown テキスト
}

// ベンチマーク比較データポイント
export interface BenchmarkPoint {
  date: string;
  portfolio: number;
  nikkei225: number | null;
  sp500: number | null;
}

// ベンチマーク比較 レスポンス
export interface BenchmarkResponse {
  data: BenchmarkPoint[];
}

// 通貨エクスポージャーアイテム
export interface ExposureItem {
  currency: string;
  value: number;
  cost: number;
  profit: number;
  profitRate: number;
  percentage: number;
}

// 通貨エクスポージャー レスポンス
export interface ExposureResponse {
  items: ExposureItem[];
}

// ダッシュボード用トランザクション
export interface DashboardTransaction {
  /** monthLabels のインデックス */
  month: number;
  action: "buy" | "sell";
  quantity: number;
  /** ネイティブ通貨単価 */
  price: number;
}

// ダッシュボード拡張: 銘柄データ
export interface DashboardStock {
  code: string;
  name: string;
  ticker: string;
  market: string;
  currency: "JPY" | "USD";
  quantity: number;
  /** ネイティブ通貨の月末価格 */
  currentPrice: number;
  /** 前月のネイティブ価格（前月データなければ null） */
  previousMonthPrice: number | null;
  /** 月間変動率（%）。データなければ null */
  monthlyChangeRate: number | null;
  color: string;
  /** 移動平均取得単価（ネイティブ） */
  acquiredPrice: number;
  /** 保有開始月〜対象月のネイティブ月末価格 */
  priceHistory: number[];
  /** priceHistory と同長の stepped line 用移動平均取得単価 */
  acquiredAvgHistory: number[];
  /** "YYYY/M" 形式。priceHistory と同長 */
  monthLabels: string[];
  transactions: DashboardTransaction[];
  /** AI コメント。未設定は null */
  comment: string | null;
  /** 円建て評価額 */
  value: number;
  /** 円建て損益 */
  profit: number;
  /** 損益率（%） */
  profitRate: number;
}

// ダッシュボード拡張: 資産推移履歴
export interface TotalHistory {
  /** "YYYY/M" 形式 */
  months: string[];
  /** 全銘柄合計の月次評価額（円） */
  assetValues: number[];
  /** 全銘柄合計の月次損益（円） */
  plValues: number[];
}

// 月次レポートデータレスポンス（新デザイン用）
export interface ReportDataResponse {
  meta: {
    year: number;
    month: number;
    exchangeRate: number; // USD/JPY レート
    reportDate: string; // "YYYY年M月末" 形式
  };
  stocks: DashboardStock[];
  totalHistory: TotalHistory;
  intro: string | null;
  summary: string | null;
}
