🌐 [English](../en/databricks-verification-runbook.md) | **日本語**

# ランブック: FSx for ONTAP S3 Access Point 上の Unity Catalog

2026-08-12 の検証を自分のアカウントで再現する手順。実時間で約 45 分、費用 2 USD 未満で、当日中に撤去できる。

## 分かることと分からないこと

始める前に期待される結果を明確にしておく。「失敗した」がこの検証の結果であり、あなたの手違いではない。

| 手順 | 期待される結果 |
|---|---|
| Access Point エイリアスに Storage Credential・External Location・External Volume を登録 | ✅ 成功する（Unity Catalog 自身の検証を有効にしたまま） |
| それ経由での読み取り（`read_files` / `list_files` / `to_file` / `dbutils.fs.ls`） | ❌ 403 で拒否される |
| 同じ読み取りをネイティブ S3 バケットに対して実行 | ✅ 成功し、オブジェクトタグも入る |

読み取りが拒否されるのは、AWS が Access Point 経由のリクエストを **Access Point ARN** に対して認可評価する一方、Unity Catalog が資格情報を払い出すときに付ける down-scoped セッションポリシーが**バケット形式** ARN で書かれているためである。セッションポリシーはロールポリシーと積集合を取るので、ロールに入れた Access Point ARN の許可は出番がない。利用者側の回避策は存在しない。

もし Access Point の読み取りが**成功**したなら、それは新情報である。使用した Databricks リリースを記録して issue を立ててほしい。

> **コントロールが重要な理由。** 本リポジトリは 2026 年 5 月から 8 月まで「Unity Catalog の External Location は S3 Access Point を非サポート」と記録していた。この記述は誤りで、3 か月生き延びた理由は、最初の試行に同じ検証を走らせるネイティブ S3 のコントロールが無かったことである。単独の失敗は、自分の IAM 設定の誤りと区別できない。以下の全手順はコントロールを保持する。

## 前提条件

| 必要なもの | 確認方法 |
|---|---|
| S3 Access Point を持つ FSx for ONTAP ファイルシステム | `aws fsx describe-s3-access-point-attachments --region <region> --query 'S3AccessPointAttachments[].{name:Name,alias:S3AccessPoint.Alias,state:Lifecycle}' --output table` |
| ファイルシステムと**同一 AWS アカウント・同一リージョン**の Databricks ワークスペース | 後述の「どのワークスペースを使うか」を参照 |
| IAM ロールと S3 バケットを作成できる権限 | `AdministratorAccess` なら十分。最小構成は `iam:CreateRole` と S3 作成権限 |
| AWS CLI、Python 3.9 以上、`databricks-sdk` | `aws --version` / `python3 -V` / `python3 -c "import databricks.sdk"` |
| ワークスペース内の SQL ウェアハウス | 停止していればプローブが起動する |

SDK はシステム Python ではなく仮想環境に入れる。PEP 668 のため結局そうすることになる。

```bash
python3 -m venv .venv
.venv/bin/pip install databricks-sdk
```

Databricks CLI のプロファイルを作る。トークンには `unity-catalog` / `files` / `sql` のスコープが必要。後続の 2 手順ではさらに必要になるので、作り直す前に知っておくほうが安い。`--vend-check` には `all-apis`、API でトークンを失効させるには `authentication` が必要である。

```ini
# ~/.databrickscfg   (chmod 600)
[fsxn-verify]
host  = https://<your-workspace-host>
token = <personal access token>
```

## 使用するワークスペースの選択

Unity Catalog の Storage Credential はそのアカウントに手を伸ばすため、ワークスペースはファイルシステムと同一アカウント・同一リージョンに置く必要がある。

| 選択肢 | この検証に使えるか | 費用 |
|---|---|---|
| 14 日間のトライアルワークスペース | ❌ サーバーレス専用のため、自アカウントへの Storage Credential を作れない | 無料 |
| 非トライアル・「Use your existing cloud account」・同一リージョン | ✅ これを使う | 後述の費用表 |
| 別リージョンの既存ワークスペース | ⚠️ クロスリージョンという余計な変数が入る | 既存の費用のまま |

「Use your existing cloud account」は自アカウント内に NAT Gateway 付きの VPC を作る。さらに一時的な IAM 委任を求めてくるので、そのポリシーは承認前に読むこと。共有アカウントでは特に。費用と判断軸の詳細: [Databricks 検証環境とコスト](./databricks-verification-environment-cost.md)。

## 手順 1 — ベースラインの記録

何かを作る**前**に実行する。これが無いと「撤去は綺麗に見える」は検証可能な主張にならないし、共有アカウントでは見えているものの大半が他人のものである。

```bash
python3 shared/scripts/audit_databricks_workspace_footprint.py \
  --region <region> --save /tmp/fsxn-baseline.json
```

