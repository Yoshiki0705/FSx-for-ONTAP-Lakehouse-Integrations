# イベント駆動アーキテクチャ（FPolicy 連携）

## 適用条件（先に確認する）

**このアーキテクチャが成立するのは、書き込みが NFS / SMB 経由で届く場合だけである。**
S3 Access Point 経由で届いた書き込みは FPolicy 通知を発火しないため、以下のパイプラインは
どれも 1 件もトリガーされない。実測 2026-08-26、ONTAP 9.18.1P3D1。FPolicy の event が
受け付けるプロトコルは `cifs` / `nfsv3` / `nfsv4` のみで、S3 に相当する値は存在しない。

| 書き込み経路 | このアーキテクチャ |
|---|---|
| NFS / SMB | 成立する |
| S3 Access Point | **成立しない。** EventBridge Scheduler によるポーリング、または ONTAP ネイティブ監査ログ（AP 経由の操作を `Source=HTTP` / `Source=S3` で記録）を起点にする |

判定方法: 取り込み対象ボリュームに S3 Access Point がアタッチされていて、かつ書き込みが
その経路で来るなら、この文書の構成は使えない。同じボリュームに NFS / SMB でも書くなら、
その分だけは検知される。

## 概要

ONTAP FPolicy を活用し、NFS/SMB ファイル操作をリアルタイムに検出して
各種 Lakehouse サービス（Databricks, Snowflake, Glue, Athena, EMR）の
パイプラインを自動トリガーするイベント駆動アーキテクチャ。

従来のポーリング方式（分単位のレイテンシ）から、イベント駆動方式（秒単位）への
移行により、ニアリアルタイムのデータ取り込みを実現する。

## アーキテクチャ全体像

```
NFS/SMB ファイル操作
    → ONTAP FPolicy (ファイルイベント検出)
        → ECS Fargate (FPolicy Server — バイナリプロトコル処理)
            → SQS (イベントバッファリング)
                → Lambda (Bridge — EventBridge 形式に変換)
                    → EventBridge Custom Bus (ルーティング)
                        ├── Databricks Jobs API (Spark Job トリガー)
                        ├── SNS → Snowpipe (リアルタイム取り込み)
                        ├── Glue Job (ETL 自動実行)
                        ├── Glue Crawler (スキーマ自動更新 → Athena)
                        └── Step Functions → EMR Step (大規模バッチ)
```

## ベンダー別統合パターン

### Databricks: FPolicy → Databricks Job API

```
FPolicy → SQS → Lambda → EventBridge → API Destination → Databricks Jobs API
```

- **レイテンシ**: <2 秒（ファイル操作 → Job 起動）
- **ユースケース**: 新規データ取り込み、画像処理、ドキュメント処理
- **認証**: Databricks PAT (Secrets Manager 格納)

### Snowflake: FPolicy → SNS → Snowpipe

```
FPolicy → SQS → Lambda → EventBridge → SNS → Snowflake SQS → Snowpipe → COPY INTO
```

- **レイテンシ**: <30 秒（ファイル操作 → テーブル反映）
- **改善**: Lambda ポーリング (5-7分) → FPolicy (30秒) = 90%+ 改善
- **ユースケース**: ストリーミング取り込み、ニアリアルタイム分析

### Glue: FPolicy → EventBridge → Glue Job

```
FPolicy → SQS → Lambda → EventBridge → Glue Job (Bronze → Silver ETL)
```

- **レイテンシ**: <5 秒（ファイル操作 → Job 起動）
- **改善**: スケジュール実行 (分単位) → イベント駆動 (秒単位)
- **ユースケース**: Medallion Architecture ETL、データ品質チェック

### Athena: FPolicy → Glue Crawler → Data Catalog

```
FPolicy → SQS → Lambda → EventBridge → Glue Crawler → Data Catalog 更新
```

- **レイテンシ**: <60 秒（ファイル操作 → Athena クエリ可能）
- **ユースケース**: スキーマ自動検出、パーティション自動追加

### EMR: FPolicy → Step Functions → EMR Step

```
FPolicy → SQS → Lambda → EventBridge → Step Functions → EMR AddStep
```

- **レイテンシ**: <10 秒（ファイル操作 → EMR Step 起動）
- **ユースケース**: 大規模バッチ処理、ML パイプライン

## レイテンシ比較（設計目標値）

> ⚠️ **これらは実測値ではありません**。下表の FPolicy 方式の数値は、各コンポーネント（FPolicy 通知 → Fargate → SQS → Lambda → 下流サービス）の想定処理時間から積み上げた**設計目標値**です。FPolicy → Lambda 経路は現時点で **設計のみ**（live 検証未実施）であり、実環境での計測値は取得していません。検証状況は [Blocker Tracker](./blocker-tracker.md) および [Snowpipe 検証結果](../../integrations/snowflake/docs/ja/snowpipe-verification-results.md) を参照してください。

| ベンダー | ポーリング方式（設計目標値） | FPolicy 方式（設計目標値） | 期待改善率 |
|---------|-------------|-------------|--------|
| Databricks | N/A (手動) | <2 秒 | — |
| Snowflake (Snowpipe) | 5-7 分 | <30 秒 | 90%+ |
| Glue | 分単位 (スケジュール) | <5 秒 | 95%+ |
| Athena (Crawler) | 分単位 (スケジュール) | <60 秒 | 90%+ |
| EMR | N/A (手動) | <10 秒 | — |

> **実測済みの数値について**: ポーリング方式の検出遅延を左右する ListObjectsV2 のレイテンシは実測しています。実測条件と生数値は [Snowpipe 検証結果](../../integrations/snowflake/docs/ja/snowpipe-verification-results.md) に記載しています。

