# 製造業向けデモシナリオ: 設計図面 AI 分類 & 類似検索

> 設計部門のファイル活用を劇的に改善するデモシナリオ

---

## ビジネスコンテキスト

### 課題

設計部門が直面する典型的な課題：

- **CAD/PDF が増え続ける**: 設計図面、品質レポート、議事録が日々数百件生成されるが、体系的に管理されていない
- **再利用率が低い**: 過去に類似の設計があっても見つけられず、ゼロから設計し直すケースが多発
- **検索に時間がかかる**: ファイルサーバーの深い階層を手動で探す時間が 1 日あたり 30 分以上
- **属人化**: ベテラン設計者の退職でナレッジが消失するリスク

### 解決後の姿

- ファイルが作成された瞬間に AI が自動分類・タグ付け
- 「部品番号 ABC-1234 に関連する設計図面」を SQL 一発で検索
- 「この図面に似た過去の設計」をベクトル検索で即座に発見
- 設計者 1 人あたり検索時間を **30 分/日** 削減

---

## デモフロー

### ステップ 1: CAD/PDF ファイルを FSx に配置

**所要時間**: 2 分

```bash
# サンプルファイルを FSx for ONTAP にコピー
./demo/scripts/upload-sample-data.sh --industry manufacturing --target /vol/engineering/
```

**配置するファイル例**:

| ファイル名 | 種類 | 説明 |
|-----------|------|------|
| `frame-assembly-ABC-1234-R3.pdf` | 設計図面 | メインフレームのアセンブリ図、SUS304 |
| `quality-report-L2026-001.pdf` | 品質レポート | ロット L2026-001 の検査結果 |
| `bom-main-frame-v2.xlsx` | 部品表 | メインフレーム BOM（47 部品） |
| `design-review-20260120.docx` | 議事録 | 設計レビュー会議（出席者 8 名） |
| `shaft-bearing-DEF-5678.dwg` | CAD 3D | シャフトベアリング 3D モデル |

**トークポイント**:
- 「設計者が普段通りにファイルを保存するだけです。特別な操作は不要です」
- 「NFS/SMB どちらのプロトコルでも、AI パイプラインが自動的にトリガーされます」

---

### ステップ 2: FPolicy でファイル検知 → AI 自動分類

**所要時間**: 約 42 秒/ファイル（自動実行）

ファイルが FSx for ONTAP に配置されると：

1. **FPolicy がファイル作成イベントを検知**
2. **Lambda が S3 Access Point 経由でファイルにアクセス**
3. **Bedrock Claude がファイル内容を解析し分類**

```
📄 Processing: frame-assembly-ABC-1234-R3.pdf
🔍 FPolicy event: CREATE detected
🤖 Bedrock analysis:
   - ファイル種別: CAD/設計図面
   - 部品番号: ABC-1234
   - リビジョン: R3
   - 材質: SUS304
   - プロジェクト: PRJ-2026-042
   - 部門: 設計第一課
✅ Classified in 42.1s | Cost: $0.07
```

**トークポイント**:
- 「FPolicy はファイルシステムレベルのイベント検知です。ポーリングではありません」
- 「Bedrock Claude は PDF の中身を読み取り、部品番号やリビジョンを自動抽出します」
- 「日本語のドキュメントも正確に処理できます」

---

### ステップ 3: 自動タグ付け結果の確認

**所要時間**: 3 分

全ファイルの処理完了後、分類結果を確認：

```sql
-- Athena で分類結果を確認
SELECT file_path, ai_classification, confidence_score, part_number, revision, material
FROM s3_tables.metadata_catalog.file_metadata
WHERE department = '設計第一課'
ORDER BY scan_timestamp DESC;
```

**期待される結果**:

| file_path | ai_classification | confidence | part_number | revision | material |
|-----------|------------------|-----------|-------------|----------|----------|
| /vol/engineering/frame-assembly-ABC-1234-R3.pdf | CAD/設計図面 | 0.94 | ABC-1234 | R3 | SUS304 |
| /vol/engineering/quality-report-L2026-001.pdf | 品質レポート | 0.97 | - | - | - |
| /vol/engineering/bom-main-frame-v2.xlsx | 部品表 (BOM) | 0.91 | - | v2 | - |
| /vol/engineering/design-review-20260120.docx | 議事録 | 0.96 | - | - | - |
| /vol/engineering/shaft-bearing-DEF-5678.dwg | CAD 3Dモデル | 0.93 | DEF-5678 | - | - |

**トークポイント**:
- 「5 種類のファイルが自動的に正しく分類されました」
- 「信頼度スコアが 0.9 以上 — 高精度な分類結果です」
- 「手動タグ付けは不要。ファイルを保存するだけで自動的にカタログ化されます」

---

### ステップ 4: 部品番号による設計図面検索

**所要時間**: 5 分

**シナリオ**: 「部品 ABC-1234 に関連するすべての設計ドキュメントを探したい」

```sql
-- 部品番号 ABC で始まるすべてのドキュメント
SELECT file_path, ai_classification, part_number, revision, last_modified
FROM s3_tables.metadata_catalog.file_metadata
WHERE part_number LIKE 'ABC%'
ORDER BY revision DESC;

-- 特定ロットの品質レポート
SELECT file_path, inspection_result, lot_number, inspection_date
FROM s3_tables.metadata_catalog.file_metadata
WHERE lot_number = 'L2026-001'
ORDER BY inspection_date DESC;

-- 直近 7 日間の設計変更
SELECT file_path, change_type, part_number, scan_timestamp
FROM s3_tables.metadata_catalog.file_metadata
WHERE ai_classification IN ('CAD/設計図面', 'CAD 3Dモデル')
  AND scan_timestamp > current_timestamp - interval '7' day
ORDER BY scan_timestamp DESC;
```

