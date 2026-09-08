🌐 [English](../en/databricks-verification-environment-cost.md) | **日本語**

# FSx for ONTAP 統合の検証用 Databricks ワークスペース: コストと判断軸

> **ステータス**: 単価は 2026-08-12 に一次情報から取得（Databricks 自身の価格データファイルと AWS Price List API）。単価は変わるため、引用前に再確認すること。
> **Evidence tier**: **Public**（公開単価）/ **Verified**（本アカウントで観測）/ **Project-context**（本プロジェクトの判断）/ **Hypothesis**。
> **このページの存在理由**: 検証ケースのうち 2 件が手元のワークスペースでは解けず、その*理由*を突き止めたことが価格表より有用だった。ボトルネックはプラン階層でも価格でもなく、ワークスペースのストレージモードとリージョンだった。

---

## エグゼクティブサマリー

- **プラン階層は多くの場合ボトルネックではない。** クレジットで動く Premium プランのワークスペースでも Unity Catalog の Storage Credential は問題なく作成できた（**Verified**）。できなかったのはクラシックコンピュートの起動で、理由はそのワークスペースが **"Serverless only"** として作成されていたことだった。
- **FSx for ONTAP 統合を検証できるかを決めるのは 2 つの属性である**: **リージョン**（FSx ファイルシステムと一致必須）と、**ストレージ / コンピュートモード**（Instance Profile が必要なら「Use your existing cloud account」必須）。
- **支配的なコストはコンピュートではない。** Databricks 管理 VPC 内の **NAT Gateway** であり、**ap-northeast-1 で $0.062/時 = 月約 $45。クラスタが動いていなくても課金される。**
- **Databricks のクレジットは AWS のインフラ費用を払わない。** クレジットは DBU 用で、EC2・NAT Gateway・S3 は AWS アカウントに別途請求される。「$400 の無償クレジット」があっても作業は無料にならない。
- **Tokyo はクラシックコンピュートでは Oregon と同額、SQL Serverless では約 43% 高い**（Premium で $1.00 対 $0.70/DBU）。
- **本当のリスクは撤去であり、しかもスタック 1 個の削除では済まない。** 自動セットアップ経路では、Databricks が IAM ロール・S3 バケット・VPC を **CloudFormation スタックではなく直接**作成する。ワークスペースを削除してもこれらは残る。

---

## 1. そのワークスペースが用を成すかを決めるもの

**Evidence tier: Verified**（本アカウント、2026-08-12）。

価格を比較する前に 3 点を確認する。ここを外すと「問いに答えられないワークスペース」に課金することになる。

