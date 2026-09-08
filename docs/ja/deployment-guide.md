# デプロイガイド — FSx for ONTAP Lakehouse Integrations

> 本リポジトリの全 28 CloudFormation テンプレートを対象とした統合デプロイリファレンス。
> **既存の FSx for ONTAP 環境**（ファイルシステム、SVM、ボリュームが既にプロビジョニング済み）へのオーバーレイを前提とする。
>
> FSx for ONTAP がまだ無い場合は [はじめに](./getting-started.md) を参照（約 45 分でプロビジョニング可能）。

---

## どのインテグレーションをデプロイすべきか？

```
ここから開始:
│
├─「ファイルを SQL で直接クエリしたい（ETL 不要）」
│   └─ パス 1: Athena（約 5 分、$0 アイドル）
│
├─「ETL が必要: 生データ → クレンジング → 集計」
│   └─ パス 2: Glue ETL（約 8 分、実行課金）
│
├─「小〜中規模データにサブ秒のアナリティクスが必要」
│   └─ パス 3: DuckDB Lambda（約 8 分、$0 アイドル）
│
├─「Snowflake から FSx for ONTAP データを読みたい」
│   └─ パス 4: Snowflake（約 10 分、$0 アイドル）
│
├─「ファイル変更のリアルタイム検出 → パイプラインが必要」
│   └─ パス 5: FPolicy（約 15 分、約 $15/月）
│
└─「Databricks で Unity Catalog インテグレーションしたい」
    └─ パス 6: Databricks（約 15 分、約 $35/月）
        ⚠️ 既知の制限あり: 検証済みデプロイパスを参照
```

---

## クイックリファレンス

