🌐 [English](../en/known-challenges.md) | **日本語**

# 既知の課題（起因レイヤー別）

> 2026-08-06 時点、[`verification-pack/`](../../verification-pack/) の記録に基づいて整理。
> 本ページは既知の問題を**どこに起因するか**でグループ化しています。それによって
> 誰が修正できるのか、回避策が成立しうるのかが決まるためです。
>
> 関連ページ: [ブロッカートラッカー](./blocker-tracker.md)は動作しないことが判明している事項。
> [未検証項目インベントリ](./unverified-inventory.md)は未テストの事項。
> [互換性マトリクス](./compatibility-matrix.md)はエンジン別のリファレンス。
> 本ページはそれらを結びつける分析です。

## レイヤーで分ける理由

「FSx for ONTAP S3 Access Points は Lakehouse 書き込みに対応していない」— この主張は
本リポジトリではもう成立しません。Athena + Glue Data Catalog 経由の Iceberg 書き込みは
エンドツーエンドで動作します（2026-08-06 検証済み）。Delta Lake 書き込みは動作しません。
どちらも同一の Access Point に対する操作です。

違いはストレージではありません。**テーブルフォーマットがコミットのポインタをどこに
保持するか**です。Iceberg はカタログに保持するため、コミットは Glue 側の条件付き更新に
なります。Delta はオブジェクトストア上の `_delta_log` に保持するため、コミット自体が
オブジェクトストアへの条件付き書き込みを必要とし、HTTP 501 が返ります。

この区別はレイヤー別に整理して初めて見えてきます。エンジン別に並べると、無関係な
失敗の羅列に見えます。

| レイヤー | 変更できる主体 | ここに起因する問題 |
|---|---|:---:|
| 1. Access Point が提供する S3 API 面 | AWS（NetApp と共同） | 8 |
| 2. ONTAP に対する FSx マネージドサービス境界 | AWS | 3 |
| 3. テーブルフォーマット仕様 | Apache / Delta プロジェクト | 2 |
| 4. エンジン実装 | 各エンジンベンダー | 7 |
| 5. ネットワーク経路 | 導入側の設計 | 2 |
| 6. ガバナンス面 | AWS / プラットフォームベンダー | 2 |

---

## レイヤー 1 — Access Point が提供する S3 API 面

Access Point の実装と Amazon S3 の実装との差分です。エンジン側の設定では回避できません。

| # | 差分 | 観測された挙動 | 下流への影響 | 回避策 |
|---|---|---|---|---|
| 1.1 | 条件付き書き込み（`If-None-Match`） | HTTP 501 `NotImplemented`。製品レベルの制約として確認（2026-05-22） | Delta Lake と Hudi のコミットが不可能。カタログがポインタを保持する場合の Iceberg は影響を受けない | Athena + Glue 経由の Iceberg、または標準 S3 への書き込み |
| 1.2 | アップロードのチェックサムがレスポンスに返らない | AWS が明記している挙動。汎用バケットと異なり、チェックサム値は「オブジェクトメタデータおよびオブジェクト自体として FSx for NetApp ONTAP ボリュームに保存されない」ため「チェックサム値はレスポンスに返らない」。ETag も MD5 ダイジェスト**ではない**と明記されている。計算したチェックサムをレスポンスと照合するクライアントはこの手順を完了できず、**書き込みが完了した後に**失敗する | Snowflake `COPY INTO @stage` が、完全なオブジェクトを残したまま失敗する（[BLK-009](./blocker-tracker.md)）。エラー文は暗号化タイプ（`aws:fsx` は `AWS_SSE_S3` でも `AWS_SSE_KMS` でもない）を指すが、これは機構ではなく対処のヒント | Access Point へアンロードしない |
| 1.3 | S3 Event Notifications | 発行されない | Snowpipe 自動取り込み不可、Auto Loader 通知モード不可、EventBridge トリガー不可 | DataSync → 標準 S3、スケジュールポーリング、または ONTAP ネイティブ監査ログ。**FPolicy は代替になりません**（AP 経由の書き込みは通知されません。実測 2026-08-26 / ONTAP 9.18.1P3D1） |
| 1.4 | オブジェクトバージョニング | 非対応。`ListObjectVersions` は `VersionId="null"` を返す | S3 ネイティブのバージョン履歴がない | ポイントインタイム復旧には ONTAP Snapshot |
| 1.5 | 単一アップロード上限 50 GB | これを超えるオブジェクトはダウンロードは可能だがアップロードは不可。マルチパートは対応 | 大容量オブジェクトの書き込みにはマルチパートが必要 | 出力ファイルを分割。スキャン効率の観点でも 128〜256 MB を目標にする |
| 1.6 | Lifecycle ポリシー、Object Lock、S3 Select、クロスリージョンレプリケーションなし | 非対応 | 保持期間や階層化を S3 の語彙で表現できない | FabricPool 階層化、SnapLock、S3 Select の代わりにクエリエンジン |
| 1.7 | 同一リージョン・同一アカウント必須 | Access Point はファイルシステムと同居する必要がある | クロスアカウント／クロスリージョンの Access Point 構成が組めない | ストレージ層ではなく分析層で共有する |
| 1.8 | 署名付き URL は公式には非対応 | 実際には動作する。署名付与はクライアント側の計算であり、サーバーには通常の署名付きリクエストとして見えるため。AWS は非対応と記載しており、安定性を保証していない | これに依存した実装はサポート外 | 本番で依存しない |

