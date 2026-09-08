# ADR-001: DataSync を FSx for ONTAP → S3 の主要同期メカニズムとして採用

| 属性 | 値 |
|------|---|
| **Status** | Accepted |
| **Date** | 2026-05-26 |
| **Decision makers** | プロジェクトアーキテクチャチーム |
| **Related blockers** | [BLK-001](../ja/blocker-tracker.md), [BLK-004](../ja/blocker-tracker.md) |

---

## Context

FSx for ONTAP 上のデータを Databricks Unity Catalog、Delta Lake、Iceberg、Snowflake（AUTO_REFRESH/Cortex Search）等の下流プラットフォームで利用する場合、標準 S3 バケットへのデータ同期が必要である。

同期メカニズムの候補は以下の3つ:

1. **AWS DataSync** — マネージドサービス。NFS → S3 の増分同期
2. **SnapMirror S3** — ONTAP ネイティブ。S3 バケット間レプリケーション
3. **カスタム ETL（Glue/EMR/Lambda）** — ユーザー実装の同期パイプライン

## Decision

**AWS DataSync を FSx for ONTAP → 標準 S3 バケットへの主要同期メカニズムとして採用する。**

具体的には:
- `TransferMode: CHANGED`（増分同期）をデフォルトとする
- `PreserveDeletedFiles: REMOVE` で削除同期を有効化する
- スケジュールは `rate(5 minutes)` 〜 `rate(1 hour)` の範囲で用途に応じて設定
- Snapshot / FlexClone ベースのステージングパターンを本番推奨とする（FlexClone はゼロ追加ストレージ — 書き込みが発生するまで容量を消費しない ONTAP 固有の効率性）

## Consequences

### 良い影響
- **マネージド**: インフラ管理不要。AWS が転送最適化、リトライ、帯域制御を担当
- **増分**: 変更バイトのみ転送。1 TB 初回 + 10 GB/日増分で月額約$27
- **監査**: CloudTrail に `StartTaskExecution` を記録。データ移動の追跡可能
- **検証済み**: 本リポジトリで動作確認済み（PoC + スケジュール実行）
- **本番影響回避**: Snapshot/FlexClone ステージングで業務ワークロードに影響なし

### 悪い影響・制約
- **データコピーが発生**: FSx for ONTAP + S3 の二重ストレージコスト
- **ゼロコピーではない**: 同期レイテンシ（最短 5 分）が存在
- **リアルタイム不可**: 1 分未満のレイテンシ要件には対応できない
- **NFS 経由のみ**: ONTAP S3 プロトコル経由の直接同期は非サポート（SnapMirror S3 が利用不可のため）

### リスク
- DataSync タスクの重複実行（前回未完了のまま次回起動）のリスクがあり、大量ファイル環境ではスケジュール間隔の調整が必要
- AWS DataSync サービスの料金改定リスク（現在 $0.0125/GB）

### スケール考慮事項
- **初回同期 > 10 TB**: DataSync は対応可能だが、完了まで数時間〜数日。ネットワーク帯域とスループットキャパシティの事前見積もりが必要
- **変更レート > 1000 files/sec**: DataSync のスキャンフェーズが律速になる可能性あり。includes/excludes フィルタで対象を分割し、複数タスクに並列化を検討
- **> 100 万ファイル/タスク**: タスクスキャン時間が増大。パーティション単位でタスクを分離し、EventBridge で並列起動する設計を推奨

## Alternatives Considered

### SnapMirror S3（却下）

- **理由**: FSx for ONTAP で利用不可（[ADR-002](./ADR-002-snapmirror-s3-unavailability.md) 参照）
- CLI コマンド未認識、REST API 未認可を確認済み
- 利用可能になった場合は本 ADR を再評価

### カスタム ETL（Glue/EMR/Lambda）

- **理由**: DataSync が提供する機能と重複し、運用複雑性が不要に増加する
- DataSync は AWS マネージドで帯域制御・リトライ・スケジュール・CloudTrail 統合を提供
- カスタム ETL は変換を伴う場合（スキーマ変換、フォーマット変換）には依然として有効 → DataSync で raw 同期後に Glue/EMR で変換する Medallion パターンを推奨

### FPolicy → Lambda → S3

- **理由**: イベント駆動で準リアルタイム（秒単位）だが、運用複雑性が高い
- Lambda 同時実行制限、DLQ 管理、バックプレッシャー対策が必要
- 1 分未満のレイテンシ要件がある場合にのみ採用 → DataSync との併用パターンとして設計
- **2026-08-26 追記（この選択肢の適用範囲）**: S3 Access Point 経由で届いた書き込みは FPolicy 通知を発火しないことを実測（ONTAP 9.18.1P3D1）。この選択肢が成立するのは書き込みが NFS / SMB 経由の場合に限られる。S3 API で書く構成では比較対象にならない

## References

- [DataSync → S3 ガイド](../ja/datasync-to-s3-guide.md)
- [ブロッカー追跡: BLK-004](../ja/blocker-tracker.md)（SnapMirror S3 利用不可）
- [AWS DataSync ドキュメント](https://docs.aws.amazon.com/datasync/latest/userguide/create-ontap-location.html)
- [SnapMirror S3 検証エビデンス](../../verification-pack/snapmirror-s3/evidence/2026-05-26/evidence-record.yaml)
