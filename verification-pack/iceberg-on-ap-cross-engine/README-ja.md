🌐 **日本語** | [English](README.md)

# エンジン横断の検証計画: Access Point 上の Iceberg を Databricks と Snowflake から読む

この文書は計画であり、結果ではありません。ここにあるケースはまだ 1 件も実行していません。結果は `evidence/<日付>/` に置きます。

## この計画が答える問い

FSx for ONTAP の S3 Access Point 上にデータとメタデータを置いた Iceberg テーブルを AWS Glue Data Catalog に登録したとき、Databricks Unity Catalog と Snowflake から読めるか。読めない場合、原因はカタログか、ストレージ経路か。

リポジトリの記録は、部品ごとに別々の状態です。

| 部品 | 記録上の状態 | 出典 |
|---|---|---|
| Athena が Access Point の alias 上に Iceberg テーブルを作成・書き込み（Glue がカタログ） | 2026-08-06 に実行 | [athena-iceberg の証跡](../athena-iceberg/evidence/2026-08-06/evidence-record.yaml) |
| Snowflake が Storage Integration と External Stage で Access Point のファイルを読む | 2026-05 と 2026-08-06 に実行 | [snowflake の証跡](../snowflake/evidence/2026-08-06/evidence-record.yaml) |
| Snowflake が Glue Iceberg REST と `VENDED_CREDENTIALS` で S3 Tables の Iceberg を読む | 2026-06-05 に実行 | [互換性マトリクス](../../docs/ja/compatibility-matrix.md) |
| Unity Catalog が Access Point の alias に External Location を登録できるが、読み取りは拒否される | 2026-08-12 に実行 | [BLK-001](../../docs/ja/blocker-tracker.md) |
| Access Point 上のテーブルを Glue HMS Federation で Foreign Catalog にする | **未実行** | [実行ガイド](../../integrations/iceberg-metadata-catalog/databricks/foreign-iceberg-execution-guide.md) |
| Access Point 上のテーブルを Snowflake の Catalog Integration（Glue）で読む | **未実行** | [互換性マトリクス](../../docs/ja/compatibility-matrix.md) |
| Access Point の stage で Directory Table を使う | [unstructured-data-access](../../docs/ja/unstructured-data-access.md) に文はあるが、実行記録は見つかっていない | — |

この計画は、「未実行」の 3 行を埋めます。

## 設計: 1 つのテーブル、1 つの対照、2 つのエンジン

どのエンジンも、同じ論理テーブルを 2 回読みます。違いはファイルの置き場所だけです。

| テーブル | 場所 | 目的 |
|---|---|---|
| `xeng_ap.probe` | `s3://<AP_ALIAS>/xeng/probe/`（internet-origin の Access Point） | 対象 |
| `xeng_s3.probe` | `s3://<STANDARD_BUCKET>/xeng/probe/` | 対照: 同じスキーマ、同じ行、標準 S3 |

対照が失敗した場合は設定の誤りで、対象の結果に意味はありません。どのトラックでも、対照の結果を先に記録します。

スキーマは `id int, marker string, ts timestamp` です。`marker` の値が異なる 3 行（`row-a`、`row-b`、`row-c`）を入れ、更新のケース用に後から 4 行目（`row-d`）を入れます。

両方のテーブルを Athena で作ります。Access Point 上での動作が記録済みの経路だからです。

## 前提条件

