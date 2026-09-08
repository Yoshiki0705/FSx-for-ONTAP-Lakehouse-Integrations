# リカバリセマンティクス: ONTAP Snapshot vs. Lakehouse Time Travel

## 概要

本ドキュメントは、ONTAP Snapshot（ストレージレベルのポイントインタイムリカバリ）と Lakehouse Time Travel（Delta Lake / Apache Iceberg のメタデータベース論理リカバリ）の関係を明確にします。これらは**補完的だが根本的に異なるメカニズム**であり、異なる障害モードから保護します。

## メカニズム比較

| 観点 | ONTAP Snapshot | Delta Lake Time Travel | Iceberg Time Travel |
|------|---------------|----------------------|---------------------|
| **レイヤー** | ストレージ（ブロックレベル） | テーブルメタデータ（トランザクションログ） | テーブルメタデータ（マニフェストリスト） |
| **粒度** | ボリューム全体 | 単一テーブル | 単一テーブル |
| **キャプチャ対象** | ポイントインタイムのボリューム上全ファイル | コミットされたトランザクションごとのテーブル状態 | スナップショットごとのテーブル状態 |
| **リカバリ方法** | ボリューム復元または `.snapshot` ディレクトリアクセス | `VERSION AS OF` または `TIMESTAMP AS OF` でクエリ | `snapshot_id` または `as_of_timestamp` でクエリ |
| **保持期間** | 設定可能なスナップショットポリシー（時間/日/週） | 設定可能な `delta.logRetentionDuration`（デフォルト 30 日） | 設定可能な `history.expire.max-snapshot-age-ms` |
| **容量効率** | Copy-on-write（変更ブロックのみ保存） | VACUUM まで以前のデータファイルを保持 | 有効期限まで以前のデータファイルを保持 |
| **テーブル横断の一貫性** | あり（ボリュームレベルのアトミックスナップショット） | なし（テーブル単位のみ） | なし（テーブル単位のみ） |
| **保護対象** | 誤削除、破損、ランサムウェア、ボリュームレベルの障害 | テーブル操作の論理エラー、不正な書き込み、スキーマミス | Delta と同じ |
| **保護対象外** | 既にコミットされた論理的なアプリケーションエラー | ストレージレベルの障害、ボリューム喪失、マルチテーブル不整合 | Delta と同じ |

## 使い分けの判断

### ONTAP Snapshot を使う場合：

| シナリオ | Snapshot を使う理由 |
|---------|-------------------|
| ボリュームレベルの災害復旧 | 全ファイルを一貫したポイントにアトミックに復元 |
| ランサムウェアリカバリ | 不変のスナップショットは侵害されたアプリケーションから変更不可 |
| テーブル横断の一貫性 | 複数テーブル/ファイルを同じポイントインタイムに復元する必要がある |
| 誤ったボリューム削除 | Snapshot + SnapMirror でボリューム外の保護を提供 |
| コンプライアンス: 長期保持 | SnapLock + Snapshot で WORM コンプライアンス |
| メンテナンス前のチェックポイント | メンテナンスで問題が発生した場合の迅速なロールバック |

### Lakehouse Time Travel を使う場合：

| シナリオ | Time Travel を使う理由 |
|---------|---------------------|
| 不正なテーブル書き込みの取り消し | 他のデータに影響を与えずに単一テーブルを元に戻す |
| テーブル変更の監査 | コンプライアンスのために過去のテーブル状態をクエリ |
| 分析結果の再現 | 過去のテーブルバージョンに対してクエリを再実行 |
| データパイプラインのデバッグ | 変換前後のテーブル状態を比較 |
| スキーマ進化のロールバック | 単一テーブルのスキーマ変更を元に戻す |

### 両方を併用する場合：

| シナリオ | アプローチ |
|---------|----------|
| 多層防御 | ストレージレベル保護に Snapshot + 論理レベル保護に Time Travel |
| 規制環境 | 災害復旧 SLA に Snapshot + 監査証跡に Time Travel |
| マルチテーブルパイプライン障害 | 一貫した状態にボリュームを復元する Snapshot、その後個別テーブル状態を確認する Time Travel |

## FSx for ONTAP S3 Access Point コンテキストでの重要な注意事項

1. **Lakehouse Time Travel には書き込みアクセスが必要**: Delta Lake と Iceberg の Time Travel はデータと並行してトランザクションログ/メタデータが書き込まれることに依存します。FSx for ONTAP S3 AP にはアトミック rename（Delta が必要）と条件付き書き込みの制限があるため、**Time Travel はトランザクションログが外部で管理されるテーブル**（例: Glue Catalog をメタデータストアとする Iceberg）または既存のバージョン管理済みテーブルへの読み取り専用アクセスでのみ利用可能です。

2. **ONTAP Snapshot はアクセス方法に関係なく動作**: Snapshot はブロックレベルでボリューム状態をキャプチャし、データが NFS、SMB、S3 API のいずれで書き込まれたかに依存しません。これにより、S3 Access Points 経由でアクセスされるデータの**主要なリカバリメカニズム**は Snapshot になります。

3. **Snapshot はテーブルセマンティクスを理解しない**: Snapshot の復元は、進行中の書き込みを含む全ファイルを復元します。Lakehouse テーブルの場合、テーブルのトランザクションログとデータファイルが一緒に復元されるため、テーブルが修復を必要とする状態（例: ロールバックされたコミットが参照する孤立データファイル）になる可能性があります。

## リカバリ判断マトリクス

| 障害タイプ | 主要リカバリ | 副次リカバリ |
|-----------|------------|------------|
| 誤ったファイル削除 | ONTAP Snapshot（`.snapshot` ディレクトリアクセス） | — |
| テーブルへの不正データ書き込み | Lakehouse Time Travel（利用可能な場合） | ONTAP Snapshot |
| ボリューム破損 | ONTAP Snapshot 復元 | SnapMirror フェイルオーバー |
| ランサムウェア | ONTAP Snapshot（不変） | 隔離された DR への SnapMirror |
| リージョン障害 | SnapMirror クロスリージョン | — |
| スキーマ移行エラー | Lakehouse Time Travel | ONTAP Snapshot |
| マルチテーブル不整合 | ONTAP Snapshot（ボリュームレベルアトミック） | 手動調整 |
| コンプライアンス監査（テーブル履歴） | Lakehouse Time Travel | — |
| コンプライアンス監査（ストレージ履歴） | ONTAP Snapshot + SnapLock | — |

## RTO / RPO 比較

| メカニズム | 典型的な RPO | 典型的な RTO | 備考 |
|-----------|------------|------------|------|
| ONTAP Snapshot | 分〜時間（ポリシーによる） | 秒〜分 | スナップショットからのほぼ即時復元 |
| SnapMirror（非同期） | 分（スケジュールによる） | 分 | DR ボリュームへのフェイルオーバー |
| SnapMirror（同期） | ゼロ | 分 | 同期レプリケーション |
| Delta Time Travel | コミット単位（書き込みごと） | 秒 | クエリレベル、復元不要 |
| Iceberg Time Travel | コミット単位（書き込みごと） | 秒 | クエリレベル、復元不要 |
| FSx for ONTAP バックアップ | 日次（自動） | 時間 | バックアップからの完全ボリューム復元 |

## 参考資料

- [ボリュームバックアップによるデータ保護](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-backups.html)
- [アクセスポイントの互換性](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
- [Amazon FSx for NetApp ONTAP のパフォーマンス](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/performance.html)
