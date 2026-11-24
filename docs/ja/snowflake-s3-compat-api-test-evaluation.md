🌐 [English](../en/snowflake-s3-compat-api-test-evaluation.md) | **日本語**

# Snowflake S3-compatible ストレージ API テストスイート評価: ONTAP S3 と NAS bucket

> **ステータス**: 初版（2026-09-26）。Snowflake 側の登録要件は公式ドキュメント由来（**Public**）。テストスイートの実行結果は本検証環境で観測（**Observed**）。失敗の内部原因は **Hypothesis**。
> **Evidence tier**: 各主張に明記（**Public** = 公開情報で検証可能 / **Observed** = 本環境のテスト実行で観測 / **Hypothesis** = 仮説）。
> **テスト環境**: Snowflake 公開テストスイート [`snowflake-s3compat-api-test-suite`](https://github.com/snowflakedb/snowflake-s3compat-api-test-suite)（aws-java-sdk-s3 1.12.62、Java 11）。対象は ONTAP のネイティブ S3 object-store server エンドポイント（独自 DNS 名 + direct credentials）で、これは §1 の (B) 経路にあたり、FSx for ONTAP S3 Access Points（§1 の (A)）とは別物である（エンドポイント種別は AWS CLI で確認済み — **Observed**）。同一エンドポイント上の2種のバケット、通常 bucket と NFS/SMB マルチプロトコルボリューム上の bucket を対象とした。
> **フレーミング**: vendor-versus ではなく right-tool-for-the-job。各ストレージ形態のトレードオフを対称に記載する。

---

## エグゼクティブサマリー

- **登録機構は2つあり、別物である**。Snowflake が FSx for ONTAP のデータを読む経路には、(A) S3 Access Points を通常の Amazon S3 バケットとして扱う **Storage Integration 経路**と、(B) 任意の S3 互換エンドポイントを登録する **S3-compatible external stage 経路**がある。本ドキュメントが扱うのは (B)。(A) は[Snowflake セットアップガイド](./snowflake-iceberg-setup.md)で扱う。
- **(B) の入口には申請フローがある**。S3-compatible エンドポイントは全アカウントで自動有効化されない。Cloudflare R2 のみ既定で有効で、それ以外は Snowflake Support への申請で有効化する。申請の前提として、公開テストスイートで自エンドポイントを検証することが求められる（**Public**）。
- **ベンダー掲載は接続保証ではない**。Snowflake のベンダー一覧は「ベンダーが自製品の一部をテストしたと申告した」一覧であり、Snowflake が互換性を検証したものではない、と KB 本文が明記している（**Public**）。掲載の有無と、自環境で申請フローを通せるかは別である。
- **ONTAP S3 通常 bucket は実質フルパス**（**Observed**）。9 テスト中の失敗は2件で、いずれもテストスイートの Troubleshooting が明示的に許容している種類（negative test のエラーコード差と、ページング件数の1個ズレ）。
- **NFS/SMB マルチプロトコル bucket は複数の乖離**（**Observed**）。9 テスト中 Failure 3 + Error 1。うち getBucketLocation は ONTAP S3 通常 bucket と同じ許容範囲だが、残りの3件（オブジェクトメタデータの ETag 不一致、ユーザーメタデータ付き PutObject の内部エラー、テスト後のクリーンアップ失敗）は質が異なる。
- **NAS bucket の3件の内部原因は推測の域を出ない**（**Hypothesis**）。観測事実は「3テストが失敗した」ことのみで、ETag・ユーザーメタデータの生成/保存ロジックは公開されておらず本環境からも未確認。ただし本質は directory marker 単体の問題ではなく、**NAS Bucket を S3 互換オブジェクトストレージとして扱うこと自体に難しい領域がある**という点にある（§5.4）。改修の観点では、HeadObject 404 だけを直しても ETag・ユーザーメタデータ・cleanup が残る（§6）。

---

## 1. 2つの登録機構の区別

**Evidence tier: Public** — [Work with Amazon S3-compatible storage](https://docs.snowflake.com/en/user-guide/data-load-s3-compatible-storage) および[本リポジトリの Snowflake セットアップガイド](./snowflake-iceberg-setup.md)より。

Snowflake が FSx for ONTAP 上のデータを読む経路は2つあり、登録の仕組みが異なる。混同すると「なぜ一方は申請が要り、他方は要らないのか」が読めなくなる。

| | (A) Storage Integration 経路 | (B) S3-compatible external stage 経路 |
|---|---|---|
| Snowflake から見た分類 | Amazon S3 | S3 互換サードパーティストレージ |
| 接続対象 | FSx for ONTAP S3 Access Points のエイリアス | 任意の S3 互換エンドポイント（ホスト名） |
| ステージ定義 | `STORAGE_INTEGRATION` + `AWS_ACCESS_POINT_ARN` | `ENDPOINT='...'` + `URL='s3compat://...'` + direct credentials |
| 事前の申請 | 不要（IAM ロールの信頼関係のみ） | **必要** — Support 申請 + 公開テストスイート検証 |
| 本リポジトリでの検証状況 | E2E 検証済み（[セットアップガイド](./snowflake-iceberg-setup.md)、2026-08 系） | 本ドキュメント（テストスイート実行の観測） |

(A) は Access Point のエイリアスを通常の S3 バケットとして扱わせるため、S3-compatible の申請フローに乗らずに接続できる。(B) は S3 互換エンドポイントとしてホスト名を直接登録するため、後述の申請フローを通る。

---

## 2. S3-compatible エンドポイントの有効化フロー

**Evidence tier: Public** — [Requirements for S3-compatible storage（docs.snowflake.com）](https://docs.snowflake.com/en/user-guide/data-load-s3-compatible-storage) と [How to enable Amazon S3-compatible storage endpoint（Snowflake Community KB）](https://community.snowflake.com/s/article/How-to-enable-Amazon-S3-compatible-storage-endpoint-for-your-Snowflake-account)より。

要件と手順:

- **自動有効化されない**。R2 など一部の主要ベンダーはシステム側で既に allowlist されている場合があり、それ以外は Snowflake Support への連絡で有効化する。docs.snowflake.com は「Cloudflare の `r2.cloudflarestorage.com` は既定で有効、それ以外は Support へ連絡」と記載し、Community KB は "Some widely-used storage vendor endpoints (e.g., Cloudflare R2, MinIO, DigitalOcean Spaces) may already be allowlisted at the system level." と記載している。
- 申請時に添える情報: (a) Snowflake アカウント名とクラウドリージョン、(b) エンドポイント URL、(c) エンドポイントを提供するソフトウェア/ハードウェアのベンダー名。この3項目は **docs.snowflake.com の同ページ**に記載がある。
- 申請の前提として、**公開テストスイートでの自エンドポイント検証**が求められる（"verify the endpoints by using our public test suite"、docs.snowflake.com）。
- **Vendor Support 要件**: テストに通ることに加えて、ストレージベンダーが「Snowflake でテスト済みの S3-compatible サービス」としてサポートしていることが前提として挙げられている（docs.snowflake.com の要件、および Community KB の "Vendor Support: Supported by your storage provider as a Snowflake S3-compatible tested service"）。すなわち NAS bucket を S3-compatible として使うには、互換性の改修だけでなく**ストレージベンダー側のサポート表明**も要件になる。
- エンドポイント側の要件（docs.snowflake.com / Community KB）: S3 API に高度に準拠していること、**virtual-hosted-style リクエスト（path-style 不可）**、**認証局発行の有効な TLS 証明書を伴う HTTPS（自己署名は不可）**、**direct credentials**、ポート番号を含まないこと、Snowflake アカウントのホストされるパブリッククラウドから到達可能なこと。TLS 証明書と virtual-hosted-style は、NAS bucket / エンドポイント構成の**申請時の確認事項**になる。

ステージ定義の形（KB のサンプル、値は例示）:

```sql
CREATE STAGE my_s3compat_stage
  URL = 's3compat://my_bucket/files/'
  ENDPOINT = 'mystorage.com'
  CREDENTIALS = (AWS_KEY_ID = '...' AWS_SECRET_KEY = '...');
```

directory table を付ける場合は `AUTO_REFRESH = FALSE` が必須で、メタデータは手動 REFRESH になる。

### ベンダー掲載の意味

**docs.snowflake.com** の「Vendor support for S3-compatible storage」一覧には複数のストレージベンダーが掲載されている。ただし**同ページ本文**が明記している: この一覧は便宜上のものであり、Snowflake は外部製品の互換性を検証していない、サードパーティ製品の不具合を修正することもできない。したがって掲載は「ベンダーが自製品の一部をテストして動作したと Snowflake に申告した」ことを示すものであって、**接続実績の保証ではなく、申請フローを省略できる根拠でもない**。実際の登録時には自エンドポイントでテストスイートを通し、結果を添えて申請する。なお前節の Vendor Support 要件はこの掲載とは別で、「ベンダーがサポート対象として表明していること」を求めるものである。

---

## 3. テストスイートの対象 API

**Evidence tier: Public** — [テストスイート README](https://github.com/snowflakedb/snowflake-s3compat-api-test-suite)より。

テストは9つの S3 API を対象とする:

| # | API | 備考 |
|:---:|---|---|
| 1 | `getBucketLocation` | SigV4 用のリージョン取得。§4.1 の許容事項を参照 |
| 2 | `getObject` | content range 読み取り（`Content-Range: bytes 10-19/100` 形式）を含む |
| 3 | `getObjectMetadata` | ETag と `x-amz-bucket-region` ヘッダ |
| 4 | `putObject` | 最大 5 GB アップロードとユーザーメタデータ付き PUT を含む |
| 5 | `listObjectsV2` | 1000 超のページングを含む（`PAGE_LISTING_TOTAL_SIZE`） |
| 6 | `deleteObject` | 単一削除 |
| 7 | `deleteObjects` | 複数削除 |
| 8 | `copyObject` | サーバサイドコピー |
| 9 | `generatePresignedUrl` | presigned URL 生成 |

README は「全 API が通ったら Snowflake の公開ドキュメントを参照」と述べており、テスト通過が申請の前提であることと整合する。putObject が 5 GB アップロードを含むため、全実行は数分かかる。

---

## 4. テスト結果

対象は2種のバケット。ONTAP S3 の通常 bucket と、NFS/SMB マルチプロトコルボリューム上の bucket である。以下の合否は本検証環境でのテスト実行の観測（**Observed**）。

### 4.1 ONTAP S3 通常 bucket

**Evidence tier: Observed。** 9 テスト中 Failure 2、Error 0。

| テスト | 結果 | 判定 |
|---|---|---|
| `getBucketLocation` | 期待 `<400>` に対し `<404>` | **許容範囲**。§下記の Troubleshooting 記載に該当 |
| `listObjectsV2`（ページング） | 期待 `<1005>` に対し `<1006>` | 1個ズレ。プレフィックス自身のカウント差の疑い |
| 他7テスト | 通過 | — |
| クリーンアップ | 成功 | — |

2件はいずれもテストスイートの README が明示的に許容している種類である。

- **negative test のエラーコード差**: README の Troubleshooting は、AWS S3 が 404/403 を返す negative case で実装が 400 など別のコードを返しても、合理的なエラーコードとメッセージであれば問題ない、と記載している。`getBucketLocation` の `<400>` vs `<404>` はこれに該当する。加えて README は、SigV4 用のリージョンを `getObjectMetadata` の `x-amz-bucket-region` ヘッダで取得しているため、サービスがバケットロケーションを無視するなら `getBucketLocation` の失敗は無視してよい、とも述べている。
- **ページングの1個ズレ**: リスト対象のプレフィックス自身を1オブジェクトと数えているために、期待値より1件多く返っていると考えられる（**Hypothesis**）。件数境界の実装差であり、データの取りこぼしや過剰計上ではない。

### 4.2 NFS/SMB マルチプロトコル bucket

**Evidence tier: Observed。** 9 テスト中 Failure 3、Error 1。加えてテスト後のクリーンアップが失敗。

| テスト | 結果 | 種別 |
|---|---|---|
| `getBucketLocation` | 期待 `<400>` に対し `<404>` | Failure（§4.1 と同じ許容範囲） |
| `getObjectMetadata` | ETag/MD5 不一致 | Failure |
| `copyObject` | ETag/MD5 不一致 | Failure |
| `putObject`（ユーザーメタデータ付き） | `InternalError` / Status 403「We encountered an internal error」 | **Error** |
| tearDown クリーンアップ | 「Directory is not empty」/ `InvalidObjectState` 403 | ログにスタックトレース（集計外） |

getBucketLocation を除く3件は、ONTAP S3 通常 bucket では発生していない。次節で原因を検討する。

---

## 5. NAS bucket の失敗の観測事実と推測の切り分け

**Evidence tier: 観測は Observed、内部原因は Hypothesis。** 観測できているのは「NAS bucket でこの3テストが失敗した」ことだけである。ONTAP S3・NAS Bucket・FSx for ONTAP S3 Access Points の各バケット実装の詳細は公開されておらず、本検証環境からも確認できていない（§6 のとおり ONTAP 管理面に外から到達できない）。以下の内部原因はいずれも推測の域を出ない。

### 5.1 ETag/MD5 不一致（getObjectMetadata・copyObject）

S3 の契約では、マルチパートでも暗号化でもないオブジェクトの ETag はオブジェクト内容の MD5 と一致する。テストは PUT したオブジェクトの ETag が既知の MD5 と一致することを期待し、NAS bucket でのみ不一致になった。ONTAP S3・NAS Bucket・S3 Access Points で ETag の生成ロジックが異なること自体は起こりうるが、「MD5 ではない別ハッシュ」「copyObject で振り直される」といった具体的な機序までは、公開情報からは言えない。**ETag に関連する内部実装差異の可能性はあるが、現時点では推測の域を出ない**、というのが正確な記述である。

> **隣接する Public 情報（別経路について）**: AWS は FSx for ONTAP の S3 Access Points について「[ETag はオブジェクトデータの MD5 ダイジェストではない](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)」と明記している。本テストが叩いたのは S3 Access Points ではなくネイティブ ONTAP S3 object-store server であり、後者の ETag 挙動は ONTAP 側の仕様に従うため本環境では未確認だが、少なくとも S3 Access Points 経路では ETag≠MD5 が仕様として文書化されている、という隣接事実がある。

### 5.2 ユーザーメタデータ付き PutObject の内部エラー

`testPutObjectWithUserMetadata` は `x-amz-meta-*` を付けた PutObject である。ONTAP S3 通常 bucket では通り、NAS bucket でのみ内部エラーになった。拡張属性（xattr）へのマップは Linux 的には自然な想定だが、ONTAP が実際にどう表現しているかは未確認である。ここは **ユーザーメタデータの保存経路に実装差異または制約がある可能性**、という表現に留める。

### 5.3 クリーンアップ時の「Directory is not empty」

tearDown の `deleteObject` が、疑似ディレクトリ（プレフィックス）を消そうとして NAS 実体では非空ディレクトリのため拒否された、と読める。3件の中では比較的説明しやすい挙動だが、内部原因はやはり推測である。

### 5.4 3件に共通する、より本質的な整理

この3件を directory marker（HeadObject の 404 まわり）の問題に矮小化しないほうがよい。今回の結果を経路別に並べると次のようになる。

| 経路 | 位置づけ |
|---|---|
| ONTAP S3（通常 bucket） | S3-compatible として実質パス（許容範囲の2件のみ） |
| NAS Bucket | 一部互換。オブジェクトストレージとして見ると差異が残る（ETag・ユーザーメタデータ・cleanup） |
| FSx for ONTAP S3 Access Points | 裏に `amazon-fsx-fsvol-*` の NAS bucket が作られる経路。AWS ネイティブ統合が使える一方、NAS bucket の癖を AWS 前段が吸収するか否かは未評価（§7） |

すなわち単純な directory marker の問題ではなく、Databricks・Snowflake・AI 系全般で見たとき、**NAS Bucket を S3 互換オブジェクトストレージとして扱うこと自体に、まだ難しい領域がある**、というのが本質に近い。確定には内部実装またはベンダーの確認が要る。

---

## 6. ストレージ開発側へのフィードバック論点

**Evidence tier: Observed に基づく整理。** NAS bucket の S3 互換挙動を改善する側（ストレージの開発・製品側）へ持っていく際の論点。

**単一改修では S3-compatible 互換が十分になると言い切れない。** NAS bucket の失敗は directory marker（HeadObject の 404 まわり）だけでなく、ETag 系・ユーザーメタデータ系・cleanup 系にも及んでいる。したがって、**HeadObject 404 問題だけを改修しても、S3-compatible 互換が十分になるとは現時点では言い切れない**。改修の優先度を議論する際は、この3系統（ETag / ユーザーメタデータ / cleanup）が残る前提で扱う必要がある。この「HeadObject 404 だけでは足りない可能性」は、検証実施者が事前に挙げていた懸念であり、今回のログがそれを裏付けた形である。

getBucketLocation の 400/404 差は README が明示的に許容する範囲であり、この論点からは除く。ONTAP S3 通常 bucket 側はそもそも実質パスである。

---

## 7. 次フェーズの確認事項（S3 Access Points の評価方針）

**Evidence tier: 未実施。** 同じテストスイートを S3 Access Points 経由でも実行し、結果を追記する予定である。次の観点を確認したい。

- FSx for ONTAP の S3 Access Points は、その裏に `amazon-fsx-fsvol-*` の NAS bucket が作られる（Access Point 削除時に確認済み）。したがって主な論点は「ONTAP S3 に近いか／AWS S3 に近いか」の二択ではなく、**NAS bucket の癖（ETag・ユーザーメタデータ）が AWS 側の前段で吸収されるのか、それとも NAS bucket と同じ箇所で落ちるのか**である。
- **テストの前提と互換性の failure を区別する必要がある**。詳細は §7.1 の対応表。
- **AI / Cortex 系の差分は一部が既知である**。S3 Access Points 経由では一部の Cortex 系 SQL が使えないこと、Cortex は US リージョン中心で一部の Cortex／AI 関数は US リージョン限定（関数による）であること、9/1 時点で Tokyo リージョンでは AI Images が未サポートであることは既に共有されている。基本的な S3 API 互換とは別軸として、この既知の差を並べて扱う。
- これを揃えると、Databricks 側で確認済みの **Unity Catalog / AI Functions / FILE 型**との比較もしやすくなる（[Databricks FILE 型評価](./databricks-file-type-evaluation.md) と同じ観点で並べられる）。

S3 Access Points は §1 の (A) のとおり Snowflake からは Amazon S3 として扱われる経路であり、テスト合否そのものが接続可否を決めるわけではない、という前提での確認である。結果が出るまでこの節はこれ以上の仮説を記載しない。

### 7.1 S3 Access Points の制約とテストスイートへの影響

**一次出典**: [Access point compatibility — FSx for ONTAP（docs.aws.amazon.com）](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)、**確認日 2026-09-26**。互換性の失敗と、テストの前提を満たせないことによる失敗は分けて扱う。

| S3 AP の制約（AWS 一次出典） | テストスイートへの影響 | tier |
|---|---|---|
| **Object Versioning 非サポート** | README は `BUCKET_NAME_1` にバージョニング有効を要求 → 前提を満たせない。ここに起因する failure は互換性の欠陥ではない | Public（README + AWS doc） |
| **ETag はオブジェクトデータの MD5 ではない** | getObjectMetadata / copyObject の ETag=MD5 検証が S3 AP でも fail する見込み。仕様であって欠陥ではない | Public（AWS doc）。S3 AP での実測は未実施 |
| **CopyObject / UploadPartCopy は同一リージョン内のサーバー側コピー**（コピー元とコピー先に S3 バケットと FSx for ONTAP の S3 Access Points を使える。コピー先が FSx for ONTAP のボリュームなら暗号化は `SSE-FSX`、ストレージクラスは `FSX_ONTAP` のみ）。出典: [What's New（2026-11-22）](https://aws.amazon.com/about-aws/whats-new/2026/11/s3-access-points-server-side-copy-fsx/)、確認日 2026-11-24。実測は [FSx-for-ONTAP-Adoption-Playbook のノート](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/domains/data-utilization/notes/s3-access-point-constraints.md)（2026-11-24、1 環境）にある | copyObject テストがどの組み合わせでコピーするかは、テストコードを確認していない。アカウントをまたぐコピーも確認していない | 未確認 |
| **conditional writes 非サポート** | 9 テストが `If-None-Match` 等の条件付き書き込みを使うかは**テストコード未確認** | 未確認 |
| `REGION_2` / `NOT_ACCESSIBLE_BUCKET` / 1000件超プレフィックス | テストハーネス側の準備で用意可能か | 未確認（S3 AP 環境で未検証） |

**Presign（generatePresignedUrl テストに直結）**: docs.aws.amazon.com の同表は **2026-09-26 時点で `Presign — Supported`**。docs.amazonaws.cn の S3 ユーザーガイド（[access-points-service-api-support](https://docs.amazonaws.cn/en_us/AmazonS3/latest/userguide/access-points-service-api-support.html)）の FSx for ONTAP 列も **Supported**。以前は `Not supported` と記載されていた。presign はクライアント側の署名の計算で、実際に走るのはサポート対象の GetObject である。その経緯は [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns の docs/s3ap-compatibility-notes.md](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/blob/main/docs/s3ap-compatibility-notes.md) にある。現在の記載どおりなら generatePresignedUrl テストは S3 AP でも通る見込みだが、S3 AP での実測は未実施。

---

## FAQ

**Q1. FSx for ONTAP を Snowflake の S3-compatible ストレージとして登録できるか。**

登録の手続き自体は KB に定義されている（Support 申請 + 公開テストスイート検証）。ただし本ドキュメントが扱うのはテストスイートの実行結果までで、申請から接続確立までの E2E は本ドキュメントの範囲外である。なお、S3 Access Points 経由（§1 の (A)）であればこの申請フローを経ずに Amazon S3 として接続でき、その経路は[セットアップガイド](./snowflake-iceberg-setup.md)で E2E 検証済みである。

**Q2. ONTAP S3 通常 bucket のテストで出た2件の失敗は問題か。**

いずれもテストスイートの README が明示的に許容している種類である。getBucketLocation のエラーコード差は negative test の実装差、ページングの1個ズレはプレフィックスのカウント差の疑いで、データの取りこぼしではない。README は SigV4 用リージョンを別ヘッダで取得しているため getBucketLocation の失敗は無視してよいとも述べている。

**Q3. NAS bucket の失敗はどう解釈すべきか。**

getBucketLocation は ONTAP S3 通常 bucket と同じ許容範囲。残る3件（ETag 不一致、ユーザーメタデータ付き PutObject の内部エラー、クリーンアップ失敗）は観測事実であり、内部原因は推測の域を出ない（**Hypothesis**）。より本質的には、NAS Bucket を S3 互換オブジェクトストレージとして扱うこと自体に難しい領域がある、と捉えるのがよい（§5.4）。改修の観点では、HeadObject 404 の1点だけ直しても ETag・ユーザーメタデータ・cleanup が残る、という点が重要（§6）。

**Q4. Snowflake のベンダー一覧に載っていれば接続できるか。**

一覧掲載は接続保証ではない。KB 本文が「便宜上の一覧であり Snowflake は互換性を検証していない」と明記している。実際の登録では自エンドポイントでテストスイートを通し、結果を添えて Support に申請する。

---

## 参考資料

**Snowflake（Public）**
- [Work with Amazon S3-compatible storage](https://docs.snowflake.com/en/user-guide/data-load-s3-compatible-storage) — 要件、有効化フロー、ベンダー一覧の注記
- [snowflake-s3compat-api-test-suite（GitHub）](https://github.com/snowflakedb/snowflake-s3compat-api-test-suite) — 対象 API 一覧と Troubleshooting

**本リポジトリ**
- [Snowflake から FSx for ONTAP のファイルを読み、Iceberg テーブルを書く](./snowflake-iceberg-setup.md) — (A) Storage Integration 経路の E2E 手順
- [S3 Access Point ネットワーキング](./fsx-ontap-s3ap-networking.md) — エンドポイント到達性の設計
- [ベンダー比較](./vendor-comparison.md) — Snowflake / Databricks の連携パス整理
- [Databricks FILE 型（β）評価](./databricks-file-type-evaluation.md) — 別エンジンでの S3 Access Points 挙動評価（本ドキュメントの姉妹編）
