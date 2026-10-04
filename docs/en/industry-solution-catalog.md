**English** | [日本語](../ja/industry-solution-catalog.md)

> 📖 **Paired with the technical guide**: This catalog is the **industry solution catalog** that pairs with the [FSx for ONTAP → Databricks UC Connection Guide](./fsx-ontap-to-databricks-unity-catalog-guide.md) (technical detail of connection paths). While the technical guide covers "How to connect," this catalog covers "Who / Why / Which path" per industry.

# FSx for ONTAP × Databricks Unity Catalog Industry Solution Catalog

> **Status**: Initial edition (2026-06-19). Integrates public reference architectures and this repository's verification results.
> **Audience**: AWS SAs, partner SI/ISVs, industry solution architects, data leaders in adopting organisations.
> **Evidence tier** per claim: **Public** (verifiable from public sources) / **Project-context** (reproducible in this repository) / **Archetype** (general knowledge based on industry-standard roles).
> **Framing**: right-tool-for-the-job, not vendor-versus. Trade-offs stated symmetrically per option.

---

## Executive Summary

| Aspect | Detail |
|---|---|
| Purpose | Provides industry-specific recommended patterns for connecting enterprise file data accumulated in FSx for ONTAP (NFS/SMB/S3/iSCSI) to Databricks Unity Catalog-governed analytics/AI platforms per industry use case |
| Common principle | Direct zero-copy UC connection is not supported (see technical guide). Production paths are the indirect paths "DataSync → S3 → UC," "Kafka → Structured Streaming → UC," and "Glue/EMR ETL → UC" |
| Cross-industry FSx for ONTAP capabilities | Multiprotocol (simultaneous NFS/SMB/S3 access to same data), Snapshot/FlexClone (consistent point-in-time copies, instant clones), SnapMirror (DR), SnapLock (WORM compliance), storage efficiency (dedup/compression) |
| Regulated industry caveats | Finance (BCBS 239, etc.), healthcare (HIPAA/GxP), public sector (data sovereignty) must include data classification, audit logs, encryption chains, and cross-border constraints as design prerequisites |
| How to use this catalog | Check your industry's section for "use case → recommended path → governance → caveats," then navigate to the relevant path detail in the technical guide via links |
| Coverage | 26 industries (manufacturing, automotive, finance, healthcare, semiconductor, media, retail, energy, telecom, public sector, plus agriculture, logistics, tourism, legal, construction, education, defense, smart city, AdTech, transportation, ESG, real estate, HR, chemical, gaming, SAP/ERP). For serverless automation pattern implementations, see the industry use cases (UC1-UC30) in [FSx for ONTAP S3 Access Points Serverless Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) (same author) |

## Cross-Industry Quick Reference

| Industry | Representative Use Cases | FSx for ONTAP Features Used | Recommended Path | Key Regulations/Constraints |
|----------|------------------------|--------------------|--------------------|-----------------------------|
| Manufacturing / Industrial | Quality analytics, predictive maintenance, traceability | Multiprotocol, Snapshot, FabricPool | DataSync / Kafka(FPolicy) | IATF 16949, OT/IT separation |
| Automotive | ADAS/AD data, connected vehicle, part genealogy | Scale-out performance, SnapMirror, SnapLock | DataSync / Kafka | Data sovereignty, ISO 26262, retention |
| Financial / Insurance | Risk analytics, fraud detection, regulatory reporting | SnapLock(WORM), Snapshot, encryption | DataSync / Glue ETL | BCBS 239, data residency, audit |
| Healthcare / Life Sciences | EHR analytics, genomics, medical imaging, drug discovery | Multiprotocol, FlexClone, SnapLock | DataSync / Glue ETL | HIPAA/ePHI, GxP, HDS, FHIR |
| Semiconductor / EDA | Chip design, verification, tape-out analysis | FlexCache, scale-out(36GB/s), Snapshot | Glue/EMR / DataSync | IP protection, export control(EAR) |
| Media & Entertainment | VFX rendering, asset management, distribution analytics | Scale-out performance, FlexClone, multiprotocol | DataSync / Glue ETL | Content rights, DRM |
| Retail / CPG | Demand forecasting, personalization, inventory optimization | Storage efficiency, Snapshot | DataSync / Kafka | PCI DSS, PII protection |
| Energy / Utilities | Grid telemetry, predictive maintenance, asset management | Multiprotocol, SnapMirror | Kafka / DataSync | NERC CIP, OT/IT separation |
| Telecommunications | Network telemetry, CDR analytics, fraud detection | Scale-out performance, Snapshot | Kafka / DataSync | Data retention, PII |
| Public Sector / Government | Citizen data analytics, defense, research | SnapLock, SnapMirror, encryption | DataSync / Glue ETL | Data sovereignty, FedRAMP, ITAR/EAR |
| Agriculture / Food 🌱 | Precision agriculture, crop health, food traceability | Multiprotocol, storage efficiency, SnapMirror | Kafka(edge) / Glue ETL | HACCP, food traceability laws |
| Logistics / SCM 📦 | Warehouse CV, delivery OCR, cold chain | Scale-out performance, multiprotocol | Kafka(edge) / DataSync | GDP, hazmat transport, customs |
| Travel / Hospitality 🏨 | Guest experience, facility inspection, crowd analysis | Multiprotocol, storage efficiency | DataSync / Kafka(edge) | Guest PII, PCI DSS, video privacy |
| Legal / Compliance | Contract analysis, ACL audit, e-Discovery | ONTAP REST API, SnapLock | DataSync / Glue ETL | Privilege, retention obligations |
| Construction / AEC | BIM, drawing OCR, safety inspection | Scale-out performance, FlexClone | DataSync / Glue ETL | Building safety regs, long-term preservation |
| Education / Research | Paper classification, research data, learning analytics | Multiprotocol, FlexClone | DataSync / Glue ETL | FERPA, research ethics |
| Defense / Space | Satellite imagery, geospatial intelligence | Scale-out performance, SnapLock, encryption | Glue ETL | ITAR/EAR, FedRAMP High, classification |
| Smart City | Geospatial, traffic, environment, disaster prevention | Multiprotocol, SnapMirror | Kafka(edge) / Glue ETL | Citizen PII, data sovereignty, OGC |
| AdTech / Marketing | Asset management, brand check, campaign analysis | Multiprotocol, FlexClone | DataSync | Targeting PII, cookie regulations |
| Transportation / Rail 🚆 | Equipment inspection, predictive maintenance, maintenance analysis | Multiprotocol, SnapLock | DataSync / Kafka | Railway safety regs, retention obligations |
| Sustainability / ESG | ESG metrics, emissions, regulatory reporting | Multiprotocol, SnapLock | DataSync | CSRD, TCFD, SEC climate disclosure |
| Real Estate | Property images, contract extraction, portfolio | Storage efficiency, multiprotocol | DataSync | Customer PII, transaction regulations |
| Human Resources | Resume screening, talent matching | ONTAP REST API, SnapLock | DataSync | Employee PII, anti-discrimination |
| Chemical / Materials | SDS management, lab notebooks, materials development | Multiprotocol, SnapLock, FlexClone | DataSync / Glue ETL | REACH, GHS, IP protection |
| Gaming | Asset quality, build, player analytics | FlexClone, FlexCache, scale-out | DataSync / Kafka | Player PII, minor protection |
| SAP / ERP-Adjacent | IDoc/EDI, batch output, master integration | High-performance storage, Snapshot/FlexClone | DataSync / Federation | Financial audit (SOX), integrity |

