# ゼロコピー メディアガバナンス: FSx for ONTAP + Databricks UC による S3 重複排除

🌐 日本語 | [English](../en/zero-copy-media-governance.md)

## 顧客課題

| # | 課題 | 根本原因 |
|---|------|---------|
| 1 | S3 保管コストが増え続けている。重複データを可能な限り持ちたくない | 汎用ファイルサーバー → DataSync（ファイル差分）→ S3 フルコピーで冗長ストレージが発生 |
| 2 | Databricks 上で画像/動画データをタグで権限制御しながら組織を跨いで活用したい | S3 にフラットにコピーされているだけでガバナンスなし。Databricks 利用は決定事項 |

### 現状アーキテクチャ（問題状態）

```
オンプレ汎用ファイルサーバー（NAS/Windows）
  ↓ DataSync（ファイル差分 — 1バイト変更でもファイル全体を再転送）
Amazon S3（フルコピー、重複排除なし）
  ↓
Databricks UC / その他サービス

問題点:
- ファイルサーバーにも S3 にもインライン重複排除機能がない
- DataSync ファイル差分: 1バイト変更 → ファイル全体を再転送
- S3 コストがデータ量に比例して増大
- メディア資産にガバナンスなし
```

---

## ソリューション選択肢

### Option A: S3 最適化のみ（最小変更）

```
汎用ファイルサーバー（変更なし）
  ↓ DataSync（ファイル差分）
S3 bucket
  ├── S3 Intelligent-Tiering（自動階層化）
  ├── S3 Lifecycle Policy（古いバージョン削除）
  └── UC External Volume（ガバナンス）
```

| メリット | デメリット |
|---------|----------|
| インフラ変更なし | 重複排除不可能 |
| 即座に実装可能 | DataSync 帯域非効率は残存 |
| | ストレージコスト削減は限定的（階層化のみ） |

**コスト削減**: 20-40%（階層化のみ、重複排除なし）

---

### Option B: FSx for ONTAP 移行（推奨）

**S3 コピーを FSx for ONTAP に置き換え、インライン重複排除で唯一のクラウドコピーとする。**

```
汎用ファイルサーバー
  ↓ DataSync（一回限りのマイグレーション）
FSx for ONTAP（唯一のクラウドコピー）
  │ ← インライン重複排除 + 圧縮（自動）
  │ ← Snapshot（ポイントインタイムリカバリ）
  │ ← FabricPool（コールドデータを S3 に自動階層化 $0.0125/GB）
  │
  ↓ S3 Access Point（用途別に複数 AP）
  ├── AP-1: Databricks（Instance Profile + boto3）
  ├── AP-2: Bedrock Knowledge Base
  └── AP-3: その他サービス

S3 フルコピー = 廃止
DataSync 継続同期 = 廃止（または新規ファイルのみ最小限）
```

**コスト比較（10TB メディア資産）**:

| 項目 | 現状（汎用FS + S3） | Option B（FSx for ONTAP） |
|------|-------------------|--------------------------|
| オンプレストレージ | 汎用FS: 10TB | 廃止（クラウド移行） |
| S3 ストレージ | 10TB × $0.023/GB = **$230/月** | $0（S3 コピー不要） |
| FSx for ONTAP | — | 10TB → 5TB（dedup）× $0.08/GB = **$400/月** |
| FabricPool（コールド 80%） | — | 4TB → S3 IA = **$50/月** |
| DataSync 転送 | 月次差分転送コスト | 廃止 |
| **合計ストレージ** | $230 + オンプレ運用費 | **$450/月**（オンプレ運用費ゼロ） |

**実効果**: オンプレ運用費（ハードウェア保守、電力、ラック、人件費）を含めると、FSx for ONTAP の方が TCO で有利になるケースが多い。

**ONTAP 重複排除効果**:

| データタイプ | 典型的な重複排除率 | 10TB → 実効容量 |
|------------|-----------------|----------------|
| 画像（類似画像多数） | 20-40% | 6-8TB |
| 動画（重複少） | 5-15% | 8.5-9.5TB |
| ドキュメント（バージョン違い多数） | 40-70% | 3-6TB |
| 混合ワークロード | 30-50% | 5-7TB |

