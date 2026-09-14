# Serving Replicated Data to Analytics Engines

**Audience**: partner and field engineers taking a "keep the data where it is" conversation to a customer that already runs a cloud data platform.
**Status**: measured 2026-09-13, ap-northeast-1, ONTAP 9.18.1P5, one file system. Read the boundaries section before quoting anything.

---

## The conversation this brief is for

A customer replicates file data into AWS, or is considering it, and wants a cloud analytics platform to query it without building a second copy and a sync pipeline. Their objection to the copy is usually not cost. It is that **governance breaks once the data is duplicated**: two sets of permissions, two lifecycles, two audit trails, and no single answer to "who can see this file".

The storage answer is that the same bytes can be presented over NFS, SMB and the S3 API at once, so the analytics engine reads the file the existing applications are already using. The question that decides whether that story survives contact with the customer's architecture is narrower: **can the engine read the replica, while replication keeps running?**

It can, for reads. That was not obvious and this repository documented the opposite until 2026-09-13.

---

## What is verified

| Claim | Status |
|---|---|
| An S3 access point serves a **live** SnapMirror destination — no break, no clone | ✅ Measured |
| Replication stays healthy while the access point is attached and being queried | ✅ Measured |
| Data from a later transfer becomes readable through the **same** access point, seconds after the transfer | ✅ Measured |
| Writes to the destination are refused (`AccessDenied`) | ✅ Measured, and correct — a replica is read-only |
| A **clone** of the destination is writable, and frozen at the cloned point in time | ✅ Measured |
| A query engine cannot tell a replica-backed access point from an ordinary one | ✅ Measured with Athena against a same-session control: identical rows, identical aggregates, latency within noise |
| Partition discovery and partition pruning work against the read-only replica | ✅ Measured |

Evidence: [S3AP-DP-ATTACH-002](../../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13-in-vpc/evidence-record.yaml) and [S3AP-DP-ATHENA-001](../../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13-athena-on-dp/evidence-record.yaml).

---

## Which shape to propose

The three routes differ in one property that decides between them: **what the consumer needs to do with the data.**

| The consumer needs to | Propose | Consequence |
|---|---|---|
| Read, always current | Access point on the **destination volume**, mounted through ONTAP | Reads only. New data appears seconds after each transfer, no rebuild |
| Write, or work from a stable snapshot | Access point on a **clone** of the destination Snapshot | Writable. Frozen at the clone point; a new clone is needed to advance it |
| Take over production service at the destination | **Break**, then mount and attach | This is failover, not analytics. Replication stops |

Two things to get right in the mechanics, because both are counter-intuitive:

- **The junction path must be set through ONTAP, not the FSx API.** `CreateVolume` refuses `JunctionPath` on a destination volume by name. `UpdateVolume` is worse: it returns HTTP 200 with the full volume object and **silently does nothing**. Automation that trusts that response proceeds on a false premise.
- **Attachment gates on the junction path, not the volume type.** Poll `DescribeVolumes` for a non-null `JunctionPath`. Do not poll for `VolumeType: RW` — after a break the FSx API keeps reporting `DP` for a minute same-region and over ten minutes cross-region, while attachment already works.

---

## What to promise about time

**Do not say "in minutes".** The ONTAP-side operation is seconds. Then the FSx control plane has to report the volume as attachable, and that took **665 s, 1011 s and 2298 s** across three runs on one file system on one day. Two of those are the same operation, so the spread is not explained by which route you pick, and it is not under the caller's control.

| Phase | Duration |
|---|--:|
| ONTAP operation (mount, or create the clone) | seconds |
| FSx control plane reports it | minutes to tens of minutes |
| Access point CREATING → AVAILABLE | ~30 s |
| First successful S3 call | seconds |

Say instead: **first-time setup is a tens-of-minutes operation; steady state after that is seconds behind each transfer.** For a live demo, build the access point in advance and demonstrate the freshness, which is the part that is genuinely fast and the part the customer actually cares about.

---

## Demo sequence that shows the real value

Provision everything except the final query before the meeting, because of the propagation delay.

1. **Show one dataset, three protocols.** The same file over NFS or SMB and through the S3 API. This is the premise everything else rests on.
2. **Query it from the analytics engine.** No copy, no pipeline.
3. **Show the replica being queried while replication runs.** Confirm the relationship is healthy in the same breath. This is the part that surprises people.
4. **Write on the source, transfer, re-query.** New rows appear. Nothing was rebuilt.
5. **Attempt a write against the replica.** It is refused. Use this rather than skip it — a customer who understands *why* it is refused trusts the rest of the model.
6. **Clone, and query the clone.** Same data, independent point in time, and writable. This is the data-scientist story: give someone a private copy in seconds without duplicating capacity.
7. **Take a Snapshot on the source, then show the clone unaffected.** Point-in-time isolation without a second dataset.

Steps 3, 4 and 6 are the ones that do not have an equivalent in a copy-based pipeline.

