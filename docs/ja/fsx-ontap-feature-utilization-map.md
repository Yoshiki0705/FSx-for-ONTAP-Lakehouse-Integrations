🌐 [English](../en/fsx-ontap-feature-utilization-map.md) | **日本語**

# FSx for ONTAP 機能活用マップ

> **目的**: 本リポジトリの各接続パス/ドキュメントで、FSx for ONTAP のどの機能が活用されているかを一覧化します。
> **最終更新**: 2026-06-20

---

## エグゼクティブサマリ

FSx for ONTAP は「**エンタープライズデータ保護 + マルチプロトコル + Lakehouse 統合**」を単一プラットフォームで提供します。標準 S3 + EBS では以下の組み合わせを実現できません:

- 同じデータに NFS / SMB / S3 API で同時アクセス
- ストレージ効率の高いゼロコスト FlexClone（検証/開発環境の瞬時作成）
- 一貫性のある Point-in-Time Snapshot（DataSync のソース整合性）
- ファイルレベルイベント検知（FPolicy → リアルタイムパイプライン）
- SnapMirror によるクロスリージョン DR（RPO 分単位）

---

## 機能 × 接続パス マトリクス

| FSx for ONTAP 機能 | DataSync → S3 → UC | Kafka (FPolicy) → UC | Athena / Glue 直接 | Snowflake 直接 | Bedrock KB | AI カタログ |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **S3 Access Points** | — (NFS ソース) | — | ✅ 必須 | ✅ 必須 | ✅ 必須 | ✅ 必須 |
| **NFS v4.1** | ✅ ソースプロトコル | — | — | — | — | — |
| **SMB** | — | — | — | — | — | — |
| **マルチプロトコル同時アクセス** | ✅ 価値の根拠 | ✅ 価値の根拠 | ✅ 価値の根拠 | ✅ 価値の根拠 | ✅ 価値の根拠 | ✅ 価値の根拠 |
| **Snapshot** | ✅ ソース整合性 | — | — | — | — | ✅ 一貫性 |
| **FlexClone** | ✅ 本番分離 | — | — | — | — | ✅ 検証環境 |
| **FPolicy** | — | ✅ イベント検知 | — | — | — | — |
| **SnapMirror** | — | — | — | — | — | — |
| **FabricPool（階層化）** | — | — | — | — | — | — |
| **SVM 分離** | ✅ テナント分離 | ✅ テナント分離 | ✅ テナント分離 | ✅ テナント分離 | — | — |
| **ONTAP Volume 暗号化** | ✅ at-rest | ✅ at-rest | ✅ at-rest | ✅ at-rest | ✅ at-rest | ✅ at-rest |

---

## 機能別詳細: この機能を使う理由

### S3 Access Points

| 属性 | 値 |
|------|---|
| **使用箇所** | Athena / Glue / EMR / Snowflake / Bedrock KB のデータアクセス |
| **特徴** | NFS/SMB で書き込んだデータを S3 API で読み取り可能（変換/コピー不要） |
| **制約** | conditional writes 非サポート、Event Notifications 非サポート（[BLK-002](./blocker-tracker.md), [BLK-003](./blocker-tracker.md)） |
| **関連ドキュメント** | [互換性マトリクス](./compatibility-matrix.md), [Networking](./fsx-ontap-s3ap-networking.md) |

> **マルチプロトコルの真価**: S3 AP の価値は「S3 API を追加提供する」ことではなく、「NFS/SMB で業務ユーザーがアクセスする**同じデータ**を変換なしで分析エンジンから読める」ことです。EBS + S3 の組み合わせでは、データのコピーまたは ETL が常に必要になります。

### Snapshot

| 属性 | 値 |
|------|---|
| **使用箇所** | DataSync のソース整合性確保、AI カタログの一貫性、DR |
| **特徴** | ゼロコスト（書き込み発生まで容量消費なし）、瞬時取得、アプリケーション停止不要 |
| **制約** | Snapshot 単体では他リージョンへのレプリケーションは不可（SnapMirror と組み合わせ） |
| **関連ドキュメント** | [DataSync ガイド](./datasync-to-s3-guide.md)（Phase 2）, [Recovery Semantics](./recovery-semantics.md) |

> **DataSync + Snapshot パターン**: Snapshot → FlexClone → DataSync の順で実行することで、「業務影響ゼロ + データ一貫性 + 増分同期」のトリプルメリットを実現します。Snapshot がなければ、同期中のファイル変更でデータ不整合のリスクがあります。

