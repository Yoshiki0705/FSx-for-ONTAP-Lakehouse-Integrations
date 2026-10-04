[English](../en/e2e-sequence-diagrams.md) | **日本語**

# End-to-End データフロー シーケンス図

> **目的**: FSx for ONTAP から下流分析プラットフォームまでの全データフローを、レイテンシ・データ量・障害時動作と共に可視化します。
> **最終更新**: 2026-06-21

---

## 概要

本ドキュメントでは、本リポジトリの 2 つの主要パスを mermaid シーケンス図で詳細化します:

1. **DataSync パス**（バッチ/準リアルタイム）: PLC → FSx for ONTAP → DataSync → S3 → Databricks UC
2. **FPolicy パス**（イベント駆動/準リアルタイム）: PLC → FSx for ONTAP → FPolicy → Lambda → Kafka → UC Delta

---

## パス 1: DataSync パス（推奨・本番向け）

### シーケンス図

```mermaid
sequenceDiagram
    participant PLC as PLC/SCADA
    participant Edge as Edge Gateway
    participant FsxOntap as FSx for ONTAP<br/>(NFS Volume)
    participant Snap as Snapshot/FlexClone
    participant DS as AWS DataSync
    participant S3 as Amazon S3<br/>(標準バケット)
    participant AL as Auto Loader<br/>(通知モード)
    participant UC as Databricks UC<br/>(Delta Table)

    Note over PLC,Edge: OT ネットワーク（工場）
    Note over FsxOntap,UC: IT ネットワーク（AWS VPC）

    PLC->>Edge: センサーデータ送信<br/>(OPC UA / MQTT / CSV export)
    Edge->>FsxOntap: NFS 書き込み<br/>(/vol1/data/sensor/*.csv)
    
    Note over FsxOntap: ファイル蓄積（5秒間隔）

    rect rgb(240, 248, 255)
        Note over FsxOntap,Snap: Phase 2: Snapshot ステージング
        FsxOntap->>Snap: Snapshot 取得（瞬時・ゼロコスト）
        Snap->>Snap: FlexClone 作成（瞬時・ゼロストレージ）
    end

    rect rgb(255, 248, 240)
        Note over Snap,S3: DataSync 転送
        DS->>Snap: NFS 読み取り（FlexClone から）
        Note right of DS: TransferMode: CHANGED<br/>変更バイトのみ転送
        DS->>S3: S3 PutObject<br/>($0.0125/GB)
    end

    rect rgb(240, 255, 240)
        Note over S3,UC: UC 取り込み
        S3-->>AL: S3 Event Notification<br/>(SQS 経由)
        AL->>UC: 増分取り込み<br/>(Delta append)
    end

    Note over UC: UC ガバナンス適用<br/>(Row Filter / Column Mask / Tags)
```

### レイテンシバジェット

| ステップ | レイテンシ | 累積 | 備考 |
|---------|:---:|:---:|------|
| PLC → Edge Gateway | ~1 ms | 1 ms | OPC UA / ローカルネットワーク |
| Edge → FSx for ONTAP (NFS write) | ~5 ms | 6 ms | NFS v4.1 over VPC |
| ファイル蓄積（バッファリング） | 5 秒〜5 分 | 5 分 | Edge Gateway のバッチ書き込み間隔 |
| Snapshot + FlexClone | ~1 秒 | 5 分 | 瞬時操作 |
| DataSync スキャン + 転送 (10 GB) | 1-2 分 | 7 分 | CHANGED モード |
| S3 Event → SQS → Auto Loader | ~30 秒 | 7.5 分 | 通知伝播 + ポーリング |
| Auto Loader → Delta 書き込み | ~30 秒 | **8 分** | Spark マイクロバッチ |

> **合計 E2E レイテンシ**: PLC 出力から UC Delta テーブルクエリ可能まで **約 7-12 分**（DataSync 5 分スケジュール時）

### 障害シナリオと復旧

