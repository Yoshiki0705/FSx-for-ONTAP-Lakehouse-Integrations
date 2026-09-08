🌐 [English](../en/ai-demo-guide.md) | **日本語**

# Databricks Analytics & AI デモガイド — FSx for ONTAP S3 AP

本ガイドでは、Databricks から S3 Access Point 経由で FSx for ONTAP データにアクセスする際の分析および AI/ML 機能とその現在のステータスを文書化します。

> 📖 **マネージドテーブル vs 外部テーブル**の詳細比較、現在の制限、推奨パターンについては [マネージドテーブル vs 外部テーブル設計ガイド](../../README.md) の該当セクションを参照してください。

> **重要**: Unity Catalog のセッションポリシーにより、FSx for ONTAP S3 Access Point 上でのテーブル作成およびサブディレクトリ一覧取得が現在ブロックされています。以下のシナリオでは、現時点で動作するもの（ドライバーノードのみの PoC）、ブロックされているもの、プラットフォーム境界が解消された場合に可能になるものを文書化しています。

> **注意 (2026-05-26)**: Databricks サポートは `access_point` フィールドが GA ではなく、S3 AP パスが UC External Location でサポートされていないことを確認しました。以下の観測結果はサポートされたコードパスではなく、副作用的な動作を記録したものです。

## 前提条件

- AWS 上の Databricks ワークスペース（Customer-managed VPC 推奨）
- FSx for ONTAP S3 Access Point の設定完了
- S3 AP アクセス権限を持つ Instance Profile（PoC パス用）
- `access_point` フィールドが設定された Unity Catalog External Location
- DBR 17.3 LTS 以降

## 現在のステータスサマリー

| 機能 | ステータス | パス | ブロッカー |
|---|:---:|---|---|
| Spark ファイル読み取り（明示パス） | ✅ 動作 | UC External Location + `access_point` | — |
| サブディレクトリ一覧 | ❌ ブロック | UC External Location | セッションポリシーのプレフィックスレベルアクセス |
| S3 AP 上の CREATE TABLE | ❌ ブロック | UC External Location | UC_CLOUD_STORAGE_ACCESS_FAILURE |
| boto3 ファイル読み取り（ドライバー） | ✅ 動作 | Instance Profile (Customer VPC) | UC ガバナンスをバイパス |
| Feature Store テーブル | ❌ ブロック | CREATE TABLE が必要 | セッションポリシー |
| MLflow トラッキング | ✅ 動作 | ストレージパスに依存しない | — |
| Model Serving | ⚠️ 未検証 | 異なるクレデンシャルパス | — |

---

## デモ 1: FSx for ONTAP からの Spark 読み取り（動作確認済み）

**ユースケース**: ML 特徴量エンジニアリングのために FSx for ONTAP から構造化データ（CSV、Parquet）を読み取り。

```python
# FSx for ONTAP S3 AP からセンサーデータを読み取り（明示的ファイルパス）
df = spark.read.format("csv") \
    .option("header", "true") \
    .option("inferSchema", "true") \
    .load("s3://<s3ap-alias>/bronze/sensor_data/sensor_readings.csv")

df.show(5)
print(f"✅ FSx for ONTAP S3 AP から {df.count()} 行を読み取り")
```

**結果**: FSx for ONTAP 上のセンサー CSV から 1000 行を正常に読み取り（External Location に `access_point` フィールドを設定した明示的ファイルパス）。

![Spark が FSx for ONTAP S3 AP 上の明示的ファイルパスの読み取りに成功](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/databricks-ai-spark-read-success.png)

*Spark が Unity Catalog ガバナンス下で、明示的ファイルパスを使用して FSx for ONTAP S3 Access Point からセンサー CSV データを正常に読み取り。*

**制限事項**: 明示的ファイルパスのみ動作。ディレクトリレベルの読み取り（例: `spark.read.parquet("s3://<alias>/bronze/")`）はセッションポリシーによりサブディレクトリ一覧がブロックされるため失敗。

![トップレベル一覧は成功 — FSx for ONTAP S3 AP 上で 287 アイテムが表示](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/databricks-ls-success-287-items.png)

*トップレベルの `dbutils.fs.ls` は 287 アイテムを表示して成功。ただし、サブディレクトリ一覧とテーブル作成は引き続きブロック。*

---

## デモ 2: CREATE TABLE — ブロック（エラー証跡）

**ユースケース**: ML パイプライン用に FSx for ONTAP データをガバナンス付き Unity Catalog テーブルとして登録。

```sql
-- FSx for ONTAP S3 AP 上に External Table を作成試行
CREATE TABLE fsxn_lakehouse.bronze.sensor_data
USING CSV
OPTIONS (header = 'true', inferSchema = 'true')
LOCATION 's3://<s3ap-alias>/bronze/sensor_data/';
```

