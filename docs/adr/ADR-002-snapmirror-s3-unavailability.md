# ADR-002: SnapMirror S3 が FSx for ONTAP で利用不可であることの確認と対応方針

| 属性 | 値 |
|------|---|
| **Status** | Accepted |
| **Date** | 2026-05-26 |
| **Decision makers** | プロジェクトアーキテクチャチーム |
| **Related blockers** | [BLK-004](../ja/blocker-tracker.md) |

---

## Context

ONTAP 9.10.1+ のドキュメントには SnapMirror S3（ONTAP S3 バケットから AWS S3 バケットへのオブジェクトレプリケーション）が記載されている。オンプレミス ONTAP 環境では利用可能な機能であり、FSx for ONTAP でも利用可能であれば DataSync より効率的な同期メカニズムとなる可能性があった。

検証の目的:
- FSx for ONTAP で SnapMirror S3 が利用可能か確認する
- 利用不可の場合、公式な制約として記録し代替方針を確定する

## Decision

**SnapMirror S3 は FSx for ONTAP で利用不可であることを公式に確認・記録し、AWS DataSync を唯一の検証済み同期メカニズムとして位置づける。**

### 検証結果（2026-05-26）

| 検証項目 | 結果 |
|---------|------|
| `snapmirror object-store` CLI コマンド | "not a recognized command" |
| `/api/cloud/targets` REST API | "not authorized for that command" |
| AWS Support への問い合わせ | サービスレベルの制限として確認 |

### 対応方針

1. SnapMirror S3 を推奨パスや代替パスとして提案しない
2. ドキュメントで「FSx for ONTAP では SnapMirror S3 は利用不可」を明示する
3. AWS への Feature Request を提出済み（BLK-004 として追跡）
4. 将来的に利用可能になった場合は ADR-001 を再評価する

## Consequences

### 良い影響
- **明確な設計境界**: 「SnapMirror S3 で解決できるのでは？」という繰り返しの議論を防止
- **DataSync への集中投資**: 代替検討に時間を使わず、DataSync パスの最適化に集中
- **正確な情報共有**: オンプレミス ONTAP との機能差異を明示し、誤った期待を防止

### 悪い影響・制約
- **ONTAP ネイティブ効率の喪失**: SnapMirror S3 は変更ブロック単位のレプリケーションが可能だが、DataSync はファイル単位の増分検出
- **NFS 経由の制約**: DataSync は NFS プロトコル経由のみ。ONTAP S3 プロトコル経由の直接同期パスが存在しない
- **オンプレミス → クラウド移行時のギャップ**: オンプレミスで SnapMirror S3 を利用している環境が FSx for ONTAP に移行する際、同期アーキテクチャの再設計が必要

### リスク
- AWS が将来的に SnapMirror S3 を有効化した場合、本 ADR は Superseded となり、ADR-001 の再評価が必要
- 利用者が「オンプレ ONTAP では使えるのに」と不満を抱くリスク → FAQ で先手を打つ

## Alternatives Considered

### SnapMirror S3 を「将来的に対応予定」として記載する（却下）

- **理由**: AWS からのタイムラインコミットがない。「対応予定」と記載すると読者に誤った期待を与える
- Feature Request は提出済みだが、対応時期は未定

### ONTAP S3 → カスタム S3 レプリケーション（却下）

- **理由**: ONTAP S3 の ListObjectsV2 から変更を検出し、カスタム Lambda で標準 S3 にコピーするパターンは技術的に可能だが、DataSync が同じことをマネージドで実現する。運用複雑性の増加に見合わない

### FSx for ONTAP FabricPool の tier 先を直接利用（却下）

- **理由**: FabricPool で S3 に tier されたデータは技術的には標準 S3 に存在するが、ONTAP が内部管理するストレージであり、ユーザーが直接 UC に登録することは想定されていない。データの一貫性が保証されない

## References

- [SnapMirror S3 検証エビデンス](../../verification-pack/snapmirror-s3/evidence/2026-05-26/evidence-record.yaml)
- [ブロッカー追跡: BLK-004](../ja/blocker-tracker.md)
- [DataSync → S3 ガイド: なぜ SnapMirror S3 ではないのか](../ja/datasync-to-s3-guide.md)
- [NetApp ONTAP ドキュメント: SnapMirror S3](https://docs.netapp.com/us-en/ontap/s3-snapmirror/index.html)（オンプレミス向け）
