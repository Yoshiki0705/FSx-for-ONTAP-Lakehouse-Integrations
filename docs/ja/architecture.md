# アーキテクチャ概要

## Amazon FSx for NetApp ONTAP（FSx for ONTAP）× S3 Access Points × Lakehouse 統合アーキテクチャ

### 全体構成図

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AWS Account                                 │
│                                                                     │
│  ┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐  │
│  │  Lakehouse   │     │  S3 Access Point │     │  FSx for ONTAP  │  │
│  │  Platform    │────▶│  (VPC-scoped)    │────▶│  Volume (S3)    │  │
│  │              │◀────│                  │◀────│                 │  │
│  └──────────────┘     └──────────────────┘     └─────────────────┘  │
│        │                       │                        │           │
│        │                       │                        │           │
│  ┌─────▼──────┐         ┌──────▼─────┐          ┌───────▼─────┐     │
│  │ Unity Cat. │         │ S3 AP      │          │ ONTAP       │     │
│  │ Ext Stage  │         │ Policy     │          │ Features    │     │
│  │ Ext Table  │         │ (IAM+VPC)  │          │ Dedup/Snap  │     │
│  └────────────┘         └────────────┘          └─────────────┘     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### コンポーネント説明

#### 1. FSx for ONTAP

エンタープライズストレージレイヤーとして機能します。

| 機能 | Lakehouse での活用 |
|------|-------------------|
| S3 プロトコル | Lakehouse プラットフォームからの直接アクセス |
| 重複排除 | 類似データセット（dev/staging/prod）のストレージ削減 |
| 圧縮 | インライン圧縮によるコスト最適化 |
| Snapshot | テーブルのポイントインタイムリカバリ |
| FlexClone | 開発環境用データセットの瞬時クローン |
| FabricPool | コールドパーティションの自動 S3 階層化 |
| SnapMirror | クロスリージョン DR |

#### 2. S3 Access Points

FSx for ONTAP と Lakehouse プラットフォーム間の接続レイヤーです。

**主な役割:**
- VPC 制限によるネットワークレベルのアクセス制御
- IAM ポリシーによるきめ細かい権限管理
- プラットフォーム別のアクセスポイント分離
- パス制限（prefix）によるデータ分離

**S3 API 対応状況:**

| API | 対応 | 備考 |
|-----|------|------|
| GetObject | ✅ | 読み取りクエリ |
| PutObject | ✅ | テーブル書き込み |
| DeleteObject | ✅ | テーブルメンテナンス |
| ListObjectsV2 | ✅ | テーブルディスカバリ |
| HeadObject | ✅ | メタデータ確認 |
| CreateMultipartUpload | ✅ | 大規模ファイル書き込み |
| GetBucketLocation | ⚠️ | 一部プラットフォームで必要 |

#### 3. Lakehouse プラットフォーム

各プラットフォームが S3 API 経由で FSx for ONTAP にアクセスします。

---

## アーキテクチャパターン詳細

### パターン A: 読み取り専用（分析クエリ）

```
┌────────────┐    S3 GetObject     ┌─────────┐    NFS/S3   ┌──────────────┐
│ Databricks │──────────────────  ▶│  S3 AP  │────────────▶│FSx for ONTAP │
│ Athena     │    ListObjectsV2    │ (read)  │             │   Volume     │
│ Snowflake  │◀──────────────────  │         │◀────────────│              │
└────────────┘                     └─────────┘             └──────────────┘
```

**ユースケース:**
- 既存 NFS/SMB データの分析クエリ
- ETL 不要のデータ探索
- アドホック分析

**ONTAP の価値:**
- 既存データをコピーせずにクエリ可能
- Snapshot で分析時点のデータを固定

### パターン B: 読み書き（マネージドテーブル）

```
┌────────────┐  Get/Put/Delete   ┌─────────┐             ┌──────────────┐
│ Databricks │◀────────────────▶ │  S3 AP  │◀──────────▶ │FSx for ONTAP │
│ (Delta)    │  Multipart Upload │ (r/w)   │             │   Volume     │
│ Snowflake  │                   │         │             │              │
│ (Iceberg)  │                   └─────────┘             └──────────────┘
└────────────┘
```

**ユースケース:**
- Delta Lake / Iceberg テーブルのストレージ
- ACID トランザクション対応テーブル
- Time Travel + ONTAP Snapshot の組み合わせ

**ONTAP の価値:**
- 重複排除で Delta/Iceberg のバージョンファイル効率化
- Snapshot でテーブル全体のリカバリ
- FlexClone で開発用テーブルコピー

### パターン C: ETL パイプライン（メダリオンアーキテクチャ）

