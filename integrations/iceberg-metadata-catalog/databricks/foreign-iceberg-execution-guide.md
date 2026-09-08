# Foreign Iceberg 検証実行ガイド / Execution Guide

> 🌐 Bilingual (JA/EN)

## ステータス / Status

| 項目 | 値 |
|------|---|
| **作成日** | 2026-06-21 |
| **検証パス** | Glue HMS Federation（GA） + iceberg_rest（ブロック中） |
| **前提** | S3 Tables テーブルバケット作成済み、Iceberg テーブルに 170+ レコード存在（EMR 検証で確認済み） |
| **関連ブロッカー** | [BLK-005](../../../docs/ja/blocker-tracker.md)（`iceberg_rest` 未サポート） |

---

## エグゼクティブサマリ / Executive Summary

**Q: FSx for ONTAP 由来の Iceberg テーブルを Databricks UC から参照できるか？**

**A: 2 つのパスが存在し、1 つは GA で即時実行可能。**

| パス | Connection Type | ステータス | UC ガバナンス | 備考 |
|------|:---:|:---:|:---:|---|
| **A: Glue HMS Federation** | `glue` | ✅ GA（即時実行可能） | ✅ 適用可能 | Glue Catalog に登録された Iceberg テーブルを Foreign Table として参照 |
| **B: Iceberg REST** | `iceberg_rest` | ❌ ブロック（BLK-005） | ✅ 適用可能 | S3 Tables REST endpoint 直接接続。CONNECTION_TYPE_NOT_SUPPORTED エラー |

**推奨**: パス A（Glue HMS Federation）を即時実行し、S3 Tables の Iceberg テーブルを UC ガバナンス下で参照する。パス B は Databricks のサポートを待つ。

> ⚠️ **重要な仮説**: パス A の「Glue HMS Federation が S3 Tables Federated Catalog テーブルを透過的に参照できるか」は**未検証の仮説**です。従来の HMS Federation は通常の Glue Catalog テーブル向けに設計されており、S3 Tables の Federated Catalog レイヤーを透過するかは live 検証が必要です。確実な動作が必要な場合は、「代替: 通常 S3 上の Iceberg テーブル」セクションを先に実行してください。

---

## 背景: 2 つのパスが存在する理由

```
FSx for ONTAP → [DataSync/FPolicy] → S3 → PyIceberg → S3 Tables (Iceberg テーブル)
                                                              │
                                                              ├── Glue Federated Catalog (s3tablescatalog)
                                                              │       │
                                                              │       ├── Athena ─── ✅ 検証済み
                                                              │       ├── EMR Spark ─── ✅ 検証済み (7.13.0+)
                                                              │       └── Databricks?
                                                              │             ├── パス A: Glue HMS Federation ─── ✅ GA
                                                              │             └── パス B: iceberg_rest ─── ❌ ブロック
                                                              │
                                                              └── S3 Tables REST endpoint
                                                                      └── Databricks パス B ─── ❌ ブロック
```

### パス A の仕組み

Databricks の **Hive Metastore Federation for AWS Glue** は、AWS Glue Data Catalog に登録されたテーブル（Iceberg テーブル含む）を UC Foreign Catalog として参照する GA 機能。S3 Tables は Glue Federated Catalog（`s3tablescatalog`）経由で Glue に登録されるため、この経路で参照可能な**はず**。

### 検証が必要な理由

- Glue HMS Federation は「通常の Glue Catalog テーブル」でのみ検証されている例が多い
- **S3 Tables の Federated Catalog テーブル**（`s3tablescatalog/*` 配下）が HMS Federation 経由で見えるかは未確認
- `authorized_paths` に S3 Tables のパス（`s3://...--table--...`）を指定する必要がある可能性

---

## パス A: Glue HMS Federation 検証手順

### 前提条件

