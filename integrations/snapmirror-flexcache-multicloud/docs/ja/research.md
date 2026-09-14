> 🌐 Language: **日本語** | [English](../en/research.md)
# S3 AP + SnapMirror + FlexCache マルチクラウドデータ配信 — 調査結果

> **ステータス**: Phase 3 検証完了 | Cross-Region SnapMirror 検証済み (2026-07-22)
> **最終更新**: 2026-07-22
> **対象**: FSx for ONTAP S3 Access Point 経由で収集されたデータの SnapMirror/FlexCache によるマルチクラウド配信

---

## Executive Summary

本調査は、FSx for ONTAP S3 AP（S3 Access Point）経由で収集されたデータを SnapMirror および FlexCache によりマルチクラウド環境へ配信し、宛先で NFS/SMB 認証アクセスを実現するユースケースのフィージビリティを体系的に評価したものである。

### 調査結果サマリー

| 分類 | 件数 | 説明 |
|------|:----:|------|
| **supported**（サポート確認済み） | 32 | 公式ドキュメントまたは技術的根拠・検証エビデンスによりサポートが確認された項目 |
| **partially_supported**（条件付きサポート） | 3 | 特定条件下でのみサポート、またはプラットフォーム依存の制約あり |
| **works_with_caveats**（動作するが注意事項あり） | 2+4 | 動作確認済みだが重要な注意事項・リスクが存在する項目（原 2 件 + cross-region 検証 4 件） |
| **version_gated**（バージョン依存） | 1 | ONTAP 9.18.1 以降でサポート。検証環境（9.17.1）では非サポート |
| **undocumented — validation required**（未文書化、検証必要） | 1 | 公式ドキュメントに記載なし、実機検証で確定が必要な項目 |
| **unsupported**（非サポート） | 2 | 明示的に非サポートが確認された項目 |
| **合計** | **41** | |

### 主要結論

FSx for ONTAP S3 AP は ONTAP の「S3 NAS bucket（S3 multiprotocol）」メカニズムに基づいており、ボリューム自体は通常の FlexVol/FlexGroup のままである。この設計により、S3 AP アタッチ済みボリュームは **SnapMirror Asynchronous（Volume-level）** で保護可能であり、マルチクラウドデータ配信の基盤として利用できることが確認された。一方、SnapMirror Synchronous および SVM-DR は S3 NAS bucket を含む構成では非サポートである。

FlexCache についても、ONTAP 9.12.1 以降で S3 NAS bucket が Origin Volume としてサポートされる旨が NetApp ドキュメントに記載されており、FSx for ONTAP S3 AP アタッチ済みボリュームを FlexCache Origin として利用する構成は技術的に実現可能と推定される。ただし FSx for ONTAP 固有の AWS マネージドレイヤーとの相互作用については実機検証が必要である。

### アーキテクチャ判断に影響する Top 3 Findings

1. **SVM-DR 非サポート（SM-004）**: S3 NAS bucket を持つ SVM では SVM-DR が使用できない。Volume-level SnapMirror が唯一の選択肢であり、デスティネーション SVM のプロトコル構成（CIFS、NFS export policy、name-mapping、Kerberos）は全て手動再構成が必要
2. **ANF への SnapMirror 非サポート（XC-007）**: Azure NetApp Files は外部 ONTAP からの SnapMirror を受け付けない。Azure へのデータ配信は CVO on Azure 経由が必要
3. **S3 AP メタデータは SnapMirror で転送されない（SM-002）**: S3 AP 自体は AWS マネージドリソースであり、デスティネーションでは新規 S3 AP アタッチが必要。IAM ポリシーも別途構成が必要

---

## Prerequisites & Constraints Summary

本セクションは、アーキテクチャ設計の迅速な判断を支援するための早見表である。

### 主要な制約（What doesn't work）

| 制約 | Finding ID | 影響 |
|------|:----------:|------|
| SVM-DR は S3 NAS bucket 搭載 SVM で非サポート | SM-004 | Volume-level SnapMirror のみ。SVM 構成の自動複製不可 |
| ANF への SnapMirror 非サポート | XC-007 | Azure 配信は CVO on Azure 経由が必須 |
| SnapMirror Synchronous は S3 NAS bucket で非サポート | SM-001 | RPO=0 は達成不可。Async（最短5分間隔）のみ |
| GCNV は FlexCache Origin 不可（Cache のみ） | FCXC-005 | GCNV からの読み取り配信には SnapMirror が必要 |
| GCNV FlexCache は NFSv4 非サポート | FCXC-005 | GCNV Cache Volume へは NFSv3 アクセスのみ |
| FlexCache write-back は RTT > 200ms で非推奨 | FCXC-006 | クロスクラウド構成では write-around mode を推奨 |

### 主要な前提条件（What you need）

| 前提条件 | 対象パス | 詳細 |
|---------|---------|------|
| Intercluster LIF | SnapMirror / FlexCache 全パス | FSx for ONTAP 側は自動構成。On-premises / CVO は手動構成 |
| Cluster Peering（TLS 1.2 暗号化） | 全クロスクラスター構成 | ONTAP 9.6+ でデフォルト有効 |
| VPN / Direct Connect / Interconnect | On-premises / CVO / GCNV 宛て | TCP 11104, 11105 + ICMP の到達性必須 |
| Active Directory（SMB アクセス時） | デスティネーション SVM | SMB/CIFS アクセスには AD 参加必須。同一ドメインまたは Trust 関係 |
| ONTAP 9.15.1+（Origin/Cache 双方） | FlexCache write-back mode | 9.17.1P1 以降を推奨 |
| ONTAP 9.12.1+（Origin） | S3 NAS bucket + FlexCache | S3 NAS bucket を Origin にする最低要件 |
| ONTAP 9.11.1+（FSx for ONTAP） | SnapMirror Async | FSx for ONTAP 初期リリースバージョン |

### サポート構成クイックリファレンス

| ソース | 宛先 | SnapMirror | FlexCache | 備考 |
|--------|------|:----------:|:---------:|------|
| FSx for ONTAP | FSx for ONTAP（同一リージョン） | ✅ | ✅ | 最もシンプルな構成 |
| FSx for ONTAP | FSx for ONTAP（別リージョン） | ✅ | ✅ | VPC Peering / Transit Gateway 必要 |
| FSx for ONTAP | On-premises ONTAP | ✅ | ✅ | Direct Connect / VPN 必要 |
| FSx for ONTAP | CVO on GCP | ✅ | ✅ | Cross-cloud VPN 必要 |
| FSx for ONTAP | CVO on Azure | ✅ | ✅ | Cross-cloud VPN 必要 |
| FSx for ONTAP | GCNV | ✅ | ✅（Cache のみ） | External Replication / FlexCache Cache |
| FSx for ONTAP | ANF | ❌ | ❌ | 非サポート。CVO on Azure 経由で代替 |

### S3 NAS Bucket と FlexCache / SnapMirror の互換性

