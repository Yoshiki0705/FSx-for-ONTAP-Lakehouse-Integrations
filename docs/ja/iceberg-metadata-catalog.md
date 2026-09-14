# 非構造化データ向け Iceberg メタデータカタログ: FSx for ONTAP とモダンデータ基盤の架け橋

🌐 日本語 | [English](../en/iceberg-metadata-catalog.md)

## エグゼクティブサマリー

本ドキュメントは、FSx for ONTAP に格納された非構造化データに対して **Apache Iceberg をメタデータカタログとして活用する**アーキテクチャパターンを定義する。生ファイルをデータ基盤に移動するのではなく、実データは ONTAP 上に残し（重複排除・マルチプロトコルアクセス・Snapshot の恩恵を維持）、メタデータ（ファイルパス、タグ、AI 分類結果、ベクトル embedding）をマネージド Iceberg テーブルで管理し、あらゆる分析エンジンからアクセス可能にする。

### 本アーキテクチャが解決する課題

| # | 課題 | 本アーキテクチャによる解決 |
|---|------|------------------------|
| 1 | 非構造化データが「どこに何があるか分からない」 | Iceberg メタデータテーブルで全ファイルをカタログ化。SQL/自然言語で即座に検索可能 |
| 2 | データ共有に「コピーして渡す」しかない | Iceberg REST endpoint + ガバナンスポリシーで即時共有。データ移動なし |
| 3 | AI/ML で活用したいが手動でファイルを探して処理している | FPolicy → Step Functions で自動パイプライン。新規ファイルを自動分類・embedding 生成 |
| 4 | S3 コピーのストレージコストが増え続ける | 実データは FSx for ONTAP に残し（重複排除 50-70%）、メタデータのみ S3 Tables に格納 |
| 5 | 非構造化データにガバナンスが適用されていない | Lake Formation LF-Tags / Horizon Row Access Policy でメタデータ + 実データの両方を制御 |

**主要テクノロジー**:
- **Amazon S3 Tables** — フルマネージド Apache Iceberg テーブル。自動コンパクション、3x クエリ性能、Iceberg REST endpoint 提供
- **FSx for ONTAP S3 Access Points** — ONTAP ボリュームへの S3 互換アクセス（AI/分析の読み取りパス）
- **S3 Metadata** — S3 オブジェクトメタデータの自動 Iceberg テーブル化（DataSync 経由の代替パス）
- **Iceberg REST Catalog** — Databricks、Snowflake、Spark 等からのクロスプラットフォームアクセス

## コアコンセプト: ホットメタデータ × コールド実データ分離

```
┌─────────────────────────────────────────────────────────────────────┐
│  HOT: メタデータ層 (Apache Iceberg on S3 Tables)                      │
│  - ファイルパス、タグ、分類、embedding                                   │
│  - 高速 SQL クエリ (Athena, Redshift, EMR)                            │
│  - ベクトル類似検索 (OpenSearch)                                       │
│  - Iceberg REST endpoint 経由のクロスプラットフォームアクセス              │
│  - Lake Formation / Horizon Catalog によるガバナンス                   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ file_path 参照
┌──────────────────────────────▼──────────────────────────────────────┐
│  COLD: データ層 (FSx for ONTAP)                                      │
│  - 実ファイル: PDF、画像、CAD、動画、音声、ログ                           │
│  - 重複排除 (50-70% ストレージ削減)                                     │
│  - マルチプロトコル: NFS/SMB (既存ワークフロー) + S3 AP (AI/分析)         │
│  - Snapshot: バッチ AI 処理の一貫性あるポイントインタイム                  │
│  - FabricPool: 低コストストレージへの自動階層化                          │
└─────────────────────────────────────────────────────────────────────┘
```

**なぜこの分離が有効か？**

| 観点 | メタデータ層 (S3 Tables) | データ層 (FSx for ONTAP) |
|------|--------------------------|--------------------------|
| クエリ速度 | サブ秒 (Iceberg 最適化) | N/A (クエリ不可) |
| ストレージ効率 | 最小 (~1GB / 10万ファイル) | 重複排除 + 圧縮 (50-70% 削減) |
| マルチエンジンアクセス | ✅ Iceberg REST endpoint | ✅ S3 AP + NFS/SMB |
| ガバナンス | Lake Formation / Horizon | S3 AP ポリシー + ONTAP ACL |
| AI 処理 | embedding をここに格納 | 生ファイルをここから読み取り |
| コスト | ~$5-15/月 (メタデータのみ) | データ量に依存 |

---

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────────┐
│                           ガバナンス層                                │
│                                                                     │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────────┐   │
│  │Lake Formation│  │Snowflake Horizon │  │Databricks Unity      │   │
│  │LF-Tags       │  │Row Access Policy │  │Catalog (External)    │   │
│  │列/行制御      │  │動的マスキング       │  │                      │   │
│  └──────────────┘  └──────────────────┘  └──────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│              メタデータ層 (Apache Iceberg)                            │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ S3 Tables (table bucket) — プライマリメタデータストア             │   │
│  │                                                              │   │
│  │ スキーマ:                                                      │   │
│  │   file_id, file_path, file_name, file_type, file_size        │   │
│  │   created_at, modified_at, source_volume, access_point_arn   │   │
│  │   tags (map), classification, confidence_score               │   │
│  │   embedding_vector (binary), summary                         │   │
│  │   sensitivity_level, has_pii, anonymized_path                │   │
│  │                                                              │   │
│  │ アクセス: Iceberg REST endpoint → Databricks, Snowflake, Spark │   │
│  │ ガバナンス: SageMaker Lakehouse + Lake Formation               │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                      イベント & 処理層                                │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ リアルタイムパス: FPolicy → Fargate → SQS → Lambda             │    │
│  │   (ファイル作成/変更/削除 → 5分以内にメタデータ同期)               │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ AI エンリッチメント: Step Functions → Bedrock/Cortex/Mosaic    │    │
│  │   (分類、embedding、要約、PII 検出)                            │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ バッチパス (代替): DataSync → S3 → S3 Metadata                │    │
│  │   (S3 オブジェクトメタデータから自動 Iceberg テーブル生成)         │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                         ストレージ層                                  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ FSx for ONTAP                                               │    │
│  │   • S3 Access Point → AI/分析の読み取りアクセス                 │    │
│  │   • NFS/SMB → 既存ワークフロー (CAD ツール、エディタ)             │    │
│  │   • 重複排除 + 圧縮 (50-70% 削減)                              │    │
│  │   • Snapshot → バッチ処理の一貫性あるポイントインタイム.           │    │
│  │   • FPolicy → リアルタイムファイルイベント検知                    │    │
│  │   • FabricPool → コールドデータの自動階層化                     │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ オンプレミス ONTAP (オプション)                                 │    │
│  │   • SnapMirror → FSx for ONTAP (ブロックレベルレプリケーション).  │   │
│  │   • FlexCache S3 AP (将来: ONTAP 9.18.1 オンプレ対応済み)       │   │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## プラットフォーム別実装パス

### AWS ネイティブパス (Athena + Lake Formation + Bedrock)

**最適な対象**: AWS ネイティブ分析スタックに既に投資している組織。

```
FSx for ONTAP ──S3 AP──→ Bedrock KB (RAG, Vision)
                    │
                    └──→ Lambda (メタデータ抽出)
                              ↓
                    S3 Tables (Iceberg メタデータ)
                              ↓
                    Glue Catalog (SageMaker Lakehouse)
                              ↓
                    Lake Formation (LF-Tags ガバナンス)
                              ↓
                    Athena / EMR / Redshift Spectrum (クエリ)
```

