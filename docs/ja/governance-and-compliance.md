# ガバナンスとコンプライアンス

## 概要

本ドキュメントは、FSx for ONTAP Lakehouse 統合のガバナンス、セキュリティ、コンプライアンスフレームワークを定義します。データ分類、アクセス制御、監査、責任分界をデプロイ前に明確に文書化する必要がある規制産業（医療、金融サービス、公共セクター）向けに設計されています。

## データ分類

| 分類 | 説明 | データ例 | アクセス制御 |
|------|------|---------|------------|
| **Public** | 非機密、公開可能 | 集計レポート、公開データセット | Internet-origin AP 経由のオープン読み取り |
| **Internal** | 業務上機密、規制対象外 | 内部分析、運用メトリクス | VPC-origin AP、チームスコープの IAM ロール |
| **Confidential** | 業務上重要、契約上の義務あり | 金融取引、顧客記録 | VPC-origin AP、ユーザー単位 IAM、制限付きファイルシステムユーザー |
| **Regulated** | 法的/規制要件の対象 | PHI（HIPAA）、PII（GDPR）、PCI DSS データ | VPC-origin AP、最小権限 IAM、読み取り専用 AP ユーザー、監査ログ必須 |

## アクセス制御アーキテクチャ

FSx for ONTAP S3 Access Points は**二層認可モデル**を使用します（[ソース](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)）：

```
┌─────────────────────────────────────────────────────────────────┐
│                    Request Flow                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Caller (IAM Principal)                                          │
│       │                                                           │
│       ▼                                                           │
│  ┌─────────────────────────────────────────┐                     │
│  │  Layer 1: AWS IAM Authorization          │                     │
│  │  ─────────────────────────────────────── │                     │
│  │  • IAM identity policy                   │                     │
│  │  • S3 Access Point resource policy       │                     │
│  │  • VPC Endpoint policy (if applicable)   │                     │
│  │  • Service Control Policy (SCP)          │                     │
│  │  • Network origin check (VPC/Internet)   │                     │
│  └─────────────────┬───────────────────────┘                     │
│                    │ ALLOW                                         │
│                    ▼                                               │
│  ┌─────────────────────────────────────────┐                     │
│  │  Layer 2: File System Authorization      │                     │
│  │  ─────────────────────────────────────── │                     │
│  │  • File system user (UNIX or Windows)    │                     │
│  │  • UNIX: mode-bits or NFSv4 ACLs        │                     │
│  │  • NTFS: Windows ACLs                    │                     │
│  │  • Directory/file level permissions      │                     │
│  └─────────────────┬───────────────────────┘                     │
│                    │ ALLOW                                         │
│                    ▼                                               │
│              Access Granted                                        │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

**両方のレイヤーがリクエストを許可する必要があります。** いずれかのレイヤーでの明示的な Deny は、他のレイヤーの Allow ステートメントを上書きします。

### レイヤー 1: IAM 認可の詳細

| ポリシータイプ | スコープ | 使用例 |
|--------------|--------|--------|
| IAM アイデンティティポリシー | プリンシパル単位（ユーザー/ロール） | アナリストロールに AP への読み取り専用アクセスを付与 |
| アクセスポイントポリシー | アクセスポイント単位 | AP を特定の IAM ロールまたは VPC に制限 |
| VPC エンドポイントポリシー | VPC エンドポイント単位 | VPC からアクセス可能な AP を制限 |
| サービスコントロールポリシー | OU/アカウント単位 | 組織全体の制限を強制 |
| ネットワークオリジン | アクセスポイント単位（作成後変更不可） | VPC-origin: バインドされた VPC 外からの全リクエストを拒否 |

### レイヤー 2: ファイルシステム認可の詳細

| セキュリティスタイル | 権限モデル | ユースケース |
|------------------|-----------|------------|
| UNIX | mode-bits (rwx) または NFSv4 ACL | Linux/NFS ワークロード |
| NTFS | Windows ACL (full/modify/read) | Windows/SMB ワークロード |
| Mixed | UNIX 有効、Windows クライアント用 NTFS | ハイブリッド環境 |

**重要**: アクセスポイントに関連付けられたファイルシステムユーザーが、その AP を通じた全リクエストの権限レベルを決定します。最小権限の原則を使用してください：
- 読み取り専用分析 → 読み取り専用ファイルシステムユーザー
- ETL 書き戻し → 特定ディレクトリにスコープされた読み書きユーザー
- 本番アクセスポイントには root（UID 0）を使用しない

## ネットワークセキュリティ

### Block Public Access

Amazon S3 は FSx for ONTAP ボリュームに接続された全アクセスポイントに対して Block Public Access をデフォルトで強制します。**この設定は変更または無効化できません。**（[ソース](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)）

### ネットワークオリジンオプション

| オリジン | セキュリティレベル | ユースケース | 制限 |
|---------|----------------|------------|------|
| **VPC** | 最高 | 規制データ、内部分析 | 作成後変更不可。Athena/マネージドサービスからアクセス不可 |
| **Internet** | 標準（IAM 制御） | AWS マネージドサービス（Athena、Bedrock、Glue） | アクセス制御に強力な IAM ポリシーが必要 |

**注**: 「Internet origin」はパブリックアクセスを意味しません。全リクエストに有効な IAM 認証情報が必要です。Block Public Access が匿名アクセスを防止します。（[ソース](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/configuring-network-access-for-s3-access-points.html)）

### 規制データ向け推奨ネットワークアーキテクチャ

```
┌─────────────────────────────────────────────────┐
│  VPC (Private Subnets Only)                      │
│                                                   │
│  ┌───────────┐    ┌──────────────────────┐       │
│  │ Analytics │───▶│ S3 Gateway Endpoint  │       │
│  │ Platform  │    │ (in-VPC traffic)     │       │
│  └───────────┘    └──────────┬───────────┘       │
│                              │                    │
│  ┌───────────┐    ┌──────────▼───────────┐       │
│  │On-premises│───▶│ S3 Interface Endpoint│       │
│  │via DX/VPN │    │ (external traffic)   │       │
│  └───────────┘    └──────────┬───────────┘       │
│                              │                    │
│                    ┌─────────▼────────────┐       │
│                    │ S3 Access Point      │       │
│                    │ (VPC origin)         │       │
│                    └─────────┬────────────┘       │
│                              │                    │
│                    ┌─────────▼────────────┐       │
│                    │ FSx for ONTAP Volume │       │
│                    └─────────────────────-┘       │
└─────────────────────────────────────────────────┘
```

## 監査とログ

| ログソース | キャプチャ対象 | 保持期間 | 用途 |
|-----------|-------------|---------|------|
| **AWS CloudTrail** | FSx for ONTAP API コール（CreateAccessPoint 等）、S3 データイベント（AP 経由の GetObject、PutObject） | 設定可能（コンプライアンスには 1 年以上推奨） | 誰が何にいつどこからアクセスしたか |
| **FSx for ONTAP 監査ログ** | NFS/SMB ファイルアクセスイベント（ONTAP fpolicy/audit 経由） | ONTAP 上で設定可能 | S3 AP を経由しない直接ファイルシステムアクセス |
| **Lakehouse 監査ログ** | クエリ履歴、テーブル変更（プラットフォーム固有） | プラットフォーム依存 | 分析アクティビティ追跡 |
| **VPC フローログ** | FSx for ONTAP ENI へ/からのネットワークトラフィック | 設定可能 | ネットワークレベルのアクセス検証 |
| **S3 Access Point アクセスログ** | CloudTrail 経由の S3 データイベント | CloudTrail と同じ | S3 API レベルのアクセス監査 |

### S3 Access Point の S3 データイベント有効化

アクセスポイント経由の個別オブジェクトレベル操作（GetObject、PutObject）を監査するには、CloudTrail で **S3 データイベント**を有効化します：

```json
{
  "EventSelectors": [{
    "ReadWriteType": "All",
    "DataResources": [{
      "Type": "AWS::S3::AccessPoint",
      "Values": ["arn:aws:s3:REGION:ACCOUNT:accesspoint/ACCESS-POINT-NAME"]
    }]
  }]
}
```

## 暗号化

| レイヤー | メカニズム | 鍵管理 | 備考 |
|---------|----------|--------|------|
| **保存時** | SSE-FSX（自動） | AWS KMS マネージド | 全 FSx for ONTAP ファイルシステムがデフォルトで暗号化。アプリケーションに透過的 |
| **転送中（S3 API）** | TLS 1.2+ | AWS マネージド | S3 API コールに HTTPS 強制 |
| **転送中（NFS）** | Kerberos 暗号化（オプション） | 顧客管理 | 同じデータにアクセスする NFS クライアント用 |
| **転送中（SMB）** | SMB 暗号化（オプション） | 顧客管理 | 同じデータにアクセスする SMB クライアント用 |

**注**: SSE-FSX は S3 Access Points でサポートされる唯一のサーバーサイド暗号化モードです。SSE-S3、SSE-KMS、SSE-C はサポートされていません。（[ソース](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)）

## データ所在地

| 観点 | 保証 |
|------|------|
| 保存データ | FSx for ONTAP がデプロイされた AWS リージョンに留まる |
| S3 Access Point | FSx for ONTAP ボリュームと同じリージョンに作成必須（[ソース](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-point-for-fsxn-restrictions-limitations-naming-rules.html)） |
| DR レプリケーション | 指定された DR リージョンへの SnapMirror（顧客制御） |
| クエリ結果 | 顧客指定の S3 バケットに書き込み（同一または異なるリージョン） |
| バックアップストレージ | ファイルシステムと同じリージョン、複数 AZ にまたがる冗長性 |

## 責任分界マトリクス（RACI）

| 責任 | AWS | FSx for ONTAP 管理者 | Lakehouse 管理者 | データオーナー |
|------|-----|-----------|-----------------|-------------|
| 物理インフラセキュリティ | **R** | — | — | — |
| FSx for ONTAP ファイルシステム保存時暗号化 | **R** | — | — | — |
| FSx for ONTAP ファイルシステムプロビジョニング | I | **R** | — | — |
| S3 Access Point 作成・ポリシー | I | **R** | C | — |
| 分析用 IAM ロール/ポリシー | I | C | **R** | — |
| ファイルシステムユーザー権限 | I | **R** | C | A |
| データ分類 | — | — | C | **R** |
| Lakehouse テーブルアクセス制御 | — | — | **R** | A |
| 監査ログレビュー | — | C | C | **R** |
| コンプライアンス検証 | — | C | C | **R** |
| インシデント対応 | C | **R** | **R** | A |

R = 実行責任、A = 説明責任、C = 相談、I = 情報提供

## 業界別考慮事項

### 医療（HIPAA）

| 要件 | 実装 |
|------|------|
| PHI アクセス制御 | VPC-origin AP + 最小権限 IAM + 読み取り専用ファイルシステムユーザー |
| 監査証跡 | AP に対する CloudTrail S3 データイベント有効化 |
| 暗号化 | SSE-FSX（保存時）+ TLS（転送中）— 両方自動 |
| データ所在地 | 単一リージョンデプロイ、BAA なしでの PHI クロスリージョンレプリケーション禁止 |
| 匿名化 | 分析アクセス前の匿名化用 Glue ETL パイプライン |
| サンプルデータ | 開発/テストには合成データのみ使用 |

### 金融サービス（PCI DSS / SOX）

| 要件 | 実装 |
|------|------|
| 職務分掌 | 管理者とアナリストで別々の IAM ロール。ドメインごとに別々の AP |
| データメッシュドメインオーナーシップ | ドメインごとの SVM とコンシューマーごとのアクセスポイント |
| 監査保持 | CloudTrail ログを 7 年以上保持（SOX） |
| 変更管理 | Infrastructure as Code（CloudFormation）、PR ベースの変更 |
| DR/BCP | SnapMirror クロスリージョン、文書化された RTO/RPO |

### 製造（OT/IT 境界）

| 要件 | 実装 |
|------|------|
| OT/IT 分離 | OT データ収集と IT 分析で別々の VPC |
| エッジ取り込み | NFS/SMB 書き込み（エッジから）→ S3 AP 読み取り（分析用） |
| 長期保持 | コールドデータの FabricPool 階層化 |
| データ鮮度 | ほぼリアルタイム（NFS 書き込みが S3 AP 経由で即座に可視） |

## セキュアリファレンスデプロイメント: 医療読み取り専用分析

```yaml
# Minimal secure deployment for healthcare analytics
Components:
  FSx for ONTAP:
    deployment_type: MULTI_AZ
    throughput_capacity: 512  # MB/s
    storage_capacity: 1024   # GB
    ontap_version: "9.17.1+"
    
  S3 Access Point:
    network_origin: VPC      # Private access only
    file_system_user: 
      type: UNIX
      username: analytics_reader  # Read-only user
    block_public_access: true     # Enforced (cannot disable)
    
  IAM:
    role: healthcare-analytics-role
    policy:
      - Effect: Allow
        Action: [s3:GetObject, s3:ListBucket]
        Resource: 
          - "arn:aws:s3:REGION:ACCOUNT:accesspoint/healthcare-ap"
          - "arn:aws:s3:REGION:ACCOUNT:accesspoint/healthcare-ap/object/*"
      # No PutObject, DeleteObject — read-only
      
  VPC:
    endpoint_type: Gateway  # For in-VPC analytics
    endpoint_policy: Scoped to healthcare-ap only
    
  Audit:
    cloudtrail: 
      data_events: enabled
      resource: "arn:aws:s3:REGION:ACCOUNT:accesspoint/healthcare-ap"
      retention: 7_years
      
  Data:
    type: Synthetic only (no real PHI in dev/test)
    format: Parquet (de-identified)
