🌐 [English](../en/databricks-standard-s3-reproduction.md) | **日本語**

# 標準 S3 × Databricks 非構造化 AI PoC の再現手順

> **目的**: [標準 S3 バケット上の Databricks 非構造化データ AI 活用 PoC](./databricks-standard-s3-unstructured-poc.md) の検証環境を、ゼロから再構築するための手順書。AWS 側は CloudFormation で再現し、Databricks 側はコンソール/API 操作を順に示す。
> **想定所要時間**: 30〜45 分（Foundation Model の初回起動待ちを含む）。
> **コスト**: Serverless SQL の従量（Small ≒ 数 DBU）+ Foundation Model 推論（トークン課金）+ S3 保管（数 KB、事実上ゼロ）。Vector Search を試す場合のみ別途エンドポイント課金（[コスト doc §7](./databricks-verification-environment-cost.md) 参照）。
> **命名の注意**: 本手順は標準 S3 汎用バケットが対象。FSx for ONTAP S3 Access Point ではない（そちらは BLK-001 でブロックされる。[FILE 型評価](./databricks-file-type-evaluation.md) を参照）。

---

## 前提条件

- Databricks ワークスペース（**US リージョン推奨**、例: us-west-2）。pay-per-token の Foundation Model は US リージョンで提供され、Tokyo ワークスペースには既定エンドポイントが無い。
- Unity Catalog 有効、Serverless SQL Warehouse を作成できる権限。
- AWS アカウント（Databricks ワークスペースと**別リージョンでも可**。本 PoC はバケットを ap-northeast-1、ワークスペースを us-west-2 に置いてクロスリージョンで動作を確認した）。
- AWS CLI と CloudFormation のデプロイ権限（IAM ロール作成を含む）。

---

## 1. AWS 側のデプロイ（CloudFormation）

テンプレート: `poc-templates/08-databricks-standard-s3/standard-s3-uc-access.yaml`。標準 S3 バケットと、Unity Catalog が assume する IAM ロールを作成する。

`UnityCatalogRoleArn` と `UnityCatalogExternalId` は**手順 2 の External Location ウィザードが提示する値**なので、先に手順 2 を一度開いて値を控えてから戻ってくるか、いったんプレースホルダでロールを作り手順 2 の提示値で更新する。本 PoC は後者（ウィザード提示どおりに信頼ポリシーを合わせる）で通した。

```bash
aws cloudformation deploy \
  --template-file poc-templates/08-databricks-standard-s3/standard-s3-uc-access.yaml \
  --stack-name databricks-stds3-poc \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    BucketName=fsxn-databricks-stds3-poc-<account-id>-<region-short> \
    RoleName=databricks-uc-stds3-poc \
    UnityCatalogRoleArn=arn:aws:iam::<databricks-uc-account>:role/unity-catalog-prod-UCMasterRole-XXXXXXXXXXXXX \
    UnityCatalogExternalId=<databricks-account-uuid> \
    Environment=dev \
  --region ap-northeast-1
```

`CAPABILITY_NAMED_IAM` はロールに明示名を付けているため必須。デプロイ後、`RoleArnOut` と `BucketNameOut` を出力から控える。

> **IAM に関する補足**: このロールのポリシーは `s3:GetBucketNotification` を**意図的に含まない**。そのため手順 2 の検証で File Events だけが 403 で失敗する（下記）。File Events を使う場合のみ、テンプレートのポリシーに `s3:GetBucketNotification` / `s3:PutBucketNotification` を追加する。

---

## 2. Unity Catalog の External Location 作成

DBSQL の `CREATE STORAGE CREDENTIAL` は構文エラー（`PARSE_SYNTAX_ERROR`、UC 管理文は DBSQL 非対応）になる。**Catalog Explorer の UI ウィザード**を使う。

