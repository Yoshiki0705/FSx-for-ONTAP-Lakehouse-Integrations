# デモガイド

🌐 日本語 | [English](demo-guide.md)

## 概要

本ガイドにより、Iceberg メタデータカタログの完全なデモを約15分で実行できます。全リソースはアイドル時に scale-to-zero（コスト $0）。

**デモフロー**: メタデータスキャン → AI 分類 → Athena クエリ → ベクトル検索 → PII 匿名化

## 前提条件

| 要件 | 詳細 |
|------|------|
| AWS CLI v2 | 適切な権限で設定済み |
| Python 3.12+ | パッケージ: `boto3 pyarrow 'pyiceberg[s3tables]' opensearch-py requests-aws4auth` |
| FSx for ONTAP | S3 Access Point 設定済み（alias が `-ext-s3alias` で終わる） |
| **Bedrock アクセス** | **Claude 3 Haiku + Titan Embeddings V2 が対象リージョンで有効であること** ([モデルアクセスの有効化](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html)) |

## クイックスタート（1コマンド）

```bash
cd integrations/iceberg-metadata-catalog/demo/scripts
chmod +x run-demo.sh
./run-demo.sh --ap-alias <your-ap-alias-ext-s3alias>
```

## ステップバイステップ

### 1. インフラデプロイ (~5分)

```bash
aws cloudformation deploy \
  --template-file cloudformation/demo-stack.yaml \
  --stack-name fsxn-metadata-catalog-demo \
  --parameter-overrides S3AccessPointAlias=<your-ap-alias> \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

**作成されるリソース**:
- S3 Tables テーブルバケット（メタデータストレージ）
- OpenSearch Serverless NextGen コレクション（ベクトル検索、scale-to-zero）
- Athena ワークグループ（SQL クエリ）

### 2. Glue Catalog 登録 + Iceberg テーブル作成 (~2分)

```bash
# S3 Tables フェデレーテッドカタログ登録（初回のみ）
aws glue create-catalog --name "s3tablescatalog" --catalog-input '{
  "FederatedCatalog": {
    "Identifier": "arn:aws:s3tables:ap-northeast-1:<ACCOUNT_ID>:bucket/*",
    "ConnectionName": "aws:s3tables"
  },
  "CreateDatabaseDefaultPermissions": [],
  "CreateTableDefaultPermissions": []
}' --region ap-northeast-1

# Iceberg テーブル作成 + メタデータスキャン
python3 ../../scripts/initial-metadata-scan.py \
  --access-point-arn <your-ap-alias-ext-s3alias> \
  --table-bucket-arn arn:aws:s3tables:ap-northeast-1:<ACCOUNT_ID>:bucket/fsxn-metadata-catalog \
  --max-files 100
```

### 3. AI エンリッチメント実行 (~3分)

```bash
python3 scripts/demo-enrich.py \
  --table-bucket-arn arn:aws:s3tables:ap-northeast-1:<ACCOUNT_ID>:bucket/fsxn-metadata-catalog \
  --ap-alias <your-ap-alias-ext-s3alias> \
  --max-files 5
```

### 4. Athena クエリ (~1分)

```sql
-- Athena コンソールまたは CLI で:
SELECT file_name, classification, confidence_score, summary
FROM "s3tablescatalog/fsxn-metadata-catalog"."metadata"."unstructured_files"
WHERE enrichment_status = 'completed'
ORDER BY confidence_score DESC;