---

## Cross-Cutting Design Caveats (All Industries)

Regardless of industry, consider these three points early in design.

### DR Scope (Critical)

> SnapMirror replicates the **FSx for ONTAP volume (source)** but does **not replicate UC tables or analytics copies on S3**. DR design must handle the analytics copy separately (re-run DataSync at the DR region, or sync via S3 Cross-Region Replication). Avoid the misconception that "SnapMirror alone completes DR." For full-pipeline DR orchestration (FSx for ONTAP + S3 + UC + MSK), see the [DR runbooks in the Compatibility Matrix](./compatibility-matrix.md).

### Governance: Right-Tool-for-the-Job, Not Either/Or

> This catalog centers on UC governance, but for AWS-native workloads (Athena/EMR/Glue-centric, especially semiconductor and media), AWS Lake Formation / Amazon DataZone (SageMaker Unified Studio) is the AWS-side governance layer. UC and AWS-native governance are not mutually exclusive; choose or combine based on use case (right-tool-for-the-job, not superiority).

> The modern UC governance pattern is **ABAC (attribute-based access control) + governed tags** ([official](https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/tutorial)). Define a consistent tag taxonomy per industry first (e.g., `pii`, `ephi`, `ip`, `payment`, `classification`), then apply policies based on it for easier management at scale. Regulated industries (finance, healthcare, public) suit **centralized** governance; large diversified organizations suit **federated (catalog-per-domain)** governance.

### Common Cost Control Lever

> For data-volume-heavy industries (media, semiconductor, telecom, automotive ADAS), the biggest cost control lever is "**do not replicate everything to S3**." Keep raw data on FSx for ONTAP and ingest only curated subsets / metadata / aggregates needed for analytics into UC. Combine with S3 Lifecycle + storage class tiering (IA/Glacier).

---

## Industry Solutions

Each industry section uses a common template: **Data characteristics → Key use cases → FSx for ONTAP features used → Recommended path → Governance/regulation → Caveats**.

---

### 1. Manufacturing / Industrial

> For detailed manufacturing data platform design, see [Manufacturing Data Platform Integration](../../integrations/manufacturing-data-platform/). This section summarizes from the UC connection perspective.

**Data characteristics**: Sensor time-series, quality inspection images, equipment logs, MES/SCADA output. Tends to generate massive small files. OT and IT networks are separated.

