# Trino / Starburst 統合

🌐 [English](../../README.md) | **日本語**

> **検証ステータス: ✅ Trino 481 で読み取り検証済み (2026-05-26)**
>
> 根拠: [`verification-pack/trino/evidence/2026-05-26`](../../../../verification-pack/trino/evidence/2026-05-26/evidence-record.yaml)（Trino 481、Docker、Glue Catalog、ネイティブ S3 とパススタイルアクセス、ap-northeast-1）
>
> - **読み取り**: FSx for ONTAP S3 Access Points 上で、`SHOW SCHEMAS`、10K / 5M 行 Parquet の `COUNT(*)`、`GROUP BY`、述語プッシュダウン付きのフィルターが成功
> - **書き戻し (CTAS)**: 481 では未テスト。Trino 438 のファイルベースメタストアでは、メタストアが原因で失敗した（S3 Access Points の問題ではない）
> - **セッションポリシー問題なし**: 直接 IAM 認証情報、中間ガバナンスレイヤーなし
> - **481 向けに設定を更新してからは、再実行していない**: 記録の検証では `fs.native-s3.enabled` を使いました。481 はこの名前を `fs.s3.enabled` に置き換え済みと警告します（このリポジトリの `fsxn.properties` は新しい名前を使用）。新しい名前では、サーバーが起動して環境変数の認証情報を受け付けること（偽の認証情報で確認）までは確認しましたが、Glue と S3 Access Points へのクエリは実行していません
>
> **ベンチマーク (Trino 438, シングルノード Docker arm64, ap-northeast-1):** 以前のファイルメタストア構成での測定です。記録しているのはこの README だけで、2026-05-24 の証拠記録は実行前の予測です。481 の結果ではなく、過去の参考値として扱ってください。
>
> | クエリ | 10K 行 | 5M 行 (103 MB) |
> |-------|--------|----------------|
> | COUNT(*) | 1,136 ms | 1,075 ms |
> | GROUP BY + AVG | 860 ms | 1,462 ms |
> | WHERE フィルター | — | 1,227 ms |

## 概要

Trino（オープンソース分散 SQL クエリエンジン）を使用して FSx for ONTAP のデータを S3 Access Points 経由でクエリします。Trino の S3 ファイルシステム実装はパススタイルアクセスをサポートしており、FSx for ONTAP S3 AP エイリアスと互換性があります。

この統合は **Trino 481**（`trinodb/trino:481`、`docker-compose.yaml` で固定）を対象にします。以前の Trino 438 の構成（ファイルメタストア、`hive.s3.*`）は、481 が旧 S3 ファイルシステムを削除したため、481 では起動しません。

## アーキテクチャ

```
Trino 481 (Docker, シングルノード)
    │
    ├── Hive Connector ──→ AWS Glue Data Catalog (スキーマとテーブル)
    │
    └── S3 ファイルシステム (ネイティブ、パススタイルアクセス)
            │
            └── FSx S3 Access Point (internet-origin)
                    │
                    └── FSx for ONTAP Volume (Parquet ファイル)
```

## 非構造化データ対応

| フォーマット | 対応 | アクセス方法 | ユースケース |
|------------|:---:|------------|------------|
| 画像 (JPEG, PNG, TIFF) | ❌ | N/A（構造化データ用 SQL エンジン） | — |
| 動画 (MP4, MOV) | ❌ | N/A | — |
| ドキュメント (PDF, DOCX) | ❌ | N/A | — |
| 音声 (WAV, MP3) | ❌ | N/A | — |
| バイナリ / アーカイブ | ❌ | N/A | — |

Trino は構造化データの分散 SQL クエリに特化したエンジンです。非構造化データの直接クエリはサポートされていません。メタデータテーブルとフェデレーテッドクエリを活用したパターンが可能です。

**パターン:**
1. **メタデータテーブル** — ファイルパス・サイズ・タイプを Hive テーブルとして登録しクエリ
2. **マルチソースフェデレーション** — FSx for ONTAP S3 AP のファイルカタログと他のデータソース（RDS, PostgreSQL）を JOIN
3. **Hive Connector** — パススタイルアクセスで S3 AP 上の Parquet メタデータを直接読み取り

