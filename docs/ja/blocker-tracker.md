🌐 [English](../en/blocker-tracker.md) | **日本語**

# ブロッカー追跡ダッシュボード

> 本ページは動作**しない**ことが判明している事項を追跡します。単に未テストである主張については [未検証項目インベントリ](./unverified-inventory.md) を参照してください。同じブロッカーを起因レイヤー別に整理したものは [レイヤー別の既知の課題](./known-challenges.md)を参照してください。

> **目的**: FSx for ONTAP × Lakehouse 統合における既知のブロッカーと制約のステータスを一元管理する Living Document。
> **最終更新**: 2026-06-20
> **更新頻度**: 四半期ごと、または重大なステータス変更時に随時更新

---

## サマリ（全ブロッカー一覧）

| ID | ブロッカー | 影響範囲 | ステータス | 回避策有無 |
|:---:|---|---|:---:|:---:|
| BLK-001 | UC の資格情報払い出しが S3 AP の読み取りを認可しない（登録は通る） | Databricks UC ガバナンス | ❌ 未解決 | ✅ あり |
| BLK-002 | Conditional Writes 非サポート | Delta Lake 書き込み（Athena 経由の Iceberg は影響なし） | ❌ 未解決 | ✅ あり |
| BLK-003 | S3 Event Notifications 非サポート | Auto Loader 通知モード / Snowpipe | ❌ 未解決 | ✅ あり |
| BLK-004 | SnapMirror S3 が FSx for ONTAP で無効化 | ONTAP ネイティブ S3 レプリケーション | ❌ 未解決 | ✅ あり |
| BLK-005 | `iceberg_rest` Connection Type 未サポート | UC Foreign Catalog × S3 Tables | ❌ 未解決 | ⚠️ 部分的 |
| BLK-006 | ListObjectsV2 レイテンシ（30-80x は撤回、実測 1.3〜1.4 倍） | 大規模ディレクトリスキャン | ⚠️ 範囲縮小 | ✅ あり |
| BLK-007 | NFS/SMB マウントが seccomp でブロック | Databricks からの直接ファイルシステムアクセス | ❌ 設計上不可 | ✅ あり |
| BLK-008 | Lake Formation 列レベル制御が S3 Tables 非対応 | S3 Tables フェデレーテッドカタログのガバナンス | ❌ 未解決 | ⚠️ テーブルレベルのみ |
| BLK-009 | S3 AP へのアンロードが checksum 検証で失敗し、オブジェクトが残る | Snowflake `COPY INTO @stage`（および AP への任意のアンロード） | ❌ 未解決 | ✅ あり |

---

## 詳細

### BLK-001: UC の資格情報払い出しでは通らない S3 AP の読み取り