**Key use cases**:
- Quality analytics / SPC (statistical process control): anomaly detection in inspection data, yield improvement
- Predictive maintenance: failure prediction from equipment sensor data
- Manufacturing traceability: lot/serial-level genealogy tracking (8D reports, recall response)
- Digital supply chain: inventory/demand visibility (Databricks official: [Digital Supply Chain Reference Architecture](https://www.databricks.com/resources/architectures/manufacturing-digital-supply-chain-reference-architecture), **Public**)

**FSx for ONTAP features used**:
- Multiprotocol: analyze data written by PLC/SCADA via NFS/SMB through S3 AP without conversion
- Snapshot: use consistent inspection-time datasets as DataSync sync source (avoid production I/O impact)
- FabricPool: auto-tier cold historical inspection data to S3

**Recommended path**:
- Batch quality analytics → **Path 1 (DataSync → S3 → UC)** + Auto Loader + DLT medallion
- Real-time quality alerts → **Path 2 (Kafka via FPolicy → Structured Streaming → UC Delta)**

**Governance/regulation**: IATF 16949 (long-term retention of quality records for automotive parts), manufacturing data classification (public aggregates vs confidential design data).

**Caveats**: PLCs typically lack Kafka Producer capability. Data flow is "PLC → NFS/SMB write → FSx for ONTAP → FPolicy detection → Lambda → Kafka." Place FPolicy Lambda / DataSync at Purdue Level 3.5 (IDMZ) for the OT/IT boundary.

---

### 2. Automotive

**Data characteristics**: ADAS/AD (autonomous driving) sensor data (camera, LiDAR, radar; petabyte-scale), connected vehicle telemetry, manufacturing traceability, part genealogy. Data distributed across multiple regions in global supply chains.

**Key use cases**:
- ADAS/AD data pipeline: collection, labeling, and dataset creation of driving logs for model training
- Connected vehicle analytics: real-time vehicle telemetry analytics, predictive maintenance, OTA update decisions
- Quality traceability: VIN/lot-level genealogy tracking, recall scope identification
- Supply chain visibility: data linkage with Tier 1/2 suppliers

**FSx for ONTAP features used**:
- Scale-out performance (up to 36 GB/s, 1.2M IOPS, [**Public**](https://aws.amazon.com/about-aws/whats-new/2023/11/amazon-fsx-netapp-ontap-scale-out-file-systems/)): ingestion of large ADAS sensor data
- SnapMirror: cross-region data replication (designed considering data sovereignty)
- SnapLock: WORM retention of quality records (regulatory compliance)

**Recommended path**:
- ADAS dataset creation → **Path 3 (Glue/EMR ETL → UC)** (large-scale batch transformation)
- Connected vehicle telemetry → **Path 2 (Kafka → Structured Streaming → UC)**
- Traceability metadata → **Path 1 (DataSync → S3 → UC)** + S3 Annotations (see [S3 Annotations Evaluation](./s3-annotations-governance-evaluation.md))

**Governance/regulation**: Data sovereignty (China PIPL/CSL, EU GDPR), functional safety (ISO 26262 traceability requirements), quality record retention (IATF 16949, minimum 15 years).

**Caveats**: In global supply chains, the same part's data exists across multiple regions. Limit DataSync to intra-region sync, and handle cross-region analytics via S3 Cross-Region Replication (data sovereignty perspective). Anonymize connected vehicle personal data before sync.

> ADAS sensor data is often in proprietary binary formats (rosbag, MDF4, in-vehicle logs), so **developing conversion parsers** to Parquet etc. is a prerequisite. Design a dedicated parser step before Path 3 (Glue/EMR ETL). Also, for autonomous driving type approval, driving logs may be subject to retention obligations as certification evidence — consider retention periods and long-term format readability.

---

### 3. Financial Services / Insurance

**Data characteristics**: Trading data (high-frequency, low-latency), market data, customer data (PII), risk model inputs, regulatory reporting data. Long-term retention obligations and tamper-proofing requirements.

**Key use cases**:
- Risk analytics: market risk / credit risk calculation (Databricks official: [Investment Management Reference Architecture](https://www.databricks.com/resources/architectures/financial-services-investment-management-reference-architecture), **Public**)
- Fraud detection: real-time transaction monitoring, AML (anti-money laundering)
- Regulatory reporting: BCBS 239 (risk data aggregation), report data generation for regulators
- Insurance: claims analytics, actuarial models, fraudulent claim detection

**FSx for ONTAP features used**:
- SnapLock (WORM): tamper-proof retention of regulatory reporting data / transaction records
- Snapshot: preserve consistent datasets at audit points
- Encryption: encryption chain at rest (volume encryption) + in transit (NFS krb5p / TLS)
- High-performance storage: data store for core banking DBs like Oracle/SQL Server ([**Public**](https://aws.amazon.com/blogs/industries/fsi-services-spotlight-featuring-amazon-fsx-for-netapp-ontap/))

**Recommended path**:
- Risk analytics / regulatory reporting → **Path 1 (DataSync → S3 → UC)** + UC full governance (lineage, tags, masks)
- Real-time fraud detection → **Path 2 (Kafka → Structured Streaming → UC)**
- Core banking DB linkage → UC Lakehouse Federation (PostgreSQL/Oracle/SQL Server, see technical guide)

**Governance/regulation**: BCBS 239 (accuracy, completeness, timeliness of risk data aggregation), data residency (per-country financial regulations), audit trail (who accessed which data), PII masking (UC Column Masks / Row Filters).

**Caveats**: Make regulatory reporting data provable "from source to reported value" via UC lineage. For multi-cloud regulatory requirements ([**Public**](https://www.databricks.com/blog/multi-cloud-architecture-portable-data-and-ai-processing-financial-services)), leverage UC's cross-cloud governance.

> BCBS 239 requires timeliness as well as aggregation accuracy. Verify that DataSync's RPO (data freshness) meets reporting requirements. Also, risk models trained on this data fall under model risk management (for example, US SR 11-7), so integrate model version management / validation records (MLflow) in addition to UC lineage.

> SnapLock has a **Compliance mode** (cannot be deleted within retention even by admin) and an **Enterprise mode** (admin can delete). Use Compliance mode for tamper-proofing regulatory reports / transaction records, and verify the Compliance Clock setting.

> Direct DataSync from a production trading DB competes with business I/O. As in manufacturing, use the **Snapshot → FlexClone → DataSync** staging pattern to avoid business impact in finance too.

---

### 4. Healthcare / Life Sciences

**Data characteristics**: EHR (electronic health records, FHIR), medical images (DICOM, large), genomics data (petabyte-scale), clinical trial data, drug discovery research data. Highly confidential data including ePHI (electronic protected health information).

**Key use cases**:
- EHR analytics: clinical outcomes analysis, population health management (AWS HealthLake / FHIR, [**Public**](https://aws.amazon.com/healthlake/getting-started/))
- Genomics: sequence data analysis pipelines, variant analysis
- Medical imaging AI: training diagnostic support models (DICOM → UC Volume)
- Drug discovery: compound screening, clinical trial data management (GxP)

**FSx for ONTAP features used**:
- Multiprotocol: route images/records written by healthcare systems via SMB to analytics platform ([**Public**: healthcare systems store patient records on SMB volumes](https://www.netapp.com/blog/ai-insights-ontap-s3-access-points-dremio/))
- FlexClone: instant clone of production genomics data to isolate research environments (no production impact)
- SnapLock: WORM retention of clinical trial data (GxP electronic records requirements)

**Recommended path**:
- EHR/clinical analytics → **Path 1 (DataSync → S3 → UC)** + UC full governance
- Genomics/imaging batch analysis → **Path 3 (Glue/EMR ETL → UC)**
- RAG/clinical document search → Bedrock KB (S3 AP direct, outside UC; HIPAA-ready architecture required, [**Public**](https://aws.amazon.com/blogs/industries/building-a-hipaa-ready-generative-ai-architecture-for-healthcare-on-aws/))

**Governance/regulation**: HIPAA (ePHI protection), HITRUST, GxP (FDA 21 CFR Part 11 electronic records/signatures), GDPR/HDS (EU health data), data minimization principle.

**Caveats**: Mask ePHI-containing data from unauthorized users via UC Column Masks. Design guardrails so ePHI does not leak into model outputs in RAG pipelines. Consider anonymization/pseudonymization before sync.

> Anonymization has standards (HIPAA Safe Harbor method vs Expert Determination method). Clarify which you comply with at design time. Notably, **DICOM images can have PHI burned into pixel data (burned-in annotation)**, so metadata removal alone is insufficient. Pixel-level de-identification is required before imaging AI training. Genomics also requires consideration of GA4GH standards and consent management.

---

### 5. Semiconductor / EDA (Electronic Design Automation)

**Data characteristics**: Chip design data (RTL, netlists), verification/simulation results, tape-out data, EDA tool libraries. Requires extremely high IOPS and low latency. Most confidential as IP (intellectual property).

**Key use cases**:
- Chip design/verification: storage foundation for EDA tools (synthesis, place & route, verification) ([**Public**: Arm chip design case study](https://aws.amazon.com/solutions/case-studies/arm-ltd-case-study/))
- Tape-out analysis: analysis of design versions / verification results
- Regression analysis: trend analysis of massive simulation job results
- Hybrid burst: cloud burst of on-premises EDA workloads ([**Public**](https://aws.amazon.com/blogs/industries/accelerating-eda-with-the-agility-of-aws-and-netapp-data-services/))

**FSx for ONTAP features used**:
- FlexCache: cache on-premises tools/libraries to cloud (appear local to cloud workloads, [**Public**](https://aws.amazon.com/blogs/industries/accelerating-eda-with-the-agility-of-aws-and-netapp-data-services/))
- Scale-out performance (36 GB/s, 1.2M IOPS): EDA high-IOPS workloads
- Snapshot: point-in-time management of design versions

**Recommended path**:
- Verification result trend analysis → **Path 3 (Glue/EMR ETL → UC)** or **Path 1 (DataSync → S3 → UC)**
- EDA workloads themselves run directly on FSx for ONTAP NFS (UC connection for analytics metadata only)

**Governance/regulation**: IP protection (strict access control of design data), export control (EAR/ITAR, restricting overseas access to design data).

**Caveats**: EDA's primary workloads (design, verification) complete on FSx for ONTAP; limiting UC connection to "analytics and trend insight" secondary use is realistic. Replicating design data itself into UC is not recommended for both IP protection and data volume reasons. Limit analysis targets to metadata and result summaries.

> Realistic UC analysis targets are job scheduler (IBM LSF / Slurm) job result logs and regression result summaries. Since tape-out time directly drives EDA license cost, analyzing license utilization and job completion trends has high ROI. Keep design data itself (RTL/netlists) on FSx for ONTAP, and optimize tool/library sharing between on-premises and cloud with FlexCache.

---

### 6. Media & Entertainment

**Data characteristics**: Video assets (VFX, 4K/8K, petabyte-scale), rendering intermediate files, digital assets, distribution logs. Large sequential I/O.

**Key use cases**:
- VFX rendering: storage foundation for render farms ([**Public**: FSx for ONTAP suits VFX rendering](https://aws.amazon.com/fsx/netapp-ontap/resources/))
- Digital asset management (DAM): metadata management / search of media assets
- Distribution analytics: viewing log / engagement analysis, recommendations
- Content AI: auto-tagging, scene detection, subtitle generation

**FSx for ONTAP features used**:
- Scale-out performance: render farm high-throughput I/O
- FlexClone: instant duplication of production environments (version management)
- Multiprotocol: same-data access for production tools (SMB) and analytics (S3 AP)

**Recommended path**:
- Distribution/viewing log analytics → **Path 1 (DataSync → S3 → UC)** + Databricks recommendations
- Asset metadata / auto-tagging → **Path 1** + S3 Annotations (content context attachment)
- Content AI (image/audio embedding) → UC Volume + AI Search

**Governance/regulation**: Content rights management, DRM, confidentiality of in-production content (NDA).

**Caveats**: Replicating video assets themselves into UC is impractical due to data volume. UC manages metadata, tags, and distribution logs. Keep assets on FSx for ONTAP, accessing via S3 AP as needed.

---

### 7. Retail / CPG

**Data characteristics**: POS transactions, inventory data, customer data (PII), e-commerce logs, supply chain data, product images.

**Key use cases**:
- Demand forecasting: sales forecasting / inventory optimization (Databricks official: [Retail Demand Forecasting Reference Architecture](https://www.databricks.com/resources/architectures/retail-demand-forecasting-reference-architecture), **Public**)
- Personalization: recommendations, customer segmentation
- Inventory optimization: real-time inventory visibility, replenishment optimization
- Product analytics: auto-classification of product images, attribute extraction

**FSx for ONTAP features used**:
- Storage efficiency (up to 65% reduction via dedup/compression, [**Public**](https://www.netapp.com/learn/aws-fsxn-blg-reduce-costs-and-increase-efficiency-with-fsx-for-ontap/)): cost optimization of massive product images/logs
- Snapshot: consistent snapshots for daily batch analytics

**Recommended path**:
- Demand forecasting / customer analytics → **Path 1 (DataSync → S3 → UC)** + Databricks ML
- Real-time inventory → **Path 2 (Kafka → Structured Streaming → UC)**
- Product image AI → UC Volume + AI Search

**Governance/regulation**: PCI DSS (payment data), PII protection (customer data), GDPR/per-country privacy laws.

**Caveats**: Payment data (card numbers, etc.) is in PCI DSS scope. Tokenize/mask before ingestion into UC. Protect customer PII via UC Column Masks.

> Dedup/compression is effective for text, logs, and structured data, but **barely works on already-compressed video or encrypted data** (note for media/genomics). Product images (JPEG) are also pre-compressed, so estimate storage efficiency expectations per data type.

---

### 8. Energy & Utilities

**Data characteristics**: Grid telemetry (smart meters, SCADA), power generation equipment sensors, geospatial data, supply/demand forecast data. OT environment and real-time requirements.

**Key use cases**:
- Grid analytics: supply/demand balance, load forecasting (Databricks official: [Office of the CFO for Manufacturing & Energy](https://www.databricks.com/resources/architectures/office-of-cfo-for-manufacturing-and-energy), **Public**)
- Predictive maintenance: failure prediction for generation/transmission equipment
- Asset management: equipment lifecycle management, maintenance optimization
- Renewable energy: generation forecasting (weather-linked), storage optimization

**FSx for ONTAP features used**:
- Multiprotocol: route SCADA/historian output to analytics platform
- SnapMirror: data replication between geographically distributed sites

**Recommended path**:
- Grid telemetry → **Path 2 (Kafka → Structured Streaming → UC)**
- Equipment data batch analysis → **Path 1 (DataSync → S3 → UC)**

**Governance/regulation**: NERC CIP (North American power infrastructure protection), OT/IT separation (critical infrastructure security).

**Caveats**: The power grid is critical infrastructure. Design OT network security boundaries strictly. Like manufacturing, use IDMZ-mediated data flow based on the Purdue model.

> **UC analytics is "insight" and must NOT be embedded in the OT control loop**. Safety-related decisions (grid control, protection relays) must complete within the OT-side real-time control system, and Databricks analytics should be limited to offline/near-real-time use for prediction, optimization, and visualization. A design where analytics-side latency or failures do not propagate to the control system is essential for safety.

---

### 9. Telecommunications

**Data characteristics**: Network telemetry, CDR (call detail records, massive/high-frequency), subscriber data (PII), network equipment logs. Ultra-large data volumes and retention obligations.

**Key use cases**:
- Network analytics: traffic analysis, quality monitoring, capacity planning
- CDR analytics: call pattern analysis, billing, fraud detection
- Fraud detection: real-time detection of SIM swap fraud, billing fraud
- Customer experience: churn prediction, service quality analysis

**FSx for ONTAP features used**:
- Scale-out performance: ingestion of massive CDR/telemetry
- Snapshot: point-in-time data preservation for audit/regulatory compliance
- Storage efficiency: cost optimization of massive logs

**Recommended path**:
- Network telemetry → **Path 2 (Kafka → Structured Streaming → UC)**
- CDR batch analytics → **Path 1 (DataSync → S3 → UC)** or **Path 3 (Glue/EMR ETL)**

**Governance/regulation**: Data retention obligations (per-country telecom laws), subscriber PII protection, secrecy of communications.

**Caveats**: CDR is ultra-large (daily terabyte-scale). Limit DataSync targets to aggregated data; keep raw CDR on FSx for ONTAP and analyze only when needed.

> CDR has high "data gravity," and even aggregated data results in massive DataSync transfer volumes. Design **edge/ingestion-time pre-aggregation and sampling** (time-window aggregation, narrowing to target KPIs), and ingest only the granularity needed for analysis into UC. Replicating all raw CDR to S3 is not recommended for both cost and performance.

---

### 10. Public Sector / Government

**Data characteristics**: Citizen data (highly confidential PII), administrative records, research data, defense-related data, geospatial data. Data sovereignty and long-term retention requirements.

**Key use cases**:
- Citizen service analytics: usage analysis of administrative services, policy-making support
- Research data management: data platform for government research institutions
- Defense/security: confidential data analysis (strict access control)
- Smart city: sensor data analysis of urban infrastructure

**FSx for ONTAP features used**:
- SnapLock (WORM): tamper-proof / long-term retention of administrative records
- SnapMirror: DR / data preservation
- Encryption: at-rest/in-transit encryption of confidential data

**Recommended path**:
- Citizen data analytics → **Path 1 (DataSync → S3 → UC)** + UC full governance + strict audit
- Research data batch → **Path 3 (Glue/EMR ETL → UC)**

**Governance/regulation**: Data sovereignty (domestic data centers may be mandatory), FedRAMP (US government cloud), ITAR/EAR (defense-related, use GovCloud), per-country government information security standards.

**Caveats**: Region selection is constrained by data sovereignty requirements. Defense-related uses GovCloud + strict IAM/network isolation. Citizen PII requires mandatory UC full governance (masks, row filters, audit).

> Depending on data sovereignty requirements, the **location of the SaaS control plane** can be a constraint. Verify whether the Databricks or Snowflake control plane is in a region meeting requirements, and note that GovCloud is a separate offering. There are cases where a configuration with the data plane domestic but the control plane abroad is not permitted.

> GovCloud has different service availability than commercial regions. Verify the GovCloud availability of Amazon FSx for NetApp ONTAP, DataSync, MSK, and Databricks in advance. ITAR/EAR-subject data requires GovCloud + strict network isolation as a prerequisite.

---

### 11. Agriculture / Food

> An industry where data originates from edge devices (sensors/cameras). The same edge-to-cloud design as manufacturing/automotive applies.

**Data characteristics**: Soil sensors, weather stations, drone aerial imagery (multispectral), pest traps, farm machinery telemetry, traceability documents. Fields are geographically dispersed with low bandwidth (LoRaWAN / LTE).

**Key use cases**:
- Precision agriculture: analysis of soil/weather/crop stress, yield forecasting (AWS: [Connected Farm](https://aws.amazon.com/blogs/industries/creating-the-connected-farm-using-sensor-and-vision-data), **Public**)
- Crop health monitoring: disease/growth assessment via drone/satellite imagery
- Food traceability: production-to-distribution genealogy tracking (lot, origin, inspection records)
- Farm machinery/fleet management: telemetry of autonomous tractors/harvesters

**FSx for ONTAP features used**:
- Multiprotocol: route data aggregated by field gateways via NFS/SMB to analytics platform
- Storage efficiency: cost optimization of massive drone imagery / time-series sensor data
- SnapMirror: aggregation of data from geographically dispersed farm sites

**Recommended path**:
- Sensor telemetry → **Path 2 (Kafka → Structured Streaming → UC)** (via edge gateway)
- Drone/satellite imagery batch analysis → **Path 3 (Glue/EMR ETL → UC)** + SageMaker geospatial
- Traceability metadata → **Path 1 (DataSync → S3 → UC)** + S3 Annotations

**Governance/regulation**: Food safety (HACCP, food traceability laws), farm data ownership, subsidy audits.

**Caveats**: Field edge devices have low bandwidth and intermittent connectivity. A design that performs filtering/inference at the edge (AWS IoT Greengrass, etc.) and sends only aggregated data to the cloud is essential. Uploading all raw imagery is impractical for bandwidth/cost. Much edge inference (crop health assessment) completes at the edge, and only assessment results and representative images are ingested into UC.

> Farm data **ownership** is often contested (farmer vs equipment OEM vs agronomy solution provider). Clarify data sharing agreements and UC access control. Agricultural data is also highly seasonal (peaks at planting/harvest), so plan FSx for ONTAP throughput for peaks or leverage elastic throughput.

---

### 12. Logistics / Supply Chain

> An industry where data originates from edge cameras/sensors. Centered on real-time visibility of warehouses and transport.

**Data characteristics**: Warehouse cameras (object recognition/inventory), delivery slips (OCR), cold chain sensors (temperature/humidity), vehicle telematics, handheld scanner logs.

**Key use cases**:
- Warehouse computer vision: inventory tracking, damage detection, mis-shipment prevention, worker safety (forklift proximity detection)
- Delivery slip OCR: automatic reading of slips/labels (repo UC12)
- Cold chain monitoring: temperature excursion detection for pharma/perishable food
- Fleet/telematics: delivery route optimization, driver behavior analysis

**FSx for ONTAP features used**:
- Scale-out performance: ingestion of massive imagery from multi-site warehouse cameras
- Multiprotocol: same-data access for WMS output and analytics
- Storage efficiency: cost optimization of surveillance footage / scan logs

**Recommended path**:
- Warehouse CV real-time alerts → inference at edge (on-prem cameras + edge appliance, <300ms), results via **Path 2 (Kafka → UC)**
- Slip OCR batch → **Path 1 (DataSync → S3 → UC)** + Textract
- Cold chain telemetry → **Path 2 (Kafka → Structured Streaming → UC)**

**Governance/regulation**: Pharma cold chain (GDP: Good Distribution Practice), hazardous materials transport records, import/export customs data.

**Caveats**: Warehouse CV has strict latency requirements (<300ms), so edge inference is the baseline. The cloud (UC) is positioned for aggregate analysis / trend insight of edge results. As AWS Panorama reaches end-of-support in May 2026, design edge CV with AWS IoT Greengrass + general-purpose cameras, or third-party edge appliances.

> Cold chain temperature excursion alerts are a **near-real-time regulatory requirement** under pharma GDP (immediate notification on excursion). Since DataSync batch sync cannot meet this, use threshold alerting at the edge/IoT Core + Path 2 (Kafka), and position UC ingestion for post-hoc trend analysis / audit. For last-mile delivery, proof-of-delivery (POD) photos are also an important data source.

---

### 13. Travel / Tourism / Hospitality

> An industry where data originates from edge sensors/cameras. Digitalization of facilities, accommodation, and tourism experiences.

**Data characteristics**: Reservation documents, facility inspection images, people-counting/occupancy sensors, building IoT (connected hotel), guest behavior data, review/inquiry text.

**Key use cases**:
- Guest experience personalization: integrated analysis of reservation/stay/behavior data (AWS: [Travel & Hospitality Connected Experiences](https://aws.amazon.com/travel-and-hospitality/connected-experiences/), **Public**)
- Facility inspection: AI analysis of room/equipment inspection images (repo UC20)
- Occupancy/crowd management: people-counting and flow analysis for tourist sites/theme parks/facilities
- Reservation document processing: OCR/structuring of reservation/contract documents

**FSx for ONTAP features used**:
- Multiprotocol: same-data access for facility management system (PMS/BMS) output and analytics
- Storage efficiency: cost optimization of inspection images / surveillance footage
- Snapshot: consistent dataset preservation around peak seasons

**Recommended path**:
- Guest behavior/reservation analytics → **Path 1 (DataSync → S3 → UC)** + Databricks ML (personalization)
- Facility inspection image AI → **Path 1** + UC Volume + AI Search
- Occupancy/people-counting → aggregate at edge (people-counting cameras), counts via **Path 2 (Kafka → UC)**

**Governance/regulation**: Guest PII (GDPR / per-country privacy laws), payment data (PCI DSS), video privacy (surveillance footage capturing people).

**Caveats**: For occupancy/crowd analysis, send only non-identifying aggregate data (counts) to the cloud and process/discard raw footage at the edge to protect privacy. Aggregating raw surveillance footage into UC is not recommended for both privacy and data volume.

> International travelers' guest data becomes **cross-border data**, making data residency complex (regulations of departure country, stay country, and HQ country intersect). Loyalty program data is high-value PII — apply UC full governance. Travel/hospitality has large seasonal/event-driven demand fluctuations, so reflect storage/compute elasticity in the design.

---

### 14. Legal / Compliance

**Data characteristics**: Contracts, legal documents, file server audit logs, NTFS ACL metadata. Long-term retention and tamper-proofing requirements.

**Key use cases**:
- File server audit: inventory of NTFS ACLs/access permissions, data governance reports (repo UC1)
- Contract analysis: extraction/classification of contract clauses, risk detection
- e-Discovery: litigation document search/classification
- Retention compliance: management of legal retention periods

**FSx for ONTAP features used**:
- ONTAP REST API: retrieval of NTFS ACL/owner/permission metadata (not retrievable via S3 API)
- SnapLock (WORM): tamper-proofing of legally retained documents
- Snapshot: preservation of file system state at audit points

**Recommended path**:
- Contract analysis/document classification → **Path 1 (DataSync → S3 → UC)** + Bedrock
- ACL audit → ONTAP REST API + Athena (can be outside UC)

**Governance/regulation**: Attorney-client privilege, document retention obligations, GDPR right to deletion.

**Caveats**: Apply strict UC access control to privileged documents. Permission-aware RAG requires NTFS ACL-respecting filtering (see [permission-aware RAG in the technical guide](./fsx-ontap-to-databricks-unity-catalog-guide.md)).

> For **litigation hold (evidence preservation)** when litigation is anticipated, data must be preserved immutably. SnapLock Compliance mode (cannot be deleted within retention even by admin) applies directly. For e-Discovery, make the **chain of custody** (who accessed/processed what and when) provable via UC audit logs.

---

### 15. Construction / AEC (Architecture-Engineering-Construction)

**Data characteristics**: BIM models (large 3D), drawings (CAD/PDF), site photos, drone inspection images, safety inspection records.

**Key use cases**:
- BIM version management: model versioning/diff analysis (repo UC10)
- Drawing OCR: text extraction/classification of drawings/specifications
- Safety compliance: AI safety inspection of site photos (PPE detection, etc.)
- Progress management: visualization of construction progress via drone aerial imagery

**FSx for ONTAP features used**:
- Scale-out performance: shared storage for large BIM models
- FlexClone: instant cloning of design versions
- Multiprotocol: same-data access for design tools (SMB) and analytics (S3 AP)

**Recommended path**:
- Drawing OCR/safety inspection → **Path 1 (DataSync → S3 → UC)** + Textract/Rekognition
- BIM metadata analysis → **Path 3 (Glue/EMR ETL → UC)**

**Governance/regulation**: Building codes/safety regulations, design deliverable rights, long-term preservation (building lifecycle).

**Caveats**: Do not replicate BIM models themselves (several GB+) into UC; keep them on FSx for ONTAP. UC manages metadata, inspection results, and progress metrics.

---

### 16. Education / Research

**Data characteristics**: Paper PDFs, research data, lecture videos, LMS logs, student data (PII).

**Key use cases**:
- Paper classification/citation analysis: classification of paper PDFs, citation network analysis (repo UC13)
- Research data management: classification/cataloging of experimental/observational data
- Learning analytics: learning behavior analysis from LMS logs, dropout prediction
- Academic search: RAG / semantic search of research documents

**FSx for ONTAP features used**:
- Multiprotocol: balance researcher NFS/SMB access with analytics
- FlexClone: reproducible clones of research datasets
- Storage efficiency: cost optimization of massive research data/videos

**Recommended path**:
- Paper classification/academic search → **Path 1 (DataSync → S3 → UC)** + Bedrock / AI Search
- Research data batch analysis → **Path 3 (Glue/EMR ETL → UC)**

**Governance/regulation**: Student PII (FERPA, etc.), research ethics/consent, research data publication/retention policies.

**Caveats**: Protect student PII via UC Column Masks. Reflect the balance between funder publication obligations (open science) and confidentiality in research data design.

---

### 17. Defense / Space

**Data characteristics**: Satellite imagery (large), sensor data, geospatial data, classified data. Most confidential, with strict access control.

**Key use cases**:
- Satellite imagery analysis: object detection, change detection, alerts (repo UC15)
- Geospatial intelligence: integrated analysis of multi-source data
- Sensor fusion: integration of multiple sensor data

**FSx for ONTAP features used**:
- Scale-out performance: processing of large satellite imagery
- SnapLock: tamper-proof retention of evidence data
- Encryption: at-rest/in-transit encryption of classified data

**Recommended path**:
- Satellite imagery batch analysis → **Path 3 (Glue/EMR ETL → UC)** + Rekognition/SageMaker
- Classified analysis → GovCloud + UC full governance + strict audit

**Governance/regulation**: ITAR/EAR (export control), DoD CC SRG, FedRAMP High, CSfC, classification levels.

**Caveats**: Classified data requires GovCloud + strict network isolation. Verify control plane location constraints (same as public sector). Reflect defense-in-depth and air-gap requirements in design.

---

### 18. Smart City

> An industry where data originates from edge sensors/cameras. Wide-area sensing of urban infrastructure.

**Data characteristics**: Geospatial data, urban sensors (traffic/environment/people flow), surveillance cameras, infrastructure IoT.

**Key use cases**:
- Geospatial analysis: CRS normalization, land use classification, disaster risk mapping (repo UC17)
- Traffic analysis: traffic volume/people flow analysis, signal optimization
- Environmental monitoring: air quality/noise/water quality sensing
- Disaster prevention: prediction/visualization of disaster risk

**FSx for ONTAP features used**:
- Multiprotocol: integration of diverse outputs from urban systems
- SnapMirror: aggregation/DR of dispersed site data

**Recommended path**:
- Urban sensor telemetry → **Path 2 (Kafka → Structured Streaming → UC)**
- Geospatial batch analysis → **Path 3 (Glue/EMR ETL → UC)**

**Governance/regulation**: Citizen PII (people flow/surveillance data), data sovereignty, INSPIRE Directive / OGC standards (geospatial).

**Caveats**: Perform non-identifying aggregation of people flow/surveillance data at the edge to protect privacy. Critical infrastructure (traffic/power) requires OT/IT separation (like energy, do not embed analytics in the control loop).

> Smart city data has governance tension between **open-data mandates** (publishing non-confidential data) and citizen privacy. Clearly separate public and confidential datasets in UC, and apply anonymization/aggregation before publication. Delta Sharing / clean rooms are effective for data linkage across multiple government agencies.

---

### 19. AdTech / Marketing

**Data characteristics**: Creative assets (images/videos), campaign data, distribution logs, brand guidelines.

**Key use cases**:
- Creative asset management: asset tagging/search (repo UC19)
- Brand compliance: brand guideline conformance checks of creatives
- Campaign analysis: distribution performance analysis, attribution
- Personalization: targeting optimization

**FSx for ONTAP features used**:
- Multiprotocol: balance production tools (SMB) with asset analytics
- FlexClone: version management of campaign assets
- Storage efficiency: cost optimization of massive creative assets

**Recommended path**:
- Asset tagging/brand check → **Path 1 (DataSync → S3 → UC)** + Rekognition/Bedrock
- Campaign analysis → **Path 1** + Databricks ML

**Governance/regulation**: Ad data PII (targeting), GDPR/cookie regulations, brand safety.

**Caveats**: Strictly govern personal data used for targeting via UC governance. Keep creative assets (videos) on FSx for ONTAP and manage metadata/tags in UC.

> With the deprecation of third-party cookies, ad measurement via first-party data and **data clean rooms** (Databricks Clean Rooms / AWS Clean Rooms) is becoming mainstream. Clean rooms enable privacy-preserving analysis across multiple parties (advertisers/publishers) without sharing raw PII. Also consider targeting fairness evaluation (bias detection).

---

### 20. Transportation / Rail

> An industry where data originates from edge sensors/cameras. Maintenance and inspection of equipment/vehicles.

**Data characteristics**: Equipment inspection images, vehicle sensors, maintenance reports, track/infrastructure inspection data.

**Key use cases**:
- Equipment inspection: AI analysis of track/vehicle/infrastructure inspection images (repo UC22)
- Predictive maintenance: failure prediction from vehicle/equipment sensors
- Maintenance report analysis: structuring/trend analysis of inspection records
- Safety management: safety analysis of operational data

**FSx for ONTAP features used**:
- Multiprotocol: balance maintenance system output with analytics
- Scale-out performance: ingestion of massive inspection images
- SnapLock: tamper-proof retention of safety records

**Recommended path**:
- Equipment inspection image AI → **Path 1 (DataSync → S3 → UC)** + Rekognition
- Vehicle sensor predictive maintenance → **Path 2 (Kafka → Structured Streaming → UC)**

**Governance/regulation**: Railway safety regulations, maintenance record retention obligations, operational data audit.

**Caveats**: Real-time control related to operational safety completes on the OT side (like energy, do not embed analytics in the control loop). UC analytics is positioned for predictive maintenance / trend insight.

> When data related to railway safety certification (SIL / EN 50128, etc.) forms the basis of a safety case, make the data **provenance** provable via UC lineage. Also, predictive maintenance false positives generate unnecessary maintenance costs, so combine model accuracy evaluation with human review of maintenance decisions.

---

### 21. Sustainability / ESG

**Data characteristics**: Energy usage, emissions data, supply chain data, ESG report documents, regulatory reporting data.

**Key use cases**:
- ESG metrics extraction: extraction/aggregation of ESG indicators from documents (repo UC23)
- Emissions calculation: calculation/reporting of Scope 1/2/3 emissions
- Supply chain ESG: ESG assessment of suppliers
- Regulatory reporting: CSRD / TCFD disclosure compliance

**FSx for ONTAP features used**:
- Multiprotocol: integration of diverse source data
- SnapLock: tamper-proof retention of regulatory reporting data

**Recommended path**:
- Metrics extraction from ESG documents → **Path 1 (DataSync → S3 → UC)** + Bedrock (`ai_parse_document`, etc.)
- Emissions aggregation → **Path 1** + Databricks (medallion)

**Governance/regulation**: CSRD (EU Corporate Sustainability Reporting Directive), TCFD, SEC climate disclosure, auditability of reporting data.

**Caveats**: ESG reporting is subject to audit. Make data provable "from source data to reported value" via UC lineage (like financial regulatory reporting).

> Scope 3 emissions are **external data** from suppliers, with varying data quality. Design data quality gates (distinguishing missing values, units, and estimates) and record estimates vs measured values distinctly in lineage. ESG data is increasingly subject to third-party assurance, requiring audit trails similar to financial audits. Delta Sharing / clean rooms are also options for acquiring supplier data.

---

### 22. Real Estate

**Data characteristics**: Property images, contracts, drawings, property metadata, market data.

**Key use cases**:
- Property image analysis: automatic classification/attribute extraction of property photos (repo UC26)
- Contract data extraction: structuring of contracts/disclosure statements
- Portfolio analysis: evaluation/optimization of property portfolios
- Market analysis: price prediction, demand analysis

**FSx for ONTAP features used**:
- Storage efficiency: cost optimization of massive property images
- Multiprotocol: balance property management system output with analytics

**Recommended path**:
- Property image analysis/contract extraction → **Path 1 (DataSync → S3 → UC)** + Rekognition/Textract
- Portfolio analysis → **Path 1** + Databricks ML

**Governance/regulation**: Customer PII, contract data retention, real estate transaction regulations.

**Caveats**: Protect customer PII / contract data via UC Column Masks.

---

### 23. Human Resources

**Data characteristics**: Resumes, HR documents, evaluation data, employee data (highly confidential PII).

**Key use cases**:
- Resume screening: resume classification/candidate evaluation (repo UC27)
- Talent matching: skill/requirement matching
- HR analytics: attrition prediction, engagement analysis

**FSx for ONTAP features used**:
- ONTAP REST API: strict access permission management of HR files
- SnapLock: HR records requiring legal retention

**Recommended path**:
- Resume screening → **Path 1 (DataSync → S3 → UC)** + Bedrock

**Governance/regulation**: Employee PII (GDPR / per-country labor laws), anti-discrimination in hiring (AI bias), strict retention of HR data.

**Caveats**: AI screening carries risks of hiring discrimination/bias. Make Databricks model governance (fairness evaluation) and human-in-the-loop final decisions mandatory. Apply the highest level of UC governance to employee PII.

---

### 24. Chemical / Materials

**Data characteristics**: SDS (safety data sheets), lab notebooks, experimental data, manufacturing records.

**Key use cases**:
- SDS management: management/classification of safety data sheets (repo UC28)
- Lab notebook analysis: structuring/search of experimental records
- Materials development: analysis of experimental data, materials exploration
- Regulatory compliance: chemical substance regulation compliance

**FSx for ONTAP features used**:
- Multiprotocol: balance lab system output with analytics
- SnapLock: tamper-proof retention of regulatory/experimental records
- FlexClone: reproducible clones of experimental datasets

**Recommended path**:
- SDS/lab notebook analysis → **Path 1 (DataSync → S3 → UC)** + Bedrock
- Materials data analysis → **Path 3 (Glue/EMR ETL → UC)**

**Governance/regulation**: Chemical substance regulations (REACH, GHS), SDS retention obligations, IP (material formulation) protection, GxP (for pharmaceutical materials).

**Caveats**: Material formulations are IP. Like semiconductor, keep design/formulation data itself on FSx for ONTAP and limit UC to analytics metadata.

---

### 25. Gaming

**Data characteristics**: Game assets (large), build artifacts, player logs, telemetry.

**Key use cases**:
- Game asset quality check: asset validation/quality analysis (repo FC6)
- Build pipeline: quality/log analysis of game builds
- Player analytics: behavior analysis, churn prediction, matchmaking optimization
- LiveOps: real-time telemetry analysis

**FSx for ONTAP features used**:
- FlexClone: instant cloning of build/asset versions
- Scale-out performance: shared storage for large assets
- FlexCache: asset sharing between distributed development sites

**Recommended path**:
- Asset quality/build analysis → **Path 1 (DataSync → S3 → UC)** or **Path 3 (Glue/EMR ETL)**
- Player telemetry → **Path 2 (Kafka → Structured Streaming → UC)**

**Governance/regulation**: Player PII, minor protection, payment data (PCI DSS).

**Caveats**: Keep game assets themselves on FSx for ONTAP. UC manages telemetry, quality metrics, and player analytics. Protect player PII via UC governance.

---

### 26. SAP / ERP-Adjacent

> Cross-industry enterprise core system integration patterns.

**Data characteristics**: IDoc, EDI, HULFT integration files, batch output, export data from core systems.

**Key use cases**:
- IDoc/EDI processing: processing/analysis of core system integration documents (repo SAP)
- Batch output analysis: ingestion of ERP batch output into analytics platform
- Master data integration: analysis of product/business partner master

**FSx for ONTAP features used**:
- High-performance storage: data store for SAP/Oracle/SQL Server ([**Public**](https://aws.amazon.com/blogs/industries/fsi-services-spotlight-featuring-amazon-fsx-for-netapp-ontap/))
- Snapshot/FlexClone: consistent backup of core DBs / test environment clones
- Multiprotocol: balance integration files (NFS/SMB) with analytics

**Recommended path**:
- Integration files/batch output → **Path 1 (DataSync → S3 → UC)**
- Core DB → UC Lakehouse Federation (PostgreSQL/Oracle/SQL Server, see [technical guide](./fsx-ontap-to-databricks-unity-catalog-guide.md)) or CDC (Debezium → Kafka → UC)

**Governance/regulation**: Core data integrity, financial data audit (SOX, etc.), master data governance.

**Caveats**: Writing to core systems is not possible via Lakehouse Federation (read-only). Design separately for reflecting analytics results back to core systems. For real-time reflection of master changes via CDC, use the Debezium → Kafka → UC pattern.

---

## Industry Data Classification and Governance Mapping

| Industry | Most Confidential Data | UC Governance Applied | Encryption Requirements | Audit Requirements |
|----------|----------------------|----------------------|------------------------|--------------------|
| Finance | Transaction records, PII | Column Masks + Row Filters + Lineage | WORM(SnapLock) + KMS | All access logged (BCBS 239) |
| Healthcare | ePHI, genome | Column Masks + anonymization | KMS + krb5p | HIPAA audit logs |
| Semiconductor | Design IP | Strict Access Control | KMS + export control | IP access tracking |
| Public Sector | Citizen PII, classified | Full governance | KMS + data sovereignty | All operations audited |
| Manufacturing/Automotive | Design, quality records | Tags + Row Filters | KMS | Traceability |
| Retail/Telecom | Customer PII, payment | Column Masks (PCI/PII) | KMS + tokenization | Access audit |
| Legal/HR | Privileged documents, employee PII | Strict Access Control + ONTAP REST API ACL | KMS + SnapLock(Compliance) | Chain of custody, all access audited |
| Agriculture/Logistics/Tourism/Transportation (edge) | Footage capturing people, location/PII | Edge aggregation (de-identification) + UC governance | KMS | Edge processing logs + UC audit |
| ESG/Sustainability | Scope 3 supplier data | Lineage (estimate vs measured) + third-party assurance | KMS | Audit trail (equivalent to financial audit) |

---

## Industry Connection Path Selection Guide

```
Q: What is your industry's data freshness requirement?
│
├── Real-time (seconds)
│     ├── Manufacturing/Energy/Transportation (OT telemetry) → Path 2 (Kafka via FPolicy)
│     ├── Finance (fraud detection) → Path 2 (Kafka)
│     └── Telecom (network monitoring) → Path 2 (Kafka)
│
├── Edge aggregation → cloud (edge inference + send aggregates)
│     ├── Agriculture (soil/drone) → edge (Greengrass) → Path 2 (Kafka)
│     ├── Logistics (warehouse CV <300ms) → edge inference → Path 2 (Kafka)
│     └── Tourism/Smart City (crowd/people flow) → edge aggregation → Path 2 (Kafka)
│
├── Near-real-time to batch (minutes to hours)
│     ├── Finance/Healthcare/Public/ESG (regulatory analytics) → Path 1 (DataSync) + UC full governance
│     ├── Retail/Tourism/Real Estate (forecasting/personalization) → Path 1 (DataSync) + ML
│     └── Automotive (connected vehicle) → Path 1 or 2 (mixed)
│
└── Large-scale batch transformation (hours to days)
      ├── Semiconductor/Media/Construction/Gaming (large volume) → Path 3 (Glue/EMR ETL)
      ├── Genomics → Path 3 (Glue/EMR)
      ├── Defense/Smart City (satellite/geospatial) → Path 3 (Glue/EMR) + geospatial
      └── Automotive ADAS dataset creation → Path 3 (Glue/EMR)

Document-centric industries (Legal/Education/HR/Chemical SDS/AdTech/SAP-EDI):
      → Path 1 (DataSync) + Bedrock/Textract (OCR, classification, extraction)
```

---

## Common Design Principles for Edge-Data Industries

In addition to manufacturing/automotive, **agriculture, logistics, tourism, smart city, and transportation** also generate data from edge devices (sensors/cameras). Common design principles:

| Principle | Detail |
|---|---|
| Infer/aggregate at the edge, analyze in the cloud | Due to low-bandwidth/low-latency requirements, perform primary processing at the edge (AWS IoT Greengrass / SageMaker Edge / on-prem CV appliances) and send only results/aggregates/representative data to the cloud |
| Avoid uploading all raw data | For bandwidth/cost/privacy reasons, transferring all raw footage/sensor streams to the cloud is not recommended |
| FSx for ONTAP as the IT-side aggregation point | The pattern edge → gateway → FSx for ONTAP (IT network) → DataSync/FPolicy → UC. Respect the OT/IT boundary |
| Privacy protection | For footage capturing people (logistics workers, tourism visitors, smart city citizens), perform non-identifying aggregation at the edge and process/discard raw footage at the edge |
| Separation from safety control | Safety control for transportation/energy/smart city completes on the OT side. Do not embed UC analytics in the control loop |
| Handling seasonality / demand fluctuation | For industries with large seasonal variation (agriculture: planting/harvest, tourism: peak seasons, retail: sale periods), plan FSx for ONTAP throughput for peaks or respond elastically with elastic throughput + S3 Intelligent-Tiering |

> **Note**: AWS Panorama reaches end-of-support in May 2026. Design edge CV with AWS IoT Greengrass + general-purpose cameras, or third-party edge appliances.

### Cross-Organization Data Sharing (Common Across Industries)

For industries requiring multi-party data utilization (multi-party collaboration in construction, supply chain, research consortia, multi-agency smart city, ESG Scope 3 suppliers, advertiser×publisher in advertising), mechanisms for governed collaboration without sharing raw data are effective:

> **After** ingesting data into UC, use Delta Sharing / OpenSharing (granting read access from provider storage to recipients, zero-copy sharing) for cross-org sharing. For analysis across multiple parties without sharing raw PII, Databricks Clean Rooms / AWS Clean Rooms are suitable (ad measurement, co-marketing, multi-site research, etc.). Both enable external sharing while maintaining UC governance (lineage, masks).

---

## Industry-Specific Phased Adoption Considerations

Adjust the technical guide's [Phased Adoption Steps](./fsx-ontap-to-databricks-unity-catalog-guide.md#phased-adoption-recommended-steps) per industry characteristics:

| Industry | Phase 1 Focus | Regulatory Gate | Notes |
|----------|--------------|----------------|-------|
| Finance/Healthcare/Public | Prioritize governance validation in PoC | Compliance audit before production | Data classification/masking from Phase 1 |
| Manufacturing/Automotive | Start from pilot line / single vehicle model | Approval at quality review | Design OT/IT boundary in Phase 1 |
| Semiconductor/Media | Analytics metadata only (do not replicate IP/assets) | IP/export control review | Lead with data volume estimation |
| Retail/Telecom | Validate PII masking in Phase 1 | PCI/privacy audit | Cost optimization of massive data |
| Agriculture/Logistics/Tourism/Transportation/Smart City (edge) | Validate edge inference + aggregation pipeline in Phase 1 | Privacy (footage) / safety-control separation review | Throughput planning for seasonal variation |
| Legal/HR/Chemical (documents/IP) | Access control + retention/IP protection in Phase 1 | Privilege/IP/export-control review | Document-centric: lead with OCR/extraction pipeline |

---

## Related Documents

| Document | Content |
|----------|---------|
| [FSx for ONTAP → Databricks UC Connection Guide](./fsx-ontap-to-databricks-unity-catalog-guide.md) | Technical detail of connection paths (technical basis for this catalog) |
| [DataSync → S3 Sync Guide](./datasync-to-s3-guide.md) | Path 1 detailed procedures |
| [Kafka-ClickHouse-UC Connectivity Guide](./kafka-clickhouse-unity-catalog-connectivity.md) | Path 2 technical detail |
| [S3 Annotations Governance Evaluation](./s3-annotations-governance-evaluation.md) | Metadata governance (traceability, etc.) |
| [Compatibility Matrix](./compatibility-matrix.md) | Platform-specific API support status |
| [Manufacturing Data Platform Integration](../../integrations/manufacturing-data-platform/) | Detailed manufacturing design |
| [FSx for ONTAP S3 Access Points Serverless Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) | Industry serverless automation pattern implementations (UC1-UC30, same author) |

---

## Disclaimer and Evidence Notes

- The use cases in this catalog are based on public reference architectures (Databricks/AWS/NetApp official) and general knowledge of industry-standard roles.
- No specific customer cases, company names, or confidential information are included. Citations are limited to public information (**Public**), with sources explicitly linked.
- Statements on regulatory requirements (HIPAA, BCBS 239, IATF 16949, etc.) are technical design considerations, **not legal/compliance judgments**. Confirmation by each organization's legal/compliance department is required.
- For connection path verification status, see the technical guide's [Verification Status Summary](./fsx-ontap-to-databricks-unity-catalog-guide.md#verification-status-summary).
