[English](../en/verification-plan-clickhouse-uc-connectivity.md) | **日本語**

# 実機検証 Phase 計画: ClickHouse `DataLakeCatalog` → Unity Catalog (Beta) + ネットワーク (NCC / SG / エンドポイント)

> ステータス: 計画（2026-06-18）。Phase A0/B0 ゲートチェックを読み取り専用で実行済み（2026-06-18）。大半が BLOCKED（ClickHouse Cloud / Databricks の資格情報なし）。A1 以降・B1 以降は資格情報確保後に着手する。
>
> 対象は [接続性ドキュメント](./kafka-clickhouse-unity-catalog-connectivity.md) の未検証項目を Phase 化したもの。各 Phase に 目的 / 前提 / ゲート / 手順 / 期待結果 / エビデンス / コスト / クリーンアップ を記載し、reproducible-evidence 慣習に準拠する。
>
> 個人名・社名は記載しない。account ID / workspace URL / SG ID 等は placeholder（`<...>`）で記載する。CLI/SQL はテンプレートであり、Beta 機能は現行公式ドキュメントで構文を確認しながら調整する。使い捨て・最小権限・検証後に必ずクリーンアップし、既存本番リソースを変更しない。

---

## 0. 全体像と共通前提

| トラック | 目的 | 主な前提 |
|---------|------|---------|
| Track A | ClickHouse `DataLakeCatalog`（Beta）で UC テーブルを読めるか実機確認 | Databricks UC + 外部データアクセス有効化、ClickHouse Cloud、検証用 UC テーブル |
| Track B | Kafka→Databricks（NCC/SG/ポート）と ClickHouse→S3（VPC エンドポイント）の通信経路確認 | Databricks serverless、既存 MSK、VPC/SG/エンドポイント権限 |

環境メモ（grounding、2026-06-18 読み取り確認）: 検証アカウントに provisioned MSK クラスタが既存で（Track B の Kafka ソースは新規構築不要）、S3 Gateway VPC エンドポイントが複数 VPC に既存。具体的 ID は本書では placeholder 化する。

コスト/安全の原則は次のとおり。

- Track A: 検証用 UC テーブルは小規模。ClickHouse Cloud は検証用ウェアハウスを最小サイズ・短時間で使う。
- Track B: 既存 MSK を利用し、新規 MSK は作らない。NCC は無料枠中心だが PrivateLink エンドポイントは課金対象。SG ルールは検証後に revoke する。
- すべて `verification-evidence/<date>/` に YAML でエビデンス記録（既存慣習）。

---

## Track A: ClickHouse `DataLakeCatalog` → Unity Catalog (Beta)

### Phase A0: 前提・ゲート

ゲート（未充足なら BLOCKED）とエビデンスは次のとおり。

| 項目 | 内容 |
|---|---|
| ゲート | ClickHouse Cloud が `DataLakeCatalog`（`catalog_type='unity'`）の Beta をサポートするバージョン/リージョンであること。Databricks メタストアで外部データアクセス（external data access）が有効であること。認証主体（サービスプリンシパル or PAT）と UC 権限（`SELECT` + 外部利用付与）があること |
| エビデンス | ゲート充足状況のチェックリスト |

### Phase A1: UC 側準備

手順（テンプレート）:

```sql
-- Databricks SQL（UC 側）
CREATE CATALOG IF NOT EXISTS ext_demo;
CREATE SCHEMA IF NOT EXISTS ext_demo.s;
CREATE TABLE ext_demo.s.t (id INT, v STRING) USING DELTA;
INSERT INTO ext_demo.s.t VALUES (1,'a'),(2,'b');
-- 外部エンジン向け付与（credential vending）
GRANT SELECT ON TABLE ext_demo.s.t TO `<principal>`;
GRANT EXTERNAL USE SCHEMA ON SCHEMA ext_demo.s TO `<principal>`;
```

外部データアクセスはメタストア設定（アカウントコンソール / API）で有効化する。期待結果はテーブル作成と付与の成功。エビデンスは `DESCRIBE EXTENDED` と grant 一覧。

