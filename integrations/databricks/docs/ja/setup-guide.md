🌐 [English](../en/setup-guide.md) | **日本語**

# Databricks セットアップガイド

## 概要

FSx for NetApp ONTAP を Databricks Unity Catalog の External Location として設定し、
Delta Lake / Iceberg テーブルのストレージレイヤーとして使用する手順です。

## 前提条件

- AWS アカウントに FSx for NetApp ONTAP がデプロイ済み
- FSx for ONTAP SVM で S3 プロトコルが有効化済み
- Databricks ワークスペース（Unity Catalog 有効）
- AWS CLI v2 設定済み
- Terraform 1.5+ (Unity Catalog リソース管理用)

## アーキテクチャ

```
Databricks Unity Catalog
    │
    ├── Storage Credential (IAM Role)
    │       │
    │       └── AssumeRole ──→ fsxn-lakehouse-databricks-s3-role
    │
    └── External Location
            │
            └── s3://<s3ap-alias>/ ──→ S3 Access Point ──→ FSx for ONTAP Volume
```

## Step 1: CloudFormation スタックのデプロイ

### パラメータの準備

| パラメータ | 説明 | 例 |
|-----------|------|-----|
| S3BucketName | FSx for ONTAP SVM の S3 バケット名 | `svm-lakehouse` |
| VpcId | FSx for ONTAP が存在する VPC | `vpc-0123456789abcdef0` |
| SubnetIds | プラットフォームサブネット | `subnet-xxx,subnet-yyy` |
| DatabricksAccountId | Databricks AWS アカウント | `414351767826` |
| DatabricksWorkspaceId | ワークスペース ID | `1234567890` |
| ExternalId | 外部 ID（後述） | Databricks UI から取得 |

### デプロイコマンド

```bash
aws cloudformation deploy \
  --template-file integrations/databricks/template.yaml \
  --stack-name fsxn-databricks-integration \
  --parameter-overrides \
    S3BucketName=svm-lakehouse \
    VpcId=vpc-0123456789abcdef0 \
    SubnetIds=subnet-xxx,subnet-yyy \
    DatabricksWorkspaceId=1234567890 \
    ExternalId=<databricks-external-id> \
  --capabilities CAPABILITY_NAMED_IAM \
  --region <YOUR_REGION>
```

### 出力値の確認

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-databricks-integration \
  --query 'Stacks[0].Outputs' \
  --output table
```

重要な出力値:
- `DatabricksRoleArn` — Storage Credential に使用
- `S3AccessPointAlias` — External Location の URL に使用

## Step 2: External ID の取得

1. Databricks ワークスペースにログイン
2. **Catalog** → **External Data** → **Storage Credentials** → **Create credential**
3. **AWS IAM Role** を選択
4. 表示される **External ID** をコピー
5. CloudFormation の `ExternalId` パラメータに設定してスタックを更新

## Step 3: Storage Credential の作成

### Terraform を使用する場合

```bash
cd integrations/databricks/terraform

terraform init
terraform plan \
  -var="databricks_workspace_url=https://xxx.cloud.databricks.com" \
  -var="databricks_account_id=your-account-id" \
  -var="s3_access_point_alias=<cfn-output-alias>" \
  -var="s3_access_point_arn=<cfn-output-arn>" \
  -var="iam_role_arn=<cfn-output-role-arn>" \
  -var="metastore_id=<your-metastore-id>"

terraform apply
```

### Databricks UI を使用する場合

1. **Catalog** → **External Data** → **Storage Credentials**
2. **Create credential** をクリック
3. 設定:
   - Name: `fsxn-lakehouse-fsxn-credential`
   - IAM Role ARN: CloudFormation 出力の `DatabricksRoleArn`
4. **Create** をクリック

## Step 4: External Location の作成

### Databricks UI を使用する場合

1. **Catalog** → **External Data** → **External Locations**
2. **Create location** をクリック
3. 設定:
   - Name: `fsxn-lakehouse-root`
   - URL: `s3://<S3AccessPointAlias>/`
   - Storage Credential: `fsxn-lakehouse-fsxn-credential`
4. **Test connection** で接続確認
5. **Create** をクリック

## Step 5: 接続テスト

ノートブック `01_setup_external_location.py` を実行して接続を検証します。

```python
# Databricks ノートブックで実行
files = dbutils.fs.ls("s3://<s3ap-alias>/")
print(f"Files found: {len(files)}")
```

## Step 6: テーブル作成

ノートブックを順番に実行:

1. `02_create_external_table.py` — Parquet/CSV/JSON テーブル
2. `03_delta_lake_on_fsxn.py` — Delta Lake テーブル
3. `04_iceberg_on_fsxn.py` — Iceberg テーブル

## トラブルシューティング

### 問題: Storage Credential のテストが失敗

**原因**: IAM Role の信頼ポリシーに External ID が設定されていない

**解決**:
1. CloudFormation の `ExternalId` パラメータを確認
2. スタックを更新して正しい External ID を設定

### 問題: External Location のテストで "Access Denied"

**原因**: S3 AP ポリシーが IAM Role を許可していない

**解決**:
1. S3 AP ポリシーの Principal が正しい Role ARN か確認
2. VPC 条件が正しいか確認
3. IAM Role のポリシーに S3 AP ARN が含まれているか確認

### 問題: ListObjects の空応答

**原因**: FSx for ONTAP SVM の S3 バケットにデータがない、またはパスが間違っている

**解決**:
1. ONTAP CLI で S3 バケットの内容を確認
2. S3 AP のパスプレフィックスを確認
3. サンプルデータジェネレーターを実行

## 次のステップ

- [Unity Catalog 統合詳細](unity-catalog-integration.md)
- [ノートブック 05: ML Feature Store](../../notebooks/05_ml_feature_store.py)
- [ノートブック 06: Snapshot + Time Travel](../../notebooks/06_snapshot_time_travel.py)