---

### Option C: オンプレ ONTAP + SnapMirror（ハイブリッド）

**汎用ファイルサーバーをオンプレ ONTAP に置き換え、SnapMirror でブロックレベル同期。**

```
オンプレ ONTAP（汎用FS から置き換え）
  │ ← インライン重複排除 + 圧縮
  │ ← Snapshot
  │
  ↓ SnapMirror（ブロックレベル差分 = 帯域効率最高）
FSx for ONTAP（クラウドレプリカ）
  ↓ S3 Access Point
  ├── Databricks
  └── その他サービス

DataSync（ファイル差分）= 廃止
S3 フルコピー = 廃止
```

**DataSync vs SnapMirror 帯域効率**:

| 観点 | DataSync（ファイル差分） | SnapMirror（ブロック差分） |
|------|----------------------|------------------------|
| 差分検出 | ファイルのタイムスタンプ/サイズ比較 | ブロックレベルの変更追跡 |
| 10GB ファイルの1バイト変更 | **10GB 再転送** | **4KB 転送** |
| 帯域効率 | 低 | **2,500倍効率的** |
| ネットワーク圧縮 | なし | 組み込み |
| 暗号化 | TLS | TLS + SnapMirror 暗号化 |

---

### Option D: FlexCache S3 Access Points（将来ロードマップ）

> **ステータス**: FlexCache S3 Access Points のサポートがまもなく利用可能になる見込み。将来のアーキテクチャとして提案。

**FlexCache により、オンプレ ONTAP が FSx for ONTAP データの読み取りキャッシュとして機能し、S3 AP が分析アクセスレイヤーを提供。**

```
オンプレ ONTAP（正本）
  ↓ SnapMirror
FSx for ONTAP（クラウドレプリカ）
  ↓ FlexCache S3 Access Point（新機能 — まもなく提供予定）
  │
  │ FlexCache が提供する価値:
  │ - ホットデータのエッジ/オンプレでの読み取りキャッシュ
  │ - フルレプリケーションなしでキャッシュデータへの S3 AP アクセス
  │ - WAN 帯域削減（キャッシュミスのみ WAN を通過）
  │
  ↓ S3 Access Point（FlexCache ボリューム上）
  ├── Databricks（ホットデータへの低レイテンシーアクセス）
  ├── Bedrock KB
  └── その他サービス

現行アーキテクチャに対する利点:
- ホットデータがローカルキャッシュ → サブミリ秒の読み取りレイテンシー
- コールドデータはオンデマンドフェッチ → フルレプリケーション不要
- FlexCache 上の S3 AP → 分析エンジンがキャッシュデータに直接アクセス
- キャッシュとオリジン間で重複排除が維持
```

**FlexCache S3 AP vs フルレプリケーション**:

| 観点 | フルレプリケーション（SnapMirror） | FlexCache S3 AP |
|------|-------------------------------|-----------------|
| 必要ストレージ | 宛先にフルコピー | キャッシュサイズのみ（オリジンの 10-30%） |
| 初期同期時間 | 数時間〜数日（全データセット） | 数分（アクセス時にキャッシュウォーム） |
| 帯域 | ブロックレベル差分（効率的） | オンデマンドフェッチ（最も効率的） |
| 読み取りレイテンシー（ホット） | ローカルディスク速度 | ローカルディスク速度（キャッシュ済み） |
| 読み取りレイテンシー（コールド） | ローカルディスク速度 | WAN RTT（キャッシュミス） |
| 書き込みサポート | フル読み書き | 読み取り専用（オリジンへのライトバック） |
| S3 AP アクセス | ✅（FSx ボリューム上） | ✅（FlexCache ボリューム上 — まもなく提供） |
| コスト | 両サイトにフルストレージ | キャッシュストレージのみ |

**FlexCache S3 AP アーキテクチャ**:

