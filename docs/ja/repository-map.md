🌐 [English](../en/repository-map.md) | **日本語**

# 問いごとの参照先リポジトリ

> このリポジトリが扱うのは Amazon FSx for NetApp ONTAP の一断面です。ファイルデータを
> S3 Access Point 経由で分析・Lakehouse エンジンから読む、コピーを作らない経路だけを扱います。
> **FSx for ONTAP 全般のガイドではなく、それを目指してもいません。** 隣接領域は 9 つの
> 兄弟リポジトリが担当します。**既に答えがある問いを再導出しないために、**どれを開くべきかを
> このページで示します。

## このリポジトリの担当範囲

FSx for ONTAP S3 Access Point に対する分析・Lakehouse エンジンの実測挙動です。どのエンジンと
テーブルフォーマットの組み合わせが動き、どれが動かず、各主張が何に依拠しているか。Athena、
Glue、EMR、Redshift Spectrum、DuckDB、Snowflake、Databricks、Delta Lake、Iceberg。
それぞれのデプロイ可能な CloudFormation と、全結果の裏にある evidence レコードを含みます。

**意図的に扱わない範囲**: FSx for ONTAP 自体の選定・サイジング・移行・運用、ランサムウェア対策と
不変性、監査ログの搬送、ブロックストレージ、VMware 移行。以下が担当します。

## 問いごとの参照先

| 問い | リポジトリ | 担当範囲 |
|---|---|---|
| FSx for ONTAP を採用すべきか。どう設計・移行・運用するか | [FSx-for-ONTAP-Adoption-Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook) | 設計・構築・運用の知見を、ライフサイクル（評価 → 設計 → 移行 → 構築 → 運用 → 最適化）とトピックの 2 軸で整理。確度の階層を明示。8 言語。**分析に固有でない問いの出発点** |
| S3 Access Point 単体の挙動と、実証済みのサーバーレスパターン | [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) | 17 業種のユースケース、FPolicy イベント駆動パイプライン、容量ガードレール、シークレットローテーション、SLO 可観測性、property-based testing。**本リポジトリが引用するオブジェクトサイズ上限と API 挙動の実測はここにあります** |
| ランサムウェアの検知と生還、不変性の証明 | [FSx-for-ONTAP-Cyber-Resilience-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-Cyber-Resilience-Patterns) | ONTAP ARP、サードパーティのファイルセキュリティ連携、FPolicy によるイベント駆動対応、ストレージネイティブのデータ保護 |
| 監視と、監査ログの SIEM への取り込み | [FSx-for-ONTAP-Observability-integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations) | EC2 不要の監査ログ搬送。Datadog、Splunk、New Relic、Grafana、Elastic 等へ S3 Access Point と Lambda 経由 |
| このデータ上でアクセス制御付き RAG を作る方法 | [FSx-for-ONTAP-Agentic-Access-Aware-RAG](https://github.com/Yoshiki0705/FSx-for-ONTAP-Agentic-Access-Aware-RAG) | Amazon Bedrock を用いたアクセス制御対応の Agentic RAG、AWS CDK でデプロイ。**アクセスポイントは全リクエストを 1 つの ID で認可するため、絞り込みをインデックス側で設計する必要があり、ここが関係します** |
| エッジ・IoT データをそもそもどう集めるか | [ONTAP-Edge-to-Cloud-AI](https://github.com/Yoshiki0705/ONTAP-Edge-to-Cloud-AI) | 散在するエッジデバイスのデータを ONTAP に集約し、Bedrock・Athena・SageMaker で組織横断に活用 |
| 収集した 1 つのデータセットを、コピージョブなしで NFS / SMB 拠点へ配る方法 | [S3-Burst-on-ONTAP-Files](https://github.com/Yoshiki0705/S3-Burst-on-ONTAP-Files) | S3 Access Point で収集し FlexCache で配信。実例はハイブリッドクラウドの AV / ADAS Hardware-in-the-Loop テスト |
| ガバナンス済みマルチアカウント環境への組み込み | [BLEA-FSx-for-ONTAP-Usecase](https://github.com/Yoshiki0705/BLEA-FSx-for-ONTAP-Usecase) | BLEA ゲストシステムのユースケース。エンタープライズファイルストレージと分析・サイバーレジリエンス・FlexCache・モダナイゼーションの組み合わせ |
| VMware ワークロードを EC2 + ONTAP ストレージへ移行する方法 | [VMware-Migration-EC2-ONTAP](https://github.com/Yoshiki0705/VMware-Migration-EC2-ONTAP) | ONTAP ストレージを用いた VMware から EC2 への移行 |

## 各リポジトリの関係

分担の軸は技術ではなく問いの種類です。**越えると最も時間を失う境界が 2 つ**あるので明示します。

**Adoption Playbook と本リポジトリの境界。** Playbook は「何をすべきか、なぜか」に、
ライフサイクル全体と全プロトコルにわたって答えます。本リポジトリは「エンジン X は
アクセスポイントに対して実際に動くのか、実測で何が起きたか」に答えます。**設計判断は
Playbook、互換性の主張は本リポジトリ。** Playbook は分析の結果を再掲せず本リポジトリを
引用しており、このページがその戻り経路です。

**Serverless-Patterns と本リポジトリの境界。** どちらも S3 Access Point を扱います。あちらは
アクセスポイント自体を特徴づけます（対応操作、サイズ上限、イベントパイプライン）。こちらは
それを通した分析エンジンの挙動を特徴づけます。**アクセスポイントに関する数値が本リポジトリに
出るときは、あちらへの引用になります。** 実測値は測定環境と一体でしか意味を持ちません。

## ファミリ共通の規約

- 初出は "Amazon FSx for NetApp ONTAP"、以降は "FSx for ONTAP"。
- **確度は暗示せず明示します。** 本リポジトリは 4 つのステータスマーカーと 4 段階の検証
  レベルを使います。読み方は [llms.txt](../../llms.txt)、定義は
  [互換性マトリクス](./compatibility-matrix.md) にあります。Playbook は文書の frontmatter で
  確度の階層を示します。**どちらでも、根拠の記載が無い主張は事実ではなく欠落です。**
- 数値は測定環境（リージョン、ONTAP バージョン、構成）と一緒に運びます。**それらを外して
  別の文脈へ持ち出さないでください。**

## 関連ドキュメント

- [llms.txt](../../llms.txt) — 本リポジトリの機械可読な入口
- [リーディングパスガイド](./reading-path-guide.md) — 本リポジトリ内の辿り方
- [クロスリポジトリ統合戦略](./cross-repo-integration-strategy.md) — 上記リポジトリ間の
  進行中の統合作業。実装の詳細レベル
