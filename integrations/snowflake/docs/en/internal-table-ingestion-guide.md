🌐 **English** | [日本語](../ja/internal-table-ingestion-guide.md)

# Internal Table Ingestion Guide — When COPY INTO Is Required

> **Status**: Architecture Reference — Based on validated results (May 2026)
>
> **Context**: FSx for ONTAP S3 Access Points work with Snowflake External Tables for zero-copy read access. However, many Snowflake features require data to be in **internal (managed) tables**. This guide documents which features require COPY INTO and the recommended ingestion patterns.

## Executive Summary

Snowflake External Tables on FSx for ONTAP S3 AP provide **governed zero-copy read access** — but they are read-only by design. Many advanced Snowflake capabilities (Cortex Search, Dynamic Tables, Time Travel, DML, clustering) require data to reside in internal tables.

This creates a **dual management challenge**: data lives on FSx for ONTAP (source of truth) and must be copied into Snowflake internal tables for full platform functionality.

### The AI-Ready Data Product Journey

The progression from raw NAS files to AI-ready data products in Snowflake follows a clear path:

```
FSx for ONTAP (raw files)
  ↓ S3 Access Point + AWS_ACCESS_POINT_ARN
External Table (zero-copy governed read)
  ↓ Cortex AI text functions work here (summarize, translate, sentiment)
  ↓
Dynamic Table (TARGET_LAG = '1 hour')
  ↓ Automated transformation + enrichment
  ↓ Cortex AI in SELECT clause (GA since Sep 2025)
  ↓
Cortex Search Service (semantic search / RAG)
  ↓ AI-ready data product
  ↓
Data Sharing / Data Product (governed distribution)
```

**Key insight**: You don't need to COPY INTO everything. Start with External Table for immediate AI value (Cortex text functions work on zero-copy data), then selectively promote high-value subsets to Dynamic Tables for Cortex Search and full platform capabilities.

### Key Principles

1. **External Table = zero-copy governed read** — no data movement, but limited functionality
2. **Internal Table = full Snowflake functionality** — requires COPY INTO (data duplication)
3. **Dynamic Table = the recommended bridge** — declarative, auto-managed, Cortex AI-native
4. **The goal is not "load everything"** — it's "create AI-ready data products from the most valuable subset"
5. **Sync is the challenge** — FSx for ONTAP S3 AP does not support S3 Event Notifications, so change detection requires polling or FPolicy

---

## Feature Availability: External Table vs Internal Table

### Cortex AI Functions

