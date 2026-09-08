🌐 [English](../en/ai-demo-guide.md) | **日本語**

# Snowflake Analytics & AI デモガイド — FSx for ONTAP S3 AP

本ガイドでは、`AWS_ACCESS_POINT_ARN` を使用した Snowflake [External Stage](https://docs.snowflake.com/en/user-guide/data-load-s3-create-stage) 経由で FSx for ONTAP データに対する分析および AI/ML 機能を実演します。

> 📖 **外部テーブル vs 内部テーブル**（ゼロコピー vs COPY INTO）の詳細比較、判断フローチャート、コスト分析については [内部テーブル vs 外部テーブル設計ガイド](../../README.md) の該当セクションを参照してください。

## 前提条件

- Cortex AI が有効な Snowflake アカウント
- FSx for ONTAP S3 Access Point の設定完了
- `AWS_ACCESS_POINT_ARN` を使用した External Stage（[README](../../README.md) 参照）

## デモ 1: OCR テキスト抽出 (PARSE_DOCUMENT)

**ユースケース**: NAS に保存された検査報告書、請求書、品質文書からテキストを抽出。

```sql
-- OCR: FSx for ONTAP 上の画像からテキスト抽出
SELECT SNOWFLAKE.CORTEX.PARSE_DOCUMENT(
  @fsxn_stage,
  'media/documents/invoice_sample.png',
  {'mode': 'OCR'}
) AS ocr_result;
```

**結果**: 画像から構造化テキストを抽出（約8秒）。

![PARSE_DOCUMENT OCR が FSx for ONTAP S3 AP 上の画像からテキストを抽出](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-08-parse-document-ocr.png)

*PARSE_DOCUMENT が FSx for ONTAP S3 Access Point 経由で保存された請求書画像からテキストを抽出。請求書番号、顧客名、金額などの構造化フィールドを含む結果を返却。*

**製造業ユースケース**: NFS に保存された紙ベースの検査報告書をデジタル化し、手動データ入力なしで検索・分析可能に。

## デモ 2: AI テキスト要約 (CORTEX.SUMMARIZE)

**ユースケース**: センサーデータ、ログファイル、ドキュメント内容を要約し、迅速なインサイトを取得。

```sql
-- External Table からセンサーデータを要約
SELECT SNOWFLAKE.CORTEX.SUMMARIZE(VALUE::VARCHAR) AS ai_summary
FROM fsxn_sensor_ext_table
LIMIT 1;
```

**結果**: "The text is a JSON object containing data on humidity, pressure, temperature, sensor ID, status, and timestamp."（3.3秒）

![Cortex SUMMARIZE が External Table 経由で FSx for ONTAP S3 AP データの AI 要約を生成](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-07-cortex-llm-summary.png)

*Cortex SUMMARIZE が FSx for ONTAP に保存されたセンサーデータの AI 要約を生成（External Table 経由、3.3秒）。*

**製造業ユースケース**: FSx for ONTAP に保存された IoT センサーデータからシフトサマリーを自動生成。

## デモ 3: ファイルカタログ + ダウンロード URL

**ユースケース**: 非構造化データ（画像、動画、ドキュメント）を検索可能なライブラリとして管理。

```sql
-- ファイルカタログを有効化
ALTER STAGE fsxn_stage SET DIRECTORY = (ENABLE = TRUE);
ALTER STAGE fsxn_stage REFRESH;

-- 検査画像を検索
SELECT RELATIVE_PATH, SIZE, LAST_MODIFIED,
  GET_PRESIGNED_URL(@fsxn_stage, RELATIVE_PATH, 3600) AS DOWNLOAD_URL
FROM DIRECTORY(@fsxn_stage)
WHERE RELATIVE_PATH LIKE 'media/images/%'
ORDER BY LAST_MODIFIED DESC;
```

**結果**: 各画像のダウンロード URL 付きファイルカタログ。

![Directory Table が FSx for ONTAP S3 AP 上の非構造化データをカタログ化し presigned URL を生成](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-06-directory-table-presigned-url.png)

*Directory Table が FSx for ONTAP 上の画像ファイルをメタデータ付きでカタログ化し、各ファイルのダウンロード URL を生成。*

**製造業ユースケース**: 品質エンジニアが日付/場所で検査写真を検索し、レビュー用にダウンロード。

## デモ 4: Vision AI による欠陥検出（検証中）

**ユースケース**: 製品品質検査に対する自然言語指示。

```sql
-- Vision AI: 製品検査画像を分析（構文要検証）
SELECT SNOWFLAKE.CORTEX.AI_COMPLETE(
  'claude-3-5-sonnet',
  'Analyze this product inspection image and identify any defects or quality issues.',
  {'image': BUILD_SCOPED_FILE_URL(@fsxn_stage, 'media/images/product_inspection.png')}
) AS defect_analysis;
```

**ステータス**: ✅ **回避策で検証済み** — ファイルを暗号化なし[内部ステージ](https://docs.snowflake.com/en/user-guide/data-load-local-file-system-create-stage)にコピーすれば Vision AI が動作。FSx for ONTAP S3 AP [外部ステージ](https://docs.snowflake.com/en/user-guide/data-load-s3-create-stage)への直接 `TO_FILE()` は "Remote file not found" を返す。アーキテクチャのトレードオフについては[内部テーブル vs 外部テーブル設計ガイド](../../README.md)を参照。

**回避策（検証済み）**:
```sql
-- Step 1: FSx for ONTAP S3 AP から暗号化なし内部ステージにファイルをコピー
CREATE OR REPLACE STAGE fsxn_ai_noenc_stage ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
COPY FILES INTO @fsxn_ai_noenc_stage FROM @fsxn_ap_arn_test_stage/media/documents/invoice_sample.png;
ALTER STAGE fsxn_ai_noenc_stage SET DIRECTORY = (ENABLE = TRUE);
ALTER STAGE fsxn_ai_noenc_stage REFRESH;

-- Step 2: Cross-Region Inference を有効化（ap-northeast-1 で Vision モデルに必要）
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';

-- Step 3: Vision AI を実行
SELECT SNOWFLAKE.CORTEX.COMPLETE(
  'pixtral-large',
  '請求書画像を説明してください。請求書番号、顧客名、合計金額は？',
  FILE
) AS vision_result
FROM (
  SELECT TO_FILE(BUILD_SCOPED_FILE_URL(@fsxn_ai_noenc_stage, RELATIVE_PATH)) AS FILE
  FROM DIRECTORY(@fsxn_ai_noenc_stage)
  WHERE RELATIVE_PATH LIKE '%.png' LIMIT 1
);
```

**結果**: ✅ Vision AI が正確に識別: Invoice #INV-2026-0524, Customer: Acme Corp, Amount: USD 1,234.56（41秒）

![Vision AI が FSx for ONTAP の請求書画像を正常に分析（内部ステージ回避策経由）](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-15-vision-ai-success.png)

*Cortex COMPLETE (pixtral-large) が FSx for ONTAP に保存された画像から請求書詳細を正確に抽出。COPY FILES → 内部ステージ → TO_FILE 回避策を使用。*

**FSx for ONTAP S3 AP で直接 TO_FILE が失敗する理由**:

![TO_FILE が FSx for ONTAP S3 AP 外部ステージで "Remote file not found" を返す](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-10-tofile-remote-not-found.png)

*TO_FILE() は FSx for ONTAP S3 AP 外部ステージのファイルを解決できない。同じファイルは PARSE_DOCUMENT（異なるファイルアクセスメカニズムを使用）ではアクセス可能だが、TO_FILE では不可。*

**製造業ユースケース**: 自動視覚品質検査 — 「このコンポーネントの傷を特定」「このアセンブリのアライメントを確認」などの自然言語指示。現時点では COPY FILES 回避策が必要。

## デモ 5: テキストベース Cortex AI 関数（全て動作）

全てのテキストベース Cortex AI 関数が FSx for ONTAP S3 AP External Table データで回避策なしに直接動作:

```sql
-- TRANSLATE: センサーステータスを日本語に翻訳
SELECT SNOWFLAKE.CORTEX.TRANSLATE(VALUE:status::VARCHAR, 'en', 'ja') AS translated
FROM fsxn_sensor_ext_table LIMIT 1;

-- SENTIMENT: テキストデータの感情分析
SELECT SNOWFLAKE.CORTEX.SENTIMENT(VALUE:status::VARCHAR) AS sentiment_score
FROM fsxn_sensor_ext_table LIMIT 3;

-- COMPLETE (テキストのみ): センサーデータの AI 分析
SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-large2',
  'この IoT センサー読み取り値を分析し異常を特定: ' || VALUE::VARCHAR
) AS ai_analysis FROM fsxn_sensor_ext_table LIMIT 1;

-- EXTRACT_ANSWER: 特定情報の抽出
SELECT SNOWFLAKE.CORTEX.EXTRACT_ANSWER(VALUE::VARCHAR,
  'センサー ID と温度の読み取り値は？'
) AS extracted FROM fsxn_sensor_ext_table LIMIT 1;
```

![CORTEX.TRANSLATE が FSx for ONTAP S3 AP の External Table データを正常に翻訳](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-11-cortex-translate-success.png)

*CORTEX.TRANSLATE が FSx for ONTAP S3 AP 上の External Table からセンサーステータステキストを英語から日本語に翻訳（5.1秒）。*

![CORTEX.COMPLETE が FSx for ONTAP S3 AP のセンサーデータの AI 分析を生成](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-12-cortex-complete-text-success.png)

*CORTEX.COMPLETE (mistral-large2) が FSx for ONTAP に保存された IoT センサーデータの詳細な AI 分析を生成（16秒）。*

## Cortex AI 包括的互換性マトリクス

| 関数 | 入力ソース | FSx for ONTAP S3 AP 直接 | 回避策 | 所要時間 |
|---|---|:---:|:---:|---|
| **PARSE_DOCUMENT (OCR)** | ステージパス文字列 | ✅ 直接 | — | 約8秒 |
| **CORTEX.SUMMARIZE** | External Table カラム | ✅ 直接 | — | 3.3秒 |
| **CORTEX.TRANSLATE** | External Table カラム | ✅ 直接 | — | 5.1秒 |
| **CORTEX.SENTIMENT** | External Table カラム | ✅ 直接 | — | 2.5秒 |
| **CORTEX.COMPLETE (テキスト)** | External Table カラム | ✅ 直接 | — | 16秒 |
| **CORTEX.EXTRACT_ANSWER** | External Table カラム | ✅ 直接 | — | 2.7秒 |
| **COMPLETE (vision/multimodal)** | TO_FILE + 画像 | ❌ Remote file not found | ✅ COPY FILES → 内部ステージ | 41秒 |
| **TO_FILE on 外部ステージ** | FSx for ONTAP S3 AP ステージ | ❌ 非サポート | COPY FILES to internal | — |
| **TO_FILE on 暗号化内部ステージ** | デフォルト内部ステージ | ❌ 暗号化非サポート | SNOWFLAKE_SSE を使用 | — |

### 重要な発見

1. **テキストベース関数は直接動作** — SUMMARIZE, TRANSLATE, SENTIMENT, COMPLETE (text), EXTRACT_ANSWER は External Table データで回避策不要
2. **PARSE_DOCUMENT は直接動作** — ステージパス文字列を使用（TO_FILE とは異なるメカニズム）
3. **TO_FILE は FSx for ONTAP S3 AP 外部ステージで動作しない** — "Remote file not found"（確認済み、NetApp サポートケースと一致）
4. **Vision AI 回避策が存在**: `COPY FILES` → 暗号化なし内部ステージ → `TO_FILE(BUILD_SCOPED_FILE_URL())` → COMPLETE multimodal
5. **Cross-Region Inference が必要** — ap-northeast-1 での Vision モデル利用に必須

## 検証結果サマリー

| 機能 | ステータス | 所要時間 | ユースケース |
|---|:---:|---|---|
| PARSE_DOCUMENT (OCR) | ✅ 検証済み | 約8秒 | 請求書/報告書テキスト抽出 |
| CORTEX.SUMMARIZE | ✅ 検証済み | 3.3秒 | センサーデータ/ドキュメント要約 |
| CORTEX.TRANSLATE | ✅ 検証済み | 5.1秒 | 多言語対応 |
| CORTEX.SENTIMENT | ✅ 検証済み | 2.5秒 | テキスト感情分析 |
| CORTEX.COMPLETE (テキスト) | ✅ 検証済み | 16秒 | AI 分析、異常検知 |
| CORTEX.EXTRACT_ANSWER | ✅ 検証済み | 2.7秒 | テキストからの情報抽出 |
| COMPLETE (vision) 回避策経由 | ✅ 検証済み | 41秒 | 画像分析、欠陥検出 |
| Directory Table + URLs | ✅ 検証済み | 1.3秒 | 非構造化データカタログ |
| TO_FILE on FSx for ONTAP S3 AP | ❌ ブロック | — | マルチモーダル直接アクセス非サポート |

## スクリーンショット

- [OCR 成功](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-08-parse-document-ocr.png)
- [Cortex SUMMARIZE](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-07-cortex-llm-summary.png)
- [Directory Table](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-06-directory-table-presigned-url.png)
- [TO_FILE コンパイルエラー](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-09-tofile-compilation-error.png)
- [TO_FILE remote not found](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-10-tofile-remote-not-found.png)
- [CORTEX.TRANSLATE 成功](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-11-cortex-translate-success.png)
- [CORTEX.COMPLETE テキスト成功](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-12-cortex-complete-text-success.png)
- [Vision AI 成功（回避策）](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-15-vision-ai-success.png)

---

## ガバナンスタグとデータ保護

Snowflake はタグベースのガバナンスを提供し、FSx for ONTAP S3 AP をバックエンドとする External Table を含め、自動的なデータ保護の適用を可能にします。

### 仕組み

```
Object Tag（分類）
    │
    ├── Tag-based Masking Policy（カラムレベル保護）
    │     → タグ値に基づいて機密カラムを自動マスク
    │     → タグを継承する全テーブル/ビューに適用
    │
    └── Row Access Policy（行レベルフィルタリング）
          → ユーザーのロール/属性に基づいて表示行を制限
          → クエリ時に適用、ユーザーに対して透過的
```

### ガバナンス境界: 保護される範囲

| レベル | タグサポート | マスキングポリシー | Row Access Policy | 備考 |
|---|:---:|:---:|:---:|---|
| データベース | ✅ | ✅（継承） | — | タグは配下の全スキーマ/テーブルにカスケード |
| スキーマ | ✅ | ✅（継承） | — | タグは配下の全テーブルにカスケード |
| テーブル（External Table 含む） | ✅ | ✅ | ✅ | **FSx for ONTAP S3 AP データに完全ガバナンス適用可能** |
| カラム | ✅ | ✅（直接） | — | 最も粒度の細かいマスキング対象 |
| ステージ / ファイル | ✅（タグのみ） | ❌ | ❌ | 分類用タグ。クエリ時の適用なし |

### 重要な知見: External Table は完全にガバナンス対象

一部のプラットフォームとは異なり、Snowflake は External Table にもネイティブテーブルと同じガバナンス制御を適用します:

![AWS_ACCESS_POINT_ARN なしでは SELECT が失敗 — LIST は動作するのに access denied](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-03-select-denied.png)

*`AWS_ACCESS_POINT_ARN` なし: LIST は動作するが SELECT は "access denied" で失敗。パラメータ設定後は、FSx for ONTAP S3 AP 上の External Table に完全なガバナンス（タグ、マスキング、Row Policy）を適用可能。*

```sql
-- 1. 分類タグを作成
CREATE TAG IF NOT EXISTS data_classification ALLOWED_VALUES 'PII', 'CONFIDENTIAL', 'PUBLIC';

-- 2. External Table のカラムにタグを適用
ALTER TABLE fsxn_sensor_ext_table MODIFY COLUMN customer_name SET TAG data_classification = 'PII';

-- 3. タグベースのマスキングポリシーを作成（Enterprise Edition 必要）
CREATE MASKING POLICY pii_mask AS (val STRING) RETURNS STRING ->
  CASE WHEN CURRENT_ROLE() IN ('DATA_ADMIN') THEN val
       ELSE '***MASKED***'
  END;

-- 4. マスキングポリシーをタグに紐付け
ALTER TAG data_classification SET MASKING POLICY pii_mask;

-- 結果: 'PII' タグが付いたカラムは非管理者ロールに対して自動マスク
```

### エディション要件

| 機能 | Standard | Enterprise | Business Critical |
|---|:---:|:---:|:---:|
| Object Tags (CREATE TAG, SET TAG) | ✅ | ✅ | ✅ |
| Tag-based Masking Policies | ❌ | ✅ | ✅ |
| Row Access Policies | ❌ | ✅ | ✅ |
| Data Classification（PII 自動検出） | ❌ | ✅ | ✅ |
| External Tokenization | ❌ | ✅ | ✅ |

### Databricks との比較

| 機能 | Snowflake | Databricks |
|---|---|---|
| タグベースカラムマスキング | ✅ Tag-based Masking Policy (Enterprise) | ✅ ABAC Governed Tags + Column Masks |
| 行レベルフィルタリング | ✅ Row Access Policy (Enterprise) | ✅ ABAC Row Filter Policies |
| 自動分類（PII 検出） | ✅ 組み込み (Enterprise) | ✅ 組み込み（自動データ分類） |
| External Table へのガバナンス | ✅ **完全サポート**（FSx for ONTAP S3 AP で検証済み） | ❌ **ブロック**（S3 AP 上の CREATE TABLE 失敗） |
| タグ継承 | Database → Schema → Table → Column | Catalog → Schema → Table（Column には継承しない） |
| 適用境界 | クエリ時リライト（サーバーサイド） | クエリ時リライト（サーバーサイド） |
| データがガバナンスパスから出ない | ✅ クエリ時マスキング、生データエクスポート不可 | ✅ クエリ時マスキング、生データエクスポート不可 |

### FSx for ONTAP S3 AP + Snowflake ガバナンス: 検証済み

![Snowflake 検証サマリー — 全ての読み取りおよびガバナンスパスを検証](https://raw.githubusercontent.com/Yoshiki0705/fsxn-lakehouse-integrations/main/docs/images/snowflake-05-summary-table.png)

*検証結果サマリー: LIST、SELECT、External Table、COPY INTO、Directory Table、Governance Tags の全てを `AWS_ACCESS_POINT_ARN` 付きで検証済み。*

検証環境（Standard edition）で以下を確認:
- ✅ `CREATE TAG` + `ALTER TABLE SET TAG` が FSx for ONTAP S3 AP バックエンドの External Table で動作
- ✅ `SYSTEM$GET_TAG` がタグ値を正しく取得
- ⚠️ Tag-based Masking Policies は Enterprise Edition が必要（Standard では未テスト）
- ⚠️ Row Access Policies は Enterprise Edition が必要（Standard では未テスト）

**意味**: Snowflake Enterprise Edition を使用する組織は、FSx for ONTAP データに対して完全な ABAC ガバナンス（分類、マスキング、行フィルタリング）を External Table 経由で適用可能 — データを Snowflake マネージドストレージにコピーする必要なし。

### ファイルレベルのアクセス制御: ONTAP ネイティブレイヤー

NetApp ユーザーにとって重要なガバナンスの問いは、テーブル/カラムレベルのマスキングだけでなく、**非構造化データ（画像、ドキュメント、動画）のファイルレベルのアクセス制御と統制**です。FSx for ONTAP S3 Access Points はデュアルレイヤー認可モデルを提供します:

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

各 S3 Access Point は**ファイルシステムユーザー**（UNIX UID/GID または Windows ID）にマッピングされます。その AP 経由の全 S3 API 操作はそのユーザーとして実行されます:

| S3 AP 設定 | ファイルアクセス範囲 | ユースケース |
|---|---|---|
| File system user = `root` (UID 0) | 全ファイルにフルアクセス | 管理者/分析（広範な読み取り） |
| File system user = `analytics` (UID 1001) | UID 1001 が読めるファイルのみ | スコープ付き分析アクセス |
| File system user = `dept_finance` | 財務部門のファイルのみ | 部門レベルの分離 |
| ボリュームごとに複数 S3 AP | AP ごとに異なるユーザー | コンシューマーごとのアクセススコーピング |

#### コンシューマーごとの S3 Access Point（データ分離パターン）

```
FSx for ONTAP Volume: /vol1
├── /finance/     (owner: finance_user, mode: 750)
├── /engineering/ (owner: eng_user, mode: 750)
├── /shared/      (owner: root, mode: 755)
│
├── S3 AP "snowflake-finance"    → file_system_user: finance_user
│     → /finance/ と /shared/ を読み取り可、/engineering/ は読み取り不可
│
├── S3 AP "snowflake-engineering" → file_system_user: eng_user
│     → /engineering/ と /shared/ を読み取り可、/finance/ は読み取り不可
│
└── S3 AP "snowflake-admin"      → file_system_user: root
      → 全て読み取り可（管理者/ガバナンス用）
```

#### FPolicy: ファイル操作の監視とブロック

FPolicy は ONTAP レベルでリアルタイムのファイルアクセス監視とブロックを提供 — どのプロトコル（NFS、SMB、S3 AP）が使用されても適用:

| FPolicy 機能 | 説明 | 分析への関連性 |
|---|---|---|
| ネイティブファイルブロック | 特定のファイル拡張子をブロック（.exe, .bat 等） | どのプロトコル経由でも悪意あるファイルアップロードを防止 |
| 外部 FPolicy サーバー | ファイルアクセスイベントを外部アプリに送信 | コンプライアンス用監査証跡（誰が何にいつアクセスしたか） |
| ファイルスクリーニング | ファイルタイプやパターンに基づく許可/拒否 | アクセス可能なデータタイプの制御 |
| 操作モニタリング | open, create, rename, delete, read, write を監視 | データアクセスパターンの完全な監査 |

**NetApp ユーザーへの重要な知見**: Snowflake が S3 AP 経由でデータをクエリする場合でも、ONTAP のファイルレベル権限と FPolicy は引き続き適用されます。S3 AP は ONTAP セキュリティをバイパスしません — S3 API コールをファイルシステム操作にマッピングし、設定された権限を尊重します。

### 統合: ONTAP ファイルレベル制御 × Snowflake タグガバナンス

2つのガバナンスレイヤー（ONTAP ファイルレベルと Snowflake タグベース）は独立して動作しますが、多層防御として組み合わせ可能です:

#### 統合マトリクス

| シナリオ | ONTAP レイヤー（ファイルレベル） | Snowflake レイヤー（タグ/ポリシー） | 組み合わせ効果 |
|---|---|---|---|
| **部門分離** | 部門ごとに別 S3 AP（異なる file_system_user） | テーブルを部門別にタグ分類 | ファイルが物理的にアクセス不可 + 共有テーブルのクエリ時マスキング |
| **PII 保護** | FPolicy が PII ディレクトリへのアクセスを監視 | PII カラムに Tag-based Masking Policy | ファイルアクセスが監査される + 非認可ロールにカラム値がマスク |
| **コンプライアンスホールド** | SnapLock がファイル削除を防止 | Row Access Policy がクエリ結果を制限 | ストレージでデータ不変 + ロールによるクエリ結果フィルタリング |
| **ML 学習データ制御** | Export Policy がどのクラスターが読めるか制限 | External Table に機密レベルタグ | ネットワークレベル制限 + 機密特徴量のカラムマスキング |
| **ランサムウェア防御** | ARP/AI が暗号化を検知 + 自動スナップショット | N/A（ストレージレイヤーの関心事） | ストレージ保護。分析レイヤーは影響なし |
| **チーム間データ共有** | 共有ディレクトリ（mode 755）を共通 S3 AP 経由 | Row Access Policy がチームロールでフィルタ | 全チームがテーブルを見える、各自は認可された行のみ表示 |

#### 連携の仕組み（フロー例）

```
1. データサイエンティストが Snowflake 経由で External Table をクエリ
       │
       ▼
2. Snowflake が S3 API コール（GetObject）を生成
       │
       ▼
3. S3 AP Policy チェック: IAM ロール許可？ ──── NO → AccessDenied
       │ YES
       ▼
4. ONTAP チェック: file_system_user に権限あり？ ──── NO → AccessDenied
       │ YES
       ▼
5. ファイルデータが Snowflake に返却
       │
       ▼
6. Snowflake が Tag-based Masking Policy を適用 ──── PII カラムをマスク
       │
       ▼
7. Snowflake が Row Access Policy を適用 ──── 非認可行をフィルタ
       │
       ▼
8. ユーザーに表示: 認可された行のみ、機密カラムはマスク済み
```

#### 組み合わせガバナンスの設計パターン

| パターン | ONTAP 設定 | Snowflake 設定 | 最適な用途 |
|---|---|---|---|
| **広範読み取り + 細粒度マスク** | 単一 S3 AP（root ユーザー）、全ファイル読み取り可 | 機密カラムに Tag-based masking | PII 保護付きの広範アクセスが必要な分析チーム |
| **厳格ファイル分離 + タグ分類** | 部門ごとの S3 AP（スコープ付きユーザー） | 監査/コンプライアンス追跡用タグのみ | 物理的データ分離が必要な規制産業 |
| **共有データ + ロールベースフィルタ** | 共有 S3 AP（読み取り専用ユーザー） | 部門/ロール別 Row Access Policy | 共通データセットでの部門横断分析 |
| **不変監査 + ガバナンスクエリ** | SnapLock ボリューム + FPolicy 監査 | タグ + マスキング + Row Policy | 金融/医療コンプライアンス |

#### リファレンス: ONTAP ファイルレベル + Snowflake タグ統合

| トピック | リファレンス |
|---|---|
| FSx for ONTAP S3 AP デュアルレイヤー認可 | [Managing access point access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html) |
| FSx for ONTAP S3 AP と Active Directory | [Enabling AI-powered analytics on enterprise file data](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/) |
| ONTAP Export Policy（NFS アクセス制御） | [Export rules の仕組み](https://docs.netapp.com/us-en/ontap/nfs-admin/export-rules-concept.html) |
| ONTAP FPolicy（ファイル監視/ブロック） | [FPolicy 設定タイプ](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html) |
| ONTAP Storage-Level Access Guard | [SLAG によるファイルアクセス保護](https://docs.netapp.com/us-en/ontap/smb-admin/secure-file-access-storage-level-access-guard-concept.html) |
| ONTAP NFSv4 ACL | [SVM の NFSv4 ACL](https://docs.netapp.com/us-en/ontap/nfs-admin/nfsv4-acls-concept.html) |
| Snowflake Object Tagging | [Object Tagging 入門](https://docs.snowflake.com/en/user-guide/object-tagging/introduction) |
| Snowflake Tag-based Masking | [Tag-based masking policies](https://docs.snowflake.com/en/user-guide/tag-based-masking-policies) |
| Snowflake Row Access Policies | [Row access policies の使用](https://docs.snowflake.com/en/user-guide/security-row-using) |
| Snowflake Data Classification | [機密データ分類](https://docs.snowflake.com/en/user-guide/classify-using) |
| Snowflake Governed Lakehouse for AI | [AI 向けレイクハウスガバナンス Quickstart](https://www.snowflake.com/en/developers/guides/govern-your-lakehouse-for-ai/) |

#### ガバナンスレイヤーサマリー（Snowflake + ONTAP）

| レイヤー | 適用ポイント | スコープ | 制御内容 |
|---|---|---|---|
| **ONTAP Export Policy** | ファイルシステム | ボリューム/qtree レベル | クライアント IP、プロトコル、RO/RW |
| **ONTAP ファイル権限** | ファイルシステム | ファイル/ディレクトリ単位 | UNIX mode, NFSv4 ACL, NTFS ACL |
| **ONTAP FPolicy** | ファイルシステム | 操作単位 | ファイル操作の監視、スクリーニング、ブロック |
| **ONTAP Storage-Level Access Guard** | ファイルシステム | ボリュームレベル | 全プロトコルに対する ACL オーバーライド |
| **S3 AP Policy** | AWS | Access Point 単位 | IAM 条件、VPC 制限 |
| **S3 AP File System User** | ファイルシステム | Access Point 単位 | S3 ID を UNIX/Windows ユーザーにマッピング |
| **Snowflake Object Tags** | クエリエンジン | テーブル/カラム | 分類メタデータ |
| **Snowflake Masking Policy** | クエリエンジン | カラム | クエリ時の動的データマスキング |
| **Snowflake Row Access Policy** | クエリエンジン | 行 | クエリ時の行レベルフィルタリング |

### リファレンス

- [Object Tagging](https://docs.snowflake.com/en/user-guide/object-tagging/introduction)
- [Tag-based Masking Policies](https://docs.snowflake.com/en/user-guide/tag-based-masking-policies)
- [Row Access Policies](https://docs.snowflake.com/en/user-guide/security-row-using)
- [Dynamic Data Masking](https://docs.snowflake.com/en/user-guide/security-column-ddm-intro)
- [Data Classification](https://docs.snowflake.com/en/user-guide/classify-using)

---

## 業界別ユースケース: Snowflake Cortex AI + FSx for ONTAP

### 製造業 / 品質検査

| ユースケース | Cortex 関数 | FSx 上のデータ | リファレンス |
|---|---|---|---|
| 検査報告書 OCR | PARSE_DOCUMENT (OCR モード) | スキャン報告書 (PNG/PDF) | [Snowflake PARSE_DOCUMENT ドキュメント](https://docs.snowflake.com/en/user-guide/snowflake-cortex/parse-document) |
| センサー異常要約 | CORTEX.SUMMARIZE | IoT センサー Parquet/CSV | [Cortex LLM Functions](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions) |
| 外観欠陥検出 | AI_COMPLETE (vision) | 製品画像 | [AI_COMPLETE マルチモーダル](https://docs.snowflake.com/en/sql-reference/functions/complete-snowflake-cortex-multimodal) |
| ダッシュボードからの歩留まり分析 | AI_COMPLETE (vision) | ダッシュボードスクリーンショット | [Image Analysis Quickstart](https://www.snowflake.com/en/developers/guides/build-image-analysis-app-with-streamlit-and-snowflake-cortex/) |

### 金融 / 保険

| ユースケース | Cortex 関数 | FSx 上のデータ | リファレンス |
|---|---|---|---|
| 請求書データ抽出 | PARSE_DOCUMENT (LAYOUT モード) | 請求書 PDF/画像 | [Document AI](https://docs.snowflake.com/en/user-guide/snowflake-cortex/parse-document) |
| 契約条項要約 | CORTEX.SUMMARIZE | 契約書ドキュメント | [Cortex LLM Functions](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions) |
| 保険金請求書類処理 | PARSE_DOCUMENT + SUMMARIZE | 請求フォーム | [OCR + RAG Quickstart](https://quickstarts.snowflake.com/guide/getting_started_with_ocr_and_rag_with_snowflake_notebooks/) |
| 規制文書検索 | Cortex Search (COPY INTO 経由) | コンプライアンス文書 | [Cortex Search](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-search/cortex-search-overview) |

### 医療 / ライフサイエンス

| ユースケース | Cortex 関数 | FSx 上のデータ | リファレンス |
|---|---|---|---|
| 医療記録デジタル化 | PARSE_DOCUMENT (OCR) | スキャン記録 | [PARSE_DOCUMENT](https://docs.snowflake.com/en/user-guide/snowflake-cortex/parse-document) |
| 研究論文要約 | CORTEX.SUMMARIZE | PDF 論文 | [Cortex LLM Functions](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions) |
| 検査報告テキスト抽出 | PARSE_DOCUMENT | 検査画像/PDF | [Document AI](https://docs.snowflake.com/en/user-guide/snowflake-cortex/parse-document) |
| 臨床試験データカタログ | Directory Table | 試験ドキュメント | [Directory Tables](https://docs.snowflake.com/en/user-guide/data-load-dirtables) |

### メディア / コンテンツ管理

| ユースケース | Cortex 関数 | FSx 上のデータ | リファレンス |
|---|---|---|---|
| 画像メタデータ抽出 | AI_COMPLETE (vision) | メディアアセット | [AI_COMPLETE](https://docs.snowflake.com/en/sql-reference/functions/complete-snowflake-cortex-multimodal) |
| 動画フレーム説明 | AI_COMPLETE (vision) | 抽出フレーム | [Image Analysis](https://www.snowflake.com/en/developers/guides/build-image-analysis-app-with-streamlit-and-snowflake-cortex/) |
| アセットカタログ管理 | Directory Table + Tags | 全メディアファイル | [Directory Tables](https://docs.snowflake.com/en/user-guide/data-load-dirtables) |
| コンテンツ翻訳 | CORTEX.TRANSLATE | テキストドキュメント | [Cortex TRANSLATE](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions#label-cortex-llm-translate) |

### 業界横断: データエンジニアリング

| ユースケース | Cortex 関数 | FSx 上のデータ | リファレンス |
|---|---|---|---|
| ファイルからのスキーマ推論 | PARSE_DOCUMENT + LLM | 混合フォーマットファイル | [Cortex LLM](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions) |
| データ品質評価 | CORTEX.SUMMARIZE | データサンプル | [Cortex LLM Functions](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions) |
| ファイル分類/タグ付け | AI_COMPLETE + Tags | 非構造化ファイル | [Governance Tags](https://docs.snowflake.com/en/user-guide/object-tagging/introduction) |
| 自動ドキュメント生成 | CORTEX.SUMMARIZE | コード/設定ファイル | [Cortex LLM Functions](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions) |

---

## AI/ML ワークロードにおける ONTAP の価値

| ONTAP 機能 | AI/ML メリット | リファレンス |
|---|---|---|
| **FlexCache** | リージョン/拠点間で学習データをキャッシュし低遅延アクセスを実現。分散 ML ワークロードの WAN 帯域を削減 | [FlexCache 概要](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html) |
| **SnapLock / Tamperproof Snapshot** | 不変のデータ保護 — 管理者権限でも保持期間中はロックされたスナップショットを削除不可。SEC 17a-4(f)、HIPAA、FINRA コンプライアンスに対応 | [SnapLock on FSx for ONTAP](https://netapp.com/blog/snaplock-on-amazon-fsx-ontap/) |
| **ARP/AI（自律型ランサムウェア防御）** | AI によるランサムウェア暗号化パターンのリアルタイム検知。被害拡大前に自動スナップショットを作成 | [ARP on FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/ARP.html) |
| **FlexClone** | ML 実験用のゼロコピー即時クローン — データを複製せずに異なる前処理をテスト | [FlexClone ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-volumes.html) |
| **Snapshot** | 学習データセットのポイントインタイムリカバリ。特徴量エンジニアリングパイプラインのバージョン管理 | [Snapshot ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/snapshots-ontap.html) |
| **FabricPool** | コールドな学習データや古いモデルアーティファクトを S3 に自動階層化 — Snowflake クエリに対して透過的 | [FabricPool ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/fabricpool.html) |
| **ストレージ効率化** | 重複排除 + 圧縮 + コンパクションで学習データやエンベディングを最大 65% 削減 | [ストレージ効率](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/storage-efficiency.html) |
| **SnapMirror** | 重要な ML パイプラインと学習データセットのクロスリージョン DR | [SnapMirror ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html) |
| **マルチプロトコル** | 同一データに NFS（データサイエンティスト）、SMB（Windows ユーザー）、S3 AP（Snowflake/分析）から同時アクセス可能 | [マルチプロトコルアクセス](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/supported-fsx-clients.html) |
| **FPolicy** | AI データアクセス監査用のファイル操作監視。ML パイプラインでの不正ファイルタイプのブロック | [FPolicy ドキュメント](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html) |

### AI/ML 固有のシナリオ

- **FlexCache による分散学習**: オンプレミス NAS からクラウド FSx for ONTAP に学習データセットをキャッシュ — ML クラスターが WAN を経由せずローカルキャッシュからサブミリ秒のレイテンシでデータを読み取り
- **SnapLock によるモデルガバナンス**: 学習データのスナップショットをロックし再現性を保証 — 監査人がモデル学習に使用された正確なデータセットが変更されていないことを検証可能
- **ARP/AI によるデータパイプライン保護**: 学習データやモデルアーティファクトを標的とするランサムウェアを検知・ブロック — 自動スナップショットがリカバリ用のクリーンな状態を保持

---

## はじめに

1. **FSx for ONTAP S3 AP ステージの設定** — [設定ガイド](../../README.md) に従う
2. **サンプルデータのアップロード** — NFS 経由で FSx for ONTAP に画像/ドキュメントを配置
3. **Directory Table の更新** — `ALTER STAGE REFRESH` で新規ファイルを検出
4. **Cortex 関数の実行** — 上記の SQL サンプルを使用
5. **Streamlit アプリの構築** — 画像サムネイル付きインタラクティブダッシュボード用

## Snowflake Cortex AI ドキュメント

- [Cortex AI 概要](https://docs.snowflake.com/en/user-guide/snowflake-cortex)
- [LLM Functions (SUMMARIZE, COMPLETE, TRANSLATE)](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions)
- [PARSE_DOCUMENT (OCR / Document AI)](https://docs.snowflake.com/en/user-guide/snowflake-cortex/parse-document)
- [AI_COMPLETE (マルチモーダル/Vision)](https://docs.snowflake.com/en/sql-reference/functions/complete-snowflake-cortex-multimodal)
- [Cortex Search (RAG)](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-search/cortex-search-overview)
- [Directory Tables](https://docs.snowflake.com/en/user-guide/data-load-dirtables)
- [OCR + RAG Quickstart](https://quickstarts.snowflake.com/guide/getting_started_with_ocr_and_rag_with_snowflake_notebooks/)
- [Image Analysis with Streamlit](https://www.snowflake.com/en/developers/guides/build-image-analysis-app-with-streamlit-and-snowflake-cortex/)
