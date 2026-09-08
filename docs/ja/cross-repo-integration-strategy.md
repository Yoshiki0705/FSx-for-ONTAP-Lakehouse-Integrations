🌐 [English](../en/cross-repo-integration-strategy.md) | **日本語**

# クロスリポジトリ連携戦略: FSx for ONTAP エコシステム

> **ステータス**: 初版（2026-06-18）。DAIS 2026 + AWS Summit NYC 2026 後の全体像整理。
> **目的**: Yoshiki0705 配下の公開リポジトリ間の連携方針と、残アクション項目の紐付けを明確化する。

---

## リポジトリ全体像

```
Yoshiki0705 GitHub (公開リポジトリ)
│
├── fsxn-lakehouse-integrations (本リポジトリ)
│   ├── Lakehouse / Databricks 統合パターン
│   ├── 製造データプラットフォーム PoC
│   ├── Iceberg メタデータカタログ
│   └── DAIS 2026 / Summit NYC 分析
│
├── FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns
│   ├── 17 業種ユースケース
│   ├── FPolicy イベント駆動パイプライン
│   ├── 容量ガードレール
│   └── Property-based testing
│
├── FSx-for-ONTAP-Agentic-Access-Aware-RAG
│   ├── Permission-aware RAG (CDK)
│   ├── Bedrock KB + S3 AP
│   ├── AD 連携 ACL
│   └── Agentic アクセス制御
│
├── ontap-edge-to-cloud-ai
│   ├── エッジデバイスデータ集約
│   ├── ONTAP → AWS AI/Analytics
│   └── S3 AP 経由の組織横断活用
│
└── fsxn-observability-integrations
    ├── EC2-free 監査ログ転送
    ├── Datadog / Splunk / Grafana 等
    └── S3 AP + Lambda パターン
```

---

## 連携マトリクス: 残 P1/P2 アクション × リポジトリ

| アクション | 主担当リポジトリ | 連携リポジトリ | 内容 |
|-----------|----------------|--------------|------|
| **P1: S3 Vectors × Permission-aware RAG** | `FSx-for-ONTAP-Agentic-Access-Aware-RAG` | 本リポジトリ（参照） | ✅ **実装済み**。`docs/s3-vectors-sid-architecture-guide.md` + CDK スタック（`bin/demo-app.ts`）で S3 Vectors パスが既に構築済み。本リポジトリでは参照・比較情報として活用 |
| **P2: Bedrock Managed KB × Omnigent Polly** | 本リポジトリ | `FSx-for-ONTAP-Agentic-Access-Aware-RAG` | Managed KB の Agentic Retriever が Omnigent Polly と連携し、マルチステップリトリーバル + マルチエージェント品質パイプラインを構築 |
| **P2: FSx for ONTAP 公式 RAG チュートリアル** | `FSx-for-ONTAP-Agentic-Access-Aware-RAG` | 本リポジトリ（リンク） | AWS 公式ドキュメント `docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html` へのリンク追加 |
| **P2: LTAP (Kafka → Lakebase) パス統合** | `ontap-edge-to-cloud-ai` + 本リポジトリ | 双方向 | 🆕 **設計検討中**（2026-06-18 追加）。edge repo 側で Path D として追加済み。コネクタ仕様公開 + Lakehouse//RT GA が採用ゲート |

---

## 連携パターン詳細

### 1. S3 Vectors × Permission-aware RAG（実装済み）

**ステータス**: ✅ `FSx-for-ONTAP-Agentic-Access-Aware-RAG` リポジトリで実装完了

**実装成果物**:
- `docs/s3-vectors-sid-architecture-guide.md`（日英、アーキテクチャガイド）
- `bin/demo-app.ts`（CDK スタック、S3 Vectors パス含む）
- `stack-architecture-comparison.md`（OpenSearch Serverless vs S3 Vectors 比較）

**背景**: Amazon S3 Vectors が GA（2025-12 re:Invent）。専用ベクトル DB 比 90% コスト削減、20 億ベクトル/インデックス、ap-northeast-1 対応。

**連携設計**:

