# リージョン設計ガイド

[English](../en/region-design-guide.md)

## 概要

Amazon FSx for NetApp ONTAP（FSx for ONTAP）と Lakehouse プラットフォームを統合する際、
**リージョンの選定と整合性**は最も重要な設計判断の一つです。

本ガイドでは、このプロジェクトで採用した構成と、他のリージョンを利用するユーザー向けの
設計指針を提供します。

---

## このプロジェクトの構成

### 検証環境

| コンポーネント | リージョン | 詳細 |
|--------------|-----------|------|
| FSx for ONTAP | `ap-northeast-1` (東京) | ファイルシステム ID: `<YOUR_FSX_FILESYSTEM_ID>` |
| S3 Access Point | `ap-northeast-1` (東京) | FSx for ONTAP と同一リージョン（必須） |
| Databricks Workspace | `ap-northeast-1` (東京) | 同一リージョンで VPC-scoped AP を使用 |
| AWS Account | `<YOUR_AWS_ACCOUNT_ID>` | 検証用アカウント |

### 設計判断: 同一リージョン配置

```
┌─────────────────────────────────────────────────────────────┐
│                  ap-northeast-1 (東京)                        │
│                                                               │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────────┐  │
│  │ Databricks  │──▶│ S3 Access    │──▶│ FSx for ONTAP   │  │
│  │ Workspace   │   │ Point (VPC)  │   │ Volume          │  │
│  │             │   │              │   │                 │  │
│  │ (VPC内)     │   │ (VPC-scoped) │   │ (Private Subnet)│  │
│  └─────────────┘   └──────────────┘   └─────────────────┘  │
│                                                               │
│  ✅ 低レイテンシ（< 1ms）                                     │
│  ✅ データ転送コストなし（同一 AZ 内）                          │
│  ✅ VPC-scoped AP でネットワーク分離                           │
└─────────────────────────────────────────────────────────────┘
```

---

## リージョン選定の原則

### 原則 1: FSx for ONTAP と分析プラットフォームは同一リージョンに配置

```text
推奨: 同一リージョン
┌──────────────────────────────────┐
│  Region X                         │
│  FSx for ONTAP + S3 AP + Platform │
└──────────────────────────────────┘

非推奨: クロスリージョン
┌──────────────┐         ┌──────────────┐
│  Region A    │ ──────▶ │  Region B    │
│  FSx for ONTAP│  高レイテンシ │  Platform    │
└──────────────┘  転送コスト  └──────────────┘
```

理由:
- S3 Access Point はリージョナルリソース（FSx for ONTAP と同じリージョンに作成）
- VPC-scoped AP はリージョン内の VPC からのみアクセス可能
- クロスリージョンアクセスは 100-200ms のレイテンシ追加
- クロスリージョンデータ転送は $0.02/GB のコスト発生

### 原則 2: VPC-scoped AP を優先（可能な場合）

| プラットフォーム | VPC-scoped AP | Internet-origin AP |
|---------------|--------------|-------------------|
| Databricks | ✅ 推奨 | 可能（非推奨） |
| EMR / Spark | ✅ 推奨 | 可能 |
| Lambda | ✅ 推奨 | 可能 |
| Snowflake | 不可 | ✅ 必須 |
| Athena | 不可 | ✅ 必須 |
| Glue | 不可 | ✅ 必須 |
| Redshift Spectrum | 不可 | ✅ 必須 |

### 原則 3: データレジデンシー要件を最優先

規制要件がある場合、リージョン選定はコンプライアンスが最優先：

| 規制 | 対象リージョン | 備考 |
|------|-------------|------|
| GDPR | eu-west-1, eu-central-1 | EU 域内にデータ保持 |
| FISC | ap-northeast-1 | 日本の金融規制 |
| HIPAA | us-east-1, us-west-2 | BAA 対応リージョン |
| PDPA | ap-southeast-1 | シンガポール個人情報保護 |
| PIPL | cn-north-1, cn-northwest-1 | 中国データ規制 |

---

## リージョン別推奨構成

### アジアパシフィック (APAC)

| ユースケース | 推奨リージョン | 理由 |
|------------|-------------|------|
| 日本企業（FISC 対応） | `ap-northeast-1` | 規制対応 + 全サービス利用可能 |
| 韓国企業 | `ap-northeast-2` | 低レイテンシ + Databricks 対応 |
| 東南アジア | `ap-southeast-1` | シンガポールハブ + PDPA 対応 |
| オーストラリア | `ap-southeast-2` | データ主権 + 全サービス対応 |
| インド | `ap-south-1` | 低レイテンシ + コスト効率 |

### ヨーロッパ・中東・アフリカ (EMEA)