-- 本番用クエリ（重複排除パターン — Iceberg append-only 書き込み対応）:
WITH ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY file_id ORDER BY modified_at DESC) as rn
  FROM "s3tablescatalog/fsxn-metadata-catalog"."metadata"."unstructured_files"
)
SELECT file_name, classification, confidence_score, summary
FROM ranked
WHERE rn = 1 AND is_deleted = false
ORDER BY confidence_score DESC;
```

### 5. ベクトル類似検索 (~1分)

```bash
python3 scripts/demo-search.py --query "find invoice or payment documents"
```

### 6. PII 匿名化 (~1分)

```bash
python3 scripts/demo-anonymize.py --ap-alias <your-ap-alias-ext-s3alias>
```

## デモトーキングポイント

| 時間 | デモステップ | キーメッセージ |
|------|-----------|-------------|
| 0:00 | FSx for ONTAP S3 AP のファイル表示 | 「非構造化データは ONTAP に残る — S3 コピー不要」 |
| 2:00 | メタデータスキャン実行 | 「38ファイルを30秒でカタログ化」 |
| 4:00 | Athena クエリ表示 | 「どのファイルも SQL で2秒以内に検索可能」 |
| 6:00 | AI 分類結果表示 | 「Bedrock が画像を自動分類、$0.01/ファイル」 |
| 8:00 | 類似検索実行 | 「自然言語で類似ファイルを発見」 |
| 10:00 | PII 検出表示 | 「7種類の PII を検出、全て自動墨消し」 |
| 12:00 | コストサマリー表示 | 「排除した S3 コピーのコスト以下で全機能を実現」 |

## クリーンアップ

```bash
# デモスタック削除（全リソース）
aws cloudformation delete-stack --stack-name fsxn-metadata-catalog-demo --region ap-northeast-1

# S3 Tables データ削除（必要な場合）
aws s3tables delete-table --table-bucket-arn <ARN> --namespace metadata --name unstructured_files --region ap-northeast-1
aws s3tables delete-namespace --table-bucket-arn <ARN> --namespace metadata --region ap-northeast-1
aws s3tables delete-table-bucket --table-bucket-arn <ARN> --region ap-northeast-1

# Glue カタログ削除（共有 — 不要な場合のみ）
aws glue delete-catalog --name s3tablescatalog --region ap-northeast-1
```

## トラブルシューティング

| 問題 | 解決策 |
|------|--------|
| Athena で `CATALOG_NOT_FOUND` | Step 2 (Glue カタログ登録) を実行 |
| Athena で `COLUMN_NOT_FOUND` | Lake Formation SELECT 権限を付与 |
| OpenSearch 検索が 0 件 | 30秒待機（scale-to-zero cold start）後にリトライ |
| Bedrock `ThrottlingException` | --max-files を減らすか 30秒待機 |
| Bedrock `AccessDeniedException` | モデルアクセスを有効化: [Bedrock コンソール](https://console.aws.amazon.com/bedrock/home#/modelaccess) → Claude 3 Haiku + Titan Embeddings V2 のアクセスをリクエスト |
| `ModuleNotFoundError: pyiceberg` | `pip install 'pyiceberg[s3tables]'` |
| Lambda ログが見つからない | CloudWatch Logs → `/aws/lambda/fsxn-metadata-sync` を確認 |
| パイプライン全体の状態確認 | `aws cloudwatch get-metric-data` で DLQ + Lambda エラー率を一括確認（アーキテクチャドキュメント参照） |

> **本番運用注記**: デモでは可読性のためにテキストログを使用しています。本番 Lambda では JSON 構造化ログ（`aws_lambda_powertools` または `structlog`）を使用し、CloudWatch Logs Insights での効率的なクエリを実現してください。

## デモ後フォローアップチェックリスト

デモ後、1週間以内に以下を完了してください：

- [ ] デモ録画を利用者側のステークホルダーに共有（asciinema リンクまたは GIF）
- [ ] デモ後フィードバックアンケートを送付（`docs/post-demo-survey.md`）
- [ ] 「次のステップ」テンプレートを送付（`docs/next-steps-template.md`）
- [ ] 1週間後のフォローアップミーティングを設定（PoC スコープ議論）
- [ ] デモ結果を CRM に記録（関心度、優先ユースケース、タイムライン）
- [ ] 関心度 ≥ 4 の場合: SA チームと PoC 計画を開始