**結果**: ❌ `UC_CLOUD_STORAGE_ACCESS_FAILURE` — Unity Catalog の内部検証が S3 AP パスにアクセスできず、テーブル登録が失敗。

![UC セッションポリシーにより FSx for ONTAP S3 AP 上の CREATE TABLE がブロック](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/databricks-ai-create-table-blocked.png)

*Unity Catalog が FSx for ONTAP S3 Access Point 上のテーブル作成を拒否。AssumeRole 時に生成されるセッションポリシーが、内部検証操作に対して S3 AP ARN パターンを含まない。*

**AI/ML への影響**: テーブル作成ができないため、以下がブロック:
- Feature Store テーブル登録
- ML 学習データ用 Delta Lake マネージドテーブル
- モデル学習の Unity Catalog リネージ追跡
- 学習データへのカラムレベルガバナンスタグ

---

## デモ 3: サブディレクトリ一覧 — ブロック（エラー証跡）

**ユースケース**: バッチ処理（画像分類、ドキュメント抽出）のためにサブディレクトリ内のファイルを一覧取得。

```python
# サブディレクトリ内容の一覧取得を試行
files = dbutils.fs.ls("s3://<s3ap-alias>/media/images/")
```

**結果**: ❌ `getFileStatus` で `AccessDenied` — プレフィックスベースの ListObjectsV2 がサブディレクトリに対してブロック。

![セッションポリシーによりサブディレクトリ一覧がブロック](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/databricks-ai-subdir-listing-blocked.png)

*サブディレクトリ一覧が AccessDenied で失敗。UC セッションポリシーはトップレベルの一覧を許可するが、サブディレクトリに対するプレフィックススコープの ListObjectsV2 をブロック。*

**AI/ML への影響**: サブディレクトリ一覧がないため、`spark.read.format("binaryFile").load("s3://<alias>/media/images/")` のようなバッチ処理パターンがファイルを自動検出できない。

---

## デモ 4: Instance Profile + boto3（PoC パス — 動作確認済み）

**ユースケース**: AI 処理のために FSx for ONTAP から非構造化データ（画像、ドキュメント）を読み取り。

```python
import boto3
from PIL import Image
from io import BytesIO

# Instance Profile 経由で FSx for ONTAP から画像を読み取り（UC をバイパス）
s3 = boto3.client('s3', region_name='ap-northeast-1')
response = s3.get_object(
    Bucket='<s3ap-alias>',
    Key='media/images/inspection_photo.jpg'
)
img = Image.open(BytesIO(response['Body'].read()))
print(f"✅ 画像読み込み完了: {img.size}, {img.mode}")
```

**結果**: ✅ Customer-managed VPC の Dedicated クラスター上で Instance Profile 経由により FSx for ONTAP S3 AP から画像ファイルを正常に読み取り。

**⚠️ ガバナンス警告**: このパスは Unity Catalog を完全にバイパスします。Databricks 内でのリネージ、アクセス制御、監査証跡はありません。データオーナー、セキュリティオーナー、プラットフォームオーナーの明示的な承認を得た管理された PoC にのみ使用してください。

---

## デモ 5: MLflow 実験トラッキング（動作確認済み）

**ユースケース**: FSx for ONTAP データを学習ソースとして使用する ML 実験を追跡。

```python
import mlflow

# MLflow トラッキングはストレージパスに依存せず動作
with mlflow.start_run(run_name="fsxn_sensor_model"):
    mlflow.log_param("data_source", "fsxn_s3ap")
    mlflow.log_param("data_path", "s3://<s3ap-alias>/bronze/sensor_data/")
    mlflow.log_param("access_method", "instance_profile_boto3")

    # boto3 経由で読み取ったデータでモデルを学習...
    # mlflow.log_metric("accuracy", 0.95)
    # mlflow.sklearn.log_model(model, "model")

    print("✅ MLflow 実験トラッキング完了")
```

**結果**: ✅ MLflow 実験トラッキングはデータアクセス方法に関係なく動作。ただし、boto3 経由でデータを読み取った場合、Unity Catalog リネージ（どのテーブル → どのモデル）は記録されない。

**ベストプラクティス**: boto3 PoC パスを使用する場合でも、学習済みモデルは Unity Catalog Model Registry に登録してガバナンスを確保。

---

## 将来の機能（UC セッションポリシー解消後）

Databricks が S3 Access Point に対する Unity Catalog セッションポリシーの境界を解消した場合、以下の AI/ML ワークフローが利用可能になります:

### FSx for ONTAP 上の Feature Store

```python
# 将来: FSx for ONTAP 上の Feature テーブル（CREATE TABLE が必要）
from databricks.feature_engineering import FeatureEngineeringClient

fe = FeatureEngineeringClient()
fe.create_table(
    name="fsxn_lakehouse.features.customer_features",
    primary_keys=["customer_id"],
    df=feature_df,
    description="FSx for ONTAP に保存された顧客 ML 特徴量"
)
```

### CLIP による画像エンベディング

