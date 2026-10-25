"""Google Sheets → SQLite 一方向同期モジュール"""

import os
import sqlite3
from datetime import datetime

import google.auth
import gspread
from google.auth import impersonated_credentials
from google.auth.credentials import Credentials as BaseCredentials
from google.oauth2.service_account import Credentials
from gspread.utils import ValueInputOption

from .stock_utils import get_currency_from_symbol, is_foreign_stock

SCOPES = [
    # 読み書き（--add-purchase の行追記に必要）
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _to_float(v: object) -> float:
    """数値の安全な変換（カンマ除去、空→0.0）"""
    if not v and v != 0:
        return 0.0
    s = str(v).replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _to_float_or_none(v: object) -> float | None:
    """数値の安全な変換（カンマ除去、空→None）"""
    if not v and v != 0:
        return None
    s = str(v).replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def load_sheets_credentials(
    credentials_path: str, impersonate_sa: str = ""
) -> BaseCredentials:
    """Sheets 用の認証情報を返す

    impersonate_sa があれば、実行環境の既定の認証情報から
    その SA になりすます（鍵ファイル不要）。
    無ければ従来どおり鍵ファイル（credentials_path）を使う。
    """
    if impersonate_sa:
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            # 既定の認証情報が鍵ファイルを指したままだと、
            # なりすましの元が鍵になってしまう
            raise ValueError(
                "SHEETS_IMPERSONATE_SA と GOOGLE_APPLICATION_CREDENTIALS が"
                "両方設定されています。なりすましに切り替えるなら"
                " GOOGLE_APPLICATION_CREDENTIALS を外してください"
            )
        source, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return impersonated_credentials.Credentials(
            source_credentials=source,
            target_principal=impersonate_sa,
            target_scopes=SCOPES,
        )
    return Credentials.from_service_account_file(credentials_path, scopes=SCOPES)


class SheetsSync:
    """Sheets のポートフォリオシートを SQLite の holdings / purchase_history に同期"""

    def __init__(
        self,
        credentials_path: str,
        spreadsheet_id: str,
        db_path: str,
        impersonate_sa: str = "",
    ) -> None:
        creds = load_sheets_credentials(credentials_path, impersonate_sa)
        gc = gspread.authorize(creds)
        self.spreadsheet = gc.open_by_key(spreadsheet_id)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")

    def _read_portfolio_rows(self) -> list[dict]:
        """ポートフォリオシートの全行を読み取る（同一セッション内はキャッシュ）"""
        if not hasattr(self, "_portfolio_cache"):
            sheet = self.spreadsheet.worksheet("ポートフォリオ")
            self._portfolio_cache: list[dict] = sheet.get_all_records()
        return self._portfolio_cache

    @staticmethod
    def _parse_row(row: dict) -> dict | None:
        """スプレッドシートの1行をパースする。銘柄コードが空なら None を返す。

        通貨・外国株フラグは銘柄コードから自動導出する（スプレッドシートの
        該当列は読まない）。手動列との不整合による誤判定を根絶するため。
        """
        code = str(row.get("銘柄コード", "")).strip()
        if not code:
            return None

        # 銘柄コードを唯一の真実として通貨・外国株判定を導出
        currency = get_currency_from_symbol(code)
        is_foreign = 1 if is_foreign_stock(code) else 0

        return {
            "code": code,
            "name": str(row.get("銘柄名", "")),
            "acquired_date": str(row.get("取得日", "")) or None,
            "acquired_price_jpy": _to_float(row.get("取得単価（円）")),
            "acquired_price_foreign": _to_float_or_none(row.get("取得単価（外貨）")),
            "acquired_exchange_rate": _to_float_or_none(row.get("取得時為替レート")),
            "shares": _to_float(row.get("保有株数")),
            "currency": currency,
            "is_foreign": is_foreign,
            "memo": str(row.get("備考", "")) or None,
            "updated_at": str(row.get("最終更新", "")) or datetime.now().isoformat(),
        }

    def sync_holdings(self) -> int:
        """ポートフォリオシート → holdings テーブルに同期。

        同一銘柄コードの複数行を集約し、加重平均取得価額と合計株数で1行にまとめる。
        挿入件数（銘柄数）を返す。
        """
        records = self._read_portfolio_rows()

        # 銘柄コードごとにグループ化
        groups: dict[str, list[dict]] = {}
        for row in records:
            parsed = self._parse_row(row)
            if not parsed:
                continue
            groups.setdefault(parsed["code"], []).append(parsed)

        # 全削除 → 集約して挿入
        self.conn.execute("DELETE FROM holdings")

        count = 0
        for code, rows in groups.items():
            total_shares = sum(r["shares"] for r in rows)
            # 加重平均取得価額（円）= Σ(取得単価 × 株数) / 合計株数
            if total_shares > 0:
                avg_price_jpy = (
                    sum(r["acquired_price_jpy"] * r["shares"] for r in rows)
                    / total_shares
                )
            else:
                avg_price_jpy = rows[0]["acquired_price_jpy"]

            # 外貨建ての加重平均（外貨価格がある行のみ）
            foreign_rows = [r for r in rows if r["acquired_price_foreign"]]
            if foreign_rows:
                foreign_shares = sum(r["shares"] for r in foreign_rows)
                avg_price_foreign: float | None = (
                    sum(
                        r["acquired_price_foreign"] * r["shares"]  # type: ignore[operator]
                        for r in foreign_rows
                    )
                    / foreign_shares
                    if foreign_shares > 0
                    else foreign_rows[0]["acquired_price_foreign"]
                )
                avg_exchange_rate: float | None = (
                    sum(
                        r["acquired_exchange_rate"] * r["shares"]  # type: ignore[operator]
                        for r in foreign_rows
                    )
                    / foreign_shares
                    if foreign_shares > 0
                    else foreign_rows[0]["acquired_exchange_rate"]
                )
            else:
                avg_price_foreign = rows[0]["acquired_price_foreign"]
                avg_exchange_rate = rows[0]["acquired_exchange_rate"]

            # 最も古い取得日を使用
            dates = [r["acquired_date"] for r in rows if r["acquired_date"]]
            earliest_date = min(dates) if dates else None

            # 最初の行からメタ情報を取得（通貨・外国株フラグは銘柄コード由来で全行同一）
            first = rows[0]

            self.conn.execute(
                """
                INSERT INTO holdings (code, name, acquired_date, acquired_price_jpy,
                    acquired_price_foreign, acquired_exchange_rate, shares,
                    currency, is_foreign, memo, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    code,
                    first["name"],
                    earliest_date,
                    round(avg_price_jpy, 2),
                    round(avg_price_foreign, 2) if avg_price_foreign else None,
                    round(avg_exchange_rate, 4) if avg_exchange_rate else None,
                    total_shares,
                    first["currency"],
                    first["is_foreign"],
                    first["memo"],
                    first["updated_at"],
                ),
            )
            count += 1

        self.conn.commit()
        print(f"  holdings テーブルに {count} 件同期しました")
        return count

    def sync_purchase_history(self) -> int:
        """ポートフォリオシート → purchase_history テーブルに同期。

        同一銘柄コードの行を取得日順に並べ、seq（購入回）を振って保存する。
        挿入件数を返す。
        """
        records = self._read_portfolio_rows()

        # 銘柄コードごとにグループ化
        groups: dict[str, list[dict]] = {}
        for row in records:
            parsed = self._parse_row(row)
            if not parsed:
                continue
            groups.setdefault(parsed["code"], []).append(parsed)

        # 全削除 → 全挿入
        self.conn.execute("DELETE FROM purchase_history")

        count = 0
        for code, rows in groups.items():
            # 取得日でソート（空文字は末尾に）
            sorted_rows = sorted(
                rows, key=lambda r: r["acquired_date"] or "9999-99-99"
            )

            for seq, r in enumerate(sorted_rows, start=1):
                self.conn.execute(
                    """
                    INSERT INTO purchase_history
                        (code, seq, shares, price, price_foreign,
                         exchange_rate, purchased_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        code,
                        seq,
                        r["shares"],
                        r["acquired_price_jpy"],
                        r["acquired_price_foreign"],
                        r["acquired_exchange_rate"],
                        r["acquired_date"] or "",
                    ),
                )
                count += 1

        self.conn.commit()
        print(f"  purchase_history テーブルに {count} 件同期しました")
        return count

    def append_purchase_row(
        self,
        code: str,
        purchase_date: str,
        shares: int,
        price_jpy: float | None = None,
        price_foreign: float | None = None,
        exchange_rate: float | None = None,
    ) -> str:
        """ポートフォリオシートに買付行を追記し、銘柄名を返す。

        既存の銘柄コードへの追加購入のみをサポートする。銘柄名は同一銘柄コードの
        既存行から引き継ぐため、シートに未登録の銘柄コードは追記できない
        （新規銘柄はシートを直接編集して最初の1行を作成すること）。

        Args:
            code: 銘柄コード（例: 7974.T, NVDA）
            purchase_date: 取得日（"YYYY-MM-DD"）
            shares: 保有株数
            price_jpy: 取得単価（円）。日本株の場合に指定する
            price_foreign: 取得単価（外貨）。外国株の場合に指定する
            exchange_rate: 取得時為替レート。外国株の場合に指定する

        Returns:
            シートから引き継いだ銘柄名

        Raises:
            ValueError: シートに必須列が無い、または銘柄コードが未知の場合
        """
        sheet = self.spreadsheet.worksheet("ポートフォリオ")
        header = sheet.row_values(1)
        col_index = {name: i for i, name in enumerate(header)}

        required_columns = (
            "銘柄コード",
            "銘柄名",
            "取得日",
            "取得単価（円）",
            "取得単価（外貨）",
            "取得時為替レート",
            "保有株数",
        )
        missing = [c for c in required_columns if c not in col_index]
        if missing:
            raise ValueError(
                f"シートに必須列が見つかりません: {', '.join(missing)}"
            )

        # 銘柄名は既存行から引き継ぐ（銘柄コードを唯一の真実として扱う方針に合わせる）
        name: str | None = None
        for row in self._read_portfolio_rows():
            if str(row.get("銘柄コード", "")).strip() == code:
                name = str(row.get("銘柄名", ""))
                break
        if name is None:
            raise ValueError(
                f"未知の銘柄コードです: {code}（シートに既存行が必要です）"
            )

        values: list[str | int | float] = [""] * len(header)
        values[col_index["銘柄コード"]] = code
        values[col_index["銘柄名"]] = name
        values[col_index["取得日"]] = purchase_date
        values[col_index["保有株数"]] = shares
        if "最終更新" in col_index:
            values[col_index["最終更新"]] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        if price_jpy is not None:
            # 日本株: 円建て単価のみ設定し、外貨2列は空のままにする
            values[col_index["取得単価（円）"]] = price_jpy
        else:
            # 外国株: 円建て単価は空のまま（sync 時に price=0.0 になる既存規約と一致）
            if price_foreign is None or exchange_rate is None:
                raise ValueError(
                    "外国株は取得単価（外貨）と取得時為替レートの両方が必要です"
                )
            values[col_index["取得単価（外貨）"]] = price_foreign
            values[col_index["取得時為替レート"]] = exchange_rate

        sheet.append_row(
            values,
            value_input_option=ValueInputOption.user_entered,
            table_range="A1",
        )

        # キャッシュ破棄: 破棄しないと直後の sync が追記前のキャッシュを読んで
        # 新行が DB に反映されない
        if hasattr(self, "_portfolio_cache"):
            del self._portfolio_cache

        return name

    def close(self) -> None:
        self.conn.close()
