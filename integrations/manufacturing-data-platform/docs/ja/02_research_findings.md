# 技術調査結果

🌐 [English](../en/02_research_findings.md) | **日本語**

---

## RES-001: Kafka から Databricks への取り込み

### ステータス: 確認済み — 本番対応パターン

### 調査結果

1. **Structured Streaming + Delta Lake** は Databricks 上のファーストクラスかつ本番実績のあるパターン。(REF-001, REF-002, REF-003)

2. **正確に1回のセマンティクス** は Kafka から Delta テーブルへの書き込み時に保証される。Delta Lake トランザクションログが並行ストリームでも冪等書き込みを提供。(REF-002, REF-004)

3. **Unity Catalog ガバナンス** はストリーミングワークロードで完全サポート。Structured Streaming は UC に登録されたマネージドテーブルと外部テーブルの両方に書き込み可能。(REF-001)

4. **スキーマ進化** は Delta Lake のスキーマ進化機能（mergeSchema、schema auto-merge）でサポート。

5. **チェックポイントと復旧**: Structured Streaming はクラウドストレージ（S3）に保存されたチェックポイントで進捗を追跡。障害時は最終コミット済みオフセットから処理を再開。(REF-004)

6. **セキュリティ**: Kafka 認証に SASL_SSL、転送時暗号化に SSL をサポート。シークレット管理は Databricks secrets または AWS Secrets Manager 経由。(REF-003)

7. **Amazon MSK 統合**: Databricks は IAM 認証または SASL/SCRAM で MSK クラスターに接続。VPC ピアリングまたは AWS PrivateLink 経由のプライベート接続。(REF-003)

8. **Confluent Tableflow**（2025年10月 GA）は代替のマネージドアプローチ：Kafka トピックを Delta テーブルに自動的にマテリアライズし、Unity Catalog に登録。カスタムストリーミングパイプラインコード不要。(REF-005, REF-006, REF-007)

### 本番運用の考慮事項

| 懸念 | 軽減策 |
|------|--------|
| コンシューマーラグ | CloudWatch（MSK）+ Databricks ストリーミングメトリクスで監視 |
| 遅延到着データ | ウォーターマークベースの処理（設定可能な閾値） |
| スキーマ変更 | スキーマレジストリ + Delta Lake スキーマ進化 |
| リプレイ | コンシューマーオフセットリセットまたは特定の Kafka タイムスタンプから再開 |
| コスト | Databricks ストリーミングジョブコスト（DBU）+ MSK スループット |

### 確認済み事実

- Kafka → Structured Streaming → Delta Lake → Unity Catalog はサポート済みの GA 本番パターン
- 正確に1回の処理が保証される
- Amazon MSK（セルフマネージド・サーバーレス）で動作
- Confluent Cloud で動作

### 仮定

- MSK と Databricks ワークスペース VPC 間のネットワーク接続性（VPC ピアリングまたは PrivateLink が必要）
- MSK クラスターは Databricks ワークスペースと同一リージョン

---

## RES-002: ClickHouse から Databricks への統合

### ステータス: 確認済み — 実行可能だが二次パス

### 調査結果

1. **ClickHouse Spark Connector** が公式統合方法。DataSourceV2 API 上に構築、Catalog API と TableProvider（フォーマットベース）アクセスパターンの両方をサポート。(REF-010, REF-011)

2. **Databricks 固有ガイド** が ClickHouse ドキュメントに存在し、コネクターが Databricks Runtime で動作することを確認。(REF-010)

3. **JDBC フォールバック** もよりシンプルだがパフォーマンスは劣るアプローチとしてサポート。(REF-012)

4. **読み書きサポート**: コネクターは Databricks ノートブックおよびジョブから ClickHouse の読み書きをサポート。(REF-011)

5. **ユースケース**: ClickHouse は運用分析ソースとして機能。Databricks は定期的に ClickHouse から集計/キュレーション済みデータをプルして、エンリッチメント、ML 特徴量、履歴分析に利用可能。