```
FSx for ONTAP (ドキュメント)
       │
       ▼ S3 Access Point
Bedrock Embedding Model
       │
       ▼
Amazon S3 Vectors
(ACL メタデータ付きベクトル格納)
       │
       ├── metadata: {owner, group, acl_hash, svm, volume, source_path}
       │
       ▼ メタデータフィルタ検索
Permission-aware Retrieval
       │
       ▼
Bedrock FM (回答生成)
```

**主担当**: `FSx-for-ONTAP-Agentic-Access-Aware-RAG` — 既存の OpenSearch Serverless パスに S3 Vectors 代替パスを追加

**本リポジトリでの扱い**: 製造データプラットフォームの「ベクトルストア選択」セクションで S3 Vectors を候補に追加し、コスト比較を記載

**OpenSearch Serverless vs S3 Vectors 選定基準**:

| 軸 | OpenSearch Serverless | S3 Vectors |
|----|----------------------|------------|
| フィルタリング | 複雑なメタデータフィルタ + ブール演算 | 基本メタデータフィルタ |
| コスト | OCU ベース（最低 2 OCU ≈ $700/月） | ストレージ + クエリ（従量課金） |
| スケール | 大規模（数十億ベクトル対応） | 20 億/インデックス（GA） |
| レイテンシ | 10-100ms | サブ 100ms |
| Bedrock KB 統合 | ネイティブ対応 | Managed KB で対応（要確認） |
| 適用シナリオ | 高度なフィルタ、ハイブリッド検索、k-NN + BM25 | コスト重視、シンプルな ACL フィルタ、大量ベクトル |

### 2. Bedrock Managed KB × Omnigent Polly

**背景**: Bedrock Managed Knowledge Base (GA 2026-06-17) は Agentic Retriever を含み、AgentCore Gateway と MCP 経由で統合。

**連携設計**:

```
Omnigent (マルチエージェントオーケストレーション)
       │
       ├── Polly (マルチエージェントコーディング)
       │
       ├── Quality Supervisor Agent
       │        │
       │        ▼
       │   Bedrock Managed KB (Agentic Retriever)
       │        │
       │        ├── S3 コネクタ → FSx for ONTAP S3 AP
       │        ├── Smart Parsing (PDF/Office/テーブル)
       │        └── マルチステップリトリーバル
       │
       └── AgentCore Gateway (MCP)
                │
                ├── Unity AI Gateway (Databricks ガバナンス)
                └── AWS Context (ディスカバリ)
```

**主担当**: 本リポジトリ（Omnigent 評価ドキュメント内）
**連携**: `FSx-for-ONTAP-Agentic-Access-Aware-RAG` の Bedrock KB パターンを Managed KB にアップグレード

### 3. FSx for ONTAP 公式 RAG チュートリアル

**AWS 公式チュートリアル**: [Build a RAG application using Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)

