🌐 [English](../en/snowpipe-verification-results.md) | **日本語**

# Snowpipe + FSx for ONTAP S3 Access Point — 検証結果

**測定日**: 2026-08-05（AWS 側・ListObjectsV2）および 2026-08-06（Snowflake 側） | **リージョン**: ap-northeast-1

本ドキュメントは、FSx for ONTAP S3 Access Point から Snowflake へデータを取り込む
経路について、実際に測定できたこと、そして同じく重要な**測定できていないこと**を
記録します。本リポジトリでこれまで引用してきた数値のいくつかにエビデンス記録が
存在せず、そのうち1件は再現しなかったため作成しました。

生エビデンス:

- [ListObjectsV2 レイテンシ 2026-08-05](../../../../verification-pack/s3ap-list-latency/evidence/2026-08-05/benchmark-result.yaml)
- [Pattern A AWS 側 2026-08-05](../../../../verification-pack/snowpipe-pattern-a/evidence/2026-08-05/aws-side-verification.yaml)
- [Pattern A Snowflake 側 2026-08-06](../../../../verification-pack/snowpipe-pattern-a/evidence/2026-08-06/snowflake-side-verification.yaml)

---

## エグゼクティブサマリ

**Snowpipe は定期実行できません。** Snowpipe は設計上イベント駆動であり、「5分ごとに
Snowpipe を実行する」という選択肢は存在しません。FSx for ONTAP S3 Access Point からの
定期取り込みは **Snowflake Task による COPY INTO** で行います。これは別の機能です。

一方でイベント駆動の取り込みは、合成通知を用いる方式で E2E の動作を確認できました。
ただし4つの条件が同時に成立する必要があり、かつ**どこにもエラーが出ない失敗モード**が
存在します。

| 取り込み経路 | 状況 | エビデンス |
|---|:---:|---|
| **実際の** S3 イベントによる Snowpipe auto-ingest | ❌ 不可 | FSx for ONTAP S3 AP は S3 Event Notifications を発行しない（[BLK-003](../../../../docs/ja/blocker-tracker.md)） |
| **合成通知**による Snowpipe auto-ingest | ✅ **検証済み** | [2026-08-06](../../../../verification-pack/snowpipe-pattern-a/evidence/2026-08-06/snowflake-side-verification.yaml) test_08 — COPY_HISTORY が pipe 名でロードを記録 |
| **Task + COPY INTO（定期実行）** | ✅ **検証済み** | [2026-08-06](../../../../verification-pack/snowpipe-pattern-a/evidence/2026-08-06/snowflake-side-verification.yaml) test_04 |
| Task + `ALTER EXTERNAL TABLE ... REFRESH` | ✅ 検証済み | External Table 読み取りを 2026-05-24 に検証 |
| Pattern A: Lambda ポーリング → SNS → Snowpipe | ✅ 条件付きで検証済み | 両半分にエビデンスあり。下記2つの Pattern A セクション参照 |
| Pattern B: FPolicy → Lambda → SNS → Snowpipe | ⚠️ 設計のみ | Snowflake 側は Pattern A と同一で検証済み。FPolicy をイベント源とする部分は live 検証なし |
| Snowpipe REST API（`insertFiles`） | ⚠️ 未検証 | 選択肢として記載があるだけ |

**選び方**。定期取り込みであれば Task + COPY INTO の方が単純です。合成通知が不要で、
SNS トピックポリシーの保守も不要で、ポーリング窓では実現できない exactly-once 性を
Snowflake 自身のロード履歴が担保します。Snowpipe 経路は、運用の単純さより検知
レイテンシが重要な場合に選択してください。合成通知はロード完了まで約 0.5 秒でした
（Task はスケジュール間隔に律速されます）。

> **サイレント失敗の警告**: 合成通知の `s3.bucket.name` がステージ URL のバケット
> 文字列と一致しない場合、Snowpipe はメッセージを受信した上で破棄します。
> `SYSTEM$PIPE_STATUS` にも `COPY_HISTORY` にもエラーは出ません。この状態の pipe は
> 完全に正常に見えながら、何もロードしません。本経路の監視は、pipe のエラーを見る
> のではなく、Access Point 上のオブジェクト数と Snowflake にロードされた行数を
> 突き合わせる必要があります。

