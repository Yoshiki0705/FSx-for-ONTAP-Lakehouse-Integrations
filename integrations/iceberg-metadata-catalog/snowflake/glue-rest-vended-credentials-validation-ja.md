# Snowflake Glue REST + Vended Credentials 検証

🌐 日本語 | [English](glue-rest-vended-credentials-validation.md)

## 目的

S3 Tables アクセスのための vended credentials を使用した AWS Glue Iceberg REST エンドポイントとの Snowflake CATALOG INTEGRATION の検証を文書化する。

## 現在のステータス

| ステップ | 状態 | 備考 |
|---|---|---|
| CATALOG INTEGRATION 作成 | ✅ | `ICEBERG_REST` + `AWS_GLUE` + `VENDED_CREDENTIALS`（明示指定） |
| DESCRIBE CATALOG INTEGRATION | ✅ | 有効な IAM credentials を返す |
| CREATE ICEBERG TABLE | ✅ | 成功 (5.9s) — 2026-06-05 |
| SELECT * LIMIT 5 | ✅ | 5行返却 (1.6s) — 2026-06-05 |
| COUNT(*) | ✅ | 171行 (215ms) — AUTO_REFRESH 検証済み (PyIceberg append 170→171) |
| Time travel (AT/BEFORE TIMESTAMP) | ✅ | **検証済み**: AT(OFFSET => -1200) で 170 (追加前スナップショット) を取得 |
| AUTO_REFRESH | ✅ | **実動作確認済み**: PyIceberg append を 30秒以内に自動反映 (170→171) |
| Lake Formation カラムレベル権限 | ❌ | **VENDED_CREDENTIALS では非サポート** (2026-06-08)。AllowFullTableExternalDataAccess=false で全アクセスがブロックされる |
| サポートケース | ✅ | Snowflake support case (closed) — クローズ確認済み |

## ✅ ブレイクスルー: VENDED_CREDENTIALS 動作確認 (2026-06-05)

**Query ID**: `01c4e515-0003-ee3c-0003-6a86002d62b2`

### 検証エビデンス スクリーンショット

![COUNT(*) = 170行](screenshots/01-count-star-v2.png)

![DESCRIBE TABLE — 23カラム](screenshots/02-describe-table-v2.png)

![SHOW ICEBERG TABLES — UNMANAGED タイプ](screenshots/03-show-iceberg-tables-v2.png)

![SELECT * LIMIT 5](screenshots/04-select-star-limit5-v2.png)

### AUTO_REFRESH + Time Travel エビデンス (2026-06-08)

![AUTO_REFRESH 検証: PyIceberg append 後 COUNT(*) = 171](screenshots/05-auto-refresh-count-171-v2.png)
*AUTO_REFRESH: PyIceberg で 1レコード追加 → Snowflake の COUNT(*) が 30秒以内に 170→171 に自動反映*

![Time Travel: AT(OFFSET => -1200) で 170 を取得](screenshots/07-time-travel-offset-1200-v2.png)
*Time Travel: AT(OFFSET => -1200) で 170 を返す — append 操作前のスナップショット*

### 以前の失敗の根本原因

`ACCESS_DELEGATION_MODE` は明示指定しない場合 `EXTERNAL_VOLUME_CREDENTIALS` がデフォルト。このモードでは Snowflake が External Volume パスでストレージアクセスを検証し、S3 Tables 内部バケットに対して `ListObjectsV2` を発行 — `MethodNotAllowed` で失敗。

### 動作する設定

**重要要件:**
1. `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` を `REST_CONFIG` に**明示的に**指定
2. テーブルを**デフォルト EXTERNAL_VOLUME なし**のスキーマで作成
3. `CREATE TABLE` に `EXTERNAL_VOLUME` パラメータを**含めない**

