# 導入評価ガイド

🌐 [English](./adoption-assessment.md) | **日本語**

> このパターンが適合するか、構成をどう選ぶか、何を主張してはいけないか。
> 本書の機能に関する記述はすべて [`verification-pack/`](../../verification-pack/) の
> 記録に対応しています。未検証のものは
> [未検証項目インベントリ](../ja/unverified-inventory.md) に明示しています。

## 適用が想定される状況

| セグメント | プロファイル | 課題 |
|-----------|------------|------|
| エンタープライズ NAS ユーザー | オンプレミス NetApp ONTAP / NAS で 10TB+ のファイルデータを保有 | 分析にデータコピーが必要、S3 ネイティブサービスから NAS にアクセス不可 |
| FSx for ONTAP 利用企業 | NFS/SMB ワークロードで FSx for ONTAP を既に利用中 | Lakehouse/分析プラットフォームが S3 を要求し、データサイロが発生 |
| ハイブリッドクラウド | オンプレミス ONTAP + AWS、SnapMirror で DR/移行中 | ストレージ再設計なしでクラウド分析を活用したい |

## 解決したい課題

NAS/ONTAP 上にファイルベースのデータを持つ組織は、根本的な断絶に直面しています：

1. **データ重複**: 分析プラットフォーム（Databricks、Snowflake、Athena）が S3 上のデータを要求し、NAS から S3 へのコピーパイプラインが必要
2. **ガバナンス分断**: NAS（UNIX/NTFS 権限）と S3（IAM ポリシー）で別々のアクセス制御が存在し、コンプライアンスギャップが発生
3. **運用オーバーヘッド**: 同期パイプラインがレイテンシ、コスト、障害点を追加
4. **投資の無駄**: データを S3 にコピーすると、既存の ONTAP 機能（重複排除、スナップショット、階層化）が活用できない

## パターンの概要

Amazon FSx for ONTAP S3 Access Points により、FSx for ONTAP ボリューム上のファイルデータにデータ移動なしで S3 API アクセスが可能になります。S3 と連携するアプリケーションや AWS サービスが、アクセスポイント経由でファイルデータを直接読み書きできます。

**主要な技術仕様**（[AWS ドキュメント](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)より）：
- サポートされる S3 操作: GetObject, PutObject, DeleteObject, ListObjectsV2, HeadObject, Multipart Upload, CopyObject（同一アクセスポイント内のみ）
- 二層認可: IAM ポリシー評価 + ファイルシステムユーザー権限（UNIX または Windows）
- レイテンシ: 数十ミリ秒（S3 バケットアクセスと同等）
- スループット: FSx for ONTAP ファイルシステムのプロビジョンドスループット容量に依存
- Block Public Access がデフォルトで強制（無効化不可）
- ONTAP バージョン 9.17.1 以降が必要

## 導入で変わる点

| 成果 | 指標 |
|------|------|
| データコピーの排除 | N 個のコピー → 1 つの正規ソース |
| 同期パイプラインの廃止 | NAS → S3 ETL ジョブの排除 |
| インサイトまでの時間短縮 | パイプライン構築に数日 → 直接クエリで数時間 |
| NFS/SMB アクセスの維持 | 既存ワークロードは変更不要 |
| ガバナンスの統一 | 単一データ所在地、二層アクセス制御 |
| ファイルデータでの AI/ML 活用 | Bedrock、SageMaker、EMR が S3 AP 経由でアクセス |

## 適用範囲別の 3 構成

### Good: 単一アカウント・読み取り専用分析

**スコープ**: 単一 AWS アカウント、単一 SVM、読み取り専用分析

| コンポーネント | 構成 |
|--------------|------|
| FSx for ONTAP | Single-AZ、1 SVM、1 ボリューム |
| S3 Access Point | Internet origin、読み取り専用ファイルシステムユーザー |
| 分析 | Athena + Glue Data Catalog |
| セキュリティ | 分析チームごとの IAM ロール、読み取り専用 UNIX ユーザー |
| モニタリング | CloudTrail による API コール記録 |

**ユースケース**: データ移動なしでファイルデータ（CSV、Parquet、JSON）に対するアドホック SQL クエリ

**検証済み AWS 統合**: [Amazon Athena で SQL によるファイルクエリ](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html)

---

### Better: VPC 制限付きアクセスとカタログ統合

**スコープ**: VPC 制限付きアクセス、Glue Catalog / Unity Catalog 統合、ETL 用読み書き

