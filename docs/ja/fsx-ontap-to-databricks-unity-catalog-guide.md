🌐 [English](../en/fsx-ontap-to-databricks-unity-catalog-guide.md) | **日本語**

# FSx for ONTAP → Databricks Unity Catalog 接続総合ガイド

> **ステータス**: 初版（2026-06-18）。本リポジトリの検証結果を統合。
> **対象読者**: AWS SA、パートナー SI/ISV、データエンジニア。DAIS 2026 後の FAQ 対応。
> **Evidence tier**: 検証結果は **Project-context**（本リポジトリ内で再現可能）。公式情報は **Public**。

---

## エグゼクティブサマリ

**Q: FSx for ONTAP のデータを Databricks Unity Catalog で利用できますか？**

**A: はい。ただし直接的な External Location 登録ではなく、間接パスで実現します。**

| 結論 | 詳細 |
|------|------|
| ✅ 利用可能 | 複数の経路で FSx for ONTAP データを UC ガバナンス下に取り込み可能 |
| ❌ ゼロコピー直接接続は非対応 | UC External Location は S3 AP / ONTAP S3 / NFS マウントを**非サポート** |
| ✅ 推奨パスあり | DataSync → S3 → UC テーブル、Kafka → Structured Streaming → UC Delta |
| ⚠️ DAIS 2026 新機能は直接解決しない | OpenSharing は共有プロトコルであり、ストレージ接続ではない |

### なぜ FSx for ONTAP を使うのか（マルチプロトコルの価値）

FSx for ONTAP の最大の価値は「**同じデータに NFS / SMB / S3 AP で同時アクセスできること**」です。Databricks への接続は間接パスが必要ですが、以下の全体像で FSx for ONTAP の位置づけを理解してください:

```
同一データ（FSx for ONTAP ボリューム）
  │
  ├── NFS → データサイエンティスト（Linux ワークステーション）
  ├── SMB → ビジネスユーザー（Windows ファイル共有）
  ├── S3 AP → AWS サービス（Athena, Glue, EMR, Bedrock, Snowflake）
  │
  └── DataSync / FPolicy → S3 → Databricks UC
       （分析コピーを UC ガバナンス下で活用）
```

業務ユーザーが NFS/SMB で日常的にアクセスするデータを、**コピーや変換なしで**そのまま AWS 分析サービス（Athena, Glue, EMR）から S3 AP 経由で利用できます。Databricks UC へは間接パスが必要ですが、同じデータの**分析用コピー**を DataSync で同期することで、UC のフルガバナンス（lineage, tags, masks, row filters）を適用できます。

---

## よくある誤解と FAQ

### Q1: OpenSharing で FSx for ONTAP に直接つなげるのでは？

**A: いいえ。OpenSharing は「共有プロトコル」であり「ストレージ接続」ではありません。**

OpenSharing（Delta Sharing の後継、DAIS 2026 発表）は以下を提供:
- 組織間でのデータ・モデル・エージェントスキルの**共有**
- Apache Iceberg IRC クライアント対応
- ゼロコピー**共有**（提供者のストレージ → 受信者への読み取り権限付与）

しかし、OpenSharing は:
- ❌ FSx for ONTAP を UC のストレージとして登録する機能**ではない**
- ❌ S3 互換エンドポイントを UC External Location として認識させる機能**ではない**
- ❌ NFS/SMB ファイルシステムを UC に接続する機能**ではない**

OpenSharing でできること（FSx for ONTAP 関連）:
- ✅ FSx for ONTAP のデータを S3 に取り込み、Delta テーブル化した**後**に、OpenSharing で他組織に共有
- ✅ 自己管理の OpenSharing サーバーが FSx for ONTAP S3 AP に対してスコープ限定 STS 認証情報を vend し、ゼロコピー読み取りを実現（本リポジトリで検証済み）
- ✅ Databricks Storage Ecosystem（DAIS 2026）: NetApp が 2026 年末までにネイティブ OpenSharing 統合をコミット — 将来的に直接接続が可能になる可能性あり

```
FSx for ONTAP → [DataSync/ETL] → S3 → UC Delta テーブル → OpenSharing → 受信者
                                                              ↑ ここが OpenSharing の範囲

FSx for ONTAP → OpenSharing Server (credential vending) → 受信者 (ゼロコピー、UC ガバナンスなし)
                  ↑ 本リポジトリのリファレンス実装
```

### Q2: OpenSharing で FSx for ONTAP のファイルを直接共有できるのでは？

**A: いいえ。OpenSharing は「共有プロトコル」であり、任意のファイルを変換せずに共有する機能ではありません。**

OpenSharing の前提:
- 共有対象は **Tables**（Delta または Iceberg）、**Volumes**、**Models**、**AgentSkills**
- テーブルデータは **UC が認識するストレージ**（標準 S3 / ADLS / GCS）に存在する必要がある
- FSx for ONTAP 上のファイル（CSV、画像、PDF）をそのまま OpenSharing 経由で共有する機能は、provider 側の credential vending サーバーなしには**利用不可**

FSx for ONTAP データを OpenSharing で共有するには:
1. FSx for ONTAP → S3 に取り込み
2. S3 上で Delta/Iceberg テーブルとして登録
3. OpenSharing で共有

あるいは、独立した OpenSharing provider サーバー（本リポジトリのリファレンス実装）がスコープ限定 STS 認証情報を recipient に vend し、ゼロコピー読み取りを可能にします。ただし、ネイティブ UC recipient 経由で取り込まない限り UC ガバナンスは適用されません。

### Q3: Databricks から FSx for ONTAP に NFS マウントできないの？

**A: Databricks ランタイムの seccomp ポリシーにより、カーネル NFS マウントはブロックされます。**

- Databricks のサーバーレスおよび共有クラスターでは、セキュリティ上の理由で `mount` システムコールが制限
- 専用クラスター（Classic）でも、ランタイム境界により NFS マウントは動作しない（検証済み）
- FUSE ベースのマウント（`s3fs-fuse` 等）も同様に制限される

### Q4: FSx for ONTAP の S3 Access Point を UC External Location に登録できないの？

**A: 2026 年 5 月時点で、Databricks は S3 Access Point を UC External Location として正式にサポートしていません。**

検証結果（本リポジトリ、Databricks Support 確認済み 2026-05-26）:
- `access_point` フィールドは GA リリースされておらず、ドキュメントからも削除済み
- 一部動作（トップレベルのファイル一覧、明示パスのファイル読み取り）は「内部処理の副作用であり、サポートされたコードパスではない」（Databricks Support 回答）
- CREATE TABLE、サブディレクトリ一覧は `AccessDenied` / `UC_CLOUD_STORAGE_ACCESS_FAILURE`

### Q5: ONTAP S3（S3 互換エンドポイント）を UC に登録できないの？

**A: UC External Location は以下のみをサポートしています:**

| サポート対象 | ステータス |
|-------------|-----------|
| Amazon S3（ネイティブ） | ✅ |
| Azure Data Lake Storage Gen2 | ✅ |
| Google Cloud Storage | ✅ |
| Cloudflare R2 | ✅ |
| S3 互換エンドポイント（MinIO, ONTAP S3 等） | ❌ 非サポート |

ONTAP S3 は S3 API 互換ですが、UC のセッションポリシー生成ロジックが標準 S3 バケットのみを前提としているため、S3 互換エンドポイントは認識されません。

### Q6: Volumes コネクタ（OpenSharing）で非構造化データを共有できないの？

**A: 2026 年 6 月時点で、Volumes コネクタは OpenSharing の Agent Asset type として設計されていますが、FSx for ONTAP を直接 Volume として登録する機能は提供されていません。**

UC Volume の要件:
- External Volume → UC External Location が必要（S3 AP 非対応のためブロック）
- Managed Volume → Databricks 管理の S3 ストレージ（FSx for ONTAP ではない）

---

## 接続パス一覧: できることとできないこと

### パスごとの RPO（データ鮮度）とトレードオフ

