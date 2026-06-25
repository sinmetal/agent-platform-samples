# Agent Identity + BigQuery (3-legged OAuth) サンプル

[Agent Identity](https://docs.cloud.google.com/iam/docs/agent-identity-overview) の
**3-legged OAuth（3LO / ユーザー代理）** を使って、エージェントが
**ログインしたユーザー自身の権限で BigQuery にアクセス**するサンプルです。

- エージェント自身のマシン ID ではなく、**同意したユーザーの OAuth トークン**で
  BigQuery を呼ぶため、クエリはそのユーザーの IAM 権限で実行され、BigQuery 監査
  ログにもそのユーザーとして記録されます。
- ベースは公式 ADK サンプル [`google/adk-python` `contributing/samples/integrations/gcp_auth`](https://github.com/google/adk-python/tree/main/contributing/samples/integrations/gcp_auth)
  を Spotify → BigQuery に置き換えたものです。
- デプロイ先は Gemini Enterprise Agent Platform の **Agent Runtime**。

参考ドキュメント:
- 3LO: <https://docs.cloud.google.com/iam/docs/auth-with-3lo>
- 2LO（外部 API 向け。今回は不使用）: <https://docs.cloud.google.com/iam/docs/auth-with-2lo>
- Agent Identity 概要: <https://docs.cloud.google.com/iam/docs/agent-identity-overview>

## この環境の固定値

| 項目 | 値 |
| --- | --- |
| Project ID | `your-project-id` |
| Project Number | `YOUR_PROJECT_NUMBER` |
| Organization ID | `YOUR_ORG_ID` |
| Location | `us-central1` |
| 3LO Connector 名 | `bigquery-3lo` |

## 構成

```
agent-identity-bigquery-sample/
├── agent.py            # ADK エージェント本体（BigQuery 3LO ツール）
├── deploy.py           # Agent Runtime へ AGENT_IDENTITY 付きでデプロイ
├── requirements.txt
├── setup.sh            # gcloud セットアップコマンド（具体値入り）
├── .env.example
└── client/             # 同意フロー用フロントエンド（公式サンプル流用・汎用）
    ├── main.py         # FastAPI: agent 一覧 / chat / OAuth コールバック
    ├── requirements.txt
    └── static/         # 簡易チャット UI（popup / resume を処理）
```

## あなたが先に作る必要があるリソース（まとめ）

1. **API 有効化**: aiplatform / iamconnectors / iamconnectorcredentials / bigquery / cloudresourcemanager
2. **GCS ステージングバケット**（Agent Runtime デプロイ用）
3. **OAuth 2.0 クライアント（Web アプリ型）** — client ID / secret と、コネクタの
   コールバック URL を「承認済みリダイレクト URI」に登録
4. **3LO コネクタ `bigquery-3lo`** — `gcloud alpha agent-identity connectors create`
5. **デプロイ後**: エージェントの principal に対し、コネクタの
   `roles/iamconnectors.user` を付与
6. **エージェントの principalSet に `roles/serviceusage.serviceUsageConsumer`**

> BigQuery のデータ権限は「あなたの権限」で実行されるため、あなた
> (`you@example.com`) が既に対象データを読めるなら追加付与は不要です。
> デフォルトのお試しクエリは公開データセット `bigquery-public-data` を使います。

`setup.sh` に全コマンドを具体値入りで用意してあります。以下は手順の解説です。

---

## セットアップ手順

事前に、デプロイ/コネクタ作成を行うあなた自身のアカウントに以下のロールが必要です:
`roles/iamconnectors.admin`（コネクタ作成）, `roles/aiplatform.user`, ステージング
バケットへの書き込み権限。

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project your-project-id
cp .env.example .env   # 必要に応じて編集
source .env
```

### 1. API 有効化

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  iamconnectors.googleapis.com \
  iamconnectorcredentials.googleapis.com \
  bigquery.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project=your-project-id
```

### 2. ステージングバケット作成

```bash
gcloud storage buckets create gs://your-project-id-agent-staging \
  --project=your-project-id --location=us-central1
```

### 3. OAuth 2.0 クライアントを作成（Console）

`APIs & Services > Credentials > Create credentials > OAuth client ID`
- Application type: **Web application**
- Authorized redirect URI に **次の URL をそのまま**登録:

```
https://iamconnectorcredentials.googleapis.com/v1/projects/your-project-id/locations/us-central1/connectors/bigquery-3lo/oauthcallback
```

発行された **Client ID / Client Secret** を控えます。OAuth 同意画面が未設定なら
先に設定し、スコープ `https://www.googleapis.com/auth/bigquery` を許可、自分を
テストユーザーに追加してください。

### 4. 3LO コネクタを作成

```bash
gcloud alpha agent-identity connectors create bigquery-3lo \
  --project=your-project-id \
  --location=us-central1 \
  --three-legged-oauth-client-id="<CLIENT_ID>" \
  --three-legged-oauth-client-secret="<CLIENT_SECRET>" \
  --three-legged-oauth-authorization-url="https://accounts.google.com/o/oauth2/v2/auth" \
  --three-legged-oauth-token-url="https://oauth2.googleapis.com/token" \
  --allowed-scopes="https://www.googleapis.com/auth/bigquery"
```

### 5. エージェントをデプロイ

```bash
pip install -r requirements.txt
source .env
python deploy.py
```

出力された **Engine ID** と **Effective identity (`principal://...`)** を控えます。

### 6. エージェントにコネクタ利用権限を付与

`<ENGINE_ID>` を 5 の出力で置き換えて実行:

```bash
gcloud alpha agent-identity connectors add-iam-policy-binding bigquery-3lo \
  --project=your-project-id \
  --location=us-central1 \
  --role="roles/iamconnectors.user" \
  --member="principal://agents.global.org-YOUR_ORG_ID.system.id.goog/resources/aiplatform/projects/YOUR_PROJECT_NUMBER/locations/us-central1/reasoningEngines/<ENGINE_ID>"
```

### 7. エージェントにプロジェクト利用権限を付与

```bash
gcloud projects add-iam-policy-binding your-project-id \
  --member="principalSet://agents.global.org-YOUR_ORG_ID.system.id.goog/attribute.platformContainer/aiplatform/projects/YOUR_PROJECT_NUMBER" \
  --role="roles/serviceusage.serviceUsageConsumer"
```

---

## 動作確認（同意フロー付きフロントエンド）

3LO はユーザー同意が必要なので、ローカルのフロントエンドから実行します。

```bash
cd client
pip install -r requirements.txt
uvicorn main:app --port 8080 --reload
```

ブラウザで **`http://localhost:8080`** を開きます
（`127.0.0.1` ではなく必ず `localhost`。OAuth リダイレクト URL が `localhost`
前提のため）。

1. サイドバーで Project ID = `your-project-id`, Location =
   `us-central1` を入力 → "Load Remote Agents" → デプロイした
   `agent-identity-bigquery` を選択 → "Save & Apply Settings"
2. チャットで例えば次を送信:

   > `bigquery-public-data の shakespeare で作品ごとの単語数 上位5件を教えて`

3. 初回はログイン用ポップアップが開くので、自分の Google アカウントで同意します。
4. 同意完了後、エージェントが**あなたの権限で** BigQuery を実行し結果を返します。

お試し用に直接 SQL を投げる例:

> ```
> 次のSQLを実行して: SELECT corpus, COUNT(*) AS n FROM `bigquery-public-data.samples.shakespeare` GROUP BY corpus ORDER BY n DESC LIMIT 5
> ```

## 仕組み（ポイント）

- `agent.py` の `bigquery_query` は `AuthenticatedFunctionTool` でラップされ、
  `GcpAuthProviderScheme`（`scopes=[bigquery]`, `continue_uri=...`）で 3LO を指定。
- ユーザーが同意すると、トークンは **Google 管理の Vault** に保管され、ツール呼び
  出し時に ADK が `credential.http.credentials.token` として自動注入します。
- ツールはそのトークンで BigQuery REST `jobs.query` を叩くだけ。サービスアカウント
  キーは一切不要です。
- デプロイは `identity_type=AGENT_IDENTITY` を指定し、エージェント固有の SPIFFE
  ベース ID を発行。コネクタからトークンを取り出す権限（`iamconnectors.user`）は
  この ID に対して付与します。

## ローカルでエージェント単体を触る（任意）

API キー/2LO の確認だけなら `adk web` でも起動できます（3LO は同意フローが必要な
ためフロントエンド経由を推奨）:

```bash
adk web .
```

## 注意 / バージョン

- Agent Identity・`gcloud alpha agent-identity`・ADK の
  `google.adk.integrations.agent_identity` は新しい機能のため、最新の
  `google-adk[agent-identity]` を使ってください。コマンドやフィールド名が更新された
  場合は上記ドキュメントのリンク先を正としてください。
- `client/` 配下は公式 ADK サンプルの汎用クライアントをそのまま流用しています
  （特定のエージェントに依存しません）。
