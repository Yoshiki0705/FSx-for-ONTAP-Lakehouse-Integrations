🌐 [English](../en/setup-guide.md) | **日本語**

# Snowflake セットアップガイド

## 概要

FSx for NetApp ONTAP の S3 Access Point を Snowflake の External Stage として設定し、
External Table / Iceberg Table のストレージレイヤーとして使用する手順です。

## 前提条件

- AWS アカウントに FSx for NetApp ONTAP がデプロイ済み
- **FSx for ONTAP S3 Access Point が作成済み**（`aws fsx create-and-attach-s3-access-point` で作成）
- Snowflake アカウント（Iceberg Table には Enterprise Edition 以上が必要）
- AWS CLI v2 設定済み
- Snowflake で ACCOUNTADMIN ロールへのアクセス

## 重要: FSx for ONTAP S3 Access Point のアーキテクチャ

FSx for ONTAP S3 Access Point は通常の S3 Access Point とは**異なります**。
CloudFormation の `AWS::S3::AccessPoint` ではなく、FSx API で作成します:

```bash
aws fsx create-and-attach-s3-access-point \
  --name <ap-name> --type ONTAP \
  --ontap-configuration \
    'VolumeId=<fsvol-xxx>,FileSystemIdentity={Type=UNIX,UnixUser={Name=root}}'
```

通常の S3 との主な違い:
- **Pre-signed URL は非サポート**
- **S3 Event Notifications は非サポート**（FPolicy で代替）
- **レイテンシが高い**（ListObjects に数十秒〜数分）
- 最大アップロードサイズ: 50 GB
- StorageClass は常に `FSX_ONTAP`

## セットアップフロー

```
Step 0: FSx for ONTAP S3 Access Point 作成 (aws fsx CLI)
    ↓
Step 1: CloudFormation デプロイ (IAM Role のみ)
    ↓
Step 2: Snowflake Storage Integration 作成
    ↓
Step 3: DESCRIBE INTEGRATION → 信頼情報取得
    ↓
Step 4: CloudFormation 更新（信頼ポリシー）
    ↓
Step 5: External Stage 作成
    ↓
Step 6: External Table / Iceberg Table 作成
```

## Step 0: FSx for ONTAP S3 Access Point の作成

```bash
# 既存の Access Point を確認
aws fsx describe-s3-access-point-attachments --region <YOUR_REGION>

# 新規作成（必要な場合）
aws fsx create-and-attach-s3-access-point \
  --name snowflake-ap --type ONTAP \
  --ontap-configuration \
    'VolumeId=<YOUR_VOLUME_ID>,FileSystemIdentity={Type=UNIX,UnixUser={Name=root}}'
```

出力の **Alias**（例: `snowflake-ap-abc123-ext-s3alias`）をメモしてください。

## Step 1: CloudFormation スタックのデプロイ

```bash
# パラメータファイルをコピーして設定
cp params.example.json params.json
# params.json を編集: S3AccessPointArn と S3AccessPointAlias を設定

# デプロイ
./deploy.sh --region <YOUR_REGION>
```

テンプレートは IAM Role のみを作成します（二段階信頼ポリシー）。

## Step 2: Storage Integration の作成

Snowflake で実行（SnowSQL またはワークシート）:

```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE STORAGE INTEGRATION fsxn_storage_integration
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  ENABLED = TRUE
  STORAGE_AWS_ROLE_ARN = '<deploy.sh 出力の IAMRoleArn>'
  STORAGE_ALLOWED_LOCATIONS = (
    's3://<S3AccessPointAlias>/'
  );
```

## Step 3: 信頼ポリシー情報の取得

```sql
DESCRIBE INTEGRATION fsxn_storage_integration;
```

以下の値をメモ:
- `STORAGE_AWS_IAM_USER_ARN` → Snowflake の AWS アカウント ID（ARN 内の12桁の数字）
- `STORAGE_AWS_EXTERNAL_ID` → 信頼ポリシー用の External ID

## Step 4: CloudFormation の更新（信頼ポリシー）

```bash
./scripts/update_trust_policy.sh \
  --snowflake-arn "<STORAGE_AWS_IAM_USER_ARN>" \
  --external-id "<STORAGE_AWS_EXTERNAL_ID>"
```

または params.json を更新して `./deploy.sh` を再実行。

## Step 5: External Stage の作成

```sql
USE ROLE SYSADMIN;
USE DATABASE FSXN_LAKEHOUSE;
USE SCHEMA BRONZE;

CREATE OR REPLACE STAGE FSXN_BRONZE_STAGE
  STORAGE_INTEGRATION = fsxn_storage_integration
  URL = 's3://<S3AccessPointAlias>/';

-- 検証（注意: FSx for ONTAP S3 AP のレイテンシにより LIST は 30-60 秒以上かかる場合があります）
LIST @FSXN_BRONZE_STAGE;
```

## Step 6: テーブルの作成

SQL スクリプトを順番に実行:
1. `03_file_format.sql` — ファイルフォーマット定義
2. `04_external_table.sql` — External Table 作成
3. `05_iceberg_table.sql` — Iceberg Table 作成（Enterprise Edition 必要）
4. `06_snowpipe.sql` — Snowpipe 設定（オプション、FPolicy 必要）
5. `07_data_sharing.sql` — データ共有設定（オプション）
6. `08_directory_table.sql` — Directory Table（非構造化データ）
7. `09_snowpark_image_udf.sql` — Snowpark UDF

## パフォーマンスに関する注意事項

| 操作 | 想定レイテンシ | 備考 |
|------|--------------|------|
| CREATE STAGE | 30-60 秒 | 初回 S3 AP 接続確立 |
| LIST @stage | 30 秒〜5 分以上 | ファイル数に依存 |
| SELECT (External Table) | 数秒 | メタデータキャッシュ後 |
| Iceberg DML | 数秒 | 書き込み操作 |

> **ヒント**: FSx for ONTAP S3 AP は通常の S3 よりレイテンシが高いです。
> インタラクティブなクエリには、頻繁にアクセスするデータを Snowflake ネイティブテーブルに
> マテリアライズすることを検討してください。

## トラブルシューティング

### 問題: CREATE STAGE が非常に長い（数分）

**原因**: FSx for ONTAP S3 AP の初回接続レイテンシが高い

**解決**: これは想定される動作です。セッションのタイムアウトを延長してください:
`ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 600;`

### 問題: LIST @stage が空を返す、またはタイムアウト

**原因**: FSx for ONTAP S3 AP の ListObjects が遅い（特にファイル数が多い場合）

**解決**:
1. タイムアウト延長: `ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 600;`
2. サブディレクトリパスを使用してファイル数を削減
3. NFS マウント経由でデータの存在を確認

### 問題: GET_PRESIGNED_URL のエラー応答

**原因**: FSx for ONTAP S3 Access Point は Pre-signed URL を**サポートしていない**

**解決**: これは既知の制限です。代替アクセスパターンを使用:
- IAM ロール経由の直接 S3 API アクセス（アプリケーション向け）
- NFS マウントによる直接ファイルアクセス

### 問題: "Failure using stage area" エラー

**原因**: IAM Role の信頼ポリシーが未設定（Phase 2 未完了）

**解決**: `scripts/update_trust_policy.sh` を DESCRIBE INTEGRATION の値で実行

### 問題: Snowpipe でのファイル未検出

**原因**: FSx for ONTAP は S3 Event Notification を直接サポートしない

**解決**: FPolicy イベント駆動パターンを使用（`06_snowpipe.sql` および
`shared/cloudformation/fpolicy-*.yaml` 参照）