| パス | RPO（データ鮮度） | スループット | UC ガバナンス | データコピー |
|------|------------------|-------------|--------------|-------------|
| DataSync → S3 → UC | 5 分〜24 時間（スケジュール依存） | 高（DataSync 最適化） | ✅ フル | 選択的（構造化サブセットのみ S3 へ; [戦略詳細](#コピー対象と残留データ具体例) 参照） |
| Kafka → SS → UC | 秒〜10 秒（ストリーミング遅延） | 中〜高（パーティション並列） | ✅ フル | イベント単位（ストリームレコード → Delta） |
| Glue/EMR ETL → UC | 分〜時間（ジョブスケジュール） | 高（Spark 分散） | ✅ フル | ETL 出力のみ（変換済みデータを S3 へ） |
| Foreign Iceberg | ニアリアルタイム（REFRESH 依存） | 読み取り専用 | ✅ 読み取り | 最小（メタデータのみ） |
| Athena + S3 AP (UC 外) | リアルタイム（S3 AP 直接読み取り） | 中 | ❌ AWS 側のみ | 不要（ゼロコピー） |
| boto3 PoC | リアルタイム | 低（ドライバーのみ） | ❌ なし | 不要 |

### Snowflake と Databricks の接続比較

FSx for ONTAP S3 AP に対する接続能力の差異:

| 機能 | Snowflake | Databricks (UC) | 理由 |
|------|-----------|-----------------|------|
| External Table (S3 AP) | ✅ 動作 | ❌ ブロック | Snowflake は `AWS_ACCESS_POINT_ARN` で S3 AP を解決。UC はセッションポリシーが S3 AP 未対応 |
| Directory Table / Volume | ✅ 動作 | ❌ ブロック | 同上（External Location 依存） |
| Event-driven Snowpipe / Auto Loader | ⚠️ FPolicy 経由 | ❌ ブロック | S3 Event Notifications が FSx for ONTAP S3 AP で非対応。両者とも FPolicy 経由の代替が必要 |
| Zero-copy 読み取り | ✅ | ❌ | UC は標準 S3 バケットのみ |
| ガバナンス (Tags, Masking) | ✅ | ✅（S3 経由で取り込み後） | UC のガバナンスは S3 上テーブルに適用 |
| AI/ML 機能 | Cortex AI（限定的） | Mosaic AI（フル） | ML トレーニング / Feature Store は Databricks が強い |

**選定指針**: ゼロコピー + ガバナンスが最優先なら Snowflake。フル AI/ML パイプラインが必要なら Databricks（DataSync 経由）。両者は排他的ではなく、同じ FSx for ONTAP データに対して併用可能。

### 全体像

```
FSx for ONTAP
  │
  ├─── S3 Access Point ───┬── UC External Location ──── ❌ 非サポート
  │                       ├── Athena / EMR / Glue ───── ✅ 動作
  │                       ├── Bedrock KB ────────────── ✅ 動作（公式チュートリアル）
  │                       └── Snowflake External Table ─ ✅ 動作
  │
  ├─── ONTAP S3 ──────────── UC External Location ──── ❌ S3 互換非サポート
  │
  ├─── NFS ───────────────┬── Databricks NFS mount ─── ❌ seccomp ブロック
  │                       ├── DataSync → S3 → UC ───── ✅ 検証済み（推奨）
  │                       └── EMR / Glue 経由 ───────── ✅ 動作
  │
  ├─── SMB ───────────────── Databricks SMB mount ──── ❌ 非サポート
  │
  └─── Kafka（FPolicy 経由）── Structured Streaming ─── ✅ UC Delta テーブル
```

> **補足: Lakehouse Federation** — UC Lakehouse Federation は MySQL / PostgreSQL / SQL Server / Snowflake / Redshift / BigQuery 等への読み取りクエリを UC から発行する機能です。FSx for ONTAP は RDBMS ではないため Federation の直接対象にはなりませんが、ClickHouse（PostgreSQL 互換ポート 9005）経由の Federation は理論上可能です（未検証）。詳細は [Kafka-ClickHouse-UC 接続ガイド](./kafka-clickhouse-unity-catalog-connectivity.md) を参照。

### 接続方法 × ファイルフォーマット クロスマトリクス

| ファイルフォーマット | DataSync→S3→UC | Kafka→SS→UC Delta | Glue/EMR ETL→UC | Foreign Iceberg | boto3 PoC |
|---|:---:|:---:|:---:|:---:|:---:|
| **CSV** | ✅ | ✅（Kafka メッセージ化後） | ✅ | — | ✅（ガバナンスなし） |
| **Parquet** | ✅ | — | ✅ | — | ✅（ガバナンスなし） |
| **JSON** | ✅ | ✅（ネイティブ） | ✅ | — | ✅（ガバナンスなし） |
| **Delta Lake** | ✅（S3上で変換） | ✅（出力先） | ✅ | — | — |
| **Iceberg** | ✅（S3上で変換） | — | ✅ | ✅（Glue REST 経由、検証中） | — |
| **画像 (JPEG/PNG)** | ✅（Volume 登録） | — | ✅（BinaryFile） | — | ✅（ガバナンスなし） |
| **PDF / Office** | ✅（Volume 登録） | — | ✅（BinaryFile） | — | ✅（ガバナンスなし） |
| **動画 (MP4)** | ✅（Volume 登録） | — | ⚠️（大容量注意） | — | ✅（ガバナンスなし） |
| **音声 (WAV/MP3)** | ✅（Volume 登録） | — | ✅（BinaryFile） | — | ✅（ガバナンスなし） |

**凡例**: ✅ = 動作確認済みまたは公式サポート / ⚠️ = 制約あり / — = 非該当

---

## コピー対象と残留データ：具体例

> 「DataSync → S3 → UC」は FSx for ONTAP ボリューム全体を標準 S3 バケットに複製するという意味ではない。実際に書き込まれるのは**分析に必要な構造化サブセット**のみであり、用途に応じて適切な AWS ストレージサービスに格納する。通常はソースボリュームの 1% 未満。

### 本アーキテクチャで使用する S3 関連サービスの区別

| サービス | 本アーキテクチャでの役割 | 書き込まれるデータ |
|---------|----------------------|------------------|
| **FSx for ONTAP S3 Access Points** | READ ソース（NFS/SMB データへのゼロコピーアクセス） | なし — このパイプラインでは読み取り専用 |
| **標準 S3 バケット** | DataSync 同期先 or UC Managed Table（Delta）の書き込み先 | 同期ファイル or Delta テーブルデータファイル |
| **S3 Tables**（Iceberg、自動コンパクション付き） | 構造化メタデータの書き込み先（Iceberg フォーマット） | ETL 抽出済みメタデータ、測定値、AI 分類結果 |
| **S3 Vectors** | ベクトル埋め込みの書き込み先 | Titan Embeddings 出力（セマンティック検索用） |

> **重要**: ETL パイプラインは FSx for ONTAP S3 AP から**読み取り**、**S3 Tables、S3 Vectors、または標準 S3 バケット**のいずれかに**書き込む**。これらは特性が異なる別サービスであり、下流の消費者に応じて選択する。

### 例: 製造業の品質検査（200 ロット/日）

**FSx for ONTAP 上のソースデータ**（NFS/SMB 経由で工場システムがアクセス、S3 AP 経由で ETL が読み取り）:

```
/quality-inspection/2026-06-20/
├── lot-A001-report.pdf          (2.3 MB)   ← 検査レポート PDF
├── lot-A001-image-front.tiff    (15 MB)    ← 外観検査画像
├── lot-A001-image-back.tiff     (14 MB)    ← 外観検査画像
├── lot-A001-measurements.csv    (48 KB)    ← 寸法測定値
└── lot-A001-sensor-log.json     (120 KB)   ← 製造時センサーログ
    (× 200 ロット/日 ≈ 6 GB/日、FSx for ONTAP 上合計)
```

**ETL 出力先別の内訳**:

| 出力先 | テーブル / コレクション | 内容 | サイズ/日 | フォーマット | 下流の消費者 |
|--------|----------------------|------|:--------:|-----------|------------|
| **S3 Tables** | `quality.inspection_metadata` | AI 分類済みメタデータ（ロット単位） | ~100 KB | Iceberg（自動コンパクション） | Athena, EMR, Glue（ネイティブ）; Databricks（Foreign Iceberg / Glue HMS 経由） |
| **S3 Tables** | `quality.measurements` | 測定ポイント別の寸法値 | ~800 KB | Iceberg | 同上 |
| **S3 Vectors** | `quality-embeddings` | ドキュメント埋め込み（1024 次元） | ~800 KB | ベクトルインデックス | Bedrock Knowledge Bases, OpenSearch セマンティック検索 |
| **標準 S3 バケット** | `catalog.schema.sensor_data`（UC） | センサー集計統計 | ~50 KB | Delta（UC Managed Table） | Databricks UC（フルガバナンス: lineage, tags, masks） |

**AWS ストレージへの書き込み合計: ~1.75 MB/日** — **FSx for ONTAP 上のソース 6 GB/日 の 0.03%**

**FSx for ONTAP に残るもの**: 画像（TIFF）、完全な PDF、生センサーログ。ドリルダウンが必要な場合に FSx for ONTAP S3 AP または OpenSharing STS credential vending でオンデマンドアクセス。

### 書き込み先の選び方

| 下流の消費者 | 書き込み先 | 理由 |
|------------|----------|------|
| Athena / EMR / Glue（AWS ネイティブ分析） | **S3 Tables**（Iceberg） | ネイティブ統合、自動コンパクション、テーブル管理不要 |
| Databricks UC（フルガバナンス必要） | **標準 S3 バケット**（Delta、UC Managed Table） | UC は External Location / Managed Table に標準 S3 を要求 |
| セマンティック検索 / RAG / 類似度クエリ | **S3 Vectors** | ベクトル埋め込み専用、Bedrock と統合 |
| Databricks UC AND AWS ネイティブ両方 | **S3 Tables** + UC Foreign Iceberg | S3 Tables（Iceberg）に書き込み; Databricks は Foreign Iceberg（Glue HMS Federation）で読み取り |
| Snowflake | **標準 S3 バケット** or **S3 Tables** | Snowflake は External Stage（標準 S3）or Managed Iceberg（利用者管理の S3）で読み取り |

### 3 つのインジェスト戦略（改訂版）

| 戦略 | 読み取り元 | 書き込み先 | AWS ストレージ上のサイズ | UC ガバナンス | 実装複雑度 |
|------|----------|----------|:------------------:|:---:|:---:|
| **A. 選択的 ETL**（推奨） | FSx for ONTAP S3 AP | S3 Tables + S3 Vectors + 標準 S3（混合） | 最小（ソースの ~0.03%） | フル（出力先ごと） | 中（ETL パイプライン構築要） |
| **B. ファイル種別フィルタリング** | FSx for ONTAP NFS（DataSync 経由） | 標準 S3 バケット | 中程度（対象ファイル分） | フル（COPY INTO → UC Delta） | 低（DataSync + SQL） |
| **C. ボリューム全量同期** | FSx for ONTAP NFS（DataSync 経由） | 標準 S3 バケット | 高（= ソースボリューム） | External Table（読み取り専用）or 選択的 COPY INTO | 最低（DataSync のみ） |

### 戦略 A: 選択的 ETL パイプライン（推奨）

```
FSx for ONTAP (6 GB/日、全ファイル種別)
    │
    ▼ FSx for ONTAP S3 AP 経由で読み取り（or OpenSharing STS credential vending）
ETL (Databricks Job / Glue / Lambda)
    │
    ├── CSV → パース → S3 Tables (Iceberg): measurements テーブル
    ├── JSON → 集計 → S3 Tables (Iceberg): sensor_summary テーブル
    ├── PDF → Bedrock AI → S3 Tables (Iceberg): metadata テーブル
    ├── PDF/画像 → Titan Embeddings → S3 Vectors: セマンティックインデックス
    └── TIFF → 参照 URI のみメタデータに記録（ファイルコピーなし）
    │
    ▼ （オプション）Databricks UC 消費者向け:
標準 S3 バケット → UC Managed Delta Table（センサー集計）
    or
S3 Tables → Glue Catalog → UC Foreign Iceberg（追加コピーなし）
```

ソースの画像・ドキュメントは FSx for ONTAP に残る。AWS ストレージサービスには**派生した構造化・分析可能データ**のみが格納され、生ファイルのコピーではない。

### 戦略 B: DataSync のファイル種別フィルタリング

DataSync は FSx for ONTAP NFS から選択したファイルを標準 S3 バケットにコピーする:

```bash
# CSV と Parquet のみ同期（画像・PDF はスキップ）
aws datasync create-task \
  --source-location-arn <SRC> \
  --destination-location-arn <DST> \
  --includes '[{"FilterType":"SIMPLE_PATTERN","Value":"*.csv"},{"FilterType":"SIMPLE_PATTERN","Value":"*.parquet"}]'
```

Databricks 側（標準 S3 バケットから読み取り、UC Managed Delta に書き込み）:
```sql
COPY INTO quality.measurements
FROM 's3://<STANDARD-BUCKET>/quality-inspection/'
FILEFORMAT = CSV
PATTERN = '*/measurements.csv';
```

### 戦略 C: ボリューム全量同期（最シンプル・最高コスト）

DataSync が FSx for ONTAP NFS の全ファイルを標準 S3 バケットにコピーする。全ファイル種別へのアクセスが分析に必要な場合（例: 画像 ML トレーニング）のみ適切。この場合でも、External Table（読み取り専用）を作成し、全てを Delta 変換するのではなく必要部分だけ `COPY INTO` することを推奨。

---

## 推奨パス詳細

### パス 1: DataSync → S3 → UC（推奨・本番向け）

**唯一の検証済み本番パス。FSx for ONTAP NFS → S3 定期同期 → UC External/Managed テーブル。**

```
FSx for ONTAP (NFS)
  ↓ AWS DataSync (rate(5 minutes) ～ daily)
Amazon S3 bucket (標準)
  ↓
UC External Location (Storage Credential + IAM Role)
  ↓
UC External Table / Managed Table / Volume
```

**手順概要** ([詳細ガイド](./datasync-to-s3-guide.md)):

```bash
# 1. DataSync ソース (FSx for ONTAP NFS)
aws datasync create-location-fsx-ontap \
  --storage-virtual-machine-arn <SVM_ARN> \
  --protocol NFS={} \
  --subdirectory /vol1/data/

# 2. DataSync 宛先 (S3)
aws datasync create-location-s3 \
  --s3-bucket-arn arn:aws:s3:::<BUCKET> \
  --s3-config BucketAccessRoleArn=<ROLE_ARN>

# 3. DataSync タスク
aws datasync create-task \
  --source-location-arn <SRC> \
  --destination-location-arn <DST> \
  --options '{"TransferMode":"CHANGED","PreserveDeletedFiles":"REMOVE"}'

# 4. スケジュール
aws datasync update-task --task-arn <TASK> \
  --schedule ScheduleExpression="rate(5 minutes)"
```

> **注意**: `rate(5 minutes)` は小規模環境向け。大量ファイル環境ではタスク重複（前回未完了のまま次回起動）のリスクがあるため、実環境では `rate(15 minutes)` 〜 `rate(1 hour)` を推奨。ファイル数が数万件を超える場合はフィルタで対象を分割し、複数タスクに分離すること。

> **帯域見積もり**: DataSync の同期時間は FSx for ONTAP のスループットキャパシティ + VPC ネットワーク帯域で制約されます。事前に見積もりを実施してください:
> - 例: 100GB のデータ、1Gbps 帯域 → 理論値 ~13 分（実効 60-70% で ~20 分）
> - VPC のジャンボフレーム（MTU 9001）を有効化することで NFS スループットが大幅改善
> - FSx for ONTAP のスループットキャパシティ（128MB/s〜4GB/s）がボトルネックになる場合あり

> **IAM 最小権限**: DataSync の実行 IAM Role は以下に制限してください:
> - S3 宛先: `s3:PutObject`, `s3:DeleteObject`, `s3:GetBucketLocation` のみ（リソース ARN を特定バケット/プレフィックスに制約）
> - FSx for ONTAP ソース: `fsx:DescribeFileSystems`, `datasync:*` の必要最小限
> - `s3:*` や `fsx:*` のワイルドカード権限は使用禁止

```sql
-- 5. UC External Location 登録
CREATE EXTERNAL LOCATION fsxn_synced
  URL 's3://<BUCKET>/fsxn-sync/'
  WITH (STORAGE CREDENTIAL <credential_name>);

-- 6. テーブル作成
CREATE TABLE catalog.schema.sensor_data
USING DELTA
AS SELECT * FROM parquet.`s3://<BUCKET>/fsxn-sync/sensor-data/`;
```

**適用シナリオ**: 構造化データの定期分析、ML 訓練データ、レポーティング

> **推奨: Snapshot からの同期**: 本番ボリュームから直接 DataSync すると、同期中のファイル変更でデータ不整合が生じるリスクがあります。推奨は「Snapshot → FlexClone → DataSync」パターン:
> 1. Snapshot を取得（一貫性のある時点コピー）
> 2. FlexClone を作成（瞬時・ゼロコピー）
> 3. FlexClone に対して DataSync を実行
> 4. 同期完了後に FlexClone を削除
>
> これにより、業務への影響ゼロかつデータ一貫性を保証した同期が可能です。

> **Auto Loader との組み合わせ** (Data Engineering SA findings): DataSync で S3 に同期した後、**Auto Loader** で差分取り込みすることで増分処理を効率化できます。さらに **DLT (Spark Declarative Pipelines)** でストリーミングテーブルとして定義すると、monitoring / error handling / schema evolution が自動化されます:
> ```python
> # DLT パイプライン定義
> import dlt
>
> @dlt.table
> def sensor_data():
>     return (spark.readStream
>         .format("cloudFiles")  # Auto Loader
>         .option("cloudFiles.format", "parquet")
>         .load("s3://<BUCKET>/fsxn-sync/sensor-data/")
>     )
> ```

> **Medallion アーキテクチャ対応**: DataSync → S3 は **Bronze 層**（raw データ）として位置づけ。Silver（クレンジング済み）/ Gold（ビジネス集計）への変換は DLT で定義します:
> ```
> Bronze: DataSync → S3 (raw files) → Auto Loader → streaming_table
> Silver: DLT 品質チェック (expectations: null/範囲/参照整合性) + スキーマ正規化
> Gold:   DLT 集計 + ビジネスロジック + Liquid Clustering + OPTIMIZE (BI クエリ高速化)
> ```

> **Auto Loader モード選択**: DataSync 先の S3 バケットでは **S3 Event Notifications** が利用可能（FSx for ONTAP S3 AP では不可だが、標準 S3 バケットでは対応）。Auto Loader は **ファイル通知モード**（SQS 経由）を推奨 — ディレクトリリスティングモード比でスキャンコストを大幅削減。

---

### パス 2: Kafka → Structured Streaming → UC Delta（リアルタイム向け）

**FPolicy でファイル変更を検出し、Lambda 経由で Kafka に送信、Databricks で UC Delta テーブルに書き込み。**

```
FSx for ONTAP
  ↓ FPolicy (ファイル操作イベント検出)
AWS Lambda
  ↓ Kafka Producer
Amazon MSK (Kafka)
  ↓ Structured Streaming (DBR 16.1+, UC service credentials)
UC-managed Delta Table
```

**手順概要** ([詳細ガイド](./kafka-clickhouse-unity-catalog-connectivity.md)):

```python
# Databricks Structured Streaming
df = (spark.readStream
  .format("kafka")
  .option("kafka.bootstrap.servers", "<MSK_BOOTSTRAP>")
  .option("subscribe", "fsxn-events")
  .option("kafka.security.protocol", "SASL_SSL")
  .option("kafka.sasl.mechanism", "AWS_MSK_IAM")
  .load()
)

# UC-managed Delta テーブルに書き込み
(df.selectExpr("CAST(value AS STRING) as json_payload")
  .writeStream
  .format("delta")
  .option("checkpointLocation", "/Volumes/catalog/schema/checkpoints/")
  .toTable("catalog.schema.fsxn_events")
)
```

**適用シナリオ**: イベント駆動インジェスト、ニアリアルタイム品質検査、ストリーミング ETL

> **注意: FPolicy はメタデータイベントのみ**: FPolicy はファイル**操作イベント**（作成・更新・削除・リネーム）を検出しますが、ファイル**内容**を転送しません。典型的な設計パターン:
> - **Kafka メッセージ**: メタデータのみ（ファイルパス、サイズ、操作タイプ、タイムスタンプ）
> - **ペイロード読み取り**: Databricks Spark が S3 AP 経由で直接ファイル内容を読み取り（UC 外パス）、または DataSync で S3 に同期済みのコピーを読み取り
>
> 大容量ファイル（動画等）の場合、Lambda の 15 分タイムアウト / 10GB メモリ上限に注意。大容量ペイロードは DataSync パスとの併用を推奨。

> **製造現場でのデータ起点**: PLC / SCADA は通常 Kafka Producer としてデータを送信する機能を持ちません。典型的な製造環境のデータフローは:
> ```
> PLC / SCADA → NFS/SMB 書き込み → FSx for ONTAP → FPolicy 検出 → Lambda → Kafka
> ```
> FPolicy は「ファイルが書かれた後」のイベント検出であり、PLC からの直接ストリーミングではありません。
> OT ネットワーク（FSx for ONTAP 配置）と IT ネットワーク（Databricks / MSK 配置）が分離されている場合、Transit Gateway / VPC Peering 経由で Lambda / DataSync の通信パスを設計する必要があります。

> **産業プロトコル経由のデータフロー**: 実際の製造現場では、PLC がファイルを直接書き出すよりも、中間層を経由するパターンが一般的です:
> ```
> パターン A: PLC → OPC UA サーバー → ヒストリアン → CSV/Parquet エクスポート → FSx for ONTAP (NFS)
> パターン B: PLC → MQTT ブローカー (Sparkplug B) → Kafka Bridge → MSK → UC Delta
> パターン C: PLC → AWS IoT SiteWise Edge → FSx for ONTAP (NFS) → FPolicy / DataSync
> パターン D: PLC → AWS IoT Greengrass (Lambda@Edge) → FSx for ONTAP (NFS) → DataSync → S3 → UC
> ```
> PLC 出力はバイナリ独自フォーマット（.dat, .bin）の場合もあり、CSV/JSON への変換パーサーの開発が必要な場合があります。

> **OT/IT セキュリティ境界**:
> - **Purdue Level 3.5 (IDMZ)**: FPolicy Lambda や DataSync エージェントは Level 3.5（Industrial DMZ）に配置し、OT (Level 0-3) と IT (Level 4-5) を直接接続しない設計を推奨
> - **IDMZ 許可ポート**: NFS 2049 (FSx for ONTAP → DataSync)、HTTPS 443 (Lambda → MSK IAM / DataSync → S3)、Kafka 9094-9098 (Lambda → MSK TLS/IAM)
> - **IEC 62443 準拠環境**: NFS 通信は `krb5p`（Kerberos 暗号化）を使用し、IDMZ 経由のコンジットで通信チャネル要件を満たすこと
> - **暗号化**: DataSync は TLS (in-transit) + S3 SSE-KMS (at-rest)。FSx for ONTAP 側は volume encryption (at-rest) + NFS krb5p (in-transit)。規制産業（GxP, ITAR）ではこの暗号化チェーンの文書化が必要
> - **データダイオード環境**（高セキュリティ要件時）: FSx for ONTAP → S3 への片方向 DataSync フローはデータダイオードの論理的代替として機能する
> - **監査ログ 4 層** (Security Audit Analyst findings): データフロー全体で 4 層の監査ログが発生。インシデント時の相関分析を事前設計すること:
>   1. ONTAP FPolicy / audit log（ファイル操作）
>   2. DataSync CloudTrail（転送操作）
>   3. S3 access logs / CloudTrail data events（オブジェクト操作）
>   4. UC audit logs（テーブルアクセス、クエリ）
> - **証拠保全**: セキュリティインシデント発生時、FSx for ONTAP の **SnapLock** で改ざん不可能な Snapshot を保全可能。フォレンジック用データの完全性を WORM (Write Once Read Many) で保証
> - **Secrets 管理**: Lakehouse Federation で外部 DB に接続する際のパスワードは **Databricks Secrets** (`secret('scope', 'key')` 関数) で管理。コード内平文記載禁止。AWS Secrets Manager 連携も可

> **DLT / CDC パターン** (Data Engineering SA findings):
> - **DLT (Streaming Table)**: 本番環境では Structured Streaming を直接書く代わりに DLT で定義することを推奨。monitoring, error handling, schema evolution が組み込み。
> - **CDC (Change Data Capture)**: PostgreSQL / MySQL のマスタデータ変更をリアルタイムに UC Delta に反映する場合、**Debezium → Kafka → DLT** パターンが有効:
>   ```
>   EC2 PostgreSQL (on FSx for ONTAP) → Debezium Connector → MSK → DLT Streaming Table → UC Delta
>   ```
>   製造マスタデータ（製品マスタ、設備台帳）の変更をリアルタイムに分析基盤に反映するユースケースに適用。

> **配信保証と重複排除**: FPolicy → Lambda → Kafka パスは **at-least-once** 配信です。ネットワーク再送やLambdaリトライにより重複イベントが発生する可能性があるため、UC Delta テーブル側で **event_id による重複排除（MERGE / dedup）** を設計してください:
> ```sql
> MERGE INTO catalog.schema.fsxn_events AS target
> USING (SELECT * FROM stream_batch) AS source
> ON target.event_id = source.event_id
> WHEN NOT MATCHED THEN INSERT *;
> ```

> **Zerobus Ingest vs Kafka 選定基準**:
>
> | 軸 | Zerobus Ingest | Kafka (MSK) |
> |---|---|---|
> | 管理 | Databricks フルマネージド | ユーザー管理 or MSK マネージド |
> | レイテンシ | サブ秒（Databricks 内直接） | 秒〜（Spark Streaming 経由） |
> | 外部コンシューマー | ❌ Databricks のみ | ✅ 複数コンシューマー（ClickHouse 等） |
> | エッジからの接続 | HTTPS REST / SDK | Kafka プロトコル（9094等） |
> | 既存 Kafka 基盤 | 不要 | あれば活用 |
> | 適用シナリオ | Databricks のみで消費する IoT イベント | 複数システムでファンアウト |
>
> **選定指針**: Databricks のみで消費するなら Zerobus。ClickHouse 等の他システムにもファンアウトが必要なら Kafka。両方使う（Kafka + Zerobus → 別テーブル）設計も有効。

---

### パス 3: Glue / EMR ETL → UC（バッチ変換向け）

**AWS Glue または EMR が FSx for ONTAP S3 AP から直接読み取り、S3 上に Delta/Parquet を書き込み。**

```
FSx for ONTAP (S3 AP)
  ↓ Glue ETL Job / EMR Spark
Amazon S3 (Delta / Parquet)
  ↓
UC External Location → Table
```

**公式チュートリアル**:
- [AWS Glue + FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html)
- [EMR Serverless + FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-run-spark-with-emr-serverless.html)

**適用シナリオ**: 大規模バッチ変換、スキーマ変換、データ品質チェック

---

### パス 4: Foreign Iceberg（Glue REST 経由、検証中）

**FSx for ONTAP データを Iceberg テーブル化し、Glue Iceberg REST endpoint 経由で UC Foreign Catalog に公開。**

```
FSx for ONTAP (S3 AP)
  ↓ PyIceberg / Glue (Iceberg テーブル書き込み)
S3 Tables / Glue Catalog (Iceberg メタデータ)
  ↓ Iceberg REST endpoint
UC Foreign Catalog (読み取り専用)
```

**ステータス**: ❌ **ブロック確認済み（2026-06-21）**。`iceberg_rest` connection type が ap-northeast-1 ワークスペースで非対応。S3 Tables マネージドバケットの UC External Location 登録も不可。([検証結果](../../integrations/iceberg-metadata-catalog/databricks/uc-foreign-iceberg-validation.md#validation-execution-results-2026-06-21))

> **運用注記**: `REFRESH FOREIGN TABLE` は自動実行されません（Databricks は外部 Iceberg のメタデータ更新を自動検知しない）。定期的なリフレッシュが必要な場合は **Databricks Workflow** でスケジュールジョブを設定してください。

---

### パス 5: ClickHouse → UC（DataLakeCatalog、逆方向読み取り）

**ClickHouse が UC の Delta/Iceberg テーブルを credential vending 経由で読み取り。**

FSx for ONTAP のデータが UC Delta テーブルに取り込まれた後、ClickHouse からも同じデータを UC ガバナンス下で参照可能。

```sql
-- ClickHouse 側
CREATE DATABASE uc_delta
ENGINE = DataLakeCatalog('unity', '<WORKSPACE_URL>', '<TOKEN>')
SETTINGS catalog_type = 'unity';

SELECT * FROM uc_delta.catalog.schema.sensor_data LIMIT 10;
```

**詳細**: [Kafka-ClickHouse-UC 接続ガイド](./kafka-clickhouse-unity-catalog-connectivity.md)

---

## 検証ステータスサマリ

| パス | ステータス | 検証日 | エビデンス |
|------|-----------|--------|-----------|
| S3 AP → UC External Location | ❌ **非サポート確認** | 2026-05-26 | Databricks Support 回答 |
| ONTAP S3 → UC External Location | ❌ **非サポート確認** | 2026-05 | 02_research_findings.md |
| NFS mount from Databricks | ❌ **ブロック** | 2026-05 | seccomp 制限 |
| DataSync → S3 → UC | ✅ **検証済み** | 2026-05 | datasync-to-s3-guide.md |
| Kafka → Structured Streaming → UC | ✅ **設計検証済み** | 2026-06 | [kafka-clickhouse-unity-catalog-connectivity.md](./kafka-clickhouse-unity-catalog-connectivity.md) |
| Glue/EMR → S3 → UC | ✅ **公式チュートリアル** | — | AWS 公式ドキュメント |
| Foreign Iceberg (Glue REST) | ❌ **ブロック確認** | 2026-06-21 | `iceberg_rest` type 非対応 + S3 Tables バケット EL 登録不可 |
| boto3 PoC (ガバナンスなし) | ✅ **動作確認** | 2026-05 | ai-demo-guide.md |
| S3 AP → Athena (UC 外) | ✅ **動作確認** | 2026-04 | S3 AP Serverless Patterns repo |
| S3 AP → Bedrock KB (UC 外) | ✅ **公式チュートリアル** | — | AWS 公式ドキュメント |

---

## DAIS 2026 発表の影響整理

| DAIS 2026 発表 | FSx for ONTAP → UC 接続への影響 | 説明 |
|---|---|---|
| **OpenSharing** | ❌ 直接解決しない | 共有プロトコル。ストレージ接続ではない |
| **Delta Sharing Iceberg IRC** | ❌ 直接解決しない | テーブル共有。前提としてテーブルが UC 内に存在する必要がある |
| **LTAP / Lakebase** | ❌ 直接解決しない | Operational DB。FSx for ONTAP とは異なるストレージ層 |
| **Lakehouse//RT** | ❌ 直接解決しない | クエリエンジン。FSx for ONTAP に対して動作しない |
| **Document Intelligence** | ⚠️ 間接的に利用可能 | S3 経由でドキュメントを取り込めば利用可能 |
| **Lakeflow Zerobus Ingest** | ⚠️ 間接的に利用可能 | Kafka 代替。ap-northeast-1 対応。ただし入力は Databricks 側 |
| **Unity AI Gateway** | ❌ 関連なし | エージェント/モデルのガバナンス。ストレージ接続ではない |
| **Agent Bricks** | ❌ 関連なし | エージェント実行基盤。ストレージ接続ではない |
| **UC Foreign Iceberg GA** | ❌ **ブロック確認（2026-06-21）** | `iceberg_rest` type が ap-northeast-1 で非対応。S3 Tables マネージドバケットの UC External Location 登録も不可。Databricks Support への確認が必要 |
| **OpenSharing SecureConnect** | ⚠️ 間接的に利用可能 | UC テーブル化後の外部共有をセキュア化。受信者ごとの FW 変更不要（プロバイダー側 1 回設定のみ）。FSx for ONTAP データの S3 → UC → 外部組織共有パスのセキュリティを強化 |

---

## なぜ直接接続できないのか: 技術的理由

### UC External Location のセッションポリシー制約

Databricks が IAM Role を AssumeRole する際、内部的に**セッションポリシー**を生成します。このポリシーは以下を前提として構築されます:

1. ストレージパスが `s3://<bucket-name>/prefix/` 形式であること
2. `arn:aws:s3:::<bucket-name>` が有効な S3 バケット ARN であること
3. ListObjectsV2 / GetObject / PutObject が標準 S3 API で動作すること

S3 Access Point の場合:
- パスは `s3://<access-point-alias>/prefix/` 形式
- ARN は `arn:aws:s3:region:account:accesspoint/name`
- セッションポリシーのリソース制約が S3 AP ARN を正しく処理しない

**結果**: トップレベルの操作は一部成功するが（副作用）、サブディレクトリ操作・テーブル作成・書き込みはすべて `AccessDenied` になる。

### NFS/SMB マウントの制約

Databricks ランタイムは Docker コンテナ上で動作し、**seccomp（Secure Computing Mode）プロファイル**が `mount` / `umount` システムコールを禁止しています。これは:
- カーネル NFS マウント (`mount -t nfs`) → ブロック
- FUSE マウント (`s3fs`, `nfs-ganesha`) → ブロック
- SMB マウント (`mount -t cifs`) → ブロック

この制約はセキュリティ上の設計であり、回避策はありません。

### ONTAP S3 の制約

ONTAP S3 は S3 API 互換プロトコルを提供しますが:
- カスタムエンドポイント URL を UC External Location に指定する API が存在しない
- UC は `s3://<bucket-name>/` 形式のパスのみを受け付け、カスタム S3 エンドポイントを指定する `endpoint_url` パラメータがない

---

## 選択ガイド: ユースケース別推奨

```
Q: データの鮮度要件は？
│
├── リアルタイム（秒単位） ─── パス 2: Kafka → Structured Streaming
│
├── ニアリアルタイム（分単位）─── パス 1: DataSync (rate(5 min)) → UC
│
├── バッチ（時間〜日単位） ──── パス 1: DataSync (daily) or パス 3: Glue/EMR
│
└── アドホック分析 ──────────── Athena + S3 AP（UC 不要）or boto3 PoC
```

```
Q: ガバナンス要件は？
│
├── UC フルガバナンス必須 ─── パス 1 or 2（S3 経由で UC テーブル化）
│
├── AWS 側ガバナンスで十分 ── Athena + S3 AP + IAM ポリシー
│
├── Snowflake ガバナンス ──── Snowflake External Table（S3 AP 直接対応）
│
└── ガバナンス不要（PoC） ── boto3 PoC（Instance Profile）
```

```
Q: データコピーを許容するか？
│
├── コピー許容 ─── パス 1 (DataSync) / パス 2 (Kafka) / パス 3 (ETL)
│
├── コピー最小化 ── UC Foreign Iceberg（検証中）/ Athena（UC 外）
│
└── ゼロコピー必須 ── UC では現時点で不可。Athena or Snowflake を推奨
```

---

## 段階的導入推奨ステップ

(Manufacturing IT/OT Convergence Program Manager findings)

大規模製造環境では全パスを一度に実装するのではなく、段階的に導入することを推奨します:

| Phase | 内容 | 期間目安 | 成功基準 |
|-------|------|---------|---------|
| **1. PoC** | DataSync → S3 → UC テーブル（1 ボリューム、構造化データのみ） | 2-4 週 | UC でクエリ可能、データ鮮度 OK |
| **2. 本番化** | DataSync スケジュール最適化 + Auto Loader + DLT (medallion) | 4-8 週 | Bronze/Silver/Gold パイプライン稼働 |
| **3. リアルタイム追加** | FPolicy → Lambda → Kafka → SS → UC Delta（イベント駆動） | 4-8 週 | ニアリアルタイムイベント取り込み |
| **4. AI/ML 統合** | UC Volume + Feature Store + AI Search + Bedrock KB | 4-12 週 | ML パイプライン稼働 |
| **5. マルチシステム拡張** | Lakehouse Federation (EC2 DB) + ClickHouse 連携 | 4-8 週 | 統合分析ビュー |

> **注意**: Phase 1-2 はほぼすべての環境に適用。Phase 3 以降はユースケース駆動で選択的に実装。

---

## EC2 セルフマネージド DB × FSx for ONTAP × UC 接続パターン

### 概要

EC2 上でセルフマネージドの DB/ストリーミング基盤を動かし、FSx for ONTAP をそのデータストアとして利用した場合、Databricks UC とどう接続するかを整理します。

### UC Lakehouse Federation 対応データベース

UC Lakehouse Federation は JDBC 経由で外部 DB に対して**プッシュダウンクエリ**を実行し、UC ガバナンス下で読み取りを行う機能です。以下のデータベースが公式にサポートされています:

| データベース | Federation ステータス | EC2 セルフマネージド | FSx for ONTAP をデータストアに | UC 接続方式 |
|---|:---:|:---:|:---:|---|
| **PostgreSQL** | ✅ GA | ✅ | ✅ NFS マウント可 | `CREATE CONNECTION TYPE postgresql` |
| **MySQL** | ✅ GA | ✅ | ✅ NFS マウント可 | `CREATE CONNECTION TYPE mysql` |
| **SQL Server** | ✅ GA | ✅ | ⚠️ SMB のみ（Linux 版は NFS 可） | `CREATE CONNECTION TYPE sqlserver` |
| **Oracle** | ✅ Public Preview | ✅ | ✅ NFS（ASM 不可、FS ベースのみ） | `CREATE CONNECTION TYPE oracle` |
| **Teradata** | ✅ Public Preview | ✅ | ⚠️ 限定的（独自ストレージ推奨） | `CREATE CONNECTION TYPE teradata` |
| **Snowflake** | ✅ GA | — (SaaS) | — | `CREATE CONNECTION TYPE snowflake` |
| **Redshift** | ✅ GA | — (マネージド) | — | `CREATE CONNECTION TYPE redshift` |
| **BigQuery** | ✅ GA | — (SaaS) | — | `CREATE CONNECTION TYPE bigquery` |
| **Databricks** | ✅ GA | — | — | `CREATE CONNECTION TYPE databricks` |

> **重要な制約**:
> - Lakehouse Federation は**読み取り専用**です。UC から外部 DB への INSERT / UPDATE / DELETE は実行できません。外部 DB へのデータ投入は別途設計が必要です。
> - **ネットワーク前提条件**: EC2 DB がプライベートサブネットにある場合、Databricks serverless compute からの接続には **NCC (Network Connectivity Config)** または **PrivateLink** の設定が必要です。Classic compute の場合は VPC Peering / Transit Gateway で対応。
>   - NCC 制限値（AWS）: アカウントあたり最大 10 NCC / リージョン、30 Private Endpoints / リージョン
>   - NCC コスト: Private Endpoint 時間課金 + データ処理量（GB）課金が発生
> - **クエリ特性**: Federation は JDBC プッシュダウンのため、大量データの全件スキャン分析には不向きです。フィルタリング / ルックアップ / 小〜中規模の集計クエリに最適化されています。大規模分析にはパス 1（DataSync → UC Delta）を推奨。
> - **プッシュダウン非対応操作** (Federation Query Optimizer findings): WINDOW 関数、複雑な UDF、一部の LIKE パターン（先頭ワイルドカード `%abc`）等はプッシュダウンされず、全行がネットワーク越しに転送されて性能劣化します。`EXPLAIN` でクエリプランを確認し、PushedFilters / PushedAggregates を検証してください。

### FSx for ONTAP をデータストアにできる EC2 セルフマネージド DB

| DB / ミドルウェア | データディレクトリ | FSx for ONTAP プロトコル | 実用性 | UC 接続方式 |
|---|---|---|:---:|---|
| **PostgreSQL** | `data_directory` | NFS | ✅ 推奨 | Lakehouse Federation (JDBC) |
| **MySQL / MariaDB** | `datadir` | NFS | ✅ 推奨 | Lakehouse Federation (JDBC) |
| **MongoDB** | `dbPath` | NFS | ⚠️ 動作するが WiredTiger journal の fsync チューニング要。**Lakehouse Federation 非対応**（Spark MongoDB Connector のみ） | Spark MongoDB Connector → UC Delta |
| **ClickHouse** | `path` | NFS / ONTAP S3 (cold tier) | ✅ 動作確認済み | DataLakeCatalog (UC → CH) / 逆方向のみ |
| **Kafka** | `log.dirs` | NFS | ⚠️ レイテンシ増加を許容する場合 | Structured Streaming → UC Delta |
| **Redis / Valkey** | RDB/AOF ファイル | NFS | ⚠️ 永続化のみ（キャッシュ主体） | Spark Redis Connector → UC Delta |
| **Elasticsearch / OpenSearch** | `path.data` | NFS | ❌ data 非推奨（[公式非サポート](https://www.elastic.co/guide/en/elasticsearch/reference/current/storage-types.html)、translog 破損リスク）。✅ Snapshot リポジトリとしては NFS 利用可 | Spark ES Connector → UC Delta |
| **Apache Cassandra** | `data_file_directories` | NFS | ❌ 非推奨（ローカル SSD 前提設計） | Spark Cassandra Connector → UC Delta |
| **Neo4j** | `dbms.directories.data` | NFS | ⚠️ 小規模のみ | Spark Neo4j Connector → UC Delta |
| **InfluxDB** | `data-dir` | NFS | ⚠️ 小規模のみ | Spark JDBC (Flux SQL) → UC Delta |
| **TimescaleDB** | `data_directory` (PG 拡張) | NFS | ✅ PostgreSQL と同じ（Federation 対応）| Lakehouse Federation (JDBC) — PostgreSQL と同一パス |
| **Apache Druid** | `druid.storage.*` | NFS (deep storage) / ONTAP S3 | ✅ deep storage として適合（ONTAP S3 使用時は `druid.storage.baseKey` + カスタム endpoint URL 設定が必要） | Spark JDBC → UC Delta |
| **Apache Pinot** | segment store | NFS / ONTAP S3 | ⚠️ deep storage として検討可 | Spark Connector → UC Delta |
| **MinIO** | `MINIO_VOLUMES` | NFS / ブロックストレージ | ✅ | S3 互換 → Spark 読み取り → UC Delta |

### DB × FSx for ONTAP × UC の接続パターン分類

```
パターン A: Lakehouse Federation（JDBC プッシュダウン）
  EC2 DB (PostgreSQL/MySQL/SQL Server/Oracle)
    ↑ data on FSx for ONTAP (NFS/SMB)
    ↓ JDBC
  Databricks UC Foreign Catalog
    → UC ガバナンス適用（tags, row filters, lineage）
    → データ移動なし（クエリ時にリモート実行）

パターン B: Structured Streaming → UC Delta
  EC2 ストリーミング基盤 (Kafka/Pulsar)
    ↑ log on FSx for ONTAP (NFS)
    ↓ Kafka protocol
  Databricks Structured Streaming
    → UC-managed Delta テーブルに書き込み
    → ニアリアルタイム

パターン C: Spark Connector → UC Delta（バッチ ETL）
  EC2 DB (MongoDB/Cassandra/Elasticsearch/Redis)
    ↑ data on FSx for ONTAP (NFS)
    ↓ 専用 Spark Connector (JDBC/API)
  Databricks ETL Job
    → UC-managed Delta テーブルに書き込み
    → バッチ（スケジュール実行）

パターン D: 逆方向読み取り（外部エンジン → UC）
  EC2 DB (ClickHouse)
    ↓ UC Iceberg REST / credential vending
  Databricks UC Delta/Iceberg テーブルを読み取り
    → UC ガバナンス下で外部エンジンがデータ消費
```

### Kafka × FSx for ONTAP の詳細

| 観点 | NFS (FSx for ONTAP) | ローカル EBS |
|------|---------------------|-------------|
| レイテンシ | +1-3ms（ネットワーク越し） | ~0.1ms |
| `log.dirs` 利用 | ✅ 動作 | ✅ 推奨 |
| Snapshot による復旧 | ✅ ブローカー全体の PIT リカバリ | EBS Snapshot（AZ 内） |
| SnapMirror DR | ✅ クロスリージョン | EBS は AZ 内、別途設計要 |
| 複数ブローカーで共有 | ❌ 非推奨（パーティション排他前提） | — |
| MSK 利用 | ❌ 不可（マネージドストレージ固定） | — |
| Tiered Storage | FabricPool で cold セグメントを S3 に自動階層化 | Kafka 独自 Tiered Storage |

**推奨パターン**:
- **レイテンシ重視（本番ストリーミング）**: EBS (io2/gp3) + Kafka MirrorMaker 2 for DR
- **データ保護・運用統合重視**: FSx for ONTAP NFS + Snapshot/SnapMirror（レイテンシ許容時）
- **ハイブリッド**: ホットデータ = EBS、コールドセグメント = FSx for ONTAP (FabricPool 経由で S3 tier)

### ClickHouse × FSx for ONTAP の詳細

**storage_policy による階層化設計**:

```xml
<!-- ClickHouse storage_policy 設定例 -->
<storage_configuration>
  <disks>
    <hot>
      <type>local</type>
      <path>/var/lib/clickhouse/</path> <!-- ローカル SSD -->
    </hot>
    <cold>
      <type>s3</type>
      <endpoint>https://<SVM_S3_ENDPOINT>:443/<BUCKET>/</endpoint>
      <access_key_id>***</access_key_id>
      <secret_access_key>***</secret_access_key>
    </cold>
  </disks>
  <policies>
    <tiered>
      <volumes>
        <hot><disk>hot</disk></hot>
        <cold><disk>cold</disk></cold>
      </volumes>
      <move_factor>0.1</move_factor> <!-- 10% 使用で cold に移動 -->
    </tiered>
  </policies>
</storage_configuration>
```

**UC との接続 — DataLakeCatalog の type 使い分け**:
- `catalog_type = 'unity'` → UC 上の **Delta テーブル**を読み取り
- `catalog_type = 'rest'` → UC Iceberg REST endpoint 経由で **Iceberg テーブル**を読み取り

```sql
-- Delta テーブル読み取り
CREATE DATABASE uc_delta ENGINE = DataLakeCatalog('unity', '<URL>', '<TOKEN>')
SETTINGS catalog_type = 'unity';

-- Iceberg テーブル読み取り
CREATE DATABASE uc_iceberg ENGINE = DataLakeCatalog('rest', '<URL>', '<TOKEN>')
SETTINGS catalog_type = 'rest';
```

> **⚠️ ClickHouse Keeper / ZooKeeper は FSx for ONTAP 非推奨**: Keeper のトランザクションログは極低レイテンシ（<1ms）の fsync が必須です。NFS 越しの 1-3ms 追加レイテンシはクラスター全体のレプリケーション性能に影響します。Keeper / ZK データは**ローカル SSD (io2)** に配置してください。

### PostgreSQL / MySQL × FSx for ONTAP の詳細

PostgreSQL と MySQL は FSx for ONTAP NFS 上で**最も推奨度が高い**組み合わせです:

- PostgreSQL: `data_directory = '/mnt/fsxn/pgdata'` → WAL / テーブルスペースを NFS 上に配置可能
- MySQL: `datadir = /mnt/fsxn/mysql` → InnoDB テーブルスペースを NFS 上に配置可能

> **NFS マウントオプション推奨** (NFS Performance Architect / PostgreSQL DBA findings):
> ```bash
> # DB ワークロード向け FSx for ONTAP NFS マウント
> mount -t nfs4.1 <SVM_NFS_LIF>:/vol1/pgdata /mnt/fsxn/pgdata \
>   -o hard,nointr,rsize=1048576,wsize=1048576,noac,nfsvers=4.1
> ```
> - `nfsvers=4.1`: セッショントランキング + 委任による性能改善
> - `noac`: 属性キャッシュ無効化（DB の write-read 一貫性確保）
> - `hard`: サーバー無応答時に無限リトライ（データ破損防止）
> - `rsize/wsize=1048576`: 1MB I/O（スループット最大化）

> **MySQL 固有注記**: NFS 上では `innodb_flush_method = fsync` を推奨。`O_DIRECT` は NFS で正しく動作しない場合があります。

> **Lakebase 移行オプション**: PostgreSQL ワークロードが UC ガバナンスと統合を最優先する場合、**Databricks Lakebase**（マネージド PostgreSQL 互換 DB、GA）への移行も選択肢です。Lakebase は UC ネイティブ統合 + Lakehouse//RT クエリ + Private Link を提供しますが、ap-northeast-1 非対応（2026-06-18 現在）に注意。

**UC 接続**:
```sql
-- Databricks 側
CREATE CONNECTION pg_on_fsxn TYPE postgresql
OPTIONS (
  host = '<EC2_PRIVATE_IP>',
  port = '5432',
  user = 'readonly_user',
  password = secret('scope', 'pg_password')
);

CREATE FOREIGN CATALOG pg_catalog
USING CONNECTION pg_on_fsxn
OPTIONS (database = 'manufacturing');

-- クエリ（プッシュダウン実行）
SELECT * FROM pg_catalog.public.sensor_readings
WHERE timestamp > '2026-06-01';
```

**FSx for ONTAP の価値**:
- Snapshot → DB の論理バックアップ不要（一貫性のある PIT リカバリ）
- FlexClone → 開発/テスト DB を瞬時作成（本番データのゼロコピークローン）
- SnapMirror → DR サイトへのレプリケーション（pg_basebackup / mysqldump 不要）
- マルチプロトコル → 同じボリューム上の DB データを S3 AP 経由で Glue/Athena からも分析可能

> **WAL 性能に関する注記** (Databricks SA findings): PostgreSQL の WAL (Write-Ahead Log) を NFS 越しに fsync する場合、ローカルディスク比で 1-3ms のレイテンシ増加があります。高スループット書き込み環境では以下を検討:
> - `synchronous_commit = off`（データ損失リスクを許容する場合のみ）
> - WAL をローカル EBS、データファイルのみ FSx for ONTAP NFS に分離
> - ストリーミングレプリケーション構成（primary: EBS、standby: FSx for ONTAP → Lakehouse Federation は standby に接続）

### AI/ML データアクセスパス

FSx for ONTAP 上のデータを Databricks AI/ML 機能で活用する経路:

| AI/ML 機能 | 必要なデータ形態 | FSx for ONTAP からの経路 |
|---|---|---|
| **Feature Store** | UC テーブル | DataSync → S3 → UC テーブル → Feature Table 登録。Feature 鮮度は DataSync RPO に依存（5 分〜24 時間）。リアルタイム Feature 更新はパス 2 (Kafka → SS) を使用 |
| **AI Search (Vector Search)** | UC Volume or テーブル | DataSync → S3 → UC Volume → AI Search Pipeline |
| **MLflow Artifact** | UC Volume or S3 | DataSync → S3 → UC Volume パス指定 |
| **Model Serving (入力データ)** | API リクエスト | アプリ層で S3 AP 経由読み取り → サービング API 呼び出し |
| **Bedrock KB (RAG)** | S3 AP 直接 | FSx for ONTAP S3 AP → Bedrock KB（UC 外パス、公式チュートリアル） |
| **Document Intelligence** | S3 経由 | DataSync → S3 → Lakeflow → 構造化テーブル |

> **エッジ AI 画像検査パス**: NVIDIA Jetson / AWS Panorama 等のエッジ AI カメラで検査した画像（推論結果付き）を UC で管理するパス:
> ```
> Edge AI カメラ → ローカル NVMe バッファ → バッチ転送 → FSx for ONTAP (NFS) → DataSync → S3 → UC Volume
> ```
> 高速連写（10-100 枚/秒/ライン）ではローカルバッファが必須。NFS 直接書き込みは帯域制約のため非推奨。

> **RAG / AI Search パイプライン**: FSx for ONTAP 上のドキュメントを AI Search で検索可能にする具体フロー:
> ```
> FSx for ONTAP (ドキュメント) → DataSync → S3 → UC Volume
>   → Spark UDF (チャンキング: RecursiveCharacterTextSplitter 等)
>   → Embedding Model (Databricks FMAPI or Bedrock)
>   → AI Search Index (sync index on UC table)
>   → Agent retriever tool (RAG クエリ)
> ```

> **画像 embedding パイプライン**: 検査画像を AI Search で類似検索可能にする場合:
> ```
> UC Volume (検査画像) → Spark UDF (CLIP / ViT embedding 生成) → AI Search Index → 類似画像検索
> ```

---

## コスト比較

| パス | ストレージコスト | コンピュートコスト | 運用負荷 |
|------|----------------|------------------|---------|
| DataSync → S3 → UC | FSx for ONTAP + S3（重複） | DataSync 転送料 + Databricks | 中（スケジュール管理） |
| Kafka → SS → UC | FSx（メタデータのみ Kafka） | MSK + Databricks Streaming | 高（パイプライン管理） |
| Glue/EMR ETL | FSx for ONTAP + S3（重複） | Glue/EMR ジョブ実行料 | 中（ジョブスケジュール） |
| Athena (UC 外) | FSx for ONTAP のみ | クエリスキャン量課金 | 低（サーバーレス） |
| boto3 PoC | FSx for ONTAP のみ | Databricks クラスター | 低（ガバナンスなし）⚠️ データ流出リスク |

> **boto3 PoC セキュリティ警告**: boto3 PoC パスは UC ガバナンスを完全にバイパスするため、ユーザーがデータをローカルにダウンロードし外部に持ち出す流出リスクがあります。使用する場合は:
> - Databricks workspace の **egress 制御**（S3 bucket policy + VPC endpoint policy で宛先制限）
> - **IP ACL** によるアクセス元制限
> - **監査ログ** の有効化（CloudTrail + UC audit logs）
> - 時間制限付き承認（PoC 期間限定）

---

## 関連ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| [業界別ソリューションカタログ](./industry-solution-catalog.md) | **本ガイドとセット**。業界ごとのユースケース → 推奨パス → ガバナンスのマッピング |
| [DataSync → S3 ガイド](./datasync-to-s3-guide.md) | DataSync の詳細手順とスケジュール設計 |
| [Kafka-ClickHouse-UC 接続ガイド](./kafka-clickhouse-unity-catalog-connectivity.md) | ストリーミング + カタログ接続の技術詳細 |
| [Databricks 統合 README](../../integrations/databricks/README.md) | S3 AP 検証結果、エラーエビデンス、推奨パターン |
| [OpenSharing & Volume ガイド](../../integrations/databricks/docs/ja/delta-sharing-volume-guide.md) | OpenSharing 3 パターンの詳細設計 |
| [AI デモガイド](../../integrations/databricks/docs/ja/ai-demo-guide.md) | 動作するデモと動作しないデモのエビデンス |
| [Foreign Iceberg 検証計画](../../integrations/iceberg-metadata-catalog/databricks/uc-foreign-iceberg-validation.md) | Glue REST 経由の UC Foreign Catalog 検証 SQL |
| [OpenSharing 統合分析](./opensharing-integration-analysis.md) | OpenSharing の FSx for ONTAP との接点評価 |
| [AWS 公式: FSx for ONTAP + Bedrock KB](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html) | 公式 RAG チュートリアル（UC 外のパス） |
| [AWS 公式: FSx for ONTAP + Glue](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html) | 公式 Glue ETL チュートリアル |
| [AWS 公式: FSx for ONTAP + EMR](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-run-spark-with-emr-serverless.html) | 公式 EMR Serverless チュートリアル |

---

## 今後の展望

> **補足: FabricPool と UC**: FSx for ONTAP の FabricPool で S3 に tier されたデータは、技術的には標準 S3 バケット上に存在するため UC External Location でアクセス可能です。ただし、FabricPool の tier 先は ONTAP が透過的に管理する内部ストレージであり、ユーザーが直接 UC に登録して利用することは想定されていません。この経路は実用的ではなく、推奨しません。

| 項目 | ステータス | 解除条件 |
|------|-----------|---------|
| UC External Location S3 AP 対応 | ❌ 非対応（feature request 提出済み） | Databricks のプラットフォーム開発 |
| UC Foreign Iceberg × S3 Tables | ❌ ブロック確認（2026-06-21） | `iceberg_rest` type 非対応 + S3 Tables EL 登録不可。Databricks Support 確認待ち |
| OpenSharing Volumes コネクタ | 🔲 設計段階 | Databricks 開発 + FSx for ONTAP 対応 |
| Lakebase × FSx for ONTAP | ⚠️ Lakebase ap-northeast-1 非対応 | Databricks リージョン拡大 |