```

## デプロイ前チェックリスト

> **重要**: 本ドキュメントは汎用的なガバナンスフレームワークを提供します。実際のデプロイでは、全セクションを顧客の法務、セキュリティ、データ保護、ビジネスステークホルダーとともにカスタマイズする必要があります。顧客固有のレビューなしにこれらのテンプレートをそのまま使用しないでください。

### 医療 PoC ガバナンスインテーク質問

医療 PoC を開始する前に、顧客と以下の質問に回答してください：

| # | 質問 | 回答選択肢 | 設計への影響 |
|---|------|-----------|------------|
| 1 | データに PHI または PII が含まれますか？ | はい / いいえ / 部分的に | はいの場合：S3 AP 公開前に匿名化パイプラインが必要 |
| 2 | データは匿名化済み、仮名化済み、それとも生データですか？ | 匿名化済み / 仮名化済み / 生データ | 生データ/仮名化：処理なしで S3 AP 経由公開不可 |
| 3 | 想定される用途は？ | 管理 / 研究 / 臨床文書 / CDS / 患者向け | リスクレベルと必要な承認を決定（RAG 用途リスク分類参照） |
| 4 | AI 生成レスポンスを誰がレビューしますか？ | 指名された役割/人物 | 用途分類に適格な人物である必要あり |
| 5 | データオーナーは誰ですか？ | 指名された役割/人物 | アクセス承認とリスク受容に必要 |
| 6 | 残留リスクを受容できるのは誰ですか？ | 指名された役割/人物 | リスク受容権限マトリクス参照 |
| 7 | 必要な監査ログ保持期間は？ | 年数 | 最低 6 年（HIPAA）または 7 年（SOX） |
| 8 | IRB/倫理委員会の承認は必要ですか？ | はい / いいえ | 研究二次利用には必要 |

### 医療 PoC 推奨初期スコープ

最初の医療 PoC では、最もリスクの低い構成に限定してください：

- ✅ 匿名化済みドキュメントのみ（生の PHI なし）
- ✅ 研究支援または管理用途のみ
- ✅ 読み取り専用 S3 Access Point
- ✅ 全 RAG レスポンスに人間レビュー必須
- ❌ 患者向けレスポンス：初期スコープ外
- ❌ 臨床意思決定支援：初期スコープ外
- ❌ 生の PHI：初期スコープ外

### 医療
- [ ] 匿名化パイプラインの検証
- [ ] サンプル/テストデータに PHI がないことの確認
- [ ] VPC-origin アクセスポイント（Athena/マネージドサービスを使用しない場合）
- [ ] 読み取り専用ファイルシステムユーザー
- [ ] CloudTrail S3 データイベント有効化
- [ ] 監査ログ保持期間の設定（7 年以上）
- [ ] AWS との BAA 締結
- [ ] データ所在地の確認（単一リージョン）

### 金融サービス
- [ ] 職務分掌の検証（管理者 ≠ アナリストロール）
- [ ] ドメインごとのアクセスポイント（スコープ付きポリシー）
- [ ] CloudTrail 有効化（長期保持）
- [ ] SnapMirror DR の設定とテスト
- [ ] 変更管理プロセスの文書化
- [ ] 暗号化の検証（保存時 + 転送中）

### 製造
- [ ] OT/IT ネットワーク分離の確認
- [ ] エッジデータ取り込みパスの検証
- [ ] データ鮮度 SLA の文書化
- [ ] 長期保持ポリシーの設定（FabricPool）

---

## 安全性 vs. 保証

技術的安全性と組織的保証は異なる関心事です。規制産業では両方が必要です。

| 観点 | 安全性（技術的安全性） | 保証（説明可能な安心） |
|------|---------------------|--------------------------|
| **何に答えるか** | 「システムは技術的に安全か？」 | 「なぜ安全なのかをステークホルダーに説明できるか？」 |
| **対象者** | セキュリティエンジニア、監査人 | CxO、コンプライアンス担当者、患者、規制当局 |
| **エビデンス** | 設定、テスト結果、ペネトレーションテスト | ドキュメント、図表、責任マトリクス、監査レポート |
| **FSx for ONTAP S3 AP の制御** | IAM ポリシー、AP ポリシー、VPC エンドポイント、ファイルシステム ACL、SSE-FSX、Block Public Access | アーキテクチャ図、RACI マトリクス、監査ログサンプル、インシデント対応手順 |

### 安全性制御からの保証構築

| 安全性制御 | 保証成果物 |
|-----------|-----------|
| Block Public Access（強制、無効化不可） | 「匿名アクセスは不可能です — これは AWS がインフラレベルで強制しており、いかなる管理者もオーバーライドできません」 |
| 二層認可 | IAM とファイルシステムの両方のチェックが通過する必要があることを示すアーキテクチャ図 |
| VPC-origin アクセスポイント | 「データはプライベートネットワーク内からのみアクセス可能です — インターネットからのリクエストはポリシー評価前に拒否されます」 |
| CloudTrail S3 データイベント | 誰がいつどこからどのデータにアクセスしたかを示す月次監査レポート |
| SSE-FSX 暗号化 | 「全データは AWS KMS を使用して保存時に暗号化されます — 暗号化は自動で無効化できません」 |
| 読み取り専用ファイルシステムユーザー | 「分析システムはデータの読み取りのみ可能です — ファイルの変更や削除は物理的に不可能です」 |

### 保証ドキュメントチェックリスト

- [ ] 非技術者向けアーキテクチャ概要（平易な言葉による 1 ページ図）
- [ ] データがどこに存在し誰がアクセスできるかを示すデータフロー図
- [ ] 全責任者が署名した RACI マトリクス
- [ ] 監視能力を示す監査ログサンプルレポート（墨消し済み）
- [ ] インシデント対応手順書
- [ ] 年次アクセスレビュープロセス文書
- [ ] 第三者向け説明資料（規制当局、患者、パートナー向け）

---

## 生成 AI / RAG ガバナンス

FSx for ONTAP S3 AP を生成 AI のデータソースとして使用する場合（例：Amazon Bedrock Knowledge Bases、Snowflake Cortex Search）、追加のガバナンス考慮事項が適用されます。

### プラットフォーム別 RAG ガバナンス

| プラットフォーム | RAG パス | データ移動 | ガバナンスモデル | 最適用途 |
|----------|----------|---------|------------|----------|
| **Amazon Bedrock KB** | FSx for ONTAP S3 AP → Bedrock KB → OpenSearch（embedding） | 顧客アカウント内に embedding 作成 | IAM + Bedrock ガードレール + 人間レビュー | AWS ネイティブ、権限認識型検索 |
| **Snowflake Cortex Search** | FSx for ONTAP S3 AP → External Table → COPY INTO → Cortex Search Service | Snowflake ストレージにデータコピー | Snowflake RBAC + Tags + Row Access Policy | Snowflake ネイティブ、ガバナンス付き分析 + RAG |

### Snowflake ガバナンス（FSx for ONTAP データ上）

Snowflake は S3 Access Points 経由でアクセスする FSx for ONTAP データに対して補完的なガバナンスレイヤーを提供します:

| 機能 | 動作 | ガバナンス価値 |
|------|------|-------------|
| **Object Tagging** | `ALTER TABLE ext_table SET TAG sensitivity = 'confidential'` | テーブル/カラムレベルのデータ分類 |
| **Row Access Policy** | ユーザーロール/コンテキストに基づく行フィルタリング | データ重複なしの行レベルセキュリティ |
| **Dynamic Data Masking** | 非認可ロールに対するカラムマスキングポリシー | External Table 上のカラムレベル保護 |
| **Access History** | `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY` で全クエリ追跡 | クエリレベルの監査証跡 |
| **Data Sharing ガバナンス** | Row Access Policy 適用済み External Table の共有 | パートナー/サプライヤーへのガバナンス付き配布 |
| **Cortex AI ガードレール** | Cross-Region Inference 制御、モデルアクセスポリシー | AI 処理境界の制御 |

**Snowflake ガバナンスは FSx for ONTAP S3 AP 上の External Table に適用可能** — ガバナンス機能（Tags, Row Policy, Masking, Sharing, Access History）に COPY INTO は不要。Cortex AI 関数（COMPLETE, SUMMARIZE, EXTRACT_ANSWER）および Cortex Search も Managed Iceberg Table で直接動作し、内部テーブルへのデータ配置は不要（2026年5月確認）。Vision AI の TO_FILE のみ FSx for ONTAP S3 AP ステージでは COPY FILES ワークアラウンドが必要。

### Snowflake 外部エンジンアクセスの監査（2026年5月確認）

Horizon Iceberg REST Catalog 経由の外部エンジンアクセスは `SNOWFLAKE.ACCOUNT_USAGE.STORAGE_REQUEST_HISTORY` で追跡される。HTTP オペレーション（Class 1: PUT/COPY/POST/LIST, Class 2: GET/SELECT）がタイムウィンドウごとのカウント付きで記録される。注意: 外部エンジンは Snowflake クエリエンジンを通らないため、QUERY_HISTORY には記録されない。

### Snowflake Open Catalog (Polaris) vs Horizon REST Catalog

| パス | ユースケース | メタデータ所有者 | ガバナンス強制 |
|------|-----------|---------------|-------------|
| **Horizon REST Catalog**（推奨） | Snowflake が primary writer | Snowflake | ✅ Row Access Policy + Masking 強制 |
| **Open Catalog (Polaris)** | 専用カタログレイヤーが必要 | Open Catalog | Snowflake から同期（Open Catalog では read-only） |
| **Externally managed Iceberg** | 外部エンジンが primary writer | Glue/外部 | Snowflake は External Iceberg Table として読み取り（read-only） |

参照: [Snowflake Open Catalog Sync](https://docs.snowflake.com/en/user-guide/tables-iceberg-open-catalog-sync)

### Snowflake Horizon Iceberg REST Catalog — 外部エンジンへのガバナンス適用（2026年5月確認）

> **自環境での確認（2026-05）**: Snowflake Horizon Catalog は外部エンジンアクセスに対してもガバナンスポリシーを強制する（Row Access Policy と Dynamic Data Masking をカタログレイヤーで評価）。

| 観点 | Snowflake Horizon Catalog | Databricks Unity Catalog |
|------|--------------------------|--------------------------|
| **外部エンジンへの Row Access Policy** | ✅ **強制** — vended credentials 発行前にポリシー評価 | ❌ 外部エンジンでは強制されない |
| **外部エンジンへの Dynamic Data Masking** | ✅ **強制** — カタログレイヤーでマスキング適用 | ❌ 外部エンジンでは強制されない |
| **外部エンジンへの RBAC** | ✅ **強制** — ロールベースアクセス制御を評価 | ✅ メタデータアクセスは制御 |
| **データアクセスモデル** | ポリシー評価によりスコープされた vended credentials | ポリシー強制なしの vended credentials |
| **エディション要件** | 全エディション（Standard, Enterprise, Business Critical） | 全エディション |
| **課金** | 100万APIコールあたり0.5クレジット（課金開始: 2026年下半期） | プラットフォーム費用に含む |
| **対応外部エンジン** | Apache Spark, Trino（Databricks UC 統合: 「未発表」） | Athena, EMR, Trino, Spark |

**Horizon Catalog の外部エンジン向けガバナンスの仕組み:**

```
外部エンジン（Spark/Trino）
  │
  │ 1. Horizon Iceberg REST Catalog API に認証
  │    （Snowflake ユーザー認証情報を使用）
  ▼
