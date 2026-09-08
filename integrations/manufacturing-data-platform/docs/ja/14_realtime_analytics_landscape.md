# ハイブリッド製造アーキテクチャにおけるリアルタイム分析: ポジショニングガイド

🌐 [English](../en/14_realtime_analytics_landscape.md) | 日本語

> 最終更新: 2026-06-18
> 背景: Databricks Data + AI Summit 2026 — LTAP アーキテクチャ / Lakehouse//RT / Lakebase 発表

---

## 背景

Databricks Data + AI Summit (2026年6月) にて、Databricks は 2 つの相互に関連する重大発表を行った:

1. **LTAP (Lake Transactional/Analytical Processing)** — OLTP と OLAP を単一のレイクストレージ上で統合する新アーキテクチャ概念。CDC パイプラインを「不要」と宣言。
2. **Lakehouse//RT** — 「Reyden」エンジンをベースとしたリアルタイムクエリ層。Delta Lake / Iceberg テーブル上でミリ秒レベルのクエリを実行。

LTAP は**アーキテクチャ思想**、Lakehouse//RT は**クエリエンジン実装**であり、両者は以下の関係にある:

```
LTAP（概念: トランザクション + 分析 = 1コピー）
 ├── Lakebase（トランザクション層 — Postgres 互換）
 ├── Lakehouse//RT（リアルタイム分析層 — Reyden エンジン）
 └── Databricks SQL / Spark（バッチ/BI 分析層）
```

本ドキュメントでは、オンプレミスのリアルタイム分析（ClickHouse）とクラウドのガバナンス付き分析（Databricks）を含むハイブリッド製造データプラットフォームのアーキテクチャに、これらの発表がどう影響するかを評価する。

---

## アーキテクチャコンテキスト: 3層ハイブリッドプラットフォーム

```
Layer 1: エッジ/工場（オンプレミス）
  Kafka → ClickHouse → ローカルダッシュボード、異常検知

Layer 2: クラウドリアルタイム分析
  Kafka（レプリケーション） → ClickHouse Cloud or Lakehouse//RT → 運用ダッシュボード

Layer 3: ガバナンス付き AI/分析
  Databricks → Unity Catalog → Delta/Iceberg → AI, BI, コンプライアンス
```

Lakehouse//RT が提起する問い: **Layer 2 に専用 RT データベースが必要か、それとも Databricks が Layer 2 と 3 の両方を担えるか？**

---

## LTAP: パイプラインの終焉？ — アーキテクチャ影響分析

### LTAP の定義

LTAP (Lake Transactional/Analytical Processing) は DAIS 2026 キーノートで Ali Ghodsi が発表した新アーキテクチャ概念（evidence tier: **Public**）。40年間続いた OLTP/OLAP 分離を「レイク上の単一データコピー」で解消すると主張する。

| 特性 | 従来のアーキテクチャ | LTAP |
|------|---------------------|------|
| データコピー | 運用 DB → CDC → 分析 DB（2+ コピー） | レイク上の 1 コピー |
| パイプライン | ETL / CDC 必須 | 不要（Databricks 主張） |
| トランザクション | 専用 OLTP DB (PostgreSQL, MySQL 等) | Lakebase (Postgres 互換, レイク上) |
| 分析クエリ | 専用 OLAP DB / DWH | Lakehouse//RT (Reyden), Databricks SQL |
| データ鮮度 | CDC 遅延（秒〜分） | リアルタイム（同一ストレージ） |
| ガバナンス | 分散（DB ごとに個別） | 統一 (Unity Catalog) |

**Databricks の主張**: CDC は「Continuous Data Corruption」— スキーマドリフト、順序保証の破綻、トランザクション境界の消失が本番障害の原因。LTAP はこれらを構造的に排除する。

### LTAP を構成するコンポーネント

