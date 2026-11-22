# Success Stories — Industry Use Cases

🌐 [日本語](#日本語版) | [English](#english-version)

> ⚠️ **DISCLAIMER**: The following are **hypothetical examples for illustration purposes only**.
> They do not represent actual customer deployments or verified results.
> Specific metrics are projected estimates based on architecture analysis, not measured outcomes.

---

<a id="english-version"></a>

## English Version

### Overview

These hypothetical scenarios illustrate how the Iceberg Metadata Catalog for FSx for ONTAP
could deliver value across different industries. Each story follows the pattern:
**Challenge → Solution → Projected Impact**.

---

### 🏭 Manufacturing: Design Document Reuse

**Hypothetical scenario: Large manufacturing company with 20+ years of CAD files**

#### Challenge

- 500,000+ CAD files (DWG, STEP, IGES) across multiple FSx for ONTAP volumes
- Engineers spend ~3 days searching for reusable designs manually
- Duplicate designs created because existing ones can't be found
- No searchable catalog — only folder structure and tribal knowledge

#### Solution with Metadata Catalog

```
FSx for ONTAP (CAD files) → S3 Access Point → Metadata Scan
    → AI Classification (Bedrock Vision: "pump housing", "valve assembly")
    → Iceberg Table (searchable metadata)
    → Athena SQL: "Find all pump housings > 200mm diameter"
```

#### Projected Impact

| Metric | Before | After (Projected) | Improvement |
|--------|--------|-------------------|-------------|
| Design search time | ~3 days | ~2 seconds | 99.99% reduction |
| Duplicate designs created/year | ~120 | ~10 | 92% reduction |
| Engineering hours saved/year | ~2,400 hrs | — | $360K value |
| Time-to-market for new products | 18 months | 15 months | 3 months faster |

#### Key Talking Point

> "3 days of searching → 2 seconds. Engineers design instead of searching."

---

### 🏦 Financial Services: Contract Compliance Search

**Hypothetical scenario: Financial institution with regulatory compliance requirements**

#### Challenge

- 200,000+ contracts, agreements, and compliance documents
- Quarterly audit requires finding all contracts with specific clauses
- Manual review: 2 weeks per audit cycle with 5 compliance staff
- Risk of missing documents → regulatory penalties

#### Solution with Metadata Catalog

```
FSx for ONTAP (contracts) → S3 Access Point → Metadata Scan
    → AI Summarization (Bedrock Claude: extract key clauses)
    → PII Detection (Comprehend: identify sensitive data)
    → Iceberg Table + Cortex Search
    → NL Query: "Find all contracts with auto-renewal expiring in Q1"
```

#### Projected Impact

| Metric | Before | After (Projected) | Improvement |
|--------|--------|-------------------|-------------|
| Audit preparation time | 2 weeks | 4 hours | 97% reduction |
| Documents missed per audit | ~15 | ~0 | Near-zero risk |
| Compliance staff needed | 5 FTE (2 weeks) | 1 FTE (4 hours) | 80% reduction |
| Regulatory penalty risk | High | Low | Significant reduction |

#### Key Talking Point

> "Complete audit readiness in hours, not weeks. Zero missed documents."

---

### 🏥 Healthcare: DICOM Research Sharing

**Hypothetical scenario: Research hospital sharing medical imaging data**

#### Challenge

- 1M+ DICOM files (MRI, CT, X-ray) across research departments
- Researchers need to find specific imaging studies for clinical trials
- HIPAA compliance requires strict access control and audit
- Cross-institution collaboration blocked by data sharing complexity

#### Solution with Metadata Catalog

```
FSx for ONTAP (DICOM files) → S3 Access Point → Metadata Scan
    → AI Classification (modality, body part, study type)
    → PII Anonymization (patient identifiers removed from metadata)
    → Iceberg Table + Row Access Policy (department-level)
    → Delta Sharing (cross-institution, metadata only)
```

#### Projected Impact

| Metric | Before | After (Projected) | Improvement |
|--------|--------|-------------------|-------------|
| Study discovery time | 1-2 days | < 30 seconds | 99%+ reduction |
| Cross-institution sharing setup | 3-6 months | 1 day | 99% faster |
| HIPAA compliance verification | Manual review | Automated policy | Continuous |
| Research dataset assembly | 2 weeks | 2 hours | 98% reduction |

#### Key Talking Point

> "Researchers find relevant imaging studies in seconds, share across institutions
> without copying data, with HIPAA compliance built into the platform."

---

### 🎬 Media & Entertainment: Video Asset Reuse

**Hypothetical scenario: Media company with large video archive**

#### Challenge

- 100,000+ video files (raw footage, edited content, graphics)
- Creative teams can't find existing B-roll or stock footage
- Re-shooting or re-purchasing footage that already exists
- No way to search by visual content or scene description

#### Solution with Metadata Catalog

```
FSx for ONTAP (video files) → S3 Access Point → Metadata Scan
    → AI Analysis (Bedrock Vision: scene description, objects, text)
    → Vector Embeddings (semantic similarity search)
    → Iceberg Table + OpenSearch
    → NL Query: "Find sunset footage over ocean with no people"
```

#### Projected Impact

| Metric | Before | After (Projected) | Improvement |
|--------|--------|-------------------|-------------|
| Asset search time | 2-4 hours | < 1 minute | 99% reduction |
| Stock footage purchases/year | $500K | $100K | $400K savings |
| Re-shoot costs avoided/year | — | $200K | New savings |
| Creative team productivity | Baseline | +30% | Significant |

#### Key Talking Point

> "Find the perfect B-roll in seconds. Stop re-buying footage you already own."

---

### Summary: Cross-Industry Value

| Industry | Primary Value | Search Improvement | Cost Impact |
|----------|--------------|-------------------|-------------|
| Manufacturing | Design reuse | 3 days → 2 sec | $360K/year saved |
| Financial | Compliance speed | 2 weeks → 4 hours | Risk reduction |
| Healthcare | Research sharing | 1-2 days → 30 sec | Faster trials |
| Media | Asset discovery | 2-4 hours → 1 min | $600K/year saved |

---

<a id="日本語版"></a>

## 日本語版

> ⚠️ **免責事項**: 以下は**説明目的の仮想的な事例**です。
> 実際の利用者の導入事例や検証済みの結果を表すものではありません。
> 具体的な数値はアーキテクチャ分析に基づく予測値であり、実測値ではありません。

---

### 概要

以下の仮想シナリオは、FSx for ONTAP 向け Iceberg メタデータカタログが
各業界でどのように価値を提供できるかを示しています。
各ストーリーは **課題 → ソリューション → 予測効果** のパターンに従います。

---

### 🏭 製造業: 設計ドキュメントの再利用

**仮想シナリオ: 20年以上のCADファイルを持つ大手製造企業**

#### 課題

- 複数のFSx for ONTAPボリュームに50万件以上のCADファイル（DWG、STEP、IGES）
- エンジニアが再利用可能な設計を手動で探すのに約3日かかる
- 既存の設計が見つからないため重複設計が発生
- 検索可能なカタログがない — フォルダ構造と属人的知識のみ

#### メタデータカタログによるソリューション

```
FSx for ONTAP (CADファイル) → S3アクセスポイント → メタデータスキャン
    → AI分類 (Bedrock Vision: "ポンプハウジング", "バルブアセンブリ")
    → Icebergテーブル (検索可能なメタデータ)
    → Athena SQL: "直径200mm以上のポンプハウジングを全て検索"
```

#### 予測効果

| 指標 | 導入前 | 導入後（予測） | 改善率 |
|------|--------|---------------|--------|
| 設計検索時間 | 約3日 | 約2秒 | 99.99%削減 |
| 年間重複設計数 | 約120件 | 約10件 | 92%削減 |
| 年間節約エンジニアリング時間 | 約2,400時間 | — | 5,400万円相当 |
| 新製品の市場投入時間 | 18ヶ月 | 15ヶ月 | 3ヶ月短縮 |

#### キートーキングポイント

> 「3日間の検索が2秒に。エンジニアは検索ではなく設計に集中できます。」

---

### 🏦 金融: 契約コンプライアンス検索

**仮想シナリオ: 規制コンプライアンス要件を持つ金融機関**

#### 課題

- 20万件以上の契約書、合意書、コンプライアンス文書
- 四半期監査で特定条項を含む全契約の特定が必要
- 手動レビュー: 監査サイクルごとに5名で2週間
- 文書の見落としリスク → 規制上のペナルティ

#### メタデータカタログによるソリューション

```
FSx for ONTAP (契約書) → S3アクセスポイント → メタデータスキャン
    → AI要約 (Bedrock Claude: 主要条項の抽出)
    → PII検出 (Comprehend: 機密データの特定)
    → Icebergテーブル + Cortex Search
    → 自然言語クエリ: "Q1に自動更新が期限切れになる全契約を検索"
```

#### 予測効果

| 指標 | 導入前 | 導入後（予測） | 改善率 |
|------|--------|---------------|--------|
| 監査準備時間 | 2週間 | 4時間 | 97%削減 |
| 監査あたりの見落とし文書数 | 約15件 | 約0件 | リスクほぼゼロ |
| 必要コンプライアンス人員 | 5名（2週間） | 1名（4時間） | 80%削減 |
| 規制ペナルティリスク | 高 | 低 | 大幅削減 |

#### キートーキングポイント

> 「監査準備が週単位から時間単位に。見落とし文書ゼロを実現。」

---

### 🏥 医療: DICOM研究データ共有

**仮想シナリオ: 医用画像データを共有する研究病院**

#### 課題

- 研究部門全体で100万件以上のDICOMファイル（MRI、CT、X線）
- 研究者が臨床試験用の特定画像検査を見つける必要がある
- HIPAA準拠のため厳格なアクセス制御と監査が必要
- データ共有の複雑さにより施設間連携が阻害されている

#### メタデータカタログによるソリューション

```
FSx for ONTAP (DICOMファイル) → S3アクセスポイント → メタデータスキャン
    → AI分類 (モダリティ、部位、検査種別)
    → PII匿名化 (患者識別子をメタデータから除去)
    → Icebergテーブル + Row Access Policy (部門レベル)
    → Delta Sharing (施設間、メタデータのみ)
```

#### 予測効果

| 指標 | 導入前 | 導入後（予測） | 改善率 |
|------|--------|---------------|--------|
| 検査発見時間 | 1-2日 | 30秒未満 | 99%以上削減 |
| 施設間共有セットアップ | 3-6ヶ月 | 1日 | 99%高速化 |
| HIPAAコンプライアンス検証 | 手動レビュー | 自動ポリシー | 継続的 |
| 研究データセット構築 | 2週間 | 2時間 | 98%削減 |

#### キートーキングポイント

> 「研究者が関連画像検査を数秒で発見、データコピーなしで施設間共有、
> HIPAAコンプライアンスがプラットフォームに組み込まれています。」

---

### 🎬 メディア: 映像アセットの再利用

**仮想シナリオ: 大規模映像アーカイブを持つメディア企業**

#### 課題

- 10万件以上の映像ファイル（素材、編集済みコンテンツ、グラフィックス）
- クリエイティブチームが既存のBロールやストック映像を見つけられない
- 既に所有している映像の再撮影や再購入が発生
- 映像内容やシーン説明での検索手段がない

#### メタデータカタログによるソリューション

```
FSx for ONTAP (映像ファイル) → S3アクセスポイント → メタデータスキャン
    → AI分析 (Bedrock Vision: シーン説明、オブジェクト、テキスト)
    → ベクトル埋め込み (セマンティック類似検索)
    → Icebergテーブル + OpenSearch
    → 自然言語クエリ: "人物なしの海上の夕日映像を検索"
```

#### 予測効果

| 指標 | 導入前 | 導入後（予測） | 改善率 |
|------|--------|---------------|--------|
| アセット検索時間 | 2-4時間 | 1分未満 | 99%削減 |
| 年間ストック映像購入費 | 7,500万円 | 1,500万円 | 6,000万円削減 |
| 回避された再撮影コスト/年 | — | 3,000万円 | 新規削減 |
| クリエイティブチーム生産性 | ベースライン | +30% | 大幅向上 |

#### キートーキングポイント

> 「完璧なBロールを数秒で発見。既に所有している映像の再購入を停止。」

---

### まとめ: 業界横断の価値

| 業界 | 主要価値 | 検索改善 | コスト効果 |
|------|---------|---------|-----------|
| 製造業 | 設計再利用 | 3日 → 2秒 | 年間5,400万円節約 |
| 金融 | コンプライアンス高速化 | 2週間 → 4時間 | リスク削減 |
| 医療 | 研究共有 | 1-2日 → 30秒 | 治験加速 |
| メディア | アセット発見 | 2-4時間 → 1分 | 年間9,000万円節約 |