| コンポーネント | 構成 |
|--------------|------|
| FSx for ONTAP | Single-AZ または Multi-AZ、複数ボリューム |
| S3 Access Point | VPC origin（特定 VPC にバインド）、読み書きファイルシステムユーザー |
| 分析 | Databricks Unity Catalog / Snowflake External Stage / Glue ETL |
| セキュリティ | VPC エンドポイントポリシー + アクセスポイントポリシー + ファイルシステム権限 |
| ネットワーク | Gateway エンドポイント（VPC 内）+ Interface エンドポイント（Direct Connect 経由オンプレミス） |
| モニタリング | CloudTrail + CloudWatch メトリクス |

**ユースケース**: FSx for ONTAP からソースデータを読み取り、Glue/EMR で変換し、加工済み結果を書き戻す ETL パイプライン

**検証済み AWS 統合**:
- [AWS Glue を使用した ETL パイプライン構築](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html)
- [Amazon EMR Serverless での Spark ジョブ実行](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-run-spark-with-emr-serverless.html)

---

### Best: マルチアカウントガバナンス + DR + AI

**スコープ**: マルチアカウント、Lake Formation / IAM / S3 AP ポリシー、SnapMirror DR、監査ログ、AI/RAG

| コンポーネント | 構成 |
|--------------|------|
| FSx for ONTAP | Multi-AZ、複数 SVM、DR リージョンへの SnapMirror |
| S3 Access Points | コンシューマーごとのアクセスポイント（スコープ付き IAM ポリシー） |
| 分析 | Databricks + Snowflake + Athena（マルチプラットフォーム） |
| AI/ML | Amazon Bedrock Knowledge Bases による RAG |
| セキュリティ | Lake Formation + S3 AP ポリシー + VPC origin + ファイルシステム ACL |
| ガバナンス | CloudTrail、ONTAP 監査ログ、データ分類タグ |
| DR | SnapMirror クロスリージョンレプリケーション、ONTAP Snapshots |

**ユースケース**: ドメイン固有のアクセスポイントによるエンタープライズデータメッシュ、AI ドキュメント検索、規制データガバナンス

**検証済み AWS 統合**:
- [Amazon Bedrock Knowledge Bases を使用した RAG アプリケーション構築](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)
- Good / Better 構成の全統合

---

## 業界別ユースケースパターン

| ユースケース名 | 業界 | パターン | 構成 |
|--------------|------|---------|-------|
| Zero-Copy NAS Analytics for Manufacturing | 製造 | 読み取り専用分析 | Good |
| Regulated Data Lakehouse for Healthcare Research | 医療 | マネージドテーブル（読み取り） | Better |
| Financial Data Mesh with FSx for ONTAP and S3 Access Points | 金融 | データ共有 | Best |
| AI-Powered Document Intelligence on Enterprise Files | 全業界 | Bedrock RAG | Best |
| Hybrid Cloud Analytics Bridge | 全業界 | ETL パイプライン | Better |
| Media Asset Analytics without Data Migration | メディア | 読み取り専用分析 | Good |

## ユースケース別導入ステップ

### Zero-Copy NAS Analytics for Manufacturing

| ステップ | アクション | タイムライン |
|---------|----------|------------|
| 1 | FSx for ONTAP + S3 Access Point のデプロイ | Day 1-2 |
| 2 | Glue Crawler の設定 | Day 2 |
| 3 | サンプルデータでの Athena クエリ検証 | Day 3 |
| 4 | BI ツール（QuickSight）接続 | Day 4-5 |
| **成功基準** | 1GB データセットに対するクエリレイテンシ < 10 秒、データコピーゼロ | |

### Regulated Data Lakehouse for Healthcare Research

| ステップ | アクション | タイムライン |
|---------|----------|------------|
| 1 | Multi-AZ FSx for ONTAP + VPC-origin S3 AP のデプロイ | Week 1 |
| 2 | Lake Formation 権限の設定 | Week 1 |
| 3 | 匿名化パイプライン用 Glue ETL のセットアップ | Week 2 |
| 4 | 分析プラットフォームへの外部テーブル登録 | Week 2 |
| 5 | 監査証跡とアクセス制御の検証 | Week 3 |
| **成功基準** | PHI が VPC 外に出ない、監査証跡が完全、クエリ < 30 秒 | |

### Financial Data Mesh with FSx for ONTAP and S3 Access Points

| ステップ | アクション | タイムライン |
|---------|----------|------------|
| 1 | ドメインごとの SVM によるマルチアカウントセットアップ | Week 1-2 |
| 2 | コンシューマーごとの S3 Access Points（スコープ付きポリシー） | Week 2-3 |
| 3 | クロスアカウント IAM ロールと VPC エンドポイント | Week 3 |
| 4 | SnapMirror DR 設定 | Week 4 |
| 5 | Databricks Unity Catalog + Snowflake External Stage | Week 4-5 |
| **成功基準** | ドメイン分離の検証、DR RTO < 1 時間、マルチプラットフォームクエリ | |

