🌐 **English** | [日本語](../ja/opensharing-integration-analysis.md)

> 📖 **FAQ**: For questions like "Can OpenSharing connect directly to FSx for ONTAP?" see the [UC Connection Guide](./fsx-ontap-to-databricks-unity-catalog-guide.md) FAQ section (Q1, Q6).

# OpenSharing × FSx for ONTAP: Integration Analysis

> **Status**: Protocol-level analysis from the public OpenSharing specification + independent verification of STS credential vending against FSx for ONTAP S3 Access Points (2026-06-17). Native vendor implementation (Storage Ecosystem partners) not yet validated (expected end of year). Technical questions posted to the Databricks Community Forum ([post #1](https://community.databricks.com/t5/data-engineering/unity-catalog-external-location-with-amazon-s3-access-points/m-p/160296#M54880), [post #2](https://community.databricks.com/t5/data-engineering/opensharing-vended-sts-credentials-on-s3-access-points-verified/m-p/160298#M54881)).

> **Evidence tier**: Tagged per claim — **Public** (verifiable from public sources), **Project-context** (reproducible in this repository), **Archetype** (generic role-based reasoning).

## What Changed (Public Evidence)

On 2026-06-10, Databricks announced **OpenSharing** — the evolution of the Delta Sharing protocol, now hosted by the Linux Foundation — and a **Storage Ecosystem** of partners that connect on-premises and hybrid storage to Databricks without data movement.

| Fact | Source |
|------|--------|
| OpenSharing is the first open protocol covering AI assets (agent skills, AI models, unstructured data) in addition to structured data | [Databricks Press Release](https://www.databricks.com/company/newsroom/press-releases/databricks-announces-opensharing) |
| Adds support for Apache Iceberg IRC clients, extending reach beyond prior Delta Sharing recipients | Same |
| Storage Ecosystem connects hybrid/on-prem storage via OpenSharing using a zero-copy architecture into Unity Catalog | [Databricks Blog](https://www.databricks.com/blog/announcing-databricks-storage-ecosystem-governing-enterprise-data-estate-wherever-it-lives) |
| GA / preview launch partners include object-storage and hybrid-storage vendors; additional enterprise storage partners are listed as "coming soon" by end of year | Same |
| Volumes APIs for unstructured data are explicitly previewed as the next step | Same |
| Partner Well-Architected Framework documents the integration blueprint, including two paths to serve Iceberg via the protocol (Delta Shallow Clone or Apache XTable metadata translation) | [Partner Framework](https://databrickslabs.github.io/partner-architecture/data-collaboration/software-defined-storage) |
| **DAIS 2026 keynote (2026-06-16)**: SecureConnect enables secure cross-cloud connectivity with zero-copy data sharing; Global Distribution adds automated replication across clouds and regions | [What's new with Unity Catalog](https://www.databricks.com/blog/whats-new-unity-catalog-data-ai-summit-2026) |
| **DAIS 2026 keynote (2026-06-16)**: Iceberg v3 GA, Managed Iceberg GA, Foreign Iceberg GA, new federation connectors, and cross-engine ABAC are now available | Same |
| **DAIS 2026 keynote (2026-06-16)**: Storage Ecosystem partner status clarified — MinIO (GA), Everpure (Private Preview), Qumulo and VAST Data (Private Preview Soon); **NetApp, Cohesity, Commvault, and Nutanix confirmed coming by end of year**. SecureConnect is a Databricks-managed proxy (one-time config, no per-recipient firewall changes) — now in **Public Preview** with optional **NCC Private Link** connectivity between the proxy and provider storage, mutual TLS, and cross-region/cross-cloud support; serverless recipients require zero configuration ([SecureConnect blog](https://www.databricks.com/blog/introducing-opensharing-secureconnect)). Providers can also share from external catalogs (AWS Glue, Hive Metastore, Snowflake Horizon) without replication. | [OpenSharing blog](https://www.databricks.com/blog/introducing-opensharing-next-evolution-delta-sharing-agentic-era) |
| **DAIS 2026 (2026-06-16)**: **Share to any Iceberg client — GA**. Databricks users can share data to any external Iceberg-compatible client (Snowflake, Trino, Spark, Flink) with full transactional consistency. OIDC now supported for sharing to Iceberg clients | [OpenSharing and Marketplace blog](https://www.databricks.com/blog/announcing-new-opensharing-and-marketplace-capabilities-ai-era) |
| **DAIS 2026 (2026-06-16)**: **LTAP (Lake Transactional/Analytical Processing)** announced — architecture unifying OLTP and OLAP on a single lakehouse storage layer. Lakebase serves as the transactional engine; operational data is immediately queryable in the lake without pipelines | [LTAP press release](https://www.databricks.com/company/newsroom/press-releases/databricks-launches-ltap-first-lake-transactionalanalytical) |

> FSx for ONTAP is an AWS-managed enterprise storage service with multiprotocol access (NFS/SMB/iSCSI/S3) and data protection features (Snapshot, FlexClone, SnapMirror, FabricPool). The analysis below evaluates how the OpenSharing pattern could complement the existing S3 Access Point integration patterns in this repository.

## Why This Matters for This Repository

The current compatibility matrix lists the Databricks + FSx for ONTAP S3 Access Point path as **blocked** (the platform's session policy does not recognize the S3 AP ARN format). OpenSharing is relevant because its sharing model is based on short-lived presigned URLs, where the sharing server handles only **metadata and access control** while data transfer happens directly between client and storage.

**Architecture-level observation**: This separation could allow the S3 AP ARN recognition issue to be bypassed at the architecture level, because the consuming platform interacts with the sharing protocol rather than parsing the storage ARN directly. This is a hypothesis to be validated, not a confirmed result.

## Technical Note: Presigned URL Behavior on FSx for ONTAP

Because the OpenSharing model relies on short-lived presigned URLs or STS credentials, the presigned-URL behavior of FSx for ONTAP is central to this analysis. Two questions must be kept separate:

1. **Whether the documentation lists Presign as supported** (the documented stance), and
2. **Whether a client-generated presigned URL actually works** against the endpoint (empirical behavior).

A presigned URL is produced purely by client-side SigV4 query-string signing — no server call is needed to create it. The real question is whether the endpoint honors the signed GET request.

| Endpoint | Documented `Presign` | Observed behavior |
|----------|:--------------------:|-------------------|
| FSx for ONTAP S3 Access Point | Listed as not supported ([AWS docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)) | In this repository's prior testing, a client-generated SigV4 presigned URL returned HTTP 200 against the S3 Access Point endpoint |
| ONTAP S3 (native object server) | Supported on ONTAP 9.11+ (SigV4; v2 presign not supported) | Documented capability |

**Takeaway**: "Whether the S3 Access Point documents Presign support" and "whether a client's presigned URL works against it" are different questions. The documented stance alone should not be used to exclude a backend. The native ONTAP S3 object server documents presigned-URL support (SigV4) and is a dependable option; the S3 Access Point path showed working client-generated presigned URLs in prior testing and warrants empirical validation per use case. Use SigV4 (v2 presign is not supported on ONTAP S3).

**Additional path — temporary credentials**: The OpenSharing protocol's credential vending can issue *either* presigned URLs *or* temporary, scoped cloud credentials (e.g. AWS STS), depending on asset type and access mode ([OpenSharing spec](https://github.com/OpenSharing-IO/OpenSharing)). With the temporary-credentials mode, the recipient reads via a standard `GetObject` call rather than a presigned URL. Because `GetObject` is supported on FSx for ONTAP S3 Access Points, this mode sidesteps the presign question entirely and is a strong candidate for the access path.

**Governance granularity note**: Credential vending (presigned URL or temporary credentials) grants access at the storage-location (prefix) level — it does not carry row- or column-level policies. Where fine-grained, cross-engine governance (row filters, column masks) is required, an Iceberg REST catalog with server-side scan planning is the appropriate layer. Treat table-level zero-copy delivery and fine-grained governance as distinct mechanisms, and scope any vended credentials to the specific table location with least privilege.

> This note describes FSx for ONTAP / ONTAP capabilities only. Behavior should be re-validated in your own environment and ONTAP version.

## Protocol Surface (from the Public Specification)

The OpenSharing specification is published openly ([OpenSharing-IO/OpenSharing](https://github.com/OpenSharing-IO/OpenSharing), Apache 2.0). The following protocol details are **read directly from the public spec** (evidence tier: **Public**) and shape how an FSx for ONTAP-backed integration would be built. They are protocol facts, not yet independently validated against an FSx for ONTAP backend.

**Asset hierarchy**: `Share → Schema → { Table, Volume, AgentSkill, Model, Agent (proposal), Glossary (proposal) }`. A single bearer token authorizes access to a whole share; the share is the access-control unit.

**Recipient profile**: A JSON profile carries `endpoint` (Delta tables), a separate `icebergEndpoint` (Iceberg tables), a `bearerToken`, and an optional `expirationTime`. The separate Iceberg endpoint is the key to cross-engine reach.

**Tables — two access modes**: Each table advertises `accessModes` of `url`, `dir`, or both, and a `format` of `delta` and/or `iceberg`:

| Access mode | Mechanism | FSx for ONTAP implication |
|-------------|-----------|---------------------------|
| `url` | Presigned URL (client-side query API) | Works on native ONTAP S3 (SigV4); S3 Access Point showed working client-generated URLs in prior testing |
| `dir` | Directory access via temporary STS credentials | Recipient reads with standard `GetObject` — supported on S3 Access Points, sidesteps the presign question |

**Iceberg via standard REST Catalog**: The spec implements the standard [Iceberg REST Catalog API](https://github.com/apache/iceberg/blob/main/open-api/rest-catalog-open-api.yaml) — `getConfig`, `listNamespaces`, `loadNamespaceMetadata`, `listTables`, `loadTable`, `reportMetrics`. **Implication**: standard Iceberg REST clients (PyIceberg, Spark Iceberg, Athena) can consume shared tables directly. This reduces the need for an Apache XTable / shallow-clone bridge to a fallback rather than a requirement.

**Credential vending**: For AWS, the server vends standard STS temporary credentials (`accessKeyId` + `secretAccessKey` + `sessionToken`) with an `expirationTime`. Azure (SAS), GCP (OAuth), and Cloudflare R2 are also defined. The AWS path aligns with the `GetObject` access already validated in this repository's prior work.

**Volumes (unstructured) — proposal stage**: The `Volume` asset shares a directory `storageLocation` (e.g. `s3://bucket/path/`) and vends **STS credentials only** (no presigned-URL mode). This is the natural connection point for FSx for ONTAP unstructured payloads (images, video, documents) and links to the metadata-catalog work in this repository. The current connectors support tables first; volumes are in progress.

> These are specification-level facts. Whether each behaves as specified against an FSx for ONTAP backend (S3 Access Point or native ONTAP S3) is what the phased validation activity will establish.

## Validated: STS Credential Vending on FSx for ONTAP S3 Access Point (2026-06-17)

The following has been **independently verified** against a live FSx for ONTAP S3 Access Point (evidence tier: **Project-context**).

### What works (verified)

| Test | Result | Implication |
|------|--------|-------------|
| Generate scoped STS credentials (prefix-limited) | ✅ | OpenSharing server can vend temporary credentials scoped to a specific table path |
| `ListObjects` with scoped STS on allowed prefix | ✅ (5 objects) | Recipient can discover files in the shared table |
| `GetObject` with scoped STS (Parquet, CSV, JSON, PNG, TXT, Delta log, Iceberg metadata) | ✅ All formats | Access mechanism is format-agnostic; works for Table and Volume asset types |
| `GetObject` on denied prefix with same credentials | ✅ AccessDenied | Least-privilege enforcement works; credentials cannot escape their scope |
| Credential expiration (15 min) | ✅ | Time-bounded access as specified by the protocol |

### What this means for OpenSharing

The OpenSharing protocol's `dir` access mode (where the server vends temporary AWS credentials instead of presigned URLs) **works on FSx for ONTAP S3 Access Points**. A recipient with vended credentials can:
- List and read any file within the scoped prefix
- Read Parquet data files (for Delta/Iceberg Table assets)
- Read unstructured files (for Volume assets: images, PDFs, video)
- Cannot access data outside the vended scope

### What this does NOT solve (important distinction)

| Limitation | Remains | Why |
|-----------|---------|-----|
| **Delta/Iceberg transactional writes to FSx for ONTAP S3 AP** | ❌ Still blocked | Conditional writes (`If-None-Match`) return 501; atomic rename not supported. This is a product-level FSx for ONTAP S3 AP limitation, unrelated to OpenSharing. |
| **Foreign Iceberg reading S3 Tables from Databricks** | ❌ Still blocked | External Location validation rejects S3 Tables internal buckets (HeadBucket fails). Unrelated to this credential vending test. |
| **Databricks UC read from FSx for ONTAP S3 AP** | ❌ Still blocked | The `access_point` field on a UC External Location produced partial reads in a 2026-05-24 test, but Databricks Support confirmed on 2026-05-26 that the field is not GA and S3 AP is not a supported UC target — the partial success is "a side effect of incomplete internal handling, not a supported code path" ([details](../../integrations/databricks/README.md#where-the-denial-originates)). Today's STS test validates the *OpenSharing recipient* path, which is a separate route. |

### Architectural clarity

```
FSx for ONTAP (source of truth for raw data: images, CSV, sensor logs, documents)
    │
    │ READ path (verified ✅):
    │   • OpenSharing STS credential vending (any recipient, June 2026) ← NEW
    │   • Direct IAM (Athena, Glue, EMR — existing)
    │
    │ READ path (NOT supported ❌):
    │   • UC External Location on S3 AP (not GA; Databricks Support, 2026-05-26)
    │
    │ WRITE path (NOT on FSx for ONTAP S3 AP):
    │   • Delta/Iceberg managed tables live on standard S3 or S3 Tables
    │   • FSx for ONTAP S3 AP cannot host transactional table metadata
    │
    ▼
Analytics engines read raw data from FSx, write governed tables elsewhere
```

**FSx for ONTAP is the data source; table format management happens on separate storage.** OpenSharing enables governed, zero-copy read distribution of that source data to any recipient.

### Reproduction script

A self-contained verification script is provided for anyone to reproduce these results against their own FSx for ONTAP S3 Access Point:

```bash
cd integrations/iceberg-metadata-catalog/scripts/
python verify-opensharing-credential-vending.py \
  --ap-alias <your-ap-alias-ext-s3alias> \
  --allowed-prefix media/ \
  --denied-prefix benchmark/
```

The script tests both modes (STS + presigned URL), outputs pass/fail per format, and saves a JSON evidence file. Prerequisites: `boto3`, `requests`, AWS credentials with `s3:GetObject`, `s3:ListBucket`, `sts:GetFederationToken`.

### Presigned URL mode (supplementary finding)

In addition to the STS mode (primary), presigned URLs also work empirically:

| Condition | Result |
|-----------|--------|
| Regional endpoint (`s3.REGION.amazonaws.com`) + SigV4 | ✅ HTTP 200 for all formats |
| Global endpoint (`s3.amazonaws.com`) | ❌ HTTP 301 (redirect, signature mismatch) |
| AWS documentation stance | "Not supported" |

**Recommendation**: Use STS credential vending as the primary mode (officially supported, prefix-scoped). Presigned URLs work today but lack an official support guarantee and require the regional endpoint workaround.

> **Note on ONTAP S3 native**: The presigned URL test above was performed against FSx for ONTAP **S3 Access Points**. ONTAP S3 native (direct object server, 9.11+) documents presigned URL support (SigV4) officially, but has **not been independently verified** in this repository. The STS credential vending mode applies only to the S3 Access Point path (AWS-managed, supports AWS STS).

## Scope and Principles

- **Complement, not replacement**: The OpenSharing path complements — it does not replace — the existing AWS-native S3 Access Point patterns (Athena, Glue, EMR, Redshift, SageMaker) already documented in this repository.
- **Source of truth stays on enterprise storage**: The authoritative data remains the Iceberg/Parquet on FSx for ONTAP. Presigned-URL references and any bridged metadata are derived artifacts.
- **Share a curated subset, not everything**: The goal is to expose curated, AI-ready data products, not to share entire volumes indiscriminately. Deny-by-default for data with unknown permissions.
- **Single governance boundary**: Designate one catalog as the governance boundary; avoid distributing policy across multiple catalogs.
- **Interim until native**: Independent validation in this repository uses the open-source OpenSharing reference implementation (protocol-compliant, same lineage as Delta Sharing) ahead of any native vendor implementation.

## Design Considerations

**Architecture**: The presigned-URL sharing model decouples the consuming platform from storage-specific ARN formats, preserving the zero-copy principle. However, an OpenSharing server becomes a Tier-1 dependency with catalog-equivalent blast radius — availability, scaling, and P99 latency design are required.

**Manufacturing / edge data**: Sensor data, quality-inspection images, and engineering documents on enterprise storage become directly consumable by ML/AI workloads. The previewed Volumes APIs extend this to unstructured payloads. Edge-specific concerns (time sync, event ordering, deduplication) remain outside the sharing protocol; metadata-to-payload linkage stays a custom design responsibility.

**Governance**: Shared data can become subject to centralized governance (lineage, access control, audit) without copying. The Iceberg REST **scan planning** capability (Iceberg 1.11) lets a catalog apply row filters and column masks at plan time, enabling cross-engine attribute-based access control. OpenSharing's Iceberg IRC support benefits from this. ([Catalog landscape analysis](https://amdatalakehouse.substack.com/p/the-state-of-apache-iceberg-catalogs)). Must validate: write-back support, column-level security / row filter / tag travel to shared tables.

**Enterprise storage integration**: An OpenSharing endpoint would be a new data-exposure surface alongside NFS/SMB/iSCSI/S3, turning enterprise file storage from a silo into a governed, interoperable node. Technical characteristics to validate with FSx for ONTAP: point-in-time recovery (Snapshot) complementing table time travel, instant logical copies (FlexClone) for shared sandboxes, cross-region replication (SnapMirror) for DR-capable endpoints, and multiprotocol so the same data serves file workloads and AI simultaneously. Open question: whether a native implementation sits on ONTAP S3, S3 Access Points, or an independent data path.

**Catalog landscape**: As of mid-2026, the open table format question is largely settled in favor of Apache Iceberg; the technical focus has moved to the **catalog layer**, which is becoming the AI control plane. ([Source](https://amdatalakehouse.substack.com/p/the-state-of-apache-iceberg-catalogs)). Key distinction: OpenSharing is a *sharing* protocol; Iceberg REST is a *catalog* protocol — they operate at different layers and are complementary, not mutually exclusive. Governance policy is not portable across catalogs today; the pragmatic answer is a **single catalog as governance boundary**.

**Storage ecosystem pattern**: Launch-partner storage vendors share a common theme — connect data that cannot move (sovereignty, gravity, cost) to cloud AI without migration. Implementation: the storage partner stands up an OpenSharing endpoint, connects it to the catalog, and serverless compute queries in place.

## Consensus

1. OpenSharing is a strong candidate path to **bypass the current UC External Location limitation** (to be validated).
2. A **multi-surface strategy with Iceberg as the common data plane** — rather than betting on a single sharing protocol — best serves vendor neutrality and cross-engine coexistence.
3. There is value in **validating with an OSS OpenSharing server backed by FSx for ONTAP first**, ahead of any native vendor implementation.
4. **Governance should be consolidated to a single boundary**; avoid distributing policy across multiple catalogs.
5. The existing unstructured-data metadata catalog work connects strongly to the previewed **Volumes APIs** direction.

## Technical Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| D-1 | Two-track parallel PoC: (1) OpenSharing path via OSS server backed by FSx for ONTAP; (2) Iceberg IRC path via a neutral catalog | Covers both Databricks-optimized and engine-neutral consumption |
| D-2 | Single catalog as governance boundary; evaluate both a platform-native catalog and a neutral catalog for cross-engine ABAC travel | Policy portability across catalogs is unsolved industry-wide |
| D-3 | Publish as a forward-looking analysis and a future blog installment, connected to the unstructured-data catalog work | Maintains series continuity; AWS Community perspective |
| D-4 | Track native vendor implementation; do not wait for it; do not predict GA timing beyond public statements | Evidence discipline |

## Risk Register (Summary)

| Risk | Severity | Mitigation |
|------|----------|------------|
| Sharing server as a new Tier-1 single point of failure | High | HA design, latency monitoring, consider managed options |
| Presigned URL reuse / unauthorized access | High | Short-lived URLs, prefer remote signing, deny-by-default |
| Iceberg/Delta bridging operational complexity | Medium | Metadata-only translation, idempotent design, dead-letter on failure |
| Governance policy fragmented across catalogs | High | Enforce a single governance boundary |
| Permission changes / deletes not reflected in shared metadata | High | Re-sync or event-driven invalidation, deny-by-default |

## Proposed Architecture Pattern

```
Pattern E: OpenSharing (Zero-Copy Governed Access) — analysis stage

FSx for ONTAP → OpenSharing Server (sharing + access control)
                      → Catalog (governance boundary)
                      → Lakehouse Serverless Compute (in-place query)
                      → Iceberg IRC clients (cross-engine)
```

## Open Questions

Resolved from the public specification (still pending validation against FSx for ONTAP):
- **Iceberg vs Delta delivery** — both are specified; Iceberg uses a standard REST Catalog endpoint, Delta uses the OpenSharing endpoint.
- **Access mechanism** — tables support `url` (presigned) and/or `dir` (STS credentials); volumes use STS credentials only.
- **Read vs write** — the specified APIs are read-oriented (list / get / loadTable / temporary-credentials); no explicit write-back endpoint is defined, so write-back remains to be tested empirically.

Still open:
- Does a native implementation sit on ONTAP S3, S3 Access Points, or an independent path?
- Relative timing of AWS-managed vs on-premises availability?
- Do column/row governance policies travel to shared tables (depends on Iceberg REST scan planning)?
- How will NetApp's committed native integration (end of 2026) interact with FSx for ONTAP vs on-premises ONTAP?

## Next Activity

A phased validation activity has been defined (read → Iceberg IRC → governance travel → write-back → unstructured design → publication). See the repository's Supported Integrations table and the upcoming blog series for status updates.

### Reference Server PoC (2026-06-29)

A lightweight OSS reference server implementing the OpenSharing Volumes API has been developed and validated against the FSx for ONTAP S3 AP in this environment:

- **Location**: [`integrations/opensharing-server/`](../../integrations/opensharing-server/)
- **Scope**: Volumes API (credential vending for unstructured data)
- **Tests**: 12/12 PASS (API contract + E2E against FSx for ONTAP S3 AP)
- **Key finding**: S3 AP ARN format requires specific IAM policy patterns (`arn:aws:s3:*:*:accesspoint/*/object/<prefix>*`) — standard bucket ARN patterns fail

This implementation documents the S3 Access Point-specific IAM policy patterns discovered during validation and may be useful as a reference for other implementors targeting S3-compatible backends.

## Path to UC Native Consumption

The ultimate goal is **zero-copy, governed access**: FSx for ONTAP data consumed directly in Unity Catalog with full governance (lineage, tags, ABAC, column masks, row filters) — without staging to a separate S3 bucket.

### Current state (July 2026)

| Layer | Status | Evidence |
|-------|--------|----------|
| Protocol specification (Volumes) | ✅ Complete | [OpenSharing-IO/OpenSharing](https://github.com/OpenSharing-IO/OpenSharing) `spec/protocols/VOLUMES.md` |
| Provider server (FSx for ONTAP S3 AP) | ✅ Validated | This repository: 11 formats, prefix isolation, credential expiry |
| UC Recipient — Tables (D2D) | ✅ GA | Databricks documentation |
| UC Recipient — Volumes (D2D) | ✅ GA | `ALTER SHARE ADD VOLUME` supported |
| UC Recipient — non-Databricks provider (Tables) | ⚠️ Partial | Storage Ecosystem MinIO GA; open-provider Tables via profile file |
| UC Recipient — non-Databricks provider (Volumes) | ❌ Not available | No documentation; not validated for any partner |

### Why notebook access is not sufficient

UC governance applies exclusively to UC-registered objects. Reading data via `boto3` in a notebook with vended credentials is **outside UC governance scope** — no ABAC, no tag-based access control, no audit lineage. For any workload requiring governance, data must be consumed as a UC-registered asset.

### The critical gap

```
What exists:                               What's missing:
┌─────────────────────────┐               ┌────────────────────────────────────┐
│ CREATE PROVIDER p1;     │               │ UC accepts credential profile from │
│ SHOW SHARES IN PROVIDER │  ← gap →      │ a non-Databricks OpenSharing       │
│   p1;                   │               │ server for Volumes                 │
│ CREATE CATALOG c1 USING │               │                                    │
│   SHARE p1.factory;     │               │ UC surfaces shared Volumes as      │
│ SELECT * FROM c1...;    │               │ governed Foreign Volumes            │
└─────────────────────────┘               └────────────────────────────────────┘
  SQL exists in Databricks                   Platform behavior not available
```

### Validation plan

| Step | Action | Expected outcome |
|------|--------|-----------------|
| 1 | Generate OpenSharing credential profile (`config.share` JSON) from reference server | Profile file with endpoint + bearer token |
| 2 | Attempt `CREATE PROVIDER` in Databricks workspace using the profile | Either success (path is open) or specific error (path is restricted) |
| 3a | If success: `SHOW SHARES IN PROVIDER` → `CREATE CATALOG USING SHARE` | Volumes visible as UC objects with governance |
| 3b | If error: document the error, file feature request with Databricks | Evidence for product prioritization |

### Acceleration levers

| Lever | Rationale |
|-------|-----------|
| **Technical proof** (this repo) | Protocol-compliant server works E2E. "Only UC recipient is missing" is a clear, scoped ask. |
| **NetApp partner channel** | Storage Ecosystem commitment means NetApp has a direct line to Databricks product. FSx for ONTAP should be included. |
| **AWS SA feedback** | FSx for ONTAP + Databricks is a common customer pattern on AWS. Feature request via AWS channels adds signal. |
| **Public blog series** | Demonstrating the protocol-compliant implementation publicly (with working code) creates community visibility and discoverability. |

### Decision: proceed with credential profile generation

Based on this analysis, the next concrete action is to implement credential profile generation in the reference server and attempt `CREATE PROVIDER` in a Databricks workspace. This will either:
- Unlock UC native consumption immediately (if the path is open), or
- Produce a specific, documented dependency for the feature request

