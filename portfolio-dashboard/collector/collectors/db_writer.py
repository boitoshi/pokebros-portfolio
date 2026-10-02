"""SQLite データ書き込みモジュール"""

import sqlite3


class DbWriter:
    """SQLite へのデータ書き込みクラス"""

    def __init__(self, db_path: str) -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")

    def close(self) -> None:
        self.conn.close()

    def save_monthly_price(self, data: dict) -> None:
        """月次市場データを保存（UPSERT）"""
        self.conn.execute(
            """
            INSERT INTO monthly_prices (
                date, code, price_jpy, high, low, average,
                change_rate, avg_volume, created_at)
            VALUES (
                :date, :code, :price_jpy, :high, :low, :average,
                :change_rate, :avg_volume, :created_at)
            ON CONFLICT(date, code) DO UPDATE SET
                price_jpy=excluded.price_jpy, high=excluded.high, low=excluded.low,
                average=excluded.average, change_rate=excluded.change_rate,
                avg_volume=excluded.avg_volume, created_at=excluded.created_at
        """,
            data,
        )
        self.conn.commit()

    def save_monthly_pnl(self, data: dict) -> None:
        """月次損益を保存（UPSERT）"""
        self.conn.execute(
            """
            INSERT INTO monthly_pnl (date, code, name, acquired_price, current_price,
                shares, cost, value, profit, profit_rate, currency,
                acquired_price_foreign, current_price_foreign,
                acquired_exchange_rate, current_exchange_rate, updated_at)
            VALUES (:date, :code, :name, :acquired_price, :current_price,
                :shares, :cost, :value, :profit, :profit_rate, :currency,
                :acquired_price_foreign, :current_price_foreign,
                :acquired_exchange_rate, :current_exchange_rate, :updated_at)
            ON CONFLICT(date, code) DO UPDATE SET
                name=excluded.name, current_price=excluded.current_price,
                value=excluded.value, profit=excluded.profit,
                profit_rate=excluded.profit_rate,
                current_price_foreign=excluded.current_price_foreign,
                current_exchange_rate=excluded.current_exchange_rate,
                updated_at=excluded.updated_at
        """,
            data,
        )
        self.conn.commit()

    def save_exchange_rate(self, data: dict) -> None:
        """為替レートを保存（UPSERT）"""
        self.conn.execute(
            """
            INSERT INTO exchange_rates (
                date, pair, rate, prev_rate, change_rate, high, low, updated_at)
            VALUES (
                :date, :pair, :rate, :prev_rate, :change_rate, :high, :low, :updated_at)
            ON CONFLICT(date, pair) DO UPDATE SET
                rate=excluded.rate, prev_rate=excluded.prev_rate,
                change_rate=excluded.change_rate, high=excluded.high, low=excluded.low,
                updated_at=excluded.updated_at
        """,
            data,
        )
        self.conn.commit()

    def save_dividend(self, data: dict) -> None:
        """配当受取記録を保存（UPSERT）"""
        self.conn.execute(
            """
            INSERT INTO dividends (
                date, code, name, dividend_foreign, shares,
                total_foreign, currency, exchange_rate, total_jpy)
            VALUES (
                :date, :code, :name, :dividend_foreign, :shares,
                :total_foreign, :currency, :exchange_rate, :total_jpy)
            ON CONFLICT(date, code) DO UPDATE SET
                name=excluded.name, dividend_foreign=excluded.dividend_foreign,
                shares=excluded.shares, total_foreign=excluded.total_foreign,
                currency=excluded.currency, exchange_rate=excluded.exchange_rate,
                total_jpy=excluded.total_jpy
        """,
            data,
        )
        self.conn.commit()

    def get_dividend_keys(self) -> set[tuple[str, str]]:
        """dividends テーブルに既に存在する (date, code) の組を取得する。

        --import-dividends の dry-run で「上書き」判定に使う。

        Returns:
            {(date, code), ...} の set
        """
        cursor = self.conn.execute("SELECT date, code FROM dividends")
        return {(row[0], row[1]) for row in cursor.fetchall()}

    def save_wp_post(self, data: dict) -> None:
        """WordPress 投稿URLを保存（UPSERT）"""
        self.conn.execute(
            """
            INSERT INTO wp_posts (month, url, title, created_at)
            VALUES (:month, :url, :title, :created_at)
            ON CONFLICT(month) DO UPDATE SET
                url=excluded.url, title=excluded.title, created_at=excluded.created_at
        """,
            data,
        )
        self.conn.commit()

    def save_latest_pnl(self, row: dict) -> None:
        """最新スナップショット（latest_pnl）を保存（UPSERT・全列更新）"""
        self.conn.execute(
            """
            INSERT INTO latest_pnl (code, name, currency, price_date, current_price,
                current_price_foreign, exchange_rate, month_start_price_native,
                shares, cost, acquired_price, acquired_price_foreign,
                value, profit, profit_rate, updated_at)
            VALUES (:code, :name, :currency, :price_date, :current_price,
                :current_price_foreign, :exchange_rate, :month_start_price_native,
                :shares, :cost, :acquired_price, :acquired_price_foreign,
                :value, :profit, :profit_rate, :updated_at)
            ON CONFLICT(code) DO UPDATE SET
                name=excluded.name, currency=excluded.currency,
                price_date=excluded.price_date,
                current_price=excluded.current_price,
                current_price_foreign=excluded.current_price_foreign,
                exchange_rate=excluded.exchange_rate,
                month_start_price_native=excluded.month_start_price_native,
                shares=excluded.shares, cost=excluded.cost,
                acquired_price=excluded.acquired_price,
                acquired_price_foreign=excluded.acquired_price_foreign,
                value=excluded.value, profit=excluded.profit,
                profit_rate=excluded.profit_rate, updated_at=excluded.updated_at
        """,
            row,
        )
        self.conn.commit()

    def delete_latest_pnl_except(self, codes: list[str]) -> int:
        """指定コード以外の latest_pnl 行を削除する（holdings から消えた銘柄の掃除）

        Returns:
            削除した行数
        """
        if codes:
            placeholders = ",".join("?" * len(codes))
            cursor = self.conn.execute(
                f"DELETE FROM latest_pnl WHERE code NOT IN ({placeholders})",
                codes,
            )
        else:
            cursor = self.conn.execute("DELETE FROM latest_pnl")
        self.conn.commit()
        return cursor.rowcount

    def get_holding_by_code(self, code: str) -> dict | None:
        """holdings から銘柄コードで1件取得する（配当記録の銘柄名・通貨引き当て用）。

        Args:
            code: 銘柄コード

        Returns:
            該当行の dict。存在しない場合は None
        """
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.execute(
            "SELECT name, currency FROM holdings WHERE code = ? LIMIT 1",
            (code,),
        )
        row = cursor.fetchone()
        self.conn.row_factory = None
        return dict(row) if row else None

    def save_benchmark(self, data: dict) -> None:
        """ベンチマークデータを保存（UPSERT）"""
        self.conn.execute(
            """
            INSERT INTO benchmark_data (date, portfolio, nikkei225, sp500)
            VALUES (:date, :portfolio, :nikkei225, :sp500)
            ON CONFLICT(date) DO UPDATE SET
                portfolio=excluded.portfolio, nikkei225=excluded.nikkei225,
                sp500=excluded.sp500
        """,
            data,
        )
        self.conn.commit()

    def get_portfolio_data(self) -> list[dict]:
        """holdings テーブルから保有銘柄を取得"""
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.execute("SELECT * FROM holdings")
        rows = cursor.fetchall()
        self.conn.row_factory = None
        return [dict(row) for row in rows]

    def get_performance_data(self, year: int, month: int) -> list[dict]:
        """指定月の損益データを取得"""
        target_date = f"{year}-{month:02d}-末"
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.execute(
            "SELECT * FROM monthly_pnl WHERE date = ?", (target_date,)
        )
        rows = cursor.fetchall()
        self.conn.row_factory = None
        return [dict(row) for row in rows]

    def get_market_data(self, date_str: str) -> dict[str, dict]:
        """指定日の市場データを銘柄コード→データのdictで取得"""
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.execute(
            "SELECT * FROM monthly_prices WHERE date = ?", (date_str,)
        )
        rows = cursor.fetchall()
        self.conn.row_factory = None
        return {row["code"]: dict(row) for row in rows}

    def get_latest_exchange_rates(self) -> dict[str, float]:
        """最新の為替レートを通貨コード→レートのdictで取得"""
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.execute("""
            SELECT pair, rate FROM exchange_rates
            WHERE date = (SELECT MAX(date) FROM exchange_rates)
        """)
        rows = cursor.fetchall()
        self.conn.row_factory = None
        rates: dict[str, float] = {}
        for row in rows:
            pair = row["pair"]
            if pair.endswith("/JPY"):
                currency = pair.replace("/JPY", "")
                rates[currency] = row["rate"]
        return rates

    def get_benchmark_row(self, date: str) -> dict | None:
        """指定月の benchmark_data 行を取得する（市況コンテキスト用）。

        portfolio/nikkei225/sp500 は最初の記録月を基準にした累積リターン(%)。

        Args:
            date: 対象月（"YYYY-MM-末" 形式）

        Returns:
            該当行の dict。存在しない場合は None
        """
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.execute(
            "SELECT * FROM benchmark_data WHERE date = ?", (date,)
        )
        row = cursor.fetchone()
        self.conn.row_factory = None
        return dict(row) if row else None

    def get_exchange_rate_for_exact_month(
        self, pair: str, year: int, month: int
    ) -> float | None:
        """指定月の為替レートのみを取得する（フォールバックなし）。

        get_exchange_rate_for_month と異なり、対象月にデータが無い場合でも
        最新レートにフォールバックしない。市況コンテキストで誤った月のレートを
        「事実」として渡さないようにするための厳密版。

        Args:
            pair: 通貨ペア（例: "USD/JPY"）
            year: 年
            month: 月

        Returns:
            為替レート。対象月のデータが無ければ None
        """
        prefix = f"{year}-{month:02d}"
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.execute(
            """
            SELECT rate FROM exchange_rates
            WHERE pair = ? AND date LIKE ?
            ORDER BY date DESC LIMIT 1
            """,
            (pair, f"{prefix}%"),
        )
        row = cursor.fetchone()
        self.conn.row_factory = None
        return float(row["rate"]) if row else None

    def get_purchase_history(self, code: str) -> list[dict]:
        """指定銘柄の購入履歴を取得する。

        Args:
            code: 銘柄コード

        Returns:
            購入履歴のリスト（seq 昇順）
        """
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.execute(
            "SELECT * FROM purchase_history WHERE code = ? ORDER BY seq",
            (code,),
        )
        rows = cursor.fetchall()
        self.conn.row_factory = None
        return [dict(row) for row in rows]

    def get_all_pnl_data(self) -> list[dict]:
        """全月の損益データを取得（ベンチマーク計算用）"""
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.execute("SELECT * FROM monthly_pnl ORDER BY date")
        rows = cursor.fetchall()
        self.conn.row_factory = None
        return [dict(row) for row in rows]

    def save_ai_comment(self, date: str, code: str, kind: str, content: str) -> None:
        """AI コメントを保存（UPSERT）。

        Args:
            date: 対象月（"YYYY-MM-末" 形式）
            code: 銘柄コード。intro/summary は空文字列
            kind: コメント種別（"stock" | "intro" | "summary"）
            content: コメント本文
        """
        from datetime import datetime

        self.conn.execute(
            """
            INSERT INTO ai_comments (date, code, kind, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(date, code, kind) DO UPDATE SET
                content=excluded.content, created_at=excluded.created_at
            """,
            (date, code, kind, content, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        self.conn.commit()

    def get_ai_comments(self, date: str) -> dict[tuple[str, str], str]:
        """指定月の AI コメントを {(code, kind): content} 形式で取得する。

        Args:
            date: 対象月（"YYYY-MM-末" 形式）

        Returns:
            {(code, kind): content} の辞書。コメントなしは空辞書
        """
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.execute(
            "SELECT code, kind, content FROM ai_comments WHERE date = ?",
            (date,),
        )
        rows = cursor.fetchall()
        self.conn.row_factory = None
        return {(row["code"], row["kind"]): row["content"] for row in rows}

    def get_stock_meta(self) -> dict[str, dict]:
        """stock_meta テーブルから全銘柄メタ情報を取得する。

        Returns:
            {code: {"color": str, "market": str, "sort_order": int}} の辞書
        """
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.execute(
            "SELECT code, color, market, sort_order FROM stock_meta"
        )
        rows = cursor.fetchall()
        self.conn.row_factory = None
        return {
            row["code"]: {
                "color": row["color"],
                "market": row["market"],
                "sort_order": row["sort_order"],
            }
            for row in rows
        }

    def get_pnl_history_until(self, date: str) -> list[dict]:
        """指定月以前の全 monthly_pnl を日付昇順で取得する（totalHistory 構築用）。

        Args:
            date: 上限月（"YYYY-MM-末" 形式、この月を含む）

        Returns:
            monthly_pnl レコードのリスト（date 昇順）
        """
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.execute(
            "SELECT * FROM monthly_pnl WHERE date <= ? ORDER BY date",
            (date,),
        )
        rows = cursor.fetchall()
        self.conn.row_factory = None
        return [dict(row) for row in rows]

    def get_exchange_rate_for_month(
        self, pair: str, year: int, month: int
    ) -> float | None:
        """指定月の為替レートを取得する（対象月内のレートを優先、なければ最新）。

        Args:
            pair: 通貨ペア（例: "USD/JPY"）
            year: 年
            month: 月

        Returns:
            為替レート。取得できない場合は None
        """
        prefix = f"{year}-{month:02d}"
        self.conn.row_factory = sqlite3.Row
        # 対象月のレートを優先
        cursor = self.conn.execute(
            """
            SELECT rate FROM exchange_rates
            WHERE pair = ? AND date LIKE ?
            ORDER BY date DESC LIMIT 1
            """,
            (pair, f"{prefix}%"),
        )
        row = cursor.fetchone()
        if row:
            self.conn.row_factory = None
            return float(row["rate"])
        # 対象月になければ最新レートを取得
        cursor = self.conn.execute(
            """
            SELECT rate FROM exchange_rates
            WHERE pair = ?
            ORDER BY date DESC LIMIT 1
            """,
            (pair,),
        )
        row = cursor.fetchone()
        self.conn.row_factory = None
        return float(row["rate"]) if row else None

    def update_monthly_pnl_acquisition(self, rows: list[dict]) -> int:
        """monthly_pnl の取得系カラムのみを一括 UPDATE（バックフィル用）。

        purchase_history から再計算した shares/cost/acquired_price 系のみを
        更新し、current_price 系（保存済みの正しい市場データ）には触れない。

        Args:
            rows: UPDATE 対象の行のリスト。各要素は date, code, shares, cost,
                acquired_price, acquired_price_foreign, acquired_exchange_rate,
                value, profit, profit_rate, updated_at をキーに持つ dict。

        Returns:
            更新された行数（rowcount の合計）。
        """
        if not rows:
            return 0
        cursor = self.conn.executemany(
            """
            UPDATE monthly_pnl SET
                shares = :shares,
                cost = :cost,
                acquired_price = :acquired_price,
                acquired_price_foreign = :acquired_price_foreign,
                acquired_exchange_rate = :acquired_exchange_rate,
                value = :value,
                profit = :profit,
                profit_rate = :profit_rate,
                updated_at = :updated_at
            WHERE date = :date AND code = :code
            """,
            rows,
        )
        self.conn.commit()
        return cursor.rowcount

    def display_portfolio_summary(self, year: int, month: int) -> None:
        """ポートフォリオサマリーを表示"""
        records = self.get_performance_data(year, month)
        if not records:
            print("  データなし")
            return
        total_value = sum(r["value"] for r in records)
        total_profit = sum(r["profit"] for r in records)
        total_cost = sum(r["cost"] for r in records)
        profit_rate = (total_profit / total_cost * 100) if total_cost > 0 else 0
        print(f"\n  評価額合計: {total_value:,.0f}円")
        print(f"  損益合計: {total_profit:,.0f}円 ({profit_rate:.2f}%)")
        for r in sorted(records, key=lambda x: x["profit"], reverse=True):
            print(
                f"    {r['name']:10s} {r['profit']:>10,.0f}円 ({r['profit_rate']:.1f}%)"
            )
