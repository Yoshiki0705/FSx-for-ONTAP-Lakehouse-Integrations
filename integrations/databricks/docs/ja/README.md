🌐 [English](../../README.md) | **日本語**

# Databricks 統合

🌐 [English](../../README.md) | **日本語**

> **検証ステータス: 実験的 — S3 AP は UC で非サポート（確認済み）**
> - Unity Catalog External Location は S3 Access Point のパスを読み取れません。登録は成功し、通らないのは読み取りです（Unity Catalog が払い出す down-scoped セッションポリシーがバケット形式 ARN のため。2026-08-12 実測）。`access_point` フィールドは現行ドキュメントに存在せず、削除されています。
> - 観測された部分的成功（ルートレベルの一覧取得、明示的ファイル読み取り）は「不完全な内部処理の副作用であり、サポートされたコードパスではない」とのことです。
> - Instance Profile + boto3 は、制御されたドライバーノード PoC としてのみ成功しました。
> - 本リポジトリは Databricks + FSx S3 Access Points の本番サポートを主張するものではありません。

## 概要

Amazon FSx for NetApp ONTAP（FSx for ONTAP）と Databricks を S3 Access Points 経由で統合する実験的検証パッケージです。

Unity Catalog External Location は現在セッションポリシーの制約により動作しないため、本番環境での Delta Lake テーブルには [Databricks がサポートするクラウドストレージパターン](https://docs.databricks.com/aws/en/connect/storage/amazon-s3) を使用してください。

## アーキテクチャ

```
┌───────────────────────────────────────────────────────────────────────┐
│                              AWS Account                              │
│                                                                       │
│  ┌────────────────────┐                                               │
│  │  Databricks        │                                               │
│  │  Unity Catalog     │                                               │
│  │  ┌──────────────┐  │     ┌──────────────┐     ┌───────────────┐    │
│  │  │ External     │  │     │ S3 Access    │     │ FSx for ONTAP │    │
│  │  │ Location     │──┼────▶│ Point        │────▶│ Volume        │    │
│  │  │              │  │     │ (VPC-scoped) │     │ (S3 protocol) │    │
│  │  └──────────────┘  │     └──────────────┘     └───────────────┘    │
│  │  ┌──────────────┐  │            │                    │             │
│  │  │ Storage      │  │     ┌──────▼──────┐      ┌──────▼──────┐      │
│  │  │ Credential   │──┼────▶│ IAM Role    │      │ Dedup/Snap/ │      │
│  │  │ (IAM Role)   │  │     │ (AssumeRole)│      │ FlexClone   │      │
│  │  └──────────────┘  │     └─────────────┘      └─────────────┘      │
│  └────────────────────┘                                               │
└───────────────────────────────────────────────────────────────────────┘
```

## S3 Access Point パス

```
s3://<s3ap-alias>/bronze/    # 取り込み済み生データ
s3://<s3ap-alias>/silver/    # クレンジング・変換済み
s3://<s3ap-alias>/gold/      # ビジネスレディ集計
```

## 検証結果 (2026-05-17)

| アプローチ | 結果 | 備考 |
|----------|------|------|
| S3 AP + Unity Catalog | ❌ | セッションポリシーが S3 AP ARN をサポートしない |
| S3 AP + Unity Catalog（`access_point` フィールド） | ⚠️ GA ではない | `access_point` フィールドは現行ドキュメントに存在しない。部分的成功は拒否される経路を通っていないため（2026-08-12 実測） |
| S3 AP + boto3 (Managed VPC) | ❌ | IMDS ブロック |
| NFS マウント (Managed VPC) | ❌ | Egress 制限 + seccomp |
| NFS マウント (Customer VPC) | ❌ | seccomp フィルターが NFS マウントをブロック |
| NFS RPC 直接 (Customer VPC) | ✅ | Python RPC で全操作成功 |
| ONTAP REST API (Customer VPC) | ✅ | 認証・設定変更可能 |
| Instance Profile + boto3 (Customer VPC, Dedicated) | ✅ | S3 AP 読み取り成功。UC ガバナンスをバイパス — PoC のみ |

## 拒否の由来

2026-08-12 に、ネイティブ S3 のコントロールを同一セッションで併走させて実証しました。ロール・
ネットワークは同一で、資格情報は Unity Catalog 自身が払い出したもの
（`POST /api/2.0/unity-catalog/temporary-path-credentials`）です。

1. **S3 Access Point のパスを External Location として登録することは成功します。** 通らないのは
   読み取りです。登録自体が非対応という以前の記述は誤りで、[BLK-001](../../../../docs/ja/blocker-tracker.md)
   で訂正しています。
2. Unity Catalog が払い出す down-scoped セッションポリシーは**バケット形式 ARN**
   （`arn:aws:s3:::<alias>`）で書かれている一方、AWS はアクセスポイント経由のリクエストを
   **アクセスポイント ARN**（`arn:aws:s3:<region>:<account>:accesspoint/<name>`）に対して認可
   評価します。両者は一致せず、セッションポリシーはロールポリシーと積集合を取るため、ロール本体
   が許可していても拒否されます。
3. 同一セッションでネイティブ S3 パスに払い出した資格情報は通ります。このコントロールがあること
   で、失敗からの推測ではなくセッションポリシーが機構であると言えます。
4. `access_point` フィールドは現行の Unity Catalog ドキュメントに存在しません。かつて提供されて
   いたのか、なぜ削除されたのかは **`open`** です。
5. 2026-05-26 に Databricks へ照会。機能ギャップとして起票済みで、公開された時期の情報はありません。

**推奨される暫定パス**: FSx for ONTAP から標準 S3 バケットにデータを同期（DataSync）し、その S3 バケットを UC External Location として登録。

UC ガバナンスなしの読み取り専用分析には、AWS ネイティブサービス（Athena、EMR Serverless、DuckDB Lambda）または Snowflake を FSx for ONTAP S3 AP 上で直接使用。

## 主要概念: Databricks ストレージ & 取り込みアーキテクチャ

Databricks のストレージと取り込みの概念を理解することが、FSx for ONTAP S3 AP 統合の評価に不可欠です。

> **パートナー向けクイックリファレンス**: 顧客から「Databricks で NAS データを S3 Access Points 経由で読めますか？」と聞かれた場合 — 答えは「部分的に可能だが制限あり」。ファイルレベルの読み取りは UC ガバナンス下で動作するが、テーブル作成とディレクトリ一覧はブロックされている。NAS データに対するガバナンス付き分析には、現時点で Snowflake External Table または Athena を推奨。Databricks 固有のワークロードには、S3 へのステージング取り込み → UC マネージドテーブルを推奨（[推奨アーキテクチャパターン](#推奨アーキテクチャパターン現時点)参照）。顧客が既に Databricks を使用している場合、FPolicy → Lambda → S3 → Auto Loader パターンで取り込みデータに完全 UC ガバナンスを維持可能。

> **パートナー向けクイックリファレンス(OpenSharing)**: 顧客から「Databricks で **OpenSharing** 経由で FSx for ONTAP のデータを読めますか?」と聞かれた場合の一次回答:
> - **プロトコル層は検証済み**: OpenSharing OSS リファレンスサーバー → STS credential vending → S3 AP 読み取り(2026-07 再確認)。再現可能な実装は [opensharing-server](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/tree/main/integrations/opensharing-server)。
> - **Databricks ネイティブ recipient(UC Foreign Volume/Table 認識)は実装待ち**(年末の Storage Ecosystem パートナー提供見込み)。
> - **今できること**: notebook 経由の PoC(`requests` + `boto3` で cred vending → S3 AP 読み取り → 必要に応じて UC テーブル書き込み)。trial(Serverless only)ワークスペースでは compute 起動事象に注意 — これは *環境固有* であり Databricks Serverless 一般の制限ではない。
> - **本番でガバナンス付き取り込みが今必要**なら、従来どおり DataSync → S3 → UC マネージドテーブル。

### Storage Credential → External Location → External Table/Volume

```
Storage Credential（IAM ロール ARN + External ID）
    │
    └── External Location（クラウドストレージパス + クレデンシャル）
            │
            ├── External Table（表形式データ: Parquet, Delta, Iceberg）
            └── External Volume（非表形式: 画像、ドキュメント、音声）
```

| 概念 | 説明 | FSx for ONTAP S3 AP ステータス | リファレンス |
|---|---|:---:|---|
| **[Storage Credential](https://docs.databricks.com/aws/en/connect/unity-catalog/storage-credentials)** | Databricks がクラウドストレージにアクセスするために引き受ける IAM ロール。AssumeRole 時に Databricks がセッションポリシーを生成し、IAM ロール自体がより広い権限を持っていても、引き受けたセッションの操作を制限する。 | ✅ 作成済み | [ドキュメント](https://docs.databricks.com/aws/en/connect/unity-catalog/storage-credentials) |
| **[External Location](https://docs.databricks.com/aws/en/connect/unity-catalog/cloud-storage/s3/s3-external-location-manual)** | S3 パスを Storage Credential にマッピング。アクセス境界を定義 | ⚠️ 作成済み（`access_point` フィールド付き — GA ではない; [拒否の由来](#拒否の由来)参照） | [ドキュメント](https://docs.databricks.com/aws/en/connect/unity-catalog/cloud-storage/s3/s3-external-location-manual) |
| **[External Table](https://docs.databricks.com/aws/en/tables/external)** | External Location にデータが存在する UC ガバナンス付きテーブル | ❌ CREATE TABLE ブロック | [ドキュメント](https://docs.databricks.com/aws/en/tables/external) |
| **[External Volume](https://docs.databricks.com/aws/en/volumes/managed-vs-external)** | External Location の非構造化ファイルに対する UC ガバナンス付きボリューム | ❌ ブロック（同じセッションポリシー問題） | [ドキュメント](https://docs.databricks.com/aws/en/volumes/managed-vs-external) |
| **[Managed Table](https://docs.databricks.com/aws/en/data-governance/unity-catalog/managed-versus-external)** | UC マネージドテーブル（データライフサイクルを Databricks が制御） | ✅ 動作（標準 S3 上） | [ドキュメント](https://docs.databricks.com/aws/en/data-governance/unity-catalog/managed-versus-external) |
| **[Managed Volume](https://docs.databricks.com/aws/en/volumes/managed-vs-external)** | 非構造化ファイル用 UC マネージドボリューム（Databricks マネージドストレージ） | ✅ 動作（標準 S3 上） | [ドキュメント](https://docs.databricks.com/aws/en/volumes/managed-vs-external) |

### Auto Loader（増分取り込み）

[Auto Loader](https://docs.databricks.com/ingestion/auto-loader/index.html) は Snowflake の Snowpipe に相当する機能 — クラウドストレージに到着した新しいファイルを増分的に処理します。

| モード | 説明 | S3 Event Notifications 必要 | FSx for ONTAP S3 AP ステータス |
|---|---|:---:|:---:|
| **[Directory Listing](https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader/directory-listing-mode)** | 定期的にディレクトリを一覧して新規ファイルを検出 | ❌ 不要 | ⚠️ External Location が必要（ブロック） |
| **[File Notification](https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader/file-notification-mode)** | S3 Event Notifications + SQS でリアルタイム検出 | ✅ 必要 | ❌ 不可（FSx for ONTAP S3 AP は S3 Events 非サポート） |

**Snowflake との比較:**

| 機能 | Snowflake (Snowpipe) | Databricks (Auto Loader) | FSx for ONTAP S3 AP サポート |
|---|---|---|:---:|
| イベント駆動取り込み | Snowpipe (S3 Events → SNS → Snowflake) | File Notification モード (S3 Events → SQS) | ❌ 両方ブロック（FSx for ONTAP S3 AP に S3 Events なし） |
| ポーリングベース取り込み | スケジュール `ALTER STAGE REFRESH` (Task) | Directory Listing モード | ⚠️ Snowflake: 動作; Databricks: UC でブロック |
| FSx 向け代替手段 | FPolicy → Lambda → SNS → Snowpipe | FPolicy → Lambda → S3 に書き込み → Auto Loader | ✅ 回避策あり |
| 増分処理 | Snowpipe がロード済みファイルを追跡 | Auto Loader がチェックポイントで処理済みファイルを追跡 | — |

### サポートされる取り込みフォーマット

**Auto Loader 対応フォーマット:**

| フォーマット | Auto Loader | スキーマ推論 | スキーマ進化 | 備考 |
|---|:---:|:---:|:---:|---|
| JSON | ✅ | ✅ | ✅ | ネスト構造対応 |
| CSV | ✅ | ✅ | ✅ | ヘッダー検出、デリミタオプション |
| Parquet | ✅ | ✅ | ✅ | カラムプルーニング、述語プッシュダウン |
| Avro | ✅ | ✅ | ✅ | スキーマレジストリ互換 |
| ORC | ✅ | ✅ | ❌ | 読み取り専用スキーマ |
| XML | ✅ | ✅ | ✅ | ネイティブサポート |
| TEXT | ✅ | — | — | 行単位取り込み |
| BINARYFILE | ✅ | — | — | 画像、PDF、音声 — バイナリとして取り込み |

**Auto Loader 非対応フォーマット（代替取り込み方法が必要）:**

| フォーマット | 代替取り込み方法 | 考慮事項 |
|---|---|---|
| Delta Lake（既存） | `CONVERT TO DELTA` または `SHALLOW CLONE` | 外部ストレージ上の既存 Delta テーブル用 |
| Iceberg（既存） | `CREATE TABLE ... USING ICEBERG LOCATION` | 既存 Iceberg メタデータを登録 |
| 動画 (MP4, MOV) | `BINARYFILE` フォーマット → カスタム UDF 処理 | 大容量ファイル。ストリーミングフレーム抽出を検討 |
| 音声 (WAV, MP3) | `BINARYFILE` フォーマット → 文字起こし UDF | Spark ML または外部 API で文字起こし |
| DB エクスポート (mysqldump, pg_dump) | カスタム ETL（Spark SQL パース） | SQL 文を構造化データにパース |
| 圧縮アーカイブ (ZIP, TAR.GZ) | カスタム UDF で解凍 → 内容を処理 | 取り込み前に展開 |

### FSx for ONTAP 向けデータ取り込み代替手段（Auto Loader がブロックされている場合）

Auto Loader は External Location が必要（FSx for ONTAP S3 AP 上で現在ブロック）のため、以下の代替手段を使用:

| 方法 | 説明 | レイテンシ | ガバナンス | リファレンス |
|---|---|---|---|---|
| **FPolicy → Lambda → S3 → Auto Loader** | FPolicy が FSx 上のファイル変更を検知 → Lambda が S3 バケットにコピー → Auto Loader が取り込み | 秒 | ✅ 完全 UC（S3 コピー上） | [FPolicy ドキュメント](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html) |
| **AWS Glue ETL** | Glue ジョブが FSx for ONTAP S3 AP から読み取り → S3/Delta に書き込み | 分 | AWS 側 | [Glue + FSx チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html) |
| **EMR Serverless** | Spark ジョブが FSx for ONTAP S3 AP から読み取り → S3/Delta に書き込み | 分 | AWS 側 | [EMR + FSx チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-run-spark-with-emr-serverless.html) |
| **AWS DataSync** | FSx NFS → S3 バケットのスケジュール同期 | 分〜時間 | AWS 側 | [DataSync ドキュメント](https://docs.aws.amazon.com/datasync/latest/userguide/create-ontap-location.html) |
| **SnapMirror to S3** | ONTAP ネイティブの S3 バケットへのレプリケーション | 分 | ONTAP 側 | [SnapMirror S3](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-snapmirror.html) |
| **Instance Profile + boto3 (PoC)** | Databricks ドライバーからの直接 S3 AP 読み取り | リアルタイム | ❌ UC なし | ガバナンスをバイパス |

> **SnapMirror to S3 — FSx for ONTAP で利用不可と確認（2026年5月）**: SnapMirror S3（`snapmirror object-store` コマンドおよび `/api/cloud/targets` API）は FSx for ONTAP のマネージドサービス制約として**無効化**されています。ONTAP S3 サーバーとバケットの作成は動作しますが、SnapMirror S3 レプリケーションコマンドは全権限レベル（admin/advanced/diagnostic）で "not a recognized command" を返します。SnapMirror S3 "Continuous" ポリシーは存在しますが使用不可。ONTAP 9.17.1P6 で検証済み。AWS に機能要望を提出済み。**FSx for ONTAP から S3 への唯一の検証済み同期メカニズムとして AWS DataSync を使用してください。**

**推奨本番パターン:**
```
FSx for ONTAP ──FPolicy──▶ Lambda ──▶ S3 バケット ──▶ Auto Loader ──▶ Delta Table（UC ガバナンス付き）
     │                                                                      │
     └── NFS/SMB ユーザーが同じデータにアクセス                                  └── 完全 UC ガバナンス
```

### Volumes: 非構造化データガバナンス

[Unity Catalog Volumes](https://docs.databricks.com/aws/en/volumes/managed-vs-external) は Snowflake の Directory Table に相当 — 非表形式ファイル（画像、ドキュメント、音声、動画）へのガバナンス付きアクセスを提供します。

| 概念 | Snowflake 相当 | 説明 | FSx for ONTAP S3 AP ステータス |
|---|---|---|:---:|
| **External Volume** | 外部ステージの Directory Table | 外部ストレージ上のガバナンス付きファイルアクセス | ❌ ブロック（External Location が必要） |
| **Managed Volume** | 内部ステージ + Directory Table | Databricks マネージドストレージ上のガバナンス付きファイルアクセス | ✅ 動作（標準 S3） |
| **Volume パス** (`/Volumes/catalog/schema/volume/`) | `@stage/path/` | SQL/Python でのファイルアクセス統一パス | ❌ FSx for ONTAP S3 AP では利用不可 |

**重要な違い**: Snowflake の Directory Table は FSx for ONTAP S3 AP 外部ステージで今日動作します。Databricks の External Volumes は External Location の作成が必要で、セッションポリシーによりブロックされています。

### 概念マッピング: Snowflake ↔ Databricks

| Snowflake 概念 | Databricks 相当 | 目的 | FSx for ONTAP S3 AP (Snowflake) | FSx for ONTAP S3 AP (Databricks) |
|---|---|---|:---:|:---:|
| Storage Integration | Storage Credential | IAM ロール参照 | ✅ | ✅ |
| External Stage | External Location | クラウドストレージパスマッピング | ✅ | ✅（部分的） |
| External Table | External Table | 外部データへのガバナンス付き読み取り | ✅ | ❌ ブロック |
| Directory Table | External Volume | 非構造化データのファイルカタログ | ✅ | ❌ ブロック |
| Snowpipe | Auto Loader | 増分ファイル取り込み | ⚠️（S3 Events なし） | ❌ ブロック |
| COPY INTO | COPY INTO / Auto Loader | バッチデータロード | ✅ | ❌ ブロック |
| Internal Stage | Managed Volume | Snowflake/Databricks マネージドストレージ | ✅ | ✅ |
| `AWS_ACCESS_POINT_ARN` | `access_point` フィールド | セッションポリシー用 S3 AP ARN | ✅（全て解決） | ⚠️（部分的解決） |

## マネージドテーブル vs 外部テーブル — 設計ガイド

Unity Catalog におけるマネージドテーブルと外部テーブルの違いを理解することがアーキテクチャ判断に不可欠です — 特に現在の FSx for ONTAP S3 AP セッションポリシーの制限を考慮して。

> **主要概念**: [外部テーブル](https://docs.databricks.com/aws/en/tables/external)（UC がメタデータのみ管理）| [マネージドテーブル](https://docs.databricks.com/aws/en/data-governance/unity-catalog/managed-versus-external)（UC が両方管理）| [External Location](https://docs.databricks.com/aws/en/connect/unity-catalog/storage-credentials)（クラウドパスをクレデンシャルにマッピング）
>
> 分析および AI/ML 固有の影響については [Analytics & AI デモガイド](ai-demo-guide.md) を参照。

### 比較マトリクス

| 観点 | UC 外部テーブル（FSx for ONTAP S3 AP 上） | UC マネージドテーブル（S3 バケット上） | boto3 PoC（UC テーブルなし） |
|---|---|---|---|
| **データ所在** | FSx for ONTAP（ゼロコピー） | Databricks マネージド S3 | FSx for ONTAP |
| **UC ガバナンス** | ❌ **ブロック**（CREATE TABLE 失敗） | ✅ 完全（タグ、マスク、リネージ） | ❌ なし |
| **ONTAP 機能の保持** | ✅ Snapshot, FlexClone, FPolicy | ❌ データは ONTAP 外 | ✅（読み取り専用） |
| **マルチプロトコルアクセス** | ✅ NFS/SMB/S3 AP | ❌ S3 のみ | ✅ NFS/SMB/S3 AP |
| **クエリ性能** | N/A（テーブル作成ブロック） | ✅ 最適化 Delta/Iceberg | ❌ Spark 最適化なし |
| **Delta Lake 機能** | ❌ ブロック | ✅ ACID, Time Travel, MERGE | ❌ 適用外 |
| **ML Feature Store** | ❌ ブロック | ✅ 完全サポート | ❌ 適用外 |
| **データ鮮度** | リアルタイム（サポートされれば） | 取り込みパイプラインに依存 | リアルタイム（boto3 が現在の状態を読み取り） |
| **ストレージコスト** | FSx のみ | FSx + S3（重複） | FSx のみ |
| **本番適合性** | ❌ 現時点で不可 | ✅ 推奨 | ⚠️ PoC のみ |

### 現在の状態: 動作するものと動作しないもの

```
FSx for ONTAP S3 AP
     │
     ├── UC External Location（access_point フィールド設定済み）
     │     ├── トップレベル ls: ✅（287 アイテム）
     │     ├── 明示的ファイル読み取り（spark.read.csv）: ✅（1000 行）
     │     ├── サブディレクトリ一覧: ❌（AccessDenied）
     │     ├── CREATE TABLE: ❌（UC_CLOUD_STORAGE_ACCESS_FAILURE）
     │     └── 書き込み操作: ❌（PutObject AccessDenied）
     │
     └── Instance Profile + boto3（Customer VPC, Dedicated クラスター）
           ├── GetObject: ✅
           ├── ListObjectsV2: ✅
           └── UC ガバナンス: ❌（完全にバイパス）
```

### 推奨アーキテクチャパターン（現時点）

FSx for ONTAP S3 AP 上の UC 外部テーブルがブロックされているため、推奨パターンは**ステージング取り込み**アプローチ:

```
FSx for ONTAP ──S3 AP──▶ 取り込みジョブ ──▶ S3 バケット ──▶ UC マネージドテーブル ──▶ ML/AI
     │                    (Glue/EMR/Lambda)                    │
     │                                                         └── 完全 UC ガバナンス
     └── 同一データに NFS/SMB でアクセス（ソースオブトゥルース）
```

**または読み取り専用分析の場合:**
```
FSx for ONTAP ──S3 AP──▶ Athena（SQL 分析、コピー不要）
                    └──▶ Snowflake External Table（ガバナンス付き、コピー不要）
```

### パターン別の選択ガイド

| 要件 | 推奨パターン | 理由 |
|---|---|---|
| ガバナンス付き ML 学習データ | S3 バケット → UC マネージドテーブル | 完全 UC ガバナンス、Feature Store、リネージ |
| NAS 上の読み取り専用 SQL 分析 | Athena + FSx for ONTAP S3 AP | コピー不要、サーバーレス、ガバナンス付き |
| NAS 上のガバナンス付き外部テーブル | Snowflake External Table | 現時点で完全ガバナンス付きで動作 |
| 探索的データアクセス（PoC） | Instance Profile + boto3 | 迅速なアクセス、ガバナンスなし |
| 本番 Delta Lake テーブル | S3 バケット（標準パターン） | ACID, MERGE, OPTIMIZE に必要 |
| リアルタイム NAS データ + UC ガバナンス | プラットフォームサポート待ち | UC セッションポリシー解消が必要 |

### コスト & ガバナンスのトレードオフ

| パターン | ストレージコスト | ガバナンス | 性能 | ONTAP 機能 |
|---|---|---|---|---|
| **Athena + FSx for ONTAP S3 AP** | 最低（FSx のみ） | AWS 側（IAM, S3 AP） | 良好（サーバーレス） | ✅ 保持 |
| **Snowflake External Table** | 低（FSx のみ） | ✅ 完全（タグ、マスキング） | 中程度 | ✅ 保持 |
| **S3 にステージング → UC テーブル** | 高（FSx + S3） | ✅ 完全 UC | 最高（Delta 最適化） | ❌ コピーで失われる |
| **boto3 PoC** | 最低（FSx のみ） | ❌ なし | 低（ドライバーのみ） | ✅ 保持 |

### AI レディネススコア

| パターン | ガバナンス | 性能 | AI 機能 | コスト | 運用容易性 | 総合 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Athena + FSx for ONTAP S3 AP** | ★★★☆☆ | ★★★★☆ | ★☆☆☆☆ (SQL のみ) | ★★★★★ | ★★★★★ | **3.6** |
| **Snowflake External Table** | ★★★★☆ | ★★★☆☆ | ★★★★☆ (Cortex AI) | ★★★★★ | ★★★★☆ | **4.0** |
| **S3 にステージング → UC テーブル** | ★★★★★ | ★★★★★ | ★★★★★ (全 Mosaic AI) | ★★☆☆☆ | ★★☆☆☆ | **3.8** |
| **boto3 PoC (Databricks)** | ★☆☆☆☆ | ★★☆☆☆ | ★★★☆☆ (ドライバーのみ) | ★★★★★ | ★★★☆☆ | **2.8** |
| **Bedrock KB + FSx for ONTAP S3 AP** | ★★★☆☆ | ★★★★☆ | ★★★★☆ (RAG) | ★★★★☆ | ★★★★☆ | **3.8** |

- **ガバナンス**: UC リネージ、タグ、マスキング、Row Filter
- **性能**: クエリレイテンシ、分散処理
- **AI 機能**: 利用可能な AI/ML 関数の幅
- **コスト**: ストレージ効率、コンピュートコスト
- **運用容易性**: セットアップ、メンテナンス、パイプラインの複雑さ

> **スコアリング方法論**: 各次元は本リポジトリの検証済みエビデンスに基づき著者が評価。AWS の公式アセスメントではありません。スコアは1つのテスト環境（DBR 17.3 LTS, ap-northeast-1）での観測結果を反映。

> **性能スコアに関する注意**: 性能スコアは FSx for ONTAP S3 AP アクセスパターン内での相対比較であり、ネイティブ S3 バケット性能との比較ではありません。FSx for ONTAP S3 AP 経由の全パターンは、同等のネイティブ S3 操作より高いレイテンシを持ちます。

> **スコアの使い方**: Overall スコアをパターン選択の出発点として使用。4.0 以上はガバナンス付き本番ワークロードに適合。3.5〜3.9 はトレードオフを評価した上で利用可能。3.0 未満は PoC 専用パスで、補償コントロールと明示的承認が必要。

**パターン選択ガイド:**
- **Snowflake External Table**（4.0）: コピーなしで NAS データに対するガバナンス付き AI が優先の場合
- **S3 にステージング → UC テーブル**（3.8）: Databricks の最大性能と全 Mosaic AI が必要な場合（データ重複コストを許容）
- **Bedrock KB**（3.8）: FSx 上のゼロコピーで AWS ネイティブ RAG が主要要件の場合
- **boto3 PoC**（2.8）: 明示的承認付きの期間限定探索のみ

### リファレンス

- [Unity Catalog External Tables](https://docs.databricks.com/aws/en/tables/external)
- [Managed vs External Assets](https://docs.databricks.com/aws/en/data-governance/unity-catalog/managed-versus-external)
- [External Locations](https://docs.databricks.com/aws/en/connect/unity-catalog/storage-credentials)
- [Delta Lake on Databricks](https://docs.databricks.com/aws/en/delta/index)

## 非構造化データ対応

| フォーマット | 対応 | アクセス方法 | ユースケース |
|------------|:---:|------------|------------|
| 画像 (JPEG, PNG, TIFF) | ⚠️ | Instance Profile + boto3（ドライバーのみ） | 画像分類、品質検査 |
| 動画 (MP4, MOV) | ⚠️ | Instance Profile + boto3（ドライバーのみ） | フレーム抽出、動画分析 |
| ドキュメント (PDF, DOCX) | ⚠️ | Instance Profile + boto3（ドライバーのみ） | テキスト抽出、RAG パイプライン |
| 音声 (WAV, MP3) | ⚠️ | Instance Profile + boto3（ドライバーのみ） | 文字起こし、音声分析 |
| バイナリ / アーカイブ | ⚠️ | Instance Profile + boto3（ドライバーのみ） | ダウンロード、カスタム処理 |

**現在の制約:**
- Unity Catalog External Table 作成がブロック → ガバナンス付き非構造化データカタログ不可
- `spark.read.binaryFile` は明示的ファイルパスで動作（`access_point` フィールド設定時）
- Instance Profile + boto3 は UC ガバナンスをバイパス（PoC のみ、本番非推奨）
- Snowflake の Directory Table や GET_PRESIGNED_URL に相当する機能なし
- Executor スケール処理は未検証

### FILE 型（β、2026-08）— 評価済み。ブロッカーは解消しない

Databricks は [FILE 型](https://www.databricks.com/blog/introducing-file-type-native-column-type-multimodal-data)を導入した。非構造化ファイルへのガバナンスされた参照を Delta の列として持ち、構造化列と並べてクエリでき、AI 関数に渡せる。Unity Catalog における「ガバナンス付き非構造化データカタログ」に最も近いものである。

ただし上記のステータスは変わらない。`FILE EXTERNAL` は **UC Volume 内**のファイルのみサポートされ、UC External Volume は S3 Access Point 上に作成できない（BLK-001）。到達可能なのは `FILE MANAGED` のみで、これはバイト列を UC 管理ストレージへ**コピー**する。

前進したのは別機能である。[`_object_metadata` 列](https://docs.databricks.com/aws/en/ingestion/object-metadata-column)（DBR 18.2+）が S3 の**オブジェクトタグ**とユーザー定義メタデータをクエリ可能な列として公開し、かつオブジェクトタグ付けは FSx for ONTAP S3 AP で**サポートされる**（2026-08-12 検証済み）。Databricks が Access Point パス経由でそのタグを読めるかは**未検証**。

| 目的 | 参照先 |
|---|---|
| 完全な評価、3 層設計、未解決の質問 | [databricks-file-type-evaluation](../../../../docs/ja/databricks-file-type-evaluation.md) ([English](../../../../docs/en/databricks-file-type-evaluation.md)) |
| FSx for ONTAP 側のオブジェクトタグ実測（上限、ASCII 制約、file-scope、上書き挙動） | [s3ap-object-tagging 証拠](../../../../verification-pack/s3ap-object-tagging/evidence/2026-08-12/evidence-record.yaml) |
| Databricks 側の実行可能な検証 | [`notebooks/10_file_type_object_metadata.py`](../../notebooks/10_file_type_object_metadata.py) · [test-cases.yaml](../../../../verification-pack/databricks/test-cases.yaml) の `DBX-FILE-*` |

**FSx for ONTAP 上の非構造化データの推奨代替手段:**
- **Snowflake**（Directory Table + GET_PRESIGNED_URL）でファイルカタログとセキュア URL 生成
- **AWS Lambda** でサーバーレスファイル処理（[AWS チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-process-files-with-lambda.html)）
- **Amazon Bedrock** でドキュメント RAG（[AWS チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)）

## ONTAP の価値

| ONTAP 機能 | Databricks へのメリット | リファレンス |
|---|---|---|
| **FlexCache** | リージョン/拠点間で学習データをキャッシュし低遅延アクセスを実現。Write-back モードで特徴量エンジニアリングを高速化 | [FlexCache ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html) |
| **SnapLock / Tamperproof Snapshot** | 不変の学習データ保護 — 管理者権限でも保持期間中は削除不可。規制 ML のコンプライアンス | [SnapLock on FSx](https://netapp.com/blog/snaplock-on-amazon-fsx-ontap/) |
| **ARP/AI** | AI によるランサムウェア検知。学習データとモデルアーティファクトを自動スナップショットで保護 | [ARP on FSx](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/ARP.html) |
| **FlexClone** | フルコピーなしの即時 dev/test データセットプロビジョニング。ゼロコピー ML 実験 | [FlexClone ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-volumes.html) |
| **Snapshot** | テーブルレベルのポイントインタイムリカバリ（Delta Time Travel を補完）。特徴量パイプラインのバージョン管理 | [Snapshot ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/snapshots-ontap.html) |
| **FabricPool** | コールドパーティションの S3 自動階層化（Databricks コンピュートに透過的） | [FabricPool ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/fabricpool.html) |
| **ストレージ効率化** | 重複排除 + 圧縮 + コンパクションで Delta バージョンファイルを最大 65% 削減 | [ストレージ効率](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/storage-efficiency.html) |
| **SnapMirror** | レイクハウスデータと ML パイプラインのクロスリージョン DR | [SnapMirror ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html) |
| **マルチプロトコル** | NFS（データサイエンティスト）+ SMB（Windows ユーザー）+ S3 AP（Databricks/Spark）— 同一データ、コピー不要 | [マルチプロトコル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/supported-fsx-clients.html) |
| **FPolicy** | ファイル操作の監視とブロック。データアクセスコンプライアンスの監査証跡 | [FPolicy ドキュメント](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html) |

## ガバナンス & AI/ML ガイド

| ガイド | 説明 |
|---|---|
| [Analytics & AI デモガイド](ai-demo-guide.md) | 分析 & AI 機能、現在のステータス、動作するデモ、ブロックされたパス |
| [OpenSharing & Volume Sharing ガイド](delta-sharing-volume-guide.md) | OpenSharing で FSx ベースの構造化/非構造化データを Databricks に共有する方法 — 3パターン（メタデータテーブル、AI処理済み、Raw ファイル） |
| [ガバナンス: タグとデータ保護 (ABAC)](ai-demo-guide.md#ガバナンスタグとデータ保護-abac) | UC ABAC、Governed Tags、カラムマスク、Row Filter — 現在の制限 |
| [ガバナンス: ファイルレベルアクセス制御](ai-demo-guide.md#ファイルレベルのアクセス制御-ontap-ネイティブレイヤー) | ONTAP デュアルレイヤー認可、FPolicy、チームごとの S3 AP 分離（補償コントロール） |
| [統合: ONTAP × Databricks タグ](ai-demo-guide.md#統合-ontap-ファイルレベル制御--databricks-タグガバナンス) | 組み合わせガバナンスマトリクス、現在 vs 将来、設計パターン |
| [FILE 型（β）評価](../../../../docs/ja/databricks-file-type-evaluation.md) | FILE 列によるマルチモーダルデータ、BLK-001 が依然適用される理由、`_object_metadata` によるオブジェクトタグの橋渡し、推奨する 3 層メタデータ設計 |

## クイックスタート

```bash
# 1. CloudFormation テンプレートをデプロイ
cp params.example.json params.json  # パラメータを編集
./deploy.sh

# 2. Databricks Storage Credential を設定（Terraform または UI）
cd terraform/
cp terraform.tfvars.example terraform.tfvars
terraform init && terraform apply

# 3. External Location を作成して S3 AP を指定
# 4. ノートブックを順番に実行 (01 → 06)
```
