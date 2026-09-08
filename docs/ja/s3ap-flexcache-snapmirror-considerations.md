> 🌐 Language: **日本語** | [English](../en/s3ap-flexcache-snapmirror-considerations.md)

# S3 Access Points + FlexCache / SnapMirror — 追加設計考慮事項

> S3 Access Points で収集したデータを FlexCache（読み取り加速）や SnapMirror（DR）で配信する際の、追加で考慮すべき設計ポイント。[S3 AP 全般の設計考慮事項](s3ap-design-considerations.md) を先に確認すること。

---

## 前提

- FSx for ONTAP S3 Access Points は ONTAP の S3 NAS bucket メカニズムに基づく
- S3 AP アタッチ済みボリュームは、通常の FlexVol/FlexGroup と同様に SnapMirror / FlexCache の対象にできる
- 互換性の詳細は [調査ドキュメント](../../integrations/snapmirror-flexcache-multicloud/docs/ja/research.md) を参照

---

## 1. ディレクトリ設計が FlexCache / SnapMirror に与える影響

S3 AP のディレクトリ設計は、単体での性能だけでなく FlexCache / SnapMirror の効率にも影響する。

### FlexCache への影響

| ディレクトリ構成 | FlexCache の動作 | 影響 |
|----------------|----------------|------|
| 単一ディレクトリに 100 万ファイル | 同一 FlexGroup constituent にファイルが集中 | 1 ノードのみにキャッシュ負荷。FlexCache の分散効果が薄れる |
| 適切にディレクトリ分散 | 複数 constituent にまたがる | 複数ノードでキャッシュヒット。FlexCache の並列性を活用 |
| 深すぎる階層（>10 レベル） | readdir の再帰が深くなる | キャッシュミス時の Origin 問い合わせが多段に |

**推奨**: FlexCache を前提とする場合、ディレクトリ内ファイル数を分散し、FlexGroup constituent の並列性を意識した階層設計を行う。

### SnapMirror への影響

| 書き込みパターン | SnapMirror 増分転送への影響 |
|----------------|--------------------------|
| 小ファイルを多数のディレクトリに分散書き込み | 変更ブロックが分散し、増分転送が効率的 |
| 1 つの巨大ファイルに追記 | 変更ブロックが集中し、毎回大きな転送量が発生 |
| 1 ディレクトリに大量ファイルを一括作成 | ディレクトリメタデータ更新が集中し、転送量が増加 |

**推奨**: SnapMirror を前提とする場合、多数の小〜中ファイルに分割して書き込む方が増分転送効率が良い。巨大な単一ファイルへの追記は避ける。

---

## 2. FlexCache 利用時の考慮事項

### 2.1 書き込みモードの選択

| モード | 動作 | Origin 反映 | S3 AP 経由の書き込みとの関係 |
|--------|------|:-----------:|---------------------------|
| write-around（デフォルト） | Cache への書き込みが Origin に同期転送 | 即時 | Origin 側 S3 AP からの書き込みと衝突しにくい |
| write-back | Cache にローカル書き込み後、非同期 flush | 30-90 秒 | Origin 側 S3 AP 書き込みが XLD を revoke し、Cache の dirty data が失われるリスク |

**設計ルール**: S3 AP で Origin に書き込み、FlexCache で宛先から読み取るパターンでは **write-around mode を推奨**。write-back mode を使う場合は、S3 AP と FlexCache で同一ファイルに並行書き込みしないこと。

### 2.2 キャッシュ伝搬とデータ可視性

| 観点 | 値 | 備考 |
|------|-----|------|
| 新規ファイル可視性（キャッシュミス時） | ~3-6 秒 | 検証値（intra-cluster ~6秒、cross-region <3秒） |
| 既読ファイル更新の反映 | TTL 経過後（デフォルト 30 秒） | `read_after_write_flush_time` で調整可 |
| FlexCache プリポピュレート | 未対応（S3 AP 経由） | NFS/SMB アクセスで事前キャッシュ充填は可能 |

**設計ルール**: S3 AP で書き込んだ直後に Cache Volume で読み取る場合、初回読み取りは Origin に問い合わせる（キャッシュミス）。2 回目以降は TTL 期間中はキャッシュから返される。

### 2.3 ListObjectsV2 と FlexCache

FlexCache Cache Volume 上で ListObjectsV2 を実行する場合（ONTAP 9.18.1+ で Cache Volume S3 対応時）:

- ListObjectsV2 はディレクトリメタデータの読み取り操作
- キャッシュ済みディレクトリの一覧はローカル速度で返される
- キャッシュミスのディレクトリは Origin への問い合わせが発生し、レイテンシが RTT 分増加

**推奨**: 高頻度で LIST を実行する prefix（ディレクトリ）は、事前に NFS アクセスでキャッシュを暖めておくとレスポンスが改善する。

---

## 3. SnapMirror 利用時の考慮事項