Snowflake Horizon Catalog
  │
  │ 2. RBAC + Row Access Policy + Masking Policy を評価
  │    （認証ユーザーのコンテキストに基づく）
  ▼
  │ 3. Iceberg メタデータ + スコープされた一時認証情報を返却
  │    （認証情報はポリシーで許可されたデータに限定）
  ▼
外部エンジンが S3 データファイルを直接読み取り
  （Snowflake はデータ転送パスに介在しない）
```

**規制ワークロードへのアーキテクチャ上の意味:**
- **Snowflake Horizon パス**: 単一のガバナンスレイヤーで内部 Snowflake クエリと外部エンジンアクセスの両方をカバー。追加の Lake Formation 設定不要。
- **Databricks UC パス**: 外部エンジンアクセスには別途 Lake Formation をガバナンスレイヤーとして設定する必要あり（UC ガバナンスは Databricks コンピュート内でのみ適用）。

**参照**: [Snowflake Horizon Iceberg REST Catalog — External Engine Access](https://docs.snowflake.com/en/user-guide/tables-iceberg-access-using-external-query-engine-snowflake-horizon)（Step 5: Configure data protection policies）

### 比較: AWS ネイティブ vs Snowflake vs Databricks ガバナンス

| 観点 | AWS ネイティブ（Lake Formation） | Snowflake（External Table） | Databricks（Unity Catalog、DataSync → S3 経由） |
|------|---|---|---|
| テーブル/カラム権限 | ✅ Lake Formation grants | ✅ Object Tags + Column Masking | ✅ UC Grants + Column Masks |
| 行レベルフィルタリング | ✅ Data Cells Filter | ✅ Row Access Policy | ✅ Row Filters |
| タグベースアクセス制御 | ✅ LF-Tags | ✅ Object Tags + タグベースマスキング | ✅ UC Tags + タグベースポリシー |
| 監査証跡 | ✅ CloudTrail + LF audit | ✅ Access History + クエリログ | ✅ System Tables（監査ログ） |
| クロスアカウント/組織共有 | ✅ LF クロスアカウント grants | ✅ Snowflake Data Sharing（よりシンプル） | ✅ Delta Sharing（オープンプロトコル） |
| AI ガバナンス | ✅ Bedrock ガードレール | ✅ Cortex AI 制御 + Cross-Region 設定 | ✅ Mosaic AI ガードレール + Model Registry |
| データリネージ | ❌ 組み込みなし | ❌ 組み込みなし | ✅ 自動（UC リネージグラフ） |
| セットアップ複雑度 | 中（LF admin + grants） | 低（Snowflake プラットフォーム組み込み） | 中（DataSync + UC セットアップ） |
| カバーするエンジン | Athena, Redshift, EMR, Glue | Snowflake のみ | Databricks（Spark, SQL, ML） |
| データ移動必要性 | なし（同一データ上のガバナンス） | ガバナンスにはなし; Cortex Search には COPY INTO | **あり — DataSync → S3 が必要**（UC は FSx for ONTAP S3 AP に直接アクセス不可） |
| FSx for ONTAP S3 AP 直接アクセス | ✅ | ✅（`AWS_ACCESS_POINT_ARN` 使用） | ❌（UC テーブル作成ブロック; DataSync パスが必要） |
| 外部エンジンでのガバナンス適用 | ✅（Athena, Redshift, EMR 全てガバナンス適用） | ✅ **Horizon Catalog が外部エンジンに Row Access Policy + Masking を強制**（2026年5月確認） | ❌ **UC Row Filters/Column Masks は外部エンジンで適用されない**（Athena/EMR が Iceberg REST Catalog 経由でアクセスすると UC ガバナンスをバイパス） |

### Databricks Unity Catalog ガバナンス（DataSync → S3 経由）

Databricks Unity Catalog は **DataSync で S3 に同期した後**、FSx for ONTAP データに対してエンタープライズガバナンスを提供します。UC は FSx for ONTAP S3 AP に直接アクセスできません（セッションポリシー制限、2026年5月確認）が、DataSync → S3 → UC パスで全ガバナンス機能が利用可能です:

| 機能 | 動作 | ガバナンス価値 |
|------|------|-------------|
| **テーブル/カラム Grants** | `GRANT SELECT ON TABLE ... TO group` | プリンシパルごとの細粒度アクセス制御 |
| **Row Filters** | `ALTER TABLE ... SET ROW FILTER function` | ユーザーコンテキストに基づく行レベルセキュリティ |
| **Column Masks** | `ALTER TABLE ... ALTER COLUMN ... SET MASK function` | ロールごとの動的カラムマスキング |
| **UC Tags** | `ALTER TABLE ... SET TAGS ('sensitivity' = 'pii')` | データ分類と発見性 |
| **自動リネージ** | 組み込みリネージグラフ（テーブル→テーブル、カラム→カラム） | 影響分析、コンプライアンストレーシング |
| **監査ログ** | `system.access.audit` システムテーブル | 誰が何にいつどこからアクセスしたか |
| **Delta Sharing** | オープンプロトコル — Delta Sharing 互換クライアントと共有 | データコピーなしのクロス組織共有（Snowflake, Pandas, Spark が読み取り可能） |
| **Mosaic AI ガバナンス** | Model Registry, Feature Store, AI ガードレール | ML モデルライフサイクルガバナンス |
| **Lakehouse Monitoring** | データ品質メトリクス、ドリフト検出 | プロアクティブなデータ品質ガバナンス |

**重要な制約**: 全ての Databricks UC ガバナンスはデータが S3 にある必要があります（FSx for ONTAP S3 AP 直接ではない）。推奨アーキテクチャ:

```
FSx for ONTAP (Source of Truth)
  ↓ DataSync（増分同期、5分スケジュール）