```
┌─────────────────────────────────────────────────────────────┐
│  オンプレミス                                                 │
│  ┌──────────────────┐                                       │
│  │ ONTAP（ソース）    │                                       │
│  │ 10TB メディア資産  │                                       │
│  │ Dedup: 5TB 実効   │                                       │
│  └────────┬─────────┘                                       │
│           │ SnapMirror（ブロック差分）                         │
└───────────┼─────────────────────────────────────────────────┘
            │ Direct Connect / VPN
┌───────────┼─────────────────────────────────────────────────┐
│  AWS      ▼                                                 │
│  ┌──────────────────┐     ┌──────────────────────┐          │
│  │ FSx for ONTAP    │     │ FlexCache Volume     │          │
│  │（フルレプリカ）     │────▶│（2TB キャッシュ）      │          │
│  │ 5TB（dedup）      │     │ S3 AP 有効           │          │
│  └──────────────────┘     └──────────┬───────────┘          │
│                                      │                      │
│                           ┌──────────▼───────────┐          │
│                           │ S3 Access Point      │          │
│                           │（FlexCache 上）       │          │
│                           └──────────┬───────────┘          │
│                                      │                      │
│                    ┌─────────────────┼─────────────────┐    │
│                    │                 │                 │    │
│              ┌─────▼──────┐   ┌──────▼──────┐  ┌──────▼──┐  │
│              │ Databricks │   │ Bedrock KB  │  │ Athena  │  │
│              │ UC Volume  │   │             │  │         │  │
│              └────────────┘   └─────────────┘  └─────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**コスト試算（FlexCache S3 AP）**:

| 項目 | フルレプリケーション | FlexCache S3 AP |
|------|-----------------|-----------------|
| FSx ストレージ | 5TB × $0.08 = $400/月 | 2TB キャッシュ × $0.08 = $160/月 |
| FabricPool | $50/月 | $20/月 |
| **合計** | **$450/月** | **$180/月** |
| **現行 S3 コピーとの比較削減率** | 50% | **80%** |

---

## Databricks パス

**背景**: 既存の Databricks 資産(UC、Delta Lake、MLflow パイプライン、チームスキル)を活用。

### UC Volume + メタデータテーブル + タグベースアクセス制御 + OpenSharing

```sql
-- 1. External Volume（S3 または FSx for ONTAP S3 AP 経由の DataSync サブセットをバックエンド）
CREATE EXTERNAL VOLUME media_assets
  LOCATION 's3://company-media-bucket/assets/';

-- 2. メタデータカタログテーブル
CREATE TABLE media_catalog (
  asset_id STRING GENERATED ALWAYS AS IDENTITY,
  volume_path STRING,
  media_type STRING,            -- 'image/jpeg', 'video/mp4'
  department STRING,
  project STRING,
  classification STRING,        -- 'public', 'internal', 'confidential'
  tags MAP<STRING, STRING>,
  file_size_bytes BIGINT,
  checksum STRING,              -- 重複検出用
  source_path STRING,
  synced_at TIMESTAMP
);

-- 3. UC Tags
ALTER TABLE media_catalog SET TAGS ('data_domain' = 'media_assets');

-- 4. タグベース Row Filter
CREATE FUNCTION media_access_filter(department STRING, classification STRING)
RETURN
  IS_ACCOUNT_GROUP_MEMBER('media_admin')
  OR (department = current_user_attribute('department')
      AND classification IN ('public', 'internal'))
  OR (IS_ACCOUNT_GROUP_MEMBER(concat(department, '_confidential'))
      AND classification = 'confidential');

ALTER TABLE media_catalog SET ROW FILTER media_access_filter
  ON (department, classification);

-- 5. OpenSharing（組織横断共有）
CREATE SHARE media_partner_share;
ALTER SHARE media_partner_share ADD TABLE media_catalog;

-- 6. 重複検出
SELECT checksum, COUNT(*) as copies,
       SUM(file_size_bytes) as wasted_bytes
