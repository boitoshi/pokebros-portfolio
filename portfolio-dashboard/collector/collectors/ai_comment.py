"""Claude Sonnet を使った月次投資ブログ用AIコメント生成モジュール。

記事全体の重複や期間の異なる数値同士の比較を避けるため、導入文と全銘柄の
コメントを1回のAPI呼び出しでまとめて生成する。プロンプトに渡した数値以外の
ニュース・イベント・値動き理由は扱わない。
"""

from __future__ import annotations

import json
import re
from typing import Any

import anthropic

_HALLUCINATION_GUARD = (
    "入力で与えられた数値・事実のみに言及してください。"
    "ニュース・イベント・決算・製品発表などの出来事や、値動きの理由は"
    "入力に含まれていても扱わないでください。推測も一切禁止です。"
)

_STYLE_GUARD = (
    "記事全体を一つの文章として考え、導入と銘柄別コメントで同じ数値・説明・"
    "感想を繰り返さないでください。投資用語の初心者向け解説は不要です。"
    "ポケモン・推し活・お布施に触れる表現は記事全体で最大1箇所にしてください。"
    "読者に投資やお布施投資を勧める文は書かないでください。"
)

_FORBIDDEN_OUTPUT_TERMS = (
    "ニュース",
    "イベント",
    "決算",
    "製品発表",
    "新製品",
    "業績",
    "材料",
    "値動きの理由",
    "上昇理由",
    "下落理由",
    "要因",
    "背景",
    "日経",
    "S&P",
    "市場全体",
    "市況",
    "USD/JPY",
    "ドル円",
    "為替の影響",
)


def _format_market_context(market_context: dict | None) -> str:
    """市況辞書を、期間を明示したプロンプト用テキストに整形する。"""
    market_context = market_context or {}
    lines: list[str] = []

    nikkei_change = market_context.get("nikkei_change")
    if nikkei_change is not None:
        lines.append(f"  - 日経平均株価の月間騰落率: {nikkei_change:+.2f}%")

    sp500_change = market_context.get("sp500_change")
    if sp500_change is not None:
        lines.append(f"  - S&P500の月間騰落率: {sp500_change:+.2f}%")

    usdjpy_rate = market_context.get("usdjpy_rate")
    usdjpy_change = market_context.get("usdjpy_change")
    if usdjpy_rate is not None:
        rate_line = f"  - USD/JPY月末レート: {usdjpy_rate:.2f}円"
        if usdjpy_change is not None:
            rate_line += f"（月間騰落率 {usdjpy_change:+.2f}%）"
        lines.append(rate_line)

    if not lines:
        return "（市況データなし。市況・ベンチマークには言及しないこと）"
    return "\n".join(lines)


def _format_number(
    value: float | int | str | None,
    decimals: int = 2,
    *,
    sign: bool = False,
) -> str:
    """数値を整形し、欠損・不正値は明示的な欠損表示にする。"""
    try:
        number = float(value) if value is not None else None
    except (TypeError, ValueError):
        number = None
    if number is None:
        return "データなし"
    sign_spec = "+" if sign else ""
    return f"{number:{sign_spec},.{decimals}f}"


def _format_percent(value: float | int | str | None) -> str:
    formatted = _format_number(value, sign=True)
    return formatted if formatted == "データなし" else f"{formatted}%"


