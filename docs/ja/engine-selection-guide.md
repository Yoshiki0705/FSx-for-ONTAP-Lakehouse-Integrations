# エンジン選定ガイド

[English](../en/engine-selection-guide.md) | **日本語**

> FSx for ONTAP S3 Access Point のユースケースに応じて、コスト・ガバナンス・AI 対応度から適切な分析エンジンを選択するためのガイド。

---

## クイック判断テーブル

| 主要な質問 | 推奨エンジン | アクセスパターン | ガバナンス | AI 対応度 | PoC コスト (1日) |
|---|---|---|---|---|---|
| 「NAS データを最安で検索したい」 | DuckDB Lambda | ゼロコピー | なし (IAM のみ) | 発見 / プロファイリング | ~$0.01 |
| 「サーバーレス SQL、インフラ不要」 | Athena | ゼロコピー | Glue + Lake Formation | 発見 → キュレーション | ~$0.05 |
| 「Spark ETL で書き戻しが必要」 | EMR Serverless | ゼロコピー (読み取り) + FSx for ONTAP に書き込み | IAM | Parquet / Iceberg 作成 | ~$0.50 |
| 「DWH JOIN + エンタープライズガバナンスが必要」 | Redshift Spectrum + Lake Formation | ゼロコピー | Lake Formation (列/行/タグ) | ガバナンス付き分析 | ~$1.50 |
| 「NAS データで AI（要約、RAG、感情分析）」 | Snowflake External Table + Cortex | ゼロコピー | Snowflake RBAC + Tags | AI 対応 (Cortex AI 即時利用可) | ~$5 |
| 「Databricks 利用中、フル UC + ML が必要」 | DataSync → S3 → UC | S3 同期あり | Unity Catalog (フル) | フル ML/AI (Mosaic AI, Feature Store) | ~$10 |
| 「FSx for ONTAP で Delta/Iceberg は使える？」 | No — FSx for ONTAP から読み取り、S3 に書き込み | 読み取り: ゼロコピー、書き込み: S3 | エンジンに依存 | エンジンに依存 | ~$0.50 |

---

## FSx for ONTAP + S3 AP が適するケース (vs S3 のみ)

| 検討事項 | S3 のみ | FSx for ONTAP + S3 AP |
|---|---|---|
| 既存 NFS/SMB ワークロード | マイグレーションまたはデュアルパス維持が必要 | 変更不要 — 既存アプリは NFS/SMB を継続 |
| ストレージ効率 | 重複排除/圧縮なし | ONTAP 重複排除 + 圧縮 (1.5–2x 典型) |
| ポイントインタイムリカバリ | S3 Versioning (オブジェクト単位、大規模で高コスト) | ONTAP Snapshot (ボリューム単位、瞬時、スペース効率良) |
| 開発/テストデータプロビジョニング | フルコピーが必要 | FlexClone (瞬時ゼロコピークローン) |
| マルチプロトコルアクセス | S3 のみ | NFS + SMB + S3 で同一データに同時アクセス |
| アプリケーション変更の要否 | 必要 (S3 SDK に書き換え) | 不要 (NFS/SMB そのまま、S3 AP は追加的) |

---

## エンジン別アーキテクチャパターン

### パターン A: 読み取り専用分析 (Athena, DuckDB, Redshift Spectrum)

```
分析エンジン → (S3 API) → S3 Access Point → FSx for ONTAP Volume
```

- External Table / External Stage として登録
- Parquet、CSV、JSON、ORC ファイルを直接クエリ
- FSx for ONTAP への書き戻し不要

### パターン B: 読み書き ETL (EMR Spark, Glue)

```
FSx for ONTAP → S3 AP → EMR/Glue (変換) → S3 AP → FSx for ONTAP (キュレーション済み)
```

- Raw → Bronze → Silver → Gold（メダリオン）
- Parquet/CSV の書き戻しは動作（Delta/Iceberg フォーマットは不可）

### パターン C: 外部プラットフォーム + S3 AP ARN (Snowflake)

```
Snowflake → External Stage (AWS_ACCESS_POINT_ARN) → S3 AP → FSx for ONTAP
```

- ステージ設定で明示的に AP ARN を指定
- SELECT + External Table の完全サポートを確認済み

### パターン D: 同期ベース (Databricks)

```
FSx for ONTAP → DataSync → S3 → Unity Catalog (Delta テーブル)
```

- プラットフォームが S3 AP ARN を直接利用できない場合に使用
- レイテンシ追加（同期間隔）だがフルプラットフォーム機能が利用可能

### パターン E: OpenSharing（ゼロコピーガバナンスアクセス）— 分析中

```
FSx for ONTAP → OpenSharing Server → Catalog → Lakehouse Compute
```

- Presigned-URL 共有モデルが S3 AP ARN 制限をバイパスする可能性
- [OpenSharing 統合分析](opensharing-integration-analysis.md) を参照

---

## オープンテーブルフォーマットの考慮事項

FSx for ONTAP S3 Access Points は条件付き書き込み (`If-None-Match`) をサポートしていません。これによる各フォーマットの挙動は次のとおりです。

| フォーマット | 読み取り | 書き込み |
|---|---|---|
| Delta Lake | 動作 | HTTP 501 を返す |
| Apache Iceberg | 既存テーブルの読み取りは動作見込み | 失敗（S3FileIO が AP エイリアスでメタデータを処理できない） |
| Apache Hudi | 動作見込み | 同様の書き込み制限が予想される |

推奨アプローチは、FSx for ONTAP から S3 Access Points 経由でソースデータを読み取り、マネージドテーブルはネイティブ S3 に書き込むことです。

### Iceberg によるマルチプラットフォームブリッジ

Snowflake と Databricks を両方使う環境では、オープン Iceberg フォーマットでクロスプラットフォーム共有が可能:

```
FSx for ONTAP (ソース) → S3 AP / DataSync → S3 → Snowflake Managed Iceberg Table
                                                          ↓
                                                同一 Iceberg on S3
                                                          ↓
                                    Databricks UC / Athena / EMR (Iceberg 読み取り)
```

ベンダーロックインなし。データオーナーシップは保持。各プラットフォームが独自のガバナンスレイヤーを適用。

---

## コスト比較サマリ

| エンジン | 月額コスト (アイドル) | クエリ単価 | 適する用途 |
|---|---|---|---|
| DuckDB Lambda | $0 | ~$0.00001 | アドホック探索、プロファイリング |
| Athena | $0 | $5/TB スキャン | サーバーレス SQL、低頻度クエリ |
| EMR Serverless | $0 | ~$0.05/ジョブ (小規模) | ETL、Spark ワークロード |
| Redshift Spectrum | クラスターコスト | $5/TB スキャン | エンタープライズ DWH + ガバナンス |
| Snowflake | クレジットベース | ~$2/クレジット | マルチクラウド、AI/Cortex |
| Databricks (DataSync 経由) | クラスター/サーバーレス | DBU ベース | フル ML/AI プラットフォーム |

詳細なコストモデリングは [コスト見積もり](../adoption-guide/cost-estimation-ja.md) を参照。

---

## 関連リソース

- [互換性マトリクス](compatibility-matrix.md) — プラットフォーム対応状況の詳細
- [アーキテクチャ](architecture.md) — システムアーキテクチャ全体
- [業界別ソリューションカタログ](industry-solution-catalog.md) — 26 業界の推奨パターン
- [PoC 実行ガイド](../implementation-guide/poc-execution-guide-ja.md) — ステップバイステップのデプロイ手順
