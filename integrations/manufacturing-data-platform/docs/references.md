# Research References

> All sources collected during technical research for the manufacturing data platform PoC.
> Last updated: 2026-06-07

## Kafka → Databricks Integration

| # | Title | Source | URL | Accessed | Summary | Relevance |
|---|-------|--------|-----|----------|---------|-----------|
| REF-001 | Using Unity Catalog with Structured Streaming | Databricks Docs | https://docs.databricks.com/aws/structured-streaming/unity-catalog | 2026-06-07 | Confirms Structured Streaming can write to Unity Catalog-governed managed and external tables. Supports Delta Lake and Apache Iceberg formats. | Critical - validates Kafka→UC path |
| REF-002 | Delta table streaming reads and writes | Databricks Docs | https://docs.databricks.com/structured-streaming/delta.html | 2026-06-07 | Delta Lake transaction log guarantees exactly-once processing even with concurrent streams or batch queries. | Critical - confirms exactly-once semantics |
| REF-003 | Connect to Apache Kafka | Databricks Docs | https://docs.databricks.com/aws/en/connect/streaming/kafka | 2026-06-07 | Official guide for connecting Databricks Structured Streaming to Kafka. Supports startingOffsets, SSL/SASL auth, schema registry. | Critical - primary ingestion pattern |
| REF-004 | Kafka to Delta With Exactly-Once Guarantees | DZone | https://dzone.com/articles/streaming-optimization-kafka-delta | 2026-06-07 | End-to-end exactly-once fault tolerance with Spark Structured Streaming and Delta Lake. Covers checkpointing, failure recovery. | High - production pattern validation |
| REF-005 | Confluent Tableflow GA: Delta Lake & Unity Catalog | Confluent/BusinessWire | https://www.businesswire.com/news/home/20251029878892/en/ | 2026-06-07 | GA announcement (Oct 2025) for Confluent Tableflow with Delta Lake and Unity Catalog integrations. Automatically materializes Kafka topics into Delta tables. | High - managed alternative to custom streaming |
| REF-006 | Databricks Delta Lake Sink Connector | Confluent Docs | https://docs.confluent.io/kafka-connectors/databricks-delta-lake-sink/current/overview.html | 2026-06-07 | Confluent connector that stages Kafka data in S3 then commits to Databricks Delta Lake. | Medium - alternative ingestion approach |
| REF-007 | A Real-time Open Lakehouse with Redpanda and Databricks | Databricks Blog | https://www.databricks.com/blog/real-time-open-lakehouse-redpanda-and-databricks | 2026-06-07 | Kafka streams into Unity Catalog-managed Iceberg tables in one step. Real-time lakehouse without custom ETL. | High - validates streaming→UC pattern |
| REF-008 | Data Ingestion Reference Architecture | Databricks | https://www.databricks.com/resources/architectures/data-ingestion-reference-architecture | 2026-06-07 | Official reference architecture supporting batch, CDC, and streaming ingestion with Unity Catalog governance. | High - canonical architecture reference |

## ClickHouse → Databricks Integration

| # | Title | Source | URL | Accessed | Summary | Relevance |
|---|-------|--------|-----|----------|---------|-----------|
| REF-010 | Integrating ClickHouse with Databricks | ClickHouse Docs | https://clickhouse.com/docs/en/integrations/data-ingestion/apache-spark/databricks | 2026-06-07 | Official guide for ClickHouse Spark connector on Databricks. Covers platform-specific setup and usage patterns. | Critical - primary integration method |
| REF-011 | Spark ClickHouse Connector (Native) | ClickHouse Docs | https://clickhouse.com/docs/en/integrations/apache-spark/spark-native-connector | 2026-06-07 | Supports Catalog API and TableProvider API. Enables read/write between Spark and ClickHouse. | Critical - connector capabilities |
| REF-012 | Spark JDBC with ClickHouse | ClickHouse Docs | https://clickhouse.com/docs/integrations/apache-spark/spark-jdbc | 2026-06-07 | JDBC as alternative data source in Spark for ClickHouse. Common but less performant than native connector. | Medium - fallback approach |
| REF-013 | spark-clickhouse-connector (GitHub) | Housepower/GitHub | https://github.com/housepower/spark-clickhouse-connector/ | 2026-06-07 | Open-source Spark ClickHouse Connector built on DataSourceV2 API. Community-maintained. | Medium - OSS alternative |
| REF-014 | How to Integrate ClickHouse and Databricks | hoop.dev | https://hoop.dev/blog/how-to-integrate-clickhouse-and-databricks-for-fast-trustworthy-analytics/ | 2026-06-07 | Integration patterns: JDBC, ODBC, REST. Databricks controls compute; ClickHouse serves as high-speed warehouse. | Medium - architecture patterns |

