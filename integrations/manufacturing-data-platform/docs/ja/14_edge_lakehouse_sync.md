# 14. Edge-to-Cloud ↔ Lakehouse プロジェクト同期

**同期日**: 2026-06-15
**Edge リポジトリ**: [ONTAP-Edge-to-Cloud-AI](https://github.com/Yoshiki0705/ONTAP-Edge-to-Cloud-AI)
**Lakehouse リポジトリ**: [FSx-for-ONTAP-Lakehouse-Integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations)

---

## 1. 同期対象の設計決定

Edge-to-Cloud プロジェクトで確定した以下の設計を Lakehouse 側に反映済み。

### 1.1 統一イベントスキーマ v2.0.0

Edge デバイスから Kafka に publish される共通エンベロープ。両プロジェクトでこのスキーマを正とする。

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| event_id | UUID v4 | ✅ | イベント一意識別子 |
| event_type | string | ✅ | payload_arrival, sensor_event, quality_event, anomaly_event, telemetry_event |
| domain | string | - | 固定: manufacturing |
| event_category | string | - | quality_inspection, environmental_monitoring, equipment_telemetry, storage_health |
| source_id | string | ✅ | Edge デバイス ID (例: rpi5-001) |
| asset_type | string | - | 3d_printer, storage_system, sensor_array |
| asset_id | string | - | 個別アセット ID |
| site_id | string | ✅ | サイト ID (例: lab-tokyo) |
| line_id | string | - | ライン ID |
| equipment_id | string | - | 設備 ID |
| sensor_id | string | - | センサー ID |
| timestamp | ISO 8601 | ✅ | イベント発生時刻 |
| ingest_time | ISO 8601 | - | Kafka publish 時刻 |
| schema_version | string | - | 固定: 2.0.0 |
| payload_uri | string | - | nfs://svm/vol/path (or null) |
| payload_type | string | - | image, csv, json, null |
| content_type | string | - | MIME type |
| checksum | string | - | sha256:\<hex\> |
| size_bytes | int | - | ペイロードサイズ |
| lineage_id | string | - | セッション/バッチ追跡 ID |
| processing_status | string | - | pending_analysis, completed, failed |
| metadata | object | - | event_type 固有のメタデータ |

### 1.2 Kafka Topic 設計

| Topic | Partition Key | 用途 |
|-------|--------------|------|
| factory.events.raw | site_id-equipment_id | 全イベント (primary) |
| factory.events.quality | site_id-equipment_id | AI 分析結果 |
| factory.events.anomaly | site_id-equipment_id | 異常検知 |
| factory.events.dlq | - | Dead Letter Queue |

**注意**: v1 の個別 topic 設計 (`factory.sensor-data`, `factory.quality-events`, `factory.system-alerts`) から統一 topic + event_type routing に変更。

### 1.3 ClickHouse テーブル設計 (Edge 側 DDL が正)

| テーブル | エンジン | TTL | 役割 |
|---------|---------|-----|------|
| kafka_events_raw | MergeTree | 30d | 全イベント raw 保存 |
| quality_events | ReplacingMergeTree | 365d | AI 分析結果 |
| payload_manifest | MergeTree | 365d | ONTAP ↔ イベント橋渡し |
| sensor_events_rollup_1m | AggregatingMergeTree | 90d | 1分集約メトリクス |
| anomaly_events | MergeTree | 365d | 異常検知結果 |
| dead_letter_events | MergeTree | 30d | 処理失敗イベント |
| training_features_export | MergeTree | なし | Databricks export 用 |

Kafka Table Engine + Materialized View 5本で自動 routing。

### 1.4 Databricks 連携パス

| パス | データ種別 | 方式 | Lakehouse 側実装 |
|------|-----------|------|-----------------|
| A | Kafka イベント → Bronze | Spark Structured Streaming (DLT) | `04_kafka_to_bronze_dlt.py` |
| B | ClickHouse 集計特徴量 → Silver/Gold | Parquet Export → ONTAP S3 → DataSync → S3 → UC | `05_training_features_import.py` |
| C | ONTAP NFS 生画像/CSV → Bronze | DataSync → S3 → Auto Loader | (planned) |

### 1.5 Unity Catalog 設計

```
manufacturing_poc (catalog)
├── bronze
│   ├── kafka_events           ← Path A: Kafka Structured Streaming
│   ├── sensor_events          ← kafka_events から extract
│   ├── quality_events         ← kafka_events から extract
│   ├── payload_manifest       ← payload_arrival イベントから生成
│   └── raw_images             ← Path C: Auto Loader
├── silver
│   ├── training_features      ← Path B: ClickHouse export import
│   ├── quality_trends         ← bronze.quality_events から集計
│   └── equipment_health       ← bronze.sensor_events + anomaly から導出
├── gold
│   ├── training_dataset       ← ML 学習用データセット
│   ├── quality_summary        ← ダッシュボード用集計
│   └── predictive_maintenance ← 予測保全結果
└── ml
    └── print_features         ← Feature Store 登録テーブル
```

---

## 2. v1 → v2 差異サマリー

| 項目 | v1 (旧 Lakehouse) | v2 (Edge aligned) |
|------|-------------------|-------------------|
| Kafka topics | 個別 (sensor-data, quality-events, system-alerts) | 統一 (events.raw) + category topics |
| ClickHouse DB | factory | factory_v3 |
| UC schemas | factory_alpha / factory_beta (per-site) | bronze / silver / gold / ml (medallion) |
| Event schema | Flat, per-type | 統一エンベロープ v2.0.0 |
| Payload linkage | payload_reference (String) | payload_manifest テーブル |
| Feature export | なし | training_features_export + import pipeline |
| DLT | なし | 04_kafka_to_bronze_dlt.py |

---

## 3. 同期確認事項と対応状況

### ✅ 確認 1: ClickHouse テーブル設計の差異

**結果**: Edge 側 DDL を正として Lakehouse 側に `02_edge_aligned_tables.sql` を作成済み。v1 の `01_setup_tables.sql` は参考として残すが、新規デプロイは v2 DDL を使用する。

**差異の詳細**:
- Edge 側は `factory_v3` DB、Lakehouse v1 は `factory` DB
- テーブル構造は Edge 側の方が完全（payload_manifest, anomaly_events, training_features_export が追加）
- Kafka consumer group 名は環境固有のため、Edge/Lakehouse で別名を使用

### ✅ 確認 2: Kafka → Databricks Structured Streaming

**結果**: `04_kafka_to_bronze_dlt.py` を作成。DLT pipeline として deploy 可能。

**設計判断**:
- DLT を選択（vs raw Structured Streaming）: 宣言的パイプライン、data quality expectations、自動 checkpoint 管理
- `availableNow=True` trigger: 初期テストに最適、本番は `continuous` に切り替え可能

### ✅ 確認 3: training_features_export の自動化

**結果**: 
- Edge 側: `export_training_features.sh` で ClickHouse → Parquet Export を実装済み
- Lakehouse 側: `05_training_features_import.py` で S3 → Delta Lake import を実装済み

**エクスポート自動化の設計**:
```
[ClickHouse] export_training_features.sh (Edge 側)
    ↓ INSERT INTO training_features_export SELECT ...
    ↓ → Parquet via s3() table function
[ONTAP S3] Parquet ファイルとして export
    ↓
[AWS DataSync] ONTAP S3 → S3 バケット (定期タスク)
    ↓
[Databricks] Auto Loader (05_training_features_import.py, Lakehouse 側)
    ↓
[Unity Catalog] manufacturing_poc.silver.training_features
```

### ✅ 確認 4: Unity Catalog の共有前提

**結論**: `manufacturing_poc` カタログは両プロジェクトで共有。

**運用ルール**:
- カタログ名: `manufacturing_poc` (固定)
- 同一 Databricks workspace を使用
- Edge 側が bronze テーブルへ書き込む Kafka consumer を管理
- Lakehouse 側が silver/gold/ml テーブルの ETL を管理
- 変更は本ドキュメントを更新して通知

### 🔲 確認 5: 共通テストデータ

**状態**: Edge 側準備完了、Lakehouse 側取り込み待ち

**Edge 側**: `tests/sample_events/` に 21 件のサンプルイベント JSON を作成済み
**Lakehouse 側**: `poc/shared-test-data/samples/` に取り込み予定

**取り込み手順**:
```bash
EDGE_REPO="../ONTAP-Edge-to-Cloud-AI"
cp ${EDGE_REPO}/tests/sample_events/*.json \
   integrations/manufacturing-data-platform/poc/shared-test-data/samples/
```

**ブロッカー**: Edge リポジトリへのローカルアクセス（clone 済みであれば即実行可能）

---

## 4. ファイルマッピング

### Edge → Lakehouse 対応表

| Edge 側パス | Lakehouse 側パス | 同期方式 |
|------------|-----------------|---------|
| `cloud/clickhouse/ddl/` | `poc/clickhouse/02_edge_aligned_tables.sql` | 手動同期 (Edge が正) |
| `docs/*/databricks-integration.md` | `docs/ja/14_edge_lakehouse_sync.md` | 本ドキュメント |
| `docs/*/data-schema-design.md` | `poc/databricks/03_unity_catalog_v2.sql` | UC DDL として反映 |
| `synthetic_events.py` | `poc/shared-test-data/` | TBD (共有方式検討中) |

> **双方向ナビゲーション（両リポジトリの `main` で解決可能）**: Edge 側の `docs/{ja,en}/databricks-integration.md` から本ドキュメントへのバックリンクが追加され、本リポジトリからは root README と manufacturing-data-platform README の両方から Edge プロジェクトへリンク済み。上表の `databricks-integration.md` ↔ `14_edge_lakehouse_sync.md` マッピングは GitHub 上で双方向に解決する。

### Lakehouse 固有ファイル

| パス | 説明 |
|------|------|
| `poc/databricks/04_kafka_to_bronze_dlt.py` | Path A: DLT pipeline |
| `poc/databricks/05_training_features_import.py` | Path B: Feature import |
| `poc/clickhouse/01_setup_tables.sql` | v1 DDL (参考用、非推奨) |
| `poc/databricks/01_setup_catalog.sql` | v1 UC (参考用、非推奨) |
| `poc/databricks/02_streaming_pipeline.py` | v1 streaming (参考用) |

---

## 5. 責任分担表

**確定日**: 2026-06-16 (Edge 側確認済み)

| 責任 | Edge プロジェクト | Lakehouse プロジェクト |
|------|------------------|----------------------|
| イベント生成 (Pi → Kafka) | ✅ `simple_capture.py` + `event_schema.py` | — |
| Kafka Topic 設計 | ✅ 確定 (factory.events.raw 等) | ✅ 同期済み |
| ClickHouse DDL | ✅ `cloud/clickhouse/ddl/` (正) | ✅ ミラー (`02_edge_aligned_tables.sql`) |
| ClickHouse → Parquet Export | ✅ `export_training_features.sh` | ✅ Import (`05_training_features_import.py`) |
| Databricks DLT | ✅ 設計ドキュメント | ✅ 実装 (`04_kafka_to_bronze_dlt.py`) |
| Unity Catalog 設計 | ✅ 設計ドキュメント | ✅ DDL (`03_unity_catalog_v2.sql`) |
| 合成テストデータ | ✅ `synthetic_events.py` | ✅ 共有予定 (`poc/shared-test-data/`) |

---

## 6. 残タスク

**ソフトウェア・設計・スキーマ整合・クロスプロジェクト同期はすべて完了** (2026-06-16)。
残るのは物理環境準備とデータ到着後の実行のみ。

| # | タスク | 担当 | トリガー | 状態 |
|---|--------|------|---------|------|
| 1 | テストデータ取り込み | Lakehouse | clone 後即実行可 | 実行可 |
| 2 | DataSync 設定 | Lakehouse | ONTAP S3 バケット作成後 | 待機 |
| 3 | M1-M6 計測 (06/07 実行) | Lakehouse | Bronze データ到着後 | 待機 |
| 4 | Instaclustr デプロイ | Edge (物理) | PoC ドキュメント承認後 | 待機 |
| 5 | Phase 1 (Pi → ONTAP) | Edge (物理) | 物理セットアップ完了後 | 待機 |

---

## 7. Edge プロジェクトから引き継いだ改善

**反映日**: 2026-06-16

Edge 側で[設計論点チェックリスト](08_design_concern_checklist.md)に対する
設計見直しを実施。以下を Lakehouse 側に反映済み。

### 7.1 ClickHouse ミラー DDL (`02_edge_aligned_tables.sql`)

| 改善項目 | 反映内容 |
|---------|---------|
| quality_events MV 型修正 | `anomalies` はオブジェクト配列。`arrayMap(x -> JSONExtractString(x, 'type'), JSONExtractArrayRaw(...))` で type のみ抽出する `anomaly_types Array(LowCardinality(String))` カラムを追加。直接代入の型不一致バグを回避 |
| Kafka エラーハンドリング | 全 Kafka Engine に `kafka_handle_error_mode = 'stream'` を設定。`mv_kafka_errors` MV を追加し、`length(_error) > 0` のメッセージを `dead_letter_events` に routing。正常メッセージは全 MV で `WHERE length(_error) = 0` |
| feedback_events テーブル | セクション11に追加。`ReplacingMergeTree(ingest_time)`、`ORDER BY (target_event_id)`。`mv_raw_to_feedback` MV で `event_type='feedback_event'` を抽出。`is_synthetic` フラグ保持 |
| training_features_export | `human_label` / `label_confidence` / `labeled_by` / `labeled_at` カラムを追加 |

### 7.2 Databricks 連携

| ファイル | 反映内容 |
|---------|---------|
| `03_unity_catalog_v2.sql` | `bronze.feedback_events` テーブル追加。`silver.training_features` に human_label 系4カラム追加 |
| `04_kafka_to_bronze_dlt.py` | `feedback_event → bronze.feedback_events` の DLT ルート追加。`is_synthetic` フラグ保持 |
| `05_training_features_import.py` | import スキーマに human_label 系4カラム追加 |
| `06_gold_training_dataset.py` | **新規**。human_label を JOIN して教師ラベル付き Gold データセット生成。ラベル優先度: human > AI > unknown。決定論的 train/validation/test split |
| `07_success_metrics_gold.sql` | **新規**。M1-M6 の Go/No-Go 計測クエリを Databricks Gold ダッシュボード用に実装。M2 (accuracy/precision/recall) は feedback_events JOIN で算出 |

### 7.3 フィードバックループ (両プロジェクト完結)

```
operator
  → feedback_recorder Lambda (KAFKA_REST_PROXY_URL 経由で publish)
  → Kafka (factory.events.raw, event_type=feedback_event)
  → ClickHouse feedback_events (mv_raw_to_feedback)
  → training_features_export (human_label)         [Path B → Lakehouse]
  → Databricks bronze.feedback_events (DLT)         [Path A → Lakehouse]
  → Databricks gold.training_dataset (human label JOIN)
```

**注意 (Edge 設計)**: Lambda はオンプレ Kafka に直接接続できないため REST Proxy 経由。REST Proxy 未設定時は S3 のみ保存し、ClickHouse が S3 からバッチインポート。

### 7.4 ガバナンス

- 合成テストデータには `_synthetic: true` フラグを付与（[設計論点チェックリスト](08_design_concern_checklist.md)の要件）
- `_synthetic` フラグはイベントエンベロープの **top-level** に存在。ClickHouse は `JSONExtractBool(raw, '_synthetic')` で参照し、Databricks DLT はエンベロープスキーマの top-level フィールドとして取り込み（欠落時は `false`）、`bronze.kafka_events.is_synthetic` → `bronze.feedback_events.is_synthetic` へ伝播。両経路で一貫。
- ClickHouse / Bronze の `feedback_events.is_synthetic` で本番精度メトリクスから合成データを除外可能

---

## 8. 変更履歴

| 日付 | 変更内容 |
|------|---------|
| 2026-06-15 | 初版作成。Edge v3 設計を Lakehouse 側に反映。 |
| 2026-06-16 | Edge 側同期確認メッセージを受領。責任分担表を追加。export_training_features.sh 反映。 |
| 2026-06-16 | Edge 側最終同期完了。全項目一致確認。テストデータ 21件の取り込み手順を追記。 |
| 2026-06-16 | Edge プロジェクトから引き継いだ改善の反映: feedback_events, human_label, Kafka エラーハンドリング, quality_events 型修正, Gold training_dataset 生成, M1-M6 成功指標 (セクション7参照)。 |
| 2026-06-16 | フォローアップ: `_synthetic` ガバナンスフラグを top-level エンベロープ基準に統一（ClickHouse / Databricks DLT 両対応、bronze.kafka_events.is_synthetic）。 |
| 2026-06-16 | Edge ↔ Lakehouse の双方向ナビゲーションが両リポジトリの main で解決可能になった旨を追記（databricks-integration.md バックリンク）。 |