```python
# 将来: バッチ画像処理（サブディレクトリ一覧が必要）
images_df = spark.read.format("binaryFile") \
    .option("pathGlobFilter", "*.{jpg,png}") \
    .load("s3://<s3ap-alias>/media/images/")

# CLIP エンベディングを生成
embeddings_df = images_df.withColumn(
    "embedding", generate_clip_embedding(col("content"))
)
```

### RAG 用ドキュメント処理

```python
# 将来: ドキュメントテキスト抽出（binaryFile ディレクトリ読み取りが必要）
docs_df = spark.read.format("binaryFile") \
    .option("pathGlobFilter", "*.{pdf,docx}") \
    .load("s3://<s3ap-alias>/media/documents/")

# テキスト抽出、チャンク分割、エンベディング生成（RAG パイプライン）
```

### Mosaic AI モデル学習

```python
# 将来: UC リネージ付きガバナンスモデル学習
# 必要: S3 AP 上の UC テーブル → 学習データ → モデル → UC Model Registry
# 完全リネージ: データソース → 特徴量 → モデル → サービングエンドポイント
```

---

## 検証結果サマリー

| 機能 | ステータス | アクセスパス | ユースケース |
|---|:---:|---|---|
| Spark CSV 読み取り（明示パス） | ✅ 検証済み | UC External Location | ML 用構造化データ |
| トップレベルファイル一覧 | ✅ 検証済み | UC External Location | ファイル検出 |
| boto3 ファイル読み取り（ドライバー） | ✅ 検証済み | Instance Profile | 非構造化データ PoC |
| MLflow トラッキング | ✅ 検証済み | 独立 | 実験管理 |
| CREATE TABLE | ❌ ブロック | UC External Location | Feature Store、ガバナンステーブル |
| サブディレクトリ一覧 | ❌ ブロック | UC External Location | バッチファイル処理 |
| Delta 書き戻し | ❌ ブロック | UC External Location | 特徴量エンジニアリング出力 |
| Feature Store 登録 | ❌ ブロック | CREATE TABLE が必要 | ML 特徴量管理 |
| エグゼキュータースケール処理 | ⚠️ 未検証 | — | 分散 ML ワークロード |

---

## ガバナンスタグとデータ保護 (ABAC)

Databricks Unity Catalog は Governed Tags を使用した属性ベースアクセス制御（ABAC）を提供し、行レベル・カラムレベルのセキュリティを適用します。ただし、FSx for ONTAP S3 Access Point との組み合わせでは特定の要件と制限があります。

### 仕組み

```
Governed Tag（分類属性）
    │
    ├── ABAC Column Mask Policy
    │     → タグ条件に一致するカラムを自動マスク
    │     → Catalog/Schema スコープで適用
    │
    └── ABAC Row Filter Policy
          → タグ + ユーザー属性に基づいて表示行を制限
          → Unity Catalog がクエリ時に適用
```

### ガバナンス境界: 保護される範囲

| レベル | タグサポート | カラムマスク | Row Filter | 備考 |
|---|:---:|:---:|:---:|---|
| Catalog | ✅ | ✅ (ABAC スコープ) | ✅ (ABAC スコープ) | タグは配下のスキーマ/テーブルにカスケード |
| Schema | ✅ | ✅ (ABAC スコープ) | ✅ (ABAC スコープ) | タグは配下のテーブルにカスケード |
| Table (Managed) | ✅ | ✅ | ✅ | 完全ガバナンス |
| Table (External, S3 バケット上) | ✅ | ✅ | ✅ | 完全ガバナンス（標準 S3） |
| Table (External, FSx for ONTAP S3 AP 上) | ❌ **ブロック** | ❌ | ❌ | **CREATE TABLE 失敗 — ガバナンス適用不可** |
| Column | ✅（テーブル経由） | ✅（直接または ABAC） | — | タグはカラムレベルには継承しない |
| External Location | ✅（タグのみ） | ❌ | ❌ | 分類のみ、クエリ時の適用なし |

### 重大な制限: FSx for ONTAP S3 AP

**FSx for ONTAP S3 AP 上での Unity Catalog テーブル作成が現在ブロック**（UC_CLOUD_STORAGE_ACCESS_FAILURE）。これにより:

![Databricks ガバナンス影響 — FSx for ONTAP S3 AP 上で UC ガバナンスがブロック](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/databricks-summary-governance-impact.png)

*ガバナンス影響サマリー: テーブル作成がセッションポリシーによりブロックされるため、Unity Catalog ガバナンス機能（タグ、マスキング、Row Filter、リネージ）を FSx for ONTAP S3 AP データに適用不可。*

- ❌ FSx for ONTAP S3 AP データに UC テーブルとして Governed Tags を適用不可
- ❌ FSx for ONTAP S3 AP データに ABAC カラムマスクを適用不可
- ❌ FSx for ONTAP S3 AP データに Row Filter ポリシーを適用不可
- ❌ FSx for ONTAP S3 AP データのデータリネージを追跡不可
- ❌ FSx for ONTAP S3 AP データに自動データ分類を使用不可

