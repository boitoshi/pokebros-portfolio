"""collectors.latest_snapshot と PortfolioDataCollector.collect_latest のテスト。

実ネットワーク（yfinance・為替）は使わず、すべてモックする。
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd

from collectors.db_writer import DbWriter
from collectors.latest_snapshot import compute_latest_row, extract_latest_prices

TODAY = date(2026, 10, 3)

LATEST_PNL_DDL = """
CREATE TABLE IF NOT EXISTS `latest_pnl` (
  `code` text PRIMARY KEY NOT NULL,
  `name` text NOT NULL,
  `currency` text NOT NULL,
  `price_date` text NOT NULL,
  `current_price` real NOT NULL,
  `current_price_foreign` real,
  `exchange_rate` real,
  `month_start_price_native` real,
  `shares` real NOT NULL,
  `cost` real NOT NULL,
  `acquired_price` real NOT NULL,
  `acquired_price_foreign` real,
  `value` real NOT NULL,
  `profit` real NOT NULL,
  `profit_rate` real NOT NULL,
  `updated_at` text NOT NULL
);
"""

HOLDINGS_DDL = """
CREATE TABLE holdings (
  id integer PRIMARY KEY AUTOINCREMENT NOT NULL,
  code text NOT NULL, name text NOT NULL, acquired_date text,
  acquired_price_jpy real NOT NULL, acquired_price_foreign real,
  acquired_exchange_rate real, shares real NOT NULL,
  currency text DEFAULT 'JPY' NOT NULL, is_foreign integer DEFAULT 0 NOT NULL,
  memo text, updated_at text
);
"""

PURCHASE_DDL = """
CREATE TABLE purchase_history (
  id integer PRIMARY KEY AUTOINCREMENT NOT NULL,
  code text NOT NULL, seq integer NOT NULL, shares real NOT NULL,
  price real NOT NULL, price_foreign real, exchange_rate real,
  purchased_at text NOT NULL
);
"""


def jp_purchases() -> list[dict]:
    return [
        {"code": "7974.T", "seq": 1, "shares": 1, "price": 7000.0,
         "price_foreign": None, "exchange_rate": None, "purchased_at": "2026-05-01"},
        # 当月の買付
        {"code": "7974.T", "seq": 2, "shares": 1, "price": 9000.0,
         "price_foreign": None, "exchange_rate": None, "purchased_at": "2026-10-01"},
    ]


def us_purchases() -> list[dict]:
    return [
        {"code": "NVDA", "seq": 1, "shares": 2, "price": 0.0,
         "price_foreign": 100.0, "exchange_rate": 150.0, "purchased_at": "2026-01-10"},
    ]


def _compute_jp(purchases: list[dict], month_start: float | None = 8000.0):
    return compute_latest_row(
        code="7974.T", name="任天堂", purchases=purchases,
        price_native=10000.0, price_date="2026-10-02",
        month_start_price_native=month_start, exchange_rate=None,
        currency="JPY", today=TODAY, updated_at="2026-10-03 09:00:00",
    )


def test_当月買付込みの株数とコスト() -> None:
    row = _compute_jp(jp_purchases())
    assert row is not None
    assert row["shares"] == 2
    assert row["cost"] == 16000.0
    assert row["acquired_price"] == 8000.0
    assert row["value"] == 20000.0
    assert row["profit"] == 4000.0
    assert row["profit_rate"] == 25.0
    assert row["current_price_foreign"] is None
    assert row["exchange_rate"] is None
    assert row["acquired_price_foreign"] is None


def test_株数0ならNone() -> None:
    future = [{**jp_purchases()[0], "purchased_at": "2026-11-01"}]
    assert _compute_jp(future) is None
    assert _compute_jp([]) is None


def test_外国株の円換算とnative取得単価() -> None:
    row = compute_latest_row(
        code="NVDA", name="NVIDIA", purchases=us_purchases(),
        price_native=200.0, price_date="2026-10-02",
        month_start_price_native=190.0, exchange_rate=155.0,
        currency="USD", today=TODAY, updated_at="x",
    )
    assert row is not None
    assert row["current_price"] == 31000.0
    assert row["current_price_foreign"] == 200.0
    assert row["exchange_rate"] == 155.0
    assert row["acquired_price_foreign"] == 100.0
    assert row["acquired_price"] == 15000.0
    assert row["cost"] == 30000.0
    assert row["value"] == 62000.0
    assert row["profit"] == 32000.0
    assert row["profit_rate"] == 106.67


def test_month_startが無いケース() -> None:
    row = _compute_jp(jp_purchases(), month_start=None)
    assert row is not None
    assert row["month_start_price_native"] is None

    # 当月の行が履歴に無ければ extract も None を返す
    idx = pd.to_datetime(["2026-09-28", "2026-09-30"])
    hist = pd.DataFrame({"Close": [100.0, 110.0]}, index=idx)
    assert extract_latest_prices(hist, 2026, 10) == (110.0, "2026-09-30", None)
    hist2 = pd.DataFrame(
        {"Close": [100.0, 120.0, 130.0]},
        index=pd.to_datetime(["2026-09-30", "2026-10-01", "2026-10-02"]),
    )
    assert extract_latest_prices(hist2, 2026, 10) == (130.0, "2026-10-02", 120.0)
    assert extract_latest_prices(pd.DataFrame({"Close": []}), 2026, 10) is None


def test_未確定のNaN行は無視して直前の確定値を使う() -> None:
    # yfinance は東証の当日行を Close=NaN で返すことがある
    hist = pd.DataFrame(
        {"Close": [7944.0, 7940.0, float("nan")]},
        index=pd.to_datetime(["2026-09-30", "2026-10-01", "2026-10-02"]),
    )
    assert extract_latest_prices(hist, 2026, 10) == (7940.0, "2026-10-01", 7940.0)
    all_nan = pd.DataFrame(
        {"Close": [float("nan")]}, index=pd.to_datetime(["2026-10-02"])
    )
    assert extract_latest_prices(all_nan, 2026, 10) is None


# ────────────────────────────────────────────────────────────
# collect_latest（yfinance・為替はモック）
# ────────────────────────────────────────────────────────────


def _make_collector(tmp_path):
    import main

    db_path = str(tmp_path / "t.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(LATEST_PNL_DDL + HOLDINGS_DDL + PURCHASE_DDL)
    for code, name, cur in [("7974.T", "任天堂", "JPY"), ("NVDA", "NVIDIA", "USD")]:
        conn.execute(
            "INSERT INTO holdings (code, name, acquired_price_jpy, shares, currency)"
            " VALUES (?, ?, 0, 1, ?)",
            (code, name, cur),
        )
    for p in jp_purchases() + us_purchases():
        conn.execute(
            "INSERT INTO purchase_history (code, seq, shares, price, price_foreign,"
            " exchange_rate, purchased_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (p["code"], p["seq"], p["shares"], p["price"], p["price_foreign"],
             p["exchange_rate"], p["purchased_at"]),
        )
    # holdings に無い銘柄の古い行
    conn.execute(
        "INSERT INTO latest_pnl VALUES ('OLD','旧','JPY','2026-01-01',1,NULL,NULL,"
        "NULL,1,1,1,NULL,1,0,0,'x')"
    )
    conn.commit()
    conn.close()

    collector = object.__new__(main.PortfolioDataCollector)
    collector.db_writer = DbWriter(db_path)
    converter = MagicMock()
    converter.get_currency_from_symbol.side_effect = (
        lambda s: "JPY" if s.endswith(".T") else "USD"
    )
    collector.stock_collector = SimpleNamespace(currency_converter=converter)
    return collector, converter


def _fake_ticker(code: str):
    hist = pd.DataFrame(
        {"Close": [8000.0, 10000.0] if code.endswith(".T") else [190.0, 200.0]},
        index=pd.to_datetime(["2026-10-01", "2026-10-02"]),
    )
    t = MagicMock()
    t.history.return_value = hist
    return t


def _rows(collector) -> dict[str, tuple]:
    cur = collector.db_writer.conn.execute(
        "SELECT code, profit, month_start_price_native FROM latest_pnl"
    )
    return {r[0]: r[1:] for r in cur.fetchall()}


def test_為替Noneの銘柄はスキップし他は保存_holdings外は削除(tmp_path) -> None:
    collector, converter = _make_collector(tmp_path)
    converter.get_exchange_rate.return_value = None
    with patch("main.yf.Ticker", side_effect=_fake_ticker), patch(
        "main.datetime"
    ) as dt:
        dt.now.return_value = datetime(2026, 10, 3, 9, 0, 0)
        ok = collector.collect_latest()
    assert ok is True
    rows = _rows(collector)
    assert set(rows) == {"7974.T"}  # NVDA スキップ・OLD 削除
    assert rows["7974.T"] == (4000.0, 8000.0)


def test_全銘柄失敗ならFalse(tmp_path) -> None:
    collector, converter = _make_collector(tmp_path)
    converter.get_exchange_rate.return_value = None
    empty = MagicMock()
    empty.history.return_value = pd.DataFrame({"Close": []})
    with patch("main.yf.Ticker", return_value=empty), patch("main.datetime") as dt:
        dt.now.return_value = datetime(2026, 10, 3, 9, 0, 0)
        assert collector.collect_latest() is False


def test_外国株も保存される(tmp_path) -> None:
    collector, converter = _make_collector(tmp_path)
    converter.get_exchange_rate.return_value = 155.0
    with patch("main.yf.Ticker", side_effect=_fake_ticker), patch(
        "main.datetime"
    ) as dt:
        dt.now.return_value = datetime(2026, 10, 3, 9, 0, 0)
        assert collector.collect_latest() is True
    rows = _rows(collector)
    assert set(rows) == {"7974.T", "NVDA"}
    assert rows["NVDA"] == (32000.0, 190.0)
