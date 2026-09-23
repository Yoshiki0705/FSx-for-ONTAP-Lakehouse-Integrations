🌐 [English](../../README.md) | **日本語**

# Snowflake 統合

🌐 [English](../../README.md) | **日本語**

> **検証ステータス: ✅ 検証済み（`AWS_ACCESS_POINT_ARN` 使用）**
>
> Snowflake は `AWS_ACCESS_POINT_ARN` ステージパラメータを使用して FSx for ONTAP S3 Access Point のデータをクエリできます。
> このパラメータを設定すると、SELECT、External Table 作成、LIST が全て動作します。
> 設定しない場合、LIST は動作しますが SELECT は "access denied" で失敗します。

## 検証結果

| 操作 | `AWS_ACCESS_POINT_ARN` なし | `AWS_ACCESS_POINT_ARN` あり |
|---|:---:|:---:|
| Storage Integration | ✅ | ✅ |
| ステージ作成 | ✅ | ✅ |
| LIST @stage | ✅ | ✅ |
| SELECT @stage (Parquet) | ❌ Access Denied | ✅ |
| SELECT @stage (CSV) | ❌ | ✅ |
| External Table | ❌ | ✅ |
| COPY INTO (ロード) | ❌ | ✅ |
| ガバナンスタグ | N/A | ✅ |
| Snowpipe (自動取り込み) | ❌ | ❌ (S3 Event Notifications 非サポート) |
| Iceberg Table 書き込み | ❌ | ❌ (conditional writes 非サポート) |
| GET_PRESIGNED_URL | ✅ (動作確認済み) | ✅ |

## パートナー判断カード（クイックリファレンス）

| 要件 | ステータス | アクション |
|---|:---:|---|
| Snowflake から NAS ファイルをクエリ | ✅ | ステージに `AWS_ACCESS_POINT_ARN` を設定 |
| ガバナンス付き外部テーブル | ✅ | External Table 作成 + タグ適用 |
| 非構造化データカタログ | ✅ | Directory Table 有効化 + 手動 REFRESH |
| AI テキスト処理（OCR、要約、翻訳） | ✅ | External Table 上の Cortex 関数 — コピー不要 |
| AI Vision（画像分析） | ✅ | COPY FILES → 内部ステージ → TO_FILE 回避策 |
| AI RAG / セマンティック検索（Cortex Search） | ✅ | External Table → COPY INTO → Cortex Search Service (198ms) |
| 自動化エンリッチメント（Dynamic Table） | ✅ | External Table → Dynamic Table (TARGET_LAG = '1 hour', FULL refresh) |
| パートナーとキュレート済みデータを共有 | ✅ | External Table / Dynamic Table → Snowflake Data Sharing |
| マルチエンジン用オープンフォーマット | ✅ | COPY INTO → Managed Iceberg Table → Databricks/Athena が読み取り可能 |
| リアルタイム自動取り込み（Snowpipe） | ❌ | Task + ALTER EXTERNAL TABLE REFRESH または FPolicy + Lambda を使用 |
| FSx for ONTAP S3 AP 上の Iceberg 書き戻し | ❌ | トランザクショナル書き込みには標準 S3 を使用 |

> ガバナンス付き外部テーブル、AI 機能、データ共有、マルチエンジン Iceberg 互換が必要な場合は Snowflake を選択。軽量な AWS ネイティブサーバーレス SQL で十分な場合は Athena を選択。

### パートナー会話スクリプト

**NAS データ + AI 要件のある顧客向け:**
> 「Snowflake は FSx for ONTAP の NAS データに対してコピーなしで直接 AI を実行できます。テストした 10 の Cortex AI 機能のうち 8 つが FSx データ上で動作し、OCR、要約、翻訳、セマンティック検索（Cortex Search で 198ms クエリレイテンシ）を含みます。画像分析には 1 ステップのステージング回避策で Vision AI を有効化できます。NFS/SMB ユーザーがアクセスする同じデータに対して、タグ、マスキング、行レベルセキュリティの完全なガバナンスを実現します。」

**データ移動を懸念する顧客向け:**
> 「External Table を使えば、データは FSx for ONTAP に残ります。Snowflake ストレージへのコピーは不要です。NFS、SMB、S3 AP で同時にアクセス可能な同じファイルです。Snapshot、FlexClone、SnapLock などの ONTAP 機能がデータを保護し続けます。Snowflake はストレージを所有せずにガバナンスと AI を追加します。」

