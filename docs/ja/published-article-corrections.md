🌐 [English](../en/published-article-corrections.md) | **日本語**

# 公開記事の訂正

本シリーズの記事は外部プラットフォームで公開され、その場で編集されるため、リポジトリより古くなりうる。本ページは、公開記事に見つかった誤り・正しい記述・記事本体への反映状況を記録する追跡対象のファイルである。

**このページが必要な理由。** 検索エンジン経由で主張に到達した読者は、後の検証がそれを覆したことを知らない。検証記録にだけ訂正を書くとリポジトリは直るが記事は誤ったまま残る。本ページがあれば、記事本体からリンクできる引用可能な URL にもなる。

**使い方。** ⬜ が付いた項目は公開記事に未反映である。✅ になるまで、訂正対象の主張について記事を引用しないこと。

---

## Part 3 — Snowflake と FSx for ONTAP S3 Access Points

2026 年 5 月公開。2026-09-13 にリポジトリと突き合わせて確認。

記事の中心的な主張は妥当であり変更はない。ステージに `AWS_ACCESS_POINT_ARN` がなければ `LIST` は成功し `SELECT` は access denied で失敗する。設定すれば読み取りとガバナンスの経路が機能する。以下はいずれもそこには触れない。訂正対象は副次的な主張で、うち 3 件は記事を基に構築する人を誤らせる。

### C-01 — 推奨として提示された未検証の取り込み経路

| | |
|---|---|
| **深刻度** | 高 |
| **記事への反映** | ⬜ 未反映 |

記事の「Snowpipe Alternatives」節は **「Option 1: FPolicy → Lambda → SNS → Snowpipe REST API」** に **(Recommended)** を付け、レイテンシを「Seconds (<30s from file write to Snowflake availability)」としている。

問題は 3 つある。

1. **FPolicy はイベントソースとして一度もライブで実行していない。** 実際に検証したのはポーリング型 Lambda で、書き込みから通知まで 2.1 秒（スケジューラ待ちを除く）。実際の検知遅延はスケジュール間隔 + 約 2 秒。`<30s` という数値に裏付けとなる検証記録はない。
2. **描かれたトポロジではメッセージが届かない。** Snowflake のマネージド SQS キューを自分で subscribe することはできず、キューは Snowflake のアカウントにあるため `PendingConfirmation` のまま留まる。成立する形は pipe に `AWS_SNS_TOPIC` を設定して Snowflake 自身に subscribe させることである。
3. **この経路の公開成果物に後から 6 件の不備が見つかっており**、うち 2 件は無言のデータ損失を起こす。

**正しい記述。** スケジュール実行の取り込みには **Snowflake Task による `COPY INTO`** を使う（記事の Option 2 であり、これが Option 1 であるべき）。検証済みで、合成通知も SNS トピックポリシーも不要で、ポーリングウィンドウでは得られない exactly-once を Snowflake のロード履歴が与える。合成通知によるイベント駆動取り込みはエンドツーエンドで検証済み（通知からロード済み行まで約 0.5 秒）だが、4 条件の同時成立を要し、どこにもエラーが出ない失敗モードを持つ。`s3.bucket.name` にアクセスポイントの ARN（エイリアスではなく）が入ると、Snowpipe はメッセージを受理して破棄し、pipe は正常と報告する。この経路の監視はオブジェクト数とロード行数の比較で組む必要がある。

参照: [Snowpipe 検証結果](../../integrations/snowflake/docs/ja/snowpipe-verification-results.md)。

### C-02 — Dynamic Table による External Table 参照の不可

| | |
|---|---|
| **深刻度** | 高 |
| **記事への反映** | ⬜ 未反映 |

記事は Partner Decision Card、「AI-Ready Data Product Journey」の図、「What to Tell Stakeholders」の 3 か所で `External Table → Dynamic Table` を示している。

この経路は拒否される: `Object ref ... of type EXTERNAL_TABLE not supported in Dynamic Table definition`。

