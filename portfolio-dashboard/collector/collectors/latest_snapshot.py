"""トップページ用「最新スナップショット」（latest_pnl）の計算モジュール。

DB・ネットワークに依存しない純粋関数のみを置く。monthly_pnl 等の月次データには
一切触れず、今日時点の株価・保有から 1 銘柄 1 行を組み立てる。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .purchase_math import cumulative_position
from .stock_utils import is_foreign_stock


def extract_latest_prices(
    history: Any, year: int, month: int
) -> tuple[float, str, float | None] | None:
    """yfinance の history（DataFrame）から最新値と当月初値を取り出す。

    Returns:
        (最新 Close, 最終取引日 "YYYY-MM-DD", 当月最初の取引日の Close or None)。
        データが空なら None。
    """
    if history is None or len(history) == 0:
        return None
    # yfinance は未確定の当日行を Close=NaN で返すことがある（東証で実際に発生）。
    # NaN を最新値にすると current_price が NULL になるため、確定済みの行だけを使う
    history = history.dropna(subset=["Close"])
    if len(history) == 0:
        return None

    last_close = float(history["Close"].iloc[-1])
    price_date = history.index[-1].strftime("%Y-%m-%d")

    month_start: float | None = None
    for idx, close in zip(history.index, history["Close"], strict=True):
        if idx.year == year and idx.month == month:
            month_start = float(close)
            break

    return last_close, price_date, month_start


def compute_latest_row(
    *,
    code: str,
    name: str,
    purchases: list[dict],
    price_native: float,
    price_date: str,
    month_start_price_native: float | None,
    exchange_rate: float | None,
    currency: str,
    today: date,
    updated_at: str | None = None,
) -> dict | None:
    """latest_pnl の 1 行を計算する（純粋関数）。

    当月の買付まで含めた累積ポジションから算出する。保有株数 0 なら None。
    式・丸めは pnl_repair.compute_row_update と同じ。

    Args:
        exchange_rate: 外国株では必須（None は呼び出し側でスキップする）。
            日本株では無視される。
    """
    is_foreign = is_foreign_stock(code)
    pos = cumulative_position(purchases, today.year, today.month, is_foreign=is_foreign)
    if pos.shares == 0:
        return None

    if is_foreign:
        if not exchange_rate:
            raise ValueError(f"{code}: 外国株には為替レートが必要です")
        current_price = price_native * exchange_rate
        current_price_foreign: float | None = price_native
        rate: float | None = exchange_rate
        acquired_price_foreign: float | None = pos.avg_price_native
    else:
        current_price = price_native
        current_price_foreign = None
        rate = None
        acquired_price_foreign = None

    shares = pos.shares
    cost = pos.cost_jpy
    value = round(current_price * shares, 2)
    profit = round(value - cost, 2)
    profit_rate = round(profit / cost * 100, 2) if cost > 0 else 0.0

    return {
        "code": code,
        "name": name,
        "currency": currency,
        "price_date": price_date,
        "current_price": current_price,
        "current_price_foreign": current_price_foreign,
        "exchange_rate": rate,
        "month_start_price_native": month_start_price_native,
        "shares": shares,
        "cost": cost,
        "acquired_price": pos.avg_price_jpy,
        "acquired_price_foreign": acquired_price_foreign,
        "value": value,
        "profit": profit,
        "profit_rate": profit_rate,
        "updated_at": updated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
