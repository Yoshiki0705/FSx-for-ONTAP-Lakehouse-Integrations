🌐 [English](../en/kafka-clickhouse-unity-catalog-connectivity.md) | **日本語**

> 📖 **総合ガイド**: FSx for ONTAP → Databricks UC の全接続パスを俯瞰するには [UC 接続総合ガイド](./fsx-ontap-to-databricks-unity-catalog-guide.md) を参照してください。本ドキュメントはストリーミング/カタログ接続の技術詳細に特化しています。

# Kafka / ClickHouse から Databricks Unity Catalog への接続: 通信経路・ポート視点の解説

> **ステータス**: 初版（2026-06-18）。公開ドキュメントに基づく整理。
> **Evidence tier**: 各主張は **Public**（公式ドキュメントで確認）。一部 **Hypothesis**（未検証）は明示。
> **フレーミング**: ストレージプロトコル（SMB/NFS/S3 API）とは**別の視点**＝接続性（ストリーミング/カタログ/ワイヤープロトコル）で解説。right-tool-for-the-job、vendor-versus 表現なし。
> **注**: 個人名・社名（外部レビュアー）は記載しない（ロール記述のみ）。

---

## 0. なぜ「別視点」が必要か: データ・アット・レスト vs データ・イン・モーション

これまでの評価は **ストレージ視点**（FSx for ONTAP の SMB/NFS/S3 AP）= **データ・アット・レスト（静止データ）** へのファイル/オブジェクトアクセスが中心でした。Kafka / ClickHouse を含む構成は、**接続性視点** = **データ・イン・モーション（流れるデータ）+ クエリ/カタログプロトコル**で捉える必要があります。

| 観点 | ストレージ視点（既存） | 接続性視点（本ドキュメント） |
|------|----------------------|---------------------------|
| 対象 | 静止データ（ファイル/オブジェクト） | 流れるデータ + メタデータ/クエリ |
| 代表プロトコル | SMB / NFS / S3 API | Kafka（ストリーミング）/ Iceberg REST・Unity REST（カタログ）/ ネイティブ TCP・JDBC（クエリ） |
| 代表ポート | 445(SMB) / 2049(NFS) / 443(S3) | 9094-9098(Kafka) / 443(REST) / 9000・9440(ClickHouse native) |
| UC との接点 | External Location（S3 AP は非対応、別doc参照） | **ストリーミング取り込み**（Kafka→UC Delta）/ **カタログ公開**（UC Iceberg REST→外部エンジン） |
| ガバナンス強制点 | ONTAP ACL + IAM（FPolicy は NFS / SMB 経路のみで、S3 Access Point 経由の操作は遮断しない） | UC（テーブル/サービス資格情報）+ credential vending |

> 関連: ストレージ視点は [S3 Annotations 評価](./s3-annotations-governance-evaluation.md)、[zero-copy media governance](./zero-copy-media-governance.md) を参照。

---

## 1. Kafka → Databricks Unity Catalog（データ取り込み）

### 接続方法（Public）

