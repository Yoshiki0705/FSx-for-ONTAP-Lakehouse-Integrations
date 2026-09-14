🌐 [English](../en/databricks-file-type-evaluation.md) | **日本語**

# Databricks FILE 型（β）評価: マルチモーダルデータ、メタデータテーブル、FSx for ONTAP

> **ステータス**: 評価初版（2026-08-12）。Databricks 側の記述は公式ドキュメント由来。FSx for ONTAP のオブジェクトメタデータ挙動は本環境で **Verified**。Databricks ランタイムの挙動は**本環境で未検証** — [検証ステータス](#検証ステータス)を参照。
> **Evidence tier**: 各主張に明記（**Public** = 公開情報で検証可能 / **Verified** = 本環境で実測 / **Project-context** = 内部前提 / **Hypothesis** = 仮説）。
> **検証環境**: AWS ap-northeast-1、FSx for ONTAP S3 Access Point（INTERNET origin、UNIX ユーザー）、boto3 1.43.36。
> **フレーミング**: vendor-versus ではなく right-tool-for-the-job。本リポジトリが推奨する方式の制約も含めて、トレードオフを対称に記載。

---

## エグゼクティブサマリー

- **FILE 型とは**: 非構造化ファイルの**ガバナンスされた参照**（`uri`, `offset`, `size`, `content_type`, `checksum`）をバイト列の代わりに保持する Delta の列型。文書・画像・音声・動画が構造化列の隣に並び、AI 関数や UDF に列として渡せる。2026-08 にベータ発表。
- **設計レベルの判定**: FILE 型は、本リポジトリが [Iceberg メタデータカタログ](../../integrations/iceberg-metadata-catalog/README-ja.md)で既に実装しているパターン（ファイル参照 + AI 派生列を持つメタデータテーブル）を製品化したものにほぼ等しい。設計の方向性が正しかったことを示す有用なシグナル。
- **ただし FSx for ONTAP のブロッカーは依然として解消しない** — ただし従来の記録より狭い理由で。`FILE EXTERNAL` は Unity Catalog Volume 内のファイルしか参照できない。S3 Access Point 上の UC External Volume は**作成できる**。失敗するのは**それ経由の読み取り**であり、Unity Catalog が払い出す down-scoped セッションポリシーがバケット形式 ARN で書かれている一方、AWS はアクセスポイント経由のリクエストをアクセスポイント ARN に対して認可評価するためである（[BLK-001](./blocker-tracker.md#blk-001-uc-の資格情報払い出しでは通らない-s3-ap-の読み取り)、2026-08-12 に影響範囲を訂正）。利用者側の回避策はない。残る経路は `FILE MANAGED` のみで、これはバイト列を UC 管理ストレージへ**コピー**するため、zero-copy と「データがその場に留まること」に依存する ONTAP の効率機能を失う。
- **前進した点**: FILE 型とは別機能である [`_object_metadata` 列](https://docs.databricks.com/aws/en/ingestion/object-metadata-column)（DBR 18.2+）が、S3 の**オブジェクトタグ**と**ユーザー定義メタデータ**をクエリ可能な列として公開する。これはオブジェクトストレージ側メタデータとメタデータテーブルを結ぶ公式の橋であり、本リポジトリがこれまで答えを持たなかった箇所。
- **本検証で確認**: FSx for ONTAP S3 AP はオブジェクトタグと `x-amz-meta-*` を**サポートする**。タグは **file-scoped**（同一ボリューム上の別 Access Point から読める）で、**データと同じ PutObject** で付与できる。重要な制約が 2 つ: この Access Point ではオブジェクトタグは**実質 ASCII 限定**であり、オブジェクトの上書きでタグとユーザーメタデータが**無言で消える**。
- **2 つの機構は併用できない**: Databricks は、Databricks 管理ストレージではユーザーメタデータ・システムメタデータ・タグが `null` になると明記している。したがって同一のバイト列に対して `FILE MANAGED`（UC ストレージへコピー）と `_object_metadata`（元ストレージからタグを読む）を両立できない。**取り込み時に一度だけ読み、以降はテーブルを真実の源とする。**
- **推奨する形**: 3 層構成 — ONTAP/IAM を唯一の強制レイヤ、メタデータテーブルを真実の源、オブジェクトタグを狭い入口とする。オブジェクトタグは**入力**であり、認可判断の根拠にはしない。

---

## 1. FILE 型とは

**Evidence tier: Public** — [FILE type リファレンス](https://docs.databricks.com/aws/en/sql/language-manual/data-types/file-type)、[FILE タイプおよび非構造化データ](https://docs.databricks.com/aws/ja/unstructured/file)、[Ingest files as the FILE type](https://docs.databricks.com/aws/en/ingestion/file)、[発表ブログ](https://www.databricks.com/blog/introducing-file-type-native-column-type-multimodal-data)より。

`FILE` 値はバイト列ではなく参照とメタデータを保持する:

| フィールド | 型 | 備考 |
|---|---|---|
| `uri` | STRING | null 不可 |
| `offset` | BIGINT | ファイル内のバイトオフセット |
| `size` | BIGINT | バイト数 |
| `content_type` | STRING | 判明している場合の MIME タイプ |
| `checksum` | STRING | `<algorithm>:<digest>` — `ETAG`, `MD5`, `CRC32`, `CRC32C`, `SHA-256` |

列がポインタを保持するため、エンジンはバイト列を必要とする工程でのみ読み取る。比較対象として挙げられているのは、サイズやパスだけが必要な場合でも読み取りごとにオブジェクト全体をマテリアライズする `BINARY` と、ガバナンスされたリンクを持たないため別ワークロードがファイルを削除するとテーブルが古い情報を持つ `STRING` パス列。

> **メタデータ面についての補足**: 上記 5 フィールドが `FILE` 値のメタデータ面の全体である。**オブジェクトタグやユーザー定義メタデータのためのフィールドは存在しない。** 検索・フィルタ・ガバナンスの対象にしたい属性は、すべて自分でテーブルの列にする必要がある。FILE 型を前提に設計する前に理解すべき最重要点。

### FILE MANAGED と FILE EXTERNAL

| | `FILE MANAGED` | `FILE EXTERNAL` |
|---|---|---|
| バイト列 | *FileSpace*（`databricks.filespace-preview` テーブルプロパティで宣言する UC Volume）へ**コピー** | その場を**参照** |
| ソースの所在 | 任意。Lakeflow コネクタ経由で SharePoint / Google Drive / OneDrive / SFTP も可 | **Unity Catalog Volume 内のみ** |
| ライフサイクル | 行に紐づく。行を削除するとファイルがガベージコレクション対象になる | UC 管理外。行削除はファイルに影響しない |
| アクセス制御 | テーブル権限（`SELECT`）**と** Volume 権限（`READ VOLUME`） | Volume 権限（`READ VOLUME`）。テーブル権限でメタデータは見えるが、バイト列の読み取りには `READ VOLUME` が必要 |
| Databricks の推奨 | こちら（ファイル単位権限と組み込みコンプライアンスのため） | 他ツールが読む場所にファイルを留めたい場合 |

発表記事の GDPR「忘れられる権利」の主張を担っているのは `FILE MANAGED`。行を削除するとバイナリが回収対象になり、参照先を失ったポインタを残さずテーブルとストレージが同期を保つ。

### 織り込むべきベータ制約

**Evidence tier: Public。**

| 制約 | 帰結 |
|---|---|
| **Delta Lake テーブル限定** | Iceberg では利用不可。本リポジトリのメタデータカタログは S3 Tables 上の Iceberg なので、そのまま置き換えられない |
| **DBR 18 LTS 以上**。サーバーレスノートブックでは非対応（サーバーレス SQL ウェアハウスにアタッチしたノートブックでは可） | コンピュート面の前提条件 |
| ベータ — ワークスペース管理者が **Previews** ページで有効化する必要がある | 顧客ワークスペースに存在する前提を置けない |
| **パーティション列・クラスタリング列・MAP キー・結合キー・GROUP BY 式に使用不可** | 代わりに `file.uri` で結合・グループ化する |
| **参照されないマネージドファイルの自動ガベージコレクションはベータでは未サポート** | 手動掃除用ノートブックが提供される。実行するまでストレージが無言で増える |
| `FILE EXTERNAL` は **Volume 外**のファイルには非対応 | §2 のすべてを支配する制約 |
| オープンフォーマット対応は進行中と記載（「Parquet, Delta Lake, Apache Iceberg, Apache Spark への組み込みをコミュニティと進めている」） | ポータビリティは**方向性**であって、現時点で利用可能な性質では**ない**。FILE 型を「今すぐオープンで可搬」と説明してはいけない |

---

## 2. FSx for ONTAP のブロッカーが解消しない理由

**Evidence tier: Verified**（2026-08-12、専用の非トライアルワークスペースでネイティブ S3 のコントロール付きで計測 — [エビデンス](../../verification-pack/databricks/file-type/evidence/2026-08-12/evidence-record-tokyo.yaml)）。自分のアカウントで再現するには [検証ランブック](./databricks-verification-runbook.md) を参照。

> **2026-08-12 訂正。** 本節はこれまで「S3 Access Point 上に UC External Volume は作れない」と記述していた。これは誤りである。Storage Credential・External Location・External Volume はいずれも、UC 自身の検証を有効にしたまま作成できる。失敗するのは**それ経由の読み取り**である。

連鎖が終端する位置は、従来の記録より 1 段後ろで、理由も異なる:

```
目的: FSx for ONTAP 上のファイルを、コピーせずに FILE 列から参照する
  │
  ├─ FILE EXTERNAL？
  │    └─ Unity Catalog Volume 内のファイルのみサポート
  │         └─ S3 Access Point 上の UC External Volume
  │              ├─ CREATE STORAGE CREDENTIAL      → 成功
  │              ├─ CREATE EXTERNAL LOCATION       → 成功（検証有効）
  │              ├─ CREATE EXTERNAL VOLUME         → 成功
  │              └─ 経由での読み取り                → ブロック（403）
  │                   └─ BLK-001: UC が払い出す down-scoped session
  │                      policy はバケット形式 ARN で書かれ、AWS は
  │                      アクセスポイント経由のリクエストをアクセス
  │                      ポイント ARN に対して認可評価する。
  │                      "no session policy allows the s3:ListBucket action"
  │
  └─ FILE MANAGED？
       └─ 動作するが、バイト列を UC 管理ストレージへコピーする
            ├─ zero-copy を喪失。ストレージが二重課金
            ├─ ONTAP の重複排除 / 圧縮 / Snapshot / FlexClone は
            │  コピーには効かない
            └─ 元オブジェクトのタグが読めなくなる（§4 参照）
```

これは FSx for ONTAP データに対する他のあらゆる UC ガバナンス機能と同じ壁であり、推奨される暫定経路も変わらない。標準 S3 バケットへステージングし、そのコピーをガバナンスする。[BLK-001 の回避策](./blocker-tracker.md#blk-001-uc-の資格情報払い出しでは通らない-s3-ap-の読み取り)と [DataSync → S3 ガイド](./datasync-to-s3-guide.md)を参照。

> **変わったこと**: BLK-001 を解消する価値が上がった。従来は FSx for ONTAP 常駐の表形式データに対する lineage・タグ・マスク・行フィルタを得るだけだった。今は加えて ONTAP 常駐の非構造化データに対する `FILE EXTERNAL` が得られる。これは「NAS 上に留めたままのマルチモーダル AI」そのものである。Databricks に機能ギャップを提起する際に改めて述べる価値がある — [外部に提起した質問](#6-外部に提起した質問)を参照。

---

## 3. ファイル単位のアクセス制御が実際に効く範囲

**Evidence tier: Public** — [ABAC core concepts](https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/core-concepts)、[Apply tags to Unity Catalog securable objects](https://docs.databricks.com/aws/en/database-objects/tags)より。

発表記事は ABAC を強調しているので、粒度を正確にしておく価値がある。設計すべきスキーマがこれで決まるため。

- **governed tags** はアカウントレベルのキー・値ペアで、*securable*（カタログ / スキーマ / テーブル / 列）に適用される。**行には適用されない。**
- あるレベルに付けたタグは下位へ継承されるが、**列レベルには継承されない。**
- ABAC が提供するのは、テーブル・マテリアライズドビュー・ストリーミングテーブルに対する**行フィルタポリシーと列マスクポリシー**。

したがって「この画像はチーム A のみ可視」という要件は、ファイルへのタグとしては表現できない。**行の属性列にして、行フィルタで保護する**形になる。FILE 型が変えるのは行が*何を含むか*（裸のパス文字列ではなく、ライフサイクル管理された実体のあるファイル参照）であって、制御点の位置は変えない。

これは本リポジトリが Iceberg メタデータカタログについて独自に到達した結論と同じである。付記すると、本プロジェクトの社内議論でも FILE 型の発表前に同じ設計に到達していた。すなわち「テーブルで管理するならメタデータのフォーマットや文字数に制限（ルール）を課せるので、リッチなメタデータはテーブルに置き、それを検索、場合によってはアクセス制御に使う」という形である。

---

## 4. オブジェクトメタデータの橋渡し

ここが実際に前進した部分であり、FILE 型とは別の機能である。

### 4.1 Databricks 側: `_object_metadata` 列

**Evidence tier: Public** — [Object metadata column](https://docs.databricks.com/aws/en/ingestion/object-metadata-column)、DBR 18.2+。

`_object_metadata` はファイルベースのデータソースが公開する隠し STRUCT 列で、従来の `_metadata` 列（パス・サイズ・更新時刻）とは別物:

| フィールド | 型 | 内容 |
|---|---|---|
| `mime_type` | STRING | Content type |
| `etag` | STRING | ETag — 変更検知に使える |
| `user_metadata` | VARIANT | S3 の `x-amz-meta-*` ユーザー定義メタデータ |
| `system_metadata` | VARIANT | プロバイダが設定するシステムメタデータ |
| `tags` | VARIANT | **S3 オブジェクトタグ** |

値は `_object_metadata.tags:environment::string` のように取り出す。`spark.read`、Auto Loader、`COPY INTO` のいずれからも選択できるため、取り込み時にタグを Delta の列へ落とせる。

設計を左右する既知の注意点:

- いずれかのフィールドを選択すると**ファイルあたり最大 2 回の追加クラウド API 呼び出し**が発生するため、小さなファイルが大量にある場合は広域スキャンが遅くなる。
- `tags` には **`s3:GetObjectTagging`** が必要。権限がない場合、明示的に失敗せず `tags` が `null` になる。
- **Databricks 管理ストレージでは `user_metadata` / `system_metadata` / `tags` は `null`。**
- 将来フィールドが追加される可能性があるため、構造体全体ではなく特定フィールドを選択してスキーマ進化エラーを避ける。

### 4.2 FSx for ONTAP 側: Access Point が実際にサポートするもの

**Evidence tier: Verified** — 2026-08-12 実測。証拠: [`verification-pack/s3ap-object-tagging/evidence/2026-08-12/`](../../verification-pack/s3ap-object-tagging/evidence/2026-08-12/evidence-record.yaml)。再現: [`shared/scripts/probe_s3ap_object_tagging.py`](../../shared/scripts/probe_s3ap_object_tagging.py)。

AWS は FSx for ONTAP ボリュームにアタッチされた Access Point について `PutObjectTagging` / `GetObjectTagging` / `DeleteObjectTagging` をサポート、Object Annotations を**非サポート**と記載している。これで可否は決まるが、運用上の許容範囲は決まらない。本検証はそれを実測した。

| 性質 | 結果 | ネイティブ Amazon S3 と同じか |
|---|---|:---:|
| `PutObjectTagging` / `GetObjectTagging` / `DeleteObjectTagging` | サポート | ✅ |
| `x-amz-meta-*` ユーザーメタデータの往復 | サポート（`HeadObject` で返る） | ✅ |
| **書き込み時タグ付け**（`PutObject` の `x-amz-tagging`） | サポート — 1 リクエスト、追加往復なし | ✅ |
| オブジェクトあたり最大タグ数 | 10。11 で `BadRequest: Object tags cannot be greater than 10` | ✅ |
| タグキー長 | 128 は受理、129 で `InvalidTag` | ✅ |
| タグ値長 | 256 は受理、257 で `InvalidTag` | ✅ |
| **文字集合** | **U+0000–U+00FF は受理。U+0100 以上は大半の文字列で拒否** | ❌ **乖離** |
| タグのスコープ | **file-scoped** — ある Access Point で書いたタグが同一ボリュームの別 Access Point から読める | n/a |
| オブジェクト上書き後のタグ | **消える** | ✅（`PutObject` の意味論どおりだが見落としやすい） |
| オブジェクト上書き後のユーザーメタデータ | **消える** | ✅ |
| `GetObjectTagging` レイテンシ | 中央値 52–59 ms、単一呼び出し元、warm | n/a |
| Object Annotations | 非サポート（AWS ドキュメント） | ❌ |

#### 文字集合の乖離

Amazon S3 はタグのキーと値を UTF-16 で数える Unicode と記載している。この Access Point ではその挙動にならない。Latin-1 範囲の文字は受理される（`café`、`ü`、U+00FF の `ÿ`）が、U+0100 以上は `InvalidTag` で拒否される。ギリシャ文字、キリル文字、ひらがな、カタカナ、漢字、全角、BMP 外がすべて失敗する。

不整合なのは、**一部の多バイト文字列が受理される**点である。タグキーとして `分類`、`品質`、`名古屋`、`画像`、`音声` は成功し、`東京`、`機密`、`日本語`、`工場`、`検査` は失敗する。結果は**文字列ごとに安定**（繰り返し 6/6 で同一）であり、フレーク（不定性）ではないが、規則は導出できなかった。3 つの仮説を検証し、いずれも反証された:

| 仮説 | 結果 |
|---|---|
| UTF-8 バイト長のパリティ（奇数が失敗） | 反証: `名古屋`（9 バイト）が受理、`機機`（6 バイト）が拒否 |
| サービスが UTF-8 バイト列を UTF-16BE として検証している | 一致 15/21。受理された多バイト事例のすべてと矛盾 |
| バイト列が euc-jp / shift_jis / cp932 / iso2022_jp / big5 / gb2312 / euc-kr としても解釈可能 | 最良で一致 11/16。どのコーデックも分岐を説明しない |

**実務指針: FSx for ONTAP S3 AP のオブジェクトタグは ASCII に限定する。** 多バイト文字列の一部が検証に失敗し、失敗する部分集合を外部から予測できないため、日本語のタグ値を書くパイプラインは入力によって成功と失敗が分かれる。挙動 / ドキュメントに関する質問として AWS に提起済み（[§6](#6-外部に提起した質問)）。

これにより長さ制限が見た目より実務的な意味を持つ。タグ 10 個、キー 128 文字、値 256 文字、ASCII のみという条件では、オブジェクトタグは日本語の要約・分類理由・埋め込みを保持できない。保持できるのは少数の低カーディナリティな ASCII ラベルだけである。それ以外はテーブルに置く — 社内議論での「フォーマットや文字数の制限（ルール）」という直感が先取りしていた結論であり、想定より鋭い理由による。

#### presigned URL が動作するのは期待どおり

AWS の Access Point 互換性表は FSx for ONTAP ボリュームについて **`Presign` を「Not supported」**と記載している。本環境の実測では `aws s3 presign` が URL を生成し、認証なしの `curl` が **HTTP 200 とオブジェクト本体**を返した。

これは欠陥ではなく、実際には矛盾でもない。**Evidence tier: Public**（本アカウントから過去に提起したケースに対する 2026-05 の AWS Support の説明）: presign は**完全にクライアント側の SigV4 署名計算**であり、presign の時点で AWS にリクエストは届かない。生成された URL を使う操作は単なる `GetObject` であり、同じ表で Supported とされている。したがって `GetObject` を壊さずに presign だけをブロックすることは構造的に不可能である。

つまり表の `Presign` 行は「**公式にテストしていない。本番で依存しないこと**」と読むべきで、「失敗する」ではない。この表現については AWS 側でドキュメント修正リクエストが起票済みである。

> **指針**: 「Supported」は自由に構築してよい、「Not supported」は実際に動いていても依存しない、と扱う。実測で動作を確認していても本リポジトリが FSx for ONTAP データに対する presigned URL 配信パターンを推奨しないのはこのためである。また、本リポジトリの別の箇所に記録されている Snowflake `GET_PRESIGNED_URL` の結果もこれで整合する。同じ理由で動作し、同じ留保が付く。
>
> 同じ説明に含まれていた関連情報: ONTAP S3 は ONTAP 9.11.1 から v4 presigned URL、9.16.1 から v2 presigned URL をサポートし、v4 が推奨される。

### 4.3 相互排他

§4.1 と §4.2 を合わせると、パイプラインの順序を決める制約が現れる:

| 実現したいこと | バイト列の所在 | 失うもの |
|---|---|---|
| オブジェクトタグ / ユーザーメタデータを列に継承する | **元の**ストレージを直接読む（`_object_metadata`） | FILE 型の行連動ライフサイクル |
| FILE 型のライフサイクル同期（行削除 → ファイル回収） | **UC 管理**ストレージ（`FILE MANAGED`） | オブジェクトタグとユーザーメタデータ（Databricks 管理ストレージでは `null` と明記） |

同一のバイト列で両方を得ることはできない。解決策は順序付けである。**オブジェクト側メタデータは取り込み時に一度だけ実体の列へ読み込み、その時点以降はテーブルを真実の源とする。** これはまさに本プロジェクトで非公式に描かれていた「オブジェクトを書くタイミングか、もしくは一定の周期で、メタデータ用のテーブルにメタデータ情報を別途記載する」という形である。

---

## 5. 推奨する形: 3 層構成

**Evidence tier: Project-context**（推奨そのもの）。上記の **Verified** と **Public** の事実の上に構築。

```
┌─ 強制レイヤ ───────────────────────────────────────────────────┐
│  ONTAP ファイル ACL + S3 AP ポリシー + IAM                      │
│  （UC へステージング済みのデータには UC 行フィルタも）               │
│  → 実際にアクセスを拒否できる唯一の層                              │
└──────────────────────────────────────────────────────────────┘
        ▲ すべての認可判断で参照する
        │
┌─ 真実の源 ───────────────────────────────────────────────────┐
│  メタデータテーブル（現在は S3 Tables 上の Iceberg。             │
│  BLK-001 解消後は Delta + FILE 型）                       　　│
│  → 分類・要約・埋め込み・PII フラグ・ACL ヒント                  │
│  → スキーマと検証ルールは「ここ」で課す                          │
└────────────────────────────────────────────────────────────┘
        ▲ 取り込み時に一度だけ読む。以降は権威として扱わない
        │
┌─ 発見の入口 ─────────────────────────────────────────────────┐
│  S3 オブジェクトタグ（10 個以下、ASCII、キー 128 / 値 256）      │
│  → 既存 NAS 資産の取り込み、粗い絞り込み               　        │
└────────────────────────────────────────────────────────────┘
```

実測から導かれる 3 つの規則:

1. **オブジェクトタグは入力であって出力ではない。** `s3:PutObjectTagging` を持つ主体は誰でも書き換えられ、オブジェクトの上書きで消える。発見のシグナルであり、認可判断の根拠には決してしない。[S3 Annotations](./s3-annotations-governance-evaluation.md) について既に文書化している discovery と enforcement の境界と同じ。
2. **構造はテーブルで課す。** スキーマを要求し、値を検証し、日本語テキストや埋め込みを保持できるのはテーブル層だけである。オブジェクトタグはいずれも保持できない。
3. **アクセス制御は行に帰着する。** ABAC の粒度（§3）を踏まえると、ファイル単位の制御は属性列に対する行フィルタになる。属性列を先に設計する。

### 書き込み時 / 定期 — どちらも既に実装済み

本プロジェクトで非公式に描かれていた 2 つの投入方式は、本リポジトリに既に存在する:

| 方式 | 実装 | 特性 |
|---|---|---|
| **書き込み時**（イベント駆動） | FPolicy → SQS → Lambda（[`shared/cloudformation/fpolicy-ingestion.yaml`](../../shared/cloudformation/fpolicy-ingestion.yaml)、メタデータカタログ Phase 2） | 秒オーダー。FSx for ONTAP S3 AP が発行しない S3 Event Notifications の代替（[BLK-003](./blocker-tracker.md#blk-003-s3-event-notifications-非サポート)） |
| **定期スキャン** | [`initial-metadata-scan.py`](../../integrations/iceberg-metadata-catalog/scripts/initial-metadata-scan.py) | イベントの取りこぼしを回収する。突き合わせ経路 |
| オブジェクト自体への書き込み時タグ付け | `PutObject` + `x-amz-tagging` — **Verified**、1 リクエスト | 生成側が追加往復なしで ASCII ラベルを刻める |

Databricks ネイティブの相当機能（`list_files`、`STREAM read_files(..., format => 'file')`、`AUTO CDC`）はいずれも UC Volume を前提とするため、現状 FSx for ONTAP には使えない。ONTAP 常駐データに対しては FPolicy 経路が適合する。

> **コストに関する補足**: タグは `ListObjectsV2` では返らないため、オブジェクトタグからテーブルを構築するとファイルあたり 1 回の `GetObjectTagging` が必要になる。実測中央値 52–59 ms・並列度なしでは呼び出し元あたり約 17 ファイル/秒であり、並列化を要する cold path の処理であってリクエストパスに置くものではない。1 つの Access Point でのサンプル実行であり、並列度・ファイルサイズ・throughput capacity は変化させていない。

---

## 6. 外部に提起した質問

ドラフトと追跡は公開ツリー外で管理している。各ベンダーに提起した内容:

| # | 提起先 | 質問 |
|:---:|---|---|
| ~~Q1~~ | AWS | ~~`Presign` は Not supported と記載されているが presigned GET は HTTP 200 を返す~~ — **クローズ済み。既に回答を得ていた**。presign はクライアント側の署名計算であり、サービスに届くのはサポート対象の `GetObject` である。2026-08-12 に起票した重複ケースは過去履歴を確認した時点で取り下げた。表の表現に対する AWS 側のドキュメント修正リクエストは 2026-07-19 から起票済み。[§4.2](#presigned-url-が動作するのは期待どおり) を参照 |
| Q2 | AWS | **2026-08-12 エスカレーション。** U+0100 以上のオブジェクトタグのキー / 値は大半の文字列で `InvalidTag` になるが、一部は受理される（`分類` は受理、`東京` は拒否。どちらも 2 文字の漢字）。**ONTAP 側の不具合として公開されました**: [CONTAP-771956](https://kb.netapp.com/on-prem/ontap/da/S3/S3-Issues/CONTAP-771956)（Public）に、U+0000〜U+00FF は受理され U+0100 以上は大半が拒否されること、`分類` / `品質` / `名古屋` が決定的に受理される一方 `東京` / `機密` / `日本語` が拒否されること、**判定が文字単位ではない**（`分` と `類` は単独では失敗するが `分類` は成功する）ことが記載されています。修正が入ったかどうかは同 KB の更新で追跡します。修正が公開されるまでオブジェクトタグは ASCII に限定します |
| Q3 | Databricks | **2026-08-12 に再定義。** S3 Access Point エイリアスに対する External Location と External Volume は作成できるが、読み取りはすべて拒否される。down-scoped セッションポリシーがバケット形式 ARN で表現される一方、AWS はアクセスポイント経由のリクエストをアクセスポイント ARN に対して認可評価するためである（`because no session policy allows the s3:ListBucket action`）。ロケーション URL がアクセスポイントのエイリアスであるとき、Unity Catalog はアクセスポイント ARN 形式（`arn:aws:s3:<region>:<account>:accesspoint/<name>` および `.../object/*`）を出力できないか。UC が払い出した資格情報を使えば Databricks の外でも再現する |
| Q4 | Databricks | `FILE MANAGED` の FileSpace は **External** Volume でもよいのか、Managed Volume でなければならないのか。ドキュメントは限定なしに「Unity Catalog Volume」と記載している |
| Q5 | Databricks | `FILE` 列を含むテーブルは OpenSharing で共有でき、受信側で認識されるか。Volume 共有（`ALTER SHARE ... ADD VOLUME`）は存在するが、FILE 列を持つテーブルについては可否とも記載がない |
| Q6 | Databricks | 新たな重みと**訂正された影響範囲**を添えて BLK-001 を再提起: 門は登録ではなく資格情報の払い出しである。`FILE EXTERNAL` により、そのセッションポリシーが「NAS 常駐データに対するガバナンス下のマルチモーダル AI」との間に立つ唯一のものになった |

---

## 検証ステータス

### 本環境で検証済み（2026-08-12）

- FSx for ONTAP S3 AP: オブジェクトタグ Put/Get/Delete、`x-amz-meta-*`、書き込み時 `x-amz-tagging` がすべて動作
- 上限はネイティブ Amazon S3 と一致: タグ 10 個、キー 128、値 256
- 文字集合は乖離: Latin-1 は受理、U+0100 以上は大半で拒否。安定しているが説明できない受理部分集合が存在
- タグは file-scoped であり Access Point スコープではない
- タグとユーザーメタデータはオブジェクトの上書きで消える
- presigned GET が HTTP 200 を返す — presign はクライアント側の処理であり、届くのはサポート対象の `GetObject` なので期待どおり。表の「Not supported」は「失敗する」ではなく「依存しない」の意
- `GetObjectTagging` 中央値 52–59 ms（単一呼び出し元、warm — サンプル実行であってベンチマークではない）

### Databricks 側で検証済み（2026-08-12）

14 日間トライアルのワークスペースで、サーバーレス SQL ウェアハウス（DBSQL 2026.20）経由で実行した。証拠: [`verification-pack/databricks/file-type/evidence/2026-08-12/`](../../verification-pack/databricks/file-type/evidence/2026-08-12/evidence-record.yaml)。

| 主張 | 結果 |
|---|---|
| FILE 型が利用可能 | ✅ **Previews トグルに触れずに** `FILE EXTERNAL` 列を作成できた（channel CURRENT）。トライアル 1 環境の結果なので一般化はしない |
| `FILE MANAGED` は FileSpace を要求する | ✅ 明確なエラー: `FILE_TYPE_MISSING_FILESPACE.TABLE_PROPERTY_NOT_SET` |
| `list_files` → CTAS で `FILE EXTERNAL` | ✅ 3 行。`DESCRIBE` は型を `file external` と報告 |
| `FILE` 値は文書化された 5 フィールドのみを持つ | ✅ `uri` / `size` / `content_type` が入る。**タグやユーザーメタデータのフィールドは存在しない** — 本ドキュメントの中心的制約が実機で確認された |
| `checksum` は常に入るわけではない | ✅ `list_files` 由来では NULL、`to_file` と `FILE MANAGED` では `ETAG:…` が入る。文書化された規則どおり |
| `ai_parse_document` が `FILE` 値を受け取る | ✅ PDF で端から端まで成功: `error_status: None`、テキスト要素 1 件を正しい内容・bbox・confidence 付きで抽出 |
| `ARRAY` / `STRUCT` への FILE のネスト | ✅ |
| FILE 列での `PARTITIONED BY` | ✅ 正しく拒否: `INVALID_PARTITION_COLUMN_DATA_TYPE` |
| **Q5: FILE 列を含むテーブルは OpenSharing で共有できる** | ✅ **回答が出た。** `FILE EXTERNAL` と `FILE MANAGED` の両テーブルが共有に追加され `ENABLED` になった。受信側での読み取りは未検証 |
| **参照されないマネージドファイルの自動 GC はない** | ✅ **実測。** 共有解除後に `DROP TABLE` が成功しても、3 ファイルすべてが FileSpace に残った。手動掃除までストレージは無言で増える |
| `_object_metadata` は UC 管理ストレージで null を返す | ✅ **実測。** マネージド Volume 上では全フィールドが null。[§4.3](#43-相互排他) の相互排他はこの事実に依拠している |

当初「発見」に見えて実際は違ったサブテストが 2 件あった。共有中のため拒否された `DROP TABLE`（「ファイルが残った」は何も証明していない）と、不正な PDF を変換失敗として受け取ったもの。どちらも無効だった初回試行ごと証拠に記録している。

> **2 回目の実行で対比が揃ったので提起した**: FILE 列に対する `GROUP BY` は*受理される*。リファレンスは FILE 列をグループ化式に使えないと記載している。初回はあえて提起しなかった。3 ファイル各 1 行では、正しくグループ化されたのか偶然かを区別できないためである。2026-08-12 に提起可能になったのは、同一実行内の対比が揃ったからだ。`GROUP BY` と `SELECT DISTINCT` はどちらも受理される一方、`=` は ``The `=` does not support ordering on type "FILE"`` で拒否され、`ORDER BY` も同種のエラーになる。グループ化と DISTINCT はどちらも、エンジンが明示的に提供を拒む等価性のセマンティクスに依存している。これは行数の話ではなく型の演算子面の話である。運用上は引き続き、文書化された制約を契約と見なし `uri` でグループ化する。

### 最も重要なケース — 2026-08-12 に回答

**FSx for ONTAP S3 Access Point** パスに対する `_object_metadata.tags` は、本リポジトリが実際に必要としていた問いである。ファイルシステムと同一アカウント・同一リージョンに専用作成した非トライアルワークスペースで、同一セッション内にネイティブ S3 のコントロールを置いて実施した（[エビデンス](../../verification-pack/databricks/file-type/evidence/2026-08-12/evidence-record-tokyo.yaml)）。

| 手順 | 結果 |
|---|---|
| **ネイティブ S3** に対する `_object_metadata`（コントロール） | ✅ `tags` / `user_metadata` / `etag` / `mime_type` / `system_metadata` がすべて入り、AWS CLI で書いた内容と一致 |
| **S3 AP エイリアス**への Storage Credential → External Location → External Volume | ✅ UC 検証を有効にしたまま作成 |
| S3 AP 経由での `_object_metadata` / `list_files` / `to_file` の読み取り | ❌ 403 — ただし原因は判明した |

原因はサポートの欠如ではない。AWS はアクセスポイント経由のリクエストを**アクセスポイント ARN** に対して認可評価する一方、Unity Catalog が払い出す down-scoped セッションポリシーは**バケット形式** ARN で表現されているため、セッションの内側で拒否される。

```
is not authorized to perform: s3:ListBucket on resource:
"arn:aws:s3:<region>:<account>:accesspoint/<name>"
because no session policy allows the s3:ListBucket action
```

これは Unity Catalog が払い出した資格情報を使って **Databricks の外**でも再現し、ネットワークとコンピュート形態を原因から除外できる。それ以前に別の 7 つの説明を排除しており、再検証しないよう証拠記録に列挙している。利用者側の回避策はない。セッションポリシーは Unity Catalog が生成する。

したがって「`_object_metadata` は S3 AP 経由でオブジェクトタグを読むのか」への答えは依然として不明だが、理由が 1 段先に進んだ。読み取りがタグ読み取りのコードに到達しないのである。セッションポリシーが直る日のためにランナーはコミットしたまま残す: [`notebooks/10_file_type_object_metadata.py`](../../integrations/databricks/notebooks/10_file_type_object_metadata.py)、[test-cases.yaml](../../verification-pack/databricks/test-cases.yaml) の `DBX-FILE-*`。

| 項目 | 未解決の理由 |
|---|---|
| セッションポリシーが直った場合に `_object_metadata` が S3 AP 経由でタグを読むのか | 読み取りがそのコードに到達する前に拒否される |
| VPC オリジンの Access Point、WINDOWS アイデンティティの Access Point | INTERNET オリジン・UNIX root の Access Point 1 つで実施 |
| Q4: FileSpace に **External** Volume を使えるか | 再検証していない。別途判明: FileSpace をソースファイルのある Volume に向けると `INSERT` で `Cannot get file metadata under managed storage` になるため、専用 Volume が成立する形である |
| 共有された FILE 列の受信側での読み取り | 相手方が必要 |
| FILE 列に対する `GROUP BY` が大規模で*正しい*のか | 2 行で受理された。受理は正しさではない |
| Previews トグルが必要になる場合があるのか | 独立した 2 環境で不要だった。2 は標本にならず、これは環境差でありドキュメントの誤りではない |

### 未検証 — ONTAP マルチプロトコル挙動

| 項目 | 重要な理由 |
|---|---|
| オブジェクトタグ / ユーザーメタデータは **NFS や SMB** から見えるか。NAS プロトコル経由の書き換えを生き延びるか | 「既存 NAS 資産を取り込む」ケース全体がここに依存する。タグが file-scoped であることは前向きな材料だが十分ではない |
| タグは SnapMirror、FlexClone、Snapshot リストア、FabricPool 階層化を生き延びるか | タグが耐久性のあるガバナンスメタデータなのか、Access Point ローカルの便宜物なのかを決める |
| 受理される多バイト部分集合は ONTAP バージョンやリージョンを越えて安定か | 1 つのファイルシステムでのみ検証 |

---

## FAQ

**Q1. FILE 型は Databricks × FSx for ONTAP のガバナンスギャップを解決するか。**

しない。ただし壁の位置は動いた。`FILE EXTERNAL` は UC Volume を要求し、S3 Access Point 上の UC External Volume は作成できて読めない（BLK-001、2026-08-12 に影響範囲を訂正）。`FILE MANAGED` は動作するがデータをコピーする。FILE 型は BLK-001 を修正する価値を高めるが、修正はしない。有用な変化は、残るギャップが「サポートされていない」という漠然とした話ではなく、資格情報払い出しにおける具体的で報告可能な挙動になったことである。

**Q2. オブジェクトタグをアクセス制御に使えるか。**

使えない。`s3:PutObjectTagging` を持つ主体が書き換えられ、オブジェクトの上書きで消える。発見と粗い絞り込みに使い、強制は ONTAP ACL、Access Point ポリシー、IAM、そしてステージング済みデータについては UC 行フィルタに残す。[S3 Annotations](./s3-annotations-governance-evaluation.md) と同じ境界。

**Q3. FSx for ONTAP S3 AP のオブジェクトタグに日本語を格納できるか。**

信頼できる形ではできない。多バイト文字列の大半は `InvalidTag` で拒否され、一部は受理される（決定的だが予測不能）。タグは ASCII に限定し、日本語テキストはメタデータテーブルに置く。

**Q4. ここで S3 Annotations はタグの代替になるか。**

ならない。Annotations は FSx for ONTAP ボリュームにアタッチされた Access Point では非サポートで、ネイティブの汎用バケットのみを対象とする。[s3-annotations-governance-evaluation](./s3-annotations-governance-evaluation.md) を参照。Access Point 上で直接機能するのはタグである。

**Q5. Iceberg メタデータカタログを FILE 型へ移行すべきか。**

現時点では不要。FILE 型は Delta 限定なので S3 Tables 上の Iceberg カタログの置き換えにはならず、かつ自動ガベージコレクションのないベータである。設計が概念的に一致していることが有用な収穫。BLK-001 が解消し、FILE 型が Iceberg 対応で GA に達したら再評価する。

**Q6. FILE 型はオープンフォーマットか。**

現時点では違う。発表記事は Parquet、Delta Lake、Iceberg、Spark への対応をコミュニティと構築中と述べており、これは表明された方向性であって現在の性質ではない。仕様が着地するまでポータビリティは利用不可として扱う。

---

## 参考資料

**Databricks（Public）**
- [Introducing FILE type: a native column type for multimodal data](https://www.databricks.com/blog/introducing-file-type-native-column-type-multimodal-data)
- [FILE タイプおよび非構造化データ](https://docs.databricks.com/aws/ja/unstructured/file) ([English](https://docs.databricks.com/aws/en/unstructured/file))
- [FILE type リファレンス](https://docs.databricks.com/aws/en/sql/language-manual/data-types/file-type) · [Ingest files as the FILE type](https://docs.databricks.com/aws/en/ingestion/file) · [Tutorial: file-processing pipeline](https://docs.databricks.com/aws/en/ldp/tutorial-file-pipelines)
- [Object metadata column (`_object_metadata`)](https://docs.databricks.com/aws/en/ingestion/object-metadata-column) · [list_files](https://docs.databricks.com/aws/en/sql/language-manual/functions/list_files)
- [ABAC core concepts](https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/core-concepts) · [Apply tags to securable objects](https://docs.databricks.com/aws/en/database-objects/tags)

**AWS（Public）**
- [Access point compatibility (FSx for ONTAP)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) · [Tagging a file using an S3 access point](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/add-tag-set-ap.html)
- [S3 object tagging](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-tagging.html) · [PutObjectTagging](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObjectTagging.html)

**本リポジトリ**
- 証拠: [s3ap-object-tagging (2026-08-12)](../../verification-pack/s3ap-object-tagging/evidence/2026-08-12/evidence-record.yaml) · 再現: [`probe_s3ap_object_tagging.py`](../../shared/scripts/probe_s3ap_object_tagging.py)
- [ブロッカートラッカー](./blocker-tracker.md) — BLK-001, BLK-002, BLK-003
- [検証ランブック](./databricks-verification-runbook.md) — 自分のアカウントでの再現手順: CloudFormation、プローブスクリプト、判定、撤去順序
- [Databricks 統合 README](../../integrations/databricks/docs/ja/README.md) · [FSx for ONTAP → Databricks Unity Catalog 接続ガイド](./fsx-ontap-to-databricks-unity-catalog-guide.md)
- [Iceberg メタデータカタログ](../../integrations/iceberg-metadata-catalog/README-ja.md) · [iceberg-metadata-catalog（docs）](./iceberg-metadata-catalog.md)
- [非構造化データアクセス](./unstructured-data-access.md) · [ゼロコピーメディアガバナンス](./zero-copy-media-governance.md)
- [S3 Annotations / Metadata 評価](./s3-annotations-governance-evaluation.md) · [OpenSharing と Unity Catalog の解説](./opensharing-and-unity-catalog-explained.md)
- [DataSync → S3 ガイド](./datasync-to-s3-guide.md) — BLK-001 下での推奨暫定経路