**repost.aws ガイド**: [Using FSx for ONTAP S3 Access Points as an Amazon Bedrock Data Source](https://repost.aws/articles/AReKa8-o8XRGeVW2Nicbg1_w)

**追加先**:
- `FSx-for-ONTAP-Agentic-Access-Aware-RAG` の README に公式リンク追加
- 本リポジトリの関連ドキュメントにも参照リンク追加

---

## エッジ → クラウド連携: ontap-edge-to-cloud-ai との接点

`ontap-edge-to-cloud-ai` リポジトリは、エッジデバイスデータを ONTAP に集約し、S3 AP 経由で AWS AI/Analytics に接続するパターンを提供。本リポジトリの製造データプラットフォームと以下で連携:

| 本リポジトリの機能 | ontap-edge-to-cloud-ai での対応 |
|-------------------|-------------------------------|
| Layer 1 エッジデータ取り込み | エッジデバイス → ONTAP 集約パターン |
| Kafka → ClickHouse ローカル | エッジ側のストリーミング設計 |
| S3 AP → Bedrock/Athena | 集約データの分析パス |
| AWS Context 自動カタログ | エッジデータの自動ディスカバリ |

### Databricks 連携パス一覧（edge-to-cloud-ai 側）

> 同期元: `ontap-edge-to-cloud-ai/docs/ja/databricks-integration.md` (2026-06-18 更新)

| パス | 経路 | レイテンシ | ステータス |
|------|------|-----------|-----------|
| A | Kafka → Structured Streaming → Delta | 秒〜分 | ✅ 検証済み |
| B | S3 AP → Auto Loader → Delta | 分 | ✅ 検証済み |
| C | ONTAP S3 → External Location → Unity Catalog | — | 設計済み |
| **D** | **Kafka → Lakebase (LTAP)** | **ミリ秒〜秒（想定）** | **🆕 設計検討中 (2026-06-18 追加)** |

> **Path A 改善（2026-06-18 追加、2026-06-20 更新）**: Lakeflow Real-Time Mode (Spark Declarative Pipelines) は **GA（2025-12）**。Path A の Structured Streaming レイテンシ（秒〜分）を ~5ms まで短縮可能。新パスではなく、トリガーモード変更による既存 Path A の改善。即適用可能。詳細は後述の[「Lakeflow 評価」](#lakeflow-評価-zerobus-ingest--real-time-modedais-2026--2026-06-18-同期)を参照。

### Path D: Kafka → Lakebase (LTAP) — 詳細

**同期ステータス**: 設計検討中（2026-06-18 追加）。`ontap-edge-to-cloud-ai` 側で `docs/ja/databricks-integration.md` セクション 2.5 および `.kiro/specs/edge-to-cloud-poc/design.md` セクション 4.5 に追加済み。

**データフロー**:

```
エッジ ONTAP
    │ Kafka Producer (v3 イベントスキーマ)
    ▼
Kafka (MSK / Confluent)
    │
    ├── Path A: Structured Streaming → Delta (既存)
    │
    └── Path D: Kafka → Lakebase (LTAP) [将来候補]
              │
              ├── Operational DB + 分析統合
              ├── リアルタイム品質判定 API
              └── Lakebase Search (vector + full-text)
```

**LTAP コンポーネント** (evidence tier: **Public**, DAIS 2026-06-16):

| コンポーネント | 役割 | ステータス |
|---|---|---|
| Lakebase | Postgres 互換 operational DB | GA |
| Lakehouse//RT | ミリ秒クエリ (Reyden エンジン) | Preview |
| Lakebase Search | ハイブリッド vector + full-text | Beta |

**既存パスとの関係**: Path D は Path A の**代替候補（並列オプション）であり、置き換えではない**。エッジ側（ローカル ONTAP + Kafka トピック設計）に変更なし。

**採用ゲート条件**:
1. Kafka → Lakebase コネクタのドキュメント公開
2. Lakehouse//RT GA 到達
3. 既存 Path A では満たせないレイテンシ / Operational AI 要件の顕在化

**関連ドキュメント**: 本リポジトリ内の LTAP 詳細分析は [14_realtime_analytics_landscape.md](../../integrations/manufacturing-data-platform/docs/ja/14_realtime_analytics_landscape.md) のセクション「LTAP (Lake Transactional/Analytical Processing)」を参照。

### Lakeflow 評価: Zerobus Ingest / Real-Time Mode（DAIS 2026 — 2026-06-18 同期）

> 同期元: `ontap-edge-to-cloud-ai/docs/ja/databricks-integration.md` セクション 2.6（2026-06-18 追加）。DAIS 2026 (2026-06-16) の Lakeflow 発表を、エッジ → クラウドのストリーミング設計の文脈で評価した結果を記録する。

DAIS 2026 で発表された Lakeflow 関連機能を、本エコシステムのストリーミング設計（Path A〜D）の文脈で評価した。いずれも**用途に応じて選択する追加オプション**として位置づけ、既存の Kafka イベントバス設計を置き換えるものではない。

| 機能 | ステータス | 本エコシステムでの位置づけ |
|------|-----------|--------------------------|
| Zerobus Ingest | GA | Databricks 専用取り込みの**追加オプション**。Kafka をバイパスして Delta に直接書き込むが、Kafka の代替ではない（下記「主要な設計判断」参照） |
| Real-Time Mode (Spark Declarative Pipelines) | ✅ GA (2025-12) | **Path A のレイテンシ改善パス**。Structured Streaming の秒〜分を ~5ms まで短縮し得る |
| Lakeflow Connect (100+ コネクタ) | GA（コネクタ依存） | マネージドコネクタ群。ONTAP/NFS 直接接続コネクタの有無は要確認 |
| Agentic Data Engineering | Preview | データ品質 × エージェントの接点。API 公開待ち |

#### 主要な設計判断

- **Kafka は汎用イベントバスとして継続**: 本エコシステムの Kafka は ClickHouse・Lambda・Databricks など複数コンシューマに配信している。Zerobus Ingest は Databricks 単一シンクへの取り込みインターフェースであり、複数コンシューマ配信を担う Kafka の代替にはならない。Zerobus は「Databricks 専用取り込みニーズが顕在化した場合の追加経路」として扱う。
- **Real-Time Mode は Path A の改善**: Real-Time Mode は新しいパスではなく、既存 Path A（Kafka → Structured Streaming → Delta）のトリガーモード変更によるレイテンシ改善。**GA 到達済み（2025-12）**。Path A のレイテンシ要件が顕在化した場合に即適用可能。Path D (Lakebase/LTAP) の一部ユースケース（ミリ秒レイテンシ）をカバーし得る。
- **エッジ側変更なし**: Kafka Producer 設計（v3 イベントスキーマ、トピック設計）はそのまま。影響範囲はクラウド側の受信・取り込みのみ。
- **オンプレ非対応**: Lakeflow は Databricks マネージド機能であり、オンプレ/エッジ展開のオプションはない。エッジ層のリアルタイム分析（ClickHouse 等）は引き続き必要。

#### パス関係の整理

```
Kafka (汎用イベントバス、複数コンシューマ)
 ├── Path A 現行 (Structured Streaming, 秒〜分) ✅ 検証済み
 │     └── Path A 改善 (Real-Time Mode, ~5ms) ✅ GA (即適用可能)
 ├── Path D 将来 (Lakebase/LTAP, ミリ秒〜秒) 🔄 設計検討中
 └── (その他コンシューマ: ClickHouse, Lambda)

Zerobus Ingest → Delta 直接 (Kafka バイパス、Databricks 専用) 🆕 評価対象 (GA)
```

#### 採用ゲート条件

| 機能 | ゲート条件 |
|------|-----------|
| Zerobus Ingest | エッジの Databricks 専用取り込みニーズが顕在化し、Kafka 多重配信が不要なユースケースが特定されること |
| Real-Time Mode | ~~GA 到達~~ ✅ GA 済み（2025-12）。既存 Path A では満たせないレイテンシ要件が顕在化した時点で即適用 |
| Lakeflow Connect | ONTAP/NFS 直接接続コネクタの公開 |
| Agentic Data Engineering | API 公開 + データ品質ワークフローへの適用ユースケース特定 |

> **選び方（用途に応じた整理）**: 複数コンシューマへの汎用配信が必要なら Kafka イベントバス、Databricks 単一シンクへの低運用な取り込みなら Zerobus Ingest、既存 Path A のレイテンシ短縮なら Real-Time Mode、というように要件に応じて選択する。いずれも排他ではなく併用可能。

> 本エコシステム内の Lakeflow/Zerobus に関する DAIS 2026 ノートは [14_realtime_analytics_landscape.md](../../integrations/manufacturing-data-platform/docs/ja/14_realtime_analytics_landscape.md) の「DAIS 2026 追加情報」も参照。Lakehouse//RT（クエリエンジン）と Real-Time Mode（Structured Streaming のレイテンシ改善）は別機能である点に注意。

### クロスリポジトリ検証項目（LTAP パス）

| 検証項目 | 検証内容 | 担当 | ステータス |
|---------|---------|------|-----------|
| Kafka → Lakebase コネクタ | コネクタ仕様、設定方法、Kafka topic → table マッピング | edge repo + 本リポジトリ | 🔲 仕様未公開 |
| 順序保証 | Kafka **パーティション内**の順序が Lakebase 書き込みで維持されるか（パーティション間順序は Kafka 設計上未保証のため対象外） | edge repo | 🔲 未検証 |
| 障害時挙動 | Lakebase 書き込み失敗時の Kafka offset 管理、リトライ、DLQ。将来設計: DLQ メッセージのリプレイ手順（タイミング・トリガー・再投入方法）も検討対象 | edge repo | 🔲 未検証 |
| スキーマ互換性 | v3 イベントスキーマ（JSON）→ Lakebase テーブルスキーマへのマッピング | 両リポジトリ | 🔲 設計待ち |
| write → query レイテンシ | Lakebase 書き込み後のクエリ可能時間（Lakehouse//RT 経由含む） | 本リポジトリ | 🔲 Lakehouse//RT Preview 検証後 |
| ACL 連携 | Lakebase テーブルに FSx for ONTAP 由来の ACL メタデータを保持可能か | 本リポジトリ | 🔲 設計待ち |
| Lakebase ap-northeast-1 可用性 | Lakebase GA がリージョン限定でないことの確認。ap-northeast-1 で利用可能か | 本リポジトリ | ⚠️ **非対応確認済み** (2026-06-18) |
| Lakebase Private Link 接続 | VPC 内からの Lakebase アクセスに Private Link (port 5432) が利用可能か（DAIS 2026 で GA 発表済み）。注: Lakebase 自体が ap-northeast-1 で非対応のため、Lakebase リージョン拡大まで保留 | 本リポジトリ | ⚠️ Lakebase リージョン制約によりブロック |
| Zerobus Ingest 代替パス | Kafka 以外に Zerobus Ingest (Private Link 対応) からの直接 Lakebase 書き込みが可能か。前提: 外部ソース（MSK/Kafka Producer）から Zerobus Ingest endpoint への Push が可能かを先に確認 | edge repo | 🔲 仕様確認待ち |
| Real-Time Mode GA 評価 | Real-Time Mode (Spark Declarative Pipelines) **GA 到達済み（2025-12）**。Path A のレイテンシ改善（秒〜分 → ~5ms）を評価可能。トリガーモード変更だけで既存 Path A に適用可能か、また Path D (Lakebase/LTAP) の一部ユースケースをカバーし得るかを検証 | edge repo + 本リポジトリ | 🔄 GA 確認済み・実環境検証待ち |
| Zerobus Ingest SDK 検証 (gRPC/Python) | Zerobus Ingest SDK (gRPC / Python) による Delta 直接書き込みの検証。外部ソースからの Push 方式、スループット、Private Link 経路、スキーマ定義方法を確認 | edge repo | 🔲 SDK 検証待ち |

> ⚠️ **Validation Required**: Kafka → Lakebase の直接書き込みパスはコネクタ仕様が未公開であり、上記検証項目すべてが確認されるまで PoC 採用判断を行わないこと。

> ⚠️ **リージョン制約確認済み (2026-06-18)**: Lakebase Autoscaling は **ap-northeast-1 (Tokyo) で利用不可**（[公式ドキュメント](https://docs.databricks.com/en/resources/feature-region-support.html)）。APAC で利用可能なリージョンは ap-south-1 (Mumbai), ap-southeast-1 (Singapore), ap-southeast-2 (Sydney)。Path D を ap-northeast-1 ベースのアーキテクチャで検証する場合、以下の選択肢がある:
> 1. **Lakebase 対応リージョンで検証** — us-east-1 or ap-southeast-1 等で PoC 実行
> 2. **ap-northeast-1 対応待ち** — Databricks のリージョン拡大を待つ
> 3. **Path D を低優先化** — 既存 Path A (Structured Streaming → Delta) を継続
>
> Zerobus Ingest は ap-northeast-1 対応済みであり、Lakebase 未対応は Zerobus → Lakebase パスに影響する。Zerobus → Delta (Structured Streaming) パスは ap-northeast-1 で利用可能。

**今後の連携**: LTAP (Kafka → Lakebase) パスの検証を `ontap-edge-to-cloud-ai` のエッジ → クラウドフローと統合して設計。Lakehouse//RT GA 時に再評価。

---

## 可観測性連携: fsxn-observability-integrations との接点

`fsxn-observability-integrations` は S3 AP + Lambda で監査ログを外部 SIEM に転送するパターン。本リポジトリのエージェントセキュリティ設計と以下で連携:

| 本リポジトリの要件 | fsxn-observability-integrations での対応 |
|-------------------|----------------------------------------|
| FPolicy 監査ログ × エージェントアクセス突合 | ⚠️ **要再設計**: [`docs/ja/agent-fpolicy-correlation-pattern.md`](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/docs/ja/agent-fpolicy-correlation-pattern.md) (PR #22)。エージェントが S3 Access Point 経由でデータに到達する場合、FPolicy に通知が来ないため突合が成立しません（実測 2026-08-26）。入力を ONTAP ネイティブ監査ログに置き換える必要があります |
| Omnigent ツール呼び出しログ | OpenTelemetry → CloudWatch 連携 |
| Unity Catalog 監査 × ONTAP 監査の突合 | 両監査ログの時間軸結合クエリ |

---

## アクション優先度（更新版）

**ステータス凡例**: ✅ 完了（実装/設計済み） / 🔄 進行中（設計検討中） / 🔲 未着手（外部依存待ち）

| 優先度 | アクション | 主担当 | 状態 | 前提条件 |
|--------|-----------|--------|------|---------|
| **P1** | S3 Vectors 設計パターン追加 | Agentic-RAG repo | ✅ 実装済み | `docs/s3-vectors-sid-architecture-guide.md` + CDK スタック |
| **P2** | Managed KB × Omnigent 連携設計 | 本リポジトリ | ✅ 設計完了 | `omnigent-multi-agent-evaluation.md` セクション 4 に追加 |
| **P2** | 公式 RAG チュートリアルリンク | Agentic-RAG repo + 本リポジトリ | ✅ 両リポジトリ完了 | Agentic-RAG repo README に「AWS 公式リソース」セクション追加済み |
| **P2** | ontap-edge-to-cloud-ai との LTAP 統合設計 | 本リポジトリ + edge repo | 🔄 設計検討中 | edge repo 側 Path D 追加済み（2026-06-18）。Lakebase GA / コネクタ仕様公開待ち |
| **P2** | Lakeflow Real-Time Mode / Zerobus Ingest 評価 | 本リポジトリ + edge repo | 🔄 Real-Time Mode GA 確認済み・実環境検証待ち | Real-Time Mode GA（2025-12）。edge repo 側で反映済み。次ゲート: 実環境レイテンシ検証 / Zerobus Ingest SDK 検証 (gRPC/Python) |
| **P3** | AWS Context GA 後の FSx for ONTAP 自動カタログ検証 | 本リポジトリ | 🔲 | AWS Context GA 待ち |
| **P3** | 監査ログ統合クエリパターン | observability repo | ✅ 設計完了（PR #22） | 実装はエージェント基盤構築後 |

---

## 参考

- [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)
- [FSx-for-ONTAP-Agentic-Access-Aware-RAG](https://github.com/Yoshiki0705/FSx-for-ONTAP-Agentic-Access-Aware-RAG)
- [ontap-edge-to-cloud-ai](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai)
- [fsxn-observability-integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations)
- [AWS: Build a RAG application with Bedrock KB + FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)
- [repost.aws: FSx for ONTAP S3 AP as Bedrock Data Source](https://repost.aws/articles/AReKa8-o8XRGeVW2Nicbg1_w)
- [Amazon S3 Vectors GA](https://aws.amazon.com/blogs/aws/amazon-s3-vectors-now-generally-available-with-increased-scale-and-performance/)
- [Amazon Bedrock Managed Knowledge Base](https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-bedrock-managed-knowledge-base/)
- 本リポジトリ関連分析: [S3 Annotations ガバナンス評価](./s3-annotations-governance-evaluation.md)（Databricks UC × FSx for ONTAP S3 AP 課題への S3 Annotations/Metadata 適用評価、2026-06-18）
