# 決定マトリクス

🌐 [English](../en/06_decision_matrix.md) | **日本語**

---

> 各決定は正式なアーキテクチャ決定記録（ADR）として文書化されている。
> 完全な ADR インデックスは [docs/adr/README.md](../adr/README.md) を参照。

## DEC-001: Delta Lake ストレージターゲット

> 📄 詳細は [ADR-004](../adr/ADR-004.md) — Databricks 統合で S3 アクセスポイントへの直接依存を回避

| オプション | Unity Catalog 互換 | パフォーマンス | コスト | 運用複雑性 | 判定 |
|----------|-------------------|-------------|------|----------|------|
| ネイティブ Amazon S3 | ✅ はい | 高 | 低 | 低 | **選択** |
| FSx for ONTAP (ONTAP S3) | ❌ いいえ | 中 | 中 | 中 | 不採用 |
| FSx for ONTAP (S3 Access Points) | ❌ いいえ (UC 非サポート) | 中 | 中 | 中 | 不採用 |
| MinIO / S3 互換 | ❌ いいえ | 可変 | 可変 | 高 | 不採用 |

**決定:** ネイティブ Amazon S3 が AWS 上の Unity Catalog 外部ロケーションとして唯一サポートされるストレージ。これは確認済みの製品制約であり、設計選択ではない。

**ソース:** REF-020, REF-021, REF-022

---

## DEC-002: Kafka から Databricks への取り込み方法

> 📄 詳細は [ADR-001](../adr/ADR-001.md) — Kafka を工場イベントバックボーンとして使用

| オプション | 正確に1回 | マネージド | スキーマ進化 | Unity Catalog | 成熟度 | 判定 |
|----------|----------|---------|------------|-------------|--------|------|
| Structured Streaming (直接) | ✅ | 部分的（ジョブ管理） | ✅ | ✅ | 高 | **選択（主要）** |
| Confluent Tableflow | ✅ | ✅ | ✅ | ✅ | 中 (2025年10月 GA) | 代替 |
| Confluent Delta Lake Sink Connector | ✅ | ✅ | ✅ | 限定的 | 高 | 代替 |
| Delta Live Tables (DLT) | ✅ | ✅ | ✅ | ✅ | 高 | 代替 |
| カスタムバッチコンシューマー | ❌ (少なくとも1回) | ❌ | 手動 | ✅ | 低 | 不採用 |

**決定:** Databricks Structured Streaming を主要アプローチとして選択（最大の制御、十分な文書、正確に1回）。Confluent Tableflow は Confluent Cloud ユーザー向けの実行可能なマネージド代替。

**ソース:** REF-001, REF-002, REF-003, REF-004, REF-005

---

## DEC-003: リアルタイム分析エンジン

> 📄 詳細は [ADR-002](../adr/ADR-002.md) — ClickHouse をリアルタイム運用分析に使用

| オプション | クエリレイテンシ | Kafka ネイティブ | 製造リファレンス | AWS オプション | 判定 |
|----------|---------------|----------------|---------------|-------------|------|
| ClickHouse | サブ秒 | ✅ (Kafka Engine) | ✅ 複数 | Cloud, BYOC, セルフマネージド | **選択** |
| Amazon OpenSearch | サブ秒 | コネクター経由 | 限定的 | マネージド (Serverless) | 代替 |
| Amazon Timestream | サブ秒 | Lambda/Firehose 経由 | 限定的 | フルマネージド | 代替 |
| Databricks SQL (warehouse) | 秒 | ストリーミング経由 | N/A (レイクハウスと重複) | マネージド | 非該当 |
| Apache Druid | サブ秒 | ✅ | 限定的 | セルフマネージドのみ | 不採用（運用負荷） |

**決定:** サブ秒リアルタイム分析に ClickHouse を選択。強力な製造リファレンスケース（REF-030, REF-032）。ネイティブ Kafka 取り込み。複数の AWS デプロイオプション。

> **DAIS 2026 アップデート（2026-06-16）**: Databricks が **Lakehouse//RT**（Beta、Reyden エンジン）を発表 — UC ガバナンス下の Delta/Iceberg 上で直接ミリ秒リアルタイム分析。PoC の決定は変更なし（Phase A は ClickHouse）。方針は PoC で **ClickHouse と Lakehouse//RT の両方**を試行して比較知見を取得し、Phase B で再評価。詳細は [ADR-002 DAIS 2026 アップデート](../adr/ADR-002.md#dais-2026-update-2026-06-16--dais-2026-アップデート)。

**ソース:** REF-030, REF-031, REF-032, REF-040, REF-041

---

## DEC-004: ClickHouse デプロイモデル（PoC）

| オプション | 運用負荷 | コスト (PoC) | データ所在地 | ネットワーク | 判定 |
|----------|---------|------------|-----------|----------|------|
| ClickHouse Cloud | ゼロ | 中 | ClickHouse 管理 | PrivateLink | **推奨** |
| ClickHouse BYOC | 低 | 中-高 | 利用者の VPC | 同一 VPC | 代替 |
| セルフマネージド (EC2) | 高 | 低 | 利用者の VPC | 同一 VPC | コスト最適化代替 |
| セルフマネージド (EKS) | 高 | 中 | 利用者の VPC | 同一 VPC | PoC 向けではない |

**決定:** PoC には ClickHouse Cloud を推奨（最小運用負荷）。ONTAP S3 階層化テストに VPC ローカルデータアクセスが必要な場合は BYOC またはセルフマネージド EC2。

**ソース:** REF-040, REF-041, REF-044, REF-045

---

## DEC-005: ペイロード向け FSx for ONTAP vs ネイティブ S3