| コンポーネント | 役割 | ステータス |
|--------------|------|----------|
| **Lakebase** | Postgres 互換の operational DB。データは Delta/Iceberg でレイクに格納 | GA（AWS, Azure） |
| **Lakehouse//RT** | Reyden エンジンによるミリ秒クエリ。Delta/Iceberg 直接読み取り | Preview |
| **Lakebase Search** | ハイブリッド vector + full-text 検索。`lakebase_vector` / `lakebase_text` Postgres 拡張 | Beta |
| **Lakebase branching / PITR** | DB ブランチ。エージェントが破壊的操作を安全にテスト可能 | GA |
| **Unity Catalog** | 全レイヤー横断のガバナンス・リネージ・ACL | GA |

### 製造データプラットフォームへの影響

LTAP が完全に成熟した場合、本 PoC の 3 層アーキテクチャにおける **Layer 2 と Layer 3 の境界が消失**する可能性がある:

```
従来の 3 層モデル:
  Layer 1: エッジ (Kafka + ClickHouse ローカル)
  Layer 2: クラウド RT 分析 (別システム) ←── LTAP がここを吸収
  Layer 3: ガバナンス付き AI/分析 (Databricks) ←── LTAP がここに含む

LTAP モデル（Databricks のビジョン）:
  Layer 1: エッジ (Kafka + ローカル分析) — 変化なし
  Layer 2+3: Databricks LTAP
    ├── Lakebase: 品質検査結果のトランザクション書き込み
    ├── Lakehouse//RT: 運用ダッシュボード（ミリ秒応答）
    ├── Databricks SQL: BI / コンプライアンスレポート
    └── Unity Catalog: 全データのガバナンス
```

### 3 層モデル vs LTAP モデル: 製造ユースケースでの比較

| 観点 | 3 層モデル (CH + Databricks) | LTAP モデル (Databricks 統合) |
|------|------------------------------|-------------------------------|
| 管理対象システム数 | 3+ (Kafka, ClickHouse, Databricks) | 2 (Kafka, Databricks) |
| パイプライン複雑性 | CDC / Kafka Connector / 同期ロジック必要 | Lakebase に直接書き込み → 即分析 |
| ガバナンス | CH 側は自前実装 | Unity Catalog で統一 |
| エッジ対応 | ✅ CH オンプレ | ❌ Databricks はクラウドのみ |
| サブ 10ms レイテンシ | ✅ CH MergeTree | ❌ Reyden は 10-100ms |
| ネットワーク断続耐性 | ✅ ローカル動作 | ❌ クラウド接続必須 |
| AI エージェント統合 | 別途構築 | ネイティブ (Agent Bricks, Genie One) |
| Operational write + 即時分析 | CH は分析 DB（書き込みは別途） | Lakebase write → Lakehouse//RT 即クエリ |
| コスト透明性 | インフラ固定費 | DBU 課金（使った分だけ、だが予測困難） |
| 成熟度 | CH: 10年+, 本番実績多数 | LTAP: 2026-06 発表, Preview |

### LTAP が変えるもの / 変えないもの

#### 変えるもの（クラウド側の設計判断）

1. **ClickHouse Cloud の位置づけ再考**: クラウド上の「リアルタイムサービングレイヤー」として ClickHouse Cloud を採用する判断は、Lakehouse//RT GA + 価格確定後に再評価が必要
2. **CDC パイプラインの簡素化**: Kafka → ClickHouse → Databricks の 2 段インジェストが、Kafka → Lakebase の 1 段になる可能性
3. **エージェント統合の容易化**: Lakebase 上のデータに Genie One / Agent Bricks が直接アクセス。品質検査エージェントが operational データと analytical データを横断して推論