Amazon S3 バケット（同期コピー）
  ↓ Auto Loader（増分取り込み）
Unity Catalog Managed Table（フルガバナンス）
  ↓
  ├── Row Filters + Column Masks（細粒度アクセス）
  ├── 自動リネージ（影響分析）
  ├── Mosaic AI（ML トレーニング、Feature Store）
  └── Delta Sharing（クロス組織配布）
```

#### UC Iceberg REST Catalog — 外部エンジンアクセスの制約

> **自環境での確認（2026-05）**: 外部エンジン（Athena、EMR Spark、Trino）が Iceberg REST Catalog 経由で UC 管理テーブルにアクセスする場合:

| 観点 | 動作 | 影響 |
|------|------|------|
| **データアクセス** | 外部エンジンは S3 データファイルに**直接アクセス** — UC はデータをプロキシしない | 外部エンジンの IAM ロールに基盤データファイルへの S3 読み取り権限が必要 |
| **Row Filters** | ❌ 外部エンジンでは**適用されない** | 行レベルセキュリティは Databricks コンピュート（Spark/Photon）内でのみ適用 |
| **Column Masks** | ❌ 外部エンジンでは**適用されない** | カラムマスキングは Databricks コンピュート内でのみ適用 |
| **UC Grants** | メタデータアクセスは UC が制御 | 外部エンジンはテーブルを発見できるが、データレイヤーでガバナンスは適用されない |

**アーキテクチャへの影響**: UC 管理データに外部エンジン（Athena、EMR）からアクセスする際にガバナンスを適用する必要がある場合、同じ S3 データに対して **Lake Formation を追加で設定する必要がある**。UC ガバナンスと Lake Formation ガバナンスは独立して動作 — UC は Databricks アクセスを、Lake Formation は AWS ネイティブエンジンアクセスをガバナンスする。

```
UC 管理 Delta/Iceberg テーブル（S3 上）
  ├── Databricks アクセス → UC Row Filters + Column Masks（適用される）
  └── Athena/EMR アクセス（Iceberg REST Catalog 経由）→ UC ガバナンス適用されない
       └── 外部エンジンアクセスのガバナンスには Lake Formation を使用する必要あり
