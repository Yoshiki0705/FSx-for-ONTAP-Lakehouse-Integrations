# Trino + AWS Glue Iceberg REST 検証計画

🌐 日本語 | [English](trino-glue-rest-validation.md)

## 目的

AWS Glue Iceberg REST エンドポイント経由で S3 Tables メタデータへの Trino アクセスを検証する。Trino は Iceberg REST catalog をネイティブにサポートし、AWS が統合ガイダンスを公開しているため、有力な検証対象。

## 背景

- Trino の [Iceberg connector](https://trino.io/docs/current/connector/iceberg.html) は REST、Glue、Hive Metastore、JDBC、Nessie、Snowflake catalog タイプをサポート
- AWS Glue Iceberg REST エンドポイントは準拠クライアント向けに [Iceberg REST API](https://docs.aws.amazon.com/glue/latest/dg/connect-glu-iceberg-rest.html) を提供
- Lake Formation ガバナンスは Glue REST credential vending パス経由で適用

## 検証結果 (2026-06-01)

### OSS Trino 481 (Docker, シングルノード)

| ステップ | 結果 | 備考 |
|---|---|---|
| Iceberg REST catalog で Trino 起動 | ✅ | `SERVER STARTED`、カタログ認識 |
| `SHOW SCHEMAS FROM s3tables_glue_rest` | ❌ | `Missing Authentication Token` |
| 根本原因 | — | Trino は REST catalog に `NoopAuthManager` を使用; SigV4 署名が HTTP リクエストに適用されない |

**結論**: OSS Trino 481 の Iceberg REST connector は、REST catalog リクエストに対する AWS SigV4 認証をネイティブにサポートしていません。Glue Iceberg REST endpoint は SigV4 を要求しますが（`/v1/config` で `rest.sigv4-enabled=true`）、Trino の REST クライアントは未認証リクエストを送信します。

### デプロイメント別の影響

| デプロイメント | 動作見込み | 理由 |
|---|---|---|
| **EMR Trino** | ✅ はい | EMR が AWS SDK SigV4 処理を Trino にパッチ |
| **Starburst Enterprise** | ✅ はい | AWS 統合と SigV4 サポートが組み込み |
| **OSS Trino (Docker/EC2)** | ❌ 現時点で不可 | REST catalog リクエストに SigV4 署名なし |
| **OSS Trino + カスタム AuthManager** | 可能性あり | カスタムプラグイン開発が必要 |

### Glue Iceberg REST API（独立検証済み）

基盤 API は適切な SigV4 認証で呼び出した場合に完全に機能（PyIceberg/botocore で検証）:

| API コール | 結果 | レイテンシ |
|---|---|---|
| List Namespaces | ✅ `[["metadata"]]` | 229ms |
| List Tables | ✅ `["unstructured_files"]` | 308ms |
| Load Table | ✅ 54 snapshots, 23 columns | 381ms |
| `/credentials` endpoint | ❌ `UnknownOperationException` | — |

## 設定

### 重要な発見: Glue REST の Credential Vending 非対応

**2026-06-01 検証済み**: AWS Glue Iceberg REST エンドポイントは Iceberg REST `/credentials` エンドポイントを実装していません（`UnknownOperationException` を返す）。`loadTable` の `X-Iceberg-Access-Delegation: vended-credentials` ヘッダーもストレージ credentials を返しません。

これは以下を意味します:
- **Trino**: メタデータとデータアクセスの両方に独自の IAM credentials (SigV4) を使用する必要あり。`vended-credentials-enabled=false` に設定。
- **Snowflake**: `VENDED_CREDENTIALS` モードはカタログが credentials を払い出すことを期待するが、Glue REST はそれができない。これが「Failed to retrieve credentials from the Catalog」エラーの根本原因。
- **Glue REST `/v1/config`** は `rest.sigv4-enabled=true` を返し、SigV4 が意図された認証メカニズムであることを確認。

### Trino カタログプロパティ (Glue Iceberg REST — 修正版)

```properties
# catalog/s3tables.properties
connector.name=iceberg
iceberg.catalog.type=rest
iceberg.rest-catalog.uri=https://glue.ap-northeast-1.amazonaws.com/iceberg
iceberg.rest-catalog.warehouse=catalogs/<ACCOUNT_ID>:s3tablescatalog/fsxn-metadata-catalog
iceberg.rest-catalog.vended-credentials-enabled=false
iceberg.rest-catalog.signing-region=ap-northeast-1
iceberg.rest-catalog.signing-name=glue
# Trino は S3 データアクセスに独自の AWS credentials を使用
fs.native-s3.enabled=true
s3.region=ap-northeast-1
```

> **注意**: `warehouse` パラメータには `catalogs/` プレフィックスを含める必要があります。これがないと API は HTTP 400「Prefix must follow the 'catalogs/{catalogId}' format」を返します。

## 検証ステップ

| # | ステップ | 期待結果 |
|---|------|----------------|
| 1 | Glue REST で Trino Iceberg catalog を設定 | カタログがエラーなしでロード |
| 2 | `SHOW SCHEMAS FROM s3tables` | `metadata` 名前空間をリスト |
| 3 | `SHOW TABLES FROM s3tables.metadata` | `unstructured_files` をリスト |
| 4 | `SELECT * FROM s3tables.metadata.unstructured_files LIMIT 10` | ファイルメタデータ行を返す |
| 5 | タイムトラベルクエリ | 動作する |
| 6 | 最新レコードビュークエリ (ROW_NUMBER window) | 重複排除が動作 |
| 7 | メタデータテーブルアクセス | アクセス可能 |
| 8 | Lake Formation 権限適用 | 未認可クエリがブロック |

## Trino による Iceberg REST アクセスの特徴（他エンジンとの比較）

| 観点 | Trino | Databricks | Snowflake |
|---|---|---|---|
| 直接 Iceberg REST アクセス | ✅ ネイティブ | ❌ UC がブロック | 🔄 Credential vending 問題 |
| 自動リフレッシュ | ✅ 常に最新 | ❌ REFRESH 必要 | TBD |
| REST 経由の書き込み | おそらく ✅ | ❌ 読み取り専用 (Foreign) | TBD |
| Lake Formation | Glue REST 経由 | TBD (Foreign Catalog) | TBD (vended credentials) |

## 参考資料

- [Trino Iceberg connector](https://trino.io/docs/current/connector/iceberg.html)
- [AWS Glue Iceberg REST エンドポイント](https://docs.aws.amazon.com/glue/latest/dg/connect-glu-iceberg-rest.html)
- [EMR Trino + Iceberg](https://docs.aws.amazon.com/emr/latest/ReleaseGuide/emr-iceberg-use-trino-cluster.html)