**回避策（PoC のみ）**: boto3 でデータを読み取り → UC マネージドテーブルに書き込み → そこでガバナンスを適用。これはコピーを作成し、「ゼロコピー」の価値提案を損なう。

### 将来動作するもの（UC セッションポリシー解消後）

```python
# 将来: FSx for ONTAP データへの完全 ABAC（CREATE TABLE サポートが必要）

# 1. Governed Tag を作成
spark.sql("""
  CREATE GOVERNED TAG IF NOT EXISTS pii
  WITH ALLOWED_VALUES ('ssn', 'email', 'phone', 'address')
""")

# 2. FSx for ONTAP S3 AP 上に External Table を作成
spark.sql("""
  CREATE TABLE fsxn_lakehouse.bronze.customer_data
  USING PARQUET
  LOCATION 's3://<s3ap-alias>/bronze/customers/'
""")

# 3. カラムに Governed Tag を適用
spark.sql("""
  ALTER TABLE fsxn_lakehouse.bronze.customer_data
  ALTER COLUMN ssn SET GOVERNED TAG pii = 'ssn'
""")

# 4. ABAC カラムマスクポリシーを作成
spark.sql("""
  CREATE COLUMN MASK POLICY mask_pii
  ON COLUMNS MATCHING (pii IN ('ssn', 'email'))
  USING (CASE WHEN is_account_group_member('data_admin') THEN col ELSE '***' END)
""")

# 結果: SSN/email カラムが非管理者ユーザーに対して自動マスク
```

### Snowflake との比較

| 機能 | Databricks（FSx for ONTAP S3 AP 上） | Snowflake（FSx for ONTAP S3 AP 上） |
|---|---|---|
| タグ作成 | ✅ 動作（Governed Tags） | ✅ 動作（Object Tags） |
| External Table へのタグ | ❌ **ブロック**（テーブル作成不可） | ✅ **動作**（検証済み） |
| カラムマスキング | ❌ **ブロック** | ✅ 動作（Enterprise Edition） |
| 行フィルタリング | ❌ **ブロック** | ✅ 動作（Enterprise Edition） |
| PII 自動分類 | ❌ **ブロック** | ✅ 動作（Enterprise Edition） |
| タグ継承 | Catalog → Schema → Table | Database → Schema → Table → Column |
| 適用モデル | クエリ時（UC エンジン） | クエリ時（Snowflake エンジン） |

### 規制ワークロードへの推奨

Databricks が S3 Access Point に対する UC セッションポリシーの境界を解消するまで:

1. **FSx for ONTAP データのガバナンス付き分析**: **Snowflake** を使用（External Table + Tag-based Masking + Row Access Policy）
2. **ガバナンス付き ML パイプライン**: FSx for ONTAP S3 AP から UC マネージドストレージ（S3 バケット）にデータをステージングし、完全 ABAC ガバナンスを適用
3. **PoC/探索のみ**: Instance Profile + boto3 を補償コントロール付きで使用（承認記録、期間限定、監査ログ）

### ファイルレベルのアクセス制御: ONTAP ネイティブレイヤー

NetApp ユーザーにとって重要なガバナンスの問いは、テーブル/カラムレベルのマスキングだけでなく、**非構造化データ（画像、ドキュメント、動画）のファイルレベルのアクセス制御と統制**です。FSx for ONTAP S3 Access Points はデュアルレイヤー認可モデルを提供し、Databricks UC ガバナンスの利用可否に関係なく適用されます:

```
Layer 1: AWS IAM + S3 AP Policy（誰が S3 API を呼べるか）
    │
Layer 2: ONTAP ファイルシステム権限（どのファイルにアクセスできるか）
    │
    ├── Export Policy（NFS: クライアント IP、プロトコル、RO/RW/root）
    ├── NTFS ACL / NFSv4 ACL（ファイル/ディレクトリ単位の権限）
    ├── Storage-Level Access Guard（ボリュームレベルの ACL オーバーライド）
    ├── FPolicy（ファイル操作の監視、スクリーニング、ブロック）
    └── File System User マッピング（S3 AP → UNIX/Windows ID）
```

#### S3 AP ファイルレベル制御の仕組み

各 S3 Access Point は**ファイルシステムユーザー**にマッピングされます。全 S3 API 操作（Databricks からの boto3 や Spark を含む）はそのユーザーとして実行されます:

| S3 AP 設定 | ファイルアクセス範囲 | ユースケース |
|---|---|---|
| File system user = `root` (UID 0) | 全ファイルにフルアクセス | 管理者/分析（広範な読み取り） |
| File system user = `ml_team` (UID 1001) | UID 1001 が読めるファイルのみ | ML チームのデータ分離 |
| File system user = `dept_finance` | 財務部門のファイルのみ | 部門レベルの分離 |
| ボリュームごとに複数 S3 AP | AP ごとに異なるユーザー | チームごと/ワークロードごとのスコーピング |

