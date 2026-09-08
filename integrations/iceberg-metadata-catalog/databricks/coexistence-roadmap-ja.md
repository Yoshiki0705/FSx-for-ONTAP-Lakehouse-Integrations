# Databricks + AWS 共存ロードマップ

🌐 日本語 | [English](coexistence-roadmap.md)

## 目的

AWS ネイティブ分析（Athena、Lake Formation）と Databricks（Unity Catalog、SQL、ML）の両方を使用する組織向けの段階的統合計画。

## フェーズ

### Phase 1: AWS ネイティブメタデータカタログ（現在）

```
FSx for ONTAP → S3 AP → Lambda/Bedrock → S3 Tables (Iceberg)
                                              │
                                    ┌─────────┼─────────┐
                                    ▼         ▼         ▼
                              Athena ✅   OpenSearch  Lake Formation
```

- **ステータス**: ✅ 検証済み
- **ガバナンス**: Lake Formation（テーブルレベル）
- **検索**: OpenSearch Serverless NextGen (kNN)
- **コスト**: 10万ファイルで ~$114/月

### Phase 2: Databricks メタデータアクティベーション

```
S3 Tables (Iceberg) ──PyIceberg export──→ S3 (Parquet/Delta)
                                              │
                                              ▼
                                    UC External Location
                                              │
                                              ▼
                                    Databricks SQL / AI BI
```

- **ステータス**: 今すぐ利用可能（プラットフォーム依存なし）
- **ガバナンス**: 同期テーブルに対する Unity Catalog grants
- **ユースケース**: ダッシュボード、AI/BI Genie、ML 特徴量、運用レポート
- **トレードオフ**: メタデータコピー（小規模、~MB）; 生ファイルはゼロコピー維持

### Phase 3: UC Foreign Catalog 検証

```
S3 Tables (Iceberg) ←──Glue Iceberg REST──→ UC Foreign Catalog
                                              │
                                              ▼
                                    Databricks SQL / Spark
                                    (読み取り専用、REFRESH 必要)
```

- **ステータス**: 🔄 検証待ち (B-4/B-5)
- **ガバナンス**: Foreign tables に対する UC ガバナンス
- **利点**: データコピーなし、フォーマット変換なし
- **制約**: 読み取り専用、自動リフレッシュなし、credential vending なし

### Phase 4: Databricks ファーストオプション（該当する場合）

```
FSx for ONTAP → DataSync → S3 → UC Managed Iceberg / Delta + UniForm
                                              │
                                    ┌─────────┼─────────┐
                                    ▼         ▼         ▼
                              Databricks   Athena    外部
                              SQL/Spark    (Glue     Iceberg
                                           federation) クライアント
```

- **ステータス**: アーキテクチャオプション（本 PoC では未検証）
- **ガバナンス**: Unity Catalog（主系）+ AWS エンジン向け Glue federation
- **最適**: Databricks を主要プラットフォームとして標準化する組織
- **トレードオフ**: 生ファイル取り込みに DataSync が必要; UC が権威カタログ

## 判断基準

| 要素 | AWS ファースト (Phase 1-2) | Databricks ファースト (Phase 4) |
|---|---|---|
| 主要クエリエンジン | Athena | Databricks SQL |
| 主要ガバナンス | Lake Formation | Unity Catalog |
| リネージ/ディスカバリ | Glue Data Catalog | UC Explorer |
| ML/AI プラットフォーム | SageMaker / Bedrock | Databricks ML / MLflow |
| コストモデル | クエリ課金 (Athena) | DBU ベース (Databricks) |
| 生ファイルアクセス | S3 AP（直接） | DataSync → S3 → UC |
| クロスプラットフォーム | Iceberg REST（オープン） | UC Iceberg REST + Glue federation |

## 推奨開始ポイント

1. **Phase 1 から開始**（AWS ネイティブ）— 最低障壁、完全検証済み
2. **Phase 2 を追加** Databricks BI/ML が必要な場合 — プラットフォーム依存なし
3. **Phase 3 を検証** UC Foreign Catalog の互換性が Databricks のドキュメントに記載されてから
4. **Phase 4 を検討** 組織が Databricks を主要プラットフォームとして標準化する場合のみ

## 参考資料

- [AWS Glue → UC フェデレーション](https://docs.aws.amazon.com/lake-formation/latest/dg/catalog-federation-databricks.html)
- [Databricks → AWS Glue フェデレーション](https://docs.databricks.com/aws/en/query-federation/hms-federation-glue)
- [UC Foreign Iceberg 検証計画](uc-foreign-iceberg-validation-ja.md)