6. **主要取り込みパスではない**: 本アーキテクチャでは Kafka が Databricks への主要取り込みパス。ClickHouse→Databricks は集計済み運用データのバッチ読み取り用の二次パス。

### 統合パターン

| パターン | 説明 | ユースケース |
|---------|------|-----------|
| ClickHouse からの Spark 読み取り | Databricks ジョブが Spark コネクター経由で ClickHouse テーブルを読み取り | 集計メトリクスのバッチインポート |
| JDBC 読み取り | Databricks ノートブックから直接 JDBC クエリ | アドホック分析、小規模データセット |
| ClickHouse → S3 エクスポート → Databricks | ClickHouse が S3 にエクスポート、Databricks が S3 から読み取り | 分離されたバッチ転送 |

### 確認済み事実

- ClickHouse Spark コネクターは Databricks で動作（ClickHouse がドキュメント化）
- JDBC 接続性がサポートされている
- 読み取り・書き込み操作の両方がサポート
- コネクターはオープンソースでコミュニティ保守

### 仮定

- ClickHouse と Databricks 間のネットワーク接続性（VPC ピアリングまたは同一 VPC）
- ClickHouse クラスターが Databricks ドライバー/エグゼキューターノードからアクセス可能
- コネクターバージョンと Databricks Runtime バージョンの互換性

### 未解決事項

- 大規模テーブルスキャン時のパフォーマンス特性（ClickHouse から Spark 経由）
- ClickHouse Spark コネクターが製造環境の本番で使用されているか

---

## RES-003: Unity Catalog 互換性

### ステータス: 確認済み — 重要な制限事項を特定

### 主要発見: S3 互換ストレージは非サポート

**Unity Catalog 外部ロケーションがサポートするのは:**
- ネイティブ Amazon S3（AWS 上）
- Azure Data Lake Storage Gen2（Azure 上）
- Google Cloud Storage（GCP 上）
- Cloudflare R2（クロスクラウド）

**非サポート:**
- S3 互換エンドポイント（MinIO、ONTAP S3、その他の S3 互換ストレージ）
- カスタム S3 エンドポイント
- 非標準バケット構成

(REF-020, REF-021, REF-022)

### 本アーキテクチャへの影響

| 側面 | 影響 |
|------|------|
| Delta Lake ストレージ | ネイティブ Amazon S3 を使用する必要あり |
| FSx for ONTAP の役割 | Unity Catalog 外部ロケーションとしては使用不可 |
| ペイロード参照 | Delta テーブルは FSx for ONTAP ペイロードへの URI/パスを格納するが、Delta データ自体は S3 上 |
| アーキテクチャ設計 | FSx for ONTAP と Unity Catalog はメタデータ参照で接続される別システム |

### マネージドテーブル vs 外部テーブル

| タイプ | ストレージ | ガバナンス | ライフサイクル |
|--------|----------|-----------|-------------|
| マネージドテーブル | UC 管理の S3 ロケーション | UC 完全ガバナンス | UC が作成/削除を管理 |
| 外部テーブル | ユーザー指定の S3 ロケーション | UC がメタデータを管理 | ユーザーがデータライフサイクルを管理 |
| ストリーミングテーブル | UC 管理のロケーション | UC 完全ガバナンス + ストリーミングサポート | 自動パイプライン |

### 確認済み事実

- S3 互換エンドポイントは Unity Catalog 外部ロケーションとして非サポート
- 本アーキテクチャは FSx for ONTAP を UC ストレージターゲットとして使用しないことが正しい
- Kafka → Structured Streaming → ネイティブ S3 上の UC マネージド/外部テーブルが正しいパターン
- FSx for ONTAP S3 アクセスポイントは Unity Catalog 統合には役立たない

### 仮定

- Databricks ワークスペースが S3 バケットと同一 AWS リージョンにデプロイ
- UC ストレージ資格情報用の IAM ロールが設定済み