#### チームごとの S3 Access Point（UC ギャップの補償コントロール）

Databricks UC ガバナンスが FSx for ONTAP S3 AP 上で現在ブロックされているため、複数 Access Point によるファイルレベル分離が補償コントロールを提供:

```
FSx for ONTAP Volume: /vol1
├── /training-data/   (owner: ml_team, mode: 750)
├── /sensitive-docs/  (owner: compliance, mode: 700)
├── /shared-assets/   (owner: root, mode: 755)
│
├── S3 AP "databricks-ml-team"     → file_system_user: ml_team
│     → Databricks ML クラスターが /training-data/ と /shared-assets/ を読み取り
│     → /sensitive-docs/ にはアクセス不可（ONTAP レベルで permission denied）
│
├── S3 AP "databricks-compliance"  → file_system_user: compliance
│     → コンプライアンスチームが /sensitive-docs/ を読み取り
│     → 別の Instance Profile、別のクラスター
│
└── S3 AP "databricks-admin"       → file_system_user: root
      → ガバナンスレビュー用の管理者アクセス
```

#### FPolicy: ファイル操作の監視とブロック

FPolicy は ONTAP レベルでリアルタイムのファイルアクセス監視を提供 — Databricks が Instance Profile + boto3 で UC をバイパスする場合でも適用:

| FPolicy 機能 | 説明 | Databricks への関連性 |
|---|---|---|
| ネイティブファイルブロック | 特定のファイル拡張子をブロック | ML パイプラインでの不要なファイルタイプを防止 |
| 外部 FPolicy サーバー | アクセスイベントを外部アプリに送信 | UC リネージが利用不可時の監査証跡 |
| ファイルスクリーニング | ファイルタイプに基づく許可/拒否 | ML ジョブがアクセスできるデータタイプの制御 |
| 操作モニタリング | 全ファイル操作を監視 | boto3 PoC パスの補償監査 |

**NetApp ユーザーへの重要な知見**: Databricks が Unity Catalog ガバナンスをバイパスする場合（Instance Profile + boto3 経由）でも、ONTAP のファイルレベル権限と FPolicy はストレージレイヤーでアクセス制御を適用し続けます。これは UC セッションポリシーサポートが解消されるまでの補償コントロールを提供します。

### 統合: ONTAP ファイルレベル制御 × Databricks タグガバナンス

2つのガバナンスレイヤー（ONTAP ファイルレベルと Databricks ABAC）は連携して動作するよう設計されていますが、現在の S3 AP セッションポリシーの制限によりギャップが存在します。統合の仕組みと現時点で利用可能なものを示します:

#### 統合マトリクス（現在の状態）

| シナリオ | ONTAP レイヤー（ファイルレベル） | Databricks レイヤー（ABAC） | 組み合わせ効果 | ステータス |
|---|---|---|---|:---:|
| **部門分離** | 部門ごとに別 S3 AP（異なる file_system_user） | Governed Tags でテーブルを部門別分類 | ファイル物理的アクセス不可 + 共有テーブルの ABAC マスク | ⚠️ ONTAP のみ（ABAC ブロック） |
| **PII 保護** | FPolicy が PII ディレクトリへのアクセスを監視 | PII タグ付きカラムに ABAC Column Mask | ファイルアクセス監査 + カラム値マスク | ⚠️ ONTAP のみ（ABAC ブロック） |
| **ML 学習データ制御** | Export Policy がどのクラスターが読めるか制限 | Governed Tags でテーブルに機密レベル | ネットワーク制限 + 機密特徴量のカラムマスキング | ⚠️ ONTAP のみ（ABAC ブロック） |
| **ランサムウェア防御** | ARP/AI が暗号化を検知 + 自動スナップショット | N/A（ストレージレイヤーの関心事） | ストレージ保護。コンピュートは影響なし | ✅ 完全利用可能 |
| **コンプライアンスホールド** | SnapLock がファイル削除を防止 | Row Filter がクエリ結果を制限 | データ不変 + ロールによるクエリフィルタ | ⚠️ ONTAP のみ（Row Filter ブロック） |
| **チーム間データ共有** | 共有ディレクトリを共通 S3 AP 経由 | ABAC Row Filter がチームロールでフィルタ | 全チームがテーブル表示、各自は認可行のみ | ⚠️ ONTAP のみ（ABAC ブロック） |

#### 連携の仕組み（将来の状態）

