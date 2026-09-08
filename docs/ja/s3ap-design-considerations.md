> 🌐 Language: **日本語** | [English](../en/s3ap-design-considerations.md)

# FSx for ONTAP S3 Access Points — 設計考慮事項

> FSx for ONTAP S3 Access Points を使ってNAS データを S3 API で公開する際の設計ポイント。PoC 前に確認すべき制約、性能特性、運用パターンを整理する。

---

## 前提: S3 Access Points の仕組み

FSx for ONTAP S3 Access Points は、NAS ボリューム上のファイルデータを S3 互換 API でアクセス可能にする機能である。Amazon S3 バケットとは異なり、S3 API リクエストは ONTAP のファイルシステム層を経由して処理される。

この構造により、以下の特性を持つ。

- S3 オブジェクトキーは NAS のディレクトリ/ファイルパスに対応する
- S3 API の性能は、NAS 側のディレクトリ構成とファイル数に依存する
- NFS/SMB と S3 の双方から同一データにアクセス可能だが、整合性の設計が必要
- Amazon S3 のすべての機能が利用できるわけではない（Versioning 非対応など）

---

## 1. ディレクトリ設計（最重要）

### 問題: 単一ディレクトリへの大量ファイル配置

S3 クライアントが全ファイルをルート直下に書き込むと、ONTAP 上では 1 つのディレクトリに数百万ファイルが平置きされる。これにより以下が発生する。

| 現象 | 原因 |
|------|------|
| ListObjectsV2 の応答時間が極端に遅くなる | ディレクトリ内全エントリのインメモリソートが必要 |
| 新規ファイル作成が失敗する | maxdir-size（ディレクトリサイズ上限）に到達 |
| FlexGroup 利用時に 1 ノードに負荷集中 | 同一ディレクトリ内ファイルは同一 constituent に配置される傾向 |
| NFS 側の `ls` や `find` も遅くなる | 同じディレクトリメタデータを走査するため |

### 推奨: 階層パーティションで分散

```
/volume-root/
  └── {source}/{year}/{month}/{day}/
      └── {filename}.parquet
```

**設計指針:**
- 1 ディレクトリ内のファイル数は **10 万件以下** を目安に分割する
- 時系列データは日付パーティション必須（`year=YYYY/month=MM/day=DD/` または `dt=YYYY-MM-DD/`）
- 高頻度書き込みにはハッシュバケット（`bucket-{hash mod 256}/`）を検討
- 階層の深さは 5〜8 レベルを目安。20 階層超は NFS パス長制限に近づく

### ボリュームタイプの選択

| タイプ | 特性 | 推奨用途 |
|--------|------|---------|
| FlexVol | 単一ノード。シンプルだがスケールに制約 | 小規模（ファイル数 100 万以下） |
| FlexGroup | 複数 constituent に自動分散。スケーラブル | 大規模（ファイル数 100 万超、高スループット） |

FlexGroup では**ディレクトリが異なれば異なる constituent に配置**される。ディレクトリを適切に分散することで、複数ノードの並列性を活用できる。

参考:
- https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/How_do_I_avoid_maxdir-size_issues
- https://docs.netapp.com/us-en/ontap/flexgroup/definition-concept.html

---

## 2. オブジェクトキーとパス長の制約

| 制約 | 値 | 影響 |
|------|-----|------|
| S3 オブジェクトキー最大長 | 1,024 バイト | これを超える NAS パスのファイルは S3 からアクセス不能 |
| ディレクトリ/ファイル名の最大長 | 255 文字 | 1 要素がこれを超えるキーは使用不可 |
| マルチバイト文字 | UTF-8 バイト数で評価 | 日本語 1 文字 = 3〜4 バイト。文字数とバイト数を混同しない |

### 推奨事項

- 1 階層の名前は短く保つ
- 一意性のための長大文字列をファイル名に埋め込まない（UUID の短縮形を使う等）
- 既存 NAS データを公開する場合は、事前にパス長を棚卸しする
- S3 と NAS の両方で安全に扱える文字セットを定義する（英数字 + `-_./`）
- 空白、特殊文字、Unicode 正規化の差異による「S3 では見えるが NFS では化ける」問題を事前検証

---

## 3. 性能特性