```

> **規制ワークロード向け**: UC ガバナンスが非 Databricks エンジンからのアクセス時にデータを自動的に保護すると想定しないこと。コンプライアンスが Athena や EMR クエリに行/カラムレベルのアクセス制御を要求する場合、UC とは独立して同じ基盤 S3 データに Lake Formation 権限を設定すること。

> **トレードオフ**: Databricks は最も豊富なガバナンス機能セット（特に自動リネージと ML ガバナンス）を提供しますが、DataSync によるデータ重複が必要です。Snowflake と Lake Formation はコピーなしで FSx for ONTAP S3 AP データをガバナンスできます。リネージ/ML ガバナンスとゼロコピーアクセスのどちらが優先かで選択してください。

> **規制ワークロード向け推奨**: 複数の AWS ネイティブエンジン（Athena + Redshift + EMR）にガバナンスを適用する場合は **Lake Formation** を使用。主要プラットフォームが Snowflake で、データ移動なしに AI + ガバナンス + データ共有を統合する場合は **Snowflake ガバナンス** を使用。自動リネージ、ML ガバナンス（Mosaic AI, Feature Store）、または Delta Sharing（オープンプロトコル）が必要な場合は **Databricks UC** を使用 — DataSync 同期レイテンシとストレージ重複をトレードオフとして受け入れる。3つすべてが同じ FSx for ONTAP ソースデータ上で共存可能です。

### AI/RAG のデータ取り扱い

| 懸念事項 | ガバナンス制御 |
|---------|--------------|
| **ソースドキュメント内の PHI/PII** | インデックス作成前に匿名化パイプライン。生の PHI/PII を決してインデックスしない |
| **エンベディング保存場所** | Bedrock Knowledge Bases は顧客管理のベクトルストア（OpenSearch Serverless）にエンベディングを保存。同一リージョン、同一アカウントを確保 |
| **ベクトルストア暗号化** | OpenSearch Serverless はデフォルトで保存時暗号化（AWS KMS） |
| **エンベディング削除** | ソースドキュメント削除時、Knowledge Base を再同期して対応するエンベディングを削除 |
| **プロンプト/レスポンスログ** | Bedrock モデル呼び出しの CloudWatch Logs を有効化。コンプライアンス要件に従い保持 |
| **人間レビュー要件** | 医療/金融における RAG レスポンスはアクション前に人間レビュー必須 |
| **ハルシネーション軽減** | Bedrock ガードレールを設定。レスポンスにソース引用を含める。ソースドキュメントに対して検証 |
| **テスト用合成データ** | 開発/テストには合成ドキュメントを使用。非本番環境に実際の PHI/PII を使用しない |
| **モデルアクセスポリシー** | 呼び出し可能な Bedrock モデルを制限。`bedrock:InvokeModel` に IAM ポリシーを使用 |

### 規制産業向け RAG アーキテクチャ

```
┌─────────────────────────────────────────────────────────────┐
│  Regulated RAG Architecture                                  │
│                                                              │
│  ┌──────────────┐     ┌─────────────────┐                  │
│  │ Source Docs   │     │ De-identification│                  │
│  │ (FSx for ONTAP Volume)  │────▶│ Pipeline (Glue)  │                  │
│  │ NFS/SMB write │     │ Remove PHI/PII   │                  │
│  └──────────────┘     └────────┬────────┘                  │
│                                │                             │
│                       ┌────────▼────────┐                   │
│                       │ Clean Documents  │                   │
│                       │ (FSx for ONTAP Volume)     │                   │
│                       └────────┬────────┘                   │
│                                │                             │
│                       ┌────────▼────────┐                   │
│                       │ S3 Access Point  │                   │
│                       │ (read-only user) │                   │
│                       └────────┬────────┘                   │
│                                │                             │
│                       ┌────────▼────────┐                   │
│                       │ Bedrock KB       │                   │
│                       │ (ingestion)      │                   │
│                       └────────┬────────┘                   │
│                                │                             │
│                       ┌────────▼────────┐                   │
│                       │ Vector Store     │                   │
│                       │ (OpenSearch)     │                   │
│                       └────────┬────────┘                   │
│                                │                             │
│  ┌──────────────┐     ┌───────▼─────────┐                  │
│  │ User Query    │────▶│ Bedrock Agent    │                  │
│  │ (with guardrails)   │ + Guardrails     │                  │
│  └──────────────┘     └───────┬─────────┘                  │
│                                │                             │
│                       ┌────────▼────────┐                   │
│                       │ Human Review     │                   │
│                       │ (required)       │                   │
│                       └─────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

---

## データライフサイクル管理

### 保持ポリシーフレームワーク