FROM media_catalog
GROUP BY checksum HAVING COUNT(*) > 1;
```

### AI パス: Mosaic AI（Vision）、Vector Search（RAG）、Model Serving（Whisper）

### 制約
- UC Volume は S3 バックエンドが必要（FSx for ONTAP S3 AP を直接登録できない）
- UC Row Filter / Column Mask は外部エンジンには適用されない
- 外部エンジンのガバナンスには Lake Formation が必要

---

## Snowflake パス

**背景**: 既存の Snowflake 環境(Cortex AI、Data Sharing、Horizon Catalog)を活用。

### ガバナンス: External Table + Row Access Policy + Masking + Secure Data Sharing

### AI パス: Cortex Search（RAG）、Cortex AI Vision、PARSE_DOCUMENT

### 主な特徴
- **Horizon Iceberg REST Catalog が外部エンジンにガバナンスを適用**（Row Access Policy + Masking）
- 全エディション対応（課金は 2026 年下期開始）
- ゼロコピー Data Sharing（受信側でデータ重複なし）

### 制約
- FSx for ONTAP S3 AP ステージで TO_FILE が失敗（エンジニアリング調査中）
- 内部ステージへの COPY FILES が必要なのは Vision AI（TO_FILE 経由）のみ。Cortex AI 関数（COMPLETE, SUMMARIZE）と Cortex Search は Managed Iceberg Table 上で直接動作
- AUTO_REFRESH 非対応（Task + ALTER STAGE REFRESH で回避）

---

## AWS ネイティブパス

**背景**: 既存の AWS ネイティブ環境(Athena、Glue、Bedrock、Lake Formation)を活用。

### ガバナンス: Lake Formation LF-Tags + クロスアカウント grant

### AI パス: Bedrock KB（RAG）、Textract、Transcribe、SageMaker

### 主な特徴
- Athena / Bedrock から **FSx for ONTAP S3 AP へ直接アクセス**（S3 コピー不要）
- **Lake Formation が全エンジンにガバナンスを適用**（Athena, Redshift, EMR）
- Bedrock Knowledge Base は FSx for ONTAP S3 AP を直接データソースにできる

### 制約
- Athena は VPC-origin AP にアクセスできない（Internet-origin が必要）
- 組み込みのデータリネージなし（別途構築が必要）
- Bedrock KB は非構造化データの自動インデックスのみ（構造化クエリは Athena 経由）

---

## プラットフォーム比較

| 観点 | Databricks | Snowflake | AWS ネイティブ |
|------|-----------|-----------|------------|
| **FSx for ONTAP S3 AP 直接アクセス** | ❌（UC セッションポリシー） | ⚠️（LIST のみ） | ✅（Athena, Bedrock） |
| **ガバナンスモデル** | UC Tags + Row Filter | Row Access Policy + Masking | Lake Formation LF-Tags |
| **外部エンジンへのガバナンス** | ❌ | ✅（Horizon Catalog） | ✅（Lake Formation） |
| **組織横断共有** | OpenSharing（オープンプロトコル） | Secure Data Sharing（ゼロコピー） | LF クロスアカウント + RAM |
| **非構造化 AI** | Mosaic AI, Vector Search | Cortex AI, Cortex Search | Bedrock, Textract, Transcribe |
| **重複排除** | なし（S3 依存） | なし（S3 依存） | なし（S3 依存） |
| **FSx for ONTAP 併用** | ✅（Option B/C/D） | ✅（Option B/C/D） | ✅（Option B/C/D） |

---

## 推奨マトリクス

| 優先事項 | 推奨 Option | 理由 |
|---------|------------|------|
| **最速のコスト削減** | Option B（FSx for ONTAP） | インライン dedup で 30-50% 削減、S3 コピー廃止 |
| **最大の帯域効率** | Option C（SnapMirror） | ブロックレベル差分 = DataSync の 2500 倍効率的 |
| **将来最適（最低コスト）** | Option D（FlexCache S3 AP） | キャッシュのみのストレージ = 現行比 80% コスト削減 |
| **最小変更** | Option A（S3 最適化） | 階層化のみ、削減効果は限定的 |
| **Databricks ガバナンス** | UC Volume + Tags +  OpenSharing | 全 Option 共通、ストレージ選択に依存しない |

---

## 選択ガイダンス（パス別サマリー）

| パス / 観点 | 要点 |
|------------|------|
| **Snowflake パス** | Horizon Catalog で外部エンジンにガバナンスを適用可能。非構造化データの AI 活用は Cortex Search + Data Sharing。Managed Iceberg Table → Horizon REST Catalog で Databricks/Spark も同じデータを読める。 |
| **Databricks パス** | UC Volumes + OpenSharing。非構造化データの自動タグ付けは Mosaic AI。S3 コスト削減に FSx for ONTAP。将来: Lakehouse Federation で FSx for ONTAP S3 AP データへの仮想アクセスが可能になる可能性。 |
| **AWS ネイティブパス** | FSx for ONTAP S3 AP + Lake Formation で S3 コピー削減と全エンジンガバナンスを両立。Bedrock KB が FSx for ONTAP S3 AP を直接読み取り。Glue Catalog + Iceberg 形式も別の Open Table Format 選択肢。 |
| **ストレージ最適化** | ONTAP dedup は同一ファイルコピー（版・部門コピー）に有効。類似の画像/動画は同一ブロックが存在する範囲でのみ有効。 |
| **移行 / ハイブリッド** | DataSync → FSx for ONTAP は確立されたパス（10TB / Direct Connect 1Gbps ≈ 22 時間）。FlexCache + FSx for ONTAP S3 AP はハイブリッド環境で有効。 |
| **データ主権** | データ主権要件では Option C（オンプレ ONTAP + SnapMirror）が必要な場合あり。医用画像（DICOM）や監視映像は PII/PHI の可能性 — 匿名化パイプラインを検討。 |
| **アウトカム指標** | ゴール: 「コスト削減 + ガバナンス付き組織横断共有」。段階的導入（Phase 1→2→3）で投資リスクを抑制。指標例: ストレージコスト削減、データ発見時間、共有リクエストからアクセスまでの時間。業界例: 製造（設計文書再利用）、金融（契約コンプライアンス検索）、医療（DICOM 研究共有）。 |

---

## 論点別の推奨サマリー

> 各行は1つの論点についての推奨をまとめたものです。本ドキュメント内の選択肢を
> 分析して導いたものであり、特定の役割に就いている個人から収集した見解では
> ありません。

| 論点 | 主要推奨 |
|---------|---------|
| **複数エンジンにまたがるガバナンス** | Databricks 決定事項でも、Snowflake Horizon で同じデータに対して外部エンジンへのガバナンス強制が可能。他のコンシューマー向けに Horizon を併用する選択肢あり。 |
| **カタログ統合と S3 コスト** | UC Volumes + OpenSharing が有効。S3 コスト削減には即時対応として S3 Intelligent-Tiering、戦略的には FSx for ONTAP を推奨。 |
| **データコピーの回避** | FSx for ONTAP S3 AP で S3 コピーの必要性を排除。FlexCache S3 AP(ロードマップ)でさらにコスト削減。 |
| **ストレージ効率** | ONTAP 重複排除がストレージ効率に有効(S3 にはネイティブ dedup なし)。FSx for ONTAP への移行が根本原因の解決に寄与。 |
| **運用と監視** | Amazon CloudWatch と ONTAP REST API で運用を統合管理。DataSync による FSx for ONTAP への移行はサポートされたパス。FlexCache S3 AP(ロードマップ)はハイブリッド構成で有効な選択肢。 |
| **データ主権** | データ主権要件によりオンプレ ONTAP + SnapMirror(Option C)が必須の場合あり。FlexCache S3 AP でフルレプリケーションなしにクラウド分析を実現。 |
| **ビジネス成果との整合** | 顧客のゴールは「コスト削減 + ガバナンス付き共有」。FlexCache S3 AP(ロードマップ)が最小データ移動で両立に寄与。 |


---

## 運用監視とセキュリティ

本ドキュメントで提案するアーキテクチャの Observability とセキュリティ監視(SIEM)については、以下の専用プロジェクトを参照してください。

| 領域 | リポジトリ | 内容 |
|------|-----------|------|
| **Observability** | [FSx-for-ONTAP-Observability-integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations) | FSx for ONTAP の監査ログを S3 AP + Lambda パイプライン経由で Datadog / Splunk / Grafana / Elastic に送信。 |
| **SLO / アラート** | [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) | SLO Observability パターン、FPolicy イベント駆動パイプライン、キャパシティガードレール。 |