```
┌──────────────┐  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌──────────────┐
│    Source    │─▶│  S3 AP  │─▶│  Glue/   │─▶│  S3 AP  │─▶│ FSx for ONTAP│
│    (Raw)     │  │  (read) │  │  EMR/    │  │  (write)│  │    (Gold)    │
│FSx for ONTAP │  │         │  │  Lambda  │  │         │  │    Volume    │
└──────────────┘  └─────────┘  └──────────┘  └─────────┘  └──────────────┘
     Raw             Bronze         Transform      Silver/Gold      Curated
```

**ユースケース:**
- メダリオンアーキテクチャ（Raw → Bronze → Silver → Gold）
- データ品質チェック + 変換パイプライン
- スケジュール実行 ETL

**ONTAP の価値:**
- 各レイヤーを別ボリュームで管理
- レイヤー間の Snapshot 整合性
- FabricPool で Bronze レイヤーを自動階層化

### パターン D: データ共有

```
┌──────────────┐  ┌─────────────┐    ┌────────────┐
│FSx for ONTAP │─▶│  S3 AP (A)  │──▶ │ Consumer A │ (Databricks)
│    Volume    │  │  prefix=/a/ │    └────────────┘
│  (Producer)  │  └─────────────┘
│              │  ┌─────────────┐    ┌────────────┐
│              │─▶│  S3 AP (B)  │──▶ │ Consumer B │ (Snowflake)
│              │  │  prefix=/b/ │    └────────────┘
└──────────────┘  └─────────────┘
```

**ユースケース:**
- データメッシュのデータプロダクト公開
- マルチテナントデータ共有
- パートナー企業へのデータ提供

**ONTAP の価値:**
- FlexClone でコンシューマー別の論理コピー
- S3 AP ポリシーでアクセス制御
- SnapMirror でクロスリージョン共有

---

## ネットワーク構成

### VPC 内アクセス（推奨）

```
┌──────────────────────────────────────────────────────┐
│                       VPC                            │
│                                                      │
│  ┌──────────┐    ┌──────────────┐    ┌────────┐      │
│  │ Platform │──▶ │ VPC Endpoint │──▶ │ S3 AP  │      │
│  │ (Private │    │ (Interface)  │    │        │      │
│  │  Subnet) │    │ com.aws.s3   │    │        │      │
│  └──────────┘    └──────────────┘    └───┬────┘      │
│                                          │           │
│                                  ┌───────▼────────┐  │
│                                  │ FSx for ONTAP  │  │
│                                  │ (Private       │  │
│                                  │  Subnet)       │  │
│                                  └────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### セキュリティレイヤー

多層防御は次の 5 層で構成します。

| レイヤー | 役割 |
|---|---|
| VPC Endpoint Policy | VPC 内からのみアクセス許可 |
| S3 Access Points Policy | IAM Principal + VPC 条件 |
| IAM Role Policy | 最小権限の原則 |
| ONTAP Export Policy | ボリュームレベルのアクセス制御 |
| Security Group | ネットワークレベルのフィルタリング |

---

## データフォーマット対応

> 以下のテーブルは S3 API レベルでのフォーマット対応を示しています。FSx for ONTAP S3 Access Points では、トランザクショナルフォーマット（Delta Lake、Apache Hudi）の書き込み操作はアトミック rename と条件付き書き込みの欠如により非サポートです。検証済みのプラットフォーム × フォーマット × モードの組み合わせは[互換性マトリクス](compatibility-matrix.md)を参照してください。

| フォーマット | 読み取り | 書き込み | 主な用途 | FSx for ONTAP S3 AP 書き込み |
|-------------|---------|---------|---------|:------------------:|
| Parquet | ✅ | ✅ | 分析クエリ（列指向） | ✅ Append |
| Apache Iceberg | ✅ | ⚠️ | ACID テーブル（ベンダー中立） | 実験的（外部カタログ） |
| Delta Lake | ✅ | 非対応 | ACID テーブル（Databricks） | 非サポート（アトミック rename なし） |
| Apache Hudi | ✅ | 非対応 | CDC + Upsert | 非サポート（アトミック rename なし） |
| CSV | ✅ | ✅ | レガシーデータ取り込み | ✅ Append |
| JSON / NDJSON | ✅ | ✅ | セミ構造化データ | ✅ Append |
| ORC | ✅ | ✅ | Hive 互換 | ✅ Append |
| Avro | ✅ | ✅ | スキーマ進化 | ✅ Append |

---

## 次のステップ

- [クイックスタート](getting-started.md) — 最初のデプロイ
- S3 AP の基礎 — S3 Access Points × FSx for ONTAP の詳細
- [ベンダー比較](vendor-comparison.md) — プラットフォーム選定ガイド
- データフォーマット — フォーマット別の推奨構成