---

## Boundaries to state before the customer asks

Stating these early costs nothing and buys credibility. Discovering them during a PoC costs the PoC.

**Not measured, so do not present as measured**

- **The specific data platform, unless it is Athena.** Engine equivalence was proven with Athena against a control. Other engines read through the same `GetObject` and `ListObjectsV2` surface, so the risk is low — but low is not zero, and "we measured it" is a different sentence from "it should work".
- Cross-region, and second-generation file systems. All timings are intra-region on one first-generation file system.
- Scale. The engine test used three partitions and seven rows. Nothing here speaks to large listings, manifest growth, or concurrency.
- Behaviour across a break-and-resync cycle with the access point left in place.
- WINDOWS file-system identity, which is what an SMB-primary customer will need. Everything was UNIX/root. An SMB-primary environment additionally requires the SVM to be joined to Active Directory.

**Known not to work on this path**

- Event-driven ingestion. There are no S3 Event Notifications, so anything that waits for a bucket event needs a scheduled refresh instead.
- Transactional table formats writing back to the access point. Conditional writes are unavailable, so Delta commits cannot land. Iceberg works when the catalog holds the current-metadata pointer rather than the object store.
- Analytic output written back to the file system through this path. Land it on native object storage.

**Format reality, and this one derails PoCs**

Columnar and text formats read cleanly: Parquet, CSV, JSON, Avro, ORC. PDF is handled by document-AI functions on the platforms tested.

**Office and CAD formats are a different question.** The transport is format-agnostic — it moves bytes — so reading the bytes is expected to work for anything. What is unverified is whether a given platform's *parser* can be pointed at those bytes over this path. Spreadsheets in particular are frequently absent from document-parsing function support, and CAD formats have no native parser on any of these platforms. If the customer's raw layer is mostly authoring-tool output, get the format breakdown before scoping anything: which formats, what share each, and what they expect to extract. The honest position is that a spreadsheet may need a user-defined function with a library, and CAD likely needs extraction outside the data platform with only metadata catalogued in it.

---

## Discovery questions

Ordered so that an early answer can stop the rest.

1. Where does the raw data live today, and is NFS or SMB the primary protocol? SMB implies AD-joined SVMs and WINDOWS-identity access points, which is a less-travelled path here.
2. Which region, and is the data platform account in the same region?
3. What is the file-format breakdown of the raw layer, by share? Specifically, how much is spreadsheets and CAD?
4. Does the analytics consumer need to write, or only read? This picks the route.
5. What freshness does the business actually need — seconds, minutes, hours? Anything sub-minute changes the design.
6. How many files, and how are they laid out in directories? Listing was measured to 5,000 objects; beyond that is untested.
7. Is a replica involved at all, or is the analytics engine reading the primary? The replica route adds the propagation delay and read-only constraint.
8. What does the governance requirement actually attach to — files, tables, rows, or columns? Enforcement stays with storage permissions and access point policy; the platform adds table-level controls on top.
9. Which platform edition? Governance features are often edition-gated, and private connectivity usually sits in the highest tier.

---

## Traps worth knowing before you hit them

| Trap | What happens |
|---|---|
| Trusting a 200 from `UpdateVolume` | Junction path silently not set. Verify with `DescribeVolumes` |
| Polling `VolumeType` as the attachment gate | Either waits far too long or looks broken. Poll `JunctionPath` |
| Reading `aws fsx delete-volume` as "deleted" | It queues the volume. ONTAP renames it with a numeric suffix and holds it in the **volume recovery queue** while the FSx API reports it gone. A queued clone still holds its parent's Snapshot, so the parent refuses to delete and no clone is visible through the normal APIs. Fix: `volume recovery-queue show`, then `volume recovery-queue purge`. `fsxadmin` can do this — it does not need vendor support |
| Believing an empty query result about an offline volume | `snapshot show` returns nothing for an offline volume. That is not the same as having no snapshots, and it sent this project's own diagnosis in the wrong direction for two hours |
| Deleting a volume right after deleting its access point | The access point's internal object-store bucket briefly blocks it, and is not listed by the ONTAP bucket inventory. Wait and retry |
| Expecting an S3 access point on a FlexCache Cache volume | Refused by volume kind at the FSx layer, on 9.18.1P5 as on earlier releases. NetApp documents ONTAP's *native* S3 NAS bucket on Cache volumes from 9.18.1; that is a different mechanism. Use the SnapMirror destination route instead |
| Promising a replica-backed path without checking the format mix | See above |

---

## Related

- [S3 AP + FlexCache / SnapMirror design considerations](../../../docs/en/s3ap-flexcache-snapmirror-considerations.md) — §3.2 is the authoritative version of the routes above
- [Research findings](../docs/en/research.md) — SM-VAL-012 and SM-VAL-013
- [Published article corrections](../../../docs/en/published-article-corrections.md) — check before citing a published article
- [Unverified item inventory](../../../docs/en/unverified-inventory.md)
