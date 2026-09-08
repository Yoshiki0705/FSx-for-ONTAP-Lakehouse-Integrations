# 製造データプラットフォーム PoC

🌐 [English](README.md) | **日本語**

---

> S3 アクセスポイントに依存せずに、エッジ/工場データを Databricks Unity Catalog と統合する
> 製造データプラットフォームのアーキテクチャ検証。

## アーキテクチャ

```
エッジ/工場 ──→ Kafka (MSK) ──→ ClickHouse (リアルタイムダッシュボード)
                    │                         
                    └──────→ Databricks (ガバナンス付き Delta テーブル on S3)
                                    
ペイロード (画像/動画/文書) ──→ ONTAP (オンプレオリジン)
                                  ↓ FlexCache
                               FSx for ONTAP (AWS キャッシュ、フルコピーなし)
```

**主要設計原則:**
- Databricks/Unity Catalog で S3 アクセスポイント非依存
- データ多重持ちなし — FlexCache がオンデマンドキャッシュを提供
- ペイロードの単一の真実のソース（オンプレミス ONTAP）
- リアルタイム + ガバナンス付き分析を補完レイヤーとして

## クイックスタート (Phase A — AWS)

> **現在のステータス (2026-06-15):** MSK Provisioned は ACTIVE。ClickHouse Cloud ClickPipes が
> Multi-VPC エンドポイントを "Incompatible" と表示 — ClickHouse へ照会し回答待ち。
> オンプレミス Instaclustr セットアップは並行進行中（VM ホスト準備完了、VM イメージ待ち）。

```bash
# 1. インフラデプロイ（既存 VPC + FSx for ONTAP を再利用）
cd poc/infrastructure
./deploy.sh deploy          # S3 + MSK を既存 VPC にデプロイ
./deploy.sh volumes         # 既存 FSx for ONTAP にボリューム作成

# 2. 合成データジェネレーター確認
cd ../synthetic-data-generator
pip install -r requirements.txt
python generate_events.py --dry-run

# 3. テスト実行
pytest tests/ -v
```

## ドキュメント

| ドキュメント | 目的 |
|------------|------|
| [プロジェクト概要](docs/ja/00_project_overview.md) | アーキテクチャ概要とスコープ |
| [要件定義](docs/ja/01_requirements.md) | 機能・非機能要件 |
| [技術調査結果](docs/ja/02_research_findings.md) | ソース付き技術検証 |
| [アーキテクチャ設計](docs/ja/03_architecture_design.md) | 詳細設計 (DES-001〜010) |
| [リスク](docs/ja/04_risks_and_considerations.md) | リスク登録簿 (RSK-001〜017) |
| [PoC 計画](docs/ja/05_poc_plan.md) | 受入基準付き実装計画 |
| [決定マトリクス](docs/ja/06_decision_matrix.md) | コンポーネント選定根拠 |
| [ADR](docs/adr/README.md) | 14件のアーキテクチャ決定記録 |
| [SLO](docs/ja/10_slo_operational_readiness.md) | サービスレベル目標とランブック |
| [パフォーマンス](docs/ja/11_performance_targets_business_metrics.md) | レイテンシ、スループット、ビジネスメトリクス |
| [セキュリティ](docs/ja/12_security_hardening.md) | 暗号化、シークレット、監査、拒否ポリシー |
| [エンゲージメント](docs/ja/13_customer_engagement_template.md) | パートナー/SI 再利用テンプレート |
| [Edge ↔ Lakehouse 同期](docs/ja/14_edge_lakehouse_sync.md) | プロジェクト間設計同期 |

## Phase A vs Phase B

| | Phase A (現在) | Phase B (目標) |
|-|--------------|--------------|
| Kafka | AWS MSK Provisioned | Instaclustr オンプレ |
| ClickHouse | ClickHouse Cloud | Instaclustr オンプレ |
| ONTAP | FSx for ONTAP (AWS) | オンプレ ONTAP (オリジン) + FlexCache (AWS) |
| Databricks | AWS | AWS (変更なし) |
| エッジ | 合成ジェネレーター | Raspberry Pi (ontap-edge-to-cloud-ai) |

## 関連プロジェクト

- [ontap-edge-to-cloud-ai](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai) — エッジデバイス (Raspberry Pi) 統合

## 機密性

全データは合成データ。実顧客名、工場名、デバイスデータは含まない。