1. Catalog Explorer → External Data → Credentials → Create credential。IAM ロール ARN（`RoleArnOut`）を入力する。
2. Databricks が**期待する信頼ポリシー**を画面に提示する。本環境の提示値は **UC マスターロール（`arn:aws:iam::<databricks-uc-account>:role/unity-catalog-prod-UCMasterRole-...`）+ self-assume + `sts:ExternalId` = アカウント UUID**（`:root` ではなく特定ロール ARN）。手順 1 のテンプレートのパラメータをこの提示値に合わせる。
3. External Location を作成: 名前 `stds3_poc_location`、URL `s3://<bucket>/`、上記 Credential を選択。
4. 接続検証が走る。**Read / List / Write / Delete / Path Exists / Assume Role / Self Assume Role / External ID Condition = すべて Success** になれば、標準バケットで BLK-001 が起きていないことの確認になる。
5. **File Events の provision だけが Failed** になる（`no identity-based policy allows the s3:GetBucketNotification action`, 403）。File Events は任意機能なので「Force create」で先へ進める。読み書きと AI 処理には影響しない。

> **落とし穴**: ブラウザ自動操作では combobox のオーバーレイ要素がビューポート外に出て操作の往復が増える。UI は手動操作が確実。

---

## 3. カタログ・スキーマ・External Volume・サンプルデータ

Serverless SQL Warehouse（Small、10 分オートストップ）を起動し、SQL エディタで実行する。

```sql
CREATE SCHEMA IF NOT EXISTS workspace.stds3_poc;
CREATE EXTERNAL VOLUME workspace.stds3_poc.unstructured
  LOCATION 's3://<bucket>/unstructured/';
```

サンプルは合成データ（実データなし）。ローカルで生成して S3 に置く（点検画像 PNG、棒グラフ PNG、点検レポート PDF）。生成スクリプトは任意だが、本 PoC は Python（Pillow + reportlab）で以下 3 ファイルを作った。

```bash
aws s3 cp inspection-sample-01.png s3://<bucket>/unstructured/
aws s3 cp chart-sample-02.png      s3://<bucket>/unstructured/
aws s3 cp report-sample-01.pdf     s3://<bucket>/unstructured/
```

```sql
LIST '/Volumes/workspace/stds3_poc/unstructured/';  -- 3 ファイルが見えれば OK
```

---

## 4. シナリオの再現

> **モデル名の実測**: 本環境で pay-per-token として使えたのは `databricks-meta-llama-3-3-70b-instruct`（テキスト）、`databricks-llama-4-maverick`（マルチモーダル）、`databricks-gte-large-en`（embedding）。`databricks-claude-3-7-sonnet` は**存在しない**。`RESOURCE_DOES_NOT_EXIST` が出たらまずモデル名を疑う（リージョン制約と早合点しない）。

### 4.1 シナリオ 2: `ai_parse_document()` による PDF OCR

```sql
SELECT ai_parse_document(content)
FROM READ_FILES('/Volumes/workspace/stds3_poc/unstructured/report-sample-01.pdf', format => 'binaryFile');
```

`elements[0].type = title`、`content = "Synthetic Equipment Inspection Report"` が返れば成功。

### 4.2 シナリオ 3: FILE 型 + AI 関数

```sql
CREATE OR REPLACE TABLE workspace.stds3_poc.docs AS
  SELECT path, file FROM list_files('/Volumes/workspace/stds3_poc/unstructured/') WHERE path LIKE '%.pdf';
DESCRIBE TABLE workspace.stds3_poc.docs;                     -- file 列の型 = file external
SELECT path, ai_parse_document(file) FROM workspace.stds3_poc.docs;  -- FILE 列を直接 OCR
```

`file` 列の型が **`file external`** になり、それを `ai_parse_document(file)` に直接渡して OCR が通る。S3 Access Point では `FILE EXTERNAL` が BLK-001 でブロックされるが、標準バケットでは成立する（本 PoC 対比の核心）。

### 4.3 シナリオ 1: `ai_query()` による画像の LLM Vision

SQL で messages 構造を `named_struct` で手組みすると Monaco のオートクローズで括弧が壊れやすい。**Python ノートブック + `mlflow.deployments`** が確実。

