# デプロイ方針（⚠️ 旧構成: Cloud Run + CONOHA/Vercel・採用せず）

> **このドキュメントは旧システム（web-app / data-collector）向けに立てた計画で、採用されていません。現行の本番は GCE e2-micro です（docs/portfolio-dashboard.md の「GCE デプロイ手順」参照）。**

## 構成概要

| 役割 | 本番環境 | 費用 |
|------|---------|------|
| バックエンド（FastAPI） | Google Cloud Run | 月次無料枠内で実質 0 円 |
| フロントエンド（Next.js） | CONOHA サーバー or Vercel | CONOHA は既存契約内 |
| データストア | Google Sheets | 既存利用のまま |

---

## バックエンド：Cloud Run

### 概要

FastAPI アプリを Docker コンテナ化して Cloud Run にデプロイする。

### 月次無料枠（期限なし）

| リソース | 無料枠 |
|---------|-------|
| リクエスト数 | 200 万回/月 |
| CPU | 360,000 vCPU 秒/月 |
| メモリ | 180,000 GB 秒/月 |
| 送信トラフィック | 1 GB/月 |

個人利用では無料枠内に収まる見込み。

### 注意事項

- **コールドスタート**: アクセスがない期間が続くとインスタンスが停止し、初回レスポンスに 2〜5 秒かかる。許容できない場合は `--min-instances=1` を設定するが、そこだけ課金が発生する（月数百円程度）。
- **サービスアカウントキー**: `GOOGLE_APPLICATION_CREDENTIALS` に指定する JSON ファイルは Secret Manager で管理し、コンテナイメージに含めない。

### 必要な作業（実装時）

1. `web-app/backend/Dockerfile` を作成
2. Cloud Run サービスに環境変数を設定
   - `SPREADSHEET_ID`
   - `GOOGLE_APPLICATION_CREDENTIALS`（Secret Manager 経由）
3. CORS の `allow_origins` をフロントエンドの本番 URL に更新（`main.py`）
4. GitHub Actions または Cloud Build で CI/CD を構成

---

## フロントエンド：CONOHA

### CONOHA のプランによって方針が分岐する

#### パターン A：CONOHA VPS（Node.js 実行可能）

Next.js を Node.js サーバーとして起動し、Nginx でリバースプロキシを設定。WordPress と同一サーバーでバーチャルホストを分けて共存させる。

```
CONOHA VPS
├── Nginx
│   ├── blog.example.com  → WordPress（既存）
│   └── portfolio.example.com → Next.js（ポート3000にプロキシ）
```

- Next.js の起動管理は pm2 を使用
- `force-dynamic` を使っているためそのまま動作する
- 追加費用なし（既存の VPS 内で完結）

#### パターン B：CONOHA WING（共有サーバー、Node.js 非対応）

共有サーバーは PHP/静的ファイルのみ対応のため、Next.js をそのまま動かせない。2 つの選択肢がある。

**選択肢 B-1：Vercel にデプロイ（推奨）**

```
CONOHA WING  → WordPress（既存）
Vercel        → Next.js（Hobby プランで無料）
Cloud Run     → FastAPI
```

- Next.js のホームグラウンド。デプロイが最も簡単。
- Hobby プランは個人利用に限り無料・HTTPS・独自ドメイン対応。
- CONOHA との関係は「WordPress と別のサービス」として切り離す。

**選択肢 B-2：静的エクスポートして CONOHA に置く**

Next.js を `output: 'export'` モードでビルドして静的 HTML/CSS/JS を生成し、CONOHA に配置する。

```
next.config.ts
  output: 'export'   // 追加
```

- **制約**: `force-dynamic` なページは使えなくなる。API フェッチをクライアントサイドに移行する必要がある。
- バックエンドが Cloud Run にいるため、ブラウザから直接 Cloud Run を呼び出す構成になる。
- 改修コストがかかるため、B-1（Vercel）のほうが現実的。

---

## 環境変数の更新箇所（デプロイ時）

### バックエンド `web-app/backend/.env`

```env
SPREADSHEET_ID=your_spreadsheet_id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

本番では Cloud Run の環境変数・Secret Manager で管理する（ファイルは使わない）。

### フロントエンド `web-app/frontend/.env.local`

```env
NEXT_PUBLIC_API_BASE_URL=https://your-cloudrun-url.run.app
```

### `web-app/backend/main.py` の CORS

```python
allow_origins=["https://portfolio.example.com"]  # 本番 URL に変更
```

### `web-app/frontend/next.config.ts` の rewrite 先

```typescript
destination: "https://your-cloudrun-url.run.app/api/:path*"
```

---

## 費用まとめ

| 項目 | 費用 |
|------|------|
| Cloud Run | 0 円（月次無料枠内の見込み） |
| CONOHA VPS | 既存契約内（追加なし） |
| Vercel Hobby（B-1 の場合） | 0 円 |
| Google Sheets API | 0 円 |
| **合計** | **0 円（既存 CONOHA 費用のみ）** |

---

## 優先度付きアクション（実装するとき）

1. **CONOHA のプランを確認**（VPS か WING か）→ フロントの方針を決定
2. **`web-app/backend/Dockerfile` を作成**
3. **Cloud Run にバックエンドをデプロイ**・動作確認
4. **フロントエンドをデプロイ**（VPS → pm2 + Nginx、または Vercel）
5. **本番 URL で CORS・rewrite・`.env` を更新**
6. **GitHub Actions で CI/CD を構成**（push → Cloud Run 自動デプロイ）