**正しい記述。** 先に標準テーブルへ取り込む必要がある（`stage → COPY INTO 標準テーブル → Dynamic Table`）。その上で `TARGET_LAG = '60 seconds'` と `REFRESH_MODE = FULL` は仕様どおり動作する。`AUTO_REFRESH` が使えないため、Dynamic Table は上流メタデータの更新に依然として Task を必要とする。

### C-03 — アンロードは未解決の論点ではなく部分書き込みの危険

| | |
|---|---|
| **深刻度** | 高 |
| **記事への反映** | ⬜ 未反映 |

記事は「PutObject (via COPY INTO unload)」を **⚠️ TBD** とし「FSx S3 AP supports PutObject ≤5GB」と注記し、後段でアンロードは「未検証」としている。

**正しい記述。** 検証済みであり、最悪の形で失敗する。`COPY INTO @stage` は拒否されない。オブジェクトは正常な状態で書き込まれ、その後 FSx for ONTAP が暗号化を `aws:fsx` と報告するため `Remote upload failed checksum validation` で文が失敗する。**呼び出し側には失敗が返るのに、完全なオブジェクトが残る。** `ENCRYPTION = (TYPE = 'AWS_SSE_S3')` を設定しても解決せず、代わりに文がハングする。アクセスポイント経由のステージにアンロードを試したことがあるなら、対象プレフィックスを列挙して孤立オブジェクトを削除すること。

サイズの注記も実務上重要な形で誤っている。上限は **2 つ**ある。単一の `PutObject`、および各 `UploadPart` は約 5 GiB が上限で、オブジェクト全体は約 50 GiB が上限。全体側の超過は全バイト転送後の `CompleteMultipartUpload` で初めて検出される。

### C-04 — サポートケース番号の公開

| | |
|---|---|
| **深刻度** | 高（衛生面） |
| **記事への反映** | ⬜ 未反映 |

記事の「Support Update (May 2026...)」の行にベンダーのサポートケース番号が含まれている。本プロジェクトの基準では、サポートケース番号を公開成果物に載せない。チケットではなく topic で参照する。

**正しい記述。** 識別子を削除して内容を残す（「Snowflake サポートに確認、2026 年 5 月」）。

### C-05 — Expected から Verified に移った形式・機能

| | |
|---|---|
| **深刻度** | 低、かつ読者にとって有利な方向 |
| **記事への反映** | ⬜ 未反映 |

記事が「✅ Expected」「⚠️ TBD」としている項目のうち、その後測定されたもの。

| 記事の記述 | 現在 |
|---|---|
| JSON・Avro・ORC の読み取り —「Expected」 | 2026-08-06 に検証済み |
| Snowpark `SnowflakeFile.open` —「未検証」 | 検証済み |
| Iceberg Table の読み取り —「TBD」 | External Volume 上の Managed Iceberg Table への `COPY INTO` をエンドツーエンドで検証済み。宛先バケットに真の Iceberg レイアウトを確認 |
| ListObjectsV2 レイテンシ（シリーズの別記事でネイティブ S3 比 30〜80 倍と記載） | 5,000 オブジェクトまでで 1.3〜1.4 倍に再測定。以前の数値は再現せず撤回。5,000 超は未測定 |

### C-06 — Cortex 関数の件数の不整合

| | |
|---|---|
| **深刻度** | 低 |
| **記事への反映** | ⬜ 未反映 |

記事には「8 out of 10」と「7 out of 9」が併存し、比較表では別に「6 Cortex functions direct」とある。分母を 1 つに決め、どの関数を数えているかを明記すること。

### 訂正ではない事項: SnapMirror

記事は SnapMirror に触れていないため、稼働中の SnapMirror 宛先をアクセスポイント経由で提供できるという 2026-09-13 の発見は記事の変更を要しない。訂正ではなく新規の内容であり、今後のパートか[設計考慮事項](./s3ap-flexcache-snapmirror-considerations.md#32-宛先側での-s3-ap-アタッチ)に属する。

---

## 関連

- [ブロッカートラッカー](./blocker-tracker.md) — BLK-003、BLK-006、BLK-009
- [未検証項目インベントリ](./unverified-inventory.md)
- [Snowflake 統合 README](../../integrations/snowflake/docs/ja/README.md) — 現在の検証ステータス