| ユースケース | 推奨リージョン | 理由 |
|------------|-------------|------|
| EU 企業（GDPR） | `eu-west-1` | アイルランド、最も広いサービス対応 |
| ドイツ企業 | `eu-central-1` | フランクフルト、GDPR + BaFin |
| 英国企業 | `eu-west-2` | ロンドン、UK GDPR |
| 北欧企業 | `eu-north-1` | ストックホルム |
| 中東企業 | `me-south-1` | バーレーン |

### アメリカ (AMERICAS)

| ユースケース | 推奨リージョン | 理由 |
|------------|-------------|------|
| 米国企業（汎用） | `us-east-1` | 最も広いサービス対応、最低コスト |
| 米国西海岸 | `us-west-2` | 低レイテンシ（西海岸ユーザー） |
| カナダ企業 | `ca-central-1` | カナダデータ主権 |
| ブラジル企業 | `sa-east-1` | LGPD 対応 |

---

## Databricks リージョン対応

### Databricks Workspace 作成可能リージョン

| リージョン | Unity Catalog | Delta Sharing | 備考 |
|-----------|--------------|---------------|------|
| us-east-1 | ✅ | ✅ | 米国プライマリ |
| us-east-2 | ✅ | ✅ | |
| us-west-2 | ✅ | ✅ | |
| ca-central-1 | ✅ | ✅ | |
| eu-west-1 | ✅ | ✅ | EU プライマリ |
| eu-west-2 | ✅ | ✅ | |
| eu-central-1 | ✅ | ✅ | |
| ap-northeast-1 | ✅ | ✅ | **このプロジェクトで使用** |
| ap-northeast-2 | ✅ | ✅ | |
| ap-southeast-1 | ✅ | ✅ | |
| ap-southeast-2 | ✅ | ✅ | |
| ap-south-1 | ✅ | ✅ | |
| sa-east-1 | ✅ | ✅ | |

### Databricks Workspace 作成手順

1. [Databricks Account Console](https://accounts.cloud.databricks.com/) にログイン
2. 「Workspaces」→「Create Workspace」を選択
3. Cloud で AWS を選択
4. Region は FSx for ONTAP と同じリージョンを選択
5. Pricing Tier は Premium 以上（Unity Catalog に必要）
6. VPC 設定は Customer-managed VPC を推奨（FSx for ONTAP と同じ VPC またはピアリング）

---

## マルチリージョン設計パターン

### パターン: SnapMirror + リージョナル Workspace

グローバル企業で複数リージョンにデータと分析基盤を配置する場合：

```
┌─────────────────────┐    SnapMirror     ┌─────────────────────┐
│  ap-northeast-1     │ ───────────────▶ │  eu-central-1       │
│                     │                   │                     │
│  FSx for ONTAP      │                   │  FSx for ONTAP      │
│  + S3 AP            │                   │  + S3 AP            │
│  + Databricks WS    │                   │  + Databricks WS    │
│  (APAC チーム)      │                   │  (EMEA チーム)      │
└─────────────────────┘                   └─────────────────────┘
         │                                          │
         │              SnapMirror                   │
         └──────────────────┬───────────────────────┘
                            ▼
                 ┌─────────────────────┐
                 │  us-east-1          │
                 │                     │
                 │  FSx for ONTAP      │
                 │  + S3 AP            │
                 │  + Databricks WS    │
                 │  (AMERICAS チーム)   │
                 └─────────────────────┘
```

**設計ポイント:**
- 各リージョンに独立した FSx for ONTAP + S3 AP + Databricks Workspace
- SnapMirror で必要なデータをリージョン間レプリケーション
- 各チームはローカルリージョンで低レイテンシアクセス
- グローバル集計は Delta Sharing で実現

---

## 設計チェックリスト

新しいリージョンでデプロイする際のチェックリスト：

- [ ] FSx for ONTAP が対象リージョンで利用可能か確認
- [ ] 分析プラットフォーム（Databricks/Snowflake 等）が同じリージョンで利用可能か確認
- [ ] データレジデンシー/コンプライアンス要件を確認
- [ ] VPC 設計: FSx for ONTAP と分析プラットフォームが同一 VPC またはピアリング可能か
- [ ] S3 AP ネットワークオリジン要件を確認（VPC vs Internet）
- [ ] CloudFormation テンプレートの `--region` パラメータを対象リージョンに設定
- [ ] Terraform の `aws_region` 変数を対象リージョンに設定
- [ ] SnapMirror が必要な場合、DR リージョンを選定

---

## 次のステップ

- [対応リージョン一覧](supported-regions.md) — 全リージョンの詳細対応状況
- [アーキテクチャ概要](architecture.md) — 全体構成
- [クイックスタート](getting-started.md) — 最初のデプロイ