S3 Access Points 経由のアクセスは、Amazon S3 への直接アクセスとは性能特性が異なる。

### 傾向

| 観点 | 特性 |
|------|------|
| 小ファイル（< 64KB） | メタデータ処理のオーバーヘッドが相対的に大きい。スループットよりレイテンシが律速 |
| 大ファイル（> 1MB） | データ転送が支配的。Amazon S3 と性能差が縮小する傾向 |
| ListObjectsV2 | ディレクトリ内ファイル数に比例して遅延増加。数百万件ではレイテンシが秒単位に |
| PUT（書き込み） | ディレクトリ作成を伴う場合は追加コスト。既存ディレクトリへの書き込みはオーバーヘッドが小さい |
| 並行リクエスト | FSx for ONTAP のスループット容量に律速される |

### 対策

- **ListObjectsV2 の範囲を狭くする**: prefix パラメータで対象ディレクトリを限定
- **全件走査を避ける**: オブジェクトキーが既知なら HEAD/GET を直接実行
- **インデックスを外部に持つ**: Glue Data Catalog、DynamoDB、外部カタログでファイル一覧を管理
- **小ファイルの集約を検討**: 多数の JSON/CSV → Parquet へのバッチ変換
- **FSx スループット容量の適正化**: 読み書きパターンに応じたプロビジョン

---

## 4. ListObjectsV2 の設計

ListObjectsV2 は最も性能影響が大きい API 操作である。

### ONTAP 内部での動作

S3 の ListObjectsV2 リクエストは、NAS 側の `readdir`（ディレクトリエントリ列挙）に変換される。結果は**ソート済み**で返される必要があるため、大規模ディレクトリではインメモリソートのコストが発生する。

### 設計パターン

| パターン | 適用場面 | 注意点 |
|---------|---------|--------|
| Prefix 限定 LIST | 特定日付/テナントのファイル一覧 | prefix を深くするほど対象が絞られる |
| MaxKeys 制限 + ページネーション | UI 表示や段階的処理 | 1 回の返却件数を 1,000 以下に |
| LIST を使わない設計 | ストリーミング書き込み → 既知キーで GET | Kafka、Kinesis からの書き込みで自明なキー |
| 外部カタログ | Glue Crawler、Athena テーブル | LIST の代わりにカタログから Partition Discovery |

### アンチパターン

- ルートプレフィックスでの全件 LIST を定期実行
- LIST 結果を毎回全件取得してからフィルタリング
- ディレクトリ階層を無視した recursive LIST

---

## 5. マルチプロトコルアクセスの整合性

同一データに NFS/SMB と S3 から同時にアクセスする場合、整合性の設計が必要。

### 注意すべきシナリオ

| シナリオ | リスク |
|---------|--------|
| NFS で書き込み中のファイルを S3 GET | 不完全なデータが読める可能性 |
| S3 PUT 完了前に NFS でファイルを確認 | S3 PUT は完了するまでファイルが不可視（S3 セマンティクス） |
| NFS でファイルを rename → 旧キーで S3 GET | 404 Not Found |
| NFS と S3 から同一ファイルに同時書き込み | 後勝ち（last-writer-wins）。データ損失リスク |

### 推奨パターン

- **書き込みプロトコルを 1 つに限定する**（例: S3 で書き込み → NFS で読み取り）
- 書き込み中は一時ディレクトリ（`_tmp/`）に配置し、完了後に公開ディレクトリへ rename
- 「収集中」「公開済み」「処理済み」のディレクトリ状態遷移を定義
- 両方から書き込む場合は、ファイル粒度で排他を確保する設計とする

---

## 6. 機能互換性

Amazon S3 と比較して、以下の機能が非対応または制約付き。

