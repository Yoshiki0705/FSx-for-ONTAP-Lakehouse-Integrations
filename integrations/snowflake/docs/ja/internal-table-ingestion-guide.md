🌐 [English](../en/internal-table-ingestion-guide.md) | **日本語**

# 内部テーブル取り込みガイド — COPY INTO が必要なケース

> **ステータス**: アーキテクチャリファレンス — 検証結果に基づく（2026年5月）
>
> **コンテキスト**: FSx for ONTAP S3 Access Points は Snowflake External Table でのゼロコピー読み取りアクセスに対応しています。しかし、多くの Snowflake 機能は**内部（マネージド）テーブル**にデータが存在することを要求します。このガイドでは、どの機能が COPY INTO を必要とし、推奨される取り込みパターンを文書化しています。

## エグゼクティブサマリー

FSx for ONTAP S3 AP 上の Snowflake External Table は**ガバナンス付きゼロコピー読み取りアクセス**を提供しますが、設計上読み取り専用です。多くの高度な Snowflake 機能（Cortex Search、Dynamic Tables、Time Travel、DML、クラスタリング）はデータが内部テーブルに存在することを要求します。

これにより**二重管理の課題**が生じます：データは FSx for ONTAP（Source of Truth）に存在し、プラットフォームの全機能を利用するには Snowflake 内部テーブルにコピーする必要があります。

### AI-Ready データプロダクトへのジャーニー

Raw NAS ファイルから Snowflake での AI-ready データプロダクトへの進化は明確なパスに従います:

```
FSx for ONTAP (Raw ファイル)
  ↓ S3 Access Point + AWS_ACCESS_POINT_ARN
External Table (ゼロコピーのガバナンス付き読み取り)
  ↓ Cortex AI テキスト関数はここで動作（summarize, translate, sentiment）
  ↓
Dynamic Table (TARGET_LAG = '1 hour')
  ↓ 自動変換 + エンリッチメント
  ↓ SELECT 句で Cortex AI（2025年9月 GA）
  ↓
Cortex Search Service (セマンティック検索 / RAG)
  ↓ AI-ready データプロダクト
  ↓
Data Sharing / Data Product (ガバナンス付き配布)
```

**重要な知見**: すべてを COPY INTO する必要はありません。まず External Table で即座に AI 価値を得て（Cortex テキスト関数はゼロコピーデータで動作）、次に高価値なサブセットを選択的に Dynamic Table に昇格させ、Cortex Search とプラットフォーム全機能を活用します。

### 基本原則

1. **External Table = ゼロコピーのガバナンス付き読み取り** — データ移動なし、ただし機能制限あり
2. **Internal Table = Snowflake の全機能** — COPY INTO が必要（データ重複）
3. **Dynamic Table = 推奨されるブリッジ** — 宣言的、自動管理、Cortex AI ネイティブ
4. **目標は「すべてをロード」ではない** — 「最も価値のあるサブセットから AI-ready データプロダクトを作る」こと
5. **同期が課題** — FSx for ONTAP S3 AP は S3 Event Notifications をサポートしないため、変更検知にはポーリングまたは FPolicy が必要

---

## 機能利用可否: External Table vs Internal Table

### Cortex AI 関数