| 目的 | 参照先 |
|---|---|
| 単一インテグレーションを素早くデプロイ | [検証済みデプロイパス](#検証済みデプロイパス) |
| テンプレート間の依存関係を理解 | [スタック一覧](#スタック一覧) |
| VPC エンドポイント要件の確認 | [VPC エンドポイント競合マトリクス](#vpc-エンドポイント競合マトリクス) |
| デプロイ前の環境検証 | [プリフライトチェック](#プリフライトチェック) |
| コスト見積もり | [コストリファレンス](#コストリファレンス) |
| 失敗時のロールバック | [ロールバック手順](#ロールバック手順) |
| WINDOWS ユーザータイプ S3 AP テスト | [AD 環境セットアップ](#windows-ユーザータイプ用-ad-環境) |

---

## 前提条件

### 必須

- AWS CLI v2.15+ （適切な IAM 権限で設定済み）
- 既存の Amazon FSx for NetApp ONTAP ファイルシステム（S3 AP サポートには ONTAP 9.14.1 以上）
- S3 プロトコルが有効な SVM が 1 つ以上（`vserver object-store-server create`）
- その SVM に FSx for ONTAP S3 Access Point と競合する**ネイティブ ONTAP S3 サーバー**が存在しないこと（構造的競合 — [トラブルシューティング](#よくあるデプロイ失敗)参照）
- ジャンクションパス設定済みのボリュームが 1 つ以上
- `aws fsx create-and-attach-s3-access-point` で作成済みの S3 Access Point

> **ONTAP バージョンの確認方法**: FSx コンソールや `describe-file-systems` API では ONTAP バージョンは直接表示されない。ONTAP REST API で確認: `GET https://<mgmt-ip>/api/cluster?fields=version`（fsxadmin 認証情報を使用）。

### ONTAP バージョン要件

| 機能 | 最低 ONTAP バージョン | 備考 |
|---|---|---|
| S3 Access Points（基本） | 9.14.1 | Read + Write（条件付き書き込みは非サポート） |
| S3 Access Points（拡張） | 9.15.1 | スループット向上、マルチパートアップロード |
| FPolicy external engine | 9.8+ | イベント駆動パイプラインに必要 |
| FlexClone | 9.1+ | 安全なインジェスチョンパターンに使用 |

### デプロイ実行者の IAM 権限

`aws cloudformation create-stack` を実行する IAM プリンシパルに必要な権限:

```
cloudformation:*
iam:CreateRole, iam:PutRolePolicy, iam:AttachRolePolicy, iam:PassRole
s3:CreateAccessPoint, s3:PutAccessPointPolicy
ec2:CreateVpcEndpoint, ec2:CreateSecurityGroup, ec2:AuthorizeSecurityGroupIngress
lambda:CreateFunction, lambda:CreateLayerVersion
glue:CreateDatabase, glue:CreateCrawler, glue:CreateJob
fsx:DescribeFileSystems, fsx:DescribeVolumes, fsx:DescribeStorageVirtualMachines
logs:CreateLogGroup
events:PutRule, events:PutTargets
sns:CreateTopic
sqs:CreateQueue
ecs:CreateCluster, ecs:CreateService （FPolicy のみ）
```

---

## スタック一覧

### カテゴリ A: 共有インフラストラクチャ（グリーンフィールドの場合は最初にデプロイ）

| # | テンプレート | 説明 | デプロイ時間 | 冪等性 |
|---|---|---|---|---|
| A1 | `shared/cloudformation/vpc-networking.yaml` | VPC、サブネット、S3 Gateway + Interface EP、Security Group | 約 3 分 | No |
| A2 | `shared/cloudformation/fsxn-s3ap-base.yaml` | FSx for ONTAP FS + SVM + Volumes + S3 AP（フルグリーンフィールド） | 約 45 分 | No |
| A3 | `shared/cloudformation/iam-policies.yaml` | 共通 IAM ポリシー（読み取り専用、読み書き、プラットフォーム、ETL、コンシューマーロール） | 約 1 分 | Yes |
| A4 | `shared/cloudformation/sample-data-generator.yaml` | S3 AP 経由で Parquet/CSV/JSON サンプルデータを生成する Lambda | 約 2 分 | Yes |

> **注**: オーバーレイデプロイ（既存 FSx for ONTAP）の場合、A1〜A2 はスキップし、既存の VPC/サブネット/SG/FS ID をパラメータとして指定する。

### カテゴリ B: アナリティクスインテグレーション（独立、必要なものを選択）

| # | テンプレート | 説明 | デプロイ時間 | VPC 必須 |
|---|---|---|---|---|
| B1 | `integrations/athena/template.yaml` | Glue Crawler + Athena Workgroup + IAM | 約 2 分 | No |
| B2 | `integrations/glue/template.yaml` | Glue ETL（Crawler + Bronze→Silver→Gold Jobs + EventBridge） | 約 3 分 | No |
| B3 | `integrations/duckdb/template.yaml` | DuckDB Lambda（VPC アタッチ、arm64）+ Layer + S3 バケット | 約 3 分 | Yes |
| B4 | `integrations/delta-lake-oss/template.yaml` | Delta Lake OSS IAM Role + EMR 用 Instance Profile | 約 1 分 | No |
| B5 | `integrations/opensharing-server/template.yaml` | OpenSharing Volumes API（Lambda + Function URL + クレデンシャル発行） | 約 2 分 | No |

### カテゴリ C: Databricks インテグレーション（順序通りデプロイ）

| # | テンプレート | 説明 | デプロイ時間 | 依存 |
|---|---|---|---|---|
| C1 | `integrations/databricks/customer-vpc-network.yaml` | Databricks サブネット、NAT GW、ルートテーブル、クラスター SG | 約 5 分 | 既存 VPC |
| C2 | `integrations/databricks/template.yaml` | S3 AP（VPC スコープ）+ クロスアカウント IAM Role + S3 Interface EP | 約 3 分 | C1 |
| C3 | `integrations/databricks/vpc-peering.yaml` | Databricks VPC と FSx for ONTAP VPC 間の VPC ピアリング | 約 2 分 | C1 |

### カテゴリ D: Snowflake インテグレーション

| # | テンプレート | 説明 | デプロイ時間 | 依存 |
|---|---|---|---|---|
| D1 | `integrations/snowflake/template.yaml` | IAM Role（二段階信頼）+ オプション SNS for Snowpipe | 約 1 分 | S3 AP 存在 |
| D2 | `integrations/snowflake/snowpipe-lambda/template.yaml` | Snowpipe ポーリング Lambda + EventBridge スケジュール | 約 2 分 | D1 |

### カテゴリ E: FPolicy イベント駆動パイプライン（順序通りデプロイ）

| # | テンプレート | 説明 | デプロイ時間 | 依存 |
|---|---|---|---|---|
| E1 | `shared/cloudformation/fpolicy-routing.yaml` | SNS Topic + Snowpipe サブスクリプション + EventBridge ルーティング | 約 1 分 | — |
| E2 | `shared/cloudformation/fpolicy-ingestion.yaml` | SQS Queue + DLQ + SQS VPC Endpoint + Lambda Bridge | 約 3 分 | E1 |
| E3 | `shared/cloudformation/fpolicy-server-fargate.yaml` | ECS Fargate FPolicy TCP サーバー | 約 5 分 | E2 |
| E4 | `shared/cloudformation/fpolicy-ip-updater.yaml` | Fargate タスク再起動時に ONTAP external-engine IP を自動更新する Lambda | 約 2 分 | E3 |

### カテゴリ F: Iceberg メタデータカタログ

| # | テンプレート | 説明 | デプロイ時間 | 依存 |
|---|---|---|---|---|
| F1 | `integrations/iceberg-metadata-catalog/cloudformation/s3-tables-setup.yaml` | S3 Tables バケット + Athena Workgroup + Lake Formation | 約 3 分 | — |
| F2 | `integrations/iceberg-metadata-catalog/cloudformation/metadata-sync-pipeline.yaml` | SQS + FPolicy イベント用 Lambda 同期ハンドラー | 約 2 分 | F1 |
| F3 | `integrations/iceberg-metadata-catalog/demo/cloudformation/demo-stack.yaml` | オールインワンデモ（S3 Tables + OpenSearch Serverless + Athena） | 約 5 分 | — |
| F4 | `integrations/iceberg-metadata-catalog/use-cases/_shared/cloudformation/industry-demo-stack.yaml` | 業界別デモ（20 業界、S3 Tables + オプション OpenSearch） | 約 3 分 | — |

### カテゴリ G: 製造データプラットフォーム PoC（順序通りデプロイ）

| # | テンプレート | 説明 | デプロイ時間 | 依存 |
|---|---|---|---|---|
| G1 | `integrations/manufacturing-data-platform/poc/infrastructure/01-vpc-network.yaml` | 専用 VPC + サブネット + SG + S3/STS VPC Endpoints | 約 3 分 | — |
| G2 | `integrations/manufacturing-data-platform/poc/infrastructure/02-s3-buckets.yaml` | KMS キー + S3 バケット（Delta Lake、チェックポイント、監査） | 約 2 分 | G1 |
| G3 | `integrations/manufacturing-data-platform/poc/infrastructure/03-fsx-ontap.yaml` | FSx for ONTAP Single-AZ + SVM + 4 ボリューム | 約 45 分 | G1 |
| G4 | `integrations/manufacturing-data-platform/poc/infrastructure/msk-serverless.yaml` | MSK Serverless クラスター + IAM ポリシー | 約 10 分 | G1 |

### カテゴリ H: PoC クイックスタートテンプレート

| # | テンプレート | 説明 | デプロイ時間 | 依存 |
|---|---|---|---|---|
| H1 | `poc-templates/06-duckdb-lambda/template.yaml` | 最小構成 DuckDB Lambda PoC（VPC なし） | 約 2 分 | S3 AP 存在 |
| H2 | `poc-templates/04-databricks-integration/datasync-task.yaml` | DataSync NFS→S3 タスク（Databricks UC 回避策） | 約 3 分 | FSx SVM + S3 バケット |

---

## VPC エンドポイント競合マトリクス

FSx for ONTAP S3 Access Points には固有のネットワーキング要件がある。このマトリクスは各インテグレーションに必要な VPC エンドポイントを示す。

### エンドポイントタイプ

| エンドポイント | タイプ | コスト | 用途 |
|---|---|---|---|
| S3 Gateway | Gateway | **無料** | ルートテーブルから S3 サービスへの S3 トラフィックルーティング |
| S3 Interface | Interface (PrivateLink) | 約 $0.01/時/AZ + データ | VPC スコープ S3 AP 用プライベート DNS |
| SQS Interface | Interface (PrivateLink) | 約 $0.01/時/AZ + データ | プライベートサブネットの Fargate → SQS 通信 |
| STS Interface | Interface (PrivateLink) | 約 $0.01/時/AZ + データ | MSK IAM 認証、クロスアカウント AssumeRole |

### 互換性マトリクス

| インテグレーション | S3 Gateway EP | S3 Interface EP | SQS Interface EP | STS Interface EP | 備考 |
|---|:---:|:---:|:---:|:---:|---|
| Athena | — | — | — | — | AWS マネージド、顧客 VPC 不要 |
| Glue ETL（非 VPC） | — | — | — | — | AWS マネージド実行 |
| Glue ETL（VPC アタッチ） | ⚠️ | オプション | — | — | Gateway EP が S3 AP トラフィックをブロックする可能性; NAT GW 使用 |
| DuckDB Lambda（VPC） | ⚠️ | 推奨 | — | — | VPC スコープ AP には Interface EP または NAT GW が必要 |
| Delta Lake / EMR | ✅ | オプション | — | — | 標準 S3 トラフィックは Gateway EP で動作 |
| Databricks（Customer VPC） | ✅ | ✅ 必須 | — | — | VPC スコープ AP には Interface EP 必須 |
| Snowflake | — | — | — | — | SaaS プラットフォーム; internet-origin AP 必須 |
| FPolicy パイプライン | ✅ | — | ✅ 必須 | — | プライベートサブネットの Fargate に SQS EP が必要 |
| 製造 PoC | ✅ | — | — | ✅ 必須 | MSK Serverless IAM 認証に STS EP が必要 |
| OpenSharing Server | — | — | — | — | Lambda（非 VPC）、internet-origin AP |

### 重要な警告: S3 Gateway Endpoint と FSx for ONTAP S3 AP

> **S3 Gateway Endpoint は、internet-origin Access Point に対する FSx for ONTAP S3 AP トラフィックを傍受するが正しくルーティングしない場合がある。** FSx for ONTAP S3 AP エイリアスは `s3-r-w.<region>.amazonaws.com` に解決されるが、このアドレスは Gateway エンドポイントが使用する S3 プレフィックスリストに含まれない可能性がある。

**影響**: VPC アタッチの Lambda や EC2 が、S3 Gateway EP を持つルートテーブル経由で internet-origin FSx for ONTAP S3 AP にアクセス → **タイムアウト**。

**解決策**（いずれか 1 つを選択）:
1. Lambda を VPC 外に配置（VPC アタッチなし）— internet-origin AP で最もシンプル
2. FSx for ONTAP S3 AP トラフィックに NAT Gateway を使用
3. VPC スコープ S3 AP + S3 Interface Endpoint を使用（本番環境推奨）

詳細は [FSx for ONTAP S3 AP ネットワーキング](./fsx-ontap-s3ap-networking.md) を参照。

---

## 検証済みデプロイパス

### パス 1: Athena クイックスタート（最速、読み取り専用アナリティクス）

**所要時間**: 約 5 分 | **コスト**: 約 $0/月（クエリ課金） | **VPC**: 不要

```bash
# 1. プリフライトチェック
./scripts/preflight-check.sh --integration athena

# 2. デプロイ
aws cloudformation create-stack \
  --stack-name fsxn-athena-dev \
  --template-body file://integrations/athena/template.yaml \
  --parameters file://cfn-params/athena.example.json \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1

# 3. 完了待ち
aws cloudformation wait stack-create-complete --stack-name fsxn-athena-dev

# 4. Glue Crawler を実行して Athena でクエリ
aws glue start-crawler --name fsxn-athena-crawler-dev
```

### パス 2: Glue ETL メダリオンパイプライン（bronze→silver→gold）

**所要時間**: 約 8 分 | **コスト**: 約 $0.44/DPU 時間（Glue） | **VPC**: オプション

```bash
# 1. ETL スクリプトを S3 にアップロード
aws s3 cp integrations/glue/scripts/ s3://YOUR-SCRIPT-BUCKET/glue-scripts/ --recursive

# 2. デプロイ
aws cloudformation create-stack \
  --stack-name fsxn-glue-dev \
  --template-body file://integrations/glue/template.yaml \
  --parameters file://cfn-params/glue.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# 3. パイプライン実行: Crawler → Bronze→Silver → Silver→Gold
aws glue start-crawler --name fsxn-glue-crawler-dev
```

### パス 3: DuckDB サーバーレスアナリティクス（サブ秒クエリ）

**所要時間**: 約 8 分 | **コスト**: 約 $0/月（呼び出し課金） | **VPC**: 必須

```bash
# 1. DuckDB レイヤーをビルド・アップロード
cd integrations/duckdb && ./build-layer.sh

# 2. デプロイ
aws cloudformation create-stack \
  --stack-name fsxn-duckdb-dev \
  --template-body file://integrations/duckdb/template.yaml \
  --parameters file://cfn-params/duckdb.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# 3. テストクエリ
aws lambda invoke --function-name fsxn-duckdb-query-dev \
  --payload '{"query":"SELECT COUNT(*) FROM read_parquet('"'"'s3://YOUR-AP-ALIAS/data.parquet'"'"')"}' \
  response.json
```

### パス 4: Snowflake External Stage（二段階信頼）

**所要時間**: 約 10 分 | **コスト**: 約 $0/月（IAM Role のみ） | **VPC**: 不要

```bash
# フェーズ 1: プレースホルダー信頼でデプロイ
aws cloudformation create-stack \
  --stack-name fsxn-snowflake-dev \
  --template-body file://integrations/snowflake/template.yaml \
  --parameters file://cfn-params/snowflake-phase1.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# フェーズ 2: Snowflake で Storage Integration を作成し DESCRIBE を実行
# 実際の Snowflake アカウント情報でスタックを更新
aws cloudformation update-stack \
  --stack-name fsxn-snowflake-dev \
  --template-body file://integrations/snowflake/template.yaml \
  --parameters file://cfn-params/snowflake-phase2.example.json \
  --capabilities CAPABILITY_NAMED_IAM
```

### パス 5: FPolicy イベント駆動パイプライン（ファイル変更 → Snowpipe）

**所要時間**: 約 15 分 | **コスト**: 約 $15/月（Fargate + SQS + Lambda） | **VPC**: 必須

```bash
# 順序通りデプロイ: E1 → E2 → E3 → E4
for stack in fpolicy-routing fpolicy-ingestion fpolicy-server fpolicy-ip-updater; do
  aws cloudformation create-stack \
    --stack-name "fsxn-${stack}" \
    --template-body "file://shared/cloudformation/${stack}.yaml" \
    --parameters "file://cfn-params/${stack}.example.json" \
    --capabilities CAPABILITY_NAMED_IAM
  aws cloudformation wait stack-create-complete --stack-name "fsxn-${stack}"
done
```

### パス 6: Databricks Unity Catalog（VPC スコープ AP）

**所要時間**: 約 15 分 | **コスト**: 約 $35/月（NAT GW + Interface EP） | **VPC**: 必須

```bash
# ステップ 1: ネットワークインフラ
aws cloudformation create-stack \
  --stack-name databricks-network \
  --template-body file://integrations/databricks/customer-vpc-network.yaml \
  --parameters file://cfn-params/databricks-network.example.json \
  --capabilities CAPABILITY_NAMED_IAM

aws cloudformation wait stack-create-complete --stack-name databricks-network

# ステップ 2: S3 AP + IAM Role
aws cloudformation create-stack \
  --stack-name databricks-s3ap \
  --template-body file://integrations/databricks/template.yaml \
  --parameters file://cfn-params/databricks.example.json \
  --capabilities CAPABILITY_NAMED_IAM
```

---

## デプロイコマンドリファレンス

### `create-stack` vs `deploy`

| コマンド | `file://` サポート | Capabilities | 使用場面 |
|---|:---:|---|---|
| `aws cloudformation create-stack` | ✅ あり | `--capabilities CAPABILITY_NAMED_IAM` | 初回デプロイ、ファイルからの JSON パラメータ |
| `aws cloudformation deploy` | ❌ なし（S3 またはインラインのみ） | `--capabilities CAPABILITY_NAMED_IAM` | CI/CD パイプライン、SAM トランスフォーム |

**重要**: `aws cloudformation deploy` はテンプレートボディの `file://` をサポートしない。パラメータファイルを使用するローカルデプロイには `create-stack` を使用すること。

### パラメータファイル形式

すべての `cfn-params/*.example.json` ファイルは標準 AWS CLI 形式を使用:

```json
[
  {"ParameterKey": "VpcId", "ParameterValue": "vpc-0123456789abcdef0"},
  {"ParameterKey": "SubnetIds", "ParameterValue": "subnet-aaa,subnet-bbb"}
]
```

### マルチチーム環境での命名規則

同一アカウントに複数チームがデプロイする場合、`EnvironmentName` パラメータでリソースを名前空間分離する:

| チーム | EnvironmentName | スタック名 | 結果 |
|---|---|---|---|
| データエンジニアリング | `de-prod` | `de-prod-athena` | ロール: `de-prod-athena-*` |
| ML プラットフォーム | `ml-dev` | `ml-dev-duckdb` | ロール: `ml-dev-duckdb-*` |
| アナリティクス | `analytics-staging` | `analytics-staging-glue` | ロール: `analytics-staging-*` |

コスト配分タグは `create-stack` 時に `--tags Key=Team,Value=data-engineering Key=CostCenter,Value=CC-1234` で付与する。

---

## コストリファレンス

### インテグレーション別推定月額コスト（ap-northeast-1）

| インテグレーション | アイドルコスト | アクティブコスト | 主なコストドライバー |
|---|---|---|---|
| Athena (B1) | $0 | クエリ課金（$5/TB スキャン） | クエリ量 |
| Glue ETL (B2) | $0 | $0.44/DPU 時間 | ETL ジョブ時間 × ワーカー数 |
| DuckDB Lambda (B3) | $0 | $0.0000166667/GB 秒 | 呼び出し数 × メモリ × 実行時間 |
| Delta Lake / EMR (B4) | $0 | EMR クラスターコスト | インスタンス時間 |
| OpenSharing Server (B5) | $0 | $0.20/100 万リクエスト | Function URL 呼び出し |
| Databricks (C1-C3) | 約 $35 | +Databricks コンピュート | NAT GW ($32) + Interface EP ($7/AZ) |
| Snowflake (D1-D2) | $0 | Snowflake コンピュート | ウェアハウスクレジット |
| FPolicy パイプライン (E1-E4) | 約 $15 | +$0.40/100 万 SQS メッセージ | Fargate ($10) + SQS EP ($7) |
| Iceberg カタログ (F1-F2) | $0 | $0.004/1K リクエスト（S3 Tables） | テーブルリクエスト |
| 製造 PoC (G1-G4) | 約 $250 | +MSK/コンピュート | FSx for ONTAP ($180) + MSK ($45) + NAT ($32) |

### VPC エンドポイントコスト

| エンドポイント | 時間コスト（AZ あたり） | 月額（2 AZ） | データ処理 |
|---|---|---|---|
| S3 Gateway | **$0** | **$0** | **$0** |
| S3 Interface | $0.014 | 約 $20 | $0.01/GB |
| SQS Interface | $0.014 | 約 $20 | $0.01/GB |
| STS Interface | $0.014 | 約 $20 | $0.01/GB |

---

## プリフライトチェック

デプロイ前に実行:

```bash
./scripts/preflight-check.sh --integration <name>
```

利用可能なインテグレーション名: `athena`, `glue`, `duckdb`, `databricks`, `snowflake`, `fpolicy`, `manufacturing`, `iceberg-catalog`, `all`

スクリプトの検証内容:
- AWS CLI バージョンとクレデンシャル
- ターゲットリージョンの利用可能性
- 既存 FSx for ONTAP ファイルシステムのステータス
- SVM の S3 プロトコル設定
- S3 Access Point の存在とライフサイクル状態
- VPC エンドポイントの競合（VPC ベースのインテグレーション）
- IAM 権限の妥当性
- ONTAP バージョンの互換性

---

## ロールバック手順

### 自動ロールバック（デフォルト）

CloudFormation は CREATE_FAILED 時に自動ロールバックする。無効化（デバッグ用）:

```bash
aws cloudformation create-stack \
  --stack-name my-stack \
  --template-body file://template.yaml \
  --parameters file://params.json \
  --capabilities CAPABILITY_NAMED_IAM \
  --disable-rollback
```

### 手動ロールバック

```bash
# 失敗または不要なスタックの削除
aws cloudformation delete-stack --stack-name my-stack

# 保持リソースがあるスタック（データ入り S3 バケットなど）:
aws cloudformation delete-stack --stack-name my-stack \
  --retain-resources BucketLogicalId
```

### ロールバック順序（マルチスタックデプロイ）

デプロイとは**逆順**で削除:

```bash
# FPolicy パイプライン: E4 → E3 → E2 → E1
for stack in fpolicy-ip-updater fpolicy-server fpolicy-ingestion fpolicy-routing; do
  aws cloudformation delete-stack --stack-name "fsxn-${stack}"
  aws cloudformation wait stack-delete-complete --stack-name "fsxn-${stack}"
done
```

### 既知のロールバック問題

| シナリオ | 症状 | 解決策 |
|---|---|---|
| S3 バケットが空でない | DELETE_FAILED | バケットを先に空にする: `aws s3 rm s3://bucket --recursive` |
| IAM Role が使用中 | DELETE_FAILED | サービスからロールを削除してからリトライ |
| VPC EP が ENI で使用中 | DELETE_FAILED | 依存リソース（Lambda VPC 設定）を先に削除 |
| 保持設定のロググループ | 保持（削除されない） | 手動クリーンアップ: `aws logs delete-log-group` |

---

## Day 2 運用

### スタックの更新

```bash
aws cloudformation update-stack \
  --stack-name fsxn-athena-dev \
  --template-body file://integrations/athena/template.yaml \
  --parameters file://cfn-params/athena.example.json \
  --capabilities CAPABILITY_NAMED_IAM
```

### スタックイベントの監視

```bash
# リアルタイムイベント監視
aws cloudformation describe-stack-events \
  --stack-name my-stack \
  --query 'StackEvents[?ResourceStatus!=`CREATE_COMPLETE`].[Timestamp,LogicalResourceId,ResourceStatus,ResourceStatusReason]' \
  --output table
```

### 定期メンテナンス

| タスク | 頻度 | コマンド |
|---|---|---|
| S3 AP ライフサイクル確認 | 週次 | `aws fsx describe-s3-access-point-attachments` |
| Secrets Manager クレデンシャルローテーション | 90 日 | `aws secretsmanager rotate-secret` |
| CloudWatch Logs 保持期間確認 | 月次 | `/aws/lambda/*` ロググループを確認 |
| Glue Crawler スキーマドリフト確認 | データ変更後 | `aws glue start-crawler` |
| Fargate タスクヘルス確認（FPolicy） | 日次 | `aws ecs describe-services` |

### ONTAP 監査ログの SIEM への取り込み

上記のアラームが見ているのは AWS 側です。Lambda のエラー、Glue ジョブの失敗、スタックのドリフト。
**ファイルシステムの内側で何が起きたかは見ていません。** アクセスポイント経由の操作は ONTAP の
ネイティブ監査ログに記録されますが、**このログは自力では CloudWatch に届きません。** 要求元の
IAM プリンシパルも記録されず、そちらはアクセスポイントに対する CloudTrail データイベント側に
あります。**監査証跡として成立させるには 2 つが必要です。**

このログを EC2 コレクタ無しで Datadog・Splunk・New Relic・Grafana・Elastic へ送る方法は、
姉妹リポジトリ
[FSx-for-ONTAP-Observability-integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations)
で解決済みです。**ここでは再掲しません。**
[問いごとの参照先リポジトリ](./repository-map.md) も参照してください。

---

## トラブルシューティング

### よくあるデプロイ失敗

| エラー | 原因 | 修正 |
|---|---|---|
| `CAPABILITY_NAMED_IAM required` | テンプレートが名前付き IAM リソースを作成 | `--capabilities CAPABILITY_NAMED_IAM` を追加 |
| `S3 bucket already exists` | グローバルバケット名の衝突 | `BucketName` パラメータを変更するかアカウント固有の命名を使用 |
| `VPC endpoint already exists` | VPC あたりサービスごとに Gateway EP は 1 つ | スキップするか既存 EP ID を使用 |
| `Role already exists` | 以前のデプロイからの名前付きロール | 古いスタックを削除するか `EnvironmentName` を変更 |
| `Access Point creation failed` | 同一 SVM に ONTAP S3 サーバーが存在 | 別の SVM を使用するかネイティブ S3 サーバーを削除 |
| `Timeout creating FSx resources` | FSx 作成に 30〜45 分かかる | CLI タイムアウトを延長するか `wait` コマンドを使用 |

### S3 Access Point 接続の検証

```bash
# 1. AP ステータス確認
aws fsx describe-s3-access-point-attachments \
  --query 'S3AccessPointAttachments[].{Name:Name,Status:Lifecycle,Alias:S3AccessPoint.Alias}'

# 2. アクセステスト（適切なネットワーク位置から）
aws s3 ls "s3://YOUR-AP-ALIAS/" --region ap-northeast-1

# 3. タイムアウト時、DNS 解決を確認
nslookup YOUR-AP-ALIAS.s3.ap-northeast-1.amazonaws.com
```

---

## WINDOWS ユーザータイプ用 AD 環境

FSx for ONTAP S3 Access Points は 3 つの `FileSystemIdentity` タイプをサポートする:

| タイプ | AD 必須 | ユースケース |
|---|:---:|---|
| `UNIX` | No | NFS ワークロード、最もシンプル |
| `WINDOWS` | **Yes** | NTFS セキュリティデータ、AD 認証アクセス |
| `NONE` | No | root アクセス（テスト専用、非推奨） |

WINDOWS タイプの S3 AP をテストするには、SVM が Active Directory ドメインに参加済み（CIFS サーバー構成済み）である必要がある。

### クイックデプロイ

```bash
# 1. AD 環境デプロイ（パターン選択: ManagedAD, SimpleAD, SelfManagedEC2）
aws cloudformation create-stack \
  --stack-name demo-ad-env \
  --template-body file://shared/templates/demo-ad-environment.yaml \
  --parameters file://shared/params/demo-ad-environment.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# 2. AD が Active になるまで待機（約 15-30 分）
aws cloudformation wait stack-create-complete --stack-name demo-ad-env

# 3. スタック出力から DNS IP を取得
DNS_IPS=$(aws cloudformation describe-stacks --stack-name demo-ad-env \
  --query 'Stacks[0].Outputs[?OutputKey==`DnsIpAddresses`].OutputValue' --output text)

# 4. SVM をドメインに参加
./shared/scripts/demo-ad-join-svm.sh \
  --fsxn-mgmt-ip YOUR-MGMT-IP \
  --svm-name YOUR-SVM-NAME \
  --domain lakehouse.example.com \
  --dns-ips "$DNS_IPS" \
  --secret-arn $(aws cloudformation describe-stacks --stack-name demo-ad-env \
    --query 'Stacks[0].Outputs[?OutputKey==`CredentialsSecretArn`].OutputValue' --output text)

# 5. WINDOWS タイプ S3 AP を作成
aws fsx create-and-attach-s3-access-point \
  --name windows-test-ap --type ONTAP \
  --ontap-configuration '{"VolumeId":"YOUR-VOL-ID","FileSystemIdentity":{"Type":"WINDOWS","WindowsUser":{"Name":"LAKEHOUSE\\lakehouse-reader"}}}'
```

### パターン比較

| パターン | デプロイ時間 | 月額コスト | 用途 |
|---|---|---|---|
| AWS Managed Microsoft AD | 約 20 分 | 約 $100（Standard） | 本番、マルチ AZ HA |
| Simple AD | 約 15 分 | 約 $50（Small） | 開発/テスト、コスト重視 |
| Self-Managed EC2 | 約 10 分 + 設定 | 約 $30（t3.medium） | 既存ドメイン、カスタム設定 |

### 削除

```bash
# 重要: AD 削除前に SVM のドメイン参加を解除すること
# (ONTAP: vserver cifs delete -vserver <svm>)
aws cloudformation delete-stack --stack-name demo-ad-env
```

---

## 関連ドキュメント

- [FSx for ONTAP S3 AP ネットワーキング](./fsx-ontap-s3ap-networking.md) — VPC エンドポイント詳細、DNS 解決、タイムアウトトラブルシューティング
- [互換性マトリクス](./compatibility-matrix.md) — プラットフォーム検証状況
- [はじめに](./getting-started.md) — 初回セットアップウォークスルー
- [アーキテクチャ](./architecture.md) — システム設計パターン
- [PoC 実行ガイド](../implementation-guide/poc-execution-guide.md) — ステップバイステップ PoC チェックリスト
