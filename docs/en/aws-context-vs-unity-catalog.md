🌐 **English** | [日本語](../ja/aws-context-vs-unity-catalog.md)

# AWS Context vs Unity Catalog: Data Catalog and Knowledge Graph Comparison

> **Status**: Initial version (2026-06-18). AWS Context is in Preview. Based on public information from DAIS 2026 + AWS Summit NYC 2026.
> **Evidence tier**: All claims tagged **Public** (verifiable from public sources).

---

## Why This Matters for This Repository

This repository validates patterns for connecting FSx for ONTAP data to both Databricks (Unity Catalog) and AWS analytics services. AWS Context positions itself as a data catalog/discovery layer on the AWS side, **complementary to or potentially overlapping with** Unity Catalog.

For the manufacturing data platform:
- A catalog is needed to manage **structured metadata** (schemas, lineage, ACL)
- A discovery layer is needed for **agents** to find and access the right data
- **Multi-platform** governance spanning AWS native services + Databricks is required

---

## Service Overview

### AWS Context (Preview, 2026-06-17)

AWS Context is a service that automatically maps data and business logic into a knowledge graph, enabling AI agents to search and discover data (**Public**: [AWS Summit NYC 2026](https://www.aboutamazon.com/news/aws/aws-summit-nyc-2026-ai-agents), [TechTarget](https://www.techtarget.com/searchdatamanagement/news/366644853/AWS-latest-to-introduce-context-layer-for-agentic-AI)).

| Characteristic | Detail |
|----------------|--------|
| **Core technology** | Knowledge graph (extends same tech powering Amazon Quick's production knowledge graph) |
| **Metadata output format** | Apache Iceberg format, queryable via Amazon S3 Tables |
| **External catalog connectivity** | Via APIs and Model Context Protocol (MCP) servers/tools |
| **Learning** | Automatic learning from user usage patterns (hundreds of thousands of Amazon Quick daily users) |
| **Agent integration** | Unified discovery layer for agents to search and discover data |
| **Status** | Preview (announced 2026-06-17) |

### Unity Catalog (GA)

Databricks Unity Catalog is a unified governance catalog for data, AI models, agents, and MCP services (**Public**: [DAIS 2026](https://www.databricks.com/blog/whats-new-unity-catalog-data-ai-summit-2026)).

| Characteristic | Detail |
|----------------|--------|
| **Core technology** | Metastore + access control + lineage + auditing |
| **Metadata format** | Delta Lake / Iceberg metadata layer |
| **External catalog connectivity** | Federation connectors (AWS Glue, Hive Metastore, Snowflake Horizon) |
| **AI governance** | Unity AI Gateway — runtime governance for models/agents/MCP/skills |
| **Agent integration** | Directly governs Genie Ontology, Agent Bricks, Managed Omnigent |
| **Status** | GA (Iceberg v3 / Managed Iceberg / Foreign Iceberg also GA) |

---

## Comparison Table

| Dimension | AWS Context | Unity Catalog |
|-----------|-------------|---------------|
| **Primary role** | Data discovery + knowledge graph | Data governance + access control |
| **Approach** | Automatic mapping + learning | Explicit registration + policy definition |
| **Data format** | Iceberg (S3 Tables) | Delta Lake / Iceberg |
| **ACL management** | IAM-based (AWS native) | Custom ACL + ABAC (cross-engine) |
| **Lineage** | Unknown (details not yet public in Preview) | Native (table → column → dashboard) |
| **Agent discovery** | Knowledge graph search (primary use case) | Genie Ontology + metadata search |
| **MCP support** | MCP servers/tools for external connectivity | MCP services as governance targets |
| **Cross-platform** | AWS services-centric + 3rd party catalog connectivity | Multi-cloud (AWS, Azure, GCP) |
| **Storage independence** | S3 / S3 Tables centric | Delta Lake / Iceberg / external tables |
| **Maturity** | Preview (2026-06) | GA (5+ years) |
| **Cost** | Not yet announced | Included in Databricks platform fees |

---

## Positioning: Complementary or Competing?

### Complementary scenario (recommended)

```
                    AWS Context (discovery layer)
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
    S3 Tables       Glue Catalog    External catalogs
    (Iceberg)       (Athena, EMR)   (via MCP)
                                        │
                                        ▼
                                 Unity Catalog
                                 (Databricks governance)
```

- **AWS Context** = "Where is the data?" — knowledge graph for discovery
- **Unity Catalog** = "How is data accessed, and who can use it?" — governance and access control
- Both can connect via MCP — AWS Context ingests Unity Catalog metadata through MCP servers, providing unified discovery to agents

### Competing scenario

- Organizations using only Databricks → Unity Catalog alone is sufficient (AWS Context unnecessary)
- Organizations using only AWS native services → AWS Context + Glue Catalog is sufficient (Unity Catalog unnecessary)
- Organizations using both → **both needed, but responsibility separation is critical**

---

## Selection Guidance for This Repository (Manufacturing Data Platform)

### Positioning in current architecture

| Layer | Catalog Candidate | Rationale |
|-------|-------------------|-----------|
| **Layer 1: Edge** | None (local schemas only) | No catalog needed |
| **Layer 2+3: Databricks LTAP** | Unity Catalog | UC natively governs Databricks data |
| **AWS native services** (Athena, EMR, Bedrock KB) | AWS Context + Glue Catalog | Discover FSx for ONTAP data via S3 AP |
| **Cross-platform integration** | AWS Context (connected to UC via MCP) | Agents discover data across both platforms |

### FSx for ONTAP Touchpoints

| Pattern | Position in AWS Context | Position in Unity Catalog |
|---------|------------------------|--------------------------|
| File data via S3 AP | Metadata auto-registered in knowledge graph (as S3 Tables) | Registered as External Location / Foreign Iceberg |
| Quality inspection images | S3 AP URIs included as discovery targets | URI referenced from Lakebase records |
| Design documents (Document Intelligence) | Extraction results discoverable as S3 Tables | Stored as Delta tables in UC |
| Audit logs (`vserver audit`) | Correlation analysis via CloudWatch + knowledge graph | Cross-reference with Unity Catalog audit logs. **FPolicy raises nothing for operations through an S3 access point, so it is not an input for auditing** |

### Recommended Architecture

```
FSx for ONTAP (NFS/SMB/S3 AP)
       │
       ├───── S3 Access Point ─────┐
       │                           │
       ▼                           ▼
  AWS Context                 Unity Catalog
  (discovery)                 (governance)
       │                           │
       │    ┌── MCP connection ─┐  │
       │    │                   │  │
       ▼    ▼                   ▼  ▼
  Amazon Quick          Genie One / Agent Bricks
  (business users)      (data teams / engineers)
       │                           │
       └─────── Bedrock AgentCore Gateway ──────┘
               (MCP integration, governance)
```

**Design principles**:
- Data governance (ACL, lineage, auditing) is Unity Catalog's responsibility
- Data discovery (finding, relationship mapping, learning) is AWS Context's responsibility
- Agents access both via AgentCore Gateway
- FSx for ONTAP provides metadata to both catalogs via S3 AP

---

## Validation Required

> **Warning: AWS Context is in Preview — the following require post-GA validation**:
> 1. Whether S3 AP for FSx for ONTAP metadata is automatically registered in AWS Context
> 2. Whether Unity Catalog metadata can be ingested into AWS Context via MCP
> 3. Whether the AWS Context knowledge graph understands FSx for ONTAP directory structures/ACL
> 4. Whether Amazon Quick can query data on FSx for ONTAP
> 5. Pricing model (knowledge graph construction + query charges?)

---

## Related Repository Touchpoints

| Repository | AWS Context Relevance | Unity Catalog Relevance |
|------------|----------------------|------------------------|
| [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) | S3 AP events could auto-register metadata in AWS Context | — |
| [FSx-for-ONTAP-Agentic-Access-Aware-RAG](https://github.com/Yoshiki0705/FSx-for-ONTAP-Agentic-Access-Aware-RAG) | AWS Context as discovery layer for permission-aware RAG | Bedrock KB + S3 AP could link with UC External Location |
| [ontap-edge-to-cloud-ai](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai) | Auto-catalog registration of edge device data in AWS Context | Databricks-side governance of edge data |
| [fsxn-observability-integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations) | Correlation analysis of audit logs via knowledge graph | — |

---

## References

- [AWS: Context intelligence for your data and AI agents at scale](https://aws.amazon.com/blogs/machine-learning/context-intelligence-for-your-data-and-ai-agents-at-scale/) (2026-06-17)
- [About Amazon: New AI agent innovations (Summit NYC)](https://www.aboutamazon.com/news/aws/aws-summit-nyc-2026-ai-agents) (2026-06-17)
- [TechTarget: AWS latest to introduce context layer for agentic AI](https://www.techtarget.com/searchdatamanagement/news/366644853/AWS-latest-to-introduce-context-layer-for-agentic-AI) (2026-06-17)
- [Techstrong.ai: AWS Adds Context Service and Harness to AI Portfolio](https://techstrong.ai/articles/aws-adds-context-service-and-harness-to-ai-portfolio/) (2026-06-17)
- [Databricks: What's new with Unity Catalog at DAIS 2026](https://www.databricks.com/blog/whats-new-unity-catalog-data-ai-summit-2026) (2026-06-16)
- [Databricks: AI Governance — Unity AI Gateway](https://www.databricks.com/blog/ai-governance-data-ai-summit-2026-whats-new-unity-ai-gateway) (2026-06-16)