### Phase A2: ClickHouse `DataLakeCatalog` 構成（type: unity）

手順（テンプレート、現行 ClickHouse ドキュメントで要確認）:

```sql
-- ClickHouse Cloud
CREATE DATABASE uc_demo
ENGINE = DataLakeCatalog
SETTINGS
  catalog_type = 'unity',
  warehouse = '<catalog>',
  catalog_credential = '<oauth-token-or-sp>',
  storage_endpoint = '<workspace-url>/api/2.1/unity-catalog/iceberg-rest';
```

期待結果は `SHOW DATABASES` に `uc_demo` が出現すること。エビデンスは接続成否と ClickHouse server log（DataLakeCatalog 接続行）。構文/設定キーは Beta のため [ClickHouse Unity Catalog ドキュメント](https://clickhouse.com/docs/use-cases/data-lake/unity-catalog) に合わせる。

### Phase A3: 読み取り検証

手順:

```sql
SHOW TABLES FROM uc_demo;
SELECT count() FROM uc_demo.`ext_demo.s.t`;
SELECT * FROM uc_demo.`ext_demo.s.t` LIMIT 10;
```

期待結果は行数が Phase A1 で投入した件数と一致すること。エビデンスは行数、クエリレイテンシ、`EXPLAIN`。

### Phase A4: Iceberg パス（type: rest）

| 項目 | 内容 |
|---|---|
| 目的 | UC を Iceberg REST catalog として読む経路（`catalog_type='rest'`）の確認 |
| 期待結果 | 同一テーブルを Iceberg として読み取り可能 |
| エビデンス | Delta 経路（A3）との結果一致 |

### Phase A5: ガバナンス検証

手順は次の 3 点。付与されていないテーブルをクエリして AccessDenied を確認する（最小権限の実効性）。credential vending の TTL/スコープを観測する（資格情報の有効期限）。UC 監査ログに外部エンジンの読み取りが記録されるか確認する（`system.access.audit` 等）。

期待結果は、未付与は拒否・付与は成功・監査に記録。エビデンスは拒否レスポンス、監査ログ行、TTL 観測値。

### Phase A6: クリーンアップ

ClickHouse で `DROP DATABASE uc_demo;`。UC で `DROP TABLE/SCHEMA/CATALOG ext_demo...;` と grant 取り消し。ClickHouse Cloud ウェアハウスを停止する。

---

## Track B: ネットワーク（NCC / SG / エンドポイント）

### Phase B0: 前提・ゲート

ゲートは、Databricks serverless ワークスペース、NCC のリージョン可用性、SG/エンドポイント変更権限、既存 MSK のブートストラップ情報。

### Phase B1: Kafka→Databricks プライベート経路（NCC + MSK SG）

手順（テンプレート）:

```bash
# Databricks account CLI: NCC 作成 → ワークスペースへ割当（安定 egress / PrivateLink）
databricks account network-connectivity-configs create \
  --json '{"name":"<ncc-name>","region":"ap-northeast-1"}'
# MSK ブローカー SG に Databricks egress を許可（IAM 認証=9098 の例）
aws ec2 authorize-security-group-ingress --region ap-northeast-1 \
  --group-id <msk-broker-sg> --protocol tcp --port 9098 --cidr <databricks-egress-cidr>
```

```python
# Databricks ノートブック: 既存 MSK から Structured Streaming 読み取り（IAM 認証）
df = (spark.readStream.format("kafka")
      .option("kafka.bootstrap.servers", "<bootstrap-brokers:9098>")
      .option("kafka.security.protocol", "SASL_SSL")
      .option("subscribe", "<topic>").load())
```

期待結果はプライベート経路でメッセージを取得し UC 管理 Delta へ書き込めること。エビデンスは取得件数、経路（NCC/PrivateLink 経由）、SG ルール。ポートは private TLS 9094 / SCRAM 9096 / IAM 9098。

### Phase B2: ClickHouse→S3 VPC エンドポイント経路

目的は、ClickHouse → S3 のデータ読み取りを VPC エンドポイント経由にできるか（セルフマネージドの場合）の確認。ClickHouse Cloud は SaaS egress のため経路が異なる点を区別する。

手順は、既存 S3 Gateway エンドポイントのルートを確認する（セルフマネージド ClickHouse の場合）。

```bash
aws ec2 describe-vpc-endpoints --region ap-northeast-1 \
  --filters Name=service-name,Values=com.amazonaws.ap-northeast-1.s3 \
  --query 'VpcEndpoints[].{id:VpcEndpointId,vpc:VpcId}'
```

期待結果は、セルフマネージド ClickHouse は S3 エンドポイント経由で読み取り、ClickHouse Cloud は SaaS 経路（PrivateLink 可否を確認）。エビデンスはルートテーブルと S3 アクセスログ。

### Phase B3: 接続性・ポート検証

手順:

```bash
nc -zv <bootstrap-broker> 9098    # MSK IAM（private）
nc -zv <workspace-host> 443        # Databricks UC REST
```

期待結果は、許可ポートのみ疎通し、それ以外は遮断。エビデンスは nc 結果と SG ルール表。

### Phase B4: クリーンアップ

SG ルールを revoke し、検証用 NCC は不要なら削除、検証用トピック/テーブルを削除する。

---

## ゲート一覧（BLOCKED 条件のまとめ）

| ゲート | 影響トラック | 充足手段 |
|--------|------------|---------|
| ClickHouse Cloud の `DataLakeCatalog`（unity, Beta）サポート | A | 対応バージョン/リージョン確認 |
| UC 外部データアクセス有効化 | A | メタストア設定 |
| serverless ワークスペース | B | ワークスペース種別確認 |
| NCC リージョン可用性 | B | リージョン確認 |
| SG/エンドポイント変更権限 | B | IAM 権限 |

---

## エビデンス記録

各 Phase の結果は `integrations/manufacturing-data-platform/verification-evidence/<YYYY-MM-DD>/` に YAML で記録する（既存慣習に準拠）。記録項目は、日時、環境（リージョン/バージョン）、手順、期待結果、実結果（成功/失敗/制限）、ログ抜粋、クリーンアップ確認。

### 再現可能なゲートチェック（読み取り専用）

Phase A0/B0 のゲート充足状況は、再現可能なスクリプトで確認できる（読み取り専用・資格情報不要・課金リソース未作成）。

```bash
# 既定リージョン ap-northeast-1。各種ヒントは環境変数で渡せる。
bash integrations/manufacturing-data-platform/poc/infrastructure/gate-check-uc-connectivity.sh
```

各ゲートを `MET` / `NOT MET / BLOCKED` で表示し、BLOCKED 件数を集計する。出力するのはツール有無・接続ヒントの有無・MSK/エンドポイントの存在数のみで、アカウント固有 ID はスクリプトにハードコードしない。

実行済み記録（2026-06-18）: `verification-evidence/2026-06-18/gate-check-clickhouse-uc-connectivity.yaml`。Track A は BLOCKED（ClickHouse Cloud + Databricks 認証なし）。Track B は PARTIAL（既存 MSK クラスタ ACTIVE・SASL/IAM+SCRAM・private のみ・転送時 TLS、S3 Gateway エンドポイント 5 件を読み取り確認。ただし NCC/疎通テストは Databricks serverless 未確保のため未実行）。

---

## 参考

- [接続性ドキュメント（Kafka/ClickHouse → UC）](./kafka-clickhouse-unity-catalog-connectivity.md)
- [ClickHouse: Unity Catalog 連携](https://clickhouse.com/docs/use-cases/data-lake/unity-catalog)
- [Databricks: External data access for pipelines](https://docs.databricks.com/aws/en/external-access/external-for-pipelines)
- [Databricks: Kafka authentication（UC service credentials）](https://docs.databricks.com/aws/en/connect/streaming/kafka/authentication)
- [Amazon MSK: Port information](https://docs.aws.amazon.com/msk/latest/developerguide/port-info.html)

> 出典の記述はライセンス遵守のため要約・言い換えしています。