- [ ] Databricks ワークスペース（Unity Catalog 有効）
- [ ] AWS Glue に S3 Tables の Federated Catalog（`s3tablescatalog`）が登録済み
- [ ] Iceberg テーブルにデータが存在（`metadata.unstructured_files` — 170+ rows）
- [ ] IAM Role: Databricks → Glue + S3 Tables 読み取り権限

### Step 1: IAM Role の準備

Databricks 用 IAM Role に以下のポリシーを追加:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "glue:GetDatabase",
        "glue:GetDatabases",
        "glue:GetTable",
        "glue:GetTables",
        "glue:GetPartitions",
        "glue:BatchGetPartition"
      ],
      "Resource": [
        "arn:aws:glue:ap-northeast-1:<ACCOUNT_ID>:catalog",
        "arn:aws:glue:ap-northeast-1:<ACCOUNT_ID>:catalog/s3tablescatalog",
        "arn:aws:glue:ap-northeast-1:<ACCOUNT_ID>:catalog/s3tablescatalog/*",
        "arn:aws:glue:ap-northeast-1:<ACCOUNT_ID>:database/*",
        "arn:aws:glue:ap-northeast-1:<ACCOUNT_ID>:table/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3tables:GetTable",
        "s3tables:GetTableBucket",
        "s3tables:GetTableMetadataLocation",
        "s3tables:ListTables",
        "s3tables:ListNamespaces"
      ],
      "Resource": [
        "arn:aws:s3tables:ap-northeast-1:<ACCOUNT_ID>:bucket/fsxn-metadata-catalog",
        "arn:aws:s3tables:ap-northeast-1:<ACCOUNT_ID>:bucket/fsxn-metadata-catalog/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::*--table--*",
        "arn:aws:s3:::*--table--*/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "lakeformation:GetDataAccess"
      ],
      "Resource": "*"
    }
  ]
}
```

### Step 2: Storage Credential 作成

```sql
-- Databricks SQL Warehouse で実行
CREATE STORAGE CREDENTIAL IF NOT EXISTS s3tables_access
COMMENT 'Access to S3 Tables via Glue Federated Catalog'
WITH (
  AWS_IAM_ROLE = 'arn:aws:iam::<ACCOUNT_ID>:role/DatabricksS3TablesAccessRole'
);
```

### Step 3: Connection 作成（Glue HMS Federation）

```sql
-- パス A: Glue HMS Federation（GA — 即時実行可能）
CREATE CONNECTION IF NOT EXISTS glue_s3tables
TYPE glue
OPTIONS (
  region = 'ap-northeast-1',
  -- Glue Federated Catalog (s3tablescatalog) を指定
  catalog_id = '<ACCOUNT_ID>:s3tablescatalog/fsxn-metadata-catalog'
)
WITH CREDENTIAL s3tables_access;
```

> **注意**: `catalog_id` のフォーマットが `<ACCOUNT_ID>:s3tablescatalog/<TABLE_BUCKET>` で正しいか要確認。通常の Glue Catalog は `<ACCOUNT_ID>` のみ。Federated Catalog のパスはこの形式が想定されるが、実環境での動作確認が必要。

### Step 4: Foreign Catalog 作成

```sql
-- Foreign Catalog 作成
CREATE FOREIGN CATALOG IF NOT EXISTS s3tables_metadata
USING CONNECTION glue_s3tables
OPTIONS (
  authorized_paths = 's3://*--table--*'
);
```

### Step 5: テーブル確認

```sql
-- ネームスペース一覧
SHOW SCHEMAS IN s3tables_metadata;
-- 期待: metadata

-- テーブル一覧
SHOW TABLES IN s3tables_metadata.metadata;
-- 期待: unstructured_files

-- データクエリ
SELECT file_name, file_type, classification, confidence_score
FROM s3tables_metadata.metadata.unstructured_files
LIMIT 10;

-- レコード数
SELECT COUNT(*) FROM s3tables_metadata.metadata.unstructured_files;
-- 期待: 170+ (EMR 検証時の件数)
```

### Step 6: UC ガバナンス確認

```sql
-- UC Grants（Foreign Table へのアクセス制御）
GRANT SELECT ON TABLE s3tables_metadata.metadata.unstructured_files
TO `data_analysts_group`;