**NAS 統合で Snowflake vs Databricks を評価中の顧客向け:**
> 「Snowflake の `AWS_ACCESS_POINT_ARN` 付き External Table は、AI 機能を含むガバナンス付き読み取りアクセスを今日提供します。Databricks Unity Catalog は現在セッションポリシーの制限により S3 Access Points 上でテーブル作成ができません。NAS データに対するガバナンス付き分析には、Snowflake が検証済みパスです。」

> **補足（Databricks を標準 S3 ステージングで使う場合）**: 上記は FSx for ONTAP S3 Access Point 上を直接クエリする前提。Databricks では標準 S3 バケットにステージングすれば UC ガバナンス下で非構造化データ AI（`ai_query` Vision・`ai_parse_document` OCR・`FILE EXTERNAL`・AI Functions・Genie）が動作する（実機検証: [標準 S3 PoC](../../../../docs/ja/databricks-standard-s3-unstructured-poc.md) / [English](../../../../docs/en/databricks-standard-s3-unstructured-poc.md)）。両エンジンを併用する組織は、ゼロコピーのその場クエリ（Snowflake External Table）と、標準 S3 へステージング後のガバナンス付き処理（どちらのエンジンでも可）を用途で使い分けられる。

## 概要

Amazon FSx for NetApp ONTAP（FSx for ONTAP）の S3 Access Point を Snowflake の External Stage として統合し、External Table / Iceberg Table のストレージレイヤーとして使用するパターンです。

## アーキテクチャ

```
┌───────────────────────────────────────────────────────────────────────┐
│                              AWS アカウント                             │
│                                                                       │
│  ┌─────────────────┐     ┌──────────────────┐     ┌───────────────┐   │
│  │ FSx for ONTAP   │     │ FSx for ONTAP    │     │ IAM ロール     │   │
│  │ (NFS ボリューム)　│◀───▶│ S3 Access Point  │◀────│ (Snowflake    │   │
│  │                 │     │(Internet origin) │     │  AssumeRole)  │   │
│  └─────────────────┘     └────────┬─────────┘     └───────┬───────┘   │
│                                    │                        │         │
└────────────────────────────────────┼────────────────────────┼─────────┘
                                     │ S3 API                 │ STS
                                     ▼                        ▼
                          ┌────────────────────────────────────────────┐
                          │  Snowflake (SaaS — ap-northeast-1)         │
                          │                                            │
                          │  Storage Integration → External Stage      │
                          │       → External Table / Iceberg Table     │
                          │       → Snowpipe (FPolicy + SNS 経由)       │
                          └────────────────────────────────────────────┘
```

## FSx for ONTAP S3 Access Point — 対応 S3 オペレーション

| オペレーション | 対応 | 備考 |
|-------------|:---:|------|
| ListObjectsV2 | ✅ | 高レイテンシ（数十秒〜分）の場合あり |
| GetObject | ✅ | |
| PutObject | ✅ | 最大 50 GB |
| DeleteObject | ✅ | |
| HeadObject | ✅ | |
| **Pre-signed URL** | ✅ | AWS ドキュメントでは非サポートと記載されているが実際には動作 |
| **TO_FILE / FILE データ型** | ❌ | "Remote file not found" — Cortex マルチモーダルが S3 AP ファイルを解決できない |
| **PARSE_DOCUMENT** | ✅ | 異なるファイルアクセス機構を使用（ステージパス文字列） |
| S3 Event Notifications | ❌ | 代替として FPolicy を使用 |
| Object Versioning | ❌ | |

> ℹ️ **注意**: AWS ドキュメントでは Pre-signed URL は「非サポート」と記載されていますが、テストでは `GET_PRESIGNED_URL()` が FSx for ONTAP S3 AP で正しく動作することを確認しています。

> ⚠️ **TO_FILE 制限**: Snowflake の `TO_FILE()` 関数（マルチモーダル AI_COMPLETE/Vision AI で使用）は FSx for ONTAP S3 AP 外部ステージ上のファイルを解決できません。回避策: `COPY FILES` で暗号化なし内部ステージ（SNOWFLAKE_SSE）にコピーし、`TO_FILE(BUILD_SCOPED_FILE_URL(@internal_stage, path))` を使用。