| 関数 | External Table | Internal Table | COPY INTO 必要 | 参照 |
|------|:---:|:---:|:---:|---|
| [CORTEX.SUMMARIZE](https://docs.snowflake.com/en/sql-reference/functions/summarize-snowflake-cortex) | ✅ | ✅ | 不要 | 任意のテキストカラムで動作 |
| [CORTEX.TRANSLATE](https://docs.snowflake.com/en/sql-reference/functions/translate-snowflake-cortex) | ✅ | ✅ | 不要 | 任意のテキストカラムで動作 |
| [CORTEX.SENTIMENT](https://docs.snowflake.com/en/sql-reference/functions/sentiment-snowflake-cortex) | ✅ | ✅ | 不要 | 任意のテキストカラムで動作 |
| [CORTEX.EXTRACT_ANSWER](https://docs.snowflake.com/en/sql-reference/functions/extract_answer-snowflake-cortex) | ✅ | ✅ | 不要 | 任意のテキストカラムで動作 |
| [CORTEX.COMPLETE](https://docs.snowflake.com/en/sql-reference/functions/complete-snowflake-cortex) (テキスト) | ✅ | ✅ | 不要 | 任意のテキストカラムで動作 |
| [CORTEX.COMPLETE](https://docs.snowflake.com/en/sql-reference/functions/complete-snowflake-cortex-multimodal) (マルチモーダル/Vision) | ❌ | ✅ | **必要** | 内部/マネージドステージの TO_FILE が必要 |
| [PARSE_DOCUMENT](https://docs.snowflake.com/en/sql-reference/functions/parse_document) | ✅ | ✅ | 不要 | 外部ステージの BUILD_SCOPED_FILE_URL で動作 |
| [Cortex Search Service](https://docs.snowflake.com/en/sql-reference/sql/create-cortex-search) | ❌ | ✅ | **必要** | ソースクエリは内部テーブルまたは内部テーブル上のビューを参照する必要あり |

### データ管理機能

| 機能 | External Table | Internal Table | COPY INTO 必要 | 参照 |
|------|:---:|:---:|:---:|---|
| SELECT / クエリ | ✅ | ✅ | 不要 | |
| DML (INSERT/UPDATE/DELETE/MERGE) | ❌ | ✅ | **必要** | External Table は読み取り専用 |
| [Time Travel](https://docs.snowflake.com/en/user-guide/data-time-travel) | ❌ | ✅ | **必要** | DATA_RETENTION_TIME_IN_DAYS 付き内部テーブルが必要 |
| [Fail-safe](https://docs.snowflake.com/en/user-guide/data-failsafe) | ❌ | ✅ | **必要** | Time Travel 期限後の7日間リカバリ |
| [クラスタリング](https://docs.snowflake.com/en/user-guide/tables-clustering-micropartitions) | ❌ | ✅ | **必要** | マイクロパーティションは内部テーブルのみ |
| [Search Optimization](https://docs.snowflake.com/en/user-guide/search-optimization-service) | ❌ | ✅ | **必要** | 内部テーブルが必要 |
| [Dynamic Tables](https://docs.snowflake.com/en/user-guide/dynamic-tables-intro) | ⚠️ ソースのみ | ✅ | 部分的 | External Table をソースとして読み取り可能、出力は内部 |
| [Streams](https://docs.snowflake.com/en/user-guide/streams-intro) (CDC) | ❌ | ✅ | **必要** | External Table では非サポート |
| [Tasks](https://docs.snowflake.com/en/user-guide/tasks-intro) | ✅ | ✅ | 不要 | COPY INTO や REFRESH のスケジュールに使用可能 |
| [Materialized Views](https://docs.snowflake.com/en/user-guide/views-materialized) | ✅ | ✅ | 不要 | External Table 上に作成可能（パフォーマンス向上） |

### ガバナンス機能

| 機能 | External Table | Internal Table | COPY INTO 必要 | 参照 |
|------|:---:|:---:|:---:|---|
| [オブジェクトタグ](https://docs.snowflake.com/en/user-guide/object-tagging) | ✅ | ✅ | 不要 | 両方で動作 |
| [Row Access Policy](https://docs.snowflake.com/en/user-guide/security-row-intro) | ✅ | ✅ | 不要 | 両方で動作 |
| [カラムマスキング](https://docs.snowflake.com/en/user-guide/security-column-intro) | ✅ | ✅ | 不要 | 両方で動作 |
| [データ共有](https://docs.snowflake.com/en/user-guide/data-sharing-intro) | ✅ | ✅ | 不要 | External Table も共有可能 |
| [アクセス履歴](https://docs.snowflake.com/en/user-guide/access-history) | ✅ | ✅ | 不要 | 両方で追跡 |

### ファイル & 非構造化データ機能

| 機能 | External Stage (FSx for ONTAP S3 AP) | Internal Stage | COPY INTO 必要 | 参照 |
|------|:---:|:---:|:---:|---|
| [LIST @stage](https://docs.snowflake.com/en/sql-reference/sql/list) | ✅ | ✅ | 不要 | |
| [GET_PRESIGNED_URL](https://docs.snowflake.com/en/sql-reference/functions/get_presigned_url) | ✅ | ✅ | 不要 | AWS ドキュメントでは「非サポート」と記載されているが動作 |
| [BUILD_SCOPED_FILE_URL](https://docs.snowflake.com/en/sql-reference/functions/build_scoped_file_url) | ✅ | ✅ | 不要 | |
| [Directory Table](https://docs.snowflake.com/en/user-guide/data-load-dirtables) | ✅ | ✅ | 不要 | ENABLE + REFRESH が外部ステージで動作 |
| AUTO_REFRESH (Directory Table) | ❌ | ✅ | N/A | S3 Event Notifications が必要（FSx for ONTAP S3 AP 非サポート） |
| [Snowpipe](https://docs.snowflake.com/en/user-guide/data-load-snowpipe-intro) (auto-ingest) | ❌ | N/A | N/A | S3 Event Notifications が必要 |
| [TO_FILE](https://docs.snowflake.com/en/sql-reference/functions/to_file) (マルチモーダル AI 用) | ❌ | ✅ | **必要** | 内部/マネージドステージパスのみで動作 |

---

## 二重管理問題

```
FSx for ONTAP (NFS/SMB)          Snowflake 内部テーブル
   ┌─────────────────┐              ┌─────────────────┐
   │ Source of Truth │──COPY INTO──▶│ 分析用コピー      │
   │ (マルチプロトコル) │              │ (全機能利用可.)   │
   └─────────────────┘              └─────────────────┘
         │                                   │
    NFS/SMB で更新                      同期が必要
         │                                   │
     ▼ 課題 ▼                             ▼ 課題 ▼
  - S3 Event Notifications なし       - データ鮮度リスク
  - 変更検知はポーリング              - ストレージコスト
  - 削除が自動伝播されない            - コンピュートコスト
                                      - スキーマドリフト管理
```

### 具体的な課題

| 課題 | 説明 | 軽減策 |
|------|------|--------|
| **変更検知** | FSx for ONTAP S3 AP は S3 Event Notifications 非サポート → Snowpipe トリガー不可 | FPolicy → Lambda → SNS → Snowpipe REST API、またはスケジュール Task + COPY INTO |
| **削除の伝播** | COPY INTO は追記型; FSx for ONTAP 上で削除されたファイルは内部テーブルから削除されない | 定期的な全量リフレッシュ、またはメタデータ比較による MERGE |
| **スキーマ進化** | ソースファイルの新カラムが自動反映されない | INFER_SCHEMA + ALTER TABLE、またはテーブル再作成 |
| **データ鮮度** | ポーリング間隔がラグを決定 | FPolicy で準リアルタイム、Task でスケジュール |
| **コスト** | Snowflake ストレージ + COPY INTO 実行のコンピュート | 非重要データには transient テーブル使用; ソースファイル圧縮 |

---

## 推奨取り込みパターン

### パターン 1: スケジュール COPY INTO（最もシンプル）

最適用途: バッチ分析、日次/時間単位のリフレッシュが許容される場合。

```sql
-- ターゲット内部テーブル作成
CREATE OR REPLACE TABLE sensor_data (
  device_id STRING,
  timestamp TIMESTAMP,
  temperature FLOAT,
  humidity FLOAT
) DATA_RETENTION_TIME_IN_DAYS = 7;

-- スケジュール Task: 1時間ごとに COPY INTO
CREATE OR REPLACE TASK copy_sensor_data
  WAREHOUSE = COMPUTE_WH
  SCHEDULE = '60 MINUTE'
AS
  COPY INTO sensor_data
  FROM @fsxn_stage/bronze/sensor/
  FILE_FORMAT = (TYPE = PARQUET)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = CONTINUE;
```

参照: [COPY INTO](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table), [Tasks](https://docs.snowflake.com/en/user-guide/tasks-intro)

### パターン 2: FPolicy → Lambda → Snowpipe REST API（準リアルタイム）

最適用途: イベント駆動取り込み、分単位のレイテンシ。

```
FSx for ONTAP (ファイル作成/変更)
  ↓ FPolicy 通知
AWS Lambda (イベントプロセッサ)
  ↓ Snowpipe REST API 呼び出し (insertFiles)
Snowflake Snowpipe (COPY INTO 内部テーブル)
  ↓
内部テーブル (Cortex Search, DML 等で利用可能)
```

```sql
-- Snowpipe 作成（REST API 経由でトリガー、auto-ingest ではない）
CREATE OR REPLACE PIPE fsxn_sensor_pipe
AS
  COPY INTO sensor_data
  FROM @fsxn_stage/bronze/sensor/
  FILE_FORMAT = (TYPE = PARQUET)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
```

参照: [Snowpipe REST API](https://docs.snowflake.com/en/user-guide/data-load-snowpipe-rest-apis), [FPolicy](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html)

### パターン 3: Dynamic Table（自動変換） — 推奨

最適用途: External Table ソースからの継続的変換パイプライン。**最も Snowflake ネイティブなアプローチ** — 宣言的、自動管理、SELECT 句で Cortex AI 関数をサポート（2025年9月 GA）。

> **サポート確認済み（2026年5月、Snowflake support case）**: External Table ソースの Dynamic Table は `REFRESH_MODE = FULL` でサポート。最小 `TARGET_LAG` は 60 秒。External Table は change tracking 非対応のため増分リフレッシュは利用不可。

```sql
-- Dynamic Table: External Table から読み取り、内部として実体化
CREATE OR REPLACE DYNAMIC TABLE sensor_enriched
  TARGET_LAG = '1 hour'
  WAREHOUSE = COMPUTE_WH
AS
  SELECT
    device_id,
    timestamp,
    temperature,
    humidity,
    SNOWFLAKE.CORTEX.SENTIMENT(notes) AS sentiment_score,
    CURRENT_TIMESTAMP() AS enriched_at
  FROM sensor_external_table
  WHERE timestamp > DATEADD(day, -30, CURRENT_TIMESTAMP());
```

参照: [Dynamic Tables](https://docs.snowflake.com/en/user-guide/dynamic-tables-intro)

> **注意**: Dynamic Table は External Table をソースとして使用可能（全量リフレッシュモード）。増分リフレッシュには変更追跡が必要で、External Table では利用不可。

> **重要**: FSx for ONTAP S3 AP は AUTO_REFRESH をサポートしないため、Dynamic Table が新ファイルを認識する前に External Table メタデータを手動リフレッシュする必要があります。Task で自動化してください:
> ```sql
> -- External Table メタデータを5分ごとにリフレッシュする Task
> CREATE OR REPLACE TASK refresh_fsxn_external_table
>   WAREHOUSE = COMPUTE_WH
>   SCHEDULE = '5 MINUTE'
> AS
>   ALTER EXTERNAL TABLE sensor_external_table REFRESH;
> ```
> Dynamic Table は次のリフレッシュサイクル（TARGET_LAG に基づく）で新データを取得します。

> **TARGET_LAG のサイジング（本リポジトリの実行結果にもとづく）**:
> - **60 秒**（最小）: 小規模データまたはクリティカルアラート向けのみ。毎回 External Table 全体を再読み込み。
> - **5 分**: 準リアルタイム監視。中規模データ（GB レベル）で許容可能なコスト。
> - **1 時間**（推奨開始点）: バッチ分析、日次レポート。大規模データでコスト効率的。
> - **1 日**: Cortex Search Service ソース、週次レポート。最低コスト。

> **Dynamic Table が COPY INTO + Task より推奨される理由**:
> - **宣言的**: TARGET_LAG（例: '1 hour'）を定義すれば Snowflake がリフレッシュスケジュールを自動管理
> - **Cortex AI 統合**: Dynamic Table の SELECT 句で CORTEX.SUMMARIZE、CORTEX.SENTIMENT 等を直接使用可能（[2025年9月 GA](https://docs.snowflake.com/en/release-notes/2025/other/2025-09-11-dynamic-tables-cortex-aisql-support)）
> - **運用オーバーヘッドなし**: Task スケジューリング、COPY INTO 重複排除ロジック、手動エラーハンドリングが不要
> - **チェーニング**: Dynamic Table は他の Dynamic Table を参照可能（Bronze → Silver → Gold のマルチステージパイプライン）

### パターン 4: COPY INTO + Cortex Search（RAG パイプライン）

最適用途: FSx for ONTAP ドキュメントに対するセマンティック検索。

```sql
-- ステップ 1: 外部ステージから内部テーブルに COPY INTO
CREATE OR REPLACE TABLE documents (
  file_path STRING,
  content STRING,
  file_type STRING,
  ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

COPY INTO documents (file_path, content, file_type)
FROM (
  SELECT
    METADATA$FILENAME,
    $1::STRING,
    SPLIT_PART(METADATA$FILENAME, '.', -1)
  FROM @fsxn_stage/bronze/documents/
)
FILE_FORMAT = (TYPE = CSV FIELD_DELIMITER = NONE RECORD_DELIMITER = NONE)
ON_ERROR = CONTINUE;

-- ステップ 2: 内部テーブル上に Cortex Search Service 作成
CREATE OR REPLACE CORTEX SEARCH SERVICE document_search
  ON content
  ATTRIBUTES file_type
  WAREHOUSE = COMPUTE_WH
  TARGET_LAG = '1 day'
AS (
  SELECT content, file_path, file_type
  FROM documents
);
```

参照: [CREATE CORTEX SEARCH SERVICE](https://docs.snowflake.com/en/sql-reference/sql/create-cortex-search), [COPY INTO](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table)

### パターン 5: マルチモーダル AI (Vision) — 内部ステージ使用

最適用途: LLM Vision モデルによる画像/ドキュメント分析。

```sql
-- ステップ 1: ファイルを内部ステージにコピー（TO_FILE に必要）
COPY FILES
  INTO @internal_media_stage
  FROM @fsxn_stage/media/images/;

-- ステップ 2: TO_FILE で COMPLETE (マルチモーダル) を使用
SELECT
  RELATIVE_PATH AS file_name,
  SNOWFLAKE.CORTEX.COMPLETE(
    'claude-3-5-sonnet',
    'Describe this image in detail',
    TO_FILE(@internal_media_stage, RELATIVE_PATH)
  ) AS description
FROM DIRECTORY(@internal_media_stage)
WHERE RELATIVE_PATH LIKE '%.png' OR RELATIVE_PATH LIKE '%.jpg';
```

参照: [COMPLETE (マルチモーダル)](https://docs.snowflake.com/en/sql-reference/functions/complete-snowflake-cortex-multimodal), [TO_FILE](https://docs.snowflake.com/en/sql-reference/functions/to_file)

---

## COPY INTO なしで動作するもの（External Table 上のゼロコピー）

以下の操作は FSx for ONTAP S3 AP External Table 上で直接動作します — データ移動不要:

| 操作 | 例 | パフォーマンス |
|------|---|---|
| アドホック SQL クエリ | `SELECT * FROM ext_table WHERE date > '2026-01-01'` | 中程度（マイクロパーティションなし） |
| テキスト AI 関数 | `SELECT CORTEX.SUMMARIZE(text_col) FROM ext_table` | 良好 |
| ガバナンスタグ | `ALTER TABLE ext_table SET TAG sensitivity = 'internal'` | 即時 |
| Row Access Policy | `ALTER TABLE ext_table ADD ROW ACCESS POLICY ...` | 即時 |
| カラムマスキング | `ALTER TABLE ext_table MODIFY COLUMN ssn SET MASKING POLICY ...` | 即時 |
| Materialized View | `CREATE MATERIALIZED VIEW mv AS SELECT ... FROM ext_table` | クエリ性能向上 |
| データ共有 | `GRANT SELECT ON ext_table TO SHARE ...` | 即時 |
| Presigned URL | `SELECT GET_PRESIGNED_URL(@stage, path) FROM dir_table` | 高速 |
| ドキュメントパース | `SELECT PARSE_DOCUMENT(BUILD_SCOPED_FILE_URL(@stage, path))` | 約8秒/ドキュメント |

---

## 判断フレームワーク

**クイック判断テーブル** — あなたの要件を見つけて推奨に従ってください:

| あなたの要件 | 答え | データ移動 |
|---|---|---|
| 「SQL クエリだけできればいい」 | → External Table（ゼロコピー） | なし |
| 「テキスト AI（要約、翻訳、感情分析）が必要」 | → External Table（ゼロコピー） | なし |
| 「ガバナンスタグとマスキングが必要」 | → External Table（ゼロコピー） | なし |
| 「Cortex Search / RAG が必要」 | → Dynamic Table or COPY INTO | 全量コピー |
| 「Vision AI（画像分析）が必要」 | → COPY FILES → 内部ステージ | ファイルコピー |
| 「DML (INSERT/UPDATE/DELETE) が必要」 | → COPY INTO 内部テーブル | 全量コピー |
| 「Time Travel が必要」 | → COPY INTO 内部テーブル | 全量コピー |
| 「高性能クエリ（クラスタリング）が必要」 | → COPY INTO 内部テーブル | 全量コピー |

**詳細フローチャート:**

```
                    ┌─────────────────────────┐
                    │ 何が必要ですか？         │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
    ┌─────────▼─────────┐ ┌─────▼─────┐ ┌─────────▼─────────┐
    │ 読み取り専用 SQL + │ │ RAG /     │ │ DML / Time Travel │
    │ 基本 AI + ガバナンス│ │ Cortex    │ │ / クラスタリング / │
    │                   │ │ Search    │ │ マルチモーダル AI  │
    └─────────┬─────────┘ └─────┬─────┘ └─────────┬─────────┘
              │                  │                  │
    ┌─────────▼─────────┐ ┌─────▼─────┐ ┌─────────▼─────────┐
    │ External Table    │ │ COPY INTO │ │ COPY INTO         │
    │ (ゼロコピー)      │ │ + Cortex  │ │ 内部テーブル      │
    │                   │ │ Search    │ │                   │
    └───────────────────┘ └───────────┘ └───────────────────┘
```

| 要件 | 推奨パス | データ移動 |
|------|----------|-----------|
| アドホック分析、レポーティング | External Table | なし（ゼロコピー） |
| タグ/マスキング付きガバナンス読み取り | External Table | なし |
| テキスト要約、翻訳、感情分析 | External Table | なし |
| ドキュメントパース (OCR) | External Stage + PARSE_DOCUMENT | なし |
| セマンティック検索 (RAG) | COPY INTO → Cortex Search Service | 全量コピー |
| 画像/動画分析 (マルチモーダル) | COPY FILES → 内部ステージ → COMPLETE | 全量コピー |
| DML (INSERT/UPDATE/DELETE/MERGE) | COPY INTO 内部テーブル | 全量コピー |
| Time Travel / ポイントインタイムリカバリ | COPY INTO 内部テーブル | 全量コピー |
| 高性能クエリ (クラスタリング) | COPY INTO 内部テーブル | 全量コピー |
| CDC / Streams | COPY INTO 内部テーブル | 全量コピー |

---

## 業界ユースケース例

| 業界 | FSx for ONTAP 上のデータ | ゼロコピーパス（External Table） | AI-ready パス（Dynamic Table → Cortex） |
|------|---|---|---|
| **製造業** | センサーログ、検査画像、品質レポート | アドホック品質クエリ、機密データへのガバナンスタグ | Cortex Search で「類似欠陥を検索」、オペレーターノートの感情分析 |
| **金融サービス** | 契約書 PDF、取引ログ、規制提出書類 | コンプライアンスクエリ、部門別 Row Access Policy | Cortex Search で契約条項検索、監査準備の SUMMARIZE |
| **ヘルスケア** | 匿名化研究データ、画像メタデータ | PII カラムマスキング付き研究クエリ | 臨床ノートの PARSE_DOCUMENT、文献レビューの Cortex Search |
| **小売** | POS データ、顧客フィードバック、商品カタログ | 売上分析、リージョン別ガバナンスタグ | 顧客レビューの SENTIMENT、グローバル市場向け TRANSLATE |

> **パートナー向けポジショニング**: 「まず External Table で即座にガバナンス付き分析を開始（コストゼロ、データ移動ゼロ）。顧客が価値を実感したら、高価値サブセットを Dynamic Table に昇格させて Cortex AI を活用。これはマイグレーションではなく、段階的な AI-ready データプロダクト化です。」

## コスト考慮事項

| コンポーネント | External Table パス | COPY INTO パス |
|------------|---|---|
| FSx for ONTAP ストレージ | ✅（Source of Truth） | ✅（Source of Truth） |
| Snowflake ストレージ | なし | 追加（内部テーブル） |
| Snowflake コンピュート（クエリ） | クエリごと | クエリごと |
| Snowflake コンピュート（COPY INTO） | なし | 定期的な取り込みコスト |
| データ鮮度 | リアルタイム（直接読み取り） | ポーリング間隔のラグ |
| 運用複雑度 | 低 | 中（同期ロジック必要） |

**コスト最適化のヒント:**
- 非重要データには [transient テーブル](https://docs.snowflake.com/en/user-guide/tables-temp-transient) を使用（Fail-safe コストなし）
- 適切な `DATA_RETENTION_TIME_IN_DAYS` を設定（1日 vs 90日）
- COPY INTO で `MATCH_BY_COLUMN_NAME` を使用してスキーマ進化に対応
- ソースファイルを圧縮（CSV より Parquet 推奨）
- ソースファイルをクリーンアップ可能な場合は COPY INTO で `PURGE = TRUE` を使用

---

## 次のステップ

1. **最初の External Table を作成**: [設定ガイド](../../README.md#internal-table-vs-external-table--design-guide)に従い、ステージに `AWS_ACCESS_POINT_ARN` を設定して External Table を作成
2. **RAG / Cortex Search 向け**: External Table ソースに `TARGET_LAG = '1 hour'` の Dynamic Table を設定し、Cortex Search Service を作成
3. **イベント駆動取り込み向け**: FPolicy → Lambda → Snowpipe REST API をデプロイ（[Snowpipe 統合ガイド](snowpipe-integration.md)）
4. **マルチプラットフォーム共有 (Iceberg) 向け**: Snowflake Managed Iceberg Table を使用して、curated dataset を顧客所有の S3 上にオープン Iceberg 形式で書き込み — Databricks、Athena、EMR、Trino から追加コピーなしでアクセス可能

---

## 将来像: Managed Iceberg によるオープンフォーマットブリッジ

> **サポート確認済み（2026年5月）**: External Stage（`AWS_ACCESS_POINT_ARN` 付き）から Snowflake Managed Iceberg Table への COPY INTO はサポートされています。これにより FSx for ONTAP → S3 AP → Snowflake Managed Iceberg パイプラインが検証されました。

Snowflake [Managed Iceberg Tables](https://docs.snowflake.com/en/user-guide/tables-iceberg) は、顧客所有の S3 ストレージにオープン Apache Iceberg 形式でデータを書き込みます。これによりマルチプラットフォームアーキテクチャが実現します:

```
FSx for ONTAP (Source of Truth)
  ↓ S3 AP (ゼロコピー読み取り) or DataSync (S3 に同期)
Snowflake Managed Iceberg Table (curated, governed)
  ↓ 顧客所有 S3 上のオープン Iceberg 形式
  ├── Databricks UC (Iceberg 読み取り)
  ├── AWS Athena / Glue (Glue Catalog 経由で Iceberg 読み取り)
  ├── EMR Spark (Iceberg 読み書き)
  └── Trino (Iceberg 読み取り)
```

**主要メリット**:
- **ベンダーロックインなし**: データはオープン Iceberg 形式、顧客が所有
- **Snowflake がライフサイクル管理**: OPTIMIZE、Time Travel、ガバナンスタグ — プロプライエタリ形式なし
- **マルチエンジンアクセス**: 同じ curated dataset を全 Iceberg 互換エンジンから読み取り可能
- **ONTAP が Source of Truth のまま**: 高価値な curated subset のみ Iceberg に昇格

> **注意**: このパターンは Iceberg 書き込みパスに標準 S3 が必要です（FSx for ONTAP S3 AP 直接ではない）。DataSync を使用して FSx for ONTAP から S3 に関連サブセットを同期し、Snowflake で Iceberg テーブルとして管理してください。

---

## 参考資料

- [COPY INTO <table>](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table) — ステージからテーブルへのデータロード
- [External Tables](https://docs.snowflake.com/en/user-guide/tables-external-intro) — 外部ストレージ上の読み取り専用テーブル
- [Cortex AI Functions](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions) — LLM 関数概要
- [CREATE CORTEX SEARCH SERVICE](https://docs.snowflake.com/en/sql-reference/sql/create-cortex-search) — セマンティック検索
- [COMPLETE (マルチモーダル)](https://docs.snowflake.com/en/sql-reference/functions/complete-snowflake-cortex-multimodal) — Vision/画像 AI
- [Dynamic Tables](https://docs.snowflake.com/en/user-guide/dynamic-tables-intro) — 自動変換
- [Snowpipe REST API](https://docs.snowflake.com/en/user-guide/data-load-snowpipe-rest-apis) — プログラマティック取り込みトリガー
- [FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) — AWS ドキュメント

---

## 関連ドキュメント

- [Snowflake README](../../README.md) — 統合ステータス全体
- [Analytics & AI デモガイド](ai-demo-guide.md) — AI/ML 機能と検証結果
- [ブロッカートラッカー](../../../../docs/ja/blocker-tracker.md) — BLK-009 に Access Point へのアンロード挙動と部分書き込みハザードを記載