```sql
-- 1. Catalog Integration（VENDED_CREDENTIALS 明示指定）
CREATE OR REPLACE CATALOG INTEGRATION s3tables_glue_rest_int
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = 'metadata'
  REST_CONFIG = (
    CATALOG_URI = 'https://glue.ap-northeast-1.amazonaws.com/iceberg'
    CATALOG_API_TYPE = AWS_GLUE
    CATALOG_NAME = '<ACCOUNT_ID>:s3tablescatalog/fsxn-metadata-catalog'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE = SIGV4
    SIGV4_IAM_ROLE = 'arn:aws:iam::<ACCOUNT_ID>:role/fsxn-snowflake-verification-role'
    SIGV4_SIGNING_REGION = 'ap-northeast-1'
  )
  ENABLED = TRUE;

-- 2. デフォルト EXTERNAL_VOLUME なしのスキーマ
CREATE SCHEMA FSXN_LAKEHOUSE.S3TABLES_VENDED;
USE SCHEMA FSXN_LAKEHOUSE.S3TABLES_VENDED;

-- 3. EXTERNAL_VOLUME パラメータなしのテーブル
CREATE ICEBERG TABLE s3tables_vended_creds_test
  CATALOG = 's3tables_glue_rest_int'
  CATALOG_TABLE_NAME = 'unstructured_files';

-- 4. クエリ — 成功
SELECT * FROM s3tables_vended_creds_test LIMIT 5;
-- 返却: FILE_ID, FILE_PATH, FILE_NAME, FILE_TYPE, FILE_SIZE, CREATED_AT, MODIFIED_AT
```

### AWS 側の前提条件

```bash
# S3 Tables リソースを Lake Formation に登録（--with-federation は必須）
aws lakeformation register-resource \
  --resource-arn "arn:aws:s3tables:ap-northeast-1:<ACCOUNT_ID>:bucket/fsxn-metadata-catalog" \
  --role-arn "arn:aws:iam::<ACCOUNT_ID>:role/S3TablesRoleForLakeFormation" \
  --with-federation

# IAM ロールポリシーに必要:
# - glue:GetTable, glue:GetDatabase, glue:GetCatalog
# - lakeformation:GetDataAccess
# - s3tables:GetTableBucket, s3tables:GetTable, s3tables:GetNamespace
# - s3tables:GetTableData, s3tables:GetTableMetadataLocation

# IAM trust policy に Snowflake の External ID を含める
# （DESCRIBE CATALOG INTEGRATION の出力から取得）
```

### VENDED_CREDENTIALS の動作メカニズム（確認済み）

VENDED_CREDENTIALS モードでは:
1. Snowflake が適切な delegation ヘッダー付きで Glue REST `loadTable` を呼び出す
2. Lake Formation（`GetTemporaryGlueTableCredentials` 経由）が一時ストレージ credentials を返す
3. これらの credentials が `loadTable` レスポンスの config マップに含まれる
4. Snowflake がこれらの credentials でデータファイルに直接アクセス
5. **ListObjectsV2 は不要** — Snowflake は Iceberg メタデータからの正確なパスでファイルを読み取る

## 過去の設定（修正前）

> **注意**: 以下の設定は初期テストで**失敗**したものです。
> 動作する設定は上記「✅ ブレイクスルー」セクションを参照してください。

### 元の Catalog Integration（失敗 — ACCESS_DELEGATION_MODE の明示指定なし）

```sql
CREATE OR REPLACE CATALOG INTEGRATION s3tables_glue_rest_int
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = 'metadata'
  REST_CONFIG = (
    CATALOG_URI = 'https://glue.ap-northeast-1.amazonaws.com/iceberg'
    WAREHOUSE = '<ACCOUNT_ID>:s3tablescatalog/fsxn-metadata-catalog'
    CATALOG_API_TYPE = AWS_GLUE
  )
  REST_AUTHENTICATION = (
    TYPE = VENDED_CREDENTIALS
    CATALOG_IAM_ROLE_ARN = 'arn:aws:iam::<ACCOUNT_ID>:role/fsxn-snowflake-verification-role'
  )
  ENABLED = TRUE;
```

## 検証チェックリスト