### FlexClone

| 属性 | 値 |
|------|---|
| **使用箇所** | DataSync の本番分離、開発/テスト環境の瞬時作成 |
| **特徴** | **ゼロ追加ストレージ**（書き込みが発生するまで容量を消費しない）、瞬時作成（TB 規模でも秒単位） |
| **制約** | クローン先への書き込みが増えると容量消費が開始される |
| **関連ドキュメント** | [DataSync ガイド](./datasync-to-s3-guide.md)（Phase 2）, [ADR-001](../adr/ADR-001-datasync-as-primary-sync.md) |

> **ゼロコストの意味**: FlexClone は WAFL（Write Anywhere File Layout）のメタデータ参照により、物理コピーなしでボリュームの完全なクローンを作成します。1 TB のボリュームを FlexClone しても追加ストレージは 0 bytes です。EBS Snapshot とは異なり、読み取り可能な独立ボリュームとして即座にマウント可能です。

### FPolicy

| 属性 | 値 |
|------|---|
| **使用箇所** | Kafka → Structured Streaming パスのイベントソース、準リアルタイム S3 同期 |
| **特徴** | ファイル操作（作成/変更/削除/リネーム）をリアルタイムで外部に通知。S3 Event Notifications の代替 |
| **制約** | メタデータイベントのみ（ファイル内容は転送しない）、Lambda 経由の運用複雑性 |
| **関連ドキュメント** | [Kafka-ClickHouse-UC 接続](./kafka-clickhouse-unity-catalog-connectivity.md), [DataSync ガイド](./datasync-to-s3-guide.md)（FPolicy 代替パターン） |

> **S3 Event Notifications の代替**: FSx for ONTAP S3 AP が Event Notifications をサポートしません（BLK-003）。**FPolicy は代替になりません**: FPolicy が検知するのは NFS / SMB のファイル操作で、S3 AP 経由の操作は検知せず、`mandatory` 指定でも遮断しません（実測 2026-08-26 / ONTAP 9.18.1P3D1、[FPolicy と S3 Access Point のカバレッジ実測](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/docs/ja/s3ap-monitoring-coverage-implications.md)）。AP 経由の書き込みを起点にするなら、EventBridge Scheduler によるポーリングか ONTAP ネイティブ監査ログ（AP 経由の操作を `Source=HTTP` / `Source=S3` で記録）を使います。書き込みが NFS / SMB 経由のボリュームでは FPolicy が引き続き使えます。

### SnapMirror

| 属性 | 値 |
|------|---|
| **使用箇所** | クロスリージョン DR、データモビリティ |
| **特徴** | ブロック単位の効率的レプリケーション（RPO 分単位）。Volume 全体を別リージョンに同期 |
| **制約** | SnapMirror **S3**（ONTAP S3 → AWS S3）は FSx for ONTAP で利用不可（[BLK-004](./blocker-tracker.md)）。Volume レベルの SnapMirror は利用可能 |
| **関連ドキュメント** | [ADR-002](../adr/ADR-002-snapmirror-s3-unavailability.md), [ブロッカー追跡](./blocker-tracker.md) |

> **Volume SnapMirror vs SnapMirror S3 の区別**: Volume レベルの SnapMirror（FSx for ONTAP 間のレプリケーション）は完全に利用可能です。利用不可なのは「ONTAP S3 バケット → AWS S3 バケット」へのオブジェクトレプリケーション（SnapMirror S3）のみです。DR 設計では Volume SnapMirror を活用できます。

### FabricPool（階層化）

| 属性 | 値 |
|------|---|
| **使用箇所** | コスト最適化（コールドデータの S3 自動階層化） |
| **特徴** | アクセス頻度に応じてデータを SSD → S3 に自動移動。アプリケーションからは透過的（パス変更不要） |
| **制約** | 階層化されたデータの最初の読み取りにレイテンシ追加。分析ワークロードでは影響を考慮 |
| **関連ドキュメント** | [UC 接続総合ガイド](./fsx-ontap-to-databricks-unity-catalog-guide.md)（今後の展望セクション） |

### SVM（Storage Virtual Machine）分離