---

## RES-004: FSx for ONTAP の役割

### ステータス: 確認済み — ペイロードストレージとして強い価値

### 検証したこと

| 機能 | 本アーキテクチャでの利点 |
|------|------------------------|
| マルチプロトコル（NFS/SMB/S3） | エッジデバイスは NFS/SMB で書き込み、下流 ML/AI は S3 API で読み取り |
| Snapshot | ペイロードデータのポイントインタイムリカバリ、ML 訓練用の一貫したビュー |
| SnapMirror | ペイロードデータのクロスリージョン DR |
| FlexClone | テスト/開発環境用のスペース効率の良いコピー |
| ONTAP S3 | ClickHouse コールドストレージ階層化ターゲット（S3 互換） |
| データ保護 | 追加ツールなしのエンタープライズグレード |

### アーキテクチャ上の役割

FSx for ONTAP は **ペイロードストレージレイヤー** として機能する — Delta Lake ストレージターゲットではない：

```
エッジデバイス ─── NFS/SMB ───→ FSx for ONTAP（ペイロード）
                                        ↑
                                 ClickHouse 階層化（ONTAP S3）
                                     
Kafka メッセージは FSx for ONTAP パスを指す payload_uri を含む
Delta テーブルは FSx for ONTAP を参照する payload_uri カラムを含む
Databricks は FSx for ONTAP に直接アクセスしない
```

### ネイティブ Amazon S3 との比較

| 要素 | FSx for ONTAP | ネイティブ S3 |
|------|--------------|-------------|
| プロトコル柔軟性 | NFS + SMB + S3 | S3 のみ |
| レイテンシ（ファイル操作） | 低（NFS/SMB） | 高め（S3 API） |
| データ保護 | Snapshot、SnapMirror、組み込み | バージョニング、レプリケーション、別途 |
| コスト | 高め（プロビジョンド容量 + スループット） | 低め（従量課金） |
| 運用複雑性 | 高め（SVM、ボリューム、エクスポート） | 低め（バケット、ポリシー） |
| Unity Catalog 互換性 | 外部ロケーションとして非互換 | 完全互換 |
| 製造エッジ互換性 | 優秀（PLC、SCADA 向け NFS/SMB） | 限定的（S3 SDK が必要） |

### 確認済み事実

- FSx for ONTAP S3 アクセスポイントは存在するが Unity Catalog には関係ない（UC は S3 互換エンドポイントをサポートしないため）
- FSx for ONTAP はマルチプロトコルエッジデバイス統合に明確な価値を追加
- ClickHouse は階層化/コールドデータに S3 互換ストレージをサポート（ONTAP S3 は有効なターゲット）
- Snapshot/SnapMirror/FlexClone は S3 単独では利用できない運用データ保護を提供

### 未解決事項

- ClickHouse から ONTAP S3 への階層化のパフォーマンス特性（PoC での検証が必要）
- エッジデバイスペイロードアップロードの最適プロトコル（NFS vs SMB vs ONTAP S3 — エッジデバイスの機能に依存）

---

## RES-005: 非構造化データハンドリング

### ステータス: 確認済み — メタデータ/ペイロード分離は標準パターン

### 推奨パターン

メタデータ/ペイロード分離パターンは製造データプラットフォームで確立されている：

1. **軽量メタデータ**（イベントタイプ、タイムスタンプ、device_id、payload_uri、content_type、size、checksum）は Kafka を通過
2. **大容量ペイロード**（画像、動画、ドキュメント）は FSx for ONTAP に直接格納
3. **Delta テーブル** はキュレーション済みメタデータと payload_uri 参照を格納
4. **下流 AI/ML** は必要時に FSx for ONTAP からペイロードに直接アクセス（NFS マウントまたは S3 API 経由）

### ガバナンスへの影響