---

## アンチパターン: 適用すべきでないケース

| アンチパターン | 失敗する理由 | 代わりに提案すべきもの |
|-------------|------------|-------------------|
| FSx for ONTAP S3 AP 上での Delta Lake write / MERGE / compaction | Delta コミットプロトコルは atomic rename を必要とするが、FSx for ONTAP S3 AP ではサポートされていない（[API サポート](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)） | Delta テーブルの読み取り専用分析、または Delta 書き込みパスにはネイティブ S3 を使用 |
| 規制業界でのデフォルトとしての Internet-origin AP | 規制データにはネットワークレベルの分離が必要。VPC-origin は非 VPC トラフィックに対する明示的 Deny を組み込み提供 | 機密/規制データには VPC-origin AP（注: Athena は internet-origin が必要） |
| 「S3 完全互換」と主張すること | FSx for ONTAP S3 AP は S3 操作のサブセットをサポート。Object Versioning なし、条件付き書き込みなし、署名付き URL なし、50 GB アップロード制限 | 正確な表現を使用: 「サポートされる操作での S3 API アクセス」+ 互換性マトリクスへのリンク |
| Iceberg の書き込みパスをすべて同等に扱う | Athena + Glue Data Catalog 経由の Iceberg は読み書きとも検証済み（2026-08-06）。コミットのポインタを Glue が保持するため。一方 EMR Serverless 経由の Iceberg は依然失敗し、Delta はコミット自体ができない | エンジン名を明示する。「Iceberg の書き込みは動く」が成り立つのは Athena のみ |
| FSx for ONTAP スループットプロビジョニングの無視 | S3 のような無制限スループットを期待しがちだが、FSx for ONTAP S3 AP スループットはプロビジョンド容量に制限される | FSx for ONTAP スループットをワークロード要件に合わせてサイジング。PoC 検証に含める |
| 高並行性・小ファイルワークロードへの FSx for ONTAP S3 AP 提案 | 数十ミリ秒のレイテンシ + プロビジョンドスループット制限により、ネイティブ S3 と比較して最適ではない | 大規模シーケンシャルスキャン、バッチ分析、ドキュメント検索に使用。高頻度 API コールには不向き |

### 主張してはいけないこと

1. **絶対に** FSx for ONTAP S3 AP が S3 バケットのドロップイン代替であると主張しないこと
2. **絶対に** 制限事項を導入チームが明示的に承知しないまま Delta/Hudi 書き込み操作を提案しないこと
3. **絶対に** PoC 環境で実際の PHI/PII を使用しないこと
4. **絶対に** セキュリティトレードオフを文書化せずに医療/金融向けに internet-origin AP を提案しないこと
5. **必ず** 技術提案書に互換性マトリクスの参照を含めること

---

## アーキテクチャ選定ガイド

### FSx for ONTAP S3 Access Points の適用ガイド

| アプローチ | データコピー? | NAS への影響 | 分析までの時間 | ガバナンス | AI/RAG | 最適な用途 |
|----------|-----------|-----------|-------------|-----------|--------|----------|
| **FSx for ONTAP S3 AP（本ソリューション）** | なし | なし | 数時間 | 統一（二層） | あり（Bedrock） | 既存 NAS データ、読み取り中心の分析、ドキュメント AI |
| **Native S3 + DataSync** | あり（フルコピー） | なし | 数日（初期同期） | 分離（S3 vs NAS） | あり | 書き込み中心の Lakehouse、Delta/Iceberg マネージドテーブル |
| **Native S3 + ETL パイプライン** | あり（変換済み） | なし | 数日〜数週間 | 分離 | あり | 複雑な変換、S3 上のメダリオンアーキテクチャ |
| **Snowflake External Stage on FSx for ONTAP S3 AP** | なし（ゼロコピー読み取り） | なし | 数時間 | Snowflake 管理（Tags, Row Policy, Masking） | あり（Cortex AI, Cortex Search） | NAS データ上のガバナンス付き AI が必要な Snowflake 利用者。COPY INTO → Managed Iceberg でオープン形式共有。 |
| **Databricks on native S3** | あり（先に S3 へ） | なし | 数日 | Unity Catalog on S3 | あり | Databricks 中心、Delta 書き込み中心 |
| **FabricPool tiering** | 部分的（コールドティア） | 最小限 | N/A（分析用途ではない） | ONTAP 管理 | なし | コスト最適化、分析用途ではない |
| **オンプレミス分析** | なし | なし | 数週間（セットアップ） | オンプレミスツール | 限定的 | エアギャップ環境 |