> **⚠️ 検証必要事項**:
> - **インジェスト機構未確認**: Kafka → Lakebase の具体的パスは未検証。候補: Kafka Connect JDBC Sink / Lakeflow Streaming / Structured Streaming DLT。推奨パスは Databricks ドキュメント公開後に確認要。
> - **伝搬遅延未計測**: Lakebase write → Lakehouse//RT queryable の遅延は未ベンチマーク。Delta Lake の write-audit-publish プロトコルにより、「即クエリ」が数百ミリ秒〜数秒の遅延を含む可能性あり。
> - **エッジ→クラウド障害時**: Kafka レプリケーション先が Lakebase 直接書き込みの場合、クラウド障害時のデータ損失/再送設計が必要。Kafka リテンション + 再送制御で RPO を定義すること。
> - **順序保証**: Kafka partition ordering が CDC なしで Lakebase 上で維持されるかはインジェスト機構に依存。Structured Streaming は watermark で順序保証可能、JDBC sink では保証なしの可能性。

#### 変えないもの（エッジ/オンプレの設計）

1. **エッジのリアルタイム分析**: LTAP にオンプレオプションはない。工場フロアの即時判断には引き続きローカル分析エンジン（ClickHouse 等）が必須
2. **ネットワーク断続耐性**: クラウド接続喪失時にラインを止めないための設計は LTAP の範囲外
3. **サブ 10ms アラート**: 装置制御フィードバックや即時停止判断は Reyden の 10-100ms では間に合わない場合がある
4. **FSx for ONTAP のペイロード保管**: 非構造化データ（画像、動画、CAD）の保管・マルチプロトコルアクセスは LTAP と直交。引き続き FSx for ONTAP が担う

### Lakebase × FSx for ONTAP の接点

LTAP/Lakebase は structured/operational データの統合だが、FSx for ONTAP との接点は以下:

| パターン | 説明 |
|---------|------|
| **メタデータ = Lakebase、ペイロード = FSx for ONTAP** | 品質検査のメタデータ（合否、測定値、タイムスタンプ）は Lakebase に書き込み、対応する画像・ログファイルは FSx for ONTAP に保管。Lakebase レコードに S3 AP URI を持たせてリンク |
| **Document Intelligence + FSx for ONTAP** | FSx for ONTAP 上の設計文書・仕様書を Document Intelligence でパースし、結果を Lakebase / Delta テーブルに格納。Lakebase Search でエージェントがハイブリッド検索 |
| **Lakebase branching ≈ FlexClone（スコープ差あり）** | Lakebase の DB branching（エージェントのサンドボックス）は概念的に FSx for ONTAP の FlexClone（ゼロコピー分岐）と類似。ただし **スコープが異なる**: Lakebase branching は DB テーブル（構造化データ、GB〜TB 規模）、FlexClone はボリューム全体（非構造化含む、TB〜PB 規模）。structured data は Lakebase branching、unstructured data は FlexClone で安全な検証環境を構築 |
| **SnapMirror 読み取りレプリカ** | エージェントワークロードの読み取り負荷を本番 FSx for ONTAP から分離するため、SnapMirror で読み取り専用レプリカを作成。エージェントは DP ボリュームの S3 AP 経由でペイロードを読み取り、本番 NFS/SMB ワークロードに影響しない |
| **FabricPool 容量プール階層化** | 製造ペイロード（画像・動画）は蓄積が大きい。エージェントが主にアクセスするのは直近データであるため、古いペイロードは FabricPool で容量プール（S3 Standard-IA）に自動階層化し、ストレージコストを最適化 |

> **⚠️ ガバナンスギャップ**:
> - Unity Catalog は Delta/Iceberg テーブルをガバナンスするが、**S3 AP URI 先のデータを直接ガバナンスしない**。エージェントが Lakebase レコードから S3 AP URI を取得し、ペイロードを読み取る場合、Unity Catalog ACL はそのペイロード読み取りを制御しない。
> - **対策**: アプリケーション層で S3 AP URI フォロースルー時の認可チェックを実装する必要がある。IAM ポリシー + S3 AP access point policy + エージェント IAM ロール分離で制御。
> - **Lakebase Search ベクトルの ACL**: Document Intelligence で抽出した情報が Lakebase Search に格納された場合、行レベルセキュリティがベクトル検索結果に適用されるかは未確認。Permission-aware RAG チェーン（FSx for ONTAP ACL → 抽出時 ACL メタデータ保持 → Lakebase テーブル行フィルタ → エージェントクエリ時フィルタ）の設計が必要。

