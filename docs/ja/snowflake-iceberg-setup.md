# Snowflake から FSx for ONTAP のファイルを読み、Iceberg テーブルを書く

🌐 [English](../en/snowflake-iceberg-setup.md) | **日本語**

> 2026-08-06 にエンドツーエンドで検証済み（[エビデンス](../../verification-pack/snowflake/evidence/2026-08-06/evidence-record.yaml)）。
> 本ページのコマンドはすべて実アカウント・実 FSx for ONTAP に対して実行したものです。

## できること

FSx for ONTAP ボリューム上に既にあるファイルを、どこにもコピーせず Snowflake から
クエリできます。ガバナンス対象のテーブルは標準 S3 バケットへ書き込みます。
事前のデータ移動は不要です。

```
FSx for ONTAP ボリューム          S3 Access Point         Snowflake
┌──────────────────┐            ┌─────────────┐         ┌────────────────────┐
│ 既存アプリから    │            │             │  read   │ External Stage     │
│ NFS / SMB で書込  │───────────►│ 読み取り専用 │────────►│ SELECT, COPY INTO  │
│                  │            │  S3 API     │         │                    │
└──────────────────┘            └─────────────┘         └─────────┬──────────┘
                                                                  │ write
                                                        ┌─────────▼──────────┐
                                                        │ 標準 S3 上の        │
                                                        │ Managed Iceberg    │
                                                        │ Table (Ext. Vol.)  │
                                                        └────────────────────┘
```