---

## 訂正: 「ListObjectsV2 が 30-80 倍遅い」という数値について

本リポジトリではこれまで十数箇所で、FSx for ONTAP S3 Access Point に対する
ListObjectsV2 がネイティブ S3 より **30-80 倍遅い**と記載していました。この数値を
再測定した結果、**再現しませんでした**。

median、データ点ごとに記録試行5回、warm-up 1回は破棄、計測範囲はページネーションされた
ListObjectsV2 ループのみ:

| オブジェクト数 | FSx for ONTAP S3 AP | ネイティブ S3 | 比率 |
|--------:|--------------------:|----------:|------:|
| 10 | 38 ms | 27 ms | 1.4x |
| 100 | 52 ms | 39 ms | 1.3x |
| 1,000 | 162 ms | 128 ms | 1.3x |
| 5,000 | 665 ms | 704 ms | 0.9x |

ネスト構造（2階層・leaf あたり10オブジェクト、日付パーティション相当）でも
1,000件で 1.4倍、5,000件で 1.0倍で、フラット構造と有意な差はありませんでした。

**この結果が意味すること、しないこと。** 測定した規模では Access Point はネイティブ
S3 の概ね 1.4倍以内に収まり、本ブロッカーに当初記録されていた性能目標（100ファイル
未満で1秒未満、1,000ファイル未満で3秒未満）の範囲内でした。ただしリスティングが
無制限にスケールすることを意味しません。測定は 5,000 オブジェクトで打ち切っており、
単一ディレクトリに数十万〜数百万オブジェクトある場合の挙動は未検証です。小ファイルの
統合とキー空間のパーティション化という設計指針は、その理由により引き続き有効です。

30-80 倍という数値の出自は特定できていません。比較対象となるエビデンス記録が残って
いないため、特定の原因に帰属させず「未解明」として記録します。考えられる要因としては、
CLI ラッパー経由での測定（短時間の呼び出しではプロセス起動時間が支配的になる）、
当時ファイルシステムが劣化状態にあった、当時から現在までのプラットフォーム側の
変更などがあります。

> **リクエストコストに関する補足**: `MaxKeys=1000` 指定時、ネイティブ S3 は1回の API
> 呼び出しで 1,000 キーを返しましたが、Access Point は2回必要でした（5,000件では
> 6回対5回）。実時間は同等なのでボトルネックではありませんが、API コストの試算時や、
> ページネーション深度に上限があるクライアントを使う場合に、リクエスト数が同一である
> と前提しないでください。

再現方法:

```bash
python3 shared/scripts/benchmark_list_objects.py \
  --ap-arn arn:aws:s3:<region>:<account>:accesspoint/<ap-name> \
  --native-bucket <comparison-bucket> \
  --counts 10,100,1000,5000 --trials 5 --layout flat --teardown
```

---

## Pattern A の AWS 側: Lambda ポーリング → SNS

Pattern A は、S3 Event Notifications が使えないことへの回避策として、スケジュール実行
される Lambda が Access Point をリストし、S3 イベント形式の通知を合成して SNS に
publish します。その後 Snowflake が自身のマネージド SQS キューをそのトピックに
サブスクライブし、pipe がキューから消費します。

### 合格した項目

| 手順 | 結果 |
|---|---|
| Access Point への PutObject（74バイト） | 716〜805 ms |
| ポーラー Lambda の ListObjectsV2 による検知 | 実時間 981 ms |
| SNS publish と配信 | サブスクライブした SQS キューでメッセージを捕捉して確認 |
| ファイル書き込み → 通知到達 | **2.1 秒** |
| Access Point のアドレッシング | `Bucket` パラメータには ARN・alias の両方が使える。AP ARN に対して付与した IAM 権限は alias 経由のリクエストも認可する |

2.1 秒には EventBridge のスケジュール待ちを含みません。実運用の検知遅延は
（スケジュール間隔）＋約2秒なので、`rate(5 minutes)` なら最大約5分です。

### AWS 側で発見した欠陥