> **⚠️ S3 AP レイテンシ考慮**:
> - Lakehouse//RT がミリ秒クエリを提供しても、エージェントが S3 AP 経由でペイロードをフォローフェッチする場合、ONTAP S3 プロトコルのオーバーヘッドが加算される。P99 レイテンシの実測が必要。
> - 大量ペイロードの同時読み取り（マルチエージェント並列）時の S3 AP スループット上限も検証要。

### 判断フレームワーク: LTAP の採用条件

```
                          ┌──────────────────┐
                          │ オンプレ要件あり？ │
                          └────────┬─────────┘
                                   │
                    Yes ┌──────────┴──────────┐ No
                        ▼                      ▼
              ┌─────────────────┐    ┌─────────────────────┐
              │ エッジ: 専用 RT   │    │ クラウドのみ？        │
              │ (ClickHouse 等)  │    │ Databricks 既存？   │
              └─────────┬───────┘    └──────────┬──────────┘
                        │                       │
                        │              Yes ┌────┴────┐ No
                        │                  ▼         ▼
                        │    ┌──────────────────┐ ┌─────────────────┐
                        │    │ LTAP 統合を検討    │ │ 要件に応じて選択   │
                        │    │ (Layer 2+3 統合)  │ │                 │
                        │    └──────────────────┘ └─────────────────┘
                        │
                        ▼
              ┌─────────────────────────────────┐
              │ ハイブリッド:                     │
              │ Edge = 専用 RT                   │
              │ Cloud = LTAP (Lakehouse//RT +   │
              │         Lakebase) に移行検討      │
              └─────────────────────────────────┘
```

### 成熟度に関する注意（2026-06 時点）

| コンポーネント | ステータス | 本番採用の目安 |
|--------------|----------|--------------|
| Lakebase | GA | 検証可能。ただし Postgres 互換性の範囲を確認要 |
| Lakehouse//RT (Reyden) | Preview | GA + 6ヶ月の安定化を推奨 |
| Lakebase Search | Beta | Preview 以降に再評価 |
| LTAP 全体 | アーキテクチャ宣言 | コンポーネントの個別 GA を待つ |

**推奨**: LTAP はアーキテクチャビジョンとして理解し、設計の方向性に反映する。ただし、PoC の現フェーズでは Lakehouse//RT の GA と価格確定を待ってから具体的な移行判断を行う。エッジ側の設計は LTAP に関わらず継続。

---

## 比較: 専用 RT DB vs Lakehouse//RT

| 軸 | 専用 RT DB (例: ClickHouse) | Lakehouse//RT (Databricks) |
|---|---|---|
| デプロイオプション | オンプレ、クラウド、ハイブリッド | クラウドのみ（現時点） |
| クエリレイテンシ | 1-50ms (MergeTree 最適化) | 10-100ms (Reyden, Preview) |
| データフォーマット | 独自カラムナ | オープン (Delta, Iceberg) |
| ガバナンス統合 | 外部（ビルトインカタログなし） | ネイティブ (Unity Catalog) |
| インジェスト遅延 | サブ秒 (Kafka Engine) | 秒〜分 (Structured Streaming) |
| ネットワーク回復力 | 障害時もローカル動作 | クラウド接続必須 |
| コンカレンシー | 数百〜千同時クエリ | 高 (Reyden で改善) |
| コストモデル | インフラベース（クエリ課金なし） | DBU ベース（コンピュート時間課金） |
| AI/ML 統合 | 別パイプライン必要 | ネイティブ (MLflow, Feature Store) |

---

## Lakehouse//RT が専用 RT エンジンを代替できるケース

