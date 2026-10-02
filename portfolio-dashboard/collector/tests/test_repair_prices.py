"""repair_prices のテスト（ネットワーク禁止・yfinance はモック）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

import repair_prices as rp
from collectors.stock_collector import StockDataCollector

MIGRATIONS = Path(__file__).resolve().parents[2] / "server" / "drizzle" / "migrations"


def make_db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "t.db")
    for sql in sorted(MIGRATIONS.glob("*.sql")):
        for stmt in sql.read_text().split("--> statement-breakpoint"):
            conn.execute(stmt)
    conn.commit()
    return conn


def daily(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    """(日付, Close, High, Low, Volume) から日足を作る。"""
    idx = pd.DatetimeIndex([r[0] for r in rows], tz="Asia/Tokyo")
    return pd.DataFrame(
        {
            "Close": [r[1] for r in rows],
            "High": [r[2] for r in rows],
            "Low": [r[3] for r in rows],
            "Volume": [r[4] for r in rows],
        },
        index=idx,
    )


JP_DF = daily(
    [
        ("2023-07-03", 6000.0, 6100.0, 5900.0, 1000),
        ("2023-07-31", 6450.0, 6500.0, 6000.0, 3000),
    ]
)
US_DF = daily(
    [
        ("2023-07-03", 100.0, 110.0, 95.0, 10),
        ("2023-07-31", 120.0, 125.0, 99.0, 30),
    ]
)


def seed_jp(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO monthly_pnl (date, code, name, acquired_price, current_price,"
        " shares, cost, value, profit, profit_rate, currency,"
        " acquired_price_foreign, current_price_foreign, acquired_exchange_rate,"
        " current_exchange_rate) VALUES ('2023-07-末','7974.T','任天堂',6000,6172.4,"
        "2,12000,12344.8,344.8,2.87,'JPY',6000,6172.4,1.0,1.0)"
    )
    conn.execute(
        "INSERT INTO monthly_prices (date, code, price_jpy, high, low, average,"
        " change_rate, avg_volume) VALUES ('2023-07-31','7974.T',6172.4,6400,5800,"
        "6000,5,2000)"
    )
    conn.commit()


def seed_us(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO monthly_pnl (date, code, name, acquired_price, current_price,"
        " shares, cost, value, profit, profit_rate, currency,"
        " acquired_price_foreign, current_price_foreign, acquired_exchange_rate,"
        " current_exchange_rate) VALUES ('2023-07-末','NVDA','NVIDIA',14000,16000,"
        "2,28000,32000,4000,14.29,'USD',100,110,140,150)"
    )
    conn.execute(
        "INSERT INTO monthly_prices (date, code, price_jpy, high, low, average,"
        " change_rate, avg_volume) VALUES ('2023-07-31','NVDA',16500,17000,14000,"
        "15000,5,20)"
    )
    conn.commit()


def patch_fetch(monkeypatch: pytest.MonkeyPatch, data: dict) -> None:
    monkeypatch.setattr(rp, "fetch_history", lambda code, a, b: data.get(code))


def test_month_metrics_matches_calculate_stock_metrics() -> None:
    m = rp.month_metrics(JP_DF)
    ref = StockDataCollector().calculate_stock_metrics(JP_DF, "7974.T", 6000, 1.0, 2)
    assert ref is not None
    assert m["end_close"] == ref["month_end_price"]
    assert m["high"] == ref["highest_price"]
    assert m["low"] == ref["lowest_price"]
    assert m["avg_close"] == ref["average_price"]
    assert m["change_rate"] == ref["monthly_change"]
    assert m["avg_volume"] == ref["average_volume"]


def test_nan_rows_are_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    df = JP_DF.copy()
    df.loc[df.index[0], "Close"] = float("nan")

    class T:
        def __init__(self, code: str) -> None: ...
        def history(self, **kw: object) -> pd.DataFrame:
            return df

    monkeypatch.setattr(rp.yf, "Ticker", T)
    out = rp.fetch_history("7974.T", (2023, 7), (2023, 7))
    assert out is not None and len(out) == 1


def test_jp_plan_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = make_db(tmp_path)
    seed_jp(conn)
    patch_fetch(monkeypatch, {"7974.T": JP_DF})
    plan = rp.build_plan(conn)
    assert len(plan["pnl"]) == 1 and len(plan["prices"]) == 1
    s = plan["pnl"][0]["set"]
    assert s["current_price"] == 6450.0
    assert s["value"] == 12900.0
    assert s["profit"] == 900.0
    assert s["profit_rate"] == 7.5
    p = plan["prices"][0]["set"]
    assert p["price_jpy"] == 6450.0 and p["high"] == 6500.0 and p["low"] == 5900.0
    assert p["average"] == 6225.0 and p["change_rate"] == 7.5
    assert p["avg_volume"] == 2000

    rp.apply_plan(conn, plan)
    again = rp.build_plan(conn)
    assert again["pnl"] == [] and again["prices"] == []
    assert conn.execute("SELECT updated_at FROM monthly_pnl").fetchone()[0]


def test_foreign_plan_uses_stored_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = make_db(tmp_path)
    seed_us(conn)
    patch_fetch(monkeypatch, {"NVDA": US_DF})
    plan = rp.build_plan(conn)
    s = plan["pnl"][0]["set"]
    assert s["current_price_foreign"] == 120.0
    assert s["current_price"] == 18000.0  # 120 x 150
    assert s["value"] == 36000.0
    assert s["profit"] == 8000.0
    # prices: 旧 16500 / 旧 native 110 = 150 で換算
    p = plan["prices"][0]["set"]
    assert p["price_jpy"] == 18000.0
    assert p["high"] == 18750.0 and p["low"] == 14250.0
    rp.apply_plan(conn, plan)
    again = rp.build_plan(conn)
    assert again["pnl"] == [] and again["prices"] == []


def test_prices_only_foreign_uses_exchange_rates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = make_db(tmp_path)
    conn.execute(
        "INSERT INTO monthly_prices (date, code, price_jpy, high, low, average,"
        " change_rate, avg_volume) VALUES ('2023-07-31','NVDA',16500,17000,14000,"
        "15000,5,20)"
    )
    conn.execute(
        "INSERT INTO exchange_rates (date, pair, rate) VALUES "
        "('2023-07-31','USD/JPY',150)"
    )
    conn.commit()
    patch_fetch(monkeypatch, {"NVDA": US_DF})
    plan = rp.build_plan(conn)
    assert plan["pnl"] == []
    assert plan["prices"][0]["set"]["price_jpy"] == 18000.0


def test_prices_only_foreign_without_rate_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = make_db(tmp_path)
    conn.execute(
        "INSERT INTO monthly_prices (date, code, price_jpy) "
        "VALUES ('2023-07-31','NVDA',16500)"
    )
    conn.commit()
    patch_fetch(monkeypatch, {"NVDA": US_DF})
    plan = rp.build_plan(conn)
    assert plan["prices"] == []


def test_split_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conn = make_db(tmp_path)
    seed_jp(conn)
    half = JP_DF.copy()
    half[["Close", "High", "Low"]] = half[["Close", "High", "Low"]] / 4
    patch_fetch(monkeypatch, {"7974.T": half})
    plan = rp.build_plan(conn)
    assert plan["split_suspects"]
    monkeypatch.setattr(
        "sys.argv", ["repair_prices", "--db", str(tmp_path / "t.db"), "--apply"]
    )
    assert rp.main() == 2
    row = conn.execute("SELECT current_price FROM monthly_pnl").fetchone()
    assert row[0] == 6172.4  # 書き込まれていない


def test_missing_daily_skips_ticker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = make_db(tmp_path)
    seed_jp(conn)
    seed_us(conn)
    # NVDA は対象月の取引行が無い、7974.T は日足なし
    other = daily([("2023-08-01", 100.0, 101.0, 99.0, 1)])
    patch_fetch(monkeypatch, {"NVDA": other})
    plan = rp.build_plan(conn)
    assert set(plan["skipped"]) == {"7974.T", "NVDA"}
    assert plan["pnl"] == [] and plan["prices"] == []