```
1. データサイエンティストが FSx for ONTAP S3 AP 上の UC External Table をクエリ
       │
       ▼
2. Unity Catalog チェック: ユーザーに SELECT 権限あり？ ──── NO → PermissionDenied
       │ YES
       ▼
3. Spark が S3 API コール（GetObject）を生成
       │
       ▼
4. S3 AP Policy チェック: IAM ロール許可？ ──── NO → AccessDenied
       │ YES
       ▼
5. ONTAP チェック: file_system_user に権限あり？ ──── NO → AccessDenied
       │ YES
       ▼
6. ファイルデータが Spark に返却
       │
       ▼
7. UC が ABAC Column Mask を適用 ──── Governed Tags に基づき PII カラムをマスク
       │
       ▼
8. UC が ABAC Row Filter を適用 ──── タグに基づき非認可行をフィルタ
       │
       ▼
9. ユーザーに表示: 認可された行のみ、機密カラムはマスク済み
```

**現在の実態**: ステップ 1-2 が「CREATE TABLE」で失敗（UC_CLOUD_STORAGE_ACCESS_FAILURE）するため、ステップ 7-9 に到達不可。

#### 現在利用可能なもの vs 将来

| ガバナンスニーズ | 現在利用可能（ONTAP のみ） | 将来（ONTAP + UC ABAC） |
|---|---|---|
| ファイルレベル分離 | ✅ スコープ付き file_system_user のコンシューマーごと S3 AP | ✅ 同上 + UC テーブルレベルガバナンス |
| カラムマスキング | ❌ ファイルレベルでは不可（ファイルは不透明なブロブ） | ✅ タグ付きカラムへの ABAC Column Mask |
| 行フィルタリング | ❌ ファイルレベルでは不可 | ✅ タグ付きテーブルへの ABAC Row Filter |
| アクセス監査 | ✅ FPolicy + CloudTrail S3 データイベント | ✅ 同上 + リネージ付き UC 監査ログ |
| データ不変性 | ✅ SnapLock / Tamperproof Snapshot | ✅ 同上（ストレージレイヤー、常に利用可能） |
| ランサムウェア防御 | ✅ ARP/AI | ✅ 同上（ストレージレイヤー、常に利用可能） |
| データ分類 | ❌ 手動（ファイル命名/ディレクトリ構造） | ✅ UC 自動データ分類 |

#### 組み合わせガバナンスの設計パターン（現在利用可能）

| パターン | ONTAP 設定 | Databricks 設定 | ガバナンスレベル |
|---|---|---|---|
| **ファイル分離（主要）** | チームごとの S3 AP（スコープ付きユーザー） | チームごとの Instance Profile | 強（ONTAP 適用） |
| **監査証跡（補償）** | FPolicy 外部サーバー | CloudTrail + boto3 内カスタムログ | 中（UC リネージなし） |
| **不変学習データ** | 学習データセット用 SnapLock ボリューム | MLflow がソーススナップショット ID を記録 | 強（ストレージ適用） |
| **ネットワーク分離** | VPC スコープ S3 AP + Export Policy | Customer-managed VPC + セキュリティグループ | 強（ネットワーク適用） |

#### リファレンス: ONTAP ファイルレベル + Databricks タグ統合

