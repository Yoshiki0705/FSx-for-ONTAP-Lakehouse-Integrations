🌐 **English** | [日本語](../ja/repository-map.md)

# Which repository answers your question

> This repository covers one slice of Amazon FSx for NetApp ONTAP: reaching file data from
> analytics and lakehouse engines through S3 Access Points, without copying it. **It is not a
> general FSx for ONTAP guide, and it does not try to be.** Nine sibling repositories own the
> adjacent ground. This page says which one to open, so nobody re-derives an answer that
> already exists.

## What this repository owns

Measured behaviour of analytics and lakehouse engines against an FSx for ONTAP S3 Access
Point: which engine and table format combinations work, which do not, and what each claim
rests on. Athena, Glue, EMR, Redshift Spectrum, DuckDB, Snowflake, Databricks, Delta Lake,
Iceberg. Deployable CloudFormation for each, plus the evidence records behind every result.

**What it deliberately does not cover**: how to choose, size, migrate to, or operate FSx for
ONTAP itself; ransomware and immutability; audit log shipping; block storage; VMware
migration. Those are below.

## Start here instead, if your question is

| Your question | Repository | What it owns |
|---|---|---|
| Should we adopt FSx for ONTAP, and how do we design, migrate to and operate it? | [FSx-for-ONTAP-Adoption-Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook) | Design, build and operations knowledge organised by lifecycle phase (assess → design → migrate → build → operate → optimize) and by topic, with explicit evidence tiers. 8 languages. **The starting point for anything not specific to analytics.** |
| How does an S3 Access Point behave on its own, and what serverless patterns are proven? | [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) | 17 industry use cases, the FPolicy event-driven pipeline, capacity guardrails, secrets rotation, SLO observability, property-based testing. **The measured object-size ceilings and API behaviour cited here live there.** |
| How do we detect and survive ransomware, and prove immutability? | [FSx-for-ONTAP-Cyber-Resilience-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-Cyber-Resilience-Patterns) | ONTAP ARP, third-party file security integrations, FPolicy event-driven response, storage-native data protection |
| How do we monitor this, and get audit logs into our SIEM? | [FSx-for-ONTAP-Observability-integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations) | EC2-free audit log shipping to Datadog, Splunk, New Relic, Grafana, Elastic and others, via S3 Access Points and Lambda |
| How do we build access-controlled RAG over this data? | [FSx-for-ONTAP-Agentic-Access-Aware-RAG](https://github.com/Yoshiki0705/FSx-for-ONTAP-Agentic-Access-Aware-RAG) | Access-aware agentic RAG with Amazon Bedrock, deployed with AWS CDK. **Relevant because an access point authorizes every request as one identity, so retrieval scoping has to be designed in the index** |
| How do we get edge and IoT data into this in the first place? | [ONTAP-Edge-to-Cloud-AI](https://github.com/Yoshiki0705/ONTAP-Edge-to-Cloud-AI) | Aggregating scattered edge device data into ONTAP, then using Bedrock, Athena and SageMaker across organisations |
| How do we serve one collected dataset to NFS and SMB sites without a copy job? | [S3-Burst-on-ONTAP-Files](https://github.com/Yoshiki0705/S3-Burst-on-ONTAP-Files) | Collect over the S3 Access Point, distribute with FlexCache. Worked example: hybrid-cloud AV / ADAS hardware-in-the-loop testing |
| How does this fit a governed multi-account landing zone? | [BLEA-FSx-for-ONTAP-Usecase](https://github.com/Yoshiki0705/BLEA-FSx-for-ONTAP-Usecase) | BLEA guest system use case combining enterprise file storage with analytics, cyber resilience, FlexCache and modernization |
| How do we migrate VMware workloads onto EC2 with ONTAP storage? | [VMware-Migration-EC2-ONTAP](https://github.com/Yoshiki0705/VMware-Migration-EC2-ONTAP) | VMware to EC2 migration with ONTAP-backed storage |

## How the pieces relate

The split is by question type, not by technology. Two boundaries are worth stating because
crossing them wastes the most time:

**Adoption Playbook versus this repository.** The Playbook answers "what should we do and
why", across the whole lifecycle and every protocol. This repository answers "does engine X
actually work against an access point, and what did it do when measured". A design decision
belongs there; a compatibility claim belongs here. The Playbook cites this repository for
analytics results rather than restating them, and this page is the return path.

**Serverless-Patterns versus this repository.** Both touch S3 Access Points. That repository
characterises the access point itself — supported operations, size ceilings, event pipelines.
This one characterises what analytics engines do through it. When a number about the access
point appears here, it is cited to there, because a measurement is only meaningful with the
environment it was taken in.

## Conventions shared across the family

- "Amazon FSx for NetApp ONTAP" on first mention, "FSx for ONTAP" thereafter.
- Confidence is stated, not implied. This repository uses four status markers and a
  four-stage verification ladder — see [llms.txt](../../llms.txt) for how to read them, and
  [compatibility-matrix](./compatibility-matrix.md) for the definitions. The Playbook uses
  evidence tiers in document frontmatter. **In both, a claim without a stated basis is a gap,
  not a fact.**
- Numbers travel with their environment: region, ONTAP version, configuration. Do not lift a
  figure into another context without them.

## Related documents

- [llms.txt](../../llms.txt) — machine-readable entry point for this repository
- [Reading Path Guide](./reading-path-guide.md) — how to navigate this repository specifically
- [Cross-Repository Integration Strategy](./cross-repo-integration-strategy.md) — the
  in-progress integration work between these repositories, at implementation detail