| 属性 | 値 |
|------|---|
| **使用箇所** | テナント/ワークロード分離（本番 vs 開発、工場 A vs 工場 B） |
| **特徴** | 単一ファイルシステム上でネットワーク/認証/ストレージを論理的に完全分離 |
| **制約** | SVM 数の制限（FSx for ONTAP のクォータ依存） |
| **関連ドキュメント** | [互換性マトリクス](./compatibility-matrix.md)（OT/IT セキュリティ） |

---

## 技術比較: FSx for ONTAP vs 代替ストレージ

> **注**: 以下は技術的特性の比較であり、サービスの優劣を主張するものではありません。ユースケースに応じて適切な選択が異なります。

| 要件 | FSx for ONTAP | Amazon S3 + EBS | 選択の指針 |
|------|:---:|:---:|---|
| NFS + SMB + S3 同時アクセス | ✅ ネイティブ | ❌ 不可 | 業務ユーザー（NFS/SMB）と分析エンジン（S3）が同じデータを扱う場合 |
| ゼロコスト Clone（開発/テスト） | ✅ FlexClone | ❌ 別途コピー | 本番データの検証環境を即座に作成する必要がある場合 |
| Point-in-Time 整合性 | ✅ Snapshot（瞬時） | ⚠️ EBS Snapshot（分単位） | DataSync ソースの一貫性が重要な場合 |
| ファイルイベント検知 | ✅ FPolicy | ❌ 非対応 | イベント駆動パイプラインが必要な場合 |
| 容量プール階層化 | ✅ FabricPool | ✅ S3 Intelligent-Tiering | コールドデータの自動階層化が必要な場合（両方で対応可能） |
| 条件付き書き込み | ❌ 非サポート | ✅ S3 対応 | Delta/Iceberg 書き込みが必要な場合は標準 S3 |
| Event Notifications | ❌ 非サポート | ✅ S3 対応 | Auto Loader 通知モードが必要な場合は標準 S3 |
| スケール（容量無制限） | ⚠️ ボリュームサイズ制限 | ✅ 事実上無制限 | ペタバイト規模のデータレイクには標準 S3 |

> **右ツールの選択**: FSx for ONTAP は「エンタープライズファイルデータ + マルチプロトコルアクセス + データ保護」が主要要件の場合に最適です。純粋なオブジェクトストレージ用途（大規模データレイク、CDN オリジン）には標準 S3 が適切です。多くのエンタープライズ環境では**両方を組み合わせて使用**します（FSx for ONTAP = ソース + 業務アクセス、S3 = 分析コピー + Lakehouse）。

---

## ドキュメント横断: 機能とドキュメントの対応

| ドキュメント | S3 AP | Snapshot | FlexClone | FPolicy | SnapMirror | FabricPool | SVM | Multi-AZ |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| [UC 接続総合ガイド](./fsx-ontap-to-databricks-unity-catalog-guide.md) | ● | ● | ● | ● | ○ | ○ | ○ | — |
| [DataSync → S3 ガイド](./datasync-to-s3-guide.md) | — | ● | ● | ● | — | — | — | — |
| [互換性マトリクス](./compatibility-matrix.md) | ● | — | — | — | — | — | ○ | ● |
| [Kafka-ClickHouse-UC](./kafka-clickhouse-unity-catalog-connectivity.md) | — | — | — | ● | — | — | — | — |
| [S3 Annotations 評価](./s3-annotations-governance-evaluation.md) | — | ○ | — | ● | — | — | — | — |
| [Recovery Semantics](./recovery-semantics.md) | — | ● | ● | — | ● | — | — | ● |
| [Networking](./fsx-ontap-s3ap-networking.md) | ● | — | — | — | — | — | ● | — |
| [Event-driven Architecture](./event-driven-architecture.md) | — | — | — | ● | — | — | — | — |
| [ブロッカー追跡](./blocker-tracker.md) | ● | — | — | — | ○ | — | — | — |

**凡例**: ● = 主要トピックとして詳述 / ○ = 言及あり / — = 非言及

---

## 関連ドキュメント

- [UC 接続総合ガイド](./fsx-ontap-to-databricks-unity-catalog-guide.md) — 全接続パスの俯瞰
- [ブロッカー追跡](./blocker-tracker.md) — 制約の詳細と解消見通し
- [ADR-001](../adr/ADR-001-datasync-as-primary-sync.md) — DataSync 採用理由（Snapshot/FlexClone 活用含む）
- [読み順ガイド](./reading-path-guide.md) — ドキュメント全体のナビゲーション
