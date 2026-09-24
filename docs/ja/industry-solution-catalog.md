🌐 [English](../en/industry-solution-catalog.md) | **日本語**

> 📖 **技術ガイドとセット**: 本カタログは [FSx for ONTAP → Databricks UC 接続総合ガイド](./fsx-ontap-to-databricks-unity-catalog-guide.md)（接続パスの技術詳細）と対になる**業界別ソリューションカタログ**です。技術ガイドが「どう繋ぐか（How）」を扱うのに対し、本カタログは「どの業界で、何のために、どのパスを使うか（Who / Why / Which）」を扱います。

# FSx for ONTAP × Databricks Unity Catalog 業界別ソリューションカタログ

> **ステータス**: 初版（2026-06-19）。公開リファレンスアーキテクチャと本リポジトリの検証結果を統合。
> **対象読者**: AWS SA、パートナー SI/ISV、業界ソリューションアーキテクト、利用組織のデータ責任者。
> **Evidence tier**: 各主張に明記（**Public** = 公開情報で検証可能 / **Project-context** = 本リポジトリ内で再現可能 / **Archetype** = 業界標準ロールに基づく一般論）。
> **フレーミング**: vendor-versus ではなく right-tool-for-the-job。各選択肢のトレードオフを対称に記載。

---

## エグゼクティブサマリー

- **目的**: FSx for ONTAP に蓄積されたエンタープライズファイルデータ（NFS/SMB/S3/iSCSI）を、業界ごとのユースケースに応じて Databricks Unity Catalog ガバナンス下の分析・AI 基盤に接続する際の、業界別の推奨パターンを提供
- **共通原則**: UC への直接ゼロコピー接続は非対応（技術ガイド参照）。本番パスは「DataSync → S3 → UC」「Kafka → Structured Streaming → UC」「Glue/EMR ETL → UC」の間接パス
- **FSx for ONTAP の業界共通機能**: マルチプロトコル（同一データへ NFS/SMB/S3 同時アクセス）、Snapshot/FlexClone（一貫性のある時点コピー・瞬時クローン）、SnapMirror（DR）、SnapLock（WORM コンプライアンス）、ストレージ効率（重複排除/圧縮）
- **規制業界の注意点**: 金融（BCBS 239 等）、医療（HIPAA/GxP）、公共（データ主権）では、データ分類・監査ログ・暗号化チェーン・データ越境制約を設計の前提に含める
- **本カタログの使い方**: 自業界のセクションで「ユースケース → 推奨パス → ガバナンス → 注意点」を確認し、技術ガイドの該当パス詳細にリンクで遷移
- **カバレッジ**: 26 業界を収録（製造・自動車・金融・医療・半導体・メディア・小売・エネルギー・通信・公共に加え、農業・物流・観光・法務・建設・教育・防衛・スマートシティ・広告・運輸・ESG・不動産・HR・化学・ゲーミング・SAP/ERP）。サーバーレス自動化パターンの実装例は [FSx for ONTAP S3 Access Points Serverless Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)（同一著者）の業界別ユースケース（UC1-UC30）を参照

## 業界横断クイックリファレンス

| 業界 | 代表ユースケース | 活用する FSx for ONTAP 機能 | 推奨接続パス | 主要規制/制約 |
|------|----------------|-------------------|------------|-------------|
| 製造 / 産業 | 品質分析、予知保全、トレーサビリティ | マルチプロトコル、Snapshot、FabricPool | DataSync / Kafka(FPolicy) | IATF 16949、OT/IT 分離 |
| 自動車 | ADAS/AD データ、コネクテッドカー、部品系譜 | スケールアウト性能、SnapMirror、SnapLock | DataSync / Kafka | データ主権、ISO 26262、保持義務 |
| 金融 / 保険 | リスク分析、不正検知、規制報告 | SnapLock(WORM)、Snapshot、暗号化 | DataSync / Glue ETL | BCBS 239、データレジデンシー、監査 |
| 医療 / ライフサイエンス | EHR 分析、ゲノミクス、医療画像、創薬 | マルチプロトコル、FlexClone、SnapLock | DataSync / Glue ETL | HIPAA/ePHI、GxP、HDS、FHIR |
| 半導体 / EDA | チップ設計、検証、テープアウト分析 | FlexCache、スケールアウト(36GB/s)、Snapshot | Glue/EMR / DataSync | IP 保護、輸出管理(EAR) |
| メディア / エンタメ | VFX レンダリング、アセット管理、配信分析 | スケールアウト性能、FlexClone、マルチプロトコル | DataSync / Glue ETL | コンテンツ権利、DRM |
| 小売 / 消費財 | 需要予測、パーソナライゼーション、在庫最適化 | ストレージ効率、Snapshot | DataSync / Kafka | PCI DSS、PII 保護 |
| エネルギー / 公益 | グリッドテレメトリ、予知保全、資産管理 | マルチプロトコル、SnapMirror | Kafka / DataSync | NERC CIP、OT/IT 分離 |
| 通信 | ネットワークテレメトリ、CDR 分析、不正検知 | スケールアウト性能、Snapshot | Kafka / DataSync | データ保持義務、PII |
| 公共 / 政府 | 市民データ分析、防衛、研究 | SnapLock、SnapMirror、暗号化 | DataSync / Glue ETL | データ主権、FedRAMP、ITAR/EAR |
| 農業 / 食品 🌱 | 精密農業、作物健全性、食品トレーサビリティ | マルチプロトコル、ストレージ効率、SnapMirror | Kafka(エッジ) / Glue ETL | HACCP、食品トレーサビリティ法 |
| 物流 / SCM 📦 | 倉庫 CV、配送 OCR、コールドチェーン | スケールアウト性能、マルチプロトコル | Kafka(エッジ) / DataSync | GDP、危険物輸送、通関 |
| 観光 / ホスピタリティ 🏨 | ゲスト体験、施設点検、混雑分析 | マルチプロトコル、ストレージ効率 | DataSync / Kafka(エッジ) | ゲスト PII、PCI DSS、映像プライバシー |
| 法務 / コンプラ | 契約分析、ACL 監査、e-Discovery | ONTAP REST API、SnapLock | DataSync / Glue ETL | 秘匿特権、保持義務 |
| 建設 / AEC | BIM、図面 OCR、安全点検 | スケールアウト性能、FlexClone | DataSync / Glue ETL | 建築安全規制、長期保存 |
| 教育 / 研究 | 論文分類、研究データ、学習分析 | マルチプロトコル、FlexClone | DataSync / Glue ETL | FERPA、研究倫理 |
| 防衛 / 宇宙 | 衛星画像、地理空間インテリジェンス | スケールアウト性能、SnapLock、暗号化 | Glue ETL | ITAR/EAR、FedRAMP High、機密区分 |
| スマートシティ | 地理空間、交通、環境、防災 | マルチプロトコル、SnapMirror | Kafka(エッジ) / Glue ETL | 市民 PII、データ主権、OGC |
| 広告 / マーケ | アセット管理、ブランドチェック、配信分析 | マルチプロトコル、FlexClone | DataSync | ターゲティング PII、cookie 規制 |
| 運輸 / 鉄道 🚆 | 設備点検、予知保全、保守分析 | マルチプロトコル、SnapLock | DataSync / Kafka | 鉄道安全規制、保持義務 |
| サステナビリティ / ESG | ESG メトリクス、排出量、規制報告 | マルチプロトコル、SnapLock | DataSync | CSRD、TCFD、SEC 気候開示 |
| 不動産 | 物件画像、契約抽出、ポートフォリオ | ストレージ効率、マルチプロトコル | DataSync | 顧客 PII、取引規制 |
| 人材 / HR | 履歴書スクリーニング、人材マッチング | ONTAP REST API、SnapLock | DataSync | 従業員 PII、採用差別禁止 |
| 化学 / 素材 | SDS 管理、ラボノート、材料開発 | マルチプロトコル、SnapLock、FlexClone | DataSync / Glue ETL | REACH、GHS、IP 保護 |
| ゲーミング | アセット品質、ビルド、プレイヤー分析 | FlexClone、FlexCache、スケールアウト | DataSync / Kafka | プレイヤー PII、未成年保護 |
| SAP / ERP 隣接 | IDoc/EDI、バッチ出力、マスタ統合 | 高性能ストレージ、Snapshot/FlexClone | DataSync / Federation | 財務監査(SOX)、整合性 |

---

## 共通の設計上の注意（全業界横断）