| データタイプ | 保持期間 | ストレージ階層 | 削除方法 |
|------------|---------|-------------|---------|
| アクティブ分析データ | 無期限（使用中） | FSx for ONTAP SSD | 手動レビュー + 承認 |
| 過去の分析データ | ビジネス要件に従う | FSx for ONTAP Capacity Pool（FabricPool） | 自動階層化、手動削除 |
| 監査ログ（CloudTrail） | 7 年（SOX）/ 6 年（HIPAA） | S3（CloudTrail 送信先） | S3 ライフサイクルポリシー |
| ONTAP スナップショット | スナップショットポリシーに従う（例：日次 7、週次 4） | FSx for ONTAP SSD（copy-on-write） | ポリシーに従い自動 |
| RAG エンベディング | ソースドキュメントの保持期間と同じ | OpenSearch Serverless | ソース削除後に Knowledge Base を再同期 |
| クエリ結果（Athena） | 90 日（デフォルト）またはポリシーに従う | S3（Athena 結果バケット） | S3 ライフサイクルポリシー |

### データ削除手順

1. **特定**: 削除すべきファイル/レコードを特定（データオーナーの承認が必要）
2. **依存関係の確認**: データが Glue Catalog、Bedrock KB、その他のサービスから参照されているか確認
3. **ソースから削除**: NFS/SMB または S3 AP（DeleteObject）経由で削除
4. **カタログ更新**: Glue Crawler を再実行、またはテーブル/パーティションを手動ドロップ
5. **AI 再同期**: Bedrock KB で使用されている場合、再同期をトリガーしてエンベディングを削除
6. **削除確認**: ListObjectsV2 とカタログクエリで確認
7. **監査**: CloudTrail が削除イベントを自動記録

---

## インシデント対応

### インシデント対応フロー

```
Detection → Triage → Containment → Investigation → Recovery → Post-mortem
    │          │          │              │             │           │
    ▼          ▼          ▼              ▼             ▼           ▼
CloudTrail  Severity   Revoke AP     CloudTrail    Snapshot    Document
Alert       Assessment policy/IAM    log analysis  restore     & improve
```

### インシデントシナリオと対応

| シナリオ | 検知 | 封じ込め | 復旧 |
|---------|------|---------|------|
| 不正データアクセス | 予期しないプリンシパルに対する CloudTrail アラート | AP ポリシーを更新して拒否。IAM 認証情報を失効 | アクセスログをレビュー。データ露出を評価 |
| AP ポリシー設定ミス | CloudTrail `PutAccessPointPolicy` イベント | 既知の正常なポリシーに戻す（IaC） | 認可ユーザーのアクセス復旧を確認 |
| データ破損（偶発的） | アプリケーションエラーレポート。データ検証失敗 | 影響を受けたボリュームを隔離（必要に応じて） | ONTAP スナップショットから復元 |
| ランサムウェア | 異常な書き込みパターン。ファイル拡張子の変更 | NFS/SMB クライアントを切断。AP は読み取り専用のまま（設定済みの場合） | イミュータブルスナップショットから復元 |
| リージョン障害 | AWS Health Dashboard。接続喪失 | DR ランブックを起動 | SnapMirror フェイルオーバー。DR リージョンに新しい AP を作成 |

### スナップショット復元承認フロー

規制環境では、スナップショット復元は承認プロセスに従う必要があります：

1. **リクエスト**: オペレーターが復元の必要性を特定（正当な理由付き）
2. **承認**: データオーナーまたはコンプライアンス担当者が承認（文書化）
3. **通知**: 全ステークホルダーに通知（分析チーム、アプリケーションオーナー）
4. **実行**: スナップショット復元を実行
5. **整合性確認**: Glue Crawler を再実行。カタログの整合性を確認
6. **検証**: サンプルクエリでデータ整合性を確認
7. **文書化**: 復元イベント、理由、承認者、結果を記録

### DR フェイルオーバーガバナンスチェックリスト

- [ ] SnapMirror 関係が正常であることを確認（ラグが RPO 内）
- [ ] DR リージョン AP 作成手順が文書化・テスト済み
- [ ] IAM ロール/ポリシーが DR リージョンにレプリケート済み
- [ ] Glue Catalog 再作成手順が文書化済み
- [ ] アプリケーション設定更新手順が文書化済み
- [ ] ステークホルダー向けコミュニケーション計画が起動済み
- [ ] フェイルオーバー後の検証クエリが定義済み
- [ ] フェイルバック手順が文書化済み

---

## ステークホルダー説明ガイド

ステークホルダーによって関心事は異なります。役割に合わせて説明を調整してください。

| ステークホルダー | 主な関心事 | 主要な説明 | エビデンス成果物 | 判断基準 |
|---------------|-----------|-----------|---------------|---------|
| **病院 CIO** | ビジネス価値、コスト、タイムライン | 「移行なしで既存ファイルデータを分析。分析セットアップを数週間から数時間に短縮」 | コスト比較、タイムライン、アーキテクチャ概要 | ROI、実装リスク、ベンダーロックイン |
| **CISO / セキュリティチーム** | データ保護、アクセス制御、攻撃対象面 | 「二層認可、Block Public Access 強制、VPC 分離オプション、全アクセス監査済み」 | セキュリティアーキテクチャ図、ペネトレーションテスト結果、CloudTrail サンプル | 脅威モデルカバレッジ、コンプライアンス整合性 |
| **DPO** | プライバシー、データ所在地、削除権 | 「データはリージョン内に留まる、単一ソース（コピーなし）、削除手順文書化、監査証跡」 | データフロー図、保持ポリシー、削除手順 | GDPR/HIPAA 整合性、データ主体の権利 |
| **臨床研究リード** | データアクセス速度、研究促進 | 「SQL で数分で研究データをクエリ。ドキュメントの AI 検索」 | デモ、クエリレイテンシベンチマーク | インサイトまでの時間、データ鮮度 |
| **法務 / コンプライアンス** | 規制遵守、責任、契約 | 「AWS との BAA、保存時/転送中暗号化、監査保持 7 年以上、責任マトリクス」 | RACI、BAA 確認、コンプライアンスマッピング | 規制ギャップ分析 |
| **監査チーム** | エビデンス、追跡可能性、完全性 | 「全データアクセスが CloudTrail にプリンシパル、タイムスタンプ、アクション、リソースとともに記録」 | 監査ログサンプル、レポート生成手順 | 監査証跡の完全性、保持 |
| **公共セクター調達** | 認証、主権、ベンダー評価 | 「AWS リージョンデータ所在地、FedRAMP/ISO 認証、データはリージョン外に出ない」 | AWS コンプライアンス認証、データ所在地保証 | 調達チェックリスト準拠 |
| **患者コミュニケーション** | 信頼、透明性、管理 | 「あなたのデータは複数のセキュリティレイヤーで保護されています。認可された研究者のみが匿名化データにアクセスできます」 | 平易な言葉のプライバシー通知 | 患者の信頼、オプトアウトメカニズム |

---

## 保証成果物パック

規制産業デプロイメント承認のための完全な成果物セット。

| # | 成果物 | 目的 | 対象者 | 形式 |
|---|--------|------|--------|------|
| 1 | 非技術者向けアーキテクチャ概要 | システムを平易な言葉で説明 | CxO、取締役会、患者 | 図付き 1 ページ PDF |
| 2 | データフロー図 | データの所在と移動を示す | DPO、セキュリティ、監査 | Visio/draw.io 図 |
| 3 | アクセス制御説明 | 誰が何にアクセスでき、なぜかを説明 | CISO、コンプライアンス | 2 ページ文書 |
| 4 | RACI マトリクス（署名済み） | 責任を割り当て | 全ステークホルダー | 署名済み文書 |
| 5 | 監査ログサンプルレポート | 監視能力を実証 | 監査、コンプライアンス | 墨消し済み CloudTrail レポート |
| 6 | インシデント対応手順 | セキュリティイベントへの対応を定義 | セキュリティ、運用 | ランブック文書 |
| 7 | データライフサイクルポリシー | 保持、削除、アーカイブを定義 | DPO、法務 | ポリシー文書 |
| 8 | RAG ガバナンスチェックリスト | AI 固有の制御 | CISO、研究リード | チェックリスト |
| 9 | 残留リスク台帳 | 受容されたリスクを文書化 | CxO、CISO | リスク台帳 |
| 10 | コンプライアンスマッピング | 制御を規制にマッピング | コンプライアンス、監査 | マトリクス（HIPAA/PCI/SOX） |