### 判断フレームワーク

```
Q1: Lakehouse テーブル（Delta/Iceberg）への書き込みが必要か？
  → はい: 書き込みパスはネイティブ S3。FSx for ONTAP S3 AP は読み取り専用のソースデータ用
       （例外: Athena + Glue Data Catalog 経由の Iceberg は書き込み検証済み）
  → いいえ: FSx for ONTAP S3 AP が適合

Q2: サブミリ秒のレイテンシ、または無制限の同時実行数が必要か？
  → はい: ネイティブ S3
  → いいえ: FSx for ONTAP S3 AP（数十 ms のレイテンシ、プロビジョンドスループット）

Q3: 分析したい既存の NAS/ONTAP データがあるか？
  → はい: FSx for ONTAP S3 AP でコピーが不要になる
  → いいえ: ネイティブ S3 のほうが単純

Q4: S3 分析と併せて NFS/SMB アクセスが必要か？
  → はい: FSx for ONTAP S3 AP（同一データへのマルチプロトコルアクセス）
  → いいえ: ネイティブ S3 で足りる可能性がある

Q5: 既存ドキュメントに対する AI/RAG が必要か？
  → はい: FSx for ONTAP S3 AP + Bedrock Knowledge Bases
  → いいえ: Q1〜Q4 に基づいて判断
```

---

### 評価のための質問

1. 「現在、分析のために S3 にコピーしているファイルデータはどのくらいありますか？月額コストはいくらですか？」
2. 「データ作成から分析利用可能になるまでどのくらいかかりますか？」
3. 「NAS と S3 で別々のアクセス制御がありますか？クロスシステムアクセスをどのように監査していますか？」
4. 「ファイル共有上に AI で検索可能にしたいドキュメントはありますか？」
5. 「どの分析プラットフォームを使用中または評価中ですか（Databricks、Snowflake、Athena）？」
6. 「データアーキテクチャの意思決定に影響するコンプライアンス要件は何ですか？」

### 前提条件チェックリスト

- [ ] コピーが実際に問題になる規模のファイルデータが NAS/ONTAP 上にある（目安 10 TB 以上）
- [ ] ファイルシステムを接続できる VPC を持つ AWS アカウントがある
- [ ] 「分析したい」ではなく、実行したい具体的なクエリやワークロードが決まっている
- [ ] ファイルシステムが ONTAP 9.17.1 以降を実行できる
- [ ] 分析エンジンとファイルシステムを同一リージョンに配置できる
- [ ] 使用するエンジンが必要とする操作を[互換性マトリクス](../ja/compatibility-matrix.md)で確認済み

### よくある懸念と、検証結果に基づく回答

| 懸念 | 検証結果 |
|---------------|------|
| 「既に S3 にコピーしていて問題ない」 | 「そのパイプラインの月額コストはいくらですか？障害時はどうなりますか？FSx for ONTAP S3 AP ならそれを完全に排除できます。」 |
| 「本当に S3 互換ですか？」 | 「分析に必要なコア S3 操作（Get、Put、List、Delete）をサポートしています。正確な互換性マトリクスはこちらです。読み取り専用分析は完全に検証済みです。」 |
| 「パフォーマンスはどうですか？」 | 「レイテンシは数十ミリ秒で S3 と同等です。スループットは FSx for ONTAP のプロビジョニングに依存します。PoC でワークロードに合わせてサイジングします。」 |
| 「Delta Lake の書き込みが必要です」 | 「Delta 書き込みには atomic rename が必要ですが、これはサポートされていません。ソースデータの読み取りには FSx for ONTAP S3 AP を、Delta 書き込みターゲットにはネイティブ S3 を推奨します。」 |
| 「セキュリティチームがブロックするでしょう」 | 「Block Public Access がデフォルトで強制されます。二層認証（IAM + ファイルシステム）。ネットワーク分離には VPC-origin オプション。ガバナンスドキュメントはこちらです。」 |

## 参考資料

- [S3 アクセスポイント経由でのデータアクセス](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [アクセスポイントの互換性](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
- [AWS サービスでのアクセスポイント利用](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html)
- [S3 アクセスポイントのネットワークアクセス設定](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/configuring-network-access-for-s3-access-points.html)
- [Amazon FSx for NetApp ONTAP のパフォーマンス](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/performance.html)
