🌐 [English](../en/aws-context-vs-unity-catalog.md) | **日本語**

# AWS Context vs Unity Catalog: データカタログ・ナレッジグラフ比較

> **ステータス**: 初版（2026-06-18）。AWS Context は Preview。DAIS 2026 + AWS Summit NYC 2026 の公開情報に基づく。
> **エビデンス階層**: 全主張に **Public**（公開ソースで検証可能）を付記。

---

## 本リポジトリにとっての重要性

本リポジトリは FSx for ONTAP 上のデータを Databricks（Unity Catalog）と AWS 分析サービスの両方に接続するパターンを検証しています。AWS Context は AWS 側のデータカタログ/ディスカバリ層として、Unity Catalog と**補完的または競合的**に位置づけられます。

製造データプラットフォームでは:
- **構造化メタデータ**（スキーマ、リネージ、ACL）を管理するカタログが必要
- **エージェント**が適切なデータを発見し、アクセスするためのディスカバリ層が必要
- **マルチプラットフォーム**（AWS ネイティブサービス + Databricks）にまたがるガバナンスが必要

---

## サービス概要

### AWS Context（Preview, 2026-06-17）

AWS Context は、データとビジネスロジックを自動的にナレッジグラフにマッピングし、AI エージェントが検索・発見できるようにするサービス（**Public**: [AWS Summit NYC 2026](https://www.aboutamazon.com/news/aws/aws-summit-nyc-2026-ai-agents), [TechTarget](https://www.techtarget.com/searchdatamanagement/news/366644853/AWS-latest-to-introduce-context-layer-for-agentic-AI)）。

| 特性 | 内容 |
|------|------|
| **中核技術** | ナレッジグラフ（Amazon Quick の本番ナレッジグラフ技術を拡張） |
| **メタデータ出力形式** | Apache Iceberg フォーマット、Amazon S3 Tables 経由でクエリ可能 |
| **外部カタログ接続** | API および Model Context Protocol (MCP) サーバー/ツール経由 |
| **学習** | ユーザー利用パターンから自動学習（Amazon Quick で数十万ユーザーが日常利用） |
| **エージェント統合** | エージェントがデータを検索・発見するための統一ディスカバリ層 |
| **ステータス** | Preview（2026-06-17 発表） |

### Unity Catalog（GA）

Databricks Unity Catalog は、データ、AI モデル、エージェント、MCP サービスを統一ガバナンスするカタログ（**Public**: [DAIS 2026](https://www.databricks.com/blog/whats-new-unity-catalog-data-ai-summit-2026)）。

| 特性 | 内容 |
|------|------|
| **中核技術** | メタストア + アクセス制御 + リネージ + 監査 |
| **メタデータ形式** | Delta Lake / Iceberg メタデータレイヤー |
| **外部カタログ接続** | フェデレーションコネクタ（AWS Glue, Hive Metastore, Snowflake Horizon） |
| **AI ガバナンス** | Unity AI Gateway — モデル/エージェント/MCP/skill のランタイムガバナンス |
| **エージェント統合** | Genie Ontology, Agent Bricks, Managed Omnigent を直接ガバナンス |
| **ステータス** | GA（Iceberg v3 / Managed Iceberg / Foreign Iceberg も GA） |

---

## 比較表

| 軸 | AWS Context | Unity Catalog |
|----|-------------|---------------|
| **主な役割** | データディスカバリ + ナレッジグラフ | データガバナンス + アクセス制御 |
| **アプローチ** | 自動マッピング + 学習 | 明示的登録 + ポリシー定義 |
| **データ形式** | Iceberg (S3 Tables) | Delta Lake / Iceberg |
| **ACL 管理** | IAM ベース（AWS ネイティブ） | 独自 ACL + ABAC (cross-engine) |
| **リネージ** | 不明（Preview で詳細未公開） | ネイティブ（テーブル → カラム → ダッシュボード） |
| **エージェントディスカバリ** | ナレッジグラフ検索（primary use case） | Genie Ontology + メタデータ検索 |
| **MCP 対応** | MCP サーバー/ツールで外部接続 | MCP サービスをガバナンス対象に含む |
| **クロスプラットフォーム** | AWS サービス中心 + 3rd party カタログ接続 | マルチクラウド（AWS, Azure, GCP） |
| **ストレージ非依存性** | S3 / S3 Tables 中心 | Delta Lake / Iceberg / 外部テーブル |
| **成熟度** | Preview (2026-06) | GA (5年+) |
| **コスト** | 未発表 | Databricks プラットフォーム費用に含む |

---

## 位置づけ: 補完と競合の切り分け

### 補完的に使えるシナリオ（推奨）

```
                    AWS Context (ディスカバリ層)
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
    S3 Tables       Glue Catalog    外部カタログ
    (Iceberg)       (Athena, EMR)   (MCP 接続)
                                        │
                                        ▼
                                 Unity Catalog
                                 (Databricks ガバナンス)
```

- **AWS Context** = 「データはどこにあるか？」を発見するナレッジグラフ
- **Unity Catalog** = 「データにどうアクセスし、誰が使えるか？」を制御するガバナンス
- 両者は MCP 経由で接続可能 — AWS Context が Unity Catalog のメタデータを MCP サーバー経由で取り込み、エージェントに統一ディスカバリを提供

### 競合的になるシナリオ

- Databricks だけで完結する組織 → Unity Catalog のみで十分（AWS Context 不要）
- AWS ネイティブサービスだけで完結する組織 → AWS Context + Glue Catalog で十分（Unity Catalog 不要）
- 両方使う組織 → **両方必要だが責務分離が重要**

---

## 本リポジトリ（製造データプラットフォーム）での選定ガイダンス

### 現在のアーキテクチャでの位置づけ

| レイヤー | カタログ候補 | 理由 |
|---------|-------------|------|
| **Layer 1: エッジ** | なし（ローカルスキーマのみ） | カタログ不要 |
| **Layer 2+3: Databricks LTAP** | Unity Catalog | Databricks データは UC がネイティブガバナンス |
| **AWS ネイティブサービス** (Athena, EMR, Bedrock KB) | AWS Context + Glue Catalog | S3 AP 経由の FSx for ONTAP データを発見 |
| **クロスプラットフォーム統合** | AWS Context（MCP 経由で UC 接続） | エージェントが両プラットフォームのデータを発見 |

### FSx for ONTAP との接点

| パターン | AWS Context での位置づけ | Unity Catalog での位置づけ |
|---------|--------------------------|--------------------------|
| S3 AP 経由のファイルデータ | ナレッジグラフにメタデータ自動登録（S3 Tables として） | External Location / Foreign Iceberg として登録 |
| 品質検査画像 | S3 AP URI をディスカバリ対象に含む | Lakebase レコードから URI 参照 |
| 設計文書 (Document Intelligence) | 抽出結果を S3 Tables として発見可能に | Delta テーブルとして UC に格納 |
| 監査ログ (`vserver audit`) | CloudWatch + ナレッジグラフで相関分析 | Unity Catalog 監査ログとの突合。**FPolicy は S3 Access Point 経由の操作を出さないため監査の入力にしない** |

### 推奨アーキテクチャ

```
FSx for ONTAP (NFS/SMB/S3 AP)
       │
       ├───── S3 Access Point ─────┐
       │                           │
       ▼                           ▼
  AWS Context                 Unity Catalog
  (ディスカバリ)               (ガバナンス)
       │                           │
       │    ┌── MCP 接続 ──┐       │
       │    │              │       │
       ▼    ▼              ▼       ▼
  Amazon Quick          Genie One / Agent Bricks
  (ビジネスユーザー)     (データチーム / エンジニア)
       │                           │
       └─────── Bedrock AgentCore Gateway ──────┘
               (MCP 統合、ガバナンス)
```

**設計原則**:
- データガバナンス（ACL、リネージ、監査）は Unity Catalog が担う
- データディスカバリ（発見、関係性マッピング、学習）は AWS Context が担う
- エージェントは AgentCore Gateway 経由で両方にアクセス
- FSx for ONTAP は両カタログに S3 AP 経由でメタデータを提供

---

## 検証必要事項

> **⚠️ AWS Context は Preview のため、以下は GA 後に検証が必要**:
> 1. S3 AP for FSx for ONTAP のメタデータが AWS Context に自動登録されるか
> 2. MCP 経由で Unity Catalog のメタデータを AWS Context に取り込めるか
> 3. AWS Context のナレッジグラフが FSx for ONTAP のディレクトリ構造/ACL を理解するか
> 4. Amazon Quick から FSx for ONTAP 上のデータに対する問い合わせが機能するか
> 5. 価格モデル（ナレッジグラフ構築 + クエリ課金?）

---

## 関連リポジトリとの接点

| リポジトリ | AWS Context との関連 | Unity Catalog との関連 |
|-----------|---------------------|----------------------|
| [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) | S3 AP イベントで AWS Context にメタデータ自動登録するパターンが候補 | — |
| [FSx-for-ONTAP-Agentic-Access-Aware-RAG](https://github.com/Yoshiki0705/FSx-for-ONTAP-Agentic-Access-Aware-RAG) | Permission-aware RAG のディスカバリ層として活用 | Bedrock KB + S3 AP が UC External Location と連携する可能性 |
| [ontap-edge-to-cloud-ai](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai) | エッジデバイスデータの AWS Context 自動カタログ登録 | エッジデータの Databricks 側ガバナンス |
| [fsxn-observability-integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations) | 監査ログをナレッジグラフで相関分析 | — |

---

## 参考リンク

- [AWS: Context intelligence for your data and AI agents at scale](https://aws.amazon.com/blogs/machine-learning/context-intelligence-for-your-data-and-ai-agents-at-scale/) (2026-06-17)
- [About Amazon: New AI agent innovations (Summit NYC)](https://www.aboutamazon.com/news/aws/aws-summit-nyc-2026-ai-agents) (2026-06-17)
- [TechTarget: AWS latest to introduce context layer for agentic AI](https://www.techtarget.com/searchdatamanagement/news/366644853/AWS-latest-to-introduce-context-layer-for-agentic-AI) (2026-06-17)
- [Techstrong.ai: AWS Adds Context Service and Harness to AI Portfolio](https://techstrong.ai/articles/aws-adds-context-service-and-harness-to-ai-portfolio/) (2026-06-17)
- [Databricks: What's new with Unity Catalog at DAIS 2026](https://www.databricks.com/blog/whats-new-unity-catalog-data-ai-summit-2026) (2026-06-16)
- [Databricks: AI Governance — Unity AI Gateway](https://www.databricks.com/blog/ai-governance-data-ai-summit-2026-whats-new-unity-ai-gateway) (2026-06-16)