### 3.1 転送されない S3 AP メタデータ

SnapMirror はボリュームデータ（ファイル/ディレクトリ）のみを転送する。以下は宛先で別途構成が必要。

| 項目 | 転送される？ | 宛先での対応 |
|------|:----------:|------------|
| ファイルデータ | ✅ | — |
| UNIX 権限（uid/gid/mode） | ✅ | — |
| NTFS ACL | ✅ | — |
| S3 Access Point | ❌ | `aws fsx create-and-attach-s3-access-point` で新規作成 |
| S3 AP IAM ポリシー | ❌ | 宛先リージョンで別途構成 |
| S3 ユーザーメタデータ（x-amz-meta-*） | ⚠️ | ONTAP 内のストリーム属性として保持される場合あり（バージョン依存） |
| S3 Object Tags | ⚠️ | 同上 |

**設計ルール**: DR フェイルオーバー手順には S3 AP 再作成 + IAM ポリシー構成を含めること。自動化する場合は Lambda や Step Functions でオーケストレーション。

### 3.2 DP ボリュームの S3 AP アタッチ

SnapMirror 宛先ボリューム（DP タイプ）への S3 AP アタッチには条件がある。

| 状態 | S3 AP アタッチ | 備考 |
|------|:-------------:|------|
| DP（SnapMirror 関係維持中） | ❌ | Read-only のため junction path が設定不可 |
| DP → break → RW | ✅ | break 後に junction path を設定し、S3 AP を作成 |
| 再同期（resync）後 | ❌ | 再び DP に戻るため S3 AP は使用不可 |

**設計ルール**: S3 AP でデータにアクセスするには SnapMirror break が必要。break 後は片方向レプリケーションが停止するため、DR フェイルオーバーの文脈で使用する。「SnapMirror を維持しながら宛先で S3 AP」は不可。

### 3.3 RPO とデータ可視性

| 項目 | 値 | 備考 |
|------|-----|------|
| SnapMirror Async 最短スケジュール | 5 分 | FSx for ONTAP の制約 |
| 増分転送の典型的所要時間 | 10-30 秒 | データ量とスループット容量による |
| フェイルオーバー RTO（S3 AP アクセス復旧まで） | ~3 分 | break + junction path + S3 AP 作成 |
| RPO | = 最終転送からの経過時間 | 最悪ケースで 5 分 + 転送中のデータ |

**設計ルール**: リアルタイム性が必要な場合は FlexCache、DR/コンプライアンスには SnapMirror。両方が必要なら併用。

---

## 4. ディレクトリ設計の統合パターン

S3 AP 単体 + FlexCache + SnapMirror を全て考慮した推奨ディレクトリ構成。

```
/volume-root/
  └── {source-id}/                    ← テナント/ソース別に分離
      └── {year}/{month}/{day}/       ← 時系列パーティション（Hive-style）
          └── {hour}/                 ← 1 ディレクトリ内ファイル数の制御
              ├── {uuid-short}.json
              ├── {uuid-short}.parquet
              └── ...
```

### この構成が満たす要件

| 要件 | どう満たすか |
|------|------------|
| ListObjectsV2 性能 | prefix 指定で対象ディレクトリを限定。ソート対象が小さい |
| FlexGroup 分散 | ディレクトリが多数 → constituent 間で自動分散 |
| FlexCache 効率 | 読み取りが複数 constituent に分散。キャッシュヒット率向上 |
| SnapMirror 増分転送 | 小ファイル × 多ディレクトリ → 変更ブロックが分散し効率的 |
| Athena パーティションプルーニング | Hive-style パーティションを Glue Crawler が自動認識 |
| NFS バッチ処理 | 日付ディレクトリ単位で `find` や `rsync` が効率的 |
| アクセス制御 | テナントディレクトリ単位で export-policy / AP ポリシーの prefix 制限 |

---

## 5. FlexCache 削除手順

FlexCache の削除は FSx API (`delete-volume`) ではなく **ONTAP REST API** で行う。

### 正しい手順

```bash
# 1. FlexCache UUID を取得
ONTAP_API: GET /api/storage/flexcache/flexcaches?name={cache_name}

# 2. FlexCache 削除（ONTAP REST API）
ONTAP_API: DELETE /api/storage/flexcache/flexcaches/{uuid}
# → 202 Accepted（非同期ジョブ）。ジョブ完了を待つ

# 3. FSx API にゴーストエントリが残った場合（SVM 削除時にブロックされる場合）
aws fsx delete-volume --volume-id fsvol-XXXXX --ontap-configuration '{"SkipFinalBackup":true}'

# 4. SVM 削除（全ボリュームが FSx API から消えた後）
aws fsx delete-storage-virtual-machine --storage-virtual-machine-id svm-XXXXX
```

### FSx API の `delete-volume` ではなく ONTAP REST API を使う理由

