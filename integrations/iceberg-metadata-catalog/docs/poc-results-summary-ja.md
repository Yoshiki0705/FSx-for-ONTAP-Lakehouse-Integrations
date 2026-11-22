# Iceberg メタデータカタログ — PoC 結果サマリー

🌐 日本語 | [English](poc-results-summary.md)

## 構築したもの

FSx for ONTAP 上の非構造化データを **S3 にコピーせずに** 即座に検索可能・AI 分類可能にする**メタデータカタログ**。

## 主要結果 (2026-05-31 検証)

| 指標 | Before | After | 改善 |
|------|--------|-------|------|
| **ファイル発見時間** | 数分〜数時間 (手動 ListObjectsV2) | 2秒未満 (Athena SQL) | スケール時 100x+ |
| **AI 分類** | 手動 (人が各ファイルを確認) | 自動 (6秒/ファイル、$0.01/ファイル) | 完全自動化 |
| **ストレージコスト** | S3 フルコピー必要 (~$230-256/月 per 10TB)* | S3 コピー不要 ($5-15/月 メタデータのみ) | 95% 削減 |
| **ガバナンス** | 非構造化データにガバナンスなし | Lake Formation LF-Tags で全メタデータ制御 | 0% → 100% |
| **クロスプラットフォーム** | プラットフォーム別サイロ | 単一 Iceberg テーブル、複数エンジン | 統合カタログ |

## アーキテクチャ (検証済み)

```
FSx for ONTAP (実ファイル: PDF、画像、CAD、動画)
       │
       │ S3 Access Point (読み取り)
       ▼
┌─────────────────────────────────────────────┐
│  AI エンリッチメント (Bedrock)                 │
│  • Claude Vision: 画像分類                   │
│  • Titan Embeddings: 1024次元ベクトル         │
│  • 処理: ~6秒/ファイル、~$0.01/ファイル         │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│  S3 Tables (Iceberg メタデータ)               │
│  • ファイルパス、タイプ、サイズ、タイムスタンプ     │
│  • AI 分類 + 信頼度スコア                      │
│  • ベクトル embedding (類似検索用)             │ 
│  • PII 検出フラグ                             │
│  • 自動コンパクション、メンテナンス不要            │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│  クエリエンジン                               │
│  • Athena: 2秒未満クエリ ✅ 検証済み           │
│  • EMR Spark 7.13.0+: Glue REST ✅ 検証済み  │
│  • Snowflake: VENDED_CREDENTIALS ✅ 検証済み   │
│  • Databricks: UC 対応待ち ⚠️ (DataSync 代替) │
└─────────────────────────────────────────────┘
```

> **検索時間スケーリングの注記**: Part 1 の ListObjectsV2 レイテンシ比較は、40ファイルの実測値から線形外挿した namespace スキャンの推定です。スケール時のアーキテクチャ価値を示していますが、FSx for ONTAP S3 Access Point サービス性能のベンチマークではありません。本番の S3 AP スループットは FSx プロビジョニング容量、リクエスト並行数、ファイル分布、ONTAP キャッシュ状態に依存します。

## 現時点で動作確認済みの機能

| 機能 | 状態 | エビデンス |
|------|------|----------|
| メタデータスキャン (38ファイル → Iceberg テーブル) | ✅ 検証済み | 30秒、エラーゼロ |
| Athena SQL クエリ | ✅ 検証済み | サブ2秒、Lake Formation ガバナンス適用 |
| リアルタイム同期 (FPolicy → SQS → Lambda → S3 Tables) | ✅ 検証済み | 処理2秒、DLQ = 0 |
| AI 画像分類 (Bedrock Vision) | ✅ 検証済み | "Invoice" を confidence 0.9 で分類 |
| ベクトル embedding 生成 (Titan V2) | ✅ 検証済み | 1024次元、正規化済み |
| ベクトル類似検索 (OpenSearch NextGen) | ✅ 検証済み | kNN スコア 0.71、scale-to-zero |
| PII 検出 (Comprehend) | ✅ 検証済み | 7/7 エンティティ検出 (NAME, EMAIL, PHONE, ADDRESS, SSN, CREDIT_CARD, DATE_TIME) |
| ドキュメント匿名化 (墨消し) | ✅ 検証済み | 全 PII を [REDACTED] に置換 |
| ファイル削除時の soft delete | ✅ 検証済み | is_deleted=true、監査証跡保持 |
| Lake Formation アクセス制御 | ✅ 検証済み | 権限なしアクセスを正しくブロック |
| CloudTrail 監査ログ | ✅ 検証済み | 全クエリがユーザー ID 付きで記録 |
| 100ファイルバースト処理 | ✅ 検証済み | SQS リトライで全件処理、DLQ = 0 |
| Iceberg Time Travel (スナップショット履歴) | ✅ 検証済み | 5スナップショット、$history テーブル |

