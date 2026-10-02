"""過去の株価を yfinance の未調整終値に揃え直す単発修正ツール。

背景:
    2023-07〜2025-08 の日本株の月末価格が、yfinance の配当調整後終値で保存されている
    （過去のバックフィルが auto_adjust 既定で動いた名残り）。
    現行の月次収集は auto_adjust=False を明示済みで、2025-09 以降は未調整のまま。

このスクリプトが直すもの:
    monthly_pnl:    current_price / current_price_foreign / value / profit /
                    profit_rate / updated_at
    monthly_prices: price_jpy / high / low / average / change_rate / avg_volume

直さないもの:
    為替（current_exchange_rate / exchange_rates）、取得系（shares / cost /
    acquired_*）、benchmark_data、ai_comments、その他のテーブル

円換算レートは「その行に保存済みの値」を使う（repair_fx.py と同じ考え方）:
    pnl:    current_exchange_rate（日本株は 1.0）
    prices: 旧 price_jpy ÷ 旧 native を行ごとに復元。旧 native は同月 pnl の
            current_price_foreign、無ければ同月 exchange_rates の通貨/JPY で割り戻す。

安全策:
    - 日足が取れない銘柄／対象月に取引行が無い月がある銘柄は丸ごとスキップ
    - 新旧 native の比が 0.5 未満または 2 超の行が1つでもあれば、--apply でも
      書き込まず非0終了（株式分割の取り違え検出）

実行:
    uv run python repair_prices.py --db /path/to/portfolio.db            # ドライラン
    uv run python repair_prices.py --db /path/to/portfolio.db --apply    # 書き込み
"""

from __future__ import annotations

import argparse
import calendar
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

import pandas as pd
import yfinance as yf

from collectors.currency_converter import CurrencyConverter

DECIMALS = 2
# これ未満の変化は「変更なし」とみなす（冪等性のため）
MIN_DIFF = 0.01
# prices の円換算は旧 price_jpy ÷ 旧 native で復元したレートを使うため、
# 再実行時に丸めで数銭〜数円揺れる。その揺れを変更と見なさない許容値
PRICES_TOLERANCE = 0.05
SPLIT_RATIO_MIN = 0.5
SPLIT_RATIO_MAX = 2.0

Month = tuple[int, int]


def parse_pnl_date(pnl_date: str) -> Month:
    """'YYYY-MM-末' から (年, 月) を取り出す。"""
    year_s, month_s, _ = pnl_date.split("-")
    return int(year_s), int(month_s)


def parse_price_date(price_date: str) -> Month:
    """'YYYY-MM-DD' から (年, 月) を取り出す。"""
    year_s, month_s, _ = price_date.split("-")
    return int(year_s), int(month_s)


def month_end_str(year: int, month: int) -> str:
    return f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def month_metrics(df_month: pd.DataFrame) -> dict[str, float]:
    """1か月分の日足から native 通貨ベースの指標を計算する純粋関数。

    stock_collector.calculate_stock_metrics と同じ式（円換算前）。
    """
    start = float(df_month["Close"].iloc[0])
    end = float(df_month["Close"].iloc[-1])
    return {
        "start_close": start,
        "end_close": end,
        "high": float(df_month["High"].max()),
        "low": float(df_month["Low"].min()),
        "avg_close": float(df_month["Close"].mean()),
        "change_rate": round(((end / start) - 1) * 100, DECIMALS),
        "avg_volume": int(df_month["Volume"].mean()),
    }


def fetch_history(code: str, first: Month, last: Month) -> pd.DataFrame | None:
    """全期間の日足（未調整）を1回で取得する。テストではここをモックする。"""
    start = datetime(first[0], first[1], 1)
    end = datetime(last[0] + (last[1] == 12), last[1] % 12 + 1, 1)
    try:
        df = yf.Ticker(code).history(start=start, end=end, auto_adjust=False)
    except Exception as e:
        print(f"⚠️ {code}: 日足取得エラー: {e}")
        return None
    if df is None or df.empty:
        return None
    return df.dropna(subset=["Close"])


