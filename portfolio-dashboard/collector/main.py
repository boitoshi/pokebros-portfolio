#!/usr/bin/env python3
"""
データ収集メインスクリプト（SQLite版）
月次株価データ取得・SQLite保存・ブログ生成を実行
"""

import os
import sys
import time
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import yfinance as yf

from collectors.benchmark_collector import BenchmarkCollector
from collectors.db_writer import DbWriter
from collectors.dividend_import import aggregate, build_save_record, parse_rakuten_csv
from collectors.latest_snapshot import compute_latest_row, extract_latest_prices
from collectors.pnl_repair import repair_monthly_pnl
from collectors.report_generator import BlogReportGenerator
from collectors.sheets_sync import SheetsSync
from collectors.stock_collector import StockDataCollector
from collectors.stock_utils import is_foreign_stock
from collectors.template_engine import MarkdownTemplateEngine
from config.settings import (
    AI_COMMENTS_ENABLED,
    AI_COMMENTS_FORCE,
    BLOG_EMBED_ENABLED,
    CURRENCY_SETTINGS,
    DB_PATH,
    GOOGLE_APPLICATION_CREDENTIALS,
    SPREADSHEET_ID,
    WP_APP_PASSWORD,
    WP_CATEGORY_IDS,
    WP_PUBLISH_ENABLED,
    WP_URL,
    WP_USER,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def _get_next_month_date(year: int, month: int) -> str:
    """対象月の翌月1日 09:00 を ISO 形式で返す（12月は翌年1月1日）。

    Args:
        year: 対象年
        month: 対象月

    Returns:
        ISO 形式の日時文字列 "YYYY-MM-DDTHH:MM:SS"
    """
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1
    return f"{next_year:04d}-{next_month:02d}-01T09:00:00"


def _format_decimal(value: Decimal) -> str:
    """Decimal をカンマ区切りの表示用文字列に変換する（整数値は小数点を出さない）。"""
    if value == value.to_integral_value():
        return f"{int(value):,}"
    return f"{value.normalize():,}"


def _has_complete_ai_comments(existing: dict, report_data: dict) -> bool:
    """DB のコメントが intro と全保有銘柄分そろっているか判定する。"""
    if not existing.get(("", "intro")):
        return False
    expected_symbols = {
        str(holding.get("symbol") or holding.get("code"))
        for holding in report_data.get("holdings", [])
        if holding.get("symbol") or holding.get("code")
    }
    saved_symbols = {
        code
        for (code, kind), content in existing.items()
        if kind == "stock" and code and content
    }
    return expected_symbols <= saved_symbols


class PortfolioDataCollector:
    """ポートフォリオデータ収集メインクラス（SQLite版）"""

    def __init__(self) -> None:
        """初期化"""
        self.db_writer = DbWriter(DB_PATH)
        # SheetsSync は認証ファイルが存在しない環境でも起動できるよう
        # 初期化失敗を握りつぶす（--blog 等の DB 専用コマンドで有効）
        self.sheets_sync = None
        try:
            self.sheets_sync = SheetsSync(
                GOOGLE_APPLICATION_CREDENTIALS, SPREADSHEET_ID, DB_PATH
            )
        except Exception as e:
            print(f"  Sheets 同期: 無効（{e}）")
        self.stock_collector = StockDataCollector()
        self.benchmark_collector = BenchmarkCollector(self.db_writer)
        self.report_generator = BlogReportGenerator(self.db_writer)
        self.template_engine = MarkdownTemplateEngine(
            template_dir=os.path.join(os.path.dirname(__file__), "templates")
        )

        # オプショナル: AI コメント生成
        self.ai_comment = None
        if AI_COMMENTS_ENABLED:
            try:
                from collectors.ai_comment import AiCommentGenerator

                self.ai_comment = AiCommentGenerator()
                print("  AI コメント生成: 有効")
            except Exception as e:
                print(f"  AI コメント生成: 無効（{e}）")

        # オプショナル: WordPress 投稿
        self.wp_publisher = None
        if WP_PUBLISH_ENABLED and WP_URL:
            from collectors.wp_publisher import WpPublisher

            self.wp_publisher = WpPublisher(WP_URL, WP_USER, WP_APP_PASSWORD)
            print("  WordPress 投稿: 有効")

        # オプショナル: ブログ埋め込みエクスポート
        self.embed_generator = None
        if BLOG_EMBED_ENABLED:
            from collectors.embed_generator import EmbedGenerator

            self.embed_generator = EmbedGenerator(
                db=self.db_writer,
                output_dir=OUTPUT_DIR,
                template_dir=os.path.join(os.path.dirname(__file__), "templates"),
            )
            print("  ブログ埋め込みエクスポート: 有効")

    def collect_and_publish(self, year: int, month: int) -> bool:
        """月次バッチ: データ収集 → ブログ生成

        Args:
            year: 年
            month: 月

        Returns:
            成功/失敗
        """
        print(f"\n=== {year}年{month}月 月次バッチ開始 ===")

        # 1. Sheets からポートフォリオ同期
        print("\n[1/7] Sheets からポートフォリオ同期中...")
        if self.sheets_sync:
            synced = self.sheets_sync.sync_holdings()
            history_count = self.sheets_sync.sync_purchase_history()
            print(f"  同期完了: {synced}件（購入履歴: {history_count}件）")
        else:
            print("  スキップ（Sheets 認証無効）")

        # 2. yfinance で株価取得 → SQLite 保存
        print("\n[2/7] 株価データ収集中...")
        success = self.collect_monthly_data(year, month)
        if not success:
            print("❌ 株価データ収集に失敗しました")
            return False

        # 3. ベンチマーク（日経225/S&P500）取得 → SQLite 保存
        print("\n[3/7] ベンチマーク収集中...")
        self.benchmark_collector.collect(year, month)

        # 4. （廃止）チャート画像生成は行わない
        # 値動きグラフは埋め込み側の Chart.js に一本化した

        # 5. ブログ下書き生成
        print("\n[5/7] ブログ下書き生成中...")
        report_data = self.report_generator.get_monthly_report_data(year, month)
        output_path = None
        if report_data:
            markdown_text = self.template_engine.render("blog_template.md", report_data)
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            output_path = os.path.join(OUTPUT_DIR, f"blog_draft_{year}_{month:02d}.md")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(markdown_text)
            print(f"  ブログ下書きを生成しました: {output_path}")
        else:
            print("  レポートデータが取得できませんでした")

        # 6. AI コメント生成（オプショナル）
        print("\n[6/7] AI コメント生成中...")
        batch_target_date = f"{year}-{month:02d}-末"
        batch_ai_comments: dict = {}
        if self.ai_comment and report_data and output_path:
            if not AI_COMMENTS_FORCE:
                existing = self.db_writer.get_ai_comments(batch_target_date)
                if _has_complete_ai_comments(existing, report_data):
                    print("  AI コメント: DB から既存コメントを再利用します")
                    stock_coms: dict[str, str] = {}
                    for (code, kind), content in existing.items():
                        if kind == "stock" and code:
                            stock_coms[code] = content
                    batch_ai_comments = {
                        "stock_comments": stock_coms,
                        "summary": existing.get(("", "summary")),
                        "intro": existing.get(("", "intro")),
                    }
                else:
                    if existing:
                        print("  AI コメント: DB の不足分を再生成します")
                    batch_ai_comments = self.ai_comment.generate_all(report_data)
                    self._save_ai_comments(batch_target_date, batch_ai_comments)
            else:
                batch_ai_comments = self.ai_comment.generate_all(report_data)
                self._save_ai_comments(batch_target_date, batch_ai_comments)
            report_data["ai_comments"] = batch_ai_comments
            # AI コメント付きで再生成
            markdown = self.template_engine.render("blog_template.md", report_data)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(markdown)
            if any(
                (
                    batch_ai_comments.get("intro"),
                    batch_ai_comments.get("summary"),
                    batch_ai_comments.get("stock_comments"),
                )
            ):
                print("  AI コメント付きブログを再生成しました")
            else:
                print("  ⚠️ AI コメントなしでブログを再生成しました")
        else:
            print("  スキップ（AI コメント無効 or データなし）")

        # 6.5. 埋め込み HTML/JSON 生成（オプショナル）
        batch_fragment_html: str | None = None
        if self.embed_generator and report_data:
            print("\n  埋め込みコンテンツ生成中...")
            self.embed_generator.generate(year, month)
            batch_fragment_html = self.embed_generator.get_fragment_content(
                year, month
            )

        # 7. WordPress 下書き投稿（オプショナル）
        print("\n[7/7] WordPress 投稿中...")
        if self.wp_publisher and output_path:
            try:
                post_date = _get_next_month_date(year, month)
                post_title = f"【ポケモン投資】{year}年{month}月の状況"
                post_url = self.wp_publisher.create_draft(
                    title=post_title,
                    markdown_content=open(output_path, encoding="utf-8").read(),
                    slug=f"pokemon-investment-{year}{month:02d}",
                    raw_html_prepend=batch_fragment_html,
                    categories=WP_CATEGORY_IDS,
                    date=post_date,
                )
                print(f"  投稿完了: {post_url}")
                self._save_wp_post(year, month, post_url, post_title)
            except Exception as e:
                print(f"  WordPress 投稿エラー: {e}")
        else:
            print("  スキップ（WordPress 投稿無効）")

        print(f"\n=== {year}年{month}月 月次バッチ完了 ===")
        return True

    def collect_monthly_data(self, year: int, month: int) -> bool:
        """株価データ収集・SQLite保存

        Args:
            year: 年
            month: 月

        Returns:
            成功/失敗
        """
        # ポートフォリオ情報取得（holdings テーブル）
        portfolio_data = self.db_writer.get_portfolio_data()
        if not portfolio_data:
            print(
                "❌ ポートフォリオデータが取得できませんでした"
                "（holdings テーブルが空？）"
            )
            return False

        # 月末日付を計算
        if month == 12:
            last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = datetime(year, month + 1, 1) - timedelta(days=1)
        last_day_str = last_day.strftime("%Y-%m-%d")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        price_count = 0
        pnl_count = 0

        for holding in portfolio_data:
            code = holding.get("code", "")
            name = holding.get("name", "")
            shares_raw = holding.get("shares")

            # 必須フィールドが空の行はスキップ
            if not code or not name or not shares_raw:
                continue
            shares = int(float(str(shares_raw)))

            # 取得日を解析して保有期間を判定
            acquired_date_str = holding.get("acquired_date", "")
            is_owned_in_month = True  # デフォルト: 保有扱い（取得日が空の場合）
            if acquired_date_str:
                try:
                    acquired_date = datetime.strptime(
                        str(acquired_date_str), "%Y-%m-%d"
                    )
                    is_owned_in_month = (year, month) >= (
                        acquired_date.year,
                        acquired_date.month,
                    )
                except ValueError:
                    pass  # パース失敗時は保有扱い

            # 外貨情報の取得
            acquired_price_foreign = float(holding.get("acquired_price_foreign") or 0)
            acquired_exchange_rate = float(holding.get("acquired_exchange_rate") or 1.0)

            # 円建て取得単価: acquired_price_jpy → 空なら外貨×レート
            acquired_price_jpy_raw = holding.get("acquired_price_jpy")
            if acquired_price_jpy_raw:
                acquired_price_jpy = float(acquired_price_jpy_raw)
            else:
                acquired_price_jpy = acquired_price_foreign * acquired_exchange_rate

            # 外貨単価が空なら円建て値をフォールバック
            if not acquired_price_foreign:
                acquired_price_foreign = acquired_price_jpy

            print(f"  処理中: {name} ({code})")

            # 株価データ取得
            stock_data = self.stock_collector.get_stock_data(code, year, month)
            if stock_data is None:
                continue

            # メトリクス計算（為替レートは月末日基準のECB参照レートを使う）
            metrics = self.stock_collector.calculate_stock_metrics(
                stock_data,
                code,
                acquired_price_foreign,
                acquired_exchange_rate,
                shares,
                as_of=last_day,
            )
            if metrics is None:
                continue

            # monthly_prices に保存
            self.db_writer.save_monthly_price(
                {
                    "date": last_day_str,
                    "code": code,
                    "price_jpy": metrics["month_end_price"],
                    "high": metrics["highest_price"],
                    "low": metrics["lowest_price"],
                    "average": metrics["average_price"],
                    "change_rate": metrics["monthly_change"],
                    "avg_volume": metrics["average_volume"],
                    "created_at": now_str,
                }
            )
            price_count += 1

            # 為替レートも保存（外貨銘柄の場合）
            if CURRENCY_SETTINGS.get("update_rates_with_stocks", True):
                # metrics は dict[str, object] なので str / float へ明示的に絞る
                currency = str(metrics.get("currency", "JPY"))
                current_rate = metrics.get("current_exchange_rate")
                if (
                    currency != "JPY"
                    and isinstance(current_rate, float)
                    and current_rate
                ):
                    self._save_exchange_rate(
                        currency, current_rate, last_day_str, now_str
                    )

            # monthly_pnl に保存（保有期間のみ）
            if is_owned_in_month:
                self.db_writer.save_monthly_pnl(
                    {
                        "date": f"{year}-{month:02d}-末",
                        "code": code,
                        "name": name,
                        "acquired_price": acquired_price_jpy,
                        "current_price": metrics["month_end_price"],
                        "shares": shares,
                        "cost": metrics["purchase_amount"],
                        "value": metrics["current_amount"],
                        "profit": metrics["profit_loss"],
                        "profit_rate": metrics["profit_rate"],
                        "currency": metrics.get("currency", "JPY"),
                        "acquired_price_foreign": metrics["purchase_price_foreign"],
                        "current_price_foreign": metrics["month_end_price_foreign"],
                        "acquired_exchange_rate": metrics["purchase_exchange_rate"],
                        "current_exchange_rate": metrics["current_exchange_rate"],
                        "updated_at": now_str,
                    }
                )
                pnl_count += 1

                # 表示
                currency_info = ""
                if metrics.get("exchange_rate"):
                    currency_info = (
                        f" [{metrics['currency']}: {metrics['exchange_rate']:.2f}円]"
                    )
                    stock_pl = metrics.get("stock_profit_loss", 0)
                    fx_pl = metrics.get("fx_profit_loss", 0)
                    currency_info += (
                        f" (株価:{stock_pl:+,.0f}円 / 為替:{fx_pl:+,.0f}円)"
                    )
                print(
                    f"    {name}: {metrics['profit_loss']:+,.0f}円 "
                    f"({metrics['profit_rate']:+.1f}%){currency_info}"
                )
            else:
                print(f"    {name}: 市場データのみ記録（取得日: {acquired_date_str}）")

        print(f"\n  市場データ保存: {price_count}件 / 損益レポート保存: {pnl_count}件")

        # 日本株のみの場合は為替レート取得がスキップされているため、ここで取得
        self._update_all_currency_rates(last_day_str, now_str)

        # 収集直後に purchase_history 基準で取得系カラムを補正する。
        # holdings 集約は「現在の合計」を対象月に適用するため、
        # 過去月の収集（--range 等）では shares/cost が不正確になる。
        if price_count > 0:
            repair_monthly_pnl(
                self.db_writer, target_months=[(year, month)], verbose=False
            )

        return price_count > 0

    def _save_ai_comments(self, target_date: str, ai_comments: dict) -> bool:
        """生成した AI コメントを SQLite に保存する。

        Args:
            target_date: 対象月（"YYYY-MM-末" 形式）
            ai_comments: generate_all の戻り値辞書（stock_comments / summary / intro）
        """
        stock_comments = ai_comments.get("stock_comments") or {}
        summary = ai_comments.get("summary")
        intro = ai_comments.get("intro")
        if not stock_comments and not summary and not intro:
            print(
                "  ⚠️ AI コメントを生成できませんでした"
                "（DB 保存をスキップ）"
            )
            return False

        for code, content in stock_comments.items():
            if content:
                self.db_writer.save_ai_comment(target_date, code, "stock", content)
        if summary:
            self.db_writer.save_ai_comment(target_date, "", "summary", summary)
        if intro:
            self.db_writer.save_ai_comment(target_date, "", "intro", intro)
        print(f"  AI コメントを DB に保存しました（{target_date}）")
        return True

    def _save_exchange_rate(
        self, currency: str, rate: float, date_str: str, now_str: str
    ) -> None:
        """為替レートを SQLite に保存"""
        pair = f"{currency}/JPY"
        self.db_writer.save_exchange_rate(
            {
                "date": date_str,
                "pair": pair,
                "rate": rate,
                "prev_rate": None,
                "change_rate": None,
                "high": None,
                "low": None,
                "updated_at": now_str,
            }
        )

    def _save_wp_post(self, year: int, month: int, url: str, title: str) -> None:
        """WordPress 投稿URLを wp_posts に保存する。

        wp_posts テーブルが未整備の古い DB でもバッチ全体を落とさないよう、
        失敗時は警告表示のみに留める。

        Args:
            year: 対象年
            month: 対象月
            url: 作成された下書き投稿の URL
            title: create_draft に渡したタイトル文字列（同一のものを渡す）
        """
        try:
            self.db_writer.save_wp_post(
                {
                    "month": f"{year:04d}-{month:02d}",
                    "url": url,
                    "title": title,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        except Exception as e:
            print(f"  [警告] WordPress 投稿URLの保存に失敗しました: {e}")

    def _update_all_currency_rates(self, date_str: str, now_str: str) -> None:
        """全通貨の為替レートを取得・保存"""
        if not CURRENCY_SETTINGS.get("update_rates_with_stocks", True):
            return

        print("\n  為替レート取得中...")
        # date_str（月末日）基準のECB参照レートを使う（実行日スポットではない）
        on_date = datetime.strptime(date_str, "%Y-%m-%d")
        rates = self.stock_collector.currency_converter.get_all_current_rates(
            on_date
        )
        for currency, rate in rates.items():
            if rate:
                self._save_exchange_rate(currency, float(rate), date_str, now_str)
        print(f"  為替レート保存: {len(rates)}通貨")

    def sync_holdings_only(self) -> bool:
        """Sheets 同期のみ実行"""
        print("\n=== Sheets → SQLite 銘柄マスタ同期 ===")
        if not self.sheets_sync:
            print("❌ Sheets 同期が無効です（認証設定を確認してください）")
            return False
        synced = self.sheets_sync.sync_holdings()
        history_count = self.sheets_sync.sync_purchase_history()
        print(f"同期完了: {synced}件（購入履歴: {history_count}件）")
        return True

    def collect_latest(self) -> bool:
        """トップページ用の最新スナップショット（latest_pnl）を今日時点で上書きする。

        monthly_* / ブログ / AI / WP には触れない。Sheets 同期もしない。

        Returns:
            1 銘柄以上保存できたら True
        """
        print("\n=== 最新スナップショット（latest_pnl）更新 ===")
        today = datetime.now()
        month_first = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start = min(month_first, today - timedelta(days=10))
        converter = self.stock_collector.currency_converter

        holdings = self.db_writer.get_portfolio_data()
        saved = 0
        for h in holdings:
            code = h["code"]
            name = h["name"]
            try:
                history = yf.Ticker(code).history(start=start, auto_adjust=False)
                prices = extract_latest_prices(history, today.year, today.month)
                if prices is None:
                    print(f"  ⚠ {name}（{code}）: 株価データが空のためスキップ")
                    continue
                price_native, price_date, month_start = prices

                currency = converter.get_currency_from_symbol(code)
                rate: float | None = None
                if is_foreign_stock(code):
                    rate = converter.get_exchange_rate(currency, today)
                    if rate is None:
                        print(
                            f"  ❌ {name}（{code}）: 為替レート取得失敗のためスキップ"
                        )
                        continue

                row = compute_latest_row(
                    code=code,
                    name=name,
                    purchases=self.db_writer.get_purchase_history(code),
                    price_native=price_native,
                    price_date=price_date,
                    month_start_price_native=month_start,
                    exchange_rate=rate,
                    currency=currency,
                    today=today.date(),
                )
                if row is None:
                    print(f"  ⚠ {name}（{code}）: 保有株数 0 のためスキップ")
                    continue

                self.db_writer.save_latest_pnl(row)
                saved += 1
                print(
                    f"  {name}: {price_date} 終値 {row['current_price']:,.0f}円 / "
                    f"損益 {row['profit']:+,.0f}円"
                )
            except Exception as e:
                print(f"  ❌ {name}（{code}）: 処理に失敗しました（{e}）")

        removed = self.db_writer.delete_latest_pnl_except([h["code"] for h in holdings])
        if removed:
            print(f"  holdings に無い {removed} 行を削除しました")

        if saved == 0:
            print("❌ 1 銘柄も保存できませんでした")
            return False
        print(f"  完了: {saved}/{len(holdings)} 銘柄を保存")
        return True

    def repair_pnl(self, dry_run: bool = False) -> bool:
        """monthly_pnl の取得系カラムを purchase_history 基準で一括バックフィルする。

        Args:
            dry_run: True の場合は差分表示のみで DB は更新しない。

        Returns:
            常に True（バックフィル自体の成否ではなく実行完了を示す）。
        """
        repair_monthly_pnl(self.db_writer, dry_run=dry_run, verbose=True)
        return True

    def add_purchase(
        self,
        code: str,
        date_str: str,
        shares_str: str,
        price_str: str,
        rate_str: str | None = None,
    ) -> bool:
        """スプレッドシートに買付行を追記し、DB に同期する。

        Args:
            code: 銘柄コード（例: 7974.T, NVDA）
            date_str: 取得日（"YYYY-MM-DD"）
            shares_str: 保有株数（文字列。1以上の整数のみ許可）
            price_str: 取得単価（日本株=円、外国株=外貨）
            rate_str: 取得時為替レート（外国株のみ必須、日本株は指定不可）

        Returns:
            成功/失敗
        """
        if not self.sheets_sync:
            print("❌ Sheets 認証が無効です")
            return False

        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            print("❌ 日付は YYYY-MM-DD 形式で指定してください")
            return False

        try:
            shares = int(shares_str)
        except ValueError:
            shares = 0
        if shares < 1:
            print(
                "❌ 株数は 1 以上の整数で指定してください"
                "（1株未満の端株はポートフォリオ対象外）"
            )
            return False

        is_foreign = is_foreign_stock(code)
        if is_foreign and rate_str is None:
            print(
                "❌ 外国株は為替レートが必要です"
                "（例: --add-purchase NVDA 2026-08-01 1 208.27 162.35）"
            )
            return False
        if not is_foreign and rate_str is not None:
            print("❌ 日本株に為替レートは指定できません")
            return False

        try:
            price = float(price_str)
        except ValueError:
            price = 0.0
        if price <= 0:
            print("❌ 取得単価は正の数値で指定してください")
            return False

        rate: float | None = None
        if rate_str is not None:
            try:
                rate = float(rate_str)
            except ValueError:
                rate = 0.0
            if rate <= 0:
                print("❌ 為替レートは正の数値で指定してください")
                return False

        try:
            if is_foreign:
                name = self.sheets_sync.append_purchase_row(
                    code,
                    date_str,
                    shares,
                    price_foreign=price,
                    exchange_rate=rate,
                )
            else:
                name = self.sheets_sync.append_purchase_row(
                    code,
                    date_str,
                    shares,
                    price_jpy=price,
                )
        except ValueError as e:
            print(f"❌ {e}")
            return False

        price_info = f"@{price}" if not is_foreign else f"@{price}（為替{rate}）"
        print(
            f"✅ {name}（{code}）の買付行を追記しました: "
            f"{date_str} {shares}株 {price_info}"
        )

        self.sync_holdings_only()
        repair_monthly_pnl(self.db_writer, verbose=False)
        return True

    def add_dividend(
        self,
        code: str,
        date_str: str,
        shares_str: str,
        per_share_str: str,
        rate_str: str | None = None,
    ) -> bool:
        """配当受取を記録する（DB 直書き。Sheets 認証なしでも実行可能）。

        Args:
            code: 銘柄コード（例: 7974.T, NVDA）
            date_str: 受取日（"YYYY-MM-DD"）
            shares_str: 保有株数（文字列。1以上の整数のみ許可）
            per_share_str: 1株あたり配当（日本株=円、外国株=外貨）
            rate_str: 受取時為替レート（外国株のみ必須、日本株は指定不可）

        Returns:
            成功/失敗
        """
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            print("❌ 日付は YYYY-MM-DD 形式で指定してください")
            return False

        try:
            shares = int(shares_str)
        except ValueError:
            shares = 0
        if shares < 1:
            print(
                "❌ 株数は 1 以上の整数で指定してください"
                "（1株未満の端株はポートフォリオ対象外）"
            )
            return False

        is_foreign = is_foreign_stock(code)
        if is_foreign and rate_str is None:
            print(
                "❌ 外国株は為替レートが必要です"
                "（例: --add-dividend NVDA 2026-06-27 2 0.01 155.30）"
            )
            return False
        if not is_foreign and rate_str is not None:
            print("❌ 日本株に為替レートは指定できません")
            return False

        # 金額は float を経由させず Decimal で扱う（2進浮動小数の誤差を持ち込まない）
        try:
            per_share = Decimal(per_share_str)
        except InvalidOperation:
            per_share = Decimal(0)
        if not per_share.is_finite() or per_share <= 0:
            print("❌ 1株配当は正の数値で指定してください")
            return False

        rate: Decimal | None = None
        if rate_str is not None:
            try:
                rate = Decimal(rate_str)
            except InvalidOperation:
                rate = Decimal(0)
            if not rate.is_finite() or rate <= 0:
                print("❌ 為替レートは正の数値で指定してください")
                return False

        holding = self.db_writer.get_holding_by_code(code)
        if holding is None:
            print("❌ holdings に存在しない銘柄です")
            return False
        name = holding["name"]
        currency = holding["currency"]

        # 円への丸めは四捨五入で統一（組み込み round() は偶数丸めのため使わない）
        dividend_foreign: float | None
        total_foreign: float | None
        exchange_rate: float | None
        if is_foreign:
            if rate is None:  # is_foreign なら検証済みで到達しない（型ガード）
                print("❌ 外国株は為替レートが必要です")
                return False
            total_foreign_dec = per_share * shares
            total_jpy = int(
                (total_foreign_dec * rate).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
            dividend_foreign = float(per_share)
            total_foreign = float(total_foreign_dec)
            exchange_rate = float(rate)
        else:
            total_jpy = int(
                (per_share * shares).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
            dividend_foreign = None
            total_foreign = None
            exchange_rate = None

        self.db_writer.save_dividend(
            {
                "date": date_str,
                "code": code,
                "name": name,
                "dividend_foreign": dividend_foreign,
                "shares": shares,
                "total_foreign": total_foreign,
                "currency": currency,
                "exchange_rate": exchange_rate,
                "total_jpy": total_jpy,
            }
        )

        print(
            f"✅ {name}（{code}）の配当を記録しました: "
            f"{date_str} {total_jpy:,}円"
        )
        return True

    def _fetch_rate_with_retry(
        self, currency: str, dt: datetime, attempts: int = 3
    ) -> float | None:
        """受取日の為替レートを取得する（一時的な通信エラー向けにリトライする）。

        frankfurter API はまれにタイムアウトする。1件でも欠けると全件中断する
        設計のため、諦める前に間隔を空けて数回試す。

        Args:
            currency: 通貨コード（USD 等）
            dt: 受取日
            attempts: 最大試行回数

        Returns:
            為替レート（全試行が失敗したら None）
        """
        for i in range(attempts):
            try:
                rate = self.stock_collector.currency_converter.get_exchange_rate(
                    currency, dt
                )
            except Exception as e:
                # get_exchange_rate は現状すべての例外を握って None を返す
                # 実装（collectors/currency_converter.py）だが、将来例外を
                # 透過するように変わってもリトライが効くよう保険で包む
                print(f"  ⚠️ 為替レート取得中に例外が発生しました: {e}")
                rate = None
            if rate is not None:
                return rate
            if i < attempts - 1:
                print(
                    f"  ⏳ 為替レートを再取得します（{i + 2}回目）: "
                    f"{dt.strftime('%Y-%m-%d')}"
                )
                time.sleep(1)
        return None

    def import_dividends(self, csv_path: str, dry_run: bool = False) -> bool:
        """楽天証券の配当金明細 CSV（cp932）を読み込み、dividends テーブルへ
        一括登録する。

        add_dividend とは計算の向きが逆（税引前総額が正で、1株配当は導出値）
        なので処理を共有しない。フェーズを2段階に分けて実行する:

          フェーズ1: 保存レコードを全件確定させる（外国株は受取日の為替
              レートを取得する）。1件でも為替レートが取得できなければ、
              何も書き込まずエラー終了する（フェイルファスト）。
          フェーズ2: dry_run なら表示のみ。本実行なら1件ずつ保存してサマリを
              表示する。save_dividend は1件ごとに commit するため厳密な
              原子性は無い点に注意（フェーズ1を通過すれば書き込み自体が
              失敗することは想定していないが、保存ループの途中で中断した
              場合は部分的にしか入らない）。dividends は date+code の
              UPSERT なので、再実行すれば必ず揃う。

        Args:
            csv_path: CSV ファイルパス。
            dry_run: True の場合は集計結果の表示のみで DB には書き込まない
                （為替レート取得は dry_run でも実施する）。

        Returns:
            成功/失敗。
        """
        try:
            with open(csv_path, "rb") as f:
                raw_bytes = f.read()
        except FileNotFoundError:
            print(f"❌ ファイルが見つかりません: {csv_path}")
            return False

        try:
            text = raw_bytes.decode("cp932")
        except UnicodeDecodeError as e:
            print(f"❌ CSV を cp932 で読み込めません: {e}")
            return False

        try:
            rows = parse_rakuten_csv(text)
        except ValueError as e:
            print(f"❌ CSV の解析に失敗しました: {e}")
            return False

        # holdings から code → (name, currency) のマップを作る
        # （銘柄名は CSV の表記ゆれではなく holdings.name を使い、
        #   既存の配当データと表記を揃える）
        holdings = self.db_writer.get_portfolio_data()
        holdings_map = {
            h["code"]: {"name": h["name"], "currency": h["currency"]}
            for h in holdings
            if h.get("code")
        }

        aggregated, skipped = aggregate(rows, set(holdings_map.keys()))

        print(f"\n=== 配当CSVインポート: {csv_path} ===")
        print(f"  総データ行数: {len(rows)}行 / 投入対象: {len(aggregated)}件")

        if skipped:
            print(f"\n  スキップ: {len(skipped)}行")
            for s in skipped:
                print(
                    f"    {s.row_no}行目 {s.code}: {s.reason}"
                    f"（{_format_decimal(s.shares)}株 "
                    f"{_format_decimal(s.total_pretax)}{s.currency}）"
                )

        multi = [a for a in aggregated if len(a.source_row_nos) > 1]
        if multi:
            print(f"\n  合算: {len(multi)}組")
            for a in multi:
                currency = holdings_map[a.code]["currency"]
                unit = "円" if currency == "JPY" else currency
                print(
                    f"    {a.date} {a.code}: {len(a.source_row_nos)}行合算 → "
                    f"{_format_decimal(a.shares)}株 "
                    f"{_format_decimal(a.total_pretax)}{unit}"
                )

        # フェーズ1: 外国株の受取日為替レートを事前に全件取得する
        # （同じ通貨・同じ日付の組は1回しか取得しないようキャッシュする。
        #   キーを日付だけにすると、同日に複数の外貨通貨が混在した場合に
        #   先に取得した通貨のレートがもう片方に誤って流用されてしまう）
        rate_cache: dict[tuple[str, str], float | None] = {}
        for a in aggregated:
            currency = holdings_map[a.code]["currency"]
            if currency == "JPY":
                continue
            cache_key = (currency, a.date)
            if cache_key not in rate_cache:
                dt = datetime.strptime(a.date, "%Y-%m-%d")
                rate_cache[cache_key] = self._fetch_rate_with_retry(currency, dt)

        missing_keys = sorted(
            {
                (holdings_map[a.code]["currency"], a.date)
                for a in aggregated
                if holdings_map[a.code]["currency"] != "JPY"
                and rate_cache.get((holdings_map[a.code]["currency"], a.date)) is None
            }
        )
        if missing_keys:
            missing_desc = ", ".join(
                f"{currency} {date}" for currency, date in missing_keys
            )
            print(f"\n❌ 為替レートが取得できませんでした: {missing_desc}")
            print("  何も保存せず中断します")
            return False

        # 為替レートが全件揃ったので保存レコードを確定させる
        save_records: list[dict] = []
        for a in aggregated:
            info = holdings_map[a.code]
            currency = info["currency"]
            rate = (
                Decimal(str(rate_cache[(currency, a.date)]))
                if currency != "JPY"
                else None
            )
            save_records.append(
                build_save_record(a, name=info["name"], currency=currency, rate=rate)
            )

        existing_keys = self.db_writer.get_dividend_keys()

        print(f"\n  投入予定レコード（{'dry-run' if dry_run else '本実行'}）:")
        domestic_total = 0
        foreign_total_jpy = 0
        for rec in save_records:
            key = (rec["date"], rec["code"])
            mark = " [上書き]" if key in existing_keys else ""
            if rec["currency"] == "JPY":
                domestic_total += rec["total_jpy"]
                detail = ""
            else:
                foreign_total_jpy += rec["total_jpy"]
                detail = (
                    f" 外貨額={rec['total_foreign']:.2f}{rec['currency']} "
                    f"為替={rec['exchange_rate']:.2f}"
                )
            print(
                f"    {rec['date']} {rec['code']}（{rec['name']}）"
                f" {rec['shares']:g}株{detail} "
                f"→ {rec['total_jpy']:,}円{mark}"
            )

        grand_total = domestic_total + foreign_total_jpy
        print(
            f"\n  合計: {len(save_records)}件 / total_jpy合計 {grand_total:,}円"
            f"（国内株 {domestic_total:,}円 + 外国株換算 {foreign_total_jpy:,}円）"
        )
        print("  ※ 為替レートは dry-run でも実際に取得しています")

        if dry_run:
            print("\n  [dry-run] DB へは書き込んでいません")
            return True

        # フェーズ2: 保存
        for rec in save_records:
            self.db_writer.save_dividend(rec)

        print(f"\n✅ {len(save_records)}件の配当を保存しました")
        return True

    def collect_benchmark_only(self, year: int, month: int) -> bool:
        """ベンチマーク収集のみ実行"""
        print(f"\n=== {year}年{month}月 ベンチマーク収集 ===")
        self.benchmark_collector.collect(year, month)
        return True

    def generate_blog_draft(self, year: int, month: int) -> bool:
        """ブログ下書き生成（AI コメント・WordPress 投稿含む）

        Args:
            year: 年
            month: 月

        Returns:
            成功/失敗
        """
        print(f"\n=== {year}年{month}月 ブログ下書き生成 ===")

        report_data = self.report_generator.get_monthly_report_data(year, month)
        if not report_data:
            print("❌ レポートデータが取得できませんでした")
            return False

        # AI コメント生成（有効な場合）
        target_date = f"{year}-{month:02d}-末"
        ai_comments: dict = {}
        if self.ai_comment:
            # DB に既存コメントがあれば再利用（AI_COMMENTS_FORCE=true で強制再生成）
            if not AI_COMMENTS_FORCE:
                existing = self.db_writer.get_ai_comments(target_date)
                if _has_complete_ai_comments(existing, report_data):
                    print("  AI コメント: DB から既存コメントを再利用します")
                    # generate_all 形式に変換
                    stock_comments: dict[str, str] = {}
                    for (code, kind), content in existing.items():
                        if kind == "stock" and code:
                            stock_comments[code] = content
                    ai_comments = {
                        "stock_comments": stock_comments,
                        "summary": existing.get(("", "summary")),
                        "intro": existing.get(("", "intro")),
                    }
                else:
                    if existing:
                        print("  AI コメント: DB の不足分を再生成します")
                    print("  AI コメント生成中...")
                    ai_comments = self.ai_comment.generate_all(report_data)
                    if self._save_ai_comments(target_date, ai_comments):
                        print("  AI コメント生成完了")
            else:
                print("  AI コメント強制再生成中（AI_COMMENTS_FORCE=true）...")
                ai_comments = self.ai_comment.generate_all(report_data)
                if self._save_ai_comments(target_date, ai_comments):
                    print("  AI コメント生成完了")
            report_data["ai_comments"] = ai_comments
        else:
            # AI コメント無効でも DB に保存済みのコメントがあれば読み込む
            existing = self.db_writer.get_ai_comments(target_date)
            if existing:
                stock_comments = {}
                for (code, kind), content in existing.items():
                    if kind == "stock" and code:
                        stock_comments[code] = content
                report_data["ai_comments"] = {
                    "stock_comments": stock_comments,
                    "summary": existing.get(("", "summary")),
                    "intro": existing.get(("", "intro")),
                }

        markdown_text = self.template_engine.render(
            "blog_template.md", report_data
        )

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(
            OUTPUT_DIR, f"blog_draft_{year}_{month:02d}.md"
        )
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_text)

        print(f"  ブログ下書きを生成しました: {output_path}")

        # 埋め込み HTML/JSON 生成（有効な場合）
        fragment_html: str | None = None
        if self.embed_generator:
            print("\n  埋め込みコンテンツ生成中...")
            self.embed_generator.generate(year, month)
            fragment_html = self.embed_generator.get_fragment_content(year, month)

        # WordPress 下書き投稿（有効な場合）
        if self.wp_publisher:
            try:
                post_date = _get_next_month_date(year, month)
                post_title = f"【ポケモン投資】{year}年{month}月の状況"
                post_url = self.wp_publisher.create_draft(
                    title=post_title,
                    markdown_content=markdown_text,
                    slug=f"pokemon-investment-{year}{month:02d}",
                    raw_html_prepend=fragment_html,
                    categories=WP_CATEGORY_IDS,
                    date=post_date,
                )
                print(f"  WordPress 投稿完了: {post_url}")
                self._save_wp_post(year, month, post_url, post_title)
            except Exception as e:
                print(f"  WordPress 投稿エラー: {e}")

        return True

    def collect_range_data(
        self,
        start_year: int,
        start_month: int,
        end_year: int,
        end_month: int,
        auto_confirm: bool = False,
    ) -> dict:
        """期間範囲でのデータ収集

        Args:
            start_year: 開始年
            start_month: 開始月
            end_year: 終了年
            end_month: 終了月
            auto_confirm: 自動確認フラグ

        Returns:
            実行結果サマリー
        """
        print(
            f"\n=== 期間範囲データ収集: "
            f"{start_year}年{start_month}月 〜 {end_year}年{end_month}月 ==="
        )

        # 総月数計算
        total_months = 0
        ty, tm = start_year, start_month
        while (ty, tm) <= (end_year, end_month):
            total_months += 1
            tm += 1
            if tm > 12:
                tm = 1
                ty += 1

        print(f"実行予定: {total_months}ヶ月分")

        if not auto_confirm:
            confirm = input("\n実行しますか？ (y/n): ").strip().lower()
            if confirm != "y":
                print("実行をキャンセルしました")
                return {"status": "cancelled"}

        success_count = 0
        error_count = 0
        error_details: list[str] = []

        current_year, current_month = start_year, start_month
        current_count = 0

        while (current_year, current_month) <= (end_year, end_month):
            current_count += 1
            print(
                f"\n[{current_count}/{total_months}] "
                f"{current_year}年{current_month}月..."
            )

            try:
                success = self.collect_monthly_data(current_year, current_month)
                if success:
                    success_count += 1
                else:
                    error_count += 1
                    error_details.append(
                        f"{current_year}年{current_month}月: データ取得失敗"
                    )
            except Exception as e:
                error_count += 1
                error_details.append(f"{current_year}年{current_month}月: {e}")
                print(f"❌ エラー: {e}")

            # API制限回避（最後の月以外）
            if (current_year, current_month) < (end_year, end_month):
                print("  10秒待機中...")
                time.sleep(10)

            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1

        print(f"\n=== 完了: 成功 {success_count}/{total_months}件 ===")
        if error_details:
            print("エラー詳細:")
            for e in error_details:
                print(f"  - {e}")

        return {
            "status": "completed",
            "total_months": total_months,
            "success_count": success_count,
            "error_count": error_count,
            "error_details": error_details,
        }

    def run_interactive(self) -> None:
        """対話型メインメニュー"""
        print("=== ポートフォリオデータ収集システム（SQLite版）===")

        while True:
            try:
                print("\n=== メインメニュー ===")
                print("1. 月次データ収集（株価 + ベンチマーク + ブログ）")
                print("2. 期間範囲データ収集")
                print("3. Sheets → SQLite 銘柄マスタ同期")
                print("4. ベンチマークのみ収集")
                print("5. ブログ下書き生成のみ")
                print("0. 終了")

                choice = input("\n選択してください: ").strip()

                if choice == "0":
                    break

                elif choice == "1":
                    year = int(input("年を入力 (例: 2024): "))
                    month = int(input("月を入力 (1-12): "))
                    if not 1 <= month <= 12:
                        print("月は 1-12 の範囲で入力してください")
                        continue
                    self.collect_and_publish(year, month)

                elif choice == "2":
                    start_year = int(input("開始年 (例: 2024): "))
                    start_month = int(input("開始月 (1-12): "))
                    end_year = int(input("終了年 (例: 2025): "))
                    end_month = int(input("終了月 (1-12): "))
                    if not (1 <= start_month <= 12 and 1 <= end_month <= 12):
                        print("月は 1-12 の範囲で入力してください")
                        continue
                    if (start_year, start_month) > (end_year, end_month):
                        print("開始年月は終了年月より前である必要があります")
                        continue
                    self.collect_range_data(
                        start_year, start_month, end_year, end_month
                    )

                elif choice == "3":
                    self.sync_holdings_only()

                elif choice == "4":
                    year = int(input("年を入力 (例: 2024): "))
                    month = int(input("月を入力 (1-12): "))
                    if not 1 <= month <= 12:
                        print("月は 1-12 の範囲で入力してください")
                        continue
                    self.collect_benchmark_only(year, month)

                elif choice == "5":
                    year = int(input("年を入力 (例: 2024): "))
                    month = int(input("月を入力 (1-12): "))
                    if not 1 <= month <= 12:
                        print("月は 1-12 の範囲で入力してください")
                        continue
                    self.generate_blog_draft(year, month)

                else:
                    print("❌ 無効な選択です")

            except ValueError:
                print("❌ 正しい数値を入力してください")
            except KeyboardInterrupt:
                print("\n終了します")
                break
            except Exception as e:
                print(f"❌ エラーが発生しました: {e}")


def _parse_year_month(args: list[str], flag: str) -> tuple[int, int] | None:
    """引数から年月を解析するヘルパー"""
    try:
        return int(args[0]), int(args[1])
    except (IndexError, ValueError):
        print("❌ 年と月は数値で指定してください")
        print(f"使用例: python main.py {flag} 2024 12")
        return None


def main() -> None:
    """メイン関数（CLI エントリーポイント）"""
    args = sys.argv[1:]

    # python main.py --generate-chart NAME SYMBOL START END [CURRENCY]
    # 例: python main.py --generate-chart 任天堂 7974.T 2023-06-28 2026-03-31
    # DB 非依存の POC 用
    if len(args) in (5, 6) and args[0] == "--generate-chart":
        name = args[1]
        symbol = args[2]
        start = args[3]
        end = args[4]
        currency = args[5] if len(args) == 6 else "JPY"
        from collectors.chart_generator import ChartGenerator

        out_path = os.path.join(
            OUTPUT_DIR, "charts", f"{symbol}_{start}_{end}.png"
        )
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        print(f"  {name}（{symbol}）のチャートを生成中 {start}〜{end}...")
        try:
            generator = ChartGenerator()
            saved = generator.generate(symbol, name, start, end, out_path, currency)
            print(f"  保存完了: {saved}")
        except Exception as e:
            print(f"❌ チャート生成エラー: {e}")
        return

    if not SPREADSHEET_ID:
        print("❌ SPREADSHEET_ID が設定されていません。.env ファイルを確認してください")
        return

    collector = PortfolioDataCollector()

    # python main.py 2024 12  → バッチ（月次フル収集）
    if len(args) == 2 and args[0].isdigit():
        ym = _parse_year_month(args, "")
        if ym:
            print(f"バッチモード: {ym[0]}年{ym[1]}月")
            collector.collect_and_publish(*ym)

    # python main.py --sync  → Sheets同期のみ
    elif args == ["--sync"]:
        collector.sync_holdings_only()

    # python main.py --latest  → トップページ用の最新スナップショットのみ更新
    elif args == ["--latest"]:
        if not collector.collect_latest():
            sys.exit(1)

    # python main.py --benchmark 2024 12  → ベンチマークのみ
    elif len(args) == 3 and args[0] == "--benchmark":
        ym = _parse_year_month(args[1:], "--benchmark")
        if ym:
            collector.collect_benchmark_only(*ym)

    # python main.py --blog 2024 12  → ブログ生成のみ
    elif len(args) == 3 and args[0] == "--blog":
        ym = _parse_year_month(args[1:], "--blog")
        if ym:
            collector.generate_blog_draft(*ym)

    # python main.py --range 2024 1 2024 12  → 期間範囲バッチ
    elif len(args) == 5 and args[0] == "--range":
        try:
            sy, sm, ey, em = int(args[1]), int(args[2]), int(args[3]), int(args[4])
            collector.collect_range_data(sy, sm, ey, em, auto_confirm=True)
        except ValueError:
            print("❌ 年と月は数値で指定してください")
            print("使用例: python main.py --range 2024 1 2024 12")

    # python main.py --repair-pnl [--dry-run]  → monthly_pnl バックフィル
    elif len(args) in (1, 2) and args[0] == "--repair-pnl":
        if len(args) == 2 and args[1] != "--dry-run":
            print("❌ 不明なオプションです")
            print("使用例: python main.py --repair-pnl --dry-run")
        else:
            collector.repair_pnl(dry_run=(len(args) == 2))

    # python main.py --add-purchase 7974.T 2026-08-01 1 8500          （日本株）
    # python main.py --add-purchase NVDA 2026-08-01 1 208.27 162.35   （外国株）
    elif len(args) in (5, 6) and args[0] == "--add-purchase":
        collector.add_purchase(
            args[1], args[2], args[3], args[4],
            args[5] if len(args) == 6 else None,
        )

    # python main.py --add-dividend 7974.T 2026-06-27 2 118           （日本株）
    # python main.py --add-dividend NVDA 2026-06-27 2 0.01 155.30     （外国株）
    elif len(args) in (5, 6) and args[0] == "--add-dividend":
        collector.add_dividend(
            args[1], args[2], args[3], args[4],
            args[5] if len(args) == 6 else None,
        )

    # python main.py --import-dividends dividend.csv [--dry-run]
    elif len(args) in (2, 3) and args[0] == "--import-dividends":
        if len(args) == 3 and args[2] != "--dry-run":
            print("❌ 不明なオプションです")
            print(
                "使用例: python main.py --import-dividends "
                "dividend.csv --dry-run"
            )
        else:
            collector.import_dividends(args[1], dry_run=(len(args) == 3))

    # 引数なし  → 対話型
    elif not args:
        collector.run_interactive()

    else:
        print("使用方法:")
        print("  python main.py                         # 対話型")
        print("  python main.py 2024 12                 # 月次フル収集")
        print("  python main.py --sync                  # Sheets同期のみ")
        print("  python main.py --latest                # 最新スナップショット更新")
        print("  python main.py --benchmark 2024 12     # ベンチマークのみ")
        print("  python main.py --blog 2024 12          # ブログ生成のみ")
        print("  python main.py --range 2024 1 2024 12  # 期間範囲バッチ")
        print("  python main.py --repair-pnl [--dry-run]  # monthly_pnl バックフィル")
        print(
            "  python main.py --add-purchase 7974.T 2026-08-01 1 8500"
            "          # 買付追記（日本株）"
        )
        print(
            "  python main.py --add-purchase NVDA 2026-08-01 1 208.27 162.35"
            "  # 買付追記（外国株）"
        )
        print(
            "  python main.py --add-dividend 7974.T 2026-06-27 2 118"
            "                # 配当記録（日本株）"
        )
        print(
            "  python main.py --add-dividend NVDA 2026-06-27 2 0.01 155.30"
            "    # 配当記録（外国株）"
        )
        print(
            "  python main.py --import-dividends dividend.csv [--dry-run]"
            "     # 配当CSV一括インポート（楽天証券・cp932）"
        )
        print(
            "  python main.py --generate-chart 任天堂 7974.T 2023-06-28 2026-03-31"
        )


if __name__ == "__main__":
    main()