## データフォーマット対応

| フォーマット | 読み取り | 書き込み | テーブルタイプ |
|------------|---------|---------|-------------|
| Parquet | ✅ | ✅ | External Table / Iceberg |
| CSV | ✅ | ✅ | External Table |
| JSON | ✅ | ✅ | External Table |
| ORC | ✅ | ❌ | External Table |
| Avro | ✅ | ❌ | External Table |

## 内部テーブル vs 外部テーブル — 設計ガイド

FSx for ONTAP と Snowflake を統合する際、内部（マネージド）テーブルと外部テーブルの違いを理解することがアーキテクチャ判断に不可欠です。

> **主要概念**: [外部ステージ](https://docs.snowflake.com/en/user-guide/data-load-s3-create-stage)（S3/クラウドストレージ）| [内部ステージ](https://docs.snowflake.com/en/user-guide/data-load-local-file-system-create-stage)（Snowflake マネージド）| [外部テーブル](https://docs.snowflake.com/en/user-guide/tables-external)（ステージから読み取り）| [COPY INTO](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table)（内部テーブルにロード）
>
> 分析および AI/ML 固有の影響（各パターンでどの Cortex 関数が動作するか）については [Analytics & AI デモガイド](ai-demo-guide.md) の互換性マトリクスを参照。

### 比較マトリクス

| 観点 | 外部テーブル（FSx for ONTAP S3 AP 上） | 内部テーブル（COPY INTO） |
|---|---|---|
| **データ所在** | FSx for ONTAP に残る（ゼロコピー） | Snowflake マネージドストレージにコピー |
| **データ所有権** | 顧客がデータライフサイクルを管理 | Snowflake がストレージライフサイクルを管理 |
| **DROP TABLE 動作** | データは削除されない（メタデータのみ削除） | Snowflake ストレージからデータが削除される |
| **マルチプロトコルアクセス** | 同一データに NFS/SMB/S3 AP で同時アクセス可能 | Snowflake 経由のみアクセス可能 |
| **データ鮮度** | リアルタイム（現在のファイル状態を読み取り） | 次の COPY INTO / Snowpipe まで古い |
| **クエリ性能** | 遅い（S3 API レイテンシ、マイクロパーティションなし） | 速い（最適化マイクロパーティション、プルーニング） |
| **ガバナンス（タグ、マスキング）** | ✅ 完全サポート（Enterprise Edition） | ✅ 完全サポート |
| **Time Travel** | ❌ 利用不可 | ✅ 利用可能（最大90日） |
| **クラスタリング / 最適化** | ❌ 利用不可 | ✅ AUTO_CLUSTERING, OPTIMIZE |
| **Cortex AI（テキスト関数）** | ✅ 直接（SUMMARIZE, TRANSLATE 等） | ✅ 直接 |
| **Cortex AI（Vision/TO_FILE）** | ❌ FSx for ONTAP S3 AP で TO_FILE ブロック | ✅ 内部ステージで動作 |
| **ONTAP 機能の保持** | ✅ Snapshot, FlexClone, Dedup, FPolicy | ❌ データは ONTAP 外 |
| **ストレージコスト** | FSx for ONTAP のみ（Snowflake ストレージなし） | FSx + Snowflake ストレージ（重複） |
| **コンプライアンス（データレジデンシー）** | ✅ データは FSx に残る（管理された場所） | ⚠️ Snowflake マネージドストレージにデータ |

### 外部テーブルを選ぶべき場合（ゼロコピーパターン）

```
FSx for ONTAP ──S3 AP──▶ Snowflake External Table ──▶ クエリ / ガバナンス / AI
     │
     └── 同一データに NFS/SMB でアクセス可能（コピーなし）
```

**外部テーブルを選択する条件:**
- データが FSx for ONTAP に残る必要がある（コンプライアンス、データレジデンシー、マルチプロトコル）
- 現在のファイル状態へのリアルタイムアクセスが必要
- ONTAP 機能（Snapshot, FlexClone, FPolicy, SnapLock）を保持する必要がある
- ストレージコスト最適化が優先（重複ストレージを回避）
- 読み取り中心で更新頻度が低いデータ
- 複数のコンシューマー（NFS ユーザー、Snowflake、Athena 等）が同じデータを必要とする

**制限事項:**
- Time Travel、クラスタリング、マイクロパーティション最適化なし
- クエリ性能は FSx for ONTAP S3 AP レイテンシとファイルレイアウトに依存
- TO_FILE（Vision AI）が直接動作しない — COPY FILES 回避策が必要
- AUTO_REFRESH 利用不可（手動 REFRESH またはスケジュール Task が必要）

### 内部テーブルを選ぶべき場合（COPY INTO パターン）

```
FSx for ONTAP ──S3 AP──▶ COPY INTO ──▶ Snowflake 内部テーブル ──▶ クエリ / AI / Time Travel
                                              │
                                              └── 最適化マイクロパーティション、全 Snowflake 機能
```

**内部テーブルを選択する条件:**
- 最大クエリ性能が必要（マイクロパーティション、プルーニング、クラスタリング）
- Time Travel（ポイントインタイムクエリ、UNDROP）が必要
- Vision AI / TO_FILE を回避策なしで使用したい
- データ変換（ELT）がパイプラインの一部
- Snowflake ネイティブ機能（Streams, Tasks, Dynamic Tables）が必要
- COPY INTO 実行間のデータ鮮度の遅延を許容できる

> **サポート確認済み（2026年5月）**: External Stage（`AWS_ACCESS_POINT_ARN` 付き）から Managed Iceberg Table への COPY INTO がサポートされています。Dynamic Table は External Table をソースとして REFRESH_MODE = FULL で動作（最小 TARGET_LAG 60秒）。これにより FSx for ONTAP → Snowflake Managed Iceberg → Databricks/Athena/EMR からの読み取りが可能になります。

**制限事項:**
- データが重複（FSx + Snowflake ストレージコスト）
- データ鮮度は COPY INTO 頻度に依存
- ONTAP 機能（Snapshot, FlexClone）はコピーに適用されない
- データレジデンシーが Snowflake マネージドストレージに移行

### ハイブリッドパターン（AI/ML ワークロード推奨）

```
FSx for ONTAP
     │
     ├── External Table（構造化データ）──▶ テキスト AI（SUMMARIZE, TRANSLATE, SENTIMENT）
     │                                     ガバナンス（タグ、マスキング、Row Policy）
     │
     └── COPY FILES → 内部ステージ ──▶ Vision AI（COMPLETE multimodal）
                                        Document AI（TO_FILE が必要な場合）
```

**ベストプラクティス**: ガバナンス付き読み取りアクセスとテキストベース AI には External Table を使用。Vision AI（TO_FILE）が必要な場合のみ COPY FILES で内部ステージにコピー。

### 判断フローチャート

```
Q: データは FSx for ONTAP に残す必要がある？
├── YES → External Table
│         Q: 画像に対する Vision AI が必要？
│         ├── YES → Vision AI 用のみ COPY FILES で内部ステージへ
│         └── NO → External Table で十分（テキスト AI は直接動作）
│                   Q: 自動エンリッチメントが必要？
│                   ├── YES → Dynamic Table (TARGET_LAG = '1 hour', FULL refresh)
│                   └── NO → External Table のまま使用
│
└── NO → COPY INTO で内部テーブル
          Q: マルチエンジンアクセス（Databricks/Athena）が必要？
          ├── YES → Managed Iceberg Table（オープン形式で S3 に書き込み）
          └── NO → 標準内部テーブル
                    Q: パートナー/サプライヤーとデータ共有が必要？
                    ├── YES → Snowflake Data Sharing（ガバナンス付き配布）
                    └── NO → 内部テーブルのまま使用
```

### コスト比較

| パターン | FSx ストレージ | Snowflake ストレージ | Snowflake コンピュート | 合計コスト |
|---|---|---|---|---|
| External Table のみ | ✅（既存） | なし | クエリ時間のみ | 💰 最小 |
| COPY INTO（全量） | ✅（既存） | + 全量コピー | クエリ + COPY 時間 | 💰💰💰 最大 |
| ハイブリッド（External + 選択的 COPY） | ✅（既存） | + 画像のみ | クエリ + 選択的 COPY | 💰💰 中程度 |

### AI レディネススコア

| パターン | ガバナンス | 性能 | AI 機能 | コスト | 運用容易性 | 総合 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **External Table のみ** | ★★★★☆ | ★★☆☆☆ | ★★★★☆ (テキスト AI 直接) | ★★★★★ | ★★★★☆ | **4.0** |
| **COPY INTO（全量）** | ★★★★★ | ★★★★★ | ★★★★★ (全 AI) | ★★☆☆☆ | ★★★☆☆ | **3.8** |
| **ハイブリッド（External + Vision 用 COPY）** | ★★★★☆ | ★★★☆☆ | ★★★★★ (全 AI) | ★★★★☆ | ★★★☆☆ | **3.8** |

- **ガバナンス**: Tag-based masking、Row Policy、監査証跡
- **性能**: クエリレイテンシ、最適化機能
- **AI 機能**: 回避策なしで動作する Cortex 関数の数
- **コスト**: ストレージ効率（重複回避）
- **運用容易性**: セットアップとメンテナンスの手間

> **スコアリング方法論**: 各次元は本リポジトリの検証済みエビデンスに基づき著者が評価。AWS または Snowflake の公式アセスメントではありません。スコアは1つのテスト環境（Snowflake Standard, ap-northeast-1）での観測結果を反映。

> **スコアの使い方**: Overall スコアをパターン選択の出発点として使用。4.0 以上はガバナンス付き本番ワークロードに適合。3.5〜3.9 はトレードオフを評価した上で利用可能。

**パターン選択ガイド:**
- **External Table のみ**（4.0）: データが FSx に残る必要があり、テキストベース AI で十分な場合
- **COPY INTO（全量）**（3.8）: 最大性能、Time Travel、Vision AI が必要な場合
- **ハイブリッド**（3.8）: データ残留要件と全 AI 機能の両方が必要な場合

### 業種別推奨パターン

| 業種 | 推奨パターン | 根拠 | PoC 成功基準 |
|---|---|---|---|
| **製造業** | External Table + PARSE_DOCUMENT (OCR) | データは FSx に残留。検査画像をその場で処理 | OCR が 10 枚以上の検査画像から各 10 秒以内にテキスト抽出 |
| **金融サービス** | ハイブリッド（External Table + Cortex Search 用 COPY INTO） | コンプライアンスで FSx にデータ残留必須。RAG には内部テーブルが必要 | Cortex Search が関連コンプライアンス文書を 500ms 以内に返却 |
| **医療** | External Table + SnapLock | PHI は管理されたストレージから出してはならない。不変の監査 | External Table への SELECT がガバナンスタグ付きで成功 |
| **メディア / エンタメ** | External Table + COPY FILES (Vision AI) | 大容量メディアファイルは FSx に残留。AI 用に選択的ステージング | Vision AI がステージングパス経由で画像内容を正しく記述 |
| **汎用分析** | COPY INTO（全量） | 最大クエリ性能。データ重複は許容 | 代表的データセットで COPY INTO が 10 秒以内に完了 |

### リファレンス

- [Snowflake External Tables](https://docs.snowflake.com/en/user-guide/tables-external)
- [COPY INTO table](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table)
- [COPY FILES](https://docs.snowflake.com/en/sql-reference/sql/copy-files)
- [Directory Tables](https://docs.snowflake.com/en/user-guide/data-load-dirtables)
- [Time Travel](https://docs.snowflake.com/en/user-guide/data-time-travel)

## 非構造化データ対応

| フォーマット | アクセス方法 | ユースケース |
|------------|------------|------------|
| 画像 (JPEG, PNG, TIFF) | GET_PRESIGNED_URL / BUILD_SCOPED_FILE_URL | サムネイル生成、ML 推論、品質検査 |
| 動画 (MP4, MOV) | GET_PRESIGNED_URL | ストリーミング、フレーム抽出 |
| ドキュメント (PDF, DOCX) | GET_PRESIGNED_URL / Snowpark File Access | テキスト抽出、RAG、文書処理 |
| 音声 (WAV, MP3) | GET_PRESIGNED_URL | 文字起こし、音声分析 |
| バイナリ / アーカイブ | GET_PRESIGNED_URL | ダウンロード、転送 |

**非構造化データへのアクセス方法:**
1. **Directory Table** — ファイルのメタデータ（パス、サイズ、更新日時）をカタログとして管理
2. **GET_PRESIGNED_URL()** — アプリケーション向けの期限付きダウンロード URL を生成
3. **BUILD_SCOPED_FILE_URL()** — Snowflake 経由のセキュアな URL を生成
4. **Snowpark File Access** — UDF/UDTF 内でファイルを直接処理（要検証）

```sql
-- Directory Table を有効化してファイルカタログとして使用
ALTER STAGE fsxn_stage SET DIRECTORY = (ENABLE = TRUE);
ALTER STAGE fsxn_stage REFRESH;

-- ファイルカタログをクエリ
SELECT RELATIVE_PATH, SIZE, LAST_MODIFIED FROM DIRECTORY(@fsxn_stage);

-- ダウンロード URL を生成（1時間有効）
SELECT GET_PRESIGNED_URL(@fsxn_stage, 'images/photo001.jpg', 3600);
```

> **注意**: FSx for ONTAP S3 AP は S3 Event Notifications をサポートしていないため、AUTO_REFRESH は使用できません。`ALTER STAGE REFRESH` を手動または Snowflake Task でスケジュール実行してください。

## ONTAP の価値

| ONTAP 機能 | Snowflake へのメリット | リファレンス |
|---|---|---|
| **FlexCache** | リージョン/拠点間でデータをキャッシュし低遅延の Snowflake アクセスを実現。WAN 帯域を削減 | [FlexCache ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html) |
| **SnapLock / Tamperproof Snapshot** | コンプライアンス向け不変データ保護 — 管理者権限でも保持期間中は削除不可 | [SnapLock on FSx](https://netapp.com/blog/snaplock-on-amazon-fsx-ontap/) |
| **ARP/AI** | AI によるランサムウェア検知。分析データへの被害拡大前に自動スナップショット | [ARP on FSx](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/ARP.html) |
| **FlexClone** | 本番データを使った即時ステージング環境（ゼロコピー） | [FlexClone ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-volumes.html) |
| **Snapshot** | Snowflake Time Travel 保持期間を超えたデータ復旧。データパイプラインのバージョン管理 | [Snapshot ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/snapshots-ontap.html) |
| **FabricPool** | 過去パーティションの S3 自動階層化（Snowflake クエリに透過的） | [FabricPool ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/fabricpool.html) |
| **ストレージ効率化** | 重複排除 + 圧縮 + コンパクションでファイルデータを最大 65% 削減 | [ストレージ効率](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/storage-efficiency.html) |
| **SnapMirror** | Snowflake レプリケーションと DR 向けクロスリージョンデータ可用性 | [SnapMirror ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html) |
| **マルチプロトコル** | NFS（取り込み）+ SMB（Windows ユーザー）+ S3 AP（Snowflake）— 同一データ、コピー不要 | [マルチプロトコル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/supported-fsx-clients.html) |
| **FPolicy** | Lambda 経由のイベント駆動 Snowpipe 取り込み（<30秒レイテンシ） | [FPolicy ドキュメント](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html) |

## ガバナンス & AI/ML ガイド

| ガイド | 説明 |
|---|---|
| [Analytics & AI デモガイド](ai-demo-guide.md) | 分析 & AI 機能（Cortex AI、OCR、Vision）、業界別ユースケース、ONTAP 価値 |
| [内部テーブル取り込みガイド](internal-table-ingestion-guide.md) | COPY INTO が必要なケース — 機能利用可否マトリクス（External vs Internal Table）、取り込みパターン、二重管理の課題 |
| [ガバナンス: タグとデータ保護](ai-demo-guide.md#ガバナンスタグとデータ保護) | Tag-based masking、Row Access Policy、エディション要件 |
| [ガバナンス: ファイルレベルアクセス制御](ai-demo-guide.md#ファイルレベルのアクセス制御-ontap-ネイティブレイヤー) | ONTAP デュアルレイヤー認可、FPolicy、コンシューマーごとの S3 AP 分離 |
| [統合: ONTAP × Snowflake タグ](ai-demo-guide.md#統合-ontap-ファイルレベル制御--snowflake-タグガバナンス) | 組み合わせガバナンスマトリクス、設計パターン、フロー図 |

## Snowpipe & 取り込みフォーマット

### Snowpipe 対応フォーマット

| フォーマット | Snowpipe | COPY INTO | External Table | 備考 |
|---|:---:|:---:|:---:|---|
| CSV | ✅ | ✅ | ✅ | デリミタ、ヘッダー、エンコーディングオプション |
| JSON | ✅ | ✅ | ✅ | ネスト、半構造化 |
| Parquet | ✅ | ✅ | ✅ | カラムプルーニング、述語プッシュダウン |
| Avro | ✅ | ✅ | ✅ | スキーマ進化対応 |
| ORC | ✅ | ✅ | ✅ | 読み取り専用 |
| XML | ✅ | ✅ | ✅ | ネイティブサポート |

**Snowpipe/COPY INTO で直接サポートされないフォーマット（代替手段が必要）:**

| フォーマット | 代替方法 | 考慮事項 |
|---|---|---|
| 画像 (JPEG, PNG, TIFF) | Directory Table + GET_PRESIGNED_URL / PARSE_DOCUMENT (OCR) | Cortex AI でテキスト抽出。Vision AI は COPY FILES 回避策経由 |
| 動画 (MP4, MOV) | Directory Table + GET_PRESIGNED_URL → 外部処理 | CloudFront 経由ストリーミングまたは外部フレーム処理 |
| 音声 (WAV, MP3) | Directory Table + GET_PRESIGNED_URL → 文字起こしサービス | 外部 ASR（Bedrock, Whisper）または将来の AI_TRANSCRIBE |
| ドキュメント (PDF, DOCX) | PARSE_DOCUMENT（ステージ上で直接） | OCR/LAYOUT モードで FSx for ONTAP S3 AP から直接テキスト抽出 |
| バイナリ / アーカイブ | GET_PRESIGNED_URL → 外部処理 | ダウンロードして Snowflake 外で処理 |
| DB エクスポート | Snowpark UDF でカスタムパース | SQL/dump フォーマットを構造化データにパース |

### FSx for ONTAP 向けデータ取り込み代替手段（Snowpipe が利用不可の場合）

FSx for ONTAP S3 AP は S3 Event Notifications をサポートしないため、標準 Snowpipe 自動取り込みは利用不可。以下の代替手段を使用:

| 方法 | 説明 | レイテンシ | 複雑さ | リファレンス |
|---|---|---|---|---|
| **FPolicy → Lambda → SNS → Snowpipe** | FPolicy がファイル変更を検知 → Lambda が SNS 通知送信 → Snowpipe REST API がロードをトリガー | 秒（<30秒） | 中 | [FPolicy ドキュメント](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html) |
| **Snowflake Task + COPY INTO** | スケジュール Task が定期的にステージから COPY INTO を実行 | 分（設定可能） | 低 | [Tasks ドキュメント](https://docs.snowflake.com/en/user-guide/tasks-intro) |
| **Snowflake Task + ALTER STAGE REFRESH** | スケジュール Task が Directory Table メタデータを更新 | 分 | 低 | [Tasks ドキュメント](https://docs.snowflake.com/en/user-guide/tasks-intro) |
| **External function + Lambda** | Snowflake が Lambda を呼び出して新規ファイルを確認 | オンデマンド | 中 | [External functions](https://docs.snowflake.com/en/sql-reference/external-functions) |
| **AWS Glue → Snowflake** | Glue が FSx for ONTAP S3 AP から読み取り → コネクタ経由で Snowflake に書き込み | 分 | 中 | [Glue + FSx チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html) |
| **Snowpipe REST API（手動トリガー）** | アプリケーションがファイルリスト付きで Snowpipe REST API を呼び出し | 秒 | 低 | [Snowpipe REST](https://docs.snowflake.com/en/user-guide/data-load-snowpipe-rest-overview) |

> **FPolicy スループットに関する注意**: FPolicy は NFS/SMB I/O パスに最小限のレイテンシを追加します（パススルーモードで通常 1 操作あたり <1ms）。ただし、高頻度ファイル書き込みワークロード（毎秒数千ファイル）では、本番デプロイ前に FSx for ONTAP ファイルシステムへのスループット影響を検証してください。

**推奨本番パターン:**
```
FSx for ONTAP ──FPolicy──▶ Lambda ──▶ SNS ──▶ Snowpipe REST API ──▶ COPY INTO ターゲットテーブル
     │                                              │
     └── NFS/SMB ユーザーが同じデータにアクセス         └── ロードデータに Snowflake ガバナンス
```

**シンプルな代替（FPolicy なし）:**
```
Snowflake Task（5分ごと）──▶ COPY INTO from @fsxn_stage
                                      │
                                      └── ロード済みファイルを自動追跡（COPY 履歴）
```

## クイックスタート

```bash
# 1. FSx for ONTAP S3 Access Point を作成（前提条件）
aws fsx create-and-attach-s3-access-point \
  --name snowflake-ap --type ONTAP \
  --ontap-configuration 'VolumeId=fsvol-xxx,FileSystemIdentity={Type=UNIX,UnixUser={Name=root}}'

# 2. CloudFormation で IAM ロールをデプロイ
cp params.example.json params.json  # 編集: S3AccessPointArn を設定
./deploy.sh

# 3. Snowflake で SQL スクリプトを実行 (01 → 09)
```

## 既知の制限事項

> ⚠️ **重要な前提**: Snowflake は External Stage のストレージバックエンドとして FSx for ONTAP S3 Access Point を公式にはサポート対象として文書化していません。本リポジトリの検証により、`AWS_ACCESS_POINT_ARN` パラメータを設定することで読み取り・ガバナンス操作が動作することを確認していますが、これは Snowflake の公式サポート対象外の構成です。本番利用の際は Snowflake サポートに確認することを推奨します。

以下の制限事項は、FSx for ONTAP S3 AP を Snowflake External Stage として使用した場合に観測されたものです:

1. **FSx for ONTAP S3 AP レイテンシ**: ListObjects に数十秒〜数分かかる場合がある
2. **Pre-signed URL（FSx for ONTAP S3 AP 側の制限）**: AWS の FSx for ONTAP S3 AP ドキュメントでは Pre-signed URL を「非サポート」と記載しているが、Snowflake の `GET_PRESIGNED_URL()` 関数で実際にはダウンロード可能な URL が生成されることを確認済み。ただし公式サポート外のため、本番利用は自己責任
3. **S3 Event Notifications 非サポート（FSx for ONTAP S3 AP 側の制限）**: FSx for ONTAP S3 AP が S3 Event Notifications をサポートしないため、Snowpipe の自動取り込みトリガーが不可（FPolicy + Lambda で代替）
4. **最大アップロードサイズ**: 50 GB（Multipart Upload 対応）
5. **AUTO_REFRESH 不可**: S3 Event Notifications に依存するため利用不可。手動 REFRESH または Snowflake Task でスケジュール実行が必要
6. **TO_FILE / FILE データ型（Snowflake 側の制限）**: FSx for ONTAP S3 AP 外部ステージでは `TO_FILE()` が "Remote file not found" を返し、Vision AI に直接使用不可。回避策: `COPY FILES` で暗号化なし内部ステージ（SNOWFLAKE_SSE）にコピー後、`TO_FILE(BUILD_SCOPED_FILE_URL(@internal_stage, path))` を使用

## 顧客適格化質問

アーキテクチャパターンを決定するための質問:

1. **データレジデンシー**: データは FSx for ONTAP に残す必要がある？ Snowflake マネージドストレージにコピー可能？
   - FSx に残す → External Table パターン
   - コピー可 → COPY INTO で最大性能

2. **AI/ML 要件**: テキスト AI（要約、翻訳、OCR）が必要？ Vision AI（画像分析）が必要？
   - テキスト AI のみ → External Table（直接、コピー不要）
   - Vision AI 必要 → ハイブリッドパターン（External Table + 画像のみ COPY FILES）

3. **クエリ性能**: サブ秒のレスポンスが必要？ 秒レベルで許容可能？
   - サブ秒 → COPY INTO 内部テーブル（マイクロパーティション、クラスタリング）
   - 秒レベル → External Table（S3 AP レイテンシ）

4. **コンプライアンス制約**: データ移動を制限する規制要件（HIPAA, SOX, GDPR）がある？
   - あり → External Table + SnapLock + FPolicy 監査（データは FSx から出ない）
   - なし → 性能/コストのトレードオフで選択

5. **マルチプロトコルアクセス**: NFS/SMB ユーザーが Snowflake と同じデータにアクセスする必要がある？
   - あり → External Table（ゼロコピー、マルチプロトコル）
   - なし → どちらのパターンでも可