def slice_month(df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    mask = [(ts.year, ts.month) == (year, month) for ts in df.index]
    return df[mask]


def _differs(old: float | None, new: float, tol: float = MIN_DIFF) -> bool:
    if old is None:
        return True
    return round(abs(float(old) - new), 4) >= tol


def _price_tolerance(col: str, val: float, currency: str) -> float:
    if col == "avg_volume":
        return 1.0
    if currency == "JPY":
        return MIN_DIFF
    # 外貨行は復元レートの丸め揺れ（相対 1e-4 程度）を許容する
    return max(PRICES_TOLERANCE, abs(val) * 1e-4)


def build_plan(conn: sqlite3.Connection) -> dict:
    """修正計画を組み立てる（DB は変更しない）。

    Returns:
        {"pnl": [...], "prices": [...], "skipped": {code: 理由},
         "split_suspects": [...], "counts": {code: {...}}}
    """
    conn.row_factory = sqlite3.Row
    pnl_rows = conn.execute("SELECT * FROM monthly_pnl ORDER BY date, code").fetchall()
    price_rows = conn.execute(
        "SELECT * FROM monthly_prices ORDER BY date, code"
    ).fetchall()
    fx = {
        (r["date"], r["pair"]): float(r["rate"])
        for r in conn.execute("SELECT date, pair, rate FROM exchange_rates")
    }

    pnl_by_key = {(r["code"], parse_pnl_date(r["date"])): r for r in pnl_rows}
    price_by_key = {(r["code"], parse_price_date(r["date"])): r for r in price_rows}

    months_by_code: dict[str, set[Month]] = defaultdict(set)
    for code, ym in [*pnl_by_key, *price_by_key]:
        months_by_code[code].add(ym)

    converter = CurrencyConverter()
    plan: dict = {
        "pnl": [],
        "prices": [],
        "skipped": {},
        "split_suspects": [],
        "counts": {},
    }

    for code in sorted(months_by_code):
        months = sorted(months_by_code[code])
        df = fetch_history(code, months[0], months[-1])
        if df is None:
            plan["skipped"][code] = "日足が取得できません"
            continue
        monthly = {ym: slice_month(df, *ym) for ym in months}
        missing = [ym for ym, m in monthly.items() if m.empty]
        if missing:
            labels = ", ".join(f"{y}-{m:02d}" for y, m in missing)
            plan["skipped"][code] = f"取引行が無い月があります: {labels}"
            continue

        pnl_plan: list[dict] = []
        price_plan: list[dict] = []
        suspects: list[dict] = []
        warnings: list[str] = []

        for ym in months:
            met = month_metrics(monthly[ym])
            new_native = round(met["end_close"], DECIMALS)
            pnl = pnl_by_key.get((code, ym))
            price = price_by_key.get((code, ym))
            old_native_pnl: float | None = None

            if pnl is not None:
                is_jpy = (pnl["currency"] or "JPY") == "JPY"
                rate = 1.0 if is_jpy else float(pnl["current_exchange_rate"] or 0)
                if rate <= 0:
                    warnings.append(f"{pnl['date']} {code}: 為替が不正のため pnl 除外")
                else:
                    cpf = pnl["current_price_foreign"]
                    old_native_pnl = (
                        float(cpf) if cpf else float(pnl["current_price"]) / rate
                    )
                    ratio = new_native / old_native_pnl if old_native_pnl else 0.0
                    if not (SPLIT_RATIO_MIN <= ratio <= SPLIT_RATIO_MAX):
                        suspects.append(
                            {"month": pnl["date"], "code": code, "ratio": ratio}
                        )
                    new_price = round(new_native * rate, DECIMALS)
                    shares = float(pnl["shares"])
                    cost = float(pnl["cost"])
                    # pnl_repair.compute_row_update と同じ式・丸め
                    new_value = round(new_price * shares, DECIMALS)
                    new_profit = round(new_value - cost, DECIMALS)
                    new_rate = (
                        round(new_profit / cost * 100, DECIMALS) if cost > 0 else 0.0
                    )
                    # 外貨行は保存済みレートが2桁丸めで、旧 value は未丸めレート由来。
                    # 円側の差で判定すると native 不変でも毎回揺れるので、
                    # 外貨行は native の変化だけを変更条件にする
                    if _differs(old_native_pnl, new_native) or (
                        is_jpy and _differs(pnl["current_price"], new_price)
                    ):
                        pnl_plan.append(
                            {
                                "date": pnl["date"],
                                "code": code,
                                "old_native": old_native_pnl,
                                "new_native": new_native,
                                "old_value": float(pnl["value"]),
                                "new_value": new_value,
                                "old_profit_rate": float(pnl["profit_rate"]),
                                "new_profit_rate": new_rate,
                                "set": {
                                    "current_price": new_price,
                                    "current_price_foreign": new_native,
                                    "value": new_value,
                                    "profit": new_profit,
                                    "profit_rate": new_rate,
                                },
                            }
                        )

            if price is not None:
                price_date = price["date"]
                old_jpy = float(price["price_jpy"])
                currency = (
                    (pnl["currency"] if pnl is not None else None)
                    or converter.get_currency_from_symbol(code)
                    or "JPY"
                )
                if currency == "JPY":
                    p_rate = 1.0
                    old_native = old_jpy
                elif old_native_pnl:
                    old_native = old_native_pnl
                    p_rate = old_jpy / old_native
                else:
                    p_rate = fx.get((price_date, f"{currency}/JPY"), 0.0)
                    if p_rate <= 0:
                        warnings.append(
                            f"{price_date} {code}: 旧 native が分からず為替も無いため"
                            " prices をスキップ"
                        )
                        continue
                    old_native = old_jpy / p_rate
                if pnl is None or old_native_pnl is None:
                    ratio = new_native / old_native if old_native else 0.0
                    if not (SPLIT_RATIO_MIN <= ratio <= SPLIT_RATIO_MAX):
                        suspects.append(
                            {"month": price_date, "code": code, "ratio": ratio}
                        )
                new_vals = {
                    "price_jpy": round(new_native * p_rate, DECIMALS),
                    "high": round(met["high"] * p_rate, DECIMALS),
                    "low": round(met["low"] * p_rate, DECIMALS),
                    "average": round(met["avg_close"] * p_rate, DECIMALS),
                    "change_rate": met["change_rate"],
                    "avg_volume": float(met["avg_volume"]),
                }
                changed = any(
                    _differs(
                        price[col],
                        val,
                        _price_tolerance(col, val, currency),
                    )
                    for col, val in new_vals.items()
                )
                if changed:
                    price_plan.append(
                        {"date": price_date, "code": code, "set": new_vals}
                    )

        for w in warnings:
            print(f"⚠️ {w}")
        plan["pnl"].extend(pnl_plan)
        plan["prices"].extend(price_plan)
        plan["split_suspects"].extend(suspects)
        plan["counts"][code] = {
            "pnl": len(pnl_plan),
            "prices": len(price_plan),
            "value_diff": sum(c["new_value"] - c["old_value"] for c in pnl_plan),
        }

    return plan


def print_plan(plan: dict) -> None:
    for code, reason in plan["skipped"].items():
        print(f"⚠️ {code}: 銘柄ごとスキップ（{reason}）")
    for s in plan["split_suspects"]:
        print(
            f"❌ 分割の取り違え疑い: {s['month']} {s['code']} "
            f"新旧 native 比 {s['ratio']:.3f}"
        )

    if plan["pnl"]:
        print(
            f"{'月':<12} {'銘柄':<8} {'旧native':>11} {'新native':>11} "
            f"{'評価額差':>11} {'損益率':>17}"
        )
        print("-" * 78)
        for c in plan["pnl"]:
            old = c["old_native"]
            old_s = f"{old:>11,.2f}" if old is not None else f"{'-':>11}"
            print(
                f"{c['date']:<12} {c['code']:<8} {old_s} {c['new_native']:>11,.2f} "
                f"{c['new_value'] - c['old_value']:>+11,.0f} "
                f"{c['old_profit_rate']:>7.2f}% → {c['new_profit_rate']:>6.2f}%"
            )
    print(f"\nmonthly_prices 更新: {len(plan['prices'])}件")
    print("\n銘柄別:")
    for code, c in plan["counts"].items():
        print(
            f"  {code:<8} pnl {c['pnl']:>3}件 / prices {c['prices']:>3}件 / "
            f"評価額差 {c['value_diff']:>+13,.0f}円"
        )
    total = sum(c["value_diff"] for c in plan["counts"].values())
    print(f"  評価額差の合計: {total:+,.0f}円")


def apply_plan(conn: sqlite3.Connection, plan: dict) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with conn:  # 1トランザクション
        for c in plan["pnl"]:
            cols = ", ".join(f"{k} = ?" for k in c["set"])
            conn.execute(
                f"UPDATE monthly_pnl SET {cols}, updated_at = ? "
                "WHERE date = ? AND code = ?",
                (*c["set"].values(), now, c["date"], c["code"]),
            )
        for c in plan["prices"]:
            cols = ", ".join(f"{k} = ?" for k in c["set"])
            conn.execute(
                f"UPDATE monthly_prices SET {cols} WHERE date = ? AND code = ?",
                (*c["set"].values(), c["date"], c["code"]),
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="過去の株価を未調整終値に揃え直す")
    parser.add_argument("--db", required=True, help="portfolio.db のパス")
    parser.add_argument(
        "--apply", action="store_true", help="実際に書き込む（既定はドライラン）"
    )
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    plan = build_plan(conn)

    if not plan["pnl"] and not plan["prices"] and not plan["split_suspects"]:
        print("修正が必要な行はありません。")
        for code, reason in plan["skipped"].items():
            print(f"⚠️ {code}: スキップ（{reason}）")
        return 0

    print_plan(plan)

    if plan["split_suspects"]:
        print("\n❌ 分割の取り違えの疑いがあるため、書き込まずに終了します。")
        return 2

    if not args.apply:
        print("\nドライラン。書き込むには --apply を付ける。")
        return 0

    try:
        apply_plan(conn, plan)
    except sqlite3.Error as e:
        print(f"❌ 書き込みに失敗しました: {e}")
        return 1
    n_pnl, n_prices = len(plan["pnl"]), len(plan["prices"])
    print(f"\n✅ pnl {n_pnl}件 / prices {n_prices}件を更新しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