**トークポイント**:
- 「従来はフォルダ階層を辿って探していた作業が、SQL 一発で完了します」
- 「部品番号、ロット番号、日付 — あらゆる切り口で検索可能です」
- 「BI ツール（QuickSight、Tableau）からも同じデータにアクセスできます」

---

### ステップ 5: ベクトル検索で「類似設計」を発見

**所要時間**: 5 分

**シナリオ**: 「このフレーム設計に似た過去の設計はないか？」

OpenSearch Dashboards を開く：

1. **キーワード検索**: `"SUS304 フレーム アセンブリ"` → 関連ファイルを表示
2. **類似検索**: `frame-assembly-ABC-1234-R3.pdf` の「類似ファイルを検索」ボタン → ベクトル類似度で過去の設計を発見
3. **自然言語検索**: `「強度計算が含まれる設計図面で、アルミ合金を使用しているもの」` → セマンティック検索

**トークポイント**:
- 「ベクトル検索は、ファイル名が異なっていても内容が類似していれば見つけ出します」
- 「過去の設計を再利用すれば、設計時間を大幅に短縮できます」
- 「ベテラン設計者の暗黙知をシステムが補完します」

---

## サンプルデータの準備

デモ用に以下のファイルを準備してください：

```yaml
# integrations/iceberg-metadata-catalog/demo/sample-data/industry-configs/manufacturing.yaml を参照
必要ファイル数: 50 件（推奨）
  - 設計図面 (PDF): 15 件
  - 品質レポート (PDF): 10 件
  - 部品表 (XLSX): 5 件
  - 議事録 (DOCX): 8 件
  - CAD 3D (DWG): 12 件
```

サンプルデータは自動生成可能：

```bash
./demo/scripts/generate-sample-data.sh --industry manufacturing --count 50
```

---

## 期待される結果

| 指標 | 目標値 |
|------|--------|
| 分類精度 | 90% 以上（5 カテゴリ） |
| 処理時間 | 42 秒/ファイル |
| 1 ファイルあたりコスト | $0.07 |
| 検索レスポンス（Athena） | 2–3 秒 |
| 検索レスポンス（OpenSearch） | <1 秒 |
| ベクトル類似検索精度 | 上位 5 件に関連ファイルが含まれる |

---

## ROI ストーリー

### 定量効果

| 項目 | 計算 | 年間効果 |
|------|------|---------|
| 検索時間削減 | 30 分/日/人 × 50 人 × 250 日 | **6,250 時間/年** |
| 設計再利用率向上 | 新規設計の 20% を過去設計流用に転換 | **設計工数 15% 削減** |
| 品質トレーサビリティ | 不具合追跡時間 2 時間→5 分 | **即時追跡** |
| コンプライアンス | 手動分類→自動分類（監査工数削減） | **監査対応 80% 効率化** |

### コスト

| 項目 | 月額 |
|------|------|
| AI パイプライン（1,000 ファイル/日） | ~$114 |
| 検索時間削減効果（50 人 × 30 分/日） | 約 75 万円相当 |
| **ROI** | **650 倍以上** |

---

## カスタマイズのポイント

利用者の環境に合わせて以下を調整：

1. **分類カテゴリ**: 利用者のファイル種別に合わせて追加/変更
2. **抽出フィールド**: 部品番号、プロジェクトコード、部門名などを設定
3. **言語対応**: 日本語 + 英語の混在ドキュメントも対応可能
4. **セキュリティ**: Lake Formation で部門単位のアクセス制御を設定

---

## Iceberg Time Travel: 履歴比較

Iceberg テーブル形式のユニークな利点の一つがタイムトラベル — 過去の任意の時点でのメタデータをクエリする機能です。

```sql
-- スナップショット履歴の表示
SELECT * FROM s3_tables.metadata_catalog.file_metadata$snapshots
ORDER BY committed_at DESC LIMIT 10;

-- 24 時間前の時点でのメタデータをクエリ
SELECT ai_classification, COUNT(*) as file_count
FROM s3_tables.metadata_catalog.file_metadata
FOR TIMESTAMP AS OF (current_timestamp - interval '24' hour)
GROUP BY ai_classification;

-- 現在 vs. 以前の分類件数を比較
WITH current_state AS (
  SELECT ai_classification, COUNT(*) as current_count
  FROM s3_tables.metadata_catalog.file_metadata
  GROUP BY ai_classification
),
previous_state AS (
  SELECT ai_classification, COUNT(*) as previous_count
  FROM s3_tables.metadata_catalog.file_metadata
  FOR TIMESTAMP AS OF (current_timestamp - interval '7' day)
  GROUP BY ai_classification
)
SELECT COALESCE(c.ai_classification, p.ai_classification) as category,
       COALESCE(c.current_count, 0) as now,
       COALESCE(p.previous_count, 0) as week_ago,
       COALESCE(c.current_count, 0) - COALESCE(p.previous_count, 0) as delta
FROM current_state c
FULL OUTER JOIN previous_state p ON c.ai_classification = p.ai_classification
ORDER BY delta DESC;
```

**この業界でのタイムトラベル活用例**:
- ファイル分類分布の時系列変化を追跡
- コンプライアンス判断時のメタデータ状態を監査
- 意図しない一括再分類や削除からの復旧
- 異なる AI モデルバージョン間のエンリッチメント結果比較


---

*関連ファイル: [`manufacturing.yaml`](../sample-data/industry-configs/manufacturing.yaml)*