| ID | 深刻度 | 内容 |
|---|---|---|
| DEFECT-1 | High | `snowpipe-lambda/template.yaml` が実 handler ではなくプレースホルダー関数をデプロイする |
| DEFECT-2 | High | ポーリング窓より古いオブジェクトが恒久的に通知されない（データ損失） |
| DEFECT-3 | Medium | 合成通知に、実 S3 イベントが持つフィールドの欠落がある |
| DEFECT-4 | **High**（Medium から引き上げ） | AP ARN を設定すると `s3.bucket.name` に ARN が入る。2026-08-06 に Snowpipe 側でサイレントな破棄を起こすことを確認（下記 DEFECT-B 参照） |
| DEFECT-5 | Low | 窓の重複により、既に通知済みのオブジェクトを再通知する |
| DEFECT-6 | Low | ポーラーに DLQ もエラーアラームもない |

**DEFECT-1** — テンプレートのインライン `Code.ZipFile` の本体は
`return {"statusCode": 200, "body": "Deploy handler.py"}` です。公開されている
テンプレートをそのままデプロイすると、何もリストしないポーラーができます。
`handler.py` はインラインのサイズ上限を超えるため単に貼り付けることはできず、実際の
パッケージング手順が必要です。テンプレートは `Transform: AWS::Serverless-2016-10-31`
を宣言していますが SAM リソースを定義していないため、この Transform は現状無効です。

**DEFECT-2** — `STATE_TABLE` が未設定の場合、cutoff は
`now - POLLING_INTERVAL_MINUTES` であり、この cutoff が実時間に追従するため、窓より
古いオブジェクトは二度と参照されません。再現結果: 05:07:52Z に書き込んだオブジェクトが、
cutoff 05:08:33Z の 05:09:33Z 実行から不可視（`new_files_found=0`）である一方、同じ
プレフィックスへの ListObjectsV2 ではオブジェクトの存在が確認できました。悪化要因として、
`template.yaml` は `STATE_TABLE` パラメータを一切公開していないため、CloudFormation で
デプロイしたポーラーは必ずこの損失モードで動作し、`handler.py` の DynamoDB チェック
ポイント経路は公開テンプレート経由では到達不能です。

**DEFECT-3 / DEFECT-4** — 合成されるレコードは `eventVersion`, `eventSource`,
`eventName`, `eventTime`, `s3.bucket.name`, `s3.object.key`, `s3.object.size` のみを
持ちます。実際の S3 通知はこれに加えて `awsRegion`, `s3.s3SchemaVersion`,
`s3.configurationId`, `s3.bucket.ownerIdentity`, `s3.bucket.arn`, `s3.object.eTag`,
`s3.object.sequencer` を持ちます。また `handler.py` は `S3_ACCESS_POINT_ALIAS` を
そのまま `s3.bucket.name` にコピーするため、AP ARN を与えるとバケット名の位置に ARN が
出力されます。

---

## Pattern A の Snowflake 側: 合成通知による COPY 発火の成立

AWS 側の記録が残していた決定的な問いです。実際の Snowflake アカウントに対して検証し、
**答えは「発火する」**でした。ただし4つの条件が全て成立する場合に限ります。

### 4つの必須条件

| # | 条件 | 満たさない場合 |
|---|---|---|
| 1 | 外部ステージに `AWS_ACCESS_POINT_ARN` を設定する | `LIST` は成功するが読み取りが全て失敗: `Failed to access remote file: access denied` |
| 2 | pipe に `AWS_SNS_TOPIC = '<topic ARN>'` を設定する | 使用可能なサブスクリプションが存在せず、pipe に何も届かない |
| 3 | SNS トピックポリシーで Snowflake の IAM ユーザーに `sns:Subscribe` を許可する | Snowflake 自身の subscribe 呼び出しが拒否される |
| 4 | ペイロードの `s3.bucket.name` を AP の **alias** にする（ARN ではない） | メッセージは受信された上でサイレントに破棄される |

### 合格した項目