| 障害ポイント | 影響 | 検知方法 | 復旧手順 |
|---|---|---|---|
| Edge → FSx for ONTAP 切断 | データ蓄積停止 | NFS mount 監視 | Edge ローカルバッファ → 再接続後に再送 |
| FSx for ONTAP 障害 | Multi-AZ フェイルオーバー | CloudWatch FSx metrics | 自動フェイルオーバー（~30 秒） |
| DataSync 失敗 | 同期遅延 | CloudWatch アラーム | [Runbook #01](../../runbooks/01-datasync-failure-triage.md) |
| S3 書き込み失敗 | DataSync リトライ | DataSync execution status | 自動リトライ（DataSync 内蔵） |
| Auto Loader 失敗 | 取り込み遅延 | Spark Streaming metrics | Checkpoint から再開（exactly-once） |

---

## パス 2: FPolicy パス（イベント駆動）

### シーケンス図

```mermaid
sequenceDiagram
    participant PLC as PLC/SCADA
    participant FsxOntap as FSx for ONTAP<br/>(NFS Volume)
    participant FP as FPolicy Engine
    participant Lambda as AWS Lambda
    participant SQS as SQS (バッファ)
    participant Kafka as Amazon MSK<br/>(Kafka)
    participant SS as Structured Streaming<br/>(Databricks)
    participant UC as UC Delta Table

    Note over PLC,FsxOntap: OT ネットワーク
    Note over FP,UC: IT ネットワーク

    PLC->>FsxOntap: NFS 書き込み<br/>(/vol1/data/quality/*.json)
    
    FsxOntap->>FP: ファイル作成イベント検知<br/>(CREATE / MODIFY)
    
    rect rgb(255, 248, 240)
        Note over FP,SQS: イベント配信
        FP->>Lambda: イベント通知<br/>(パス, サイズ, 操作種別)
        Note right of Lambda: メタデータのみ<br/>ファイル内容は含まない
        
        alt Lambda 成功
            Lambda->>Kafka: Produce メッセージ<br/>(JSON: path, timestamp, op_type)
        else Lambda 失敗 / タイムアウト
            Lambda->>SQS: DLQ に退避
            Note over SQS: [Runbook #02] で再処理
        end
    end

    rect rgb(240, 255, 240)
        Note over Kafka,UC: ストリーミング取り込み
        Kafka->>SS: Consume<br/>(SASL_SSL + IAM 認証)
        SS->>UC: MERGE INTO (重複排除)<br/>(event_id ベース dedup)
    end

    Note over UC: UC ガバナンス適用<br/>(Row Filter / Column Mask / Tags)
```

### レイテンシバジェット

| ステップ | レイテンシ | 累積 | 備考 |
|---------|:---:|:---:|------|
| PLC → FSx for ONTAP (NFS write) | ~5 ms | 5 ms | NFS v4.1 |
| FPolicy イベント検知 | ~100 ms | 100 ms | ONTAP 内部イベント伝播 |
| FPolicy → Lambda 呼び出し | ~200 ms | 300 ms | VPC 内通信 (ENI) |
| Lambda 処理 | ~500 ms | 800 ms | メタデータ変換 + Kafka Produce |
| Kafka → Structured Streaming | ~2 秒 | 3 秒 | マイクロバッチ間隔依存 |
| Structured Streaming → UC Delta | ~2 秒 | **5 秒** | MERGE INTO |

> **合計 E2E レイテンシ**: PLC 出力から UC Delta テーブルクエリ可能まで **約 3-10 秒**（ストリーミングマイクロバッチ間隔依存）

### 障害シナリオと復旧

| 障害ポイント | 影響 | 検知方法 | 復旧手順 |
|---|---|---|---|
| FPolicy → Lambda 切断 | イベント消失リスク | FPolicy disconnect log | FPolicy 再接続（自動） |
| Lambda タイムアウト | DLQ 蓄積 | CloudWatch Lambda Errors | [Runbook #02](../../runbooks/02-fpolicy-lambda-failure.md) |
| Lambda → Kafka 失敗 | DLQ 蓄積 | CloudWatch + DLQ depth | [Runbook #02](../../runbooks/02-fpolicy-lambda-failure.md) |
| MSK ブローカー障害 | Produce 失敗 | MSK metrics | MSK 自動復旧 + Lambda リトライ |
| Structured Streaming 失敗 | 取り込み停止 | Spark metrics | Checkpoint から再開 |
| 重複イベント配信 | データ重複 | — | MERGE INTO の event_id dedup で吸収 |

---

## パス比較サマリ

| 属性 | DataSync パス | FPolicy パス |
|------|:---:|:---:|
| E2E レイテンシ | 7-12 分 | 3-10 秒 |
| スループット | 高（DataSync 最適化） | 中（Lambda 同時実行制限） |
| 運用複雑性 | 低（マネージド） | 高（Lambda + Kafka + SS） |
| データ保証 | 増分同期（バイトレベル） | at-least-once（dedup 必要） |
| コスト | $0.0125/GB 転送 + S3 | Lambda + MSK + Databricks Streaming |
| 障害復旧 | DataSync 再実行 | DLQ 再処理 + Checkpoint 再開 |
| 推奨ユースケース | バッチ分析、ML 訓練データ | リアルタイム品質検査、アラート |

> **選択指針**: 多くのエンタープライズ環境では**両方を併用**します。DataSync パスでバルクデータ（日次/時次）を同期し、FPolicy パスでクリティカルイベント（品質不良検知等）のみリアルタイム連携。全データをストリーミングする必要はありません。

---

## 関連ドキュメント

- [DataSync → S3 ガイド](./datasync-to-s3-guide.md) — DataSync パスの実装詳細
- [Kafka-ClickHouse-UC 接続ガイド](./kafka-clickhouse-unity-catalog-connectivity.md) — FPolicy/Kafka パスの実装
- [UC 接続総合ガイド](./fsx-ontap-to-databricks-unity-catalog-guide.md) — パス選定ロジック
- [Runbook #01](../../runbooks/01-datasync-failure-triage.md) — DataSync 障害対応
- [Runbook #02](../../runbooks/02-fpolicy-lambda-failure.md) — FPolicy/Lambda 障害対応
- [FSx for ONTAP 機能マップ](./fsx-ontap-feature-utilization-map.md) — 各ステップで使用される ONTAP 機能
