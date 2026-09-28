# PoC テンプレート — FSx for ONTAP S3 Access Points × Lakehouse

🌐 [English](README.md) | **日本語**

## 30分クイックスタート

基盤インフラをデプロイし、30分で最初のクエリを実行:

```bash
# 1. デプロイ (10分)
./scripts/deploy.sh --region ap-northeast-1

# 2. サンプルデータアップロード (2分)
./scripts/upload-sample-data.sh

# 3. 接続検証 (1分)
./scripts/validate.sh

# 4. 最初の Athena クエリ実行 (2分)
./02-athena-quickstart/run-first-query.sh
```

**結果**: Athena が S3 Access Point 経由で FSx for ONTAP データをクエリ — データコピーゼロ。

---

## エンジンを選択

| 顧客のプラットフォーム | モジュール | 最初のクエリまでの時間 | PoC コスト (1日) |
|---|---|---|---|
| AWS ネイティブ (Athena) | [02-athena-quickstart](02-athena-quickstart/) | 15分 | ~$0.05 |
| Snowflake | [03-snowflake-integration](03-snowflake-integration/) | 30分 | ~$5 |
| Databricks | [04-databricks-integration](04-databricks-integration/) | 1時間 | ~$10 |
| EMR Spark (ETL) | [05-emr-spark-etl](05-emr-spark-etl/) | 20分 | ~$0.50 |
| DuckDB Lambda (最安) | [06-duckdb-lambda](06-duckdb-lambda/) | 10分 | ~$0.01 |
| エンタープライズガバナンス | [07-governance](07-governance/) | 30分 | $0 (Lake Formation) |

---

## リポジトリ構造

```
poc-templates/
├── README.md                         # 本ファイル
├── 02-athena-quickstart/             # 最速の検証パス
│   ├── sample-queries.sql            # 検証クエリ
│   └── README.md                     # Athena クイックスタートガイド
├── 03-snowflake-integration/         # Snowflake External Table + Cortex AI
│   ├── 01-storage-integration.sql    # Storage Integration 設定
│   ├── 02-stage-and-table.sql        # Stage + External Table
│   ├── 03-cortex-ai-demo.sql         # Cortex AI 関数デモ
│   └── README.md                     # Snowflake セットアップガイド
├── 04-databricks-integration/        # DataSync → S3 → UC
│   ├── datasync-task.yaml            # DataSync CFn テンプレート
│   └── README.md                     # Databricks セットアップガイド（UC DDL は本文内）
├── 05-emr-spark-etl/                 # EMR Serverless 書き戻し
│   ├── spark-job.py                  # PySpark ETL スクリプト
│   └── README.md                     # EMR セットアップガイド
├── 06-duckdb-lambda/                 # 最安パス
│   ├── handler.py                    # Lambda ハンドラ
│   ├── template.yaml                 # Lambda CFn
│   └── README.md                     # DuckDB Lambda ガイド
├── 07-governance/                    # Lake Formation きめ細かな制御
│   ├── lakeformation-setup.sh        # LF 管理者 + grant
│   └── README.md                     # ガバナンスガイド
├── templates/                        # パートナー向けテンプレート
│   ├── poc-proposal.md               # 顧客向け PoC 提案書
│   ├── success-criteria.md           # Go/No-Go チェックリスト
│   ├── cost-estimate.md              # コスト計算
│   ├── discovery-questions.md        # 初回ミーティング質問集
│   ├── regulated-workload-checklist.md # ヘルスケア/金融チェックリスト
│   ├── post-poc-report.md            # 結果レポートテンプレート
│   └── ja/                           # 日本語版
├── sample-data/                      # サンプルデータセット
│   └── generate-sensor-data.py       # 1万行センサーデータ生成
└── scripts/
    ├── deploy.sh                     # ワンクリックデプロイ
    └── validate.sh                   # 接続性検証
```

各番号付きディレクトリには `README.md` と `README-ja.md` の両方があります。

**未収録。** 以前のリビジョンではこの README が以下を収録済みとして記載していました。
実際には追加されておらず、壊れた参照として残すのではなく上記ツリーから削除しました:

| 不在 | 代替 |
|---|---|
| `01-base-infrastructure/`（FSx + S3 AP + IAM の CFn） | [`shared/cloudformation/`](../shared/cloudformation/) |
| `02-athena-quickstart/create-glue-table.sql`, `run-first-query.sh` | DDL とクエリ手順は当該ディレクトリの README 本文内 |
| `03-snowflake-integration/04-dynamic-table.sql` | [`integrations/snowflake/sql/`](../integrations/snowflake/sql/) |
| `04-databricks-integration/uc-setup.sql`, `auto-loader-notebook.py` | いずれも当該ディレクトリの README 本文内 |
| `05-emr-spark-etl/emr-app.yaml` | [`integrations/`](../integrations/) の EMR テンプレート |
| `07-governance/column-level-demo.sql`, `row-filter-demo.sql` | 手順は `lakeformation-setup.sh` と README 内 |
| `sample-data/generate-documents.py` | 未実装 |
| `scripts/upload-sample-data.sh`, `cleanup.sh` | アップロード手順は各 README 内。クリーンアップは CFn スタックを削除 |

---

## 前提条件

- FSx for ONTAP (ONTAP 9.17.1+) を持つ AWS アカウント
- AWS CLI v2 設定済み
- Python 3.12+（サンプルデータ生成用）
- (オプション) Snowflake アカウント（モジュール 03 用）
- (オプション) Databricks ワークスペース（モジュール 04 用）

---

## PoC 成功基準

### 最小成功 (30分)
- [ ] S3 Access Point が `AVAILABLE`
- [ ] `ListObjectsV2` がサンプルデータファイルを返す
- [ ] Athena クエリが正しい結果を返す
- [ ] 同じファイルへの NFS/SMB アクセスが引き続き動作

### 運用成功 (1日)
- [ ] 選択したエンジンが FSx データを正常にクエリ
- [ ] IAM と S3 AP ポリシーが最小権限にスコープ
- [ ] クエリレイテンシとコストを測定
- [ ] クエリ中の FSx スループット影響を測定
- [ ] Go/No-Go 判断を文書化

### AI/ガバナンス成功 (2日)
- [ ] AI 関数が FSx データ上で動作（Cortex AI または Bedrock KB）
- [ ] ガバナンス制御を適用（Lake Formation または Snowflake Tags）
- [ ] データ共有をデモ（必要な場合）
- [ ] 規制ワークロードチェックリスト完了（該当する場合）

---

## コスト見積もり

| コンポーネント | 1日 PoC | 1週間 PoC | 備考 |
|------------|---------|---------|------|
| FSx for ONTAP (既存) | $0 | $0 | 既存ファイルシステムを使用 |
| S3 Access Point | $0 | $0 | 追加料金なし |
| Athena クエリ | ~$0.05 | ~$0.25 | $5/TB スキャン |
| EMR Serverless | ~$0.50 | ~$2.50 | ジョブ単位課金 |
| Snowflake (XS warehouse) | ~$5 | ~$25 | クレジットベース |
| Databricks (DataSync + compute) | ~$10 | ~$50 | 同期 + DBU |
| Lake Formation | $0 | $0 | 追加料金なし |
| **合計 (AWS ネイティブのみ)** | **~$0.55** | **~$2.75** | Athena + EMR |
| **合計 (Snowflake 含む)** | **~$5.55** | **~$27.75** | Snowflake クレジット追加 |

---

## パートナー向け

[templates/](templates/) に顧客向け資料があります:
- **初回ミーティング**: [discovery-questions.md](templates/discovery-questions.md)
- **提案書**: [poc-proposal.md](templates/poc-proposal.md)
- **コスト根拠**: [cost-estimate.md](templates/cost-estimate.md)
- **成功基準**: [success-criteria.md](templates/success-criteria.md)

---

## 関連ドキュメント

- **PoC ↔ ドキュメントマッピング**: [MAPPING-ja.md](MAPPING-ja.md) — 各モジュールと詳細ガイド・ブログ・検証エビデンスの対応表
- **ゼロコピー非構造化データガバナンス**: [docs/ja/zero-copy-media-governance.md](../docs/ja/zero-copy-media-governance.md) — S3 コスト削減 + マルチプラットフォームガバナンス + FlexCache S3 AP ロードマップ
- **互換性マトリクス**: [docs/ja/compatibility-matrix.md](../docs/ja/compatibility-matrix.md) — どのエンジンでどの操作が動作するか
- **運用監視**: [FSx-for-ONTAP-Observability-integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations) — 監査ログ連携（Datadog, Splunk, Grafana, Elastic 等）
- **規制ワークロード**: [regulated-workload-checklist.md](templates/regulated-workload-checklist.md)
- **最終レポート**: [post-poc-report.md](templates/post-poc-report.md)

---

## 関連

- [メイン README](../README.md) — プロジェクト概要と互換性マトリクス
- [ブログシリーズ](../README.md#get-started) — 詳細な検証記事 (Part 0-7)
- [検証パック](../verification-pack/) — 検証からのエビデンスレコード