Databricks の **Structured Streaming / Lakeflow Declarative Pipelines** が Kafka をソースとして読み取り、**UC 管理の Delta テーブル**へ書き込みます。Databricks Kafka コネクタは Apache Spark Kafka コネクタ上に構築され、`kafka.*` オプションがそのまま渡されます（[Connect to Apache Kafka](https://docs.databricks.com/aws/en/connect/streaming/kafka)）。

- **UC との接点は 2 つ**:
  1. **宛先テーブル**: 書き込み先 Delta テーブルを UC がガバナンス（タグ/権限/リネージ）。
  2. **接続認証**: **DBR 16.1 以降、MSK 認証に UC service credentials を利用可能**（推奨。特に共有クラスタ/サーバーレス）（[Kafka authentication](https://docs.databricks.com/aws/en/connect/streaming/kafka/authentication)）。

> **ストリーミング・セマンティクス**: チェックポイント（オフセット管理）は耐久ストレージ（クラウドストレージ / UC ボリューム）に保存する。デフォルトは **at-least-once**。重複は宛先側の**冪等書き込み**（Delta MERGE / イベント ID 重複排除）で吸収。順序保証は **Kafka パーティション内**に限る（コネクテッドカー telemetry 等で要注意）。

### 通信経路（ネットワーク）

```
[Databricks コンピュート]                         [Amazon MSK / Kafka]
  classic（顧客VPC）── VPC Peering / Transit Gateway ──▶ ブローカー
  serverless ──────── PrivateLink / NCC（Network Connectivity Config）─▶ ブローカー
        │                                                   │
        └─ 読み取り（Structured Streaming）────────────────┘
        ▼
[UC 管理 Delta テーブル]  ← UC がガバナンス
```

### ポート / 認証（MSK）

| 接続区分 | TLS | SASL/SCRAM | IAM |
|---------|-----|-----------|-----|
| AWS 内（プライベート） | **9094** | **9096** | **9098**（IPv6 は 20098） |
| パブリックアクセス | **9194** | **9196** | **9198** |

（[MSK Port information](https://docs.aws.amazon.com/msk/latest/developerguide/port-info.html)。平文 9092 は VPC 内のみ・非推奨。）

- **認証方式**: UC service credentials（DBR 16.1+, 推奨） / IAM（SigV4） / SASL-SCRAM / mTLS。
- **推奨**: プライベート経路（PrivateLink/NCC または VPC peering）+ TLS/IAM。パブリックポート開放は最小化。

---

## 2. ClickHouse ↔ Databricks Unity Catalog（カタログ連携・クエリ）

### 接続方法（ClickHouse → UC、サポート済・推奨）（Public）

ClickHouse の **`DataLakeCatalog` データベースエンジン**（`type: unity`（Delta）/ `rest`（Iceberg）、**Beta**）が **Databricks Unity Catalog に直接接続**し、UC テーブルを Delta / Iceberg として読み取れます（[ClickHouse: Unity Catalog](https://clickhouse.com/docs/use-cases/data-lake/unity-catalog)、[DataLakeCatalog](https://clickhouse.com/docs/engines/database-engines/datalakecatalog)）。カタログ全体が 1 つの ClickHouse データベースとして見え、ClickHouse SQL でクエリできます。

UC 側は外部エンジン向けに**オープン API + credential vending** を提供します:
- **Iceberg REST catalog**: エンドポイント `/api/2.1/unity-catalog/iceberg-rest`（[Iceberg clients](https://docs.databricks.com/aws/en/external-access/iceberg.html)）
- **Unity REST API**（Delta clients）（[Delta clients](https://docs.databricks.com/external-access/unity-rest.html)）
- **Credential vending**: UC 権限を継承した一時資格情報を外部エンジンに発行（Trino / DuckDB / StarRocks / Dremio / Spark 等が利用）（[Secure External Access via Open APIs](https://www.databricks.com/blog/secure-external-access-unity-catalog-assets-open-apis)）

> **ClickHouse Cloud vs セルフマネージド**: `DataLakeCatalog` は ClickHouse Cloud 中心の機能。ClickHouse Cloud → UC/S3 は SaaS からの egress（PrivateLink オプションの可否を要確認）。セルフマネージド（EC2/オンプレ）の場合は自前 VPC からの outbound 443 + S3 エンドポイント設計が必要。

#### UC オブジェクト種別ごとのアクセスパターン（Public）

| UC オブジェクト | フォーマット | 外部アクセス手段 |
|---|---|---|
| 管理テーブル | Delta / Iceberg | Unity REST / Iceberg REST / Delta Sharing |
| 外部テーブル | Delta | 上記 + cloud URIs |
| Foreign テーブル（federation） | Delta / Iceberg | Iceberg REST（**Preview**）/ Delta Sharing |

> 外部エンジンは**時点のメタデータ**を取得する。foreign テーブルの最新読み取りには**定期的なメタデータ更新（Lakeflow ジョブ）**が必要（[Access Databricks data using external systems](https://docs.gcp.databricks.com/external-access/index.html)）。

### 通信経路（ネットワーク）

```
[ClickHouse（クライアントとして外向き接続）]
   │ ① メタデータ取得 + credential vending
   │    HTTPS 443 → Databricks workspace（/api/2.1/unity-catalog/iceberg-rest）
   │ ② データ読み取り
   │    HTTPS 443 → Amazon S3（vended credentials で UC 権限を継承）
   ▼
[ClickHouse SQL で UC テーブルをクエリ]

（ClickHouse 自体への接続ポートは §4 参照。UC への接続は ClickHouse からの outbound 443）
```

### 重要な「方向」の区別（混同しやすい）

| 方向 | 説明 | 状態 |
|------|------|------|
| **UC = Iceberg REST サーバ → ClickHouse/Trino/Spark が読む** | UC がカタログを公開し外部エンジンが消費（credential vending） | ✅ **サポート済**（[S3 Annotations doc](./s3-annotations-governance-evaluation.md) と整合） |
| **UC が AWS S3 Tables を `iceberg_rest` connection で消費** | UC が外部 Iceberg を取り込む（逆方向） | ❌ **ブロック中**（本リポジトリ iceberg-metadata-catalog Phase 4） |

→ 「ClickHouse が UC を読む」のは**サポート済**。「UC が S3 Tables を読む」のがブロック中で、**両者は逆方向の別物**。

### Databricks → ClickHouse（逆方向）

- UC **Lakehouse Federation** の**公式 ClickHouse コネクタは調査時点で無し**（対応: MySQL/PostgreSQL/SQL Server/Snowflake/Redshift/BigQuery 等）。
- ClickHouse は **MySQL 互換（9004）/ PostgreSQL 互換（9005）** ワイヤーインターフェースを持つため、UC の MySQL/PG フェデレーションコネクタで参照する案は理論上あり得るが、**未検証（Hypothesis）**。SQL 方言差・型変換に注意。

---

## 3. Kafka を「共有バス」にする 3 層パターン（直接接続なし）

製造データプラットフォームの 3 層構成では、ClickHouse と Databricks は **Kafka を介して独立に**消費し、相互に直接接続しません。

```
                ┌──▶ ClickHouse（オンプレ/クラウド、リアルタイム OLAP）
Kafka（共有バス）─┤
                └──▶ Databricks（Structured Streaming → UC 管理 Delta）── UC ガバナンス
```

- 両者は Kafka コンシューマグループとして独立。**ClickHouse↔Databricks の直接接続は不要**。
- UC は Databricks 側の Delta テーブルをガバナンス。ClickHouse 側は ONTAP/ClickHouse 側の制御。
- 必要時のみ §2 の「ClickHouse → UC」連携で Databricks 側データを ClickHouse から参照。

---

## 4. 統合ポート / プロトコル一覧

| コンポーネント | プロトコル | ポート | 用途 | 暗号化 |
|--------------|-----------|-------|------|-------|
| Kafka（MSK, private） | TLS / SASL_SSL / IAM | 9094 / 9096 / 9098 | Databricks の取り込み | TLS |
| Kafka（MSK, public） | TLS / SASL_SSL / IAM | 9194 / 9196 / 9198 | 公開経路（最小化） | TLS |
| Databricks UC REST | HTTPS（Iceberg REST / Unity REST） | 443 | 外部エンジンのカタログ/credential | TLS |
| Amazon S3（データ） | HTTPS | 443 | vended credentials でデータ読取 | TLS |
| ClickHouse native | TCP | 9000 / **9440(TLS)** | ClickHouse クライアント/分散 | 9440 で TLS |
| ClickHouse HTTP | HTTP / HTTPS | 8123 / **8443(TLS)** | REST 風アクセス | 8443 で TLS |
| ClickHouse MySQL 互換 | MySQL wire | 9004 | 互換クライアント（UC 逆方向は未検証） | 設定依存 |
| ClickHouse PostgreSQL 互換 | PG wire | 9005 | 互換クライアント（UC 逆方向は未検証） | 設定依存 |

（出典: [MSK port-info](https://docs.aws.amazon.com/msk/latest/developerguide/port-info.html)、[ClickHouse network ports](https://clickhouse.com/docs/guides/sre/network-ports)）

---

## 5. セキュリティ考慮

- **プライベート接続を優先**: Kafka はプライベートポート（9094/9096/9098）+ PrivateLink/NCC/VPC peering。パブリックポート（919x）開放は最小化。
- **認証の集約**: Kafka 認証は **UC service credentials**（DBR 16.1+）でガバナンス下に統合。外部エンジン（ClickHouse）アクセスは **credential vending** で UC 権限を継承（資格情報の直接配布を回避）。
- **TLS 必須**: ClickHouse は 9440 / 8443 を使用（9000 / 8123 平文は内部限定）。
- **最小権限**: UC 上のテーブル/カタログ権限を最小化。credential vending の付与範囲を限定。
- **監査**: Kafka 取り込み（UC リネージ）+ 外部エンジンアクセス（UC 監査ログ）を突合。
- **ストレージ層の補償コントロール**（別視点）: ONTAP のファイルレベル ACL は引き続き有効。**ただし FPolicy は S3 Access Point 経由の操作を検知せず、`mandatory` 指定でも遮断しません**（実測 2026-08-26 / ONTAP 9.18.1P3D1）。AP 経由の経路に補償コントロールを置くなら、S3 側（アクセスポイントポリシー、IAM）か、検知のみなら ONTAP 監査ログ / ARP になります（[S3 Annotations doc §2](./s3-annotations-governance-evaluation.md)、[FPolicy と S3 Access Point のカバレッジ実測](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/docs/ja/s3ap-monitoring-coverage-implications.md)）。
- **ネットワーク制御の具体**: Databricks サーバーレスは **NCC（Network Connectivity Config）** で egress を固定（安定 IP / PrivateLink）し、MSK ブローカー側のセキュリティグループで許可する。ClickHouse → S3 は可能なら **S3 ゲートウェイ/インターフェース VPC エンドポイント**経由。SG の向き: **MSK ブローカー SG は Databricks からの inbound（9094 等）を許可**、**ClickHouse は outbound 443（Databricks workspace / S3）を許可**。
- **credential vending の運用**: vended credentials は **TTL・スコープ付きの一時資格情報**であり、外部エンジンの読み取りは UC 監査に記録される。**2 つの UC 機構を区別**すること — (a) **UC service credentials** = Databricks 自身が外部へ接続する際の認証（例: Kafka）、(b) **credential vending** = 外部エンジン（ClickHouse 等）が UC 権限を継承してデータを読む仕組み。
- **前提: 外部データアクセスの有効化**: credential vending / 外部エンジンの UC アクセスは、メタストア/ワークスペースで **「外部データアクセス（external data access）」を有効化**することが前提（[External data access for pipelines](https://docs.databricks.com/aws/en/external-access/external-for-pipelines)）。無効の場合、ClickHouse 等からの接続は拒否される。

---

## 6. 選定ガイド（用途に応じて / right-tool-for-the-job）

| やりたいこと | 接続方法 | 補足 |
|------------|---------|------|
| Kafka のイベントを UC ガバナンス下で蓄積 | Kafka → Structured Streaming/Lakeflow → UC Delta | 認証は UC service credentials 推奨 |
| ClickHouse から Databricks/UC のデータを読む | ClickHouse `DataLakeCatalog`（unity/rest）→ UC Iceberg REST + credential vending | Beta。読取はバージョン/設定依存 |
| ClickHouse と Databricks を疎結合に共存 | Kafka 共有バス（独立消費） | 直接接続不要、3 層パターン |
| Databricks から ClickHouse を参照 | （公式コネクタ無し）MySQL/PG 互換経由は未検証 | Hypothesis、要検証 |

---

## 参考

- [Databricks: Connect to Apache Kafka](https://docs.databricks.com/aws/en/connect/streaming/kafka)
- [Databricks: Kafka authentication（UC service credentials, MSK）](https://docs.databricks.com/aws/en/connect/streaming/kafka/authentication)
- [Databricks: Access Databricks tables from Apache Iceberg clients（Iceberg REST）](https://docs.databricks.com/aws/en/external-access/iceberg.html)
- [Databricks: Read Databricks tables from Delta clients（Unity REST）](https://docs.databricks.com/external-access/unity-rest.html)
- [Databricks: Secure External Access to Unity Catalog via Open APIs（credential vending）](https://www.databricks.com/blog/secure-external-access-unity-catalog-assets-open-apis)
- [ClickHouse: DataLakeCatalog engine](https://clickhouse.com/docs/engines/database-engines/datalakecatalog)
- [ClickHouse: Unity Catalog 連携](https://clickhouse.com/docs/use-cases/data-lake/unity-catalog)
- [ClickHouse: network ports](https://clickhouse.com/docs/guides/sre/network-ports)
- [Amazon MSK: Port information](https://docs.aws.amazon.com/msk/latest/developerguide/port-info.html)
- 本リポジトリ: [S3 Annotations 評価](./s3-annotations-governance-evaluation.md) / [リアルタイム分析ランドスケープ](../../integrations/manufacturing-data-platform/docs/ja/14_realtime_analytics_landscape.md)
- 実機検証計画: [検証 Phase 計画（ClickHouse→UC Beta / NCC・SG・エンドポイント）](./verification-plan-clickhouse-uc-connectivity.md)

> 出典の記述はライセンス遵守のため要約・言い換えしています。