**主な利点**:
- FSx for ONTAP S3 AP から Athena と Bedrock への直接アクセス（読み取りに S3 コピー不要）
- Lake Formation が全 AWS 分析エンジンにガバナンスを適用
- S3 Tables の自動コンパクションでテーブルメンテナンス不要
- Bedrock Knowledge Base がメタデータをインデックスし自然言語検索を実現

**ガバナンスモデル**: Lake Formation LF-Tags をメタデータテーブルの列/行に適用。タグ例: `department=engineering`, `sensitivity=confidential`, `classification=medical_image`

> **リージョン対応に関する注記**: デプロイ前にターゲットリージョンでの S3 Tables の利用可否を確認すること。ap-northeast-1 で S3 Tables が未対応の場合は、Glue Catalog + セルフマネージド Iceberg テーブルをフォールバックとして使用（同一スキーマ、手動コンパクション必要）。S3 Tables が利用可能になった時点での移行は容易。

### Databricks パス (Unity Catalog + Mosaic AI)

**最適な対象**: Databricks への既存投資がある組織（UC、Delta Lake、MLflow）。

```
S3 Tables ──Iceberg REST endpoint──→ Databricks External Catalog
                                              ↓
                                    Unity Catalog ガバナンス
                                              ↓
                                    Spark SQL / Mosaic AI クエリ
                                              ↓
                                    Vector Search (類似ファイル発見)
```

**主な利点**:
- Iceberg REST endpoint により S3 Tables メタデータに Databricks から直接アクセス
- Mosaic AI による画像/ドキュメントの自動分類パイプライン
- Vector Search による embedding ベースの類似ファイル発見
- Delta Sharing による組織横断メタデータ共有

**現在の制約**: Unity Catalog session policy が S3 AP ARN フォーマットを認識しない（直接ファイルアクセス不可）。回避策: メタデータクエリは Iceberg REST 経由 + ファイルアクセスは Bedrock/Lambda 経由。

**Vector Search 統合**: Databricks ファーストの組織では、S3 Tables から Mosaic AI Vector Search Index に embedding を同期することで、Databricks ネイティブの類似検索が可能。OpenSearch Serverless と比較して、Databricks ノートブックや Model Serving とのより緊密な統合を提供。

**ガバナンスモデル**: Unity Catalog External Catalog + Lake Formation 補完（クロスエンジン適用）。

**将来展望 — Lakehouse Federation**: Databricks の Lakehouse Federation が S3 Tables の Iceberg REST endpoint をネイティブサポートすれば、メタデータクエリと実データアクセスの両方を Databricks ワークスペース内で完結できる可能性がある。Unity Catalog 2.0 の Iceberg ネイティブ対応（2025年発表）もこの方向を加速する。