業界を問わず、以下の 3 点は設計の初期段階で考慮してください。

### DR の対象範囲（最重要）

> SnapMirror は **FSx for ONTAP ボリューム（ソース）** をレプリケートしますが、**UC テーブルや S3 上の分析コピーはレプリケートしません**。DR 設計では分析コピーを別途扱う必要があります（DR リージョンで DataSync を再実行する、または S3 Cross-Region Replication で同期する）。「SnapMirror があれば DR は完結」という誤解を避けてください。パイプライン全体（FSx for ONTAP + S3 + UC + MSK）の DR オーケストレーションは [互換性マトリクスの DR ランブック](./compatibility-matrix.md) を参照。

### ガバナンスの二者択一ではなく適材適所

> 本カタログは UC ガバナンスを中心に記載していますが、AWS ネイティブなワークロード（Athena/EMR/Glue 中心、特に半導体・メディア）では **AWS Lake Formation / Amazon DataZone（SageMaker Unified Studio）** が AWS 側のガバナンス層として機能します。UC と AWS ネイティブガバナンスは排他ではなく、用途に応じて選択または併用してください（優劣ではなく適材適所）。

> UC のガバナンスは **ABAC（属性ベースアクセス制御）+ governed tags** が現代的なパターンです（[公式](https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/tutorial)）。業界ごとに一貫したタグ分類体系（例: `pii`, `ephi`, `ip`, `payment`, `classification`）を先に定義し、それに基づいてポリシーを適用すると大規模環境で管理しやすくなります。規制業界（金融・医療・公共）は**中央集権型**ガバナンス、大規模で多様な事業を持つ組織は**カタログ単位のフェデレーション型**が適合します。

### コスト制御の共通レバー

> データ量が大きい業界（メディア、半導体、通信、自動車 ADAS）では「**すべてを S3 に複製しない**」ことが最大のコスト制御レバーです。生データは FSx for ONTAP に残し、UC に取り込むのは分析対象のキュレート済みサブセット・メタデータ・集計に限定してください。S3 Lifecycle + ストレージクラス（IA/Glacier）の階層化も併用します。

---

## 業界別ソリューション

各業界セクションは共通テンプレートで構成: **データ特性 → 主要ユースケース → 活用する FSx for ONTAP 機能 → 推奨接続パス → ガバナンス/規制 → 注意点**。

---

### 1. 製造 / 産業（Manufacturing / Industrial）

> 詳細な製造データ基盤設計は [製造データプラットフォーム統合](../../integrations/manufacturing-data-platform/) を参照。本セクションは UC 接続観点の要約です。

**データ特性**: センサー時系列、品質検査画像、設備ログ、MES/SCADA 出力。小ファイルが大量に生成される傾向。OT ネットワークと IT ネットワークが分離。

