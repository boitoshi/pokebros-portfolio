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
    default.assert_called_once_with(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
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