def _build_generation_prompt(report_data: dict) -> str:
    """導入文と全銘柄コメントを一括生成するプロンプトを構築する。"""
    year = report_data.get("year", 0)
    month = report_data.get("month_num", 0)
    holdings = report_data.get("holdings", [])

    holding_lines: list[str] = []
    for holding in holdings:
        symbol = holding.get("symbol") or holding.get("code", "")
        name = holding.get("name", "")
        currency = holding.get("currency", "JPY")
        current_price = holding.get(
            "current_price_native", holding.get("current_price", 0)
        )
        pl = holding.get("pl", 0)
        pl_rate = holding.get("pl_rate", 0)
        yen_change = _format_percent(holding.get("prev_month_change_rate"))
        native_change = _format_percent(
            holding.get("native_prev_month_change_rate")
        )
        holding_lines.extend(
            [
                f"  - 銘柄: {name}（{symbol}）",
                (
                    "    月末株価: "
                    f"{_format_number(current_price)} {currency}（現地通貨）"
                ),
                (
                    f"    円建て前月末比: {yen_change}"
                    "（カード表示と同じ対象月1か月の値動き）"
                ),
                f"    現地通貨建て前月末比: {native_change}（対象月1か月の値動き）",
                (
                    "    累積評価損益: "
                    f"{_format_number(pl, 0, sign=True)} 円（必ず円表記）"
                ),
                (
                    "    累積評価損益率: "
                    f"{_format_percent(pl_rate)}（取得時から対象月末まで）"
                ),
            ]
        )
    holdings_text = "\n".join(holding_lines) if holding_lines else "  （保有銘柄なし）"
    # キーは銘柄コードをそのまま使わせる（"7974.T" → "7974" の揺れが実際に起きた）
    symbols = _expected_symbols(report_data)
    stock_comments_example = json.dumps(
        dict.fromkeys(symbols, "銘柄別コメント") or {"銘柄コード": "銘柄別コメント"},
        ensure_ascii=False,
    )

    return (
        f"対象月: {year}年{month}月\n\n"
        "ポートフォリオ全体（いずれも対象月末時点）:\n"
        "  - 合計評価額: "
        f"{_format_number(report_data.get('total_value'), 0)} 円\n"
        "  - 累積評価損益: "
        f"{_format_number(report_data.get('total_pl'), 0, sign=True)} 円\n"
        "  - 累積評価損益率: "
        f"{_format_percent(report_data.get('total_pl_rate'))}\n\n"
        f"保有銘柄:\n{holdings_text}\n\n"
        "次のJSONだけを返してください。Markdownのコードフェンスや前後の説明は不要です。\n"
        '{"intro":"記事上部の全体コメント",'
        f'"stock_comments":{stock_comments_example}}}\n\n'
        "執筆ルール:\n"
        "- introは1段落、最大3文。主要な全体状況だけを書く。\n"
        "- 各銘柄コメントは1〜2文。その銘柄固有の数値や動きだけを書く。\n"
        "- 全銘柄をstock_commentsに含める。キーは上の例と同じ銘柄コードを"
        "「.T」などの接尾辞も含めて一字一句そのまま使う。\n"
        "- 銘柄の値動きは原則としてカードと同じ円建て前月末比を使う。\n"
        "- 累積評価損益率を市場の月間騰落率と比較しない。月間と累積を混同しない。\n"
        "- 月末株価だけが各銘柄の現地通貨。累積評価損益はUSD銘柄を含めて"
        "すべて円換算済みなので、必ず円として扱う。\n"
        "- ニュース、イベント、決算、製品発表、値動きの理由に加えて、"
        "市況・ベンチマーク・為替にも触れない。\n"
        "- 導入と各銘柄コメントで内容を重複させない。\n"
        "- 導入や銘柄コメント内で箇条書き・見出しを使わない。"
    )


def _expected_symbols(report_data: dict) -> list[str]:
    """report_data の保有銘柄コード一覧（プロンプトと検証で同じものを使う）。"""
    return [
        str(holding.get("symbol") or holding.get("code", ""))
        for holding in report_data.get("holdings", [])
        if holding.get("symbol") or holding.get("code")
    ]


def _lookup_stock_comment(stock_comments: dict, symbol: str) -> tuple[bool, object]:
    """銘柄コメントをキーの揺れを吸収して探す。(見つかったか, 値) を返す。

    完全一致 → 大文字小文字無視 → 接尾辞（".T" 等）を除いたコードの順で照合する。
    """
    if symbol in stock_comments:
        return True, stock_comments[symbol]
    base = symbol.split(".", 1)[0]
    for key, value in stock_comments.items():
        key_str = str(key).strip()
        if key_str.casefold() in (symbol.casefold(), base.casefold()):
            return True, value
    return False, None


def _fallback_comments(report_data: dict) -> dict:
    """API失敗・JSON不正時に表示されない空コメントを返す。"""
    return {
        "stock_comments": {},
        "summary": None,
        "intro": None,
    }


def _is_plain_paragraph(text: str, max_sentences: int) -> bool:
    """改行のない指定文数以内の文章かを判定する。"""
    stripped = text.strip()
    if not stripped or "\n" in stripped or "\r" in stripped:
        return False
    sentences = [part for part in re.split(r"[。！？!?]+", stripped) if part.strip()]
    return 1 <= len(sentences) <= max_sentences