| 構成 | サポート | 最低バージョン | 公式ドキュメント |
|------|:--------:|:-------------:|----------------|
| S3 NAS bucket ボリュームを **SnapMirror Async ソース**に | ✅ | 9.12.1 | [S3 multiprotocol — Data protection](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html) |
| S3 NAS bucket ボリュームを **SnapMirror Synchronous ソース**に | ❌ | — | [S3 multiprotocol — Data protection](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html) |
| S3 NAS bucket を含む SVM で **SVM-DR** | ❌ | — | [S3 multiprotocol — Data protection](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html), [KB: SVM DR + S3](https://kb.netapp.com/onprem/ontap/dp/SnapMirror/Is_SVM_Disaster_Recovery_(SVM_DR)_of_S3_buckets_supported%3F) |
| S3 NAS bucket を **FlexCache Origin** ボリュームに | ✅ | 9.12.1 | [FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html) |
| S3 NAS bucket を **FlexCache Cache** ボリュームに | ⚠️ ONTAP ✅ / FSx AP ❌ | **9.18.1** | [FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html), [FlexCache duality FAQ](https://docs.netapp.com/us-en/ontap/flexcache/flexcache-duality-faq.html). ONTAP ネイティブ S3 NAS bucket は 9.18.1 でサポートだが、FSx for ONTAP S3 AP は FlexCache への アタッチを明示的にブロック（2026-07-24 検証） |
| FlexCache Cache S3 NAS bucket + **write-back mode** | ❌ | — | [FlexCache duality FAQ](https://docs.netapp.com/us-en/ontap/flexcache/flexcache-duality-faq.html)（write-around 必須） |
| FlexCache Cache S3 — Origin/Cache **双方 9.18.1+ 必須** | 必須 | 9.18.1 | [FlexCache duality FAQ](https://docs.netapp.com/us-en/ontap/flexcache/flexcache-duality-faq.html) |
| FlexCache Origin が **SnapMirror Async 関係を持つ**構成 | ✅ | 9.5+ | [FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html) |

---

## S3 AP + SnapMirror 相互作用

本セクションでは、FSx for ONTAP S3 AP がアタッチされたボリュームの SnapMirror レプリケーション可否、メタデータ保持、および DR 手順を調査した結果を記録する。

### アーキテクチャ前提

FSx for ONTAP S3 AP は、ONTAP の **S3 multiprotocol（S3 NAS bucket）** メカニズムに基づいている。これは ONTAP ネイティブの S3 object store server（`vserver object-store-server`）とは異なるアーキテクチャである。S3 AP は既存の NAS ボリュームに対して S3 プロトコルアクセスを提供する AWS マネージドレイヤーの機能であり、ボリューム自体は通常の FlexVol/FlexGroup ボリュームのままである。

この区別は SnapMirror 互換性において決定的に重要である。

---

### SM-001: S3 AP アタッチ済みボリュームの SnapMirror ソース対応

| 項目 | 内容 |
|------|------|
| **Finding ID** | SM-001 |
| **Requirement Ref** | Requirement 1, AC 1.1 |
| **分類** | `supported`（条件付き — SnapMirror Asynchronous のみ） |
| **公開分類** | publicly verifiable |

#### 調査結果

NetApp ONTAP 公式ドキュメント「Learn about ONTAP S3 multiprotocol support」の "Data protection for S3 NAS buckets" セクションに以下の記載がある:

> "S3 NAS 'buckets' are simply mappings of NAS data for S3 clients, they are not standard S3 buckets. Therefore, there is no need to protect S3 NAS buckets using NetApp SnapMirror S3 functionality. Instead, you can protect volumes containing S3 NAS buckets using **SnapMirror asynchronous volume replication**."

FSx for ONTAP S3 AP は S3 multiprotocol メカニズムを使用しているため、S3 AP がアタッチされたボリュームは通常の NAS ボリュームとして SnapMirror Asynchronous のソースになることが可能である。

#### 制約

- SnapMirror **Synchronous** は S3 NAS bucket を含むボリュームでは**非サポート**（同ドキュメントに明記: "SnapMirror synchronous ... not supported"）
- SnapMirror Asynchronous（スケジュールベース）のみサポート

#### エビデンス

- [NetApp Docs: Learn about ONTAP S3 multiprotocol support — Data protection for S3 NAS buckets](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html)
- [AWS Docs: Replicating your data using NetApp SnapMirror](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html)

---

### SM-002: S3 AP メタデータの SnapMirror 転送後保持状況

| 項目 | 内容 |
|------|------|
| **Finding ID** | SM-002 |
| **Requirement Ref** | Requirement 1, AC 1.2 |
| **分類** | `supported (validated)` |
| **公開分類** | validation evidence |

#### 調査結果

FSx for ONTAP S3 AP のメタデータは以下の2レイヤーで構成される:

1. **AWS レイヤー（S3 AP 本体）**: S3 access point attachment、IAM ポリシー、VPC configuration — これらは FSx API で管理される AWS リソースであり、ONTAP ボリュームのデータには含まれない
2. **ONTAP レイヤー（`s3_unix` name-mapping）**: FSx が S3 AP アタッチ時に SVM 上に自動作成する `direction: s3_unix` の name-mapping エントリ（パターン: `amazon-fsx-<RANDOM>` → 指定 UNIX ユーザー）

#### Phase 3 検証結果（TC-01/TC-02 で確認）

**検証により以下が確定:**

- S3 AP メタデータ（AP attachment 自体）は SnapMirror で**転送されない**（AWS マネージドリソースであるため）— これは期待される動作
- ONTAP レイヤーの `s3_unix` name-mapping は **SVM 構成の一部**であり、ボリュームレベル SnapMirror では転送されない（SVM レベルの設定）
- デスティネーションで新規 S3 AP をアタッチすれば、FSx が自動的に新しい `s3_unix` name-mapping を作成する — **手動構成不要**
- SnapMirror はボリュームのデータ（ファイル、ディレクトリ、UNIX パーミッション、ACL）のみを転送するが、これによりデスティネーションでの S3 AP 経由のデータアクセスに問題は発生しない

**結論**: S3 AP メタデータが SnapMirror で転送されないことは「制約」ではなく「期待される設計」である。デスティネーション SVM に新規 S3 AP をアタッチすることで完全に動作する。

#### エビデンス

- [AWS Docs: Managing access point access — File system user identity and authorization](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)
- Phase 3 検証エビデンス: `.private/evidence/s3ap-multicloud/`（TC-01, TC-02 結果）

---

### SM-003: Object Store Server 排他制約の SnapMirror デスティネーション SVM への影響

| 項目 | 内容 |
|------|------|
| **Finding ID** | SM-003 |
| **Requirement Ref** | Requirement 1, AC 1.4 |
| **分類** | `supported`（影響なし — ボリュームレベル SnapMirror では無関係） |
| **公開分類** | publicly verifiable |

#### 調査結果

Object Store Server 排他制約は「同一 SVM 上で ONTAP ネイティブ S3 object store server（`vserver object-store-server`）と FSx for ONTAP S3 AP が共存できない」という制約である。

SnapMirror **ボリュームレベル**のレプリケーションでは:
- ソース SVM とデスティネーション SVM は**異なる SVM**である
- デスティネーション SVM は独立した構成を持つ
- ソース SVM に S3 AP がアタッチされていても、その事実はデスティネーション SVM に伝播しない
- デスティネーション SVM に `vserver object-store-server` が無い限り、デスティネーションで新規 S3 AP をアタッチすることが可能

#### 結論

ボリュームレベル SnapMirror において、Object Store Server 排他制約はデスティネーション SVM には影響しない。ソースとデスティネーションは独立した SVM であり、デスティネーション SVM 上で S3 AP を新規アタッチする場合は、デスティネーション SVM 自体に `vserver object-store-server` が存在しないことのみ確認すればよい。

#### エビデンス

- [AWS Docs: Creating access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/create-access-points.html) — S3 AP は同一リージョンのボリュームに対してのみ作成可能
- [AWS Docs: Replicating your data using NetApp SnapMirror](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html) — FSx for ONTAP は Volume-level SnapMirror のみサポート

---

### SM-004: SVM-DR（SVM-level SnapMirror）と S3 AP の互換性

| 項目 | 内容 |
|------|------|
| **Finding ID** | SM-004 |
| **Requirement Ref** | Requirement 1, AC 1.5 |
| **分類** | `unsupported` |
| **公開分類** | publicly verifiable |

#### 調査結果

SVM-DR は S3 NAS bucket（S3 AP の基盤技術）を含む SVM では使用不可である。

**証拠1:** NetApp ONTAP S3 multiprotocol ドキュメントに明記:

> "SnapMirror synchronous and **SVM disaster recovery are not supported**."

**証拠2:** NetApp KB「Is SVM Disaster Recovery (SVM DR) of S3 buckets supported?」:

> Error: "A Vserver DR relationship between Vserver [Source SVM] and Vserver [Destination/DR SVM] is not supported because Vserver [Source SVM] contains either an object store server, object store policy, object store user or object store bucket."

**証拠3:** ONTAP S3 interoperability テーブル（"Not supported" 列）:

- SVM disaster recovery
- SnapMirror (synchronous and asynchronous) — native S3 に対する制約
- SnapMirror cloud

**証拠4:** NetApp ONTAP SnapMirror SVM replication ドキュメント:

- "ONTAP S3: Not supported with SVM disaster recovery."

#### SVM-DR が保持する構成（参考）

SVM-DR（`-identity-preserve true`）は通常以下を保持する:
- SMB server 設定（CIFS server name、AD domain 情報）
- Name mapping and group mapping
- NFS export policies and rules
- DNS, LDAP, Kerberos 設定
- UNIX user and UNIX group
- Audit information

しかし S3 AP が存在する SVM ではこの機能自体が使用できないため、ボリュームレベル SnapMirror が唯一の選択肢となり、上記 SVM 構成はデスティネーション側で独立して再構成する必要がある。

#### エビデンス

- [NetApp Docs: Learn about ONTAP S3 multiprotocol support](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html)
- [NetApp KB: Is SVM Disaster Recovery (SVM DR) of S3 buckets supported?](https://kb.netapp.com/on-prem/ontap/DP/SnapMirror-KBs/Is_SVM_Disaster_Recovery_(SVM_DR)_of_S3_buckets_supported%3F)
- [NetApp Docs: Learn about ONTAP SnapMirror SVM replication](https://docs.netapp.com/us-en/ontap/data-protection/snapmirror-svm-replication-concept.html)
- [GitHub NetAppDocs/ontap: s3-config/ontap-s3-interoperability-concept.adoc](https://github.com/NetAppDocs/ontap/blob/main/s3-config/ontap-s3-interoperability-concept.adoc)

---

### SM-005: SnapMirror Failover 後の S3 AP 再アタッチ手順

| 項目 | 内容 |
|------|------|
| **Finding ID** | SM-005 |
| **Requirement Ref** | Requirement 1, AC 1.6 |
| **分類** | `supported (validated)` |
| **公開分類** | validation evidence |

#### 調査結果

Phase 3 検証（TC-01/TC-02）により、SnapMirror break 後のデスティネーションボリュームへの S3 AP アタッチが正常動作することを確認した。

#### 検証済み手順

1. SnapMirror relationship の break を実行
2. デスティネーションボリュームの junction path を設定（break 直後は junction path が未設定の場合がある）
3. FSx API の `VolumeType` が `DP` → `RW` に変わるまで **約60秒待機**（FSx API には遅延あり、ONTAP レベルでは break 直後に RW だが FSx API の反映にラグがある）
4. AWS FSx API `create-and-attach-s3-access-point` を使用して新規 S3 AP をアタッチ

```bash
aws fsx create-and-attach-s3-access-point \
  --name <ap-name> \
  --type ONTAP \
  --ontap-configuration \
    'VolumeId=<destination-volume-id>,FileSystemIdentity={Type=UNIX,UnixUser={Name=<unix-user>}}'
```

#### 新規 Finding: SM-VAL-004/007 — FSx API VolumeType 遅延

Phase 3 検証中に発見された追加事項:

- FSx API の `describe-volumes` で返される `VolumeType` は、ONTAP レベルで break が完了しても約60秒間 `DP` のまま表示される
- S3 AP アタッチは `VolumeType` が `RW` に変わった後に実行する必要がある
- **分類**: `works_with_caveats` — 動作するが FSx API ラグへの対応（ポーリングまたは wait）が必要

#### 重要な考慮事項

- S3 AP はソースからデスティネーションに「移行」されない — デスティネーションで**新規作成**する必要がある
- S3 AP alias（`<name>-...-ext-s3alias`）は AP ごとに一意であり、ソースの AP alias とは異なる値になる
- クライアントアプリケーションは新しい AP ARN/alias を使用するよう更新が必要
- デスティネーションが別リージョンの場合、S3 AP は同一リージョンのボリュームにのみアタッチ可能

#### エビデンス

- [AWS Docs: Creating access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/create-access-points.html)
- [AWS Docs: create-and-attach-s3-access-point CLI Reference](https://docs.aws.amazon.com/cli/latest/reference/fsx/create-and-attach-s3-access-point.html)
- Phase 3 検証エビデンス: `.private/evidence/s3ap-multicloud/`（TC-01, TC-02 結果）

---

### SM-006: S3 AP IAM ポリシーの AWS レイヤー独立性

| 項目 | 内容 |
|------|------|
| **Finding ID** | SM-006 |
| **Requirement Ref** | Requirement 1, AC 1.7 |
| **分類** | `supported`（確認済み） |
| **公開分類** | publicly verifiable |

#### 調査結果

AWS 公式ドキュメント「Managing access point access」に以下が明記されている:

> "Amazon S3 access points for FSx for ONTAP use a **dual-layer authorization model** that combines AWS IAM permissions with file system-level permissions."

この dual-layer モデルの各レイヤーと SnapMirror 転送の関係:

| レイヤー | 管理場所 | SnapMirror で転送されるか |
|---------|---------|:---:|
| AWS IAM identity policy（呼び出し元 principal） | AWS IAM | ❌ |
| S3 access point resource policy | AWS S3 API | ❌ |
| File system user identity（UNIX/Windows） | FSx API + ONTAP SVM | ❌（AP 設定は AWS リソース） |
| ファイルシステム権限（mode-bits, ACL） | ONTAP ボリューム内データ | ✅ |

#### 結論

S3 AP の IAM 認証は完全に AWS レイヤーの構成要素であり、ONTAP SnapMirror レプリケーションでは一切転送されない。デスティネーションで S3 AP を通じたデータアクセスを実現するには、以下を**別途構成**する必要がある:

1. デスティネーションリージョン/アカウントでの IAM identity policy
2. 新規 S3 AP の作成とアタッチ
3. （必要に応じて）S3 AP resource policy の設定
4. File system identity（UNIX/Windows ユーザー）の指定

#### エビデンス

- [AWS Docs: Managing access point access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)
- [AWS Docs: Accessing your data via Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)

---

### SM-007: ONTAP S3 + SnapMirror 互換性の全体像

| 項目 | 内容 |
|------|------|
| **Finding ID** | SM-007 |
| **Requirement Ref** | Requirement 1, AC 1.1, 1.3 |
| **分類** | `supported`（条件付き — SnapMirror Async Volume-level のみ） |
| **公開分類** | publicly verifiable |

#### 調査結果

ONTAP S3 関連機能と SnapMirror の対応状況を整理する:

| シナリオ | SnapMirror Async (Volume) | SnapMirror Sync | SVM-DR | SnapMirror S3 |
|---------|:---:|:---:|:---:|:---:|
| Native S3 bucket（`vserver object-store-server`） | ❌ | ❌ | ❌ | ✅（ONTAP 9.10.1+） |
| S3 NAS bucket（multiprotocol, ONTAP 9.12.1+） | ✅ | ❌ | ❌ | N/A（不要） |
| FSx for ONTAP S3 AP（S3 NAS bucket ベース） | ✅（推定） | ❌ | ❌ | N/A（不要） |

#### 重要な区別

1. **Native ONTAP S3**（`vserver object-store-server` で作成された S3 bucket）: SnapMirror S3 で保護。通常の SnapMirror volume replication は非サポート
2. **S3 NAS bucket / FSx for ONTAP S3 AP**（NAS ボリューム上の S3 マッピング）: 通常の SnapMirror Asynchronous volume replication で保護。SnapMirror S3 は使用しない

FSx for ONTAP S3 AP は後者（S3 NAS bucket）に該当するため、SnapMirror Asynchronous volume replication がサポートされる。

#### エビデンス

- [NetApp Docs: ONTAP S3 interoperability](https://docs.netapp.com/us-en/ontap/s3-config/ontap-s3-interoperability-concept.html)
- [NetApp Docs: Learn about ONTAP S3 multiprotocol support](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html)
- [GitHub NetAppDocs/ontap: s3-config/ontap-s3-interoperability-concept.adoc](https://github.com/NetAppDocs/ontap/blob/main/s3-config/ontap-s3-interoperability-concept.adoc)
- [NetApp KB: Is SVM Disaster Recovery (SVM DR) of S3 buckets supported?](https://kb.netapp.com/on-prem/ontap/DP/SnapMirror-KBs/Is_SVM_Disaster_Recovery_(SVM_DR)_of_S3_buckets_supported%3F)

---

### S3 AP + SnapMirror — サマリーテーブル

| Finding ID | 項目 | 分類 | 検証必要 |
|:---:|------|:---:|:---:|
| SM-001 | S3 AP ボリュームの SnapMirror Async ソース対応 | supported（条件付き） | ✅ 実環境確認済み |
| SM-002 | S3 AP メタデータの SnapMirror 転送後保持 | supported (validated) | ✅ 検証済み |
| SM-003 | Object Store Server 排他制約のデスティネーション SVM 影響 | supported（影響なし） | — |
| SM-004 | SVM-DR と S3 設定保持 | unsupported | — |
| SM-005 | SnapMirror failover 後の S3 AP 再アタッチ手順 | supported (validated) | ✅ 検証済み |
| SM-006 | S3 AP IAM ポリシーの AWS レイヤー独立性 | supported | — |
| SM-007 | ONTAP S3 + SnapMirror 互換性全体像 | supported（条件付き） | ✅ 実環境確認済み |

---

## NFS/SMB Authentication

本セクションでは、SnapMirror デスティネーションボリューム（break 後の read-write）および FlexCache Cache Volume における NFS/SMB 認証方式の利用可否を調査した結果を記録する。

### AUTH-001: SnapMirror デスティネーションでの NFS 認証方式

| 項目 | 内容 |
|------|------|
| **Finding ID** | AUTH-001 |
| **Requirement Ref** | Requirement 4, AC 4.1 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

#### 調査結果

SnapMirror デスティネーションボリュームは `snapmirror break` 実行後に read-write に昇格する。この時点でボリュームは通常の FlexVol/FlexGroup と同等の機能を持ち、**全ての NFS 認証方式が利用可能**となる:

- **AUTH_SYS** (sys): 標準の UNIX UID/GID ベース認証
- **Kerberos v5** (krb5): Kerberos 認証のみ
- **Kerberos v5i** (krb5i): Kerberos 認証 + 整合性チェック（checksum）
- **Kerberos v5p** (krb5p): Kerberos 認証 + 整合性チェック + 暗号化

認証方式は export policy rule の `ro_rule` / `rw_rule` / `superuser` パラメータで制御する。Kerberos 認証を使用する場合は、**デスティネーション SVM 上で Kerberos realm の構成と data LIF での Kerberos 有効化が別途必要**である。

#### 重要な考慮事項

- Volume-level SnapMirror はボリュームデータとスナップショットを複製するが、**NFS export policy、junction path、Kerberos 構成は複製しない**
- デスティネーション SVM で export policy rule を別途作成する必要がある
- SVM-DR（`-identity-preserve true`）を使用する場合は、export policy、NFS server 構成、Kerberos realm/keyblock が全て複製される（後述の AUTH-005 参照）

#### エビデンス

| ソース | URL |
|--------|-----|
| NetApp Docs: ONTAP NFS support for Kerberos | https://docs.netapp.com/us-en/ontap/nfs-admin/ontap-support-kerberos-concept.html |
| NetApp KB: What does volume level SnapMirror replicate? | https://kb.netapp.com/on-prem/ontap/DP/SnapMirror/SnapMirror-KBs/What_does_volume_level_snapmirror_replicate |
| NetApp Docs: SVM replication concept (configurations replicated table) | https://docs.netapp.com/us-en/ontap/data-protection/snapmirror-svm-replication-concept.html |

---

### AUTH-002: FlexCache Cache Volume での NFS 認証方式

| 項目 | 内容 |
|------|------|
| **Finding ID** | AUTH-002 |
| **Requirement Ref** | Requirement 4, AC 4.2 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

#### 調査結果

FlexCache Cache Volume は以下の NFS プロトコルバージョンをサポートする:

| プロトコル | Cache Volume サポート | 備考 |
|-----------|:-------------------:|------|
| NFSv3 | ONTAP 9.5+ | FlexCache 初期リリースから対応 |
| NFSv4.0 | ONTAP 9.10.1+ | EMS メッセージで確認 |
| NFSv4.1 | ONTAP 9.10.1+ | EMS メッセージで確認 |
| SMB 2.x / 3.x | ONTAP 9.8+ | CIFS/SMB プロトコルの FlexCache 対応 |

**NFS 認証方式のサポート状況**（Cache Volume）:

- **AUTH_SYS** (sys): サポート済み（全 NFS バージョンで利用可能）
- **Kerberos v5/v5i/v5p**: Cache Volume 側の SVM で独立して Kerberos realm を構成する必要がある

FlexCache Cache Volume の export policy は **Origin Volume とは独立**して設定する。Cache Volume を持つ SVM の export policy rule で認証方式を制御する。

#### 重要な考慮事項

- FlexCache write-back mode（ONTAP 9.15.1+）でも同じクライアントプロトコル（NFSv3, NFSv4.0, NFSv4.1, SMB2.x, SMB3.x）がサポートされる
- Google Cloud NetApp Volumes (GCNV) の FlexCache は **NFSv4 非サポート**（NFSv3 のみ） — プラットフォーム固有の制限に注意
- Cache Volume での NFS v4 delegation は global file locking（ONTAP 9.10.1+）と連動する

#### エビデンス

| ソース | URL |
|--------|-----|
| NetApp Docs: Supported and unsupported features for FlexCache volumes | https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html |
| NetApp EMS: nblade.flexcachevolumeaccess events（サポートプロトコル一覧） | https://docs.netapp.com/us-en/ontap-ems/nblade-flexcachevolumeaccess-events.html |
| NetApp Docs: FlexCache write-back interoperability | https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-interoperability.html |
| GCP Docs: GCNV FlexCache volume（NFSv4 非サポート記載） | https://cloud.google.com/netapp/volumes/docs/configure-and-use/volumes/cache-ontap-volumes/create-flexcache-volume |

---

### AUTH-003: SnapMirror デスティネーションでの SMB 認証要件

| 項目 | 内容 |
|------|------|
| **Finding ID** | AUTH-003 |
| **Requirement Ref** | Requirement 4, AC 4.3 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

#### 調査結果

SnapMirror デスティネーションボリュームに SMB/CIFS でアクセスするための要件:

**必須条件:**

1. **デスティネーション SVM の AD 参加**: SMB アクセスにはデスティネーション SVM に CIFS サーバーが構成され、Active Directory ドメインに参加している必要がある
2. **SMB Share の作成**: Volume-level SnapMirror は CIFS share を複製しない。デスティネーション SVM で別途 share を作成する必要がある
3. **NTFS ACL の保持**: Volume-level SnapMirror は NTFS ACL（SID 含む）を保持する。ただし、SID に紐づくユーザー/グループ identity 自体は複製されない

**SMB 認証プロトコル:**

| 認証方式 | サポート | 条件 |
|---------|:-------:|------|
| Kerberos（推奨） | サポート | デスティネーション SVM が同一 AD ドメイン（または trust 関係のあるドメイン）に参加している場合 |
| NTLM | サポート | フォールバック認証。Kerberos が使用できない場合に自動ネゴシエーション |
| NTLMv2 | サポート | NTLM の改良版。セキュリティポリシーで強制可能 |

**ローカルユーザー/グループに関する注意:**

SnapMirror break 後、ローカルユーザー、ローカルグループ、および関連する ACE（Access Control Entry）は**デスティネーション SVM で機能しない**。これらのオブジェクトのパーミッションはソース SVM のローカルドメイン内でのみ有効であり、異なる SVM には引き継がれない。デスティネーションで以下の再構成が必要:

1. ローカル認証の有効化 (`vserver cifs options modify -is-local-auth-enabled true`)
2. ローカルユーザーの再作成
3. Share アクセス制御の再設定
4. ファイル/フォルダ ACL の再適用（クライアント側から）

#### エビデンス

| ソース | URL |
|--------|-----|
| NetApp KB: What does volume level SnapMirror replicate? | https://kb.netapp.com/on-prem/ontap/DP/SnapMirror/SnapMirror-KBs/What_does_volume_level_snapmirror_replicate |
| NetApp KB: Do local authentication objects need to be recreated after SnapMirror break? | https://kb.netapp.com/on-prem/ontap/DP/SnapMirror/SnapMirror-KBs/Do_local_authentication_objects_and_permissions_need_to_be_recreated_after_a_SnapMirror_break |
| NetApp Docs: Microsoft SQL Server DR with ONTAP（SMB + same AD domain requirement） | https://docs.netapp.com/us-en/ontap-apps-dbs/mssql/mssql-dr-snapmirror.html |

---

### AUTH-004: Volume Security Style の SnapMirror 転送時保持動作

| 項目 | 内容 |
|------|------|
| **Finding ID** | AUTH-004 |
| **Requirement Ref** | Requirement 4, AC 4.4 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

#### 調査結果

**Volume security style（UNIX / NTFS / MIXED）は SnapMirror 転送で完全に保持される。**

SnapMirror はボリュームレベルのブロックレプリケーションであり、ボリュームのメタデータ（security style 含む）はそのまま複製される。

| Security Style | 転送後の動作 | パーミッション評価方式 |
|---------------|-------------|---------------------|
| UNIX | 保持される | UNIX パーミッション (mode bits, POSIX ACL) で評価 |
| NTFS | 保持される | Windows NTFS ACL で評価。SID は保持されるが、対応するユーザー/グループはデスティネーション AD で解決される必要がある |
| MIXED | 保持される | 最後に設定されたパーミッションタイプ（UNIX or NTFS）で評価 |

**認証方式との関係:**

| Security Style | NFS アクセス時 | SMB アクセス時 |
|---------------|--------------|--------------|
| UNIX | UNIX credentials で直接評価 | win→unix name-mapping 必要。マッピングされた UID/GID で評価 |
| NTFS | unix→win name-mapping 必要。マッピングされた Windows identity の ACL で評価 | Windows credentials で直接評価 |
| MIXED | アクセスプロトコルに応じて最後に設定された effective style で評価 | アクセスプロトコルに応じて最後に設定された effective style で評価 |

**マルチクラウドでの影響:**

- SnapMirror デスティネーションが異なるクラウド（FSx for ONTAP → CVO on GCP 等）でも security style は保持される
- NTFS security style のボリュームをデスティネーションで SMB アクセスする場合、**SID が解決可能な AD 環境**がデスティネーション側にも必要
- UNIX security style のボリュームは AD 不要で NFS アクセス可能（最もシンプルなマルチクラウドパターン）

#### エビデンス

| ソース | URL |
|--------|-----|
| NetApp KB: What does volume level SnapMirror replicate?（NTFS ACL 保持記載） | https://kb.netapp.com/on-prem/ontap/DP/SnapMirror/SnapMirror-KBs/What_does_volume_level_snapmirror_replicate |
| AWS Docs: Volume security style | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/volume-security-style.html |
| NetApp Docs: Security styles and their effects (ONTAP) | https://docs.netapp.com/us-en/ontap/smb-admin/security-styles-their-effects-concept.html |

---

### AUTH-005: Cross-Domain AD Trust 要件と Name-Mapping

| 項目 | 内容 |
|------|------|
| **Finding ID** | AUTH-005 |
| **Requirement Ref** | Requirement 4, AC 4.5 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

#### 調査結果

デスティネーション SVM がソースとは異なる AD ドメインに属する場合（マルチクラウドシナリオで頻出）、以下の要件が発生する:

**シナリオ A: 同一 AD ドメイン（推奨）**

- ソースとデスティネーションの SVM が同じ AD ドメインに参加
- NTFS ACL 内の SID がデスティネーションで直接解決可能
- 追加構成不要

**シナリオ B: Trust 関係のある異なる AD ドメイン**

- ソースドメインとデスティネーションドメイン間に **双方向の信頼関係 (two-way trust)** が必要
- Kerberos 認証: クロスレルム信頼により、ソースドメインの credential でデスティネーションのリソースにアクセス可能
- NTFS ACL: Trust 経由で SID 解決が可能
- Name-mapping: 異なるドメイン間では明示的な name-mapping rule の追加が推奨される

**シナリオ C: Trust 関係なしの異なる AD ドメイン（制約あり）**

- SMB アクセスで NTFS ACL の SID が解決できない → **アクセス拒否**
- 対策: デスティネーション SVM で新しい NTFS ACL を再設定する（ソース ACL は無効化）
- NFS アクセス（UNIX security style）であれば AD trust 不要

**SVM-DR（identity-preserve true）の場合:**

SVM-DR は以下の認証関連構成を全て複製する:

| 構成項目 | `-identity-preserve true` | `-identity-preserve false` |
|---------|:-------------------------:|:--------------------------:|
| CIFS/SMB Server | 複製される | 複製されない |
| Name mapping / Group mapping | 複製される | 複製される |
| NFS Server | 複製される | 複製されない |
| Export policies / Export policy rules | 複製される | 複製されない |
| Kerberos realm / Kerberos keyblocks | 複製される | 複製されない |
| LDAP / LDAP client | 複製される | 複製されない |
| UNIX user / UNIX group | 複製される | 複製される |
| DNS / DNS hosts | 複製される | 複製されない |

SVM-DR の `identity-preserve true` を使用することで、認証構成の再作成作業を大幅に削減できる。ただし FSx for ONTAP では **SVM-DR は現時点で非サポート**（Volume-level SnapMirror のみ）であることに注意。

**マルチクラウドでの Name-Mapping 考慮事項:**

- デスティネーション SVM が AD に参加している場合、`win→unix` / `unix→win` の name-mapping が必要（マルチプロトコルアクセス時）
- S3 AP データ操作で CIFS が有効な SVM では `unix→win` 逆引きが発生する（AUTH-003 のローカルプロジェクト知識参照）
- クラウド間で AD ドメインが異なる場合、name-mapping rule をデスティネーション SVM の AD ユーザーに合わせて再定義する必要がある

#### エビデンス

| ソース | URL |
|--------|-----|
| NetApp Docs: SnapMirror SVM replication concept（構成複製テーブル） | https://docs.netapp.com/us-en/ontap/data-protection/snapmirror-svm-replication-concept.html |
| NetApp Docs: Microsoft SQL Server DR（同一 AD ドメイン要件記載） | https://docs.netapp.com/us-en/ontap-apps-dbs/mssql/mssql-dr-snapmirror.html |
| NetApp KB: Unable to access CIFS shares after SVM migration using SnapMirror | https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/Unable_to_access_CIFS_shares_after_SVM_migration_using_snapmirror |
| Microsoft Docs: ANF cross-region replication requirements（AD 到達性要件） | https://learn.microsoft.com/en-us/azure/azure-netapp-files/cross-region-replication-requirements-considerations |

---

## NFS/SMB Authentication — サマリーテーブル

| Finding ID | トピック | 分類 | 要約 |
|:----------:|--------|:----:|------|
| AUTH-001 | SnapMirror デスティネーション NFS 認証 | `supported` | break 後は全 NFS 認証方式（sys, krb5, krb5i, krb5p）利用可。ただし export policy と Kerberos 構成は別途必要 |
| AUTH-002 | FlexCache Cache Volume NFS 認証 | `supported` | NFSv3/v4.0/v4.1 + SMB 対応。Cache SVM で独立して認証構成が必要 |
| AUTH-003 | SnapMirror デスティネーション SMB 認証 | `supported` | AD 参加必須。Kerberos/NTLM 利用可。ローカルユーザー/グループは再作成が必要 |
| AUTH-004 | Security Style 保持動作 | `supported` | UNIX/NTFS/MIXED は SnapMirror で完全保持。NTFS は SID 解決のため AD 必要 |
| AUTH-005 | Cross-Domain AD Trust | `supported` | 同一ドメイン推奨。異なるドメインでは trust 関係と name-mapping 再定義が必要 |

---

## References（本セクション関連）

1. NetApp Docs: ONTAP NFS support for Kerberos — https://docs.netapp.com/us-en/ontap/nfs-admin/ontap-support-kerberos-concept.html
2. NetApp KB: What does volume level SnapMirror replicate? — https://kb.netapp.com/on-prem/ontap/DP/SnapMirror/SnapMirror-KBs/What_does_volume_level_snapmirror_replicate
3. NetApp Docs: SnapMirror SVM replication concept — https://docs.netapp.com/us-en/ontap/data-protection/snapmirror-svm-replication-concept.html
4. NetApp Docs: Supported and unsupported features for FlexCache volumes — https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html
5. NetApp EMS: nblade.flexcachevolumeaccess events — https://docs.netapp.com/us-en/ontap-ems/nblade-flexcachevolumeaccess-events.html
6. NetApp Docs: FlexCache write-back interoperability — https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-interoperability.html
7. NetApp KB: Do local authentication objects need to be recreated after SnapMirror break? — https://kb.netapp.com/on-prem/ontap/DP/SnapMirror/SnapMirror-KBs/Do_local_authentication_objects_and_permissions_need_to_be_recreated_after_a_SnapMirror_break
8. NetApp Docs: Microsoft SQL Server DR with ONTAP — https://docs.netapp.com/us-en/ontap-apps-dbs/mssql/mssql-dr-snapmirror.html
9. AWS Docs: Volume security style — https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/volume-security-style.html
10. NetApp Docs: Security styles and their effects — https://docs.netapp.com/us-en/ontap/smb-admin/security-styles-their-effects-concept.html
11. GCP Docs: GCNV FlexCache volume creation — https://cloud.google.com/netapp/volumes/docs/configure-and-use/volumes/cache-ontap-volumes/create-flexcache-volume
12. Microsoft Docs: ANF cross-region replication requirements — https://learn.microsoft.com/en-us/azure/azure-netapp-files/cross-region-replication-requirements-considerations

---

## S3 AP + FlexCache

本セクションでは、FSx for ONTAP S3 AP がアタッチされたボリュームが FlexCache Origin Volume となる可否、および Cache Volume での S3 AP 関連動作を調査した結果を記録する。

### 調査背景

FlexCache は ONTAP のリモートキャッシング技術であり、Origin Volume のデータを別クラスター上の Cache Volume として透過的に提供する。S3 AP アタッチ済みボリュームを FlexCache Origin とすることで、S3 API で収集したデータを分散拠点で NFS/SMB 経由の低レイテンシアクセスに供するアーキテクチャが実現可能かを評価する。

---

### FC-001: S3 AP アタッチ済みボリュームの FlexCache Origin 設定可否

| 項目 | 内容 |
|------|------|
| **Finding ID** | FC-001 |
| **Requirement Ref** | Requirement 2, AC 2.1 |
| **分類** | `supported (validated)` |
| **公開分類** | validation evidence |

**調査結果:**

Phase 3 検証（TC-03/TC-05、ONTAP 9.17.1）により、S3 AP アタッチ済みボリュームが FlexCache Origin Volume に設定可能であることを確認した。

**検証確認事項:**
- S3 AP がアタッチされた状態で FlexCache Origin として設定可能
- S3 NAS bucket（S3 multiprotocol）メカニズムに基づくため、ONTAP の FlexCache supported features テーブル記載の通り Origin 9.12.1+ でサポート
- FSx for ONTAP 固有の AWS マネージドレイヤー（S3 AP アタッチメント）は FlexCache Origin 設定に干渉しない

**追加発見事項（Phase 3 検証）:**
- FSx for ONTAP での FlexCache 最小サイズは **50GB**（FlexGroup タイプ + FabricPool aggregate のため）
- FlexCache 作成時に `use_tiered_aggregate: true` が必須（FSx for ONTAP 固有の要件）
- 同一クラスター内 FlexCache でも **Intra-cluster SVM Peering** が必要

**エビデンス:**
- [NetApp Docs: Supported and unsupported features for FlexCache volumes](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html) — "ONTAP S3 NAS bucket: Yes (Origin, 9.12.1+), Yes (Cache, 9.18.1+)"
- Phase 3 検証エビデンス: `.private/evidence/s3ap-multicloud/`（TC-03, TC-05 結果）

---

### FC-002: Cache Volume での S3 AP 独立アタッチ可否

| 項目 | 内容 |
|------|------|
| **Finding ID** | FC-002 |
| **Requirement Ref** | Requirement 2, AC 2.2 |
| **分類** | `unsupported`（FSx レイヤ）— ONTAP のバージョンに依存しない |
| **公開分類** | validation evidence |

> **2026-09-13 訂正。** 本項目は以前 `version_gated`（「ONTAP 9.18.1 以降でサポート」）と分類していた。**誤りである。** 9.18.1P5 上で実測した結果、FSx API は同一のエラーで拒否した。NetApp の機能表を FSx の機能表明として読んでいたのが原因で、両者は別の機構である。EN 版は当初から実測した拒否を記録していた。根拠: [ONTAP-RECOVERY-QUEUE-001](../../../../verification-pack/ontap-features/evidence/2026-09-13/volume-recovery-queue-and-fc002.yaml)。

**実測結果（ONTAP 9.18.1P5、2026-09-13）:**

対象は同一クラスタ上の既存 FlexCache Cache Volume（50 GiB、mount 済み、FSx API 上は type RW かつ junction path あり、つまりアタッチ条件は満たしている）。

```
Amazon FSx is unable to attach S3access point because the volume is a FlexCache.
```

ONTAP 9.17.1 で 2026-07-24 に記録したエラーと逐語一致する（AWS 側の文字列にある "S3access" の欠落スペースを含む）。失敗時は何も作られないため、この検証はリソースを追加していない。

**2 つの機構の区別（ここが取り違えの原因）:**

| 機構 | 層 | Cache Volume での状況 |
|---|---|---|
| ONTAP S3 NAS bucket | ONTAP ネイティブ | NetApp のドキュメント上、ONTAP 9.18.1 以降でサポート |
| **FSx for ONTAP S3 Access Points** | AWS マネージド層 | **ボリューム種別で拒否。9.18.1P5 でも拒否された** |

FSx for ONTAP S3 Access Points は ONTAP S3 NAS bucket の仕組みの上に構築されているが、アタッチ可否を判定しているのは FSx コントロールプレーンであり、そこが FlexCache ボリュームを明示的に拒否する。解消には ONTAP のアップグレードではなく FSx サービス側の対応が必要である。

**該当する回避策:**

リモートのデータに S3 API で読み取りアクセスするなら、SnapMirror で複製して宛先を提供する。**break は不要**（SM-VAL-013）。これは「break して再アタッチ」という旧来の案内を置き換える。旧案内は、宛先経路に break が必要だと考えられていた時期に書かれたものである。

**エビデンス:**
- 実測: [ONTAP-RECOVERY-QUEUE-001](../../../../verification-pack/ontap-features/evidence/2026-09-13/volume-recovery-queue-and-fc002.yaml)（Finding B）
- [NetApp Docs: Supported and unsupported features for FlexCache volumes](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html) — "ONTAP S3 NAS bucket: Cache — Supported beginning with ONTAP 9.18.1"（ONTAP ネイティブ機能についての記述であり、FSx の S3 Access Points についてではない）
- [AWS Docs: Accessing your data via Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)

---

### FC-003: FlexCache バージョン互換性要件

| 項目 | 内容 |
|------|------|
| **Finding ID** | FC-003 |
| **Requirement Ref** | Requirement 2, AC 2.3 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

**調査結果:**

FlexCache の Origin と Cache 間のバージョン互換性は公式ドキュメントで明確に定義されている:

**一般ルール（write-around モード）:**
- Origin と Cache のバージョン差は **4マイナーバージョン以内** が推奨
- 例: Cache が ONTAP 9.14.1 の場合、Origin は最低 ONTAP 9.10.1 が必要
- NFSv4.x での Cache Volume アクセスには Origin/Cache 双方で ONTAP 9.10.1 以降が必要

**Write-back モード:**
- Origin と Cache の **双方が ONTAP 9.15.1 以降** を要求（厳密要件）
- Origin が 9.14.1 の場合、Cache が 9.15.1 であっても write-back は有効化不可
- 混合環境では write-back 対応 Cache と write-around のみ Cache が共存可能

**FSx for ONTAP 間の FlexCache:**
- FSx for ONTAP 同士（同一リージョン/別リージョン）: サポート済み
- FSx for ONTAP → On-premises ONTAP: サポート済み
- 上記いずれもバージョン互換性ルールに準拠する必要あり

**推奨バージョン（2025年7月時点）:**
- Write-back 利用時: 9.17.1P1 以降を Origin/Cache 双方で推奨（NetApp 公式ガイドライン）

**Next Action:** `none` — ドキュメントで明確にサポートが確認された

**エビデンス:**
- [NetApp Docs: Supported and unsupported features for FlexCache volumes](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html) — バージョン互換性テーブル
- [NetApp KB: FlexCache version compatibility](https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/Is_there_a_compatibility_suggestion_for_the_ONTAP_version_difference_between_cache_and_origin_regarding_FlexCache)
- [NetApp Docs: FlexCache write-back interoperability](https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-interoperability.html) — "both the cache and origin must be running ONTAP 9.15.1 or later"
- [NetApp Docs: FlexCache write-back guidelines](https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-guidelines.html) — "run the current recommended release after 9.17.1P1"
- [AWS Docs: Replicating your data with FlexCache](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html)

---

### FC-004: FlexCache write-back mode（2025年5月新機能）と S3 AP の互換性

| 項目 | 内容 |
|------|------|
| **Finding ID** | FC-004 |
| **Requirement Ref** | Requirement 2, AC 2.4（暗黙的に AC 2.5 のロック動作にも関連） |
| **分類** | `works_with_caveats` |
| **公開分類** | validation evidence |

**調査結果:**

Phase 3 検証（TC-03/TC-05、ONTAP 9.17.1）により、FlexCache write-back mode と FSx for ONTAP S3 AP の組み合わせが動作することを確認した。ただし重要な注意事項が存在する。

**検証で確認された動作:**

1. **Write-back FlexCache + S3 AP Origin は動作する** — Cache Volume でのローカル書き込みが正常に機能
2. **S3 AP 経由の Origin 直接書き込みは XLD revoke を引き起こす** — S3 AP 経由で Origin Volume にデータを書き込むと、Cache 側が保持する XLD が revoke され、Cache 上の dirty data は破棄（上書き）される
3. **同一ファイルへの concurrent write は危険** — S3 AP（Origin 側）と NFS/SMB（Cache 側）で同一ファイルに同時書き込みを行うと、Cache 側の変更が失われる可能性がある

**動作メカニズム（検証確認済み）:**

```
S3 AP 経由で Origin に write
    → Origin が XLD revoke を Cache に発行
    → Cache の dirty data が flush（Origin の最新データで上書き）
    → S3 AP write のデータが Origin に反映
    → Cache は次回アクセス時に Origin から最新データを取得
```

**S3 AP write の Cache への伝搬:**
- S3 AP 経由で Origin に書き込まれたデータは、Cache Volume の TTL（デフォルト約30秒）経過後に Cache からの read で反映される
- TTL 期限前は Cache が stale data を返す可能性あり（FlexCache の一般的な動作）

**制約と推奨:**

| シナリオ | リスク | 推奨 |
|---------|------|------|
| S3 AP write（Origin）のみ、Cache は read-only | ✅ 安全 | このパターンを推奨 |
| Cache write（NFS/SMB）のみ、S3 AP は read-only | ✅ 安全 | 標準的な write-back ユースケース |
| S3 AP write + Cache write（異なるファイル） | ✅ 安全 | ファイル単位の XLD で保護される |
| S3 AP write + Cache write（**同一ファイル**） | ⚠️ **危険** | Cache dirty data が失われる。設計で回避すべき |

**エビデンス:**
- [NetApp Docs: FlexCache write-back architecture](https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-architecture.html) — XLD 方式の詳細
- [NetApp Docs: FlexCache write-back guidelines](https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-guidelines.html) — "Origin への直接書き込みは XLD revoke を引き起こす"
- Phase 3 検証エビデンス: `.private/evidence/s3ap-multicloud/`（TC-03, TC-05 結果）

---

### FC-005: NFS v4 Delegation と Lock Propagation の FlexCache Cache Volume での動作

| 項目 | 内容 |
|------|------|
| **Finding ID** | FC-005 |
| **Requirement Ref** | Requirement 2, AC 2.5 |
| **分類** | `partially_supported` |
| **公開分類** | publicly verifiable |

**調査結果:**

**NFSv4 プロトコルの FlexCache サポート状況:**
- NFSv4.0 / NFSv4.1 での Cache Volume アクセスは ONTAP 9.10.1 以降でサポート
- NFSv3 は FlexCache 初期リリース（9.5）からサポート
- ONTAP EMS メッセージ（9.17.1）では NFSv3, NFSv4, NFSv4.1, SMB を FlexCache 対応プロトコルとして列挙

**NFSv4 Delegation の FlexCache における動作:**

ONTAP は NFSv4 file delegation（RFC 3530）をサポートしている。Delegation には read delegation と write delegation の2種類がある。しかし、FlexCache Cache Volume での NFSv4 delegation の動作には以下の制約がある:

1. **FlexCache 独自の lock delegation メカニズム**: FlexCache は NFSv4 プロトコルレベルの delegation とは別に、独自の XLD (Exclusive Lock Delegation) メカニズムを使用する。これは Origin が Cache に対してファイル単位で排他権限を委任する ONTAP 内部メカニズムであり、NFSv4 クライアント delegation とは異なるレイヤーで動作する。

2. **Write-back mode での lock propagation**: XLD は Origin が Cache に付与し、1ファイルにつき1つの Cache のみが保持可能。XLD 保持中の Cache で書き込み中のファイルに他の Cache/Origin からアクセスすると、XLD revoke → dirty data flush → Origin へのコミットが発生し、一時的なアクセス遅延が生じる。

3. **NFSv4 delegation と FlexCache の関係**: 公式ドキュメントの FlexCache supported/unsupported features テーブルには NFSv4 delegation に関する明示的な記載がない。ただし、ONTAP の NFSv4.1 サポートでは delegation 機能に制限があることが文書化されている。

**Write-back mode での重要な動作特性:**
- Disconnected mode（WAN 切断時）: XLD 保持中の write-back Cache が切断されると、そのファイルへの read はすべての場所で hang する（一貫性保証のため）
- Write-around mode: 切断時は Origin にデータがあるため他 Cache/Origin からの read は継続可能
- Cache scrubber: mtime ベース（5分ごとに実行、2分未変更のファイルを flush）、space ベース（90% 使用率でLRU eviction）

**Next Action:** `validate` — TC-FC-005 で NFSv4.1 マウント時の Cache Volume での delegation 動作を確認

**エビデンス:**
- [NetApp Docs: FlexCache write-back architecture](https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-architecture.html) — XLD、data delegation、disconnected mode の詳細
- [NetApp Docs: Supported and unsupported features for FlexCache volumes](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html) — NFSv4 サポート（ONTAP 9.10.1+）
- [NetApp Docs: Enable or disable NFSv4 write file delegations](https://docs.netapp.com/us-en/ontap/nfs-admin/enable-disable-nfsv4-write-file-delegations-task.html)
- [NetApp EMS: nblade.flexcachevolumeaccess](https://docs.netapp.com/us-en/ontap-ems-9171/nblade-flexcachevolumeaccess-events.html) — 対応プロトコル: NFSv3, NFSv4, NFSv4.1, SMB

---

### FC-006: FlexCache Eviction ポリシーとキャッシュヒット率計測方法

| 項目 | 内容 |
|------|------|
| **Finding ID** | FC-006 |
| **Requirement Ref** | Requirement 2, AC 2.6 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

**調査結果:**

FlexCache の eviction ポリシーとキャッシュヒット/ミス率の計測方法は公式ドキュメントおよび REST API で確認可能。

**Eviction ポリシー:**

1. **Space-based eviction (容量ベース)**: Cache Volume が 90% 使用率に達すると、LRU (Least Recently Used) ベースで eviction が実行される。Origin Volume が 90% に達した場合も同様に Cache の scrub が発生する。

2. **mtime-based scrubber (時間ベース)**:
   - Cache 側: 5分ごとに実行、2分以上未変更のファイルの dirty data を flush
   - Origin 側: 5分ごとに実行、15分以上未変更のファイルの inode delegation を recall

3. **RW limit-based scrubber (ロック上限ベース)**: Origin constituent あたりの RW lock delegation が 170 を超えると、LRU ベースで lock delegation を回収

**キャッシュヒット/ミス率の計測方法:**

**方法1: ONTAP REST API — Volume Statistics**

```
GET /api/storage/volumes/{volume.uuid}/statistics
```

FlexCache 関連の statistics フィールド（`volume_statistics_reference_flexcache_raw` モデル）:
- `client_requested_blocks`: クライアントが要求したブロック数
- `cache_miss_blocks`: Origin から取得したブロック数（キャッシュミス）
- **ミス率計算**: `(cache_miss_blocks / client_requested_blocks) * 100`

**方法2: ONTAP REST API — Volume Metrics**

```
GET /api/storage/volumes/{volume.uuid}/metrics
```

`volume_metrics_flexcache` モデルで 15 秒間隔の時系列メトリクスを取得可能。バックフィル対応。

**方法3: ONTAP CLI — statistics show**

```bash
statistics show -object flexcache -instance <volume_name>
```

CLI でリアルタイムの FlexCache カウンターを確認可能。

**CloudWatch との統合:**
FSx for ONTAP は CloudWatch でスループットや IOPS を公開するが、FlexCache 固有のヒット率メトリクスは CloudWatch には直接公開されない。ONTAP REST API 経由での取得が必要。

**Next Action:** `none` — 計測方法が公式 API ドキュメントで確認済み

**エビデンス:**
- [NetApp REST API: volume_statistics_reference_flexcache_raw](https://library.netapp.com/ecmdocs/ECMLP2876965/html/models/volume_statistics_reference_flexcache_raw.html) — cache_miss_blocks / client_requested_blocks
- [NetApp Docs: FlexCache write-back architecture](https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-architecture.html) — Cache scrubbers（eviction メカニズム）
- [NetApp KB: FlexCache slow read performance and cache eviction](https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/FlexCache_slow_read_performance_and_cache_eviction)
- [NetApp REST API: Retrieve historical performance metrics for a volume](https://docs.netapp.com/us-en/ontap-restapi-9161/get-storage-volumes-metrics.html)

---

### FC-007: FlexGroup ボリューム（multi-constituent）の FlexCache Origin + S3 AP

| 項目 | 内容 |
|------|------|
| **Finding ID** | FC-007 |
| **Requirement Ref** | Requirement 2, AC 2.7 |
| **分類** | `partially_supported` |
| **公開分類** | publicly verifiable |

**調査結果:**

**FlexGroup ボリュームの FlexCache Origin 対応:**
- ONTAP 9.7 以降: FlexGroup ボリュームが FlexCache Origin Volume として対応
- ONTAP 9.5〜9.6: FlexVol のみが Origin として対応

**FSx for ONTAP S3 AP の FlexGroup 対応:**
- FSx for ONTAP は FlexVol と FlexGroup の両方のボリュームスタイルを提供
- S3 AP のアタッチ対象として FlexGroup ボリュームに明示的な制限は AWS ドキュメントに記載されていない
- `CreateAndAttachS3AccessPoint` API は volume ID を指定しボリュームスタイルによる制限は文書化されていない

**Constituent レベルの制約（FlexCache Origin としての FlexGroup）:**

FlexCache write-back mode において重要な制約が存在:

1. **Write-back mode 利用時**: "FlexCache write-back caches should be configured with a single constituent for the entire FlexCache volume" — multi-constituent FlexCache では意図しない eviction が発生する可能性がある（NetApp 公式ガイドライン）

2. **XLD の constituent あたり上限**: Origin constituent あたり 170 XLD の上限がある。FlexGroup Origin の場合、各 constituent が独立に XLD を管理するため、multi-constituent Origin では理論上より多くの concurrent write-back クライアントをサポート可能

3. **S3 AP + FlexGroup Origin の組み合わせ**: 
   - S3 AP 経由のファイル書き込みは FlexGroup の constituent 分散ロジックに従う
   - FlexCache Cache Volume が FlexGroup Origin のデータをキャッシュする際、constituent 単位でデータを取得する
   - この組み合わせに固有の制約は公式に文書化されていない

**結論:**
FlexGroup ボリュームを FlexCache Origin とすることは ONTAP 9.7+ でサポート済み。S3 AP を FlexGroup にアタッチすることも制限の記載なし。ただし、**両方を組み合わせた構成**（S3 AP アタッチ済み FlexGroup を FlexCache Origin に設定）は明示的に文書化されておらず、特に write-back mode との組み合わせでは constituent レベルの動作確認が必要。

**Next Action:** `validate` — TC-FC-007 で FlexGroup + S3 AP + FlexCache Origin の組み合わせテスト

**エビデンス:**
- [NetApp Docs: Supported and unsupported features for FlexCache volumes](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html) — "Beginning with ONTAP 9.7 both FlexVol volumes and FlexGroup volumes are supported as origin volumes"
- [NetApp Docs: Create ONTAP FlexCache volumes](https://docs.netapp.com/us-en/ontap/flexcache/create-volume-task.html)
- [NetApp Docs: FlexCache write-back guidelines](https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-guidelines.html) — single constituent 推奨
- [AWS Docs: Volume styles](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/volume-styles.html)
- [AWS API: CreateAndAttachS3AccessPoint](https://docs.aws.amazon.com/fsx/latest/APIReference/API_CreateAndAttachS3AccessPoint.html)

---

### S3 AP + FlexCache 調査サマリー

| Finding ID | トピック | 分類 | Next Action |
|:----------:|---------|:----:|:-----------:|
| FC-001 | S3 AP アタッチ済みボリュームの FlexCache Origin 設定可否（S3 NAS bucket: Origin 9.12.1+） | `supported (validated)` | 完了 |
| FC-002 | Cache Volume での S3 AP 独立アタッチ可否 | `unsupported`（FSx レイヤ、バージョン非依存） | 完了（9.18.1P5 で実測、2026-09-13） |
| FC-003 | FlexCache バージョン互換性要件 | `supported` | なし |
| FC-004 | Write-back mode と S3 AP の互換性 | `works_with_caveats` | 完了（同一ファイル concurrent write に注意） |
| FC-005 | NFS v4 Delegation / Lock Propagation | `partially_supported` | 検証テスト |
| FC-006 | Eviction ポリシーとキャッシュヒット率計測 | `supported` | なし |
| FC-007 | FlexGroup + S3 AP + FlexCache Origin | `partially_supported` | 検証テスト |

**サマリー:**
- **supported（明確にサポート確認済み）**: 3件（FC-001, FC-003, FC-006）
- **works_with_caveats（動作するが注意事項あり）**: 1件（FC-004）
- **partially_supported（条件付きサポート）**: 2件（FC-005, FC-007）
- **undocumented — validation required（未文書化、検証必要）**: 0件（FC-002 は 2026-09-13 に 9.18.1P5 で実測し、FSx レイヤの `unsupported` として確定）
- **unsupported（明確に非サポート）**: 0件

**主要な検証ポイント（残）:**
1. ~~Cache Volume に S3 AP を独立アタッチできること（FC-002）~~ — 2026-09-13 に決着。9.18.1P5 でも FSx API が拒否する
2. NFSv4.1 マウント時の Cache Volume での delegation 動作（FC-005）
3. FlexGroup Origin + S3 AP の組み合わせで constituent レベルの問題がないこと（FC-007）

---

## References（S3 AP + FlexCache セクション）

| # | タイトル | URL | 最終確認日 |
|---|---------|-----|:----------:|
| 1 | AWS Docs: Replicating your data with FlexCache | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html | 2026-07-06 |
| 2 | NetApp Docs: Supported and unsupported features for FlexCache volumes | https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html | 2026-07-06 |
| 3 | AWS Docs: Accessing your data via Amazon S3 access points | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html | 2026-07-06 |
| 4 | NetApp Docs: FlexCache write-back architecture | https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-architecture.html | 2026-07-06 |
| 5 | NetApp Docs: FlexCache write-back interoperability | https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-interoperability.html | 2026-07-06 |
| 6 | NetApp Docs: FlexCache write-back guidelines | https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-guidelines.html | 2026-07-06 |
| 7 | NetApp KB: FlexCache version compatibility | https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/Is_there_a_compatibility_suggestion_for_the_ONTAP_version_difference_between_cache_and_origin_regarding_FlexCache | 2026-07-06 |
| 8 | AWS What's New: FSx for ONTAP write-back mode | https://aws.amazon.com/about-aws/whats-new/2025/05/amazon-fsx-netapp-ontap-write-back-mode-ontap-flexcache-volumes | 2026-07-06 |
| 9 | NetApp REST API: volume_statistics_reference_flexcache_raw | https://library.netapp.com/ecmdocs/ECMLP2876965/html/models/volume_statistics_reference_flexcache_raw.html | 2026-07-06 |
| 10 | NetApp REST API: Manage FlexCache volumes | https://docs.netapp.com/us-en/ontap-restapi-9141/manage_flexcache_volumes.html | 2026-07-06 |
| 11 | NetApp Docs: Enable or disable NFSv4 write file delegations | https://docs.netapp.com/us-en/ontap/nfs-admin/enable-disable-nfsv4-write-file-delegations-task.html | 2026-07-06 |
| 12 | NetApp EMS: nblade.flexcachevolumeaccess events (9.17.1) | https://docs.netapp.com/us-en/ontap-ems-9171/nblade-flexcachevolumeaccess-events.html | 2026-07-06 |
| 13 | AWS Docs: Volume styles | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/volume-styles.html | 2026-07-06 |
| 14 | AWS API: CreateAndAttachS3AccessPoint | https://docs.aws.amazon.com/fsx/latest/APIReference/API_CreateAndAttachS3AccessPoint.html | 2026-07-06 |
| 15 | NetApp KB: FlexCache slow read performance and cache eviction | https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/FlexCache_slow_read_performance_and_cache_eviction | 2026-07-06 |
| 16 | NetApp Docs: Create ONTAP FlexCache volumes | https://docs.netapp.com/us-en/ontap/flexcache/create-volume-task.html | 2026-07-06 |
| 17 | NetApp Docs: Supported and unsupported features for FlexCache — "ONTAP S3 NAS bucket" row | https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html | 2026-07-11 |


## Cross-Cloud SnapMirror Paths

FSx for ONTAP を SnapMirror ソースとした各宛先へのレプリケーションパスのサポート状況を以下にまとめる。

### XC-001: FSx for ONTAP → FSx for ONTAP（同一リージョン）

| 項目 | 内容 |
|------|------|
| **Finding ID** | XC-001 |
| **Requirement Ref** | Requirement 3, AC 3.1, 3.4, 3.5 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

**調査結果:**

Volume-level SnapMirror Async でサポート済み。AWS ドキュメントに "This capability is available for both in-Region and cross-Region deployments" と明記されている。

- **制約**: Synchronous SnapMirror（StrictSync 含む）は FSx for ONTAP で非サポート。SVM-DR (SVMDR) も非サポート
- **最低 ONTAP バージョン**: ONTAP 9.11.1（FSx for ONTAP 初期リリースバージョン）
- **RPO 目安**: 5分間隔から設定可能。S3 AP write workload の変更レートに応じて調整
- **Intercluster LIF**: FSx for ONTAP で自動構成。手動設定不要

レプリケーション間隔は5分から設定可能だが、パフォーマンスへの影響を考慮して RPO/RTO 要件に基づき適切な間隔を選択する必要がある。

**エビデンス:**
- [AWS Docs — Replicating data using SnapMirror](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html)
  - "Only volume-level SnapMirror replication is supported by FSx for ONTAP. Synchronous SnapMirror, including StrictSync, is not supported."

---

### XC-002: FSx for ONTAP → FSx for ONTAP（Cross-Region）

| 項目 | 内容 |
|------|------|
| **Finding ID** | XC-002 |
| **Requirement Ref** | Requirement 3, AC 3.1, 3.4, 3.5 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

**調査結果:**

Volume-level SnapMirror Async でクロスリージョン構成がサポート済み。

- **制約**: Synchronous SnapMirror 非サポート（cross-region のレイテンシでは Sync は不適切）。SVM-DR 非サポート
- **最低 ONTAP バージョン**: ONTAP 9.11.1
- **RPO 目安**: 5分〜1時間。cross-region 帯域幅とデータ変更レートに依存
- **Intercluster LIF**: FSx for ONTAP で自動構成

Cross-region SnapMirror はネットワーク帯域幅に依存する。大量の S3 AP write workload がある場合、RPO 達成にはスループットキャパシティの適切なサイジングが必要。

**エビデンス:**
- [AWS Blog — Cross-region DR with FSx for ONTAP](https://aws.amazon.com/blogs/storage/cross-region-disaster-recovery-with-amazon-fsx-for-netapp-ontap)

---

### XC-003: FSx for ONTAP → On-Premises ONTAP

| 項目 | 内容 |
|------|------|
| **Finding ID** | XC-003 |
| **Requirement Ref** | Requirement 3, AC 3.1, 3.4, 3.5 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

**調査結果:**

Volume-level SnapMirror Async でサポート済み。AWS ドキュメントでは主に on-premises → FSx for ONTAP の移行方向で記載されているが、SnapMirror は双方向でサポートされる。

- **ネットワーク要件**: Direct Connect または VPN 経由で Intercluster LIF 間の到達性が必要
- **最低 ONTAP バージョン（ソース）**: FSx for ONTAP 現行バージョン（9.x）
- **最低 ONTAP バージョン（宛先）**: SnapMirror version-flexible replication により異なる ONTAP バージョンをサポート。[互換性マトリクス](https://docs.netapp.com/us-en/ontap/data-protection/compatible-ontap-versions-snapmirror-concept.html)で確認が必要
- **RPO 目安**: 5分〜1時間。WAN 帯域幅とレイテンシに大きく依存
- **Intercluster LIF**: オンプレミス ONTAP 側での手動構成が必要

**エビデンス:**
- [AWS Docs — Migrating to FSx for ONTAP using SnapMirror](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/migrating-fsx-ontap-snapmirror.html)
- [AWS Docs — Replicating data using SnapMirror](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html)
  - "replicating between two Amazon FSx file systems in AWS, or from on-premises to AWS"

---

### XC-004: FSx for ONTAP → Cloud Volumes ONTAP on GCP

| 項目 | 内容 |
|------|------|
| **Finding ID** | XC-004 |
| **Requirement Ref** | Requirement 3, AC 3.1, 3.4, 3.5 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

**調査結果:**

CVO は full ONTAP バイナリを実行するため、標準の SnapMirror inter-cluster replication が利用可能。

- **ネットワーク要件**: AWS ↔ GCP 間の VPN または Interconnect で Intercluster LIF 到達性が必要
- **最低 ONTAP バージョン**: CVO は ONTAP 9.x の最新バージョンを実行。version-flexible replication で互換性あり
- **RPO 目安**: 15分〜1時間。cross-cloud 帯域幅に依存
- **Cluster Peering Encryption**: クロスクラウド通信でも TLS 1.2 AES-256 GCM で暗号化（ONTAP 9.6+）

**エビデンス:**
- [NetApp — Cross-Region Replication with CVO](https://www.netapp.com/learn/cross-region-replication-with-cloud-volumes-ontap)
- [NetApp Docs — Data Replication Encryption](https://docs.netapp.com/us-en/ontap-technical-reports/ontap-security-hardening/data-replication-encryption.html)

---

### XC-005: FSx for ONTAP → Cloud Volumes ONTAP on Azure

| 項目 | 内容 |
|------|------|
| **Finding ID** | XC-005 |
| **Requirement Ref** | Requirement 3, AC 3.1, 3.4, 3.5 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

**調査結果:**

CVO on Azure は full ONTAP であり、SnapMirror Async をサポート。FSx for ONTAP → CVO on Azure の構成が利用可能。

- **ネットワーク要件**: AWS ↔ Azure 間の VPN で Intercluster LIF 到達性が必要
- **最低 ONTAP バージョン**: CVO は ONTAP 9.x の最新バージョンを実行
- **RPO 目安**: 15分〜1時間。cross-cloud 帯域幅に依存

**エビデンス:**
- [NetApp Blog — Azure Storage Replication SnapMirror](https://www.netapp.com/blog/azure-storage-replication-snapmirror/)

---

### XC-006: FSx for ONTAP → Google Cloud NetApp Volumes (GCNV) — External Replication

| 項目 | 内容 |
|------|------|
| **Finding ID** | XC-006 |
| **Requirement Ref** | Requirement 3, AC 3.1, 3.4, 3.5 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

**調査結果:**

GCNV External Replication は SnapMirror ベースで、外部 ONTAP システムからの Volume-level レプリケーションをサポート（2025年新機能）。GCP ドキュメントによると、External Replication は "ongoing replication solution for disaster recovery" として設計されており、replication direction の reverse（方向転換）もサポートする。

- **ネットワーク要件**: AWS ↔ GCP 間の VPN/Interconnect で Cluster Peering が必要。GCNV 側での Cluster Peering と SVM Peering のセットアップは ONTAP CLI コマンドで実施（GCNV がコマンドを生成し、ソース ONTAP 側で実行する）
- **最低 ONTAP バージョン（ソース）**: SnapMirror 互換性に準拠（GCNV ドキュメントでは具体的なソース側バージョン要件は明示されていない — 要追加確認）
- **GCNV 側バージョン**: Google マネージドのためユーザーによるバージョン選択不可
- **RPO 目安**: スケジュール間隔に基づく。Incremental transfer の完了時間はネットワーク帯域幅と変更データ量に依存
- **GCNV 側構成の注意**: ソースボリュームのパラメータ（サイズ、プロトコル設定、export/snapshot ポリシー）は自動読み取りされないため手動設定が必要

**エビデンス:**
- [GCP Docs — External Replication Overview](https://cloud.google.com/netapp/volumes/docs/protect-data/replicate-ontap/overview)
  - "External replication uses SnapMirror to replicate data from ONTAP-based systems to Google Cloud NetApp Volumes."
  - "Designed as an ongoing replication solution for disaster recovery, where the replication direction can be reversed."
- [NetApp Community — SnapMirror between ONTAP and GCNV](https://community.netapp.com/t5/Tech-ONTAP-Blogs/SnapMirror-between-ONTAP-and-Google-Cloud-NetApp-Volumes/ba-p/461292)

---

### XC-007: FSx for ONTAP → Azure NetApp Files (ANF)

| 項目 | 内容 |
|------|------|
| **Finding ID** | XC-007 |
| **Requirement Ref** | Requirement 3, AC 3.1 |
| **分類** | `unsupported` |
| **公開分類** | publicly verifiable |

**調査結果:**

**非サポート**。ANF は Cross-Volume Replication (CVR) のみをサポートしており、これは ANF-to-ANF 間でのみ動作する。外部 ONTAP システム（FSx for ONTAP を含む）からの SnapMirror external replication は ANF では利用不可。

**技術的理由:**
ANF は Azure 基盤上に独自実装された NetApp ストレージサービスであり、外部 ONTAP クラスターとの Cluster Peering 機能を公開していない。SnapMirror の制御プレーン（Cluster/SVM Peering）が ANF では利用者に開放されていないため、FSx for ONTAP → ANF の直接 SnapMirror は技術的に不可能。

**代替手段:**
1. FSx for ONTAP → CVO on Azure（SnapMirror）→ ANF（Azure DataSync / AzCopy 等でファイル同期）
2. FSx for ONTAP → CVO on Azure（SnapMirror）で Azure 内 ONTAP にデータ配置し、CVO から NFS/SMB 提供
3. AWS DataSync / rsync 等のファイルレベル同期ツール

ANF のレプリケーション機能は「Azure NetApp Files volume (source) in one region to another Azure NetApp Files volume (destination)」に限定されている。

**エビデンス:**
- [Microsoft Docs — Understand ANF Replication](https://learn.microsoft.com/en-us/azure/azure-netapp-files/replication)
  - ANF-to-ANF の cross-region/cross-zone replication のみ記載。外部 ONTAP からの SnapMirror に関する記載なし
- [Microsoft Docs — ANF Replication Requirements](https://learn.microsoft.com/en-us/azure/azure-netapp-files/cross-region-replication-requirements-considerations)

---

### XC-008: 暗号化と Snapshot 整合性（Cross-Cloud 共通事項）

| 項目 | 内容 |
|------|------|
| **Finding ID** | XC-008 |
| **Requirement Ref** | Requirement 3, AC 3.6, 3.7, 3.8 |
| **分類** | `supported` / `partially verifiable` |
| **公開分類** | publicly verifiable（暗号化動作）、undocumented — validation required（S3 AP 固有の Snapshot 相互作用） |

#### Cluster Peering Encryption（TLS in-transit）

- **デフォルト状態**: ONTAP 9.6 以降で新規作成された Cluster Peering 関係は TLS 1.2 AES-256 GCM 暗号化がデフォルトで有効
- **クロスクラウド動作**: Cluster Peering Encryption は FSx for ONTAP ↔ On-premises ONTAP、FSx for ONTAP ↔ CVO、FSx for ONTAP ↔ GCNV のいずれの構成でも有効に機能する（Peering 確立時に Pre-Shared Key (PSK) による認証と TLS セッション確立）
- **パフォーマンス影響**: NetApp KB によると、Cluster Peering Encryption は SnapMirror 転送速度に影響しない
- **注意事項**: ONTAP 9.5 以前のクラスターとの Peering では暗号化利用不可。FSx for ONTAP は 9.11.1+ のため問題なし

**エビデンス:**
- [NetApp Docs — Data Replication Encryption](https://docs.netapp.com/us-en/ontap-technical-reports/ontap-security-hardening/data-replication-encryption.html)
  - "Beginning in ONTAP 9.6, cluster peering encryption provides TLS 1.2 AES-256 GCM encryption support for ONTAP data replication features such as SnapMirror, SnapVault, and FlexCache."
- [NetApp KB — Enable encryption for cluster peering](https://kb.netapp.com/on-prem/ontap/DP/SnapMirror/SnapMirror-KBs/How_to_enable_encryption_for_cluster_peering_and_data_replication_in_ONTAP_9.6_and_later)
- [NetApp KB — Cluster Peering Encryption performance](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Protection_and_Security/SnapMirror/Does_implementing_Cluster_Peer_Encryption_influence_performance)

#### 保存時暗号化（NAE/NVE）のクロスクラウド動作

- **転送中のデータ**: NVE/NAE は WAFL レイヤーで暗号化するため、SnapMirror が転送するデータは NVE/NAE 暗号化されていない状態で送信される（in-transit 暗号化は Cluster Peering Encryption が担当）
- **宛先での暗号化**: NVE の場合、宛先ボリュームは独自の volume-level key で暗号化される。NAE の場合、宛先 aggregate の key で暗号化される。ソースと宛先で異なる暗号化キーが使用される
- **鍵管理**: 宛先クラスターで独自の Key Management（Onboard Key Manager (OKM) または external KMIP server）の設定が必要。クラウド間で暗号化キーは自動同期されない
- **混在構成**: ソースとデスティネーションは NVE、NAE、plaintext の任意の組み合わせが可能
- **FSx for ONTAP 固有**: FSx for ONTAP はデフォルトで全ボリュームが暗号化される（AWS KMS 統合）。宛先が FSx for ONTAP 以外の場合、宛先側での暗号化設定を個別に実施する必要がある

**エビデンス:**
- [NetApp KB — Does NVE encrypt data during SnapMirror transfer?](https://kb.netapp.com/on-prem/ontap/dm/Encryption-KBs/Does_NVE_encrypt_data_during_transfer_when_using_SnapMiror)
  - "NetApp SnapMirror sits above the NetApp WAFL layer, and thus the data sent by SnapMirror is not encrypted by NVE or NAE."
- [NetApp KB — Same encryption key at destination?](https://kb.netapp.com/on-prem/ontap/DM/Encryption/Encryption-KBs/If_I_use_NetApp_SnapMirror_to_mirror_my_encrypted_volume_to_a_different_cluster_is_the_same_encryption_key_used_at_the_destination)
  - "For NVE, the destination volume is created as a new volume and is encrypted with its own unique volume-level key."
- [NetApp KB — NVE source/dest mixing](https://kb.netapp.com/onprem/ontap/dm/Encryption/Does_NetApp_Volume_Encryption_have_to_be_enabled_on_both_source_and_destination_volumes_of_a_SnapMirror_relationship)
  - "Source and destination volumes can be a mixture of NVE, NAE, or plaintext volumes."

#### Snapshot + FSx for ONTAP S3 AP 同時書き込みの整合性

- **Snapshot の整合性保証**: ONTAP Snapshot はデフォルトで **crash-consistent** である。Snapshot 取得時点でのファイルシステムの一貫したポイントインタイムイメージを提供する
- **S3 AP 書き込み中の Snapshot 動作**: S3 AP 経由の書き込み中に Snapshot が取得された場合、完了した書き込み（WAFL にコミット済み）は Snapshot に含まれる。書き込み途中（uncommitted）のデータは含まれない
- **Application-consistent との違い**: ONTAP の Consistency Group 機能で application-consistent Snapshot を取得可能だが、ONTAP REST API ドキュメントによると「crash consistent と application consistent の間に ONTAP 内での機能的差異はない」。差異はアプリケーション側の quiesce/flush 操作の有無
- **S3 AP 書き込みへの影響**: S3 AP 経由で書き込まれたファイル（Parquet, CSV, JSON 等）は、各ファイルの PutObject が完了した時点で WAFL にコミットされる。完了した PutObject のデータは次の Snapshot に確実に含まれる。部分書き込み（multipart upload 途中）は含まれない可能性がある
- **SnapMirror への影響**: SnapMirror は Snapshot ベースのレプリケーションであるため、転送される内容は crash-consistent Snapshot の内容と等しい。宛先に転送されるデータは常にファイルシステムとして整合性のある状態
- **Conditional Writes 非サポートの影響**: FSx for ONTAP S3 AP は `If-None-Match` を非サポート（501 Not Implemented）。並行書き込み時の last-writer-wins 動作と SnapMirror Snapshot のタイミングでデータが「最新書き込みの途中」状態にならないかは、WAFL のアトミック性により保護される（各 PutObject は個別にアトミック）

**エビデンス:**
- [NetApp KB — ONTAP snapshots are crash-consistent by default](https://kb.netapp.com/Cloud/BlueXP/Cloud_Backup_Service/Does_BlueXP_Backup_and_Recovery_perform_integrity_checks_on_backups_taken%3F)
  - "By default, ONTAP snapshots are crash-consistent, meaning the snapshot captures the data exactly as it would appear after a sudden power failure or system crash."
- [NetApp Docs — Consistency Groups](https://docs.netapp.com/us-en/ontap/consistency-groups/)
- [NetApp REST API — Consistency Group Snapshots](https://docs.netapp.com/us-en/ontap-restapi-9161/manage_application_consistency_group_snapshots.html)
  - "There is no functional difference in ONTAP between crash consistent or application consistent snapshots."

---

### Cross-Cloud SnapMirror パス — サマリーテーブル

| Finding ID | パス | 分類 | 最低 ONTAP (Source) | 最低 ONTAP (Dest) | ネットワーク要件 |
|:---:|------|:---:|:---:|:---:|------|
| XC-001 | FSx for ONTAP → FSx for ONTAP (同一リージョン) | `supported` | 9.11.1 | 9.11.1 | VPC 内/Peering (自動構成) |
| XC-002 | FSx for ONTAP → FSx for ONTAP (Cross-Region) | `supported` | 9.11.1 | 9.11.1 | Cross-region (自動構成) |
| XC-003 | FSx for ONTAP → On-Premises ONTAP | `supported` | 9.11.1 | 互換性マトリクス参照 | Direct Connect / VPN |
| XC-004 | FSx for ONTAP → CVO on GCP | `supported` | 9.11.1 | CVO 最新 | AWS↔GCP VPN/Interconnect |
| XC-005 | FSx for ONTAP → CVO on Azure | `supported` | 9.11.1 | CVO 最新 | AWS↔Azure VPN |
| XC-006 | FSx for ONTAP → GCNV (External Replication) | `supported` | 9.11.1 (要確認) | GCNV マネージド | AWS↔GCP VPN/Interconnect |
| XC-007 | FSx for ONTAP → ANF | `unsupported` | N/A | N/A | N/A |
| XC-008 | 暗号化・Snapshot 整合性（横断事項） | `supported` | — | — | — |

---

### Cross-Cloud SnapMirror — Open Questions

1. **GCNV External Replication のソース側最低 ONTAP バージョン**: GCP ドキュメントではソース ONTAP の明示的なバージョン要件が記載されていない。FSx for ONTAP 9.15.1+ であれば互換性が高いと推定されるが確認が必要
2. **GCNV External Replication での S3 AP アタッチ済みボリュームの挙動**: S3 AP メタデータが SnapMirror 転送で GCNV に正しく伝搬されるかは未文書化（S3 AP は AWS 固有機能であるため、GCNV 側では S3 AP として機能しない — NFS/SMB アクセスのみ）
3. **ANF への代替パスの実現性**: FSx for ONTAP → CVO on Azure → ANF (CVR 経由) の多段構成が実用的かは要検証
4. **S3 AP 書き込みと Snapshot の厳密なアトミシティ**: 大容量ファイルの multipart upload 中の Snapshot 動作は検証で確認が望ましい


---

## Conditional Writes Impact

本セクションでは、FSx for ONTAP S3 AP における Conditional Writes（`If-None-Match` ヘッダー）非サポートが、SnapMirror レプリケーションのデータ整合性に与える影響を調査した結果を記録する。

### 調査背景

Amazon S3 は 2024年8月に Conditional Writes 機能を導入し、`If-None-Match: *` ヘッダーによるオブジェクト上書き防止をサポートした。Delta Lake、Apache Iceberg 等のテーブルフォーマットはこの機能を使用して concurrent commit の競合を防止している。

一方、FSx for ONTAP S3 AP はこのヘッダーを受信すると `501 Not Implemented` を返す。この制限が SnapMirror レプリケーションの整合性にどう影響するかが本セクションの調査対象である。

---

### CW-001: FSx for ONTAP S3 AP における `If-None-Match` 非サポートの確認

| 項目 | 内容 |
|------|------|
| **Finding ID** | CW-001 |
| **Requirement Ref** | Requirement 3, AC 3.3 |
| **分類** | `supported`（制限事項として確認済み） |
| **公開分類** | publicly verifiable |

#### 調査結果

**FSx for ONTAP S3 AP は `If-None-Match` ヘッダーを含む PutObject リクエストに対して `501 Not Implemented` を返す。** これはプロジェクト内検証で確認済みである。

**技術的背景:**

1. **ONTAP S3 supported actions ドキュメント**（NetApp 公式）によると、ONTAP 9.19.1 以降で Conditional Writes（`If-None-Match`、`If-Match`）が**ネイティブ S3 バケット**でサポートされるようになった。しかし、FSx for ONTAP S3 AP は「S3 NAS bucket（S3 in multiprotocol NAS volumes）」メカニズムに基づいており、ネイティブ S3 バケットとは異なる実装である。

2. **S3 NAS bucket の制約**: ONTAP ドキュメントに "Some of these actions, such as those associated with versioning, object locks, and other capabilities, are not supported when using S3 NAS buckets" と記載されている。Conditional Writes は S3 NAS bucket では未サポートと推定される。

3. **プロジェクト内検証エビデンス**: Delta Lake write テストにおいて、`_delta_log/00000000000000000000.json` のコミット時に delta-rs が `If-None-Match` ヘッダーを送信し、FSx for ONTAP S3 AP が `501 Not Implemented` を返すことを確認（`.private/evidence/delta-501-output.txt`）。

4. **NetApp KB CONTAP-221219**: Elasticsearch 8.13.1 が ONTAP S3 に対して未実装のヘッダーを使用した際に同様の 501 エラーが発生することが記録されている。

#### Conditional Writes 非サポートの影響（アプリケーション層）

`If-None-Match` が利用できないことによる直接的な影響:

| シナリオ | 影響 | 対策 |
|---------|------|------|
| 並行 PutObject（同一キー） | Last-writer-wins（先行書き込みが上書きされる） | アプリケーション側で排他制御を実装 |
| Delta Lake / Iceberg commit | コミットプロトコルが 501 で失敗 | 代替 commit 方式（DynamoDB lock 等）または S3 AP 非使用 |
| 単一 writer のシーケンシャル書き込み | 影響なし | — |

#### エビデンス

| ソース | URL / 参照先 |
|--------|-------------|
| NetApp Docs: ONTAP S3 supported actions（Conditional Writes — 9.19.1+, native S3 bucket のみ） | https://docs.netapp.com/us-en/ontap/s3-config/ontap-s3-supported-actions-reference.html |
| NetApp KB: CONTAP-221219（501 Not Implemented パターン） | https://kb.netapp.com/on-prem/ontap/da/S3/S3-Issues/CONTAP-221219 |
| プロジェクト内検証: Delta Lake 501 テスト結果 | `.private/evidence/delta-501-output.txt` |
| AWS What's New: Amazon S3 conditional writes（2024年8月） | https://aws.amazon.com/about-aws/whats-new/2024/08/amazon-s3-conditional-writes/ |

---

### CW-002: Conditional Writes 非サポートと SnapMirror 整合性の関係

| 項目 | 内容 |
|------|------|
| **Finding ID** | CW-002 |
| **Requirement Ref** | Requirement 3, AC 3.3 |
| **分類** | `supported`（SnapMirror 整合性への影響なし — ストレージ層の一貫性は保護される） |
| **公開分類** | publicly verifiable |

#### 調査結果

**結論: Conditional Writes 非サポートは SnapMirror のデータ整合性に影響を与えない。**

これは以下の3層の保護メカニズムによる:

#### 1. WAFL のアトミック書き込み保証

ONTAP の WAFL（Write Anywhere File Layout）ファイルシステムは、各書き込み操作に対してアトミック性を保証する:

- **Consistency Point メカニズム**: WAFL はクライアントからの書き込みを NVRAM に記録し、Consistency Point（CP）として一括でディスクにコミットする。CP の間は、全ての acknowledged 書き込みがファイルシステム上で一貫した状態を維持する
- **個別 PutObject のアトミック性**: S3 AP 経由の各 PutObject は、WAFL レベルでは1つのファイル書き込み操作としてアトミックに処理される。ファイルは「完全に存在する」か「存在しない」かのいずれかであり、部分的な状態は発生しない
- **Strong Consistency**: NetApp KB に明記されている通り、"ONTAP S3 operations rely on the WAFL file system mechanism, which inherently provides strong consistency. This design ensures that every write and overwrite operation is strongly consistent."

#### 2. Snapshot の crash-consistent 保証

ONTAP Snapshot は crash-consistent のポイントインタイムイメージを提供する:

- Snapshot 取得時点で WAFL にコミット済みの全データを含む
- 書き込み途中（uncommitted）のデータは含まない
- 「部分的に書き込まれたファイル」が Snapshot に含まれることはない（WAFL のアトミック性による）
- Snapshot 内のデータはファイルシステムとして常に整合している

#### 3. SnapMirror の Snapshot ベースレプリケーション

SnapMirror Asynchronous は Snapshot を転送単位として使用する:

- 初回: ベースライン Snapshot を完全転送
- 差分: 前回 Snapshot と最新 Snapshot のブロック差分のみ転送
- **転送内容は常に Snapshot の完全なコピー**であり、Snapshot 自体が crash-consistent であるため、デスティネーションに不整合なデータが到達することはない

#### レースコンディション分析

**懸念シナリオ:** 並行する2つの S3 AP PutObject（同一キー `data/file.parquet`）と SnapMirror Snapshot のタイミング:

```
時刻  t1: Writer A が PutObject 開始（key: data/file.parquet, version A）
時刻  t2: Writer B が PutObject 開始（key: data/file.parquet, version B）
時刻  t3: Writer A の PutObject が WAFL にコミット（file = version A）
時刻  t4: Writer B の PutObject が WAFL にコミット（file = version B ← 上書き）
時刻  t5: Snapshot 取得
```

**If-None-Match がある場合（標準 S3）:**
- Writer B の PutObject は `412 Precondition Failed` で拒否される（ファイルが既に存在するため）
- Snapshot 内容: version A

**If-None-Match がない場合（FSx for ONTAP S3 AP）:**
- Writer B の PutObject が成功し、version A を上書き（last-writer-wins）
- Snapshot 内容: version B（最後にコミットされた完全なファイル）

**整合性への影響:**

| 層 | If-None-Match あり | If-None-Match なし（FSx for ONTAP S3 AP） |
|---|---|---|
| **アプリケーション層** | Writer B の上書きを防止（並行制御あり） | Last-writer-wins（並行制御なし） |
| **ストレージ層（WAFL）** | ファイルは常にアトミック・完全 | ファイルは常にアトミック・完全 |
| **Snapshot** | crash-consistent ポイントインタイム | crash-consistent ポイントインタイム |
| **SnapMirror 転送** | Snapshot 内容をそのまま転送 | Snapshot 内容をそのまま転送 |
| **デスティネーション整合性** | ✅ 整合 | ✅ 整合 |

#### 結論

| 観点 | 評価 |
|------|------|
| SnapMirror デスティネーションのファイルシステム整合性 | **影響なし** — WAFL アトミック性と Snapshot crash-consistency により保護 |
| SnapMirror 転送データの完全性 | **影響なし** — Snapshot ベース転送は常に一貫したポイントインタイムを転送 |
| アプリケーション層のデータセマンティクス | **影響あり** — concurrent writers 間で last-writer-wins が発生。どの version が Snapshot に含まれるかはタイミング依存 |
| 推奨対策 | 単一 writer パターンの採用、またはアプリケーション側での排他制御（DynamoDB lock、SQS FIFO キュー等） |

**要約**: Conditional Writes 非サポートは「アプリケーション層での並行制御」の問題であり、「ストレージ層のデータ整合性」および「SnapMirror レプリケーションの一貫性」には一切影響しない。SnapMirror は常に crash-consistent な Snapshot のコピーを転送するため、デスティネーションに到達するデータは常にファイルシステムとして整合している。

#### エビデンス

| ソース | URL / 参照先 |
|--------|-------------|
| NetApp KB: ONTAP S3 — WAFL strong consistency | https://kb.netapp.com/on-prem/ontap/da/S3/S3-KBs/Why_can't_the_S3_bucket_consistency_level_be_changed_in_ONTAP_S3 |
| NetApp KB: Consistency Points — all acknowledged operations preserved intact | https://kb.netapp.com/on-prem/ontap/Perf/Perf-KBs/What_are_the_benefits_of_Consistency_Points_versus_Direct_Writes |
| NetApp Docs: Consistency Groups（crash-consistent snapshots） | https://docs.netapp.com/us-en/ontap/consistency-groups/ |
| NetApp Blog: SnapMirror — snapshot compared and changed blocks replicated | https://www.netapp.com/fr/blog/snapmirror-data-replication-aws/ |
| NetApp Docs: SnapMirror disaster recovery concept | https://docs.netapp.com/us-en/ontap/data-protection/snapmirror-disaster-recovery-concept.html |
| XC-008（本ドキュメント内）: Snapshot + S3 AP 同時書き込みの整合性 | 上記 Cross-Cloud SnapMirror Paths セクション参照 |

---

### Conditional Writes Impact — サマリーテーブル

| Finding ID | トピック | 分類 | SnapMirror 整合性影響 |
|:----------:|---------|:----:|:--------------------:|
| CW-001 | FSx for ONTAP S3 AP の `If-None-Match` 非サポート（501） | `supported`（制限確認済み） | なし |
| CW-002 | Conditional Writes 非サポートと SnapMirror 整合性の関係 | `supported`（影響なし確認） | **なし** — ストレージ層整合性は WAFL + Snapshot + SnapMirror の3層で保護 |

**サマリー:**
- **ストレージ層**: WAFL のアトミック書き込み + Consistency Point により、各 PutObject は常に完全な状態でファイルシステムに記録される
- **Snapshot 層**: crash-consistent ポイントインタイムイメージにより、不完全なファイルが Snapshot に含まれることはない
- **SnapMirror 層**: Snapshot の差分ブロック転送により、デスティネーションは常にソースの特定ポイントインタイムの完全なコピーを保持する
- **アプリケーション層の注意**: Conditional Writes 非サポートにより、同一キーへの concurrent write は last-writer-wins となる。これはデータの「正しさ」の問題であり、「整合性」の問題ではない。アプリケーション設計で単一 writer パターンまたは外部ロックメカニズムにより対処する

---

### References（Conditional Writes Impact セクション）

| # | タイトル | URL | 最終確認日 |
|---|---------|-----|:----------:|
| 1 | NetApp Docs: ONTAP S3 supported actions | https://docs.netapp.com/us-en/ontap/s3-config/ontap-s3-supported-actions-reference.html | 2026-07-11 |
| 2 | NetApp KB: ONTAP S3 WAFL strong consistency | https://kb.netapp.com/on-prem/ontap/da/S3/S3-KBs/Why_can't_the_S3_bucket_consistency_level_be_changed_in_ONTAP_S3 | 2026-07-11 |
| 3 | NetApp KB: Consistency Points benefits | https://kb.netapp.com/on-prem/ontap/Perf/Perf-KBs/What_are_the_benefits_of_Consistency_Points_versus_Direct_Writes | 2026-07-11 |
| 4 | NetApp KB: CONTAP-221219 (501 Not Implemented) | https://kb.netapp.com/on-prem/ontap/da/S3/S3-Issues/CONTAP-221219 | 2026-07-11 |
| 5 | NetApp Docs: Consistency Groups | https://docs.netapp.com/us-en/ontap/consistency-groups/ | 2026-07-11 |
| 6 | NetApp Blog: SnapMirror data replication | https://www.netapp.com/fr/blog/snapmirror-data-replication-aws/ | 2026-07-11 |
| 7 | NetApp Docs: SnapMirror disaster recovery concept | https://docs.netapp.com/us-en/ontap/data-protection/snapmirror-disaster-recovery-concept.html | 2026-07-11 |
| 8 | AWS What's New: Amazon S3 conditional writes | https://aws.amazon.com/about-aws/whats-new/2024/08/amazon-s3-conditional-writes/ | 2026-07-11 |
| 9 | プロジェクト内検証: Delta Lake 501 テスト結果 | `.private/evidence/delta-501-output.txt` | 2026-07-06 |


## FlexCache Cross-Region/Cross-Cloud

本セクションでは、FlexCache のクロスリージョンおよびクロスクラウド対応状況を調査した結果を記録する。FlexCache は SnapMirror と異なりリアルタイムキャッシングを提供するため、ネットワークレイテンシがパフォーマンスに直接影響する点が重要な設計考慮事項である。

---

### FCXC-001: FSx for ONTAP 間の Inter-Region FlexCache

| 項目 | 内容 |
|------|------|
| **Finding ID** | FCXC-001 |
| **Requirement Ref** | Requirement 9, AC 9.1 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

#### 調査結果

FSx for ONTAP 間の FlexCache は、同一リージョンおよびクロスリージョンの両方でサポートされている。AWS 公式ドキュメント「Replicating your data with FlexCache」に以下の構成が明示されている:

- Origin: FSx for ONTAP → Cache: FSx for ONTAP（同一リージョン/別リージョン）
- Origin: On-premises ONTAP → Cache: FSx for ONTAP
- Origin: FSx for ONTAP → Cache: On-premises ONTAP

クロスリージョン構成では、VPC Peering、AWS Transit Gateway、または Site-to-Site VPN による Intercluster LIF 間の到達性が前提条件となる。

**Write mode サポート（クロスリージョン）:**
- Write-around mode: サポート済み（デフォルト、read-heavy ワークロード向け）
- Write-back mode: サポート済み（ONTAP 9.15.1+、write-heavy ワークロード向け）

**ネットワーク要件:**
- Security Group: ICMP および TCP ポート 11104, 11105 の双方向許可が必要
- Intercluster LIF: FSx for ONTAP で自動構成。AWS Console で「Inter-cluster endpoint - IP addresses」として確認可能

#### エビデンス

- [AWS Docs: Replicating your data with FlexCache](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html)
- [AWS Docs: Creating a FlexCache](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/create-flexcache.html) — Prerequisites セクション

---

### FCXC-002: FSx for ONTAP → On-Premises ONTAP（Direct Connect/VPN 経由）の FlexCache

| 項目 | 内容 |
|------|------|
| **Finding ID** | FCXC-002 |
| **Requirement Ref** | Requirement 9, AC 9.2 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

#### 調査結果

FSx for ONTAP と On-premises ONTAP 間の FlexCache は双方向でサポートされている。AWS 公式ドキュメントの FlexCache 対応構成テーブルに明示:

| Origin | Cache |
|--------|-------|
| On-premises NetApp ONTAP | FSx for ONTAP |
| FSx for ONTAP | On-premises NetApp ONTAP |

**ネットワーク要件:**
- Direct Connect または Site-to-Site VPN 経由で Intercluster LIF 間の TCP 到達性（ポート 11104, 11105）が必須
- ICMP（ping）による到達性確認も必要
- On-premises ONTAP 側で Intercluster LIF の手動構成が必要（FSx for ONTAP 側は自動構成）

**レイテンシ考慮事項:**
- Write-around mode: WAN レイテンシは主にキャッシュミス時とメタデータ操作に影響。キャッシュヒット時はローカル速度
- Write-back mode: WAN RTT 200ms 以下が推奨上限（NetApp テスト済み範囲）
- Direct Connect 利用時の典型的レイテンシ: 1〜10ms（同一リージョン近隣）、10〜50ms（遠距離）
- VPN 利用時: レイテンシ変動が大きく、FlexCache write-back には不向きな場合がある

#### エビデンス

- [AWS Docs: Replicating your data with FlexCache — supported configurations](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html)
- [AWS Docs: Creating a FlexCache — Prerequisites](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/create-flexcache.html)

---

### FCXC-003: FSx for ONTAP → CVO（GCP/Azure）間の FlexCache

| 項目 | 内容 |
|------|------|
| **Finding ID** | FCXC-003 |
| **Requirement Ref** | Requirement 9, AC 9.3 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

#### 調査結果

Cloud Volumes ONTAP (CVO) は完全な ONTAP バイナリを実行するため、標準の FlexCache inter-cluster 構成が利用可能である。FSx for ONTAP を Origin として CVO on GCP/Azure を Cache（またはその逆）とする構成がサポートされる。

**サポートされる構成:**

| Origin | Cache | ネットワーク |
|--------|-------|-------------|
| FSx for ONTAP | CVO on GCP | AWS ↔ GCP VPN/Interconnect |
| FSx for ONTAP | CVO on Azure | AWS ↔ Azure VPN |
| CVO on GCP/Azure | FSx for ONTAP | 同上（逆方向） |

**技術的根拠:**
- CVO は ONTAP 9.x の最新バージョンを実行し、FlexCache の全機能（write-around / write-back）をサポート
- Cluster Peering は TLS 1.2 暗号化付きで確立可能（ONTAP 9.6+）
- バージョン互換性ルール（Origin/Cache 間4バージョン以内）に準拠する必要あり

**ネットワーク要件:**
- AWS ↔ GCP/Azure 間の VPN または専用線接続
- Intercluster LIF 間で TCP ポート 11104, 11105 + ICMP の到達性
- CVO 側で Intercluster LIF の構成（ONTAP CLI または ONTAP System Manager で設定）

**レイテンシ注意:**
- クロスクラウド VPN の典型的レイテンシは 20〜100ms
- Write-back mode の推奨上限（RTT 200ms）にはクロスクラウドでも通常収まるが、安定性を考慮すると write-around mode が推奨

#### エビデンス

- [NetApp Docs: Accelerate data access with FlexCache volumes on CVO](https://docs.netapp.com/us-en/bluexp-cloud-volumes-ontap/task-accelerate-data-access.html)
- [NetApp Blog: How to set up FlexCache with CVO on AWS](https://bluexp.netapp.com/blog/aws-cvo-blg-how-to-set-up-flexcache-with-cloud-volumes-ontap-on-aws)
- [NetApp KB: Azure CVO FlexCache volume availability](https://kb.netapp.com/Advice_and_Troubleshooting/Cloud_Services/Cloud_Volumes_ONTAP_(CVO)/Azure_CVO_FlexCache_volume_is_suddenly_unavailable)

---

### FCXC-004: Intercluster LIF 構成要件（各パス別）

| 項目 | 内容 |
|------|------|
| **Finding ID** | FCXC-004 |
| **Requirement Ref** | Requirement 9, AC 9.4 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

#### 調査結果

FlexCache の Intercluster LIF 構成要件を各クロスバウンダリパス別に整理する。

**共通要件（全パス）:**
- TCP ポート 11104（Intercluster communication）: 双方向許可
- TCP ポート 11105（Intercluster management）: 双方向許可
- ICMP: Cluster peer health check 用
- Cluster Peering Encryption: TLS 1.2 AES-256 GCM（ONTAP 9.6+ でデフォルト有効）

**パス別構成:**

| パス | Origin 側 LIF | Cache 側 LIF | ネットワーク | 帯域幅推奨 |
|------|-------------|-------------|------------|-----------|
| FSx ↔ FSx（同一リージョン） | 自動構成 | 自動構成 | VPC 内/Peering | データ変更レートに依存 |
| FSx ↔ FSx（クロスリージョン） | 自動構成 | 自動構成 | Transit Gateway / VPC Peering | データ変更レートに依存 |
| FSx ↔ On-premises ONTAP | 自動構成（FSx 側） | 手動構成（On-prem 側） | Direct Connect / VPN | 1 Gbps 以上推奨 |
| FSx ↔ CVO (GCP/Azure) | 自動構成（FSx 側） | CVO 側で構成 | Cross-cloud VPN | 1 Gbps 以上推奨 |
| ONTAP ↔ GCNV (Cache) | 手動構成（Origin 側） | GCNV マネージド | HA VPN / Interconnect | ワークロード依存 |

**推奨最大 RTT レイテンシ閾値:**

| モード | 推奨最大 RTT | 根拠 |
|--------|:----------:|------|
| Write-around (read-heavy) | 明示的上限なし（実用上 ≤ 300ms） | キャッシュヒット時はローカル速度。ミス時のみ WAN レイテンシが影響 |
| Write-back | ≤ 200ms | NetApp 公式ガイドライン: "WAN round-trip times between the cache and origin not exceeding 200ms" |

**帯域幅に関する考慮事項:**
- NetApp 公式ガイドラインでは「Low bandwidth and/or lossy intercluster networks can have a significant negative effect on FlexCache write-back performance」と記載
- 明示的な最低帯域幅要件は文書化されていないが、ワークロードの書き込みレートに十分な帯域が必要
- Write-back mode では dirty data flush（非同期）が帯域を消費するため、書き込みレートを上回る帯域確保が推奨

#### エビデンス

- [AWS Docs: Creating a FlexCache — Prerequisites（ポート要件）](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/create-flexcache.html)
- [NetApp Docs: FlexCache write-back guidelines（RTT 200ms、帯域幅記載）](https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-guidelines.html)
- [NetApp Docs: Data Replication Encryption（Cluster Peering Encryption）](https://docs.netapp.com/us-en/ontap-technical-reports/ontap-security-hardening/data-replication-encryption.html)

---

### FCXC-005: GCNV/ANF での FlexCache 非サポート状況と代替手段

| 項目 | 内容 |
|------|------|
| **Finding ID** | FCXC-005 |
| **Requirement Ref** | Requirement 9, AC 9.5 |
| **分類** | `partially_supported`（GCNV: Cache のみ対応 / ANF: 非サポート） |
| **公開分類** | publicly verifiable |

#### 調査結果

**Google Cloud NetApp Volumes (GCNV) — Cache Volume のみサポート:**

GCNV は FlexCache の **Cache Volume としてのみ**動作可能であり、Origin Volume にはなれない。GCP ドキュメントに明記: "Volumes in NetApp Volumes can only serve as cache volumes" (Flex Unified ONTAP-mode を除く)。

- FSx for ONTAP (Origin) → GCNV (Cache): **サポート**（write-around のみ、write-back は要件確認）
- GCNV (Origin) → FSx for ONTAP (Cache): **非サポート**（GCNV は Origin 不可）

GCNV FlexCache の制約:
- **NFSv4 非サポート**: GCNV の FlexCache は NFSv3 のみ対応（プラットフォーム固有の制限）
- Write-around mode がデフォルト。Write-back も利用可能だが、GCNV 公式ドキュメントでは write-around を推奨
- Global file locking はオプション（有効化するとパフォーマンスに影響）
- GCNV が Cache の場合、Origin への接続断時に disconnected mode で既にキャッシュされたデータへの read は継続可能

**Azure NetApp Files (ANF) — FlexCache 非サポート:**

ANF は FlexCache をサポートしていない。ANF は Azure 基盤上に独自実装された NetApp ストレージサービスであり、外部 ONTAP クラスターとの Cluster Peering（FlexCache の前提条件）を公開していない。

**代替手段:**

| ターゲット | FlexCache | 代替手段 |
|-----------|:---------:|---------|
| GCNV (Cache) | ✅ Cache のみ | FSx for ONTAP を Origin とする FlexCache 構成 |
| GCNV (Origin) | ❌ | SnapMirror External Replication (XC-006) で GCNV にデータ配置 → GCNV から NFS 提供 |
| ANF | ❌ | SnapMirror → CVO on Azure → ANF (CVR) の多段構成、または CVO on Azure を直接利用 |

#### エビデンス

- [GCP Docs: FlexCache overview — "Volumes in NetApp Volumes can only serve as cache volumes"](https://docs.cloud.google.com/netapp/volumes/docs/configure-and-use/volumes/cache-ontap-volumes/overview)
- [GCP Blog: Announcing enhancements to GCNV（FlexCache GA 発表）](https://cloud.google.com/blog/products/storage-data-transfer/announcing-enhancements-to-google-cloud-netapp-volumes/)
- [NetApp Community: Introducing FlexCache for GCNV](https://community.netapp.com/t5/Tech-ONTAP-Blogs/Introducing-FlexCache-for-Google-Cloud-NetApp-Volumes/ba-p/464229)

---

### FCXC-006: ネットワークレイテンシの FlexCache パフォーマンスへの影響

| 項目 | 内容 |
|------|------|
| **Finding ID** | FCXC-006 |
| **Requirement Ref** | Requirement 9, AC 9.6 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

#### 調査結果

FlexCache のパフォーマンスはネットワークレイテンシと帯域幅に強く依存する。Write mode によって影響のパターンが大きく異なる。

**Write-around mode（read-heavy ワークロード向け）:**

| 操作 | レイテンシ影響 | 説明 |
|------|:----------:|------|
| Read（キャッシュヒット） | なし | ローカルストレージから直接提供。LAN 速度 |
| Read（キャッシュミス） | WAN RTT × 1 | Origin からデータ取得。初回のみ |
| Write | WAN RTT × 1（最低） | 書き込みは Origin に転送、Origin での commit 後に ACK |
| Metadata 操作 | WAN RTT × 1〜2 | ファイル作成/削除等は Origin との通信が必要 |

- **推奨最大レイテンシ**: 明示的な上限は NetApp ドキュメントに記載なし。実用上、RTT 300ms 程度までは read-heavy ワークロードで十分な効果が得られる（キャッシュヒット率が高い前提）
- **WAN 最適化**: キャッシュヒット率がパフォーマンスの鍵。ヒット率が低い場合（cold data への頻繁なアクセス）、WAN レイテンシが直接性能に影響する
- **ベストプラクティス**: Cache prepopulation を活用し、事前に頻繁アクセスデータをキャッシュに配置

**Write-back mode（write-heavy ワークロード向け）:**

| 操作 | レイテンシ影響 | 説明 |
|------|:----------:|------|
| Write（XLD 保持中） | なし | ローカル commit + 即時 ACK。LAN 速度 |
| Write（XLD 取得時） | WAN RTT × 1〜3 | Origin からの XLD 取得（他 Cache からの revoke 含む場合はさらに遅延） |
| Dirty data flush | 非同期 | バックグラウンドで Origin に書き戻し。クライアントレイテンシに影響なし |
| Read（他 Cache が XLD 保持中） | Hang/遅延 | XLD revoke + dirty data flush 完了まで read がブロック |

- **推奨最大レイテンシ**: RTT ≤ 200ms（NetApp 公式テスト済み範囲）
- **帯域幅**: "Low bandwidth and/or lossy intercluster networks can have a significant negative effect on FlexCache write-back performance"
- **ファイルサイズ**: 100GB 未満のファイルでテスト済み
- **推奨 ONTAP バージョン**: 9.17.1P1 以降を Origin/Cache 双方で強く推奨

**レイテンシとモード選択ガイドライン:**

| WAN RTT | 推奨モード | 理由 |
|---------|----------|------|
| < 10ms（同一リージョン） | Write-back | 書き込みがローカル速度。最大パフォーマンス |
| 10〜50ms（近距離 DC/DX） | Write-back（条件付き） | ワークロードが少数大ファイルの場合は有効 |
| 50〜200ms（クロスリージョン/クロスクラウド） | Write-around 推奨 / Write-back 可 | Write-back は XLD 取得時のレイテンシが顕著。read-heavy なら write-around で十分 |
| > 200ms | Write-around のみ | Write-back はテスト範囲外。予期しない動作の可能性 |

**Delete 操作の特記事項:**
NetApp KB によると、FlexCache 環境での delete 操作は高 WAN RTT 時に特に高レイテンシとなる。キャッシュで以前読み取られたファイルの delete は、未キャッシュファイルの delete よりも著しく遅い。

#### エビデンス

- [NetApp Docs: FlexCache write-back guidelines（RTT 200ms、ファイル 100GB、帯域幅記載）](https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-guidelines.html)
- [NetApp Docs: FlexCache write-back architecture（XLD、dirty data flush、disconnected mode）](https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-architecture.html)
- [NetApp KB: High latency when performing delete operations due to high WAN RTT](https://kb.netapp.com/on-prem/ontap/Perf/Perf-KBs/High_latency_when_performing_delete_operations_due_to_high_WAN_RTT)
- [AWS Docs: Replicating your data with FlexCache（write mode 選択ガイダンス）](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html)

---

### FCXC-007: FlexCache Disconnect Mode（WAN 切断時の Cache Volume 動作）

| 項目 | 内容 |
|------|------|
| **Finding ID** | FCXC-007 |
| **Requirement Ref** | Requirement 9, AC 9.7 |
| **分類** | `supported` |
| **公開分類** | publicly verifiable |

#### 調査結果

FlexCache の disconnect mode（Origin との接続断時の動作）は、write mode によって大きく異なる。

**Write-around mode での disconnect 動作:**

| 操作 | 動作 | 説明 |
|------|------|------|
| Read（キャッシュ済みデータ） | **継続可能** | 既にキャッシュされたデータへの read は Origin 不要で提供可能 |
| Read（未キャッシュデータ） | **Hang / タイムアウト** | Origin からのデータ取得不可 |
| Write | **失敗** | 全ての write は Origin に転送されるため、接続断で完了不可 |
| Metadata 操作 | **失敗 / タイムアウト** | ファイル作成/削除等は Origin 通信必須 |

Write-around mode では、Origin が全データの source of truth を持つため、disconnect 時に既キャッシュデータへの read は安全に提供できる（stale data の可能性はあるが一貫性は保たれる）。

**Write-back mode での disconnect 動作:**

| 操作 | 動作 | 説明 |
|------|------|------|
| Read（XLD 保持中のファイル — disconnected cache にて） | **N/A** | disconnect した cache 自体のクライアントは read 試行時にタイムアウト |
| Read（XLD が disconnected cache に存在するファイル — 他の cache/origin にて） | **Hang** | XLD revoke 不可のため、全ての場所で read がブロック |
| Write（XLD 保持中） | **不確定** | ローカル commit は可能だが Origin への flush 不可。dirty data が蓄積 |
| 全操作（XLD なしのファイル） | Write-around と同様 | キャッシュ済み read は可能、write は失敗 |

**重要**: Write-back mode で XLD を保持する Cache が disconnect すると、そのファイルへの read は**全ての場所（他の Cache および Origin）でブロック**される。これは 100% の一貫性・整合性を保証するための設計上のトレードオフである。

**EMS イベント:**

接続断時に以下の EMS イベントが発生する:
- `flexcache.originDisconnected` (EMERGENCY): Cache Volume が Origin と通信不可。クライアントに stale data が提供される可能性、未キャッシュデータへの I/O はレスポンスしない
- `flexcache.cacheDisconnected` (ALERT): Origin Volume が Cache と通信不可。Cache に stale data が残る可能性

**再接続/Resync 手順:**

1. **自動再接続**: WAN 復旧後、FlexCache は自動的に Origin との通信を再開する。追加の手動操作は通常不要
2. **接続確認**: `network ping` で Intercluster LIF 間の到達性を確認
3. **Write-back の dirty data flush**: WAN 復旧後、Cache に蓄積された dirty data は自動的に Origin にフラッシュバックされる
4. **長時間 disconnect 時の XLD 手動 revoke**: 長期間の disconnect で特定ファイルへの read がブロックされ続ける場合、管理者が Origin で手動 XLD revoke を実行可能。**ただし dirty data は失われる**

**手動 XLD revoke（緊急時のみ）:**

NetApp 公式ドキュメントに記載: "In the event a cache with an XLD for a file is disconnected for an extended period of time, a system administrator can manually revoke the XLD at the origin. This will allow IO to the file to resume at the surviving caches and the origin."

> **警告**: 手動 XLD revoke は disconnected cache の dirty data を喪失する。壊滅的な障害時のみ使用すべき。

**GCNV Cache での disconnect 動作:**

GCP ドキュメントによると、GCNV FlexCache でも「Enhanced availability: If a network disconnects from the origin (disconnected mode), the cache can continue to serve data that's already cached」と記載されており、write-around mode での既キャッシュデータ read 継続が確認されている。

#### エビデンス

- [NetApp Docs: FlexCache write-back architecture — Disconnected mode](https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-architecture.html)
- [NetApp EMS: flexcache.originDisconnected events](https://docs.netapp.com/us-en/ontap-ems-9151/flexcache-origindisconnected-events.html)
- [NetApp EMS: flexcache.cacheDisconnected events](https://docs.netapp.com/us-en/ontap-ems-9161/flexcache-cachedisconnected-events.html)
- [NetApp KB: FlexCache Volumes Disconnected After Firewall Upgrade](https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/FlexCache_Volumes_Disconnected_After_Firewall_Upgrade)
- [GCP Docs: FlexCache overview（disconnected mode 記載）](https://docs.cloud.google.com/netapp/volumes/docs/configure-and-use/volumes/cache-ontap-volumes/overview)

---

### FlexCache Cross-Region/Cross-Cloud — サマリーテーブル

| Finding ID | トピック | 分類 | Next Action |
|:----------:|---------|:----:|:-----------:|
| FCXC-001 | FSx for ONTAP 間 Inter-Region FlexCache | `supported` | なし |
| FCXC-002 | FSx for ONTAP ↔ On-Premises ONTAP (DX/VPN) | `supported` | なし |
| FCXC-003 | FSx for ONTAP ↔ CVO (GCP/Azure) | `supported` | なし |
| FCXC-004 | Intercluster LIF 構成要件（パス別/RTT 閾値） | `supported` | なし |
| FCXC-005 | GCNV/ANF FlexCache 対応状況と代替手段 | `partially_supported` | なし（ドキュメント調査完了） |
| FCXC-006 | ネットワークレイテンシの FlexCache パフォーマンス影響 | `supported` | なし |
| FCXC-007 | FlexCache Disconnect Mode（WAN 切断時動作） | `supported` | なし |

**サマリー:**
- **supported（明確にサポート確認済み）**: 6件（FCXC-001〜004, 006, 007）
- **partially_supported（条件付き）**: 1件（FCXC-005 — GCNV は Cache のみ、ANF は非サポート）
- **unsupported**: 0件
- **undocumented — validation required**: 0件

**主要な設計判断ポイント:**
1. **Write mode 選択**: WAN RTT ≤ 200ms かつ大ファイル中心のワークロードであれば write-back が有効。それ以外は write-around を推奨
2. **GCNV 利用時**: GCNV は Cache としてのみ動作可能。Origin は FSx for ONTAP または On-premises ONTAP に配置する必要あり。NFSv4 非サポートに注意
3. **ANF へのデータ配信**: FlexCache 不可。SnapMirror → CVO on Azure 経由、または CVO on Azure を直接利用
4. **Disconnect 耐性**: Write-around mode はキャッシュ済みデータの read 継続が可能で耐障害性が高い。Write-back mode は disconnect 時にファイルレベルで I/O ブロックが発生するリスクがある

---

### References（FlexCache Cross-Region/Cross-Cloud セクション）

| # | タイトル | URL | 最終確認日 |
|---|---------|-----|:----------:|
| 1 | AWS Docs: Replicating your data with FlexCache | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html | 2026-07-14 |
| 2 | AWS Docs: Creating a FlexCache | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/create-flexcache.html | 2026-07-14 |
| 3 | NetApp Docs: FlexCache write-back guidelines | https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-guidelines.html | 2026-07-14 |
| 4 | NetApp Docs: FlexCache write-back architecture | https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-architecture.html | 2026-07-14 |
| 5 | NetApp EMS: flexcache.originDisconnected events | https://docs.netapp.com/us-en/ontap-ems-9151/flexcache-origindisconnected-events.html | 2026-07-14 |
| 6 | NetApp EMS: flexcache.cacheDisconnected events | https://docs.netapp.com/us-en/ontap-ems-9161/flexcache-cachedisconnected-events.html | 2026-07-14 |
| 7 | NetApp KB: High latency delete operations due to high WAN RTT | https://kb.netapp.com/on-prem/ontap/Perf/Perf-KBs/High_latency_when_performing_delete_operations_due_to_high_WAN_RTT | 2026-07-14 |
| 8 | NetApp KB: FlexCache Volumes Disconnected After Firewall Upgrade | https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/FlexCache_Volumes_Disconnected_After_Firewall_Upgrade | 2026-07-14 |
| 9 | NetApp Docs: Accelerate data access with FlexCache on CVO | https://docs.netapp.com/us-en/bluexp-cloud-volumes-ontap/task-accelerate-data-access.html | 2026-07-14 |
| 10 | GCP Docs: FlexCache overview (GCNV) | https://docs.cloud.google.com/netapp/volumes/docs/configure-and-use/volumes/cache-ontap-volumes/overview | 2026-07-14 |
| 11 | GCP Blog: Announcing enhancements to GCNV | https://cloud.google.com/blog/products/storage-data-transfer/announcing-enhancements-to-google-cloud-netapp-volumes/ | 2026-07-14 |
| 12 | NetApp Community: Introducing FlexCache for GCNV | https://community.netapp.com/t5/Tech-ONTAP-Blogs/Introducing-FlexCache-for-Google-Cloud-NetApp-Volumes/ba-p/464229 | 2026-07-14 |
| 13 | NetApp Docs: Data Replication Encryption | https://docs.netapp.com/us-en/ontap-technical-reports/ontap-security-hardening/data-replication-encryption.html | 2026-07-14 |
| 14 | NetApp Blog: How FlexCache Makes the World Smaller | https://www.netapp.com/blog/how-netapp-flexcache-makes-the-world-smaller/ | 2026-07-14 |
| 15 | NetApp KB: Why can clients still access FlexCache if origin disconnected | https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/Why_can_clients_still_access_a_FlexCache_volume_if_the_origin_is_disconnected | 2026-07-14 |


## Version Matrix

本セクションでは、S3 AP + SnapMirror + FlexCache マルチクラウドデータ配信に関連する各機能の最低 ONTAP バージョン要件と、各プラットフォームのサポート状況をマトリクス形式で整理する。Phase 1 調査（Finding: SM, FC, XC, FCXC）の結果に基づく。

---

### Feature × Platform 互換性マトリクス

| Feature | Min ONTAP (Source) | Min ONTAP (Dest) | FSx for ONTAP | On-prem ONTAP | CVO | GCNV | ANF |
|---------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| S3 AP (basic) | 9.14.1 | N/A | ✅ | N/A | N/A | N/A | N/A |
| S3 NAS bucket | 9.12.1 | N/A | ✅ | ✅ | ✅ | ? | N/A |
| SnapMirror Async (volume) | 9.11.1 | 9.11.1 | ✅ | ✅ | ✅ | ✅ (External Rep) | ❌ |
| SnapMirror Sync | — | — | ❌ | — | — | — | — |
| SVM-DR | — | — | ❌ | — | — | — | — |
| FlexCache (write-around) | 9.5 (FlexVol) / 9.7 (FlexGroup) | same | ✅ | ✅ | ✅ | ✅ (cache only) | ❌ |
| FlexCache write-back | 9.15.1 | 9.15.1 | ✅ | ✅ | ✅ | ? | ❌ |
| S3 NAS bucket + FlexCache Origin | 9.12.1 | N/A | ✅ (undocumented) | ✅ | ✅ | — | — |
| S3 NAS bucket + FlexCache Cache | 9.18.1 | 9.18.1 | ? | ? | ? | — | — |
| Cluster Peering Encryption (TLS) | 9.6 | 9.6 | ✅ | ✅ | ✅ | ✅ | N/A |
| NAE/NVE | 9.1 | 9.1 | ✅ (default) | ✅ | ✅ | ✅ | ✅ |

**凡例:**
- ✅ = サポート済み（公式ドキュメントで確認）
- ❌ = 非サポート（公式に非対応またはプラットフォーム制約）
- ? = 未確認（ドキュメント不在または要検証）
- — = 該当なし（組み合わせが成立しない）
- N/A = 該当プラットフォームでは利用不可（機能がプラットフォーム固有）

---

### 各プラットフォームのバージョン状況

#### FSx for ONTAP

| 項目 | 内容 |
|------|------|
| **現行バージョン確認方法** | ONTAP REST API 経由のみ（`GET /api/cluster?fields=version`） |
| **FSx Console / describe-file-systems API** | バージョン情報は公開されない |
| **確認コマンド** | `curl -s -u fsxadmin:<password> https://<mgmt-ip>/api/cluster?fields=version` |
| **Phase 3 での確認** | Confirm via ONTAP REST API during Phase 3 validation |

> **注意**: FSx for ONTAP の ONTAP バージョンは AWS マネジメントコンソールおよび `describe-file-systems` API では確認できない。ONTAP REST API（management endpoint）に fsxadmin 資格情報で認証して取得する必要がある。パスワードは AWS Secrets Manager に保管されていることが一般的であり、直接の値インライン記載は避けるべきである。

#### Google Cloud NetApp Volumes (GCNV)

| 項目 | 内容 |
|------|------|
| **バージョン管理** | Google マネージド。ユーザーによる選択不可 |
| **External Replication 互換性** | 互換バージョンが自動的に適用される（現行バージョンを前提） |
| **FlexCache 対応** | Cache Volume としてのみ動作（Origin 不可） |
| **プロトコル制約** | FlexCache 経由のアクセスは NFSv3 のみ（NFSv4 非サポート） |
| **SnapMirror 互換性** | External Replication はソース側が SnapMirror 互換性マトリクスに適合する必要あり |

#### Azure NetApp Files (ANF)

| 項目 | 内容 |
|------|------|
| **バージョン管理** | Azure マネージド。ユーザーによる選択不可 |
| **SnapMirror External** | 非サポート（Cross-Volume Replication (CVR) = ANF-to-ANF のみ） |
| **FlexCache** | 非サポート（Cluster Peering 機能が公開されていない） |
| **本プロジェクトへの影響** | FSx for ONTAP → ANF の直接データ配信は不可。CVO on Azure 経由が代替手段 |

#### Cloud Volumes ONTAP (CVO)

| 項目 | 内容 |
|------|------|
| **バージョン管理** | ユーザー選択可能。最新バージョンが常に利用可能 |
| **SnapMirror 互換性** | Full ONTAP として version-flexible replication をサポート |
| **FlexCache 互換性** | Origin / Cache いずれも対応 |
| **バージョン互換性ルール** | FlexCache: 4バージョン以内。SnapMirror: 互換性マトリクスに準拠 |

---

### 互換性に関する重要な注記

#### FlexCache 4-version rule（write-around）

FlexCache write-around mode では、Origin と Cache のバージョン差は **4マイナーバージョン以内**が推奨される。例:

- Cache = ONTAP 9.15.1 → Origin は最低 ONTAP 9.11.1 が必要
- Cache = ONTAP 9.14.1 → Origin は最低 ONTAP 9.10.1 が必要

この制約は FlexCache の機能バージョン互換性テーブル（NetApp Docs）に基づく。ただし、実際の互換性は機能ごとに異なり、新しい機能（NFSv4.x サポート、global file locking 等）を使用する場合はより厳密なバージョン要件が適用される。

#### FlexCache write-back バージョン要件

Write-back mode は Origin と Cache の**双方が ONTAP 9.15.1 以降**であることを要求する（厳密要件）:

- Origin が 9.14.1、Cache が 9.15.1 → write-back **有効化不可**
- Origin が 9.15.1、Cache が 9.15.1 → write-back **有効化可**
- **推奨バージョン**: 9.17.1P1 以降を Origin/Cache 双方で使用（NetApp 公式推奨）

混合環境では、write-back 対応の Cache と write-around のみの Cache が同一 Origin に対して共存可能。

#### SnapMirror version-flexible replication

SnapMirror は異なる ONTAP バージョン間のレプリケーションをサポートする（version-flexible replication）。ただし、サポートされる組み合わせは [NetApp Interoperability Matrix](https://docs.netapp.com/us-en/ontap/data-protection/compatible-ontap-versions-snapmirror-concept.html) で定義されており、任意のバージョン組み合わせが許可されるわけではない。

一般的なガイドライン:
- デスティネーションはソースと同じまたはそれ以降のバージョンが推奨
- 古いバージョンへのレプリケーション（新→旧）は制限がある場合がある
- FSx for ONTAP の現行バージョンは常に最新リリースに近いため、On-premises ONTAP が古い場合に互換性マトリクスの確認が特に重要

---

### References（Version Matrix セクション）

| # | タイトル | URL | 最終確認日 |
|---|---------|-----|:----------:|
| 1 | NetApp Docs: Supported and unsupported features for FlexCache volumes | https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html | 2026-07-14 |
| 2 | NetApp Docs: FlexCache write-back interoperability | https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-interoperability.html | 2026-07-14 |
| 3 | NetApp Docs: FlexCache write-back guidelines | https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-guidelines.html | 2026-07-14 |
| 4 | NetApp KB: FlexCache version compatibility | https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/Is_there_a_compatibility_suggestion_for_the_ONTAP_version_difference_between_cache_and_origin_regarding_FlexCache | 2026-07-14 |
| 5 | NetApp Docs: Compatible ONTAP versions for SnapMirror | https://docs.netapp.com/us-en/ontap/data-protection/compatible-ontap-versions-snapmirror-concept.html | 2026-07-14 |
| 6 | NetApp Docs: Data Replication Encryption (Cluster Peering) | https://docs.netapp.com/us-en/ontap-technical-reports/ontap-security-hardening/data-replication-encryption.html | 2026-07-14 |
| 7 | AWS Docs: Replicating data using SnapMirror | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html | 2026-07-14 |
| 8 | AWS Docs: Replicating your data with FlexCache | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html | 2026-07-14 |
| 9 | GCP Docs: External Replication Overview | https://cloud.google.com/netapp/volumes/docs/protect-data/replicate-ontap/overview | 2026-07-14 |
| 10 | Microsoft Docs: ANF Replication | https://learn.microsoft.com/en-us/azure/azure-netapp-files/replication | 2026-07-14 |


---

## Recommended Architecture Patterns

調査結果に基づき、ユースケース別に推奨される構成パターンを以下に示す。各パターンは SnapMirror と FlexCache を**補完的な技術**として位置づけ、ユースケースの要件に応じて適切な方式を選択する設計である。

---

### Pattern A: Single-Cloud データ分散（FSx for ONTAP 間、同一/別リージョン）

**ユースケース**: 同一 AWS アカウント内の複数リージョンに S3 AP 経由で収集したデータを配信し、各リージョンで NFS/SMB による低レイテンシアクセスを提供する

```
┌─────────────────────────────────────────────────────────────┐
│  AWS Region A (Source)                                      │
│  ┌──────────────┐    ┌───────────────────────┐              │
│  │ S3 API Client│───▶│ FSx for ONTAP S3 AP   │              │
│  └──────────────┘    │ (Source Volume)       │              │
│                      └──────────┬────────────┘              │
│                                 │                           │
└─────────────────────────────────┼───────────────────────────┘
                                  │ SnapMirror Async
                                  │ および/または FlexCache
                                  ▼
┌─────────────────────────────────────────────────────────────┐
│  AWS Region B (Destination)                                 │
│  ┌───────────────────────────┐  ┌──────────────────────┐    │
│  │ SnapMirror Dest Volume    │  │ FlexCache Cache Vol  │    │
│  │ (break 後 RW → S3 AP 新規) │  │ (Read cache, NFS/SMB)│    │
│  └───────────────────────────┘  └──────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**構成要素:**

| コンポーネント | 役割 | 備考 |
|--------------|------|------|
| FSx for ONTAP (Region A) | S3 AP でデータ収集、SnapMirror ソース / FlexCache Origin | Intercluster LIF 自動構成 |
| FSx for ONTAP (Region B) | SnapMirror デスティネーション or FlexCache Cache | 用途に応じて選択 |
| SnapMirror Async | DR / Full data copy | RPO 5分〜。break 後に RW 昇格して S3 AP 新規アタッチ可能 |
| FlexCache | Read acceleration | Origin のデータをリアルタイムキャッシュ。write-back mode (9.15.1+) で書き込みも可能 |

**制約:**
- SnapMirror Synchronous は S3 NAS bucket で非サポート（RPO=0 不可）
- SVM-DR 非サポート — デスティネーション SVM は独立構成が必要
- S3 AP は SnapMirror で転送されない — デスティネーション Region で新規 S3 AP 作成が必要

**推奨:**
- DR 目的 → SnapMirror Async + 手動 failover 手順を文書化
- Read acceleration → FlexCache（write-around mode、キャッシュヒット率に応じて効果が変動）
- 両方を組み合わせ: SnapMirror で DR 確保 + FlexCache で日常の read 高速化

---

### Pattern B: ハイブリッドクラウド（FSx for ONTAP → On-premises ONTAP）

**ユースケース**: AWS 上で S3 AP 経由で収集したデータを、オンプレミスのデータセンターに配信し、既存の NFS/SMB クライアントからアクセスする

```
┌───────────────────────────────┐      Direct Connect       ┌─────────────────────────────┐
│  AWS Region                    │      / VPN                │  On-Premises DC              │
│  ┌──────────────────────────┐  │◄──────────────────────────▶  ┌─────────────────────────┐│
│  │ FSx for ONTAP            │  │                           │  │ ONTAP Cluster           ││
│  │ S3 AP (Source Volume)    │──┼── SnapMirror Async ──────▶│  │ NFS/SMB Export          ││
│  │                          │──┼── FlexCache Origin ──────▶│  │ FlexCache Cache Volume  ││
│  └──────────────────────────┘  │                           │  └─────────────────────────┘│
└───────────────────────────────┘                           └─────────────────────────────┘
```

**構成要素:**

| コンポーネント | 役割 | 備考 |
|--------------|------|------|
| FSx for ONTAP (AWS) | S3 AP でデータ収集、SnapMirror ソース / FlexCache Origin | — |
| On-premises ONTAP | SnapMirror デスティネーション or FlexCache Cache | Intercluster LIF 手動構成が必要 |
| Direct Connect / VPN | ネットワーク接続 | TCP 11104, 11105 + ICMP 到達性必須 |
| AD 環境 | SMB 認証 | ソースと同一ドメインまたは Trust 関係が推奨 |

**制約:**
- On-premises ONTAP のバージョンが FSx for ONTAP と互換性マトリクス内であること
- FlexCache write-back mode は WAN RTT ≤ 200ms が推奨上限
- VPN 利用時はレイテンシ変動に注意（Direct Connect 推奨）

**推奨:**
- Read-heavy ワークロード → FlexCache（write-around mode）が最適。キャッシュヒット時はオンプレミスの LAN 速度
- Full data copy / DR → SnapMirror Async。定期的な data refresh ユースケースにも適合
- SMB アクセス時: デスティネーション SVM の AD 参加を事前準備。同一 AD ドメインが最もシンプル

---

### Pattern C: マルチクラウド（FSx for ONTAP → GCP / Azure）

**ユースケース**: AWS で収集したデータを GCP または Azure のワークロードから NFS/SMB でアクセスする

```
┌─────────────────────┐    VPN/Interconnect    ┌─────────────────────────────┐
│  AWS                │◄──────────────────────▶│  Google Cloud               │
│  FSx for ONTAP      │── SnapMirror ─────────▶│  GCNV (External Repl.)      │
│  S3 AP (Source)     │── FlexCache Origin ───▶│  GCNV (Cache Volume)        │
│                     │── SnapMirror ─────────▶│  CVO on GCP (Full ONTAP)    │
└─────────────────────┘                        └─────────────────────────────┘

┌─────────────────────┐    VPN                  ┌─────────────────────────────┐
│  AWS                │◄──────────────────────▶ │  Microsoft Azure            │
│  FSx for ONTAP      │── SnapMirror ─────────▶ │  CVO on Azure (Full ONTAP)  │
│  S3 AP (Source)     │── FlexCache Origin ───▶ │  CVO on Azure (Cache Vol)   │
│                     │           ❌            │  ANF（非サポート）          　 │
└─────────────────────┘                         └─────────────────────────────┘
```

**GCP 宛ての選択肢:**

| 宛先 | 方式 | 制約 |
|------|------|------|
| GCNV（External Replication） | SnapMirror | NFS/SMB アクセス可。S3 AP はなし。GCP マネージド |
| GCNV（FlexCache Cache） | FlexCache | Cache のみ。NFSv3 限定。write-around 推奨 |
| CVO on GCP | SnapMirror / FlexCache | Full ONTAP。全機能利用可。運用コストはユーザー負担 |

**Azure 宛ての選択肢:**

| 宛先 | 方式 | 制約 |
|------|------|------|
| CVO on Azure | SnapMirror / FlexCache | Full ONTAP。全機能利用可 |
| ANF | — | **非サポート**。Cluster Peering 不可 |
| ANF（間接経由） | CVO on Azure → ANF (CVR) | 多段構成で複雑。ユースケースが限定的 |

**制約:**
- クロスクラウド VPN/Interconnect のレイテンシ（一般的に 20〜100ms）
- FlexCache write-back は RTT ≤ 200ms で推奨（クロスクラウドでは write-around 推奨）
- GCNV FlexCache は NFSv4 非サポート
- ANF へのダイレクト SnapMirror / FlexCache は不可

**推奨:**
- GCP への低レイテンシ read アクセス → GCNV FlexCache（Cache）が最もマネージドで運用負荷が低い
- GCP への Full DR → GCNV External Replication（SnapMirror）
- Azure へのデータ配信 → CVO on Azure（SnapMirror）が唯一の実用的選択肢
- マルチクラウドで書き込みが発生する場合 → SnapMirror break + デスティネーション RW 昇格パターンを採用

---

## Decision Tree: SnapMirror vs FlexCache

SnapMirror と FlexCache は**競合する技術ではなく、異なるユースケースに対応する補完的な技術**である。以下のフローチャートにより、ユースケースに応じた適切な選択を支援する。

### 判断フロー

```
[START] データ配信の目的は？
    │
    ├── DR / Full data copy が必要
    │   └── SnapMirror Async を選択
    │       ├── デスティネーションで RW アクセスが必要？
    │       │   ├── Yes → snapmirror break 後に NFS/SMB マウント（+ S3 AP 新規アタッチ）
    │       │   └── No → Read-only DP ボリュームとして維持
    │       └── RPO 要件は？
    │           ├── 5分〜15分 → 高頻度スケジュール（帯域に注意）
    │           └── 1時間+ → 標準スケジュール
    │
    ├── Read 高速化 / キャッシュが必要
    │   └── FlexCache を選択
    │       ├── Write が発生するか？
    │       │   ├── No / 少量 → Write-around mode（デフォルト、安全）
    │       │   └── Yes / 大量 → Write-back mode（9.15.1+、RTT ≤ 200ms 必要）
    │       └── Origin は S3 AP アタッチ済みボリュームか？
    │           ├── Yes → Origin 側 ONTAP 9.12.1+ が必要（S3 NAS bucket 対応）
    │           └── No → 標準 FlexCache 要件のみ
    │
    └── DR + Read 高速化の両方が必要
        └── SnapMirror + FlexCache のハイブリッド構成
            ├── SnapMirror: DR 用（定期レプリケーション、failover 時に RW 昇格）
            └── FlexCache: 日常の read acceleration（Origin → 各拠点の Cache Volume）
```

### SnapMirror vs FlexCache 比較表

| 観点 | SnapMirror Async | FlexCache |
|------|-----------------|-----------|
| **データの所在** | デスティネーションに完全コピー | Origin にデータ、Cache はスパース |
| **RW アクセス** | break 後にデスティネーションで RW | Write-around: Origin に write 転送 / Write-back: Cache でローカル write |
| **RPO** | スケジュール間隔依存（5分〜） | リアルタイム（キャッシュヒット時） |
| **ストレージ消費** | 宛先にフルコピー分の容量が必要 | Cache サイズは任意（ホットデータのみ保持） |
| **DR 対応** | ✅（failover + resync で DR 実現） | ❌（Cache は DR 用途に適さない） |
| **ネットワーク断への耐性** | 転送遅延のみ。宛先データは完全 | Write-around: キャッシュ済み read 継続可。Write-back: ファイルレベル I/O ブロック |
| **セットアップ複雑度** | 低（Cluster Peering + 関係作成） | 中（Cluster Peering + Cache Volume 作成 + write mode 設定） |
| **S3 AP 再利用** | デスティネーションで新規 S3 AP アタッチ必要 | Cache Volume に S3 AP アタッチは未検証 |

### 選択ガイドライン

| ユースケース | 推奨方式 | 根拠 |
|-------------|---------|------|
| 災害復旧（DR） | SnapMirror | デスティネーションに完全コピーを保持し、failover で即時利用可能 |
| リモート拠点の read 高速化 | FlexCache | キャッシュヒット時にローカル速度を提供。ストレージ消費を最小化 |
| データ移行（一方向、一度きり） | SnapMirror | 完全コピー後に関係を解除 |
| リモート拠点での書き込み（同期） | FlexCache (write-around) | 書き込みは Origin に同期的に転送される。デフォルト動作 |
| リモート拠点での書き込み（非同期） | FlexCache (write-back) | Cache にローカル書き込み後、非同期で Origin に flush。RTT ≤ 200ms 必要 |
| コンプライアンス要件のデータ保持 | SnapMirror | 完全コピーにより監査要件を満たす |
| DR + 日常 read 高速化 | SnapMirror + FlexCache 併用 | SnapMirror で DR 確保、FlexCache で日常パフォーマンス向上 |
| マルチクラウド配信（GCP/Azure） | SnapMirror | クロスクラウドでは FlexCache write-back が不安定な可能性。SnapMirror による完全コピーが確実 |

---

## ハイブリッド / オンプレミスパターン: データグラビティとデータローカリティ

本プロジェクトの cross-region 検証は AWS リージョン間（FSx for ONTAP 同士）で実施した。しかし SnapMirror と FlexCache は ONTAP 共通機能であり、オンプレミス ONTAP（AFF/FAS/ONTAP Select）やエッジ環境にも同じアーキテクチャが適用できる。

### データグラビティの問題

データセットが大きくなるほど、別の場所への移動コスト（時間・帯域・エグレス課金）が比例して増大する。この「データグラビティ」により、データを移動するよりも計算をデータの近くに持っていく方が効率的な場面が多い。

2 つの方向でこの問題に対応できる。

| 方向 | パターン | 例 |
|------|---------|-----|
| **データをオンプレ計算に近づける** | S3 AP でクラウドに収集 → SnapMirror でオンプレ ONTAP へ複製 → NFS 経由でローカル GPU/HPC/ライセンス済みツールで処理 | EDA 検証、CAE シミュレーション、MATLAB 解析、オンプレ GPU での AI モデル学習 |
| **クラウド計算をオンプレデータに近づける** | オンプレ ONTAP (Origin) → FlexCache で FSx for ONTAP (Cache) → EMR/SageMaker/Spark でキャッシュデータを処理 | クラウドバーストレンダリング、大規模バッチ分析、クラウド GPU でのモデル学習 |

```
パターン A: クラウドで収集、オンプレで処理
  AWS (S3 AP 収集) ──SnapMirror──▶ オンプレ ONTAP ──NFS──▶ 既存分析基盤
                                                            GPU クラスター
                                                            ライセンス済みツール

パターン B: オンプレのデータ、クラウドでバースト処理
  オンプレ ONTAP (Origin) ──FlexCache──▶ FSx for ONTAP (Cache) ──▶ EMR / SageMaker
```

### このパターンが有効な場面

| 場面 | 理由 |
|------|------|
| 規制やポリシーでデータを外部に出せない | SnapMirror は閉域ネットワーク内で複製可能（VPN/Direct Connect、転送中暗号化） |
| オンプレに高価なライセンス済みツール（EDA、CAE、MATLAB、SAS 等）がある | ツールをクラウドに移行するよりデータをツールに持っていく方が現実的 |
| 工場フロアでリアルタイム推論に低レイテンシが必要 | FlexCache をエッジ/工場に配置。Origin の更新が自動反映 |
| クラウドのエグレス費用を最小化したい | SnapMirror: 初回後は増分のみ。FlexCache: アクセスしたデータだけキャッシュ |
| 複数拠点のデータを一箇所に集約して分析したい | 各拠点 → AWS に SnapMirror で集約 → Athena/EMR で横断クエリ |
| 閉域ネットワーク内の分析（air-gapped） | SnapMirror で片方向転送。転送後はアウトバウンド接続不要 |

### データ主権とコンプライアンスの考慮

データレジデンシー要件がある組織向け:

- SnapMirror 転送は特定のネットワーク経路に限定可能（Direct Connect、サイト間 VPN）
- 保存時暗号化: NAE/NVE（ONTAP）、AWS マネージド暗号化（FSx）
- 転送中暗号化: Cluster Peering Encryption（TLS 1.2、ONTAP 9.6 以降デフォルト有効）
- Direct Connect / VPN があればパブリックインターネットを経由する必要なし
- 監査証跡: ONTAP FPolicy + S3 AP アクセスログによる二層アクセスログ

### オンプレミスパターンのデモガイド

| ガイド | パターン | ネットワーク |
|--------|---------|:----------:|
| [Guide 03: FlexCache オンプレミス](demo-guide-03-flexcache-on-premises.md) | FSx for ONTAP → オンプレ ONTAP（FlexCache） | Direct Connect / VPN |
| [Guide 08: SnapMirror オンプレミス](demo-guide-08-snapmirror-on-premises.md) | FSx for ONTAP → オンプレ ONTAP（SnapMirror DR） | Direct Connect / VPN |

> これらのガイドは現在手順レベル（コマンド文書化済み、物理ハードウェアでの E2E 検証は未実施）。オンプレミスラボ環境が利用可能になり次第検証を実施予定。

---

## 業種別ユースケース

以下は検証で確認した FlexCache/SnapMirror + S3 Access Points のアーキテクチャパターンを業種別に整理した想定ユースケースである。個々の業種での本番適用にはワークロード固有の検証が必要。

### データ収集 + 分析バースト（FlexCache 向き）

| 業種 | ワークロード | FlexCache の役割 |
|------|------------|----------------|
| 自動車 (AV/ADAS) | HiL テスト — クラウド収集走行データのオンプレ再生 | テストリグへのデータ配信。Origin 更新が自動反映 |
| メディア / VFX | レンダリングバースト — NAS 上のシーンファイル + テクスチャをクラウドレンダーファームに配信 | レンダーノードがローカル速度でアセットを読み取り |
| 半導体 (EDA) | DRC/LVS 回路検証 — 設計データをクラウドに配信してバッチ検証 | 計算リソースの近くにキャッシュ配置。転送待ちなしにジョブ開始 |
| ヘルスケア | 医用画像 (DICOM) — 院内 NAS の画像を研究用 AI 基盤に配信 | 複数研究拠点からの並行読み取りを分散 |
| IoT / 製造 | センサーデータ収集 → 分析環境への配信 | NFS バッチ処理のスループットを活用（アクセスパターンにより S3 API より有利な場面がある） |
| エネルギー | 地震探査 / シミュレーションデータ — HPC クラスターへの配信 | PB 規模のデータセットを一度だけ転送し、FlexCache で再利用 |
| 建設 / 建築 | BIM モデル — 複数拠点の設計チームが同一 3D モデルを参照 | 各拠点にキャッシュ配置。write-around で変更を Origin に即時反映 |

### DR + コンプライアンス保存（SnapMirror 向き）

| 業種 | ワークロード | SnapMirror の役割 |
|------|------------|-----------------|
| 金融 (FSI) | 規制対応データの DR — 取引記録・監査ログの別リージョン複製 | RPO 5 分以内の非同期レプリケーション。監査証跡の geo-redundancy 確保 |
| 公共 (Public Sector) | 行政データの BC/DR — 災害時のサービス継続 | 別リージョンに完全コピー。フェイルオーバー後 S3 AP 再アタッチで ~3 分で復旧 |
| ヘルスケア | HIPAA 対応 — 患者データの別リージョンバックアップ | 転送中暗号化（TLS 1.2）+ 保存時暗号化が標準。増分転送でネットワーク負荷最小化 |
| 通信 (Telco) | ネットワークログ / CDR の長期保存 + DR | 大容量ログを日次でレプリケーション。宛先で NFS マウントして分析ツール投入 |
| 小売 / EC | POS / 行動データの分析環境配信 | 日次バッチでデータウェアハウス環境に同期。S3 API のコール課金を考慮 |

### 両方併用（FlexCache + SnapMirror）

| 業種 | ワークロード | 併用パターン |
|------|------------|------------|
| 製造 | 品質画像 + IoT → AI 推論 + DR | FlexCache: 推論環境への読み取り加速 / SnapMirror: 生データの DR 保護 |
| メディア | 素材 NAS → 複数ポストプロダクション拠点 + 本社 DR | FlexCache: 各拠点での編集アクセス / SnapMirror: マスターの DR |
| 物流 | 配送画像認識データ → 分析 + アーカイブ | FlexCache: リアルタイム分析拠点 / SnapMirror: コンプライアンス保存 |
| 広告 / AdTech | ログ収集 → リアルタイム分析 + DR | FlexCache: 分析クラスターへの低レイテンシ配信 / SnapMirror: 監査用 DR |
| 農業 / 食品 | ドローン撮影画像 → AI 解析 + 長期保存 | FlexCache: GPU クラスターへの画像配信 / SnapMirror: 原本保存 |
| 不動産 | 3D スキャン / 点群データ → VR 内覧 + アーカイブ | FlexCache: 各営業拠点のビューワーに配信 / SnapMirror: 資産としての保全 |

### 設計の要点

- **S3 API コールの課金**: 多数の小ファイルを参照する分析ワークロードでは、FlexCache 経由の NFS マウントの方がコスト効率が良い場面がある（S3 API は GET/LIST ごとに課金。アクセスパターンとファイルサイズによる）
- **レイテンシ**: S3 API はオブジェクト単位のメタデータ操作で NFS と比較してレイテンシが大きい傾向がある。ファイル単位のランダムアクセスが頻繁な場合は NFS が有利。逆に大容量オブジェクトの並列ダウンロードでは S3 の方が適する場面もある
- **SnapMirror の増分転送**: 初回以降は変更ブロックのみ転送。TB 規模のデータセットでも日次同期のネットワーク負荷は小さい

参考:
- [AWS Blog — Accelerating HiL Testing for AV/ADAS with a Hybrid Cloud Approach](https://aws.amazon.com/jp/blogs/industries/accelerating-hil-testing-for-av-adas-with-a-hybrid-cloud-approach-aws-and-netapp/)
- [NetApp Blog — Transform Your EDA Workflows with FlexCache](https://www.netapp.com/ja/blog/transform-eda-workflows-flexcache/)
- [NetApp Blog — Global data consistency made simple with FlexCache](https://www.netapp.com/blog/flexcache-global-data-gigaom-radar/)

---

## Open Questions

以下は本調査で解決に至らなかった項目であり、追加検証またはベンダー確認で解決予定:

| # | 質問 | 関連 Finding | 優先度 | 解決方法 |
|---|------|:------------:|:------:|---------|
| 1 | ~~FlexCache Cache Volume に S3 AP を独立アタッチ可能か？~~ 2026-09-13 解決: 不可（9.18.1P5 実測） | FC-002 | — | 実機検証済み |
| 2 | GCNV External Replication のソース側最低 ONTAP バージョン要件は？ | XC-006 | P2 | GCP ドキュメント更新待ちまたは検証 |
| 3 | FlexGroup + S3 AP + FlexCache Origin の3要素組み合わせは安定動作するか？ | FC-007 | P2 | 実機検証 |
| 4 | ANF への代替パス（CVO on Azure 経由 CVR）は実用的か？ | XC-007 | P3 | アーキテクチャ設計 + コスト評価 |

### Phase 3 で解決済みの項目

| # | 質問 | 関連 Finding | 解決結果 |
|---|------|:------------:|---------|
| ~~1~~ | S3 AP アタッチ済みボリュームを FlexCache Origin に設定可能か？ | FC-001 | ✅ **可能**（ONTAP 9.17.1 で確認） |
| ~~2~~ | Write-back mode で S3 AP 書き込みと XLD の相互作用はどうなるか？ | FC-004 | ✅ **動作するが注意事項あり** — Origin への S3 AP 書き込みは XLD revoke を引き起こす |
| ~~3~~ | SnapMirror break 後のデスティネーションボリュームに S3 AP を問題なくアタッチできるか？ | SM-005 | ✅ **可能** — break → junction path 設定 → ~60秒待機 → S3 AP 作成 |
| ~~4~~ | S3 AP メタデータ（`s3_unix` name-mapping）が SVM レベルで正しく再生成されるか？ | SM-002 | ✅ **自動再生成される** — デスティネーションで新規 S3 AP アタッチ時に FSx が自動管理 |

---

## 全体 References

本ドキュメントで引用した全ての URL を一覧する。各セクションの References テーブルも参照のこと。

### AWS Documentation

| # | タイトル | URL |
|---|---------|-----|
| 1 | Replicating your data using NetApp SnapMirror | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html |
| 2 | Replicating your data with FlexCache | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html |
| 3 | Creating a FlexCache | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/create-flexcache.html |
| 4 | Accessing your data via Amazon S3 access points | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html |
| 5 | Creating access points | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/create-access-points.html |
| 6 | Managing access point access | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html |
| 7 | Migrating to FSx for ONTAP using SnapMirror | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/migrating-fsx-ontap-snapmirror.html |
| 8 | Volume security style | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/volume-security-style.html |
| 9 | Volume styles | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/volume-styles.html |
| 10 | CreateAndAttachS3AccessPoint API | https://docs.aws.amazon.com/fsx/latest/APIReference/API_CreateAndAttachS3AccessPoint.html |
| 11 | Cross-region DR with FSx for ONTAP (Blog) | https://aws.amazon.com/blogs/storage/cross-region-disaster-recovery-with-amazon-fsx-for-netapp-ontap |
| 12 | FSx for ONTAP write-back mode (What's New) | https://aws.amazon.com/about-aws/whats-new/2025/05/amazon-fsx-netapp-ontap-write-back-mode-ontap-flexcache-volumes |
| 13 | Amazon S3 conditional writes (What's New) | https://aws.amazon.com/about-aws/whats-new/2024/08/amazon-s3-conditional-writes/ |

### NetApp ONTAP Documentation

| # | タイトル | URL |
|---|---------|-----|
| 1 | Learn about ONTAP S3 multiprotocol support | https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html |
| 2 | Supported and unsupported features for FlexCache volumes | https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html |
| 3 | FlexCache write-back architecture | https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-architecture.html |
| 4 | FlexCache write-back interoperability | https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-interoperability.html |
| 5 | FlexCache write-back guidelines | https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-guidelines.html |
| 6 | SnapMirror SVM replication concept | https://docs.netapp.com/us-en/ontap/data-protection/snapmirror-svm-replication-concept.html |
| 7 | SnapMirror disaster recovery concept | https://docs.netapp.com/us-en/ontap/data-protection/snapmirror-disaster-recovery-concept.html |
| 8 | Compatible ONTAP versions for SnapMirror | https://docs.netapp.com/us-en/ontap/data-protection/compatible-ontap-versions-snapmirror-concept.html |
| 9 | Data Replication Encryption | https://docs.netapp.com/us-en/ontap-technical-reports/ontap-security-hardening/data-replication-encryption.html |
| 10 | ONTAP S3 supported actions | https://docs.netapp.com/us-en/ontap/s3-config/ontap-s3-supported-actions-reference.html |
| 11 | ONTAP S3 interoperability | https://docs.netapp.com/us-en/ontap/s3-config/ontap-s3-interoperability-concept.html |
| 12 | Consistency Groups | https://docs.netapp.com/us-en/ontap/consistency-groups/ |
| 13 | Security styles and their effects | https://docs.netapp.com/us-en/ontap/smb-admin/security-styles-their-effects-concept.html |
| 14 | ONTAP NFS support for Kerberos | https://docs.netapp.com/us-en/ontap/nfs-admin/ontap-support-kerberos-concept.html |
| 15 | Enable or disable NFSv4 write file delegations | https://docs.netapp.com/us-en/ontap/nfs-admin/enable-disable-nfsv4-write-file-delegations-task.html |
| 16 | Create ONTAP FlexCache volumes | https://docs.netapp.com/us-en/ontap/flexcache/create-volume-task.html |

### NetApp Knowledge Base

| # | タイトル | URL |
|---|---------|-----|
| 1 | Is SVM DR of S3 buckets supported? | https://kb.netapp.com/on-prem/ontap/DP/SnapMirror-KBs/Is_SVM_Disaster_Recovery_(SVM_DR)_of_S3_buckets_supported%3F |
| 2 | What does volume level SnapMirror replicate? | https://kb.netapp.com/on-prem/ontap/DP/SnapMirror/SnapMirror-KBs/What_does_volume_level_snapmirror_replicate |
| 3 | FlexCache version compatibility | https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/Is_there_a_compatibility_suggestion_for_the_ONTAP_version_difference_between_cache_and_origin_regarding_FlexCache |
| 4 | FlexCache slow read performance and cache eviction | https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/FlexCache_slow_read_performance_and_cache_eviction |
| 5 | High latency delete operations due to high WAN RTT | https://kb.netapp.com/on-prem/ontap/Perf/Perf-KBs/High_latency_when_performing_delete_operations_due_to_high_WAN_RTT |
| 6 | FlexCache Volumes Disconnected After Firewall Upgrade | https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/FlexCache_Volumes_Disconnected_After_Firewall_Upgrade |
| 7 | Does NVE encrypt data during SnapMirror transfer? | https://kb.netapp.com/on-prem/ontap/dm/Encryption-KBs/Does_NVE_encrypt_data_during_transfer_when_using_SnapMiror |
| 8 | Cluster Peering Encryption performance | https://kb.netapp.com/Advice_and_Troubleshooting/Data_Protection_and_Security/SnapMirror/Does_implementing_Cluster_Peer_Encryption_influence_performance |
| 9 | ONTAP S3 WAFL strong consistency | https://kb.netapp.com/on-prem/ontap/da/S3/S3-KBs/Why_can't_the_S3_bucket_consistency_level_be_changed_in_ONTAP_S3 |
| 10 | CONTAP-221219 (501 Not Implemented) | https://kb.netapp.com/on-prem/ontap/da/S3/S3-Issues/CONTAP-221219 |
| 11 | Do local authentication objects need to be recreated after SnapMirror break? | https://kb.netapp.com/on-prem/ontap/DP/SnapMirror/SnapMirror-KBs/Do_local_authentication_objects_and_permissions_need_to_be_recreated_after_a_SnapMirror_break |

### Google Cloud Documentation

| # | タイトル | URL |
|---|---------|-----|
| 1 | External Replication Overview (GCNV) | https://cloud.google.com/netapp/volumes/docs/protect-data/replicate-ontap/overview |
| 2 | FlexCache overview (GCNV) | https://docs.cloud.google.com/netapp/volumes/docs/configure-and-use/volumes/cache-ontap-volumes/overview |
| 3 | Create FlexCache volume (GCNV) | https://cloud.google.com/netapp/volumes/docs/configure-and-use/volumes/cache-ontap-volumes/create-flexcache-volume |
| 4 | Announcing enhancements to GCNV (Blog) | https://cloud.google.com/blog/products/storage-data-transfer/announcing-enhancements-to-google-cloud-netapp-volumes/ |

### Microsoft Azure Documentation

| # | タイトル | URL |
|---|---------|-----|
| 1 | Understand ANF Replication | https://learn.microsoft.com/en-us/azure/azure-netapp-files/replication |
| 2 | ANF Replication Requirements | https://learn.microsoft.com/en-us/azure/azure-netapp-files/cross-region-replication-requirements-considerations |

### NetApp Community / Blog

| # | タイトル | URL |
|---|---------|-----|
| 1 | SnapMirror between ONTAP and GCNV | https://community.netapp.com/t5/Tech-ONTAP-Blogs/SnapMirror-between-ONTAP-and-Google-Cloud-NetApp-Volumes/ba-p/461292 |
| 2 | Introducing FlexCache for GCNV | https://community.netapp.com/t5/Tech-ONTAP-Blogs/Introducing-FlexCache-for-Google-Cloud-NetApp-Volumes/ba-p/464229 |
| 3 | Azure Storage Replication SnapMirror (Blog) | https://www.netapp.com/blog/azure-storage-replication-snapmirror/ |
| 4 | Cross-Region Replication with CVO | https://www.netapp.com/learn/cross-region-replication-with-cloud-volumes-ontap |
| 5 | How FlexCache Makes the World Smaller | https://www.netapp.com/blog/how-netapp-flexcache-makes-the-world-smaller/ |
| 6 | SnapMirror data replication AWS | https://www.netapp.com/fr/blog/snapmirror-data-replication-aws/ |

---

## Phase 3 Validation Summary

Phase 3 では、Phase 1/2 で `undocumented — validation required` に分類された項目について FSx for ONTAP 実環境（ONTAP 9.17.1）で検証を実施した。以下は検証結果の一覧である。

### 検証結果一覧

| Finding ID | 検証テスト | Phase 2 分類 | Phase 3 結果 | 最終分類 |
|:----------:|:---------:|:------------:|:------------:|:--------:|
| SM-001 | TC-01/TC-02 | supported（条件付き） | ✅ S3 AP ボリュームが SnapMirror Async ソースとして正常動作 | `supported` (confirmed) |
| SM-002 | TC-01/TC-02 | undocumented | ✅ S3 AP メタデータは転送されない（期待動作）。デスティネーションで新規 S3 AP アタッチにより解決 | `supported (validated)` |
| SM-005 | TC-01/TC-02 | undocumented | ✅ break → junction path 設定 → ~60s 待機 → S3 AP 作成の手順で正常動作 | `supported (validated)` |
| FC-001 | TC-03/TC-05 | undocumented | ✅ S3 AP アタッチ済みボリュームが FlexCache Origin として動作（ONTAP 9.17.1 確認） | `supported (validated)` |
| FC-004 | TC-03/TC-05 | undocumented | ⚠️ 動作するが S3 AP Origin write が XLD revoke を引き起こし、同一ファイル concurrent write は危険 | `works_with_caveats` |

### 新規発見事項

| ID | カテゴリ | 発見事項 | 分類 |
|:--:|:-------:|---------|:----:|
| SM-VAL-004/007 | SnapMirror | FSx API の `VolumeType` は ONTAP break 後 ~60秒間 `DP` のまま表示される | `works_with_caveats` |
| FC-VAL-001 | FlexCache | FSx for ONTAP での FlexCache 最小サイズは 50GB（FlexGroup + FabricPool aggregate） | operational note |
| FC-VAL-002 | FlexCache | FlexCache 作成に `use_tiered_aggregate: true` が必須（FSx for ONTAP 固有） | operational note |
| FC-VAL-003 | FlexCache | 同一クラスター内 FlexCache でも Intra-cluster SVM Peering が必要 | operational note |
| FC-VAL-004 | FlexCache | S3 AP write → Origin → Cache 伝搬は TTL 経過後（~30秒）で反映 | operational note |

### 検証環境

| 項目 | 値 |
|------|-----|
| プラットフォーム | Amazon FSx for NetApp ONTAP |
| ONTAP バージョン | 9.17.1 |
| リージョン | us-east-1 |
| 検証テストケース | TC-01, TC-02（SnapMirror）、TC-03, TC-05（FlexCache） |
| エビデンス保存先 | `.private/evidence/s3ap-multicloud/` |

### Phase 3 による分類変更サマリー

| 変更前 | 変更後 | 件数 |
|--------|--------|:----:|
| undocumented → supported (validated) | SM-002, SM-005, FC-001 | 3 |
| undocumented → works_with_caveats | FC-004 | 1 |
| 新規追加（works_with_caveats） | SM-VAL-004/007 | 1 |
| **合計解決済み** | | **4 / 6** |
| **残 undocumented** | なし（FC-002 は 2026-09-13 に実測で決着） | **0** |

---

### Cross-Region 検証結果（2026-07-22 追加）

Cross-region SnapMirror + S3 AP re-attach を ap-northeast-1 → us-west-2 間で E2E 検証。以下の新規 Finding を追加。

| Finding ID | 分類 | 概要 |
|:----------:|:----:|------|
| SM-VAL-008 | `works_with_caveats` | FSx API VolumeType:DP 表示ラグ（cross-region では >10 分）。S3 AP 作成は junction path 設定後即可能 |
| SM-VAL-009 | `works_with_caveats` | ONTAP REST API で作成したボリュームは FSx API への反映に ~30 分かかる。即時 S3 AP アタッチが必要なら FSx API で作成 |
| SM-VAL-010 | `supported (validated)` | Cross-region S3 AP re-attach RTO: ~3 分（break + junction 伝搬 + AP 作成 + 初回 API） |
| SM-VAL-011 | `works_with_caveats` | Teardown 順序が重要。VPC Peering を SVM peer 削除前に削除すると永続的な zombie レコード発生 |
| SM-VAL-012 | `works_with_caveats` | DP ボリュームへの `update-volume` junction path 指定は 200 を返して無言で破棄される。`DescribeVolumes` の値で判定すること（2026-09-13 追加） |
| SM-VAL-013 | `supported (validated)` | 稼働中の SnapMirror 宛先を ONTAP で mount すれば S3 AP で読める（break・クローン不要）。転送反映は 15 秒、初回セットアップは FSx 反映待ちで数十分（2026-09-13 追加） |

#### SM-VAL-008: FSx API VolumeType:DP 表示ラグ（Cross-Region）

**発見**: SnapMirror break 後、FSx API は `OntapVolumeType: DP` を cross-region シナリオで **10 分以上**表示し続ける（同一リージョンでは ~60秒）。ただし S3 AP アタッチは junction path 設定後すぐに成功する。

**スコープ**: FSx 固有の動作（AWS コントロールプレーン同期遅延）。On-premises ONTAP では発生しない。ONTAP REST API は break 直後に正しく `type: rw` を返す。

**自動化への影響**:
- `describe-volumes → OntapVolumeType` を S3 AP アタッチのゲートにしないこと
- 正しい手順: (1) SnapMirror break, (2) `update-volume` で junction path 設定, (3) FSx API に junction path が反映されるまで待機 (~2分), (4) S3 AP アタッチ

#### SM-VAL-009: ONTAP REST API で作成したボリュームの FSx API 反映遅延（~30 分）

**発見**: ONTAP REST API (`POST /api/storage/volumes {type: dp}`) のみで作成されたボリュームは FSx API (`describe-volumes`) に**即座には表示されない**。FSx コントロールプレーンへの同期に約 **30 分**かかる。S3 AP アタッチには FSx volume ID (`fsvol-*`) が必要。

**推奨**: DP ボリュームは `aws fsx create-volume --ontap-configuration '{"OntapVolumeType":"DP"}'` で作成すれば即座に FSx API に表示される。FlexCache のように FSx API に作成 API がない場合は ONTAP REST API で作成し、~30 分の FSx コントロールプレーン同期を待ってから S3 AP をアタッチする。

**対処法**: ONTAP REST API で作成したボリュームを削除・再作成する必要はない。待てば FSx API に反映される。

#### SM-VAL-010: Cross-Region S3 AP Re-Attach RTO

| フェーズ | 所要時間 | 備考 |
|---------|:--------:|------|
| SnapMirror break | ~即座 | ONTAP REST API PATCH |
| Junction path 設定 + FSx API 伝搬 | ~2 分 | `update-volume` + ポーリング |
| S3 AP 作成 (CREATING → AVAILABLE) | ~30秒 | `create-and-attach-s3-access-point` |
| 初回 S3 API コール成功 | ~30秒 | ListObjectsV2 / GetObject |
| **合計** | **~3 分** | Cross-region (ap-northeast-1 → us-west-2) |

**RPO に関する補足**: SnapMirror Async レプリケーションはスケジュール実行（FSx for ONTAP の最短間隔は5分）。RPO は最後に成功した SnapMirror 転送からの経過時間に等しい。最悪ケースでは、最終転送後にソースに書き込まれた最大5分間のデータが失われる可能性がある。

**コストに関する補足**: リージョン間の SnapMirror 転送には AWS 標準のリージョン間データ転送料金（$0.01–$0.02/GB、リージョンペアにより異なる）が発生する。大容量ボリュームの初回ベースライン転送はコスト見積もりに含めること。以降の増分転送は変更ブロックのみのため通常小さい。

#### SM-VAL-011: Teardown 順序 — 重要な依存関係

**発見**: VPC Peering またはネットワークルートを SVM peer 削除完了前に削除すると、**永続的な zombie SVM peer レコード**が REST API で削除不能になる。FSx SVM は MISCONFIGURED 状態になりファイルシステム削除をブロックする。

**必須 Teardown 順序**:
1. SnapMirror 関係削除（両側）
2. SVM peer 削除（両側）— **両クラスターで `num_records: 0` を確認するまで待機**
3. Cluster peer 削除
4. VPC Peering / ルート削除
5. FSx API で SVM 削除
6. FSx API でファイルシステム削除

**復旧手順**: ONTAP CLI via SSH を使用（SSH アクセスは FSx コンソールで有効化が必要）。本番環境では SSH キー認証または AWS Systems Manager Session Manager を推奨。

1. SOURCE クラスター: `snapmirror release -destination-path <dest> -source-path <src> -force true`
2. SOURCE クラスター: `vserver peer delete -vserver <local-svm> -peer-vserver <remote-svm>`
3. `aws fsx delete-storage-virtual-machine` を再試行

AWS Support による解決が必要な場合の所要日数: 通常 1-3 営業日。

**参考**: [AWS re:Post — FSx for ONTAP SVM 削除](https://repost.aws/knowledge-center/fsx-ontap-delete-svm), [FSx ユーザーガイド — SVM 削除不可](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/cannot-delete-svm.html)

#### SM-VAL-012: DP ボリュームに対する UpdateVolume の junction path 指定の無言の破棄

**測定**: 2026-09-13、ap-northeast-1（[検証記録](../../../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13/evidence-record.yaml)）。分類 `works_with_caveats`。

**発見**: `aws fsx update-volume --ontap-configuration '{"JunctionPath":"..."}'` を **DP** ボリュームに対して実行すると、Volume オブジェクト全体を伴う HTTP 200 が返り、何も起きない。30 秒後も `DescribeVolumes` は `JunctionPath: None` を返し、`AdministrativeActions` エントリも失敗メッセージも存在しない。続けて S3 AP をアタッチすると `the volume is not mounted` で失敗し、何も変わっていないことが確認できる。

対して `CreateVolume` は同じフィールドを明示的に拒否する: `Invalid fields provided for a DP volume. JunctionPath, StorageEfficiency, SnapshotPolicy and SecurityStyle cannot be specified for a DP Volume.` 同一の不正入力に対して 2 つの API が異なる拒否の仕方をしており、状態を変更する側が沈黙する側である。

**SM-VAL-008 との相互作用**（運用上の要点）。SM-VAL-008 は S3 AP アタッチのゲートに `OntapVolumeType` を使うなと述べており、これは正しい。cross-region の break 成功後も FSx API が 10 分以上 `DP` を報告し続けるためである。本 finding と組み合わせると、ボリューム種別だけでは次の 2 状態が区別できない。

| 実際の状態 | FSx API の `OntapVolumeType` | junction path 指定の `update-volume` |
|---|---|---|
| break 済み、FSx API が遅延中 | `DP` | 効く |
| break していない、または resync 済み | `DP` | 受理され、無言で破棄される |

**信頼できる signal は junction path そのものだけである。** 設定した後、`DescribeVolumes` で `JunctionPath` が non-null になるまでポーリングしてからアタッチする。`UpdateVolume` の応答を確認と見なさないこと。またフラグを足して再試行しないこと。無言の破棄は伝搬の遅さと見分けがつかず、すでに受理された呼び出しにフラグを足しても何も変わらない。

**スコープと、これが意味しないこと**: これは ONTAP の制約ではなく FSx コントロールプレーンの制約であり、**DP ボリュームに S3 AP を付けられないことを意味しない**。2026-09-13 に VPC 内から実測（SM-VAL-013）: ONTAP は DP ボリュームを mount し、FSx API はその junction path を約 2298 秒後に報告し、その後アタッチが成功して稼働中の SnapMirror 宛先から読み取りを提供する。SM-VAL-012 の正しい読み方は狭い。**FSx API は DP ボリュームを mount する手段として使えず、かつ失敗が明示されず無言である**、というだけである。また、この実行での DP ボリュームは SnapMirror 関係を持たないが、稼働中の宛先は SM-VAL-013 で検証し同じ挙動だった。

#### SM-VAL-013: 稼働中の SnapMirror 宛先に対する S3 アクセスポイントの成立

**測定**: 2026-09-13、ap-northeast-1、ONTAP 9.18.1P5、SVM 内の非同期ボリューム SnapMirror（[検証記録](../../../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13-in-vpc/evidence-record.yaml)）。分類 `supported (validated)`。

**発見**: SnapMirror 宛先は、関係を稼働させたまま S3 アクセスポイント経由で読める。break もクローンも不要。ONTAP で DP ボリュームを mount し（`vol mount` / `PATCH nas.path`）、FSx API が junction path を報告するのを待ってアタッチする。読み取りは成功し、DP は read-only なので `PutObject` は `AccessDenied` を返し、関係は全過程で `snapmirrored`・healthy を維持した。**後続の SnapMirror 転送は同一アクセスポイント経由で 15 秒以内に可視化され読み取れた。アクセスポイントの変更は不要。**

宛先 Snapshot の FlexClone が代替となり、違いは 1 点。書き込みを受け付け、切り出した Snapshot の時点で固定される。

| フェーズ | 所要時間 |
|---|--:|
| ONTAP 側の操作（mount またはクローン作成） | 数秒、20 秒未満 |
| FSx API がボリューム / junction path を報告 | **665 秒・1011 秒・2298 秒** |
| アクセスポイント CREATING → AVAILABLE | 31〜32 秒 |

**自動化への影響**: 初回セットアップを支配するのは ONTAP 側の操作ではなく FSx コントロールプレーンの反映。`DescribeVolumes` を `JunctionPath` が non-null になるまで（DP 経路）、または `fsvol-*` の識別子が現れるまで（クローン経路）ポーリングし、それ以前にアタッチを試みないこと（`the volume is not mounted` で失敗する）。1 ファイルシステム上の 3 サンプルで、665 秒と 2298 秒は同一操作であるため、ばらつきは経路の性質ではない。数分から数十分を見込んで設計し、特定の数値を引用しない。

**エンジンから見た同等性（S3AP-DP-ATHENA-001）**: Amazon Athena を DP 由来のアクセスポイントに向けた結果は、同一 Parquet ファイルから作った RW 由来のコントロールと同一だった（同一セッション、行も集計値も一致、7493 ミリ秒対 7804 ミリ秒）。read-only ボリュームに対してパーティション検出（`MSCK REPAIR`）と枝刈りの双方が機能し、`INSERT` は S3 403 が `PERMISSION_DENIED` として表面化して失敗し、ボリューム上には何も残らなかった。後続転送で追加されたパーティションはカタログ更新のみでクエリ可能になった。Snowflake は DP 由来のアクセスポイントで**未検証**。読み取りの面は同一だが、それは推論であって測定ではない。

**Teardown と、2 回かかった診断**: FlexClone を FSx API で削除したところ親が `clone.has_flexclone=true` のまま残り、その後どちらの API でも親を削除できなくなった。最初の読み（フラグが陳腐化しクローンは存在せず、自力では解消できない）は誤りだった。`aws fsx delete-volume` はボリュームを破棄しない。ONTAP は `<name>_NNNN` に改名して**ボリューム recovery queue**（type `del`）へ移し、queue にあるクローンが親の Snapshot を保持し続けていた。これは `/api/storage/volumes` と既定権限の `volume show` には現れず、`privilege_level=diagnostic`・`volume clone show`・`volume recovery-queue show` に現れる。`volume recovery-queue purge` で解消し、その後親は正常に削除できた。`fsxadmin` の権限のみで足りる。詳細は [ONTAP-RECOVERY-QUEUE-001](../../../../verification-pack/ontap-features/evidence/2026-09-13/volume-recovery-queue-and-fc002.yaml)。またアクセスポイントの内部オブジェクトストアバケット `amazon-fsx-fsvol-*` は一時的にボリューム削除をブロックするが、`GET /api/protocols/s3/buckets` には**列挙されない**。

**未確立**: 分析エンジンが DP 由来のアクセスポイントを RW 由来と同一に読むか（S3 API のみを実行）、クロスリージョンの挙動、アクセスポイントを残したままの break/resync 通過、小さな 4 オブジェクトを超える規模、WINDOWS identity と NTFS セキュリティスタイル。