1. **全データが既に Databricks にある** — 別のインジェストパス不要
2. **クラウドのみのアーキテクチャ** — オンプレ/エッジ要件なし
3. **ガバナンスが最優先** — UC lineage / ACL が必須
4. **10-100ms レイテンシで十分** — BI ダッシュボード（サブ 10ms アラートでない）
5. **統一プラットフォーム志向** — 管理システム数を最小化したい

## 専用 RT エンジンが引き続き必要なケース

1. **オンプレ/エッジ展開** — 工場フロア、製造ライン、断続接続環境
2. **サブ 10ms レイテンシ必須** — リアルタイムアラート、異常検知、制御フィードバック
3. **超高頻度インジェスト** — 毎秒数百万イベント、サブ秒可視化
4. **ネットワーク断続時の動作** — クラウド接続喪失時も継続必須
5. **コスト重視の大量クエリ** — クエリ課金なし、固定インフラコスト
6. **軽量デプロイ** — 1つの分析ユースケースに Databricks フルプラットフォーム不要

---

## ハイブリッドアーキテクチャ: 共存パターン

製造・産業 IoT ユースケースでは、最適アーキテクチャは**両方を使う**ことが多い:

```
オンプレミス                          クラウド (AWS)
┌──────────────────────┐      ┌──────────────────────────┐
│ センサー/PLC/カメラ    │      │                          │
│        │             │      │   Kafka (レプリケーション) │
│        ▼             │      │        │                 │
│ Kafka (ローカル)      │─────▶│        ▼                 │
│        │             │      │ Databricks Lakehouse//RT │
│        ▼             │      │ (ガバナンス付き、AI対応、    │
│ ClickHouse (ローカル) │      │  ミリ秒クエリ)             │
│ - 異常検知            │      │                          │
│ - 品質ダッシュボード    │      │ Unity Catalog ガバナンス   │
│ - サブ5msアラート      │      │ AI/ML モデル訓練           │
│                      │      │ 工場横断比較分析            │
│ ペイロードストレージ    │      │                          │
│ (ONTAP オンプレ)      │─ ─ ─ │ FSx for ONTAP (キャッシュ) │
└──────────────────────┘      └──────────────────────────┘
```

**役割分担:**
- **ローカル ClickHouse**: 即時運用分析（ライン停止判断、品質アラート、OEE）
- **Lakehouse//RT / Databricks**: 工場横断分析、AI サービング、ガバナンス付き BI、コンプライアンス

---

## この PoC への影響

| PoC コンポーネント | Lakehouse//RT の影響 | LTAP の影響 | アクション |
|---|---|---|---|
| オンプレ ClickHouse (Phase B) | **影響なし** — クラウドのみ | **影響なし** — オンプレ対象外 | 設計通り継続 |
| ClickHouse Cloud (Phase A) | **代替可能性** — Databricks が既にあれば | **吸収対象** — Layer 2 を LTAP に統合するシナリオ | GA 後に再評価 |
| Kafka → ClickHouse パイプライン | **補完関係** — CH=ローカル RT、DB=ガバナンス分析 | **簡素化候補** — Kafka → Lakebase 直接パスで CH Cloud 不要の可能性 | 両パス維持、LTAP GA 後に削減判断 |
| Databricks Structured Streaming | **強化** — Streaming table のレイテンシ改善の可能性 | **統合** — streaming + operational + analytical が同一基盤 | GA 性能を監視 |
| FSx for ONTAP ペイロードストレージ | **影響なし** — 非構造化データは対象外 | **補完関係** — structured=Lakebase、unstructured=FSx for ONTAP | メタデータリンク設計を開始 |
| マルチエージェントパイプライン (Omnigent) | **間接的** — 分析データへのアクセス改善 | **直接的** — Agent Bricks + Lakebase でエージェント統合ネイティブ化 | Omnigent 設計に Lakebase 連携追記 |

### 推奨