**主要ユースケース**:
- 品質分析・SPC（統計的工程管理）: 検査データの異常検知、歩留まり改善
- 予知保全: 設備センサーデータからの故障予兆検知
- 製造トレーサビリティ: ロット/シリアル単位の製造系譜追跡（8D レポート、リコール対応）
- デジタルサプライチェーン: 在庫・需給の可視化（Databricks 公式: [Digital Supply Chain Reference Architecture](https://www.databricks.com/resources/architectures/manufacturing-digital-supply-chain-reference-architecture)、**Public**）

**活用する FSx for ONTAP 機能**:
- マルチプロトコル: PLC/SCADA が NFS/SMB で書き込んだデータを、変換なしで S3 AP 経由分析
- Snapshot: 検査時点の一貫したデータセットを DataSync の同期元に使用（本番 I/O 影響回避）
- FabricPool: コールドな履歴検査データを S3 に自動階層化

**推奨接続パス**:
- バッチ品質分析 → **パス 1（DataSync → S3 → UC）** + Auto Loader + DLT medallion
- リアルタイム品質アラート → **パス 2（Kafka via FPolicy → Structured Streaming → UC Delta）**

**ガバナンス/規制**: IATF 16949（自動車部品では品質記録の長期保持）、製造データの分類（公開集計 vs 機密設計データ）。

**注意点**: PLC は通常 Kafka Producer 機能を持たない。データフローは「PLC → NFS/SMB 書き込み → FSx for ONTAP → FPolicy 検出 → Lambda → Kafka」。OT/IT 境界は Purdue Level 3.5（IDMZ）に FPolicy Lambda / DataSync を配置。

---

### 2. 自動車（Automotive）

**データ特性**: ADAS/AD（自動運転）センサーデータ（カメラ・LiDAR・レーダー、ペタバイト級）、コネクテッドカーテレメトリ、製造トレーサビリティ、部品系譜。グローバルサプライチェーンで複数リージョンにデータが分散。

**主要ユースケース**:
- ADAS/AD データパイプライン: 走行ログの収集・ラベリング・モデル学習用データセット化
- コネクテッドカー分析: 車両テレメトリのリアルタイム分析、予知保全、OTA 更新判断
- 品質トレーサビリティ: VIN/ロット単位の系譜追跡、リコール範囲特定
- サプライチェーン可視化: ティア 1/2 サプライヤーとのデータ連携

**活用する FSx for ONTAP 機能**:
- スケールアウト性能（最大 36 GB/s、1.2M IOPS、[**Public**](https://aws.amazon.com/about-aws/whats-new/2023/11/amazon-fsx-netapp-ontap-scale-out-file-systems/)）: ADAS の大容量センサーデータの取り込み
- SnapMirror: リージョン間データレプリケーション（データ主権を考慮した設計）
- SnapLock: 品質記録の WORM 保持（規制対応）

**推奨接続パス**:
- ADAS データセット化 → **パス 3（Glue/EMR ETL → UC）**（大規模バッチ変換）
- コネクテッドカーテレメトリ → **パス 2（Kafka → Structured Streaming → UC）**
- トレーサビリティメタデータ → **パス 1（DataSync → S3 → UC）** + S3 Annotations（[S3 Annotations 評価](./s3-annotations-governance-evaluation.md) 参照）

**ガバナンス/規制**: データ主権（中国 PIPL/CSL、EU GDPR）、機能安全（ISO 26262 のトレーサビリティ要求）、品質記録の保持義務（IATF 16949、最低 15 年）。

**注意点**: グローバルサプライチェーンでは同一部品データが複数リージョンに存在。DataSync はリージョン内同期に限定し、クロスリージョン分析は S3 Cross-Region Replication で対応（データ主権の観点）。コネクテッドカー個人データは匿名化後に同期。

> ADAS センサーデータは独自バイナリフォーマット（rosbag、MDF4、車載ログ）の場合が多く、Parquet 等への**変換パーサーの開発が前提**です。パス 3（Glue/EMR ETL）の前段に専用パーサーステップを設計してください。また、自動運転の型式認証（type approval）では走行ログが認証エビデンスとして保持義務の対象になる場合があり、保持期間とフォーマット可読性の長期保証を考慮してください。

---

### 3. 金融サービス / 保険（Financial Services / Insurance）

**データ特性**: 取引データ（高頻度・低レイテンシ）、市場データ、顧客データ（PII）、リスクモデル入力、規制報告データ。長期保持義務と改ざん防止要件。

**主要ユースケース**:
- リスク分析: 市場リスク・信用リスクの計算（Databricks 公式: [Investment Management Reference Architecture](https://www.databricks.com/resources/architectures/financial-services-investment-management-reference-architecture)、**Public**）
- 不正検知: リアルタイム取引監視、AML（マネーロンダリング対策）
- 規制報告: BCBS 239（リスクデータ集計）、規制当局への報告データ生成
- 保険: 保険金請求分析、アクチュアリーモデル、不正請求検知

**活用する FSx for ONTAP 機能**:
- SnapLock（WORM）: 規制報告データ・取引記録の改ざん防止保持
- Snapshot: 監査時点の一貫したデータセット保全
- 暗号化: 保存時（volume encryption）+ 転送時（NFS krb5p / TLS）の暗号化チェーン
- 高性能ストレージ: Oracle/SQL Server 等のコアバンキング DB のデータストア（[**Public**](https://aws.amazon.com/blogs/industries/fsi-services-spotlight-featuring-amazon-fsx-for-netapp-ontap/)）

**推奨接続パス**:
- リスク分析・規制報告 → **パス 1（DataSync → S3 → UC）** + UC フルガバナンス（lineage, tags, masks）
- リアルタイム不正検知 → **パス 2（Kafka → Structured Streaming → UC）**
- コアバンキング DB 連携 → UC Lakehouse Federation（PostgreSQL/Oracle/SQL Server、技術ガイド参照）

**ガバナンス/規制**: BCBS 239（リスクデータ集計の正確性・完全性・適時性）、データレジデンシー（各国金融規制）、監査証跡（誰がどのデータにアクセスしたか）、PII マスキング（UC Column Masks / Row Filters）。

**注意点**: 規制報告データは UC の lineage で「ソースから報告値までの系譜」を証明可能にする。マルチクラウド規制要件（[**Public**](https://www.databricks.com/blog/multi-cloud-architecture-portable-data-and-ai-processing-financial-services)）がある場合、UC のクロスクラウドガバナンスを活用。

> BCBS 239 は集計の正確性だけでなく**適時性（timeliness）**を要求します。DataSync の RPO（データ鮮度）が報告要件を満たすか確認してください。また、このデータで学習するリスクモデルは**モデルリスク管理**（米国 SR 11-7 等）の対象となるため、UC lineage に加えてモデルのバージョン管理・検証記録（MLflow）を統合してください。

> SnapLock には **Compliance モード**（管理者でも保持期間内は削除不可）と **Enterprise モード**（管理者は削除可能）があります。規制報告・取引記録の改ざん防止には Compliance モードを使用し、Compliance Clock の設定を確認してください。

> 本番取引 DB から直接 DataSync すると業務 I/O と競合します。金融でも製造同様、**Snapshot → FlexClone → DataSync** のステージングパターンで業務影響を回避してください。

---

### 4. 医療 / ライフサイエンス（Healthcare / Life Sciences）

**データ特性**: EHR（電子カルテ、FHIR）、医療画像（DICOM、大容量）、ゲノミクスデータ（ペタバイト級）、臨床試験データ、創薬研究データ。ePHI（保護対象保健情報）を含む高機密データ。

**主要ユースケース**:
- EHR 分析: 臨床アウトカム分析、人口健康管理（AWS HealthLake / FHIR、[**Public**](https://aws.amazon.com/healthlake/getting-started/)）
- ゲノミクス: シーケンスデータ解析パイプライン、バリアント解析
- 医療画像 AI: 画像診断支援モデルの学習（DICOM → UC Volume）
- 創薬: 化合物スクリーニング、臨床試験データ管理（GxP）

**活用する FSx for ONTAP 機能**:
- マルチプロトコル: 医療システムが SMB で書き込んだ画像/記録を分析基盤へ（[**Public**: 医療システムは患者記録を SMB ボリュームに保存](https://www.netapp.com/blog/ai-insights-ontap-s3-access-points-dremio/)）
- FlexClone: 本番ゲノミクスデータの瞬時クローンで研究環境を分離（本番影響なし）
- SnapLock: 臨床試験データの WORM 保持（GxP の電子記録要件）

**推奨接続パス**:
- EHR/臨床分析 → **パス 1（DataSync → S3 → UC）** + UC フルガバナンス
- ゲノミクス/画像バッチ解析 → **パス 3（Glue/EMR ETL → UC）**
- RAG/臨床ドキュメント検索 → Bedrock KB（S3 AP 直接、UC 外、HIPAA 対応アーキテクチャ要件あり、[**Public**](https://aws.amazon.com/blogs/industries/building-a-hipaa-ready-generative-ai-architecture-for-healthcare-on-aws/)）

**ガバナンス/規制**: HIPAA（ePHI 保護）、HITRUST、GxP（FDA 21 CFR Part 11 電子記録/署名）、GDPR/HDS（EU 医療データ）、データ最小化原則。

**注意点**: ePHI を含むデータは UC Column Masks で非認可ユーザーから秘匿。RAG パイプラインでは ePHI がモデル出力に漏洩しないようガードレールを設計。匿名化/仮名化を同期前に実施するパターンを検討。

> 匿名化には標準があります（HIPAA Safe Harbor 方式 vs Expert Determination 方式）。どちらに準拠するかを設計時に明確化してください。特に **DICOM 画像はピクセルデータに PHI が焼き込まれている（burned-in annotation）場合があり**、メタデータ除去だけでは不十分です。画像 AI 学習前にピクセルレベルの de-identification が必要です。ゲノミクスは GA4GH 標準と同意管理（consent）も考慮対象です。

---

### 5. 半導体 / EDA（Semiconductor / Electronic Design Automation）

**データ特性**: チップ設計データ（RTL、ネットリスト）、検証/シミュレーション結果、テープアウトデータ、EDA ツールライブラリ。極めて高い IOPS と低レイテンシを要求。IP（知的財産）として最高機密。

**主要ユースケース**:
- チップ設計・検証: EDA ツール（合成・配置配線・検証）のストレージ基盤（[**Public**: Arm のチップ設計事例](https://aws.amazon.com/solutions/case-studies/arm-ltd-case-study/)）
- テープアウト分析: 設計バージョン・検証結果の分析
- リグレッション分析: 大量シミュレーションジョブ結果の傾向分析
- ハイブリッドバースト: オンプレ EDA ワークロードのクラウドバースト（[**Public**](https://aws.amazon.com/blogs/industries/accelerating-eda-with-the-agility-of-aws-and-netapp-data-services/)）

**活用する FSx for ONTAP 機能**:
- FlexCache: オンプレのツール/ライブラリをクラウドにキャッシュ（クラウドワークロードからローカルに見える、[**Public**](https://aws.amazon.com/blogs/industries/accelerating-eda-with-the-agility-of-aws-and-netapp-data-services/)）
- スケールアウト性能（36 GB/s、1.2M IOPS）: EDA の高 IOPS ワークロード
- Snapshot: 設計バージョンの時点管理

**推奨接続パス**:
- 検証結果の傾向分析 → **パス 3（Glue/EMR ETL → UC）** または **パス 1（DataSync → S3 → UC）**
- EDA ワークロード自体は FSx for ONTAP の NFS で直接実行（UC 接続は分析メタデータのみ）

**ガバナンス/規制**: IP 保護（設計データの厳格なアクセス制御）、輸出管理（EAR/ITAR、設計データの国外アクセス制限）。

**注意点**: EDA の主ワークロード（設計・検証）は FSx for ONTAP 上で完結し、UC 接続は「分析・傾向把握」の二次利用に限定するのが現実的。設計データそのものを UC に複製するのは IP 保護・データ量の両面で非推奨。分析対象はメタデータ・結果サマリに絞る。

> UC 接続の現実的な分析対象は、ジョブスケジューラ（IBM LSF / Slurm）のジョブ結果ログ・リグレッション結果サマリです。テープアウト時間は EDA ライセンスコストに直結するため、ライセンス使用率とジョブ完了傾向の分析が高い ROI を持ちます。設計データ本体（RTL/ネットリスト）は FSx for ONTAP に留め、FlexCache でオンプレ/クラウド間のツール・ライブラリ共有を最適化してください。

---

### 6. メディア / エンタメ（Media & Entertainment）

**データ特性**: 映像素材（VFX、4K/8K、ペタバイト級）、レンダリング中間ファイル、デジタルアセット、配信ログ。大容量シーケンシャル I/O。

**主要ユースケース**:
- VFX レンダリング: レンダーファームのストレージ基盤（[**Public**: FSx for ONTAP は VFX rendering に適合](https://aws.amazon.com/fsx/netapp-ontap/resources/)）
- デジタルアセット管理（DAM）: メディアアセットのメタデータ管理・検索
- 配信分析: 視聴ログ・エンゲージメント分析、レコメンデーション
- コンテンツ AI: 自動タグ付け、シーン検出、字幕生成

**活用する FSx for ONTAP 機能**:
- スケールアウト性能: レンダーファームの高スループット I/O
- FlexClone: 制作環境の瞬時複製（バージョン管理）
- マルチプロトコル: 制作ツール（SMB）と分析（S3 AP）の同一データアクセス

**推奨接続パス**:
- 配信/視聴ログ分析 → **パス 1（DataSync → S3 → UC）** + Databricks レコメンデーション
- アセットメタデータ・自動タグ → **パス 1** + S3 Annotations（コンテンツコンテキスト付与）
- コンテンツ AI（画像/音声 embedding）→ UC Volume + AI Search

**ガバナンス/規制**: コンテンツ権利管理、DRM、制作中コンテンツの機密保持（NDA）。

**注意点**: 映像素材そのものを UC に複製するのはデータ量の観点で非現実的。UC で管理するのはメタデータ・タグ・配信ログ。素材本体は FSx for ONTAP に残し、必要に応じて S3 AP 経由でアクセス。

---

### 7. 小売 / 消費財（Retail / CPG）

**データ特性**: POS トランザクション、在庫データ、顧客データ（PII）、ECサイトログ、サプライチェーンデータ、商品画像。

**主要ユースケース**:
- 需要予測: 販売予測・在庫最適化（Databricks 公式: [Retail Demand Forecasting Reference Architecture](https://www.databricks.com/resources/architectures/retail-demand-forecasting-reference-architecture)、**Public**）
- パーソナライゼーション: レコメンデーション、顧客セグメンテーション
- 在庫最適化: リアルタイム在庫可視化、補充最適化
- 商品分析: 商品画像の自動分類、属性抽出

**活用する FSx for ONTAP 機能**:
- ストレージ効率（重複排除/圧縮で最大 65% 削減、[**Public**](https://www.netapp.com/learn/aws-fsxn-blg-reduce-costs-and-increase-efficiency-with-fsx-for-ontap/)）: 大量の商品画像・ログのコスト最適化
- Snapshot: 日次バッチ分析の一貫したスナップショット

**推奨接続パス**:
- 需要予測・顧客分析 → **パス 1（DataSync → S3 → UC）** + Databricks ML
- リアルタイム在庫 → **パス 2（Kafka → Structured Streaming → UC）**
- 商品画像 AI → UC Volume + AI Search

**ガバナンス/規制**: PCI DSS（決済データ）、PII 保護（顧客データ）、GDPR/各国個人情報保護法。

**注意点**: 決済データ（カード番号等）は PCI DSS スコープ。UC への取り込み前にトークン化/マスキング。顧客 PII は UC Column Masks で保護。

> 重複排除/圧縮はテキスト・ログ・構造化データで効果が高い一方、**既に圧縮された動画や暗号化データではほとんど効きません**（メディア・ゲノミクスで注意）。商品画像（JPEG）も圧縮済みのため、ストレージ効率の期待値はデータ種別で見積もってください。

---

### 8. エネルギー / 公益（Energy & Utilities）

**データ特性**: グリッドテレメトリ（スマートメーター、SCADA）、発電設備センサー、地理空間データ、需給予測データ。OT 環境とリアルタイム性要求。

**主要ユースケース**:
- グリッド分析: 需給バランス、負荷予測（Databricks 公式: [Office of the CFO for Manufacturing & Energy](https://www.databricks.com/resources/architectures/office-of-cfo-for-manufacturing-and-energy)、**Public**）
- 予知保全: 発電設備・送電設備の故障予兆検知
- 資産管理: 設備ライフサイクル管理、メンテナンス最適化
- 再生可能エネルギー: 発電予測（気象連動）、蓄電最適化

**活用する FSx for ONTAP 機能**:
- マルチプロトコル: SCADA/ヒストリアンの出力を分析基盤へ
- SnapMirror: 地理的に分散した拠点間のデータレプリケーション

**推奨接続パス**:
- グリッドテレメトリ → **パス 2（Kafka → Structured Streaming → UC）**
- 設備データバッチ分析 → **パス 1（DataSync → S3 → UC）**

**ガバナンス/規制**: NERC CIP（北米電力インフラ保護）、OT/IT 分離（重要インフラのセキュリティ）。

**注意点**: 電力グリッドは重要インフラ（クリティカルインフラ）。OT ネットワークのセキュリティ境界を厳格に設計。製造業と同様、Purdue モデルに基づく IDMZ 経由のデータフロー。

> **UC 上の分析は「インサイト」であり、OT の制御ループ（control loop）に組み込んではいけません**。グリッド制御・保護リレー等の安全に関わる判断は OT 側のリアルタイム制御系で完結させ、Databricks 分析は予測・最適化・可視化のオフライン/準リアルタイム用途に限定してください。分析系の遅延や障害が制御系に波及しない設計が安全上必須です。

---

### 9. 通信（Telecommunications）

**データ特性**: ネットワークテレメトリ、CDR（通話詳細記録、大量・高頻度）、加入者データ（PII）、ネットワーク機器ログ。超大量データと保持義務。

**主要ユースケース**:
- ネットワーク分析: トラフィック分析、品質監視、容量計画
- CDR 分析: 通話パターン分析、課金、不正検知
- 不正検知: SIM スワップ詐欺、課金詐欺のリアルタイム検知
- カスタマーエクスペリエンス: 解約予測、サービス品質分析

**活用する FSx for ONTAP 機能**:
- スケールアウト性能: 大量 CDR/テレメトリの取り込み
- Snapshot: 監査・規制対応のための時点データ保全
- ストレージ効率: 大量ログのコスト最適化

**推奨接続パス**:
- ネットワークテレメトリ → **パス 2（Kafka → Structured Streaming → UC）**
- CDR バッチ分析 → **パス 1（DataSync → S3 → UC）** または **パス 3（Glue/EMR ETL）**

**ガバナンス/規制**: データ保持義務（各国の通信法）、加入者 PII 保護、通信の秘密。

**注意点**: CDR は超大量（日次テラバイト級）。DataSync の対象を集計済みデータに絞り、生 CDR は FSx for ONTAP に保持して必要時のみ分析。

> CDR は「データグラビティ（data gravity）」が大きく、集計済みデータでも DataSync 転送量が膨大になります。**エッジ/取り込み時点での事前集計・サンプリング**（時間窓集計、対象 KPI への絞り込み）を設計し、UC には分析に必要な粒度のみを取り込んでください。生 CDR 全件の S3 複製はコスト・性能の両面で非推奨です。

---

### 10. 公共 / 政府（Public Sector / Government）

**データ特性**: 市民データ（高機密 PII）、行政記録、研究データ、防衛関連データ、地理空間データ。データ主権と長期保持要件。

**主要ユースケース**:
- 市民サービス分析: 行政サービスの利用分析、政策立案支援
- 研究データ管理: 政府研究機関のデータ基盤
- 防衛/安全保障: 機密データ分析（厳格なアクセス制御）
- スマートシティ: 都市インフラのセンサーデータ分析

**活用する FSx for ONTAP 機能**:
- SnapLock（WORM）: 行政記録の改ざん防止・長期保持
- SnapMirror: DR・データ保全
- 暗号化: 機密データの保存時/転送時暗号化

**推奨接続パス**:
- 市民データ分析 → **パス 1（DataSync → S3 → UC）** + UC フルガバナンス + 厳格な監査
- 研究データバッチ → **パス 3（Glue/EMR ETL → UC）**

**ガバナンス/規制**: データ主権（国内データセンター必須の場合あり）、FedRAMP（米国政府クラウド）、ITAR/EAR（防衛関連、GovCloud 使用）、各国の政府情報セキュリティ基準。

**注意点**: データ主権要件によりリージョン選択が制約される。防衛関連は GovCloud + 厳格な IAM/ネットワーク分離。市民 PII は UC のフルガバナンス（masks, row filters, audit）を必須適用。

> データ主権要件によっては、**SaaS のコントロールプレーンの所在地**が制約になります。Databricks や Snowflake のコントロールプレーンが要件を満たすリージョンにあるか、また GovCloud では別オファリングになる点を確認してください。データプレーンが国内にあってもコントロールプレーンが国外にある構成が許容されないケースがあります。

> GovCloud ではサービスの可用性が商用リージョンと異なります。Amazon FSx for NetApp ONTAP、DataSync、MSK、Databricks の GovCloud 提供状況を事前に確認してください。ITAR/EAR 対象データは GovCloud + 厳格なネットワーク分離が前提です。

---

### 11. 農業 / 食品（Agriculture / Food）

> エッジのセンサー/カメラからデータが発生する業界。製造・自動車と同様のエッジ→クラウド設計が適用されます。

**データ特性**: 土壌センサー、気象ステーション、ドローン空撮画像（マルチスペクトル）、害虫トラップ、農機テレメトリ、トレーサビリティ文書。圃場は広域分散・低帯域（LoRaWAN / LTE）。

**主要ユースケース**:
- 精密農業: 土壌・気象・作物ストレスの分析、収量予測（AWS: [Connected Farm](https://aws.amazon.com/blogs/industries/creating-the-connected-farm-using-sensor-and-vision-data)、**Public**）
- 作物健全性モニタリング: ドローン/衛星画像による病害・生育判定
- 食品トレーサビリティ: 生産〜流通の系譜追跡（ロット・産地・検査記録）
- 農機/フリート管理: 自動運転トラクター・収穫機のテレメトリ

**活用する FSx for ONTAP 機能**:
- マルチプロトコル: 圃場ゲートウェイが NFS/SMB で集約したデータを分析基盤へ
- ストレージ効率: 大量のドローン画像・時系列センサーデータのコスト最適化
- SnapMirror: 地理分散した農場拠点のデータ集約

**推奨接続パス**:
- センサーテレメトリ → **パス 2（Kafka → Structured Streaming → UC）**（エッジゲートウェイ経由）
- ドローン/衛星画像のバッチ解析 → **パス 3（Glue/EMR ETL → UC）** + SageMaker geospatial
- トレーサビリティメタデータ → **パス 1（DataSync → S3 → UC）** + S3 Annotations

**ガバナンス/規制**: 食品安全（HACCP、食品トレーサビリティ法）、農地データの所有権、補助金監査。

**注意点**: 圃場のエッジデバイスは低帯域・間欠接続。エッジ（AWS IoT Greengrass 等）でフィルタリング・推論を行い、集約データのみをクラウドに送る設計が必須。生画像の全件アップロードは帯域・コストの観点で非現実的。多くのエッジ推論（作物健全性判定）はエッジで完結し、UC には判定結果と代表画像のみを取り込みます。

> 農地データの**所有権**はしばしば争点になります（農家 vs 農機 OEM vs 農業ソリューション提供者）。データ共有契約と UC のアクセス制御を明確にしてください。また農業データは季節性が極めて高く（作付け・収穫期にピーク）、FSx for ONTAP のスループットはピークに合わせた計画またはエラスティックスループットの活用を検討してください。

---

### 12. 物流 / サプライチェーン（Logistics / Supply Chain）

> エッジのカメラ/センサーからデータが発生する業界。倉庫・輸送のリアルタイム可視化が中心。

**データ特性**: 倉庫カメラ（物体認識・在庫）、配送伝票（OCR）、コールドチェーンセンサー（温度・湿度）、車両テレマティクス、ハンディスキャナーログ。

**主要ユースケース**:
- 倉庫コンピュータビジョン: 在庫追跡、破損検知、誤出荷防止、作業者安全（フォークリフト接近検知）
- 配送伝票 OCR: 伝票・ラベルの自動読み取り（repo UC12）
- コールドチェーン監視: 医薬品・生鮮食品の温度逸脱検知
- フリート/テレマティクス: 配送ルート最適化、ドライバー行動分析

**活用する FSx for ONTAP 機能**:
- スケールアウト性能: 多拠点倉庫カメラの大量画像の取り込み
- マルチプロトコル: 倉庫管理システム（WMS）出力と分析の同一データアクセス
- ストレージ効率: 監視映像・スキャンログのコスト最適化

**推奨接続パス**:
- 倉庫 CV のリアルタイムアラート → エッジで推論（オンプレカメラ + エッジアプライアンス、<300ms）、結果を **パス 2（Kafka → UC）**
- 伝票 OCR バッチ → **パス 1（DataSync → S3 → UC）** + Textract
- コールドチェーンテレメトリ → **パス 2（Kafka → Structured Streaming → UC）**

**ガバナンス/規制**: 医薬品コールドチェーン（GDP: Good Distribution Practice）、危険物輸送記録、輸出入通関データ。

**注意点**: 倉庫 CV はレイテンシ要件が厳しく（<300ms）、エッジ推論が基本。クラウド（UC）はエッジ結果の集約分析・傾向把握に位置づけます。AWS Panorama は 2026 年 5 月でサポート終了のため、エッジ CV は AWS IoT Greengrass + 汎用カメラ、またはサードパーティのエッジアプライアンスで設計してください。

> コールドチェーンの温度逸脱アラートは、医薬品 GDP では**準リアルタイムの規制要件**（逸脱時に即時通知）です。これは DataSync のバッチ同期では満たせないため、エッジ/IoT Core でのしきい値アラート + パス 2（Kafka）を使用し、UC への取り込みは事後の傾向分析・監査に位置づけてください。配送のラストマイルでは、配達証明（POD）写真も重要なデータソースです。

---

### 13. 観光 / ホスピタリティ（Travel / Tourism / Hospitality）

> エッジのセンサー/カメラからデータが発生する業界。施設・宿泊・観光体験のデータ化。

**データ特性**: 予約文書、施設点検画像、人数カウント/混雑センサー、建物 IoT（コネクテッドホテル）、ゲスト行動データ、レビュー/問い合わせテキスト。

**主要ユースケース**:
- ゲスト体験のパーソナライゼーション: 予約・滞在・行動データの統合分析（AWS: [Travel & Hospitality Connected Experiences](https://aws.amazon.com/travel-and-hospitality/connected-experiences/)、**Public**）
- 施設点検: 客室・設備の点検画像の AI 分析（repo UC20）
- 混雑/人数管理: 観光地・テーマパーク・施設の人数カウント、動線分析
- 予約文書処理: 予約・契約文書の OCR・構造化

**活用する FSx for ONTAP 機能**:
- マルチプロトコル: 施設管理システム（PMS/BMS）出力と分析の同一データアクセス
- ストレージ効率: 点検画像・監視映像のコスト最適化
- Snapshot: 繁忙期前後の一貫したデータセット保全

**推奨接続パス**:
- ゲスト行動・予約分析 → **パス 1（DataSync → S3 → UC）** + Databricks ML（パーソナライゼーション）
- 施設点検画像 AI → **パス 1** + UC Volume + AI Search
- 混雑/人数カウント → エッジで集計（人数カウントカメラ）、集計値を **パス 2（Kafka → UC）**

**ガバナンス/規制**: ゲスト PII（GDPR / 各国個人情報保護法）、決済データ（PCI DSS）、映像のプライバシー（人物が写る監視映像）。

**注意点**: 人数カウント/混雑分析では、個人を特定しない集計データ（カウント値）のみをクラウドに送り、生映像はエッジで処理・破棄する設計でプライバシーを保護してください。生の監視映像を UC に集約するのはプライバシー・データ量の両面で非推奨。

> 国際旅行者のゲストデータは**越境データ**となり、データレジデンシーが複雑になります（出発国・滞在国・本社所在国の規制が交錯）。ロイヤルティプログラムデータは高価値 PII であり、UC のフルガバナンスを適用してください。観光・宿泊は季節性・イベント駆動の需要変動が大きく、ストレージ/コンピュートの弾力性を設計に反映してください。

---

### 14. 法務 / コンプライアンス（Legal / Compliance）

**データ特性**: 契約書、法的文書、ファイルサーバー監査ログ、NTFS ACL メタデータ。長期保持・改ざん防止要件。

**主要ユースケース**:
- ファイルサーバー監査: NTFS ACL・アクセス権限の棚卸し、データガバナンスレポート（repo UC1）
- 契約分析: 契約条項の抽出・分類・リスク検出
- e-Discovery: 訴訟対応の文書検索・分類
- 保持コンプライアンス: 法定保持期間の管理

**活用する FSx for ONTAP 機能**:
- ONTAP REST API: NTFS ACL・所有者・権限メタデータの取得（S3 API では取得不可）
- SnapLock（WORM）: 法定保持文書の改ざん防止
- Snapshot: 監査時点のファイルシステム状態保全

**推奨接続パス**:
- 契約分析・文書分類 → **パス 1（DataSync → S3 → UC）** + Bedrock
- ACL 監査 → ONTAP REST API + Athena（UC 外も可）

**ガバナンス/規制**: 弁護士・依頼者間秘匿特権、文書保持義務、GDPR の削除権。

**注意点**: 秘匿特権文書は UC のアクセス制御を厳格に。permission-aware RAG では NTFS ACL を尊重したフィルタリングが必須（[技術ガイドのパーミッション考慮 RAG](./fsx-ontap-to-databricks-unity-catalog-guide.md) 参照）。

> 訴訟が予見される場合の**リティゲーションホールド（証拠保全）**では、データを改ざん不可能な状態で保全する必要があります。SnapLock Compliance モード（管理者でも保持期間内は削除不可）が直接適用できます。e-Discovery では証拠の**チェーンオブカストディ**（誰がいつアクセス・処理したか）を UC audit log で証明可能にしてください。

---

### 15. 建設 / AEC（Construction / Architecture-Engineering-Construction）

**データ特性**: BIM モデル（大容量 3D）、図面（CAD/PDF）、現場写真、ドローン点検画像、安全点検記録。

**主要ユースケース**:
- BIM バージョン管理: モデルの版管理・差分分析（repo UC10）
- 図面 OCR: 図面・仕様書のテキスト抽出・分類
- 安全コンプライアンス: 現場写真の AI 安全点検（保護具着用検知等）
- 進捗管理: ドローン空撮による工程進捗の可視化

**活用する FSx for ONTAP 機能**:
- スケールアウト性能: 大容量 BIM モデルの共有ストレージ
- FlexClone: 設計バージョンの瞬時クローン
- マルチプロトコル: 設計ツール（SMB）と分析（S3 AP）の同一データアクセス

**推奨接続パス**:
- 図面 OCR・安全点検 → **パス 1（DataSync → S3 → UC）** + Textract/Rekognition
- BIM メタデータ分析 → **パス 3（Glue/EMR ETL → UC）**

**ガバナンス/規制**: 建築基準・安全規制、設計成果物の権利、長期保存（建物ライフサイクル）。

**注意点**: BIM モデル本体（数 GB〜）は UC に複製せず FSx for ONTAP に保持。UC で管理するのはメタデータ・点検結果・進捗指標。

---

### 16. 教育 / 研究（Education / Research）

**データ特性**: 論文 PDF、研究データ、講義動画、学習管理システム（LMS）ログ、学生データ（PII）。

**主要ユースケース**:
- 論文分類・引用分析: 論文 PDF の分類、引用ネットワーク分析（repo UC13）
- 研究データ管理: 実験データ・観測データの分類・カタログ化
- 学習分析: LMS ログからの学習行動分析、ドロップアウト予測
- 学術検索: 研究文書の RAG / セマンティック検索

**活用する FSx for ONTAP 機能**:
- マルチプロトコル: 研究者の NFS/SMB アクセスと分析の両立
- FlexClone: 研究データセットの再現可能なクローン
- ストレージ効率: 大量の研究データ・動画のコスト最適化

**推奨接続パス**:
- 論文分類・学術検索 → **パス 1（DataSync → S3 → UC）** + Bedrock / AI Search
- 研究データバッチ分析 → **パス 3（Glue/EMR ETL → UC）**

**ガバナンス/規制**: 学生 PII（FERPA 等）、研究倫理・同意、研究データの公開/保持ポリシー。

**注意点**: 学生 PII は UC Column Masks で保護。研究データは資金提供元の公開義務（オープンサイエンス）と機密保持のバランスを設計に反映。

---

### 17. 防衛 / 宇宙（Defense / Space）

**データ特性**: 衛星画像（大容量）、センサーデータ、地理空間データ、機密データ。最高機密・厳格なアクセス制御。

**主要ユースケース**:
- 衛星画像解析: 物体検出・変化検出・アラート（repo UC15）
- 地理空間インテリジェンス: マルチソースデータの統合分析
- センサーフュージョン: 複数センサーデータの統合

**活用する FSx for ONTAP 機能**:
- スケールアウト性能: 大容量衛星画像の処理
- SnapLock: 証拠データの改ざん防止保持
- 暗号化: 機密データの保存時/転送時暗号化

**推奨接続パス**:
- 衛星画像バッチ解析 → **パス 3（Glue/EMR ETL → UC）** + Rekognition/SageMaker
- 機密分析 → GovCloud + UC フルガバナンス + 厳格な監査

**ガバナンス/規制**: ITAR/EAR（輸出管理）、DoD CC SRG、FedRAMP High、CSfC、機密区分。

**注意点**: 機密データは GovCloud + 厳格なネットワーク分離が前提。コントロールプレーン所在地の制約（公共セクターと同様）を確認。深層防御とエアギャップ要件を設計に反映。

---

### 18. スマートシティ（Smart City）

> エッジのセンサー/カメラからデータが発生する業界。都市インフラの広域センシング。

**データ特性**: 地理空間データ、都市センサー（交通・環境・人流）、監視カメラ、インフラ IoT。

**主要ユースケース**:
- 地理空間解析: CRS 正規化・土地利用分類・災害リスクマッピング（repo UC17）
- 交通分析: 交通量・人流の分析、信号最適化
- 環境モニタリング: 大気質・騒音・水質のセンシング
- 防災: 災害リスクの予測・可視化

**活用する FSx for ONTAP 機能**:
- マルチプロトコル: 都市システムの多様な出力の統合
- SnapMirror: 拠点分散データの集約・DR

**推奨接続パス**:
- 都市センサーテレメトリ → **パス 2（Kafka → Structured Streaming → UC）**
- 地理空間バッチ解析 → **パス 3（Glue/EMR ETL → UC）**

**ガバナンス/規制**: 市民 PII（人流・監視データ）、データ主権、INSPIRE Directive / OGC 標準（地理空間）。

**注意点**: 人流・監視データは個人を特定しない集計をエッジで行い、プライバシーを保護。重要インフラ（交通・電力）は OT/IT 分離（エネルギー業界と同様、制御ループに分析を組み込まない）。

> スマートシティデータは**オープンデータ義務**（非機密データの公開）と市民プライバシーのガバナンス上の緊張があります。公開データセットと機密データセットを UC で明確に分離し、公開前に匿名化・集計を適用してください。複数行政機関にまたがるデータ連携には Delta Sharing / クリーンルームが有効です。

---

### 19. 広告 / マーケティング（AdTech / Marketing）

**データ特性**: クリエイティブアセット（画像・動画）、キャンペーンデータ、配信ログ、ブランドガイドライン。

**主要ユースケース**:
- クリエイティブアセット管理: アセットのタグ付け・検索（repo UC19）
- ブランドコンプライアンス: クリエイティブのブランドガイドライン適合チェック
- キャンペーン分析: 配信パフォーマンス分析、アトリビューション
- パーソナライゼーション: ターゲティング最適化

**活用する FSx for ONTAP 機能**:
- マルチプロトコル: 制作ツール（SMB）とアセット分析の両立
- FlexClone: キャンペーン素材のバージョン管理
- ストレージ効率: 大量クリエイティブアセットのコスト最適化

**推奨接続パス**:
- アセットタグ付け・ブランドチェック → **パス 1（DataSync → S3 → UC）** + Rekognition/Bedrock
- キャンペーン分析 → **パス 1** + Databricks ML

**ガバナンス/規制**: 広告データの PII（ターゲティング）、GDPR/cookie 規制、ブランドセーフティ。

**注意点**: ターゲティングに使う個人データは UC ガバナンスで厳格に管理。クリエイティブ本体（動画）は FSx for ONTAP に保持し、メタデータ・タグを UC で管理。

> サードパーティ cookie の廃止に伴い、ファーストパーティデータと**データクリーンルーム**（Databricks Clean Rooms / AWS Clean Rooms）による広告効果測定が主流になっています。クリーンルームは生 PII を共有せずに複数当事者（広告主・媒体）でプライバシー保護分析を可能にします。ターゲティングの公平性評価（バイアス検出）も考慮してください。

---

### 20. 運輸 / 鉄道（Transportation / Rail）

> エッジのセンサー/カメラからデータが発生する業界。設備・車両の保守点検。

**データ特性**: 設備点検画像、車両センサー、保守レポート、軌道/インフラ点検データ。

**主要ユースケース**:
- 設備点検: 軌道・車両・インフラの点検画像 AI 分析（repo UC22）
- 予知保全: 車両・設備センサーからの故障予兆検知
- 保守レポート分析: 点検記録の構造化・傾向分析
- 安全管理: 運行データの安全分析

**活用する FSx for ONTAP 機能**:
- マルチプロトコル: 保守システム出力と分析の両立
- スケールアウト性能: 大量点検画像の取り込み
- SnapLock: 安全記録の改ざん防止保持

**推奨接続パス**:
- 設備点検画像 AI → **パス 1（DataSync → S3 → UC）** + Rekognition
- 車両センサー予知保全 → **パス 2（Kafka → Structured Streaming → UC）**

**ガバナンス/規制**: 鉄道安全規制、保守記録の保持義務、運行データの監査。

**注意点**: 運行安全に関わるリアルタイム制御は OT 側で完結（エネルギー業界と同様、分析を制御ループに組み込まない）。UC 分析は予知保全・傾向把握に位置づけ。

> 鉄道の安全認証（SIL / EN 50128 等）に関わるデータが安全ケース（safety case）の根拠となる場合、データの**来歴**（provenance）を UC lineage で証明可能にしてください。また予知保全の誤検知は不要な保守コストを生むため、モデルの精度評価と保守判断の人間レビューを組み合わせてください。

---

### 21. サステナビリティ / ESG（Sustainability / ESG）

**データ特性**: エネルギー使用量、排出量データ、サプライチェーンデータ、ESG レポート文書、規制報告データ。

**主要ユースケース**:
- ESG メトリクス抽出: 文書からの ESG 指標抽出・集計（repo UC23）
- 排出量算定: Scope 1/2/3 排出量の計算・レポーティング
- サプライチェーン ESG: サプライヤーの ESG 評価
- 規制報告: CSRD / TCFD 等の開示対応

**活用する FSx for ONTAP 機能**:
- マルチプロトコル: 多様なソースデータの統合
- SnapLock: 規制報告データの改ざん防止保持

**推奨接続パス**:
- ESG 文書からのメトリクス抽出 → **パス 1（DataSync → S3 → UC）** + Bedrock（`ai_parse_document` 等）
- 排出量集計 → **パス 1** + Databricks（medallion）

**ガバナンス/規制**: CSRD（EU 企業サステナビリティ報告指令）、TCFD、SEC 気候開示、報告データの監査可能性。

**注意点**: ESG 報告は監査対象。UC lineage で「ソースデータから報告値までの系譜」を証明可能にする（金融の規制報告と同様）。

> Scope 3 排出量はサプライヤーからの**外部データ**であり、データ品質がばらつきます。データ品質ゲート（欠損・単位・推計値の区別）を設計し、推計と実測を区別して系譜に記録してください。ESG データは第三者保証（assurance）の対象になりつつあり、財務監査と同様の証跡が求められます。サプライヤーデータの取得には Delta Sharing / クリーンルームも選択肢です。

---

### 22. 不動産（Real Estate）

**データ特性**: 物件画像、契約書、図面、物件メタデータ、市場データ。

**主要ユースケース**:
- 物件画像分析: 物件写真の自動分類・属性抽出（repo UC26）
- 契約データ抽出: 契約書・重要事項説明書の構造化
- ポートフォリオ分析: 物件ポートフォリオの評価・最適化
- 市場分析: 価格予測、需要分析

**活用する FSx for ONTAP 機能**:
- ストレージ効率: 大量物件画像のコスト最適化
- マルチプロトコル: 物件管理システム出力と分析の両立

**推奨接続パス**:
- 物件画像分析・契約抽出 → **パス 1（DataSync → S3 → UC）** + Rekognition/Textract
- ポートフォリオ分析 → **パス 1** + Databricks ML

**ガバナンス/規制**: 顧客 PII、契約データの保持、不動産取引規制。

**注意点**: 顧客 PII・契約データは UC Column Masks で保護。

---

### 23. 人材 / HR（Human Resources）

**データ特性**: 履歴書、人事文書、評価データ、従業員データ（高機密 PII）。

**主要ユースケース**:
- 履歴書スクリーニング: 履歴書の分類・候補者評価（repo UC27）
- 人材マッチング: スキル・要件のマッチング
- 人事分析: 離職予測、エンゲージメント分析

**活用する FSx for ONTAP 機能**:
- ONTAP REST API: 人事ファイルの厳格なアクセス権限管理
- SnapLock: 法定保持が必要な人事記録

**推奨接続パス**:
- 履歴書スクリーニング → **パス 1（DataSync → S3 → UC）** + Bedrock

**ガバナンス/規制**: 従業員 PII（GDPR / 各国労働法）、採用差別禁止（AI バイアス）、人事データの厳格な保持。

**注意点**: AI スクリーニングは採用差別・バイアスのリスク。Databricks のモデルガバナンス（公平性評価）と人間による最終判断（human-in-the-loop）を必須とする。従業員 PII は最高レベルの UC ガバナンスを適用。

---

### 24. 化学 / 素材（Chemical / Materials）

**データ特性**: SDS（安全データシート）、ラボノート、実験データ、製造記録。

**主要ユースケース**:
- SDS 管理: 安全データシートの管理・分類（repo UC28）
- ラボノート分析: 実験記録の構造化・検索
- 材料開発: 実験データの分析、材料探索
- 規制コンプライアンス: 化学物質規制対応

**活用する FSx for ONTAP 機能**:
- マルチプロトコル: ラボシステム出力と分析の両立
- SnapLock: 規制記録・実験記録の改ざん防止保持
- FlexClone: 実験データセットの再現可能なクローン

**推奨接続パス**:
- SDS・ラボノート分析 → **パス 1（DataSync → S3 → UC）** + Bedrock
- 材料データ分析 → **パス 3（Glue/EMR ETL → UC）**

**ガバナンス/規制**: 化学物質規制（REACH、GHS）、SDS 保持義務、IP（材料配合）保護、GxP（医薬品材料の場合）。

**注意点**: 材料配合は IP。半導体と同様、設計/配合データ本体は FSx for ONTAP に留め、UC は分析メタデータに限定。

---

### 25. ゲーミング（Gaming）

**データ特性**: ゲームアセット（大容量）、ビルド成果物、プレイヤーログ、テレメトリ。

**主要ユースケース**:
- ゲームアセット品質チェック: アセットの検証・品質分析（repo FC6）
- ビルドパイプライン: ゲームビルドの品質・ログ分析
- プレイヤー分析: 行動分析、チャーン予測、マッチメイキング最適化
- ライブオプス: リアルタイムテレメトリ分析

**活用する FSx for ONTAP 機能**:
- FlexClone: ビルド/アセットバージョンの瞬時クローン
- スケールアウト性能: 大容量アセットの共有ストレージ
- FlexCache: 分散開発拠点間のアセット共有

**推奨接続パス**:
- アセット品質・ビルド分析 → **パス 1（DataSync → S3 → UC）** または **パス 3（Glue/EMR ETL）**
- プレイヤーテレメトリ → **パス 2（Kafka → Structured Streaming → UC）**

**ガバナンス/規制**: プレイヤー PII、未成年保護、課金データ（PCI DSS）。

**注意点**: ゲームアセット本体は FSx for ONTAP に保持。UC ではテレメトリ・品質指標・プレイヤー分析を管理。プレイヤー PII は UC ガバナンスで保護。

---

### 26. SAP / ERP 隣接（SAP / ERP-Adjacent）

> 業界横断のエンタープライズ基幹システム連携パターン。

**データ特性**: IDoc、EDI、HULFT 連携ファイル、バッチ出力、基幹システムのエクスポートデータ。

**主要ユースケース**:
- IDoc/EDI 処理: 基幹システム連携文書の処理・分析（repo SAP）
- バッチ出力分析: ERP バッチ出力の分析基盤への取り込み
- マスタデータ統合: 製品・取引先マスタの分析

**活用する FSx for ONTAP 機能**:
- 高性能ストレージ: SAP/Oracle/SQL Server のデータストア（[**Public**](https://aws.amazon.com/blogs/industries/fsi-services-spotlight-featuring-amazon-fsx-for-netapp-ontap/)）
- Snapshot/FlexClone: 基幹 DB の一貫したバックアップ・テスト環境クローン
- マルチプロトコル: 連携ファイル（NFS/SMB）と分析の両立

**推奨接続パス**:
- 連携ファイル/バッチ出力 → **パス 1（DataSync → S3 → UC）**
- 基幹 DB → UC Lakehouse Federation（PostgreSQL/Oracle/SQL Server、[技術ガイド](./fsx-ontap-to-databricks-unity-catalog-guide.md) 参照）または CDC（Debezium → Kafka → UC）

**ガバナンス/規制**: 基幹データの整合性、財務データ監査（SOX 等）、マスタデータガバナンス。

**注意点**: 基幹システムへの書き込みは Lakehouse Federation では不可（読み取り専用）。分析結果の基幹反映は別途設計。CDC でマスタ変更をリアルタイム反映する場合は Debezium → Kafka → UC パターン。

---

## 業界別データ分類とガバナンスマッピング

| 業界 | 最高機密データ | UC ガバナンス適用 | 暗号化要件 | 監査要件 |
|------|--------------|-----------------|-----------|---------|
| 金融 | 取引記録、PII | Column Masks + Row Filters + Lineage | WORM(SnapLock) + KMS | 全アクセス記録（BCBS 239） |
| 医療 | ePHI、ゲノム | Column Masks + 匿名化 | KMS + krb5p | HIPAA 監査ログ |
| 半導体 | 設計 IP | 厳格な Access Control | KMS + 輸出管理 | IP アクセス追跡 |
| 公共 | 市民 PII、機密 | フルガバナンス | KMS + データ主権 | 全操作監査 |
| 製造/自動車 | 設計、品質記録 | Tags + Row Filters | KMS | トレーサビリティ |
| 小売/通信 | 顧客 PII、決済 | Column Masks（PCI/PII） | KMS + トークン化 | アクセス監査 |
| 法務/HR | 秘匿特権文書、従業員 PII | 厳格な Access Control + ONTAP REST API ACL | KMS + SnapLock(Compliance) | チェーンオブカストディ、全アクセス監査 |
| 農業/物流/観光/運輸（エッジ） | 個人が写る映像、位置/PII | エッジ集計（非識別化）+ UC ガバナンス | KMS | エッジ処理ログ + UC 監査 |
| ESG/サステナビリティ | Scope 3 サプライヤーデータ | Lineage（推計 vs 実測）+ 第三者保証 | KMS | 監査証跡（財務監査同等） |

---

## 業界別接続パス選択ガイド

```
Q: あなたの業界のデータ鮮度要件は？
│
├── リアルタイム（秒単位）
│     ├── 製造/エネルギー/運輸（OT テレメトリ） → パス 2（Kafka via FPolicy）
│     ├── 金融（不正検知） → パス 2（Kafka）
│     └── 通信（ネットワーク監視） → パス 2（Kafka）
│
├── エッジ集約 → クラウド（エッジ推論 + 集約値送信）
│     ├── 農業（土壌/ドローン） → エッジ(Greengrass) → パス 2（Kafka）
│     ├── 物流（倉庫 CV <300ms） → エッジ推論 → パス 2（Kafka）
│     └── 観光/スマートシティ（混雑/人流） → エッジ集計 → パス 2（Kafka）
│
├── ニアリアルタイム〜バッチ（分〜時間）
│     ├── 金融/医療/公共/ESG（規制分析） → パス 1（DataSync）+ UC フルガバナンス
│     ├── 小売/観光/不動産（需要予測/パーソナライズ） → パス 1（DataSync）+ ML
│     └── 自動車（コネクテッドカー） → パス 1 or 2（混在）
│
└── 大規模バッチ変換（時間〜日）
      ├── 半導体/メディア/建設/ゲーミング（大容量） → パス 3（Glue/EMR ETL）
      ├── ゲノミクス → パス 3（Glue/EMR）
      ├── 防衛/スマートシティ（衛星/地理空間） → パス 3（Glue/EMR）+ geospatial
      └── 自動車 ADAS データセット化 → パス 3（Glue/EMR）

文書中心の業界（法務/教育/HR/化学 SDS/広告/SAP-EDI）:
      → パス 1（DataSync）+ Bedrock/Textract（OCR・分類・抽出）
```

---

## エッジ発生データ業界の共通設計原則

製造・自動車に加え、**農業・物流・観光・スマートシティ・運輸**もエッジ機器（センサー/カメラ）からデータが発生します。これらに共通する設計原則:

1. **エッジで推論・集約、クラウドで分析**: 低帯域・低レイテンシ要件のため、エッジ（AWS IoT Greengrass / SageMaker Edge / オンプレ CV アプライアンス）で一次処理し、結果・集約値・代表データのみをクラウドへ送る
2. **生データの全件アップロードを避ける**: 帯域・コスト・プライバシーの観点で、生映像/生センサーストリームの全件クラウド転送は非推奨
3. **FSx for ONTAP は IT 側の集約点**: エッジ → ゲートウェイ → FSx for ONTAP（IT ネットワーク）→ DataSync/FPolicy → UC のパターン。OT/IT 境界を尊重
4. **プライバシー保護**: 人物が写る映像（物流の作業者、観光の来訪者、スマートシティの市民）は、個人を特定しない集計をエッジで行い、生映像はエッジで処理・破棄
5. **安全制御との分離**: 運輸・エネルギー・スマートシティの安全制御は OT 側で完結。UC 分析を制御ループに組み込まない
6. **季節性・需要変動への対応**: 農業（作付け/収穫）・観光（繁忙期）・小売（セール期）など季節変動の大きい業界では、FSx for ONTAP のスループットをピークに合わせて計画するか、エラスティックスループット + S3 Intelligent-Tiering で弾力的に対応する

> **補足**: AWS Panorama は 2026 年 5 月でサポート終了。エッジ CV は AWS IoT Greengrass + 汎用カメラ、またはサードパーティのエッジアプライアンスで設計してください。

### 組織横断データ共有（複数業界共通）

複数当事者でのデータ活用が必要な業界（建設の多者協業、サプライチェーン、研究コンソーシアム、スマートシティの複数行政機関、ESG の Scope 3 サプライヤー、広告の広告主×媒体）では、生データを共有せずにガバナンス下で協業する仕組みが有効です:

> UC にデータを取り込んだ**後**、組織横断共有には Delta Sharing / OpenSharing（提供者のストレージから受信者へ読み取り権限付与、ゼロコピー共有）を使用します。生 PII を共有せずに複数当事者で分析する場合は、Databricks Clean Rooms / AWS Clean Rooms が適します（広告効果測定、共同マーケティング、多施設研究等）。いずれも UC ガバナンス（lineage, masks）を維持したまま外部共有を実現します。

---

## 段階的導入の業界別考慮

技術ガイドの [段階的導入推奨ステップ](./fsx-ontap-to-databricks-unity-catalog-guide.md#段階的導入推奨ステップ) を業界特性で調整:

| 業界 | Phase 1 重点 | 規制ゲート | 特記事項 |
|------|------------|-----------|---------|
| 金融/医療/公共 | PoC でガバナンス検証を最優先 | 本番前にコンプライアンス監査 | データ分類・マスキングを Phase 1 から |
| 製造/自動車 | パイロットライン/単一車種から | 品質会議での承認 | OT/IT 境界を Phase 1 で設計 |
| 半導体/メディア | 分析メタデータのみ（IP/素材は複製しない） | IP/輸出管理レビュー | データ量見積もりを先行 |
| 小売/通信 | PII マスキング検証を Phase 1 で | PCI/個人情報保護監査 | 大量データのコスト最適化 |
| 農業/物流/観光/運輸/スマートシティ（エッジ） | エッジ推論 + 集約パイプラインを Phase 1 で検証 | プライバシー（映像）・安全制御分離レビュー | 季節変動に応じたスループット計画 |
| 法務/HR/化学（文書・IP） | アクセス制御 + 保持/IP 保護を Phase 1 で | 秘匿特権/IP/輸出管理レビュー | 文書中心は OCR/抽出パイプラインを先行 |

---

## 関連ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| [FSx for ONTAP → Databricks UC 接続総合ガイド](./fsx-ontap-to-databricks-unity-catalog-guide.md) | 接続パスの技術詳細（本カタログの技術的根拠） |
| [DataSync → S3 同期ガイド](./datasync-to-s3-guide.md) | パス 1 の詳細手順 |
| [Kafka-ClickHouse-UC 接続ガイド](./kafka-clickhouse-unity-catalog-connectivity.md) | パス 2 の技術詳細 |
| [S3 Annotations ガバナンス評価](./s3-annotations-governance-evaluation.md) | メタデータガバナンス（トレーサビリティ等） |
| [互換性マトリクス](./compatibility-matrix.md) | プラットフォーム別 API 対応状況 |
| [製造データプラットフォーム統合](../../integrations/manufacturing-data-platform/) | 製造業の詳細設計 |
| [FSx for ONTAP S3 Access Points Serverless Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) | 業界別サーバーレス自動化パターン（UC1-UC30）の実装例（同一著者） |

---

## 免責とエビデンスについて

- 本カタログのユースケースは公開リファレンスアーキテクチャ（Databricks/AWS/NetApp 公式）と業界標準ロールの一般的知見に基づきます。
- 特定顧客の事例・社名・機密情報は含みません。引用は公開情報（**Public**）に限定し、リンクで出典を明示しています。
- 規制要件（HIPAA、BCBS 239、IATF 16949 等）の記載は技術設計上の考慮点であり、**法的・コンプライアンス判断ではありません**。各組織の法務・コンプライアンス部門の確認が必要です。
- 接続パスの検証ステータスは技術ガイドの [検証ステータスサマリ](./fsx-ontap-to-databricks-unity-catalog-guide.md#検証ステータスサマリ) を参照してください。
