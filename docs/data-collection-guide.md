# データ収集システム操作ガイド（⚠️ 旧構成: data-collector）

> **このドキュメントは旧システム（data-collector・Google Sheets 転記）の記述です。現行の collector は `portfolio-dashboard/collector/` で、コマンドは AGENTS.md と docs/portfolio-dashboard.md 参照。**

## 概要
data-collectorは月次で株価データを取得し、Google Sheetsに転記するシステムです。
外国株の為替レート取得にも対応しています。

## 🚀 基本的な使い方

### 1. 事前準備
```bash
# 依存関係インストール（uvを使用）
cd data-collector
uv sync

# 開発用依存関係も含める場合
uv sync --extra dev

# 環境変数確認
# .envファイルにSPREADSHEET_IDとGOOGLE_APPLICATION_CREDENTIALSが設定されていることを確認
```

### 2. 月次データ取得の実行

#### 対話型実行（推奨）
```bash
uv run python main.py

# メニュー選択
# 1. 月次データ取得・分析 <- これを選択
# 年月を入力（例：2024年12月）
```

#### バッチ実行
```bash
# 2024年12月のデータを自動取得
uv run python main.py 2024 12

# 前月のデータを自動取得（スケジューラー用）
uv run python schedulers/monthly_runner.py

# uvスクリプトを使用（pyproject.tomlで定義済み）
uv run collect-data
uv run monthly-runner
```

## 📊 銘柄管理

### デフォルト銘柄の確認・編集

現在のデフォルト銘柄：
- **7974.T**: 任天堂（5,500円 × 10株）
- **2432.T**: DeNA（2,100円 × 5株）  
- **NVDA**: エヌビディア（850ドル × 2株）

#### デフォルト銘柄の追加・変更
`data-collector/config/settings.py` を編集：

```python
DEFAULT_STOCKS = {
    "7974.T": {"name": "任天堂", "purchase_price": 5500, "shares": 10, "purchase_date": "2024-01-15"},
    "2432.T": {"name": "DeNA", "purchase_price": 2100, "shares": 5, "purchase_date": "2024-02-10"},
    "NVDA": {"name": "エヌビディア", "purchase_price": 850, "shares": 2, "purchase_date": "2024-03-05"},
    # 新しい銘柄を追加
    "AAPL": {"name": "Apple", "purchase_price": 180, "shares": 5, "purchase_date": "2024-03-01"},
    "6758.T": {"name": "ソニー", "purchase_price": 12000, "shares": 3, "purchase_date": "2024-02-20"}
}
```

#### Google Sheetsでの銘柄管理
1. **ポートフォリオシート**で直接銘柄を追加・編集可能
2. 列構成：銘柄コード | 銘柄名 | 取得日 | 取得単価（円） | 保有株数 | 取得額合計 | 最終更新 | 備考

### 銘柄コードの書き方

#### 日本株
- **東証**: `6758.T` (ソニー)、`7974.T` (任天堂)
- **大証**: `4755.OS` (楽天グループ)

#### 米国株
- **NASDAQ**: `AAPL` (Apple)、`GOOGL` (Alphabet)
- **NYSE**: `JPM` (JPモルガン)、`KO` (コカ・コーラ)

#### その他の市場
- **香港**: `0700.HK` (テンセント)
- **ロンドン**: `SHEL.L` (シェル)

## 💱 外貨・為替レート取得

### 対応通貨ペア
yfinanceを使用して以下の為替レートを取得可能：

- **USD/JPY**: `USDJPY=X`
- **EUR/JPY**: `EURJPY=X`  
- **GBP/JPY**: `GBPJPY=X`
- **AUD/JPY**: `AUDJPY=X`
- **CAD/JPY**: `CADJPY=X`

### 外国株の円換算機能
外国株（NVDA等）の評価額を円換算で表示する機能を実装可能です。

```python
# 実装例：USD建て株式の円換算
def convert_to_jpy(usd_amount, usd_jpy_rate):
    return usd_amount * usd_jpy_rate
```

## 📅 定期実行の設定

### crontabでの自動実行
```bash
# 毎月1日の朝9時に前月データを取得
0 9 1 * * cd /path/to/data-collector && uv run monthly-runner

# 毎月15日に当月データを取得
0 9 15 * * cd /path/to/data-collector && uv run python main.py $(date +%Y) $(date +%m)

# uvスクリプトでの簡潔な実行
0 9 1 * * cd /path/to/data-collector && uv run collect-data
```

## 📋 データ出力形式

### 生成されるシート
1. **ポートフォリオ** - 銘柄マスタ情報
2. **データ記録** - Django backend用の詳細データ
3. **損益レポート** - 月次損益計算結果

### データ記録シートの列構成
| 列名 | 内容 | 例 |
|------|------|-----|
| 月末日付 | 対象月の月末日 | 2024-12-31 |
| 銘柄 | 銘柄コード | NVDA |
| 取得価格（円） | 購入時の価格 | 850 |
| 報告月末価格（円） | 月末時点の価格 | 950.25 |
| 保有株数 | 保有している株数 | 2 |
| 最高値 | 月中の最高値 | 965.50 |
| 最安値 | 月中の最安値 | 820.00 |
| 平均価格 | 月中の平均価格 | 890.75 |
| 月間変動率(%) | 月初から月末の変動率 | +12.5 |
| 平均出来高 | 月中の平均出来高 | 45000000 |
| 取得日時 | データ取得日時 | 2024-12-31 15:30:00 |
| 備考 | 自動生成の説明 | 自動取得 (エヌビディア) |

## 🔧 トラブルシューティング

### よくあるエラー

#### 1. 認証エラー
```
Google Sheets設定エラー: 認証に失敗しました
```
**解決方法**: 
- `config/my-service-account.json` の存在確認
- Google Cloud Console でAPI有効化確認

#### 2. 銘柄データ取得エラー
```
⚠️ XXXX のデータが取得できませんでした
```
**解決方法**:
- 銘柄コードの正しさを確認
- yfinanceでサポートされている銘柄か確認
- インターネット接続確認

#### 3. スプレッドシートアクセスエラー
```
SPREADSHEET_IDが設定されていません
```
**解決方法**:
- `.env` ファイルの SPREADSHEET_ID を確認
- スプレッドシートの共有設定を確認

### ログの確認
```bash
# エラーログの確認
tail -f logs/data_collector.log

# 詳細ログを有効化
echo "LOG_LEVEL=DEBUG" >> .env
```

## 📈 データ活用

### Django Webアプリでの表示
取得したデータは自動的に以下で利用可能：
- `web-app/backend` - Django API経由でデータ取得
- `web-app/frontend` - Vue.js でチャート表示

### 手動でのデータ確認
1. **Google Sheets** で直接確認
2. **対話型実行** でポートフォリオサマリー表示（メニュー2番）

## 🔄 更新履歴
- 2024-12-22: 初版作成、外貨取得機能の説明追加
- 外貨対応機能は今後のアップデートで実装予定