| 機能 | 状態 | 代替策 |
|------|:----:|--------|
| バージョニング | ❌ 非対応 | ONTAP Snapshot によるポイントインタイム保護 |
| ライフサイクルポリシー | ❌ 非対応 | FabricPool 自動階層化 + カスタムスクリプト |
| Object Lock / WORM | ❌ 非対応 | SnapLock（ONTAP 機能） |
| S3 Event Notification | ❌ 非対応 | スケジュールポーリング、または ONTAP ネイティブ監査ログ。**FPolicy + EventBridge は代替になりません**（AP 経由の書き込みは通知されません。実測 2026-08-26 / ONTAP 9.18.1P3D1） |
| 条件付き書き込み (If-None-Match) | ❌ 501 Not Implemented | アプリ側で排他制御 |
| Cross-Region Replication | ❌ 非対応 | SnapMirror（[参照](s3ap-flexcache-snapmirror-considerations.md)） |
| S3 Select | ❌ 非対応 | Athena / DuckDB でクエリ |
| Multipart Upload | ✅ 対応（9.16.1+） | Advanced Capacity Balancing 有効化推奨 |

### 重要な注意

「S3 互換」は「Amazon S3 と同一」を意味しない。利用予定のサービスや SDK が内部的に呼び出す API（HeadBucket、ListBuckets、GetBucketLocation 等）まで含めた E2E 検証が必要。

---

## 7. セキュリティ設計

### Access Point の分割

用途別に Access Point を分割し、それぞれに最小権限の IAM ポリシーを付与する。

```
ap-analytics-readonly     ← Athena / DuckDB（GetObject, ListBucket のみ）
ap-etl-ingestion          ← Glue ETL（PutObject, GetObject）
ap-sagemaker-training     ← SageMaker（GetObject のみ、特定 prefix）
ap-audit-readonly         ← 監査チーム（GetObject, ListBucket, 全 prefix）
```

### 二層認可モデル

S3 Access Points は**二層認可**を実装する。

1. **IAM + AP ポリシー層**: S3 API リクエスト受信時に評価
2. **ファイルシステム権限層**: ONTAP の UNIX/NTFS ACL（FileSystemIdentity で決定）

両方のチェックを通過しなければアクセスは許可されない。IAM で許可されても、NAS 権限で拒否されればアクセス不可。

---

## 8. PoC チェックリスト

### アーキテクチャ

- [ ] NAS データの S3 公開であり、Amazon S3 バケットとは異なることを関係者が理解している
- [ ] 利用予定の AWS サービスが必要とする S3 API を把握している
- [ ] 対象の FSx for ONTAP バージョンでの対応機能を確認している

### 名前空間

- [ ] オブジェクトキー 1,024 バイト制約を考慮している
- [ ] 1 要素 255 文字制約を考慮している
- [ ] マルチバイト文字をバイト数で評価している
- [ ] 巨大な単一ディレクトリを避けている
- [ ] ディレクトリ階層が深くなりすぎていない（目安: 5〜8 レベル）

### 性能

- [ ] 本番相当のファイル数・サイズで ListObjectsV2 の性能を測定している
- [ ] 小ファイル（< 64KB）のワークロードで PUT/GET レイテンシを測定している
- [ ] NFS/SMB と S3 の同時負荷をテストしている
- [ ] P95/P99 レイテンシを確認している（平均値だけで判断しない）

### 機能

- [ ] バージョニング非対応の影響を評価している
- [ ] 条件付き書き込み非対応（501）の影響を評価している
- [ ] Multipart Upload の対応状況を確認している
- [ ] SDK が暗黙的に呼び出す API も含めて検証している

### 運用

- [ ] 書き込みプロトコルのルールを定義している
- [ ] Snapshot による代替保護を設計している
- [ ] S3 側と NAS 側の監査方法を定義している
- [ ] Access Point を用途別に分割している

---

## 関連ドキュメント

- [FlexCache / SnapMirror 利用時の追加考慮事項](s3ap-flexcache-snapmirror-considerations.md)
- [S3 AP + SnapMirror + FlexCache 調査・検証](../../integrations/snapmirror-flexcache-multicloud/docs/ja/research.md)
- [S3 AP データ収集 CloudFormation テンプレート（設計 TIPS 付き）](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/tree/main/infrastructure/s3ap-data-collection) — パラメータ Description に設計ガイダンスを埋め込んだデプロイテンプレート
- [AWS Docs: S3 Access Points for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [AWS Docs: Best practices — Optimizing S3 performance](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html)
- [NetApp KB: How to avoid maxdir-size issues](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/How_do_I_avoid_maxdir-size_issues)
- [NetApp Docs: FlexGroup volumes](https://docs.netapp.com/us-en/ontap/flexgroup/definition-concept.html)
