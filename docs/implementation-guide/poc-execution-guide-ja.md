🌐 [English](./poc-execution-guide.md) | **日本語**

# PoC 実行ガイド: FSx for ONTAP AI メタデータカタログ

> AI メタデータカタログパイプラインのデプロイと検証のためのステップバイステップチェックリスト。

---

## 前提条件

| 要件 | 詳細 |
|------|------|
| AWS アカウント | FSx for ONTAP、Lambda、Bedrock、S3 Tables、OpenSearch の権限 |
| FSx for ONTAP | 既存環境または新規プロビジョニング |
| Bedrock モデルアクセス | 対象リージョンで有効化（Claude + Titan Embeddings） |
| ネットワーク接続性 | VPC ピアリング/エンドポイントの検証済み |
| サンプルファイル | 代表的なファイル 100–1,000 件を特定 |

---

## 実装タイムライン

### Phase 1: インフラストラクチャ（1–2 日）

- FSx for ONTAP デプロイ（または既存環境の検証）
- S3 Access Point 設定
- S3 Tables (Iceberg) ネームスペース作成
- Lambda 関数と IAM ロールのデプロイ
- ネットワーク接続性の検証（VPC、セキュリティグループ）

### Phase 2: AI パイプライン（2–3 日）

- FSx for ONTAP に FPolicy を設定
- Bedrock 連携の分類パイプラインをデプロイ
- 対象ファイル種別向けの分類テンプレート設定
- OpenSearch Serverless コレクション構築
- 既存ファイルの初期バッチ処理実行
- AI 分類精度を検証

### Phase 3: 検索・分析インターフェース（1–2 日）

- Athena ワークグループと保存クエリの設定
- OpenSearch Dashboards（検索 UI）のデプロイ
- Lake Formation ガバナンスポリシーの設定
- 対象ユースケース用ダッシュボード作成
- 受入テストの実施

**合計: 5–7 営業日**（キックオフから稼働まで）

---

## 実行チェックリスト

### デプロイ前（Day 0）

- [ ] PoC スコープと成功基準を定義
- [ ] AWS アカウント ID とリージョンを確認
- [ ] FSx for ONTAP 環境が利用可能（または新規プロビジョニング）
- [ ] サンプルファイルを特定（代表的なファイル 100–1,000 件）
- [ ] ネットワーク接続性を検証（VPC ピアリング/エンドポイント）
- [ ] 対象リージョンで Bedrock モデルアクセスを有効化

### Phase 1: デプロイ（Day 1–2）

- [ ] CloudFormation スタックのデプロイ成功
- [ ] S3 Access Point の検証（FSx for ONTAP からファイル読み取り可能）
- [ ] Lambda 関数をサンプルファイルでテスト
- [ ] S3 Tables ネームスペースを作成し Athena からアクセス確認

### Phase 2: パイプライン（Day 3–5）

- [ ] FPolicy 設定完了、イベントが流れていることを確認 — **PoC が NFS / SMB で書き込む場合に限る。** S3 access point 経由で届いた書き込みは FPolicy 通知を一切発火しない（2026-08-26 実測、ONTAP 9.18.1P3D1。構造的な理由は 9.18.1P5 で再確認済み）。S3 API で書く PoC ではこの条件は達成不能なので、ポーリングまたは監査ログの経路を使う
- [ ] サンプルファイルで AI 分類が実行されている
- [ ] 分類精度をレビュー（目標: >85%）
- [ ] OpenSearch インデックスにデータが投入されている
- [ ] ベクトル埋め込みが生成されている

### Phase 3: 検証（Day 6–7）

- [ ] Athena SQL でファイル検索可能を確認
- [ ] OpenSearch UI でファイル検索可能を確認
- [ ] PII 検出の検証（該当する場合）
- [ ] パイプラインパフォーマンスを計測（目標: 単一ファイル 42 秒）
- [ ] コスト予測を [コスト見積もり](../adoption-guide/cost-estimation-ja.md) と照合

### PoC 後

- [ ] 計測メトリクスとともに結果を文書化
- [ ] ファイル種別ごとの精度評価
- [ ] ギャップとチューニング要件を特定
- [ ] 本番スケーリング考慮事項を文書化

---

## 成功基準

| メトリクス | 目標 | 計測方法 |
|-----------|------|---------|
| パイプラインレイテンシ | <60 秒（単一ファイル） | CloudWatch Lambda duration |
| 分類精度 | 信頼度平均 >85% | サンプルセットの手動レビュー |
| 検索可用性 | ファイル作成から 2 分以内に検索可能 | エンドツーエンドタイミングテスト |
| FPolicy 影響 | 付加レイテンシ <5ms | NAS クライアント I/O 計測 |
| ファイルあたりコスト | 見積もりの 2 倍以内 | CloudWatch + Cost Explorer |

---

## よくある問題とトラブルシューティング

| 問題 | 考えられる原因 | 解決策 |
|------|-------------|--------|
| S3 AP が AccessDenied を返す | IAM ポリシーまたは S3 AP ポリシーの設定ミス | Lambda ロールが AP ARN に対し `s3:GetObject` を持つか確認 |
| FPolicy イベントが流れない | **まずデータの書き込み経路を確認する。** S3 access point 経由の書き込みは FPolicy 通知を一切発火せず、これは設定ミスではなく期待された挙動である。それ以外なら、エンジン未接続またはスコープが狭すぎる | 先に書き込み経路を確定し、その後 `vserver fpolicy show` とイベントスコープを確認 |
| Bedrock タイムアウト | ファイルが大きすぎるかプロンプトが複雑すぎる | ファイルサイズ制限を下げるかプロンプトを簡素化 |
| OpenSearch インデックスが空 | 埋め込みパイプラインがサイレントに失敗 | Lambda CloudWatch ログでエラーを確認 |
| Athena クエリが 0 行を返す | S3 Tables ネームスペースまたはテーブルが未登録 | Athena ワークグループで `SHOW TABLES` を確認 |
| FPolicy レイテンシが高い | 同期モードまたはネットワークボトルネック | 許容可能なら非同期 FPolicy に切り替え |

---

## CloudFormation クイックデプロイ

```bash
# フルスタックをデプロイ（単一コマンド）
aws cloudformation deploy \
  --template-file integrations/iceberg-metadata-catalog/cloudformation/template.yaml \
  --stack-name fsxontap-metadata-catalog \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    FsxFileSystemId=fs-0123456789abcdef0 \
    SvmId=svm-0123456789abcdef0 \
    S3AccessPointAlias=your-ap-alias-s3alias \
    BedrockModelId=anthropic.claude-3-5-sonnet-20241022-v2:0
```

---

## 関連ドキュメント

| ドキュメント | 内容 |
|------------|------|
| [テクニカルオーバービュー](../adoption-guide/technical-overview-ja.md) | アーキテクチャと検証メトリクス |
| [テクニカル FAQ](../adoption-guide/technical-faq-ja.md) | 制約と統合に関する詳細 Q&A |
| [コスト見積もり](../adoption-guide/cost-estimation-ja.md) | コンポーネント別コスト内訳 |
| [アーキテクチャ比較](../adoption-guide/architecture-comparison-ja.md) | アプローチ選定のための判断フレームワーク |

---

*最終更新: 2026-06*