## 手順 2 — IAM ロールとコントロールバケットのデプロイ

```bash
cp cfn-params/databricks-uc-storage-credential.example.json \
   cfn-params/databricks-uc-storage-credential.json
# コピーを編集: Databricks アカウント UUID、Access Point 名、エイリアス
```

記入済みのコピーは gitignore 対象なので、誤ってコミットされることはない。

```bash
aws cloudformation deploy \
  --region <region> \
  --stack-name fsxn-databricks-uc-credential \
  --template-file integrations/databricks/uc-storage-credential-role.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides file://cfn-params/databricks-uc-storage-credential.json

aws cloudformation describe-stacks --region <region> \
  --stack-name fsxn-databricks-uc-credential \
  --query 'Stacks[0].Outputs' --output table
```

成否を決めるパラメータが 2 つあり、どちらも「Access Point 非対応」と読めてしまう 403 を生む。

- **`DatabricksAccountId` はアカウント UUID である。** metastore ID でもワークスペース ID でもない。Storage Credential が `sts:ExternalId` として提示する値である。
- **IAM ポリシーには Access Point ARN が必要。** テンプレートは Access Point ARN とエイリアス形式 ARN の両方を許可するので、自分でポリシーを書く場合にのみ問題になる。

出力が再度述べる非対称に注意。External Location の **URL** はエイリアス形式（`s3://<alias>/`）でなければならない（ARN スタイルの URL は `url does not specify a valid bucket name` で拒否される）一方、IAM **ポリシー**は ARN 形式を要求する。

## 手順 3 — 比較の実行

スタックの `NextStep` 出力が、ARN まで埋まったコマンドそのものである。

```bash
.venv/bin/python shared/scripts/probe_uc_external_location.py \
  --profile fsxn-verify \
  --role-arn <スタック出力から> \
  --ap-alias <あなたのエイリアス>-ext-s3alias \
  --ap-name <あなたの Access Point 名> \
  --control-bucket <スタック出力から> \
  --region <region>
```

`--control-bucket` は意図的に必須である。手順 4 で説明する決定的テストには `--vend-check` を、Unity Catalog オブジェクトを同じ実行で片付けるには `--teardown-after` を足す。

## 手順 4 — 判定の読み方

スクリプトは 3 つの結論のいずれかを出す。合否ではない。

