# クイックスタートガイド

🌐 [English](../en/getting-started.md)

## 前提条件

- AWS アカウント
- Amazon FSx for NetApp ONTAP（FSx for ONTAP）ファイルシステム（デプロイ済み）
- FSx for ONTAP SVM で S3 Access Point が有効
- AWS CLI v2 設定済み
- Python 3.12+

## Step 1: リポジトリのクローン

```bash
git clone https://github.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations.git
cd FSx-for-ONTAP-Lakehouse-Integrations
```

## Step 2: 基本インフラのデプロイ

> **注意:** `<YOUR_REGION>` を対象の AWS リージョン（例: `us-east-1`, `ap-northeast-1`）に置き換えてください。リージョンは設定可能で、FSx for ONTAP ファイルシステムがデプロイされているリージョンと一致させる必要があります。

### VPC + ネットワーク

```bash
aws cloudformation deploy \
  --template-file shared/cloudformation/vpc-networking.yaml \
  --stack-name fsxn-lakehouse-vpc \
  --capabilities CAPABILITY_IAM \
  --region <YOUR_REGION>
```

### FSx for ONTAP + S3 Access Point

```bash
aws cloudformation deploy \
  --template-file shared/cloudformation/fsxn-s3ap-base.yaml \
  --stack-name fsxn-lakehouse-base \
  --parameter-overrides \
    VpcId=<vpc-id> \
    PreferredSubnetId=<subnet-1> \
    StandbySubnetId=<subnet-2> \
    FSxNSecurityGroupId=<sg-id> \
    S3BucketName=<svm-bucket-name> \
  --capabilities CAPABILITY_IAM \
  --region <YOUR_REGION>
```

## Step 3: 接続テスト

```bash
# S3 AP alias を CloudFormation 出力から取得
AP_ALIAS=$(aws cloudformation describe-stacks \
  --stack-name fsxn-lakehouse-base \
  --query 'Stacks[0].Outputs[?OutputKey==`S3AccessPointAlias`].OutputValue' \
  --output text)

# 接続テスト実行（AWS_DEFAULT_REGION 環境変数を使用、または --region を指定）
python shared/scripts/validate-access.py --access-point-alias $AP_ALIAS --region <YOUR_REGION>
```

## Step 4: ベンダー統合の選択

| ベンダー | ディレクトリ | ステータス |
|---------|------------|----------|
| Athena | `integrations/athena/` | ✅ セキュリティ検証済み |
| Glue | `integrations/glue/` | ✅ 機能検証済み |
| Delta Lake OSS | `integrations/delta-lake-oss/` | ✅ 読み取り検証済み / ❌ 書き込み非サポート |
| Databricks | `integrations/databricks/` | ⚠️ ブロック（UC が S3 Tables 未対応） |
| Snowflake | `integrations/snowflake/` | ✅ 検証済み（Glue REST + VENDED_CREDENTIALS で Iceberg 読み取り; S3 AP 経由 External Stage） |

各ベンダーの `README.md` と `docs/ja/setup-guide.md` を参照してください。

## 次のステップ

- [アーキテクチャ概要](architecture.md)
- [対応リージョン](supported-regions.md)
- [ベンダー比較](vendor-comparison.md)
