🌐 [English](./README.md) | **日本語**

# FSx for ONTAP Lakehouse Integrations

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Yoshiki0705/fsxn-lakehouse-integrations/badge)](https://scorecard.dev/viewer/?uri=github.com/Yoshiki0705/fsxn-lakehouse-integrations)
[![gitleaks](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/actions/workflows/gitleaks.yml/badge.svg)](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/actions/workflows/gitleaks.yml)

> エンタープライズファイルデータ（NFS/SMB）を **FSx for ONTAP S3 Access Points** 経由で各種分析・Lakehouse エンジンからクエリする検証フレームワーク。データ移動不要。データエンジニア、ソリューションアーキテクト、実装パートナー向け。

---

## 目的別の出発点

| やりたいこと | ガイド | 所要時間 |
|---|---|:---:|
| 何のための構成かを専門用語なしで把握する | [ビジネスガイド](docs/ja/quickstart-business-guide.md) | 5分 |
| ユースケースに合うエンジンを選ぶ | [エンジン選定ガイド](docs/ja/engine-selection-guide.md) | 10分 |
| アーキテクチャの選択肢とトレードオフを比較する | [アーキテクチャ比較](docs/adoption-guide/architecture-comparison-ja.md) | 15分 |
| S3 AP のディレクトリ設計・性能特性を理解する | [S3 AP 設計考慮事項](docs/ja/s3ap-design-considerations.md) | 15分 |
| PoC をエンドツーエンドで実行する | [PoC 実行ガイド](docs/implementation-guide/poc-execution-guide-ja.md) | 15分 |
| ベースインフラをデプロイする | [デプロイガイド](docs/ja/deployment-guide.md) | 30分 |
| FlexCache / SnapMirror でマルチリージョン配信する | [FlexCache/SnapMirror 考慮事項](docs/ja/s3ap-flexcache-snapmirror-considerations.md) | 15分 |
| FSx for ONTAP → Databricks Unity Catalog を接続する | [UC 接続ガイド](docs/ja/fsx-ontap-to-databricks-unity-catalog-guide.md) | 30分 |
| 非構造化データ（画像/動画/文書）をレイクハウスでガバナンスする | [Databricks FILE 型評価](docs/ja/databricks-file-type-evaluation.md) | 20分 |
| Databricks 検証の実費を事前に見積もる | [Databricks 検証環境とコスト](docs/ja/databricks-verification-environment-cost.md) | 10分 |
| Unity Catalog × S3 Access Point の結果を自分のアカウントで再現する | [Databricks 検証ランブック](docs/ja/databricks-verification-runbook.md) | 実作業 45分 |

<details>
<summary>📂 全インテグレーション・検証ステータス</summary>

| プラットフォーム | ステータス | パターン | 主な発見 |
|---|:---:|---|---|
| [Athena](integrations/athena/) | ✅ 検証済み | Glue Catalog + Serverless | 54.8 MB/s、5M 行 2 秒 |
| [Glue ETL](integrations/glue/) | ✅ 検証済み | Crawler + Medallion | 読み取り + 書き戻し (Parquet) |
| [EMR Spark](integrations/emr-spark/) | ✅ 検証済み | Spark SQL + Iceberg | 読み取り + 書き戻し、10K 行 16 秒 |
| [Redshift Spectrum](integrations/redshift-spectrum/) | ✅ 検証済み | External Schema + Lake Formation | 5M 行 4.3 秒 |
| [DuckDB Lambda](integrations/duckdb/) | ✅ 検証済み | サーバーレス軽量 | 5M 行 779ms、~$0.00001/クエリ |
| [Snowflake](integrations/snowflake/) | ✅ 検証済み | External Stage (`AWS_ACCESS_POINT_ARN`) | SELECT + External Table |
| [Delta Lake OSS](integrations/delta-lake-oss/) | ⚠️ 読み取りのみ | delta-rs + Spark | 書き込みは 501（条件付き書き込み非対応） |
| [Databricks](integrations/databricks/) | ⚠️ ブロック中 | Unity Catalog + Delta Lake | セッションポリシーが S3 AP ARN を認識しない |
| [Iceberg メタデータカタログ](integrations/iceberg-metadata-catalog/) | ✅ AWS ネイティブ | S3 Tables + PyIceberg + Bedrock | AI カタログ; クロスプラットフォーム進行中 |
| [製造データプラットフォーム](integrations/manufacturing-data-platform/) | 🔧 PoC | Kafka + ClickHouse + Databricks | エッジ→クラウドストリーミング |
| Dremio / Trino / BigQuery / Fabric | 🔲 計画中 | — | — |

**主要な知見**: AWS ネイティブサービスはそのまま動作。サードパーティは明示的な S3 AP ARN 設定が必要。詳細は [互換性マトリクス](docs/ja/compatibility-matrix.md) を参照。

</details>

---

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│  分析エンジン (Athena / EMR / DuckDB / Snowflake / ...)           │
└────────────────────────────┬────────────────────────────────────┘
                             │ S3 API
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              S3 Access Point  (IAM + AP ポリシー)                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  FSx for ONTAP Volume                                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────────┐  │
│  │ NFS/SMB  │ │ Snapshot │ │FlexClone │ │ Dedup/Compression  │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

既存の NFS/SMB アプリケーションは変更不要。S3 Access Points が分析向けの読み取り（および限定的な書き込み）パスを追加 — データコピーなし、同期パイプラインなし。

アーキテクチャ詳細: [docs/ja/architecture.md](docs/ja/architecture.md)

<details>
<summary>⚠️ 制約・既知の制限事項</summary>

| 制約 | 影響 | 回避策 |
|---|---|---|
| 条件付き書き込み非対応 (If-None-Match) | Delta/Iceberg/Hudi が直接書き込み不可 | FSx for ONTAP から読み取り、S3 に書き込み |
| Databricks セッションポリシーが S3 AP ARN を拒否 | Unity Catalog External Location がブロック | DataSync → S3、または OpenSharing（分析中） |
| 同一リージョン要件 | 分析エンジンと FSx for ONTAP を同一リージョンに配置 | [リージョン設計ガイド](docs/ja/region-design-guide.md) |
| ONTAP S3 object-store-server と S3 AP の競合 | 同一 SVM に共存不可 | 別 SVM を使用 |
| AD 参加済み SVM の S3 AP は DC 接続が必須 | AD 不通時にデータ操作が失敗 | [AD 統合メモ](docs/en/fsx-ontap-s3ap-networking.md) |
| アクセスポイントは全リクエストを**1 つの ID** で認可 | 元の per-file ACL が、AP 経由で読む分析 / RAG パイプラインに引き継がれない | 絞り込みはストレージ層ではなくインデックス側で設計 — [Adoption Playbook: データ活用ハブ](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/ja/domains/data-utilization) |

</details>

<details>
<summary>📚 関連記事・リポジトリ</summary>

**ブログシリーズ**（7 パートの検証 Deep Dive）:

| パート | トピック | 日本語 | English |
|:---:|---|---|---|
| 0 | シリーズ概要 | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-lakehouse-part0-overview) | [dev.to](https://dev.to/aws-builders/fsx-for-ontap-s3-access-points-x-lakehouse-what-works-what-doesnt-and-why-1jo3) |
| 1 | Athena | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-lakehouse-part1-athena) | [dev.to](https://dev.to/aws-builders/query-nas-data-in-place-with-athena-and-fsx-for-ontap-s3-access-points-3lhh) |
| 2 | Databricks | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-lakehouse-part2-databricks) | [dev.to](https://dev.to/aws-builders/databricks-and-fsx-for-ontap-s3-access-points-a-layer-by-layer-validation-of-observed-boundaries-p4d) |
| 3 | Snowflake | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-lakehouse-part3-snowflake) | [dev.to](https://dev.to/aws-builders/snowflake-and-fsx-for-ontap-s3-access-points-from-access-denied-to-working-external-tables-9k8) |
| 4 | DuckDB Lambda | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-lakehouse-part4-duckdb) | [dev.to](https://dev.to/aws-builders/serverless-analytics-on-nas-data-for-000001query-duckdb-lambda-x-fsx-for-ontap-2o5o) |
| 5 | EMR Spark | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-lakehouse-part5-emr-spark) | [dev.to](https://dev.to/aws-builders/read-write-etl-on-nas-data-with-emr-serverless-spark-no-cluster-no-copy-hgm) |
| 6 | Redshift + Lake Formation | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-lakehouse-part6-redshift-lakeformation) | [dev.to](https://dev.to/aws-builders/redshift-spectrum-lake-formation-enterprise-governance-on-nas-data-2pik) |
| 7 | テーブルフォーマット制約 | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-lakehouse-part7-table-format) | [dev.to](https://dev.to/aws-builders/why-delta-iceberg-and-hudi-cant-write-to-fsx-s3-access-points-and-what-works-instead-5be3) |
| 8 | OpenSharing | [はてなブログ](https://hakobiya.hatenablog.com/entry/fsxn-lakehouse-part8-opensharing) | — |

**関連リポジトリ**:

| リポジトリ | 説明 |
|---|---|
| [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) | FSx for ONTAP S3 AP 向け 17 サーバーレスパターン |
| [ontap-edge-to-cloud-ai](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai) | エッジ (Raspberry Pi) → ONTAP → Kafka — [製造プラットフォーム](integrations/manufacturing-data-platform/)にフィード |
| [FSx-for-ONTAP-Adoption-Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook) | ライフサイクルとドメインで整理した導入設計ノート。データ活用ハブが、本リポジトリの統合の上流にあるアクセスポイントの制約とデータセット版管理の判断を扱う |

**ドキュメント索引**: [リーディングパスガイド](docs/ja/reading-path-guide.md) · [業界別ソリューションカタログ（26 業界）](docs/ja/industry-solution-catalog.md)

</details>

<details>
<summary>🔧 開発者向け</summary>

```bash
npm install && npm test                    # Lint + ユニットテスト
zizmor .github/workflows/                  # Actions セキュリティチェック
gitleaks detect --no-git --source .        # シークレットスキャン
```

- **スタック**: CloudFormation (YAML), Python 3.12, Bash, pytest, cfn-lint
- **セキュリティ**: 全 Actions を SHA ピン留め。Renovate で依存関係自動更新。[サプライチェーン詳細](.github/workflows/)
- **コントリビュート**: Issue・PR 歓迎。プッシュ前に `npm test` と `gitleaks` を実行してください。

</details>

<details>
<summary>🔀 S3 Access Points + SnapMirror / FlexCache — マルチリージョンデータ配信</summary>

S3 Access Points で収集したデータを SnapMirror（DR）や FlexCache（読み取り加速）で別リージョン/別クラウドに配信し、宛先で NFS/SMB/S3 API アクセスを実現する構成を検証済み。

**S3 Access Points と FlexCache / SnapMirror の互換性（動作検証済み）:**

| 構成 | サポート | 条件 |
|------|:--------:|------|
| S3 AP ボリュームを SnapMirror Async ソースに | ✅ 検証済み | ONTAP 9.12.1+ |
| S3 AP ボリュームを FlexCache Origin に | ✅ 検証済み | ONTAP 9.12.1+ |
| FlexCache Cache Volume に S3 AP アタッチ | ✅ (version-gated) | ONTAP 9.18.1+ |
| SnapMirror Synchronous | ❌ | S3 NAS bucket では非サポート |
| SVM-DR | ❌ | S3 NAS bucket を含む SVM では非サポート |

> FSx for ONTAP S3 Access Points は ONTAP の S3 NAS bucket メカニズムに基づいている。上記は [NetApp 公式ドキュメント](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html) で S3 NAS bucket として記載されている仕様に対し、FSx for ONTAP S3 Access Points で動作検証を実施した結果である。

**詳細ドキュメント**: [SnapMirror + FlexCache 調査・検証](integrations/snapmirror-flexcache-multicloud/) (12 デモガイド、検証スクリプト、41 調査結果)

</details>

---

## License

MIT — see [LICENSE](LICENSE).

---

🌐 [English](./README.md) | **日本語**