| テスト | 結果 |
|---|---|
| `integrations/snowflake/template.yaml` によるストレージ統合と二段階 IAM 信頼 | PASS — 記載どおりに動作 |
| `AWS_ACCESS_POINT_ARN` **あり**のステージから 5行読み取り | PASS、1.7 秒 |
| AP ステージからの `COPY INTO` | PASS — 2ファイル5行、`SUM(amount)` がソースの計算と一致 |
| AP ステージで `AUTO_INGEST = TRUE` が受理される | PASS — Snowflake がマネージド SQS チャネルを払い出した。pipe 作成時点で FSx for ONTAP バックエンドを理由に拒否される要素はない |
| `AWS_SNS_TOPIC` 付き pipe → Snowflake が自身のキューをサブスクライブ | PASS — トピックに確定済みサブスクリプション ARN が出現 |
| **合成通知 → COPY 発火** | **PASS** — 受信 01:55:30.721Z、取り込み 01:55:31.211Z（約 0.5 秒）。`COPY_HISTORY`: `events_003.json \| Loaded \| rows=1 \| pipe=EVENTS_PIPE_SNS \| errors=0` |

### 2件の失敗と、そこから分かること

**Snowflake のキューを自前でサブスクライブすることはできません。**
`aws sns subscribe --protocol sqs --notification-endpoint <Snowflake の SQS ARN>` は
`pending confirmation` を返し、`PendingConfirmation` のまま確定しません。このキューは
Snowflake 自身の AWS アカウントにあり、自分が開始していないサブスクリプションを確認
応答しません。この点が重要なのは、[イベント駆動アーキテクチャ](../../../../docs/ja/event-driven-architecture.md)
および `06_snowpipe.sql` のヘッダーコメントに描かれた `... → SNS → Snowflake SQS → Snowpipe`
という図が、パイプラインがそのキューに直接 push するかのように読めるためです。実際は
そうではありません。サブスクリプションは、`AWS_SNS_TOPIC` を伴う `CREATE PIPE` の実行時に
Snowflake が作成します。`06_snowpipe.sql` の SQL 自体は既に正しく、誤解を招くのは
散文の側です。

> **順序に関する落とし穴**: SNS はサブスクリプションを (protocol, endpoint) で重複排除
> します。同じ Snowflake キューに対する `PendingConfirmation` のエントリが残っていると
> Snowflake 自身の subscribe が阻害され、`CREATE PIPE` は成功しながら使用可能な
> サブスクリプションが存在しない状態になります。事前にサブスクライブしないでください。
> 既に停留エントリがある場合、実 ARN を持たないため `sns unsubscribe` では削除できません。
> トピックを削除して作り直してください。

**バケット名の不一致はサイレントに失敗します。** 同じペイロードで `s3.bucket.name` を
alias ではなく Access Point の ARN にして publish した結果、
`lastReceivedMessageTimestamp` は進み（メッセージは到達）、
`lastForwardedMessageTimestamp` は変化せず（転送されなかった）、行数は変わらず、
`SYSTEM$PIPE_STATUS` にも `COPY_HISTORY` にもエラーは出ませんでした。本ドキュメントで
最も運用上危険な発見です。

### Snowflake 側で発見した欠陥

| ID | 深刻度 | ファイル | 内容 |
|---|---|---|---|
| DEFECT-A | High | `sql/02_external_stage.sql` | 全ステージが `AWS_ACCESS_POINT_ARN` なしで作成され、読み取りが全て失敗する |
| DEFECT-B | High | `snowpipe-lambda/handler.py` | `s3.bucket.name` を環境変数から検証なしで取得しており、ARN が入るとサイレントな破棄を招く |
| DEFECT-C | Medium | `shared/cloudformation/fpolicy-routing.yaml` | `sns:Subscribe` の許可が `aws:SourceArn` を条件にしているが、Snowflake の直接呼び出しでは同キーが存在せず、この statement は何も許可しない |
| DEFECT-D | Low | `fpolicy-routing.yaml`, `snowflake/template.yaml` | 両方が `sns:Receive` を列挙しているが、これは有効な SNS アクションではない（cfn-lint W3037） |
| DEFECT-E | Medium | `integrations/snowflake/template.yaml` | SNS トピックポリシーがデプロイ元アカウントの root にフォールバックし、Snowflake がサブスクライブできないトピックができる |