```sql
-- ファイルカタログをクエリ
SELECT file_path, file_type, file_size, last_modified
FROM fsxn.default.file_catalog
WHERE file_type = 'image/jpeg'
  AND file_size > 1000000;

-- 他のデータソースとフェデレーテッド JOIN
SELECT f.file_path, m.model_name, m.accuracy
FROM fsxn.default.file_catalog f
JOIN ml_catalog.default.model_results m ON f.file_path = m.input_path;
```

## 主な設定

Trino のネイティブ S3 ファイルシステムは、S3 Access Point のエイリアスを解決するために、`s3.path-style-access=true` と明示的な `s3.endpoint` が必要です（DuckDB の `s3_url_style='path'` と同じパターン）。スキーマとテーブルは Glue Data Catalog に置きます。

```properties
# config/etc/catalog/fsxn.properties
connector.name=hive
hive.metastore=glue
hive.metastore.glue.region=ap-northeast-1
fs.s3.enabled=true
s3.path-style-access=true
s3.endpoint=https://s3.ap-northeast-1.amazonaws.com
s3.region=ap-northeast-1
```

認証情報は AWS の既定の認証情報チェーンから読みます。`docker-compose.yaml` はシェルの `AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`、`AWS_SESSION_TOKEN` をコンテナに渡すので、一時的な認証情報も使えます。

481 で使えなくなった設定:

| 設定 | Trino 481 での結果 | 代わり |
|---|---|---|
| `hive.s3.*`（パススタイル、エンドポイント、リージョン、アクセスキー） | サーバーが起動しない（`Configuration property 'hive.s3.endpoint' was not used`） | `fs.s3.enabled=true` と `s3.*` |
| `file:` の場所を使う `hive.metastore=file` | スキーマ作成時に `No factory for ...` で失敗 | `hive.metastore=glue`。`fs.hadoop.enabled=true` を足すとローカルの確認では動きましたが、481 のリリースノートはこの設定を HDFS 専用と記載しています |
| `fs.native-s3.enabled` | 動作するが「置き換え済み」の警告が出る | `fs.s3.enabled` |

## 期待される動作

Parquet の読み取りは 481 で検証済みです（上のステータスを参照）。Parquet の書き込み（CTAS）は 481 では未テストで、`03_write_back.sql` がそのテストです。Delta と Iceberg の書き込みは、他のエンジンと同じ atomic rename の制約で失敗すると予想しますが、ここでは試していません。認証は直接の IAM 認証情報で、中間のガバナンスレイヤーはないため、セッションポリシーの問題はありません。

## Glue Iceberg REST エンドポイント経由の S3 Tables

`config/etc/catalog/s3tables_glue_rest.properties` は、S3 Tables 用の 2 つ目のカタログを定義します。481 では読み込まれますが、署名なしのリクエストを送るため、Glue は `Missing Authentication Token` を返します。Trino が署名するのは `iceberg.rest-catalog.security=SIGV4` を指定したときだけです。ファイルではこの設定をコメントアウトしています。有効にすると 481 は `s3.aws-access-key` と `s3.aws-secret-key` がないと起動せず、どちらもセッショントークンを受け付けないためです。手順はファイルのコメントにあります。偽の認証情報での対照実験では、481 が署名つきのリクエストを送ることを確認しました（`The security token included in the request is invalid`）。有効な認証情報での実行は、していません。

## クイックスタート

前提: Docker、シェルにエクスポートした AWS 認証情報、Glue Data Catalog を使う権限。SSO の場合は `eval "$(aws configure export-credentials --format env)"` を実行します。

```bash
# 1. Trino を起動 (Docker)。認証情報がなくてもサーバーは起動しますが、クエリには必要です
docker compose up -d

# 2. Trino CLI で接続
docker exec -it trino trino --catalog fsxn --schema default

# 3. Glue に登録済みのテーブルに対してクエリを実行
trino> SELECT COUNT(*) FROM sensor_data;
trino> SELECT status, AVG(temperature) FROM sensor_data GROUP BY status;
```

`scripts/run_verification.sh <エイリアス>` は一連の流れを実行します。Glue にデータベース `sensor_data` とテーブル `readings` を作成し、`scripts/cleanup.sh` はそれらを削除しません。削除するコマンドはスクリプトの冒頭にあります。