-- UC Tags 付与
ALTER TABLE s3tables_metadata.metadata.unstructured_files
SET TAGS ('data_source' = 'fsxn-metadata-catalog', 'data_classification' = 'internal');

-- Lineage 確認（クエリ実行後に UC lineage graph に表示されるか）
```

### Step 7: Refresh Semantics 確認

```sql
-- 1. 現在のレコード数を記録
SELECT COUNT(*) as before_count FROM s3tables_metadata.metadata.unstructured_files;

-- 2. AWS 側で PyIceberg を使って新規レコードを追加
--    (Lambda or ローカルスクリプトで実行)

-- 3. Refresh なしで再クエリ（stale な値が返るはず）
SELECT COUNT(*) as stale_count FROM s3tables_metadata.metadata.unstructured_files;

-- 4. Refresh 実行
REFRESH FOREIGN TABLE s3tables_metadata.metadata.unstructured_files;

-- 5. 再クエリ（更新された値が返るはず）
SELECT COUNT(*) as after_count FROM s3tables_metadata.metadata.unstructured_files;
```

---

## パス B: iceberg_rest（参考 — 現在ブロック中）

```sql
-- ❌ 以下は BLK-005 によりブロック中
-- CONNECTION_TYPE_NOT_SUPPORTED エラーが返る

CREATE CONNECTION s3tables_iceberg_rest TYPE iceberg_rest
OPTIONS (
  uri = 'https://glue.ap-northeast-1.amazonaws.com/iceberg',
  warehouse = '<ACCOUNT_ID>:s3tablescatalog/fsxn-metadata-catalog',
  credential_name = 's3tables_access'
);
-- Error: CONNECTION_TYPE_NOT_SUPPORTED
```

> パス B は Databricks が `iceberg_rest` を Connection Type として GA サポートした後に再検証する。現時点ではパス A を推奨。

---

## 成功基準 / Success Criteria

| 基準 | 期待結果 | パス A | パス B |
|------|---------|:---:|:---:|
| Foreign Catalog 作成成功 | エラーなし | 🔲 要検証 | ❌ ブロック |
| SHOW SCHEMAS でネームスペース表示 | `metadata` | 🔲 要検証 | ❌ |
| SHOW TABLES でテーブル表示 | `unstructured_files` | 🔲 要検証 | ❌ |
| SELECT クエリ成功 | データ返却 | 🔲 要検証 | ❌ |
| COUNT(*) 一致 | EMR 検証値 (170+) と一致 | 🔲 要検証 | ❌ |
| REFRESH FOREIGN TABLE 動作 | 最新 snapshot 反映 | 🔲 要検証 | ❌ |
| UC Grants 適用 | アクセス制御動作 | 🔲 要検証 | ❌ |
| UC Tags 付与 | Tag 設定成功 | 🔲 要検証 | ❌ |
| UC Lineage 記録 | クエリ履歴に表示 | 🔲 要検証 | ❌ |

---

## リスクと想定される課題

### データ鮮度のレイヤー累積

Foreign Iceberg パスでは、データ鮮度に**3 つのレイヤー**が累積します:

| レイヤー | 遅延 | 制御方法 |
|---------|------|---------|
| DataSync RPO（FSx for ONTAP → S3） | 5 分〜24 時間 | DataSync スケジュール |
| PyIceberg 書き込み → Iceberg snapshot | 秒〜分 | Lambda/Step Functions 実行頻度 |
| REFRESH FOREIGN TABLE（UC 側） | 手動/スケジュール | Databricks Workflow で定期実行 |

**合計鮮度**: DataSync RPO + Iceberg 書き込み遅延 + REFRESH 遅延 = **10 分〜24 時間+**

> **鮮度設計**: Foreign Iceberg は「分析用メタデータカタログ」の参照に最適であり、リアルタイム性が求められるユースケースには適しません。リアルタイム要件がある場合は FPolicy → Kafka → Structured Streaming パスを併用してください。

| リスク | 影響 | 緩和策 |
|--------|------|--------|
| `catalog_id` に Federated Catalog パスが未サポート | Foreign Catalog 作成失敗 | 通常の Glue Catalog ID (`<ACCOUNT_ID>` のみ) を試行 |
| `authorized_paths` に S3 Tables のパスが合致しない | テーブル読み取り拒否 | `s3://*` を暫定設定して動作確認後に絞り込み |
| Lake Formation credential vending が Databricks に未対応 | データ読み取り失敗 | Storage Credential の IAM Role で直接 S3 読み取り権限を付与 |
| Foreign Iceberg が S3 Tables の internal パス形式を解決できない | ファイル読み取り失敗 | Glue Iceberg REST 経由ではなく直接 S3 パス読み取りで回避 |

