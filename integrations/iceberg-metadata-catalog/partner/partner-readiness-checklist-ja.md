# パートナー準備チェックリスト

🌐 日本語 | [English](partner-readiness-checklist.md)

## 目的

利用者の環境で Iceberg メタデータカタログパターンをデプロイするパートナー向けの事前確認チェックリスト。

## FSx for ONTAP

- [ ] FSx デプロイタイプ（Single-AZ / Multi-AZ）
- [ ] SVM 名とプロトコル設定
- [ ] ボリューム ID（カタログ対象ボリューム）
- [ ] スループットキャパシティ（プロビジョニング済み）
- [ ] SSD ストレージ容量と IOPS
- [ ] キャパシティプールティアリングポリシー
- [ ] NFS/SMB プロトコル使用状況とクライアント数
- [ ] Active Directory 統合（Windows ACL の場合）
- [ ] 既存の FPolicy 設定（ある場合）

## S3 Access Point

- [ ] ボリュームごとの Access Point（または共有）
- [ ] IAM ポリシー（許可されたプリンシパル）
- [ ] 関連付けられたファイルシステム ID（UNIX UID/GID または Windows ドメイン\\ユーザー）
- [ ] VPC 制限（該当する場合）
- [ ] 想定リクエストレート（同時スキャン数）
- [ ] プレフィックススコープ（公開するパス）

## メタデータカタログ

- [ ] ファイル ID 方式（パスハッシュ / inode / コンテンツハッシュ）
- [ ] latest-record ビュー作成済み
- [ ] パス機密性ポリシー定義済み
- [ ] 保持ポリシー定義済み
- [ ] DR 再バインドポリシー（SnapMirror の場合）
- [ ] ドメインメタデータ拡張の必要性（製造業、金融等）

## AI エンリッチメント

- [ ] Bedrock モデルアクセス有効化（Claude Haiku + Titan Embeddings）
- [ ] Vision 分類が必要なファイルタイプ
- [ ] バックフィルボリューム見積もり（ファイル数 × エンリッチメント率）
- [ ] Batch Inference vs リアルタイムの判断
- [ ] 人間レビューワークフロー定義済み

## 運用

- [ ] CloudWatch ダッシュボード（Lambda + SQS + FSx メトリクス）
- [ ] FPolicy イベント設計（create/close/rename/delete のみ）
- [ ] バックフィル同時実行数制限
- [ ] Iceberg メンテナンススケジュール
- [ ] OpenSearch コレクション作成済み（ベクトル検索が必要な場合）
- [ ] SnapMirror / DR 動作の文書化

## ガバナンス

- [ ] Lake Formation グラント設定済み
- [ ] カラム公開制御用 Athena Views
- [ ] PII 検出言語（EN / JA / その他）
- [ ] 監査ログ保持（CloudTrail Trail → S3）
- [ ] 承認エビデンステンプレート完了
