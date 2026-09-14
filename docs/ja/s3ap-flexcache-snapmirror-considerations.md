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

### 3.2 宛先側での S3 AP アタッチ

**稼働中の SnapMirror 宛先は、break もクローンもなしに S3 AP 経由で読める。** 2026-09-13 実測。本節は以前これと逆のことを書いていた。訂正内容と誤りの原因は下記。

**ゲートは junction path であって、ボリューム種別ではない。** AWS はアタッチの条件をボリュームが [mount されていること](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/create-access-points.html)と規定しており、`RW` か `DP` かには言及していない。

**そしてその junction path を設定するのは ONTAP の操作であって FSx の操作ではない。** ONTAP は DP ボリュームを mount する。DP ボリュームに対する `vol mount` は NetApp の [SVM DR テストの KB](https://kb.netapp.com/on-prem/ontap/DP/SnapMirror/SnapMirror-KBs/Can_we_do_the_SVM_level_DR_test_without_stopping_the_Production_SVM_and_cloning_the_destination_volumes) に実例として載っており、今回それを確認した。FSx API は同じ変更を拒否する。`CreateVolume` は DP に対する `JunctionPath` をフィールド名を挙げて拒否し、`UpdateVolume` は受理して無言で破棄する。ONTAP 側で mount すれば FSx API はいずれ junction path を報告し、その後アタッチが成功する。

| 宛先側の対象 | S3 AP アタッチ | 読み取り | 書き込み | 備考 |
|---|:---:|:---:|:---:|---|
| DP ボリューム（**FSx API** で junction path 設定を試行） | ❌ | — | — | `CreateVolume` はフィールド名を挙げて拒否。`UpdateVolume` は 200 を返して破棄。アタッチは `the volume is not mounted` で失敗 |
| **DP ボリューム（ONTAP で mount）** | ✅ | ✅ | ❌ `AccessDenied` | レプリケーションは `snapmirrored`/healthy のまま。後続転送の新規データが同一 AP 経由で **15 秒**で見えた。AP の変更は不要 |
| **宛先 Snapshot の FlexClone** | ✅ | ✅ | ✅ | 関係に影響なし。クローン時点で固定され、後続転送では進まない |
| DP → break → RW | ✅ | ✅ | ✅ | DR フェイルオーバー経路。SM-005、SM-VAL-008/010 |

根拠は [S3AP-DP-ATTACH-002](../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13-in-vpc/evidence-record.yaml)（ONTAP 9.18.1P5）。FSx API のみの行は [S3AP-DP-ATTACH-001](../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13/evidence-record.yaml)。

**実際の制約は可否ではなくセットアップの所要時間である。** ONTAP 側の 2 経路はいずれも、アタッチ可能になるまで FSx コントロールプレーンの反映を待つ。

| フェーズ | 所要時間 |
|---|--:|
| ONTAP 側の操作（mount またはクローン作成） | 数秒、20 秒未満 |
| **FSx API がボリューム / junction path を報告** | **665 秒・1011 秒・2298 秒** |
| S3 AP が CREATING → AVAILABLE | 31〜32 秒 |
| 初回 S3 コール成功 | 数秒 |

同一ファイルシステム・同一日の 3 サンプル。うち 665 秒と 2298 秒は同一ファイルシステム上の**同一操作**であり、**ばらつきは経路の違いでは説明できない**。「数分から数十分、こちら側で制御できない」と伝えてポーリングループを設計すること。特定の数値を引用しない。セットアップ後の定常状態は別問題で、DP 経路では転送の数秒後に新規データが読めた。

**分析エンジンから見た違いはない。** Amazon Athena を DP 由来のアクセスポイントと、同一 Parquet ファイルから作った RW 由来のコントロールに、同一セッションで向けた。行も集計値も一致し、7493 ミリ秒に対して 7804 ミリ秒。read-only ボリュームに対してパーティション検出とパーティション枝刈りの双方が機能し、`INSERT` は S3 403 が `PERMISSION_DENIED` として表面化して明示的に失敗した。後続転送で追加されたパーティションは、アクセスポイントもテーブルも変更せずカタログ更新のみでクエリ可能になった。根拠は [S3AP-DP-ATHENA-001](../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13-athena-on-dp/evidence-record.yaml)。

> **2026-09-13 まで本節が誤っていた理由。** 元の行は DP に対して ❌ を主張し、理由を「read-only のため junction path が設定不可」としていたが、検証記録を伴っていなかった。最初の検証は VPC 外から行い、FSx API の拒否を再現して ❌ を確認した。検証したように見えるが、測っていたのは FSx API だけだった。ONTAP 管理エンドポイントはプライベートアドレスであり、実際に可否を決めている層には到達していなかった。**到達できる API を試すことは、主張を試すことではない。**

#### break せずにレプリカのデータを提供する構成

宛先を読むために break は不要である。関係を維持したままの経路が 2 つあり、選択を決める違いは 1 点だけ、**消費側が書き込む必要があるか**である。

**読み取り専用で常に最新 — DP 宛先を mount する。** ONTAP で宛先を `vol mount` し、FSx API が junction path を報告するのを待ってアタッチする。読み取りは通り、書き込みは `AccessDenied` になり、各 SnapMirror 転送は同一 AP 経由で数秒後に見える。転送ごとに作り直すものはない。

**書き込み可能で時点固定 — 宛先をクローンする。** ONTAP 9.14.1 以降、NetApp は**稼働中の SnapMirror 関係を妨げずにフェイルオーバーをテストするため、宛先のボリュームクローンを作成する**手順を文書化している（[手順](https://docs.netapp.com/ja-jp/ontap/data-protection/create-delete-snapmirror-failover-test-task.html)）。宛先と同一の Storage VM 上、FlexVol と FlexGroup の双方、同期・非同期の両関係に対応。クローンは AP 経由で書き込みを受け、切り出した Snapshot の時点に留まる（後続転送では進まない）。NetApp の[宛先データアクセス手順](https://docs.netapp.com/ja-jp/ontap/data-protection/configure-destination-volume-data-access-concept.html)が break を前提に書かれているのは、その対象が本番サービスの引き継ぎであり、上記いずれとも別の要件だからである。

クローン経路の制約: **1 つの関係につきテストクローンは同時に 1 つまで**、SnapLock vault 関係は対象外、そして上記 KB 由来で **SVM-DR 関係に含まれる DP ボリュームは直接クローンできない**。最後の 1 つは、SVM-DR が利用できずボリューム単位の SnapMirror のみが選択肢となる FSx for ONTAP では影響しないが（SM-007）、オンプレミスでは影響する。

**設計ルール**: 既定で選ばず、要件で選ぶ。

| 要件 | 構成 |
|---|---|
| 各転送に追従しながら宛先を読む | ONTAP で DP 宛先を mount し、S3 AP をそこにアタッチ |
| 書き込む、または消費側に独立した時点を渡す | 宛先 Snapshot をクローンし、S3 AP をクローンにアタッチ |
| 宛先で本番サービスを引き継ぐ | break → mount → アタッチ（DR フェイルオーバー経路） |
| ソースの書き込みを近リアルタイムで見る | SnapMirror ではなく FlexCache（§2.2） |

顧客に約束する前に述べておくべき未測定事項: **Snowflake そのもの**。Athena はエンジン層がボリューム種別を意識しないことの有力な根拠であり、Snowflake も同じ `GetObject` と `ListObjectsV2` の面を通して読むが、Snowflake を DP 由来のアクセスポイントに向けてはいないので、測定済みとして提示しないこと。ほかに未測定なのは、AP を残したまま break と resync を経ても経路が維持されるか、クロスリージョンや第 2 世代ファイルシステムでの反映時間、少数の小さなオブジェクトを超える規模、そして WINDOWS の file-system identity。

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
| FSx API 経由で DP ボリュームを mount しようとする | 拒否される。`CreateVolume` はフィールド名を挙げて `JunctionPath` を拒否し、`UpdateVolume` は 200 を返して破棄する | ONTAP 側で mount し、FSx API が junction path を報告するのを待ってからアタッチする（§3.2） |
| `UpdateVolume` の 200 応答を junction path 設定成功の証拠として扱う | DP ボリュームでは Volume オブジェクトを返して**無言で何もしない**。エラーも `AdministrativeActions` エントリも失敗メッセージもない。自動化が誤った前提で先へ進む | `DescribeVolumes` で `JunctionPath` を読み直してその値で判定する。`UpdateVolume` の応答では判定しない |
| 「SnapMirror を break しなければならない」を理由に宛先側 S3 AP 構成を却下する | 誤り。稼働中の宛先は ONTAP で mount すれば AP 経由で読み取りを提供し、クローンは書き込みも提供する。break は本番サービスの引き継ぎのためだけ | §3.2 |
| クローンや新規 mount した宛先を「分単位で」と約束する | ONTAP 側の操作は数秒だが、FSx コントロールプレーンがアタッチ可能として報告するまで 1011 秒と 2298 秒を要した | 初回セットアップは数十分を見込む。その後の定常的な鮮度は数秒 |
| `aws fsx delete-volume` を「削除済み」と読む | 実際は「削除待ちに投入」である。ONTAP はボリュームを改名して**ボリューム recovery queue**（type `del`、既定の保持は 12 時間）へ移し、その間 FSx API は削除済みと報告する。queue にある FlexClone は親の Snapshot を保持し続けるため、親は "has one or more clones" で削除を拒否するが、そのクローンは `DescribeVolumes`・`/api/storage/volumes`・既定権限の `volume show` のいずれにも現れない | `volume recovery-queue show` で確認し `volume recovery-queue purge` する（advanced 権限）。その後 親は正常に削除できる。機構と保持期間の設定は [Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook) の `docs/ja/domains/block-storage/notes/lun-layout-decides-recovery-granularity.md` |
| AP を取り付けたボリュームの撤去手順を ONTAP の `volume delete` で組む | AP の内部バケットはボリューム単位なので、一時的にではなく**恒久的に**削除を阻む。取り付けに失敗した AP のボリュームでも同じ | AWS 側の API で削除する。同 playbook の `s3-access-point-constraints.md`「撤去時の停滞」 |
| オブジェクト API に列挙されないことをクローン不在の根拠とする | queue にあるクローンは `privilege_level=diagnostic`、`volume clone show`、recovery queue にのみ現れる | recovery queue に問う |
| snapshot の一覧が空であることを Snapshot 依存なしの根拠とする | `snapshot show` は**オフライン**のボリュームに対して何も返さず、CLI passthrough はその理由を示すがオブジェクト API は示さない。オンラインにすると同じボリュームが、保持中の Snapshot を `busy` かつ `owners: ["volume clone"]` として報告した | snapshot のクエリを信じる前にボリュームをオンラインにする |
| `GET /api/protocols/s3/buckets` が空であることを AP のバケット残存なしの証拠と読む | AP の内部バケット `amazon-fsx-fsvol-*` はここに列挙されないが、ボリューム削除をブロックし、エラーメッセージには名前が出る | 強制せず、解消を待って削除を再試行する |
| ONTAP REST API のみで DP ボリューム作成 | FSx API への反映に ~30 分かかる。即時 S3 AP アタッチ不可 | 即時性が必要なら `aws fsx create-volume` を使用。FlexCache 等は ONTAP API で作成後 ~30 分待機 |
| VPC Peering を SVM peer 削除前に削除 | zombie SVM peer → MISCONFIGURED → 復旧困難 | SM-VAL-011 の順序を遵守 |
| ListObjectsV2 を全件走査で定期実行 | ディレクトリサイズに比例してレイテンシ増大 | prefix 限定 or 外部カタログ |
| データグラビティを無視してクラウドのみで設計 | 不要なエグレス費用。レイテンシ要件を満たせない | オンプレ処理が有利な場面では SnapMirror でオンプレに複製して活用 |

---

## 関連ドキュメント

- [S3 AP 全般の設計考慮事項](s3ap-design-considerations.md)
- [S3 AP データ収集 CloudFormation テンプレート（設計 TIPS 付き）](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/tree/main/infrastructure/s3ap-data-collection) — Mermaid 設計判断フローにデータ配信パターン分岐を含む
- [S3 AP + SnapMirror + FlexCache 調査・検証](../../integrations/snapmirror-flexcache-multicloud/docs/ja/research.md)
- 検証記録: [S3AP-DP-ATTACH-002 — 稼働中の SnapMirror 宛先の提供（2026-09-13、VPC 内）](../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13-in-vpc/evidence-record.yaml) · [S3AP-DP-ATTACH-001 — FSx API のみの初回検証](../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13/evidence-record.yaml)
- [Demo Guide 07: SnapMirror Cross-Region + S3 AP Re-Attach](../../integrations/snapmirror-flexcache-multicloud/docs/ja/demo-guide-07-snapmirror-cross-region.md)
- [Demo Guide 01: FlexCache Same-Region](../../integrations/snapmirror-flexcache-multicloud/docs/ja/demo-guide-01-flexcache-same-region.md)
- [AWS Docs: S3 performance best practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html)
- [NetApp KB: maxdir-size issues](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/How_do_I_avoid_maxdir-size_issues)
- [NetApp Docs: FlexGroup definition](https://docs.netapp.com/us-en/ontap/flexgroup/definition-concept.html)
- [NetApp Docs: FlexCache hotspot remediation](https://docs.netapp.com/us-en/ontap/flexcache-hot-spot/flexcache-hotspot-remediation-architecture.html)
- [NetApp Blog: FlexGroups and Advanced Data Distribution](https://community.netapp.com/t5/Tech-ONTAP-Blogs/FlexGroups-and-Advanced-Data-Distribution/ba-p/456416)