| 判定 | 意味 | 対応 |
|---|---|---|
| **判定不能** — コントロールが読めなかった | プラットフォームではなく自分の環境の問題 | スクリプトが表示した External ID をロールの信頼ポリシーと突き合わせ、ロールがコントロールバケットを許可しているか確認する |
| **登録は成功、読み取りは拒否** | 2026-08-12 の結果 | 自分側に直すものはない。[BLK-001](./blocker-tracker.md#blk-001-uc-の資格情報払い出しでは通らない-s3-ap-の読み取り) である |
| **登録も読み取りも成功** | プラットフォームが変わった | Databricks のリリースを記録し、本リポジトリに issue を立てる |
| **登録自体が失敗** | ほぼ確実に IAM ポリシーの Access Point ARN 欠落 | 自分のポリシーをテンプレートと比較する |

`--vend-check` は Databricks のコンピュートを一切介さずに決着をつける。Unity Catalog に「自分が使う資格情報」を渡させ、それを自分のマシンから実行する。同じロール、同じセッション、同じネットワークで、変数は「どの経路にスコープされた資格情報か」だけである。コントロールが成功して Access Point が拒否されるなら、原因はセッションポリシーであり、自分の IAM やネットワークでは変えられない。

既定で無効な設定が 2 つ必要で、どちらが欠けているかを明示して失敗する。

```sql
-- metastore 管理者
ALTER METASTORE SET external_access_enabled = true;
GRANT EXTERNAL USE SCHEMA   ON SCHEMA <catalog>.<schema> TO `you@example.com`;
GRANT EXTERNAL USE LOCATION ON EXTERNAL LOCATION <name>  TO `you@example.com`;
```

これらは実際のガバナンス統制である。共有メタストアなら終わったら戻すこと。

## 手順 5 — この順序での撤去

順序が重要である。直接手をつけると失敗する箇所が 2 つある。

```bash
# 1. プローブが作成した Unity Catalog オブジェクト
.venv/bin/python shared/scripts/probe_uc_external_location.py \
  --profile fsxn-verify --teardown-only \
  --control-bucket <bucket> --ap-alias <alias>

# 2. Access Point 上のプローブ用オブジェクトは上の手順で消える。
#    バケットとロールはスタックの所有物
aws s3 rm s3://<control-bucket> --recursive --region <region>
aws cloudformation delete-stack --region <region> \
  --stack-name fsxn-databricks-uc-credential
aws cloudformation wait stack-delete-complete --region <region> \
  --stack-name fsxn-databricks-uc-credential

# 3. 手順 1 のベースラインと照合する
python3 shared/scripts/audit_databricks_workspace_footprint.py \
  --region <region> --compare /tmp/fsxn-baseline.json
```

この検証のためにワークスペースも作った場合は、Databricks アカウントコンソールで削除し、**そのうえで**残った AWS リソースを消す。これらは CloudFormation スタックではなく直接作成されるため、ワークスペースを削除しても 1 つも消えない。

| 順 | リソース | 罠 |
|---:|---|---|
| 1 | NAT Gateway | サブネット削除前に `deleting` ではなく `deleted` になっている必要がある |
| 2 | Elastic IP | リリースしないと課金が続く |
| 3 | S3 gateway endpoint | — |
| 4 | Internet gateway | 削除前にデタッチする |
| 5 | サブネット | — |
| 6 | セキュリティグループ | ingress **と** egress のルールを先に削除しないと依存関係で失敗する |
| 7 | ルートテーブル | メインルートテーブルは単独削除できない。VPC と一緒に消える |
| 8 | VPC | 1〜7 が終わるまで `DependencyViolation` で失敗する |
| 9 | ワークスペースの S3 バケット | 先に空にする |
| 10 | `databricks-*-role-*` の IAM ロール 2 つ | インラインポリシーを先に削除する |

その後 audit を再実行し、ベースラインとの差分がゼロであることを確認する。

## 費用

ap-northeast-1 で 2026-08-12 に当日実行したときの実測。価格は同日取得。引用する前に再確認すること。

| 項目 | 費用 |
|---|---|
| NAT Gateway（ワークスペース VPC） | 0.062 USD/時 + 0.062 USD/GB — 放置すると月およそ 45 USD |
| クラシックシングルノードクラスター `m5d.large` | インスタンス 0.146 USD/時 + DBU |
| サーバーレス SQL ウェアハウス Small | このリージョンで 1.00 USD/DBU 時 |
| S3 コントロールバケット | 無視できる程度。オブジェクトは 7 日で失効 |
| IAM ロール、External Location | 無料 |

重要なのは NAT Gateway である。このランブックの他のものは使うのを止めれば課金が止まるが、NAT Gateway は止まらない。

## トラブルシューティング

| 症状 | 原因 |
|---|---|
| Credential 作成時にストレージプロバイダから `403 Forbidden` | External ID が Databricks アカウント UUID になっていない |
| External Location で `AccessDeniedException`、コントロールは成功 | IAM ポリシーに Access Point ARN 形式が無い |
| `url does not specify a valid bucket name` | ARN スタイルの URL を使っている。エイリアス形式にする |
| 読み取りで `/…/_delta_log: … statusCode: 403` | セッションポリシーの問題。想定どおりで、これが今回の発見 |
| `READ VOLUME` を付与済みでも `LIST_FILES_AUTHORIZATION_ERROR.ON_PATH` | 同じ原因。欠けているのは権限ではない |
| `Cannot get file metadata under managed storage` | Access Point とは無関係。`FILE MANAGED` の FileSpace がソースファイルのある Volume を指している。専用 Volume を使う |
| `External Data Access … is disabled` | `--vend-check` にはメタストアの `external_access_enabled` が必要 |
| `Provided access token does not have required scopes: all-apis` | `--vend-check` には `all-apis` を持つトークンが必要 |
| 信頼ポリシーを手書きして `Invalid principal` | 存在する前のロールを自身の principal に指定している。テンプレートは account root + `aws:PrincipalArn` 条件を使う |
| スタック作成中のバケット名エラー | ロール名が長すぎる。コントロールバケット名はロール名から派生する |

## このランブックが扱わないこと

- VPC オリジンの Access Point、および `WINDOWS` アイデンティティの Access Point。実施したのは INTERNET オリジン・UNIX root の Access Point 1 つである。
- セッションポリシーが広がった場合に `_object_metadata` が Access Point 経由でオブジェクトタグを読むのかどうか。読み取りはそのコードに到達する前に拒否される。
- これらの経路のスループットやレイテンシ。
- 登録より先の FILE 型そのもの。それは [Databricks FILE 型評価](./databricks-file-type-evaluation.md) を参照。

## 関連

- [Databricks FILE 型評価](./databricks-file-type-evaluation.md) — 本ランブックの元になった分析
- [Databricks 検証環境とコスト](./databricks-verification-environment-cost.md) — トライアルと非トライアル、実行費用
- [ブロッカートラッカー BLK-001](./blocker-tracker.md#blk-001-uc-の資格情報払い出しでは通らない-s3-ap-の読み取り) — 訂正後のブロッカー
- [互換性マトリクス](./compatibility-matrix.md) — 他エンジンとの位置関係
- エビデンス: [2026-08-12 の実行](../../verification-pack/databricks/file-type/evidence/2026-08-12/evidence-record-tokyo.yaml)
