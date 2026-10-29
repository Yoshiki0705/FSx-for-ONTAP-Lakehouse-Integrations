# AWS Athena 統合

🌐 [English](../../README.md) | **日本語**

> **検証ステータス: ✅ セキュリティ検証済み (2026-05-23)**
>
> ベンチマーク: ピークスループット 54.8 MB/s、5M 行を 2.2 秒でクエリ（103 MB Parquet、128 MB/s プロビジョニング）。
> 9/9 ネガティブセキュリティテスト PASS。CloudTrail 監査確認済み。

## 概要

Amazon Athena から Amazon FSx for NetApp ONTAP（FSx for ONTAP）のデータを直接クエリします。
Glue Data Catalog と S3 Access Points を使用したサーバーレス・従量課金制の分析基盤です。

## アーキテクチャ

```
Athena (サーバーレス SQL)
    │
    └── Glue Data Catalog
            │
            ├── Glue Crawler (スキーマ検出)
            │
            └── S3 Access Point (internet origin) ──→ FSx for ONTAP Volume
                                                        ├── transactions/ (Parquet, パーティション)
                                                        ├── customers/ (CSV)
                                                        ├── events/ (JSON)
                                                        └── gold/ (CTAS 出力)
```

## 重要: ネットワークオリジン

Athena は **internet ネットワークオリジン** の S3 Access Point が必要です。
VPC 限定のアクセスポイントは Athena では動作しません。
### SVM が Active Directory に参加している場合
ここでの読み取りの検証は、ドメインコントローラに到達できる AD 参加の SVM で行いました。**WINDOWS** タイプのアクセスポイントでは、アクセスポイント経由のデータ操作（ListObjectsV2 / GetObject）に SVM からドメインコントローラへの到達が必要で、到達できないと `HeadBucket` は成功してもこれらの操作は失敗します。AD 非参加の SVM 上の **UNIX** タイプのアクセスポイントは、この依存を避けられます。コントローラが到達不能な場合の挙動はここでは測っていません。ファイルの所有の仕方に合うユーザータイプ（`S3AccessPointName` のマッピング）を選び、WINDOWS の場合はコントローラへの到達性を保ってください。

## 既存の分析エンジンを使っている場合
再利用の価値があるのは到達の経路です。S3 Access Point を使うと、ONTAP ボリュームを別の S3 バケットへコピーせずに、その場でクエリエンジンから読めます。Athena はその上のエンジンの 1 つで、本リポジトリには他エンジンの統合（`integrations/glue`、`integrations/emr-spark`、`integrations/trino-starburst`、`integrations/redshift-spectrum`、`integrations/snowflake`、`integrations/databricks` など）もあります。どのエンジンが合うかは、すでに運用しているものによります。

- **Athena（この統合）**: サーバーレスで、動かすクラスタがなく、クエリ単位の課金です。internet-origin のアクセスポイントとデータ上の Glue テーブルが要ります。
- **既存のエンジン（EMR/Spark、Trino、Redshift Spectrum、マネージドのレイクハウス）**: 外部テーブルの場所を同じアクセスポイントのエイリアスに向け、既存のカタログを使います。考慮点: アクセスポイントのネットワークとユーザータイプの制約はエンジンによらず同じで、FSx for ONTAP S3 Access Points が実装しない条件付き・トランザクショナルな書き込み（例: Delta Lake のコミット）は動きません。コミットが Glue カタログを通る Iceberg は動きます（上記）。

いずれの場合も、アクセスポイントはデータをコピーしません。ファイルは ONTAP ボリュームに残り、NFS/SMB からも引き続き読めます。エンジンの選択は「どれが優れているか」ではなく、運用しているものに合わせて決めてください。下のストレージの到達経路はどれも同じです。

## データフォーマット対応

| フォーマット | 読み取り | 書き込み (CTAS) | 備考 |
|------------|---------|----------------|------|
| Parquet | ✅ | ✅ | パーティションプルーニング対応 |
| CSV | ✅ | ✅ | |
| JSON | ✅ | ✅ | |
| ORC | ✅ | ✅ | |
| Avro | ✅ | ❌ | |

## 非構造化データ対応

| フォーマット | 対応 | アクセス方法 | ユースケース |
|------------|:---:|------------|------------|
| 画像 (JPEG, PNG, TIFF) | ❌ | N/A（構造化データ用 SQL エンジン） | — |
| 動画 (MP4, MOV) | ❌ | N/A | — |
| ドキュメント (PDF, DOCX) | ❌ | N/A | — |
| 音声 (WAV, MP3) | ❌ | N/A | — |
| バイナリ / アーカイブ | ❌ | N/A | — |

Athena は構造化データ（Parquet, CSV, JSON）のクエリに最適化された SQL エンジンです。非構造化データ（画像、動画、音声）の直接クエリはサポートされていません。メタデータテーブルを作成してファイルパスを管理し、他のサービス（Lambda, Bedrock）と連携することで処理パイプラインを構築できます。

**非構造化データワークフローのパターン:**
1. **メタデータテーブル** — Glue Crawler でファイルパス・サイズ・更新日時をカタログ化
2. **Athena + Lambda UDF** — クエリ結果のファイルパスを Lambda に渡して処理
3. **パイプライン連携** — Athena でファイルを特定し、Lambda/Bedrock で処理

```sql
-- ファイルメタデータをクエリ（Glue Crawler で登録済みの場合）
SELECT key, size, last_modified
FROM fsxn_file_catalog
WHERE key LIKE '%.pdf'
ORDER BY last_modified DESC;
```

**FSx for ONTAP 上の非構造化データの推奨代替手段:**
- **AWS Lambda** でサーバーレスファイル処理（[AWS チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-process-files-with-lambda.html)）
- **Amazon Bedrock** でドキュメント RAG（[AWS チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)）
- **Snowflake**（Directory Table + GET_PRESIGNED_URL）でファイルカタログとセキュア URL 生成

## クイックスタート

```bash
# 1. パラメータをコピーして値を設定
cp params.example.json params.json

# 2. サンプルデータを生成
pip install pandas pyarrow
python scripts/generate_sample_data.py

# 3. FSx for ONTAP に NFS 経由でアップロード
./scripts/upload_sample_data.sh

# 4. インフラをデプロイ
./deploy.sh

# 5. 接続を検証
python scripts/validate_connectivity.py
```