**最小バージョン**: Access Point 自体は ONTAP 9.17.1、マルチパートアップロードは 9.16.1。

> **1.1 と 1.2 の組み合わせについて**: この2つが、クリーンな拒否ではなく残留物を生む
> 差分です。[部分書き込みハザード](#部分書き込みハザード2つの原因1つの症状)を参照。

---

## レイヤー 2 — ONTAP に対する FSx マネージドサービス境界

ONTAP は実装しています。FSx for ONTAP が公開していません。機能は製品には存在するが
マネージドサービスには存在しない、という形の制約です。

| # | 差分 | 観測された挙動 | 影響 |
|---|---|---|---|
| 2.1 | SnapMirror S3 が無効化されている | `snapmirror object-store show` → `"object-store" is not a recognized command`（admin / advanced / diagnostic の全権限レベルで同じ）。`/api/cloud/targets` → `not authorized for that command`。ONTAP 9.17.1P6 で確認。`Continuous` SnapMirror ポリシーはシステム上に存在するが参照できない | ONTAP ネイティブの S3 レプリケーションが使えない。AWS DataSync（NFS → S3）が唯一の検証済み同期手段。オンプレミス ONTAP は 9.10.1+ で対応しているため、これを前提とした移行計画は見直しが必要 |
| 2.2 | SVM あたり object-store サーバーは1つ | Access Point が既にある SVM で `vserver object-store-server create` → `Only one object store server is supported per Vserver`。Access Point は `show` に表示されない内部 object-store サーバーを設置する | 1つの SVM で Access Point と ONTAP ネイティブ S3 バケットを併存させられない。タイミングの問題ではなく構造的な制約。別 SVM を使う |
| 2.3 | ネームサービススタックが S3 データパス上にある | SVM に AD 参加用の DNS サーバーが設定されており、それが到達不能になると、**その SVM 上の全 Access Point がタイムアウトする**。ボリュームが UNIX セキュリティスタイルで、エクスポートポリシーが緩く、Access Point のライフサイクルが `AVAILABLE` であっても発生する | 無関係な AD / DNS 障害が S3 ストレージ障害として現れる。切り分けが誤ったレイヤーに向かう。[ネットワーキング考慮事項](./fsx-ontap-s3ap-networking.md)を参照 |

---

## レイヤー 3 — テーブルフォーマット仕様

ここに FSx for ONTAP の不具合はありません。各フォーマットがコミットをどう定義しているか
と、差分 1.1 との相互作用の結果です。

| フォーマット | コミット機構 | Access Point 上での結果 | ステータス |
|---|---|:---:|---|
| Apache Iceberg | 現行メタデータのポインタをカタログが保持。コミットは Glue 内のアトミック更新 | ✅ 動作 | 2026-08-06 に Athena + Glue で検証: CREATE、INSERT、UPDATE、DELETE、タイムトラベル、`OPTIMIZE`、`VACUUM`、同時2コミットがすべて成功。データとメタデータの双方が Access Point 上 |
| Delta Lake | コミットログをオブジェクトストア上の `_delta_log/` に保持。put-if-absent が必要 — ログファイルは未存在の場合にのみ作成されなければならない | ❌ **既定構成では**失敗 | 初回コミットファイルで `Server returned non-2xx status code: 501 Not Implemented`（delta-rs 1.2.1、2026-05-23）。読み取りパスは正常に動作。後述の `S3DynamoDBLogStore` に関する注記（本プロジェクトでは未検証）を参照 |
| Apache Hudi | タイムラインがアトミックリネーム（`.inflight` → `.commit`）を要求 | ❓ **未テスト** | 記録されている結論は、Delta の結果と Hudi のアーキテクチャからの推論であり、実測ではない。EMR での実行を試みたが、EMR 7.1.0 の既定構成に Hudi カタログプラグインがなく実行に至っていない。UNV-023 として管理 |

> Hudi は、本ドキュメント内で実測していない結論を記載している唯一の項目です。同じ
> アトミックリネーム要件、同じ欠落プリミティブという論理は妥当ですが、推論です。
> 推論として明記しています。

### Delta Lake: put-if-absent という要件と外部化の成立

「Delta はここに書き込めない」は過大に読まれやすいため、節を分けて記載します。

Delta が必要としているのは S3 の条件付き書き込みそのものではありません。コミットファイルに
対する put-if-absent です。Delta プロジェクトは 2019 年からこの要件を示しています。
[delta-io/delta#39](https://github.com/delta-io/delta/issues/39) は、S3 ファイルシステムが
「put if absent を実行する手段を提供しないため、複数の同時ライターが同一バージョンファイルを
容易に複数回コミットしうる」と記録しています。
[マルチクラスタ書き込みの記事](https://delta.io/blog/2022-05-18-multi-cluster-writes-to-delta-lake-storage-in-s3/)は、
コミットを「既に存在しない場合にのみ」ログファイルを作成する操作として説明しています。

Amazon S3 は
[2024年8月](https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-s3-functionality-conditional-writes/)に
`If-None-Match` の条件付き書き込みを獲得し、FSx for ONTAP S3 Access Points はパリティに
達していません。しかし Delta は同じ問題に対する別の答えを2年早く出しています。
**`S3DynamoDBLogStore`** です。Delta Lake 1.2 で追加され、put-if-absent の判定を
オブジェクトストアに依存せず DynamoDB の条件付き書き込みへ移します
（[ストレージ構成](https://docs.delta.io/latest/delta-storage.html)）。

これは Iceberg が Glue Data Catalog で使っているのと構造的に同じ手法であり、だからこそ
ここで Iceberg の書き込みが動作します。したがって正確な記述は次のとおりです。

| 構成 | 本プロジェクトでの状態 |
|---|---|
| `s3a://` 上の既定 `LogStore` | ❌ 失敗を実測 — コミットファイルで 501 |
| DynamoDB コミットテーブルを用いた `S3DynamoDBLogStore` | ❓ **未検証。** 機構上は Access Point への条件付き書き込みを必要としないはず。未実行のため主張しない |
| `AWS_S3_ALLOW_UNSAFE_RENAME=true` を設定した `delta-rs` | ❓ 未検証。かつ "unsafe" と名付けられている理由がある。同時実行の保護を提供するのではなく取り除くもの。使うとしても単一ライターのみ |

中段が実測されるまで、Access Point 上の Delta 書き込みは実務上利用不可として扱ってください。
これを記録する意図は、上限が未試行の構成であって、証明された不可能性ではないという点にあります。

---

## レイヤー 4 — エンジン実装

同じ Access Point、同じ S3 API に対する結果です。各エンジンのクライアント実装が
Access Point エイリアスをどう扱うか、あるいはストレージとは無関係な制約に起因します。

| # | エンジン | 問題 | 症状（原文） | 回避策 |
|---|---|---|---|---|
| 4.1 | EMR Serverless（Iceberg 書き込み） | S3FileIO がメタデータ書き込み時に Access Point エイリアスを処理できない | `java.lang.NullPointerException: Cannot invoke "org.apache.iceberg.TableMetadata.metadataFileLocation()" because "metadata" is null` | Iceberg 書き込みには Athena を使う。同じテーブルフォーマットが成功する |
| 4.2 | Databricks Unity Catalog | 登録は成功する。通らないのは読み取りで、Unity Catalog が払い出す down-scoped セッションポリシーがバケット形式 ARN で書かれているため（2026-08-12 自環境で実証） | `CREATE TABLE` で `UC_CLOUD_STORAGE_ACCESS_FAILURE` | DataSync → 標準 S3 → External Location（[BLK-001](./blocker-tracker.md)） |
| 4.3 | Databricks Unity Catalog | `iceberg_rest` が Connection Type として受け付けられず、S3 Tables を Foreign Catalog として参照できない | `CONNECTION_TYPE_NOT_SUPPORTED`（2026-05-31） | Glue HMS Federation（`CREATE CONNECTION TYPE glue`）が GA の経路 |
| 4.4 | Databricks Runtime | ランタイムの seccomp プロファイルが `mount` / `umount` を禁止しており、クラスタから NFS/SMB をマウントできない | — | 意図的なセキュリティ設計であり解消は見込まれない。ネットワーク経路を使う |
| 4.5 | Snowflake | Dynamic Table が External Table を参照できない | `Object ref EXT_FMT_JSON of type EXTERNAL_TABLE not supported in Dynamic Table definition` | 先に `COPY INTO` で標準テーブルへ着地させ、その上に Dynamic Table を定義する。2026-08-06 に動作確認済み |
| 4.6 | Snowflake | ステージのテーブル関数形式ではインラインの `FILE_FORMAT` が受け付けられない | — | 名前付き `FILE FORMAT` オブジェクトを使う。Access Point の制約ではなく Snowflake の構文 |
| 4.7 | ClickHouse | `s3()` が STS セッショントークンを受け取れず、一時credentialsを使えない | `UNKNOWN_SETTING: s3_session_token is neither a builtin setting`（v26.5.1） | IAM ユーザーの長期キー、または IMDS 経由の EC2 インスタンスプロファイル |
| 4.8 | Databricks FILE 型（β） | `FILE EXTERNAL` は Unity Catalog Volume 内のファイルしか参照を保存できず、UC External Volume は Access Point 上に作成できないため、ONTAP 常駐ファイルをコピーなしに参照できない | —（構造的制約。ランタイムエラーではなく文書化された制限） | `FILE MANAGED`（バイト列を UC 管理ストレージへコピー）。ただしその場合オブジェクトタグは読めなくなる。[評価](./databricks-file-type-evaluation.md) |
| 4.9 | Access Point のオブジェクトタグ | U+0100 以上のタグキー / 値は大半の文字列で拒否されるが一部は受理される。文字列ごとに決定的だが、外部から規則を導出できない | `InvalidTag: The TagValue you have provided is invalid` | オブジェクトタグは ASCII に限定し、ローカライズされたテキストはメタデータテーブルに置く。ONTAP の不具合として公開済み（[CONTAP-771956](https://kb.netapp.com/on-prem/ontap/da/S3/S3-Issues/CONTAP-771956)、[自環境の実測](../../verification-pack/s3ap-object-tagging/evidence/2026-08-12/evidence-record.yaml)） |

### Access Point の問題ではないが、そう見えるもの

| 症状 | 実際の原因 |
|---|---|
| Athena と DuckDB では読める Parquet を Spark / Glue / EMR が読めない | ナノ秒タイムスタンプ。pandas と DuckDB `COPY TO` は既定で `TIMESTAMP(NANOS)` を出力し、Spark 3.3+ はこれを拒否する。エンジン横断で使うデータはマイクロ秒で生成する |
| 同一データで Redshift Serverless が Athena より遅い | Serverless のコールドスタート。500万行で 4,277 ms 対 2,196 ms（2026-05-23） |

---

## レイヤー 5 — ネットワーク経路

いずれも導入側の設計判断であり、サービスの不具合ではありません。着手初日に最も
遭遇しやすい失敗のため記載しています。

| # | 問題 | 機構 | 解決 |
|---|---|---|---|
| 5.1 | VPC 内のコンピュートが Internet Origin の Access Point に対してタイムアウトする | エイリアスは `s3-r-w.<region>.amazonaws.com` に解決されるが、これは S3 Gateway Endpoint が使う S3 プレフィックスリストに含まれない場合がある。Gateway Endpoint がトラフィックを捕捉し、ルーティングに失敗する | コンピュートを VPC 外に配置、NAT Gateway 経由にする、または VPC Origin の Access Point + S3 Interface Endpoint を使う |
| 5.2 | Athena、EMR Serverless、Redshift Spectrum は VPC Origin の Access Point を使えない | 導入側 VPC の外にある AWS マネージドインフラで動作するため | これらのエンジンには Internet Origin の Access Point が必要 |

> **`HeadBucket` はヘルスチェックにならない。** ファイルシステム層に触れずに S3 層で
> 成功するため、データ操作が失敗する状況でも 200 を返します。`ListObjectsV2 --max-keys 1`
> で確認してください。

---

## レイヤー 6 — ガバナンス面

| # | 問題 | 影響 | 回避策 |
|---|---|---|---|
| 6.1 | S3 Tables のフェデレーテッドカタログに対して Lake Formation の列レベル権限が未実装 | テーブルレベルの許可は機能するが、列マスキングは機能しない | 列レベル制御が必要なテーブルは、汎用 S3 上の通常の Glue Catalog テーブルに配置する |
| 6.2 | Unity Catalog のガバナンスが Access Point 上のデータに届かない | リネージ、タグ、マスク、行フィルターが FSx for ONTAP のデータに直接適用できない。4.2 の帰結 | DataSync → 標準 S3 → External Location。得られるガバナンスに対して、転送とストレージで概算 $27/月/TB のコストがかかる |

---

## 部分書き込みハザード：2つの原因、1つの症状

運用上の影響が最も大きい発見であり、2つの原因が別のレイヤーにあるため見落としやすい
ものです。

どちらも同じ形をとります。**ステートメントは失敗を報告し、完全または部分的な
オブジェクトが Access Point 上に残る。**

| 原因 | レイヤー | 残るもの |
|---|---|---|
| Delta のコミットが 501 に当たる（差分 1.1） | 1 | Delta は Parquet を先に書きコミットを後に行うため、`_delta_log` のないデータファイルが残る。リトライごとに増える。2026-08-06 に観測: 4つのプレフィックスに孤児データファイル、1つには1分間隔で書かれた3ファイル |
| アンロードがチェックサム検証に失敗する（差分 1.2） | 1 | 完全で妥当なオブジェクト。実測値: 25 バイト、gzip として妥当、内容も正しい、`ServerSideEncryption: aws:fsx`。ステートメントは 479 ms で失敗 |

失敗したステートメントを「何も起きていない」と扱う呼び出し側は、どちらのケースでも
誤ります。以下で残留物を掃き出せます。

```bash
./shared/scripts/check_orphaned_unload_objects.py --access-point <alias>
```

完了マーカー（`_SUCCESS`、`_delta_log/`、`_committed_*`）を持たないエンジン出力の
プレフィックスを報告します。これは中断された書き込みのストレージ側から見た署名です。

> Snowflake ステージに `ENCRYPTION=(TYPE='AWS_SSE_S3')` を設定しても 1.2 は解決しません。
> 即時失敗がハングに置き換わるだけです。2分54秒でキャンセル、何も書かれませんでした。

---

## 取り下げた主張

本リポジトリが以前行っていた主張のうち、実測に耐えなかったものです。取り下げも結果で
あるため記録しています。

| 主張 | 何が起きたか |
|---|---|
| ListObjectsV2 はネイティブ S3 の 30〜80 倍遅い | 2026-08-05 に再測定: 10〜5,000 オブジェクトで **0.9〜1.4 倍**。フラット構成とネスト構成のいずれも同様。30〜80 倍は再現せず、元の数値の出所も特定できなかった。単一ディレクトリで 5,000 を超える場合の挙動は未測定であり、ONTAP はディレクトリエントリをメモリ上でソートするため、ファイル集約とパーティション構造は設計上の妥当な実践として残る。ただし小規模での実測ペナルティを根拠とはしない |
| Snowflake の外部ステージは設計上読み取り専用である | 誤りであり、1.2 を隠していた。書き込みは拒否されない。着地した後に検証で失敗する |
| Access Point 上での Iceberg 同時書き込みは破損リスクがある | 実測ではなく推論だった。Athena の同時2コミットは正しい行数を返し、更新の喪失もなかった。2ライター試験は同時実行の上限を示すものではないが、リスクが categorical ではないことは示している |

---

## 現在の知見の境界

未テストは22件あります。[未検証項目インベントリ](./unverified-inventory.md)を参照。
検証済みの結果をどう読むべきかに最も影響する3件は以下です。

| 未確認事項 | なぜ重要か |
|---|---|
| Iceberg と Snowflake の全結果が1桁の行数で実施されている | 現実的なテーブルサイズでのマニフェスト増加、コンパクションコスト、パーティション進化が未測定（UNV-021） |
| Athena 同時実行試験はキャッシュに収まる規模だった | 25/25 のクエリが成功しフルスキャンは約2倍に劣化したが、128 MBps でプロビジョニングされたファイルシステムに対して集計約 389 MB/s が流れている。キャッシュが大きく効いている。これは同時実行が25までは失敗要因にならないという証拠であり、スループットモデルではない（UNV-022） |
| Hudi は一度も実行されていない | レイヤー3を参照 |

---

## 他ページとの読み分け

| 知りたいこと | 参照先 |
|---|---|
| 特定のエンジンと操作が動作するか | [互換性マトリクス](./compatibility-matrix.md) |
| 特定の既知の失敗のステータスと回避策 | [ブロッカートラッカー](./blocker-tracker.md) |
| 何がテストされていないか、実施に何が必要か | [未検証項目インベントリ](./unverified-inventory.md) |
| そもそもこのパターンが適合するか | [導入評価ガイド](../adoption-guide/adoption-assessment-ja.md) |
