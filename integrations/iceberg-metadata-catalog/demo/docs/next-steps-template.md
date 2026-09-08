# Next Steps — After the Demo

🌐 [日本語](#日本語版) | [English](#english-version)

---

<a id="english-version"></a>

## English Version

### Thank You for Attending

Thank you for your time today. Below are the recommended next steps to move from demo to production value.

---

### Action Items

| # | Action | Owner | Timeline |
|---|--------|-------|----------|
| 1 | Share demo recording with stakeholders | [Customer Contact] | This week |
| 2 | Identify 1-2 priority use cases | [Customer Team] | 1 week |
| 3 | Estimate data volume for PoC | [Customer IT/Storage] | 1 week |
| 4 | Submit PoC application (see below) | [Customer Contact] | 2 weeks |
| 5 | PoC environment provisioning | [NetApp + AWS] | 2-3 weeks |
| 6 | PoC execution & validation | [Joint team] | 4-6 weeks |
| 7 | Production planning & sizing | [Joint team] | After PoC |

---

### PoC Application Process

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Interest   │───▶│  PoC Plan   │───▶│  Execution  │───▶│ Production  │
│  Confirmed  │    │  & Sizing   │    │  (4-6 wks)  │    │  Deployment │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
     Week 1            Week 2-3           Week 4-9          Week 10+
```

**PoC scope (recommended)**:
- 1 FSx for ONTAP volume (existing or new)
- 1,000-10,000 files for metadata cataloging
- 2-3 query patterns to validate
- 1 AI enrichment workflow (classification or summarization)

---

### Data Requirements for PoC

Please prepare the following information:

| Item | Details |
|------|---------|
| **Data volume** | Total TB of unstructured data |
| **File count** | Approximate number of files |
| **File types** | Primary formats (PDF, DOCX, images, CAD, etc.) |
| **Access patterns** | Who queries, how often, what they search for |
| **Compliance needs** | GDPR, SOX, HIPAA, industry-specific |
| **Existing storage** | Current NAS/SAN/object storage setup |
| **Analytics platform** | Databricks, Snowflake, AWS native, or other |
| **Network** | VPC connectivity, Direct Connect availability |

---

### Timeline Expectations

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Planning | 1-2 weeks | PoC design document, success criteria |
| Provisioning | 1-2 weeks | FSx for ONTAP + S3 Tables + compute |
| Data onboarding | 1 week | Sample data loaded, metadata scanned |
| Validation | 2-3 weeks | Query performance, AI enrichment, governance |
| Report | 1 week | Results, recommendations, production sizing |

**Total PoC duration: 6-9 weeks**

---

### Contact Information

| Role | Name | Email | Phone |
|------|------|-------|-------|
| Solutions Architect | [SA Name] | [email] | [phone] |
| Account Manager | [AM Name] | [email] | [phone] |
| Technical Support | — | [support email] | — |
| Partner/SI Contact | [Partner Name] | [email] | [phone] |

---

### Resources

- Demo recording: [link to asciinema/video]
- Architecture diagram: [link]
- Pricing calculator: [link]
- Documentation: [GitHub repo link]

---

<a id="日本語版"></a>

## 日本語版

### デモご参加への御礼

本日はお時間をいただきありがとうございました。デモから本番環境での価値実現に向けた推奨ネクストステップを以下にまとめます。

---

### アクションアイテム

| # | アクション | 担当 | 期限 |
|---|-----------|------|------|
| 1 | デモ録画を関係者に共有 | [お客様ご担当者] | 今週中 |
| 2 | 優先ユースケースを1-2件特定 | [お客様チーム] | 1週間 |
| 3 | PoC用データ量の見積もり | [お客様IT/ストレージ担当] | 1週間 |
| 4 | PoC申請書の提出（下記参照） | [お客様ご担当者] | 2週間 |
| 5 | PoC環境のプロビジョニング | [NetApp + AWS] | 2-3週間 |
| 6 | PoC実施・検証 | [合同チーム] | 4-6週間 |
| 7 | 本番計画・サイジング | [合同チーム] | PoC後 |

---

### PoC申請プロセス

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  興味確認   │───▶│  PoC計画    │───▶│  実施       │───▶│  本番展開   │
│             │    │  & サイジング│    │  (4-6週間)  │    │             │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
     1週目           2-3週目            4-9週目           10週目以降
```

**PoC推奨スコープ**:
- FSx for ONTAP ボリューム 1つ（既存または新規）
- メタデータカタログ化対象ファイル: 1,000〜10,000件
- 検証するクエリパターン: 2-3種類
- AI エンリッチメントワークフロー 1つ（分類または要約）

---

### PoC用データ要件

以下の情報をご準備ください：

| 項目 | 詳細 |
|------|------|
| **データ量** | 非構造化データの総TB数 |
| **ファイル数** | おおよそのファイル数 |
| **ファイル形式** | 主要フォーマット（PDF、DOCX、画像、CAD等） |
| **アクセスパターン** | 誰が、どのくらいの頻度で、何を検索するか |
| **コンプライアンス要件** | 個人情報保護法、業界固有規制 |
| **既存ストレージ** | 現在のNAS/SAN/オブジェクトストレージ構成 |
| **分析プラットフォーム** | Databricks、Snowflake、AWS ネイティブ、その他 |
| **ネットワーク** | VPC接続性、Direct Connect利用可否 |

---

### タイムライン目安

| フェーズ | 期間 | 成果物 |
|---------|------|--------|
| 計画 | 1-2週間 | PoC設計書、成功基準 |
| プロビジョニング | 1-2週間 | FSx for ONTAP + S3 Tables + コンピュート |
| データオンボーディング | 1週間 | サンプルデータ投入、メタデータスキャン |
| 検証 | 2-3週間 | クエリ性能、AIエンリッチメント、ガバナンス |
| レポート | 1週間 | 結果、推奨事項、本番サイジング |

**PoC総期間: 6-9週間**

---

### 連絡先

| 役割 | 氏名 | メール | 電話 |
|------|------|--------|------|
| ソリューションアーキテクト | [SA名] | [email] | [phone] |
| アカウントマネージャー | [AM名] | [email] | [phone] |
| テクニカルサポート | — | [サポートメール] | — |
| パートナー/SI担当 | [パートナー名] | [email] | [phone] |

---

### 参考資料

- デモ録画: [asciinema/動画リンク]
- アーキテクチャ図: [リンク]
- 料金計算ツール: [リンク]
- ドキュメント: [GitHubリポジトリリンク]