| 確認項目 | 状態 | エビデンス |
|---|---|---|
| IAM trust policy に Snowflake user ARN を含む | ✅ | Trust policy 更新済み |
| IAM ロールに Glue 権限あり | ✅ | ポリシーアタッチ済み |
| IAM ロールに S3 Tables 権限あり | ✅ | s3tables:* 付与 |
| IAM ロールに Lake Formation 権限あり | ✅ | lakeformation:GetDataAccess |
| Lake Formation リソース登録 (--with-federation) | ✅ | credential vending に必須 |
| Lake Formation AllowFullTableExternalDataAccess = true | ✅ | テスト用に設定 |
| Glue REST エンドポイントが Snowflake に応答 | ✅ | DESCRIBE が credentials を返す |
| ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS 明示指定 | ✅ | 重要な修正点 |
| スキーマにデフォルト EXTERNAL_VOLUME なし | ✅ | S3TABLES_VENDED スキーマ |
| CREATE TABLE に EXTERNAL_VOLUME パラメータなし | ✅ | 動作確認 |
| Credential vending がストレージ credentials を返す | ✅ | **2026-06-05 動作確認** |
| CREATE ICEBERG TABLE | ✅ | 成功 (5.9s) |
| SELECT * クエリ | ✅ | 5行返却 (1.6s) |
| SYSTEM$VERIFY_CATALOG_INTEGRATION | ✅ | "Statement executed successfully" |
| COUNT(*) | ✅ | 171行 (215ms) — AUTO_REFRESH 実動作確認 (170→171) |
| Time travel (AT/BEFORE TIMESTAMP) | ✅ | **検証済み**: AT(OFFSET => -1200) で 170 (過去スナップショット) を取得 |
| AUTO_REFRESH | ✅ | **実動作確認済み**: 30秒以内に新スナップショット検出 |
| Lake Formation カラムレベル権限 | ❌ | **VENDED_CREDENTIALS では非サポート** (2026-06-08) |

## 仮説の履歴（解決済み）

### 元の仮説（確認後に解決）

**初期発見 (2026-06-01)**: AWS Glue Iceberg REST エンドポイントは Iceberg REST `/credentials` エンドポイントを実装していない。`POST /v1/.../credentials` は `UnknownOperationException` を返す。

**解決 (2026-06-05)**: この発見自体は正しいが、ブロッカーではなかった。Lake Formation の credential vending は独自メカニズム（`GetTemporaryGlueTableCredentials`）で動作し、`ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` が明示的に設定されている場合にトリガーされる。Credentials は `loadTable` レスポンスの config マップに含まれ、別の `/credentials` エンドポイント経由ではない。

**核心的な知見**: 以前の失敗は credential vending 機能の欠如ではなく、`ACCESS_DELEGATION_MODE` が `EXTERNAL_VOLUME_CREDENTIALS` にデフォルト設定されていたことが原因。`VENDED_CREDENTIALS` を明示的に設定すると、Glue REST + Lake Formation スタックは Snowflake に正しく一時 credentials を返す。

**Snowflake が期待する credential 形式（サポートにより 2026-06-02 確認）**:
`ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` の場合、Snowflake は loadTable レスポンスの config に以下を期待:
- `s3.access-key-id`（必須）
- `s3.secret-access-key`（必須）
- `s3.session-token`（必須）
- `s3.session-token-expires-at-ms`（オプション）

Error 004174 はこれらのフィールドがレスポンスに存在しない場合に発生。

これが Snowflake の「Failed to retrieve credentials from the Catalog」エラーの根本原因です:
- Snowflake の `VENDED_CREDENTIALS` モードは REST catalog が短期ストレージ credentials を返すことを期待
- Glue REST は代わりに SigV4 認証を使用 — 呼び出し元が S3 データアクセス用の独自 IAM credentials を持つ必要がある
- これは Snowflake の vended credentials モデルと Glue REST の SigV4 モデル間の根本的な非互換性