```python
from mlflow.deployments import get_deploy_client
import base64
client = get_deploy_client("databricks")
img = base64.b64encode(open("/Volumes/workspace/stds3_poc/unstructured/inspection-sample-01.png","rb").read()).decode()
resp = client.predict(endpoint="databricks-llama-4-maverick", inputs={"messages":[{"role":"user","content":[{"type":"text","text":"Describe this image."},{"type":"image_url","image_url":{"url":f"data:image/png;base64,{img}"}}]}]})
print(resp)
```

合成画像（青い四角・オレンジの円・下部の黒い線）を正しく記述すれば成功。

### 4.4 シナリオ 4: AI Functions 一通り

```sql
CREATE OR REPLACE TABLE workspace.stds3_poc.doc_chunks
  TBLPROPERTIES (delta.enableChangeDataFeed = true) AS
  SELECT explode(...) ...;  -- ai_parse_document 出力を title/text/table の 3 チャンクに分割
SELECT ai_classify(chunk, array('inspection_report','financial','marketing','legal')) FROM workspace.stds3_poc.doc_chunks;  -- inspection_report
SELECT ai_gen('Summarize in 8 words or fewer: ' || chunk) FROM workspace.stds3_poc.doc_chunks;
SELECT ai_analyze_sentiment(chunk) FROM workspace.stds3_poc.doc_chunks;  -- neutral
```

### 4.5 シナリオ 6: Genie による自然言語問い合わせ

```sql
CREATE OR REPLACE TABLE workspace.stds3_poc.inspection_findings
  (item STRING, status STRING, score DOUBLE) COMMENT '点検結果の表';
INSERT INTO workspace.stds3_poc.inspection_findings VALUES
  ('Weld seam','Review',0.71), ('Coating','OK',0.95), ('Pressure valve','OK',0.98);
```

Genie スペースを作り `inspection_findings` を接続。"Which inspection item has the lowest score?" に対し **Weld seam（0.71、Review）と返れば成功**（NL→SQL 自動生成 → 実行 → NL 回答）。

### 4.6 シナリオ 5: Mosaic AI Vector Search（環境依存で未完）

エンドポイント作成と Delta Sync Index の作成要求までは Verified。ただし本環境ではインデックスが約 16 分 `PROVISIONING_ENDPOINT` のまま ONLINE 化しなかった（`databricks-gte-large-en` の高レイテンシとトライアル/共有環境のプロビジョニング遅延。[コスト doc §7](./databricks-verification-environment-cost.md) に詳細）。試す場合は課金に注意（**最後のインデックス削除から 24 時間はエンドポイント課金が残る**）。撤去のような重要操作は `try/except` 等のインデント付き Python を避け、フラットな 1 行文で行う（Monaco の auto-indent 対策）。

---

## 5. 撤去

不可逆操作を含む。実行前に対象を確認する。

```bash
# AWS: バケットを空にしてから CFn スタックを削除（バケットは DeletionPolicy: Retain なので個別削除）
aws s3 rm s3://<bucket>/ --recursive
aws s3api delete-bucket --bucket <bucket> --region ap-northeast-1
aws cloudformation delete-stack --stack-name databricks-stds3-poc --region ap-northeast-1
```

Databricks 側は依存の逆順で削除する: テーブル（`docs` / `doc_chunks` / `inspection_findings`）→ External Volume → スキーマ `stds3_poc` → External Location `stds3_poc_location` → 自動生成 Storage Credential。Genie スペースとノートブックも削除する。SQL Warehouse は共有なら停止のみ（10 分オートストップ）。Vector Search を作成した場合はインデックス → エンドポイントの順で削除し、24 時間の課金テールに注意する。

---

## 参考資料

- [標準 S3 バケット上の Databricks 非構造化データ AI 活用 PoC](./databricks-standard-s3-unstructured-poc.md) — 検証結果本体（6 シナリオ、IAM/認証、CloudTrail 裏付け、Snowflake Cortex 対比）
- [FILE 型（β）評価](./databricks-file-type-evaluation.md) — S3 Access Point 上の挙動と標準 S3 へのステージング推奨
- [検証環境とコスト](./databricks-verification-environment-cost.md) — pay-per-token US-only、Vector Search 課金テール、撤去チェックリスト
- CloudFormation テンプレート: `poc-templates/08-databricks-standard-s3/standard-s3-uc-access.yaml`