## Unity Catalog & Storage

| # | Title | Source | URL | Accessed | Summary | Relevance |
|---|-------|--------|-----|----------|---------|-----------|
| REF-020 | Connect to cloud object storage using Unity Catalog | Databricks Docs | https://docs.databricks.com/aws/connect/storage/ | 2026-06-07 | Supported storage: Amazon S3, Cloudflare R2. Only native cloud storage supported for external locations. | Critical - confirms no S3-compatible support |
| REF-021 | Create a storage credential and external location for S3 | Databricks Docs | https://docs.databricks.com/aws/en/connect/unity-catalog/cloud-storage/s3/s3-external-location-manual | 2026-06-07 | Requires S3 bucket + IAM role. No mention of S3-compatible endpoints. Bucket dots not supported. | Critical - external location limitations |
| REF-022 | Connecting S3-compatible endpoint (MinIO) to Unity Catalog | Databricks Community | https://community.databricks.com/t5/data-engineering/connecting-an-s3-compatible-endpoint-such-as-minio-to-unity/td-p/144802 | 2026-06-07 | Community thread confirming S3-compatible endpoints are NOT supported by Unity Catalog external locations. | Critical - confirms limitation |
| REF-023 | Set Up Unity Catalog with External Storage | Databricks DevHub | https://developers.databricks.com/templates/unity-catalog-setup | 2026-06-07 | Template requires S3 bucket and IAM role in same AWS account and region. | High - deployment requirements |
| REF-024 | External Tables in Unity Catalog | Databricks Docs | https://docs.databricks.com/en/sql/language-manual/sql-ref-external-tables.html | 2026-06-07 | External tables store files in cloud object storage within user's cloud tenant. UC manages metadata but not data lifecycle. | High - table type understanding |

## ClickHouse + Kafka + Manufacturing

| # | Title | Source | URL | Accessed | Summary | Relevance |
|---|-------|--------|-----|----------|---------|-----------|
| REF-030 | Critical Manufacturing uses ClickHouse for factory floor analytics | ClickHouse Blog | https://clickhouse.com/blog/criticial-manufacturing | 2026-06-07 | Real-world case: SQL Server→ClickHouse migration. Kafka-based ingestion, real-time dashboards, sub-second queries on billions of events. | Critical - manufacturing reference |
| REF-031 | Building a Real-Time Data Platform: Kafka + ClickHouse | Medium | https://medium.com/@awaissattar/building-a-real-time-data-platform-kafka-kafka-connect-kafka-streams-clickhouse-1f483386bf1b | 2026-06-07 | Architecture overview: Kafka as streaming backbone, ClickHouse as analytics database. Production patterns. | High - architecture validation |
| REF-032 | Real-time AI-assisted analytics at the industrial edge (EMQ) | ClickHouse Blog | https://clickhouse.com/blog/emq-ai-assisted-analytics | 2026-06-07 | MQTT-based industrial IoT platform → ClickHouse Cloud. High-throughput ingestion, sub-second queries, 1000+ enterprise customers. | Critical - edge/IoT reference |
| REF-033 | Apache Kafka as Data Historian (IIoT/Industry 4.0) | kai-waehner.de | https://www.kai-waehner.de/blog/2020/04/21/apache-kafka-as-data-historian-an-iiot-industry-4-0-real-time-data-lake/ | 2026-06-07 | Kafka replacing traditional data historians in manufacturing. Digital twin, OEE, real-time data lake concepts. | High - industry context |
| REF-034 | Real-time Event Streaming with ClickHouse and Confluent Cloud | ClickHouse Blog | https://clickhouse.com/blog/real-time-event-streaming-with-kafka-connect-confluent-cloud-clickhouse | 2026-06-07 | Kafka Connect integration with ClickHouse. Simplified architecture using ClickPipes. | Medium - ingestion patterns |

## ClickHouse Deployment & Storage