**影響**:
1. Snowflake は Glue REST で S3 Tables に対して `VENDED_CREDENTIALS` を使用できない（確認された制限）
2. Trino/Spark は独自の IAM credentials (SigV4) を使用するため Glue REST にアクセス可能
3. Snowflake は vended credentials の代わりに External Volume（独自のストレージ credentials）を使用する必要がある可能性
4. 相互運用性のギャップとして Snowflake と AWS の双方に起票すべき

**期待される credential フィールド（Apache Iceberg REST の仕様）**:
`ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` の場合、Snowflake は Iceberg REST `loadTable` レスポンスの config マップに標準 Apache Iceberg credential フィールドが含まれることを期待します:
- `s3.access-key-id`（必須）
- `s3.secret-access-key`（必須）
- `s3.session-token`（必須）
- `s3.session-token-expires-at-ms`（任意）

Error 004174 はこれらのフィールドが欠落している場合に発生します。

**エラー進行（自アカウントで観測、2026-06-02）**:
アカウントから確認できるエラー進行:
1. 004139（Lake Formation 権限エラー）→ メタデータアクセスブロック
2. 004174（credential 取得失敗）→ メタデータ解決成功、ストレージ credentials なし

これにより証明: Glue REST 到達可能、カタログとテーブル解決成功、メタデータ認証を超えて進行、しかし利用可能な credential ペイロードを取得できない。

## 代替パス

### 1. Object Store Catalog Integration（読み取り専用、credential vending 不要）

Snowflake は External Volume を使用して Iceberg メタデータファイルから直接テーブルを読み取ることができます。REST catalog の credential vending を完全にバイパスします。

```sql
-- Object Store catalog integration を作成
CREATE OR REPLACE CATALOG INTEGRATION iceberg_object_store_int
  CATALOG_SOURCE = OBJECT_STORE
  TABLE_FORMAT = ICEBERG
  ENABLED = TRUE;

-- メタデータファイルを直接指す Iceberg テーブルを作成
CREATE ICEBERG TABLE FSXN_LAKEHOUSE.PUBLIC.s3tables_metadata
  EXTERNAL_VOLUME = 's3tables_metadata_vol'
  CATALOG = 'iceberg_object_store_int'
  METADATA_FILE_PATH = 'metadata/00001-fcb8fb99-20cb-4b72-84bb-012d2c85891c.metadata.json';
```

**制限事項**:
- 読み取り専用アクセス
- メタデータファイルの場所が変わるたびに手動リフレッシュが必要
- 現在のメタデータファイルパスを知る必要あり（コミットごとに変更）

**S3 Tables に対する課題**: S3 Tables 内部バケットのパス形式が Snowflake の External Volume で正しく解決できるか追加調査が必要。

### 2. 解決ステータス（2026-06-08 更新）

| アクション | 担当 | 状態 |
|---|---|---|
| loadTable レスポンス証拠を Snowflake に提供 | 顧客（我々） | ✅ 完了 (2026-06-02) |
| SYSTEM$VERIFY_CATALOG_INTEGRATION 実行 | 顧客（我々） | ✅ 完了 — "Statement executed successfully" |
| VENDED_CREDENTIALS 明示指定 + External Volume なしでテスト | 顧客（我々） | ✅ 完了 — **成功** (2026-06-05) |
| Snowflake サポートに成功報告 | 顧客（我々） | ✅ 完了 (2026-06-08) |
| AUTO_REFRESH、time travel、カラムレベル権限の検証 | 顧客（我々） | 🔄 フォローアップで質問済み |
| フォローアップ質問への回答 | Snowflake | 🔄 待ち |
| ドキュメント改善（S3 Tables + VENDED_CREDENTIALS の KB 記事） | Snowflake | 🔄 リクエスト済み (2026-06-08) |

## 参考資料

- [Snowflake: Iceberg 用 Vended credentials](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-vended-credentials)
- [Snowflake: REST catalog integration](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest)
- [Snowflake: Credentials vending の仕組み](https://www.snowflake.com/en/engineering-blog/iceberg-catalog-credentials/)
- [AWS: S3 Tables + Glue REST エンドポイント](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-tables-integrating-glue-endpoint.html)