- **Phase A (AWS)**: ClickHouse Cloud でリアルタイム検証を継続。Lakehouse//RT GA + 価格確定後に再評価。**LTAP ビジョンに基づき、Kafka → Lakebase 直接書き込みの PoC パスを並行して設計**（Lakebase は GA だが ap-northeast-1 非対応 — us-east-1 or ap-southeast-1 で検証）。
- **Phase B (オンプレ)**: ClickHouse オンプレは影響なし。LTAP / Lakehouse//RT にオンプレオプションなし。
- **長期**: LTAP が Layer 2+3 を統合する方向性を前提に、クラウド側アーキテクチャの簡素化パスを設計しておく。エッジ側は独立して進化させる。
- **FSx for ONTAP 連携**: Lakebase レコードと FSx for ONTAP ペイロードのリンク設計（S3 AP URI をメタデータカラムに保持）を Phase A の早期に検証する。

> **クロスリポジトリ連携**: `ontap-edge-to-cloud-ai` リポジトリでは Path D (Kafka → Lakebase) として LTAP パスを設計検討中（2026-06-18 追加）。詳細は [クロスリポジトリ連携戦略](../../../../docs/ja/cross-repo-integration-strategy.md) のエッジ → クラウド連携セクションを参照。

> **DAIS 2026 追加情報（2026-06-18）**:
> - **Lakeflow Zerobus Ingest**: 高スループットイベント取り込みの新インターフェース（GA）。Private Link 対応。Kafka の代替ではなく、Databricks 専用取り込みの**追加オプション**として位置づけ。`ontap-edge-to-cloud-ai` で評価済み（[クロスリポジトリ連携戦略の Lakeflow 評価](../../../../docs/ja/cross-repo-integration-strategy.md#lakeflow-評価-zerobus-ingest--real-time-modedais-2026--2026-06-18-同期)参照）。([Lakeflow blog](https://www.databricks.com/blog/lakeflow-new-era-agentic-data-engineering))
> - **Lakeflow Real-Time Mode (Spark Declarative Pipelines)**: Structured Streaming のレイテンシを秒〜分から ~5ms まで短縮する実行モード（**GA, 2025-12**）。上記「専用 RT DB vs Lakehouse//RT」比較表のインジェスト遅延（秒〜分, Structured Streaming）を改善するパス。**Lakehouse//RT（クエリエンジン）とは別機能**で、`ontap-edge-to-cloud-ai` の Path A 改善として即適用可能。([Lakeflow blog](https://www.databricks.com/blog/lakeflow-new-era-agentic-data-engineering))
> - **Lakebase Private Link (GA)**: VPC 内から Lakebase への Private Link 接続（port 5432）が利用可能。エージェント → Lakebase アクセスのネットワーク経路にパブリックインターネットを経由しない設計が可能。([Security blog](https://www.databricks.com/blog/whats-new-databricks-platform-security-and-compliance-data-ai-summit-2026))
> - **AIM (Automatic Identity Management) for Entra ID — GA on AWS**: ユーザー/グループの Databricks ワークスペースへの ID 同期を自動化。エージェントが属するグループメンバーシップの自動反映に寄与し、ACL ベースのアクセス制御設計を簡素化する可能性。

> ⚠️ **リージョン制約確認済み (2026-06-18)**: [公式ドキュメント](https://docs.databricks.com/en/resources/feature-region-support.html)により、**Lakebase Autoscaling は ap-northeast-1 (Tokyo) で利用不可**であることを確認。本プロジェクトが ap-northeast-1 前提の場合、LTAP Path D (Kafka → Lakebase) の検証は以下のいずれかで対応:
> - Lakebase 対応リージョン（us-east-1 / ap-southeast-1 / ap-southeast-2）で技術検証のみ実施
> - ap-northeast-1 対応を待つ（Databricks リージョン拡大時期不明）
> - Path A (Kafka → Structured Streaming → Delta) を継続し、Path D を長期候補に留める
>
> Zerobus Ingest は ap-northeast-1 対応済みのため、Zerobus → Delta (Structured Streaming) パスは利用可能。

---

## 主要ポイント

1. **LTAP は「パイプラインの終焉」を宣言** — OLTP/OLAP 分離、CDC、データコピーを構造的に排除するアーキテクチャビジョン
2. Lakehouse//RT は LTAP のクエリ層実装。Databricks 内クラウドリアルタイム分析の大きな進歩
3. 「別のサービングレイヤー」パターン（クラウド上の ClickHouse, Druid, Pinot）を直接ターゲット
4. **Lakebase が LTAP のトランザクション層**。Postgres 互換で operational write + 即時分析を実現
5. オンプレ、エッジ、ネットワーク断続環境のリアルタイム分析には対応**しない** — ハイブリッド製造アーキテクチャでは引き続きエッジ層が必要
6. **FSx for ONTAP は非構造化ペイロードストレージとして LTAP と直交的に共存** — structured data = Lakebase、unstructured data = FSx for ONTAP の役割分担
7. エージェント統合（Agent Bricks / Genie One）が LTAP データにネイティブアクセスする設計は、Omnigent マルチエージェント設計に影響

---

## 参考

### AWS 公式: FSx for ONTAP × Bedrock RAG

- [AWS 公式チュートリアル: Build a RAG application using Amazon Bedrock Knowledge Bases with FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html) — S3 AP 経由で FSx for ONTAP を Bedrock KB データソースとして構成する公式ガイド
- [repost.aws: Using FSx for ONTAP S3 Access Points as an Amazon Bedrock Data Source](https://repost.aws/articles/AReKa8-o8XRGeVW2Nicbg1_w) — コミュニティガイド

### Databricks / DAIS 2026

- [Databricks: LTAP プレスリリース](https://www.databricks.com/company/newsroom/press-releases/databricks-launches-ltap-first-lake-transactionalanalytical) (2026-06-16)
- [Databricks: Introducing Lakehouse//RT](https://www.databricks.com/blog/introducing-lakehousert-real-time-performance-unified-lakehouse) (2026-06-16)
- [Databricks: Lakehouse//RT プレスリリース](https://www.databricks.com/company/newsroom/press-releases/databricks-launches-lakehousert-bring-real-time-analytics-directly) (2026-06-16)
- [Databricks: Lakebase Search (Beta)](https://www.databricks.com/blog/announcing-lakebase-search-agent-native-retrieval-built-lakebase-postgres) (2026-06-16)
- [Databricks: Agent Bricks DAIS 2026](https://www.databricks.com/blog/agent-bricks-dais-2026) (2026-06-16)
- [Databricks: What's new with Unity Catalog](https://www.databricks.com/blog/whats-new-unity-catalog-data-ai-summit-2026) (2026-06-16)
- [diginomica: Why Databricks calls CDC 'continuous data corruption'](https://diginomica.com/why-databricks-calls-cdc-continuous-data-corruption-and-what-it-built-instead) (2026-06-16)
- [Databricks: Lakeflow — A new era of agentic data engineering](https://www.databricks.com/blog/lakeflow-new-era-agentic-data-engineering) (2026-06-16)
- [Databricks: What's new in Platform Security and Compliance](https://www.databricks.com/blog/whats-new-databricks-platform-security-and-compliance-data-ai-summit-2026) (2026-06-17)
- [Databricks: AWS and Databricks at DAIS 2026](https://www.databricks.com/blog/aws-and-databricks-data-ai-summit-2026-accelerating-real-world-ai-innovation) (2026-06-09)
- [ClickHouse vs Databricks: Join Performance](https://clickhouse.com/blog/join-me-if-you-can-clickhouse-vs-databricks-snowflake-join-performance) (2025)
- [ClickHouse: Real-Time Analytics Platforms Comparison](https://clickhouse.com/resources/engineering/real-time-analytics-platforms-a-practical-comparison) (2025)
- 本リポジトリ: [Kafka/ClickHouse → Unity Catalog 接続（通信経路・ポート視点、ストレージとは別観点）](../../../../docs/ja/kafka-clickhouse-unity-catalog-connectivity.md)