| # | Title | Source | URL | Accessed | Summary | Relevance |
|---|-------|--------|-----|----------|---------|-----------|
| REF-040 | ClickHouse BYOC on AWS (GA) | ClickHouse Blog | https://clickhouse.com/blog/announcing-general-availability-of-clickhouse-bring-your-own-cloud-on-aws | 2026-06-07 | GA announcement for ClickHouse BYOC. Deploys in customer's AWS VPC. Uses EKS, EC2, S3. | High - deployment option |
| REF-041 | ClickHouse Deployment Options | ClickHouse Docs | https://clickhouse.com/docs/infrastructure/deployment-options | 2026-06-07 | Options: ClickHouse Cloud, BYOC, self-managed. BYOC bridges managed and self-managed. | High - deployment decisions |
| REF-042 | Integrating S3 with ClickHouse (Tiered Storage) | ClickHouse Docs | https://clickhouse.com/docs/en/integrations/s3 | 2026-06-07 | S3 as cold storage tier. S3BackedMergeTree. Supports S3-compatible endpoints. Data Lake architecture patterns. | Critical - tiering to FSx for ONTAP S3 |
| REF-043 | Separation of Storage and Compute | ClickHouse Docs | https://clickhouse.com/docs/guides/separation-storage-compute | 2026-06-07 | S3BackedMergeTree for cold data. Less critical query performance on cold data. | High - architecture pattern |
| REF-044 | ClickHouse Cluster on AWS (Solution) | AWS Solutions | https://aws.amazon.com/solutions/implementations/clickhouse-cluster/ | 2026-06-07 | AWS reference implementation: EC2 instances + ZooKeeper + ELB. | Medium - self-managed option |
| REF-045 | ClickHouse Cloud on AWS (Partner) | ClickHouse/AWS | https://clickhouse.com/partners/aws | 2026-06-07 | Fully managed service on AWS. Available in AWS Marketplace. Graviton-optimized. | High - managed option |

## FSx for ONTAP

| # | Title | Source | URL | Accessed | Summary | Relevance |
|---|-------|--------|-----|----------|---------|-----------|
| REF-050 | Amazon FSx for ONTAP S3 access (announcement) | AWS What's New | https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-fsx-netapp-ontap-s3-access/ | 2026-06-07 | Dec 2025 announcement: S3 Access Points for FSx for ONTAP. Enables S3 API access to ONTAP volumes. | High - multiprotocol capability |
| REF-051 | Accessing data via Amazon S3 access points | AWS Docs | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html | 2026-06-07 | S3 access points attach to FSx for ONTAP volumes. Simplifies data access for S3-compatible applications. | High - technical details |
| REF-052 | Bridge legacy and modern applications with S3 Access Points for FSx | AWS Blog | https://aws.amazon.com/blogs/storage/bridge-legacy-and-modern-applications-with-amazon-s3-access-points-for-amazon-fsx/ | 2026-06-07 | Multi-protocol access without data duplication. Concurrent file and object access. | High - use case validation |
| REF-053 | AI insights with ONTAP and S3 Access Points | NetApp Blog | https://www.netapp.com/blog/ai-insights-ontap-s3-access-points-dremio/ | 2026-06-07 | Manufacturing quality data on NFS + analytics via S3. Real-world use case described. | High - manufacturing context |

## Confluent + Databricks Partnership

| # | Title | Source | URL | Accessed | Summary | Relevance |
|---|-------|--------|-----|----------|---------|-----------|
| REF-060 | Confluent and Databricks Partner for Real-Time AI | Yahoo Finance | https://nz.finance.yahoo.com/news/confluent-databricks-partner-usher-age-210400133.html | 2026-06-07 | Partnership for bi-directional Tableflow↔Unity Catalog integration. Governs data across operational and analytical systems. | High - ecosystem validation |
| REF-061 | Building AI-Ready Tables with Tableflow and Unity Catalog | Confluent Current | https://current.confluent.io/post-conference-videos-25/ | 2026-06-07 | Tableflow automatically materializes Kafka topics into Delta tables, registers with Unity Catalog. No custom streaming pipelines needed. | High - managed approach |


## Instaclustr (NetApp) — On-Premises and Managed Services