### 成果物作成タイムライン

| 週 | 作成する成果物 | 必要なインプット元 |
|----|-------------|----------------|
| 1 | #1 アーキテクチャ、#2 データフロー | 技術チーム |
| 2 | #3 アクセス制御、#4 RACI ドラフト | セキュリティ + データオーナー |
| 3 | #5 監査サンプル、#6 インシデント対応 | 運用 + セキュリティ |
| 4 | #7 ライフサイクル、#8 RAG ガバナンス | DPO + 研究リード |
| 5 | #9 リスク台帳、#10 コンプライアンスマッピング | CISO + 法務 |
| 6 | レビューと承認 | 全ステークホルダー |

---

## 医療データの二次利用

医療データが主たる臨床目的を超えて使用される場合（例：研究、AI トレーニング、集団健康分析）、追加のガバナンスが適用されます。

### 一次利用 vs. 二次利用

| 観点 | 一次利用 | 二次利用 |
|------|---------|---------|
| 目的 | 直接的な患者ケア | 研究、分析、AI、品質改善 |
| データ形式 | 識別可能（PHI） | 匿名化または非識別化 |
| 同意 | 治療同意 | 研究同意またはウェイバー（IRB/倫理委員会） |
| アクセス | 臨床スタッフ | 研究者、データサイエンティスト、AI システム |
| 保存 | 臨床システム（EHR） | 研究データプラットフォーム（FSx for ONTAP + 分析） |
| ガバナンス | 臨床データガバナンス | 研究データガバナンス + 倫理 |

### 二次利用ガバナンスフレームワーク

| 制御 | 実装 |
|------|------|
| **同意 / 承認** | 研究利用に対する IRB/倫理委員会の承認。同意根拠を文書化 |
| **匿名化** | 分析アクセス前に HIPAA Safe Harbor または Expert Determination 方式を適用 |
| **再識別リスク** | k-匿名性を評価。リンケージ変数を制限。再識別試行を監視 |
| **データセットアクセス承認** | データガバナンス委員会によるプロジェクト単位の承認。期限付きアクセス |
| **研究ワークスペース分離** | 研究用に別の VPC/アカウント。承認なしのデータエクスポート禁止 |
| **エクスポート制御** | 結果のみ（集計済み）。レビューなしの個人レベルデータエクスポート禁止 |
| **出版レビュー** | データを使用する全出版物は再識別リスクのレビューが必要 |
| **監査証跡** | 全研究データアクセスをログ。定期的なアクセスレビュー |

### FSx for ONTAP S3 AP 向け匿名化パイプライン

```
Clinical Volume (PHI)          Research Volume (De-identified)
      │                                    │
      ▼                                    ▼
┌──────────────┐              ┌─────────────────────┐
│ NFS/SMB      │              │ S3 Access Point     │
│ (clinical    │              │ (read-only,         │
│  staff only) │              │  research team)     │
└──────┬───────┘              └──────────┬──────────┘
       │                                  │
       ▼                                  ▼
┌──────────────────────────────────────────────────┐
│         FSx for ONTAP (separate volumes)          │
│  Vol1: /clinical (PHI)  │  Vol2: /research (safe) │
└─────────────┬────────────┴───────────────────────┘
              │
     ┌────────▼────────┐
     │ Glue ETL        │
     │ De-identification│
     │ Pipeline         │
     │ (scheduled)      │
     └─────────────────┘
```

**重要な原則**: PHI ボリュームには S3 Access Point を設定しません。匿名化された研究ボリュームのみが S3 AP 経由で公開されます。

---

## RAG の人間レビューワークフロー

規制産業で RAG を使用する場合、AI 生成レスポンスはアクション前に人間レビューが必要です。

### ワークフローステップ

```
┌─────────┐    ┌──────────┐    ┌──────────────┐    ┌──────────┐
│ 1. User │───▶│ 2. RAG   │───▶│ 3. Response  │───▶│ 4. Human │
│ submits │    │ retrieves│    │ generated    │    │ reviewer │
│ query   │    │ + answers│    │ with citations│    │ evaluates│
└─────────┘    └──────────┘    └──────────────┘    └────┬─────┘
                                                        │
                                          ┌─────────────┼─────────────┐
                                          ▼             ▼             ▼
                                    ┌──────────┐ ┌──────────┐ ┌──────────┐
                                    │ APPROVE  │ │ EDIT     │ │ REJECT   │
                                    │ (as-is)  │ │ (modify) │ │ (discard)│
                                    └────┬─────┘ └────┬─────┘ └────┬─────┘
                                         │            │             │
                                         ▼            ▼             ▼
                                    ┌──────────────────────────────────┐
                                    │ 5. Decision logged               │
                                    │    (who, when, action, reason)   │
                                    └──────────────┬───────────────────┘
                                                   │
                                         ┌─────────▼─────────┐
                                         │ 6. Response        │
                                         │    delivered to user│
                                         └─────────┬─────────┘
                                                   │
                                         ┌─────────▼─────────┐
                                         │ 7. Feedback loop   │
                                         │    (accuracy       │
                                         │     tracking)      │
                                         └───────────────────┘
```

### レビュー基準

| 基準 | チェック内容 | 不合格時のアクション |
|------|------------|-------------------|
| ソース正確性 | 引用が回答と一致するか？ | REJECT または EDIT |
| 完全性 | 回答が質問全体に対応しているか？ | EDIT で不足情報を追加 |
| ハルシネーション | 回答にソースにない主張が含まれるか？ | REJECT |
| PHI 漏洩 | 回答に患者識別可能な情報が含まれるか？ | REJECT + エスカレーション |
| 臨床安全性 | 回答に基づいて行動した場合、患者に害を及ぼす可能性があるか？ | REJECT + エスカレーション |
| 規制コンプライアンス | 回答が適用される規制に準拠しているか？ | REJECT + 法務レビュー |

### レビュー SLA

| 優先度 | レビュー時間 | エスカレーション |
|--------|------------|---------------|
| 通常の研究クエリ | 4 時間以内 | 8 時間後に自動エスカレーション |
| 臨床意思決定支援 | 1 時間以内 | 未レビューの場合即時エスカレーション |
| コンプライアンス/監査クエリ | 2 時間以内 | コンプライアンス担当者にエスカレーション |

---

## ガバナンス承認ワークフロー

規制産業デプロイメントの逐次承認プロセス。

| ステップ | 承認者 | 必要な成果物 | 判断基準 | 可能な結果 |
|---------|--------|------------|---------|-----------|
| 1. 技術レビュー | プラットフォームアーキテクト | アーキテクチャ図、互換性マトリクス | 技術的に健全、非サポートパターンなし | 承認 / 変更要求 |
| 2. セキュリティレビュー | CISO / セキュリティチーム | セキュリティアーキテクチャ、ネガティブテスト結果、AP ポリシー | 全セキュリティ検証基準を満たす | 承認 / 条件付き（緩和策付き）/ 却下 |
| 3. データオーナーレビュー | データガバナンス委員会 | データ分類、アクセススコープ、保持ポリシー | データが適切に使用され、アクセスが最小化 | 承認 / スコープ制限 / 却下 |
| 4. 法務 / コンプライアンス | 法務顧問 | コンプライアンスマッピング、BAA、データ所在地 | 規制要件を満たす | 承認 / 追加制御要求 / 却下 |
| 5. 臨床 / ビジネスオーナー | 部門長 | ビジネスケース、KPI 目標、ユーザー影響 | ビジネス価値が正当化され、リスクが許容可能 | 承認 / 延期 / 却下 |
| 6. エグゼクティブ承認 | CIO / CISO | 残留リスク台帳、コスト承認、RACI | 組織的リスクが許容可能 | 承認 / 却下 |
| 7. 本番稼働承認 | 運用リード | ランブックテスト済み、監視設定済み、DR 検証済み | 運用準備完了 | 承認 / 延期 |