| 属性 | 要件 | 理由 |
|---|---|---|
| **リージョン** | FSx for ONTAP ファイルシステムと一致 | S3 Access Point はボリュームと同一リージョンにしか存在できない。コンピュートを同居させればクロスリージョンのレイテンシと egress を避けられ、[リージョン設計ガイド](./region-design-guide.md)とも整合する |
| **ストレージ / コンピュートモード** | クラシックコンピュートが必要なら **「Use your existing cloud account」** | "Serverless only" のワークスペースはクラシッククラスタを起動できず、Instance Profile が使えない。Instance Profile がなければ Access Point への唯一の経路は UC External Location で、それはまさに [BLK-001](./blocker-tracker.md#blk-001-uc-の資格情報払い出しでは通らない-s3-ap-の読み取り) がブロックしている |
| プラン階層 | Premium で十分 | Enterprise は DBU 単価が高く、本用途に不要なコンプライアンス機能が付く。特筆すべきは、クレジットで動く Premium でも UC Storage Credential が**作成できた**こと |

> **名前を付けておくべき罠**: 「トライアル」「無償クレジット」を「機能制限あり」と読み替え、有償プランが解決策だと結論しがちである。本件ではプランは既に Premium で、Storage Credential も動いた。制約は**ワークスペース作成時に選んだストレージモード**であり、これは後から変更できない。別のワークスペースを作ることになる。

---

## 2. 公開単価

### Databricks DBU 単価

**Evidence tier: Public** — `databricks.com/product/pricing` が描画に使っている価格データファイルより、2026-08-12 取得。

| SKU | AP (Tokyo) Premium | AP (Tokyo) Enterprise | US West (Oregon) Premium |
|---|---|---|---|
| Jobs Compute / Photon | **$0.15** | $0.20 | $0.15 |
| All-Purpose / Photon | **$0.55** | $0.65 | $0.55 |
| SQL Classic | $0.22 | $0.22 | — |
| SQL Pro | $0.78 | $0.78 | — |
| SQL Serverless | **$1.00** | $1.00 | **$0.70** |
| Jobs Serverless | $0.39 | — | — |

クラシックコンピュートは Tokyo と Oregon で同額。**SQL Serverless は Tokyo が約 43% 高い。** サーバーレス SQL 主体のワークロードならリージョン選択が価格に実際に響くが、クラシックコンピュートでは響かない。

> **Jobs Compute は All-Purpose の約 4 分の 1**（$0.15 対 $0.55）。対話型ノートブックを必要としないスクリプト化された検証なら、ジョブとして実行するほうが安い形になる。対話的なデバッグに価値がある場合に All-Purpose を使う。

### AWS 単価（ap-northeast-1）

**Evidence tier: Public** — AWS Price List API、2026-08-01 発効。

| リソース | 単価 |
|---|---|
| m5d.large（2 vCPU, 8 GiB） | $0.146 / 時 |
| m5d.xlarge（4 vCPU, 16 GiB） | $0.292 / 時 |
| r5d.large（2 vCPU, 16 GiB） | $0.174 / 時 |
| **NAT Gateway** | **$0.062 / 時** + $0.062 / GB |

---

## 3. 支配的なコスト

```
NAT Gateway : $0.062/h × 24 × 30 ＝ 月約 $44.6（アイドル時）
検証本体     : 単一ノード m5d.large、All-Purpose、6 時間 ＝ 約 $4.2
```

コンピュートを支えるために存在するインフラが、コンピュート本体より一桁高い。前者は常時課金、後者は稼働時のみ課金だからである。

帰結は 2 つ。

1. **インスタンスサイズより期間がはるかに重要。** ノードを大きくしても数セントの違い。ワークスペースを 1 か月放置すれば数十ドルの違いになる。
2. **クレジットは守ってくれない。** Databricks クレジットは DBU で消費される。NAT Gateway は AWS の課金である。「無償」の Databricks クレジット上でアイドルしているワークスペースも、AWS 課金は発生し続ける。

> **コストに関する補足**: 見積りを受け入れる前に、管理 VPC が NAT Gateway を 1 個作るのか AZ ごとに作るのかを確認すること。AZ ごとならこの行は倍以上になる。想定ではなく作成後の VPC を実際に見る。

---

## 4. 判断マトリクス

**Evidence tier: Project-context** — 本リポジトリの未解決ケースに対する判断。

| 選択肢 | AWS 費用 | Databricks 費用 | Access Point の読み取りを検証できるか |
|---|---|---|---|
| **A. サーバーレスワークスペース（同一リージョン）** | $0 | SQL Serverless $1.00/DBU | ❌ 不可。Serverless only では Instance Profile が使えず、唯一の経路である UC External Location は BLK-001 でブロック |
| **B.「Use your existing cloud account」（同一リージョン）** | NAT Gateway 約 $1.5/日 + 稼働中の EC2 | Jobs $0.15 または All-Purpose $0.55 /DBU | ✅ **可能 — これだけが可能** |
| **C. 別リージョンの既存ワークスペースを流用** | $0 | そのモードが許す範囲 | ❌ Serverless only なら不可。クロスリージョンでは egress とレイテンシも加わる |

選択肢 A にも数ドル分の狭い価値はある。**現行の**ワークスペースで BLK-001 を再確認し、今日時点のエラーメッセージを採取することである。それは証拠ではあるが、必要としている証拠ではない。

**B を選び、撤去を後工程ではなく作業の一部として扱う。**

---

## 5. スタック削除では終わらない撤去

**Evidence tier: Verified** — ワークスペース作成フローで観測、2026-08-12。

自動セットアップ経路では、レビュー画面が作成対象を正確に列挙する。

| 用途 | リソース |
|---|---|
| Cloud storage | IAM ロール `databricks-storage-role-<workspace-id>` |
| Cloud storage | S3 バケット `databricks-storage-<workspace-id>` |
| Cloud storage | アクセスポリシー `databricks-uc-storage-policy-<workspace-id>` |
| Cloud credentials | IAM ロール `databricks-compute-role-<workspace-id>` |
| Cloud credentials | **VPC `databricks-compute-vpc-<workspace-id>`** — NAT Gateway を含む |
| Cloud credentials | アクセスポリシー `databricks-compute-policy-<workspace-id>` |

これらは **CloudFormation スタックではなく、委譲された IAM 権限で直接**作成される。削除すべきスタックが存在しないため、撤去は各リソースを個別に消すことを意味する。そして課金するのは VPC である。

**Databricks ワークスペースを削除してもこれらは 1 つも消えない。** この非対称性が、アイドルの NAT Gateway が何か月も生き残る仕組みである。

撤去は信用せず検証する。

```bash
# 0 が返ること
aws ec2 describe-nat-gateways --region <region> \
  --filter Name=state,Values=available --query 'length(NatGateways)' --output text

# 命名規約から VPC とバケットを確認
aws ec2 describe-vpcs --region <region> \
  --filters 'Name=tag:Name,Values=databricks-compute-vpc-*' --output json
aws s3api list-buckets --output json   # databricks-storage-<workspace-id> を探す
```

> **何かを作る前にベースラインを記録する。** 対象リージョンで利用可能な NAT Gateway が 0 個であることを先に数えたので、あとから見つかった NAT Gateway は疑いなく自分のものだと言える。このベースラインがないと、撤去の検証で自分のリソースと既存のリソースを区別できない。

過去のワークスペースが残した IAM ロールは課金されないが蓄積する。6 週間前に作成されたワークスペースのロールが残っているのを見つけた。命名規約による定期的な棚卸しの価値がある。

---

## 6. 自動化できない対話ステップ

**Evidence tier: Verified。**

自動セットアップ経路の最後は **「Log in to AWS and create workspace」** で、AWS コンソールのサインインと IAM アクセスリクエストのレビュー画面が開く。このサインインには **MFA コード**が必要である。

AWS CLI の資格情報では足りない。これは API 呼び出しではなくコンソールのフローである。このステップには人を前提に計画し、それ以前（名称・リージョン・ストレージモードの選択、作成対象リストのレビュー）はすべて事前に準備できることを踏まえる。

完全にスクリプト化したい場合は、Credential Configuration・Storage Configuration・Network Configuration を自分で作成してアカウント API に登録し、それらを参照してワークスペースを作成する。これは対話的な MFA プロンプトを、IAM と VPC の定義を自分で書いて保守することと引き換えにする選択である。

---

## 参考資料

- [Databricks の価格](https://www.databricks.com/jp/product/pricing) · [AWS pricing by Databricks](https://www.databricks.com/product/aws-pricing)
- [Serverless workspaces](https://docs.databricks.com/admin/workspace/serverless-workspaces)
- [AWS NAT Gateway の価格](https://aws.amazon.com/jp/vpc/pricing/) · [Amazon EC2 の価格](https://aws.amazon.com/jp/ec2/pricing/on-demand/)
- 本リポジトリ: [ブロッカートラッカー](./blocker-tracker.md)（BLK-001）· [リージョン設計ガイド](./region-design-guide.md) · [FILE 型評価](./databricks-file-type-evaluation.md) · [Databricks 統合](../../integrations/databricks/README.md)
