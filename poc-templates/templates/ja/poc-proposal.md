🌐 [English](../poc-proposal.md) | **日本語**

# PoC 提案書: FSx for ONTAP S3 Access Points × 分析

## 宛先: [顧客名]
## 作成: [パートナー名]
## 日付: [YYYY-MM-DD]

---

## エグゼクティブサマリー

[顧客] は [X TB] のエンタープライズファイルデータを [FSx for ONTAP / オンプレミス ONTAP] に保存しています。現在、分析にはこのデータを S3 にコピーする必要があり、重複ストレージ、データの陳腐化、パイプライン保守のオーバーヘッドが発生しています。

**提案ソリューション**: FSx for ONTAP で S3 Access Points を有効化し、既存ファイルデータへの直接 S3 API アクセスを提供。分析プラットフォーム（Athena、Snowflake、Databricks、EMR）がデータをその場でクエリ — コピーなし、同期パイプラインなし、重複ストレージなし。

**期待される成果**: データ鮮度ラグの排除（24時間 → ほぼゼロ）、[N] 個のコピーパイプライン削除、重複ストレージで ~$[X]/月の削減。

---

## ビジネス課題

| 現在の課題 | 影響 | 根本原因 |
|-----------|------|---------|
| データ鮮度ラグ | 陳腐なデータに基づく意思決定 | S3 への夜間バッチコピー |
| 重複ストレージコスト | $___/月の S3 コピー | 分析に S3 が必要 |
| パイプライン保守 | ___h/月の運用オーバーヘッド | 同期パイプラインの障害 |
| ガバナンスの断片化 | NAS と S3 で別々の制御 | 2つのアクセスパス |

---

## 提案ソリューション

```
Before: NFS/SMB → [コピーパイプライン] → S3 → 分析プラットフォーム
After:  NFS/SMB ←→ FSx for ONTAP ←→ S3 Access Point → 分析プラットフォーム
                    (同じデータ、同じボリューム、ゼロコピー)
```

---

## PoC スコープ

| 項目 | スコープ |
|------|---------|
| 期間 | [1日 / 1週間 / 2週間] |
| データ | [サンプル / 本番のサブセット] |
| エンジン | [Athena / Snowflake / Databricks / EMR] |
| ガバナンス | [IAM のみ / Lake Formation / Snowflake Tags] |
| AI/ML | [なし / Cortex AI / Bedrock KB] |
| 成功基準 | [添付の success-criteria.md 参照] |

---

## 成果物

| # | 成果物 | タイムライン |
|---|--------|-----------|
| 1 | S3 Access Point 設定・検証完了 | 1日目 |
| 2 | 選択エンジンからの最初の成功クエリ | 1日目 |
| 3 | ガバナンス制御の適用・テスト | 2日目 |
| 4 | パフォーマンスベンチマーク（レイテンシ、スループット） | 2-3日目 |
| 5 | AI/ML デモ（スコープ内の場合） | 3-4日目 |
| 6 | エビデンス付き Go/No-Go 推奨 | 最終日 |
| 7 | アーキテクチャ推奨付き Post-PoC レポート | +2日 |

---

## コスト

| コンポーネント | 見積もりコスト |
|------------|------------|
| AWS インフラ（PoC 期間） | ~$[X] |
| パートナープロフェッショナルサービス | [X] 日 × $[レート] |
| **PoC 投資合計** | **$[X]** |

詳細は [cost-estimate.md](cost-estimate.md) を参照。

---

## 期待 ROI（PoC 後の本番）

| 指標 | 現状 | 導入後 | 年間削減 |
|------|------|-------|---------|
| 重複 S3 ストレージ | $___/月 | $0 | $___/年 |
| パイプライン保守 | ___h/月 | 0h | ___h/年 |
| データ鮮度 | ___時間 | ほぼゼロ | — |
| インサイトまでの時間 | ___日 | ___時間 | — |

---

## リスク軽減

| リスク | 軽減策 |
|--------|-------|
| NFS/SMB ワークロードへの FSx スループット影響 | PoC 中に測定; ロールバック = AP ポリシー取り消し |
| プラットフォームが S3 AP を非サポート | [ブログシリーズ](https://github.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations#blog-series--ブログシリーズ)で検証済み; フォールバック = DataSync |
| ガバナンス要件を満たせない | Lake Formation (AWS) または Snowflake Tags で細粒度制御を提供 |
| PoC データに機密情報を含む | 合成データを使用; 承認後のみ実データ |

---

## 次のステップ

1. [ ] 顧客が PoC スコープとタイムラインを確認
2. [ ] パートナーが基盤インフラをデプロイ（1日目午前）
3. [ ] 最初のクエリ成功（1日目午後）
4. [ ] ガバナンスと AI 検証（2-3日目）
5. [ ] Go/No-Go 判断ミーティング（最終日）

---

## 参考資料

- [GitHub: fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations)
- [AWS: FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [ブログシリーズ: 7パート検証](https://github.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations#blog-series--ブログシリーズ)
