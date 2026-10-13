# Google Sheets API設定ガイド（⚠️ 旧構成: data-collector）

> **このドキュメントは旧システム（data-collector）のサービスアカウント権限エラーの対応記録です。Google Sheets は現行 collector の `--sync` の入力元として現役ですが、認証設定は `portfolio-dashboard/collector/config/settings.py` と `.env.example` 参照。**

## エラー解決手順

### 現在のエラー: `APIError: [403]: The caller does not have permission`

このエラーは、サービスアカウントがスプレッドシートにアクセスする権限がないことを示しています。

## 🔧 解決手順

### 1. スプレッドシートの共有設定確認

**Google Sheetsで以下を実行:**

1. **スプレッドシートを開く**
   - URL: `https://docs.google.com/spreadsheets/d/1OzUHxgBoFz6tzkd3hg4j3L2yeQ5Qw0vk3mIk4j4IjIM/edit`

2. **共有設定を確認**
   - 右上の「共有」ボタンをクリック
   - サービスアカウントのメールアドレスが追加されているか確認:
     ```
     spreadsheet-access@pokebros-project.iam.gserviceaccount.com
     ```

3. **サービスアカウントを追加（未追加の場合）**
   - 「ユーザーやグループを追加」に以下のメールアドレスを入力:
     ```
     spreadsheet-access@pokebros-project.iam.gserviceaccount.com
     ```
   - **権限**: 「編集者」を選択
   - 「送信」をクリック

### 2. Google Cloud Console設定確認

**Google Cloud Consoleで以下を確認:**

1. **プロジェクト**: `pokebros-project`
2. **有効化すべきAPI**:
   - Google Sheets API
   - Google Drive API

3. **API有効化手順**:
   ```
   1. Google Cloud Console → API とサービス → ライブラリ
   2. "Google Sheets API" を検索 → 有効化
   3. "Google Drive API" を検索 → 有効化
   ```

### 3. サービスアカウント権限確認

**IAMで権限確認:**
```
1. Google Cloud Console → IAM と管理 → IAM
2. サービスアカウント「spreadsheet-access@pokebros-project.iam.gserviceaccount.com」を確認
3. 最低限必要な権限: 「編集者」または「Google Sheets API利用」
```

## 🧪 権限テスト

以下のコマンドで権限をテスト:

```bash
cd data-collector
uv run python -c "
from collectors.sheets_writer import SheetsDataWriter
from config.settings import GOOGLE_APPLICATION_CREDENTIALS, SPREADSHEET_ID

writer = SheetsDataWriter(GOOGLE_APPLICATION_CREDENTIALS, SPREADSHEET_ID)
if writer.setup_google_sheets():
    print('✅ Google Sheets接続成功')
    try:
        sheets = writer.spreadsheet.worksheets()
        print(f'✅ 利用可能シート: {[s.title for s in sheets]}')
    except Exception as e:
        print(f'❌ シート一覧取得エラー: {e}')
else:
    print('❌ Google Sheets接続失敗')
"
```

## 🔄 よくある解決方法

### ケース1: サービスアカウントが共有されていない
**症状**: `[403] The caller does not have permission`
**解決**: スプレッドシートにサービスアカウントを「編集者」として追加

### ケース2: APIが有効化されていない
**症状**: `API has not been used in project`
**解決**: Google Cloud ConsoleでGoogle Sheets API・Google Drive APIを有効化

### ケース3: 認証ファイルが間違っている
**症状**: `No such file or directory` または認証エラー
**解決**: 
1. 認証ファイルパスを確認: `/Users/akabros/Documents/code/pokebros-portfolio/data-collector/config/my-service-account.json`
2. ファイル内容を確認（client_emailが正しいか）

### ケース4: スプレッドシートIDが間違っている
**症状**: `Requested entity was not found`
**解決**: .envファイルのSPREADSHEET_IDを確認
```
SPREADSHEET_ID=1OzUHxgBoFz6tzkd3hg4j3L2yeQ5Qw0vk3mIk4j4IjIM
```

## 📝 設定完了後の確認事項

1. ✅ サービスアカウントがスプレッドシートに「編集者」権限で追加済み
2. ✅ Google Sheets API・Google Drive APIが有効化済み
3. ✅ 認証ファイルが正しい場所に配置済み
4. ✅ .envファイルのSPREADSHEET_IDが正しい
5. ✅ 権限テストコマンドが成功

## 🎯 次のステップ

設定完了後、以下で動作確認:

```bash
cd data-collector
uv run python main.py
# メニュー3番「シート初期化」を実行
```

成功すれば、月次データ取得が可能になります。