---

## 代替: 通常 S3 上の Iceberg テーブル（確実パス）

S3 Tables ではなく**通常の S3 バケット上に Iceberg テーブルを作成**し、Glue Catalog に登録する方法は確実に動作する:

```bash
# PyIceberg で通常 S3 上に Iceberg テーブル作成
# (S3 Tables ではなく通常の s3://<BUCKET>/iceberg/ パス)
python3 integrations/iceberg-metadata-catalog/scripts/create-iceberg-on-standard-s3.py
```

```sql
-- Glue Catalog に登録された通常 S3 Iceberg テーブルを Foreign Catalog で参照
CREATE CONNECTION glue_standard TYPE glue
OPTIONS (region = 'ap-northeast-1');

CREATE FOREIGN CATALOG glue_iceberg
USING CONNECTION glue_standard
OPTIONS (authorized_paths = 's3://<BUCKET>/iceberg/');

-- これは確実に動作する（Glue HMS Federation の GA 機能）
SELECT * FROM glue_iceberg.metadata_db.unstructured_files LIMIT 10;
```

> **通常 S3 パスの利点**: S3 Tables の複雑さ（Federated Catalog、credential vending、internal パス）を回避。DataSync 同期先の S3 バケットに Iceberg テーブルを直接作成し、Glue Catalog 経由で UC に公開する。

---

## 検証実行計画

| 順序 | 検証内容 | 所要時間 | ブロッカー |
|:---:|---|:---:|:---:|
| 1 | 通常 S3 Iceberg + Glue HMS Federation（確実パス） | 1-2 時間 | なし |
| 2 | S3 Tables + Glue Federated Catalog + HMS Federation（パス A） | 2-3 時間 | Federated Catalog パスの動作確認 |
| 3 | iceberg_rest（パス B） | — | BLK-005 待ち |

**推奨**: 順序 1 から実行し、確実に動作するパスを確立した後に順序 2 を試行。

---

## 関連ドキュメント

- [UC 接続総合ガイド](../../../docs/ja/fsx-ontap-to-databricks-unity-catalog-guide.md) — パス 4: Foreign Iceberg
- [ブロッカー追跡](../../../docs/ja/blocker-tracker.md) — BLK-005
- [互換性マトリクス](../../../docs/ja/compatibility-matrix.md) — S3 Tables セクション
- [S3 Tables CloudFormation](../cloudformation/s3-tables-setup.yaml) — インフラ構築
- [EMR Spark 検証結果](../lakehouse-tools/tool-compatibility-matrix.yaml) — EMR 7.13.0+ で動作確認済み
- [AWS 公式ブログ: Glue Iceberg REST → Databricks](https://aws.amazon.com/blogs/big-data/access-amazon-s3-iceberg-tables-from-databricks-using-aws-glue-iceberg-rest-catalog-in-amazon-sagemaker-lakehouse)
- [Databricks: Hive Metastore Federation for AWS Glue](https://docs.databricks.com/aws/en/query-federation/hms-federation-glue)