> 📄 詳細は [ADR-003](../adr/ADR-003.md) — FSx for ONTAP を大容量非構造化データのペイロードストレージとして使用
> 📄 [ADR-005](../adr/ADR-005.md) も参照 — 大容量ファイルにメタデータ/ペイロード分離を使用

| 基準 | FSx for ONTAP | ネイティブ Amazon S3 |
|------|--------------|-------------------|
| プロトコル柔軟性 | ✅ NFS + SMB + S3 | ❌ S3 のみ |
| エッジデバイス互換性 | ✅ PLC/SCADA 向け NFS/SMB | ⚠️ S3 SDK が必要 |
| データ保護 | ✅ Snapshot, SnapMirror | ⚠️ バージョニングのみ |
| スペース効率クローン | ✅ FlexClone | ❌ フルコピー必要 |
| マルチプロトコル同時 | ✅ 同一データに複数プロトコル | ❌ S3 のみ |
| コスト | ⚠️ 高め（プロビジョンド） | ✅ 低め（従量課金） |
| 運用複雑性 | ⚠️ 高め（SVM、ボリューム） | ✅ 低め（バケット） |
| ClickHouse コールド階層 | ✅ ONTAP S3 エンドポイント | ✅ ネイティブ S3 |
| Unity Catalog 互換性 | ❌ Delta テーブルには不可 | ✅ 完全サポート |

**決定:** マルチプロトコルアクセスとエンタープライズデータ保護が明確な価値を提供するペイロードストレージに FSx for ONTAP を選択。Delta Lake テーブルにはネイティブ S3 を使用（Unity Catalog の要件）。これは相互補完設計であり、二者択一ではない。

**ソース:** REF-050, REF-051, REF-052, REF-053

---

## DEC-006: Kafka サービス

| オプション | マネージド | コスト (PoC) | IAM 認証 | サーバーレス | 判定 |
|----------|---------|-----------|---------|-----------|------|
| Amazon MSK Provisioned | ✅ | 中 | ✅ | ❌ | **選択** |
| Amazon MSK Serverless | ✅ | 低 | ✅ | ✅ | 代替 |
| Confluent Cloud | ✅ | 中-高 | 異なる | ✅ | Tableflow 必要時 |
| セルフマネージド (EC2) | ❌ | 低 | 手動 | ❌ | PoC 向けではない |

**決定:** PoC には Amazon MSK（Provisioned または Serverless）。ネイティブ AWS 統合、IAM 認証、VPC デプロイ。Tableflow が必要な場合は Confluent Cloud。

---

## DEC-007: ClickHouse から Databricks への統合パターン

| パターン | パフォーマンス | 複雑性 | 結合度 | 判定 |
|---------|-------------|--------|--------|------|
| Kafka（共有）→ 両システム | 高 | 低 | 疎 | **主要（既に設計済み）** |
| Spark コネクター（バッチ読み取り） | 中 | 中 | 中 | 二次（オンデマンド） |
| S3 エクスポート → Databricks | 中 | 低 | 疎 | フォールバック |
| JDBC 直接クエリ | 低 | 低 | 密 | アドホックのみ |

**決定:** 主要統合は間接的（両方が Kafka から消費）。Spark コネクター経由の ClickHouse→Databricks 直接読み取りはバッチ集計プル用の二次/オプションパス。

---

## 最終アーキテクチャ実現可能性評価

### 判定: 修正付きで実現可能

| 基準 | 評価 |
|------|------|
| 技術的実現可能性 | ✅ 全コンポーネントに実績のある統合パスあり |
| Unity Catalog 互換性 | ✅ Delta テーブルにネイティブ S3 を正しく使用 |
| Kafka→Databricks | ✅ 正確に1回の本番実績パターン |
| ClickHouse リアルタイム分析 | ✅ 製造リファレンスあり |
| FSx for ONTAP ペイロードストレージ | ✅ マルチプロトコルエッジアクセスに明確な価値 |
| S3 アクセスポイント回避 | ✅ アーキテクチャは S3 アクセスポイントに依存しない |
| ClickHouse→ONTAP S3 階層化 | ⚠️ PoC 検証が必要 |
| ClickHouse→Databricks コネクター | ⚠️ PoC 検証が必要 |
| 分割ガバナンスモデル | ⚠️ 受容済みトレードオフ、明確な文書化が必要 |

### 元仮説からの必要修正

1. **Delta テーブルはネイティブ S3 上に必須**（ONTAP S3 ではない）— 確認済み制約
2. **ClickHouse→Databricks は二次パス** — 主要取り込みは Kafka→Structured Streaming のまま
3. **FSx for ONTAP の役割はペイロードストレージ** — レイクハウスストレージターゲットではない
4. **ガバナンスは分割** — 構造化データに UC、非構造化ペイロードに ONTAP

### 必要なベンダー確認

1. ClickHouse: ONTAP S3 エンドポイントへの S3 互換階層化（パフォーマンス、安定性）
2. Databricks: 現行 Databricks Runtime との Spark コネクターバージョン互換性
3. AWS: MSK↔Databricks PrivateLink/VPC ピアリング接続性検証

### 最小 PoC 成功基準

1. ✅ イベントがシミュレーター → Kafka → ClickHouse に流れる（サブ秒クエリ動作）
2. ✅ イベントがシミュレーター → Kafka → Databricks Delta テーブルに流れる（正確に1回）
3. ✅ Delta テーブルが Unity Catalog により管理される
4. ✅ ペイロードファイルが FSx for ONTAP 上に存在し Delta テーブルから参照される
5. ✅ シミュレート障害後のパイプライン復旧が動作
6. ⚠️ ClickHouse コールド階層から ONTAP S3 が動作（ストレッチゴール）