- **リネージ**: Unity Catalog は Delta テーブル内の構造化データのリネージを追跡。ペイロードのリネージにはカスタムメタデータが必要。
- **アクセス制御**: UC は Delta テーブルアクセスを管理。ペイロードアクセスは FSx for ONTAP 権限で別途管理。
- **監査**: UC 監査ログは Delta テーブルへのクエリを追跡。ペイロードアクセス監査は ONTAP 監査ログ経由。

### 確認済み事実

- ペイロードを Delta Lake にコピーする必要はない
- Delta テーブルは URI カラム経由で外部ペイロードを参照可能
- これは IoT/製造アーキテクチャの標準パターン
- 構造化メタデータと非構造化ペイロードのガバナンスは異なるシステムが担当

---

## RES-006: 公開リファレンスパターン

### ステータス: 複数の関連リファレンスを発見

### 製造 + Kafka + ClickHouse

| リファレンス | 主要パターン | 関連性 |
|------------|------------|--------|
| Critical Manufacturing (REF-030) | SQL Server → ClickHouse 移行、Kafka ベース取り込み、リアルタイム工場フロアダッシュボード | Kafka + ClickHouse の直接的な製造リファレンス |
| EMQ Industrial IoT (REF-032) | MQTT → ClickHouse Cloud、1000+ エンタープライズ顧客、高スループット産業分析 | エッジ/IoT から ClickHouse パターンの検証 |
| Kafka as Data Historian (REF-033) | IIoT における従来型データヒストリアンの Kafka 代替、OEE、デジタルツイン概念 | Industry 4.0 アーキテクチャコンテキスト |

### 確認済み事実

- Kafka + ClickHouse による製造分析は実績のある本番パターン
- Kafka → Databricks + Unity Catalog は実績のある本番パターン
- 3つの組み合わせ（Kafka + ClickHouse + Databricks）はアーキテクチャとして健全だが単一リファレンスとしての文書化は少ない
- FSx for ONTAP をレイクハウスとペイロードストアとして併用するのは新規だが妥当なパターン

---

## RES-007: AWS 上の ClickHouse デプロイ

### ステータス: 確認済み — 複数の実行可能なオプション

| オプション | タイプ | 主要特徴 |
|----------|--------|---------|
| ClickHouse Cloud | フルマネージド | ゼロ運用、自動スケーリング、S3 バックエンド、AWS Marketplace |
| ClickHouse BYOC | 利用者の VPC でマネージド | データは利用者の VPC 内、EKS ベース、S3 ストレージ |
| セルフマネージド（EC2） | 自主運用 | フルコントロール、手動スケーリング、ZooKeeper/Keeper |
| セルフマネージド（EKS） | K8s 上で自主運用 | コンテナベース、Helm チャート利用可能 |
| AWS ソリューション（CloudFormation） | AWS 提供テンプレート | EC2 + ZooKeeper + ELB リファレンスデプロイ |

### PoC への推奨

**ClickHouse Cloud** または **BYOC** が運用オーバーヘッド最小化に最適。コストが主要な懸念事項の場合は EC2 でのセルフマネージドも許容。

### ClickHouse S3 階層化ストレージ

ClickHouse は S3 および S3 互換ストレージを階層化/コールドデータ用のネイティブディスクタイプとしてサポート：

- **S3BackedMergeTree**: S3 をバックエンドストレージとする MergeTree エンジンバリアント
- **階層化ストレージポリシー**: ホットデータはローカル SSD、コールドデータは S3 に自動移動
- **S3 互換サポート**: MinIO、GCS、Cloudflare R2、その他の S3 互換エンドポイントの動作確認済み

**含意**: ClickHouse は ONTAP S3 プロトコル経由で FSx for ONTAP にコールドデータを階層化可能。これにより：
- ClickHouse コールドデータとエッジペイロードの統合ストレージ
- ClickHouse コールド階層に対する ONTAP データ保護（Snapshot/SnapMirror）
- 履歴分析データの EBS 比でのコスト最適化

(REF-042, REF-043)