読み取りは Access Point 経由、書き込みは標準 S3 へ。この分離は意図的です。
Access Point **へ** Iceberg や Delta を書き込むことは現時点では成立せず、
しかもオブジェクトが残る形で失敗します（[書き込み先を分ける理由](#書き込み先を分ける理由)）。

## 事前に必要なもの

| 必要なもの | 確認方法 | 無い場合 |
|---|---|---|
| ONTAP 9.17.1 以降の FSx for ONTAP ファイルシステム | S3 Access Point の要件。コンソールに ONTAP バージョンは出ないので ONTAP REST API で確認 | アップグレード、または新しいファイルシステムを使用 |
| ネイティブ ONTAP S3 object-store server が**無い** SVM | `vserver object-store-server show` | 別の SVM を使用。同一 SVM に共存できません |
| `CREATE STORAGE INTEGRATION` を実行できる Snowflake アカウント | `SELECT CURRENT_ROLE()` が ACCOUNTADMIN、または該当権限を持つロール | アカウント管理者に依頼 |
| AWS CLI v2、IAM ロールと S3 バケットの作成権限 | `aws sts get-caller-identity` | — |

リージョンは思うほど厳密ではありません。Access Point と Snowflake アカウントは
同一リージョンでなくても動作しますが、クロスリージョンではレイテンシと
データ転送料が増えます。同一リージョンが妥当な既定値です。

## ステップ1 — S3 Access Point を作成

Access Point は本リポジトリの CloudFormation テンプレートでは作成しません。
個々の統合ではなくファイルシステムに属するものだからです。

```bash
aws fsx create-and-attach-s3-access-point \
  --name my-lakehouse-ap \
  --type FSX \
  --fsx-configuration 'VolumeId=fsvol-EXAMPLE,FileSystemIdentity={Type=UNIX,UnixConfiguration={Uid=0,Gid=0}}'
```

ここでの判断は2つです。

**ネットワークオリジン。** `VpcConfiguration` は指定しません。Snowflake が必要とするのは
インターネットオリジンの Access Point です。Snowflake は自身のネットワークから
データに到達し、お使いの VPC 内からは来ません。VPC スコープの Access Point は
Snowflake から読めません。

**ファイルシステム ID。** `Uid=0,Gid=0` は root で、すべて読めます。初回は十分です。
それ以降は、公開したいディレクトリだけを読める専用 UNIX ユーザーを作り、その uid を
指定してください。Access Point は IAM ポリシー**と**このファイルシステム ID の権限の
両方を評価するため、この ID は形式ではなく実効的な制御です。

出力のエイリアスを記録してください。`my-lakehouse-ap-<ランダム>-ext-s3alias` の形で、
Snowflake はこれをバケット名として扱います。

## ステップ2 — Snowflake が読み取りに使う IAM ロール

```bash
cp cfn-params/snowflake-phase1.example.json cfn-params/snowflake.json
# 編集: ステップ1で得た S3AccessPointArn と S3AccessPointAlias
aws cloudformation deploy \
  --template-file integrations/snowflake/template.yaml \
  --stack-name fsxn-snowflake \
  --parameter-overrides file://cfn-params/snowflake.json \
  --capabilities CAPABILITY_NAMED_IAM
```

続いて Snowflake で、`IAMRoleArn` 出力を使って実行します。

```sql
CREATE STORAGE INTEGRATION fsxn_s3ap
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  STORAGE_AWS_ROLE_ARN = '<スタック出力の IAMRoleArn>'
  ENABLED = TRUE
  STORAGE_ALLOWED_LOCATIONS = ('s3://<AP エイリアス>/');

DESC STORAGE INTEGRATION fsxn_s3ap;
```

結果から `STORAGE_AWS_IAM_USER_ARN` と `STORAGE_AWS_EXTERNAL_ID` をコピーし、
信頼ポリシーを完成させます。

```bash
./integrations/snowflake/scripts/update_trust_policy.sh \
  --snowflake-arn "<STORAGE_AWS_IAM_USER_ARN>" \
  --external-id "<STORAGE_AWS_EXTERNAL_ID>"
```

この2パス構成は避けられません。Snowflake は統合が存在するまでどのプリンシパルを
使うか教えず、ロールは知らないプリンシパルを信頼できないためです。本リポジトリの
Snowflake 連携はすべてこの形です。

## ステップ3 — ステージと、すべてを左右するパラメータ

```sql
CREATE OR REPLACE STAGE my_stage
  URL = 's3://<AP エイリアス>/path/'
  STORAGE_INTEGRATION = fsxn_s3ap
  AWS_ACCESS_POINT_ARN = 'arn:aws:s3:<region>:<account>:accesspoint/<ap-name>';
```

`AWS_ACCESS_POINT_ARN` が要点です。これが無いと次のようになります。

| 操作 | パラメータ無し | パラメータ有り |
|---|---|---|
| `LIST @my_stage` | 動作 | 動作 |
| `SELECT FROM @my_stage` | **AccessDenied** | 動作 |
| ステージからの `COPY INTO` | **AccessDenied** | 動作 |

`LIST` は通るのに読み取りが全て失敗するのは、ステージの設定が正しく見えるため
非常に紛らわしい失敗です。原因は、アクセスポイント ARN を明示しない限り
Snowflake のセッションポリシーがオブジェクトレベル操作を標準バケット ARN に
限定することです。

`SELECT` で AccessDenied が出て `LIST` は通る場合、まずこのパラメータを確認してください。

## ステップ4 — ファイルの読み取り

```sql
LIST @my_stage;

-- Parquet と CSV
SELECT $1, $2 FROM @my_stage/data.csv;

-- JSON・Avro・ORC は名前付きファイルフォーマットが必要。
-- この位置ではインラインの FILE_FORMAT は受け付けられません
CREATE OR REPLACE FILE FORMAT ff_json TYPE = JSON;
SELECT $1:event_id::string
FROM @my_stage/events.json (FILE_FORMAT => ff_json);
```

検証済みフォーマット: Parquet、CSV、JSON、Avro、ORC。あわせて External Table、
Directory Table、ガバナンスタグ、`BUILD_SCOPED_FILE_URL`、および SQL で解析できない
ファイル向けの Snowpark `SnowflakeFile.open` も検証済みです。

## ステップ5 — Iceberg テーブルの書き込み

```bash
./integrations/snowflake/scripts/setup_external_volume.sh \
  --bucket acme-lakehouse-iceberg-apne1
```

スクリプトが IAM ロールをデプロイし、Snowflake に貼り付ける `CREATE EXTERNAL VOLUME`
文を表示します。その後 `DESC EXTERNAL VOLUME` が返す2つの値を渡します。

```bash
./integrations/snowflake/scripts/setup_external_volume.sh --phase3 \
  --snowflake-arn "<STORAGE_AWS_IAM_USER_ARN>" \
  --external-id "<STORAGE_AWS_EXTERNAL_ID>"
```

先に進む前に確認します。

```sql
SELECT SYSTEM$VERIFY_EXTERNAL_VOLUME('fsxn_lakehouse_iceberg_vol');
```

正常な結果は `"success": true` で、`writeResult`・`readResult`・`listResult`・
`deleteResult` がすべて `PASSED` です。続いて以下を実行します。

```sql
CREATE OR REPLACE ICEBERG TABLE my_table (id STRING, value FLOAT)
  CATALOG = 'SNOWFLAKE'
  EXTERNAL_VOLUME = 'fsxn_lakehouse_iceberg_vol'
  BASE_LOCATION = 'my_table/';

COPY INTO my_table
FROM (SELECT $1:id::string, $1:value::float FROM @my_stage/events.json)
FILE_FORMAT = (TYPE = JSON);
```

生成されるのは真の Iceberg テーブル（metadata JSON、manifest Avro、data Parquet）で、
他の Iceberg 対応エンジンからも読めます。

## 書き込み先を分ける理由

別個の2つの問題があり、いずれも実測済みです。

**Access Point へのアンロードはオブジェクトを残します。** `COPY INTO @stage` は
拒否されません。オブジェクトは書き込まれ内容も正常ですが、その後
`Remote upload failed checksum validation` で文が失敗します。FSx for ONTAP が
サーバーサイド暗号化を `aws:fsx` と報告し、これが `AWS_SSE_S3` でも `AWS_SSE_KMS` でも
ないためです。書き込み失敗と伝えられる一方、完全なオブジェクトが残ります。
[BLK-009](./blocker-tracker.md) として記録。

**Delta の書き込みはデータが着地した後、コミットで失敗します。** Access Point は
条件付き書き込みを実装していないため（`If-None-Match` が 501）、`_delta_log` への
コミットが失敗し Parquet ファイルは残ります。リトライごとに孤児が増えます。
[BLK-002](./blocker-tracker.md) として記録。

Athena 経由の Iceberg は例外です。Glue Data Catalog がメタデータのポインタを保持し、
コミットが S3 側の条件付き書き込みを必要としないためです。

過去に Access Point へ書き込みを試したことがある場合は、残骸を洗い出してください。

```bash
./shared/scripts/check_orphaned_unload_objects.py --access-point <AP エイリアス>
```

エンジンの出力ファイルがあるのに完了マーカーが無いプレフィックスを報告します。
ストレージ側から見た「中断された書き込み」の形です。`--delete` の前に必ず確認してください。

## このパターンが向く場合・向かない場合

| 状況 | 適合 | 理由 |
|---|---|---|
| 既存アプリが NAS にファイルを置いており、SQL をかけたい | 良い | 本来の対象。構築・運用するパイプラインが不要 |
| 同一データに複数プロトコル — NFS で書き S3 で読む | 良い | ボリュームは1コピー、Access Point はその view |
| 可能な限り新しいデータが必要 | 良い | 読み取りはボリュームに当たる。同期遅延を考慮する必要がない |
| 形の整ったデータセットへの大規模スキャン | 妥当 | スループットはファイルシステムのプロビジョンド値が上限。サイジングは自分で決められる |
| 同じストレージへのトランザクショナルなテーブル書き込み | 不向き | Delta はコミットできず、アンロードはオブジェクトを残す。標準 S3 へ書く |
| 数百万の小さなファイル | 不向き | オブジェクト単位のオーバーヘッドが支配的。事前に集約するか Parquet で着地させる |
| そもそも NAS 上にデータが無い | 不向き | 既に S3 にあるなら Access Point は経路を1つ増やすだけで利点がない |

率直に言えば、これは既に ONTAP 上にあるデータのコピー工程を省くものです。
データがそこに無いのであれば、標準 S3 のほうが単純な構成です。

## よくある失敗

| 症状 | 原因 | 対処 |
|---|---|---|
| `LIST` は通るが `SELECT` が AccessDenied | ステージに `AWS_ACCESS_POINT_ARN` が無い | 追加する。ステップ3参照 |
| セットアップ直後に全て AccessDenied | 信頼ポリシーがフェーズ1のプレースホルダのまま | `update_trust_policy.sh` を実行 |
| external id を貼った後も AccessDenied | 末尾が `=` の値が途中で切れている | 値全体を再コピー |
| `SYSTEM$VERIFY_EXTERNAL_VOLUME` が `listResult` のみ失敗 | IAM ポリシーのプレフィックスと `STORAGE_BASE_URL` が不一致 | 一致させる |
| Access Point 作成が object storage server に言及して失敗 | その SVM でネイティブ ONTAP S3 が稼働中 | 別の SVM を使う |
| `COPY INTO @stage` が checksum 検証で失敗 | 想定どおり — [BLK-009](./blocker-tracker.md) | Access Point へアンロードしない |
| Snowpipe が発火しない | Access Point は S3 Event Notifications を発行しない（[BLK-003](./blocker-tracker.md)） | `COPY INTO` を実行する Snowflake Task を使う |

## 後片付け

```sql
DROP EXTERNAL VOLUME IF EXISTS fsxn_lakehouse_iceberg_vol;   -- バケット削除より先に
DROP STAGE IF EXISTS my_stage;
DROP STORAGE INTEGRATION IF EXISTS fsxn_s3ap;
```

```bash
aws cloudformation delete-stack --stack-name fsxn-lakehouse-sf-external-volume
aws cloudformation delete-stack --stack-name fsxn-snowflake
aws fsx detach-and-delete-s3-access-point --name my-lakehouse-ap
```

バケットより先に External Volume を削除してください。順序が逆だと、存在しない
ストレージを指すオブジェクトが Snowflake 側に残ります。バケットは
`DeletionPolicy: Retain` なのでスタック削除でテーブルが消えることはありません。
削除する意図があるときに、明示的に空にして削除してください。

## 関連ドキュメント

| ドキュメント | 内容 |
|---|---|
| [互換性マトリクス](./compatibility-matrix.md) | 全エンジン・全フォーマットの検証ステータス |
| [ブロッカートラッカー](./blocker-tracker.md) | 動作しないものとその理由 |
| [未検証項目インベントリ](./unverified-inventory.md) | 未検証のものと、検証に必要なもの |
| [Snowflake 統合](../../integrations/snowflake/README.md) | SQL・Lambda・テストの詳細 |