## CloudFormation テンプレート

| テンプレート | パス | 説明 |
|------------|------|------|
| FPolicy Server | `shared/cloudformation/fpolicy-server-fargate.yaml` | ECS Fargate + FPolicy バイナリプロトコル処理 |
| FPolicy Ingestion | `shared/cloudformation/fpolicy-ingestion.yaml` | SQS + Lambda Bridge + EventBridge Custom Bus |
| FPolicy Routing | `shared/cloudformation/fpolicy-routing.yaml` | EventBridge ルール + 各種ターゲット |

## デプロイ手順

### Step 1: FPolicy Ingestion スタック

```bash
aws cloudformation deploy \
  --template-file shared/cloudformation/fpolicy-ingestion.yaml \
  --stack-name fsxn-fpolicy-ingestion \
  --parameter-overrides \
    VpcId=<VPC_ID> \
    PrivateSubnetIds=<SUBNET_1>,<SUBNET_2> \
    VpcEndpointSecurityGroupId=<SG_ID> \
  --capabilities CAPABILITY_NAMED_IAM
```

### Step 2: FPolicy Server スタック

```bash
aws cloudformation deploy \
  --template-file shared/cloudformation/fpolicy-server-fargate.yaml \
  --stack-name fsxn-fpolicy-server \
  --parameter-overrides \
    VpcId=<VPC_ID> \
    SubnetIds=<PRIVATE_SUBNET_1>,<PRIVATE_SUBNET_2> \
    FSxNSecurityGroupId=<FSXN_SG_ID> \
    SQSQueueArn=<QUEUE_ARN> \
    SQSQueueUrl=<QUEUE_URL> \
  --capabilities CAPABILITY_IAM
```

### Step 3: FPolicy Routing スタック（ターゲット別）

```bash
# Glue Job の場合
aws cloudformation deploy \
  --template-file shared/cloudformation/fpolicy-routing.yaml \
  --stack-name fsxn-fpolicy-routing-glue \
  --parameter-overrides \
    TargetType=GLUE_JOB \
    GlueJobName=fsxn-bronze-to-silver \
  --capabilities CAPABILITY_IAM

# Snowpipe の場合
aws cloudformation deploy \
  --template-file shared/cloudformation/fpolicy-routing.yaml \
  --stack-name fsxn-fpolicy-routing-snowpipe \
  --parameter-overrides \
    TargetType=SNS_SNOWPIPE \
    SNSTopicArn=arn:aws:sns:${AWS_REGION}:${AWS_ACCOUNT_ID}:snowpipe-notify \
  --capabilities CAPABILITY_IAM
```

### Step 4: ONTAP FPolicy 設定

```bash
# Fargate タスク IP 取得
TASK_ARN=$(aws ecs list-tasks --cluster fsxn-fpolicy-server-fpolicy-cluster \
  --desired-status RUNNING --query 'taskArns[0]' --output text)
TASK_IP=$(aws ecs describe-tasks --cluster fsxn-fpolicy-server-fpolicy-cluster \
  --tasks $TASK_ARN \
  --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' \
  --output text)

# ONTAP REST API で FPolicy 設定
# 詳細: fpolicy-configuration-reference.md
```

### Step 5: テスト

```bash
# NFS マウント (vers=4.1 必須)
sudo mount -t nfs -o vers=4.1 <SVM_IP>:/vol1 /mnt/fsxn

# テストファイル作成
echo "fpolicy-test" > /mnt/fsxn/test-file.parquet

# SQS メッセージ確認
aws sqs receive-message --queue-url <QUEUE_URL> --max-number-of-messages 5
```

## 重要な制約事項

| 制約 | 詳細 | 回避策 |
|------|------|--------|
| **NFSv4.2 非サポート** | FPolicy は NFSv4.2 の monitoring を非サポート。`mount -o vers=4` は NFSv4.2 にネゴシエートされるため使用不可 | `vers=4.1` または `vers=3` を明示指定 |
| **NLB 非互換** | FPolicy バイナリフレーミングが NLB TCP パススルーで動作しない | Fargate タスク IP を直接 ONTAP external-engine に指定 |
| **SMB は AD 必須** | CIFS サーバーが Active Directory に参加している必要がある | NFS のみの場合は不要 |
| **SQS VPC Endpoint 必須** | Fargate (Private Subnet) から SQS への通信に必要 | Interface VPC Endpoint 作成 |
| **直接 IP 接続** | ONTAP external-engine には Fargate タスクの直接 Private IP を指定 | タスク再起動時に IP 変更 → 自動更新スクリプト必要 |

## コスト見積もり

| コンポーネント | 月額コスト (概算) | 備考 |
|-------------|----------------|------|
| ECS Fargate (0.25 vCPU, 0.5GB) | ~$15 | 24/7 稼働 |
| SQS | ~$0.50 | メッセージ数依存 |
| Lambda (Bridge) | ~$1 | イベント数依存 |
| EventBridge | ~$1 | ルール評価 + イベント配信 |
| SQS VPC Endpoint | ~$7 | Interface Endpoint |
| **合計** | **~$25/月** | |

## 参考リポジトリ

- [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)
  - `docs/event-driven/architecture-design.md` — アーキテクチャ比較
  - `docs/event-driven/fpolicy-configuration-reference.md` — FPolicy 設定リファレンス
  - `docs/event-driven/fpolicy-e2e-verification-report.md` — E2E 検証レポート
  - `shared/cfn/fpolicy-server-fargate.yaml` — 参考テンプレート
  - `shared/cfn/fpolicy-ingestion.yaml` — 参考テンプレート
  - `shared/cfn/fpolicy-routing.yaml` — 参考テンプレート
