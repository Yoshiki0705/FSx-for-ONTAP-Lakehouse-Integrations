# ListObjectsV2 Latency Evidence

Two evidence records compare a fully paginated `ListObjectsV2` listing on an Amazon FSx for NetApp ONTAP S3 Access Point with the same listing on a native Amazon S3 bucket. Each record measures both targets from the same client in the same run, minutes apart, in `ap-northeast-1`. The directory is part of the [Verification Pack](../README.md).

This README is for readers who found a listing-latency figure and want to see what stands behind it, and for authors about to cite one. Evidence tier: documented, as defined in the Adoption Playbook's [evidence policy](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/en/evidence-policy.md). This is design guidance for people using the two records: it restates what they contain and adds no measurement. Both records are sample runs from one environment, and neither is a production estimate or a service limit.

## The Two Records

The records are called `-001` and `-002` below. A reference such as OBS-2 is the `id` of an entry under `observations` in the YAML.

| Record | Date | Object counts | Read first |
|---|---|---|---|
| [`BENCH-S3AP-LIST-001`](evidence/2026-08-05/benchmark-result.yaml) | 2026-08-05 | Flat layout: 10, 100, 1,000 and 5,000. Nested layout: 1,000 and 5,000 | `environment`, `observations`, `conclusion.caveats` |
| [`BENCH-S3AP-LIST-002`](evidence/2026-09-14-scale/benchmark-result.yaml) | 2026-09-14 | Flat layout only: 10,000 and 20,000 | `environment`, `observations` OBS-2, OBS-4 and OBS-5, `conclusion.what_to_publish`, `conclusion.caveats` |

`-001` re-measures a figure that earlier documentation in this repository had repeated without an evidence record: that listing on an access point is "30-80x slower than native S3 for small directories". Its recorded verdict is `NOT REPRODUCED`. `-002` runs the same script from the same client location at larger counts. It closes, up to 20,000 objects, the caveat that counts above 5,000 were untested, and it found no degradation up to that count.

Both runs use [`shared/scripts/benchmark_list_objects.py`](../../shared/scripts/benchmark_list_objects.py): five recorded trials per count after one discarded warm-up call, median reported, client retries disabled. The raw trial data sits beside each YAML: [`raw-flat.json`](evidence/2026-08-05/raw-flat.json) and [`raw-nested.json`](evidence/2026-08-05/raw-nested.json) for `-001`, [`raw-scale.json`](evidence/2026-09-14-scale/raw-scale.json) for `-002`.

## Read Before Quoting

The two `environment` blocks do not record the same keys.

| Key under `environment` | `-001` | `-002` |
|---|---|---|
| `ontap_version` | not recorded | `NetApp Release 9.18.1P5` |
| `ap_origin` | not recorded | `INTERNET` |
| `fsx_throughput_mbps`, `fsx_storage_gb`, `fsx_disk_iops` | recorded | not recorded |

Both record `SINGLE_AZ_1` and a client on a local workstation over the public internet, outside the VPC. A statement about the ONTAP version or the access point's origin type can rest on `-002` only. A statement about throughput capacity, storage capacity or disk IOPS can rest on `-001` only.

- **Do not quote a single ratio as general behaviour.** `-002` `conclusion.what_to_publish` says not to present the 1.3-1.4x range as a general figure, and OBS-2 gives the reason: the spread of the native S3 trials alone is wide enough that a precise ratio overstates what was measured. The same field lists what can be said instead. The 30-80x figure does not reproduce anywhere from 10 to 20,000 objects, and listing 20,000 objects takes seconds in absolute terms (OBS-4, measured from outside the VPC).
- Compare the access point with native S3 only inside one run. `-002` OBS-5 says absolute times are not comparable between the two runs, which were taken on different days over the public internet, and gives an example in which the difference exceeds what the object count explains.
- Both runs measured from outside the VPC, so every figure includes the public-internet round trip (`-001` OBS-4). The records do not show what a client inside the VPC would see.
- Each record covers one file system, one storage virtual machine (SVM), one volume, one region and one day (`conclusion.caveats` in both). Every object is 9 bytes, which `-001` treats as irrelevant to listing cost because the call returns metadata only (`methodology.object_body_rationale`).
- `slowdown_factor` is the access point's median divided by the native S3 median for the same object count. A value below 1 means the access point's median was the lower of the two.

> **Request-count note**: At 1,000 objects and above, the access point needed more `ListObjectsV2` calls than native S3 to return the same keys at `MaxKeys=1000` (OBS-3 in each record). Wall time stayed comparable, so the records treat this as an efficiency detail. A per-request cost estimate, or a client that caps pagination, should not assume the same call count for both targets.

## What the Records Do Not Cover

- Object counts above 20,000.
- The nested layout above 5,000 objects. `-002` ran the flat layout only.
- Tail latency. Each count has five trials and no percentile above the median is reported. The YAML gives the median, minimum and maximum per count, and the raw JSON also holds the mean, the standard deviation and all five durations.
- Other deployment types, other throughput capacities, and ONTAP versions other than the one `-002` records. Both records use `SINGLE_AZ_1`.
- A client inside the VPC, and an access point with VPC origin. `-002` records Internet origin, and `-001` does not record the origin.
- Concurrent clients. Both runs were single-threaded.

## Reproduce

The `conclusion.reproduce` field of each record holds the command line, with placeholders for the access point ARN and the comparison bucket. The `-001` command shows the flat run only. The nested run of `-001` used `--layout nested` with counts 1,000 and 5,000 and fan-out 10, as `raw-nested.json` records. The script creates its benchmark objects under a prefix on both targets and removes them when run with `--teardown`, so point it at a file system and a bucket meant for testing.

## Cited From

| Document | Linked record |
|---|---|
| Blocker tracker, BLK-006 ([EN](../../docs/en/blocker-tracker.md), [JA](../../docs/ja/blocker-tracker.md)) | `-001` and `-002` |
| Compatibility matrix ([EN](../../docs/en/compatibility-matrix.md), [JA](../../docs/ja/compatibility-matrix.md)) | `-001` |
| Unverified inventory ([EN](../../docs/en/unverified-inventory.md), [JA](../../docs/ja/unverified-inventory.md)) | `-001` |
| Published article corrections ([EN](../../docs/en/published-article-corrections.md), [JA](../../docs/ja/published-article-corrections.md)) | `-002` |
| Snowflake integration README ([EN](../../integrations/snowflake/README.md)) | `-001` |
| Snowpipe verification results ([EN](../../integrations/snowflake/docs/en/snowpipe-verification-results.md), [JA](../../integrations/snowflake/docs/ja/snowpipe-verification-results.md)) | `-001` |

This table is maintained by hand. To regenerate the list of documents, run `git grep -l "s3ap-list-latency" -- "*.md"` from the repository root.

## Reader Path

A figure taken from this directory rests on the two records above. The Adoption Playbook's performance pages help a reader place those records among results for other protocols and topics. This directory does not depend on either page.

| Playbook page | What it gives a reader of these records |
|---|---|
| Performance hub ([EN](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/en/domains/performance/README.md), [JA](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/domains/performance/README.md)) | The performance domain's reading order, which starts from isolating what a figure measured, and its notes on throughput, latency and caching |
| Performance evidence map ([EN](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/en/reference/performance-evidence-map.md), [JA](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/performance-evidence-map.md)) | An index of which document holds each result, by protocol and topic. It carries no performance values, and it links the `2026-09-14-scale` record as the place for S3 Access Points `ListObjectsV2` results |
