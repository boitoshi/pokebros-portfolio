"""collectors.sheets_sync.load_sheets_credentials のテスト。

実ネットワーク・実際の認証情報は使わず、google.auth.default をモックする。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from google.auth import impersonated_credentials

from collectors.sheets_sync import SCOPES, load_sheets_credentials

SA = "portfolio-sheets@example-project.iam.gserviceaccount.com"


def test_なりすまし先があれば既定の認証情報からなりすます(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    source = MagicMock()
    with patch("google.auth.default", return_value=(source, "p")) as default:
        creds = load_sheets_credentials("/does/not/exist.json", SA)
    default.assert_called_once_with()
    assert isinstance(creds, impersonated_credentials.Credentials)
    assert creds.service_account_email == SA
    assert creds._target_scopes == SCOPES


def test_なりすまし先と鍵ファイルの環境変数が両方あれば止める(monkeypatch):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/app/key.json")
    with patch("google.auth.default") as default:
        with pytest.raises(ValueError, match="GOOGLE_APPLICATION_CREDENTIALS"):
            load_sheets_credentials("/app/key.json", SA)
    default.assert_not_called()


def test_なりすまし先が無ければ鍵ファイルを使う(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    with patch(
        "collectors.sheets_sync.Credentials.from_service_account_file"
    ) as from_file:
        load_sheets_credentials("/path/key.json", "")
    from_file.assert_called_once_with("/path/key.json", scopes=SCOPES)


def test_月次バッチはSheets同期が無効なら株価収集へ進まずに止める():
    from main import PortfolioDataCollector

    collector = object.__new__(PortfolioDataCollector)
    collector.sheets_sync = None
    # 中止せずに先へ進んだら、ここが呼ばれて assert で落ちる
    collector.collect_monthly_data = MagicMock(return_value=True)
    collector.benchmark_collector = MagicMock()
    collector.report_generator = MagicMock()
    assert collector.collect_and_publish(2026, 10) is False
    collector.collect_monthly_data.assert_not_called()


def test_月次バッチが失敗したら終了コード1で終わる(monkeypatch):
    import main

    fake = MagicMock()
    fake.collect_and_publish.return_value = False
    monkeypatch.setattr(main, "PortfolioDataCollector", lambda: fake)
    monkeypatch.setattr(main, "SPREADSHEET_ID", "dummy")
    monkeypatch.setattr("sys.argv", ["main.py", "2026", "10"])
    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 1