| Function | External Table | Internal Table | COPY INTO Required | Reference |
|----------|:---:|:---:|:---:|---|
| [CORTEX.SUMMARIZE](https://docs.snowflake.com/en/sql-reference/functions/summarize-snowflake-cortex) | ✅ | ✅ | No | Works on any text column |
| [CORTEX.TRANSLATE](https://docs.snowflake.com/en/sql-reference/functions/translate-snowflake-cortex) | ✅ | ✅ | No | Works on any text column |
| [CORTEX.SENTIMENT](https://docs.snowflake.com/en/sql-reference/functions/sentiment-snowflake-cortex) | ✅ | ✅ | No | Works on any text column |
| [CORTEX.EXTRACT_ANSWER](https://docs.snowflake.com/en/sql-reference/functions/extract_answer-snowflake-cortex) | ✅ | ✅ | No | Works on any text column |
| [CORTEX.COMPLETE](https://docs.snowflake.com/en/sql-reference/functions/complete-snowflake-cortex) (text) | ✅ | ✅ | No | Works on any text column |
| [CORTEX.COMPLETE](https://docs.snowflake.com/en/sql-reference/functions/complete-snowflake-cortex-multimodal) (multimodal/vision) | ❌ | ✅ | **Yes** | Requires TO_FILE on internal/managed stage |
| [PARSE_DOCUMENT](https://docs.snowflake.com/en/sql-reference/functions/parse_document) | ✅ | ✅ | No | Works with BUILD_SCOPED_FILE_URL on external stage |
| [Cortex Search Service](https://docs.snowflake.com/en/sql-reference/sql/create-cortex-search) | ❌ | ✅ | **Yes** | Source query must reference internal table or view on internal table |

### Data Management Features

| Feature | External Table | Internal Table | COPY INTO Required | Reference |
|---------|:---:|:---:|:---:|---|
| SELECT / Query | ✅ | ✅ | No | |
| DML (INSERT/UPDATE/DELETE/MERGE) | ❌ | ✅ | **Yes** | External tables are read-only |
| [Time Travel](https://docs.snowflake.com/en/user-guide/data-time-travel) | ❌ | ✅ | **Yes** | Requires internal table with DATA_RETENTION_TIME_IN_DAYS |
| [Fail-safe](https://docs.snowflake.com/en/user-guide/data-failsafe) | ❌ | ✅ | **Yes** | 7-day recovery after Time Travel expires |
| [Clustering](https://docs.snowflake.com/en/user-guide/tables-clustering-micropartitions) | ❌ | ✅ | **Yes** | Micro-partitions only on internal tables |
| [Search Optimization](https://docs.snowflake.com/en/user-guide/search-optimization-service) | ❌ | ✅ | **Yes** | Requires internal table |
| [Dynamic Tables](https://docs.snowflake.com/en/user-guide/dynamic-tables-intro) | ⚠️ Source only | ✅ | Partial | Can read from external table as source, output is internal |
| [Streams](https://docs.snowflake.com/en/user-guide/streams-intro) (CDC) | ❌ | ✅ | **Yes** | Not supported on external tables |
| [Tasks](https://docs.snowflake.com/en/user-guide/tasks-intro) | ✅ | ✅ | No | Can schedule COPY INTO or REFRESH |
| [Materialized Views](https://docs.snowflake.com/en/user-guide/views-materialized) | ✅ | ✅ | No | Can be created on external tables for performance |

### Governance Features

| Feature | External Table | Internal Table | COPY INTO Required | Reference |
|---------|:---:|:---:|:---:|---|
| [Object Tagging](https://docs.snowflake.com/en/user-guide/object-tagging) | ✅ | ✅ | No | Works on both |
| [Row Access Policies](https://docs.snowflake.com/en/user-guide/security-row-intro) | ✅ | ✅ | No | Works on both |
| [Column Masking](https://docs.snowflake.com/en/user-guide/security-column-intro) | ✅ | ✅ | No | Works on both |
| [Data Sharing](https://docs.snowflake.com/en/user-guide/data-sharing-intro) | ✅ | ✅ | No | External tables can be shared |
| [Access History](https://docs.snowflake.com/en/user-guide/access-history) | ✅ | ✅ | No | Tracked for both |

### File & Unstructured Data Features

| Feature | External Stage (FSx for ONTAP S3 AP) | Internal Stage | COPY INTO Required | Reference |
|---------|:---:|:---:|:---:|---|
| [LIST @stage](https://docs.snowflake.com/en/sql-reference/sql/list) | ✅ | ✅ | No | |
| [GET_PRESIGNED_URL](https://docs.snowflake.com/en/sql-reference/functions/get_presigned_url) | ✅ | ✅ | No | Works despite AWS docs saying "not supported" |
| [BUILD_SCOPED_FILE_URL](https://docs.snowflake.com/en/sql-reference/functions/build_scoped_file_url) | ✅ | ✅ | No | |
| [Directory Table](https://docs.snowflake.com/en/user-guide/data-load-dirtables) | ✅ | ✅ | No | ENABLE + REFRESH works on external stage |
| AUTO_REFRESH (Directory Table) | ❌ | ✅ | N/A | Requires S3 Event Notifications (not supported on FSx for ONTAP S3 AP) |
| [Snowpipe](https://docs.snowflake.com/en/user-guide/data-load-snowpipe-intro) (auto-ingest) | ❌ | N/A | N/A | Requires S3 Event Notifications |
| [TO_FILE](https://docs.snowflake.com/en/sql-reference/functions/to_file) (for multimodal AI) | ❌ | ✅ | **Yes** | Only works with internal/managed stage paths |

---

## The Dual Management Problem

```
FSx for ONTAP (NFS/SMB)          Snowflake Internal Table
   ┌─────────────────┐              ┌─────────────────┐
   │ Source of Truth  │──COPY INTO──▶│ Analytics Copy  │
   │ (multi-protocol) │              │ (full features) │
   └─────────────────┘              └─────────────────┘
         │                                   │
    Updated via NFS/SMB                 Requires sync
         │                                   │
    ▼ Challenges ▼                      ▼ Challenges ▼
  - No S3 Event Notifications        - Stale data risk
  - Change detection is polling       - Storage cost (Snowflake)
  - Deletes not propagated            - Compute cost (COPY INTO)
    automatically                     - Schema drift management
```

### Specific Challenges

| Challenge | Description | Mitigation |
|-----------|-------------|------------|
| **Change detection** | FSx for ONTAP S3 AP does not support S3 Event Notifications → cannot trigger Snowpipe | FPolicy → Lambda → SNS → Snowpipe REST API, or scheduled Task + COPY INTO |
| **Delete propagation** | COPY INTO is append-only; deleted files on FSx for ONTAP are not removed from internal table | Periodic full refresh, or MERGE with metadata comparison |
| **Schema evolution** | New columns in source files not automatically reflected | Use INFER_SCHEMA + ALTER TABLE, or recreate table |
| **Data freshness** | Polling interval determines lag | FPolicy for near-real-time, Task for scheduled |
| **Cost** | Snowflake storage + compute for COPY INTO execution | Use transient tables for non-critical data; compress source files |

---

## Recommended Ingestion Patterns

### Pattern 1: Scheduled COPY INTO (Simplest)

Best for: Batch analytics, daily/hourly refresh acceptable.

```sql
-- Create target internal table
CREATE OR REPLACE TABLE sensor_data (
  device_id STRING,
  timestamp TIMESTAMP,
  temperature FLOAT,
  humidity FLOAT
) DATA_RETENTION_TIME_IN_DAYS = 7;

-- Scheduled Task: COPY INTO every hour
CREATE OR REPLACE TASK copy_sensor_data
  WAREHOUSE = COMPUTE_WH
  SCHEDULE = '60 MINUTE'
AS
  COPY INTO sensor_data
  FROM @fsxn_stage/bronze/sensor/
  FILE_FORMAT = (TYPE = PARQUET)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = CONTINUE;
```

Reference: [COPY INTO](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table), [Tasks](https://docs.snowflake.com/en/user-guide/tasks-intro)

### Pattern 2: FPolicy → Lambda → Snowpipe REST API (Near Real-Time)

Best for: Event-driven ingestion, minutes-level latency.

```
FSx for ONTAP (file created/modified)
  ↓ FPolicy notification
AWS Lambda (event processor)
  ↓ Snowpipe REST API call (insertFiles)
Snowflake Snowpipe (COPY INTO internal table)
  ↓
Internal table (available for Cortex Search, DML, etc.)
```

```sql
-- Create Snowpipe (triggered via REST API, not auto-ingest)
CREATE OR REPLACE PIPE fsxn_sensor_pipe
AS
  COPY INTO sensor_data
  FROM @fsxn_stage/bronze/sensor/
  FILE_FORMAT = (TYPE = PARQUET)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
```

Reference: [Snowpipe REST API](https://docs.snowflake.com/en/user-guide/data-load-snowpipe-rest-apis), [FPolicy](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html)

### Pattern 3: Dynamic Table (Automated Transformation) — Recommended

Best for: Continuous transformation pipeline from external table source. **This is the most Snowflake-native approach** — declarative, auto-managed, and supports Cortex AI functions in the SELECT clause (GA since September 2025).

> **Support Confirmed (May 2026, Snowflake support case)**: Dynamic Tables with External Table source are supported with `REFRESH_MODE = FULL`. Minimum `TARGET_LAG` is 60 seconds. Incremental refresh is not available because External Tables do not support change tracking.

```sql
-- Dynamic Table reads from External Table, materializes as internal
CREATE OR REPLACE DYNAMIC TABLE sensor_enriched
  TARGET_LAG = '1 hour'
  WAREHOUSE = COMPUTE_WH
AS
  SELECT
    device_id,
    timestamp,
    temperature,
    humidity,
    SNOWFLAKE.CORTEX.SENTIMENT(notes) AS sentiment_score,
    CURRENT_TIMESTAMP() AS enriched_at
  FROM sensor_external_table
  WHERE timestamp > DATEADD(day, -30, CURRENT_TIMESTAMP());
```

Reference: [Dynamic Tables](https://docs.snowflake.com/en/user-guide/dynamic-tables-intro)

> **Note**: Dynamic Tables can use external tables as source (full refresh mode). Incremental refresh requires change tracking, which is not available on external tables.

> **Important**: Since FSx for ONTAP S3 AP does not support AUTO_REFRESH, you must manually refresh the External Table metadata before the Dynamic Table can see new files. Use a Task to automate this:
> ```sql
> -- Task to refresh External Table metadata every 5 minutes
> CREATE OR REPLACE TASK refresh_fsxn_external_table
>   WAREHOUSE = COMPUTE_WH
>   SCHEDULE = '5 MINUTE'
> AS
>   ALTER EXTERNAL TABLE sensor_external_table REFRESH;
> ```
> The Dynamic Table will then pick up new data on its next refresh cycle (based on TARGET_LAG).

> **TARGET_LAG sizing, from the runs in this repository**:
> - **60 seconds** (minimum): Only for small datasets or critical alerting. Each refresh re-reads the entire External Table.
> - **5 minutes**: Near-real-time monitoring. Acceptable cost for medium datasets (GB-level).
> - **1 hour** (recommended starting point): Batch analytics, daily reporting. Cost-efficient for large datasets.
> - **1 day**: Cortex Search Service source, weekly reporting. Lowest cost.

> **Why Dynamic Table is recommended over COPY INTO + Task**:
> - **Declarative**: Define TARGET_LAG (e.g., '1 hour') and Snowflake manages the refresh schedule automatically
> - **Cortex AI integration**: Use CORTEX.SUMMARIZE, CORTEX.SENTIMENT, etc. directly in the Dynamic Table SELECT clause (GA since [September 2025](https://docs.snowflake.com/en/release-notes/2025/other/2025-09-11-dynamic-tables-cortex-aisql-support))
> - **No operational overhead**: No Task scheduling, no COPY INTO deduplication logic, no manual error handling
> - **Chaining**: Dynamic Tables can reference other Dynamic Tables for multi-stage pipelines (Bronze → Silver → Gold)

### Pattern 4: COPY INTO + Cortex Search (RAG Pipeline)

Best for: Semantic search over FSx for ONTAP documents.

```sql
-- Step 1: COPY INTO internal table from external stage
CREATE OR REPLACE TABLE documents (
  file_path STRING,
  content STRING,
  file_type STRING,
  ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

COPY INTO documents (file_path, content, file_type)
FROM (
  SELECT
    METADATA$FILENAME,
    $1::STRING,
    SPLIT_PART(METADATA$FILENAME, '.', -1)
  FROM @fsxn_stage/bronze/documents/
)
FILE_FORMAT = (TYPE = CSV FIELD_DELIMITER = NONE RECORD_DELIMITER = NONE)
ON_ERROR = CONTINUE;

-- Step 2: Create Cortex Search Service on internal table
CREATE OR REPLACE CORTEX SEARCH SERVICE document_search
  ON content
  ATTRIBUTES file_type
  WAREHOUSE = COMPUTE_WH
  TARGET_LAG = '1 day'
AS (
  SELECT content, file_path, file_type
  FROM documents
);
```

Reference: [CREATE CORTEX SEARCH SERVICE](https://docs.snowflake.com/en/sql-reference/sql/create-cortex-search), [COPY INTO](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table)

### Pattern 5: Multimodal AI (Vision) on Internal Stage

Best for: Image/document analysis with LLM vision models.

```sql
-- Step 1: Copy files to internal stage (required for TO_FILE)
COPY FILES
  INTO @internal_media_stage
  FROM @fsxn_stage/media/images/;

-- Step 2: Use COMPLETE (multimodal) with TO_FILE
SELECT
  RELATIVE_PATH AS file_name,
  SNOWFLAKE.CORTEX.COMPLETE(
    'claude-3-5-sonnet',
    'Describe this image in detail',
    TO_FILE(@internal_media_stage, RELATIVE_PATH)
  ) AS description
FROM DIRECTORY(@internal_media_stage)
WHERE RELATIVE_PATH LIKE '%.png' OR RELATIVE_PATH LIKE '%.jpg';
```

Reference: [COMPLETE (multimodal)](https://docs.snowflake.com/en/sql-reference/functions/complete-snowflake-cortex-multimodal), [TO_FILE](https://docs.snowflake.com/en/sql-reference/functions/to_file)

---

## What Works WITHOUT COPY INTO (Zero-Copy on External Table)

These operations work directly on FSx for ONTAP S3 AP External Tables — no data movement needed:

| Operation | Example | Performance |
|-----------|---------|-------------|
| Ad-hoc SQL queries | `SELECT * FROM ext_table WHERE date > '2026-01-01'` | Moderate (no micro-partitions) |
| Text AI functions | `SELECT CORTEX.SUMMARIZE(text_col) FROM ext_table` | Good |
| Governance tags | `ALTER TABLE ext_table SET TAG sensitivity = 'internal'` | Instant |
| Row access policies | `ALTER TABLE ext_table ADD ROW ACCESS POLICY ...` | Instant |
| Column masking | `ALTER TABLE ext_table MODIFY COLUMN ssn SET MASKING POLICY ...` | Instant |
| Materialized views | `CREATE MATERIALIZED VIEW mv AS SELECT ... FROM ext_table` | Improves query perf |
| Data sharing | `GRANT SELECT ON ext_table TO SHARE ...` | Instant |
| Presigned URLs | `SELECT GET_PRESIGNED_URL(@stage, path) FROM dir_table` | Fast |
| Document parsing | `SELECT PARSE_DOCUMENT(BUILD_SCOPED_FILE_URL(@stage, path))` | ~8s/doc |

---

## Decision Framework

**Quick decision table** — find your requirement and follow the recommendation:

| Your requirement | Answer | Data movement |
|---|---|---|
| "I just need SQL queries" | → External Table (zero-copy) | None |
| "I need text AI (summarize, translate, sentiment)" | → External Table (zero-copy) | None |
| "I need governance tags and masking" | → External Table (zero-copy) | None |
| "I need Cortex Search / RAG" | → Dynamic Table or COPY INTO | Full copy |
| "I need Vision AI (image analysis)" | → COPY FILES to internal stage | File copy |
| "I need DML (INSERT/UPDATE/DELETE)" | → COPY INTO internal table | Full copy |
| "I need Time Travel" | → COPY INTO internal table | Full copy |
| "I need high-performance queries (clustering)" | → COPY INTO internal table | Full copy |

**Detailed flowchart:**

```
                    ┌─────────────────────────┐
                    │ What do you need?       │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
    ┌─────────▼─────────┐ ┌─────▼─────┐ ┌─────────▼─────────┐
    │ Read-only SQL +   │ │ RAG /     │ │ DML / Time Travel │
    │ basic AI + govern │ │ Cortex    │ │ / clustering /    │
    │                   │ │ Search    │ │ multimodal AI     │
    └─────────┬─────────┘ └─────┬─────┘ └─────────┬─────────┘
              │                  │                  │
    ┌─────────▼─────────┐ ┌─────▼─────┐ ┌─────────▼─────────┐
    │ External Table    │ │ COPY INTO │ │ COPY INTO         │
    │ (zero-copy)       │ │ + Cortex  │ │ internal table    │
    │                   │ │ Search    │ │                   │
    └───────────────────┘ └───────────┘ └───────────────────┘
```

| Requirement | Recommended Path | Data Movement |
|---|---|---|
| Ad-hoc analytics, reporting | External Table | None (zero-copy) |
| Governed read with tags/masking | External Table | None |
| Text summarization, translation, sentiment | External Table | None |
| Document parsing (OCR) | External Stage + PARSE_DOCUMENT | None |
| Semantic search (RAG) | COPY INTO → Cortex Search Service | Full copy |
| Image/video analysis (multimodal) | COPY FILES to internal stage → COMPLETE | Full copy |
| DML (INSERT/UPDATE/DELETE/MERGE) | COPY INTO internal table | Full copy |
| Time Travel / point-in-time recovery | COPY INTO internal table | Full copy |
| High-performance queries (clustering) | COPY INTO internal table | Full copy |
| CDC / Streams | COPY INTO internal table | Full copy |

---

## Industry Use Case Examples

| Industry | Data on FSx for ONTAP | Zero-copy path (External Table) | AI-ready path (Dynamic Table → Cortex) |
|----------|---|---|---|
| **Manufacturing** | Sensor logs, inspection images, quality reports | Ad-hoc quality queries, governance tags on sensitive data | Cortex Search for "find similar defects", sentiment on operator notes |
| **Financial services** | Contract PDFs, transaction logs, regulatory filings | Compliance queries, row access policies by department | Cortex Search for contract clause retrieval, SUMMARIZE for audit prep |
| **Healthcare** | De-identified research data, imaging metadata | Research queries with column masking on PII | PARSE_DOCUMENT for clinical notes, Cortex Search for literature review |
| **Retail** | POS data, customer feedback, product catalogs | Sales analytics, governance tags by region | SENTIMENT on customer reviews, TRANSLATE for global markets |

> **Partner positioning**: "Start with External Table for immediate governed analytics (zero cost, zero data movement). When the customer sees value, promote high-value subsets to Dynamic Tables for Cortex AI. This is not a migration — it's progressive AI-ready data product creation."

---

## Cost Considerations

| Component | External Table Path | COPY INTO Path |
|-----------|---|---|
| FSx for ONTAP storage | ✅ (source of truth) | ✅ (source of truth) |
| Snowflake storage | None | Additional (internal table) |
| Snowflake compute (query) | Per-query | Per-query |
| Snowflake compute (COPY INTO) | None | Periodic ingestion cost |
| Data freshness | Real-time (direct read) | Polling interval lag |
| Operational complexity | Low | Medium (sync logic needed) |

**Cost optimization tips:**
- Use [transient tables](https://docs.snowflake.com/en/user-guide/tables-temp-transient) for non-critical data (no Fail-safe cost)
- Set appropriate `DATA_RETENTION_TIME_IN_DAYS` (1 day vs 90 days)
- Use `MATCH_BY_COLUMN_NAME` in COPY INTO to handle schema evolution
- Compress source files (Parquet recommended over CSV)
- Use `PURGE = TRUE` in COPY INTO if source files can be cleaned up

---

## Next Steps

1. **Create your first External Table**: Follow the [Configuration Guide](../../README.md#internal-table-vs-external-table--design-guide) — set `AWS_ACCESS_POINT_ARN` on your stage and create an External Table
2. **For RAG / Cortex Search**: Set up a Dynamic Table with `TARGET_LAG = '1 hour'` on your External Table source, then create a Cortex Search Service
3. **For event-driven ingestion**: Deploy FPolicy → Lambda → Snowpipe REST API ([Snowpipe Integration Guide](snowpipe-integration.md))
4. **For multi-platform sharing (Iceberg)**: Use Snowflake Managed Iceberg Tables to write curated datasets in open Iceberg format to customer-owned S3 — accessible by Databricks, Athena, EMR, and Trino without additional copies

---

## Future: Managed Iceberg as the Open Format Bridge

> **Support Confirmed (May 2026)**: COPY INTO from External Stage (with `AWS_ACCESS_POINT_ARN`) to Snowflake Managed Iceberg Table is supported. This validates the FSx for ONTAP → S3 AP → Snowflake Managed Iceberg pipeline.

Snowflake [Managed Iceberg Tables](https://docs.snowflake.com/en/user-guide/tables-iceberg) write data in open Apache Iceberg format to customer-owned S3 storage. This enables a multi-platform architecture:

```
FSx for ONTAP (source of truth)
  ↓ S3 AP (zero-copy read) or DataSync (sync to S3)
Snowflake Managed Iceberg Table (curated, governed)
  ↓ Open Iceberg format on customer-owned S3
  ├── Databricks UC (read Iceberg)
  ├── AWS Athena / Glue (read Iceberg via Glue Catalog)
  ├── EMR Spark (read/write Iceberg)
  └── Trino (read Iceberg)
```

**Key benefits**:
- **No vendor lock-in**: Data is in open Iceberg format, owned by the customer
- **Snowflake manages lifecycle**: OPTIMIZE, Time Travel, governance tags — without proprietary format
- **Multi-engine access**: Same curated dataset readable by all Iceberg-compatible engines
- **ONTAP remains source of truth**: Only high-value curated subsets are promoted to Iceberg

> **Note**: This pattern requires data to be on standard S3 (not FSx for ONTAP S3 AP directly) for the Iceberg write path. Use DataSync to sync relevant subsets from FSx for ONTAP to S3, then manage as Iceberg tables in Snowflake.

---

## References

- [COPY INTO <table>](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table) — Load data from stage to table
- [External Tables](https://docs.snowflake.com/en/user-guide/tables-external-intro) — Read-only tables on external storage
- [Cortex AI Functions](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions) — LLM functions overview
- [CREATE CORTEX SEARCH SERVICE](https://docs.snowflake.com/en/sql-reference/sql/create-cortex-search) — Semantic search
- [COMPLETE (multimodal)](https://docs.snowflake.com/en/sql-reference/functions/complete-snowflake-cortex-multimodal) — Vision/image AI
- [Dynamic Tables](https://docs.snowflake.com/en/user-guide/dynamic-tables-intro) — Automated transformation
- [Snowpipe REST API](https://docs.snowflake.com/en/user-guide/data-load-snowpipe-rest-apis) — Programmatic ingestion trigger
- [FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) — AWS documentation

---

## Related Documents

- [Snowflake README](../../README.md) — Full integration status
- [Analytics & AI Demo Guide](ai-demo-guide.md) — AI/ML capabilities and validation results
- [Blocker Tracker](../../../../docs/en/blocker-tracker.md) — BLK-009 records the unload behaviour on an Access Point, including the partial-write hazard