| 項目 | 要件 |
|---|---|
| ファイルシステム | ONTAP 9.17.1 以降。REST API で確認する（コンソールには出ない） |
| Access Point | internet-origin。Snowflake と Athena は VPC-origin を読めない。Databricks のサーバーレスも VPC の外にある |
| IAM | エンジンごとに 1 ロール。`s3:GetObject`、`s3:ListBucket`、`s3:GetBucketLocation` を **Access Point の ARN** に付与（alias をバケット扱いした ARN だけでは Databricks で失敗する。BLK-001 参照） |
| Glue | 同一リージョンの標準 Glue Data Catalog。`s3tablescatalog` ではない |
| Lake Formation | Snowflake の vended credentials のケース（S3）だけで必要。`register-resource` で Access Point の場所を登録する（2026-05-24 の記録で API が受け付けたことを確認済み） |
| Databricks | ファイルシステムと同一リージョンの、トライアルではないワークスペース。ストレージ資格情報の external ID は Databricks のアカウント UUID。Glue 用のサービス資格情報（IAM ロールは自己引き受け）と、実行中ずっと維持する Lake Formation 権限（一時的にでも失うと、Unity Catalog が foreign catalog のスキーマを削除して作り直す。[Databricks の Glue フェデレーションのページ](https://docs.databricks.com/aws/en/query-federation/hms-federation-glue)による）。DBR 13.3 LTS 以降の標準アクセスモードのコンピュート |
| Snowflake | integration を作成できるロール（`ACCOUNTADMIN` など）のセッション |
| 構文 | 実行前に、Databricks と Snowflake の最新ドキュメントで `CREATE CONNECTION`（Glue）、`CREATE FOREIGN CATALOG`、`CREATE CATALOG INTEGRATION`、`CREATE EXTERNAL VOLUME` を読み直す。両社ともこれらの文を変更する |

**認証情報。** サインインページのスナップショットを取らず、トークンやシークレットを出力しません。`AGENTS.md` の「Browser Automation and Credentials」に従います。

## 準備 S0: テーブルの作成（Athena）

```sql
CREATE DATABASE xeng_ap;
CREATE DATABASE xeng_s3;

CREATE TABLE xeng_ap.probe (id int, marker string, ts timestamp)
LOCATION 's3://<AP_ALIAS>/xeng/probe/'
TBLPROPERTIES ('table_type'='ICEBERG');

CREATE TABLE xeng_s3.probe (id int, marker string, ts timestamp)
LOCATION 's3://<STANDARD_BUCKET>/xeng/probe/'
TBLPROPERTIES ('table_type'='ICEBERG');

INSERT INTO xeng_ap.probe VALUES (1,'row-a',current_timestamp),(2,'row-b',current_timestamp),(3,'row-c',current_timestamp);
INSERT INTO xeng_s3.probe VALUES (1,'row-a',current_timestamp),(2,'row-b',current_timestamp),(3,'row-c',current_timestamp);
```

合格条件: `xeng_ap.probe` と `xeng_s3.probe` の `SELECT marker` が、どちらも `row-a`、`row-b`、`row-c` を返すこと。2 つのテーブルの Glue `metadata_location` を保存します。各エンジンが読みに行く先が分かります。

## トラック D: Databricks Unity Catalog

最初に D0 を実行します。BLK-001 は 2026-08-12 の記録で、その後に修正された可能性があります。

| ID | ケース | 手順 | 記録する内容 |
|---|---|---|---|
| D0 | BLK-001 の再確認 | Access Point の alias にストレージ資格情報、External Location、External Volume を作成し、volume に `list_files` を実行 | 成功、または 403 の文面。成功したなら D2 も成功する可能性が高い |
| D1 | 対照: `xeng_s3` の Foreign Catalog | 接続タイプ Hive Metastore、メタストアタイプ AWS Glue の接続を、サービス資格情報で作成。`s3://<STANDARD_BUCKET>/xeng/` に External Location。`authorized_paths` と、**カタログ自身に設定したストレージ上の場所**を指定した foreign catalog（Databricks は Iceberg の読み取りに必須としており、メタストアの root を継承するだけでは足りない）。続けて `SHOW SCHEMAS`、`SHOW TABLES`、`SELECT marker` | 行の集合。`row-a..c` であること |
| D2 | 対象: `xeng_ap` の Foreign Catalog | D1 と同じ手順で、`authorized_paths` に Access Point の alias を指定。5 つの文を 1 つずつ実行 | **最初に失敗した文**（接続、External Location、foreign catalog、`SHOW TABLES`、メタデータの `SELECT`、データの `SELECT` のどれか）。エラー文は原文のまま |
| D3 | 更新 | Athena から `row-d` を挿入。更新前に `SELECT COUNT(*)`、次に `REFRESH FOREIGN TABLE`、もう一度 `SELECT COUNT(*)` | 各段階の件数。D1 で実行し、D2 が読める場合は D2 でも実行 |
| D4 | Unity Catalog の外 | インスタンスプロファイルを付けた Spark クラスタで、クラスタ単位に Glue カタログを設定し、`xeng_ap.probe` を読む | 成功か失敗か。成功すれば、データは読め、止まっているのは Unity Catalog 経路だけだと分かる。この経路ではガバナンスは効かない |

D2 で有用なのは、どの層で失敗するかです。BLK-001 は、データの読み取りがセッションポリシーのエラーで失敗すると予測しています。その手前のカタログ手順が成功するかどうかは、どこにも記録がありません。

## トラック S: Snowflake

| ID | ケース | 手順 | 記録する内容 |
|---|---|---|---|
| S1 | 対照: `xeng_s3` の Glue Catalog Integration | `CREATE CATALOG INTEGRATION`（`ICEBERG_REST`、`AWS_GLUE`、`SigV4`、`VENDED_CREDENTIALS`）、返された external ID での信頼ポリシー更新、`SYSTEM$VERIFY_CATALOG_INTEGRATION`、`CREATE ICEBERG TABLE ... CATALOG_TABLE_NAME`、`SELECT` | 行の集合。雛形: [snowflake-setup.sql](../../integrations/iceberg-metadata-catalog/snowflake/etl-standard-glue-path/snowflake-setup.sql) |
| S2 | 対象: External Volume 方式 | `ACCESS_DELEGATION_MODE = EXTERNAL_VOLUME_CREDENTIALS`（既定）の Catalog Integration。`STORAGE_BASE_URL = 's3://<AP_ALIAS>/xeng/'` **と `STORAGE_AWS_ACCESS_POINT_ARN`** を指定した `CREATE EXTERNAL VOLUME`（`CREATE EXTERNAL VOLUME` のリファレンスは、基底 URL が Access Point の alias の場合に必須と記載）。Iceberg のデータとメタデータのファイルは基底 URL の配下に置く。`SYSTEM$VERIFY_EXTERNAL_VOLUME`。`EXTERNAL_VOLUME` と `CATALOG_TABLE_NAME = 'probe'` を指定した Iceberg テーブル。`SELECT` | volume 検証の結果（書き込みを試すため、BLK-009 は Access Point への書き込みがチェックサム検証で失敗すると予測している）と、その後も読み取りが成立するか。実行後に `check_orphaned_unload_objects.py` を実行 |
| S3 | 対象: vended credentials 方式 | Lake Formation に `s3://<AP_ALIAS>/xeng/` を登録。integration ロールに `xeng_ap.probe` の `SELECT` を付与。S1 と同じ Catalog Integration を `xeng_ap` に向ける。`SELECT` | Lake Formation が Access Point の場所に認証情報を払い出すか。払い出さない場合はエラー文 |
| S4 | 更新 | Athena から `row-d` を挿入。`ALTER ICEBERG TABLE ... REFRESH`、または `AUTO_REFRESH` を待つ。件数を数える | `row-d` が見えるまでの秒数。S2 または S3 で読めた方式ごとに記録 |

## トラック U: 非構造化ファイル

非構造化ファイルはカタログのテーブルではなく、パスで到達します。カタログに関する問いは、ファイルメタデータのテーブルが指すパスを各エンジンが開けるか、になります。

| ID | ケース | 手順 | 記録する内容 |
|---|---|---|---|
| U1 | Snowflake の Directory Table | Access Point の alias を指す stage を `DIRECTORY = (ENABLE = TRUE)` で作成。`ALTER STAGE ... REFRESH`。`SELECT * FROM DIRECTORY(@stage)` | オブジェクト数に対する行数と、更新の挙動（Access Point はイベント通知を出さない。BLK-003） |
| U2 | Iceberg の一覧テーブルから `TO_FILE` までのパス | `xeng_ap.files(path string, size bigint)` に、Access Point 配下の 2 オブジェクトを指す 2 行を挿入。Snowflake で stage と結合し、`TO_FILE` または `PARSE_DOCUMENT` を呼ぶ | テーブル → パス → ファイルの連鎖が最後まで動くか |
| U3 | 同じ一覧からの Databricks のパス | D1 で `xeng_s3.files` を読み、Access Point のパスに `read_files` または `FILE EXTERNAL` を実行 | D0 の結果に従う見込み。`FILE EXTERNAL` は Unity Catalog の volume が必要なので、D0 が失敗する間は止まる |

## 結果の読み方

| 結果 | 解釈 |
|---|---|
| D1 と S1 が成功、D2 がデータ読み取りで失敗、S2 または S3 が成功 | 制限は、Access Point のパスに対する Unity Catalog のセッションポリシーにある。カタログの置き場所は関係しない |
| D2 がデータ読み取りより前（接続、External Location、foreign catalog）で失敗 | BLK-001 に加えて、カタログ側の制限がある |
| D2 が成功 | BLK-001 はこの経路では成立しない。ブロッカー一覧を更新する |
| S2 が volume の書き込み検証で失敗し、読み取りは成功 | 読み取り経路は動く。読み取り専用ロールを分け、検証手順は省く |
| S2 と S3 がともに失敗し、D4 が成功 | Snowflake の Catalog Integration が Access Point 上で止まるのは、カタログではなくストレージ層 |
| D1 または S1 が失敗 | 設定の誤り。直して再実行し、対象については何も記録しない |

これらの結果が出て初めて、エンジンごとに S3 Tables や標準 S3 の Iceberg への変換が必要か、Access Point 上のまま使えるかを、リポジトリとして言えます。S3 Tables はこの計画では試しません。Databricks が内部バケットを登録できないことは、すでに記録されているためです（B-10）。

## この計画のために調べた先行事例

Snowflake と Databricks のドキュメント、ベンダーのガイド、公開ブログを検索しました。FSx for ONTAP の S3 Access Point 上にある Iceberg テーブルを、カタログ経由でどちらかのエンジンから読んだ資料は見つかりませんでした。あるのは次のものです。

| 出典 | 内容 | この計画での使い方 |
|---|---|---|
| [Snowflake: Glue Iceberg REST の Catalog Integration](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-glue)と [vended credentials](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-vended-credentials) | 標準 S3 バケット。テーブルのファイルは 1 テーブルにつき 1 バケットに置く。テーブルを作成するまで権限は検証されない | S1 の雛形。対照の根拠 |
| [Snowflake のガイド: Iceberg と AWS Glue](https://www.snowflake.com/en/developers/guides/data-lake-using-apache-iceberg-with-snowflake-and-aws-glue/) | 標準 S3 上の Glue と Lake Formation による認証情報の払い出し | S1 と S3 の手順の順序 |
| [Snowflake の `CREATE EXTERNAL VOLUME`](https://docs.snowflake.com/en/sql-reference/sql/create-external-volume) | Access Point の alias は `STORAGE_AWS_ACCESS_POINT_ARN` で指定できる | S2 のパラメータ。見つかった資料では、FSx for ONTAP に対して実行した例はない |
| [Databricks: AWS Glue の Hive metastore federation](https://docs.databricks.com/aws/en/query-federation/hms-federation-glue) | 標準 S3。authorized paths、Iceberg 用のカタログのストレージ上の場所、サービス資格情報、Lake Formation 権限の継続 | D1 の雛形 |
| [AWS: Databricks Unity Catalog へのフェデレーション](https://aws.amazon.com/blogs/big-data/access-databricks-unity-catalog-data-using-catalog-federation-in-the-aws-glue-data-catalog/) | 逆向き。標準 S3 | 下の対象外 |
| 同じ題材の dev.to の記事（[Snowflake](https://dev.to/aws-builders/snowflake-and-fsx-for-ontap-s3-access-points-from-access-denied-to-working-external-tables-9k8)、[Databricks](https://dev.to/aws-builders/databricks-and-fsx-for-ontap-s3-access-points-a-layer-by-layer-validation-of-observed-boundaries-p4d)） | Access Point 上の stage と External Location。セッションポリシーの ARN 不一致 | ブロッカー一覧と同じ証跡 |
| [AWS re:Post のスレッド](https://repost.aws/pt/questions/QUmbYyURiVSzu4tdccXuLqvQ/hive-unknown-error-invalid-port-in-file-system-location) | テーブルの場所に Access Point の **ARN** を指定すると、Athena が `Invalid port in file system location` で拒否する | S0 では ARN ではなく alias をテーブルの場所にする |

上の Snowflake の記事は、条件付き書き込みがないため Access Point 上の Iceberg テーブルは「そのままでは不向き」と書いています。この文は書き込みについてのものです。このリポジトリの 2026-08-06 の Athena の実行は Iceberg を Access Point 上に書き込めており、この計画は読み取りだけなので矛盾はしませんが、記事の書き方は根拠より広く読めます。

対象を扱った資料がないため、標準 S3 の対照（D1、S1）は上記のベンダー文書に従い、対象のケース（D2、S2、S3）は新規の測定になります。

## 費用

下の単価は、このアカウントの過去の実行で記録した AWS Pricing API の値（ap-northeast-1、2026-10-26 取得）とベンダーのページによります。実行前に再確認してください。価格は変わります。

| 項目 | 根拠 | 2〜4 時間の実行 1 回の見積り |
|---|---|---|
| FSx for ONTAP ファイルシステム | 既存のファイルシステム（Single-AZ、128 MBps、SSD 1,024 GiB、稼働中）を再利用。数 GiB の使い捨てボリュームはプロビジョン済み容量の内側に収まる | 増分なし。常時の課金（GB-月あたり $0.150、MBps-月あたり $0.906 で 1 時間あたり約 $0.37）はすでに発生している |
| Access Point | Pricing API では未確認。実行前に確認する | 未確認。小額と仮定 |
| Athena | スキャン TB あたり $5.00、1 クエリ最低 10 MB | 約 50 クエリで $0.01 未満 |
| S3 標準バケット（対照） | GB-月あたり $0.025 | $0.01 未満 |
| Glue Data Catalog | メタデータオブジェクト 1,000,000 件とリクエスト 1,000,000 件までは月ごとに無料 | $0 |
| Lake Formation | 権限に個別の課金なし | $0 |
| Snowflake | X-Small ウェアハウス、1 時間 1 クレジット、秒課金（起動ごとに最低 60 秒）、自動停止 | 最大 2〜4 クレジット。ドル換算はアカウントの契約単価による |
| Databricks | サーバーレス SQL ウェアハウス。DBU 課金。1 DBU の定価は製品、プラン、リージョンで異なり、ap-northeast-1 の確認済みの値は見つかっていない | ウェアハウスのサイズと DBU 単価は、実行前にワークスペースで確認する。自動停止は 5 分にする。D4 は従来型クラスタを追加し、EC2 も課金される |
| エンジン間のデータ転送 | テーブルは数 KB | 無視できる |

AWS 側の増分はほぼありません。確認すべき費用は 2 つのベンダーの請求で、どちらも、このリポジトリが持たない契約条件に依存します。

**費用の上限対策。** ケースの合間はウェアハウスを停止したままにします。同じ日のうちに止めて撤去します。使い捨てのボリュームと Access Point を残さないでください。ファイルシステムの常時課金はどちらでも変わりませんが、S2 で残る Snowflake 側の孤立オブジェクトは、費用がかからないまま後の実行を失敗させる唯一の残りです。

## 対象外

- AWS ブログにある逆向き（Glue が Unity Catalog **へ**フェデレーションし、AWS のエンジンが Unity Catalog のテーブルを読む構成）。対象は Unity Catalog 管理のストレージで、Access Point ではない。必要なら別に実施する
- 書き込み経路。Foreign Iceberg テーブルは Databricks から読み取り専用で、Access Point への unload は BLK-009
- 性能。テーブルは 1 桁の行数

## 想定する失敗

| 失敗 | 対策 |
|---|---|
| S2 の書き込み検証の失敗後、Snowflake が Access Point にオブジェクトを残す | 孤立オブジェクトの検査を実行し、残りを削除する |
| 「未対応」に見えるが、実際は ARN か external ID の誤りである 403 | IAM ポリシーに Access Point の ARN を使う。Databricks の external ID はアカウント UUID。残りは D1 で見つかる |
| Athena が、エンジンの解釈できない形のパスをメタデータに書く | S0 で `metadata_location` を保存し、各エンジンの報告と比べる |
| トライアルまたは制限付きの Databricks ワークスペース | BLK-001 のときと同様に、トライアルではないワークスペースを使う |
| 実行中の認証切れ | `aws sso login` を依頼して待つ |

## 証跡と撤去

- `verification-pack/templates/evidence-record.yaml` を `evidence/<日付>/evidence-record.yaml` にコピーする。記録は 1 つで、ケース ID ごとに 1 ブロック。生の出力は `evidence/<日付>/raw/` に置く
- コミット前に、アカウント ID、ワークスペース URL、Access Point の alias、名前をプレースホルダーに置き換える。リポジトリの gitleaks と PII の検査を実行する
- 撤去の順序: Snowflake の integration、volume、テーブル → Databricks の catalog、connection、External Location、volume、資格情報 → Lake Formation の登録 → Glue のデータベース → Access Point（Amazon FSx の API で削除する。Access Point が付いたボリュームは ONTAP からは削除できない）→ 使い捨てのボリューム → 標準バケット。何かを削除する前に `raw/` を書き出す
- ケースごとに、成功、最初に失敗した文つきの失敗、未実行のいずれかで報告する。未実行のケースを隣のケースから推測しない