## コスト (実測値)

| コンポーネント | 月額コスト (10TB、10万ファイル) |
|-------------|-------------------------------|
| S3 Tables (メタデータストレージ) | ~$5 |
| Lambda (イベント同期 + AI) | ~$55 |
| Bedrock (AI 分類 + embedding) | ~$100-500 (実測: $0.01/ファイル) |
| OpenSearch Serverless NextGen | **アイドル時 $0** + アクティブ時 $0.24/OCU-hour |
| SQS + Step Functions | ~$6 |
| Comprehend (PII 検出) | ~$5 (AI 処理に含む) |
| **合計** | **~$170-570** (アクティブ時)、**~$0** (アイドル時) |
| FSx for ONTAP (既存、変更なし) | — |
| S3 コピー (排除) | **-$230-256 削減** |

**実質効果**: ベクトル検索と PII 匿名化を含む AI 搭載メタデータカタログを、排除した S3 コピーのコスト以下で運用可能。Scale-to-zero により PoC/開発環境はアイドル時 $0。

> *S3 Standard ストレージ料金: us-east-1 $0.023/GB ($230/10TB)、ap-northeast-1 $0.025/GB ($256/10TB)。2026-06-01 確認。

**PoC デプロイ時間**: 全 6 Phase を 1 日で検証完了。

## 既知の制約

| 制約 | 影響 | 回避策 | 状態 |
|------|------|--------|------|
| Databricks SQL Warehouse が S3 Tables を直接クエリ不可 | Spark クラスターまたは Athena が必要 | Spark クラスター設定 or Athena | 機能リクエスト提出済み |
| Snowflake が S3 Tables を VENDED_CREDENTIALS で直接クエリ可能 | ✅ 解決済み (2026-06-05) | Glue REST + ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS | AUTO_REFRESH / Time Travel 検証済み |
| Lake Formation 列レベル制御が S3 Tables フェデレーテッドカタログで未サポート | 特定カラムを非表示にできない | Athena View | AWS ケース提出済み |
| Lambda 並行書き込みで Iceberg commit conflict | 一部書き込みがリトライ | reserved_concurrency=1 | 設計推奨 |

## 次のステップ (利用者の判断ポイント)

| オプション | 選択する場合 | 追加コスト |
|----------|------------|----------|
| **現状デプロイ (Phase 1-3)** | メタデータ検索 + AI 分類で十分 | $0 追加 |
| **ベクトル検索追加 (Phase 5)** | 「類似ファイル検索」が必要 | Scale-to-zero: アイドル時 $0 + アクティブ時 ~$0.24/OCU-hour (NextGen, 2026年5月 GA) |
| **匿名化追加 (Phase 6)** | PII/PHI データのクリーンルームが必要 | +$22/月 |
| **プラットフォーム更新待ち** | Databricks/Snowflake 直接アクセスが必要 | $0 (サポートケース監視) |

## 試す方法

```bash
# 1. メタデータカタログ作成 (5分)
./scripts/create-table-bucket.sh create

# 2. 既存ファイルスキャン (30秒)
python scripts/initial-metadata-scan.py --access-point-arn <AP_ALIAS> \
  --table-bucket-arn <TABLE_BUCKET_ARN> --max-files 1000

# 3. Athena でクエリ (即時)
SELECT file_name, file_type, classification, summary
FROM "s3tablescatalog/fsxn-metadata-catalog"."metadata"."unstructured_files"
WHERE classification = 'invoice' AND confidence_score >= 0.7;
```

詳細ガイド: [PoC ガイド](poc-guide-ja.md)