| トピック | リファレンス |
|---|---|
| FSx for ONTAP S3 AP デュアルレイヤー認可 | [Managing access point access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html) |
| FSx for ONTAP S3 AP と Active Directory | [Enabling AI-powered analytics on enterprise file data](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/) |
| ONTAP Export Policy（NFS アクセス制御） | [Export rules の仕組み](https://docs.netapp.com/us-en/ontap/nfs-admin/export-rules-concept.html) |
| ONTAP FPolicy（ファイル監視/ブロック） | [FPolicy 設定タイプ](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html) |
| ONTAP Storage-Level Access Guard | [SLAG によるファイルアクセス保護](https://docs.netapp.com/us-en/ontap/smb-admin/secure-file-access-storage-level-access-guard-concept.html) |
| Databricks ABAC 概要 | [属性ベースアクセス制御](https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/) |
| Databricks Governed Tags | [UC オブジェクトへのタグ適用](https://docs.databricks.com/aws/en/database-objects/tags) |
| Databricks Row Filters & Column Masks | [Row filters and column masks](https://docs.databricks.com/aws/en/data-governance/unity-catalog/filters-and-masks) |
| Databricks ABAC チュートリアル | [ABAC 設定チュートリアル](https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/tutorial) |
| Databricks ABAC + Delta Sharing | [ガバナンス境界を越えた ABAC](https://www.databricks.com/blog/how-delta-sharing-supports-abac-sharing-providers-and-recipients) |
| Databricks Data Classification (GA) | [ABAC、Governed Tags、データ分類 GA](https://www.databricks.com/blog/abac-row-filtering-and-column-masking-policies-governed-tags-and-data-classification-are-now) |

#### ガバナンスレイヤーサマリー（Databricks + ONTAP）

| レイヤー | 適用ポイント | スコープ | FSx for ONTAP S3 AP でのステータス |
|---|---|---|---|
| **ONTAP Export Policy** | ファイルシステム | ボリューム/qtree | ✅ 常に適用 |
| **ONTAP ファイル権限** | ファイルシステム | ファイル/ディレクトリ単位 | ✅ 常に適用 |
| **ONTAP FPolicy** | ファイルシステム | 操作単位 | ✅ 常に適用 |
| **ONTAP Storage-Level Access Guard** | ファイルシステム | ボリューム | ✅ 常に適用 |
| **S3 AP Policy** | AWS | Access Point 単位 | ✅ 常に適用 |
| **S3 AP File System User** | ファイルシステム | Access Point 単位 | ✅ 常に適用 |
| **Databricks UC Tags** | クエリエンジン | テーブル/カラム | ❌ ブロック（テーブル作成不可） |
| **Databricks ABAC Masks** | クエリエンジン | カラム | ❌ ブロック |
| **Databricks Row Filters** | クエリエンジン | 行 | ❌ ブロック |

### リファレンス

- [ABAC in Unity Catalog](https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/)
- [Governed Tags](https://docs.databricks.com/aws/en/database-objects/tags)
- [Row Filters and Column Masks](https://docs.databricks.com/aws/en/data-governance/unity-catalog/filters-and-masks)
- [ABAC チュートリアル](https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/tutorial)
- [Multi-domain Column Masking](https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/multi-domain)

---

## 業界別ユースケース（将来の状態）

### 製造業 / 品質検査

| ユースケース | Databricks 機能 | FSx 上のデータ | ステータス |
|---|---|---|---|
| センサー異常検知 | MLflow + Spark ML | IoT センサー Parquet/CSV | ⚠️ 明示パス読み取りのみ |
| 画像欠陥分類 | CLIP / カスタム CNN | 製品画像 | ❌ バッチ読み取りブロック |
| 予知保全 | Feature Store + AutoML | 設備テレメトリ | ❌ Feature テーブルブロック |
| 品質レポート生成 | LLM (Foundation Model API) | 検査ドキュメント | ⚠️ boto3 PoC のみ |

### 金融 / 保険

| ユースケース | Databricks 機能 | FSx 上のデータ | ステータス |
|---|---|---|---|
| ドキュメント分類 | Spark NLP / binaryFile | 契約書 PDF | ❌ バッチ読み取りブロック |
| 不正検知特徴量 | Feature Store | 取引データ | ❌ Feature テーブルブロック |
| リスクモデル学習 | MLflow + XGBoost | 過去データ | ⚠️ 明示パス読み取りのみ |
| 規制文書テキスト抽出 | UDF + pypdf | コンプライアンス文書 | ⚠️ boto3 PoC のみ |

### 医療 / ライフサイエンス

| ユースケース | Databricks 機能 | FSx 上のデータ | ステータス |
|---|---|---|---|
| 医療画像分析 | torchvision / CLIP | DICOM/PNG 画像 | ❌ バッチ読み取りブロック |
| 臨床試験データ準備 | Spark ETL | 試験ドキュメント | ⚠️ 明示パス読み取りのみ |
| 研究論文エンベディング | Sentence Transformers | PDF 論文 | ❌ バッチ読み取りブロック |
| 患者記録抽出 | pypdf + NLP | スキャン記録 | ⚠️ boto3 PoC のみ |

### メディア / コンテンツ管理

| ユースケース | Databricks 機能 | FSx 上のデータ | ステータス |
|---|---|---|---|
| 画像類似検索 | CLIP エンベディング | メディアアセット | ❌ バッチ読み取りブロック |
| 動画フレーム抽出 | OpenCV + Spark | 動画ファイル | ❌ バッチ読み取りブロック |
| コンテンツタグ付け | Foundation Model API | 全メディア | ⚠️ boto3 PoC のみ |
| アセットメタデータカタログ | Delta テーブル | ファイルメタデータ | ❌ CREATE TABLE ブロック |

---

## 現時点での推奨代替手段

UC セッションポリシーの解消を待つ間、FSx for ONTAP データに対する AI/ML には以下の検証済みパスを使用:

| AI/ML ニーズ | 推奨サービス | ステータス | リファレンス |
|---|---|---|---|
| ドキュメント RAG | Amazon Bedrock Knowledge Bases | AWS ドキュメント済み | [チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html) |
| OCR / Document AI | Snowflake PARSE_DOCUMENT | ✅ 検証済み | [デモガイド](../../../snowflake/docs/ja/ai-demo-guide.md) |
| テキスト要約 | Snowflake Cortex SUMMARIZE | ✅ 検証済み | [デモガイド](../../../snowflake/docs/ja/ai-demo-guide.md) |
| ファイル処理 (Lambda) | AWS Lambda | AWS ドキュメント済み | [チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-process-files-with-lambda.html) |
| SQL 分析 | Amazon Athena | ✅ 検証済み (Part 1) | [ブログ](https://dev.to/aws-builders/query-nas-data-in-place-with-athena-and-fsx-for-ontap-s3-access-points-3lhh) |
| Spark ETL | EMR Serverless | シリーズ内で検証済み | [チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-run-spark-with-emr-serverless.html) |

---

## AI/ML ワークロードにおける ONTAP の価値

| ONTAP 機能 | AI/ML メリット | リファレンス |
|---|---|---|
| **FlexCache** | リージョン/拠点間で学習データをキャッシュし低遅延アクセスを実現。分散 ML ワークロードの WAN 帯域を削減。Write-back モードにより特徴量エンジニアリングの書き込みレイテンシを低減 | [FlexCache 概要](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html) |
| **SnapLock / Tamperproof Snapshot** | 不変のデータ保護 — 管理者権限でも保持期間中はロックされたスナップショットを削除不可。学習データガバナンスにおいて SEC 17a-4(f)、HIPAA、FINRA コンプライアンスに対応 | [SnapLock on FSx for ONTAP](https://netapp.com/blog/snaplock-on-amazon-fsx-ontap/) |
| **ARP/AI（自律型ランサムウェア防御）** | AI によるランサムウェア暗号化パターンのリアルタイム検知。学習データやモデルアーティファクトへの被害拡大前に自動スナップショットを作成 | [ARP on FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/ARP.html) |
| **FlexClone** | ML 実験用のゼロコピー即時クローン — データを複製せずに異なる前処理をテスト。開発/テスト用データセットの即時プロビジョニング | [FlexClone ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-volumes.html) |
| **Snapshot** | 学習データセットのポイントインタイムリカバリ。特徴量エンジニアリングパイプラインのバージョン管理。Delta Lake Time Travel を補完 | [Snapshot ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/snapshots-ontap.html) |
| **FabricPool** | コールドな学習データや古いモデルアーティファクトを S3 に自動階層化 — Databricks コンピュートに対して透過的 | [FabricPool ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/fabricpool.html) |
| **マルチプロトコル** | 同一データに NFS（データサイエンティスト）、SMB（Windows ユーザー）、S3 AP（Databricks/Spark）から同時アクセス可能 | [マルチプロトコルアクセス](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/supported-fsx-clients.html) |
| **重複排除** | Delta バージョンファイル、類似エンベディング、重複する特徴量データセットのストレージを削減 | [ストレージ効率](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/storage-efficiency.html) |
| **SnapMirror** | 重要な ML パイプラインと Feature Store のクロスリージョン DR | [SnapMirror ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html) |
| **FPolicy** | AI データアクセス監査用のファイル操作監視。ML パイプラインでの不正ファイルタイプのブロック | [FPolicy ドキュメント](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html) |

### AI/ML 固有のシナリオ

- **FlexCache による分散学習**: オンプレミス NAS からクラウド FSx for ONTAP に学習データセットをキャッシュ — Databricks クラスターが WAN を経由せずローカルキャッシュからサブミリ秒のレイテンシでデータを読み取り。Write-back モード（2025年5月提供開始）により特徴量エンジニアリングパイプラインの書き込みレイテンシを低減。
- **SnapLock によるモデルガバナンス**: 学習データのスナップショットをロックし再現性を保証 — 監査人がモデル学習に使用された正確なデータセットが変更されていないことを検証可能。規制産業（医療、金融）で特に重要。
- **ARP/AI によるデータパイプライン保護**: 学習データやモデルアーティファクトを標的とするランサムウェアを検知・ブロック — 自動スナップショットがリカバリ用のクリーンな状態を保持。取り込みからサービングまでの ML データライフサイクル全体を保護。

---

## はじめに

1. **インフラデプロイ** — [セットアップガイド](setup-guide.md) に従う
2. **External Location 設定** — `access_point` フィールドを設定（[UC 統合](unity-catalog-integration.md)）
3. **明示的ファイル読み取りテスト** — 既知のファイルパスで Spark 読み取りを検証
4. **PoC 用**: Dedicated クラスターに Instance Profile を設定
5. **実験トラッキング** — アクセスパスに関係なく MLflow を使用
6. **モニタリング**: S3 AP サポートに関する Databricks プラットフォームアップデートを監視

## Databricks AI/ML ドキュメント

- [Mosaic AI 概要](https://docs.databricks.com/en/machine-learning/index.html)
- [Feature Engineering](https://docs.databricks.com/en/machine-learning/feature-store/index.html)
- [MLflow on Databricks](https://docs.databricks.com/en/mlflow/index.html)
- [Foundation Model APIs](https://docs.databricks.com/en/machine-learning/foundation-models/index.html)
- [Unity Catalog Models](https://docs.databricks.com/aws/en/catalog-explorer/explore-models)
- [External Locations](https://docs.databricks.com/aws/en/connect/unity-catalog/storage-credentials)
- [Instance Profiles (レガシー)](https://docs.databricks.com/en/admin/sql/data-access-configuration.html)
- [Binary File Data Source](https://docs.databricks.com/en/query/formats/binary-file.html)