def _contains_forbidden_content(text: str) -> bool:
    """対象外トピックや評価損益の外貨誤表記を検出する。"""
    if any(term.casefold() in text.casefold() for term in _FORBIDDEN_OUTPUT_TERMS):
        return True
    return bool(
        re.search(
            r"(?:評価損益|損益)[^。！？!?]{0,30}(?:USD|米ドル|ドル)",
            text,
            flags=re.IGNORECASE,
        )
    )


def _validation_error(value: object, max_sentences: int) -> str | None:
    """コメントの検証エラーを返す。問題がなければ None。"""
    if not isinstance(value, str):
        return "文字列ではありません"
    if not _is_plain_paragraph(value, max_sentences):
        return f"1段落・{max_sentences}文以内の条件を満たしません"
    if _contains_forbidden_content(value):
        return "禁止された内容を含んでいます"
    return None


def _parse_generation_response(text: str, report_data: dict) -> dict:
    """ClaudeのJSON応答を項目ごとに検証し、generate_all形式へ変換する。"""
    raw = text.strip()
    if raw.startswith("```") and raw.endswith("```"):
        first_newline = raw.find("\n")
        raw = raw[first_newline + 1 : -3].strip() if first_newline >= 0 else ""

    try:
        parsed: Any = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        print(f"⚠️ AI コメント生成の JSON 解析に失敗しました: {type(exc).__name__}")
        return _fallback_comments(report_data)

    if not isinstance(parsed, dict):
        print("⚠️ AI コメント生成の JSON がオブジェクトではありません")
        return _fallback_comments(report_data)
    intro = parsed.get("intro")
    stock_comments = parsed.get("stock_comments")
    intro_error = _validation_error(intro, 3)
    validated_intro: str | None = None
    if intro_error:
        print(f"⚠️ AI コメント intro を除外しました: {intro_error}")
    else:
        validated_intro = intro.strip()

    if not isinstance(stock_comments, dict):
        print("⚠️ AI コメント stock_comments を除外しました: オブジェクトではありません")
        stock_comments = {}

    validated_comments: dict[str, str] = {}
    for symbol in _expected_symbols(report_data):
        found, comment = _lookup_stock_comment(stock_comments, symbol)
        # 3. キーが無いことと値の型違いを区別して出す
        comment_error = (
            "キーがありません" if not found else _validation_error(comment, 2)
        )
        if comment_error:
            print(
                f"⚠️ AI コメント {symbol} を除外しました: {comment_error}"
            )
            continue
        assert isinstance(comment, str)
        validated_comments[symbol] = comment.strip()

    return {
        "stock_comments": validated_comments,
        "summary": None,
        "intro": validated_intro,
    }


class AiCommentGenerator:
    """Claude Sonnet による月次投資ブログコメント生成クラス。"""

    MODEL = "claude-sonnet-5"

    def __init__(self) -> None:
        """初期化。ANTHROPIC_API_KEY 環境変数を自動読み込み。"""
        self.client = anthropic.Anthropic()

    def generate_all(self, report_data: dict) -> dict:
        """導入文と全銘柄コメントを1回のAPI呼び出しで生成する。"""
        try:
            prompt = _build_generation_prompt(report_data)
            response = self.client.messages.create(
                model=self.MODEL,
                thinking={"type": "disabled"},
                max_tokens=1200,
                system=(
                    "あなたはポケモン関連銘柄を保有するブログの編集者です。"
                    "月次記事全体の流れを考え、短く自然な日本語に整えてください。"
                    f"{_HALLUCINATION_GUARD}{_STYLE_GUARD}"
                ),
                messages=[{"role": "user", "content": prompt}],
            )
            text_block = next(
                (block for block in response.content if block.type == "text"), None
            )
            response_text = getattr(text_block, "text", None)
            if not isinstance(response_text, str):
                print("⚠️ AI コメント生成の応答にテキストがありません")
                return _fallback_comments(report_data)
            return _parse_generation_response(response_text, report_data)
        except Exception as exc:  # noqa: BLE001
            print(
                "⚠️ AI コメント生成に失敗しました: "
                f"{type(exc).__name__}: {exc}"
            )
            return _fallback_comments(report_data)