| # | Title | Source | URL | Accessed | Summary | Relevance |
|---|-------|--------|-----|----------|---------|-----------|
| REF-070 | Understanding NetApp Instaclustr architectures, part 3: Running Instaclustr workloads on-premises | Instaclustr Blog | https://www.instaclustr.com/blog/understanding-netapp-instaclustr-architectures-part-3-running-instaclustr-workloads-on-premises/ | 2026-06-07 | Describes how Instaclustr deploys and manages workloads on customer-provided on-premises infrastructure. | Critical — validates on-prem managed Kafka + ClickHouse |
| REF-071 | On-Premises Solution | Instaclustr | https://www.instaclustr.com/platform/private-on-prem/ | 2026-06-07 | Instaclustr Managed Platform supports on-prem deployment. 300M+ node hours under management. AWS/GCP/Azure/On-prem. | Critical — confirms on-prem availability |
| REF-072 | Instaclustr for ClickHouse (Private Preview) | Instaclustr Blog | https://www.instaclustr.com/blog/instaclustr-for-clickhouse-now-in-private-preview/ | 2026-06-07 | NetApp launches Instaclustr for ClickHouse on managed platform. Available in Private Preview. | High — ClickHouse managed by same vendor as ONTAP |
| REF-073 | How FSx for ONTAP and Managed ClickHouse enhance lakehouse analytics | Instaclustr Blog | https://www.instaclustr.com/blog/how-fsx-for-netapp-ontap-and-managed-clickhouse-enhance-lakehouse-analytics/ | 2026-06-07 | Architecture pattern: FSx for ONTAP as lakehouse storage + Instaclustr ClickHouse for analytics. Direct validation of this project's architecture. | Critical — exact architecture match |
| REF-074 | Amazon Q + ClickHouse + Kafka + ONTAP integration | Instaclustr Resource | https://www.instaclustr.com/resources/get-key-insights-when-integrating-amazon-q-with-clickhouse-apache-kafka-and-netapp-ontap/ | 2026-06-07 | Integration of real-time Kafka streams + ONTAP historical data + ClickHouse analytics + AI (Amazon Q). | High — AI analytics path validation |
| REF-075 | Managed Apache Kafka | Instaclustr | https://www.instaclustr.com/solutions/managed-apache-kafka/ | 2026-06-07 | Fully managed Kafka clusters on AWS/GCP/Azure and on-premises. Terraform provisioning. Kafka Connect bundled. | High — on-prem Kafka managed service |
| REF-076 | ClickHouse Kafka Connect Sink Connector | Instaclustr Docs | https://www.instaclustr.com/support/documentation/kafka-connect/bundled-kafka-connect-plugins/clickhouse-kafka-connect-sink/ | 2026-06-07 | Bundled ClickHouse sink connector for Kafka Connect on Instaclustr platform. | High — Kafka→ClickHouse connector option |
| REF-077 | Understanding NetApp Instaclustr architectures, part 1: Running workloads in NetApp accounts | Instaclustr Blog | https://www.instaclustr.com/blog/understanding-netapp-instaclustr-architectures-part-1-running-workloads-in-netapp-accounts/ | 2026-06-07 | Fully managed approach: workloads in NetApp-owned cloud accounts. | Medium — Phase A alternative |
| REF-078 | Streaming analytics pipeline with Terraform and Instaclustr | Instaclustr Blog | https://www.instaclustr.com/blog/how-to-build-a-streaming-analytics-pipeline-with-terraform-and-instaclustr-part-1-setting-up-your-first-kafka-cluster | 2026-06-07 | Step-by-step guide for Kafka cluster setup via Terraform on Instaclustr. | High — deployment procedure reference |

## Edge Project Integration

| # | Title | Source | URL | Accessed | Summary | Relevance |
|---|-------|--------|-----|----------|---------|-----------|
| REF-080 | ontap-edge-to-cloud-ai | GitHub (Yoshiki0705) | https://github.com/Yoshiki0705/ONTAP-Edge-to-Cloud-AI | 2026-06-07 | Separate project for edge devices (Raspberry Pi) that will merge with this platform. | Critical — convergence target |


## FlexCache — On-Demand Caching (No Data Duplication)

