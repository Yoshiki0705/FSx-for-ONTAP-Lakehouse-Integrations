# 未検証項目インベントリ

🌐 [English](../en/unverified-inventory.md) | **日本語**

> 2026-08-06 時点。本リポジトリの主張のうち、実行記録に裏付けられて**いない**ものと、その阻害要因の一覧です。

抜けを数えられる状態にすることが目的です。[互換性マトリクス](./compatibility-matrix.md) で ⚠️ または 🔲 が付いた主張は、本ページに現れるはずです。現れていなければ、マトリクスが先行しており本ページが不正確ということになります。

動作**しない**ことが判明している事項は [ブロッカートラッカー](./blocker-tracker.md) が扱います。本ページの対象は「壊れているもの」ではなく「未知のもの」です。

**合計 24 件。** 2026-09-13 に 2 件を追加し同日クローズ（UNV-031・UNV-032、稼働中の SnapMirror 宛先のアクセスポイント提供）。2026-08-12 に 1 件クローズ（UNV-030、FILE 列の共有）。 2026-08-06 に 5 件をクローズしました（下記「直近でクローズした項目」参照）。

## サマリ

| 阻害要因 | 件数 | 内容 |
|---|:---:|---|
| 現在実行可能。未実施のみ | 12 | 本プロジェクトで既に使用している AWS サービスのみで完結します。次の現実的な候補です。 |
| Snowflake セッションが必要 | 1 | 認証情報は本リポジトリに保持していません。サインインすれば一度の作業で実行可能です。 |
| Databricks ワークスペースが必要 | 5 | 2026 年 5 月に使用したワークスペースは削除済みです。なお Unity Catalog 経路は BLK-001 により、いずれにせよブロックされます。 |
| 別エンジンのデプロイが必要 | 3 | ClickHouse インスタンスは稼働していません。 |
| アカウントティアまたはコストによる制約 | 1 | 有償ティアまたは課金リソースが必要です。 |
| 経過時間による制約 | 1 | 短縮できません。 |
| 検証不可 | 1 | 未リリースの要素に依存します。 |

## 現在実行可能。未実施のみ

本プロジェクトで既に使用している AWS サービスのみで完結します。次の現実的な候補です。

