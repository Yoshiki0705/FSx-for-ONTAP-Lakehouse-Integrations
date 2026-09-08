🌐 [English](../en/delta-sharing-volume-guide.md) | **日本語**

# OpenSharing & Volume Sharing 統合ガイド

> **ステータス**: アーキテクチャリファレンス — Pattern A/B は PoC 実施可能、Pattern C は Databricks UC 機能開発待ち（ブロック中）
>
> **コンテキスト**: このガイドは、FSx for ONTAP S3 Access Points との直接的な UC External Location 統合が[現在サポートされていない](../../README.md#where-the-denial-originates)状況において、OpenSharing を使って FSx for ONTAP データを Databricks Unity Catalog ガバナンス下で利用する方法を文書化しています。

## エグゼクティブサマリー

OpenSharing は**共有プロトコル**であり、変換エンジンではありません。任意の NAS ファイル（画像、動画、PDF）をその場でクエリ可能なテーブルに変換するものではありません。OpenSharing が公開するのは、**準備済みの表形式データセット**です。

FSx for ONTAP と Databricks の統合において、OpenSharing は以下の場合に実用的な共有レイヤーを提供します：
- Databricks がストレージの直接所有者ではなく**受信者（Recipient）**として機能する場合
- データが先に Delta または Parquet テーブルに変換されている場合
- Unity Catalog Volumes がガバナンス付き非表形式ファイルアクセスに使用される場合

### 基本原則

1. **OpenSharing = 共有プロトコル**（変換エンジンではない）
2. **FSx for ONTAP S3 Access Points はオブジェクトアクセスを提供** — OpenSharing にはテーブルセマンティクスが必要
3. **非構造化データの場合**: 共有可能な資産は派生した構造化表現（メタデータ、抽出テキスト、キャプション、embedding）
4. **真のゼロコピー Raw ファイルアクセスには**: Unity Catalog が FSx for ONTAP S3 AP をファーストクラスのストレージロケーションとしてサポートする必要あり（機能ギャップ — [Databricks エンジニアリングに報告済み](../../README.md#where-the-denial-originates)）

### Quick Start: 今日何をすべきか？

| あなたの状況 | 推奨アクション | パターン |
|---|---|---|
| **Databricks 顧客で NAS データのガバナンス付き分析が必要** | DataSync → S3 → UC External Location → Delta Tables | DataSync パス（検証済み） |
| **ファイルメタデータを Databricks ユーザーと共有したい** | Lambda + ListObjectsV2 → Delta Table → OpenSharing | Pattern A |
| **NAS ドキュメントに対する AI/RAG が Databricks で必要** | Textract/Bedrock → Delta Table → OpenSharing | Pattern B |
| **Raw ファイル（画像/動画/PDF）を Databricks で閲覧したい** | DataSync → S3 → UC External Volume → Volume Sharing | Pattern C（S3 同期あり） |
| **ゼロコピー直接アクセスが欲しい（S3 バケットなし）** | 現時点では利用不可 — Databricks UC 機能開発待ち | Pattern C（ブロック中） |

---

## 3つの統合パターン

### Pattern A: メタデータテーブル共有（推奨初回 PoC）

Raw ファイルそのものではなく、**ファイルカタログ**を OpenSharing で共有する。

```
FSx for ONTAP
  ↓ S3 Access Point (ListObjectsV2)
AWS Lambda / Glue / Step Functions
  ↓ ファイルインベントリ抽出
Parquet or Delta メタデータテーブル (S3上)
  ↓
OpenSharing (UC Share or OSS Server)
  ↓
Databricks 受信者
```

**共有テーブルスキーマ例:**

| カラム | 型 | 説明 |
|--------|------|-------------|
| `file_id` | STRING | 一意識別子 |
| `path` | STRING | S3 AP パス |
| `s3_ap_key` | STRING | アクセスポイント内のオブジェクトキー |
| `size_bytes` | BIGINT | ファイルサイズ |
| `last_modified` | TIMESTAMP | 最終更新日時 |
| `etag` | STRING | S3 ETag |
| `file_extension` | STRING | 例: `.pdf`, `.jpg`, `.parquet` |
| `mime_type` | STRING | MIME タイプ |
| `classification` | STRING | データ分類ラベル |
| `scan_timestamp` | TIMESTAMP | インベントリ取得日時 |

**使用 AWS サービス:**
- FSx for ONTAP S3 Access Points — S3 API によるファイルアクセス
- AWS Lambda — 小規模 PoC（ListObjectsV2 → メタデータ抽出）
- AWS Step Functions — バッチ処理のワークフロー制御
- AWS Glue — Parquet/Delta への ETL、カタログ管理
- Amazon S3 — メタデータテーブル保存先（OpenSharing との互換性のため推奨）

**PoC 成功基準:** Databricks が FSx for ONTAP ファイルメタデータを表す OpenSharing テーブルをクエリできること。

**このパターンでの ONTAP の価値**: Snapshot により過去のファイルインベントリを即座に復元可能。メタデータスキャンが不正確な結果を生成した場合、以前の Snapshot に戻して再スキャン — データ損失なし、再アップロード不要。

**本番化チェックリスト (Pattern A):**
- [ ] データ鮮度 SLA 定義（例: メタデータテーブルを N 分/時間ごとに更新）
- [ ] 障害ハンドリング: Lambda DLQ、Step Functions 指数バックオフリトライ
- [ ] 監視: CloudWatch メトリクス（Lambda エラー、呼び出し回数、実行時間）
- [ ] コストモデル: Lambda 呼び出し × ファイル数 × スケジュール頻度
- [ ] スキーマ進化: 新しいファイルタイプやメタデータフィールドの追加方法
- [ ] アクセス制御: 共有メタデータテーブルを誰がクエリできるか（OpenSharing Recipient 権限）
- [ ] 運用ランブック: メタデータテーブルが古い場合や Lambda 失敗時の対応手順

---

### Pattern B: AI 処理済みテーブル共有（RAG / 検索 / 分析）

非構造化データを AI サービスで処理し、**派生した構造化出力**を OpenSharing で共有する。

```
FSx for ONTAP (Raw ファイル: PDF, 画像, 音声, 動画)
  ↓ S3 Access Point (GetObject)
AWS AI サービス (Textract, Rekognition, Transcribe, Bedrock)
  ↓ 抽出テキスト / キャプション / 文字起こし / embedding
Parquet or Delta テーブル (S3上)
  ↓
OpenSharing
  ↓
Databricks 受信者 (Mosaic AI, Vector Search, MLflow)
```

**データタイプ別共有テーブルスキーマ:**

#### ドキュメント (PDF/DOCX) — RAG パイプライン

| カラム | 型 | 説明 |
|--------|------|-------------|
| `document_id` | STRING | ドキュメント ID |
| `source_path` | STRING | FSx for ONTAP S3 AP パス |
| `page_number` | INT | ページ番号 |
| `chunk_id` | STRING | テキストチャンク ID |
| `text` | STRING | 抽出テキスト |
| `summary` | STRING | AI 生成要約 |
| `embedding` | ARRAY<FLOAT> | ベクトル embedding |
| `classification` | STRING | ドキュメント分類 |
| `created_at` | TIMESTAMP | 処理日時 |

#### 画像 — ビジュアル検索

| カラム | 型 | 説明 |
|--------|------|-------------|
| `image_id` | STRING | 画像 ID |
| `source_path` | STRING | FSx for ONTAP S3 AP パス |
| `mime_type` | STRING | image/jpeg, image/png 等 |
| `width` | INT | 画像幅 (px) |
| `height` | INT | 画像高さ (px) |
| `detected_labels` | ARRAY<STRING> | 物体検出結果 |
| `caption` | STRING | AI 生成キャプション |
| `embedding` | ARRAY<FLOAT> | ビジュアル embedding |
| `created_at` | TIMESTAMP | 処理日時 |

#### 動画/音声 — 文字起こし & 分析

| カラム | 型 | 説明 |
|--------|------|-------------|
| `video_id` | STRING | 動画/音声 ID |
| `source_path` | STRING | FSx for ONTAP S3 AP パス |
| `start_time_sec` | FLOAT | セグメント開始時間 |
| `end_time_sec` | FLOAT | セグメント終了時間 |
| `transcript` | STRING | 文字起こしテキスト |
| `detected_objects` | ARRAY<STRING> | フレーム内検出オブジェクト |
| `scene_summary` | STRING | AI シーン説明 |
| `embedding` | ARRAY<FLOAT> | セグメント embedding |
| `created_at` | TIMESTAMP | 処理日時 |

**データタイプ別 AWS AI サービス:**

| データタイプ | 主要サービス | 補助 | 出力 |
|-----------|----------------|-----------|--------|
| PDF/ドキュメント | Amazon Textract | Amazon Bedrock (要約, embed) | テキスト, 表, フォーム, 要約 |
| 画像 | Amazon Rekognition | Bedrock マルチモーダル (キャプション) | ラベル, オブジェクト, 顔, キャプション |
| 音声 | Amazon Transcribe | Bedrock (要約) | 文字起こし, 話者 ID |
| 動画 | Rekognition Video | Transcribe + Bedrock | ラベル, シーン, 文字起こし |

**PoC 成功基準:** Databricks が AI 処理済みメタデータ（抽出テキスト、ラベル、要約、embedding）を OpenSharing 経由でクエリできること。

**このパターンでの ONTAP の価値**: FlexClone により AI 処理用のデータセットを即座にゼロコピーで複製可能 — 本番 NFS/SMB ワークロードに影響なし。Storage Efficiency（重複排除 + 圧縮）によりソースファイルと AI 派生テーブルの両方を維持するコストを削減。

**本番化チェックリスト (Pattern B):**
- [ ] AI 処理パイプライン SLA: ファイル作成から検索可能な embedding までのエンドツーエンドレイテンシ
- [ ] 品質ゲート: embedding 品質検証、OCR 精度閾値、ハルシネーション検出
- [ ] コストモデル: Textract/Rekognition/Transcribe のページ/分単位課金 × ボリューム × 頻度
- [ ] 障害ハンドリング: 部分処理（一部ファイルの OCR 失敗）、リトライロジック、ポイズンメッセージ処理
- [ ] データリネージ: どのソースファイルがどの embedding/要約を生成したか追跡（監査・再処理用）
- [ ] 増分処理: 新規/変更ファイルのみ処理（毎回の全量再処理を回避）
- [ ] 監視: 処理成功率、embedding ドリフト検出、パイプラインラグメトリクス
- [ ] セキュリティ: AI サービスが顧客データを保持しないことを確認; 規制コンテンツのデータレジデンシー検証

---

### Pattern C: UC Volume による Raw ファイル共有（Databricks 機能拡張が必要）

理想的なゼロコピーアーキテクチャ — ただし現在は UC セッションポリシーの制限によりブロック。

**理想的なアーキテクチャ:**
```
FSx for ONTAP
  ↓ S3 Access Point
Databricks UC External Location (直接)
  ↓
UC External Volume
  ↓
OpenSharing (Volume Sharing)
  ↓
Databricks 受信者 (read_files, ai_query, ai_parse_document)
```

**現在の現実（S3 コピーが必要）:**
```
FSx for ONTAP
  ↓ DataSync
Amazon S3 バケット (標準)
  ↓
Databricks UC External Location
  ↓
UC External Volume
  ↓
OpenSharing (Volume Sharing)
  ↓
Databricks 受信者
```

**DataSync → S3 → UC パスの本番設計:**

これは FSx for ONTAP + Databricks の**完全にサポートされた本番対応パス**です。Unity Catalog の完全なガバナンス、Delta Lake ACID、Mosaic AI、Feature Store が全て利用可能です。

| コンポーネント | 設計判断 | 根拠 |
|------------|---------|------|
| 同期メカニズム | AWS DataSync（検証済み） | FSx for ONTAP NFS から S3 バケットへのスケジュール同期。増分転送をサポート。 |
| S3 バケット設計 | `s3://fsxn-lakehouse-<env>/raw/`, `/bronze/`, `/silver/`, `/gold/` | メダリオンアーキテクチャによる段階的精製 |
| UC カタログ構造 | `fsxn_lakehouse.raw.*`, `fsxn_lakehouse.curated.*` | Raw 取り込みとガバナンス付き消費を分離 |
| Delta Table 設計 | Managed Tables（UC がライフサイクル制御） | OPTIMIZE, VACUUM, Time Travel, Z-ORDER が有効 |
| 取り込み | Auto Loader（S3 バケット上の Directory Listing モード） | 増分、exactly-once、スキーマ進化 |
| ガバナンス | UC Tags + Row Access Policies + Column Masks | 同期データに完全なエンタープライズガバナンス |
| AI/ML | Mosaic AI, Feature Store, MLflow（Delta Tables 上） | プラットフォームの全機能が利用可能 |
| コスト | FSx ストレージ + S3 ストレージ + Databricks コンピュート | プラットフォーム全機能のために重複コストを受容 |

**エンドツーエンドデータ鮮度モデル:**

| 同期パターン | DataSync スケジュール | Auto Loader 検出 | UC テーブル反映 | 合計ラグ |
|---|---|---|---|---|
| DataSync (5分スケジュール) + Auto Loader (5分ポーリング) | 5分 | 5分 | <1分 | **最大約10分** |
| DataSync (1分スケジュール) + Auto Loader (1分ポーリング) | 1分 | 1分 | <1分 | **最大約2-3分** |
| FPolicy → Lambda → S3 + Auto Loader (File Notification) | リアルタイム | 秒（SQS） | <1分 | **約30秒** |
| DataSync (時間スケジュール) + Auto Loader (5分ポーリング) | 60分 | 5分 | <1分 | **最大約65分** |

> **製造業ユースケース向け**: 「工場の画像データが Databricks で見えるまで何分かかるか？」— DataSync 5分スケジュール + Auto Loader 5分ポーリングで「10分以内」。準リアルタイム要件（<1分）には FPolicy → Lambda → S3 パスを使用。

**代表的なコスト概算（DataSync → S3 → UC パス）:**

| コンポーネント | 1 TB データセット | 10 TB データセット | 備考 |
|------------|---|---|---|
| DataSync 転送 | 約$0.04/GB（初回）、以降増分 | 約$0.40/GB 初回、以降増分 | 転送 GB あたり課金; 増分同期は変更分のみ転送 |
| S3 Standard ストレージ | 約$23/月 | 約$230/月 | FSx for ONTAP データの同期コピーを保存 |
| Auto Loader (Jobs コンピュート) | 約$5-10/月 | 約$15-30/月 | 1日数分のジョブクラスター |
| Delta Table オーバーヘッド | 約$2-5/月 | 約$10-20/月 | メタデータ、トランザクションログ、バージョン |
| **合計追加コスト** | **約$30-40/月** | **約$260-280/月** | 既存 FSx for ONTAP コストに追加 |

> これは「Databricks プラットフォームの全機能」（ACID、Time Travel、Mosaic AI、ガバナンス）のコストです。ゼロコピーパス（Athena、Snowflake External Table）はストレージ追加コスト $0 ですが、これらの機能は利用できません。

> **Databricks 顧客への重要な洞察**: DataSync → S3 → UC パスは回避策ではなく、下記の実測にもとづく**本リポジトリの推奨本番アーキテクチャ**です。ゼロコピーパスでは得られない機能を提供します: ACID トランザクション、Time Travel、MERGE、OPTIMIZE、完全な Mosaic AI、エンタープライズガバナンス。トレードオフはデータ重複と同期レイテンシです。

> **このパターンでの ONTAP の価値**: FabricPool により FSx for ONTAP 上のコールドデータは自動的に S3 に階層化（NFS/SMB ユーザーには透過的）、ストレージコストを削減。Snapshot により DataSync 転送のポイントインタイム整合性を確保 — Snapshot から同期することでデータの一貫したビューを保証。

> **SnapMirror S3 に関する注記**: NetApp ONTAP ドキュメントでは SnapMirror S3（ONTAP S3 バケット → AWS S3 レプリケーション）が ONTAP 9.10.1+ から利用可能と記載されています。しかし、**この機能は FSx for ONTAP では無効化されています**（2026年5月検証、ONTAP 9.17.1P6）。`snapmirror object-store` CLI コマンドと `/api/cloud/targets` REST API はマネージドサービス制約としてブロックされています。AWS DataSync が唯一の検証済み同期パスです。AWS に機能要望を提出済み。

**現在動作するもの（S3 コピーあり）:**

```sql
-- Provider 側: S3 上に External Volume 作成（FSx for ONTAP から同期済み）
CREATE EXTERNAL VOLUME media_files
  LOCATION 's3://fsxn-synced-bucket/unstructured-data/'
  COMMENT 'FSx for ONTAP から同期された画像、動画、PDF';

-- Volume を Share に追加
CREATE SHARE IF NOT EXISTS unstructured_data_share
  COMMENT 'パートナー向けドキュメント・メディアファイル';

ALTER SHARE unstructured_data_share
  ADD VOLUME catalog.schema.media_files;

-- Recipient に付与
GRANT SELECT ON SHARE unstructured_data_share
  TO RECIPIENT <partner_org>;
```

```sql
-- Recipient 側: 共有ファイルにアクセス
CREATE CATALOG IF NOT EXISTS shared_media
  FROM SHARE <provider_name>.unstructured_data_share;

-- ファイルメタデータクエリ
SELECT * EXCEPT (content), _metadata
FROM read_files(
  '/Volumes/shared_media/schema/media_files/',
  format => 'binaryFile'
) LIMIT 10;

-- 共有画像の AI 分析
SELECT path,
  ai_query('databricks-llama-4-maverick',
    'Describe this image:', files => content)
FROM read_files(
  '/Volumes/shared_media/schema/media_files/',
  format => 'binaryFile',
  fileNamePattern => '*.{jpg,png}')
WHERE _metadata.file_size < 5000000;

-- 共有 PDF のパース
SELECT path,
  ai_parse_document(content, map('version', '2.0'))
FROM read_files(
  '/Volumes/shared_media/schema/media_files/',
  format => 'binaryFile',
  fileNamePattern => '*.pdf');
```

**Databricks への機能リクエスト（2026年5月報告済み）:**

1. UC External Location で S3 Access Point ARN をファーストクラスのストレージロケーションとしてサポート
2. FSx for ONTAP S3 AP ARN パターンに対応した UC セッションポリシー生成の更新
3. UC Volume が FSx for ONTAP S3 AP をバックエンドストレージとして使用可能にする
4. UC ストレージ抽象化を標準 S3 バケット以外（S3 Access Points、FSx for ONTAP アタッチドアクセスポイント）に一般化
5. Databricks-to-Databricks Volume Sharing が非バケット S3 AP バックエンドで動作するか明確化

**PoC 成功基準:** Databricks が必要な UC 機能拡張を確認するか、ゼロコピー FSx for ONTAP アクセスの代替サポート設計を提供すること。

---

## パターン比較

| 観点 | Pattern A | Pattern B | Pattern C |
|-----------|-----------|-----------|-----------|
| **共有資産** | ファイルメタデータテーブル | AI 処理済みテーブル | Raw ファイル (UC Volume 経由) |
| **FSx for ONTAP 上のデータ** | 残存（直接共有しない） | 残存（派生物を共有） | 残存（直接アクセス） |
| **S3 コピー必要量** | メタデータのみ (~KB) | 派生テーブル (~MB-GB) | 全ファイル同期 (~GB-TB) |
| **PoC 複雑度** | 低 | 中 | ブロック中（Databricks UC 機能開発が必要） |
| **ガバナンス** | OpenSharing + UC | OpenSharing + UC | UC Volume ACL |
| **AI/ML 対応度** | カタログのみ | 完全（embedding, RAG） | 完全（read_files + ai_query） |
| **リアルタイム鮮度** | ポーリングベース | パイプライン依存 | ほぼリアルタイム（サポート時） |
| **Snowflake 連携** | ✅ 同じ curated Iceberg を S3 上で共有可能 | ✅ Open format で共有可能 | ❌ UC Volume は Databricks 専用 |
| **最適用途** | ファイル発見、監査 | RAG、検索、分析 | 直接ファイル処理 |

> **Open Table Format を共有データレイヤーとして活用**: Pattern A と B は S3 上に Delta/Parquet テーブルを生成します。これらのテーブルは Snowflake External Iceberg Table や AWS Glue Data Catalog テーブルとしても登録可能で、追加コピーなしに複数エンジンから同じ curated dataset にアクセスできます。これがベンダーロックインを回避しつつ、各プラットフォームのガバナンスと AI 機能を維持する「共通データ面」です。

---

## 非構造化データ: Unity Catalog での Raw ファイルの扱い

### 核心の質問: 画像、動画、PDF を「そのまま」使えるか？

**はい — UC Volume を通じて可能です。** Unity Catalog Volume はファイルを元の形式のまま保存します。Parquet や Delta に変換されません。JPEG は JPEG のまま、PDF は PDF のままです。

参照: [What are Unity Catalog volumes?](https://docs.databricks.com/aws/en/volumes/managed-vs-external) — "Volumes govern non-tabular data of any format, including structured, semi-structured, or unstructured."

### UC Volume でサポートされる非構造化ファイルフォーマット

| カテゴリ | ファイルフォーマット | AI 処理 | ユースケース |
|---------|---|---|---|
| **画像** | JPEG, PNG, GIF, BMP, TIFF, WebP, SVG, HEIC, RAW (CR2, NEF, ARW) | `ai_query()` (Vision), `ai_parse_document()` | 画像分類、品質検査、OCR |
| **ドキュメント** | PDF, DOCX, DOC, XLSX, XLS, PPTX, PPT, ODT, ODS, ODP, RTF, TXT, MD | `ai_parse_document()`, `ai_query()` | テキスト抽出、要約、RAG |
| **動画** | MP4, MOV, AVI, MKV, WebM, FLV, WMV, MPEG, 3GP | カスタム UDF（フレーム抽出） | 動画分析、シーン検出 |
| **音声** | WAV, MP3, FLAC, AAC, OGG, WMA, M4A, AIFF | カスタム UDF（文字起こし） | 音声テキスト変換、話者分離 |
| **CAD/エンジニアリング** | DWG, DXF, STEP, STL, IGES, OBJ, FBX, GLTF | カスタム UDF | 製造業、3D 分析 |
| **医療/科学** | DICOM, NIfTI, HDF5, FITS, NetCDF | カスタム UDF | 医療画像、科学データ |
| **地理空間** | GeoTIFF, Shapefile (.shp), GeoJSON, KML, GPX, LAS/LAZ (LiDAR) | カスタム UDF | マッピング、地形分析 |
| **アーカイブ** | ZIP, TAR, GZ, 7Z, RAR, BZIP2 | 展開 → 内容処理 | バッチ処理 |
| **ログ/設定** | JSON, YAML, XML, CSV, TSV, LOG, INI, TOML | `read_files()` で直接 | ログ分析、設定管理 |
| **コード/スクリプト** | PY, JS, TS, Java, C, CPP, SQL, SH, Notebook (.ipynb) | `ai_query()` でコード分析 | コードレビュー、ドキュメント生成 |
| **メール** | EML, MSG, MBOX, PST | カスタム UDF | E-discovery、コンプライアンス |
| **フォント/デザイン** | TTF, OTF, WOFF, PSD, AI, INDD, SKETCH, FIG | カスタム UDF | アセット管理 |

### Databricks で非構造化データが見える3つの方法

#### 方法 1: UC Volume（ファイルは元の形式のまま）

```
Unity Catalog
  └── Catalog: enterprise_data
       └── Schema: raw_media
            └── Volume: fsxn_files (External Volume on S3)
                 ├── images/
                 │    ├── product_photo_001.jpg     ← 元の JPEG (2.3 MB)
                 │    ├── xray_scan_042.dicom       ← 元の DICOM (15 MB)
                 │    └── floor_plan.dwg            ← 元の CAD (8 MB)
                 ├── videos/
                 │    ├── security_cam_2026-05-26.mp4  ← 元の MP4 (1.2 GB)
                 │    └── training_session.webm     ← 元の WebM (450 MB)
                 ├── documents/
                 │    ├── contract_v3.pdf           ← 元の PDF (340 KB)
                 │    ├── financial_report.xlsx     ← 元の Excel (2.1 MB)
                 │    └── meeting_notes.docx        ← 元の Word (89 KB)
                 ├── audio/
                 │    ├── customer_call_001.wav     ← 元の WAV (45 MB)
                 │    └── podcast_ep12.mp3          ← 元の MP3 (62 MB)
                 └── scientific/
                      ├── brain_mri.nii.gz          ← 元の NIfTI (120 MB)
                      └── sensor_data.hdf5          ← 元の HDF5 (3.4 GB)
```

**UC から見える姿**: ファイルパス、サイズ、更新日時。Volume レベルの権限でガバナンス。

**ユーザーができること**:
```sql
-- 全ファイル一覧
SELECT * FROM DIRECTORY('/Volumes/enterprise_data/raw_media/fsxn_files/');

-- ファイル内容をバイナリとして読み取り
SELECT path, content FROM read_files(
  '/Volumes/enterprise_data/raw_media/fsxn_files/documents/',
  format => 'binaryFile'
);

-- 画像の AI 分析（Vision モデル）
SELECT path,
  ai_query('databricks-llama-4-maverick',
    'Describe this image in detail:', files => content) AS description
FROM read_files(
  '/Volumes/enterprise_data/raw_media/fsxn_files/images/',
  format => 'binaryFile',
  fileNamePattern => '*.{jpg,jpeg,png}')
WHERE _metadata.file_size < 10000000;

-- PDF ドキュメントのパース
SELECT path,
  ai_parse_document(content, map('version', '2.0')) AS parsed
FROM read_files(
  '/Volumes/enterprise_data/raw_media/fsxn_files/documents/',
  format => 'binaryFile',
  fileNamePattern => '*.pdf');
```

参照: [Work with unstructured data in volumes](https://docs.databricks.com/aws/en/volumes/unstructured-data-tutorial)

#### 方法 2: Delta Table に binaryFile として取り込み（ファイル内容が Parquet 内に格納）

```sql
CREATE TABLE image_embeddings AS
SELECT
  path,
  _metadata.file_name,
  _metadata.file_size,
  _metadata.file_modification_time,
  content  -- 元ファイルのバイト列が Parquet の BINARY カラムに格納される
FROM read_files(
  '/Volumes/enterprise_data/raw_media/fsxn_files/images/',
  format => 'binaryFile'
);
```

**元ファイルに何が起きるか**:
- ファイルのバイナリ内容が **Parquet ファイル内の BINARY カラムにコピー**される
- 元ファイルは Volume 上にそのまま残る（削除されない）
- Delta Table にはバイト列の**コピー**が含まれる（参照ではない）
- テーブル内ではファイルは元の形式ではない — Parquet 内のバイト配列

**使用すべき場面**: ファイル内容自体に ACID、Time Travel、OpenSharing が必要な場合。

#### 方法 3: メタデータのみテーブル化（ファイルは元の場所に残る）

```sql
CREATE TABLE file_catalog AS
SELECT
  path,
  _metadata.file_name AS file_name,
  _metadata.file_size AS size_bytes,
  _metadata.file_modification_time AS last_modified,
  SPLIT_PART(_metadata.file_name, '.', -1) AS extension
FROM read_files(
  '/Volumes/enterprise_data/raw_media/fsxn_files/',
  format => 'binaryFile'
);
```

**元ファイルに何が起きるか**: 何も起きない — ファイルはそのまま元の場所に残る。テーブルにはメタデータ（パス、サイズ、タイムスタンプ）のみ含まれる。実際のファイル内容にアクセスするには、`path` カラムを使って Volume から読み取る。

### 比較: 元ファイルはどうなるか？

| 方法 | 元ファイル形式が保持されるか？ | ファイルの所在 | UC ガバナンスレベル | OpenSharing 対応？ |
|------|:---:|---|---|---|
| **UC Volume** | ✅ はい（JPEG は JPEG のまま） | Volume ストレージ（S3 バケット） | Volume レベル (READ/WRITE VOLUME) | ✅ Volume Sharing |
| **Delta Table (binaryFile)** | ❌ いいえ（Parquet 内のバイト列） | Delta Table（Parquet ファイル） | テーブルレベル (SELECT, カラムマスク) | ✅ Table Sharing |
| **メタデータのみテーブル** | ✅ はい（ファイル未変更） | 元の場所（Volume/Stage） | テーブルレベル（メタデータ）+ Volume レベル（ファイルアクセス） | ⚠️ メタデータのみ共有 |

### FSx for ONTAP S3 AP: 各方法の現在のステータス

| 方法 | FSx for ONTAP S3 AP 直接？ | S3 同期あり？ | 備考 |
|------|:---:|:---:|---|
| UC Volume (External) | ❌ ブロック中 | ✅ 動作 | DataSync → S3 → External Volume が必要 |
| UC Volume (Managed) | N/A | ✅ 動作 | Managed Volume にファイルをコピー |
| Delta Table (binaryFile) | ❌ ブロック中 | ✅ 動作 | 同期済み Volume から読み取り、Delta Table に書き込み |
| メタデータのみテーブル | ✅ 可能 (Pattern A) | ✅ 動作 | FSx for ONTAP S3 AP で ListObjectsV2 → メタデータテーブル |

### 重要なポイント

**UC Volume は非構造化データの「変換なし」パス**です — ファイルは元の形式のまま、UC でガバナンスされ、SQL (`read_files`)、Python (`dbutils.fs`)、AI 関数 (`ai_query`, `ai_parse_document`) でアクセス可能です。

FSx for ONTAP のブロッカーはファイル形式ではありません — **UC が FSx for ONTAP S3 AP をストレージロケーションとして登録できない**ことです。これが解決されれば（Databricks 機能開発）、FSx for ONTAP 上のファイルはフォーマット変換なしで UC Volume を通じて直接アクセスできるようになります。

### Databricks 上での非構造化ファイルのレンダリング・閲覧

**ユーザーは Databricks 上で画像を見たり、動画を再生したり、音声を聴いたり、PDF を読んだりできるか？**

#### UC Volume パス（元ファイルのまま — ガバナンス付きファイル閲覧に推奨）

UC Volume 内のファイルはパスでアクセスし、ノートブック上で直接レンダリング可能:

```python
# === 画像 (JPEG, PNG, TIFF, DICOM 等) ===
from IPython.display import display, Image

# Volume から画像を直接表示
display(Image(filename="/Volumes/catalog/schema/media/images/inspection_001.jpg"))

# 複数画像をギャラリーとして表示
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

fig, axes = plt.subplots(1, 3, figsize=(15, 5))
for i, img_path in enumerate([
    "/Volumes/catalog/schema/media/images/assembly_line_cam01.jpg",
    "/Volumes/catalog/schema/media/images/quality_check_042.png",
    "/Volumes/catalog/schema/media/images/weld_inspection.tiff"
]):
    axes[i].imshow(mpimg.imread(img_path))
    axes[i].set_title(img_path.split("/")[-1])
plt.show()
```

```python
# === PDF・ドキュメント ===
from IPython.display import display, IFrame, HTML

# PDF をインラインでレンダリング
display(IFrame(src="/Volumes/catalog/schema/media/documents/safety_manual.pdf",
               width=800, height=600))

# AI で PDF からテキスト抽出
df = spark.sql("""
  SELECT path,
    ai_parse_document(content, map('version', '2.0')) AS parsed_text
  FROM read_files(
    '/Volumes/catalog/schema/media/documents/',
    format => 'binaryFile',
    fileNamePattern => '*.pdf')
""")
display(df)
```

```python
# === 音声 (WAV, MP3, FLAC 等) ===
from IPython.display import display, Audio

# Volume から音声ファイルを直接再生
display(Audio(filename="/Volumes/catalog/schema/media/audio/customer_call_001.wav"))
display(Audio(filename="/Volumes/catalog/schema/media/audio/machine_vibration.mp3"))
```

```python
# === 動画 (MP4, WebM, MOV 等) ===
from IPython.display import display, Video

# Volume から動画を再生
display(Video(filename="/Volumes/catalog/schema/media/videos/assembly_process.mp4",
              embed=True, width=640))

# 大きな動画は HTML5 video タグで
from IPython.display import HTML
display(HTML('''
  <video width="640" controls>
    <source src="/Volumes/catalog/schema/media/videos/robot_arm_cycle.webm"
            type="video/webm">
  </video>
'''))
```

```python
# === 3D/CAD ファイル (STL, OBJ, GLTF) ===
import trimesh

# 3D モデルを読み込み・可視化
mesh = trimesh.load("/Volumes/catalog/schema/media/cad/part_assembly.stl")
mesh.show()  # ノートブック内で 3D ビューアが開く
```

```python
# === 医療画像 (DICOM) ===
import pydicom
import matplotlib.pyplot as plt

# DICOM 画像を読み込み・表示
ds = pydicom.dcmread("/Volumes/catalog/schema/media/medical/chest_xray.dcm")
plt.imshow(ds.pixel_array, cmap='gray')
plt.title(f"Patient: {ds.PatientName}, Study: {ds.StudyDescription}")
plt.show()
```

参照: [Work with files in Unity Catalog volumes](https://docs.databricks.com/aws/en/volumes/volume-files) — "You can use standard Python, Scala, or R libraries to read and write files in volumes."

参照: [Work with unstructured data in volumes](https://docs.databricks.com/aws/en/volumes/unstructured-data-tutorial) — 画像、PDF、AI 処理の完全チュートリアル。

#### Delta Table パス（binaryFile — Parquet 内にバイト列として格納）

ファイルが Delta Table の BINARY カラムに格納されている場合でもレンダリング可能だが、デコードステップが追加で必要:

```python
# Delta Table から画像バイト列を読み取り
df = spark.read.table("shared_catalog.schema.image_table")
row = df.filter("file_name = 'inspection_001.jpg'").first()

# デコードして表示
from IPython.display import display, Image
display(Image(data=row.content))  # 'content' は BINARY カラム

# Delta Table から音声を再生
from IPython.display import Audio
audio_row = df.filter("file_name = 'machine_sound.wav'").first()
display(Audio(data=audio_row.content, rate=44100))
```

```python
# Databricks の display() は BINARY カラムをサムネイルとして自動レンダリング
display(spark.read.table("shared_catalog.schema.image_table")
        .select("path", "content", "file_name"))
# → Databricks UI が content カラムに画像サムネイルを表示
```

参照: [Databricks display() function](https://docs.databricks.com/aws/en/notebooks/notebooks-manage#display-function) — Databricks ノートブックはバイナリ画像データをインラインでレンダリング可能。

#### 比較: ガバナンス付きファイル閲覧のユーザー体験

| 観点 | UC Volume（元ファイル） | Delta Table (binaryFile) |
|------|---|---|
| **画像閲覧** | ✅ パス直接 → `Image(filename=...)` | ✅ バイト列デコード → `Image(data=...)` |
| **動画再生** | ✅ `Video(filename=...)` or HTML5 `<video>` | ⚠️ バイト列を一時ファイルに書き出す必要あり |
| **音声再生** | ✅ `Audio(filename=...)` | ⚠️ `Audio(data=bytes, rate=...)` |
| **PDF レンダリング** | ✅ `IFrame(src=path)` | ⚠️ バイト列を一時ファイルに書き出す必要あり |
| **3D/CAD 閲覧** | ✅ `trimesh.load(path)` | ⚠️ バイト列を一時ファイルに書き出す必要あり |
| **DICOM 医療画像** | ✅ `pydicom.dcmread(path)` | ⚠️ バイト列からデシリアライズ必要 |
| **サムネイルギャラリー** | ✅ Catalog Explorer のファイルブラウザ | ⚠️ カスタムノートブックコード必要 |
| **ファイルダウンロード** | ✅ Volume から直接ダウンロード | ⚠️ バイト列抽出 → 保存 → ダウンロード |
| **共有受信者の体験** | ファイルエクスプローラー（フォルダ閲覧） | テーブルビュー（行と列） |
| **非技術者フレンドリー** | ✅ 馴染みのあるファイル/フォルダナビゲーション | ❌ SQL/Python の知識が必要 |

**ガバナンス付きファイル閲覧の結論**: UC Volume + Volume Sharing は**ファイルシステムのようなブラウジング体験**を提供し、非技術者（工場作業者、管理者、監査人）がフォルダをナビゲートしてファイルを直接閲覧できます。Delta Table (binaryFile) は各ファイルのレンダリングにノートブックコードが必要で、データエンジニア向けには適していますが、ブラウズ可能なガバナンス付きファイルアクセスには不向きです。

---

## Provider vs Recipient: 役割の明確化

| 役割 | Databricks が Provider | Databricks が Recipient |
|------|---|---|
| **データ所在** | UC 内にデータが必要（S3 バケット） | どこでも可（FSx for ONTAP → 処理 → 共有） |
| **ガバナンス** | UC がアクセスを統制 | Provider が統制; UC はローカルポリシー適用 |
| **アーキテクチャ** | FSx for ONTAP → S3 → UC → Share | FSx for ONTAP → Lambda/Glue → Delta table → OSS OpenSharing Server → Databricks |
| **複雑度** | シンプル（UC が全て処理） | 柔軟（顧客管理の共有サーバー） |
| **推奨対象** | Databricks 中心の組織 | マルチプラットフォーム環境 |

**重要な洞察**: Databricks が**受信者**の場合、顧客管理の [OSS OpenSharing サーバー](https://github.com/delta-io/delta-sharing)が FSx for ONTAP ベースのデータセットを UC にデータを置くことなく公開できます。

---

## ガバナンスレイヤー

| レイヤー | スコープ | 適用ポイント |
|-------|-------|-------------------|
| FSx ファイル権限 | NFS/SMB ACL, UNIX ユーザー | FSx for ONTAP |
| S3 AP ポリシー | IAM ベース、アクセスポイント単位 | AWS IAM |
| FPolicy | ファイル操作の監査/ブロック | ONTAP |
| OpenSharing | Share レベル、Recipient レベル | 共有サーバーまたは UC |
| Unity Catalog | テーブル/Volume/カラム/行レベル | Databricks |

本番デプロイでは、組織要件に基づいて**主要ガバナンスポイント**を定義してください。

---

## データ鮮度の考慮事項

| 鮮度要件 | 推奨パターン | メカニズム |
|---|---|---|
| 日次 | Pattern A or B | スケジュール Glue/Lambda ジョブ |
| 時間単位 | Pattern A or B | Step Functions + CloudWatch Events |
| 準リアルタイム（分） | Pattern A + FPolicy | FPolicy → Lambda → 差分更新 |
| リアルタイム（秒） | Pattern C（将来） | 直接 FSx for ONTAP S3 AP アクセス（UC サポート必要） |

---

## 推奨 PoC ロードマップ

```
Phase 1: Pattern A — ファイルメタデータ共有
├── Lambda 関数: FSx for ONTAP S3 AP で ListObjectsV2 → Parquet テーブル
├── OpenSharing: メタデータテーブルを Databricks に公開
├── Databricks: ファイルカタログをクエリ、タイプ/日付/サイズでフィルタ
└── 成功: Databricks がガバナンス付き FSx for ONTAP ファイルインベントリを参照可能

Phase 2: Pattern B — AI 処理済み共有
├── Textract: FSx for ONTAP 上の PDF からテキスト抽出
├── Bedrock: embedding と要約を生成
├── Delta テーブル: チャンク + embedding を保存
├── OpenSharing: Databricks に公開
└── 成功: Databricks Vector Search で FSx for ONTAP 由来コンテンツを検索可能

Phase 3: Pattern C — ブロック中（Databricks UC 機能開発が必要）
├── 機能ギャップを Databricks UC エンジニアリングに報告済み（2026年5月）
├── UC エンジニアリングの回答とタイムラインを追跡
├── サポートされた場合: 直接 FSx for ONTAP S3 AP → UC Volume → Volume Sharing
└── それまで: Pattern A/B + Raw ファイルは S3 同期を継続（唯一の本番対応パス）
```

---

## FAQ: なぜ「EC2 で Delta Table を作るだけ」では ETL 不要にならないのか？

よくある誤解として、OpenSharing は純粋にメタデータの問題であり、FSx for ONTAP 上のファイルに Delta Table を向けるだけで ETL やデータ移動なしに共有できる、というものがあります。このセクションでは、なぜそれが成立しないかを Databricks ドキュメントの参照付きで説明します。

### 誤解: 「OpenSharing はメタデータだけの問題なので、EC2 で Delta Table を作って共有すればよい」

**前提の想定**: FSx for ONTAP にファイルがある → EC2 インスタンスがそのファイルを指す Delta Table を作成 → OpenSharing でテーブルを公開 → Databricks が読む。ETL なし、コピーなし。

**FSx for ONTAP S3 Access Points でこれが動作しない理由:**

#### 1. Delta Table ≠ 任意のファイルへのポインタ

Delta Table は既存ファイルを指すだけのメタデータではありません。以下で構成される**特定のストレージフォーマット**です：
- Parquet データファイル（実データ）
- `_delta_log/` ディレクトリ内の JSON コミットファイル（トランザクションログ）

トランザクションログはテーブルへの全変更を記録し、ACID 保証を提供するものです。Delta Table の作成には、Parquet ファイルとコミットログの**両方をストレージロケーションに書き込む**必要があります。

参照: [What are ACID guarantees on Databricks?](https://docs.databricks.com/aws/lakehouse/acid) — "Databricks uses Delta Lake by default for all reads and writes and builds upon the ACID guarantees provided by the open source Delta Lake protocol."

#### 2. Delta Lake コミットプロトコルには条件付き書き込みが必要

Delta Lake の S3 上でのコミットプロトコルには以下のいずれかが必要です：
- **put-if-absent**（条件付き書き込み）セマンティクス、または
- **DynamoDB ベースのコミットコーディネーター**（マルチクラスター書き込み用）

FSx for ONTAP S3 Access Points は**条件付き書き込みをサポートしていません**（`If-None-Match` ヘッダーは "not supported" を返す）。これは：
- FSx for ONTAP S3 AP に Delta コミットログを安全に書き込めない
- 並行ライターがトランザクションログを破損する
- 単一ライターでもアトミックなコミットを保証できない

ことを意味します。

参照: [Multi-cluster writes to Delta Lake on S3](https://delta.io/blog/2022-05-18-multi-cluster-writes-to-delta-lake-storage-in-s3/) — "S3 currently lacks 'put-If-Absent' consistency guarantees. Thus, to guarantee ACID transactions on S3, one would need to have concurrent writes originating from the same Apache Spark driver."

参照: [Delta Lake storage configuration](http://docs.delta.io/latest/delta-storage.html) — "Delta Lake uses the scheme of the path to dynamically identify the storage system and use the corresponding LogStore implementation that provides the transactional guarantees."

#### 3. S3 上の Delta Lake には `_delta_log` 用の特定 IAM 権限が必要

標準 S3 上でも、Delta Lake は基本的な読み書き以上の特定権限を要求します：
- `s3:PutObject` — データファイルとコミットログファイル用
- `s3:GetObject` — 最新コミットバージョンの読み取り用
- `s3:ListBucket` — コミットログエントリの発見用
- `s3:DeleteObject` — VACUUM 操作用

FSx for ONTAP S3 AP では、UC セッションポリシーが `PutObject` とサブディレクトリの `ListBucket` をブロックするため、UC ガバナンス下での Delta Table 作成は不可能です。

参照: [Access denied when writing Delta Lake tables to S3](https://kb.databricks.com/en_US/delta/s3-permissions-delta) — "Delta Lake requires creation of a _delta_log directory. The write operation also needs to check the latest version of the commit logs."

#### 4. OpenSharing にはテーブルの Unity Catalog 登録が必要

OpenSharing（Databricks-to-Databricks プロトコル）は **Unity Catalog に登録されたテーブル**を共有します。UC に登録されたテーブルは以下のいずれかに存在する必要があります：
- **UC Managed Storage** ロケーション（Databricks 管理の S3 バケット）、または
- **UC External Location**（Storage Credential で登録された顧客 S3 バケット）

FSx for ONTAP S3 AP は UC External Location 経由で読み取れません。登録は成功し、通らないのは読み取りです（Unity Catalog が払い出す down-scoped セッションポリシーがバケット形式 ARN のため。2026-08-12 実測）。したがって、仮に FSx for ONTAP S3 AP 上に Delta Table を作成できたとしても、共有のために UC に登録することはできません。

参照: [Create and manage shares for OpenSharing](https://docs.databricks.com/en/delta-sharing/create-share.html) — Share は "only one Unity Catalog metastore" のアセットのみ含むことができる。

参照: [What is the OpenSharing Databricks-to-Databricks protocol?](https://docs.databricks.com/aws/en/delta-sharing/share-data-databricks) — UC 対応ワークスペースと UC 登録アセットが必要。

#### 5. OSS OpenSharing Server でも有効な Delta Table が必要

[OSS OpenSharing サーバー](https://github.com/delta-io/delta-sharing)を使用する場合（UC をバイパス）でも、サーバーは一貫した `_delta_log` を持つ有効な Delta Table を指す必要があります。同じストレージ要件が適用されます — Delta コミットプロトコルをサポートするストレージバックエンドが必要です。

### 「EC2 で Delta Table を作成する」とは実際に何を意味するか

EC2 上で Spark ジョブを実行し、FSx for ONTAP S3 AP からファイルを読み取って Delta Table を書き込む場合、それは ETL を実行しています：

```
FSx for ONTAP S3 AP (ソースファイル: CSV, Parquet, JSON, 画像)
  ↓ GetObject (読み取り)
EC2 / EMR / Glue (Spark ジョブ)
  ↓ spark.read → 変換 → spark.write.format("delta")
S3 バケット (Delta Table: Parquet ファイル + _delta_log/)
  ↓ UC に登録
OpenSharing
```

これは「メタデータだけ」ではありません。以下を行っています：
1. FSx for ONTAP S3 AP からソースファイルを**読み取り** (GetObject)
2. Delta スキーマの Parquet フォーマットに**変換**
3. Parquet データファイル + コミットログを別のストレージロケーション（S3 バケット）に**書き込み**
4. テーブルを Unity Catalog に**登録**

これは定義上 ETL です。"E" (Extract) は FSx for ONTAP からの読み取り。"T" (Transform) は Delta フォーマットへの変換。"L" (Load) は S3 への書き込みです。

### まとめ: なぜ S3 バケットが必要か

| ステップ | FSx for ONTAP S3 AP 単独では不十分な理由 |
|---------|---|
| Delta コミットログの書き込み | FSx for ONTAP S3 AP で条件付き書き込みが非サポート |
| UC への登録 | UC External Location が S3 AP ARN を非サポート |
| マルチクラスター安全性 | FSx for ONTAP S3 AP 用の DynamoDB LogStore 相当がない |
| OpenSharing | UC 登録テーブルまたはサポートされたストレージ上の有効な Delta Table が必要 |

### 唯一の真の「Zero Copy」パス

データコピーが発生しない唯一のシナリオは **Pattern C**（UC Volume Sharing）です — ただし Databricks が FSx for ONTAP S3 AP をファーストクラスの UC ストレージロケーションとしてサポートする必要があります。Volume Sharing はテーブルデータではなくファイル参照を共有するため、Delta コミットログは不要です。

**現在のステータス**: ブロック中 — Databricks UC 機能開発待ち（2026 年 5 月報告済み、タイムラインなし）。

### 代替案: OSS OpenSharing Server による Parquet 直接参照（実験的、未検証）

[OSS OpenSharing サーバー](https://github.com/delta-io/delta-sharing)は、完全な Delta コミットログなしで Parquet ファイルを共有することをサポートしています。FSx for ONTAP S3 AP 上に既知のスキーマを持つ構造化された Parquet ファイルが既に存在する場合、OSS サーバーがそれらを共有テーブルとして公開できる可能性があります。

**動作の仕組み:**
1. Parquet ファイルが FSx for ONTAP 上に存在（ETL ジョブ、NFS クライアント、他のエンジンが書き込み）
2. OSS OpenSharing サーバーが S3 AP パスを指す `delta-sharing-server.yaml` で設定
3. Recipient が OpenSharing プロトコル経由で共有「テーブル」をクエリ

**制約とリスク:**
- ACID 保証なし（コミットログなし = トランザクション分離なし）
- スキーマ進化追跡なし（スキーマは外部管理が必要）
- Time Travel やバージョニングなし
- 同じ Parquet ファイルへの並行書き込みが不整合な読み取りを生む可能性
- OSS サーバーが S3 AP パスの署名付き URL を生成できる必要あり（S3 AP アクセス権限付き IAM ロールが必要）
- これは Databricks サポート対象パスではない — Unity Catalog を完全にバイパス

**検討すべき場面**: 「FSx for ONTAP 上の既存 Parquet ファイルをデータ移動なしで外部消費者に公開する」要件があり、かつガバナンス/ACID 要件が最小限の場合のみ。ガバナンスが必要な本番ワークロードには、DataSync → S3 → UC パスを使用してください。

> **検証ステータス**: このアプローチは FSx for ONTAP S3 Access Points に対して**未検証**です。Pattern A PoC 検証の一環として検証予定の理論的代替案として記載しています。主な未知数: OSS サーバーが FSx for ONTAP S3 AP パスの有効な署名付き URL を生成できるか、ListObjectsV2 レイテンシが共有プロトコルのファイル検出に影響するか。

---

## 次のステップ

1. **Pattern A PoC を開始**: FSx for ONTAP S3 AP で ListObjectsV2 を呼び出す Lambda 関数をデプロイし、メタデータを S3 上の Delta Table に書き込み、OpenSharing で公開
2. **Databricks への即時アクセス**: DataSync → S3 → UC External Location を設定して完全ガバナンスを実現（[README 設定ガイド](../../README.md#quick-start)）
3. **Databricks 機能ギャップを追跡**: UC エンジニアリングの FSx for ONTAP S3 AP ネイティブサポートへの回答を監視（2026年5月報告済み、タイムラインなし）

---

## 参考資料

- [Work with unstructured data in volumes](https://docs.databricks.com/aws/en/volumes/unstructured-data-tutorial) — Volume Sharing を含む完全チュートリアル
- [What are Unity Catalog volumes?](https://docs.databricks.com/aws/en/volumes/managed-vs-external) — Managed vs External volumes
- [Volume Sharing with OpenSharing (Video)](https://www.databricks.com/resources/demos/videos/data-sharing/volume-sharing-delta-sharing) — デモ動画
- [Create and manage shares](https://docs.databricks.com/en/delta-sharing/create-share.html) — Share に Volume を追加する手順
- [OpenSharing OSS](https://github.com/delta-io/delta-sharing) — オープンソース OpenSharing サーバー
- [FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) — AWS ドキュメント

---

## 関連ドキュメント

- [Databricks README](../../README.md) — 統合ステータスとアーキテクチャ全体
- [Analytics & AI デモガイド](ai-demo-guide.md) — AI/ML 機能と現在のステータス
- [ブロッカートラッカー](../../../../docs/ja/blocker-tracker.md) — BLK-001 に Unity Catalog / S3 Access Point の制約、確認日、利用可能な回避策を記載