> **DAIS 2026 アップデート（2026-06-16, evidence tier: Public）**: Databricks は Iceberg v3 GA / Managed Iceberg GA / Foreign Iceberg GA / 新フェデレーションコネクタ / cross-engine ABAC を発表（[What's new with Unity Catalog](https://www.databricks.com/blog/whats-new-unity-catalog-data-ai-summit-2026)）。本アーキテクチャに直結する 2 点:
> - **FILE type（Beta）**: managed Delta/Iceberg テーブルが非構造化データ（PDF・画像・音声・動画）をネイティブにガバナンス可能に。これは UC テーブル内で非構造化ペイロードを*ガバナンス*するマネージドな選択肢であり、本アーキテクチャの役割（FSx for ONTAP 上に置いたまま、AI エンリッチ済み・クロスエンジンの*ディスカバリ*: 分類・PII 処理・ベクトル類似検索）を**置換するものではなく補完**する。非 Databricks エンジン（Athena・Snowflake・EMR）からのアクセスも維持。UC Volumes（ディレクトリ単位ガバナンス）や OpenSharing Volumes asset とも関連。
> - **External access to managed Delta tables（Public Preview）** と新フェデレーションコネクタは、上記の S3 AP / S3 Tables アクセス制約に影響する可能性がある。**要再検証**: Foreign Iceberg が S3 Tables 内部バケットを解決できるようになったか（従来のブロッカーは External Location 検証が標準 S3 API を拒否する点）。
> - **Iceberg v4 / Delta 5.0 統合（ロードマップ）**: Databricks は Delta Lake 5.0 が Iceberg v4 metadata tree をネイティブのコンテンツメタデータとして採用することを提案 — Delta と Iceberg の両クライアントが同一のオンディスク構造を直接 read/write、変換レイヤーもオーバーヘッドもなし（[UC blog](https://www.databricks.com/blog/unity-catalog-and-next-era-apache-icebergtm), [DAIS session](https://www.databricks.com/dataaisummit/session/format-co-evolution-how-iceberg-v4-and-delta-50-share-unified-metadata)）。長期的含意: Delta/Iceberg のフォーマット選択が論点でなくなり、UniForm（現行の変換レイヤー）は不要になり、本アーキテクチャの Iceberg メタデータテーブルへのクロスエンジンアクセスがさらに単純化される。

**Mosaic AI エンリッチメントパイプライン例**:
```python
# Databricks ノートブックでの AI エンリッチメント
from databricks.sdk import WorkspaceClient
import mlflow

# S3 Tables メタデータから pending レコードを取得
pending_files = spark.sql("""
  SELECT file_id, file_path, file_type
  FROM iceberg_catalog.metadata.unstructured_files
  WHERE enrichment_status = 'pending'
  LIMIT 100
""")

# Mosaic AI Foundation Model で分類
for row in pending_files.collect():
    result = mlflow.deployments.predict(
        endpoint="databricks-meta-llama-3-70b-instruct",
        inputs={"prompt": f"Classify this file: {row.file_name}"}
    )
    # 結果を S3 Tables に書き戻し
```

### Snowflake パス (Horizon Catalog + Cortex AI)

**最適な対象**: Snowflake への既存投資がある組織（Cortex AI、Data Sharing、Horizon）。

```
FSx for ONTAP ──S3 AP Stage──→ COPY INTO → Managed Iceberg Table
                                                    ↓
                                          Cortex AI (PARSE_DOCUMENT, Vision)
                                                    ↓
                                          Horizon Iceberg REST Catalog
                                                    ↓
                                          外部エンジン (Spark, Databricks)
                                          Row Access Policy 適用済み
```

**主な利点**:
- Cortex AI が非構造化データを直接処理（PARSE_DOCUMENT、COMPLETE、Vision）
- Horizon Catalog が外部エンジンアクセスにもガバナンスを適用（Row Access Policy、Masking）
- STORAGE_REQUEST_HISTORY で外部エンジンアクセスを監査
- Secure Data Sharing によるゼロコピー組織横断メタデータ共有

**現在の制約**: TO_FILE が S3 AP ステージで失敗（エンジニアリング調査中）。回避策: COPY FILES で内部ステージに転送後 Vision AI 処理。

**ガバナンスモデル**: Horizon Catalog Row Access Policy + Dynamic Masking。Snowflake 内部と外部エンジンの両方に適用。

**Cortex AI エンリッチメントパイプライン例**:
```sql
-- FSx for ONTAP S3 AP Stage からドキュメントを処理し、メタデータを生成
-- Step 1: COPY FILES で内部ステージに転送 (TO_FILE 制約回避)
COPY FILES INTO @internal_processing_stage
  FROM @fsxn_ap_stage/new_documents/
  PATTERN = '.*\.pdf';

-- Step 2: PARSE_DOCUMENT でテキスト抽出 (S3 AP Stage で直接動作)
SELECT
  file_name,
  SNOWFLAKE.CORTEX.PARSE_DOCUMENT(
    @fsxn_ap_stage, relative_path, {'mode': 'LAYOUT'}
  ):content AS extracted_text
FROM DIRECTORY(@fsxn_ap_stage)
WHERE relative_path LIKE '%.pdf';

-- Step 3: Cortex COMPLETE で分類・要約
SELECT
  file_path,
  SNOWFLAKE.CORTEX.COMPLETE('claude-sonnet-4-5',
    'Classify this document into one of: contract, invoice, report, manual. '
    || 'Also provide a 2-sentence summary. Document: ' || extracted_text
  ) AS ai_result
FROM extracted_documents;

-- Step 4: 結果を Managed Iceberg Table に INSERT
INSERT INTO managed_iceberg_metadata (file_id, classification, summary, enriched_at)
SELECT file_id, parsed_classification, parsed_summary, CURRENT_TIMESTAMP()
FROM ai_results;
```

**Horizon Catalog による外部エンジンガバナンス適用例**:
```sql
-- Row Access Policy: 部門ベースのアクセス制御
CREATE OR REPLACE ROW ACCESS POLICY department_filter AS (department STRING)
  RETURNS BOOLEAN ->
    CURRENT_ROLE() IN ('ADMIN_ROLE')
    OR department = CURRENT_SESSION_CONTEXT('department');

-- Managed Iceberg Table に適用 → 外部エンジン (Spark, Databricks) にも自動適用
ALTER TABLE managed_iceberg_metadata
  ADD ROW ACCESS POLICY department_filter ON (department_tag);
```

---

## 意思決定マトリクス: メタデータ層の選択

| 基準 | S3 Tables | Snowflake Managed Iceberg | Glue Catalog (セルフマネージド Iceberg) |
|------|-----------|--------------------------|----------------------------------------|
| **運用負荷** | なし (フルマネージド) | なし (フルマネージド) | 中 (手動コンパクション、スナップショット期限) |
| **クエリ性能** | セルフマネージド比 3x | 同等 | ベースライン |
| **クロスプラットフォーム** | ✅ Iceberg REST endpoint | ✅ Horizon REST Catalog | ✅ Glue Catalog + Iceberg |
| **ガバナンス** | Lake Formation + SageMaker Lakehouse | Horizon (Row Access Policy, Masking) | Lake Formation |
| **外部エンジン適用** | ✅ (Lake Formation 経由) | ✅ (Horizon 経由) | ✅ (Lake Formation 経由) |
| **自動コンパクション** | ✅ 組み込み | ✅ 組み込み | ❌ 手動 or Glue ジョブ |
| **コスト (10万レコード)** | ~$5-15/月 | Snowflake コンピュートに含む | ~$5/月 + メンテナンスコンピュート |
| **リージョン対応** | 拡大中 (要確認) | 全 Snowflake リージョン | 全 AWS リージョン |
| **最適な用途** | AWS ネイティブ + マルチエンジン | Snowflake ファースト + 外部共有 | 最大の柔軟性 |

**推奨**: AWS ネイティブパスでは S3 Tables から開始。外部エンジンへの Horizon ガバナンスが必要な場合は Snowflake Managed Iceberg を追加。S3 Tables が未対応のリージョンでは Glue Catalog をフォールバックとして使用。

---

## イベント検知: FPolicy パイプライン vs DataSync + S3 Metadata

| 観点 | FPolicy パイプライン | DataSync + S3 Metadata |
|------|---------------------|----------------------|
| **レイテンシ** | ~5 秒 (リアルタイム) | 分〜時間 (バッチ) |
| **データコピー** | 不要 (メタデータのみ) | 必要 (全ファイルを S3 にコピー) |
| **ストレージコスト** | 最小 (S3 Tables のメタデータのみ) | 大 (S3 に全ファイルのコピー) |
| **構築複雑度** | 中 (FPolicy Server + Lambda) | 低 (DataSync タスク + S3 Metadata 有効化) |
| **メタデータの豊富さ** | カスタム (任意のフィールド抽出可) | 標準 S3 オブジェクトメタデータ + カスタムタグ |
| **AI エンリッチメント** | 別パイプライン (Step Functions) | 別パイプライン (同様) |
| **最適な用途** | リアルタイムカタログ、S3 コピー予算なし | バッチ処理、S3 コピーが他の理由で必要 |

**推奨**: FPolicy パイプラインをプライマリパスとして使用（S3 コピーコストを排除）。DataSync + S3 Metadata は S3 コピーが他の理由で既に必要な場合（例: Bedrock KB データソース、クロスリージョンアクセス）の補完パスとして使用。

> **Iceberg 実装上の注記**: FPolicy パイプラインで S3 Tables に書き込む際、PyIceberg SDK の `append` 操作を使用する。Iceberg format-version=2 では Row-level Deletes（Position Delete Files）がサポートされており、ファイル削除時の soft delete を効率的に実装できる。ただし、S3 Tables の自動コンパクションが Position Delete Files を定期的にマージするため、読み取り性能への影響は最小限に抑えられる。

> **ハイブリッド構成の注記**: FPolicy パイプラインと DataSync パスは排他ではなく**併用可能**。例えば、FPolicy でリアルタイムメタデータ同期を行いつつ、DataSync で Bedrock KB 用の S3 コピーを維持する構成が現実的。この場合、S3 Metadata テーブルと S3 Tables メタデータテーブルを Athena で JOIN することで、両方のメタデータソースを統合クエリできる。

### ハイブリッド構成例: FPolicy + DataSync 併用

```
FSx for ONTAP
  ├── FPolicy → SQS → Lambda → S3 Tables (リアルタイムメタデータ)
  │                                  ↓
  │                          Athena / Databricks / Snowflake
  │
  └── DataSync (日次) → S3 General Purpose Bucket
                              ├── S3 Metadata (自動 Iceberg)
                              ├── Bedrock KB (RAG データソース)
                              └── クロスリージョン DR コピー
```

**使い分けの判断基準**:
- メタデータ検索のみ必要 → FPolicy パイプラインのみ（S3 コピー不要）
- Bedrock KB で RAG も必要 → FPolicy + DataSync 併用
- DR 要件あり → DataSync でクロスリージョン S3 コピー + S3 Metadata

### 本番運用ノート: S3 AP I/O とチェックポイント設計

#### S3 Access Point スループット影響

FSx for ONTAP S3 Access Point の読み取りはファイルシステムのプロビジョンドスループットを消費する。

| シナリオ | 典型的なスループット | 本番影響 |
|---------|-------------------|---------|
| イベント駆動メタデータスキャン（本パイプライン） | < 10 MB/s | NFS/SMB ワークロードへの影響は無視可能 |
| バックフィル（数千ファイルの一括スキャン） | 50-200 MB/s バースト | オフピーク時にスケジュール |
| 高頻度ポーリング（サブ分間隔） | 可変 | Lambda 同時実行制限で制御 |

**緩和策:**
- CloudWatch `DataReadBytes` メトリクスでファイルシステムを監視
- Lambda 予約同時実行数で S3 AP 読み取りの並列度を制限
- 初回バックフィルは `burst` スループットモードまたはオフピーク時にスケジュール

#### 本番チェックポイント: DynamoDB 移行

PoC では SSM Parameter Store でスキャン位置を管理。本番では DynamoDB のリースベースロックで Lambda 同時実行時の二重処理を防止:

```
DynamoDB テーブル: metadata-scan-checkpoints
  PK: scan_path (S)          # スキャン対象の S3 AP パスプレフィックス
  属性:
    status:       S           # PENDING | PROCESSING | COMPLETED | FAILED
    lease_expiry: N           # Unix タイムスタンプ — この時刻でロック自動解除
    processor_id: S           # Lambda リクエスト ID（呼び出しごとに一意）
    last_offset:  S           # 最後に処理したファイルパスまたはマーカー
    ttl:          N           # COMPLETED レコードを7日後に自動削除
```

**条件付き書き込みパターン（ゴーストロック防止）:**

```python
# リース取得 — アクティブなプロセッサがいない場合のみ成功
table.put_item(
    Item={...},
    ConditionExpression=(
        'attribute_not_exists(scan_path) OR '  # 新規スキャン
        'status = :failed OR '                  # 以前失敗
        'lease_expiry < :now'                   # ゴーストロック失効
    )
)
```

**設計ポイント:**
- `lease_expiry` = Lambda タイムアウト + 5分バッファ（例: 計15分）
- `status=PROCESSING` が 2× リース期間を超えた場合に CloudWatch アラーム（ゴースト検出）
- DynamoDB TTL で COMPLETED レコードを7日後に自動削除（コスト制御）
- Lambda クラッシュ/タイムアウト時: リースが自動失効し、次の呼び出しがロックを取得

---

## AI エンリッチメントパイプライン

### ファイルタイプ別処理モード

| ファイルタイプ | AI サービス | 出力 | レイテンシ | コスト (1ファイル) |
|--------------|-----------|------|---------|-----------------|
| PDF/ドキュメント | Bedrock Claude (要約、抽出) | 要約、エンティティ、分類 | 5-30秒 | $0.01-0.05 |
| 画像 | Bedrock Claude Vision (分類、説明) | 説明、分類、オブジェクト | 3-10秒 | $0.01-0.03 |
| 音声 | Transcribe → Bedrock (要約) | 文字起こし、要約、感情 | 30-120秒 | $0.02-0.10 |
| 動画 | フレーム抽出 → Vision (サンプリング) | シーン説明、分類 | 60-300秒 | $0.05-0.50 |
| CAD/3D | メタデータ抽出のみ | 寸法、レイヤー、コンポーネント | 1-5秒 | $0.001 |
| ログ/センサー | パターン検出 (Bedrock) | 異常、パターン、統計 | 5-15秒 | $0.01-0.03 |

### Embedding 生成

全ファイルタイプに対して 1536 次元ベクトル embedding（Amazon Titan Embeddings V2）を生成:
- ドキュメント: 本文テキストから
- 画像: AI 生成説明文から
- 音声: 文字起こしテキストから
- 動画: 連結シーン説明から

Embedding により**類似検索**が可能: 「このファイルに似たファイルを探す」— OpenSearch Serverless の kNN 検索、または Iceberg embedding カラムのブルートフォーススキャン。

### モデル選択ガイダンス

> **モデル選択の注記**: embedding モデルの選択はコストと精度のトレードオフ。以下の判断基準を参考にすること。

| 用途 | 推奨モデル | 次元数 | コスト/1K tokens | 精度 |
|------|----------|--------|----------------|------|
| 汎用テキスト検索 | Amazon Titan Embeddings V2 | 1024 | $0.00002 | 高 |
| 高精度セマンティック検索 | Cohere Embed v3 | 1024 | $0.0001 | 最高 |
| 多言語対応 (日英混在) | Amazon Titan Embeddings V2 (multilingual) | 1024 | $0.00002 | 高 |
| 画像+テキスト統合 | Amazon Titan Multimodal Embeddings | 1024 | $0.0008/image | 中-高 |

**推奨**: 日英混在環境では Amazon Titan Embeddings V2 (multilingual) から開始。精度が不足する場合は Cohere Embed v3 に切り替え。embedding 次元数は 1024 を標準とし、ストレージ効率と検索精度のバランスを取る。

### エラーハンドリングとリトライ戦略

```
AI エンリッチメント失敗時のフロー:

1. Bedrock ThrottlingException
   → exponential backoff (1s, 2s, 4s, 8s, max 30s)
   → 3回リトライ後: enrichment_status = "failed", retry_count++
   → CloudWatch Alarm → 並列度を下げる

2. ファイル読み取り失敗 (S3 AP AccessDenied / Timeout)
   → enrichment_status = "failed", error_reason = "access_denied"
   → 次回リコンシリエーションで再試行

3. AI 処理結果が低品質 (confidence < 0.3)
   → enrichment_status = "low_confidence"
   → 人間レビューキューに追加 (SNS → 管理者通知)

4. Lambda タイムアウト (大ファイル: >100MB)
   → ECS Fargate タスクにフォールバック (タイムアウトなし)
   → 動画/大容量 CAD ファイルはデフォルトで Fargate パス
```

### PII 検出と匿名化

```
ファイル → PII 検出 (Comprehend / Bedrock)
              │
              ├─ PII なし → has_pii=false, anonymization_status="not_required"
              │
              └─ PII 検出 → has_pii=true
                               ↓
                     匿名化パイプライン
                     (顔ぼかし、PII 墨消し、DICOM 匿名化)
                               ↓
                     anonymized_path = クリーンバージョンのパス
                     anonymization_status = "completed"
```

### PII 検出エンジンの選択: 言語別

| 言語 | 推奨エンジン | 検出可能な PII タイプ | 検証結果 |
|------|-----------|-------------------|---------|
| **英語** | Amazon Comprehend (`detect_pii_entities`) | NAME, EMAIL, PHONE, ADDRESS, SSN, CREDIT_DEBIT_NUMBER, DATE_TIME 等 | ✅ 7/7 検出 (confidence >= 0.8) |
| **スペイン語** | Amazon Comprehend (`detect_pii_entities`) | 英語と同等 | — (未テスト) |
| **日本語** | **Bedrock Claude** (プロンプトベース) | 氏名、メール、電話番号、住所、マイナンバー、クレジットカード、生年月日 | ✅ 8/8 検出 (confidence 1.0) |
| **その他の言語** | Bedrock Claude (プロンプトベース) | プロンプトで指定した任意の PII タイプ | — |

> **制約**: Amazon Comprehend の `detect_pii_entities` API は `en`（英語）と `es`（スペイン語）のみサポート（2026年5月時点）。日本語を含むその他の言語では Bedrock Claude をPII 検出エンジンとして使用する。

### 日本語 PII 検出パターン (Bedrock Claude)

```python
import boto3, json

bedrock = boto3.client('bedrock-runtime', region_name='ap-northeast-1')

def detect_pii_japanese(text: str) -> list:
    """
    Bedrock Claude による日本語 PII 検出。
    Comprehend が日本語未サポートのため、LLM ベースで検出する。
    
    検出対象:
      - 氏名 (NAME)
      - メールアドレス (EMAIL)
      - 電話番号 (PHONE)
      - 住所 (ADDRESS)
      - マイナンバー (MY_NUMBER)
      - クレジットカード番号 (CREDIT_CARD)
      - 生年月日 (DATE_OF_BIRTH)
      - パスポート番号 (PASSPORT)
      - 運転免許証番号 (DRIVER_LICENSE)
    """
    prompt = f"""以下の日本語テキストから個人情報（PII）を全て検出してください。
JSON配列で返してください: [{{"type": "...", "value": "...", "confidence": 0.X}}]

検出対象のPIIタイプ:
- NAME: 氏名（日本語・英語）
- EMAIL: メールアドレス
- PHONE: 電話番号（固定・携帯）
- ADDRESS: 住所（郵便番号含む）
- MY_NUMBER: マイナンバー（12桁）
- CREDIT_CARD: クレジットカード番号
- DATE_OF_BIRTH: 生年月日
- PASSPORT: パスポート番号
- DRIVER_LICENSE: 運転免許証番号
- OTHER: その他の個人識別情報

テキスト:
{text}"""

    response = bedrock.invoke_model(
        modelId='anthropic.claude-3-haiku-20240307-v1:0',
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            'anthropic_version': 'bedrock-2023-05-31',
            'max_tokens': 2048,
            'messages': [{'role': 'user', 'content': prompt}],
        }),
    )
    
    result = json.loads(response['body'].read())
    ai_text = result['content'][0]['text']
    
    # Parse JSON response
    if '```json' in ai_text:
        ai_text = ai_text.split('```json')[1].split('```')[0]
    elif '```' in ai_text:
        ai_text = ai_text.split('```')[1].split('```')[0]
    
    return json.loads(ai_text.strip())
```

**検証結果 (2026-05-31)**:

入力テキスト:
```
社員情報
氏名: 山田太郎
メールアドレス: taro.yamada@example.co.jp
電話番号: 090-1234-5678
住所: 〒150-0002 東京都渋谷区渋谷1-2-3
マイナンバー: 1234 5678 9012
クレジットカード: 4111-1111-1111-1111
生年月日: 1985年3月15日
```

検出結果: **8/8 エンティティ検出（全て confidence 1.0）**

| PII タイプ | 検出値 | Confidence |
|-----------|--------|-----------|
| NAME | 山田太郎 | 1.0 |
| EMAIL | taro.yamada@example.co.jp | 1.0 |
| PHONE | 090-1234-5678 | 1.0 |
| ADDRESS | 〒150-0002 東京都渋谷区渋谷1-2-3 | 1.0 |
| MY_NUMBER | 1234 5678 9012 | 1.0 |
| CREDIT_CARD | 4111-1111-1111-1111 | 1.0 |
| DATE_OF_BIRTH | 1985年3月15日 | 1.0 |
| OTHER (社員番号) | EMP-2024-0042 | 1.0 |

### PII 検出エンジン選択ロジック

```python
def detect_pii(text: str, language: str) -> list:
    """言語に応じて最適な PII 検出エンジンを選択"""
    if language in ('en', 'es'):
        # Comprehend: 高速、低コスト、確定的
        return detect_pii_comprehend(text, language)
    else:
        # Bedrock Claude: 多言語対応、高精度、やや高コスト
        return detect_pii_bedrock(text, language)
```

| 比較項目 | Comprehend | Bedrock Claude |
|---------|-----------|---------------|
| 対応言語 | en, es のみ | 全言語 |
| レイテンシ | ~200ms | ~2-5秒 |
| コスト | $0.0001/100文字 | ~$0.003/リクエスト (Haiku) |
| 精度 | 高（学習済みモデル） | 非常に高（LLM 推論） |
| マイナンバー検出 | ❌ 未対応 | ✅ 対応 |
| カスタム PII タイプ | ❌ 固定 | ✅ プロンプトで追加可能 |
| 推奨用途 | 英語大量処理 | 日本語、多言語、カスタム PII |

**データクリーンルームパターン**: オリジナルメタデータテーブル（制限アクセス）+ クリーンメタデータテーブル（広範囲アクセス、匿名化ファイルのみ）。Lake Formation で分離を適用。

---

## コスト見積もり

### シナリオ: 10TB 非構造化データ、10万ファイル、1000変更/日

| コンポーネント | 月額コスト | 備考 |
|-------------|-----------|------|
| **S3 Tables (メタデータストレージ)** | ~$5 | 10万レコードで ~1GB |
| **S3 Tables (リクエスト)** | ~$10 | Lambda からの書き込み + クエリからの読み取り |
| **Lambda (メタデータ同期)** | ~$5 | 1000イベント/日 × 200ms × 128MB |
| **Lambda (AI エンリッチメント)** | ~$50 | 100新規ファイル/日 × 30s × 512MB。実測: 6秒/ファイル (画像分類 + embedding) |
| **Bedrock (AI 処理)** | ~$100-500 | モデル選択とボリュームに依存。実測: $0.01/ファイル (Claude 3 Haiku Vision) |
| **Step Functions** | ~$5 | ステート遷移 |
| **SQS** | ~$1 | メッセージ処理 |
| **OpenSearch Serverless (オプション)** | **$0 (アイドル時)** | NextGen scale-to-zero (2026年5月GA)。アクティブ時 $0.24/OCU-hour。PoC/開発環境はアイドル時コストゼロ |
| **FSx for ONTAP (既存)** | — | プライマリストレージとして既にプロビジョニング済み |
| | | |
| **合計 (ベクトル検索なし)** | **~$175-575/月** | |
| **合計 (ベクトル検索あり)** | **~$175-575/月 (アクティブ時)** | NextGen scale-to-zero によりアイドル時追加コストなし |

### 代替アプローチとのコスト比較

| アプローチ | 月額コスト (10TB) | メタデータレイテンシ | ガバナンス |
|----------|-----------------|-------------------|-----------|
| **本アーキテクチャ (FPolicy + S3 Tables)** | $175-575 | ~5 秒 | Lake Formation / Horizon |
| S3 フルコピー + Glue Crawler | $230-256 (S3)* + $50 (Glue) | 時間 | Lake Formation |
| S3 フルコピー + S3 Metadata | $230-256 (S3)* + $15 (Metadata) | 分 | Lake Formation |
| カスタム DynamoDB カタログ | $50-200 | 秒 | カスタム IAM |

> *S3 Standard ストレージ料金: us-east-1 $0.023/GB ($230/10TB)、ap-northeast-1 $0.025/GB ($256/10TB)。2026-06-01 確認。

> **コスト評価の注記**: 上記コストは直接コストのみ。本アーキテクチャの真の ROI は「データ発見時間の短縮」「共有リードタイムの削減」「AI 自動化による人件費削減」を含めて評価すべき。10人のデータサイエンティストが週5時間をデータ探索に費やしている場合、年間 $150K+ の人件費削減が見込める。

### TCO 比較 (3年間、10TB、100K ファイル)

| 項目 | 現状 (S3 コピー + 手動) | 本アーキテクチャ |
|------|----------------------|----------------|
| ストレージ (S3 + FSx) | $8,280 (S3) + $16,200 (FSx) | $0 (S3 不要) + $16,200 (FSx) |
| メタデータ管理 | $0 (なし) | $540 (S3 Tables 3年) |
| AI 処理 | $0 (手動) | $3,600-18,000 (Bedrock) |
| 人件費 (データ探索) | $450,000 (10人×5h/週×3年) | $45,000 (90% 削減) |
| **3年 TCO** | **$474,480** | **$65,340-$79,740** |
| **削減率** | — | **83-86%** |

> **ベンチマーク注記**: 上記の人件費削減率 (90%) は仮定値であり、実際の効果は組織のデータ利用パターンに依存する。PoC で実測した「データ発見時間」の Before/After を用いて顧客固有の ROI を算出すること。

---

## 運用モニタリング

### パイプライン健全性ダッシュボード

| メトリクス | ソース | アラート条件 | 対応 |
|----------|--------|-----------|------|
| FPolicy イベント処理数/分 | CloudWatch (Lambda) | 0 が 10分以上継続 | FPolicy Server / SQS 確認 |
| メタデータ同期レイテンシ (p99) | CloudWatch (Lambda Duration) | > 30秒 | Lambda メモリ/タイムアウト調整 |
| DLQ メッセージ数 | CloudWatch (SQS) | > 0 | DLQ メッセージ内容確認、リドライブ |
| AI エンリッチメント pending 数 | Athena クエリ (S3 Tables) | > 1000 | Step Functions 並列度調整 |
| リコンシリエーション gap 数 | CloudWatch (Step Functions) | > 100 | FPolicy イベントロス調査 |
| Bedrock スロットリング | CloudWatch (Bedrock) | ThrottlingException > 0 | リクエストレート調整、バックオフ |
| S3 AP AccessDenied | CloudTrail | > 10/10分 | IAM/AP ポリシー確認 |

### ストレージ層メトリクス統合

Amazon FSx for NetApp ONTAP の CloudWatch メトリクスおよび ONTAP REST API から以下のストレージ層メトリクスを監視し、メタデータカタログの健全性と合わせて確認:

| メトリクス | ソース | 確認ポイント | メタデータカタログとの関連 |
|----------|--------|-----------|----------------------|
| ボリューム使用率 | CloudWatch (FSx) / ONTAP REST API | 85% 超でアラート | 新規ファイル追加が停止 → メタデータ同期も停止 |
| 重複排除率 | ONTAP REST API | 期待値との乖離 | 重複ファイルの特定 → メタデータで可視化 |
| FabricPool 階層化率 | ONTAP REST API | コールドデータ比率 | AI 処理対象ファイルのアクセスレイテンシに影響 |
| Snapshot 使用量 | CloudWatch (FSx) / ONTAP REST API | 予期しない増加 | AI バッチ処理用 Snapshot の削除忘れ |

詳細なオブザーバビリティパイプラインは [fsxn-observability-integrations](https://github.com/Yoshiki0705/fsxn-observability-integrations) を参照。

---

## 成功 KPI

| KPI | Before (現状) | After (本アーキテクチャ) | 計測方法 |
|-----|-------------|------------------------|---------|
| **データ発見時間** | 数日 (手動検索、同僚に確認) | 数秒 (SQL メタデータ検索、自然言語) | 「Xが必要」から「Xを発見」までの時間 |
| **共有リードタイム** | 数週間 (コピー、承認、転送) | 即時 (Iceberg REST + ガバナンスポリシー) | 共有リクエストからアクセス付与までの時間 |
| **AI 処理スループット** | 手動 (人がファイル選択、ツール実行) | 自動 (FPolicy → Step Functions パイプライン) | 人手介入なしで処理されるファイル数/日 |
| **ストレージコスト** | ベースライン (S3 フルコピー + 重複排除なし) | 30-70% 削減 (ONTAP 重複排除 + S3 コピー排除) | 月次ストレージ支出 |
| **ガバナンスカバレッジ** | 0% (メタデータなし、非構造化データにアクセス制御なし) | 100% (全ファイルカタログ化、LF-Tags/Horizon 適用) | 分類 + アクセスポリシー適用済みファイルの割合 |
| **組織横断データ再利用** | ほぼゼロ (サイロ化されたコピー) | 計測可能 (Delta Sharing / Secure Data Sharing メトリクス) | 2組織以上からアクセスされるユニークデータセット数 |

---

## 業界別ユースケース例

| 業界 | ユースケース | 主要ファイル | AI 処理 | ビジネス価値 |
|------|-----------|-----------|---------|------------|
| **製造業** | 設計図面の類似検索 | CAD (DWG, STEP)、図面 (PDF) | Embedding → 類似検索 | 過去設計の再利用率↑、R&D 期間↓ |
| **金融** | 契約書の自動分類 + コンプライアンス検索 | 契約書 (PDF)、明細書 | エンティティ抽出、分類 | コンプライアンス検索時間: 数日→数秒 |
| **医療** | DICOM 画像の匿名化共有（研究用） | 医療画像 (DICOM)、レポート (PDF) | DICOM 匿名化、PII 墨消し | プライバシーリスクなしの研究データセット構築 |
| **メディア** | 動画アセットのタグ検索 + コンテンツ再利用 | 動画 (MP4)、画像 (RAW, JPEG) | シーン分類、物体検出 | コンテンツ再利用効率↑、ライセンスコンプライアンス |
| **公共セクター** | 監視映像のガバナンス + 異常検知 | 動画 (H.264)、センサーログ | 顔検出（ぼかし用）、異常検知 | 市民プライバシー保護 + セキュリティ |
| **エネルギー/ユーティリティ** | IoT センサーログのパターン検出 | センサーデータ (CSV, Parquet)、保守ログ | 異常検知、予知保全 | 計画外ダウンタイム↓、保守コスト↓ |

---

## データ主権、暗号化、監査保持期間

> **規制対応の注記**: 規制産業では「データがどこにあるか」「誰がアクセスしたか」「いつ削除されたか」の3点が常に説明可能でなければならない。本アーキテクチャは、メタデータと実データの両方が同一リージョンに留まり、全アクセスが CloudTrail + Lake Formation ログで追跡可能な設計となっている。ただし、本ドキュメントはガバナンスガイダンスであり、法的/コンプライアンス判断を代替するものではない。規制要件の最終判断は法務・コンプライアンス部門に確認すること。

### データ主権

| コンポーネント | 所在地 | リージョン間転送 |
|-------------|--------|---------------|
| 生ファイル (FSx for ONTAP) | FSx for ONTAP ファイルシステムと同一リージョン | なし (S3 AP は同一リージョンのみ) |
| メタデータテーブル (S3 Tables) | 同一リージョン (設定可能) | なし (クエリ結果もリージョン内) |
| AI 処理 (Bedrock/Lambda) | 同一リージョン | なし (リージョン内処理) |
| ガバナンス (Lake Formation) | 同一リージョン | クロスアカウント可能 (同一リージョン) |

**保証**: メタデータと生データの両方が同一 AWS リージョンに留まる。デフォルトアーキテクチャでは越境データ転送は発生しない。規制産業のデータレジデンシー要件を満たす。

### 保存時暗号化

| 層 | 暗号化 | 鍵管理 |
|----|--------|--------|
| FSx for ONTAP | SSE-FSX (AES-256) | AWS KMS マネージド、透過的 |
| S3 Tables | SSE-S3 or SSE-KMS | 顧客選択 (コンプライアンスには KMS 推奨) |
| SQS メッセージ | SSE-SQS or SSE-KMS | AWS マネージド or 顧客 KMS |
| Lambda 環境 | デフォルト暗号化 | AWS マネージド |
| OpenSearch Serverless | デフォルト暗号化 | AWS マネージド or 顧客 KMS |

### 監査ログ保持期間

| 規制 | 必要保持期間 | 推奨設定 |
|------|-----------|---------|
| HIPAA (医療) | 6-7年 | CloudTrail: S3 アーカイブ (7年)、Lake Formation ログ: 7年 |
| SOX / 金融 | 5-7年 | CloudTrail: S3 アーカイブ (7年)、クエリログ: 5年 |
| GDPR (EU) | 処理期間 + 合理的期間 | CloudTrail: 最低3年、削除監査: 無期限 |
| 一般企業 | 1-3年 | CloudTrail: 90日ホット + S3 アーカイブ (3年) |

**実装**: CloudTrail ログを S3 に配信し、保持要件に合わせたライフサイクルポリシーを設定。Lake Formation アクセスログも同様のパターンに従う。

---

## ONTAP Snapshot と FlexClone の AI 処理活用

> **ストレージ効率の注記**: ONTAP の重複排除はブロックレベル（4KB）で動作する。同一ファイルの部門コピー（例: 設計図面を5部門が保持）では最大 80% の削減が期待できる。一方、「類似だが異なる」ファイル（例: バージョン違いの PDF）では効果は限定的（10-30%）。本アーキテクチャでは、メタデータカタログにより「どのファイルが同一か」を可視化し、不要なコピーの削除判断を支援する。

### 重複排除効果の目安

| データパターン | 重複排除率 | 例 |
|-------------|----------|---|
| 同一ファイルの部門コピー | 70-80% | 設計図面を5部門が保持 → 実質1コピー |
| バージョン管理されたドキュメント | 30-50% | 契約書 v1, v2, v3 → 共通ブロック共有 |
| 画像/動画（ユニーク） | 5-15% | 製品写真、監視映像 → ヘッダー/メタデータ部分のみ |
| ログ/センサーデータ | 20-40% | 繰り返しパターンのあるテキストデータ |
| 圧縮済みファイル (ZIP, MP4) | 0-5% | 既に圧縮済みのためブロック重複が少ない |

> **注意**: 上記は一般的な目安であり、実際の効果はデータの特性に依存する。PoC での実測を推奨。`volume efficiency show` コマンドで実際の削減率を確認可能。

### パターン: Snapshot ベースのバッチ AI 処理

```
1. AI バッチ処理前に Snapshot を作成
   → 一貫性あるポイントインタイムビューを保証
   → 処理中にファイルが変更されない

2. AI パイプラインが Snapshot から読み取り (S3 AP 経由)
   → 本番 NFS/SMB ワークロードへの干渉なし
   → 決定論的結果 (同じ入力 = 同じ出力)

3. 処理完了後、Snapshot を削除可能
   → 追加ストレージコストゼロ (ONTAP Snapshot は容量効率的)
```

**ユースケース**: 毎晩の AI エンリッチメントバッチで全新規ファイルを処理。Snapshot により処理中のファイル変更を防止し、部分読み取りや不整合な分類を防ぐ。

### パターン: FlexClone による AI サンドボックス

```
1. 本番ボリュームを FlexClone
   → 即時 (メタデータのみの操作)
   → 追加ストレージゼロ (Copy-on-Write)

2. AI チームが FlexClone 上で実験
   → ファイルの変更、削除、再編成が自由
   → 本番ボリュームへの影響なし

3. 検証済み結果をメタデータテーブルに書き込み
   → 実験後に FlexClone を削除
```

**ユースケース**: データサイエンスチームが本番データで新しい分類モデルをテストしたい場合。FlexClone がストレージオーバーヘッドゼロで数秒でフルコピーを提供。

---

## 定期フルスキャン同期（リコンシリエーション）

### 必要性

FPolicy 非同期モードは極端な高負荷時（10,000+ イベント/秒の持続）にイベントをドロップする可能性がある。また、FPolicy 有効化前に作成されたファイルにはメタデータレコードがない。定期的なリコンシリエーションによりメタデータテーブルの完全性を保証する。

### 設計

```
EventBridge スケジュール (毎日 02:00 UTC)
  → Step Functions: FullScanReconciliation
    → Lambda: FSx for ONTAP S3 AP で ListObjectsV2 (ページネーション)
    → Lambda: Metadata_Table と比較 (anti-join)
    → Lambda: 欠落レコードを INSERT (enrichment_status = "pending")
    → CloudWatch メトリクス: reconciliation_gap_count
```

### 設定パラメータ

| パラメータ | デフォルト | 備考 |
|----------|---------|------|
| スケジュール | 毎日 02:00 UTC | 低トラフィック時間帯 |
| スコープ | FPolicy 有効な全ボリューム | ボリューム単位で設定可能 |
| バッチサイズ | Lambda 呼び出しあたり 1000 オブジェクト | ページネーション |
| アラート閾値 | gap_count > 100 | FPolicy イベントロスを示唆 |

---

## Snowflake Cortex Search によるメタデータ自然言語検索

### パターン: メタデータテーブルに対する Cortex Search

```
Managed Iceberg Table (メタデータ)
  → Cortex Search Service (インデックス対象: summary, tags, classification, file_name)
    → 自然言語クエリ: 「2025年のポンプ設計に関連するエンジニアリング図面を探して」
      → 結果: file_path + メタデータのランク付きリスト
```

### 設定例

```sql
-- メタデータテーブルに Cortex Search サービスを作成
CREATE OR REPLACE CORTEX SEARCH SERVICE metadata_search
  ON unstructured_file_metadata
  WAREHOUSE = 'COMPUTE_WH'
  TARGET_LAG = '1 hour'
  ATTRIBUTES = 'file_type, classification, sensitivity_level'
  COLUMNS = 'summary, file_name, tags'
  AS (
    SELECT
      file_id,
      file_path,
      file_name,
      file_type,
      classification,
      sensitivity_level,
      summary,
      OBJECT_CONSTRUCT_KEEP_NULL(*) AS tags_json
    FROM unstructured_file_metadata
    WHERE is_deleted = FALSE
      AND enrichment_status = 'completed'
  );
```

### SQL 検索との比較

| 観点 | SQL (Athena/Redshift) | Cortex Search |
|------|---------------------|---------------|
| クエリタイプ | 完全一致、LIKE、正規表現 | 自然言語、セマンティック |
| セットアップ | なし (標準 SQL) | Cortex Search サービス作成 |
| 関連性ランキング | 手動 (ORDER BY) | 自動 (ML ベース) |
| あいまい検索 | 限定的 | 組み込み |
| 最適な用途 | 構造化フィルタ (日付、タイプ、タグ) | 発見 (「Xに関するドキュメントを探す」) |

**推奨**: 構造化クエリ（既知のフィルタ）には SQL、発見（未知またはあいまいな要件）には Cortex Search を使用。両方とも同じ Iceberg メタデータテーブルにアクセス。

---

## 匿名化品質保証プロセス

### 課題

AI ベースの PII 検出は 100% 正確ではない。偽陰性（PII 見逃し）はコンプライアンスリスクを生む。偽陽性（過剰墨消し）はデータの有用性を低下させる。

### 推奨プロセス

```
┌─────────────────────────────────────────────────────────┐
│ Stage 1: 自動 PII 検出                                   │
│   Comprehend + Bedrock → has_pii フラグ                  │
│   期待精度: 95-98%                                       │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│ Stage 2: 自動匿名化                                      │
│   顔ぼかし、PII 墨消し、DICOM 匿名化                    │
│   出力: 匿名化ファイル + anonymized_path                 │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│ Stage 3: 人間によるサンプリングレビュー (週次)            │
│   - 匿名化ファイルのランダム 5% サンプル                 │
│   - レビュー項目: PII 完全除去？ 過剰墨消し？            │
│   - フィードバックループ → モデルファインチューニング     │
│   - エスカレーション: ミス率 > 2% でパイプライン一時停止  │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│ Stage 4: 監査証跡                                        │
│   - 誰がレビューしたか、いつ、どの判断                   │
│   - 各ファイルを処理したパイプラインバージョン            │
│   - 保持期間: 規制要件に準拠                             │
└─────────────────────────────────────────────────────────┘
```

### DICOM 匿名化方式

| 方式 | HIPAA 準拠 | データ有用性 | 複雑度 |
|------|-----------|------------|--------|
| **Safe Harbor** | ✅ (18 識別子を除去) | 低い (積極的除去) | 低 |
| **Expert Determination** | ✅ (統計的検証) | 高い (選択的除去) | 高 |
| **ハイブリッド** (推奨) | ✅ | 中-高 | 中 |

**推奨**: 初期デプロイでは Safe Harbor から開始（シンプル、コンプライアンス保証）。データ有用性が重要な研究データセットでは Expert Determination に移行。

---

## 制約と制限事項

### アンチパターン（避けるべき設計）

| アンチパターン | なぜ問題か | 正しいアプローチ |
|-------------|----------|--------------|
| FSx for ONTAP S3 AP に直接 Iceberg テーブルを書き込む | conditional writes 未サポートで commit 失敗 | メタデータは S3 Tables に、実データは FSx for ONTAP に分離 |
| 全ファイルを S3 にコピーしてから S3 Metadata を使う | 本アーキテクチャの「S3 コピー排除」の価値を否定 | FPolicy パイプラインでメタデータのみ同期 |
| embedding を DynamoDB に格納する | kNN 検索が非効率、Iceberg エコシステムと分断 | S3 Tables の BINARY カラム or OpenSearch Serverless |
| 全ファイルを AI 処理する（フィルタなし） | コスト爆発（100K ファイル × $0.05 = $5,000/回） | 新規/変更ファイルのみ処理、file_type でフィルタ |
| メタデータテーブルに実データ（バイナリ）を格納 | テーブルサイズ爆発、クエリ性能劣化 | file_path 参照のみ格納、実データは FSx for ONTAP に残す |
| 単一の巨大 Lambda で全処理を実行 | タイムアウト、デバッグ困難、リトライ粒度が粗い | Step Functions で処理を分割、ファイルタイプ別 Lambda |
| ガバナンスなしでメタデータを公開 | 機密ファイルのパスが漏洩 → 実データへの不正アクセス | Lake Formation / Horizon で列/行レベル制御を必ず適用 |

| 制約 | 影響 | 緩和策 |
|------|------|--------|
| FSx for ONTAP S3 AP: conditional writes 未サポート | FSx for ONTAP S3 AP に直接 Iceberg テーブルを書き込めない | メタデータは S3 Tables に格納（FSx for ONTAP ではなく）; 生ファイルは FSx for ONTAP に格納 |
| FSx for ONTAP S3 AP: S3 Event Notifications 未サポート | ネイティブ S3 イベントで変更検知不可 | FPolicy が同等のリアルタイム検知を提供 |
| FSx for ONTAP S3 AP: ListObjectsV2 レイテンシ | 5,000 オブジェクトまではネイティブ S3 比 1.3〜1.4 倍、10,000 件と 20,000 件では 0.7 倍で実用上問題なし。20,000 を超える規模は未測定（[BLK-006](./blocker-tracker.md)） | メタデータテーブルにより LIST 操作自体が不要になり、規模に依存しなくなる |
| Databricks: Session policy が S3 AP をブロック | UC から FSx for ONTAP ファイルに直接アクセス不可 | メタデータは Iceberg REST 経由; ファイルは Bedrock/Lambda 経由 |
| Databricks: SQL Warehouse が S3 Tables 未対応 | `CREATE CONNECTION TYPE iceberg_rest` 未サポート (2026年5月検証) | Spark クラスターで Iceberg REST Catalog 設定、または Athena 経由 |
| Snowflake: TO_FILE が S3 AP で失敗 | Vision AI に内部ステージ回避策が必要 | COPY FILES で内部ステージに転送; PARSE_DOCUMENT は直接動作 |
| Snowflake: S3 Tables 直接読み取り不可 | `CATALOG = 'ICEBERG_REST'` 未サポート (2026年5月検証) | COPY INTO → Managed Iceberg Table; External Volume 作成は成功 |
| S3 Tables: リージョン対応 | 全リージョンで利用可能ではない | Glue Catalog + セルフマネージド Iceberg にフォールバック |

詳細なプラットフォーム × フォーマット × モードの検証状況は [互換性マトリクス](compatibility-matrix.md) を参照。

---

## 関連ドキュメント

| ドキュメント | 関係 |
|------------|------|
| [ゼロコピー非構造化データガバナンス](zero-copy-media-governance.md) | ストレージ最適化オプション (A/B/C/D) — 本ドキュメントはメタデータカタログ層にフォーカス |
| [互換性マトリクス](compatibility-matrix.md) | 各プラットフォーム × フォーマット × モードの詳細検証状況 |
| [ガバナンスとコンプライアンス](governance-and-compliance.md) | Horizon Catalog、Lake Formation、監査ログの詳細 |
| [fsxn-observability-integrations](https://github.com/Yoshiki0705/fsxn-observability-integrations) | FSx for ONTAP 監査ログのモニタリングパイプライン |

---

## 設計のポイントと考慮事項

| 観点 | 推奨事項 | 反映箇所 |
|------|---------|---------|
| **Open Table Format 選定** | S3 Tables をプライマリメタデータストアに採用。Iceberg REST endpoint によりエンジン非依存のアクセスを実現。S3 Metadata を補完パスとして位置づけ。 | アーキテクチャ, 意思決定マトリクス |
| **マルチエンジンアクセス** | Iceberg REST endpoint 経由の External Catalog 構成。各プラットフォームの session policy 制約を文書化し、回避策を明示。 | プラットフォーム別パス, 制約 |
| **外部エンジンガバナンス** | Horizon Catalog / Lake Formation による外部エンジンへのガバナンス適用。Row Access Policy / LF-Tags でプラットフォーム横断の一貫したアクセス制御。 | ガバナンス層, Snowflake パス |
| **ストレージ効率** | ホットメタデータ × コールド実データの分離設計。ONTAP 重複排除の効果を最大化しつつ、メタデータ層は最小コストで運用。 | コアコンセプト, コスト見積もり |
| **イベント駆動設計** | FPolicy パイプラインで既存基盤を活用したリアルタイム検知。DataSync + S3 Metadata をバッチ代替パスとして提供。 | イベント検知, ハイブリッド構成 |
| **規制対応** | PII 検出 + 匿名化パイプライン。データクリーンルームパターン。監査証跡の保持期間を規制別に明示。データ主権（同一リージョン保証）。 | AI エンリッチメント, データ主権 |
| **ビジネス価値の実証** | 段階的導入（Quick Start → フルデプロイ）。成功 KPI の定量化。Go/No-Go 判断基準による投資リスク最小化。 | 成功 KPI, 次のステップ |

---

## 次のステップ

### クイックスタート: 最小構成で価値を実証 (1週間)

> **段階的導入の注記**: 全機能を一度に構築するのではなく、最小構成で「データ発見時間の短縮」を実証し、ステークホルダーの合意を得てから拡張する段階的アプローチを推奨。

**Week 1 の目標**: FSx for ONTAP 上の既存ファイル 1000 件のメタデータを S3 Tables に登録し、Athena で検索可能にする。

```bash
# Step 1: S3 Tables テーブルバケット作成 (5分)
aws s3tables create-table-bucket \
  --name fsxn-metadata-catalog \
  --region ap-northeast-1

# Step 2: 既存ファイルのメタデータ抽出スクリプト実行 (30分)
python scripts/initial-metadata-scan.py \
  --access-point-alias <AP_ALIAS> \
  --table-bucket fsxn-metadata-catalog \
  --max-files 1000

# Step 3: Athena でクエリ確認 (5分)
# "2025年以降に作成された PDF ファイルを全て表示"
SELECT file_name, file_path, created_at, file_size
FROM metadata_catalog.unstructured_files
WHERE file_type = 'application/pdf'
  AND created_at >= TIMESTAMP '2025-01-01'
ORDER BY created_at DESC;
```

**Week 1 の成功基準**: 「特定のファイルを探す」作業が数日→数秒に短縮されることを実証。

### フルデプロイメントロードマップ

1. **Phase 1**: S3 Tables テーブルバケット + Iceberg スキーマのデプロイ (1週間)
2. **Phase 2**: FPolicy → SQS → Lambda メタデータ同期パイプライン構築 (1-2週間)
3. **Phase 3**: AI エンリッチメント Step Functions ワークフロー実装 (2-3週間)
4. **Phase 4**: クロスプラットフォームアクセス設定 (Databricks, Snowflake, EMR) (1-2週間)
5. **Phase 5**: 検索・発見機能構築 (SQL + ベクトル) (1-2週間)
6. **Phase 6**: 匿名化パイプライン実装 (1-2週間)

### 各 Phase の Go/No-Go 判断基準

| Phase | Go 条件 | No-Go 時の対応 |
|-------|---------|--------------|
| Phase 1 → 2 | Athena クエリが 3秒以内に返る | S3 Tables リージョン未対応 → Glue Catalog フォールバック |
| Phase 2 → 3 | FPolicy イベントが 5分以内に S3 Tables に反映 | FPolicy Server 不安定 → DataSync バッチパスに切り替え |
| Phase 3 → 4 | AI 分類の precision > 0.7 | モデル精度不足 → プロンプト調整 or モデル変更 |
| Phase 4 → 5 | 2+ プラットフォームからメタデータクエリ成功 | Session policy 問題 → Lambda API Gateway 経由に変更 |
| Phase 5 → 6 | 類似検索で関連ファイルが top-5 に含まれる | embedding 品質不足 → モデル変更 or チャンク戦略見直し |

詳細な実装計画は [タスク一覧](../../tasks.md) を参照。