| ID | 対象 | 未検証の主張 | 必要なもの |
|---|---|---|---|
| Snowflake | Managed Iceberg Table への書き込み（AP 経由 Stage からの COPY INTO）エンドツーエンド | 検証済み — External Volume の全チェックが PASSED、テーブル作成、行のロードと読み出し、宛先バケットに真の Iceberg レイアウト | [2026-08-06](../../verification-pack/snowflake/evidence/2026-08-06/evidence-record.yaml) |
| Snowflake | Access Point データに対する Dynamic Table | 制約付きで検証済み — `TARGET_LAG='60 seconds'`・`REFRESH_MODE=FULL` は仕様どおり動作。ただし Dynamic Table は EXTERNAL TABLE を参照できないため、先に標準テーブルへ取り込む必要がある | [2026-08-06](../../verification-pack/snowflake/evidence/2026-08-06/evidence-record.yaml) |
| Snowflake | AP 経由 Stage に対する Snowpark `SnowflakeFile.open` | 検証済み — ファイル内容を取得 | [2026-08-06](../../verification-pack/snowflake/evidence/2026-08-06/evidence-record.yaml) |
| Snowflake | AP 経由 Stage からの JSON・Avro・ORC 読み取り | 検証済み — 3 形式すべて同一内容から同一の行を取得 | [2026-08-06](../../verification-pack/snowflake/evidence/2026-08-06/evidence-record.yaml) |
| Snowflake | Access Point へのアンロード（COPY INTO） | **動作せず。かつ従来の理由記載が誤りだった。** 書き込みは拒否されず、オブジェクトは正常な状態で書き込まれた後、FSx for ONTAP が暗号化を `aws:fsx` と報告するため checksum 検証で文が失敗する。完全なオブジェクトが残るため部分書き込みの危険がある | [2026-08-06](../../verification-pack/snowflake/evidence/2026-08-06/evidence-record.yaml) |
| UNV-012 | Databricks | No automated tests exist for the integration (`integrations/databricks/tests/` holds only `.gitkeep`) | Test authoring. Snowflake has 8 test files; Databricks has none. |
| UNV-016 | EMR Serverless | Iceberg write commit | An EMR Serverless run. Recorded as failing with a NullPointerException in S3FileIO; the failure is noted but no evidence record exists. |
| UNV-017 | AWS Glue ETL | Delta Lake write commit protocol | A Glue job run. Expected to fail for the same reason Delta fails elsewhere. |
| UNV-018 | AWS Glue ETL | Iceberg write with concurrent writers | Two simultaneous Glue jobs against one table. |
| UNV-019 | AWS Glue ETL / EMR Spark | Iceberg REST Catalog against S3 Tables | A job configured with the REST catalog. Inferred from the PyIceberg result. |
| UNV-020 | Redshift Spectrum | Glue federated catalog path to S3 Tables | A Redshift Serverless workgroup and a federated catalog. The plain Glue-table path over the AP is verified (2026-05-23). |
| UNV-021 | Athena | Iceberg at realistic table size — manifest growth, compaction cost, partition evolution | A larger dataset. The 2026-08-06 run used a single-digit row count. |
| UNV-022 | Athena | Concurrency above 25, and working sets larger than the ONTAP cache | A dataset well beyond cache size and a higher concurrency sweep. The 2026-08-06 run was cache-resident. |
| UNV-023 | Hudi | Any operation on an FSx for ONTAP S3 AP | A Hudi-capable engine. Listed under BLK-002 but never tested. |
| UNV-025 | FSx for ONTAP | ListObjectsV2 latency above 5,000 objects | A larger object population. The 2026-08-05 measurement covered 10 to 5,000 objects. |
| UNV-026 | Bedrock | Whether the Managed Knowledge Base S3 connector accepts an S3 AP URI (the traditional Knowledge Base path is verified) | A Managed Knowledge Base run. |
| UNV-027 | Tooling | PyIceberg wheel on macOS Apple Silicon | A run on that platform. A wheel exists; this project has not exercised it. |
| ~~UNV-031~~ | FSx for ONTAP | ~~レプリケーションを継続したまま SnapMirror 宛先を S3 アクセスポイントで提供できるか~~ | **2026-09-13 クローズ: 両経路とも成立。** ONTAP で DP 宛先を mount すると読み取り専用のアクセスポイントが得られ、後続転送が 15 秒で読めた（関係は `snapmirrored` のまま）。宛先 Snapshot のクローンは**書き込み可能**で、その Snapshot 時点に固定される。先に実測した FSx API の拒否は FSx コントロールプレーン限定の制約だった。[検証記録](../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13-in-vpc/evidence-record.yaml)、SM-VAL-013 |
| ~~UNV-032~~ | FSx for ONTAP | ~~SM-VAL-009 の約 30 分の反映が FlexClone に当てはまるか。「クローンして即クエリ」が分単位になるかを決める~~ | **2026-09-13 クローズ: 分単位ではないが 30 分より速い。** FSx がクローンを報告したのは **1011 秒**、ONTAP で mount した DP ボリュームは **2298 秒**。ONTAP 側の操作自体は数秒、アタッチは 32 秒。初回セットアップは反映待ちが支配して数十分、DP 経路の定常的な鮮度は数秒。1 ファイルシステム上の 2 サンプルであり校正された範囲ではない。[検証記録](../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13-in-vpc/evidence-record.yaml) |

## Snowflake セッションが必要

認証情報は本リポジトリに保持していません。サインインすれば一度の作業で実行可能です。

| ID | 対象 | 未検証の主張 | 必要なもの |
|---|---|---|---|
| UNV-004 | Snowflake | Horizon Catalog governance (row access policies, masking) enforced on external engines reading the Iceberg table | A Snowflake session and a second engine configured against the Horizon catalog. |

## Databricks ワークスペースが必要

2026 年 5 月に使用したワークスペースは削除済みです。なお Unity Catalog 経路は BLK-001 により、いずれにせよブロックされます。

| ID | 対象 | 未検証の主張 | 必要なもの |
|---|---|---|---|
| UNV-009 | Databricks | Iceberg REST Catalog from a Databricks Spark cluster (`spark.sql.catalog.s3tables`) | A Databricks workspace with a Spark cluster. Inferred from the EMR mechanism; no run. |
| UNV-010 | Databricks | Executor-scale boto3 access from a customer-managed VPC | A customer-managed-VPC workspace. The Databricks-managed VPC case is recorded as failing (egress to FSx blocked); the customer-VPC case is untested. |
| UNV-011 | Databricks | 16 of the 18 cases in `verification-pack/databricks/test-cases.yaml` have no recorded run | A workspace matching each case's preconditions. |
| UNV-028 | Databricks | `FILE MANAGED` の FileSpace に **External** Volume を使えるか | **2026-08-12 に部分クローズ。** `FILE MANAGED` / `FILE EXTERNAL` のテーブル作成は検証済み。**初回記述の訂正:** 「FileSpace は専用 Volume でなくてよい」と書いていたが、これは `CREATE TABLE` の成功だけを根拠にしたものだった。同日、実際に効く `INSERT` で再検証した結果、FileSpace をソースファイルのある Volume に向けると `Cannot get file metadata under managed storage` で失敗する。運用上は専用 Volume が必要である。External Volume 自体の可否は未検証。[証拠](../../verification-pack/databricks/file-type/evidence/2026-08-12/evidence-record-tokyo.yaml) |
| UNV-029 | Databricks | FSx for ONTAP S3 AP パスに対する `_object_metadata.tags`（DBR 18.2+）— オブジェクトタグの橋渡し | **2026-08-12 にネイティブ S3 のコントロール付きで実施。未解決だが 1 段進んだ。** コントロールは `tags` と `user_metadata` を返す。Access Point 経由では、タグ読み取りのコードに到達する前に拒否される。UC の down-scoped セッションポリシーがバケット形式 ARN を使う一方、AWS はアクセスポイント経由のリクエストをアクセスポイント ARN に対して認可評価するためである。元の問いへの回答は、こちらの環境ではなく Databricks 側の変更に依存する。ケース `DBX-FILE-041a…041e`。[証拠](../../verification-pack/databricks/file-type/evidence/2026-08-12/evidence-record-tokyo.yaml) |
| ~~UNV-030~~ | Databricks | ~~`FILE` 列を含むテーブルを OpenSharing で共有できるか~~ | **2026-08-12 クローズ: 可能。** `FILE EXTERNAL` / `FILE MANAGED` の両テーブルが共有に追加され `ENABLED` になった。受信側での読み取りは未検証。[証拠](../../verification-pack/databricks/file-type/evidence/2026-08-12/evidence-record.yaml) |