| # | Title | Source | URL | Accessed | Summary | Relevance |
|---|-------|--------|-----|----------|---------|-----------|
| REF-090 | Replicating your data with FlexCache | AWS Docs | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html | 2026-06-07 | FlexCache brings datasets closer to clients without full replication. Remote caching capability of ONTAP. | Critical — primary data connectivity mechanism |
| REF-091 | FlexCache write-back mode GA (May 2025) | AWS What's New | https://aws.amazon.com/about-aws/whats-new/2025/05/amazon-fsx-netapp-ontap-write-back-mode-ontap-flexcache-volumes | 2026-06-07 | Write-back mode caches writes locally and asynchronously updates origin. Reduces write latency. | High — enables bidirectional workflow |
| REF-092 | Caching data using Amazon FSx for ONTAP | AWS Blog | https://aws.amazon.com/de/blogs/storage/caching-data-using-amazon-fsx-for-netapp-ontap/ | 2026-06-07 | FlexCache volumes cache data from remote ONTAP volumes. Origin can be on-premises NetApp system. | Critical — confirms on-prem origin → cloud cache pattern |
| REF-093 | ONTAP FlexCache volumes documentation | NetApp Docs | https://docs.netapp.com/us-en/ontap/flexcache | 2026-06-07 | FlexCache transitions workloads to hybrid cloud by caching on-prem data in cloud. Removes cloud silos. | High — architecture rationale |
| REF-094 | Creating a FlexCache on FSx for ONTAP | AWS Docs | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/create-flexcache.html | 2026-06-07 | Step-by-step for creating FlexCache backed by on-premises ONTAP origin. | High — implementation guide |
| REF-095 | FlexCache for data locality in AWS WorkSpaces | NetApp Tech Blog | https://community.netapp.com/t5/Tech-ONTAP-Blogs/Accelerating-Remote-Work-Harnessing-FlexCache-in-AWS-WorkSpaces-for-Data/ba-p/451852 | 2026-06-07 | FlexCache for optimal data placement in multi-regional deployments. Performance across distributed environments. | Medium — architectural pattern reference |


## Edge Buffering and Store-and-Forward

| # | Title | Source | URL | Accessed | Summary | Relevance |
|---|-------|--------|-----|----------|---------|-----------|
| REF-100 | Buffering Production Data During Network Outages (Store-and-Forward) | FlowFuse Blog | https://flowfuse.com/blog/2025/11/store-and-forward-edge-data-buffering/ | 2026-06-07 | Store-and-forward pattern: write to local SQLite first, forward when network available. | Critical — exact pattern used in ADR-008 |
| REF-101 | MQTT Store and Forward Overview | Chariot IoT Docs | https://docs.chariot.io/display/CLD83/MQTT+Store+and+Forward+Overview | 2026-06-07 | MQTT store-and-forward buffers data locally when MQTT server connections are down. Critical for avoiding data loss. | High — MQTT layer buffering validation |
| REF-102 | Introducing ReplayQ, EMQX's Buffer Layer | EMQX Blog | https://www.emqx.com/en/blog/introducing-replayq | 2026-06-07 | EMQX ReplayQ provides persistent buffering for Kafka bridge during network disruptions. | Medium — alternative commercial approach |
| REF-103 | EMQX Kafka Data Bridge | EMQX Docs | https://docs.emqx.com/en/emqx/latest/data-integration/data-bridge-kafka.md | 2026-06-07 | MQTT to Kafka bridge with SASL/SCRAM authentication. Bi-directional data integration. | High — MQTT→Kafka bridge reference |
| REF-104 | Building an IIoT Platform with Open Source Tools | ExpertBeacon | https://expertbeacon.com/building-an-industrial-iot-platform-with-open-source-tools/ | 2026-06-07 | Raspberry Pi as gateway with MQTT broker for buffering. MiNiFi agents for forwarding. | High — Raspberry Pi edge architecture |
| REF-105 | Kafka Producer Retries and Idempotence | Conduktor Learn | https://docs.conduktor.io/learn/advanced/producers/retries | 2026-06-07 | Kafka producer automatic retry for retryable errors. Idempotent producer prevents duplicates. | Critical — Kafka producer config reference |
| REF-106 | Kafka Producer Best Practices: acks, Offsets, Idempotence | ActiveWizards | https://activewizards.com/blog/kafka-producer-and-consumer-best-practices | 2026-06-07 | Best practices for acks, idempotence, retries, partitioning. Misconfiguration leads to data loss or duplicates. | High — production configuration guide |
