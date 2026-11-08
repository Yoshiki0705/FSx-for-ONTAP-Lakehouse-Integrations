# 長時間自律運用の規律 — このリポジトリ固有の接続

土台はグローバル steering にある（複製しない。読む側はそちらを一次情報にする）。

- 並行実行・監査役・判断記録の形: `ai-agent-workflow`（Parallel-by-default 節、Auditor Sub-Agent 節）
- ベンチマークのメタデータとばらつきの規律: `benchmark-and-evidence-standards`

このファイルは、その土台をこのリポジトリのどこに接続するかだけを書く。多段タスク（新パターン追加 / 検証 / IaC 変更）に着手するたびに参照する。

## 判断記録の置き場所

このリポジトリには agent 向けの `.agents/tasks/` 慣習が無い。設計判断の慣習は ADR、検証の慣習は verification-pack の evidence YAML。どちらも追跡対象。Decisions / Rejected alternatives / Assumptions の3節は、タスクの種類で置き場所が分かれる。

| タスクの性質 | 置き場所 | git | 3節の対応 |
|---|---|:---:|---|
| 設計判断（同期方式の選択、アーキテクチャ標準の採択など） | `docs/adr/ADR-NNN-*.md` の既存フォーマット | 追跡 | Decisions → Decision、Rejected alternatives → Alternatives Considered、Assumptions → Context/Consequences に書く |
| 検証（統合エンジンの互換性実測、昇格判断） | `verification-pack/<integration>/evidence/*.yaml` | 追跡 | 判断の根拠（却下案・未検証前提）は process metadata なので下の `.private/tasks/` に分ける。YAML には測定事実のみ |
| 上記に当てはまらない多段タスクの process metadata（却下案・未検証前提・根拠 tier） | `.private/tasks/<task>/impl-note.md` | **gitignored** | 3節をこの1ファイルに収める。別ファイルに切り出さない |

`.private/`（と `.agents/`）は `.gitignore` 済み。却下案・未検証前提・根拠 tier を含む process metadata は、グローバル steering の output-standards（review provenance は公開物に残さず非公開へ）に従い gitignored 側に置く。これが既定。公開する ADR / evidence YAML には、確定した判断と測定事実だけを書く。

既存の記録ファイルがあるタスクでは、新名を増やさずそれに3節を追記する。`impl-note.md` に統一しなくてよい。

## evidence tier の語彙 — 新語の不追加

Decisions の根拠欄に evidence tier を対応づけるとき、このリポジトリに既にある2系統の語彙を使う。グローバル steering の例示（verified / documented / field-observation / hypothesis）を上書きで持ち込まない。5つ目の語を作らない。

| 系統 | 語彙 | 出典 | Decisions 根拠欄での使い方 |
|---|---|---|---|
| Verification Level | Functional Verified / Security Verified / Production Validated | `verification-pack/README.md` | 統合エンジンの互換性・昇格に関わる判断の根拠 |
| ADR Status | Proposed / Accepted / Deprecated / Superseded | `docs/adr/README.md` | 設計判断の状態 |

根拠が「測定」なら対応する Verification Level を、「文献」なら出典 URL を、「推測」なら明示的に推測と書く（土台の `benchmark-and-evidence-standards` の Distinction Requirements に従い Sample run / Service limit / Observed limit を区別する）。

## 監査役の既存の仕組みへの相乗り

専用カスタムエージェント（`.kiro/agents/`）も自動 hook も作らない。合図（同一アプローチ2回失敗 / 同じファイルを3回以上編集 / 多段タスクで同じエラー再発）に気づいたら手で呼ぶ。

- 判断の見直し・観点の洗い出し: `semantic_reviewer` に判断記録（上の置き場所のいずれか）と変更差分を渡す
- 前提が実装と合うかの確認: `context-gatherer` に「この Assumptions は実装と合致するか」を調べさせる

指示は疑う方向に向ける（推測根拠はどれか、復活すべき却下案はあるか、外れたら無駄になる未検証前提はどれか）。公開物コミット直前のレビューは persona review board の担当で、監査役とは分ける。

## ばらつきの接続 — 検証テンプレートの既知の穴

性能・スループット・レイテンシ・コストを測るとき、変更の効果を主張する前に未変更構成のラン間ばらつきを測る（規律の本体は `benchmark-and-evidence-standards`）。このリポジトリ固有の接続:

- `verification-pack/templates/evidence-record.yaml` には `query_latency_p50_ms` / `query_latency_p95_ms` の単発値フィールドしか無く、`iteration_count` / `standard deviation` / ラン間ばらつきを記録する欄が無い。性能数値を YAML に残すときは、土台が必須とするメタデータ（`benchmark_run_id` / `iteration_count` / `warm_up_runs` / 標準偏差）を `additional_config` か記録本文に補って書く。単発値だけを残さない。
- `verification-pack/README.md` が参照する `templates/benchmark-record.yaml` は**実在しない**。ベンチマーク記録のテンプレートが要る多段タスクで、このズレに最初に触れたら、土台の必須メタデータを満たす形で新設するか、README の参照を直す（どちらも公開物なのでコミット前に persona review board）。

## このリポジトリ固有の繰り返しタスク型チェックリスト

2回目の同種の失敗は「ここに項目が足りない」兆候。1項目ずつ育てる。

### 検証ランの追加（verification-pack に統合エンジンを1つ足す）

- [ ] `verification-pack/<integration>/` に `01-functional-tests` / `02-negative-tests` / `03-benchmark` / `evidence` の構成を既存ディレクトリに合わせて作る
- [ ] negative-test は `templates/negative-test-result.yaml` の NEG-001〜010 を起点にする（新 AP で ACL 非継承・単一 identity 認可の論点を外さない）
- [ ] evidence YAML に環境メタデータ（region / fsxn_deployment_type / throughput_capacity / ontap_version）を埋める。空のまま PASS にしない
- [ ] 性能を測るなら、未変更構成のラン間ばらつきを先に測る（上の「ばらつきの接続」）
- [ ] 昇格判断は README の Promotion Decision チェックリストで行う。Production Validated を実測なしで名乗らない

### 新 CloudFormation パターンの追加

- [ ] 命名を外さない（Amazon FSx for NetApp ONTAP → FSx for ONTAP。短縮形や bare 形は不可）。pre-commit の命名ゲートで確認
- [ ] 例 IP は RFC 5737（`198.51.100.x`）。実 IP・アカウント ID を書かない
- [ ] パラメータファイルは `[{"ParameterKey":...,"ParameterValue":...}]` 形式。`cfn-params/` の実値は gitignored、example だけ追跡
- [ ] JA/EN parity（同じ節構成・数値の単位一致）。docs-quality / number-parity ゲートで確認
- [ ] S3 Access Points のネットワーク注意点（Gateway Endpoint が internet-origin AP を落としうる）を該当パターンで踏まない