## 別エンジンのデプロイが必要

ClickHouse インスタンスは稼働していません。

| ID | 対象 | 未検証の主張 | 必要なもの |
|---|---|---|---|
| UNV-013 | ClickHouse | `s3()` table function reading Parquet directly from an FSx for ONTAP S3 AP | A ClickHouse instance with IAM credentials. |
| UNV-014 | ClickHouse | `iceberg()` table function plus Glue Catalog integration | ClickHouse 23.8+ and a Glue-catalogued Iceberg table. |
| UNV-015 | ClickHouse | S3Queue engine ingesting from a standard S3 bucket fed by DataSync | A ClickHouse instance. Direct S3Queue against the AP is blocked by BLK-003 (no event notifications). |

## アカウントティアまたはコストによる制約

有償ティアまたは課金リソースが必要です。

| ID | 対象 | 未検証の主張 | 必要なもの |
|---|---|---|---|
| UNV-007 | Snowflake | PrivateLink connectivity to an AP-backed stage | A Snowflake Business Critical account or higher, plus PrivateLink setup. |

## 経過時間による制約

短縮できません。

| ID | 対象 | 未検証の主張 | 必要なもの |
|---|---|---|---|
| UNV-003 | Snowflake | COPY INTO 64-day load-history deduplication | A Snowflake session and 64 days of elapsed time. Cannot be shortened; the window is a Snowflake-side retention period. |

## 検証不可

未リリースの要素に依存します。

| ID | 対象 | 未検証の主張 | 必要なもの |
|---|---|---|---|
| UNV-024 | FSx for ONTAP | Behaviour on ONTAP 9.18.1 and later | The release. Cannot be verified today. |

## 直近でクローズした項目

本一覧に載っていたもののうち、実測が完了したものです。

| 対象 | 主張 | 結果 | エビデンス |
|---|---|---|---|
| Athena | FSx for ONTAP S3 AP 上の Iceberg 読み取り**および書き込み** | 検証済み — UPDATE、DELETE、タイムトラベル、OPTIMIZE、VACUUM、2 件の同時コミットを含むライフサイクル全体 | [2026-08-06](../../verification-pack/athena-iceberg/evidence/2026-08-06/evidence-record.yaml) |
| Athena | 高同時実行スキャン（10-50 アナリスト） | 25 並列まで検証。25/25 成功、全カラムスキャンで約 2 倍に劣化、キュー時間は 200 ms 未満。データセットはキャッシュに収まる規模 | [2026-08-06](../../verification-pack/athena-concurrency/evidence/2026-08-06/evidence-record.yaml) |
| Snowflake | 合成した S3 通知で Snowpipe COPY が発火するか | 検証済み — publish から約 0.5 秒で取り込み | [2026-08-06](../../verification-pack/snowpipe-pattern-a/evidence/2026-08-06/snowflake-side-verification.yaml) |
| FSx for ONTAP | ネイティブ S3 に対する ListObjectsV2 レイテンシ | 10〜5,000 オブジェクトで 1.3〜1.4 倍として再測定。従来の 30〜80 倍は再現せず撤回 | [2026-08-05](../../verification-pack/s3ap-list-latency/evidence/2026-08-05/benchmark-result.yaml) |

## 本ページの使い方

主張が未検証から実測済みに移ったとき: エビデンスを `verification-pack/<topic>/evidence/<date>/` に記録し、マトリクスの該当行がそれを参照するよう更新し、上記の**直近でクローズした項目**へ移し、合計件数を調整してください。

検証ではなく撤回に至った場合は、その旨と理由をマトリクスに残してください。撤回も結果のひとつです。