### 承認エビデンスの保持

全承認決定は文書化し保持する必要があります：
- 承認者の氏名と役割
- 決定日
- 決定内容（承認 / 条件付き / 却下）
- 条件（条件付きの場合）
- レビューしたエビデンス
- 保持期間：監査ログ保持期間と同じ（規制対象は 7 年以上）

---

## 残留リスク台帳テンプレート

| リスク ID | 説明 | 影響度 (1-5) | 発生可能性 (1-5) | リスクスコア | 既存の制御 | 残留レベル | オーナー | 対処 | リスク受容権限 | レビュー頻度 |
|----------|------|:---:|:---:|:---:|-----------|:---:|--------|------|------------|:---:|
| R-001 | FSx for ONTAP S3 AP はアトミックリネームをサポートしない。Delta 書き込みが破損する可能性 | 5 | 1 | 5 | アンチパターンを文書化。読み取り専用 AP を強制 | Low | プラットフォームチーム | 回避（Delta 書き込みを使用しない） | CISO | 四半期 |
| R-002 | 数十 ms のレイテンシがリアルタイム分析 SLA を満たさない可能性 | 3 | 3 | 9 | 本番前にベンチマーク。SLA を文書化 | Medium | プラットフォームチーム | 緩和（より高いスループットをプロビジョニング） | ビジネスオーナー | 四半期 |
| R-003 | AP ポリシー設定ミスが全アクセスをブロックする可能性 | 4 | 2 | 8 | IaC 管理ポリシー。SCP が変更を制限。ランブック | Low | セキュリティチーム | 緩和（SCP + IaC + ランブック） | CISO | 月次 |
| R-004 | スナップショット復元が Glue Catalog の不整合を引き起こす可能性 | 3 | 2 | 6 | カタログ修復のランブック。Crawler 再実行 | Low | データプラットフォーム | 緩和（ランブック + 自動化） | プラットフォームリード | 四半期 |
| R-005 | 臨床コンテキストでの RAG ハルシネーション | 5 | 3 | 15 | 人間レビュー必須。Bedrock ガードレール。引用チェック | Medium | AI チーム | 緩和（human-in-loop 必須） | 臨床リード | 月次 |

### リスクスコアリングガイド

- **影響度**: 1=無視可能、2=軽微、3=中程度、4=重大、5=致命的
- **発生可能性**: 1=まれ、2=起こりにくい、3=起こりうる、4=起こりやすい、5=ほぼ確実
- **リスクスコア**: 影響度 × 発生可能性
- **残留レベル**: Low (1-6)、Medium (7-12)、High (13-19)、Critical (20-25)

---

## 平易な言葉での説明例

非技術者ステークホルダー（患者、市民、取締役会メンバー）向け。

| 質問 | 平易な言葉での回答 |
|------|------------------|
| **私のデータはどこに保存されていますか？** | 「あなたのデータは [リージョン] の AWS データセンター内のセキュアなファイルシステムに保存されています。分析のために別の場所に移動またはコピーされることはありません。」 |
| **誰が私のデータにアクセスできますか？** | 「特定の職務を持つ認可されたスタッフのみがデータにアクセスできます。全アクセスには 2 つの別々の権限チェックが必要です — 1 つは AWS セキュリティから、もう 1 つはファイルシステム自体からです。」 |
| **インターネット上の誰かが私のデータを見ることができますか？** | 「いいえ。パブリックアクセスはデフォルトでブロックされており、オンにすることはできません。認可されたユーザーでさえ、アクセスのたびに身元を証明する必要があります。」 |
| **AI は何を見ますか？** | 「AI は匿名化されたドキュメントのみを見ます — AI がアクセスする前に全ての個人情報が削除されます。」 |
| **人間が AI の回答をチェックしますか？** | 「はい。全ての AI 生成回答は、いかなる決定に使用される前に資格のある人物によってレビューされます。」 |
| **AI が間違った回答をした場合は？** | 「間違った回答はフラグ付け、ログ記録、破棄されます。システムはこれらのエラーから学習し、時間とともに改善されます。」 |
| **データの削除を依頼できますか？** | 「はい。文書化された削除プロセスがあります。データが削除されると、ファイルシステム、検索インデックス、AI のナレッジベースから削除されます。」 |
| **誰かが不正にデータにアクセスしていないことをどう確認しますか？** | 「全てのデータアクセスは、誰が、いつ、何をしたかとともに自動的にログ記録されます。これらのログは [7 年以上] 保持され、定期的にレビューされます。」 |

---

## RAG 用途リスク分類

医療/規制コンテキストでは、RAG のユースケースによってリスクレベルが異なります。

| 分類 | リスクレベル | 例 | 許可されるデータ | 必要なレビュー | 禁止される用途 | 承認レベル |
|------|:---:|------|-------------|-------------|-------------|-----------|
| **管理** | Low | 会議スケジューリング、施設情報、HR ポリシー検索 | Public + Internal | オプション（スポットチェック） | 臨床データなし | チームリード |
| **研究支援** | Medium | 文献検索、プロトコル検索、方法論ガイダンス | 匿名化研究データ | 必須（研究者） | 識別可能な患者データなし | 研究リード + IRB |
| **臨床文書** | Medium-High | 退院サマリー作成、コーディング支援 | 匿名化臨床ノート | 必須（臨床医） | 自律的文書作成なし | 臨床ディレクター |
| **臨床意思決定支援** | High | 鑑別診断支援、治療オプション検索 | 匿名化 + エビデンスベースのソースのみ | 必須（医師） | 自律的意思決定なし | メディカルディレクター + CISO |
| **患者向け** | Highest | 患者ポータル Q&A、予約ガイダンス | 公衆衛生情報のみ | 必須（臨床 + 法務） | 臨床アドバイスなし、PHI なし | エグゼクティブ + 法務 + 臨床 |

### リスクベースの制御

| リスクレベル | ログ | 人間レビュー | ガードレール | 監査頻度 |
|:---:|---------|:---:|-----------|:---:|
| Low | 標準 | オプション | 基本（トピックフィルタリング） | 四半期 |
| Medium | 強化 | 必須 | 中程度（引用必須） | 月次 |
| Medium-High | 完全（プロンプト + レスポンス） | 必須 | 厳格（ハルシネーション検出） | 隔週 |
| High | 完全 + 臨床コンテキスト | 必須（医師） | 最大（Bedrock ガードレール + カスタム） | 週次 |
| Highest | 完全 + リーガルホールド | 必須（複数者） | 最大 + 法務レビュー | 継続的 |

---

## 参考資料

- [Managing access point access — Dual-layer authorization](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)
- [Configuring network access for Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/configuring-network-access-for-s3-access-points.html)
- [Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
- [Monitoring FSx for ONTAP API Calls with AWS CloudTrail](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/logging-using-cloudtrail-win.html)
- [Access points naming rules, restrictions, and limitations](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-point-for-fsxn-restrictions-limitations-naming-rules.html)
- [Build a RAG application using Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)