- FlexCache は ONTAP 内部で特殊な FlexGroup として管理され、Origin との関係メタデータを持つ
- ONTAP REST API の `DELETE /api/storage/flexcache/flexcaches/{uuid}` はこの関係を正しくクリーンアップする
- FSx API の `delete-volume` は通常のボリューム削除パスを使い、FlexCache 固有のクリーンアップを行わない場合がある
- 404 レスポンスは成功扱い（冪等）。409 Conflict は待機後リトライ

### FSx API のコントロールプレーン反映遅延

- ONTAP REST API で削除完了後も、FSx API (`describe-volumes`) に fsvol-* エントリが残る場合がある
- SVM 削除時に「Cannot delete storage virtual machine while it has non-root volumes」エラーが出る場合は、FSx API 経由で `delete-volume` を実行してゴーストを解消する
- この反映遅延は作成時と同様に ~30 分程度

---

## 6. 監視と運用

### FlexCache 監視

| メトリクス | 確認方法 | 閾値目安 |
|-----------|---------|---------|
| キャッシュヒット率 | ONTAP REST API: `GET /api/storage/flexcache/flexcaches/{uuid}?fields=*` | < 50% ならディレクトリ分散を見直す |
| Origin 問い合わせレイテンシ | `statistics show -object flexcache` | RTT × 2 以上なら Origin 側ボトルネック |
| Cache Volume 使用率 | `volume show -fields percent-used` | 80% 超で eviction 頻度が上がる |

### SnapMirror 監視

| メトリクス | 確認方法 | 閾値目安 |
|-----------|---------|---------|
| Lag Time | CloudWatch: `SnapMirrorLagTime` | > RPO 目標（例: 900秒）でアラート |
| Transfer Duration | CloudWatch: `SnapMirrorTransferDuration` | 増加傾向なら書き込み量がスループットを超過 |
| Healthy | CloudWatch: `SnapMirrorHealthy` | < 1 で即時調査 |

---

## 7. アンチパターンまとめ

| パターン | 問題 | 対策 |
|---------|------|------|
| ルート直下に全ファイル配置 | maxdir-size 超過 + FlexCache 偏り + LIST 劣化 | 階層パーティション分割 |
| 1 つの巨大ファイルに追記 | SnapMirror 増分転送が毎回大きい | 小ファイル分割 |
| S3 AP + FlexCache write-back で同一ファイル書き込み | XLD revoke → dirty data 消失 | write-around 使用 or ファイル分離 |
| DP ボリュームに S3 AP アタッチ試行 | 失敗する（junction path 設定不可） | break 後にアタッチ |
| ONTAP REST API のみで DP ボリューム作成 | FSx API への反映に ~30 分かかる。即時 S3 AP アタッチ不可 | 即時性が必要なら `aws fsx create-volume` を使用。FlexCache 等は ONTAP API で作成後 ~30 分待機 |
| VPC Peering を SVM peer 削除前に削除 | zombie SVM peer → MISCONFIGURED → 復旧困難 | SM-VAL-011 の順序を遵守 |
| ListObjectsV2 を全件走査で定期実行 | ディレクトリサイズに比例してレイテンシ増大 | prefix 限定 or 外部カタログ |
| データグラビティを無視してクラウドのみで設計 | 不要なエグレス費用。レイテンシ要件を満たせない | オンプレ処理が有利な場面では SnapMirror でオンプレに複製して活用 |

---

## 関連ドキュメント

- [S3 AP 全般の設計考慮事項](s3ap-design-considerations.md)
- [S3 AP データ収集 CloudFormation テンプレート（設計 TIPS 付き）](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/tree/main/infrastructure/s3ap-data-collection) — Mermaid 設計判断フローにデータ配信パターン分岐を含む
- [S3 AP + SnapMirror + FlexCache 調査・検証](../../integrations/snapmirror-flexcache-multicloud/docs/ja/research.md)
- [Demo Guide 07: SnapMirror Cross-Region + S3 AP Re-Attach](../../integrations/snapmirror-flexcache-multicloud/docs/ja/demo-guide-07-snapmirror-cross-region.md)
- [Demo Guide 01: FlexCache Same-Region](../../integrations/snapmirror-flexcache-multicloud/docs/ja/demo-guide-01-flexcache-same-region.md)
- [AWS Docs: S3 performance best practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html)
- [NetApp KB: maxdir-size issues](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/How_do_I_avoid_maxdir-size_issues)
- [NetApp Docs: FlexGroup definition](https://docs.netapp.com/us-en/ontap/flexgroup/definition-concept.html)
- [NetApp Docs: FlexCache hotspot remediation](https://docs.netapp.com/us-en/ontap/flexcache-hot-spot/flexcache-hotspot-remediation-architecture.html)
- [NetApp Blog: FlexGroups and Advanced Data Distribution](https://community.netapp.com/t5/Tech-ONTAP-Blogs/FlexGroups-and-Advanced-Data-Distribution/ba-p/456416)