| 属性 | 値 |
|------|---|
| **影響サービス** | Databricks Unity Catalog |
| **影響機能** | S3 AP 上の External Location / External Table / External Volume に対する**読み取り** / **`FILE EXTERNAL` 列（FILE 型、β）**。登録そのものは影響を受け**ない** — [影響範囲の訂正](#影響範囲の訂正-2026-08-12-登録の成立と読み取りの不成立)を参照 |
| **根本原因** | Unity Catalog が資格情報を払い出す際に付与する down-scoped セッションポリシーが**バケット形式 ARN**（`arn:aws:s3:::<alias>`）で書かれている一方、AWS はアクセスポイント経由のリクエストを**アクセスポイント ARN** に対して認可評価する。両者は一致せず、セッションポリシーはロールポリシーと積集合を取るため、ロール本体が許可していてもセッション内で拒否される |
| **確認日** | 2026-05-26（Databricks Support が根本原因を提示）。2026-08-12（本リポジトリ）ネイティブ S3 のコントロール付きで機構を直接実証 |
| **ステータス** | ❌ 未解決 — **かつ 2026-08-12 まで影響範囲の記述が誤っていた**: 登録は成功し、読み取りが失敗する |
| **解除条件** | ロケーション URL がアクセスポイントのエイリアスである場合に、Unity Catalog が down-scoped セッションポリシーへアクセスポイント ARN 形式（`arn:aws:s3:<region>:<account>:accesspoint/<name>` および `.../object/*`）を出力すること |
| **影響度** | **Critical** — UC ガバナンス（lineage, tags, masks, row filters）を FSx for ONTAP データに直接適用できない |
| **利用者側の回避策** | **なし。** セッションポリシーは Unity Catalog が生成するため、こちら側の IAM ポリシーやネットワーク変更では広げられない |
| **報告経路** | サポートケースではなく本ドキュメントに記録している。当アカウントには Help Center のアクセス権がない（2026-08-12 に確認。2026-05 のケースも同じ理由でクローズ）。発見がサポート経路に依存しないよう、再現可能な形で書いている |

**回避策（推奨パス）**:
1. **DataSync → 標準 S3 → UC External Location** — 推奨。フルガバナンス適用可能。[詳細](./datasync-to-s3-guide.md)
2. **Kafka → Structured Streaming → UC Delta** — リアルタイム要件時。[詳細](./kafka-clickhouse-unity-catalog-connectivity.md)
3. **Glue/EMR ETL → 標準 S3 → UC** — バッチ変換時

**エビデンス**: [integrations/databricks/README.md](../../integrations/databricks/README.md)

> **影響の限定**: このブロッカーは「ゼロコピーのガバナンス適用」をブロックしますが、DataSync パスで S3 にコピーすれば UC のフルガバナンスは適用可能です。コピーコスト（~$27/月/TB）対ガバナンス価値のトレードオフで判断してください。

#### 影響範囲の訂正 2026-08-12: 登録の成立と読み取りの不成立

本ブロッカーは「UC External Location が S3 AP を非サポート」と記録していた。ファイルシステムと同一アカウント・同一リージョンに専用の非トライアルワークスペースを作って計測した結果、この記述は誤りである。

| 手順 | 結果 |
|---|---|
| IAM ロールによる `CREATE STORAGE CREDENTIAL` | ✅ |
| `s3://<AP エイリアス>/` に対する `CREATE EXTERNAL LOCATION`（`skip_validation=False`） | ✅ — UC 自身の読み書き検証を通過 |
| そのロケーション上の `CREATE EXTERNAL VOLUME` | ✅ |
| 経由での読み取り（`read_files` / `list_files` / `to_file` / `dbutils.fs.ls`） | ❌ 403 / AccessDenied |

ここまで到達するには IAM 側で 2 点が必要で、どちらかを誤ると「S3 AP 非対応」に見える 403 が出る。

1. Storage Credential の External ID は **Databricks アカウント UUID** であって metastore ID ではない
2. IAM 権限ポリシーは**アクセスポイント ARN** を参照する必要がある。エイリアスをバケット名とした ARN のみでは失敗する（AWS CLI ではエイリアス形式で成功するにもかかわらず）

読み取りの失敗はサーバーレス SQL でもクラシック DBR 18.2 クラスターでも同一で、さらに **Databricks の外**でも再現する。Unity Catalog が払い出した資格情報を作業端末から使うと同じ拒否が起きる。原因は AWS のエラー本文が名指ししている。

```
is not authorized to perform: s3:ListBucket on resource:
"arn:aws:s3:<region>:<account>:accesspoint/<name>"
because no session policy allows the s3:ListBucket action
```

途中で排除した仮説（再検証不要）: UC の Volume 権限、IAM ロールの権限、存在しないキーへの HEAD のステータスコード、`x-amz-expected-bucket-owner`、S3 エンドポイントのホスト名、compute role の権限（クラシッククラスターには既定の AWS 資格情報が存在しない）、Databricks 管理 VPC が作成する S3 Gateway エンドポイント。

**FILE 型における重み。** `FILE EXTERNAL` は UC Volume を要し、S3 AP 上の UC Volume は作成できても読めないため、ONTAP 常駐ファイルに対する `FILE EXTERNAL` は依然として成立しない。`FILE MANAGED` はバイト列を UC 管理ストレージにコピーする。したがって本件の解消は、従来の表形式ガバナンスに加えて「NAS 上に留まるデータに対するガバナンス下のマルチモーダル AI」をもたらす。

エビデンス: [evidence-record-tokyo.yaml](../../verification-pack/databricks/file-type/evidence/2026-08-12/evidence-record-tokyo.yaml)。
再現手順: [検証ランブック](./databricks-verification-runbook.md)（IAM ロールをデプロイし、ネイティブ S3 のコントロール付きで比較を実行する）。
`_object_metadata` 経路を含む完全な分析: [databricks-file-type-evaluation](./databricks-file-type-evaluation.md)。

---

### BLK-002: Conditional Writes 非サポート

| 属性 | 値 |
|------|---|
| **影響サービス** | FSx for ONTAP S3 Access Points |
| **影響機能** | Delta Lake のトランザクショナル書き込み。Hudi は未テスト。**カタログがポインタを管理する Iceberg は影響を受けない** — 下記スコープ参照 |
| **根本原因** | FSx for ONTAP S3 AP が `If-None-Match` ヘッダーを実装していない（HTTP 501 返却） |
| **確認日** | 2026-05-22（AWS Support 確認、プロダクトレベルの制限） |
| **ステータス** | ❌ 未解決 — Feature Request 提出済み |
| **解除条件** | AWS が FSx for ONTAP S3 AP に conditional writes を実装（S3 ネイティブ 2024-08 parity） |
| **影響度** | **Medium** — 2026-08-06 に範囲を縮小。Delta Lake の書き込みは不可だが、Athena 経由の Iceberg 書き込みは動作。読み取りは影響なし |

**実測スコープ（2026-08-06）**

| テーブルフォーマット / エンジン | 書き込み | 理由 |
|---|:---:|---|
| Delta Lake（エンジン問わず） | ❌ | コミットログがオブジェクトストア上の `_delta_log` に存在するため、コミット自体が conditional write を必要とする |
| Iceberg（Athena + Glue Catalog） | ✅ | 現行メタデータのポインタを Glue が保持。コミットは S3 ではなく Glue 側の条件付き更新になる。INSERT、UPDATE、DELETE、タイムトラベル、`OPTIMIZE`、`VACUUM`、および 2 件の同時コミットがすべて成功 |
| Iceberg（EMR Serverless） | ❌ | 別要因で失敗: メタデータ書き込み時に S3FileIO が Access Point エイリアスを処理できない（NullPointerException） |
| Hudi | ❓ | 未テスト |

「Iceberg の並行書き込みはデータ破損リスクがある」という従来の記述は実測ではなく推論であり、撤回します。

**失敗した Delta 書き込みはデータファイルを残します。** 2026-08-06 に検証用 Access Point で
確認: 4 つのプレフィックスに `_delta_log` を伴わない Delta データファイルが存在し、
うち 1 つには 1 分間隔で書かれた 3 つのデータファイルが残っていました。Delta は先に
Parquet を書き、後からコミットするため、コミットが 501 で失敗してもデータファイルは残ります。
リトライごとに孤児が増えます。

これは [BLK-009](#blk-009-s3-access-point-へのアンロードにおける-checksum-検証の失敗とオブジェクトの残留)
と原因は異なりますが、残骸の形は同じです。以下で洗い出せます:

```bash
./shared/scripts/check_orphaned_unload_objects.py --access-point <alias>
```

このスクリプトは、エンジンの出力ファイルがあるのに完了マーカー
（`_SUCCESS`、`_delta_log/`、`_committed_*`）が無いプレフィックスを報告します。
ストレージ側から見た「中断された書き込み」の形です。
Athena での 2 件の同時コミットは行数が正しく、ロストアップデートも発生しませんでした。ただし小規模なテストであり、並行性が原理的に危険ではないことを示すにとどまり、並行数の上限を示すものではありません。

**Delta Lake の回避策**:
1. **読み取り専用で利用** — Athena / Glue / Snowflake からの読み取りは正常動作
2. **書き込み先は標準 S3** — DataSync → 標準 S3 → Delta 書き込み
3. **Iceberg を使う** — Athena と Glue Catalog の組み合わせなら Access Point 上に直接書き込める

**エビデンス**: [Athena Iceberg 検証](../../verification-pack/athena-iceberg/evidence/2026-08-06/evidence-record.yaml) · [互換性マトリクス](./compatibility-matrix.md)（Lakehouse テーブルフォーマットへの影響セクション）

> **S3 parity ロードマップ**: S3 ネイティブに conditional writes が追加されたのは 2024-08 です。FSx for ONTAP S3 AP への追加は AWS の開発ロードマップ次第ですが、parity 達成は合理的な期待です。タイムラインは未公開。

---

### BLK-003: S3 Event Notifications 非サポート

| 属性 | 値 |
|------|---|
| **影響サービス** | FSx for ONTAP S3 Access Points |
| **影響機能** | Databricks Auto Loader（通知モード）、Snowflake Snowpipe auto-ingest、EventBridge 連携 |
| **根本原因** | FSx for ONTAP S3 AP が S3 Event Notifications（s3:ObjectCreated 等）を発行しない |
| **確認日** | 2026-05-22（API ドキュメント + 実環境検証） |
| **ステータス** | ❌ 未解決 — Feature Request 提出済み |
| **解除条件** | AWS が FSx for ONTAP S3 AP に Event Notifications を実装 |
| **影響度** | **Medium** — イベント駆動パイプラインが直接構築できない。スケジュールベースの代替は可能 |
| **回避策の検証状況** | Lambda ポーリング → SNS の AWS 側は検証済み（欠陥 6 件あり）。Snowflake 側（合成通知の受理）は未検証。[Snowpipe 検証結果](../../integrations/snowflake/docs/ja/snowpipe-verification-results.md) |

**回避策**:
1. ~~**FPolicy → Lambda → S3**~~ — **無効。** AP 経由の書き込みは FPolicy 通知を発火しないため、この経路では 1 件も流れません（実測 2026-08-26 / ONTAP 9.18.1P3D1）。書き込みが NFS / SMB 経由のボリュームでのみ有効です。[詳細](./datasync-to-s3-guide.md)（FPolicy 代替パターンセクション）
2. **DataSync → 標準 S3** — 標準 S3 に同期後、Event Notifications を利用
3. **Auto Loader リスティングモード** — ディレクトリスキャンで検知（ListObjectsV2 レイテンシの影響あり）
4. **スケジュールポーリング** — EventBridge schedule で定期クロール

> **FPolicy は S3 Access Point 経由の書き込みを検知しません**: 実測 2026-08-26 / ONTAP 9.18.1P3D1。FPolicy の event が受け付けるプロトコルは cifs / nfsv3 / nfsv4 のみで、`mandatory` 指定でも AP 経由の操作は遮断されません。書き込みが NFS / SMB 経由の場合に限り FPolicy → Lambda は技術的に有効ですが、運用複雑性が高い（Lambda 同時実行制限、DLQ、バックプレッシャー）。DataSync スケジュール（rate(5 minutes)）で許容できる場合はそちらを優先してください。

---

### BLK-004: SnapMirror S3 が FSx for ONTAP で無効化

| 属性 | 値 |
|------|---|
| **影響サービス** | FSx for ONTAP |
| **影響機能** | ONTAP S3 バケット → AWS S3 のネイティブレプリケーション |
| **根本原因** | FSx for ONTAP がサービスレベルで SnapMirror S3 コマンドをブロック |
| **確認日** | 2026-05-26（CLI + REST API 両方で確認） |
| **ステータス** | ❌ 未解決 — Feature Request 提出済み |
| **解除条件** | AWS が FSx for ONTAP で SnapMirror S3 を有効化 |
| **影響度** | **Medium** — DataSync で代替可能だが、ONTAP ネイティブの効率的なレプリケーションが使えない |

**回避策**:
- **AWS DataSync** — FSx for ONTAP NFS → S3 の唯一の検証済みマネージド同期メカニズム。[詳細](./datasync-to-s3-guide.md)

**エビデンス**: [verification-pack/snapmirror-s3/evidence/2026-05-26/evidence-record.yaml](../../verification-pack/snapmirror-s3/evidence/2026-05-26/evidence-record.yaml)

> **オンプレミスとの差異**: オンプレミス ONTAP では SnapMirror S3 は利用可能です（9.10.1+）。FSx for ONTAP 固有の制限であり、オンプレミス→クラウドの移行計画では注意が必要です。

---

### BLK-005: `iceberg_rest` Connection Type 未サポート

| 属性 | 値 |
|------|---|
| **影響サービス** | Databricks Unity Catalog |
| **影響機能** | UC Foreign Catalog × S3 Tables Iceberg REST endpoint |
| **根本原因** | Databricks SQL Warehouse が `iceberg_rest` を Connection Type として認識しない |
| **確認日** | 2026-05-31（`CONNECTION_TYPE_NOT_SUPPORTED` エラー確認; ケースクローズ — サポートティア不足により資格なし） |
| **ステータス** | ❌ 未解決 — サポートケースクローズ（資格なし）; プラットフォームレベルでの解決待ち |
| **解除条件** | Databricks が `iceberg_rest` を UC Connection Type として GA サポート |
| **影響度** | **Medium** — S3 Tables / S3 Metadata の Iceberg テーブルを UC から直接参照できない |

**回避策**:
1. **Databricks Spark クラスターで手動カタログ設定** — クラスタースコープで `spark.sql.catalog.s3tables` を設定（UC ガバナンス外）
2. **Glue HMS Federation（推奨）** — `CREATE CONNECTION TYPE glue` で Glue Federated Catalog 経由で S3 Tables Iceberg テーブルを Foreign Catalog として参照。UC ガバナンス適用可能。[検証ガイド](../../integrations/iceberg-metadata-catalog/databricks/foreign-iceberg-execution-guide.md)
3. **Athena / EMR 経由でクエリ** — AWS ネイティブエンジンは `s3tablescatalog` 経由で正常動作
4. **通常 S3 上の Iceberg テーブル** — S3 Tables を使わず通常 S3 バケットに Iceberg テーブルを作成し、Glue Catalog 経由で UC に公開（最も確実）

**エビデンス**: [互換性マトリクス](./compatibility-matrix.md)（S3 Tables Iceberg REST Endpoint セクション）

> **二重ブロッカー**: S3 Annotations 評価の案3（annotation テーブルの UC 参照）は BLK-001 + BLK-005 の二重ブロッカーにより完全にブロックされています。案1（AWS ネイティブエンジンでのクエリ）は影響を受けません。

---

### BLK-006: ListObjectsV2 レイテンシ（再測定 — 30-80x は再現せず）

| 属性 | 値 |
|------|---|
| **影響サービス** | FSx for ONTAP S3 Access Points |
| **影響機能** | ディレクトリスキャン、Glue Crawler、Auto Loader リスティングモード |
| **根本原因** | FSx for ONTAP S3 AP のプロダクトレベルのパフォーマンス特性 |
| **当初の確認日** | 2026-05-22（AWS Support がプロダクトレベルの特性として確認、30-80x として引用） |
| **再測定日** | 2026-08-05 — 10〜5,000 オブジェクトで **0.9x〜1.4x**。30-80x は再現しませんでした。[エビデンス](../../verification-pack/s3ap-list-latency/evidence/2026-08-05/benchmark-result.yaml) |
| **ステータス** | ⚠️ 範囲を縮小 — 5,000 オブジェクト以下では観測されず、それを超える規模は未定量 |
| **解除条件** | 10 万オブジェクト以上での測定により、ペナルティが現れる境界（もしあれば）を特定すること |
| **影響度** | **Low** — 測定したオブジェクト数では検出不能。ワークアラウンドは設計上の良い実践として引き続き有効 |

**再測定サマリ**（median、データ点ごとに 5 試行、計測範囲はページネーションされたリストループのみ）:

| オブジェクト数 | FSx for ONTAP S3 AP | ネイティブ S3 | 比率 |
|--------:|--------------------:|----------:|------:|
| 10 | 38 ms | 27 ms | 1.4x |
| 100 | 52 ms | 39 ms | 1.3x |
| 1,000 | 162 ms | 128 ms | 1.3x |
| 5,000 | 665 ms | 704 ms | 0.9x |

2 階層のネスト構造でも同じ比率でした。すべての結果が、本ブロッカーに当初記録されていた性能目標（100 ファイル未満で 1 秒未満、1,000 ファイル未満で 3 秒未満）の範囲内に収まっています。

**未解明のまま残る点**: リスティングは 5,000 オブジェクトまでしか測定していません。単一ディレクトリに数十万〜数百万オブジェクトある場合の挙動は未検証で、[S3 AP 設計上の考慮点](./s3ap-design-considerations.md) には ONTAP がディレクトリ内全エントリをインメモリでソートする必要があると記載されており、これはエントリ数に応じて増大するはずです。したがって以下のワークアラウンドは推奨される設計実践として引き続き有効です。ただし、小規模で実測された 30-80x のペナルティを根拠とするものではなくなりました。

**当初の数値の出自**: 特定できていません。比較対象となるエビデンス記録が残っていないため、帰属させずに未解明として残します。考えられる要因としては、CLI ラッパー経由での測定（短時間の呼び出しではプロセス起動時間が支配的）、当時ファイルシステムが劣化状態にあった、その後のプラットフォーム側の変更などがあります。

**回避策**:
1. **ファイル統合** — 小ファイルを ≥ 128 MB に統合して ListObjects 呼び出し回数を削減
2. **パーティション構造** — `year=YYYY/month=MM/day=DD/` で整理し、スキャン範囲を限定
3. **Glue Catalog 参照** — ファイル一覧ではなく Glue Catalog のメタデータを参照するクエリパスを使用
4. **Auto Loader 通知モード** — DataSync → 標準 S3 経由で通知モードを利用（ListObjects 不要）

---

### BLK-007: NFS/SMB マウントが seccomp でブロック

| 属性 | 値 |
|------|---|
| **影響サービス** | Databricks Runtime |
| **影響機能** | Databricks クラスターからの NFS/SMB/FUSE マウント |
| **根本原因** | Databricks ランタイムの seccomp プロファイルが `mount` / `umount` システムコールを禁止 |
| **確認日** | 2026-05（設計上の制約として確認） |
| **ステータス** | ❌ 設計上不可 — セキュリティ設計であり、解除見込みなし |
| **解除条件** | なし（セキュリティ設計として意図的） |
| **影響度** | **N/A — Architectural** — セキュリティ設計として意図的。解除見込みなし。代替パスが確立されており実用上の影響は限定的 |

**回避策**:
- BLK-001 と同じ代替パスを使用（DataSync / Kafka / Glue/EMR 経由）

---

### BLK-008: Lake Formation 列レベル制御が S3 Tables 非対応

| 属性 | 値 |
|------|---|
| **影響サービス** | AWS Lake Formation × S3 Tables |
| **影響機能** | S3 Tables フェデレーテッドカタログでの列レベル権限 |
| **根本原因** | Lake Formation が S3 Tables カタログに対して列レベル（Column-level）の制御を未実装 |
| **確認日** | 2026-05（テーブルレベルのみ適用されることを確認） |
| **ステータス** | ❌ 未解決 — Feature Request 提出予定 |
| **解除条件** | AWS が S3 Tables フェデレーテッドカタログで Lake Formation 列レベル権限をサポート |
| **影響度** | **Low** — テーブルレベル制御は動作。列レベルが必要な場合は通常の Glue Catalog テーブルを使用 |

**回避策**:
- 列レベル制御が必要なテーブルは通常の Glue Catalog テーブル（汎用 S3 バケット上）に配置し、Lake Formation 列マスクを適用

---

### BLK-009: S3 Access Point へのアンロードにおける checksum 検証の失敗とオブジェクトの残留

| 属性 | 値 |
|------|---|
| **影響サービス** | FSx for ONTAP S3 Access Points × アンロードを行う任意のエンジン |
| **影響機能** | Snowflake `COPY INTO @stage`。返却された暗号化タイプに対して checksum を検証する他のアンロード処理も同様と考えられる |
| **根本原因** | AWS はアップロード時のチェックサムの扱いが異なることを明記している。チェックサムは「オブジェクトメタデータおよびオブジェクト自体として FSx for NetApp ONTAP ボリュームに保存されない」ため「チェックサム値はレスポンスに返らない」。ETag も MD5 ダイジェストではないと明示されている（[Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)）。計算したチェックサムをレスポンスと照合するクライアントはこの手順を完了できない。書き込み自体は先に成功する。エラー文は暗号化タイプ（`aws:fsx`、`AWS_SSE_S3` でも `AWS_SSE_KMS` でもない）を指すが、これはクライアントが提示する対処のヒントであり機構ではない |
| **確認日** | 2026-08-06（実測） |
| **ステータス** | ❌ 未解決 |
| **解除条件** | FSx for ONTAP S3 AP がクライアントの受け付ける暗号化タイプを報告する、またはクライアントが `aws:fsx` を許容する |
| **影響度** | **Medium** — 操作自体が利用不可であり、かつクリーンに拒否されず状態が残る形で失敗する |

**実測内容**

| 試行 | 結果 |
|---|---|
| 暗号化を明示しない `COPY INTO @stage` | 479 ms で `Remote upload failed checksum validation` により失敗。**それでもオブジェクトは書き込まれていた** — 25 バイト、gzip 正常、内容一致、`ServerSideEncryption: aws:fsx` |
| ステージに `ENCRYPTION=(TYPE='AWS_SSE_S3')` を設定 | ハング。2 分 54 秒でキャンセル。書き込みなし |

**単なる拒否より問題が大きい理由**: 文は失敗を報告するため、呼び出し側は何も書かれていないと考える。しかし完全なオブジェクトが Access Point 上に残る。AP 経由ステージへのアンロードを試したことがある場合は、対象プレフィックスを一覧して孤児オブジェクトを削除すること。

**回避策**:
1. **Access Point へアンロードしない。** 標準 S3 バケット、または Snowflake マネージドストレージ（内部テーブル、あるいは External Volume 上の Managed Iceberg Table— 2026-08-06 検証済み）へ書き込む
2. 同一ボリュームへ NFS または SMB でアクセスできる場合はそちらへ書き込む。S3 レイヤーを経由しない

**エビデンス**: [Snowflake 検証 2026-08-06](../../verification-pack/snowflake/evidence/2026-08-06/evidence-record.yaml)

> 本リポジトリの以前のリビジョンは、これを「Snowflake External Stage は設計上読み取り専用」と説明していました。これは誤りであり、部分書き込みの挙動を見えなくしていました。

---

## ブロッカー解消時の影響マップ

```mermaid
graph TD
    BLK001[BLK-001 解消<br/>UC × S3 AP] --> Z1[ゼロコピー UC ガバナンス実現]
    BLK001 --> Z2[DataSync 不要化<br/>コスト削減]
    
    BLK002[BLK-002 解消<br/>Conditional Writes] --> W1[FSx for ONTAP S3 AP に<br/>Delta Lake 直接書き込み<br/>Iceberg は Athena 経由で既に可能]
    BLK002 --> W2[Lakehouse テーブル<br/>フォーマット完全対応]
    
    BLK003[BLK-003 解消<br/>Event Notifications] --> E1[Auto Loader 通知モード<br/>直接動作]
    BLK003 --> E2[Snowpipe auto-ingest<br/>直接動作]
    BLK003 --> E3[FPolicy 代替<br/>不要化]
    
    BLK005[BLK-005 解消<br/>iceberg_rest] --> I1[UC Foreign Catalog<br/>× S3 Tables]
    BLK005 --> I2[S3 Annotations<br/>案3 解除]
    
    style Z1 fill:#ccffcc
    style W1 fill:#ccffcc
    style E1 fill:#ccffcc
    style I1 fill:#ccffcc
```

> **最大インパクト**: BLK-001 と BLK-002 が同時に解消されれば、FSx for ONTAP S3 AP が Databricks UC のフル機能（読み取り + 書き込み + ガバナンス）を直接サポートする構成が実現し、DataSync パスが「必須」から「オプション」に変わります。

---

## 機能要望ステータス

| ベンダー | 要望内容 | 提出日 | ステータス |
|---------|---------|--------|-----------|
| Databricks | UC External Location の S3 AP サポート | 2026-05 | クローズ（サポートティア不足により資格なし）。[Community 投稿](https://community.databricks.com/t5/data-engineering/unity-catalog-external-location-with-amazon-s3-access-points/m-p/160296#M54880)（2026-06） |
| Databricks | `iceberg_rest` Connection Type サポート | 2026-05 | クローズ（サポートティア不足により資格なし） |
| Databricks | OpenSharing STS credential vending on S3 AP | 2026-06 | [Community 投稿](https://community.databricks.com/t5/data-engineering/opensharing-vended-sts-credentials-on-s3-access-points-verified/m-p/160298#M54881) — アーキテクチャガイダンス募集中 |
| AWS | FSx for ONTAP S3 AP に conditional writes 追加 | 2026-05 | 提出済み・未回答 |
| AWS | FSx for ONTAP S3 AP に Event Notifications 追加 | 2026-05 | 提出済み・未回答 |
| AWS | FSx for ONTAP に SnapMirror S3 有効化 | 2026-05 | 提出済み・未回答 |
| AWS | ListObjectsV2 レイテンシ改善 | 2026-05 | 提出済み・プロダクト特性として確認 |
| AWS | S3 Tables × Lake Formation 列レベル制御 | 2026-05 | 提出予定 |

> ケース番号・担当者名は非公開（ロールベース表記のみ。ステアリング準拠）。

---

## 四半期レビュースケジュール

| レビュー日 | 確認事項 |
|-----------|---------|
| 2026-09（Q3） | Databricks リリースノート確認、AWS re:Invent 前の GA 確認 |
| 2026-12（Q4） | re:Invent 発表確認、2027 計画への反映 |
| 2027-03（Q1） | DAIS 2027 向け事前確認 |

---

## ブロッカー間の前提条件チェーン

一部のブロッカーは解消の順序に依存関係があります:

```mermaid
graph LR
    BLK001[BLK-001<br/>UC × S3 AP] -->|前提| BLK002_IMPACT[BLK-002 解消の<br/>UC への恩恵]
    BLK001 -->|前提| BLK005_IMPACT[BLK-005 解消の<br/>UC への恩恵]
    
    BLK002[BLK-002<br/>Conditional Writes] -->|独立| ATHENA[Athena/EMR<br/>書き込み恩恵]
    
    style BLK001 fill:#ffcccc,stroke:#cc0000,stroke-width:2px
    style BLK002_IMPACT fill:#ffffcc
    style BLK005_IMPACT fill:#ffffcc
    style ATHENA fill:#ccffcc
```

| シナリオ | 結果 |
|---------|------|
| BLK-002 のみ解消（BLK-001 未解消） | Athena/EMR/Glue から FSx for ONTAP S3 AP に直接 Delta Lake 書き込みが可能になる（Iceberg は Athena 経由で既に可能）。**ただし Databricks UC からの恩恵はなし**（BLK-001 がゲート） |
| BLK-001 のみ解消（BLK-002 未解消） | UC External Location として S3 AP を登録可能 → **読み取り + UC ガバナンス**が実現。書き込みは引き続き標準 S3 経由 |
| BLK-001 + BLK-002 同時解消 | **フル機能**: ゼロコピー + UC ガバナンス + Delta/Iceberg 書き込み。DataSync が「必須」→「オプション」に |
| BLK-003 のみ解消（BLK-001 未解消） | Auto Loader 通知モードが FSx for ONTAP S3 AP で動作。ただし UC ガバナンスは引き続き標準 S3 経由が必要 |
| BLK-005 のみ解消（BLK-001 未解消） | UC SQL Warehouse から S3 Tables/annotation テーブルをクエリ可能。FSx for ONTAP S3 AP 直接接続は別問題（BLK-001） |

> **キーインサイト**: BLK-001（UC × S3 AP）は他の複数ブロッカーの**ゲートブロッカー**です。BLK-001 が未解消の限り、BLK-002/003/005 の解消は Databricks UC パスには直接恩恵をもたらしません（Athena/EMR など UC 外パスには恩恵あり）。

---

## 解消シグナルの監視方法

四半期レビュー時に以下のソースを確認してください:

| ブロッカー | 監視ソース | 監視キーワード |
|-----------|-----------|-------------|
| BLK-001 | [Databricks Release Notes](https://docs.databricks.com/en/release-notes/index.html) | "External Location", "S3 Access Point", "access_point" |
| BLK-001 | [Databricks Changelog](https://docs.databricks.com/en/release-notes/product/index.html) | "storage", "External Location" |
| BLK-002 | [AWS What's New](https://aws.amazon.com/about-aws/whats-new/) | "FSx for ONTAP", "conditional writes", "If-None-Match" |
| BLK-003 | [AWS What's New](https://aws.amazon.com/about-aws/whats-new/) | "FSx for ONTAP", "Event Notifications", "S3 events" |
| BLK-004 | [AWS What's New](https://aws.amazon.com/about-aws/whats-new/) | "FSx for ONTAP", "SnapMirror S3" |
| BLK-005 | [Databricks Release Notes](https://docs.databricks.com/en/release-notes/index.html) | "iceberg_rest", "Foreign Catalog", "S3 Tables" |
| BLK-006 | [AWS What's New](https://aws.amazon.com/about-aws/whats-new/) | "FSx for ONTAP", "performance", "ListObjects" |
| BLK-008 | [AWS What's New](https://aws.amazon.com/about-aws/whats-new/) | "Lake Formation", "S3 Tables", "column-level" |

> **自動化のヒント**: GitHub Actions で上記 RSS フィードを定期チェックし、キーワードヒット時に Issue を自動作成するパイプラインを構築可能です。

---

## 関連ドキュメント

- [UC 接続総合ガイド](./fsx-ontap-to-databricks-unity-catalog-guide.md) — ブロッカーの影響を受けるパス設計
- [互換性マトリクス](./compatibility-matrix.md) — 制約の技術詳細
- [DataSync → S3 ガイド](./datasync-to-s3-guide.md) — BLK-001/002/003 の主要回避策
- [S3 Annotations 評価](./s3-annotations-governance-evaluation.md) — BLK-005 の影響を受ける案3
- [読み順ガイド](./reading-path-guide.md) — ドキュメント全体のナビゲーション