**DEFECT-A の影響が最大です。** `LIST` が通るためスクリプトは成功したように見え、
失敗は実際にバイトを読む時にしか現れません。External Table、`COPY INTO`、Snowpipe は
いずれもバイトを読みます。`02_external_stage.sql` より後ろの番号付き SQL ファイルは
全て、壊れたステージを引き継ぎます。

**DEFECT-C の詳細** — `aws:SourceArn` は、AWS サービスがリソースに代わって呼び出す
場合にのみ設定されます。Snowflake は IAM ユーザーとして `sns:Subscribe` を直接呼び出す
ため同キーは存在せず、条件は成立しません。同ファイルには IAM ユーザーを Principal に
指定した正しい `AllowSnowflakeIAMUserSubscribe` statement が既にあり、機能するのは
そちらです。

### 未検証のまま残っている点

- Snowpipe がペイロードのどのフィールドを必須とし、どれを無視するか。意図的に変えたのは
  `s3.bucket.name` のみで、他のフィールドは常に完全な形で送信しました。
- 同一の合成通知が複数回配信された場合の挙動。
- チャネルのバックログを発生させる規模の通知量での挙動。
- EventBridge ベースの Snowpipe 経路が合成イベントを同様に受理するか。
- Pattern B の FPolicy イベント源。Snowflake 側は Pattern A と同一で検証済みですが、
  FPolicy → Lambda は live で動かしたことがありません。

---

## すべての経路に共通する制約

| 制約 | 影響 |
|---|---|
| S3 Event Notifications なし | 実イベントによる auto-ingest と `AUTO_REFRESH` が利用不可。合成通知が必要（[BLK-003](../../../../docs/ja/blocker-tracker.md)） |
| `AUTO_REFRESH` なし | External Table / Directory Table のメタデータは明示的な `REFRESH` が必要（通常 Task で駆動） |
| 条件付き書き込みなし | Iceberg / Delta の書き戻しがブロックされる（[BLK-002](../../../../docs/ja/blocker-tracker.md)） |
| サイズ上限は 2 つある | 単一の `PutObject`（および 1 つの `UploadPart`）は 5 GiB 水準、オブジェクト全体は 50 GiB 水準。これを超えるファイルはマルチパートアップロードが必要で、オブジェクト全体の超過は `CompleteMultipartUpload` の時点で初めて検出される（**全バイトを転送し終えた後**）。[詳細](../../../../docs/ja/compatibility-matrix.md#上限に対するパートサイズの余裕) |
| ステージに `AWS_ACCESS_POINT_ARN` が必須 | 設定しないと `LIST` は成功したまま読み取りが失敗する。誤解を招く部分的成功 |
| AP ステージで `TO_FILE()` 非対応 | Vision AI には `COPY FILES` によるステージング手順が必要 |
| Snowflake の公式サポート対象外 | Snowflake は FSx for ONTAP S3 Access Point を External Stage のバックエンドとして文書化していません。読み取り・取り込み・ガバナンス経路は本書で検証済みですが、本番利用前に Snowflake サポートへ確認してください |

> **Dynamic Table に関する補足**: External Table を source とする Dynamic Table は
> `REFRESH_MODE = FULL` が必要（増分リフレッシュは change tracking を要求し、External
> Table はこれを提供しない）で、`TARGET_LAG` の最小値は 60 秒です。また `AUTO_REFRESH`
> が使えないため、前段で External Table のメタデータをリフレッシュする Task が依然として
> 必要です。

---

## 関連ドキュメント

- [Snowflake 統合 README](../../README.md) — 検証状況と選択指針
- [Snowpipe 統合ガイド](./snowpipe-integration.md) — 3つの候補パターン
- [内部テーブル取り込みガイド](./internal-table-ingestion-guide.md) — Task + COPY INTO と Dynamic Table のパターン
- [ブロッカートラッカー](../../../../docs/ja/blocker-tracker.md) — BLK-003 と BLK-006
- [イベント駆動アーキテクチャ](../../../../docs/ja/event-driven-architecture.md) — FPolicy 経路の設計目標値
- [互換性マトリクス](../../../../docs/ja/compatibility-matrix.md) — 制約の全リスト
