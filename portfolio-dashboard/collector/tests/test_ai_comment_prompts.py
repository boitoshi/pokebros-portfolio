"""月次記事AIコメントの一括生成・応答検証テスト。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from collectors.ai_comment import (
    _HALLUCINATION_GUARD,
    _STYLE_GUARD,
    AiCommentGenerator,
    _build_generation_prompt,
    _format_market_context,
    _parse_generation_response,
)

FULL_MARKET_CONTEXT = {
    "nikkei_change": 3.25,
    "sp500_change": -1.10,
    "usdjpy_rate": 152.34,
    "usdjpy_change": 0.85,
}

JPY_STOCK = {
    "name": "任天堂",
    "symbol": "7974.T",
    "current_price": 8500,
    "pl": 12000,
    "pl_rate": 5.5,
    "currency": "JPY",
    "prev_month_change_rate": 17.78,
    "native_prev_month_change_rate": 17.78,
}

USD_STOCK = {
    "name": "NVIDIA",
    "symbol": "NVDA",
    "current_price": 33265.5,
    "current_price_native": 208.27,
    "pl": 65018,
    "pl_rate": 27.99,
    "currency": "USD",
    "prev_month_change_rate": 9.63,
    "native_prev_month_change_rate": 6.84,
}

REPORT_DATA = {
    "year": 2026,
    "month_num": 8,
    "total_value": 500000,
    "total_pl": 77018,
    "total_pl_rate": 18.26,
    "holdings": [JPY_STOCK, USD_STOCK],
    "market_context": FULL_MARKET_CONTEXT,
}


def test_format_market_context_labels_monthly_periods() -> None:
    text = _format_market_context(FULL_MARKET_CONTEXT)
    assert "日経平均株価の月間騰落率: +3.25%" in text
    assert "S&P500の月間騰落率: -1.10%" in text
    assert "USD/JPY月末レート: 152.34円（月間騰落率 +0.85%）" in text


def test_format_market_context_omits_missing_values() -> None:
    text = _format_market_context({"nikkei_change": 3.25})
    assert "日経平均株価" in text
    assert "S&P500" not in text
    assert "USD/JPY" not in text


def test_format_market_context_handles_no_data() -> None:
    assert "市況データなし" in _format_market_context(None)
    assert "市況データなし" in _format_market_context({})


def test_prompt_contains_all_holdings_and_clear_units_and_periods() -> None:
    prompt = _build_generation_prompt(REPORT_DATA)
    assert "任天堂（7974.T）" in prompt
    assert "NVIDIA（NVDA）" in prompt
    assert "月末株価: 208.27 USD（現地通貨）" in prompt
    assert "円建て前月末比: +9.63%" in prompt
    assert "現地通貨建て前月末比: +6.84%" in prompt
    assert "累積評価損益: +65,018 円（必ず円表記）" in prompt
    assert "累積評価損益率: +27.99%（取得時から対象月末まで）" in prompt
    assert "累積評価損益率を市場の月間騰落率と比較しない" in prompt


def test_prompt_defines_article_wide_structure_and_forbidden_topics() -> None:
    prompt = _build_generation_prompt(REPORT_DATA)
    assert "introは1段落、最大3文" in prompt
    assert "各銘柄コメントは1〜2文" in prompt
    assert "導入と各銘柄コメントで内容を重複させない" in prompt
    for topic in ("ニュース", "イベント", "決算", "製品発表", "値動きの理由"):
        assert topic in prompt
    assert "市況・ベンチマーク・為替にも触れない" in prompt
    assert "同じ対象月の市況" not in prompt
    assert "読者に投資やお布施投資を勧める文は書かない" in _STYLE_GUARD
    assert "推測" in _HALLUCINATION_GUARD


def test_parse_valid_json_returns_no_summary() -> None:
    response = json.dumps(
        {
            "intro": "全体コメントです。",
            "stock_comments": {
                "7974.T": "任天堂コメントです。",
                "NVDA": "NVIDIAコメントです。",
            },
        },
        ensure_ascii=False,
    )
    result = _parse_generation_response(response, REPORT_DATA)
    assert result == {
        "intro": "全体コメントです。",
        "stock_comments": {
            "7974.T": "任天堂コメントです。",
            "NVDA": "NVIDIAコメントです。",
        },
        "summary": None,
    }


def test_parse_accepts_json_code_fence() -> None:
    result = _parse_generation_response(
        '```json\n{"intro":"導入",'
        '"stock_comments":{"7974.T":"任天堂", "NVDA":"NVIDIA"}}\n```',
        REPORT_DATA,
    )
    assert result["intro"] == "導入"
    assert result["summary"] is None


def test_parse_failure_uses_safe_fallback_and_missing_comment_is_excluded() -> None:
    invalid_json = _parse_generation_response("not json", REPORT_DATA)
    missing_stock = _parse_generation_response(
        '{"intro":"導入", "stock_comments":{"7974.T":"任天堂"}}',
        REPORT_DATA,
    )
    assert invalid_json == {"intro": None, "stock_comments": {}, "summary": None}
    assert missing_stock == {
        "intro": "導入",
        "stock_comments": {"7974.T": "任天堂"},
        "summary": None,
    }


def test_parse_excludes_only_fields_with_extra_sentences_or_line_breaks() -> None:
    too_many_stock_sentences = _parse_generation_response(
        '{"intro":"導入です。", "stock_comments":{'
        '"7974.T":"一文目。二文目。三文目。", "NVDA":"一文です。"}}',
        REPORT_DATA,
    )
    multiline_intro = _parse_generation_response(
        '{"intro":"一段落目。\\n二段落目。", "stock_comments":{'
        '"7974.T":"一文です。", "NVDA":"一文です。"}}',
        REPORT_DATA,
    )
    assert too_many_stock_sentences == {
        "intro": "導入です。",
        "stock_comments": {"NVDA": "一文です。"},
        "summary": None,
    }
    assert multiline_intro == {
        "intro": None,
        "stock_comments": {"7974.T": "一文です。", "NVDA": "一文です。"},
        "summary": None,
    }


def test_parse_excludes_only_fields_with_forbidden_content() -> None:
    forbidden_event = _parse_generation_response(
        '{"intro":"決算期待が上昇理由です。", "stock_comments":{'
        '"7974.T":"一文です。", "NVDA":"一文です。"}}',
        REPORT_DATA,
    )
    wrong_pl_currency = _parse_generation_response(
        '{"intro":"導入です。", "stock_comments":{'
        '"7974.T":"一文です。", "NVDA":"評価損益は65,018 USDです。"}}',
        REPORT_DATA,
    )
    assert forbidden_event == {
        "intro": None,
        "stock_comments": {"7974.T": "一文です。", "NVDA": "一文です。"},
        "summary": None,
    }
    assert wrong_pl_currency == {
        "intro": "導入です。",
        "stock_comments": {"7974.T": "一文です。"},
        "summary": None,
    }


def test_parse_reports_invalid_json_and_stock_validation_reason(capsys) -> None:
    _parse_generation_response("not json", REPORT_DATA)
    invalid_json_output = capsys.readouterr().out
    assert "JSON 解析に失敗" in invalid_json_output
    assert "JSONDecodeError" in invalid_json_output

    _parse_generation_response(
        '{"intro":"導入です。", "stock_comments":{'
        '"7974.T":"一文です。", "NVDA":"USD/JPYの影響です。"}}',
        REPORT_DATA,
    )
    validation_output = capsys.readouterr().out
    assert "NVDA を除外" in validation_output
    assert "禁止された内容" in validation_output



def test_prompt_lists_exact_symbol_keys() -> None:
    prompt = _build_generation_prompt(REPORT_DATA)
    # 実際の銘柄コード（接尾辞込み）をキーにした例を出す
    expected = '"stock_comments":{"7974.T": "銘柄別コメント", "NVDA": "銘柄別コメント"}'
    assert expected in prompt
    assert "一字一句そのまま" in prompt


def test_parse_accepts_symbol_without_suffix_and_case_difference() -> None:
    # 2026-09 の本番で、AI が "7974.T" を "7974" に縮めて返し、コメントが落ちた
    result = _parse_generation_response(
        '{"intro":"導入です。", "stock_comments":{'
        '"7974":"任天堂の一文です。", "nvda":"NVIDIAの一文です。"}}',
        REPORT_DATA,
    )
    assert result["stock_comments"] == {
        "7974.T": "任天堂の一文です。",
        "NVDA": "NVIDIAの一文です。",
    }


def test_parse_reports_missing_key_separately(capsys) -> None:
    _parse_generation_response(
        '{"intro":"導入です。", "stock_comments":{'
        '"7974.T": 123, "OTHER":"関係ない銘柄です。"}}',
        REPORT_DATA,
    )
    output = capsys.readouterr().out
    assert "7974.T を除外しました: 文字列ではありません" in output
    assert "NVDA を除外しました: キーがありません" in output

class _FakeMessages:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.response_text)]
        )


class _FailingMessages:
    def create(self, **kwargs: object) -> SimpleNamespace:
        raise RuntimeError("API unavailable")


def test_generate_all_api_error_uses_safe_fallback(capsys) -> None:
    generator = AiCommentGenerator.__new__(AiCommentGenerator)
    generator.client = SimpleNamespace(messages=_FailingMessages())

    result = generator.generate_all(REPORT_DATA)

    assert result == {"intro": None, "stock_comments": {}, "summary": None}
    output = capsys.readouterr().out
    assert "AI コメント生成に失敗" in output
    assert "RuntimeError" in output


def test_generate_all_calls_api_once_and_returns_no_summary() -> None:
    response = json.dumps(
        {
            "intro": "全体コメントです。",
            "stock_comments": {
                "7974.T": "任天堂コメントです。",
                "NVDA": "NVIDIAコメントです。",
            },
        },
        ensure_ascii=False,
    )
    messages = _FakeMessages(response)
    generator = AiCommentGenerator.__new__(AiCommentGenerator)
    generator.client = SimpleNamespace(messages=messages)

    result = generator.generate_all(REPORT_DATA)

    assert len(messages.calls) == 1
    assert result["summary"] is None
    assert set(result["stock_comments"]) == {"7974.T", "NVDA"}
